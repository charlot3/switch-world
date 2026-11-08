"""In-process coverage for the two console entry points.

``test_cli.py`` runs the shipped argparse surface in a subprocess, which proves
the packaging edge but leaves the CLI bodies at 0% coverage. These tests call
``main`` in-process against a temporary world so every branch is measured and a
regression fails with an assertion instead of only a nonzero exit code.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

from switch_world.interfaces.cli import director as director_cli
from switch_world.interfaces.cli import world as world_cli

_AMBIENT_PREFIXES = ("BIFROST_", "SWITCH_", "TAVILY_", "WORLD_TOKEN_")


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Point both CLIs at a throwaway world in local (scripted) mode."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("WORLD_DEV", "1")
    monkeypatch.setenv("WORLD_AGENT_MODE", "local")
    monkeypatch.setenv("WORLD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("WORLD_DB", str(data_dir / "world.sqlite"))
    monkeypatch.delenv("WORLD_ROOT", raising=False)
    for name in list(os.environ):
        if name.startswith(_AMBIENT_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    return data_dir


def test_director_help_exits_before_building_anything(capsys):
    with pytest.raises(SystemExit) as excinfo:
        director_cli.main(["--help"])
    assert excinfo.value.code == 0
    assert "authored beats" in capsys.readouterr().out


def test_director_status_and_reset_in_process(cli_env, capsys):
    assert director_cli.main(["--status"]) == 0
    assert '"now"' in capsys.readouterr().out

    assert director_cli.main(["--reset"]) == 0
    assert "world reset" in capsys.readouterr().out


def test_director_tell_alice_in_process(cli_env, capsys):
    assert director_cli.main(["--tell-alice"]) == 0
    assert "Alice now knows" in capsys.readouterr().out


def test_director_local_beat_in_process(cli_env, capsys):
    assert (
        director_cli.main(["--beat", "truck-lunch", "--transport", "local"])
        == 0
    )
    output = capsys.readouterr().out
    assert "beat: Lunch, Mia's truck (truck-lunch)" in output
    assert "scene card:" in output


def test_director_default_runs_the_cafe(cli_env, capsys):
    # The café refuses to run before Alice holds the secret.
    assert director_cli.main(["--tell-alice"]) == 0
    capsys.readouterr()

    assert director_cli.main([]) == 0
    output = capsys.readouterr().out
    assert "branch:" in output
    assert "scene card:" in output


def test_world_help_exits_before_building_anything(capsys):
    with pytest.raises(SystemExit) as excinfo:
        world_cli.main(["--help"])
    assert excinfo.value.code == 0
    assert "Serve the switch-world" in capsys.readouterr().out


def test_world_serve_seeds_a_fresh_database(cli_env, monkeypatch, capsys):
    calls: dict[str, object] = {}

    def fake_run(app, **kwargs):
        calls.update(kwargs)
        calls["app"] = app

    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))

    code = world_cli.main(
        ["--host", "127.0.0.1", "--port", "8899", "--seed", "w5-good"]
    )

    assert code == 0
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8899
    assert calls["app"] is not None
    output = capsys.readouterr().out
    assert "serving on http://127.0.0.1:8899" in output
    assert "seeding scenario" in output
    assert (cli_env / "world.sqlite").is_file()


def test_world_reports_an_unwritable_data_dir(cli_env, monkeypatch, capsys):
    def denied(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", denied)

    assert world_cli.main([]) == 1
    assert "cannot create WORLD_DATA_DIR" in capsys.readouterr().err
