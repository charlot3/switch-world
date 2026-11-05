"""FastAPI app: dashboard, read-only API, dev simulation, and the MCP mount."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .mcp_server import create_mcp
from .service import WorldService

CANON_PATH = config.ROOT / "world" / "canon.json"


def load_canon() -> dict:
    """The authored story bible. It is read-only state, not world state."""
    return json.loads(CANON_PATH.read_text(encoding="utf-8"))


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
        data = service.state()
        data["canon"] = load_canon()
        return data

    @app.get("/api/canon")
    def canon():
        return load_canon()

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

    @app.get("/api/dm/{character}")
    def dm_history(character: str, limit: int = 100, before_id: int | None = None):
        return service.phone_history(character, limit=limit, before_id=before_id)

    @app.post("/api/dm")
    def dm(payload: dict | None = None):
        from director.dm import reply_to_dm

        payload = payload or {}
        try:
            return reply_to_dm(
                service,
                character=str(payload.get("character") or ""),
                message=str(payload.get("message") or ""),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"DM failed: {exc}") from exc

    @app.post("/api/dev/run-beat")
    def run_beat_endpoint(payload: dict | None = None):
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.beats import run_beat

        payload = payload or {}
        beat = payload.get("beat") or "cafe"
        transport = payload.get("transport") or "local"
        try:
            return run_beat(
                service,
                beat,
                transport=transport,
                force_share=payload.get("force_share"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"beat failed: {exc}") from exc

    @app.post("/api/dev/run-arc")
    def run_arc_endpoint(payload: dict | None = None):
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.beats import run_arc

        payload = payload or {}
        try:
            return run_arc(service, force_share=payload.get("force_share"))
        except Exception as exc:
            raise HTTPException(502, f"arc failed: {exc}") from exc

    @app.post("/api/dev/tavily-event")
    def tavily_event(payload: dict | None = None):
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.tavily_beat import fetch_world_event

        payload = payload or {}
        try:
            return fetch_world_event(service, query=payload.get("query"))
        except Exception as exc:
            raise HTTPException(502, f"Tavily event failed: {exc}") from exc

    @app.post("/api/dev/run-bifrost")
    def run_bifrost():
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.bifrost_scene import run_cafe_bifrost

        try:
            return run_cafe_bifrost(service)
        except Exception as exc:
            raise HTTPException(502, f"Bifrost beat failed: {exc}") from exc

    @app.get("/api/bifrost/usage")
    def bifrost_usage():
        from gateway.bifrost import BifrostClient

        return BifrostClient().usage_summary()

    @app.post("/api/dev/reset")
    def reset():
        if not config.DEV_MODE:
            raise HTTPException(404)
        service.reset()
        return {"ok": True, "state": service.state()}

    return app


app = create_app()
