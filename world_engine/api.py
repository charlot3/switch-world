"""Compatibility re-export of the FastAPI app factory.

The implementation lives in :mod:`switch_world.interfaces.http.app`. Importing
this module must not construct an app; callers invoke ``create_app`` explicitly.
"""
from __future__ import annotations

from switch_world.interfaces.http.app import create_app

__all__ = ["create_app"]
