"""Pure scene/take vocabulary shared by the backend and the dashboard.

The dashboard needs the same cast order, event kinds, take boundaries and
action/response modes the server writes.  Keeping them here (stdlib only) means
``scripts/gen-js-contract.py`` can generate ``web/js/vocab.js`` from one source
instead of maintaining a second copy in JavaScript.
"""
from __future__ import annotations

from .models import CHARACTER_ORDER

# Presentation order of the cast.  ``CHARACTER_ORDER`` is the one authoritative
# map; a tuple keeps the JSON/JS generation deterministic.
CAST_ORDER = tuple(CHARACTER_ORDER)

# Event kinds the scene transcript renders.  Anything else stays out of the log.
SCENE_EVENT_KINDS = (
    "dialogue",
    "silence",
    "reaction",
    "action",
    "chorus",
    "whisper",
    "whisper_reply",
    "boundary_violation",
)

# Beat modes that are spoken rather than shown as a stage direction.
SPEECH_MODES = ("speech", "chorus", "whisper", "whisper_reply")

# Authored take order, matching the Worlds rail.  w5-good and w5-bad are a fork.
TAKE_ORDER = (
    "w1-gift",
    "w2-two-clocks",
    "w3-quiet-route",
    "w4-three-of-us",
    "w5-good",
    "w5-bad",
    "w6-long-tuesday",
    "w7-last-call",
)

# Cue operations a take scene may run after the player's turn.
CUE_OPS = (
    "remember_preference",
    "give_item",
    "set_outfit",
    "advance_time",
    "mark_absent",
    "ending",
)

# A take scene begins at one of these events.
TAKE_BOUNDARY_EVENT_KINDS = ("take_load", "take_scene")

# Events written by a director group turn or a cue that mean "the player did
# something in this scene".  A bare scenario/take load is deliberately absent.
TAKE_CHANGE_EVENT_KINDS = (
    "dialogue",
    "action",
    "silence",
    "turn_plan",
    "boundary_violation",
    "social_verdict",
    "item_given",
    "outfit_change",
    "relationship_update",
    "take_cue",
    "ending",
    "beat",
    "branch",
)

# Action mode separates what the player does as themselves from what they
# attempt on an NPC.  ``continue`` and ``wait`` are deliberate non-moves.
ACTION_MODES = ("result", "attempt", "continue", "wait")

# The response spectrum a refused or limited attempt can land on.
RESPONSE_MODES = ("refuse", "negotiate", "limited", "surface", "sincere")


def _ordered_unique(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for group in groups:
        for value in group:
            seen.setdefault(value, None)
    return tuple(seen)


# Every event kind the dashboard may receive in ``/api/state``.
EVENT_KINDS = _ordered_unique(
    SCENE_EVENT_KINDS,
    TAKE_BOUNDARY_EVENT_KINDS,
    TAKE_CHANGE_EVENT_KINDS,
    ("dm",),
)
