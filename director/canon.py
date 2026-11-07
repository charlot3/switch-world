"""The authored story bible, and the checks that keep a live beat inside it.

The world engine is permissive on purpose: agents can remember almost anything and
move relationships in small deltas. The canon is the other half of that contract.
It gives the director a fixed set of facts, a small set of authored beats and three
legal endings, then checks the *state* after the beat rather than trusting the prose.

This module is deliberately dependency-free apart from the service, so the local
simulation and the live Switch beat use the same rules.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from world_engine import config
from world_engine.service import WorldService

CANON_PATH = Path(config.CONTENT_ROOT) / "canon.json"

_STOPWORDS = {
    "about", "after", "again", "already", "also", "because", "been", "before",
    "being", "could", "decided", "does", "doing", "from", "have", "haven",
    "her", "here", "hers", "him", "his", "into", "just", "know", "knows", "like",
    "more", "most", "much", "must", "not", "now", "only", "other",
    "others", "over", "said", "same", "she", "should", "some", "something",
    "still", "such", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "thing", "this", "those", "through", "told", "under",
    "until", "very", "want", "was", "were", "what", "when", "where", "which",
    "while", "will", "with", "would", "yet", "you", "your",
}


def load() -> dict:
    return json.loads(CANON_PATH.read_text(encoding="utf-8"))


def _words(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z]{4,}", (text or "").lower())
        if word not in _STOPWORDS
    }


def _matches_secret(proposition: str, reference: str) -> bool:
    """A paraphrase counts; a suspicion about Alice does not.

    The reference is Alice's own statement of the secret. Emily's belief must share
    at least two content words with it — "leaving", "city", "month" for the default —
    so "Alice is holding something back" can never be mistaken for a disclosure.
    """
    reference_words = _words(reference)
    if not reference_words:
        return False
    overlap = reference_words & _words(proposition)
    return len(overlap) >= min(2, len(reference_words))


def _misattributes(proposition: str) -> bool:
    """The secret is the user leaving, not Alice or a third party leaving.

    A confident belief that makes Alice (or Sophia/Mia) the person leaving is a
    distortion of the proposition, not a disclosure of it. It belongs to The Leak.
    """
    text = (proposition or "").lower()
    return bool(re.search(
        r"\b(?:alice|sophia|mia)(?:'s| is| was| will be)?\s+(?:leaving|moving|going|out of)\b",
        text,
    ))


def branch_for(service: WorldService, key: str) -> dict:
    """Classify the café beat from the ledger, not from the dialogue text."""
    canon = load()
    branches = {branch["id"]: branch for branch in canon["branches"]}
    holders = service.who_knows(key)["holders"]
    alice = next((h for h in holders if h["holder"] == "alice"), None)
    emily = next((h for h in holders if h["holder"] == "emily"), None)
    reference = (alice or {}).get("proposition") or ""

    def direct(holder: dict | None) -> bool:
        return bool(
            holder
            and str(holder.get("source", "")).startswith("character:alice")
            and float(holder.get("confidence", 0)) >= 0.6
            and _matches_secret(holder.get("proposition", ""), reference)
            and not _misattributes(holder.get("proposition", ""))
        )

    def distorted(holder: dict | None) -> bool:
        return bool(
            holder
            and str(holder.get("source", "")).startswith("character:alice")
            and float(holder.get("confidence", 0)) >= 0.6
            and (
                not _matches_secret(holder.get("proposition", ""), reference)
                or _misattributes(holder.get("proposition", ""))
            )
        )

    third = any(
        h["holder"] in {"sophia", "mia"} and float(h.get("confidence", 0)) >= 0.4
        for h in holders
    )

    if third or distorted(emily):
        branch_id = "partial-leak"
    elif direct(emily):
        branch_id = "disclosure"
    else:
        branch_id = "non-disclosure"
    return dict(branches[branch_id], holder=emily, reference=reference)


def validate(service: WorldService, canon: dict | None = None) -> list[str]:
    """Structural checks on the world state after a beat.

    Semantic guardrails live in the prompts; this catches the failures the ledger can
    prove — a belief held by someone who is not in the cast, an event with an unknown
    participant, a relationship outside 0..1, or a branch that is not authored.
    """
    canon = canon or load()
    state = service.state()
    characters = state["characters"]
    known = {character["id"] for character in characters} | {"user", "director"}
    aliases = {
        "you": "user", "the user": "user", "me": "user",
        "user": "user", "director": "director",
    }
    for character in characters:
        aliases[character["name"].lower()] = character["id"]
        aliases[character["name"].split()[0].lower()] = character["id"]

    def resolve(value: str) -> str:
        raw = str(value).strip()
        return aliases.get(raw.lower(), raw.lower() if raw.lower() in known else raw)

    issues: list[str] = []
    for belief in state["beliefs"]:
        if resolve(belief["holder"]) not in known:
            issues.append(f"belief holder {belief['holder']} is not in the cast")
    for event in service.events():
        for participant in event.get("participants", []):
            if resolve(participant) not in known:
                issues.append(f"event {event['id']} has unknown participant {participant}")
    for edge in state["relationships"]:
        if resolve(edge["a"]) not in known:
            issues.append(f"relationship source {edge['a']} is not in the cast")
        if resolve(edge["b"]) not in known:
            issues.append(f"relationship target {edge['b']} is not in the cast")
        for measure in ("trust", "closeness", "tension"):
            value = float(edge.get(measure, 0))
            if not 0.0 <= value <= 1.0:
                issues.append(f"{edge['a']}->{edge['b']} {measure}={value} is outside 0..1")
    return issues


def brief(actor: str | None = None, canon: dict | None = None) -> str:
    """The canon paragraph a character sees before its scene turn.

    Private facts are per-character: Alice sees the secret, Emily sees her suspicion
    and her own news, and neither sees the other's private facts.
    """
    canon = canon or load()
    public = " ".join(canon["public_facts"])
    private = " ".join(canon.get("private_facts", {}).get(actor or "", []))
    rules = " ".join(canon["invariants"])
    parts = [f"Canon — do not contradict. {public}"]
    if private:
        parts.append(f"Your private canon: {private}")
    parts.append(f"Rules: {rules}")
    return " ".join(parts)


def record_branch(
    service: WorldService,
    branch: dict,
    issues: list[str] | None = None,
    participants: list[str] | None = None,
) -> dict:
    """Write the branch into the immutable feed so the scene card can show it."""
    issues = issues or []
    state = "canon holds" if not issues else "canon warning: " + "; ".join(issues)
    event = service.record_event(
        "director",
        "branch",
        f"Branch: {branch['label']} ({branch['id']}) — {state}.",
        participants=participants or ["alice", "emily"],
        visibility="public",
    )
    if issues:
        service.record_event(
            "director",
            "canon_warning",
            "Worldline check: " + "; ".join(issues),
            participants=[],
            visibility="public",
        )
    return event
