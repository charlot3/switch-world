#!/usr/bin/env python3
"""Container entrypoint for the switch-world guest demo.

The demo is the normal FastAPI world engine plus dashboard, with a persistent
SQLite database that is seeded exactly once with the w5-good scenario. It runs
with WORLD_DEV=0, which turns every authored-beat/dev mutation endpoint
(scenario/take load, clock advance, dev reset, ...) into a 404; the social
endpoints the dashboard uses (group line, whisper, DM, friend) stay open.

With WORLD_AGENT_MODE=cloud (the compose default) the group room answers each
planned speaker with one DeepSeek call, because no Switch Console is available
to host the four live sessions. The planning, addressing, relay and recording
paths are identical to the local Switch mode.

Run from the repository root inside the image:
    python deploy/demo/entrypoint.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

DEMO_SCENARIO = os.environ.get("DEMO_SCENARIO", "w5-good")

# Defaults for the demo. Operators may override them, but the container is
# tuned for: one writer, local disk, no dev endpoints, port 8893.
DEFAULTS = {
    "WORLD_DB": "/data/world.sqlite",
    "WORLD_DATA_DIR": "/data",
    "WORLD_ENGINE_HOST": "0.0.0.0",
    "WORLD_ENGINE_PORT": "8893",
    "WORLD_DEV": "0",
}
for key, value in DEFAULTS.items():
    os.environ.setdefault(key, value)


def _fail(message: str) -> None:
    print("switch-world-demo: " + message, file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    from switch_world.config import load_settings
    from switch_world.container import build_container
    from switch_world.interfaces.http.app import create_app
    from switch_world.application.scenarios import load_scenario

    settings = load_settings(os.environ)
    data_dir = settings.data_dir
    db_path = settings.db_path

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _fail(f"cannot create WORLD_DATA_DIR={data_dir}: {exc}")
    if not os.access(data_dir, os.W_OK):
        _fail(
            f"WORLD_DATA_DIR={data_dir} is not writable by uid {os.getuid()}. "
            "On the host run: sudo chown -R 10001:10001 deploy/demo/data"
        )

    if settings.dev_mode:
        print(
            "switch-world-demo: WARNING WORLD_DEV is enabled; mutating dev "
            "endpoints will be exposed to guests.",
            file=sys.stderr,
        )

    container = build_container(settings)
    service = container.service

    # Seed once. `load_scenario` resets the database, so it must never run on an
    # ordinary restart. current_scenario_id() is None for a fresh/base DB only;
    # once a scenario has been applied the meta row survives every restart.
    current = service.current_scenario_id()
    if current is None:
        print(f"switch-world-demo: seeding scenario {DEMO_SCENARIO!r} into {db_path}")
        try:
            load_scenario(service, DEMO_SCENARIO)
        except (ValueError, OSError) as exc:
            _fail(f"failed to load scenario {DEMO_SCENARIO!r}: {exc}")
        except Exception as exc:  # pragma: no cover - startup diagnostics
            _fail(f"unexpected error loading scenario {DEMO_SCENARIO!r}: {exc!r}")
    elif current != DEMO_SCENARIO:
        # An operator deliberately (or previously) seeded another world. Keep it
        # rather than resetting state on every boot.
        print(
            f"switch-world-demo: database already seeded with {current!r}; "
            f"leaving it as-is (DEMO_SCENARIO={DEMO_SCENARIO!r})"
        )
    else:
        print(f"switch-world-demo: database already seeded with {current!r}")

    app = create_app(service, settings, container=container)

    host = settings.host
    port = settings.port
    print(f"switch-world-demo: serving on http://{host}:{port}  db={db_path}")

    import uvicorn

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.environ.get("WORLD_LOG_LEVEL", "info"),
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":
    main()
