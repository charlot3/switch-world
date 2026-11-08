"""Studio rail (health chips, beat clock, cast and recent feed)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from switch_world.application.studio import studio_summary

from .. import schemas
from ..deps import HttpRuntime, get_runtime

router = APIRouter()


@router.get("/api/studio/summary", response_model=schemas.StudioSummaryResponse)
def studio_summary_endpoint(runtime: HttpRuntime = Depends(get_runtime)):
    return studio_summary(runtime.service)


__all__ = ["router"]
