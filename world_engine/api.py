"""FastAPI app: dashboard, read-only API, dev simulation, and the MCP mount."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .mcp_server import create_mcp
from datetime import datetime
from .scenarios import evaluate_ending, list_scenarios, load_scenario
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
        data["scene"] = clock_view()
        return data

    @app.get("/api/canon")
    def canon():
        return load_canon()

    @app.get("/api/matrix")
    def matrix():
        return {"matrix": service.matrix(), "clock": service.clock()}

    # ---- scenarios (recordable demo worlds) ------------------------------

    @app.get("/api/scenarios")
    def scenarios():
        return {"scenarios": list_scenarios()}

    @app.get("/api/scenarios/current")
    def current_scenario():
        return {"scenario": service.current_scenario()}

    @app.post("/api/scenarios/{scenario_id}/load")
    def load_scenario_endpoint(scenario_id: str):
        if not config.DEV_MODE:
            raise HTTPException(404)
        try:
            scenario = load_scenario(service, scenario_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        state = service.state()
        state["canon"] = load_canon()
        state["scene"] = clock_view()
        return {"scenario": scenario, "state": state}

    @app.post("/api/endings/evaluate")
    def endings_evaluate():
        return evaluate_ending(service)

    def clock_view() -> dict:
        from director.clock import current_beat, next_beat

        canon_data = load_canon()
        clock = service.clock()
        now = datetime.fromisoformat(clock["now"])
        current = current_beat(canon_data, now)
        upcoming, target = next_beat(canon_data, now)
        slim = lambda beat: {
            key: beat.get(key)
            for key in ("id", "title", "time", "place", "characters", "choices", "summary")
        }
        return {
            **clock,
            "current_beat": slim(current),
            "next_beat": slim(upcoming),
            "next_at": target.isoformat(timespec="seconds"),
        }

    @app.get("/api/clock")
    def clock():
        return clock_view()

    @app.post("/api/clock/mode")
    def clock_mode(payload: dict | None = None):
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.clock import align_realtime

        payload = payload or {}
        mode = str(payload.get("mode") or "").strip()
        raw_scale = payload.get("scale")
        try:
            scale = None if raw_scale is None else float(raw_scale)
            if mode == "realtime":
                result = align_realtime(service, load_canon(), scale=scale)
                return {**result, "clock": service.clock(), "view": clock_view()}
            if mode == "mock":
                service.set_clock_mode("mock", scale=scale)
                return {"clock": service.clock(), "view": clock_view()}
            raise ValueError("mode must be mock or realtime")
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/clock/advance")
    def clock_advance(payload: dict | None = None):
        if not config.DEV_MODE:
            raise HTTPException(404)
        from director.clock import advance_to_beat, advance_to_next, done_beats, next_unplayed
        from director.beats import run_beat

        payload = payload or {}
        canon_data = load_canon()
        try:
            explicit = str(payload["beat"]) if payload.get("beat") else None
            if payload.get("run") and not explicit:
                # Fast-forward the arc: play the first beat that has not happened yet.
                upcoming = next_unplayed(canon_data, done_beats(service))
                if upcoming is None:
                    view = clock_view()
                    return {
                        "beat": view["current_beat"],
                        "clock": service.clock(),
                        "view": view,
                        "played": None,
                        "arc_complete": True,
                    }
                explicit = upcoming["id"]
            if explicit:
                moved = advance_to_beat(service, canon_data, explicit)
            else:
                moved = advance_to_next(service, canon_data)
            beat_id = moved["beat"]["id"]
            played = None
            if payload.get("run") and explicit:
                played = run_beat(service, beat_id, transport="local")
            return {
                "beat": moved["beat"],
                "clock": service.clock(),
                "view": clock_view(),
                "played": played,
            }
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"clock advance failed: {exc}") from exc

    @app.get("/api/friends")
    def friends():
        return {"friends": service.friends()}

    @app.post("/api/friends/{character}")
    def add_friend(character: str):
        if not config.DEV_MODE:
            raise HTTPException(404)
        try:
            friend = service.add_friend(character)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        service.record_event(
            "user",
            "friend",
            f"You added {character.title()} as a friend. The phone is open.",
            participants=[character],
            visibility="public",
        )
        return {"friend": friend, "friends": service.friends(), "state": service.state()}

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
        if not service.character_exists(character):
            raise HTTPException(404, f"unknown character: {character}")
        if not service.is_friend(character):
            raise HTTPException(
                403,
                f"Add {character.title()} as a friend before opening the phone.",
            )
        return service.phone_history(character, limit=limit, before_id=before_id)

    @app.post("/api/dm")
    def dm(payload: dict | None = None):
        from director.dm import reply_to_dm

        payload = payload or {}
        character = str(payload.get("character") or "")
        if not service.character_exists(character):
            raise HTTPException(404, f"unknown character: {character}")
        if not service.is_friend(character):
            raise HTTPException(
                403,
                f"Add {character.title()} as a friend before messaging them.",
            )
        try:
            return reply_to_dm(
                service,
                character=character,
                message=str(payload.get("message") or ""),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"DM failed: {exc}") from exc

    @app.post("/api/group/say")
    def group_say(payload: dict | None = None):
        from director.group import say_in_group

        payload = payload or {}
        characters = payload.get("characters")
        try:
            return say_in_group(
                service,
                str(payload.get("message") or ""),
                characters=characters if isinstance(characters, list) else None,
                timeout=float(payload.get("timeout") or 45.0),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"group scene failed: {exc}") from exc

    @app.post("/api/group/whisper")
    def group_whisper(payload: dict | None = None):
        from director.whisper import whisper_to_character

        payload = payload or {}
        try:
            return whisper_to_character(
                service,
                to=str(payload.get("to") or ""),
                message=str(payload.get("message") or ""),
                timeout=float(payload.get("timeout") or 35.0),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"whisper failed: {exc}") from exc

    @app.get("/api/studio/summary")
    def studio_summary_endpoint():
        from .studio import studio_summary

        return studio_summary(service)

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

    @app.get("/api/switch-log")
    def switch_log(room: str | None = "world"):
        from director.switch_log import collect

        try:
            events = collect(room=None if room in (None, "all") else room)
        except Exception as exc:
            raise HTTPException(502, f"Switch log failed: {exc}") from exc
        body = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
        return PlainTextResponse(
            body,
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="switch-log.jsonl"'},
        )

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
