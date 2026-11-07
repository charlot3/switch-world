"""Compatibility shim over :mod:`switch_world.adapters.persistence.schema`.

The schema and the SQLite connection live in the persistence adapter now. This
module keeps the historical ``world_engine.db`` names importable for older
callers (and the ``WorldService._conn`` compatibility path).
"""
from __future__ import annotations

from pathlib import Path

from switch_world.adapters.persistence import schema
from switch_world.adapters.persistence.schema import SCHEMA

from . import config


def connect(db_path: Path | str):
    return schema.connect(db_path)


def init_db(
    db_path: Path | str,
    state_dir: Path | str = config.STATE_DIR,
) -> None:
    return schema.init_db(
        db_path,
        state_dir,
        world_start=config.WORLD_START,
        world_day=config.WORLD_DAY,
    )


def reset(
    db_path: Path | str,
    state_dir: Path | str = config.STATE_DIR,
) -> None:
    return schema.reset(
        db_path,
        state_dir,
        world_start=config.WORLD_START,
        world_day=config.WORLD_DAY,
    )


__all__ = ["SCHEMA", "connect", "init_db", "reset"]
