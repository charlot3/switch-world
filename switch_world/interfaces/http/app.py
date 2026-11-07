"""FastAPI app: dashboard, read-only API, dev simulation, and the MCP mount.

This module is the HTTP driving adapter. It is constructed explicitly by the
composition root; importing it must not build an app.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from switch_world.config import Settings
from world_engine import config
from world_engine.mcp_server import create_mcp
from datetime import datetime
from world_engine.scenarios import evaluate_ending, list_scenarios, load_scenario
from world_engine.service import IdempotencyConflict, WorldService
from world_engine.takes import (
    TakeNotChanged,
    apply_cues,
    current_take,
    list_takes,
    load_take,
    next_scene,
    take_snapshot,
    take_snapshot_from_snapshot,
)

CANON_PATH = config.ROOT / "world" / "canon.json"


def load_canon() -> dict:
    """The authored story bible. It is read-only state, not world state."""
    return json.loads(CANON_PATH.read_text(encoding="utf-8"))


REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
PAUSED_MESSAGE = "The scene is paused. Resume when you are ready."
STALE_MESSAGE = "the world moved since you loaded it; refresh and try again"


def _request_id(payload: dict) -> str | None:
    raw = payload.get("request_id")
    if raw is None:
        return None
    request_id = str(raw).strip()
    if not REQUEST_ID.match(request_id):
        raise HTTPException(
            400, "request_id must be 8-64 characters of A-Za-z0-9_-"
        )
    return request_id


def _digest(values: dict) -> str:
    body = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _expected_revision(payload: dict) -> int | None:
    raw = payload.get("expected_revision")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "expected_revision must be an integer") from exc


def _replay(service: WorldService, scope: str, request_id: str | None, digest: str):
    if not request_id:
        return None
    try:
        return service.idempotent_replay(scope, request_id, digest)
    except IdempotencyConflict as exc:
        raise HTTPException(
            409,
            detail={"error": "REQUEST_CONFLICT", "detail": str(exc)},
        ) from exc


def _check_revision(service: WorldService, expected: int | None) -> None:
    if expected is None:
        return
    current = service.revision()
    if expected != current:
        raise HTTPException(
            409,
            detail={
                "error": "STALE_REVISION",
                "revision": current,
                "expected_revision": expected,
                "detail": STALE_MESSAGE,
            },
        )


def _legacy_transport(settings: Settings | None = None):
    """A deferred transport for a caller that built no container.

    The client is resolved on first use, so the compatibility path still works
    with a monkeypatched ``director.group.SwitchClient`` in older tests. The
    agent mode selects the same room HEAD did, so a direct
    ``create_app(service, settings)`` caller is not always sent to Switch. The
    composition root path never reaches this helper.
    """
    from switch_world.adapters.transports.legacy import LegacySwitchTransport

    mode = settings.agent_mode if settings is not None else config.AGENT_MODE
    if str(mode).strip().lower() == "cloud":

        def client_factory():
            from director.cloud_switch import CloudSwitch

            return CloudSwitch()

    else:

        def client_factory():
            from director.group import SwitchClient

            return SwitchClient()

    return LegacySwitchTransport(client_factory=client_factory)


def create_app(
    service: WorldService | None = None,
    settings: Settings | None = None,
    container=None,
) -> FastAPI:
    if service is None and container is not None:
        service = container.service
    service = service or WorldService()
    # The composition root owns transport construction; routes only receive it.
    transport = getattr(container, "transport", None) or _legacy_transport(settings)

    def dev_enabled() -> bool:
        """Prefer the composition root's Settings over the ambient shim."""
        return settings.dev_mode if settings is not None else config.DEV_MODE

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
        return {"ok": True, "dev": dev_enabled(), "clock": service.clock()}

    @app.get("/api/state")
    def state():
        # One store snapshot for the whole projection: clock, take and every
        # subprojection come from the same read.
        snapshot = service.store.reader.snapshot()
        data = service.state_from_snapshot(snapshot)
        data["canon"] = load_canon()
        # `scene` already carries the clock/beat view the Story stage reads. When a
        # take is active, merge its scene card into the same object so both the old
        # dashboard keys and the new take fields stay available.
        clock = clock_view(clock=snapshot["clock"])
        take = take_snapshot_from_snapshot(snapshot)
        take_scene = take.get("scene")
        data["scene"] = {**clock, **take_scene} if take_scene else clock
        data["take"] = take.get("take")
        data["take_index"] = take.get("take_index")
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
        if not dev_enabled():
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

    # ---- takes (short, recordable scripts on top of a scenario) ----------

    @app.get("/api/takes")
    def takes():
        return {"takes": list_takes()}

    @app.get("/api/takes/current")
    def takes_current():
        return current_take(service)

    @app.post("/api/takes/{take_id}/load")
    def takes_load(take_id: str):
        if not dev_enabled():
            raise HTTPException(404)
        try:
            return load_take(service, take_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/takes/next")
    def takes_next(payload: dict | None = None):
        if not dev_enabled():
            raise HTTPException(404)
        payload = payload or {}
        request_id = _request_id(payload)
        digest = _digest({"force": bool(payload.get("force"))})
        replayed = _replay(service, "takes/next", request_id, digest)
        if replayed is not None:
            return replayed
        _check_revision(service, _expected_revision(payload))
        try:
            result = next_scene(service, force=bool(payload.get("force")))
        except TakeNotChanged as exc:
            raise HTTPException(
                409,
                detail={"error": "NOTHING_CHANGED", "detail": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        result["revision"] = service.revision()
        if request_id:
            service.store_idempotent("takes/next", request_id, digest, result)
        return result

    @app.post("/api/takes/cue")
    def takes_cue(payload: dict | None = None):
        """Internal/dev hook: apply the current scene's cues after a turn/choice."""
        if not dev_enabled():
            raise HTTPException(404)
        payload = payload or {}
        raw_choice = payload.get("choice")
        try:
            choice = int(raw_choice) if raw_choice is not None else None
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "choice must be an integer") from exc
        try:
            return apply_cues(
                service,
                user_line=str(payload.get("line") or ""),
                choice=choice,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def clock_view(clock: dict | None = None) -> dict:
        from director.clock import current_beat, next_beat

        canon_data = load_canon()
        clock = clock or service.clock()
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
        if not dev_enabled():
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
        if not dev_enabled():
            raise HTTPException(404)
        from director.clock import advance_to_beat, advance_to_next, done_beats, next_unplayed
        from director.beats import run_beat

        payload = payload or {}
        if payload.get("offscreen"):
            # One public off-screen beat. No model call and no belief writes.
            try:
                if payload.get("minutes") is not None:
                    service.advance_time("director", int(payload["minutes"]))
                event = service.record_offscreen(
                    character=payload.get("character"),
                    kind=payload.get("kind"),
                )
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, str(exc)) from exc
            return {
                "offscreen": event,
                "clock": service.clock(),
                "view": clock_view(),
                "played": None,
                "revision": service.revision(),
            }
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
        # Befriending is a social action, not an authored-beat mutation: the
        # guest demo keeps it available with WORLD_DEV=0 so the phone can unlock.
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

    @app.post("/api/safety/pause")
    def safety_pause(payload: dict | None = None):
        """Pause or resume the scene. The flag lives in meta and is cleared explicitly."""
        payload = payload or {}
        raw = payload.get("paused", True)
        paused = raw if isinstance(raw, bool) else str(raw).lower() not in (
            "0", "false", "no", "off",
        )
        result = service.set_paused(paused)
        return {
            **result,
            "message": PAUSED_MESSAGE if paused else "The scene is running again.",
        }

    @app.post("/api/safety/resume")
    def safety_resume():
        return service.set_paused(False)

    @app.get("/api/safety")
    def safety():
        return {"paused": service.paused(), "revision": service.revision()}

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
        if not dev_enabled():
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
        if not dev_enabled():
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
        if service.paused():
            raise HTTPException(423, PAUSED_MESSAGE)
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
        if service.paused():
            raise HTTPException(423, PAUSED_MESSAGE)
        request_id = _request_id(payload)
        characters = payload.get("characters")
        message = str(payload.get("message") or "")
        digest = _digest(
            {
                "message": message,
                "characters": characters if isinstance(characters, list) else None,
            }
        )
        replayed = _replay(service, "group/say", request_id, digest)
        if replayed is not None:
            return replayed
        _check_revision(service, _expected_revision(payload))
        try:
            from switch_world.application.scene import say_in_group

            result = say_in_group(
                service,
                message,
                characters=characters if isinstance(characters, list) else None,
                transport=transport,
                timeout=float(payload.get("timeout") or 45.0),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"group scene failed: {exc}") from exc

        # A take owns the scene's deterministic cues. When a take is loaded, run the
        # current scene's matching cues after the turn and hand the trail back.
        if take_snapshot(service).get("take"):
            try:
                result["cues"] = apply_cues(service, user_line=message)
            except ValueError as exc:
                result["cues"] = {"applied": [], "changed": False, "error": str(exc)}
        result["revision"] = service.revision()
        result["turn_number"] = service.turn()
        if request_id:
            service.store_idempotent("group/say", request_id, digest, result)
        return result

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
        from world_engine.studio import studio_summary

        return studio_summary(service)

    @app.post("/api/dev/run-beat")
    def run_beat_endpoint(payload: dict | None = None):
        if not dev_enabled():
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
        if not dev_enabled():
            raise HTTPException(404)
        from director.beats import run_arc

        payload = payload or {}
        try:
            return run_arc(service, force_share=payload.get("force_share"))
        except Exception as exc:
            raise HTTPException(502, f"arc failed: {exc}") from exc

    @app.post("/api/dev/tavily-event")
    def tavily_event(payload: dict | None = None):
        if not dev_enabled():
            raise HTTPException(404)
        from director.tavily_beat import fetch_world_event

        payload = payload or {}
        try:
            return fetch_world_event(service, query=payload.get("query"))
        except Exception as exc:
            raise HTTPException(502, f"Tavily event failed: {exc}") from exc

    @app.post("/api/dev/run-bifrost")
    def run_bifrost():
        if not dev_enabled():
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
        if not dev_enabled():
            raise HTTPException(404)
        service.reset()
        return {"ok": True, "state": service.state()}

    return app

