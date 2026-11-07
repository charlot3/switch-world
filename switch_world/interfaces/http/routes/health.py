"""Liveness route."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import schemas
from ..deps import HttpRuntime, get_runtime

router = APIRouter()


@router.get("/health", response_model=schemas.HealthResponse)
def health(runtime: HttpRuntime = Depends(get_runtime)):
    return {
        "ok": True,
        "dev": runtime.dev_enabled(),
        "clock": runtime.service.clock(),
    }


__all__ = ["router"]
