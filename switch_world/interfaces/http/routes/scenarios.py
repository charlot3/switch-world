"""Scenario and ending routes (recordable demo worlds)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from world_engine.scenarios import evaluate_ending, list_scenarios, load_scenario

from .. import schemas
from ..deps import HttpRuntime, clock_view, get_runtime, load_canon
from ..errors import NotFound

router = APIRouter()


@router.get("/api/scenarios", response_model=schemas.ScenariosResponse)
def scenarios():
    return {"scenarios": list_scenarios()}


@router.get(
    "/api/scenarios/current", response_model=schemas.ScenarioCurrentResponse
)
def current_scenario(runtime: HttpRuntime = Depends(get_runtime)):
    return {"scenario": runtime.service.current_scenario()}


@router.post(
    "/api/scenarios/{scenario_id}/load", response_model=schemas.ScenarioLoadResponse
)
def load_scenario_endpoint(
    scenario_id: str, runtime: HttpRuntime = Depends(get_runtime)
):
    if not runtime.dev_enabled():
        raise NotFound()
    service = runtime.service
    scenario = load_scenario(service, scenario_id)
    state = service.state()
    state["canon"] = load_canon()
    state["scene"] = clock_view(service)
    return {"scenario": scenario, "state": state}


@router.post("/api/endings/evaluate", response_model=schemas.EndingResponse)
def endings_evaluate(runtime: HttpRuntime = Depends(get_runtime)):
    return evaluate_ending(runtime.service)


__all__ = ["router"]
