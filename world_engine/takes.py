"""The TAKE layer: short, linear recording scripts on top of a scenario.

A take is not a second world engine. Loading one resets the world DB, loads its
scenario, and starts scene 0. The model writes lines; code owns the scene order, the
cues, the fallbacks, the ending and the state. A cue runs after a player turn or a
choice and only ever changes recorded state -- it never invents prose.

The take's progress lives in the generic `meta` table:

    take                 the validated take JSON
    take_id              the active take id
    take_index           the current scene index
    take_scene_start     the last event id when the scene began
    take_scene_changed   "1" once a turn or cue changed something

That keeps a take inside the same reset semantics as a scenario: `reset` removes every
key and the dashboard always reads a coherent world.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config
from .scenarios import evaluate_ending, get_scenario, load_scenario
from .service import CHARACTER_ORDER, VISIBILITIES, WorldService
from switch_world.domain import (
    TAKE_CHANGED_META,
    TAKE_ID_META,
    TAKE_INDEX_META,
    TAKE_META,
    TAKE_START_META,
)

TAKE_DIR = Path(config.CONTENT_ROOT) / "takes"

# Authored order, matching the Worlds rail. w5-good and w5-bad are a fork.
TAKE_ORDER = [
    "w1-gift",
    "w2-two-clocks",
    "w3-quiet-route",
    "w4-three-of-us",
    "w5-good",
    "w5-bad",
    "w6-long-tuesday",
    "w7-last-call",
]

CUE_OPS = (
    "remember_preference",
    "give_item",
    "set_outfit",
    "advance_time",
    "mark_absent",
    "ending",
)

# Events written by the director group turn or by a cue that mean "the player did
# something in this scene". A bare scenario/take load is deliberately not here.
CHANGE_EVENT_KINDS = (
    "dialogue",
    "action",
    "silence",
    "turn_plan",
    "boundary_violation",
    "social_verdict",
    "item_given",
    "outfit_change",
    "relationship_update",
    "take_cue",
    "ending",
    "beat",
    "branch",
)

_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_KEY = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TONES = ("good", "bad", "neutral")


class TakeError(ValueError):
    """A take request that cannot be honoured (unknown id, last scene, ...)."""


class TakeNotChanged(TakeError):
    """The scene-change invariant refused to advance because nothing happened."""


# ---- validation -----------------------------------------------------------


def _fail(message: str) -> None:
    raise ValueError(message)


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")
    return value.strip()


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID.match(value):
        _fail(f"{field} must be lowercase letters, digits and dashes")
    return value


def _actor(value: Any, field: str) -> str:
    if not isinstance(value, str) or value not in CHARACTER_ORDER:
        _fail(f"{field} names unknown character {value!r}")
    return value


def _art_path(art: str) -> Path:
    if not art.startswith("/static/"):
        _fail("art must live under /static/")
    return Path(config.WEB_DIR) / art[len("/static/"):]


def _art_exists(art: str) -> bool:
    try:
        return _art_path(art).is_file()
    except ValueError:
        return False


def _lines(value: Any, field: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        _fail(f"{field} must be a non-empty list of strings")
    out: list[str] = []
    for line in value:
        if not isinstance(line, str) or not line.strip():
            _fail(f"{field} must contain non-empty strings")
        out.append(line.strip())
    return out


def _validate_trigger(cue: dict, field: str) -> None:
    if "match" in cue:
        if not isinstance(cue["match"], str) or not cue["match"]:
            _fail(f"{field}.match must be a non-empty regex")
        try:
            re.compile(cue["match"])
        except re.error as exc:
            raise ValueError(f"{field}.match is not a valid regex: {exc}") from exc
    if "choice" in cue:
        choice = cue["choice"]
        if isinstance(choice, bool) or not isinstance(choice, int) or choice < 1:
            _fail(f"{field}.choice must be a positive integer (1-based)")


def _validate_cue(
    cue: Any,
    field: str,
    cast: list[str],
    declared_outfits: dict,
) -> None:
    if not isinstance(cue, dict):
        _fail(f"{field} must be an object")
    op = cue.get("op")
    if op not in CUE_OPS:
        _fail(f"{field}.op must be one of {', '.join(CUE_OPS)}")
    _validate_trigger(cue, field)

    if op == "remember_preference":
        key = cue.get("key")
        if not isinstance(key, str) or not _KEY.match(key):
            _fail(f"{field}.key must be lowercase letters, digits and dashes")
        _string(cue.get("proposition"), f"{field}.proposition")
        if "holder" in cue:
            _actor(cue["holder"], f"{field}.holder")
        confidence = cue.get("confidence", 0.9)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            _fail(f"{field}.confidence must be a number")
        if not 0.0 <= float(confidence) <= 1.0:
            _fail(f"{field}.confidence must be between 0 and 1")
        if cue.get("visibility", "private") not in VISIBILITIES:
            _fail(f"{field}.visibility must be private, shared or public")
    elif op == "give_item":
        _string(cue.get("item"), f"{field}.item")
        if "to" in cue:
            to = cue["to"]
            if to != "user":
                _actor(to, f"{field}.to")
        if "label" in cue:
            _string(cue["label"], f"{field}.label")
    elif op == "set_outfit":
        character = _actor(cue.get("character"), f"{field}.character")
        outfit = _string(cue.get("outfit"), f"{field}.outfit")
        declared = declared_outfits.get(character)
        if not isinstance(declared, dict) or declared.get("id") != outfit:
            _fail(
                f"{field}.outfit {outfit!r} is not declared for {character!r} "
                "in the scenario"
            )
        if "source_belief" in cue:
            belief = cue["source_belief"]
            if not isinstance(belief, str) or not _KEY.match(belief):
                _fail(f"{field}.source_belief must be a belief key")
        if "reason" in cue:
            _string(cue["reason"], f"{field}.reason")
    elif op == "advance_time":
        minutes = cue.get("minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            _fail(f"{field}.minutes must be an integer")
    elif op == "mark_absent":
        _actor(cue.get("character"), f"{field}.character")
        if cue.get("character") not in cast:
            _fail(f"{field}.character must be in the scene cast")
        if "reason" in cue:
            _string(cue["reason"], f"{field}.reason")
    elif op == "ending":
        if "id" in cue:
            _id(cue["id"], f"{field}.id")
        if "label" in cue:
            _string(cue["label"], f"{field}.label")
        if "tone" in cue and cue["tone"] not in TONES:
            _fail(f"{field}.tone must be good, bad or neutral")


def validate_take(take: Any, path: Path) -> None:
    """Validate one take object against the real scenario and asset tree."""
    if not isinstance(take, dict):
        _fail("take must be an object")

    take_id = take.get("id")
    if not isinstance(take_id, str) or not _ID.match(take_id):
        _fail("id must be lowercase letters, digits and dashes")
    if path.stem != take_id:
        _fail(f"id {take_id!r} does not match the file name")
    _string(take.get("title"), "title")

    scenario_id = take.get("scenario")
    _id(scenario_id, "scenario")
    try:
        scenario = get_scenario(scenario_id)
    except ValueError as exc:
        _fail(f"scenario {scenario_id!r} could not be loaded: {exc}")
        return

    scenario_cast = list(scenario.get("cast") or [])
    declared_outfits = scenario.get("outfits") or {}
    warm = take.get("warm", [])
    if not isinstance(warm, list):
        _fail("warm must be a list of character ids")
    for character in warm:
        _actor(character, "warm")
        if character not in scenario_cast:
            _fail(f"warm names {character!r}, which is not in the scenario cast")

    ending = take.get("ending")
    scenario_ending = scenario.get("ending")
    if ending is not None:
        if not isinstance(ending, str) or not _ID.match(ending):
            _fail("ending must be null or a lowercase ending id")
        if not isinstance(scenario_ending, dict):
            _fail(f"scenario {scenario_id} declares no ending to reference")
        if ending != scenario_ending.get("id"):
            _fail(
                f"ending {ending!r} does not match the scenario ending "
                f"{scenario_ending.get('id')!r}"
            )

    scenes = take.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        _fail("scenes must be a non-empty list")

    seen_ids: set[str] = set()
    for index, scene in enumerate(scenes):
        field = f"scenes[{index}]"
        if not isinstance(scene, dict):
            _fail(f"{field} must be an object")
        scene_id = _id(scene.get("id"), f"{field}.id")
        if scene_id in seen_ids:
            _fail(f"duplicate scene id {scene_id!r}")
        seen_ids.add(scene_id)
        _string(scene.get("title"), f"{field}.title")
        _string(scene.get("place"), f"{field}.place")

        cast = scene.get("cast")
        if not isinstance(cast, list) or not cast:
            _fail(f"{field}.cast must be a non-empty list")
        for character in cast:
            _actor(character, f"{field}.cast")
            if character not in scenario_cast:
                _fail(
                    f"{field}.cast names {character!r}, which is not in the "
                    f"scenario cast"
                )
        if len(set(cast)) != len(cast):
            _fail(f"{field}.cast contains duplicates")

        art = _string(scene.get("art"), f"{field}.art")
        if not _art_exists(art):
            _fail(f"{field}.art does not exist: {art}")

        _lines(scene.get("opening"), f"{field}.opening")
        _lines(scene.get("choices"), f"{field}.choices")

        cues = scene.get("cues", [])
        if not isinstance(cues, list):
            _fail(f"{field}.cues must be a list")
        for cue_index, cue in enumerate(cues):
            _validate_cue(
                cue,
                f"{field}.cues[{cue_index}]",
                cast,
                declared_outfits,
            )

        fallback = scene.get("fallback_lines", {})
        if not isinstance(fallback, dict):
            _fail(f"{field}.fallback_lines must be an object keyed by character")
        for character, line in fallback.items():
            _actor(character, f"{field}.fallback_lines key")
            if character not in cast:
                _fail(f"{field}.fallback_lines key {character!r} is not in the cast")
            _string(line, f"{field}.fallback_lines.{character}")

        must_change = scene.get("must_change", False)
        if not isinstance(must_change, bool):
            _fail(f"{field}.must_change must be a boolean")

        next_id = scene.get("next")
        if index == len(scenes) - 1:
            if next_id is not None:
                _fail(f"{field}.next must be null on the last scene")
        else:
            expected = scenes[index + 1]
            expected_id = expected.get("id") if isinstance(expected, dict) else None
            if next_id != expected_id:
                _fail(
                    f"{field}.next must point at the next scene "
                    f"{expected_id!r}"
                )


def _load_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name}: could not read take") from exc
    try:
        validate_take(data, path)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc
    return data


def _files(takes_dir: Path | None = None) -> list[Path]:
    folder = Path(takes_dir or TAKE_DIR)
    if not folder.is_dir():
        return []
    order = {take_id: index for index, take_id in enumerate(TAKE_ORDER)}
    paths = [path for path in folder.glob("*.json") if path.is_file()]
    return sorted(paths, key=lambda path: (order.get(path.stem, len(order)), path.stem))


def get_take(take_id: str) -> dict:
    """One validated take by id. Unknown or unsafe ids raise ValueError."""
    take_id = (take_id or "").strip()
    if not _ID.match(take_id):
        raise ValueError("unknown take: " + take_id)
    path = TAKE_DIR / f"{take_id}.json"
    if not path.is_file():
        raise ValueError("unknown take: " + take_id)
    return _load_file(path)


def _summary(take: dict) -> dict:
    return {
        "id": take["id"],
        "title": take.get("title", take["id"]),
        "scenario": take["scenario"],
        "scene_count": len(take.get("scenes") or []),
        "ending": take.get("ending"),
    }


def list_takes() -> list[dict]:
    """Take cards for the shelf, in authored order."""
    return [_summary(_load_file(path)) for path in _files()]


def validate_takes(takes_dir: Path | None = None) -> list[str]:
    """Return one human-readable error per invalid take; empty means valid."""
    folder = Path(takes_dir or TAKE_DIR)
    if not folder.is_dir():
        return [f"{folder}: takes directory is missing"]
    paths = _files(folder)
    if not paths:
        return [f"{folder}: no takes found"]
    errors: list[str] = []
    for path in paths:
        try:
            _load_file(path)
        except ValueError as exc:
            errors.append(f"{path}: {exc}")
    return errors


# ---- stored take state ----------------------------------------------------


def _parse_current(
    raw: str | None, index_raw: str | None
) -> tuple[dict | None, int | None]:
    if not raw:
        return None, None
    try:
        take = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise TakeError("the stored take is not valid JSON") from exc
    if not isinstance(take, dict) or not take.get("scenes"):
        raise TakeError("the stored take has no scenes")
    try:
        index = int(index_raw) if index_raw is not None else 0
    except (TypeError, ValueError) as exc:
        raise TakeError("the stored scene index is not a number") from exc
    index = max(0, min(index, len(take["scenes"]) - 1))
    return take, index


def _current(service: WorldService) -> tuple[dict | None, int | None]:
    meta = service.store.reader.get_metas((TAKE_META, TAKE_INDEX_META))
    return _parse_current(meta[TAKE_META], meta[TAKE_INDEX_META])


def scene_view(scene: dict, index: int) -> dict:
    """The small scene card the Story HUD and the state endpoint read."""
    opening = scene.get("opening")
    if isinstance(opening, str):
        opening = [opening]
    return {
        "id": scene["id"],
        "title": scene.get("title", scene["id"]),
        "place": scene.get("place", ""),
        "opening": list(opening or []),
        "choices": list(scene.get("choices") or []),
        "index": index,
        "cast": list(scene.get("cast") or []),
        "art": scene.get("art"),
        "next": scene.get("next"),
        "must_change": bool(scene.get("must_change", False)),
    }


def _take_snapshot(take: dict | None, index: int | None) -> dict:
    if take is None or index is None:
        return {"take": None, "scene": None, "take_index": None}
    return {
        "take": _summary(take),
        "scene": scene_view(take["scenes"][index], index),
        "take_index": index,
    }


def take_snapshot(service: WorldService) -> dict:
    """What `/api/state` adds: the take summary, the scene card and the index."""
    take, index = _current(service)
    return _take_snapshot(take, index)


def take_snapshot_from_snapshot(snapshot: dict) -> dict:
    """The same projection, built from a store snapshot (no second connection)."""
    take, index = _parse_current(
        snapshot.get("take_meta"), snapshot.get("take_index_meta")
    )
    return _take_snapshot(take, index)


def _state_with_take(service: WorldService) -> dict:
    snapshot = service.store.reader.snapshot()
    state = service.state_from_snapshot(snapshot)
    state.update(take_snapshot_from_snapshot(snapshot))
    return state


def _begin_scene(service: WorldService, event_id: int | None) -> None:
    """Mark the post-event boundary for the must-change invariant."""
    with service.store.transaction() as conn:
        service.store.writer.set_meta(
            TAKE_START_META, str(event_id or 0), conn=conn
        )
        service.store.writer.set_meta(TAKE_CHANGED_META, "0", conn=conn)


def scene_changed(service: WorldService) -> bool:
    """True once a player turn or a cue landed after the scene began."""
    with service.store.transaction() as conn:
        meta = service.store.reader.get_metas(
            (TAKE_CHANGED_META, TAKE_START_META), conn=conn
        )
        if meta[TAKE_CHANGED_META] == "1":
            return True
        start_raw = meta[TAKE_START_META] or "0"
        try:
            start = int(start_raw)
        except (TypeError, ValueError):
            start = 0
        return service.store.reader.has_change_event_after(
            start, CHANGE_EVENT_KINDS, conn=conn
        )


def _sync_presence(service: WorldService, take: dict, scene: dict) -> None:
    """Frame the scene: only its cast is present; everyone else is out of scene."""
    try:
        scenario = get_scenario(take["scenario"])
    except ValueError:
        scenario = {}
    cast = set(scene.get("cast") or [])
    for character in scenario.get("cast") or []:
        if character in cast:
            service.mark_present(character)
        else:
            service.mark_absent(character, reason=f"not in scene {scene['id']}")


# ---- cues -----------------------------------------------------------------


def _cue_matches(
    cue: dict, user_line: str, choice: int | None, phase: str = "turn"
) -> bool:
    if phase == "enter":
        return True
    if cue.get("on") == "scene_enter":
        return False
    if "choice" in cue:
        if choice is not None and int(cue["choice"]) == int(choice):
            return True
        if "match" not in cue:
            return False
    if "match" in cue:
        return bool(re.search(cue["match"], user_line or "", re.I))
    return True


def _apply_remember(service: WorldService, scene: dict, cue: dict) -> dict:
    holder = cue.get("holder") or (scene.get("cast") or [None])[0]
    if not holder:
        raise TakeError("remember_preference has no holder and the scene has no cast")
    key = cue["key"]
    # Deterministic across repeated turns: one active fact per (holder, key).
    known = {row["holder"] for row in service.who_knows(key).get("holders", [])}
    if holder in known:
        return {"op": "remember_preference", "holder": holder, "key": key, "skipped": True}
    belief = service.remember(
        holder,
        cue["proposition"],
        source="user",
        confidence=float(cue.get("confidence", 0.9)),
        visibility=cue.get("visibility", "private"),
        proposition_key=key,
    )
    return {
        "op": "remember_preference",
        "holder": holder,
        "key": key,
        "belief_id": belief.get("id"),
        "skipped": False,
    }


def _apply_item(service: WorldService, scene: dict, cue: dict) -> dict:
    to = cue.get("to") or (scene.get("cast") or ["user"])[0]
    label = cue.get("label")
    item = service.give_item(cue["item"], to, label=label)
    return {
        "op": "give_item",
        "item": item["id"],
        "to": item["holder"],
        "label": item["label"],
    }


def _apply_outfit(service: WorldService, cue: dict) -> dict:
    outfit = service.set_outfit(
        cue["character"],
        cue["outfit"],
        reason=cue.get("reason", ""),
        source_belief_id=cue.get("source_belief"),
    )
    return {
        "op": "set_outfit",
        "character": outfit["character"],
        "outfit": outfit["outfit_id"],
        "source_belief_key": outfit.get("source_belief_key"),
    }


def _apply_ending(service: WorldService, take: dict, scene: dict, cue: dict) -> dict:
    scenario = service.current_scenario() or {}
    card = scenario.get("ending")
    wanted = cue.get("id") or take.get("ending")
    if isinstance(card, dict) and (not wanted or wanted == card.get("id")):
        result = evaluate_ending(service)
        return {
            "op": "ending",
            "id": (result.get("ending") or {}).get("id"),
            "recorded": result.get("recorded", False),
        }
    if not wanted:
        raise TakeError("ending cue has no id and the scenario declares no ending")
    label = cue.get("label") or wanted
    tone = cue.get("tone", "neutral")
    event = service.record_event(
        "director",
        "ending",
        f"Ending: {label}.",
        participants=list(scene.get("cast") or []),
        visibility="public",
        metadata={
            "take_id": take.get("id"),
            "scenario_id": (scenario or {}).get("id"),
            "ending_id": wanted,
            "tone": tone,
        },
    )
    return {"op": "ending", "id": wanted, "event_id": event["id"], "recorded": True}


def _apply_cue(service: WorldService, take: dict, scene: dict, cue: dict) -> dict:
    op = cue["op"]
    if op == "remember_preference":
        return _apply_remember(service, scene, cue)
    if op == "give_item":
        return _apply_item(service, scene, cue)
    if op == "set_outfit":
        return _apply_outfit(service, cue)
    if op == "advance_time":
        clock = service.advance_time("director", int(cue["minutes"]))
        return {"op": "advance_time", "minutes": int(cue["minutes"]), "now": clock["now"]}
    if op == "mark_absent":
        result = service.mark_absent(cue["character"], reason=cue.get("reason", ""))
        return {"op": "mark_absent", "character": result["character"], "reason": result["reason"]}
    if op == "ending":
        return _apply_ending(service, take, scene, cue)
    raise TakeError("unknown cue op: " + str(op))


def apply_cues(
    service: WorldService,
    take: dict | None = None,
    index: int | None = None,
    user_line: str = "",
    choice: int | None = None,
    phase: str = "turn",
) -> dict:
    """Run the current scene's matching cues after a player turn or choice.

    Matching cues change recorded state, then one `take_cue` event is recorded per
    applied cue. No cue writes prose. Returns the applied list so the director can
    show a compact cue trail if it wants one.
    """
    if take is None or index is None:
        take, index = _current(service)
        if take is None or index is None:
            raise TakeError("no take is loaded")
    scene = take["scenes"][index]
    applied: list[dict] = []
    cues = scene.get("enter_cues") if phase == "enter" else scene.get("cues")
    for cue in cues or []:
        if not _cue_matches(cue, user_line, choice, phase):
            continue
        try:
            result = _apply_cue(service, take, scene, cue)
        except ValueError as exc:
            raise TakeError(f"cue {cue['op']} failed: {exc}") from exc
        applied.append(result)
        service.record_event(
            "director",
            "take_cue",
            f"Cue: {cue['op']}" + (f" {cue.get('key')}" if cue.get("key") else ""),
            participants=list(scene.get("cast") or []),
            visibility="public",
            metadata={
                "take_id": take.get("id"),
                "scene_id": scene.get("id"),
                "op": cue["op"],
                "result": result,
            },
        )

    if applied:
        with service.store.transaction() as conn:
            service.store.writer.set_meta(TAKE_CHANGED_META, "1", conn=conn)
    return {"scene_id": scene.get("id"), "applied": applied, "changed": bool(applied)}


# ---- load / advance -------------------------------------------------------


def load_take(service: WorldService, take_id: str) -> dict:
    """Reset the world, load the take's scenario, and start scene 0."""
    take = get_take(take_id)
    load_scenario(service, take["scenario"])

    if not take.get("scenes"):
        raise TakeError("the take has no scenes")
    scene = take["scenes"][0]

    with service.store.transaction() as conn:
        service.store.writer.set_meta(
            TAKE_META, json.dumps(take, ensure_ascii=False), conn=conn
        )
        service.store.writer.set_meta(TAKE_ID_META, take["id"], conn=conn)
        service.store.writer.set_meta(TAKE_INDEX_META, "0", conn=conn)

    _sync_presence(service, take, scene)
    event = service.record_event(
        "director",
        "take_load",
        f"Take: {take.get('title', take['id'])}.",
        participants=list(scene.get("cast") or []),
        visibility="public",
        metadata={
            "take_id": take["id"],
            "scenario_id": take["scenario"],
            "scene_id": scene["id"],
            "index": 0,
            "warm": list(take.get("warm") or []),
        },
    )
    _begin_scene(service, event.get("id"))

    return {
        "take": _summary(take),
        "scene": scene_view(scene, 0),
        "index": 0,
        "state": _state_with_take(service),
    }


def current_take(service: WorldService) -> dict:
    """The active take card, or null fields when no take is loaded."""
    take, index = _current(service)
    if take is None or index is None:
        return {"take": None, "scene": None, "index": None, "state": _state_with_take(service)}
    return {
        "take": _summary(take),
        "scene": scene_view(take["scenes"][index], index),
        "index": index,
        "state": _state_with_take(service),
    }


def next_scene(service: WorldService, force: bool = False) -> dict:
    """Advance one scene, enforcing the must-change invariant."""
    take, index = _current(service)
    if take is None or index is None:
        raise TakeError("no take is loaded")
    scene = take["scenes"][index]
    next_id = scene.get("next")
    if not next_id:
        raise TakeError("this is the last scene")

    if scene.get("must_change", False) and not force and not scene_changed(service):
        raise TakeNotChanged(
            "nothing has changed in this scene yet; make a turn or a choice, "
            "or pass force=true"
        )

    scene_ids = [item.get("id") for item in take["scenes"]]
    try:
        next_index = scene_ids.index(next_id)
    except ValueError as exc:
        raise TakeError(f"unknown next scene {next_id!r}") from exc
    next_scene_data = take["scenes"][next_index]

    _sync_presence(service, take, next_scene_data)
    event = service.record_event(
        "director",
        "take_scene",
        f"Scene: {next_scene_data.get('title', next_scene_data['id'])}.",
        participants=list(next_scene_data.get("cast") or []),
        visibility="public",
        metadata={
            "take_id": take["id"],
            "scene_id": next_scene_data["id"],
            "index": next_index,
            "forced": bool(force),
        },
    )
    with service.store.transaction() as conn:
        service.store.writer.set_meta(
            TAKE_INDEX_META, str(next_index), conn=conn
        )
    _begin_scene(service, event.get("id"))
    if next_scene_data.get("enter_cues"):
        apply_cues(
            service, take, next_index, user_line="", choice=None, phase="enter"
        )

    return {
        "take": _summary(take),
        "scene": scene_view(next_scene_data, next_index),
        "index": next_index,
        "state": _state_with_take(service),
        "changed": True,
    }
