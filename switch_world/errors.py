"""Application-level error types.

The HTTP adapter maps these to responses where it can. Domain failures live in
the store and application modules; this module holds the small shared base
classes the interfaces can catch without importing an adapter.
"""
from __future__ import annotations


class SwitchWorldError(Exception):
    """Base class for errors raised by switch-world application code."""
