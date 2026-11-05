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

from world_engine import config
from world_engine.service import WorldService

POLICY_PATH = Path(config.ROOT) / "world" / "social.json"
CJK = re.compile(r"[一-鿿]")
TOPIC_LABELS = ["small talk", "daily life", "private feelings", "body or appearance", "physical contact"]


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
    imperative = _matches(
        lowered,
        ["kiss me", "touch me", "hold me", "亲我", "吻我", "抱我", "亲一下"],
    )
    boundary = "none"
    tier = int(topic["tier"])
    if tier == 4:
        boundary = "violation" if (forced or imperative) and not consent else "flirt"
    return {
        "topic": topic["id"],
        "tier": tier,
        "topic_label": topic["label"],
        "addressee": addressee,
        "consent_ask": consent,
        "boundary": boundary,
    }


def appraise(
    service: WorldService,
    character: str,
    text: str,
    public: bool = False,
) -> dict:
    policy = load()
    state = affinity(service, character)
    classified = classify(text)
    tier = int(classified["tier"])
    ceiling = int(state["ceiling"])
    if public and tier >= 2:
        ceiling -= 1
    if state["tension"] >= 0.35:
        ceiling -= 1
    ceiling = max(0, min(4, ceiling))

    if tier == 4 and classified["boundary"] == "violation":
        stance = "hard_refuse"
        boundary = "violation"
    elif tier == 4:
        boundary = classified["boundary"]
        stance = "tease" if ceiling >= 4 else ("deflect" if ceiling >= 3 else "refuse")
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
        "boundary": boundary,
        "reason": reason,
        "public": public,
    }


def relationship_block(service: WorldService, character: str) -> str:
    state = affinity(service, character)
    ceiling = state["ceiling"]
    open_labels = TOPIC_LABELS[: ceiling + 1]
    closed_labels = TOPIC_LABELS[ceiling + 1 :]
    open_text = ", ".join(open_labels) or "small talk"
    closed_text = ", ".join(closed_labels) or "nothing specific"
    return (
        f"Your relationship with the user right now: trust {state['trust']:.2f} · "
        f"closeness {state['closeness']:.2f} · tension {state['tension']:.2f} → "
        f"{state['label']} ({state['stars']}/5).\n"
        f"Open with them: {open_text}. Not yet: {closed_text}.\n"
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


def deflection(character: str, verdict: dict, message: str) -> str:
    policy = load()
    lines = policy["characters"].get(character, {})
    key = "hard_refuse" if verdict["stance"] == "hard_refuse" else (
        "refuse" if verdict["stance"] == "refuse" else "deflect"
    )
    zh = bool(CJK.search(message or ""))
    return lines.get(key + "_zh" if zh else key) or lines.get(key) or "No."


def contains_leak(reply: str, verdict: dict) -> bool:
    """A refusal that still names the forbidden topic is a leak, not a refusal."""
    if verdict["stance"] not in {"deflect", "refuse", "hard_refuse"}:
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
