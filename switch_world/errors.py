"""Application-level error types.

The HTTP adapter maps these to responses where it can; the domain errors that
currently live in :mod:`world_engine.service` and :mod:`world_engine.takes`
will move here as the v2 refactor progresses.
"""
from __future__ import annotations


class SwitchWorldError(Exception):
    """Base class for errors raised by switch-world application code."""
