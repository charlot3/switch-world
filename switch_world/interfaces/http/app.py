"""FastAPI app factory: build the app, mount routers, map errors.

Route definitions live in :mod:`switch_world.interfaces.http.routes`.  This
module is the composition seam only: it resolves the HTTP container, mounts the
MCP/static endpoints and includes the routers.  Importing it constructs
nothing; :func:`create_app` is always called explicitly.

A caller may pass either a composition-root :class:`~switch_world.container.Container`
or the historical ``create_app(service, settings)`` pair.  The latter gets the
compatibility runtime (lazy director adapters) from
:mod:`switch_world.interfaces.http.deps`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from switch_world.config import Settings
from switch_world.interfaces.mcp.server import create_mcp
from switch_world import config
from switch_world.application.facade import WorldService

from .deps import build_runtime
from .errors import register_error_handlers
from .routes import dev, director, health, scenarios, scene, studio, takes, world


def create_app(
    service: WorldService | None = None,
    settings: Settings | None = None,
    container=None,
) -> FastAPI:
    if service is None and container is not None:
        service = container.service
    service = service or WorldService()
    runtime = build_runtime(service, settings, container)

    mcp = create_mcp(service)
    mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="switch-world",
        version="0.1.0",
        description=(
            "A Switch-native AI social world with a provenance-tracked secret "
            "ledger."
        ),
        lifespan=lifespan,
    )

    # One typed container per app; routes take services, transports and models
    # from it, never from module globals.
    app.state.runtime = runtime
    app.state.container = runtime

    register_error_handlers(app)

    app.mount("/mcp", mcp_app)
    # The container's settings win so a wheel serves the resources bundled
    # inside the package; legacy callers keep the module-level shim path.
    web_dir = (
        Path(runtime.settings.web_dir) if runtime.settings is not None else Path(config.WEB_DIR)
    )
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    app.include_router(world.router, tags=["world"])
    app.include_router(scene.router, tags=["scene"])
    app.include_router(director.router, tags=["director"])
    app.include_router(scenarios.router, tags=["scenarios"])
    app.include_router(takes.router, tags=["takes"])
    app.include_router(studio.router, tags=["studio"])
    app.include_router(dev.router, tags=["dev"])
    app.include_router(health.router, tags=["health"])

    return app


__all__ = ["create_app"]
