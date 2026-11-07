"""Typed identifiers shared by ports and adapters.

They are :func:`typing.NewType` aliases: the runtime value stays a plain string,
while signatures make the intent explicit. This module is stdlib-only.
"""
from __future__ import annotations

from typing import NewType

CharacterId = NewType("CharacterId", str)
RoomId = NewType("RoomId", str)
TurnId = NewType("TurnId", str)
MessageId = NewType("MessageId", str)

__all__ = ["CharacterId", "MessageId", "RoomId", "TurnId"]
