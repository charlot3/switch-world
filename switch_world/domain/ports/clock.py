"""Clock contract: the only source of "now" for application code.

Tests inject a fake clock instead of monkeypatching ``datetime``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ClockReading:
    """One coherent read of wall time and a monotonic counter."""

    wall: datetime
    monotonic: float


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


__all__ = ["Clock", "ClockReading"]
