"""Wall-clock and monotonic time for production containers."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from switch_world.domain.ports.clock import ClockReading


class SystemClock:
    """A :class:`Clock` backed by the host's UTC wall clock and monotonic timer.

    ``now()`` is timezone-aware UTC so persisted timestamps compare cleanly
    across machines. ``monotonic()`` is for deadlines only; it has no relation
    to wall time.
    """

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    def read(self) -> ClockReading:
        return ClockReading(wall=self.now(), monotonic=self.monotonic())


__all__ = ["SystemClock"]
