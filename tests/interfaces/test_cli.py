"""Subprocess tests for the new ``director`` console entry point.

They exercise the shipped argparse surface rather than calling functions, so a
change that only works in-process (or that secretly writes to the checkout)
fails here. Every run points WORLD_DATA_DIR/WORLD_DB at pytest's tmp path.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = "switch_world.interfaces.cli.director"


def _run(*args: str, data_dir: Path):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("BIFROST_", "SWITCH_", "TAVILY_", "WORLD_TOKEN_")):
            env.pop(key)
    env.update(
        {
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "WORLD_DEV": "1",
            "WORLD_AGENT_MODE": "local",
            "WORLD_DATA_DIR": str(data_dir),
            "WORLD_DB": str(data_dir / "world.sqlite"),
        }
    )
    env.pop("WORLD_ROOT", None)
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        cwd=str(data_dir.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_status_creates_only_the_tmp_database(tmp_path):
    data_dir = tmp_path / "data"

    result = _run("--status", data_dir=data_dir)

    assert result.returncode == 0, result.stderr
    assert '"now"' in result.stdout
    assert (data_dir / "world.sqlite").is_file()


def test_reset_reports_and_leaves_a_seeded_database(tmp_path):
    data_dir = tmp_path / "data"

    result = _run("--reset", data_dir=data_dir)

    assert result.returncode == 0, result.stderr
    assert "world reset" in result.stdout
    status = _run("--status", data_dir=data_dir)
    assert status.returncode == 0, status.stderr
    assert '"now"' in status.stdout


def test_beat_local_runs_an_authored_beat(tmp_path):
    data_dir = tmp_path / "data"

    result = _run("--beat", "truck-lunch", "--transport", "local", data_dir=data_dir)

    assert result.returncode == 0, result.stderr
    assert "beat: Lunch, Mia's truck (truck-lunch)" in result.stdout
    assert "scene card:" in result.stdout
    assert (data_dir / "exports").is_dir()
