"""Take routes (short, recordable scripts on top of a scenario)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from switch_world.application.takes import (
    TakeNotChanged,
    apply_cues,
    current_take,
    list_takes,
    load_take,
    next_scene,
)

from .. import schemas
from ..deps import (
    HttpRuntime,
    check_revision,
    digest,
    expected_revision,
    get_runtime,
    payload_value,
    replay,
    request_id,
)
from ..errors import BadRequest, Conflict, NotFound

router = APIRouter()


@router.get("/api/takes", response_model=schemas.TakesResponse)
def takes():
    return {"takes": list_takes()}


@router.get("/api/takes/current", response_model=schemas.TakeCurrentResponse)
def takes_current(runtime: HttpRuntime = Depends(get_runtime)):
    return current_take(runtime.service)


@router.post("/api/takes/{take_id}/load", response_model=schemas.TakeLoadResponse)
def takes_load(take_id: str, runtime: HttpRuntime = Depends(get_runtime)):
    if not runtime.dev_enabled():
        raise NotFound()
    return load_take(runtime.service, take_id)


@router.post("/api/takes/next", response_model=schemas.TakeNextResponse)
def takes_next(
    payload: schemas.TakesNextRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    if not runtime.dev_enabled():
        raise NotFound()
    service = runtime.service
    request_id_value = request_id(payload)
    request_digest = digest({"force": bool(payload_value(payload, "force"))})
    replayed = replay(service, "takes/next", request_id_value, request_digest)
    if replayed is not None:
        return replayed
    check_revision(service, expected_revision(payload))
    try:
        result = next_scene(service, force=bool(payload_value(payload, "force")))
    except TakeNotChanged as exc:
        raise Conflict(
            {"error": "NOTHING_CHANGED", "detail": str(exc)}
        ) from exc
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    result["revision"] = service.revision()
    if request_id_value:
        service.store_idempotent(
            "takes/next", request_id_value, request_digest, result
        )
    return result


@router.post("/api/takes/cue", response_model=schemas.CueResponse)
def takes_cue(
    payload: schemas.TakesCueRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    """Internal/dev hook: apply the current scene's cues after a turn/choice."""
    if not runtime.dev_enabled():
        raise NotFound()
    raw_choice = payload_value(payload, "choice")
    try:
        choice = int(raw_choice) if raw_choice is not None else None
    except (TypeError, ValueError) as exc:
        raise BadRequest("choice must be an integer") from exc
    try:
        return apply_cues(
            runtime.service,
            user_line=str(payload_value(payload, "line") or ""),
            choice=choice,
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


__all__ = ["router"]
