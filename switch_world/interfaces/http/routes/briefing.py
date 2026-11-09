"""Read-only projection of the latest pre-meeting briefing.

``POST /api/dev/briefing`` is the only route that prepares a briefing and writes
its artifact. This route serves what is already on disk from the latest
``briefing`` event and never creates or rewrites a file.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from .. import schemas
from ..deps import HttpRuntime, get_runtime
from ..errors import NotFound

router = APIRouter()


def _latest(runtime: HttpRuntime) -> tuple[dict, dict, str]:
    event = runtime.service.latest_event("briefing")
    if not event:
        raise NotFound("no briefing has been prepared yet")
    metadata = event.get("metadata") or {}
    path = metadata.get("path")
    if not path:
        raise NotFound("the latest briefing has no artifact path")
    artifact = Path(str(path))
    if not artifact.is_file():
        raise NotFound(f"briefing artifact not found: {artifact}")
    return event, metadata, artifact.read_text(encoding="utf-8")


@router.get(
    "/api/briefing/latest", response_model=schemas.BriefingLatestResponse
)
def latest_briefing(runtime: HttpRuntime = Depends(get_runtime)):
    """The newest briefing event plus the markdown page it points at."""
    event, metadata, markdown = _latest(runtime)
    return {
        "subject": metadata.get("subject"),
        "meeting": metadata.get("meeting"),
        "briefing": markdown,
        "path": metadata.get("path"),
        "name": metadata.get("name"),
        "sources": metadata.get("source_list") or [],
        "offline": metadata.get("offline"),
        "event": event,
    }


@router.get("/api/briefing/latest.md", response_class=PlainTextResponse)
def latest_briefing_markdown(runtime: HttpRuntime = Depends(get_runtime)):
    """The same page as a plain markdown download."""
    _, _, markdown = _latest(runtime)
    return PlainTextResponse(markdown, media_type="text/markdown; charset=utf-8")


__all__ = ["router"]
