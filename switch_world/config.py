"""Immutable settings loaded from an explicit environment mapping.

``load_settings`` is a pure function: it reads only the mapping it is given and
never touches ``os.environ``, the filesystem, or the network at import time.
Callers that need process settings pass ``os.environ`` explicitly.

Paths resolve in two stages so the same package works from a source checkout
and from an installed wheel:

* when the repository is present (``<root>/world/canon.json`` exists) the
  authored content, dashboard and agent identities are read from the checkout;
* otherwise they are read from the resources hatch force-includes into the
  wheel at ``switch_world/resources/{world,web,agents}``.

``WORLD_ROOT`` overrides the resolved root and ``WORLD_DATA_DIR`` overrides the
writable data directory. The data directory is never the package directory in
a wheel, so an installed engine does not try to write inside site-packages.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEV_TOKENS = {
    "dev-alice": "alice",
    "dev-emily": "emily",
    "dev-sophia": "sophia",
    "dev-mia": "mia",
    "dev-director": "director",
}

TOKEN_NAMES = ("ALICE", "EMILY", "SOPHIA", "MIA", "DIRECTOR")


@dataclass(frozen=True)
class Settings:
    """Everything the composition root needs, resolved once."""

    root: Path
    content_root: Path
    state_dir: Path
    web_dir: Path
    agents_dir: Path
    data_dir: Path
    db_path: Path
    export_dir: Path
    host: str
    port: int
    dev_mode: bool
    agent_mode: str
    world_start: str
    world_day: str
    token_overrides: tuple[tuple[str, str], ...] = ()
    # Transport settings resolved once for the composition root.
    switch_base_url: str = "http://127.0.0.1:8000"
    switch_agent_id: str = "director"
    switch_token: str = ""
    cloud_api_key: str = ""
    cloud_base_url: str = "https://api.deepseek.com/v1"
    cloud_model: str = "deepseek-flash"
    # First-class Bifrost mode: every character call goes through this gateway.
    bifrost_url: str = "http://127.0.0.1:8080/v1"
    bifrost_api_key: str = ""
    bifrost_models_path: Path | None = None

    def token_map(self) -> dict[str, str]:
        """token -> actor id. Env tokens override the dev defaults."""
        mapping = dict(DEV_TOKENS)
        mapping.update(dict(self.token_overrides))
        return mapping

    @property
    def tokens(self) -> dict[str, str]:
        """Backwards-friendly alias for :meth:`token_map`."""
        return self.token_map()

    @property
    def web_root(self) -> Path:
        """Historical name used by the packaging smoke test."""
        return self.web_dir


def _dev_mode(value: str) -> bool:
    return value.lower() not in ("0", "false", "no")


def _repo_root() -> Path:
    """The checkout root when ``switch_world`` is imported from one."""
    return Path(__file__).resolve().parent.parent


def _package_resources() -> Path:
    """The force-included resource root inside an installed wheel."""
    from importlib.resources import files

    return Path(str(files("switch_world").joinpath("resources")))


def _is_repo_root(path: Path) -> bool:
    return (path / "world" / "canon.json").is_file()


def _first_dir(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[-1]


def _resolve_roots(env: Mapping[str, str]) -> tuple[Path, Path, Path, Path]:
    """Return ``(root, content_root, web_dir, agents_dir)``.

    The repository wins when it is present. An explicit ``WORLD_ROOT`` may be
    either a checkout root (contains ``world/canon.json``) or a content root
    (contains ``canon.json``). The wheel resources are the final fallback.
    """
    repo = _repo_root()
    resources = _package_resources()
    override = (env.get("WORLD_ROOT") or "").strip()

    if override:
        root = Path(override).expanduser()
        content_root = root / "world" if _is_repo_root(root) else root
    elif _is_repo_root(repo):
        root = repo
        content_root = repo / "world"
    else:
        root = resources
        content_root = resources / "world"

    web_dir = _first_dir(root / "web", repo / "web", resources / "web")
    agents_dir = _first_dir(root / "agents", repo / "agents", resources / "agents")
    return root, content_root, web_dir, agents_dir


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``env``.

    ``None`` means "defaults only", so the function remains pure; pass
    ``os.environ`` for process settings.
    """
    env = {} if env is None else env
    root, content_root, web_dir, agents_dir = _resolve_roots(env)

    override = (env.get("WORLD_ROOT") or "").strip()
    data_override = env.get("WORLD_DATA_DIR")
    if data_override:
        data_dir = Path(data_override)
    elif override:
        data_dir = root / "data"
    elif _is_repo_root(_repo_root()):
        data_dir = _repo_root() / "data"
    else:
        # An installed wheel must not write into site-packages.
        data_dir = Path.home() / ".switch-world" / "data"

    token_overrides = tuple(
        (value, name.lower())
        for name in TOKEN_NAMES
        if (value := env.get("WORLD_TOKEN_" + name))
    )

    return Settings(
        root=root,
        content_root=content_root,
        state_dir=content_root / "state",
        web_dir=web_dir,
        agents_dir=agents_dir,
        data_dir=data_dir,
        db_path=Path(env.get("WORLD_DB", data_dir / "world.sqlite")),
        export_dir=data_dir / "exports",
        host=env.get("WORLD_ENGINE_HOST", "127.0.0.1"),
        port=int(env.get("WORLD_ENGINE_PORT", "8890")),
        dev_mode=_dev_mode(env.get("WORLD_DEV", "1")),
        agent_mode=env.get("WORLD_AGENT_MODE", "switch").strip().lower(),
        world_start=env.get("WORLD_START", "2026-11-03T08:00:00+09:00"),
        world_day=env.get("WORLD_DAY", "2026-11-03"),
        token_overrides=token_overrides,
        switch_base_url=env.get("SWITCH_API_ENDPOINT", "http://127.0.0.1:8000"),
        switch_agent_id=env.get("SWITCH_AGENT_ID", "director"),
        switch_token=env.get("SWITCH_API_TOKEN", ""),
        cloud_api_key=env.get(
            "DEEPSEEK_API_KEY", env.get("WORLD_CLOUD_API_KEY", "")
        ),
        cloud_base_url=env.get(
            "WORLD_CLOUD_BASE_URL", "https://api.deepseek.com/v1"
        ),
        cloud_model=env.get("WORLD_CLOUD_MODEL", "deepseek-flash"),
        bifrost_url=(
            env.get("BIFROST_URL") or "http://127.0.0.1:8080/v1"
        ).strip().rstrip("/"),
        bifrost_api_key=(env.get("BIFROST_API_KEY") or "").strip(),
        bifrost_models_path=content_root / "models.json",
    )


# ---------------------------------------------------------------------------
# Process-level compatibility names
# ---------------------------------------------------------------------------
#
# ``load_settings`` stays the pure function new code should call. Callers that
# historically read module-level values (``config.STATE_DIR``,
# ``config.AGENT_MODE``, ...) keep working through a lazily resolved cache that
# is rebuilt from ``os.environ`` on first access. It never reads the
# environment at import time, so importing this module still has no side
# effects. Assigning an attribute (as tests do with
# ``monkeypatch.setattr(config, "AGENT_MODE", "cloud")``) shadows the lazy
# value, and :func:`refresh` rebuilds the cache from the current environment.

_PROCESS_FIELDS = {
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

_process_settings: Settings | None = None


def refresh() -> Settings:
    """Rebuild the process settings cache from the current environment."""
    global _process_settings
    _process_settings = load_settings(os.environ)
    return _process_settings


def _process() -> Settings:
    """The lazily resolved process settings (never read at import time)."""
    global _process_settings
    if _process_settings is None:
        _process_settings = load_settings(os.environ)
    return _process_settings


def __getattr__(name: str):
    field = _PROCESS_FIELDS.get(name)
    if field is not None:
        return getattr(_process(), field)
    if name == "token_map":
        return _process().token_map
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
