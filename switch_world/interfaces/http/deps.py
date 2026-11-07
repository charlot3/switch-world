"""HTTP dependencies: the app container, auth/actor resolution and helpers.

Every route receives one :class:`HttpRuntime`.  It is built by the composition
root when a :class:`~switch_world.container.Container` is supplied and by
:func:`build_runtime` for older ``create_app(service)`` callers, where it keeps
the historical lazy adapters so the director shims and test monkeypatches keep
working.

The route layer never constructs a provider.  It asks this module for the
transport, model or artifact store and gets a typed 503 when the composition
root did not supply one.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request

from switch_world.config import Settings
from switch_world.domain.ports.artifacts import ArtifactStore
from switch_world.domain.ports.model import ModelClient
from switch_world.domain.ports.transport import CharacterTransport
from world_engine import config
from world_engine.service import WorldService

from .errors import BadRequest, Conflict, Forbidden, ServiceUnavailable

CANON_PATH = config.ROOT / "world" / "canon.json"

REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
STALE_MESSAGE = "the world moved since you loaded it; refresh and try again"


@dataclass
class HttpRuntime:
    """The objects one HTTP request is allowed to use."""

    service: WorldService
    settings: Settings | None
    transport: CharacterTransport | None
    model: ModelClient | None
    artifacts: ArtifactStore | None
    # True only for a caller that did not build a composition container.
    # The DM and whisper routes keep the historical lazy shims on that path so
    # older tooling and tests that patch ``director.dm`` still work.
    legacy_compat: bool = False

    def dev_enabled(self) -> bool:
        """The composition root's setting wins over the ambient shim."""
        if self.settings is not None:
            return self.settings.dev_mode
        return config.DEV_MODE


def build_runtime(
    service: WorldService,
    settings: Settings | None,
    container: Any | None,
) -> HttpRuntime:
    """Resolve the typed HTTP container for both construction paths."""
    if container is not None:
        container_settings = getattr(container, "settings", None) or settings
        artifacts = getattr(container, "artifacts", None)
        if artifacts is None and container_settings is not None:
            from switch_world.adapters.artifacts.files import FileArtifactStore

            artifacts = FileArtifactStore(container_settings.export_dir)
        return HttpRuntime(
            service=service,
            settings=container_settings,
            transport=getattr(container, "transport", None),
            model=getattr(container, "model", None),
            artifacts=artifacts,
            legacy_compat=False,
        )

    from switch_world.adapters.artifacts.files import FileArtifactStore

    export_dir = settings.export_dir if settings is not None else config.EXPORT_DIR
    return HttpRuntime(
        service=service,
        settings=settings,
        transport=_legacy_transport(settings),
        model=None,
        artifacts=FileArtifactStore(export_dir),
        legacy_compat=True,
    )


def _legacy_transport(settings: Settings | None = None) -> CharacterTransport:
    """A deferred transport for a caller that built no container."""
    from switch_world.adapters.transports.legacy import deferred_transport

    mode = settings.agent_mode if settings is not None else config.AGENT_MODE
    return deferred_transport(mode)


def get_runtime(request: Request) -> HttpRuntime:
    """The container stored by :func:`create_app` (the dependency to inject)."""
    return request.app.state.runtime


# ---------------------------------------------------------------------------
# Optional authentication
# ---------------------------------------------------------------------------


def resolve_actor(request: Request, runtime: HttpRuntime) -> str | None:
    """The bearer-token actor, or ``None`` when no token was presented.

    A presented-but-invalid token is a real 403; an anonymous request keeps the
    historical public demo behaviour.  New write surfaces can call
    :func:`require_actor` to demand one.
    """
    authorization = request.headers.get("authorization") or ""
    if not authorization:
        return None
    try:
        return runtime.service.actor_from_headers(request.headers)
    except PermissionError as exc:
        raise Forbidden(str(exc)) from exc


def require_actor(request: Request, runtime: HttpRuntime) -> str:
    actor = resolve_actor(request, runtime)
    if actor is None:
        raise Forbidden("missing bearer token")
    return actor


# ---------------------------------------------------------------------------
# Request helpers shared by the mutating routes
# ---------------------------------------------------------------------------


def payload_value(payload: Any, key: str, default: Any = None) -> Any:
    if payload is None:
        return default
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def request_id(payload: Any) -> str | None:
    raw = payload_value(payload, "request_id")
    if raw is None:
        return None
    value = str(raw).strip()
    if not REQUEST_ID.match(value):
        raise BadRequest("request_id must be 8-64 characters of A-Za-z0-9_-")
    return value


def expected_revision(payload: Any) -> int | None:
    raw = payload_value(payload, "expected_revision")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise BadRequest("expected_revision must be an integer") from exc


def digest(values: dict[str, Any]) -> str:
    body = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def replay(
    service: WorldService, scope: str, request_id_value: str | None, request_digest: str
):
    if not request_id_value:
        return None
    # IdempotencyConflict is mapped by errors.py; no wrapping needed.
    return service.idempotent_replay(scope, request_id_value, request_digest)


def check_revision(service: WorldService, expected: int | None) -> None:
    if expected is None:
        return
    current = service.revision()
    if expected != current:
        raise Conflict(
            {
                "error": "STALE_REVISION",
                "revision": current,
                "expected_revision": expected,
                "detail": STALE_MESSAGE,
            }
        )


# ---------------------------------------------------------------------------
# Provider requirements
# ---------------------------------------------------------------------------


def require_transport(runtime: HttpRuntime) -> CharacterTransport:
    if runtime.transport is None:
        raise ServiceUnavailable(
            "no character transport is configured; build the app with a "
            "container that provides one"
        )
    return runtime.transport


def require_model(runtime: HttpRuntime) -> ModelClient:
    if runtime.model is None:
        raise ServiceUnavailable(
            "no model provider is configured; build the app with a container "
            "that provides one"
        )
    return runtime.model


def require_artifacts(runtime: HttpRuntime) -> ArtifactStore:
    if runtime.artifacts is None:
        raise ServiceUnavailable(
            "no artifact store is configured; build the app with a container "
            "that provides one"
        )
    return runtime.artifacts


# ---------------------------------------------------------------------------
# Read-only projections
# ---------------------------------------------------------------------------


def load_canon() -> dict:
    """The authored story bible. It is read-only state, not world state."""
    return json.loads(CANON_PATH.read_text(encoding="utf-8"))


def clock_view(service: WorldService, clock: dict | None = None) -> dict:
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


def render_scene_card(service: WorldService, title: str | None = None) -> dict:
    """Render a scene card from one snapshot and write nothing.

    The route that serves this must not leave an export behind; an explicit
    ``POST /api/dev/scene-card/export`` writes through the artifact store.
    """
    snapshot = service.store.reader.snapshot()
    state = service.state_from_snapshot(snapshot)
    clock = state["clock"]
    lines: list[str] = []
    lines.append("# Scene card — " + (title or "A Tuesday in late autumn"))
    lines.append("")
    lines.append(f"**World time:** {clock['now']}  ")
    lines.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Cast")
    lines.append("")
    for character in state["characters"]:
        lines.append(f"- **{character['name']}** — {character['role']}")
    lines.append("")
    lines.append("## What happened")
    lines.append("")
    for event in state["events"][-24:]:
        lines.append(
            f"- `{event['created_at']}` **{event['kind']}** — {event['summary']}"
        )
    lines.append("")
    lines.append("## Who knows what")
    lines.append("")
    for row in state["matrix"]:
        holders = row["holders"]
        if not holders:
            continue
        parts = []
        for character_id, cell in holders.items():
            source = cell["source"]
            parts.append(
                f"{character_id} {cell['confidence']:.2f} "
                f"({source}, {cell['visibility']})"
            )
        lines.append(f"- **{row['label']}** — " + "; ".join(parts))
    lines.append("")
    lines.append("## Relationship changes")
    lines.append("")
    changes = [event for event in state["events"] if event["kind"] == "relationship_update"]
    if changes:
        for event in changes[-12:]:
            lines.append(f"- `{event['created_at']}` {event['summary']}")
    else:
        lines.append("- None recorded.")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append("Every belief above names its source. A character can only read its own")
    lines.append("private beliefs through the world engine's scoped MCP token.")
    lines.append("")
    return {"path": None, "text": "\n".join(lines)}


__all__ = [
    "HttpRuntime",
    "build_runtime",
    "check_revision",
    "clock_view",
    "digest",
    "expected_revision",
    "get_runtime",
    "load_canon",
    "payload_value",
    "render_scene_card",
    "replay",
    "request_id",
    "require_actor",
    "require_artifacts",
    "require_model",
    "require_transport",
    "resolve_actor",
]
