"""The application turn pipeline.

One user line becomes one recorded turn in a fixed order:

1. the user's line is recorded first, so a slow or dead room cannot erase it;
2. the deterministic turn plan is recorded;
3. planned speakers are selected;
4. prompts are delivered through an injected :class:`CharacterTransport`;
5. each reply is sanitised exactly once by the policy;
6. an in-band :class:`AgentReply`'s writes are applied with the character as
   the actor (the same authority a character has through MCP);
7. dialogue, action and silence beats are recorded;
8. at most one one-hop agent-to-agent relay is delivered and recorded.

No transport or model is constructed here. The recorder only uses the port it
was given.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from switch_world.application import arbiter as social_arbiter
from switch_world.application import social
from switch_world.application.facade import WorldService
from switch_world.application.social import clean_scene_line

from switch_world.domain.agents import MemoryWrite, RelationshipWrite, WorldWrite
from switch_world.domain.ids import CharacterId, TurnId
from switch_world.domain.ports.transport import (
    CharacterTransport,
    Prompt,
    RoomHandle,
    TransportError,
)

from .group_planning import (
    BOUNDARY_CONFIDENCE,
    BOUNDARY_KEY,
    BOUNDARY_REACTIONS,
    TURN_CAP_SECONDS,
    _agent_mentions,
    _beat_mode,
    _expression,
    _metadata,
    _plan_summary,
    _prompt_for,
    _relay_prompt,
    _role_for,
    _sanitise_reply,
    _speakers,
)

SILENCE_SUMMARY = "{name} stays silent."


class TurnRecorder:
    """Record one group turn through a transport."""

    def __init__(
        self,
        service: WorldService,
        transport: CharacterTransport,
        *,
        room_name: str = "world",
        time_source: Any | None = None,
    ) -> None:
        self.service = service
        self.transport = transport
        self.room_name = room_name
        self._time = time_source or time
        self._envelope = self._wants_envelope()

    def _wants_envelope(self) -> bool:
        """True when the transport's model path is asked to answer in JSON.

        The group prompt carries the envelope contract only for a JSON model
        transport (cloud/Bifrost). A Switch or local room speaks plain text, so
        asking it for JSON would put the envelope in the transcript instead of
        the character's line.
        """
        capabilities = getattr(self.transport, "capabilities", None)
        if not callable(capabilities):
            return False
        return getattr(capabilities(), "response_format", "text") == "json"

    # ---- entry points -----------------------------------------------------
    def record_turn(
        self,
        message: str,
        present: list[str],
        verdicts: dict[str, dict],
        plan: dict,
        turn_id: str,
        *,
        timeout: float = TURN_CAP_SECONDS,
        arbiter_client: Any | None = None,
    ) -> dict:
        if not present:
            # An empty room still keeps the user's line; nobody is planned for.
            self.service.record_event(
                "user",
                "dialogue",
                "You: " + message,
                participants=["user"],
                visibility="public",
                metadata=_metadata(
                    turn_id, "speech", "primary", "neutral", None, False
                ),
            )
            turn = {"id": turn_id, "plan": plan, "lines": [], "missing": []}
            return self._result(
                room=None,
                present=[],
                verdicts={},
                replies=[],
                missing=[],
                silent=[],
                timed_out=False,
                turn=turn,
            )

        # ---- 3. room + user line first, then the plan ---------------------
        room = self.transport.open_room(name=self.room_name)
        self._record_user(message, present, room, turn_id)
        self._record_plan(plan, turn_id, room)
        arbiter_note = self._arbitrate(
            message, present, verdicts, plan, turn_id, room, arbiter_client
        )
        self._record_planned_silence(plan, turn_id, room)

        # ---- 4. deliver to the planned speakers only ----------------------
        speakers = _speakers(plan)
        prompts = [
            Prompt(
                speaker=CharacterId(character),
                text=_prompt_for(
                    self.service,
                    character,
                    message,
                    verdicts[character],
                    _role_for(plan, character),
                    arbiter_note=(
                        arbiter_note if character == plan.get("primary") else None
                    ),
                    present=present,
                    envelope=self._envelope,
                ),
            )
            for character in speakers
        ]
        inbound = self._deliver(room, speakers, prompts, turn_id, timeout)

        # One usable inbound per speaker; the transport may return several
        # events. HEAD kept polling past a placeholder, meta or empty body, so
        # pick the first event that survives cleaning rather than the first.
        by_sender: dict[str, Any] = {}
        for item in inbound:
            sender = str(item.sender)
            if sender in by_sender or not clean_scene_line(item.text):
                continue
            by_sender[sender] = item

        # ---- 5-7. sanitise, apply writes, record beats --------------------
        lines: list[dict] = []
        replies: list[dict] = []
        seen: set[str] = set()
        for character in speakers:
            role = _role_for(plan, character)
            verdict = verdicts[character]
            item = by_sender.get(character)
            body = clean_scene_line(item.text) if item is not None else ""
            if item is None or not body:
                lines.append(
                    self._record_silence(character, role, turn_id, plan, room)
                )
                continue

            # The collection saw a real line: this speaker is not "missing",
            # even if the line turns out to be a duplicate event below.
            seen.add(character)
            body = _sanitise_reply(character, body, verdict, message)
            message_id = "" if item.synthetic else str(item.event_id)
            if message_id and self.service.event_by_message_id(message_id):
                # A repeated event id is a recorded silence beat, not a dropped
                # line: the turn keeps its shape and the UI keeps a row.
                lines.append(
                    self._record_silence(character, role, turn_id, plan, room)
                )
                continue

            # Apply the envelope's writes with the character as the actor.
            self._apply_writes(character, item.writes)
            social.record_verdict(self.service, character, verdict)
            social.apply_deltas(self.service, character, verdict)
            mode, text = _beat_mode(body, role)
            expression = _expression(verdict, role, mode)
            kind = "action" if mode == "action" else "dialogue"
            summary = (
                f"{character.title()}: {text}"
                if kind == "dialogue"
                else f"{character.title()} {text}"
            )
            recorded = self.service.record_event(
                character,
                kind,
                summary,
                participants=[character],
                visibility="public",
                room_id=room.room_id,
                message_id=message_id,
                metadata=_metadata(
                    turn_id, mode, role, expression, plan.get("primary"), plan["chorus"]
                ),
            )
            lines.append(
                {
                    "character": character,
                    "mode": mode,
                    "role": role,
                    "text": text,
                    "expression": expression,
                    "event_id": recorded["id"],
                }
            )
            replies.append(
                {
                    "character": character,
                    "text": text,
                    "event_id": recorded["id"],
                    "message_id": message_id or None,
                }
            )

        # Only planned speakers can be missing; the rest were deliberately silent.
        turn_missing = [character for character in speakers if character not in seen]
        turn = {"id": turn_id, "plan": plan, "lines": lines, "missing": turn_missing}

        # ---- 8. at most one one-hop relay ---------------------------------
        self._relay(
            message, present, verdicts, plan, turn_id, room, turn, replies, timeout
        )

        return self._result(
            room={"room_id": room.room_id, "name": room.name},
            present=present,
            verdicts=verdicts,
            replies=replies,
            missing=turn_missing,
            silent=list(plan.get("silent") or []),
            timed_out=bool(turn_missing),
            turn=turn,
        )

    def record_boundary(
        self,
        message: str,
        present: list[str],
        verdicts: dict,
        target: str,
        turn_id: str,
    ) -> dict:
        """Cut the act and show only the consequence.

        The user's line is deliberately not written: the public feed gets one
        detail-free boundary event, the target refuses and leaves, and every
        other present character privately records that the user crossed a line.
        """
        classified = social.classify(message)
        witnesses = [c for c in present if c != target]
        plan = {
            "primary": target,
            "reactors": witnesses,
            "silent": [],
            "chorus": False,
            "topic": classified["topic"],
            "action_mode": classified["action_mode"],
            "response": "refuse",
            "responses": {
                c: (verdicts.get(c) or {}).get("response") for c in present
            },
            "boundary": "violation",
        }
        self.service.record_event(
            "director",
            "turn_plan",
            _plan_summary(plan) + " The act is cut; only the consequence is shown.",
            participants=[],
            visibility="public",
            metadata={
                "turn_id": turn_id,
                "plan": plan,
                "topic": classified["topic"],
            },
        )
        boundary = self.service.record_event(
            "director",
            "boundary_violation",
            f"The user crossed a physical boundary with {target.title()}.",
            participants=[target],
            visibility="public",
            metadata=_metadata(
                turn_id, "reaction", "primary", "alarmed", target, False
            ),
        )

        target_verdict = {
            **verdicts[target],
            "stance": "hard_refuse",
            "boundary": "violation",
        }
        verdicts[target] = target_verdict
        social.record_verdict(self.service, target, target_verdict)
        social.apply_deltas(self.service, target, target_verdict)

        refusal = social.deflection(target, target_verdict, message)
        refusal_event = self.service.record_event(
            target,
            "dialogue",
            f"{target.title()}: {refusal}",
            participants=[target],
            visibility="public",
            metadata=_metadata(
                turn_id, "speech", "primary", "hurt", target, False
            ),
        )
        lines = [
            {
                "character": target,
                "mode": "speech",
                "role": "primary",
                "text": refusal,
                "expression": "hurt",
                "event_id": refusal_event["id"],
            }
        ]
        replies = [
            {
                "character": target,
                "text": refusal,
                "event_id": refusal_event["id"],
                "message_id": None,
            }
        ]

        # The target leaves the scene. Later group sends filter absent characters.
        self.service.mark_absent(target, reason="crossed a physical boundary")

        proposition = f"The user crossed a physical boundary with {target.title()}."
        for witness in witnesses:
            confidence = BOUNDARY_CONFIDENCE.get(witness, 0.8)
            self.service.remember(
                witness,
                proposition=proposition,
                source="observation",
                confidence=confidence,
                visibility="private",
                proposition_key=BOUNDARY_KEY,
            )
            reaction = BOUNDARY_REACTIONS.get(witness, "goes still.")
            reaction_event = self.service.record_event(
                witness,
                "dialogue",
                f"{witness.title()}: {reaction}",
                participants=[witness],
                visibility="public",
                metadata=_metadata(
                    turn_id, "reaction", "reactor", "alarmed", target, False
                ),
            )
            lines.append(
                {
                    "character": witness,
                    "mode": "reaction",
                    "role": "reactor",
                    "text": reaction,
                    "expression": "alarmed",
                    "event_id": reaction_event["id"],
                }
            )

        turn = {"id": turn_id, "plan": plan, "lines": lines, "missing": []}
        result = self._result(
            room=None,
            present=present,
            verdicts=verdicts,
            replies=replies,
            missing=[],
            silent=None,
            timed_out=False,
            turn=turn,
        )
        result["boundary"] = boundary
        return result

    # ---- user line and plan ----------------------------------------------
    def _record_user(
        self, message: str, present: list[str], room: RoomHandle, turn_id: str
    ) -> None:
        self.service.record_event(
            "user",
            "dialogue",
            "You: " + message,
            participants=["user", *present],
            visibility="public",
            room_id=room.room_id,
            metadata=_metadata(
                turn_id, "speech", "primary", "neutral", None, False
            ),
        )

    def _record_plan(self, plan: dict, turn_id: str, room: RoomHandle) -> None:
        self.service.record_event(
            "director",
            "turn_plan",
            _plan_summary(plan),
            participants=[],
            visibility="public",
            room_id=room.room_id,
            metadata={"turn_id": turn_id, "plan": plan, "topic": plan["topic"]},
        )

    def _arbitrate(
        self,
        message: str,
        present: list[str],
        verdicts: dict[str, dict],
        plan: dict,
        turn_id: str,
        room: RoomHandle,
        arbiter_client: Any | None,
    ) -> dict | None:
        target = plan.get("primary")
        if not target:
            return None
        if arbiter_client is None and not social_arbiter.enabled():
            return None
        note = social_arbiter.arbitrate(
            self.service,
            target,
            message,
            verdicts[target],
            client=arbiter_client,
        )
        plan["arbiter"] = note
        if note.get("used"):
            self.service.record_event(
                "director",
                "social_arbiter",
                f"Slow social check: {note['stance']} "
                f"({note['tone']}, {note.get('latency_ms', 0)} ms).",
                participants=[target],
                visibility="public",
                room_id=room.room_id,
                metadata={"arbiter": note, "primary": target},
            )
        return note

    def _record_planned_silence(
        self, plan: dict, turn_id: str, room: RoomHandle
    ) -> None:
        for character in plan.get("silent") or []:
            self._record_silence(character, "silent", turn_id, plan, room)

    def _record_silence(
        self, character: str, role: str, turn_id: str, plan: dict, room: RoomHandle
    ) -> dict:
        event = self.service.record_event(
            character,
            "silence",
            SILENCE_SUMMARY.format(name=character.title()),
            participants=[character],
            visibility="public",
            room_id=room.room_id,
            metadata=_metadata(
                turn_id, "silence", role, "neutral", plan.get("primary"), False
            ),
        )
        return {
            "character": character,
            "mode": "silence",
            "role": role,
            "text": None,
            "expression": "neutral",
            "event_id": event["id"],
        }

    # ---- transport --------------------------------------------------------
    def _deliver(
        self,
        room: RoomHandle,
        speakers: Sequence[str],
        prompts: Sequence[Prompt],
        turn_id: str,
        timeout: float,
    ) -> list[Any]:
        cap = min(max(1.0, float(timeout)), TURN_CAP_SECONDS)
        deadline = self._now() + cap
        try:
            delivery = self.transport.deliver_many(
                room, prompts, turn_id=TurnId(turn_id), deadline=deadline
            )
        except TransportError as exc:
            raise RuntimeError(
                "the Switch room did not accept the message; check that the gateway and "
                f"the four live sessions are running ({exc})"
            ) from exc
        if delivery.inline:
            return list(delivery.inline)
        try:
            return self.transport.collect(
                delivery,
                speakers=[CharacterId(character) for character in speakers],
                deadline=deadline,
            )
        except TransportError as exc:
            raise RuntimeError(
                "the Switch room did not return the turn; check that the gateway and "
                f"the four live sessions are running ({exc})"
            ) from exc

    def _relay(
        self,
        message: str,
        present: list[str],
        verdicts: dict[str, dict],
        plan: dict,
        turn_id: str,
        room: RoomHandle,
        turn: dict,
        replies: list[dict],
        timeout: float,
    ) -> None:
        # One agent-to-agent aside per turn, from the first planned speaker who
        # names another present character. Read the already-sanitised line text,
        # so a refusal or leak replacement can never be forwarded to the target.
        relay = None
        relay_text = ""
        for line in turn["lines"]:
            if line.get("mode") in {"silence", "boundary"}:
                continue
            body = (line.get("text") or "").strip()
            character = str(line.get("character") or "")
            if not body or not character:
                continue
            mentions = _agent_mentions(body, present, character)
            if mentions:
                relay = {"from": character, "to": mentions[0], "delivered": False}
                relay_text = body
                break
        if not relay:
            return

        plan["relay"] = relay
        self.service.record_event(
            "director",
            "agent_relay",
            f"{relay['from'].title()} turns to {relay['to'].title()}.",
            participants=[relay["from"], relay["to"]],
            visibility="public",
            room_id=room.room_id,
            metadata={
                "turn_id": turn_id,
                "from": relay["from"],
                "to": relay["to"],
            },
        )

        target = relay["to"]
        budget = min(12.0, max(2.0, float(timeout)))
        posted = False
        try:
            delivery = self.transport.deliver_many(
                room,
                [
                    Prompt(
                        speaker=CharacterId(target),
                        text=_relay_prompt(
                            self.service,
                            relay["from"],
                            target,
                            relay_text,
                            envelope=self._envelope,
                        ),
                    )
                ],
                turn_id=TurnId(f"{turn_id}-relay"),
            )
            posted = True
        except TransportError:
            posted = False

        relay_turn = None
        if posted:
            # Match HEAD: the aside's budget starts after its own post, so a
            # slow relay post does not consume the reply window.
            deadline = self._now() + budget
            if delivery.inline:
                inbound = list(delivery.inline)
            else:
                try:
                    inbound = self.transport.collect(
                        delivery,
                        speakers=[CharacterId(target)],
                        deadline=deadline,
                    )
                except TransportError:
                    inbound = []
            for item in inbound:
                if str(item.sender) != target:
                    continue
                body = clean_scene_line(item.text)
                if not body:
                    continue
                event_id = "" if item.synthetic else str(item.event_id)
                if event_id and self.service.event_by_message_id(event_id):
                    # Already recorded in the planned phase; keep looking for
                    # the actual relay reply in the same snapshot.
                    continue
                relay_turn = item
                break

        if relay_turn is None:
            turn["relay_missing"] = [target]
            return

        verdict = verdicts[target]
        body = _sanitise_reply(target, clean_scene_line(relay_turn.text), verdict, message)
        beat_mode, text = _beat_mode(body, "reply")
        duplicate = any(
            line.get("character") == target
            and _normalise(line.get("text")) == _normalise(text)
            for line in turn["lines"]
        )
        if duplicate:
            turn["relay_duplicate"] = target
            relay["delivered"] = True
            return

        self._apply_writes(target, relay_turn.writes)
        mode = "reply" if beat_mode == "speech" else beat_mode
        expression = _expression(verdict, "reply", mode)
        kind = "action" if beat_mode == "action" else "dialogue"
        summary = (
            f"{target.title()}: {text}"
            if kind == "dialogue"
            else f"{target.title()} {text}"
        )
        metadata = _metadata(
            turn_id, mode, "reply", expression, relay["from"], False
        )
        metadata["reply_to"] = relay["from"]
        metadata["relay"] = True
        event_id = "" if relay_turn.synthetic else str(relay_turn.event_id)
        recorded = self.service.record_event(
            target,
            kind,
            summary,
            participants=[target],
            visibility="public",
            room_id=room.room_id,
            message_id=event_id or None,
            metadata=metadata,
        )
        turn["lines"].append(
            {
                "character": target,
                "mode": mode,
                "role": "reply",
                "text": text,
                "expression": expression,
                "target": relay["from"],
                "event_id": recorded["id"],
            }
        )
        replies.append(
            {
                "character": target,
                "text": text,
                "event_id": recorded["id"],
                "message_id": event_id or None,
            }
        )
        relay["delivered"] = True

    # ---- writes -----------------------------------------------------------
    def _apply_writes(
        self, character: str, writes: Sequence[WorldWrite]
    ) -> dict:
        belief = None
        moved: list[dict] = []
        for write in writes:
            if isinstance(write, MemoryWrite):
                try:
                    belief = self.service.remember(
                        character,
                        proposition=write.proposition,
                        source=write.source,
                        confidence=write.confidence,
                        visibility=write.visibility,
                        proposition_key=write.proposition_key,
                    )
                except (KeyError, TypeError, ValueError):
                    belief = None
            elif isinstance(write, RelationshipWrite):
                try:
                    moved.append(
                        self.service.update_relationship(
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
        return {"memory": belief, "relationships": moved}

    # ---- result / time ----------------------------------------------------
    def _result(
        self,
        *,
        room: dict | None,
        present: list[str],
        verdicts: dict,
        replies: list[dict],
        missing: list[str],
        silent: list[str] | None,
        timed_out: bool,
        turn: dict,
    ) -> dict:
        # ``silent=None`` marks the boundary result, whose old shape had no key.
        result = {
            "room": room,
            "targets": present,
            "verdicts": verdicts,
            "replies": replies,
            "missing": missing,
            "timed_out": timed_out,
            "clock": self.service.clock(),
            "revision": self.service.revision(),
            "turn": turn,
        }
        if silent is not None:
            result["silent"] = silent
        return result

    def _now(self) -> float:
        monotonic = getattr(self._time, "monotonic", None)
        if callable(monotonic):
            return float(monotonic())
        return float(self._time.time())


def _normalise(text: Any) -> str:
    import re

    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


__all__ = ["TurnRecorder"]
