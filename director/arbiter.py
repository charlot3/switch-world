"""A second, slower opinion for body/contact turns.

The deterministic social ladder in `director.social` remains authoritative. This module
adds one bounded, high-reasoning model call only when a turn is about the body or physical
contact: the place where a fast model most often misreads warmth, consent, or a limit.

The arbiter never writes the character's prose and can never make a response more
permissive than `social.appraise` already allowed. It can only keep the same stance or
become more cautious, and it supplies a short tone/limit hint for the character prompt.
If the call is slow, unavailable, or malformed, the deterministic verdict is used without
comment.
"""
from __future__ import annotations

import os
import time

from world_engine.service import WorldService

from . import social

CONTACT_TOPICS = {"body", "contact"}
ALLOWED_STANCES = {
    "hard_refuse", "refuse", "negotiate", "limited", "deflect", "tease", "answer",
}
# Lower is more cautious. The arbiter may move down this scale but never up.
STANCE_RANK = {
    "hard_refuse": 0,
    "refuse": 1,
    "negotiate": 2,
    "limited": 3,
    "deflect": 4,
    "answer": 5,
    "sincere": 5,
    "surface": 5,
    "tease": 6,
}
ALLOWED_TONES = {"warm", "shy", "firm", "playful", "concerned", "neutral"}
DEFAULT_TIMEOUT = 6.0


def enabled() -> bool:
    return os.environ.get("WORLD_ARBITER", "0").strip().lower() in {
        "1", "true", "on", "yes",
    }


def should_arbitrate(verdict: dict) -> bool:
    """True only for a non-coercive body/contact turn.

    A forced action already has a hard boundary cut; spending a slower call there would
    delay the safety response without changing it.
    """
    if not verdict:
        return False
    if verdict.get("topic") not in CONTACT_TOPICS:
        return False
    if verdict.get("forced"):
        return False
    return verdict.get("stance") != "hard_refuse"


def _messages(service: WorldService, character: str, message: str, verdict: dict) -> list[dict]:
    state = social.affinity(service, character)
    system = (
        "You are an off-stage social director for a 17+ SFW interactive story. "
        "You do not write dialogue. The deterministic policy is authoritative: "
        f"stance={verdict.get('stance')}, response={verdict.get('response')}, "
        f"topic={verdict.get('topic')}, boundary={verdict.get('boundary')}. "
        "Check that this handling fits the relationship and the public setting. "
        "You may keep the stance or become more cautious, never more permissive. "
        "Never invent explicit content, never move a scene toward sex, and never "
        "override a refusal. Return one compact JSON object only."
    )
    user = (
        f"Character: {character}\n"
        f"Affinity: {state.get('stars')}/5 ({state.get('label')})\n"
        f"Trust {state.get('trust'):.2f}, closeness {state.get('closeness'):.2f}, "
        f"tension {state.get('tension'):.2f}\n"
        f"The user says: {message!r}\n\n"
        "Return ONLY:\n"
        '{"stance": "hard_refuse|refuse|negotiate|limited|deflect|tease|answer", '
        '"tone": "warm|shy|firm|playful|concerned|neutral", '
        '"limit": "a short concrete limit, or null", '
        '"line_hint": "one short direction for the character, not dialogue"}'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _clip(value, limit: int) -> str | None:
    if value in (None, ""):
        return None
    text = " ".join(str(value).split())
    return text[:limit] if text else None


def arbitrate(
    service: WorldService,
    character: str,
    message: str,
    verdict: dict,
    *,
    client=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Ask the high-effort arbiter, with a deterministic fallback on every failure."""
    if not enabled() or not should_arbitrate(verdict):
        return {"used": False, "reason": "not_needed"}

    if client is None:
        from gateway.bifrost import BifrostClient

        client = BifrostClient(timeout=timeout)

    started = time.monotonic()
    try:
        raw = client.chat_json(
            "arbiter",
            _messages(service, character, message, verdict),
            reasoning="high",
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        if not isinstance(raw, dict):
            raise ValueError("arbiter did not return an object")
        stance = str(raw.get("stance") or "").strip().lower()
        if stance not in ALLOWED_STANCES:
            raise ValueError(f"arbiter stance {stance!r} is not allowed")
        deterministic = str(verdict.get("stance") or "refuse")
        # Never soften the gate: a lower rank is allowed, a higher one is clamped.
        if STANCE_RANK.get(stance, 0) > STANCE_RANK.get(deterministic, 0):
            stance = deterministic
        tone = str(raw.get("tone") or "neutral").strip().lower()
        if tone not in ALLOWED_TONES:
            tone = "neutral"
        return {
            "used": True,
            "stance": stance,
            "deterministic_stance": deterministic,
            "tone": tone,
            "limit": _clip(raw.get("limit"), 120),
            "line_hint": _clip(raw.get("line_hint"), 200),
            "latency_ms": latency_ms,
            "model": "arbiter",
        }
    except Exception as exc:  # noqa: BLE001 - a slow arbiter must not block the scene
        return {
            "used": False,
            "reason": "fallback",
            "error": str(exc)[:240],
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


def block(note: dict | None) -> str:
    """The prompt fragment. Empty when the arbiter was not used."""
    if not note or not note.get("used"):
        return ""
    parts = [
        "Off-stage social check (never mention it, never name it):",
        f"stance {note.get('stance')} / tone {note.get('tone')}.",
    ]
    if note.get("limit"):
        parts.append(f"Keep this limit visible: {note['limit']}.")
    if note.get("line_hint"):
        parts.append(f"Direction: {note['line_hint']}.")
    parts.append("The deterministic boundary still stands; do not become more intimate.")
    return " ".join(parts)
