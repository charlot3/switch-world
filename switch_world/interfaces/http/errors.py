"""HTTP error vocabulary and the one place domain failures become responses.

Routes raise a small typed error (or let a domain error escape) and this module
translates it once.  Keeping the mapping here means a route never builds a
``JSONResponse`` and every endpoint reports the same failure in the same shape.

Mapping:

======================  ======  ==========================================
error                     status  body
======================  ======  ==========================================
``BadRequest``            400    ``{"detail": "<message>"}``
``Forbidden``             403    ``{"detail": "<message>"}``
``NotFound``              404    ``{"detail": "Not Found"}``
``Conflict``              409    ``{"detail": "<message or object>"}``
``Locked``                423    ``{"detail": "<message>"}``
``BadGateway``            502    ``{"detail": "<message>"}``
``ServiceUnavailable``    503    ``{"detail": "<message>"}``
``ValueError``            400    ``{"detail": "<message>"}``
``PermissionError``       403    ``{"detail": "<message>"}``
``IdempotencyConflict``   409    ``{"detail": {"error": "REQUEST_CONFLICT", ...}}``
``TakeNotChanged``        409    ``{"detail": {"error": "NOTHING_CHANGED", ...}}``
``TakeError``             400    ``{"detail": "<message>"}``
``TransportError``        502    ``{"detail": "transport failed: ..."}``
``ModelError``            502    ``{"detail": "model failed: ..."}``
``ArtifactNotFound``      404    ``{"detail": "<message>"}``
======================  ======  ==========================================
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from switch_world.domain.models import IdempotencyConflict
from switch_world.domain.ports.artifacts import ArtifactNotFound
from switch_world.domain.ports.model import ModelError
from switch_world.domain.ports.transport import TransportError
from switch_world.application.takes import TakeError, TakeNotChanged


class APIError(Exception):
    """A failure the HTTP boundary knows how to render."""

    status_code = 500
    default_detail: Any = "Internal Server Error"

    def __init__(
        self,
        detail: Any | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.detail = self.default_detail if detail is None else detail
        self.headers = headers
        super().__init__(str(self.detail))


class BadRequest(APIError):
    status_code = 400
    default_detail = "Bad Request"


class Forbidden(APIError):
    status_code = 403
    default_detail = "Forbidden"


class NotFound(APIError):
    status_code = 404
    default_detail = "Not Found"


class Conflict(APIError):
    status_code = 409
    default_detail = "Conflict"


class Locked(APIError):
    status_code = 423
    default_detail = "Locked"


class BadGateway(APIError):
    status_code = 502
    default_detail = "Bad Gateway"


class ServiceUnavailable(APIError):
    status_code = 503
    default_detail = "Service Unavailable"


def error_body(detail: Any) -> dict[str, Any]:
    """The historical FastAPI ``HTTPException`` body shape."""
    return {"detail": detail}


def _response(status_code: int, detail: Any, headers: dict[str, str] | None = None):
    return JSONResponse(
        status_code=status_code,
        content=error_body(detail),
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach the domain-to-HTTP mapping to an app exactly once."""

    @app.exception_handler(APIError)
    async def _api_error(_request: Request, exc: APIError):
        return _response(exc.status_code, exc.detail, exc.headers)

    @app.exception_handler(IdempotencyConflict)
    async def _idempotency_conflict(_request: Request, exc: IdempotencyConflict):
        return _response(
            409, {"error": "REQUEST_CONFLICT", "detail": str(exc)}
        )

    @app.exception_handler(TakeNotChanged)
    async def _take_not_changed(_request: Request, exc: TakeNotChanged):
        return _response(
            409, {"error": "NOTHING_CHANGED", "detail": str(exc)}
        )

    @app.exception_handler(TakeError)
    async def _take_error(_request: Request, exc: TakeError):
        return _response(400, str(exc))

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError):
        return _response(400, str(exc))

    @app.exception_handler(PermissionError)
    async def _permission_error(_request: Request, exc: PermissionError):
        return _response(403, str(exc))

    @app.exception_handler(ArtifactNotFound)
    async def _artifact_not_found(_request: Request, exc: ArtifactNotFound):
        return _response(404, str(exc))

    @app.exception_handler(TransportError)
    async def _transport_error(_request: Request, exc: TransportError):
        return _response(502, f"transport failed: {exc}")

    @app.exception_handler(ModelError)
    async def _model_error(_request: Request, exc: ModelError):
        return _response(502, f"model failed: {exc}")


__all__ = [
    "APIError",
    "BadGateway",
    "BadRequest",
    "Conflict",
    "Forbidden",
    "Locked",
    "NotFound",
    "ServiceUnavailable",
    "error_body",
    "register_error_handlers",
]
