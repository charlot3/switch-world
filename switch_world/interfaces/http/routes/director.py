"""Director/operator routes: Switch room export and provider usage."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import timezone

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from .. import schemas
from ..deps import HttpRuntime, get_runtime, require_model, require_transport
from ..errors import BadGateway

router = APIRouter()


def _log_event(room, turn) -> dict:
    """One neutral transport turn in the historical JSONL shape."""
    received_at = turn.received_at
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    return {
        "room_id": room.room_id,
        "room_name": room.name,
        "event_id": str(turn.event_id),
        "kind": "message",
        "sender": str(turn.sender),
        "sender_name": str(turn.sender),
        "timestamp": int(received_at.timestamp() * 1000),
        "timestamp_iso": received_at.isoformat(),
        "body": turn.text,
        "attachments": [],
    }


@router.get(
    "/api/switch-log",
    response_class=PlainTextResponse,
    response_model=str,
    responses={
        200: {
            "content": {
                "application/x-ndjson": {"schema": {"type": "string"}}
            },
            "description": "One JSON object per transport event",
        }
    },
)
def switch_log(
    room: str | None = "world", runtime: HttpRuntime = Depends(get_runtime)
):
    """Export room history through the transport port, never a private op.

    The transport owns room lookup and ``history(room)``; this route only maps
    the returned turns to JSONL.  A caller that built no transport gets 503,
    not a client constructed on the request path.
    """
    transport = require_transport(runtime)
    # The port exposes history by room, not a provider-wide listing. "all" is
    # the dashboard's name for the public room this app writes.
    names = ["world"] if room in (None, "all") else [room]
    events: list[dict] = []
    try:
        for name in names:
            handle = transport.open_room(name=name)
            events.extend(_log_event(handle, turn) for turn in transport.history(handle))
    except Exception as exc:
        raise BadGateway(f"Switch log failed: {exc}") from exc
    events.sort(key=lambda item: item.get("timestamp") or 0)
    body = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
    return PlainTextResponse(
        body,
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="switch-log.jsonl"'},
    )


@router.get("/api/bifrost/usage", response_model=schemas.BifrostUsageResponse)
def bifrost_usage(runtime: HttpRuntime = Depends(get_runtime)):
    """The configured model's usage block; 503 when no provider is configured."""
    model = require_model(runtime)
    summary = getattr(model, "usage_summary", None)
    if callable(summary):
        value = summary()
        if isinstance(value, dict):
            return value
        return {"usage": value}
    usage = getattr(model, "usage", None)
    if callable(usage):
        return asdict(usage())
    raise BadGateway("the configured model exposes no usage summary")


__all__ = ["router"]
