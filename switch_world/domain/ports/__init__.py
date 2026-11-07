"""Ports: the contracts the application depends on, with no I/O.

Every module here imports only the standard library and other domain modules.
Concrete adapters live under :mod:`switch_world.adapters`.
"""
from __future__ import annotations

from .artifacts import ArtifactNotFound, ArtifactRef, ArtifactStore
from .clock import Clock, ClockReading
from .content import ContentNotFound, ContentStore
from .model import (
    Message,
    ModelBudgetExceeded,
    ModelClient,
    ModelError,
    ModelFormat,
    ModelReply,
    Usage,
    UsageSummary,
)
from .transport import (
    CharacterTransport,
    Delivery,
    InboundTurn,
    Prompt,
    RoomHandle,
    TransportCapabilities,
    TransportError,
)

__all__ = [
    "ArtifactNotFound",
    "ArtifactRef",
    "ArtifactStore",
    "CharacterTransport",
    "Clock",
    "ClockReading",
    "ContentNotFound",
    "ContentStore",
    "Delivery",
    "InboundTurn",
    "Message",
    "ModelBudgetExceeded",
    "ModelClient",
    "ModelError",
    "ModelFormat",
    "ModelReply",
    "Prompt",
    "RoomHandle",
    "TransportCapabilities",
    "TransportError",
    "Usage",
    "UsageSummary",
]
