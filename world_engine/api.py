"""FastAPI app: dashboard, read-only API, dev simulation, and the MCP mount."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .mcp_server import create_mcp
from .service import WorldService


def create_app(service: WorldService | None = None) -> FastAPI:
    service = service or WorldService()
    mcp = create_mcp(service)
    mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="switch-world",
        version="0.1.0",
        description="A Switch-native AI social world with a provenance-tracked secret ledger.",
        lifespan=lifespan,
    )

    app.mount("/mcp", mcp_app)
    app.mount("/static", StaticFiles(directory=str(config.WEB_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(config.WEB_DIR / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True, "dev": config.DEV_MODE, "clock": service.clock()}

    @app.get("/api/state")
    def state():
        return service.state()

    @app.get("/api/matrix")
    def matrix():
        return {"matrix": service.matrix(), "clock": service.clock()}

    @app.get("/api/who-knows/{key}")
    def who_knows(key: str):
        return service.who_knows(key)

    @app.get("/api/scene-card")
    def scene_card():
        return service.scene_card()

    @app.get("/api/scene-card.md")
    def scene_card_md():
        card = service.scene_card()
        return PlainTextResponse(
            card["text"],
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="scene-card.md"'},
        )

    @app.post("/api/dev/tell-alice")
    def tell_alice(payload: dict | None = None):
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.simulate import user_tells_alice

        payload = payload or {}
        secret = payload.get("secret") or (
            "I've decided to leave the city at the end of the month. "
            "I haven't told the others yet."
        )
        key = payload.get("key") or "user-leaving-city"
        belief = user_tells_alice(service, secret=secret, key=key)
        return {"belief": belief, "matrix": service.matrix()}

    @app.post("/api/dev/run-cafe")
    def run_cafe(payload: dict | None = None):
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.simulate import run_cafe

        payload = payload or {}
        try:
            result = run_cafe(service, force_share=payload.get("force_share"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return result

    @app.post("/api/dev/reset")
    def reset():
        if not config.DEV_MODE:
            raise HTTPException(404)
        service.reset()
        return {"ok": True, "state": service.state()}

    return app


app = create_app()
