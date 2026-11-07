"""Scene routes: scene card, direct messages, group turn and whisper."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from world_engine.takes import apply_cues, take_snapshot

from .. import schemas
from ..deps import (
    HttpRuntime,
    check_revision,
    digest,
    expected_revision,
    get_runtime,
    payload_value,
    render_scene_card,
    replay,
    request_id,
    require_model,
    require_transport,
)
from ..errors import (
    BadGateway,
    BadRequest,
    Forbidden,
    Locked,
    NotFound,
    ServiceUnavailable,
)

router = APIRouter()

PAUSED_MESSAGE = "The scene is paused. Resume when you are ready."


# ---- scene card -----------------------------------------------------------


@router.get("/api/scene-card", response_model=schemas.SceneCardResponse)
def scene_card(runtime: HttpRuntime = Depends(get_runtime)):
    """Render the card from one snapshot. A GET never writes an artifact."""
    return render_scene_card(runtime.service)


@router.get(
    "/api/scene-card.md",
    response_class=PlainTextResponse,
    response_model=str,
    responses={
        200: {
            "content": {"text/markdown": {"schema": {"type": "string"}}},
            "description": "The rendered scene card",
        }
    },
)
def scene_card_md(runtime: HttpRuntime = Depends(get_runtime)):
    card = render_scene_card(runtime.service)
    return PlainTextResponse(
        card["text"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="scene-card.md"'},
    )


# ---- direct messages ------------------------------------------------------


@router.get("/api/dm/{character}", response_model=schemas.DmHistoryResponse)
def dm_history(
    character: str,
    limit: int = 100,
    before_id: int | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    service = runtime.service
    if not service.character_exists(character):
        raise NotFound(f"unknown character: {character}")
    if not service.is_friend(character):
        raise Forbidden(
            f"Add {character.title()} as a friend before opening the phone."
        )
    return service.phone_history(character, limit=limit, before_id=before_id)


@router.post("/api/dm", response_model=schemas.DmResponse)
def dm(
    payload: schemas.DmRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    service = runtime.service
    if service.paused():
        raise Locked(PAUSED_MESSAGE)
    character = str(payload_value(payload, "character") or "")
    if not service.character_exists(character):
        raise NotFound(f"unknown character: {character}")
    if not service.is_friend(character):
        raise Forbidden(
            f"Add {character.title()} as a friend before messaging them."
        )
    message = str(payload_value(payload, "message") or "")
    if not runtime.legacy_compat:
        model = require_model(runtime)
    try:
        if runtime.legacy_compat:
            # The shim keeps HEAD's lazy client construction and the tests that
            # patch it; the composition-root path never reaches this branch.
            from director.dm import reply_to_dm

            return reply_to_dm(service, character=character, message=message)
        from switch_world.application.scene import dm as dm_use_case

        return dm_use_case(service, character=character, message=message, model=model)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    except Exception as exc:
        raise BadGateway(f"DM failed: {exc}") from exc


# ---- group turn -----------------------------------------------------------


@router.post("/api/group/say", response_model=schemas.GroupSayResponse)
def group_say(
    payload: schemas.GroupSayRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    from switch_world.application.scene import say_in_group

    service = runtime.service
    if service.paused():
        raise Locked(PAUSED_MESSAGE)
    request_id_value = request_id(payload)
    characters = payload_value(payload, "characters")
    message = str(payload_value(payload, "message") or "")
    request_digest = digest(
        {
            "message": message,
            "characters": characters if isinstance(characters, list) else None,
        }
    )
    replayed = replay(service, "group/say", request_id_value, request_digest)
    if replayed is not None:
        return replayed
    check_revision(service, expected_revision(payload))
    transport = require_transport(runtime)
    try:
        raw_timeout = payload_value(payload, "timeout")
        timeout = float(raw_timeout or 45.0)
        result = say_in_group(
            service,
            message,
            characters=characters if isinstance(characters, list) else None,
            transport=transport,
            timeout=timeout,
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    except Exception as exc:
        raise BadGateway(f"group scene failed: {exc}") from exc

    # A take owns the scene's deterministic cues. When a take is loaded, run the
    # current scene's matching cues after the turn and hand the trail back.
    if take_snapshot(service).get("take"):
        try:
            result["cues"] = apply_cues(service, user_line=message)
        except ValueError as exc:
            result["cues"] = {"applied": [], "changed": False, "error": str(exc)}
    result["revision"] = service.revision()
    result["turn_number"] = service.turn()
    if request_id_value:
        service.store_idempotent(
            "group/say", request_id_value, request_digest, result
        )
    return result


@router.post("/api/group/whisper", response_model=schemas.WhisperResponse)
def group_whisper(
    payload: schemas.WhisperRequest | None = None,
    runtime: HttpRuntime = Depends(get_runtime),
):
    service = runtime.service
    to = str(payload_value(payload, "to") or "")
    message = str(payload_value(payload, "message") or "")
    try:
        raw_timeout = payload_value(payload, "timeout")
        timeout = float(raw_timeout or 35.0)
        if runtime.legacy_compat:
            from director.whisper import whisper_to_character

            return whisper_to_character(
                service, to=to, message=message, timeout=timeout
            )
        if runtime.model is None:
            # A private room can answer without a model; the staged path cannot.
            capable = False
            if runtime.transport is not None:
                try:
                    capable = bool(runtime.transport.capabilities().private_rooms)
                except Exception:
                    capable = False
            if not capable:
                require_model(runtime)
        from switch_world.application.scene import whisper

        return whisper(
            service,
            to=to,
            message=message,
            model=runtime.model,
            transport=runtime.transport,
            timeout=timeout,
        )
    except ServiceUnavailable:
        raise
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    except Exception as exc:
        raise BadGateway(f"whisper failed: {exc}") from exc


__all__ = ["router"]
