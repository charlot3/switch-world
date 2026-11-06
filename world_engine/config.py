"""Paths, tokens and the world clock defaults.

The prototype runs with deterministic dev tokens so `uv run world-engine` works
without any setup. Real agent configs are generated from `.env` by
scripts/render-agent-configs.sh.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "world" / "state"
WEB_DIR = ROOT / "web"

DATA_DIR = Path(os.environ.get("WORLD_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("WORLD_DB", DATA_DIR / "world.sqlite"))
EXPORT_DIR = DATA_DIR / "exports"

HOST = os.environ.get("WORLD_ENGINE_HOST", "127.0.0.1")
PORT = int(os.environ.get("WORLD_ENGINE_PORT", "8890"))
DEV_MODE = os.environ.get("WORLD_DEV", "1").lower() not in ("0", "false", "no")
# "switch" (default): group replies come from live Switch agents.
# "cloud": no Console is available, so one DeepSeek call answers each planned
# speaker. The planning, addressing, relay and recording paths are identical.
AGENT_MODE = os.environ.get("WORLD_AGENT_MODE", "switch").strip().lower()

WORLD_START = os.environ.get("WORLD_START", "2026-11-03T08:00:00+09:00")
WORLD_DAY = os.environ.get("WORLD_DAY", "2026-11-03")

DEV_TOKENS = {
    "dev-alice": "alice",
    "dev-emily": "emily",
    "dev-sophia": "sophia",
    "dev-mia": "mia",
    "dev-director": "director",
}


def token_map() -> dict[str, str]:
    """token -> actor id. Env tokens override the dev defaults."""
    mapping = dict(DEV_TOKENS)
    for name in ("ALICE", "EMILY", "SOPHIA", "MIA", "DIRECTOR"):
        value = os.environ.get("WORLD_TOKEN_" + name)
        if value:
            mapping[value] = name.lower()
    return mapping
