"""Importing the composition root and the HTTP shim must do no work.

The old ``world_engine.api`` built a FastAPI app at import time, which opened a
SQLite database. This probe imports the modules in a clean subprocess with a
temporary working directory and watches for file, database and socket effects.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PROBE = r"""
import json
import sys

sockets = []


def _audit(event, args):
    if event.startswith("socket."):
        sockets.append(event)


sys.addaudithook(_audit)

import switch_world.config  # noqa: F401
import switch_world.container  # noqa: F401
import world_engine.api  # noqa: F401

print(json.dumps(sorted(set(sockets))))
"""


def test_importing_has_no_file_database_or_socket_side_effects(tmp_path):
    data_dir = tmp_path / "data"
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "WORLD_DEV": "0",
            "WORLD_DATA_DIR": str(data_dir),
            "WORLD_DB": str(data_dir / "world.sqlite"),
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []
    # Constructing the app (as the old module did) would create the data
    # directory and world.sqlite under WORLD_DATA_DIR / WORLD_DB.
    assert list(tmp_path.iterdir()) == []
    assert not data_dir.exists()
    assert not (data_dir / "world.sqlite").exists()
