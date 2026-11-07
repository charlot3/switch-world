from __future__ import annotations

import os

import uvicorn

from switch_world.config import load_settings
from switch_world.container import build_container

from .api import create_app


def main() -> None:
    settings = load_settings(os.environ)
    container = build_container(settings)
    uvicorn.run(
        create_app(container.service, settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
