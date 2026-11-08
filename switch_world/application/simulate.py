"""Local prototype of the café beat.

This is a deterministic harness, not the production director. It exercises the
same world-state writes as the Switch-driven director: Alice records what the
user told her, Emily learns it second-hand, Emily's view of Alice and the user
moves, and the scene card is exported. The dialogue is authored.

``run_cafe`` is now a thin wrapper over
:mod:`switch_world.application.beats` with the local strategy.  It keeps the
historical signature, return shape and the requirement that the caller seed the
secret first; it deliberately does not move the clock (callers that need the
18:30 jump use :func:`switch_world.application.beat_runners.advance_to` or
:func:`switch_world.application.beat_runners.run_beat`).
"""
from __future__ import annotations

from switch_world.application.canon import (  # noqa: F401  (historical re-exports)
    branch_for,
    load as load_canon,
    record_branch,
    validate,
)
from switch_world.application.facade import WorldService
from switch_world.domain.demo import DEMO_KEY, DEMO_SECRET


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
    """Run the café scene. Requires Alice to know ``DEMO_KEY``."""
    known = service.who_knows(DEMO_KEY)["holders"]
    alice_knows = any(h["holder"] == "alice" and h["source"] == "user" for h in known)
    if not alice_knows:
        raise ValueError(
            "Alice does not know the secret yet; POST /api/dev/tell-alice (or call "
            "user_tells_alice) first."
        )

    # Imported lazily: application.beats imports user_tells_alice from this
    # module, so a module-level import here would be circular.
    from switch_world.adapters.clock import SystemClock
    from switch_world.application.beat_strategies import LocalBeatStrategy
    from switch_world.application.beats import load_spec, run_beat

    result = run_beat(
        load_spec(
            "cafe",
            transport="local",
            force_share=force_share,
            seed=False,
            advance=False,
            record_beat=False,
            canon_warning=False,
        ),
        LocalBeatStrategy(),
        service,
        SystemClock(),
    )
    return {
        "shared": (result["branch"] or {}).get("id") == "disclosure",
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "transcript": result["transcript"],
        "card": result["card"],
        "matrix": result["matrix"],
        "clock": result["clock"],
    }


__all__ = [
    "branch_for",
    "load_canon",
    "record_branch",
    "run_cafe",
    "user_tells_alice",
    "validate",
]
