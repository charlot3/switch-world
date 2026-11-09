"""The Four Hearts pre-meeting briefing, end to end on the offline fixture.

The suite runs with ``TAVILY_OFFLINE=1`` so the three fixture items are the
sources, a ``ScriptedModelClient`` so every character answers deterministically,
and a temporary export directory so the artifact and the recorded event are
both visible to the test.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from switch_world import config
from switch_world.adapters.models import ScriptedModelClient
from switch_world.application.briefing import prepare_briefing
from switch_world.application.facade import WorldService
from switch_world.interfaces.http.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = "switch_world.interfaces.cli.director"
MEETING = "2026-11-18T10:00:00+09:00"


@pytest.fixture()
def service(tmp_path):
    return WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )


@pytest.fixture()
def export_dir(tmp_path, monkeypatch):
    path = tmp_path / "exports"
    monkeypatch.setattr(config, "EXPORT_DIR", path)
    return path


def _model() -> ScriptedModelClient:
    return ScriptedModelClient(
        {
            "alice": [
                {
                    "reply": (
                        "Anthropic keeps shipping in the same direction; "
                        "the question is whether it changes our pitch."
                    )
                }
            ],
            "emily": [
                {"reply": "Do we trust their safety claims enough to repeat them?"}
            ],
            "sophia": [{"reply": "What did they launch, and who is it really for?"}],
            "mia": [{"reply": "Their hiring push is the signal I care about."}],
        }
    )


def _prepare(service, **kwargs):
    return prepare_briefing(
        service, "Anthropic", MEETING, model=_model(), **kwargs
    )


def test_offline_briefing_has_sources_sections_and_artifact(
    service, export_dir, monkeypatch
):
    monkeypatch.setenv("TAVILY_OFFLINE", "1")

    result = _prepare(service)

    assert len(result["sources"]) == 3
    assert all("Offline fixture" in source["title"] for source in result["sources"])
    assert {source["event_id"] for source in result["sources"]} == {
        event["id"] for event in result["events"] if event["kind"] == "world_event"
    }

    text = result["briefing"]
    for section in (
        "## Snapshot",
        "## Recent developments",
        "## Discussion points",
        "## Open questions",
        "## Sources",
        "## Provenance",
    ):
        assert section in text
    assert "offline fixture" in text.lower()
    assert "Anthropic" in text
    assert MEETING in text

    artifact = Path(result["path"])
    assert artifact.is_file()
    assert artifact.name == "briefing-anthropic.md"
    assert artifact.read_text(encoding="utf-8") == text

    assert result["replies"]
    assert "@user" not in text
    assert "@director" not in text
    assert "```" not in text
    assert "tool_call" not in text.lower()

    briefings = service.events("briefing")
    assert len(briefings) == 1
    assert briefings[0]["metadata"]["path"] == result["path"]
    assert briefings[0]["metadata"]["source_count"] == 3
    assert "Anthropic" in briefings[0]["summary"]


def test_duplicate_search_results_do_not_duplicate_events(
    service, export_dir, monkeypatch
):
    monkeypatch.setenv("TAVILY_OFFLINE", "1")
    _prepare(service)
    world_events = service.events("world_event")
    summaries = [event["summary"] for event in world_events]
    assert len(summaries) == len(set(summaries)) == 3


def test_briefing_without_a_model_still_writes_the_page(
    service, export_dir, monkeypatch
):
    monkeypatch.setenv("TAVILY_OFFLINE", "1")
    result = prepare_briefing(service, "Anthropic", MEETING)
    assert result["replies"] == []
    assert "did not discuss the findings" in result["briefing"]
    assert Path(result["path"]).is_file()


def test_latest_briefing_route_is_read_only(service, export_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("TAVILY_OFFLINE", "1")

    with TestClient(create_app(service)) as client:
        assert client.get("/api/briefing/latest").status_code == 404

    result = _prepare(service)
    before = {path.name for path in export_dir.iterdir()}

    with TestClient(create_app(service)) as client:
        response = client.get("/api/briefing/latest")
        again = client.get("/api/briefing/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == result["path"]
    assert body["briefing"] == result["briefing"]
    assert body["subject"] == "Anthropic"
    assert len(body["sources"]) == 3
    assert again.status_code == 200
    assert {path.name for path in export_dir.iterdir()} == before


def test_dev_briefing_route_is_wired(service, export_dir, monkeypatch):
    captured: dict = {}

    def fake_prepare(service_, subject, meeting, **kwargs):
        captured.update(
            {"subject": subject, "meeting": meeting, "kwargs": kwargs}
        )
        return {
            "subject": subject,
            "meeting": meeting,
            "briefing": "# Briefing",
            "path": "/tmp/briefing-anthropic.md",
            "sources": [],
            "events": [],
            "replies": [],
        }

    monkeypatch.setattr(
        "switch_world.application.briefing.prepare_briefing", fake_prepare
    )
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/api/dev/briefing",
            json={"subject": "Anthropic", "meeting": MEETING},
        )

    assert response.status_code == 200
    assert response.json()["path"].endswith("briefing-anthropic.md")
    assert captured["subject"] == "Anthropic"
    assert captured["meeting"] == MEETING


def test_cli_briefing_subprocess(tmp_path):
    data_dir = tmp_path / "data"
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
            "TAVILY_OFFLINE": "1",
        }
    )
    env.pop("WORLD_ROOT", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--briefing",
            "--subject",
            "Anthropic",
            "--meeting",
            MEETING,
        ],
        cwd=str(data_dir.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "briefing:" in result.stdout
    assert "briefing-anthropic.md" in result.stdout
    assert (data_dir / "exports" / "briefing-anthropic.md").is_file()
