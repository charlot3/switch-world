"""Local prototype of the café beat.

This is a deterministic harness, not the production director. It exercises the same
world-state writes the Switch-driven director will make: Alice records what the user
told her, Emily learns it second-hand, Emily's view of Alice and the user moves, and
the scene card is exported. The dialogue is authored; the real beat uses OpenCode
sessions in Switch rooms.
"""
from __future__ import annotations

from . import DEMO_KEY, DEMO_SECRET
from .canon import branch_for, load as load_canon, record_branch, validate
from switch_world.application.facade import WorldService


def user_tells_alice(
    service: WorldService,
    secret: str = DEMO_SECRET,
    key: str = DEMO_KEY,
) -> dict:
    """Record the user's DM to Alice. Idempotent for the same key + source."""
    existing = service.who_knows(key)["holders"]
    for holder in existing:
        if holder["holder"] == "alice" and holder["source"] == "user":
            return holder
    belief = service.remember(
        "alice",
        proposition=secret,
        source="user",
        confidence=1.0,
        visibility="private",
        proposition_key=key,
    )
    service.record_event(
        "alice",
        "conversation",
        "The user told Alice something in a DM.",
        participants=["user", "alice"],
        visibility="private",
    )
    return belief


def _alice_shares(service: WorldService) -> bool:
    rel = service.relationship("alice", "emily")
    return rel["trust"] >= 0.7 and rel["tension"] <= 0.35


def run_cafe(service: WorldService, force_share: bool | None = None) -> dict:
    """Run the café scene. Requires Alice to know DEMO_KEY."""
    known = service.who_knows(DEMO_KEY)["holders"]
    alice_knows = any(h["holder"] == "alice" and h["source"] == "user" for h in known)
    if not alice_knows:
        raise ValueError(
            "Alice does not know the secret yet; POST /api/dev/tell-alice (or call "
            "user_tells_alice) first."
        )

    share = _alice_shares(service) if force_share is None else bool(force_share)
    canon = load_canon()
    transcript: list[str] = []

    service.record_event(
        "director",
        "scene_start",
        "Café, 18:30. Alice and Emily are at a table.",
        participants=["alice", "emily"],
        visibility="public",
    )

    if not share:
        line = "I've had a long week. Tell me something good."
        transcript.append("Alice: " + line)
        service.record_event("alice", "dialogue", "Alice: " + line, ["alice"], "public")
        line = "You're deflecting. What aren't you telling me?"
        transcript.append("Emily: " + line)
        service.record_event("emily", "dialogue", "Emily: " + line, ["emily"], "public")
        service.record_event(
            "director",
            "non_disclosure",
            "Alice chose not to tell Emily. Emily noticed the deflection.",
            participants=["alice", "emily"],
            visibility="public",
        )
        branch = branch_for(service, DEMO_KEY)
        issues = validate(service, canon)
        record_branch(service, branch, issues)
        service.advance_time("director", 30)
        service.record_event(
            "director", "scene_end", "The café scene ends.", ["alice", "emily"], "public"
        )
        card = service.scene_card(f"Café, 18:30 — {branch['id']}")
        return {
            "shared": False,
            "branch": branch,
            "canon_issues": issues,
            "transcript": transcript,
            "card": card,
            "matrix": service.matrix(),
            "clock": service.clock(),
        }

    line = (
        "I shouldn't be telling you this, but our friend — the one who's been coming "
        "around — is leaving the city at the end of the month. They haven't told the "
        "others yet."
    )
    transcript.append("Alice: " + line)
    service.record_event("alice", "dialogue", "Alice: " + line, ["alice"], "public")

    line = (
        "They told you before they told me? I don't know whether to be flattered or "
        "worried."
    )
    transcript.append("Emily: " + line)
    service.record_event("emily", "dialogue", "Emily: " + line, ["emily"], "public")

    already = any(h["holder"] == "emily" for h in service.who_knows(DEMO_KEY)["holders"])
    if not already:
        service.remember(
            "emily",
            proposition="The user is leaving the city at the end of the month.",
            source="character:alice",
            confidence=0.8,
            visibility="shared",
            proposition_key=DEMO_KEY,
        )
        service.update_relationship(
            "emily",
            "alice",
            trust_delta=-0.10,
            closeness_delta=0.02,
            tension_delta=0.05,
            reason="heard the news second-hand",
        )
        service.update_relationship(
            "emily",
            "user",
            trust_delta=-0.05,
            closeness_delta=-0.02,
            tension_delta=0.02,
            reason="told Alice before me",
        )
        service.record_event(
            "director",
            "disclosure",
            "Alice told Emily: the user is leaving the city.",
            participants=["alice", "emily"],
            visibility="public",
        )

    branch = branch_for(service, DEMO_KEY)
    issues = validate(service, canon)
    record_branch(service, branch, issues)
    service.advance_time("director", 30)
    service.record_event(
        "director", "scene_end", "The café scene ends.", ["alice", "emily"], "public"
    )
    card = service.scene_card(f"Café, 18:30 — {branch['id']}")
    return {
        "shared": True,
        "branch": branch,
        "canon_issues": issues,
        "transcript": transcript,
        "card": card,
        "matrix": service.matrix(),
        "clock": service.clock(),
    }
