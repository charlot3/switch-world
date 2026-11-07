"""Character transport contract.

A transport owns room lifecycle and message delivery. The application builds
prompts and one-hop relay rules; the transport only carries them. The
capability record lets the application branch on transport behaviour (in-band
writes, private rooms, event-id shape) without ``hasattr`` probes.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol

from ..ids import CharacterId, MessageId, TurnId

if TYPE_CHECKING:
    from ..agents import WorldWrite


class TransportError(RuntimeError):
    """A room operation failed.

    Adapters raise this (or a subclass) instead of leaking an ``httpx`` or
    provider exception through the port. A model failure inside an in-band
    transport is still a :class:`~switch_world.domain.ports.model.ModelError`.
    """


@dataclass(frozen=True)
class TransportCapabilities:
    """What a transport can do, declared once at startup."""

    response_format: Literal["text", "json"]
    write_mode: Literal["out_of_band", "in_band", "none"]
    private_rooms: bool
    non_blocking_post: bool
    addressing: bool
    event_id_field: Literal["id", "event_id", "synthetic"]


@dataclass(frozen=True)
class RoomHandle:
    """An open room. ``private_for`` is set only for one-to-one rooms."""

    room_id: str
    name: str
    private_for: CharacterId | None = None


@dataclass(frozen=True)
class Prompt:
    """One addressed line to deliver to a character."""

    speaker: CharacterId
    text: str


@dataclass(frozen=True)
class InboundTurn:
    """A message read back from a transport."""

    sender: CharacterId
    text: str
    event_id: MessageId
    received_at: datetime
    # In-band transports may carry an envelope's writes; out-of-band ones
    # leave the tuple empty because the character already wrote through MCP.
    writes: tuple[WorldWrite, ...] = ()
    source: str = "mcp"
    # True when the adapter invented the id because the wire event had none.
    # A synthetic id is only valid inside one snapshot, so it is never stored
    # as a durable message id.
    synthetic: bool = False


@dataclass(frozen=True)
class Delivery:
    """The result of a non-blocking multi-prompt post.

    ``cursor`` is captured *before* posting and is the only valid "since"
    marker for this turn. In-band transports fill ``inline`` with replies that
    arrived during the post.
    """

    room: RoomHandle
    turn_id: TurnId
    cursor: str
    inline: tuple[InboundTurn, ...] = field(default_factory=tuple)


class CharacterTransport(Protocol):
    """Rooms, delivery and history. No application policy lives here."""

    name: str

    def capabilities(self) -> TransportCapabilities: ...

    def open_room(
        self, *, name: str, private_for: CharacterId | None = None
    ) -> RoomHandle: ...

    def deliver_many(
        self,
        room: RoomHandle,
        prompts: Sequence[Prompt],
        *,
        turn_id: TurnId,
        deadline: float | None = None,
    ) -> Delivery: ...

    def collect(
        self, delivery: Delivery, *, speakers: Sequence[CharacterId], deadline: float
    ) -> list[InboundTurn]: ...

    def history(self, room: RoomHandle) -> list[InboundTurn]: ...

    def close(self) -> None: ...


__all__ = [
    "CharacterTransport",
    "Delivery",
    "InboundTurn",
    "Prompt",
    "RoomHandle",
    "TransportCapabilities",
    "TransportError",
]
