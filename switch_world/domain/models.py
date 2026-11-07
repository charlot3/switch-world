"""Pure domain constants and value helpers.

Nothing here opens a database, reads the environment or imports an adapter.
"""
from __future__ import annotations

import re

VISIBILITIES = ("private", "shared", "public")
SOURCE_KINDS = ("user", "character", "event", "observation")
CHARACTER_ORDER = {"alice": 0, "emily": 1, "sophia": 2, "mia": 3}
CONNECTION_LABELS = ("close", "steady", "strained", "rival", "distant")

SCENARIO_META = "scenario"
SCENARIO_ID_META = "scenario_id"
PAUSE_META = "paused"
REVISION_META = "revision"
IDEMPOTENCY_KEEP = 500

TAKE_META = "take"
TAKE_ID_META = "take_id"
TAKE_INDEX_META = "take_index"
TAKE_START_META = "take_scene_start"
TAKE_CHANGED_META = "take_scene_changed"

LABELS = {
    "user-leaving-city": "The user is leaving the city",
    "bookshop-lease": "Alice's bookshop lease is not being renewed",
    "bookshop-trouble": "Alice's bookshop is in trouble",
    "alice-hiding-shop": "Alice is hiding something about the shop",
    "emily-distracted": "Emily has seemed distracted",
    "emily-new-job": "Emily applied for a job in another city",
    "emily-leaving": "Emily is planning to leave",
    "emily-change": "Emily is about to make a big change",
    "sophia-book": "Sophia is writing a book",
    "sophia-watching": "Sophia is watching the group closely",
    "alice-money": "Alice is worried about money",
    "truck-debt": "Mia's truck is in debt",
    "tuesday-cafe": "The group meets at the café on Tuesdays at 18:30",
}


class IdempotencyConflict(ValueError):
    """The same request id was reused with a different payload."""


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "proposition"


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1]


def connection_label(affinity: float, tension: float) -> str:
    if tension > 0.55:
        return "rival"
    if affinity >= 0.70:
        return "close"
    if affinity >= 0.42:
        return "steady"
    if affinity >= 0.24:
        return "strained"
    return "distant"
