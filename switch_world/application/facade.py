"""The world facade over :class:`switch_world.adapters.persistence.WorldStore`.

The public surface of :class:`WorldService` is unchanged: every method keeps its
name, signature and return shape. The body delegates to the store's reader,
writer or admin face. New code should call the store directly; this class is the
application seam the MCP tools, the HTTP adapter and the directors use.

``_conn`` remains only as a deprecated compatibility path for legacy callers that
need a raw connection (the clock test is the one remaining user).
"""
from __future__ import annotations

import hmac
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from switch_world.adapters.persistence import WorldStore
from switch_world.domain import (
    CHARACTER_ORDER,
    CONNECTION_LABELS,
    IDEMPOTENCY_KEEP,
    LABELS,
    PAUSE_META,
    REVISION_META,
    SCENARIO_ID_META,
    SCENARIO_META,
    SOURCE_KINDS,
    VISIBILITIES,
    IdempotencyConflict,
    clamp,
    connection_label,
    slugify,
    tokens,
)

from switch_world.config import Settings, load_settings


def _settings() -> Settings:
    """Resolve process settings at call time (no import-time side effects)."""
    return load_settings(os.environ)

VISIBILITIES = VISIBILITIES
SOURCE_KINDS = SOURCE_KINDS
CHARACTER_ORDER = CHARACTER_ORDER
CONNECTION_LABELS = CONNECTION_LABELS
SCENARIO_META = SCENARIO_META
SCENARIO_ID_META = SCENARIO_ID_META
PAUSE_META = PAUSE_META
REVISION_META = REVISION_META
IDEMPOTENCY_KEEP = IDEMPOTENCY_KEEP
LABELS = LABELS
IdempotencyConflict = IdempotencyConflict

# Historical private aliases retained for compatibility.
_clamp = clamp
_tokens = tokens


class WorldService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        tokens: Mapping[str, str] | None = None,
        state_dir: Path | str | None = None,
    ):
        settings = _settings()
        self.db_path = Path(db_path or settings.db_path)
        self.state_dir = Path(state_dir or settings.state_dir)
        self.tokens = dict(tokens or settings.token_map())
        self.store = WorldStore(
            db_path=self.db_path,
            state_dir=self.state_dir,
            world_start=settings.world_start,
            world_day=settings.world_day,
        )
        # Resolve the clock provider through the class so tests that monkeypatch
        # ``WorldService._real_now`` keep controlling realtime clocks.
        self.store._real_now_provider = lambda: WorldService._real_now()

    # ---- plumbing ---------------------------------------------------------

    @contextmanager
    def _conn(self):
        """Deprecated: use ``self.store.transaction()`` instead.

        Kept only for legacy callers that need raw SQL; no production module
        should call it. ``tests/architecture/test_no_private_connections.py``
        enforces that.
        """
        with self.store.transaction() as conn:
            yield conn

    def actor_for_token(self, token: str) -> str:
        # Compare against every entry without short-circuiting so the lookup
        # time does not reveal which token (or which prefix) was presented.
        candidate = token.encode("utf-8")
        actor = None
        for known, owner in self.tokens.items():
            if hmac.compare_digest(known.encode("utf-8"), candidate):
                actor = owner
        if actor is None:
            raise PermissionError("unknown world token")
        return actor

    def actor_from_headers(self, headers: Mapping[str, str] | None) -> str:
        headers = headers or {}
        auth = headers.get("authorization") or headers.get("Authorization") or ""
        if not auth.lower().startswith("bearer "):
            raise PermissionError("missing bearer token")
        return self.actor_for_token(auth.split(" ", 1)[1].strip())

    @staticmethod
    def _real_now() -> datetime:
        return datetime.now().astimezone()

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value)

    @staticmethod
    def _validate_scale(value: Any) -> float:
        return WorldStore._validate_scale(value)

    # ---- compatibility private helpers -----------------------------------

    def _clock(self, conn: sqlite3.Connection) -> dict[str, Any]:
        return self.store._clock(conn)

    @classmethod
    def _clock_from_row(cls, row: sqlite3.Row) -> dict[str, Any]:
        return WorldStore._clock_from_row(row, cls._real_now())

    def _now(self, conn: sqlite3.Connection) -> str:
        return self.store._now(conn)

    def _character_exists(self, conn: sqlite3.Connection, cid: str) -> bool:
        return self.store._character_exists(conn, cid)

    def _canonical_actor(self, conn: sqlite3.Connection, value: str) -> str:
        return self.store._canonical_actor(conn, value)

    def _canonical_participant(self, conn: sqlite3.Connection, value: str) -> str:
        return self.store._canonical_participant(conn, value)

    def _current_scenario(self, conn: sqlite3.Connection) -> dict | None:
        return self.store._current_scenario(conn)

    def _scenario_id(self, conn: sqlite3.Connection) -> str | None:
        return self.store._scenario_id(conn)

    def _resolve_belief_id(
        self, conn: sqlite3.Connection, source_belief: int | str
    ) -> dict:
        return self.store._resolve_belief_id(conn, source_belief)

    def _parse_source(
        self, conn: sqlite3.Connection, actor: str, source: str, now: str
    ) -> tuple[str, str]:
        return self.store._parse_source(conn, actor, source, now)

    def _belief(self, conn: sqlite3.Connection, belief_id: int) -> dict:
        return self.store._belief(conn, belief_id)

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict:
        return WorldStore._event_dict(row)

    @staticmethod
    def _connection_label(affinity: float, tension: float) -> str:
        return connection_label(affinity, tension)

    def _revision(self, conn: sqlite3.Connection) -> int:
        return self.store._revision(conn)

    def _bump_revision(self, conn: sqlite3.Connection) -> int:
        return self.store._bump_revision(conn)

    # ---- clock ------------------------------------------------------------

    def clock(self) -> dict[str, Any]:
        return self.store.reader.clock()

    def set_clock_mode(
        self,
        mode: str,
        now: str | None = None,
        scale: float | None = None,
    ) -> dict[str, Any]:
        return self.store.writer.set_clock_mode(mode, now=now, scale=scale)

    # ---- friends (phone gating) ------------------------------------------

    def friends(self) -> list[dict[str, str]]:
        return self.store.reader.friends()

    def is_friend(self, character: str) -> bool:
        return self.store.reader.is_friend(character)

    def add_friend(self, character: str) -> dict[str, str]:
        return self.store.writer.add_friend(character)

    def character_exists(self, character: str) -> bool:
        return self.store.reader.character_exists(character)

    def characters(self) -> list[dict]:
        return self.store.reader.characters()

    # ---- scenarios (loadable demo worlds) --------------------------------

    def current_scenario(self) -> dict | None:
        return self.store.reader.current_scenario()

    def current_scenario_id(self) -> str | None:
        return self.store.reader.current_scenario_id()

    def recorded_ending(self, scenario_id: str | None = None) -> dict | None:
        return self.store.reader.recorded_ending(scenario_id)

    # ---- outfits ----------------------------------------------------------

    def outfits(self) -> dict[str, dict]:
        return self.store.reader.outfits()

    def set_outfit(
        self,
        character: str,
        outfit_id: str,
        reason: str = "",
        source_belief_id: int | str | None = None,
        label: str | None = None,
        art: str | None = None,
    ) -> dict:
        return self.store.writer.set_outfit(
            character,
            outfit_id,
            reason=reason,
            source_belief_id=source_belief_id,
            label=label,
            art=art,
        )

    # ---- items ------------------------------------------------------------

    def items(self) -> list[dict]:
        return self.store.reader.items()

    def item(self, item_id: str) -> dict | None:
        return self.store.reader.item(item_id)

    def give_item(
        self,
        item_id: str,
        to: str,
        label: str | None = None,
        owner: str | None = None,
        status: str = "carried",
        *,
        actor: str | None = None,
    ) -> dict:
        return self.store.writer.give_item(
            item_id,
            to,
            label=label,
            owner=owner,
            status=status,
            actor=actor,
        )

    # ---- connections ------------------------------------------------------

    def connections(self) -> list[dict]:
        return self.store.reader.connections()

    # ---- beliefs ----------------------------------------------------------

    def remember(
        self,
        actor: str,
        proposition: str,
        source: str,
        confidence: float = 0.8,
        visibility: str = "private",
        proposition_key: str | None = None,
    ) -> dict:
        return self.store.writer.remember(
            actor,
            proposition,
            source,
            confidence=confidence,
            visibility=visibility,
            proposition_key=proposition_key,
        )

    def recall(self, actor: str, query: str = "", limit: int = 8) -> dict:
        return self.store.reader.recall(actor, query=query, limit=limit)

    # ---- presence ---------------------------------------------------------

    ABSENT_PREFIX = "absent:"

    def mark_absent(self, character: str, reason: str = "") -> dict:
        return self.store.writer.mark_absent(character, reason=reason)

    def mark_present(self, character: str) -> dict:
        return self.store.writer.mark_present(character)

    def is_absent(self, character: str) -> bool:
        return self.store.reader.is_absent(character)

    def absent_characters(self) -> list[str]:
        return self.store.reader.absent_characters()

    # ---- relationships ----------------------------------------------------

    def relationship(self, actor: str, other: str) -> dict:
        return self.store.reader.relationship(actor, other)

    def update_relationship(
        self,
        actor: str,
        other: str,
        trust_delta: float = 0.0,
        closeness_delta: float = 0.0,
        tension_delta: float = 0.0,
        reason: str = "",
    ) -> dict:
        return self.store.writer.update_relationship(
            actor,
            other,
            trust_delta=trust_delta,
            closeness_delta=closeness_delta,
            tension_delta=tension_delta,
            reason=reason,
        )

    # ---- events -----------------------------------------------------------

    def record_event(
        self,
        actor: str,
        kind: str,
        summary: str,
        participants: Iterable[str] | None = None,
        visibility: str = "public",
        room_id: str | None = None,
        message_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict:
        return self.store.writer.record_event(
            actor,
            kind,
            summary,
            participants=participants,
            visibility=visibility,
            room_id=room_id,
            message_id=message_id,
            metadata=metadata,
        )

    def events(self, kind: str | None = None) -> list[dict]:
        return self.store.reader.events(kind)

    def event_by_message_id(self, message_id: str) -> dict | None:
        return self.store.reader.event_by_message_id(message_id)

    def latest_event(self, kind: str) -> dict | None:
        return self.store.reader.latest_event(kind)

    def completed_beats(self) -> list[str]:
        return self.store.reader.completed_beats()

    def who_knows(self, proposition_key: str) -> dict:
        return self.store.reader.who_knows(proposition_key)

    # ---- phone history -----------------------------------------------------

    def phone_history(
        self,
        character: str,
        limit: int = 100,
        before_id: int | None = None,
        include_scene: bool = False,
    ) -> dict:
        return self.store.reader.phone_history(
            character, limit=limit, before_id=before_id, include_scene=include_scene
        )

    # ---- state and projections -------------------------------------------

    def state(self) -> dict:
        """The full dashboard projection, built from one store snapshot."""
        return self.state_from_snapshot(self.store.reader.snapshot())

    def state_from_snapshot(self, snapshot: dict) -> dict:
        """Build the public state shape from a store snapshot (pure)."""
        scenario = snapshot["scenario"]
        items = snapshot["items"]
        return {
            "clock": snapshot["clock"],
            "revision": snapshot["revision"],
            "turn": snapshot["turn"],
            "paused": snapshot["paused"],
            "characters": snapshot["characters"],
            "beliefs": snapshot["beliefs"],
            "relationships": snapshot["relationships"],
            "events": snapshot["events"],
            "friends": snapshot["friends"],
            "absent_characters": snapshot["absent_characters"],
            "done_beats": snapshot["done_beats"],
            "branch": snapshot["branch"],
            "matrix": snapshot["matrix"],
            "scenario": scenario,
            "outfits": snapshot["outfits"],
            "items": items,
            "item": self._scenario_item(items, scenario),
            "cast_art": dict((scenario or {}).get("cast_art") or {}),
            "scene_art": (scenario or {}).get("scene_art"),
            "connections": snapshot["connections"],
        }

    @staticmethod
    def _scenario_item(items: list[dict], scenario: dict | None) -> dict | None:
        if not items:
            return None
        wanted = (scenario or {}).get("item")
        if isinstance(wanted, dict) and wanted.get("id"):
            for item in items:
                if item["id"] == wanted["id"]:
                    return item
        return items[0]

    def matrix(self) -> list[dict]:
        return self.store.reader.matrix()

    def advance_time(self, actor: str, minutes: int) -> dict:
        return self.store.writer.advance_time(actor, minutes)

    # ---- revision, pause and idempotency ----------------------------------

    def revision(self) -> int:
        return self.store.reader.revision()

    def turn(self) -> int:
        return self.store.reader.turn()

    def paused(self) -> bool:
        return self.store.reader.paused()

    def set_paused(self, paused: bool) -> dict:
        return self.store.writer.set_paused(paused)

    # ---- off-screen beats -------------------------------------------------

    OFFSCREEN_TEMPLATES = {
        "promise": "{name} promised to sort something out before the next meet-up.",
        "rumor": "Word going around: {name} has been unusually quiet about something.",
        "errand": "{name} slipped out to run an errand and will be back later.",
    }

    def record_offscreen(
        self,
        character: str | None = None,
        kind: str | None = None,
    ) -> dict:
        return self.store.writer.record_offscreen(character=character, kind=kind)

    # ---- idempotency ------------------------------------------------------

    def idempotent_replay(
        self, scope: str, request_id: str, digest: str
    ) -> dict | None:
        return self.store.reader.idempotent_replay(scope, request_id, digest)

    def store_idempotent(
        self,
        scope: str,
        request_id: str,
        digest: str,
        response: Mapping[str, Any],
    ) -> None:
        return self.store.writer.store_idempotent(scope, request_id, digest, response)

    # ---- scene card -------------------------------------------------------

    def scene_card(self, title: str | None = None) -> dict:
        state = self.state()
        clock = state["clock"]
        lines: list[str] = []
        lines.append("# Scene card — " + (title or "A Tuesday in late autumn"))
        lines.append("")
        lines.append(f"**World time:** {clock['now']}  ")
        lines.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}")
        lines.append("")
        lines.append("## Cast")
        lines.append("")
        for c in state["characters"]:
            lines.append(f"- **{c['name']}** — {c['role']}")
        lines.append("")
        lines.append("## What happened")
        lines.append("")
        for e in state["events"][-24:]:
            lines.append(f"- `{e['created_at']}` **{e['kind']}** — {e['summary']}")
        lines.append("")
        lines.append("## Who knows what")
        lines.append("")
        for row in state["matrix"]:
            holders = row["holders"]
            if not holders:
                continue
            parts = []
            for cid, cell in holders.items():
                source = cell["source"]
                parts.append(f"{cid} {cell['confidence']:.2f} ({source}, {cell['visibility']})")
            lines.append(f"- **{row['label']}** — " + "; ".join(parts))
        lines.append("")
        lines.append("## Relationship changes")
        lines.append("")
        changes = [e for e in state["events"] if e["kind"] == "relationship_update"]
        if changes:
            for e in changes[-12:]:
                lines.append(f"- `{e['created_at']}` {e['summary']}")
        else:
            lines.append("- None recorded.")
        lines.append("")
        lines.append("## Provenance")
        lines.append("")
        lines.append("Every belief above names its source. A character can only read its own")
        lines.append("private beliefs through the world engine's scoped MCP token.")
        lines.append("")
        text = "\n".join(lines)

        export_dir = _settings().export_dir
        export_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = export_dir / f"scene-card-{stamp}.md"
        path.write_text(text)
        return {"path": str(path), "text": text}

    # ---- dev --------------------------------------------------------------

    def reset(self) -> None:
        self.store.admin.reset()


__all__ = [
    "CHARACTER_ORDER",
    "CONNECTION_LABELS",
    "IDEMPOTENCY_KEEP",
    "IdempotencyConflict",
    "LABELS",
    "PAUSE_META",
    "REVISION_META",
    "SCENARIO_ID_META",
    "SCENARIO_META",
    "SOURCE_KINDS",
    "VISIBILITIES",
    "WorldService",
    "slugify",
]
