"""The composition root: settings in, constructed objects out.

Deliberately framework-free. Importing this module builds nothing; only
calling :func:`build_container` creates clients and opens the world store.
"""
from __future__ import annotations

from dataclasses import dataclass

from switch_world.config import Settings
from world_engine.service import WorldService


@dataclass
class Container:
    settings: Settings
    service: WorldService


def build_container(settings: Settings) -> Container:
    """Construct the object graph the HTTP app needs today."""
    service = WorldService(
        db_path=settings.db_path,
        state_dir=settings.state_dir,
        tokens=settings.token_map(),
    )
    return Container(settings=settings, service=service)
