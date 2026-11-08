"""The one authored-beat pipeline.

Every transport runs the same ordered scene:

    scene_start -> per-turn prompt -> reply -> branch_for -> validate ->
    record_branch -> advance_time -> scene_end -> get_beat -> scene card

The pipeline owns the lifecycle, the ledger checks and the writes.  A
:class:`BeatAgent` supplies only what actually differs between the four
runners: the prompts and the transport that carries them.  Nothing here
constructs a Switch client, a Bifrost client or a model; those are injected by
the caller.

The four historical runners (``director/beats.py``, ``director/bifrost_scene.py``,
``director/run_switch.py`` and ``director/simulate.py``) are thin wrappers over
this module: they resolve a :class:`BeatSpec`, pick a strategy from
:mod:`switch_world.application.beat_strategies`, and adapt the result back to
their historical return shape.  ``tests/integration/test_beats_parity.py``
still proves the shapes and effects.
"""
from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from switch_world.application.canon import (
    branch_for,
    load as load_canon,
    record_branch,
    validate,
)
from switch_world.application.facade import WorldService
from switch_world.application.simulate import user_tells_alice
from switch_world.application.social import appraise, clean_scene_line

from switch_world.domain.agents import MemoryWrite, RelationshipWrite, WorldWrite
from switch_world.domain.ids import TurnId
from switch_world.domain.ports.clock import Clock

from .group_planning import _sanitise_reply

DEMO_KEY = "user-leaving-city"

# Beats that require Alice to have been told the secret before they run.
SECRET_BEATS = frozenset({"cafe", "morning-shop", "roundup"})


# ---------------------------------------------------------------------------
# Values exchanged between the pipeline and an injected strategy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneEvent:
    """A director event the strategy wants recorded at a lifecycle point."""

    kind: str
    summary: str
    participants: tuple[str, ...] = ()
    visibility: str = "public"


@dataclass(frozen=True)
class BeatTurn:
    """One prompt the pipeline is about to deliver.

    ``authored`` is set for the local runner: its dialogue comes from the
    canon, not from a model or a room, so the pipeline records it verbatim.
    """

    character: str
    prompt: str = ""
    authored: str | None = None
    writes: tuple[WorldWrite, ...] = ()
    followups: tuple[SceneEvent, ...] = ()
    sanitise: bool = False
    abort_on_empty: bool = False
    no_reply: str | None = None
    participants: tuple[str, ...] | None = None
    visibility: str = "public"


@dataclass(frozen=True)
class BeatReply:
    """A strategy's answer for one turn, before the pipeline records it."""

    text: str
    writes: tuple[WorldWrite, ...] = ()
    followups: tuple[SceneEvent, ...] = ()


@dataclass
class BeatContext:
    """Everything a strategy may read while a beat is running."""

    spec: BeatSpec
    canon: Mapping[str, Any]
    beat: Mapping[str, Any]
    store: WorldService
    clock: Clock
    world_context: str
    clock_now: str
    branch: dict[str, Any] | None = None
    branch_id: str | None = None
    prior: dict[str, str] = field(default_factory=dict)
    room: Any | None = None


class BeatAgent(Protocol):
    """The injected half of a beat: prompts and transport only."""

    name: str

    def opening(self, context: BeatContext) -> SceneEvent | None: ...

    def turn(self, index: int, context: BeatContext) -> BeatTurn | None: ...

    def reply(self, turn: BeatTurn, context: BeatContext) -> BeatReply | None: ...

    def branch_event(self, context: BeatContext) -> SceneEvent | None: ...

    def branch_participants(self, context: BeatContext) -> Sequence[str] | None: ...

    def closing(self, context: BeatContext) -> SceneEvent | None: ...

    def canon_warning_after_beat(self, context: BeatContext) -> bool: ...

    def card_after_beat(self, context: BeatContext) -> bool: ...


# ---------------------------------------------------------------------------
# Beat description
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BeatSpec:
    """One authored beat plus the run options the caller owns."""

    beat: Mapping[str, Any]
    canon: Mapping[str, Any]
    transport: str = "local"
    key: str = DEMO_KEY
    force_share: bool | None = None
    seed: bool = True
    advance: bool = True
    room_name: str = "world"
    timeout: float = 90.0
    record_beat: bool = True
    canon_warning: bool = True

    @property
    def id(self) -> str:
        return str(self.beat["id"])

    @property
    def title(self) -> str:
        return str(self.beat.get("title") or self.id)

    @property
    def owns_branch(self) -> bool:
        """The café owns the authored branch; the other beats read it."""
        return self.id == "cafe"

    @property
    def apply_effects(self) -> bool:
        return not self.owns_branch

    @property
    def advance_minutes(self) -> int:
        return 30 if self.owns_branch else 0


def get_beat(beat_id: str, canon: Mapping[str, Any] | None = None) -> dict:
    canon = canon or load_canon()
    for beat in canon["beats"]:
        if beat["id"] == beat_id:
            return beat
    raise ValueError(f"unknown beat: {beat_id}")


def prompts_for(beat: Mapping[str, Any], branch_id: str | None = None) -> dict[str, str]:
    if branch_id and beat.get("prompts_by_branch"):
        return beat["prompts_by_branch"].get(branch_id, {})
    return beat.get("prompts", {})


def load_spec(
    beat_id: str,
    *,
    canon: Mapping[str, Any] | None = None,
    transport: str = "local",
    key: str = DEMO_KEY,
    force_share: bool | None = None,
    seed: bool = True,
    advance: bool = True,
    room_name: str = "world",
    timeout: float = 90.0,
    record_beat: bool = True,
    canon_warning: bool = True,
) -> BeatSpec:
    """Resolve an authored beat id into a :class:`BeatSpec`."""
    canon = canon or load_canon()
    return BeatSpec(
        beat=get_beat(beat_id, canon),
        canon=canon,
        transport=transport,
        key=key,
        force_share=force_share,
        seed=seed,
        advance=advance,
        room_name=room_name,
        timeout=timeout,
        record_beat=record_beat,
        canon_warning=canon_warning,
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_beat(
    spec: BeatSpec,
    agent: BeatAgent,
    store: WorldService,
    clock: Clock,
) -> dict:
    """Run one authored beat through the shared lifecycle.

    The store is the compatibility facade (``WorldService``) while the store
    port is being narrowed; the clock is the injected monotonic/wall source a
    transport uses for its deadline.
    """
    beat = spec.beat
    beat_id = spec.id
    canon = spec.canon

    if spec.seed and beat_id in SECRET_BEATS:
        _ensure_secret(store, spec.key)

    # The aftermath reads the branch the café already wrote.
    branch: dict[str, Any] | None = None
    branch_id: str | None = None
    if beat_id == "aftermath":
        if store.latest_event("branch") is None:
            raise ValueError("run the café beat first; aftermath needs a branch")
        branch = branch_for(store, spec.key)
        branch_id = branch["id"]

    if spec.advance:
        _advance_to_beat(store, canon, beat_id)

    context = BeatContext(
        spec=spec,
        canon=canon,
        beat=beat,
        store=store,
        clock=clock,
        world_context=_world_context(store),
        clock_now=store.clock()["now"],
        branch=branch,
        branch_id=branch_id,
    )

    opening = agent.opening(context)
    if opening is not None:
        _record_scene_event(store, opening)

    transcript: list[str] = []
    turns: list[dict[str, Any]] = []
    aborted = False
    index = 0
    while True:
        turn = agent.turn(index, context)
        if turn is None:
            break
        reply = (
            BeatReply(text=turn.authored or "")
            if turn.authored is not None
            else agent.reply(turn, context)
        )
        text = "" if reply is None else (reply.text or "")
        text = clean_scene_line(text)
        if not text:
            summary = turn.no_reply or f"{turn.character.title()} did not answer."
            _record_scene_event(
                store,
                SceneEvent("no_reply", summary, (turn.character,)),
            )
            if turn.abort_on_empty:
                aborted = True
                break
            index += 1
            continue

        if turn.sanitise:
            verdict = appraise(store, turn.character, turn.prompt, public=False)
            text = _sanitise_reply(turn.character, text, verdict, turn.prompt)

        label = "You" if turn.character == "user" else turn.character.title()
        participants = (
            list(turn.participants)
            if turn.participants is not None
            else [turn.character]
        )
        store.record_event(
            turn.character,
            "dialogue",
            f"{label}: {text}",
            participants=participants,
            visibility=turn.visibility,
        )
        context.prior[turn.character] = text
        transcript.append(f"{label}: {text}")

        writes = _apply_writes(store, turn.character, turn.writes)
        if reply is not None:
            writes.extend(_apply_writes(store, turn.character, reply.writes))
        for event in (*turn.followups, *(reply.followups if reply else ())):
            _record_scene_event(store, event)
        turns.append(
            {
                "character": turn.character,
                "reply": text,
                "writes": writes,
            }
        )
        index += 1

    issues: list[str] = []
    if spec.owns_branch and not aborted:
        branch = branch_for(store, spec.key)
        context.branch = branch
        context.branch_id = branch["id"]
        issues = validate(store, canon)

        event = agent.branch_event(context)
        if event is not None:
            _record_scene_event(store, event)

        participants = agent.branch_participants(context)
        if participants is None:
            record_branch(store, branch, issues)
        else:
            record_branch(store, branch, issues, participants=list(participants))

        if spec.advance_minutes:
            store.advance_time("director", spec.advance_minutes)
        closing = agent.closing(context)
        if closing is not None:
            _record_scene_event(store, closing)

    if spec.apply_effects and not aborted:
        _apply_effects(store, beat_id, branch_id)

    title = _card_title(spec, branch, aborted)
    card_first = spec.owns_branch and not aborted and not agent.card_after_beat(context)
    card: dict[str, Any] | None = None
    if card_first:
        card = store.scene_card(title)

    if not aborted:
        if spec.record_beat:
            _record_beat(store, beat)
        if spec.canon_warning and (
            not spec.owns_branch or agent.canon_warning_after_beat(context)
        ):
            issues = _canon_warning(store, canon)

    if card is None:
        card = store.scene_card(title)

    return {
        "beat": get_beat(beat_id, canon),
        "transport": getattr(agent, "name", spec.transport),
        "branch": branch,
        "canon_issues": issues,
        "transcript": transcript,
        "turns": turns,
        "card": card,
        "matrix": store.matrix(),
        "clock": store.clock(),
    }


# ---------------------------------------------------------------------------
# Lifecycle helpers (copied from the four runners so the old public functions
# stay untouched during the parity proof)
# ---------------------------------------------------------------------------


def _record_scene_event(store: WorldService, event: SceneEvent) -> dict:
    return store.record_event(
        "director",
        event.kind,
        event.summary,
        participants=list(event.participants),
        visibility=event.visibility,
    )


def _ensure_secret(store: WorldService, key: str) -> None:
    holders = store.who_knows(key)["holders"]
    if not any(h["holder"] == "alice" and h["source"] == "user" for h in holders):
        user_tells_alice(store, key=key)


def _advance_to_beat(store: WorldService, canon: Mapping[str, Any], beat_id: str) -> dict:
    now = datetime.fromisoformat(store.clock()["now"])
    for beat in sorted(canon.get("beats", []), key=lambda item: item.get("order", 0)):
        if beat["id"] != beat_id:
            continue
        hour, minute = (int(part) for part in beat["time"].split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        minutes = max(0, math.ceil((target - now).total_seconds() / 60))
        clock = store.advance_time("director", minutes)
        return {
            "beat": beat,
            "clock": clock,
            "target": target.isoformat(timespec="seconds"),
        }
    raise ValueError("unknown beat: " + beat_id)


def _apply_effects(
    store: WorldService, beat_id: str, branch_id: str | None = None
) -> None:
    if beat_id == "morning-shop":
        store.update_relationship(
            "alice",
            "user",
            closeness_delta=0.03,
            tension_delta=0.02,
            reason="the morning visit; holding the secret for them",
        )
    elif beat_id == "truck-lunch":
        store.update_relationship(
            "mia",
            "sophia",
            closeness_delta=0.03,
            tension_delta=-0.02,
            reason="Sophia listened without making Mia say it",
        )
        store.update_relationship(
            "sophia",
            "mia",
            closeness_delta=0.02,
            reason="Mia let the money worry show for a second",
        )
        if not any(
            h["holder"] == "sophia"
            for h in store.who_knows("truck-debt")["holders"]
        ):
            store.remember(
                "sophia",
                proposition="Mia is more worried about money than she admits.",
                source="character:mia",
                confidence=0.45,
                visibility="private",
                proposition_key="truck-debt",
            )
    elif beat_id == "aftermath":
        if branch_id == "disclosure":
            store.update_relationship(
                "emily",
                "alice",
                trust_delta=0.03,
                closeness_delta=0.02,
                tension_delta=-0.03,
                reason="Alice chose to tell her, even if late",
            )
            store.update_relationship(
                "emily",
                "user",
                trust_delta=-0.02,
                tension_delta=0.02,
                reason="told Alice before her",
            )
            store.update_relationship(
                "alice",
                "emily",
                closeness_delta=0.02,
                reason="Emily did not make her regret telling",
            )
        elif branch_id == "partial-leak":
            store.update_relationship(
                "emily",
                "alice",
                trust_delta=-0.05,
                tension_delta=0.06,
                reason="the secret reached her sideways",
            )
            store.update_relationship(
                "emily",
                "user",
                trust_delta=-0.04,
                tension_delta=0.04,
                reason="the version she heard was not theirs to give",
            )
            store.update_relationship(
                "sophia",
                "emily",
                closeness_delta=0.02,
                reason="corrected the distorted version",
            )
        else:
            store.update_relationship(
                "emily",
                "alice",
                trust_delta=-0.02,
                tension_delta=0.05,
                reason="Alice kept the secret and deflected",
            )
            store.update_relationship(
                "emily",
                "user",
                trust_delta=-0.03,
                tension_delta=0.03,
                reason="left out again",
            )
            store.update_relationship(
                "alice",
                "user",
                tension_delta=0.02,
                reason="the weight of the withheld thing",
            )
    elif beat_id == "roundup":
        store.update_relationship(
            "mia",
            "user",
            closeness_delta=0.01,
            reason="brought fries to the group chat",
        )


def _apply_writes(
    store: WorldService, character: str, writes: Sequence[WorldWrite]
) -> list[dict]:
    applied: list[dict] = []
    for write in writes:
        if isinstance(write, MemoryWrite):
            try:
                belief = store.remember(
                    character,
                    proposition=write.proposition,
                    source=write.source,
                    confidence=write.confidence,
                    visibility=write.visibility,
                    proposition_key=write.proposition_key,
                )
            except (KeyError, TypeError, ValueError):
                belief = None
            applied.append({"memory": belief})
        elif isinstance(write, RelationshipWrite):
            try:
                applied.append(
                    store.update_relationship(
                        character,
                        other=write.other,
                        trust_delta=write.trust_delta,
                        closeness_delta=write.closeness_delta,
                        tension_delta=write.tension_delta,
                        reason=write.reason,
                    )
                )
            except (TypeError, ValueError):
                continue
    return applied


def _record_beat(store: WorldService, beat: Mapping[str, Any]) -> dict:
    return store.record_event(
        "director",
        "beat",
        f"Beat: {beat['id']} — {beat['title']} (done).",
        participants=beat.get("characters", []),
        visibility="public",
    )


def _canon_warning(store: WorldService, canon: Mapping[str, Any]) -> list[str]:
    issues = validate(store, canon)
    if issues:
        store.record_event(
            "director",
            "canon_warning",
            "Worldline check: " + "; ".join(issues),
            participants=[],
            visibility="public",
        )
    return issues


def _world_context(store: WorldService, max_chars: int = 700) -> str:
    event = store.latest_event("world_event")
    if not event:
        return ""
    return event.get("summary", "")[:max_chars]


def _card_title(
    spec: BeatSpec, branch: Mapping[str, Any] | None, aborted: bool
) -> str:
    if spec.owns_branch:
        if aborted:
            return "Café, 18:30 — no reply"
        return f"Café, 18:30 — {(branch or {}).get('id', 'no reply')}"
    return f"{spec.title} — {spec.id}"


def new_turn_id() -> TurnId:
    """A unique turn id for a transport delivery."""
    return TurnId("t-" + uuid.uuid4().hex[:12])


__all__ = [
    "BeatAgent",
    "BeatContext",
    "BeatReply",
    "BeatSpec",
    "BeatTurn",
    "SceneEvent",
    "get_beat",
    "load_spec",
    "prompts_for",
    "run_beat",
]
