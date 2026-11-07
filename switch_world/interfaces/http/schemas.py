"""Typed request and response bodies for the HTTP adapter.

The v1 app accepted an untyped optional payload dictionary on every mutating
route and returned untyped dictionaries.  The models here give the OpenAPI
document a shape without changing any path, method or JSON field: response
models inherit :class:`OpenModel`, which allows keys the dashboard adds over
time.

Request models stay deliberately permissive for fields the old handlers parsed
by hand (``expected_revision``, ``choice``, ``scale``).  Keeping ``int | str``
lets the route preserve the historical 400 for a malformed value instead of
turning it into FastAPI's 422.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class OpenModel(BaseModel):
    """A response model that keeps any field the handler returns."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class TakesNextRequest(BaseModel):
    force: bool = False
    request_id: str | None = None
    expected_revision: int | str | None = None


class TakesCueRequest(BaseModel):
    line: str = ""
    choice: int | str | None = None


class ClockModeRequest(BaseModel):
    mode: str = ""
    scale: float | str | None = None


class ClockAdvanceRequest(BaseModel):
    offscreen: bool = False
    minutes: int | str | None = None
    character: str | None = None
    kind: str | None = None
    beat: str | None = None
    run: bool = False


class SafetyPauseRequest(BaseModel):
    paused: bool | str | None = True


class TellAliceRequest(BaseModel):
    secret: str | None = None
    key: str | None = None


class RunCafeRequest(BaseModel):
    force_share: bool | None = None


class DmRequest(BaseModel):
    character: str = ""
    message: str = ""


class GroupSayRequest(BaseModel):
    message: str = ""
    characters: list[str] | str | None = None
    timeout: float | str | None = None
    request_id: str | None = None
    expected_revision: int | str | None = None


class WhisperRequest(BaseModel):
    to: str = ""
    message: str = ""
    timeout: float | str | None = None


class RunBeatRequest(BaseModel):
    beat: str = "cafe"
    transport: str = "local"
    force_share: bool | None = None


class RunArcRequest(BaseModel):
    force_share: bool | None = None


class TavilyEventRequest(BaseModel):
    query: str | None = None


class SceneCardExportRequest(BaseModel):
    title: str | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    ok: bool
    dev: bool
    clock: dict[str, Any]


class StateResponse(BaseModel):
    clock: dict[str, Any]
    revision: int
    turn: int
    paused: bool
    characters: list[Any]
    beliefs: list[Any]
    relationships: list[Any]
    events: list[Any]
    friends: list[Any]
    absent_characters: list[Any]
    done_beats: list[Any]
    branch: Any
    matrix: list[Any]
    scenario: dict[str, Any] | None
    outfits: dict[str, Any]
    items: list[Any]
    item: Any
    cast_art: dict[str, Any]
    scene_art: Any
    connections: list[Any]
    canon: dict[str, Any]
    scene: dict[str, Any]
    take: dict[str, Any] | None
    take_index: int | None


class CanonResponse(OpenModel):
    """The authored story bible; its keys are data, not a stable schema."""


class MatrixResponse(BaseModel):
    matrix: list[Any]
    clock: dict[str, Any]


class ClockResponse(OpenModel):
    now: str | None = None
    mode: str | None = None
    scale: float | None = None
    current_beat: dict[str, Any] | None = None
    next_beat: dict[str, Any] | None = None
    next_at: str | None = None


class ScenariosResponse(BaseModel):
    scenarios: list[Any]


class ScenarioCurrentResponse(BaseModel):
    scenario: dict[str, Any] | None


class ScenarioLoadResponse(BaseModel):
    scenario: dict[str, Any]
    state: dict[str, Any]


class EndingResponse(OpenModel):
    """The ending projection carries narrative fields defined by the scenario."""


class TakesResponse(BaseModel):
    takes: list[Any]


class TakeCurrentResponse(BaseModel):
    take: dict[str, Any] | None
    scene: dict[str, Any] | None
    index: int | None
    state: dict[str, Any]


class TakeLoadResponse(BaseModel):
    take: dict[str, Any]
    scene: dict[str, Any]
    index: int
    state: dict[str, Any]


class TakeNextResponse(OpenModel):
    """A scene card with the take's dynamic fields."""


class CueResponse(OpenModel):
    changed: bool | None = None
    applied: list[Any] | None = None


class ClockModeResponse(OpenModel):
    clock: dict[str, Any] | None = None
    view: dict[str, Any] | None = None


class ClockAdvanceResponse(OpenModel):
    """A clock move: the keys depend on off-screen versus arc advance."""


class FriendsResponse(BaseModel):
    friends: list[Any]


class FriendResponse(BaseModel):
    friend: dict[str, Any]
    friends: list[Any]
    state: dict[str, Any]


class SafetyPauseResponse(OpenModel):
    paused: bool | None = None
    revision: int | None = None
    message: str | None = None


class SafetyResponse(BaseModel):
    paused: bool
    revision: int


class WhoKnowsResponse(OpenModel):
    key: str | None = None
    holders: list[Any] | None = None


class SceneCardResponse(BaseModel):
    path: str | None = None
    text: str


class SceneCardExportResponse(BaseModel):
    name: str
    path: str
    media_type: str
    size: int


class DmHistoryResponse(OpenModel):
    character: str | None = None
    messages: list[Any] | None = None
    has_more: bool | None = None


class DmResponse(OpenModel):
    character: str | None = None
    reply: str | None = None


class GroupSayResponse(OpenModel):
    turn: dict[str, Any] | None = None
    replies: list[Any] | None = None
    revision: int | None = None
    turn_number: int | None = None


class WhisperResponse(OpenModel):
    target: str | None = None
    reply: str | None = None
    transport: str | None = None


class StudioSummaryResponse(OpenModel):
    health: dict[str, bool] | None = None
    clock: dict[str, Any] | None = None


class TellAliceResponse(BaseModel):
    belief: dict[str, Any]
    matrix: list[Any]


class RunCafeResponse(OpenModel):
    shared: bool | None = None
    branch: dict[str, Any] | None = None


class RunBeatResponse(OpenModel):
    """A beat result; each runner contributes its own fields."""


class RunBifrostResponse(OpenModel):
    """The Bifrost café result (branch, transcript, bifrost usage)."""


class RunArcResponse(OpenModel):
    beats: list[Any] | None = None
    branch: dict[str, Any] | None = None


class TavilyEventResponse(OpenModel):
    """A real-world event: offline results carry a different key set."""


class BifrostUsageResponse(OpenModel):
    """The provider's usage block, whose keys are provider-specific."""


class ResetResponse(BaseModel):
    ok: bool
    state: dict[str, Any]


__all__ = [
    "BifrostUsageResponse",
    "CanonResponse",
    "ClockAdvanceRequest",
    "ClockAdvanceResponse",
    "ClockModeRequest",
    "ClockModeResponse",
    "ClockResponse",
    "CueResponse",
    "DmHistoryResponse",
    "DmRequest",
    "DmResponse",
    "EndingResponse",
    "FriendResponse",
    "FriendsResponse",
    "GroupSayRequest",
    "GroupSayResponse",
    "HealthResponse",
    "MatrixResponse",
    "OpenModel",
    "ResetResponse",
    "RunArcRequest",
    "RunArcResponse",
    "RunBeatRequest",
    "RunBeatResponse",
    "RunBifrostResponse",
    "RunCafeRequest",
    "RunCafeResponse",
    "SafetyPauseRequest",
    "SafetyPauseResponse",
    "SafetyResponse",
    "ScenarioCurrentResponse",
    "ScenarioLoadResponse",
    "ScenariosResponse",
    "SceneCardExportRequest",
    "SceneCardExportResponse",
    "SceneCardResponse",
    "StateResponse",
    "StudioSummaryResponse",
    "TakeCurrentResponse",
    "TakeLoadResponse",
    "TakeNextResponse",
    "TakesCueRequest",
    "TakesNextRequest",
    "TakesResponse",
    "TavilyEventRequest",
    "TavilyEventResponse",
    "TellAliceRequest",
    "TellAliceResponse",
    "WhisperRequest",
    "WhisperResponse",
    "WhoKnowsResponse",
]
