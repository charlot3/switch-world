"""Injected reply strategies for the one beat pipeline.

A strategy is only the half of a beat that actually differs between transports:
the prompt text and the way a reply travels back.  The pipeline in
:mod:`switch_world.application.beats` owns the scene lifecycle, the ledger
checks and the writes.

* :class:`LocalBeatStrategy` uses the authored canon dialogue (no model, no room).
* :class:`BifrostBeatStrategy` calls a :class:`ModelClient` (Bifrost/OpenCode).
* :class:`CloudBeatStrategy` calls the same :class:`ModelClient` surface for the
  guest deployment; it never needs ``wait_for`` because there is no room.
* :class:`SwitchBeatStrategy` delivers prompts through a
  :class:`CharacterTransport` (the live Switch room).

The café prompts are copied verbatim from the four historical runners; the
authored beat JSON and every prompt string stay unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from switch_world.application.canon import brief
from switch_world.domain.agents import parse_agent_reply
from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.model import Message, ModelClient, ModelFormat
from switch_world.domain.ports.transport import CharacterTransport, Prompt

from .beats import (
    BeatContext,
    BeatReply,
    BeatTurn,
    SceneEvent,
    new_turn_id,
    prompts_for,
)

# ---------------------------------------------------------------------------
# Prompts copied from the runners (do not reword: they are authored content)
# ---------------------------------------------------------------------------

BIFROST_ALICE_PROMPT = (
    "It is 18:30 at the café. Emily is across the table and notices you are "
    "distracted. She asks directly: \"Is something wrong?\" A friend of yours — "
    "the person who has been coming around lately — told you in a private DM "
    "that they are leaving the city at the end of the month. They have not told "
    "the others. You decide whether to tell Emily. You already know the secret; "
    "set memory to null — do not record a new belief. If your view of Emily "
    "changed, include relationship deltas. Do not call them \"the user\" in the "
    "room. Reply with dialogue only, 1-3 sentences, no stage directions."
)

BIFROST_EMILY_PROMPT = (
    "Alice says: \"{alice}\" — how do you respond? If you learned the "
    "secret, include a memory with source \"character:alice\", confidence "
    "0.7-0.9, visibility \"shared\" and proposition_key "
    "\"user-leaving-city\". If she only dodged and you merely suspect, record a "
    "suspicion with proposition_key \"alice-holding-back\", source "
    "\"observation\", confidence 0.3-0.5 and visibility \"private\". If your view "
    "of Alice or the friend changed, include relationship deltas. Reply with "
    "dialogue only, 1-3 sentences, no stage directions."
)

SWITCH_ALICE_PROMPT = (
    "{canon}\n\n"
    "It is 18:30 at the café. Emily is here, and she notices you're distracted. She asks "
    "you directly: \"Is something wrong?\" A friend of yours — the person who has been "
    "coming around lately — told you in a private DM that they are leaving the city at the "
    "end of the month; they haven't told the others. You decide whether to tell Emily. If "
    "you tell her, say it in this room, then call world__remember with source user and "
    "proposition_key {key} so the record stays honest. If you keep it, say so honestly. "
    "Keep it to a few sentences, and do not call them 'the user' in the room."
)

SWITCH_EMILY_PROMPT = (
    "{canon}\n\n"
    'Alice says: "{alice}" — how do you respond? If you learned something from her, call '
    "world__remember with source character:alice, a confidence below 1.0 and "
    "proposition_key {key}. If she only dodged, you may remember a suspicion instead, but "
    "do not record it as the secret itself. If your view of Alice or the user changed, call "
    "world__update_relationship with a short reason. Keep it to a few sentences."
)

LOCAL_ALICE_DEFLECT = "I've had a long week. Tell me something good."
LOCAL_EMILY_DEFLECT = "You're deflecting. What aren't you telling me?"
LOCAL_ALICE_DISCLOSE = (
    "I shouldn't be telling you this, but our friend — the one who's been coming "
    "around — is leaving the city at the end of the month. They haven't told the "
    "others yet."
)
LOCAL_EMILY_DISCLOSE = (
    "They told you before they told me? I don't know whether to be flattered or "
    "worried."
)


def _alice_shares(store: Any) -> bool:
    rel = store.relationship("alice", "emily")
    return rel["trust"] >= 0.7 and rel["tension"] <= 0.35


def _lines_for(beat: Mapping[str, Any], branch_id: str | None) -> list[dict]:
    if beat.get("local_by_branch"):
        return beat["local_by_branch"].get(branch_id or "non-disclosure", [])
    return beat.get("local", [])


class LocalBeatStrategy:
    """The deterministic authored runner: no model and no room."""

    name = "local"

    def opening(self, context: BeatContext) -> SceneEvent | None:
        if context.spec.owns_branch:
            return SceneEvent(
                "scene_start",
                "Café, 18:30. Alice and Emily are at a table.",
                ("alice", "emily"),
            )
        return None

    def turn(self, index: int, context: BeatContext) -> BeatTurn | None:
        if context.spec.owns_branch:
            return self._cafe_turn(index, context)
        lines = _lines_for(context.beat, context.branch_id)
        if index >= len(lines):
            return None
        line = lines[index]
        return BeatTurn(
            character=str(line["speaker"]),
            authored=str(line["text"]),
        )

    def _cafe_turn(self, index: int, context: BeatContext) -> BeatTurn | None:
        spec = context.spec
        share = (
            _alice_shares(context.store)
            if spec.force_share is None
            else bool(spec.force_share)
        )
        if index == 0:
            return BeatTurn(
                character="alice",
                authored=LOCAL_ALICE_DISCLOSE if share else LOCAL_ALICE_DEFLECT,
            )
        if index == 1:
            if not share:
                return BeatTurn(
                    character="emily",
                    authored=LOCAL_EMILY_DEFLECT,
                    followups=(
                        SceneEvent(
                            "non_disclosure",
                            "Alice chose not to tell Emily. Emily noticed the deflection.",
                            ("alice", "emily"),
                        ),
                    ),
                )
            already = any(
                h["holder"] == "emily"
                for h in context.store.who_knows(spec.key)["holders"]
            )
            writes: tuple = ()
            followups: tuple[SceneEvent, ...] = ()
            if not already:
                from switch_world.domain.agents import MemoryWrite, RelationshipWrite

                writes = (
                    MemoryWrite(
                        proposition=(
                            "The user is leaving the city at the end of the month."
                        ),
                        source="character:alice",
                        confidence=0.8,
                        visibility="shared",
                        proposition_key=spec.key,
                    ),
                    RelationshipWrite(
                        other="alice",
                        trust_delta=-0.10,
                        closeness_delta=0.02,
                        tension_delta=0.05,
                        reason="heard the news second-hand",
                    ),
                    RelationshipWrite(
                        other="user",
                        trust_delta=-0.05,
                        closeness_delta=-0.02,
                        tension_delta=0.02,
                        reason="told Alice before me",
                    ),
                )
                followups = (
                    SceneEvent(
                        "disclosure",
                        "Alice told Emily: the user is leaving the city.",
                        ("alice", "emily"),
                    ),
                )
            return BeatTurn(
                character="emily",
                authored=LOCAL_EMILY_DISCLOSE,
                writes=writes,
                followups=followups,
            )
        return None

    def reply(self, turn: BeatTurn, context: BeatContext) -> BeatReply:
        return BeatReply(text=turn.authored or "")

    def branch_event(self, context: BeatContext) -> SceneEvent | None:
        return None

    def branch_participants(self, context: BeatContext) -> Sequence[str] | None:
        return None

    def closing(self, context: BeatContext) -> SceneEvent | None:
        if context.spec.owns_branch:
            return SceneEvent(
                "scene_end", "The café scene ends.", ("alice", "emily")
            )
        return None

    def canon_warning_after_beat(self, context: BeatContext) -> bool:
        return True

    def card_after_beat(self, context: BeatContext) -> bool:
        # The historical local runner rendered the card inside run_cafe, before
        # the beat event was recorded.
        return not context.spec.owns_branch


class _ModelBeatStrategy:
    """Shared prompt/transport half for the two model-backed editions."""

    name = "model"

    def __init__(
        self,
        model: ModelClient,
        *,
        timeout: float = 90.0,
        prompts=None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        # The legacy runners expose ``prompts_for`` as a module attribute and
        # tests patch it; resolving the callable here keeps that working.
        self._prompts = prompts or prompts_for

    # ---- lifecycle --------------------------------------------------------
    def opening(self, context: BeatContext) -> SceneEvent | None:
        if context.spec.owns_branch:
            return SceneEvent(
                "scene_start",
                self._cafe_opening(context),
                ("alice", "emily"),
            )
        return SceneEvent(
            "beat_start",
            f"Beat: {context.beat['id']} — {context.beat['title']}",
            tuple(context.beat.get("characters", ())),
        )

    def _cafe_opening(self, context: BeatContext) -> str:
        return "Café, 18:30. Alice and Emily are at a table."

    # ---- turns ------------------------------------------------------------
    def turn(self, index: int, context: BeatContext) -> BeatTurn | None:
        if context.spec.owns_branch:
            return self._cafe_turn(index, context)
        prompts = self._prompts(context.beat, context.branch_id)
        characters = [
            character
            for character in context.beat.get("characters", [])
            if character not in {"user", "director"} and prompts.get(character)
        ]
        if index >= len(characters):
            return None
        character = characters[index]
        return BeatTurn(
            character=character,
            prompt=prompts[character],
            sanitise=True,
            no_reply=f"{character.title()} did not answer.",
        )

    def _cafe_turn(self, index: int, context: BeatContext) -> BeatTurn | None:
        if index == 0:
            return BeatTurn(
                character="alice",
                prompt=BIFROST_ALICE_PROMPT,
                sanitise=True,
                abort_on_empty=True,
                no_reply="Alice did not answer in the room.",
            )
        if index == 1:
            prompt = BIFROST_EMILY_PROMPT.format(
                alice=context.prior.get("alice", "")
            )
            return BeatTurn(
                character="emily",
                prompt=prompt,
                sanitise=True,
                no_reply="Emily did not answer in the room.",
            )
        return None

    # ---- replies ----------------------------------------------------------
    def reply(self, turn: BeatTurn, context: BeatContext) -> BeatReply | None:
        messages = [
            Message(
                "system",
                self._system_prompt(turn.character, context),
            ),
            Message("user", turn.prompt),
        ]
        response = self.model.generate(
            CharacterId(turn.character), messages, format=ModelFormat.JSON
        )
        parsed = parse_agent_reply(turn.character, response, envelope=True)
        return BeatReply(text=parsed.text, writes=parsed.writes)

    def _system_prompt(self, character: str, context: BeatContext) -> str:
        from switch_world.application.prompts import _system

        return _system(
            character,
            context.canon,
            context.world_context,
            clock=context.clock_now,
        )

    # ---- lifecycle tail ---------------------------------------------------
    def branch_event(self, context: BeatContext) -> SceneEvent | None:
        return None

    def branch_participants(self, context: BeatContext) -> Sequence[str] | None:
        return None

    def closing(self, context: BeatContext) -> SceneEvent | None:
        if context.spec.owns_branch:
            return SceneEvent(
                "scene_end", self._cafe_closing(context), ("alice", "emily")
            )
        return None

    def _cafe_closing(self, context: BeatContext) -> str:
        return "The café scene ends."

    def canon_warning_after_beat(self, context: BeatContext) -> bool:
        return False

    def card_after_beat(self, context: BeatContext) -> bool:
        return True


class BifrostBeatStrategy(_ModelBeatStrategy):
    """Model replies through the local Bifrost/OpenCode gateway."""

    name = "bifrost"

    def _cafe_opening(self, context: BeatContext) -> str:
        return (
            "Café, 18:30. Alice and Emily are at a table. "
            "The dialogue is generated through Bifrost."
        )

    def _cafe_closing(self, context: BeatContext) -> str:
        return "The Bifrost café scene ends."


class CloudBeatStrategy(_ModelBeatStrategy):
    """Model replies through the injected cloud :class:`ModelClient`.

    There is no room and no ``wait_for``: the scripted/cloud model answers each
    prompt directly, so a beat completes in seconds with a test double.
    """

    name = "cloud"

    def _cafe_opening(self, context: BeatContext) -> str:
        return (
            "Café, 18:30. Alice and Emily are at a table. "
            "The dialogue is generated by the cloud model."
        )

    def _cafe_closing(self, context: BeatContext) -> str:
        return "The cloud café scene ends."


class SwitchBeatStrategy:
    """The live Switch room: prompts carry the canon brief and an @mention."""

    name = "switch"

    def __init__(
        self,
        transport: CharacterTransport,
        *,
        timeout: float = 90.0,
        prompts=None,
    ) -> None:
        self.transport = transport
        self.timeout = timeout
        self._prompts = prompts or prompts_for

    # ---- lifecycle --------------------------------------------------------
    def opening(self, context: BeatContext) -> SceneEvent | None:
        if context.spec.owns_branch:
            return SceneEvent(
                "scene_start",
                "Café, 18:30. Alice and Emily are at a table.",
                ("alice", "emily"),
            )
        return SceneEvent(
            "beat_start",
            f"Beat: {context.beat['id']} — {context.beat['title']}",
            tuple(context.beat.get("characters", ())),
        )

    def turn(self, index: int, context: BeatContext) -> BeatTurn | None:
        if context.spec.owns_branch:
            return self._cafe_turn(index, context)
        prompts = self._prompts(context.beat, context.branch_id)
        characters = [
            character
            for character in context.beat.get("characters", [])
            if character not in {"user", "director"} and prompts.get(character)
        ]
        if index >= len(characters):
            return None
        character = characters[index]
        return BeatTurn(
            character=character,
            prompt=prompts[character],
            sanitise=True,
            no_reply=f"{character.title()} did not answer.",
        )

    def _cafe_turn(self, index: int, context: BeatContext) -> BeatTurn | None:
        if index == 0:
            return BeatTurn(
                character="alice",
                prompt=SWITCH_ALICE_PROMPT.format(
                    canon=brief("alice", context.canon), key=context.spec.key
                ),
                sanitise=True,
                abort_on_empty=True,
                no_reply="Alice did not answer in the room.",
            )
        if index == 1:
            prompt = SWITCH_EMILY_PROMPT.format(
                canon=brief("emily", context.canon),
                alice=context.prior.get("alice", "").replace('"', "'"),
                key=context.spec.key,
            )
            return BeatTurn(
                character="emily",
                prompt=prompt,
                sanitise=True,
                no_reply="Emily did not answer in the room.",
            )
        return None

    # ---- replies ----------------------------------------------------------
    def reply(self, turn: BeatTurn, context: BeatContext) -> BeatReply | None:
        room = self._room(context)
        text = self._post_text(turn, context)
        deadline = context.clock.monotonic() + self.timeout
        delivery = self.transport.deliver_many(
            room,
            [Prompt(CharacterId(turn.character), text)],
            turn_id=new_turn_id(),
            deadline=deadline,
        )
        inbound = self.transport.collect(
            delivery,
            speakers=[CharacterId(turn.character)],
            deadline=deadline,
        )
        if not inbound:
            return None
        return BeatReply(text=inbound[0].text)

    def _room(self, context: BeatContext) -> Any:
        if context.room is None:
            context.room = self.transport.open_room(name=context.spec.room_name)
        return context.room

    def _post_text(self, turn: BeatTurn, context: BeatContext) -> str:
        if context.spec.owns_branch:
            return f"@{turn.character} {turn.prompt}"
        return (
            f"@{turn.character} {brief(turn.character, context.canon)}"
            f"\n\n{turn.prompt}"
        )

    # ---- lifecycle tail ---------------------------------------------------
    def branch_event(self, context: BeatContext) -> SceneEvent | None:
        if not context.spec.owns_branch:
            return None
        shared = context.branch_id == "disclosure"
        return SceneEvent(
            "disclosure" if shared else "scene_turn",
            (
                "Alice and Emily met at the café; the world state records what "
                "Emily learned."
                if shared
                else "Alice and Emily met at the café; Alice kept the secret."
            ),
            ("alice", "emily"),
        )

    def branch_participants(self, context: BeatContext) -> Sequence[str] | None:
        if not context.spec.owns_branch:
            return None
        holders = context.store.who_knows(context.spec.key)["holders"]
        return ["alice", "emily"] + [
            holder["holder"]
            for holder in holders
            if holder["holder"] in {"sophia", "mia"}
        ]

    def closing(self, context: BeatContext) -> SceneEvent | None:
        if context.spec.owns_branch:
            return SceneEvent(
                "scene_end", "The café scene ends.", ("alice", "emily")
            )
        return None

    def canon_warning_after_beat(self, context: BeatContext) -> bool:
        return False

    def card_after_beat(self, context: BeatContext) -> bool:
        return True


__all__ = [
    "BifrostBeatStrategy",
    "CloudBeatStrategy",
    "LocalBeatStrategy",
    "SwitchBeatStrategy",
]
