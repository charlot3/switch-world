"""``world-engine``: serve the FastAPI app and the dashboard.

The entry point parses arguments before importing anything that can build an
application, so ``world-engine --help`` is instant and never opens a database
or creates the data directory. ``main`` builds :class:`Settings` and the
composition-root container once, then hands the app to uvicorn.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="world-engine",
        description=(
            "Serve the switch-world HTTP API, MCP endpoint and dashboard. "
            "Settings come from the environment (WORLD_ROOT, WORLD_DATA_DIR, "
            "WORLD_DB, WORLD_ENGINE_HOST, WORLD_ENGINE_PORT, ...)."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help="bind address (overrides WORLD_ENGINE_HOST; default 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="listen port (overrides WORLD_ENGINE_PORT; default 8890)",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="uvicorn log level (default: info)",
    )
    parser.add_argument(
        "--seed",
        metavar="SCENARIO",
        default=None,
        help=(
            "seed a scenario once if the database has never been seeded "
            "(the demo image uses --seed w5-good); restarts keep existing state"
        ),
    )
    return parser


def _prepare_data_dir(settings) -> bool:
    """Create the writable data directory, with the demo image's uid hint."""
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            f"world-engine: cannot create WORLD_DATA_DIR={settings.data_dir}: {exc}",
            file=sys.stderr,
        )
        return False
    if not os.access(settings.data_dir, os.W_OK):
        uid = getattr(os, "getuid", lambda: "?")()
        print(
            f"world-engine: WORLD_DATA_DIR={settings.data_dir} is not writable "
            f"by uid {uid}",
            file=sys.stderr,
        )
        return False
    return True


def _seed_scenario(service, scenario: str) -> None:
    """Apply ``scenario`` only on a fresh database; never reset on restart."""
    from switch_world.application.scenarios import load_scenario

    current = service.current_scenario_id()
    if current is None:
        print(f"world-engine: seeding scenario {scenario!r}")
        load_scenario(service, scenario)
    elif current != scenario:
        print(
            f"world-engine: database already seeded with {current!r}; "
            f"leaving it as-is (requested {scenario!r})"
        )
    else:
        print(f"world-engine: database already seeded with {current!r}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Heavy imports stay below --help so only serving builds objects.
    from switch_world.config import load_settings
    from switch_world.container import build_container
    from switch_world.interfaces.http.app import create_app

    settings = load_settings(os.environ)
    overrides: dict[str, object] = {}
    if args.host:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if overrides:
        settings = replace(settings, **overrides)

    if not _prepare_data_dir(settings):
        return 1

    container = build_container(settings)
    try:
        if args.seed:
            _seed_scenario(container.service, args.seed)

        app = create_app(container.service, settings, container=container)

        import uvicorn

        print(
            f"world-engine: serving on http://{settings.host}:{settings.port} "
            f"db={settings.db_path} web={settings.web_dir} "
            f"content={settings.content_root}"
        )
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            log_level=args.log_level,
        )
    finally:
        container.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
