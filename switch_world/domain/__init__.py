"""Pure domain vocabulary: ids, visibilities, labels and small value helpers.

This package has no I/O. Both the persistence adapter and the compatibility
service import these names, so they have one definition.
"""
from __future__ import annotations

from .models import (
    CHARACTER_ORDER,
    CONNECTION_LABELS,
    IDEMPOTENCY_KEEP,
    LABELS,
    PAUSE_META,
    REVISION_META,
    SCENARIO_ID_META,
    SCENARIO_META,
    SOURCE_KINDS,
    TAKE_CHANGED_META,
    TAKE_ID_META,
    TAKE_INDEX_META,
    TAKE_META,
    TAKE_START_META,
    VISIBILITIES,
    IdempotencyConflict,
    clamp,
    connection_label,
    slugify,
    tokens,
)

__all__ = [
    "CHARACTER_ORDER",
    "CONNECTION_LABELS",
    "IDEMPOTENCY_KEEP",
    "LABELS",
    "PAUSE_META",
    "REVISION_META",
    "SCENARIO_ID_META",
    "SCENARIO_META",
    "SOURCE_KINDS",
    "TAKE_CHANGED_META",
    "TAKE_ID_META",
    "TAKE_INDEX_META",
    "TAKE_META",
    "TAKE_START_META",
    "VISIBILITIES",
    "IdempotencyConflict",
    "clamp",
    "connection_label",
    "slugify",
    "tokens",
]
