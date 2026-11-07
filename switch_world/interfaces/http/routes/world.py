"""World state, clock, friends, safety and dashboard routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from world_engine import config
from world_engine.takes import take_snapshot_from_snapshot

from .. import schemas
from ..deps import (
    HttpRuntime,
    clock_view,
    get_runtime,
    load_canon,
    payload_value,
)
from ..errors import BadRequest

router = APIRouter()


@router.get("/", response_class=FileResponse, include_in_schema=False)
def index(runtime: HttpRuntime = Depends(get_runtime)):
    web_dir = runtime.settings.web_dir if runtime.settings is not None else config.WEB_DIR
    return FileResponse(web_dir / "index.html")


@router.get("/api/state", response_model=schemas.StateResponse)
def state(runtime: HttpRuntime = Depends(get_runtime)):
    service = runtime.service
    # One store snapshot for the whole projection: clock, take and every
    # subprojection come from the same read.
    snapshot = service.store.reader.snapshot()
    data = service.state_from_snapshot(snapshot)
    data["canon"] = load_canon(runtime)
    # `scene` already carries the clock/beat view the Story stage reads. When a
    # take is active, merge its scene card into the same object so both the old
    # dashboard keys and the new take fields stay available.
    clock = clock_view(service, clock=snapshot["clock"], runtime=runtime)
    take = take_snapshot_from_snapshot(snapshot)
    take_scene = take.get("scene")
    data["scene"] = {**clock, **take_scene} if take_scene else clock
    data["take"] = take.get("take")
    data["take_index"] = take.get("take_index")
    return data


@router.get("/api/canon", response_model=schemas.CanonResponse)
def canon(runtime: HttpRuntime = Depends(get_runtime)):
    return load_canon(runtime)


@router.get("/api/matrix", response_model=schemas.MatrixResponse)
def matrix(runtime: HttpRuntime = Depends(get_runtime)):
    service = runtime.service
    return {"matrix": service.matrix(), "clock": service.clock()}


# ---- clock ----------------------------------------------------------------


@router.get("/api/clock", response_model=schemas.ClockResponse)
def clock(runtime: HttpRuntime = Depends(get_runtime)):
    return clock_view(runtime.service, runtime=runtime)


@router.post("/api/clock/mode", response_model=schemas.ClockModeResponse)
def clock_mode(
    payload: schemas.ClockModeRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        from ..errors import NotFound

        raise NotFound()
    from director.clock import align_realtime

    service = runtime.service
    mode = str(payload_value(payload, "mode") or "").strip()
    raw_scale = payload_value(payload, "scale")
    try:
        scale = None if raw_scale is None else float(raw_scale)
        if mode == "realtime":
            result = align_realtime(service, load_canon(runtime), scale=scale)
            return {
                **result,
                "clock": service.clock(),
                "view": clock_view(service, runtime=runtime),
            }
        if mode == "mock":
            service.set_clock_mode("mock", scale=scale)
            return {
                "clock": service.clock(),
                "view": clock_view(service, runtime=runtime),
            }
        raise BadRequest("mode must be mock or realtime")
    except (TypeError, ValueError) as exc:
        raise BadRequest(str(exc)) from exc


@router.post("/api/clock/advance", response_model=schemas.ClockAdvanceResponse)
def clock_advance(
    payload: schemas.ClockAdvanceRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        from ..errors import NotFound

        raise NotFound()
    from director.beats import run_beat
    from director.clock import advance_to_beat, advance_to_next, done_beats, next_unplayed

    from ..errors import BadGateway

    service = runtime.service
    if payload_value(payload, "offscreen"):
        # One public off-screen beat. No model call and no belief writes.
        try:
            minutes = payload_value(payload, "minutes")
            if minutes is not None:
                service.advance_time("director", int(minutes))
            event = service.record_offscreen(
                character=payload_value(payload, "character"),
                kind=payload_value(payload, "kind"),
            )
        except (TypeError, ValueError) as exc:
            raise BadRequest(str(exc)) from exc
        return {
            "offscreen": event,
            "clock": service.clock(),
            "view": clock_view(service, runtime=runtime),
            "played": None,
            "revision": service.revision(),
        }
    canon_data = load_canon(runtime)
    try:
        explicit = str(payload_value(payload, "beat")) if payload_value(payload, "beat") else None
        if payload_value(payload, "run") and not explicit:
            # Fast-forward the arc: play the first beat that has not happened yet.
            upcoming = next_unplayed(canon_data, done_beats(service))
            if upcoming is None:
                view = clock_view(service, runtime=runtime)
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
        if payload_value(payload, "run") and explicit:
            played = run_beat(service, beat_id, transport="local")
        return {
            "beat": moved["beat"],
            "clock": service.clock(),
            "view": clock_view(service, runtime=runtime),
            "played": played,
        }
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    except Exception as exc:
        raise BadGateway(f"clock advance failed: {exc}") from exc


# ---- friends --------------------------------------------------------------


@router.get("/api/friends", response_model=schemas.FriendsResponse)
def friends(runtime: HttpRuntime = Depends(get_runtime)):
    return {"friends": runtime.service.friends()}


@router.post("/api/friends/{character}", response_model=schemas.FriendResponse)
def add_friend(character: str, runtime: HttpRuntime = Depends(get_runtime)):
    # Befriending is a social action, not an authored-beat mutation: the guest
    # demo keeps it available with WORLD_DEV=0 so the phone can unlock.
    service = runtime.service
    friend = service.add_friend(character)
    service.record_event(
        "user",
        "friend",
        f"You added {character.title()} as a friend. The phone is open.",
        participants=[character],
        visibility="public",
    )
    return {"friend": friend, "friends": service.friends(), "state": service.state()}


# ---- safety ---------------------------------------------------------------


PAUSED_MESSAGE = "The scene is paused. Resume when you are ready."


@router.post("/api/safety/pause", response_model=schemas.SafetyPauseResponse)
def safety_pause(
    payload: schemas.SafetyPauseRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    """Pause or resume the scene. The flag lives in meta and is cleared explicitly."""
    raw = payload_value(payload, "paused", True)
    if isinstance(raw, bool):
        paused = raw
    elif raw is None:
        paused = True
    else:
        paused = str(raw).lower() not in ("0", "false", "no", "off")
    result = runtime.service.set_paused(paused)
    return {
        **result,
        "message": PAUSED_MESSAGE if paused else "The scene is running again.",
    }


@router.post("/api/safety/resume", response_model=schemas.SafetyResponse)
def safety_resume(runtime: HttpRuntime = Depends(get_runtime)):
    return runtime.service.set_paused(False)


@router.get("/api/safety", response_model=schemas.SafetyResponse)
def safety(runtime: HttpRuntime = Depends(get_runtime)):
    service = runtime.service
    return {"paused": service.paused(), "revision": service.revision()}


# ---- ledger ---------------------------------------------------------------


@router.get("/api/who-knows/{key}", response_model=schemas.WhoKnowsResponse)
def who_knows(key: str, runtime: HttpRuntime = Depends(get_runtime)):
    return runtime.service.who_knows(key)
