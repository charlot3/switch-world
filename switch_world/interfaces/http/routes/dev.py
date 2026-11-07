"""Development routes. Every route here is disabled unless WORLD_DEV is on."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from .. import schemas
from ..deps import (
    HttpRuntime,
    get_runtime,
    payload_value,
    render_scene_card,
    require_artifacts,
)
from ..errors import BadGateway, BadRequest, NotFound

router = APIRouter()


@router.post("/api/dev/tell-alice", response_model=schemas.TellAliceResponse)
def tell_alice(
    payload: schemas.TellAliceRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        raise NotFound()
    from director.simulate import user_tells_alice

    secret = payload_value(payload, "secret") or (
        "I've decided to leave the city at the end of the month. "
        "I haven't told the others yet."
    )
    key = payload_value(payload, "key") or "user-leaving-city"
    service = runtime.service
    belief = user_tells_alice(service, secret=secret, key=key)
    return {"belief": belief, "matrix": service.matrix()}


@router.post("/api/dev/run-cafe", response_model=schemas.RunCafeResponse)
def run_cafe(
    payload: schemas.RunCafeRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        raise NotFound()
    from director.simulate import run_cafe as run_cafe_use_case

    try:
        return run_cafe_use_case(
            runtime.service, force_share=payload_value(payload, "force_share")
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    except Exception as exc:
        raise BadGateway(f"cafe failed: {exc}") from exc


@router.post("/api/dev/run-beat", response_model=schemas.RunBeatResponse)
def run_beat_endpoint(
    payload: schemas.RunBeatRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        raise NotFound()
    from director.beats import run_beat

    beat = payload_value(payload, "beat") or "cafe"
    transport = payload_value(payload, "transport") or "local"
    try:
        return run_beat(
            runtime.service,
            beat,
            transport=transport,
            force_share=payload_value(payload, "force_share"),
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    except Exception as exc:
        raise BadGateway(f"beat failed: {exc}") from exc


@router.post("/api/dev/run-arc", response_model=schemas.RunArcResponse)
def run_arc_endpoint(
    payload: schemas.RunArcRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        raise NotFound()
    from director.beats import run_arc

    try:
        return run_arc(
            runtime.service, force_share=payload_value(payload, "force_share")
        )
    except Exception as exc:
        raise BadGateway(f"arc failed: {exc}") from exc


@router.post("/api/dev/tavily-event", response_model=schemas.TavilyEventResponse)
def tavily_event(
    payload: schemas.TavilyEventRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        raise NotFound()
    from director.tavily_beat import fetch_world_event

    try:
        return fetch_world_event(
            runtime.service, query=payload_value(payload, "query")
        )
    except Exception as exc:
        raise BadGateway(f"Tavily event failed: {exc}") from exc


@router.post("/api/dev/run-bifrost", response_model=schemas.RunBifrostResponse)
def run_bifrost(runtime: HttpRuntime = Depends(get_runtime)):
    if not runtime.dev_enabled():
        raise NotFound()
    from director.bifrost_scene import run_cafe_bifrost

    try:
        return run_cafe_bifrost(runtime.service)
    except Exception as exc:
        raise BadGateway(f"Bifrost beat failed: {exc}") from exc


@router.post(
    "/api/dev/scene-card/export", response_model=schemas.SceneCardExportResponse
)
def export_scene_card(
    payload: schemas.SceneCardExportRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    """Explicitly write the scene card through the artifact store.

    The read route never writes; this is the only handler that does.
    """
    if not runtime.dev_enabled():
        raise NotFound()
    artifacts = require_artifacts(runtime)
    card = render_scene_card(runtime.service, payload_value(payload, "title"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        ref = artifacts.write(f"scene-card-{stamp}.md", card["text"])
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    return {
        "name": ref.name,
        "path": ref.path,
        "media_type": ref.media_type,
        "size": ref.size,
    }


@router.post("/api/dev/reset", response_model=schemas.ResetResponse)
def reset(runtime: HttpRuntime = Depends(get_runtime)):
    if not runtime.dev_enabled():
        raise NotFound()
    service = runtime.service
    service.reset()
    return {"ok": True, "state": service.state()}


__all__ = ["router"]
