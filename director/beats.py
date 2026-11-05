"""Authored beat runner: several small demos instead of one café scene.

Every beat in `world/canon.json` is runnable on its own:

- `local` — deterministic authored dialogue, no model, works in both editions;
- `bifrost` — the same beat generated through Bifrost/OpenCode (Geek Room);
- `switch` — the same beat posted to the live Switch room (Flip).

The café remains the required beat and owns the branch. The others are optional scenes
that let the project be demonstrated in parts without changing the canon.
"""
from __future__ import annotations

from datetime import datetime

from world_engine.service import WorldService

from . import DEMO_KEY
from .canon import branch_for, load as load_canon, record_branch, validate
from .simulate import run_cafe, user_tells_alice

BEAT_ORDER = ("morning-shop", "truck-lunch", "cafe", "aftermath", "roundup")


def get_beat(beat_id: str, canon: dict | None = None) -> dict:
    canon = canon or load_canon()
    for beat in canon["beats"]:
        if beat["id"] == beat_id:
            return beat
    raise ValueError(f"unknown beat: {beat_id}")


def advance_to(service: WorldService, time_text: str) -> None:
    """Move the world clock to a beat's HH:MM on the same day, never backwards."""
    now = datetime.fromisoformat(service.clock()["now"])
    hour, minute = (int(part) for part in time_text.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = max(0, int((target - now).total_seconds() // 60))
    if delta:
        service.advance_time("director", delta)


def _ensure_secret(service: WorldService) -> None:
    holders = service.who_knows(DEMO_KEY)["holders"]
    if not any(h["holder"] == "alice" and h["source"] == "user" for h in holders):
        user_tells_alice(service, key=DEMO_KEY)


def _record_beat(service: WorldService, beat: dict) -> dict:
    return service.record_event(
        "director",
        "beat",
        f"Beat: {beat['id']} — {beat['title']} (done).",
        participants=beat.get("characters", []),
        visibility="public",
    )


def _record_lines(service: WorldService, lines: list[dict]) -> list[dict]:
    recorded = []
    for line in lines:
        speaker = line["speaker"]
        label = "You" if speaker == "user" else speaker.title()
        recorded.append(
            service.record_event(
                speaker,
                "dialogue",
                f"{label}: {line['text']}",
                participants=[speaker],
                visibility="public",
            )
        )
    return recorded


def _canon_warning(service: WorldService, canon: dict) -> list[str]:
    issues = validate(service, canon)
    if issues:
        service.record_event(
            "director",
            "canon_warning",
            "Worldline check: " + "; ".join(issues),
            participants=[],
            visibility="public",
        )
    return issues


def _apply_effects(service: WorldService, beat_id: str, branch_id: str | None = None) -> None:
    if beat_id == "morning-shop":
        service.update_relationship(
            "alice", "user",
            closeness_delta=0.03,
            tension_delta=0.02,
            reason="the morning visit; holding the secret for them",
        )
    elif beat_id == "truck-lunch":
        service.update_relationship(
            "mia", "sophia",
            closeness_delta=0.03,
            tension_delta=-0.02,
            reason="Sophia listened without making Mia say it",
        )
        service.update_relationship(
            "sophia", "mia",
            closeness_delta=0.02,
            reason="Mia let the money worry show for a second",
        )
        if not any(h["holder"] == "sophia" for h in service.who_knows("truck-debt")["holders"]):
            service.remember(
                "sophia",
                proposition="Mia is more worried about money than she admits.",
                source="character:mia",
                confidence=0.45,
                visibility="private",
                proposition_key="truck-debt",
            )
    elif beat_id == "aftermath":
        if branch_id == "disclosure":
            service.update_relationship(
                "emily", "alice",
                trust_delta=0.03, closeness_delta=0.02, tension_delta=-0.03,
                reason="Alice chose to tell her, even if late",
            )
            service.update_relationship(
                "emily", "user",
                trust_delta=-0.02, tension_delta=0.02,
                reason="told Alice before her",
            )
            service.update_relationship(
                "alice", "emily",
                closeness_delta=0.02,
                reason="Emily did not make her regret telling",
            )
        elif branch_id == "partial-leak":
            service.update_relationship(
                "emily", "alice",
                trust_delta=-0.05, tension_delta=0.06,
                reason="the secret reached her sideways",
            )
            service.update_relationship(
                "emily", "user",
                trust_delta=-0.04, tension_delta=0.04,
                reason="the version she heard was not theirs to give",
            )
            service.update_relationship(
                "sophia", "emily",
                closeness_delta=0.02,
                reason="corrected the distorted version",
            )
        else:
            service.update_relationship(
                "emily", "alice",
                trust_delta=-0.02, tension_delta=0.05,
                reason="Alice kept the secret and deflected",
            )
            service.update_relationship(
                "emily", "user",
                trust_delta=-0.03, tension_delta=0.03,
                reason="left out again",
            )
            service.update_relationship(
                "alice", "user",
                tension_delta=0.02,
                reason="the weight of the withheld thing",
            )
    elif beat_id == "roundup":
        service.update_relationship(
            "mia", "user",
            closeness_delta=0.01,
            reason="brought fries to the group chat",
        )


def prompts_for(beat: dict, branch_id: str | None = None) -> dict[str, str]:
    if branch_id and beat.get("prompts_by_branch"):
        return beat["prompts_by_branch"].get(branch_id, {})
    return beat.get("prompts", {})


def _lines_for(beat: dict, branch_id: str | None = None) -> list[dict]:
    if beat.get("local_by_branch"):
        return beat["local_by_branch"].get(branch_id or "non-disclosure", [])
    return beat.get("local", [])


def run_local_beat(
    service: WorldService,
    beat_id: str,
    force_share: bool | None = None,
) -> dict:
    canon = load_canon()
    beat = get_beat(beat_id, canon)

    if beat_id == "cafe":
        _ensure_secret(service)
        advance_to(service, beat["time"])
        result = run_cafe(service, force_share=force_share)
        _record_beat(service, beat)
        _canon_warning(service, canon)
        return {
            "beat": beat,
            "transport": "local",
            "branch": result["branch"],
            "canon_issues": result["canon_issues"],
            "transcript": result["transcript"],
            "card": result["card"],
            "matrix": service.matrix(),
            "clock": service.clock(),
        }

    if beat_id == "aftermath":
        branch_events = [e for e in service.state()["events"] if e["kind"] == "branch"]
        if not branch_events:
            raise ValueError("run the café beat first; aftermath needs a branch")
        branch = branch_for(service, DEMO_KEY)
        branch_id = branch["id"]
    else:
        branch = None
        branch_id = None

    if beat_id in {"morning-shop", "roundup"}:
        _ensure_secret(service)
    advance_to(service, beat["time"])
    lines = _lines_for(beat, branch_id)
    _record_lines(service, lines)
    _apply_effects(service, beat_id, branch_id)
    _record_beat(service, beat)
    issues = _canon_warning(service, canon)
    card = service.scene_card(f"{beat['title']} — {beat_id}")
    return {
        "beat": beat,
        "transport": "local",
        "branch": branch,
        "canon_issues": issues,
        "transcript": [f"{'You' if line['speaker'] == 'user' else line['speaker'].title()}: {line['text']}" for line in lines],
        "card": card,
        "matrix": service.matrix(),
        "clock": service.clock(),
    }


def run_arc(service: WorldService, force_share: bool | None = None) -> dict:
    results = []
    for beat_id in BEAT_ORDER:
        results.append(run_local_beat(service, beat_id, force_share=force_share))
    last = results[-1]
    cafe = next(item for item in results if item["beat"]["id"] == "cafe")
    return {
        "beats": results,
        "branch": cafe["branch"],
        "card": last["card"],
        "matrix": service.matrix(),
        "clock": service.clock(),
    }


def run_beat(
    service: WorldService,
    beat_id: str,
    transport: str = "local",
    force_share: bool | None = None,
    client=None,
    switch=None,
    room_name: str = "world",
    timeout: float = 90.0,
) -> dict:
    if transport == "local":
        return run_local_beat(service, beat_id, force_share=force_share)
    if transport == "bifrost":
        from .bifrost_scene import run_beat_bifrost

        return run_beat_bifrost(service, beat_id, client=client)
    if transport == "switch":
        from .run_switch import run_beat_switch

        return run_beat_switch(
            service,
            beat_id,
            switch=switch,
            room_name=room_name,
            timeout=timeout,
        )
    raise ValueError("transport must be local, bifrost or switch")
