"""Loadable demo scenarios: a reset plus an authored seed.

A scenario is a read-only JSON preset in `world/scenarios/`. Loading one resets the
world database and applies the seed (clock, friends, relationships, beliefs, outfits,
items and the scene/ending metadata). Switching is a reset, not a second engine, so one
scenario is live at a time and the dashboard always reads a coherent world.

The loader is deliberately strict. A typo in a cast id or a belief key must fail at the
boundary, not after a demo has already been recorded.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config
from .service import (
    CHARACTER_ORDER,
    VISIBILITIES,
    WorldService,
)

SCENARIO_DIR = Path(config.CONTENT_ROOT) / "scenarios"

# Authored order, not alphabetical: w5-good and w5-bad are a fork and should sit
# together in the Worlds rail.
SCENARIO_ORDER = [
    "w1-gift",
    "w2-two-clocks",
    "w3-quiet-route",
    "w4-three-of-us",
    "w5-good",
    "w5-bad",
    "w6-long-tuesday",
    "w7-last-call",
]

_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
KEY = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TONES = ("good", "bad", "neutral")


def _fail(path: Path, message: str) -> None:
    raise ValueError(f"{path.name}: {message}")


def _number(value: Any, path: Path, field: str, lo: float = 0.0, hi: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < lo or number > hi:
        _fail(path, f"{field} must be between {lo} and {hi}")
    return number


def _actor(value: Any, path: Path, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, f"{field} must be a character id")
    if value != "user" and value not in CHARACTER_ORDER:
        _fail(path, f"{field} names unknown character {value!r}")
    return value


def _source(value: Any, path: Path) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, "belief source is required")
    if value in {"user", "observation"}:
        return value
    if value.startswith("character:"):
        character = value.split(":", 1)[1]
        if character not in CHARACTER_ORDER:
            _fail(path, f"belief source names unknown character {character!r}")
        return value
    _fail(path, "belief source must be user, observation or character:<id>")


def _validate(scenario: dict, path: Path) -> None:
    if not isinstance(scenario, dict):
        _fail(path, "scenario must be an object")

    scenario_id = scenario.get("id")
    if not isinstance(scenario_id, str) or not _ID.match(scenario_id):
        _fail(path, "id must be lowercase letters, digits and dashes")
    if path.stem != scenario_id:
        _fail(path, f"id {scenario_id!r} does not match the file name")
    if not isinstance(scenario.get("title"), str) or not scenario["title"].strip():
        _fail(path, "title is required")
    if "seed" in scenario and (
        isinstance(scenario["seed"], bool) or not isinstance(scenario["seed"], int)
    ):
        _fail(path, "seed must be an integer")
    if "notes" in scenario and not isinstance(scenario["notes"], str):
        _fail(path, "notes must be a string")

    cast = scenario.get("cast")
    if not isinstance(cast, list) or not cast:
        _fail(path, "cast must be a non-empty list")
    if any(not isinstance(character, str) for character in cast):
        _fail(path, "cast must contain character ids")
    if len(set(cast)) != len(cast):
        _fail(path, "cast contains duplicates")
    for character in cast:
        if character not in CHARACTER_ORDER:
            _fail(path, f"cast names unknown character {character!r}")

    absent = scenario.get("absent", [])
    if not isinstance(absent, list) or any(
        not isinstance(character, str) for character in absent
    ):
        _fail(path, "absent must be a list of character ids")
    for character in absent:
        if character not in CHARACTER_ORDER:
            _fail(path, f"absent names unknown character {character!r}")
    overlap = set(cast) & set(absent or [])
    if overlap:
        _fail(path, "a character cannot be both present and absent: " + ", ".join(sorted(overlap)))

    friends = scenario.get("friends", [])
    if not isinstance(friends, list) or any(
        not isinstance(character, str) for character in friends
    ):
        _fail(path, "friends must be a list of character ids")
    for character in friends:
        if character not in CHARACTER_ORDER:
            _fail(path, f"friends names unknown character {character!r}")

    clock = scenario.get("clock", {})
    if not isinstance(clock, dict):
        _fail(path, "clock must be an object")
    now = clock.get("now")
    if not isinstance(now, str):
        _fail(path, "clock.now is required")
    try:
        datetime.fromisoformat(now)
    except ValueError as exc:
        raise ValueError(f"{path.name}: clock.now is not an ISO datetime") from exc
    if clock.get("mode", "mock") not in {"mock", "realtime"}:
        _fail(path, "clock.mode must be mock or realtime")
    if "scale" in clock:
        scale = clock["scale"]
        if isinstance(scale, bool) or not isinstance(scale, (int, float)):
            _fail(path, "clock.scale must be a number")
        if not math.isfinite(float(scale)) or float(scale) <= 0:
            _fail(path, "clock.scale must be greater than zero")

    relationships = scenario.get("relationships", [])
    if not isinstance(relationships, list):
        _fail(path, "relationships must be a list")
    seen_edges: set[tuple[str, str]] = set()
    for edge in relationships:
        if not isinstance(edge, dict):
            _fail(path, "each relationship must be an object")
        a = _actor(edge.get("a"), path, "relationship.a")
        b = _actor(edge.get("b"), path, "relationship.b")
        if a == b:
            _fail(path, "a relationship cannot point at itself")
        if (a, b) in seen_edges:
            _fail(path, f"duplicate relationship {a} -> {b}")
        seen_edges.add((a, b))
        for field in ("trust", "closeness", "tension"):
            if field not in edge:
                _fail(path, f"relationship {a} -> {b} is missing {field}")
            _number(edge[field], path, f"relationship {a}.{b}.{field}")

    beliefs = scenario.get("beliefs", [])
    if not isinstance(beliefs, list):
        _fail(path, "beliefs must be a list")
    seen_beliefs: set[tuple[str, str]] = set()
    for belief in beliefs:
        if not isinstance(belief, dict):
            _fail(path, "each belief must be an object")
        holder = belief.get("holder")
        if holder not in CHARACTER_ORDER:
            _fail(path, f"belief holder names unknown character {holder!r}")
        proposition = belief.get("proposition")
        if not isinstance(proposition, str) or not proposition.strip():
            _fail(path, "belief proposition is required")
        key = belief.get("key") or belief.get("proposition_key")
        if not isinstance(key, str) or not KEY.match(key):
            _fail(path, "belief key must be lowercase letters, digits and dashes")
        if (holder, key) in seen_beliefs:
            _fail(path, f"duplicate belief {holder}/{key}")
        seen_beliefs.add((holder, key))
        _source(belief.get("source"), path)
        _number(belief.get("confidence", 0.8), path, f"belief {holder}/{key}.confidence")
        if belief.get("visibility", "private") not in VISIBILITIES:
            _fail(path, "belief visibility must be private, shared or public")

    outfits = scenario.get("outfits", {})
    if not isinstance(outfits, dict):
        _fail(path, "outfits must be an object keyed by character")
    for character, spec in outfits.items():
        if character not in CHARACTER_ORDER:
            _fail(path, f"outfit names unknown character {character!r}")
        if not isinstance(spec, dict):
            _fail(path, f"outfit {character} must be an object")
        if not isinstance(spec.get("id"), str) or not spec["id"]:
            _fail(path, f"outfit {character} needs an id")
        if not isinstance(spec.get("label"), str) or not spec["label"]:
            _fail(path, f"outfit {character} needs a label")
        if "art" in spec and not isinstance(spec["art"], str):
            _fail(path, f"outfit {character}.art must be a path")
        if "reason" in spec and not isinstance(spec["reason"], str):
            _fail(path, f"outfit {character}.reason must be a string")
        if "source_belief" in spec and (
            not isinstance(spec["source_belief"], str)
            or not KEY.match(spec["source_belief"])
        ):
            _fail(path, f"outfit {character}.source_belief must be a belief key")

    cast_art = scenario.get("cast_art", {})
    if not isinstance(cast_art, dict):
        _fail(path, "cast_art must be an object keyed by character")
    for character, art in cast_art.items():
        if character not in CHARACTER_ORDER:
            _fail(path, f"cast_art names unknown character {character!r}")
        if not isinstance(art, str) or not art:
            _fail(path, f"cast_art.{character} must be a path")

    if "scene_art" in scenario and not isinstance(scenario["scene_art"], str):
        _fail(path, "scene_art must be a path")

    raw_items: list[Any] = []
    if scenario.get("item") is not None:
        raw_items.append(scenario["item"])
    declared_items = scenario.get("items", [])
    if not isinstance(declared_items, list):
        _fail(path, "items must be a list")
    raw_items.extend(declared_items)
    seen_items: set[str] = set()
    for spec in raw_items:
        if not isinstance(spec, dict):
            _fail(path, "each item must be an object")
        item_id = spec.get("id")
        if not isinstance(item_id, str) or not item_id:
            _fail(path, "item id is required")
        if item_id in seen_items:
            _fail(path, f"duplicate item {item_id!r}")
        seen_items.add(item_id)
        if not isinstance(spec.get("label"), str) or not spec["label"]:
            _fail(path, f"item {item_id} needs a label")
        holder = spec.get("holder", "user")
        _actor(holder, path, f"item {item_id}.holder")
        owner = spec.get("owner", holder)
        _actor(owner, path, f"item {item_id}.owner")
        if "status" in spec and not isinstance(spec["status"], str):
            _fail(path, f"item {item_id}.status must be a string")

    opening = scenario.get("opening")
    if opening is not None:
        if not isinstance(opening, dict):
            _fail(path, "opening must be an object")
        if not isinstance(opening.get("line"), str) or not opening["line"].strip():
            _fail(path, "opening.line is required")
        if "title" in opening and not isinstance(opening["title"], str):
            _fail(path, "opening.title must be a string")
        choices = opening.get("choices", [])
        if not isinstance(choices, list) or any(
            not isinstance(choice, str) or not choice.strip() for choice in choices
        ):
            _fail(path, "opening.choices must be a list of strings")

    ending = scenario.get("ending")
    if ending is not None:
        if not isinstance(ending, dict):
            _fail(path, "ending must be an object")
        if not isinstance(ending.get("id"), str) or not ending["id"]:
            _fail(path, "ending.id is required")
        if not isinstance(ending.get("label"), str) or not ending["label"]:
            _fail(path, "ending.label is required")
        if ending.get("tone", "neutral") not in TONES:
            _fail(path, "ending.tone must be good, bad or neutral")
        evidence = ending.get("evidence", [])
        if not isinstance(evidence, list) or any(
            not isinstance(line, str) for line in evidence
        ):
            _fail(path, "ending.evidence must be a list of strings")


def _load_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name}: could not read scenario") from exc
    _validate(data, path)
    return data


def _files() -> list[Path]:
    if not SCENARIO_DIR.is_dir():
        return []
    order = {scenario_id: index for index, scenario_id in enumerate(SCENARIO_ORDER)}
    paths = [path for path in SCENARIO_DIR.glob("*.json") if path.is_file()]
    return sorted(
        paths,
        key=lambda path: (order.get(path.stem, len(order)), path.stem),
    )


def get_scenario(scenario_id: str) -> dict:
    """One validated scenario by id. Unknown or malformed ids raise ValueError."""
    scenario_id = (scenario_id or "").strip()
    if not _ID.match(scenario_id):
        raise ValueError("unknown scenario: " + scenario_id)
    path = SCENARIO_DIR / f"{scenario_id}.json"
    if not path.is_file():
        raise ValueError("unknown scenario: " + scenario_id)
    return _load_file(path)


def list_scenarios() -> list[dict]:
    """Scenario cards for the Worlds rail, in authored order."""
    out: list[dict] = []
    for path in _files():
        scenario = _load_file(path)
        out.append(
            {
                "id": scenario["id"],
                "title": scenario.get("title", scenario["id"]),
                "seed": scenario.get("seed"),
                "ending": scenario.get("ending"),
                "cast": list(scenario.get("cast", [])),
                "notes": scenario.get("notes", ""),
            }
        )
    return out


def load_scenario(service: WorldService, scenario_id: str) -> dict:
    """Reset the world and apply one scenario seed. Returns the full scenario."""
    scenario = get_scenario(scenario_id)
    service.reset()

    clock = scenario.get("clock") or {}
    now = datetime.fromisoformat(clock["now"])
    now_iso = now.isoformat(timespec="seconds")
    mode = clock.get("mode", "mock")
    scale = float(clock.get("scale", 1.0))
    anchor = (
        service._real_now().isoformat(timespec="seconds")
        if mode == "realtime"
        else None
    )
    cast = list(scenario.get("cast") or [])

    with service.store.transaction() as conn:
        service.store.admin.apply_scenario(
            conn,
            scenario,
            now_iso=now_iso,
            mode=mode,
            scale=scale,
            anchor=anchor,
            cast=cast,
        )

    for character, spec in (scenario.get("outfits") or {}).items():
        if spec.get("apply", True) is False:
            continue
        service.set_outfit(
            character,
            spec["id"],
            reason=spec.get("reason", ""),
            source_belief_id=spec.get("source_belief"),
            label=spec.get("label"),
            art=spec.get("art"),
        )

    return scenario


def evaluate_ending(service: WorldService) -> dict:
    """Return the scenario's authored ending card and record it once.

    This is a demo card, not a live predicate engine: the good and bad presets are the
    fork. Idempotence is per scenario run, so a second call returns the same card and
    does not add a second ending event.
    """
    scenario = service.current_scenario()
    card = (scenario or {}).get("ending")
    if not isinstance(card, dict):
        return {"ending": None, "evidence": [], "recorded": False}

    evidence = list(card.get("evidence") or [])
    scenario_id = scenario["id"]
    existing = service.recorded_ending(scenario_id)
    if existing:
        return {
            "ending": card,
            "evidence": evidence,
            "recorded": False,
            "event_id": existing["id"],
        }

    event = service.record_event(
        "director",
        "ending",
        f"Ending: {card.get('label', card.get('id', 'ending'))}.",
        participants=list(scenario.get("cast") or []),
        visibility="public",
        metadata={
            "scenario_id": scenario_id,
            "ending_id": card.get("id"),
            "tone": card.get("tone", "neutral"),
            "evidence": evidence,
        },
    )
    return {
        "ending": card,
        "evidence": evidence,
        "recorded": True,
        "event_id": event["id"],
    }
