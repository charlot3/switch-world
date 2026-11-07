"""Compatibility shim over :mod:`switch_world.config`.

New code should call ``switch_world.config.load_settings(os.environ)`` and pass
the resulting Settings to the composition root. This module keeps the
historical module-level names working for existing callers and tests.

Values are resolved lazily on first access, so importing this module does not
read the environment. Assigning an attribute directly (as tests do with
``monkeypatch.setattr(config, "DEV_MODE", False)``) shadows the lazy value, and
:func:`refresh` rebuilds the cached Settings from the current environment.
"""
from __future__ import annotations

import os
from typing import Any

from switch_world.config import DEV_TOKENS, Settings, load_settings

_SETTINGS: Settings | None = None

_FIELDS = {
    "ROOT": "root",
    "CONTENT_ROOT": "content_root",
    "STATE_DIR": "state_dir",
    "WEB_DIR": "web_dir",
    "AGENTS_DIR": "agents_dir",
    "DATA_DIR": "data_dir",
    "DB_PATH": "db_path",
    "EXPORT_DIR": "export_dir",
    "HOST": "host",
    "PORT": "port",
    "DEV_MODE": "dev_mode",
    "AGENT_MODE": "agent_mode",
    "WORLD_START": "world_start",
    "WORLD_DAY": "world_day",
}


def _settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = load_settings(os.environ)
    return _SETTINGS


def refresh() -> Settings:
    """Rebuild the cached Settings from the current process environment."""
    global _SETTINGS
    _SETTINGS = load_settings(os.environ)
    return _SETTINGS


def __getattr__(name: str) -> Any:
    field = _FIELDS.get(name)
    if field is not None:
        return getattr(_settings(), field)
    if name == "token_map":
        return _settings().token_map
    if name == "DEV_TOKENS":
        return DEV_TOKENS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
