"""Deterministic social policy: affinity tier, topic gate, refusal and deltas.

The models write the prose; this module decides what the relationship and the topic
allow before the prose is written. It is intentionally network-free so a blocked turn
never depends on a second model call, and every refusal is reproducible.

The policy is authored in `world/social.json`: topic keywords, tier ceilings, per-character
deflection/refusal lines (English and Chinese), and the relationship deltas.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from switch_world.domain import protocol as _protocol
from world_engine import config
from world_engine.service import WorldService

POLICY_PATH = Path(config.CONTENT_ROOT) / "social.json"
CJK = re.compile(r"[一-鿿]")
TOPIC_LABELS = ["small talk", "daily life", "private feelings", "body or appearance", "physical contact"]

# Switch emits these while it boots an agent session. They are not in-character
# replies; a line made only of one is treated as no reply at all.
PLACEHOLDERS = (
    "starting a session to handle this",
    "starting a session",
    "starting a new session",
    "session is starting",
)

# A line made only of ellipses is a model's "no reply" placeholder, not dialogue.
ELLIPSIS_ONLY = re.compile(r"^[\s.…]+$")


def _is_placeholder_line(line: str) -> bool:
    """True when the line is a Switch placeholder or only an ellipsis."""
    if not line.strip():
        return True
    if any(marker in line.lower() for marker in PLACEHOLDERS):
        return True
    return bool(ELLIPSIS_ONLY.fullmatch(line))

# Live models occasionally leak the room's addressing grammar into the scene:
# a literal "@user", an "@director" aside, or a line about not being online.
# None of that is in-character, so the line is dropped before it is recorded.
# Keep these as literal substrings only when the phrase cannot occur in a real line.
META_LINE_MARKERS = (
    "@user",
    "@director",
    "the user",
    "as an ai",
    "i'm an ai",
    "i am an ai",
    "stage direction",
    "system prompt",
    "mention the policy",
    "discuss the policy",
    "talk about the policy",
    "following instructions",
    "following the instructions",
    "just a character",
    "only a character",
    # A character never returns code, a local path, or an agent's tool log.
    "```",
    "/users/",
    "tool calls",
    "tool call",
    "worked for",
    "**working",
    "world__remember",
    "world__update_relationship",
    "mcp__",
)

# Absence/availability phrases are anchored to first person and (for "here"/"in this
# room") to the end of the line, so ordinary in-scene lines such as
# "I'm not here to judge you." or "The card reader is offline again." survive.
META_LINE_PATTERNS = (
    re.compile(
        r"\b(?:i'?m|i am|i'?ll|i will|we'?re|we are|we'?ll|we will)\s+"
        r"(?:currently\s+)?(?:(?:be|going|to|staying|stay)\s+){0,3}off-?\s?line\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i'?m|i am|we'?re|we are)\s+not\s+(?:currently\s+)?online\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:i|we)\s+(?:need|have|got)\s+to\s+(?:leave|go)\b", re.IGNORECASE),
    re.compile(r"\b(?:i|we)\s+(?:need|have)\s+to\s+get\s+going\b", re.IGNORECASE),
    re.compile(
        r"\b(?:i(?:'m| am)|we(?:'re| are))\s+not\s+(?:online\s+)?(?:in this room|here)"
        r"(?:\s+right now)?\s*[.!?]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i|we)(?:'m| am|'re| are)?\s+(?:cannot|can't|can not)\s+be here"
        r"(?:\s+right now)?\s*[.!?]*\s*$",
        re.IGNORECASE,
    ),
)


def _is_meta_line(line: str) -> bool:
    lowered = line.lower()
    if any(marker in lowered for marker in META_LINE_MARKERS):
        return True
    return any(pattern.search(line) for pattern in META_LINE_PATTERNS)


def _strip_meta(text: str) -> str:
    """Drop whole lines that are stage machinery rather than a character's line.

    A fenced code block is dropped as a block: an agent that reached for a tool
    can return a shell command whose fence markers sit on their own lines, and
    the inner lines carry no marker of their own.
    """
    kept: list[str] = []
    in_fence = False
    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or _is_meta_line(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def clean_scene_line(text: str | None) -> str:
    """Drop Switch placeholders and stage machinery; "" means there is no real line."""
    text = _strip_meta(text)
    kept = [
        line
        for line in (text or "").splitlines()
        if not _is_placeholder_line(line) and not _is_meta_line(line)
    ]
    return "\n".join(kept).strip()

# Action mode separates what the player *does as themselves* from what they *attempt
# on an NPC*. An attempt is never auto-success; it always earns a response from the
# spectrum below. `continue` and `wait` are deliberate non-moves.
ACTION_MODES = _protocol.ACTION_MODES
RESPONSES = _protocol.RESPONSE_MODES

CONTINUE_MARKERS = (
    "continue", "go on", "keep going", "carry on", "next", "接着", "继续", "往下",
)
WAIT_MARKERS = (
    "wait", "hold on", "one moment", "just a moment", "pause", "give me a second",
    "等等", "等一下", "稍等", "慢着",
)
# Verbs that reach for an outcome on someone else. The target test below keeps
# "I hug my knees" as a result while "I hug you" is an attempt.
ATTEMPT_MARKERS = (
    "kiss", "hug", "embrace", "touch", "grab", "pull", "push", "pin", "straddle",
    "hold your hand", "hold her hand", "hold my hand", "take your hand",
    "take her hand", "take my hand", "put my arm", "put your arm", "arm around",
    "sit on my lap", "sit on your lap", "sit next to me", "sit beside me",
    "come with me", "come here", "follow me", "walk with me", "dance with",
    "lead you", "lift your", "lift her", "remove your", "take off your",
    "give", "hand", "offer", "show", "buy", "bring",
    "undress", "seduce", "persuade", "convince", "ask you out", "ask her out",
    "confess", "propose", "marry", "kiss me", "touch me", "hold me", "抱", "亲",
    "吻", "牵", "摸", "搂", "抓", "掀", "坐我腿上",
)
NPC_TARGETS = re.compile(
    r"\b(?:you|your|yours|yourself|alice|emily|sophia|mia|her|him|them)\b"
)
IMPERATIVE_ATTEMPT = re.compile(
    r"^\s*(?:please\s+)?(?:hold|kiss|hug|touch|take|grab|pull|push|give|hand|"
    r"show|come|sit|dance|follow|marry|tell|ask|lead|bring|put)\b",
    re.I,
)


def _has_attempt_target(text: str, addressee: str | None) -> bool:
    """True when the attempt is aimed at someone else, not at the player's own body.

    "hold my hand" and "kiss me" are imperatives aimed at the NPC; "I hug my knees"
    is the player's own result.
    """
    if addressee:
        return True
    if re.search(r"[你妳]", text or ""):
        return True
    if NPC_TARGETS.search(text or ""):
        return True
    return bool(IMPERATIVE_ATTEMPT.match((text or "").strip()))


def _action_mode(text: str, addressee: str | None = None) -> str:
    """Classify the player's move: own result, attempt on an NPC, continue, or wait."""
    raw = (text or "").strip()
    lowered = raw.lower()
    if not lowered:
        return "wait"
    if _matches(lowered, list(CONTINUE_MARKERS)):
        return "continue"
    if _matches(lowered, list(WAIT_MARKERS)):
        return "wait"
    if _matches(lowered, list(ATTEMPT_MARKERS)) and _has_attempt_target(raw, addressee):
        return "attempt"
    return "result"


def load() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def affinity(service: WorldService, character: str) -> dict:
    """The same number the dashboard's five hearts use."""
    edge = service.relationship(character, "user")
    score = _clamp((float(edge["trust"]) + float(edge["closeness"])) / 2 - float(edge["tension"]) / 2)
    stars = max(0, min(5, int(round(score * 5))))
    tiers = load()["tiers"]
    tier = next((item for item in tiers if int(item["stars"]) == stars), tiers[-1])
    return {
        "score": score,
        "stars": stars,
        "label": tier["label"],
        "ceiling": int(tier["ceiling"]),
        "trust": float(edge["trust"]),
        "closeness": float(edge["closeness"]),
        "tension": float(edge["tension"]),
    }


def _matches(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    for keyword in keywords:
        needle = keyword.lower()
        if needle.isascii():
            if re.search(r"\b" + re.escape(needle) + r"\b", lowered):
                return True
        elif needle in lowered:
            return True
    return False


def classify(text: str) -> dict:
    """Topic tier, addressee and whether the line is a physical action or consent ask."""
    policy = load()
    lowered = (text or "").lower()
    topic = {"id": "small-talk", "tier": 0, "label": "small talk"}
    for candidate in policy["topics"]:
        if _matches(lowered, candidate["keywords"]):
            if int(candidate["tier"]) > int(topic["tier"]):
                topic = candidate
    addressee = None
    mention = re.search(r"@([a-zA-Z]+)", text or "")
    if mention and mention.group(1).lower() in policy["characters"]:
        addressee = mention.group(1).lower()
    consent = _matches(
        lowered,
        ["may i", "can i", "would you mind", "do you want me to", "可以吗", "能不能", "愿意", "可以亲", "可以抱"],
    )
    forced = _matches(
        lowered,
        ["force", "grab", "lift", "without asking", "强", "掀", "抓", "摸", "搂"],
    )
    boundary = "none"
    tier = int(topic["tier"])
    if tier == 4:
        # A verbal request ("kiss me") is an attempt, not a boundary violation. Only
        # coercion/force is a violation; the affinity ladder decides the response.
        boundary = "violation" if forced else "flirt"
    return {
        "topic": topic["id"],
        "tier": tier,
        "topic_label": topic["label"],
        "addressee": addressee,
        "consent_ask": consent,
        "boundary": boundary,
        "forced": forced,
        "action_mode": _action_mode(text, addressee),
    }


def _response_for(stance: str, action_mode: str, tier: int, ceiling: int) -> str:
    """Map the topic stance onto the NPC response spectrum.

    The stance remains the gate; the response says *how* the character handles the
    player's move inside that gate. A refusal is a normal outcome, not an error.
    """
    if stance in {"hard_refuse", "refuse"}:
        return "refuse"
    if stance == "negotiate":
        return "negotiate"
    if stance == "limited":
        return "limited"
    if stance == "deflect":
        return "negotiate" if action_mode == "attempt" else "surface"
    if action_mode == "attempt":
        return "limited"
    if stance == "tease":
        return "limited" if tier >= max(1, ceiling) else "surface"
    return "sincere"


def appraise(
    service: WorldService,
    character: str,
    text: str,
    public: bool = False,
) -> dict:
    state = affinity(service, character)
    classified = classify(text)
    tier = int(classified["tier"])
    ceiling = int(state["ceiling"])
    # Public is more guarded, except for a tasteful appearance/body compliment at
    # Close (4 stars): that is the "contract" tier, where she may flirt a little and
    # still set the limit. Lower affinity still drops a tier in public.
    if public and tier >= 2 and not (classified["topic"] == "body" and state["stars"] >= 4):
        ceiling -= 1
    if state["tension"] >= 0.35:
        ceiling -= 1
    ceiling = max(0, min(4, ceiling))

    fade = False
    if tier == 4:
        if classified.get("forced"):
            stance = "hard_refuse"
            boundary = "violation"
        elif state["stars"] >= 5:
            # Intimate: any consensual contact is allowed, but the public build fades
            # before the explicit scene and describes the aftermath.
            stance = "tease"
            boundary = "consented"
            fade = True
        elif state["stars"] == 4:
            # Close: contact is not refused; allow a limited version and name the limit.
            stance = "limited"
            boundary = "flirt" if classified["boundary"] != "violation" else "violation"
        elif state["stars"] == 3:
            # Warming: negotiate, with visible shyness.
            stance = "negotiate"
            boundary = "flirt" if classified["boundary"] != "violation" else "violation"
        elif classified["boundary"] == "violation":
            # A direct uninvited kiss/touch at one or two hearts is a boundary cut.
            stance = "hard_refuse"
            boundary = "violation"
        else:
            stance = "refuse"
            boundary = "none"
    elif tier == 3:
        if state["stars"] >= 4:
            stance = "tease"
        elif state["stars"] == 3:
            stance = "negotiate"
        elif state["stars"] == 2:
            stance = "deflect"
        else:
            stance = "refuse"
        boundary = "none"
    elif tier > ceiling + 1:
        stance = "refuse"
        boundary = "none"
    elif tier == ceiling + 1:
        stance = "deflect"
        boundary = "none"
    else:
        stance = "tease" if tier >= 3 else "answer"
        boundary = "none"

    reason = (
        f"{classified['topic_label']} (tier {tier}) vs ceiling {ceiling} "
        f"({state['label']}, {state['stars']}/5)"
    )
    return {
        **state,
        **classified,
        "ceiling": ceiling,
        "stance": stance,
        "response": _response_for(
            stance, str(classified.get("action_mode")), tier, ceiling
        ),
        "boundary": boundary,
        "fade": fade,
        "reason": reason,
        "public": public,
    }


def relationship_block(service: WorldService, character: str) -> str:
    state = affinity(service, character)
    stars = state["stars"]
    if stars >= 5:
        open_text = (
            "small talk, daily life, private feelings, body/appearance, and consensual "
            "physical affection; you are intimate and may be openly warm"
        )
        limit_text = "explicit scenes fade before they happen; the aftermath is enough"
    elif stars == 4:
        open_text = (
            "small talk, daily life, private feelings, body/appearance, and a limited, "
            "tasteful amount of physical affection; you are close"
        )
        limit_text = (
            "a brief public kiss or hug is welcome; you set the pace and can be shy or "
            "flustered, but do not flat-refuse"
        )
    elif stars == 3:
        open_text = "small talk, daily life and private feelings"
        limit_text = (
            "body/appearance and contact are negotiable with shyness; ask for a condition "
            "or a smaller step rather than refusing"
        )
    elif stars == 2:
        open_text = "small talk and daily life"
        limit_text = "body/appearance and contact are not open yet; deflect kindly"
    else:
        open_text = "small talk"
        limit_text = "body/appearance and contact are not open yet; decline gently"
    return (
        f"Your relationship with the user right now: trust {state['trust']:.2f} · "
        f"closeness {state['closeness']:.2f} · tension {state['tension']:.2f} → "
        f"{state['label']} ({stars}/5).\n"
        f"Open with them: {open_text}.\n"
        f"Boundary: {limit_text}.\n"
        "Do not mention this scale, these rules, or the fact that you have a policy."
    )


def policy_block(verdict: dict) -> str:
    stance = verdict["stance"]
    if stance in {"answer", "tease"}:
        return (
            f"Social policy: this is {verdict['topic_label']} (tier {verdict['tier']}); "
            f"your ceiling is {verdict['ceiling']}. You may answer directly in your own voice. "
            "Do not mention the policy."
        )
    if stance == "deflect":
        return (
            "Social policy: this is too intimate for where you are with the user. Do not answer "
            "the question. Deflect in one or two sentences, in your own voice, and do not lecture. "
            "Do not mention the policy."
        )
    if stance == "negotiate":
        return (
            "Social policy: this is close to your limit, but not a flat no. Offer a condition, "
            "ask for a smaller step, and let the shyness show; do not answer explicitly in "
            "public. One or two sentences. Do not lecture and do not mention the policy."
        )
    if stance == "limited":
        return (
            "Social policy: you are close enough to allow this. Do not flat-refuse and do "
            "not deflect. A brief public kiss or hug is fine if it is tender; be warm, a "
            "little shy or flustered, and name one playful limit. One or two sentences. Do "
            "not render explicit content and do not mention the policy."
        )
    if stance == "refuse":
        return (
            "Social policy: this is outside what you will discuss with the user. Do not answer. "
            "Refuse briefly in your own voice; you may change the subject. Do not lecture and do "
            "not mention the policy."
        )
    return (
        "Social policy: the user has crossed a physical boundary without consent. Do not comply, "
        "do not romanticize it, and do not describe the act. React with a clear refusal; you may "
        "leave. One or two sentences. Do not mention the policy."
    )


RESPONSE_BLOCKS = {
    "refuse": (
        "Response spectrum — refuse: decline clearly in one or two sentences, in your own "
        "voice. A refusal is a complete, normal answer; you do not owe a reason."
    ),
    "negotiate": (
        "Response spectrum — negotiate: you are not giving a flat yes. Name your condition, "
        "ask for something first, or offer a smaller version. Keep it one or two sentences."
    ),
    "limited": (
        "Response spectrum — limited: allow part of what was asked, not all of it. Be warm "
        "or dry in your own voice, but hold the line you are holding."
    ),
    "surface": (
        "Response spectrum — surface: stay on the surface. A light, social answer; do not "
        "open a private topic or over-share."
    ),
    "sincere": (
        "Response spectrum — sincere: answer honestly and directly. One concrete detail, "
        "no performance."
    ),
}

ACTION_BLOCKS = {
    "result": (
        "Action mode — result: the user described their own speech, body or belongings. "
        "React to it; do not narrate the user's action for them."
    ),
    "attempt": (
        "Action mode — attempt: the user is trying something that affects you. This is an "
        "attempt, never an automatic success. Decide for yourself and answer from the "
        "response spectrum: you may refuse, negotiate, allow only part, or respond sincerely. "
        "Never narrate the outcome as already done."
    ),
    "continue": (
        "Action mode — continue: the user is asking the scene to move on. Pick up the "
        "current thread in your own voice; do not restart the conversation."
    ),
    "wait": (
        "Action mode — wait: the user is holding the moment. Keep the beat short; do not "
        "invent a new topic or a new action for them."
    ),
}


def response_block(verdict: dict) -> str:
    response = verdict.get("response") or "sincere"
    return RESPONSE_BLOCKS.get(response, RESPONSE_BLOCKS["sincere"])


def action_block(verdict: dict) -> str:
    mode = verdict.get("action_mode") or "result"
    return ACTION_BLOCKS.get(mode, ACTION_BLOCKS["result"])


def fade_block(verdict: dict) -> str:
    if not verdict.get("fade"):
        return ""
    return (
        "The relationship is intimate and the contact is consensual. Do not render an "
        "explicit scene: cut before it, time-skip, and describe the aftermath in one or two "
        "sentences. All characters are adults."
    )


REFUSAL = re.compile(
    r"\b(?:pretend|not going to|won'?t|will not|don'?t|do not|not here|weather|"
    r"not now|ask me later|absolutely not)\b",
    re.I,
)


def looks_like_refusal(reply: str) -> bool:
    return bool(REFUSAL.search(reply or ""))


def limited_line(character: str, verdict: dict, message: str) -> str:
    policy = load()
    lines = policy["characters"].get(character, {})
    zh = bool(CJK.search(message or ""))
    return (
        lines.get("limited_zh" if zh else "limited")
        or lines.get("limited")
        or "A little. Not all of it."
    )


def deflection(character: str, verdict: dict, message: str) -> str:
    policy = load()
    lines = policy["characters"].get(character, {})
    if verdict["stance"] == "limited":
        return limited_line(character, verdict, message)
    key = "hard_refuse" if verdict["stance"] == "hard_refuse" else (
        "refuse" if verdict["stance"] == "refuse" else "deflect"
    )
    zh = bool(CJK.search(message or ""))
    return lines.get(key + "_zh" if zh else key) or lines.get(key) or "No."


def contains_leak(reply: str, verdict: dict) -> bool:
    """A refusal that still names the forbidden topic is a leak, not a refusal."""
    if verdict["stance"] not in {"deflect", "refuse", "hard_refuse", "negotiate", "limited"}:
        return False
    if verdict["topic"] not in {"body", "contact"}:
        return False
    policy = load()
    topic = next((item for item in policy["topics"] if item["id"] == verdict["topic"]), None)
    if not topic:
        return False
    keywords = list(topic["keywords"])
    if verdict["topic"] == "body":
        keywords += [
            "black", "white", "red", "blue", "pink", "green", "lace", "cotton", "silk",
            "黑色", "白色", "红色", "蓝色", "粉色", "蕾丝",
        ]
    return _matches(reply or "", keywords)


def apply_deltas(service: WorldService, character: str, verdict: dict) -> dict | None:
    policy = load()
    deltas = policy["deltas"].get(verdict["stance"], {})
    if not deltas:
        return None
    return service.update_relationship(
        character,
        "user",
        trust_delta=float(deltas.get("trust", 0)),
        closeness_delta=float(deltas.get("closeness", 0)),
        tension_delta=float(deltas.get("tension", 0)),
        reason=f"social: {verdict['reason']} → {verdict['stance']}",
    )


def record_verdict(service: WorldService, character: str, verdict: dict) -> dict:
    return service.record_event(
        "director",
        "social_verdict",
        f"Social: {character} · {verdict['reason']} → {verdict['stance']}.",
        participants=[character],
        visibility="public",
    )
