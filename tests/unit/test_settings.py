"""Settings are a pure function of an explicit environment mapping."""
from __future__ import annotations

from pathlib import Path

from switch_world.config import DEV_TOKENS, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_load_settings_ignores_ambient_environment(monkeypatch):
    monkeypatch.setenv("WORLD_DEV", "0")
    monkeypatch.setenv("WORLD_AGENT_MODE", "cloud")
    monkeypatch.setenv("WORLD_DATA_DIR", "/ambient/ignored")

    settings = load_settings({})

    assert settings.dev_mode is True
    assert settings.agent_mode == "switch"
    assert settings.data_dir == REPO_ROOT / "data"
    assert settings.port == 8890


def test_load_settings_defaults():
    settings = load_settings()

    assert settings.root == REPO_ROOT
    assert settings.state_dir == REPO_ROOT / "world" / "state"
    assert settings.web_dir == REPO_ROOT / "web"
    assert settings.data_dir == REPO_ROOT / "data"
    assert settings.db_path == REPO_ROOT / "data" / "world.sqlite"
    assert settings.export_dir == REPO_ROOT / "data" / "exports"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8890
    assert settings.dev_mode is True
    assert settings.agent_mode == "switch"
    assert settings.world_start == "2026-11-03T08:00:00+09:00"
    assert settings.world_day == "2026-11-03"


def test_load_settings_parses_dev_off_and_cloud():
    settings = load_settings({"WORLD_DEV": "0", "WORLD_AGENT_MODE": " Cloud "})

    assert settings.dev_mode is False
    assert settings.agent_mode == "cloud"


def test_load_settings_parses_bifrost_mode():
    settings = load_settings(
        {
            "WORLD_AGENT_MODE": "bifrost",
            "BIFROST_URL": "http://bifrost.internal:8080/v1/",
            "BIFROST_API_KEY": " local-key ",
        }
    )

    assert settings.agent_mode == "bifrost"
    assert settings.bifrost_url == "http://bifrost.internal:8080/v1"
    assert settings.bifrost_api_key == "local-key"
    assert settings.bifrost_models_path == REPO_ROOT / "world" / "models.json"


def test_load_settings_parses_false_spellings():
    for value in ("0", "false", "FALSE", "no", "No"):
        assert load_settings({"WORLD_DEV": value}).dev_mode is False
    for value in ("1", "true", "yes"):
        assert load_settings({"WORLD_DEV": value}).dev_mode is True


def test_token_map_override_wins_and_keeps_dev_tokens():
    settings = load_settings(
        {
            "WORLD_TOKEN_ALICE": "alice-secret",
            "WORLD_TOKEN_DIRECTOR": "director-secret",
        }
    )

    tokens = settings.token_map()

    assert tokens["alice-secret"] == "alice"
    assert tokens["director-secret"] == "director"
    assert tokens["dev-alice"] == "alice"
    assert tokens["dev-director"] == "director"
    assert DEV_TOKENS["dev-mia"] == "mia"
    assert settings.tokens == tokens


def test_load_settings_reads_paths_and_clock_from_env():
    settings = load_settings(
        {
            "WORLD_DATA_DIR": "/var/world-data",
            "WORLD_DB": "/var/custom.sqlite",
            "WORLD_ENGINE_HOST": "0.0.0.0",
            "WORLD_ENGINE_PORT": "8893",
            "WORLD_START": "2027-01-01T00:00:00+00:00",
            "WORLD_DAY": "2027-01-01",
        }
    )

    assert settings.data_dir == Path("/var/world-data")
    assert settings.db_path == Path("/var/custom.sqlite")
    assert settings.export_dir == Path("/var/world-data/exports")
    assert settings.host == "0.0.0.0"
    assert settings.port == 8893
    assert settings.world_start == "2027-01-01T00:00:00+00:00"
    assert settings.world_day == "2027-01-01"
