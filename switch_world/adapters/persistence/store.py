"""SQLite-backed world store.

This is the only component that runs SQL. The compatibility facade
(:class:`world_engine.service.WorldService`) and the scenario/take loaders call
the grouped readers/writers below instead of opening their own connections.

The store exposes three narrow faces over one object:

``reader``
    Queries and projections. No writes.
``writer``
    State changes, each committed in its own transaction unless the caller
    passes an explicit connection from :meth:`WorldStore.transaction`.
``admin``
    Whole-database operations such as reset and applying a scenario seed.

All methods accept ``conn=None``. When a connection is supplied the caller owns
the transaction (used by scenario/take loading and by :meth:`snapshot`); when it
is omitted the store opens, commits and closes its own connection.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from switch_world.domain import (
    CHARACTER_ORDER,
    IDEMPOTENCY_KEEP,
    LABELS,
    PAUSE_META,
    REVISION_META,
    SCENARIO_ID_META,
    SCENARIO_META,
    SOURCE_KINDS,
    TAKE_CHANGED_META,
    TAKE_INDEX_META,
    TAKE_META,
    TAKE_START_META,
    VISIBILITIES,
    IdempotencyConflict,
    clamp,
    connection_label,
    slugify,
    tokens,
)
from . import schema

# Presence is stored in the generic meta table under this prefix.
ABSENT_PREFIX = "absent:"

# Meta keys that belong to the take layer, read together with the state snapshot.
TAKE_SNAPSHOT_KEYS = (TAKE_META, TAKE_INDEX_META, TAKE_START_META, TAKE_CHANGED_META)

# Public events that only the director (or system) may write.  Characters may
# still write their own dialogue, action, silence, DM and whisper events, but
# they cannot forge a turn plan, a beat, a branch or any lifecycle/system line.
DIRECTOR_ONLY_PUBLIC_KINDS = frozenset(
    {
        "scene_start",
        "scene_end",
        "turn_plan",
        "beat",
        "branch",
        "scenario",
        "system",
        "canon_warning",
        "boundary_violation",
        "social_arbiter",
        "item_given",
        "outfit_change",
        "relationship_update",
        "friend",
        "offscreen",
        "no_reply",
    }
)


class WorldStore:
    def __init__(
        self,
        db_path: Path | str,
        state_dir: Path | str | None = None,
        *,
        world_start: str | None = None,
        world_day: str | None = None,
    ) -> None:
        if state_dir is None or world_start is None or world_day is None:
            settings = _ambient_settings()
            state_dir = state_dir or settings.state_dir
            world_start = world_start or settings.world_start
            world_day = world_day or settings.world_day
        self.db_path = Path(db_path)
        self.state_dir = Path(state_dir)
        self.world_start = str(world_start)
        self.world_day = str(world_day)
        self._real_now_provider = None
        self._reader = _Reader(self)
        self._writer = _Writer(self)
        self._admin = _Admin(self)
        schema.init_db(
            self.db_path,
            self.state_dir,
            world_start=self.world_start,
            world_day=self.world_day,
        )

    # ---- faces ------------------------------------------------------------

    @property
    def reader(self) -> "_Reader":
        return self._reader

    @property
    def writer(self) -> "_Writer":
        return self._writer

    @property
    def admin(self) -> "_Admin":
        return self._admin

    # ---- connections ------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        return schema.connect(self.db_path)

    @contextmanager
    def transaction(self):
        """One write connection. Commits on success, rolls back on error."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _read(self, fn, conn: sqlite3.Connection | None = None):
        if conn is not None:
            return fn(conn)
        connection = self.connect()
        try:
            return fn(connection)
        finally:
            connection.close()

    def _write(self, fn, conn: sqlite3.Connection | None = None):
        if conn is not None:
            return fn(conn)
        connection = self.connect()
        try:
            result = fn(connection)
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    # ---- time -------------------------------------------------------------

    def _real_now(self) -> datetime:
        provider = self._real_now_provider
        return provider() if provider is not None else datetime.now().astimezone()

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value)

    @classmethod
    def _clock_from_row(cls, row: sqlite3.Row, real_now: datetime) -> dict[str, Any]:
        """Resolve the story clock.

        In ``realtime`` the stored ``now`` is an anchor and the story advances
        from the real time recorded in ``anchor_real``, multiplied by ``scale``
        (1.0 is wall-clock speed; 60.0 is one story hour per real minute).
        """
        now = cls._parse_time(row["now"])
        mode = row["mode"] or "mock"
        scale = float(row["scale"] or 1.0) if "scale" in row.keys() else 1.0
        if mode == "realtime" and row["anchor_real"]:
            anchor = cls._parse_time(row["anchor_real"])
            elapsed = (real_now - anchor).total_seconds() * scale
            now = now + timedelta(seconds=elapsed)
        return {
            "now": now.isoformat(timespec="seconds"),
            "day": now.date().isoformat(),
            "mode": mode,
            "scale": scale,
        }

    def _clock(self, conn: sqlite3.Connection) -> dict[str, Any]:
        row = conn.execute(
            "SELECT now, day, mode, anchor_real, scale FROM clock WHERE id = 1"
        ).fetchone()
        return self._clock_from_row(row, self._real_now())

    def _now(self, conn: sqlite3.Connection) -> str:
        return self._clock(conn)["now"]

    @staticmethod
    def _validate_scale(value: Any) -> float:
        try:
            scale = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("clock scale must be a number greater than zero") from exc
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("clock scale must be a number greater than zero")
        return scale

    # ---- actor helpers ----------------------------------------------------

    def _character_exists(self, conn: sqlite3.Connection, cid: str) -> bool:
        return conn.execute("SELECT 1 FROM characters WHERE id = ?", (cid,)).fetchone() is not None

    def _canonical_actor(self, conn: sqlite3.Connection, value: str) -> str:
        """Resolve an id, a display name, a first name, or 'you' to a canonical actor."""
        raw = (value or "").strip()
        if not raw:
            raise ValueError("character is required")
        lowered = raw.lower()
        if lowered in {"user", "you", "the user", "me"}:
            return "user"
        if lowered in CHARACTER_ORDER or lowered == "director":
            return lowered
        pattern = (
            lowered.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            + " %"
        )
        row = conn.execute(
            "SELECT id FROM characters WHERE id = ? OR lower(name) = ? "
            "OR lower(name) LIKE ? ESCAPE '\\'",
            (raw, lowered, pattern),
        ).fetchone()
        if row:
            return row["id"]
        raise ValueError("unknown character: " + raw)

    def _canonical_participant(self, conn: sqlite3.Connection, value: str) -> str:
        try:
            return self._canonical_actor(conn, value)
        except ValueError:
            return str(value).strip()

    # ---- event helpers ----------------------------------------------------

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict:
        event = dict(row)
        event["participants"] = json.loads(event.pop("participants_json", None) or "[]")
        raw = event.pop("metadata_json", None)
        try:
            event["metadata"] = json.loads(raw or "{}")
        except (TypeError, ValueError):
            event["metadata"] = {}
        return event

    # ---- reader -----------------------------------------------------------

    def clock(self, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        return self._read(self._clock, conn)

    def friends(self, conn: sqlite3.Connection | None = None) -> list[dict[str, str]]:
        def query(c):
            rows = c.execute(
                "SELECT character, since FROM friends ORDER BY since, character"
            ).fetchall()
            return [dict(r) for r in rows]

        return self._read(query, conn)

    def is_friend(self, character: str, conn: sqlite3.Connection | None = None) -> bool:
        def query(c):
            row = c.execute(
                "SELECT 1 FROM friends WHERE character = ?", (character,)
            ).fetchone()
            return row is not None

        return self._read(query, conn)

    def character_exists(
        self, character: str, conn: sqlite3.Connection | None = None
    ) -> bool:
        return self._read(lambda c: self._character_exists(c, character), conn)

    def characters(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        def query(c):
            rows = [dict(r) for r in c.execute("SELECT * FROM characters")]
            return sorted(rows, key=lambda item: CHARACTER_ORDER.get(item["id"], 99))

        return self._read(query, conn)

    def _current_scenario(self, conn: sqlite3.Connection) -> dict | None:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (SCENARIO_META,)
        ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["value"])
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict):
            return data
        scenario_id = self._scenario_id(conn)
        return {"id": scenario_id} if scenario_id else None

    def _scenario_id(self, conn: sqlite3.Connection) -> str | None:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (SCENARIO_ID_META,)
        ).fetchone()
        return str(row["value"]) if row else None

    def current_scenario(
        self, conn: sqlite3.Connection | None = None
    ) -> dict | None:
        return self._read(self._current_scenario, conn)

    def current_scenario_id(
        self, conn: sqlite3.Connection | None = None
    ) -> str | None:
        return self._read(self._scenario_id, conn)

    def recorded_ending(self, scenario_id: str | None = None) -> dict | None:
        scenario_id = scenario_id or self.current_scenario_id()
        if not scenario_id:
            return None
        for event in reversed(self.events("ending")):
            if event.get("metadata", {}).get("scenario_id") == scenario_id:
                return event
        return None

    def _outfits(self, conn: sqlite3.Connection) -> dict[str, dict]:
        rows = [
            dict(r) for r in conn.execute(
                """SELECT o.*, b.proposition_key AS source_belief_key
                     FROM outfits o
                     LEFT JOIN beliefs b ON b.id = o.source_belief_id"""
            )
        ]
        rows.sort(key=lambda row: CHARACTER_ORDER.get(row["character"], 99))
        return {row["character"]: row for row in rows}

    def outfits(self, conn: sqlite3.Connection | None = None) -> dict[str, dict]:
        return self._read(self._outfits, conn)

    def items(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        def query(c):
            rows = c.execute("SELECT * FROM items ORDER BY created_at, id").fetchall()
            return [dict(r) for r in rows]

        return self._read(query, conn)

    def item(
        self, item_id: str, conn: sqlite3.Connection | None = None
    ) -> dict | None:
        def query(c):
            row = c.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            return dict(row) if row else None

        return self._read(query, conn)

    def _connections(self, conn: sqlite3.Connection) -> list[dict]:
        characters = sorted(CHARACTER_ORDER, key=lambda cid: CHARACTER_ORDER[cid])
        rows = [dict(r) for r in conn.execute("SELECT * FROM relationships")]
        directed = {(row["a"], row["b"]): row for row in rows}
        out: list[dict] = []
        for index, a in enumerate(characters):
            for b in characters[index + 1:]:
                edges = [
                    directed[(a, b)] if (a, b) in directed else None,
                    directed[(b, a)] if (b, a) in directed else None,
                ]
                edges = [edge for edge in edges if edge is not None]
                if not edges:
                    affinity, tension, shared = 0.5, 0.0, 0
                else:
                    affinities = [
                        ((float(e["trust"]) + float(e["closeness"])) / 2)
                        - float(e["tension"]) / 2
                        for e in edges
                    ]
                    affinity = sum(affinities) / len(affinities)
                    tension = sum(float(e["tension"]) for e in edges) / len(edges)
                    shared = max(int(e.get("shared_secret_count") or 0) for e in edges)
                out.append(
                    {
                        "a": a,
                        "b": b,
                        "affinity": round(clamp(affinity), 4),
                        "tension": round(clamp(tension), 4),
                        "label": connection_label(affinity, tension),
                        "shared_secret_count": shared,
                    }
                )
        return out

    def connections(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        return self._read(self._connections, conn)

    def _parse_source(
        self, conn: sqlite3.Connection, actor: str, source: str, now: str
    ) -> tuple[str, str]:
        source = (source or "").strip()
        if source == "user":
            return "user", "user"
        if source == "observation":
            return "observation", actor
        if ":" in source:
            kind, sid = source.split(":", 1)
            if kind not in SOURCE_KINDS:
                raise ValueError(
                    "source must be user, observation, character:<id> or event:<id>"
                )
            if kind == "character" and not self._character_exists(conn, sid):
                raise ValueError("unknown character in source: " + sid)
            if kind == "event":
                row = conn.execute("SELECT 1 FROM events WHERE id = ?", (int(sid),)).fetchone()
                if not row:
                    raise ValueError("unknown event in source: " + sid)
            return kind, sid
        raise ValueError("source must be user, observation, character:<id> or event:<id>")

    def _belief(self, conn: sqlite3.Connection, belief_id: int) -> dict:
        row = conn.execute(
            """SELECT b.*, c.name AS holder_name
                 FROM beliefs b JOIN characters c ON c.id = b.holder
                WHERE b.id = ?""",
            (belief_id,),
        ).fetchone()
        return dict(row) if row else {}

    def recall(
        self, actor: str, query: str = "", limit: int = 8
    ) -> dict:
        def load(c):
            rows = c.execute(
                """SELECT b.*, c.name AS holder_name
                     FROM beliefs b JOIN characters c ON c.id = b.holder
                    WHERE b.superseded_by IS NULL
                      AND (b.holder = ? OR b.visibility = 'public')
                    ORDER BY b.id""",
                (actor,),
            ).fetchall()
            return rows, self._clock(c)

        rows, clock = self._read(load)
        now = self._parse_time(clock["now"])
        q = tokens(query)
        scored: list[tuple[float, dict]] = []
        for row in rows:
            item = dict(row)
            text = item["proposition"].lower()
            overlap = sum(1 for t in q if t in text)
            relevance = (overlap / len(q)) if q else 0.0
            learned = self._parse_time(item["learned_at"])
            hours = max(0.0, (now - learned).total_seconds() / 3600.0)
            recency = math.pow(0.995, hours)
            score = 2.0 * relevance + float(item["confidence"]) + 0.5 * recency
            if item["holder"] == actor:
                score += 0.25
            item["mine"] = item["holder"] == actor
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        seen: set[str] = set()
        out: list[dict] = []
        for score, item in scored:
            key = item["proposition_key"]
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "proposition": item["proposition"],
                    "key": key,
                    "confidence": item["confidence"],
                    "source": f"{item['source_kind']}:{item['source_id']}"
                    if item["source_kind"] in ("character", "event")
                    else item["source_kind"],
                    "learned_at": item["learned_at"],
                    "visibility": item["visibility"],
                    "mine": item["mine"],
                    "score": round(score, 4),
                }
            )
            if len(out) >= max(1, int(limit)):
                break
        return {"actor": actor, "query": query, "memories": out}

    def is_absent(
        self, character: str, conn: sqlite3.Connection | None = None
    ) -> bool:
        def query(c):
            row = c.execute(
                "SELECT 1 FROM meta WHERE key = ?", (ABSENT_PREFIX + character,)
            ).fetchone()
            return row is not None

        return self._read(query, conn)

    def _absent_characters(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT key FROM meta WHERE key LIKE ?", (ABSENT_PREFIX + "%",)
        ).fetchall()
        ids = {str(row["key"]).split(":", 1)[1] for row in rows}
        return sorted(
            (cid for cid in ids if cid in CHARACTER_ORDER),
            key=lambda cid: CHARACTER_ORDER[cid],
        )

    def absent_characters(
        self, conn: sqlite3.Connection | None = None
    ) -> list[str]:
        return self._read(self._absent_characters, conn)

    def relationship(
        self, actor: str, other: str, conn: sqlite3.Connection | None = None
    ) -> dict:
        def query(c):
            canonical = self._canonical_actor(c, other)
            row = c.execute(
                "SELECT * FROM relationships WHERE a = ? AND b = ?", (actor, canonical)
            ).fetchone()
            if not row:
                return {
                    "a": actor, "b": canonical, "trust": 0.5,
                    "closeness": 0.5, "tension": 0.0,
                    "shared_secret_count": 0, "last_interaction": self._now(c),
                    "exists": False,
                }
            result = dict(row)
            result["exists"] = True
            return result

        return self._read(query, conn)

    def events(
        self, kind: str | None = None, conn: sqlite3.Connection | None = None
    ) -> list[dict]:
        def query(c):
            rows = c.execute(
                "SELECT * FROM events WHERE (? IS NULL OR kind = ?) ORDER BY id",
                (kind, kind),
            ).fetchall()
            return [self._event_dict(row) for row in rows]

        return self._read(query, conn)

    def event_by_message_id(
        self, message_id: str, conn: sqlite3.Connection | None = None
    ) -> dict | None:
        if not message_id:
            return None

        def query(c):
            row = c.execute(
                "SELECT * FROM events WHERE message_id = ? ORDER BY id DESC LIMIT 1",
                (message_id,),
            ).fetchone()
            return self._event_dict(row) if row else None

        return self._read(query, conn)

    def _latest_event(self, conn: sqlite3.Connection, kind: str) -> dict | None:
        row = conn.execute(
            "SELECT * FROM events WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,)
        ).fetchone()
        return self._event_dict(row) if row else None

    def latest_event(
        self, kind: str, conn: sqlite3.Connection | None = None
    ) -> dict | None:
        return self._read(lambda c: self._latest_event(c, kind), conn)

    def _completed_beats(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT kind, summary FROM events WHERE kind IN ('beat', 'branch')"
        ).fetchall()
        done: set[str] = set()
        for row in rows:
            if row["kind"] == "branch":
                done.add("cafe")
                continue
            match = re.match(r"Beat:\s*([a-z-]+)", str(row["summary"] or ""), re.I)
            if match:
                done.add(match.group(1))
        order = {"morning-shop": 0, "truck-lunch": 1, "cafe": 2, "aftermath": 3, "roundup": 4}
        return sorted(done, key=lambda beat: (order.get(beat, 99), beat))

    def completed_beats(
        self, conn: sqlite3.Connection | None = None
    ) -> list[str]:
        return self._read(self._completed_beats, conn)

    def who_knows(
        self, proposition_key: str, conn: sqlite3.Connection | None = None
    ) -> dict:
        def query(c):
            rows = c.execute(
                """SELECT b.*, c.name AS holder_name
                     FROM beliefs b JOIN characters c ON c.id = b.holder
                    WHERE b.proposition_key = ? AND b.superseded_by IS NULL
                    ORDER BY b.confidence DESC""",
                (proposition_key,),
            ).fetchall()
            return rows

        rows = self._read(query, conn)
        holders = [
            {
                "holder": r["holder"],
                "name": r["holder_name"],
                "proposition": r["proposition"],
                "confidence": r["confidence"],
                "source": f"{r['source_kind']}:{r['source_id']}"
                if r["source_kind"] in ("character", "event")
                else r["source_kind"],
                "learned_at": r["learned_at"],
                "visibility": r["visibility"],
            }
            for r in rows
        ]
        return {
            "key": proposition_key,
            "label": LABELS.get(
                proposition_key, holders[0]["proposition"] if holders else proposition_key
            ),
            "holders": holders,
        }

    def phone_history(
        self,
        character: str,
        limit: int = 100,
        before_id: int | None = None,
        include_scene: bool = False,
    ) -> dict:
        limit = max(1, min(int(limit), 200))
        kind_clause = "kind IN ('dialogue', 'dm')" if include_scene else "kind = 'dm'"
        messages: list[dict] = []
        cursor = before_id
        batch = max(limit * 2, 200)
        while len(messages) <= limit:
            def query(c):
                return c.execute(
                    f"""SELECT id, kind, summary, participants_json, created_at
                          FROM events
                         WHERE {kind_clause}
                           AND (? IS NULL OR id < ?)
                         ORDER BY id DESC
                         LIMIT ?""",
                    (cursor, cursor, batch),
                ).fetchall()

            rows = self._read(query)
            if not rows:
                break
            for row in rows:
                participants = json.loads(row["participants_json"] or "[]")
                if character not in participants:
                    continue
                summary = row["summary"] or ""
                if ":" not in summary:
                    continue
                label, text = summary.split(":", 1)
                text = text.strip()
                if row["kind"] == "dm":
                    role = "user" if label.strip().lower() in {"you", "user"} else "character"
                    source = "dm"
                else:
                    role = "user" if label.strip().lower() in {"you", "user"} else "character"
                    source = "scene"
                messages.append(
                    {
                        "id": row["id"],
                        "kind": source,
                        "role": role,
                        "text": text,
                        "created_at": row["created_at"],
                    }
                )
                if len(messages) > limit:
                    break
            cursor = rows[-1]["id"]
            if len(rows) < batch or len(messages) > limit:
                break

        has_more = len(messages) > limit
        messages = messages[:limit]
        messages.reverse()
        oldest = messages[0]["id"] if messages else None
        return {
            "character": character,
            "messages": messages,
            "has_more": has_more,
            "oldest_id": oldest,
        }

    def _matrix(self, conn: sqlite3.Connection) -> list[dict]:
        rows = conn.execute(
            """SELECT b.*, c.name AS holder_name
                 FROM beliefs b JOIN characters c ON c.id = b.holder
                WHERE b.superseded_by IS NULL ORDER BY b.learned_at, b.id"""
        ).fetchall()
        by_key: dict[str, dict] = {}
        for r in rows:
            row = by_key.setdefault(
                r["proposition_key"],
                {
                    "key": r["proposition_key"],
                    "label": LABELS.get(r["proposition_key"], r["proposition"]),
                    "holders": {},
                },
            )
            cell = {
                "proposition": r["proposition"],
                "confidence": r["confidence"],
                "source": f"{r['source_kind']}:{r['source_id']}"
                if r["source_kind"] in ("character", "event")
                else r["source_kind"],
                "source_kind": r["source_kind"],
                "source_id": r["source_id"],
                "visibility": r["visibility"],
                "learned_at": r["learned_at"],
            }
            previous = row["holders"].get(r["holder"])
            if previous is None or cell["learned_at"] >= previous["learned_at"]:
                row["holders"][r["holder"]] = cell
        order = [
            "user-leaving-city", "bookshop-lease", "bookshop-trouble", "alice-hiding-shop",
            "emily-new-job", "emily-leaving", "emily-change", "emily-distracted",
            "alice-money", "sophia-book", "sophia-watching", "truck-debt", "tuesday-cafe",
        ]
        return sorted(
            by_key.values(),
            key=lambda row: (
                order.index(row["key"]) if row["key"] in order else 999,
                row["key"],
            ),
        )

    def matrix(self, conn: sqlite3.Connection | None = None) -> list[dict]:
        return self._read(self._matrix, conn)

    def _revision(self, conn: sqlite3.Connection) -> int:
        event_head = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS head FROM events"
        ).fetchone()["head"]
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (REVISION_META,)
        ).fetchone()
        try:
            meta = int(row["value"]) if row else 0
        except (TypeError, ValueError):
            meta = 0
        return max(int(event_head), meta)

    def revision(self, conn: sqlite3.Connection | None = None) -> int:
        return self._read(self._revision, conn)

    def _turn(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM events "
            "WHERE kind IN ('turn_plan', 'dm', 'whisper', 'take_scene', 'take_load')"
        ).fetchone()
        return int(row["n"])

    def turn(self, conn: sqlite3.Connection | None = None) -> int:
        return self._read(self._turn, conn)

    def _paused(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (PAUSE_META,)
        ).fetchone()
        return bool(row and str(row["value"]) == "1")

    def paused(self, conn: sqlite3.Connection | None = None) -> bool:
        return self._read(self._paused, conn)

    def get_meta(
        self, key: str, conn: sqlite3.Connection | None = None
    ) -> str | None:
        def query(c):
            row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else None

        return self._read(query, conn)

    def get_metas(
        self, keys: Iterable[str], conn: sqlite3.Connection | None = None
    ) -> dict[str, str | None]:
        keys = tuple(keys)

        def query(c):
            placeholders = ",".join("?" for _ in keys)
            rows = c.execute(
                f"SELECT key, value FROM meta WHERE key IN ({placeholders})", keys
            ).fetchall()
            found = {row["key"]: str(row["value"]) for row in rows}
            return {key: found.get(key) for key in keys}

        return self._read(query, conn)

    def has_change_event_after(
        self,
        start: int,
        kinds: Iterable[str],
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        kinds = tuple(kinds)

        def query(c):
            placeholders = ",".join("?" for _ in kinds)
            row = c.execute(
                f"SELECT 1 FROM events WHERE id > ? AND kind IN ({placeholders}) LIMIT 1",
                (start, *kinds),
            ).fetchone()
            return row is not None

        return self._read(query, conn)

    def idempotent_replay(
        self, scope: str, request_id: str, digest: str
    ) -> dict | None:
        if not request_id:
            return None

        def query(c):
            return c.execute(
                "SELECT digest, response_json FROM idempotency "
                "WHERE scope = ? AND request_id = ?",
                (scope, request_id),
            ).fetchone()

        row = self._read(query)
        if not row:
            return None
        if str(row["digest"]) != str(digest):
            raise IdempotencyConflict(
                "request_id was already used with a different payload"
            )
        try:
            data = json.loads(row["response_json"])
        except (TypeError, ValueError) as exc:
            raise IdempotencyConflict(
                "the stored response for this request_id is unreadable"
            ) from exc
        if not isinstance(data, dict):
            raise IdempotencyConflict(
                "the stored response for this request_id is not an object"
            )
        data["replayed"] = True
        return data

    def snapshot(self) -> dict:
        """Everything ``/api/state`` needs, read on one connection.

        This is deliberately one query batch: the dashboard used to open a
        connection per subprojection (matrix, outfits, items, presence, ...),
        which multiplied the request's SQLite handles.
        """

        def build(c: sqlite3.Connection) -> dict:
            characters = sorted(
                (dict(r) for r in c.execute("SELECT * FROM characters")),
                key=lambda item: CHARACTER_ORDER.get(item["id"], 99),
            )
            beliefs = [
                dict(r) for r in c.execute(
                    """SELECT b.*, c.name AS holder_name
                         FROM beliefs b JOIN characters c ON c.id = b.holder
                        WHERE b.superseded_by IS NULL ORDER BY b.id"""
                )
            ]
            relationships = [dict(r) for r in c.execute("SELECT * FROM relationships")]
            recent_rows = c.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT 50"
            ).fetchall()
            events_recent = [
                self._event_dict(row) for row in reversed(recent_rows)
            ]
            clock = self._clock(c)
            friends = [
                r["character"] for r in c.execute(
                    "SELECT character FROM friends ORDER BY since, character"
                )
            ]
            scenario = self._current_scenario(c)
            revision = self._revision(c)
            turn = self._turn(c)
            pause_row = c.execute(
                "SELECT value FROM meta WHERE key = ?", (PAUSE_META,)
            ).fetchone()
            meta = self.get_metas(TAKE_SNAPSHOT_KEYS, conn=c)
            return {
                "characters": characters,
                "beliefs": beliefs,
                "relationships": relationships,
                "events": events_recent,
                "clock": clock,
                "friends": friends,
                "scenario": scenario,
                "revision": revision,
                "turn": turn,
                "paused": bool(pause_row and str(pause_row["value"]) == "1"),
                "absent_characters": self._absent_characters(c),
                "done_beats": self._completed_beats(c),
                "branch": self._latest_event(c, "branch"),
                "matrix": self._matrix(c),
                "outfits": self._outfits(c),
                "items": self.items(conn=c),
                "connections": self._connections(c),
                "take_meta": meta.get(TAKE_META),
                "take_index_meta": meta.get(TAKE_INDEX_META),
                "take_start_meta": meta.get(TAKE_START_META),
                "take_changed_meta": meta.get(TAKE_CHANGED_META),
            }

        return self._read(build)

    # ---- writer -----------------------------------------------------------

    def set_clock_mode(
        self,
        mode: str,
        now: str | None = None,
        scale: float | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        if mode not in {"mock", "realtime"}:
            raise ValueError("clock mode must be mock or realtime")

        def apply(c):
            current = self._clock(c)
            target = (
                self._parse_time(now) if now else self._parse_time(current["now"])
            )
            target_scale = self._validate_scale(
                current["scale"] if scale is None else scale
            )
            anchor = self._real_now().isoformat(timespec="seconds") if mode == "realtime" else None
            c.execute(
                "UPDATE clock SET now = ?, day = ?, mode = ?, anchor_real = ?, scale = ? "
                "WHERE id = 1",
                (
                    target.isoformat(timespec="seconds"), target.date().isoformat(),
                    mode, anchor, target_scale,
                ),
            )

        self._write(apply, conn)
        if conn is not None:
            return self._read(self._clock, conn)
        return self.clock()

    def add_friend(
        self, character: str, conn: sqlite3.Connection | None = None
    ) -> dict[str, str]:
        def apply(c):
            if not self._character_exists(c, character):
                raise ValueError("unknown character: " + character)
            now = self._now(c)
            c.execute(
                "INSERT OR IGNORE INTO friends(character, since) VALUES (?, ?)",
                (character, now),
            )
            row = c.execute(
                "SELECT character, since FROM friends WHERE character = ?", (character,)
            ).fetchone()
            return dict(row)

        return self._write(apply, conn)

    def _resolve_belief_id(
        self, conn: sqlite3.Connection, source_belief: int | str
    ) -> dict:
        if isinstance(source_belief, str) and not source_belief.strip().isdigit():
            row = conn.execute(
                """SELECT id, proposition_key FROM beliefs
                    WHERE proposition_key = ? AND superseded_by IS NULL
                    ORDER BY id DESC LIMIT 1""",
                (source_belief.strip(),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, proposition_key FROM beliefs WHERE id = ?",
                (int(source_belief),),
            ).fetchone()
        if not row:
            raise ValueError("unknown source belief: " + str(source_belief))
        return dict(row)

    def set_outfit(
        self,
        character: str,
        outfit_id: str,
        reason: str = "",
        source_belief_id: int | str | None = None,
        label: str | None = None,
        art: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        def apply(c):
            canonical = self._canonical_actor(c, character)
            if canonical == "user":
                raise ValueError("outfits belong to a character, not the user")
            scenario = self._current_scenario(c) or {}
            declared = (scenario.get("outfits") or {}).get(canonical)
            if not isinstance(declared, dict) or declared.get("id") != outfit_id:
                raise ValueError(
                    f"outfit {outfit_id!r} is not declared for {canonical}"
                )
            belief = None
            if source_belief_id is not None:
                belief = self._resolve_belief_id(c, source_belief_id)
            final_label = label or declared.get("label") or outfit_id
            final_art = art if art is not None else declared.get("art", "")
            final_reason = reason if reason else declared.get("reason", "")
            changed_at = self._now(c)
            c.execute(
                """INSERT INTO outfits(character, outfit_id, label, art, reason,
                                       source_belief_id, changed_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(character) DO UPDATE SET
                     outfit_id = excluded.outfit_id,
                     label = excluded.label,
                     art = excluded.art,
                     reason = excluded.reason,
                     source_belief_id = excluded.source_belief_id,
                     changed_at = excluded.changed_at""",
                (
                    canonical, outfit_id, final_label, final_art, final_reason,
                    belief["id"] if belief else None, changed_at,
                ),
            )
            row = c.execute(
                """SELECT o.*, b.proposition_key AS source_belief_key
                     FROM outfits o
                     LEFT JOIN beliefs b ON b.id = o.source_belief_id
                    WHERE o.character = ?""",
                (canonical,),
            ).fetchone()
            metadata = {
                "character": canonical,
                "outfit_id": outfit_id,
                "label": final_label,
                "art": final_art,
                "reason": final_reason,
                "source_belief_id": belief["id"] if belief else None,
                "source_belief_key": belief["proposition_key"] if belief else None,
            }
            suffix = f" ({final_reason})" if final_reason else ""
            c.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility,
                                      created_at, metadata_json)
                   VALUES ('outfit_change', ?, ?, 'public', ?, ?)""",
                (
                    f"{canonical.title()} changed into {final_label}{suffix}",
                    json.dumps([canonical]),
                    changed_at,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            return dict(row)

        return self._write(apply, conn)

    def give_item(
        self,
        item_id: str,
        to: str,
        label: str | None = None,
        owner: str | None = None,
        status: str = "carried",
        conn: sqlite3.Connection | None = None,
        *,
        actor: str | None = None,
    ) -> dict:
        item_id = (item_id or "").strip()
        if not item_id:
            raise ValueError("item id is required")

        def apply(c):
            target = self._canonical_actor(c, to)
            if target == "director":
                raise ValueError("the director cannot hold an item")
            final_owner = owner
            if final_owner is not None:
                final_owner = self._canonical_actor(c, final_owner)
                if final_owner == "director":
                    raise ValueError("the director cannot own an item")
            now = self._now(c)
            row = c.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is not None and actor is not None:
                # Authorization belongs here, not in the prompt or the caller.
                # ``None`` marks a trusted in-process caller (takes, seeds); the
                # MCP edge always passes the authenticated actor.
                who = self._canonical_actor(c, actor)
                if who != "director" and who != row["holder"]:
                    raise PermissionError(
                        f"{who} does not hold {item_id!r}; only the holder or the "
                        "director can give it"
                    )
            if row is None:
                if not label:
                    raise ValueError("unknown item: " + item_id)
                final_owner = final_owner or target
                c.execute(
                    """INSERT INTO items(id, label, holder, owner, status, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (item_id, label, target, final_owner, status, now),
                )
            else:
                final_owner = final_owner if final_owner is not None else row["owner"]
                c.execute(
                    "UPDATE items SET holder = ?, owner = ?, status = ? WHERE id = ?",
                    (target, final_owner, status, item_id),
                )
            item = dict(
                c.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            )
            verb = "took" if target == "user" else "gave"
            suffix = "" if target == "user" else f" to {target.title()}"
            c.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility,
                                      created_at, metadata_json)
                   VALUES ('item_given', ?, ?, 'public', ?, ?)""",
                (
                    f"You {verb} {item['label']}{suffix}.",
                    json.dumps([target]),
                    now,
                    json.dumps(
                        {
                            "item_id": item["id"], "label": item["label"],
                            "holder": item["holder"], "owner": item["owner"],
                            "status": item["status"],
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            return item

        return self._write(apply, conn)

    def remember(
        self,
        actor: str,
        proposition: str,
        source: str,
        confidence: float = 0.8,
        visibility: str = "private",
        proposition_key: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        if actor == "director":
            raise ValueError("the director records events, not beliefs")
        if not proposition or not proposition.strip():
            raise ValueError("proposition is required")
        if visibility not in VISIBILITIES:
            raise ValueError("visibility must be one of " + ", ".join(VISIBILITIES))
        confidence = clamp(confidence)

        def apply(c):
            if not self._character_exists(c, actor):
                raise ValueError("unknown character: " + actor)
            now = self._now(c)
            kind, sid = self._parse_source(c, actor, source, now)
            key = (proposition_key or slugify(proposition)).strip()
            cur = c.execute(
                """INSERT INTO beliefs(holder, proposition, proposition_key, source_kind,
                                       source_id, confidence, learned_at, visibility)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (actor, proposition.strip(), key, kind, sid, confidence, now, visibility),
            )
            belief_id = cur.lastrowid
            if kind == "character" and sid != actor:
                updated = c.execute(
                    """UPDATE relationships
                          SET shared_secret_count = shared_secret_count + 1, last_interaction = ?
                        WHERE a = ? AND b = ?""",
                    (now, actor, sid),
                ).rowcount
                if not updated:
                    c.execute(
                        """INSERT INTO relationships(a, b, trust, closeness, tension,
                                                     shared_secret_count, last_interaction)
                           VALUES (?,?,?,?,?,?,?)""",
                        (actor, sid, 0.5, 0.5, 0.0, 1, now),
                    )
            return self._belief(c, int(belief_id))

        return self._write(apply, conn)

    def mark_absent(
        self, character: str, reason: str = "", conn: sqlite3.Connection | None = None
    ) -> dict:
        def apply(c):
            if not self._character_exists(c, character):
                raise ValueError("unknown character: " + character)
            value = (reason or "out of scene").strip() or "out of scene"
            c.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (ABSENT_PREFIX + character, value),
            )
            return {"character": character, "absent": True, "reason": value}

        return self._write(apply, conn)

    def mark_present(
        self, character: str, conn: sqlite3.Connection | None = None
    ) -> dict:
        def apply(c):
            if not self._character_exists(c, character):
                raise ValueError("unknown character: " + character)
            c.execute(
                "DELETE FROM meta WHERE key = ?", (ABSENT_PREFIX + character,)
            )
            return {"character": character, "absent": False, "reason": ""}

        return self._write(apply, conn)

    def update_relationship(
        self,
        actor: str,
        other: str,
        trust_delta: float = 0.0,
        closeness_delta: float = 0.0,
        tension_delta: float = 0.0,
        reason: str = "",
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        if actor == "director":
            raise ValueError("the director does not have relationships")

        def apply(c):
            if not self._character_exists(c, actor):
                raise ValueError("unknown character: " + actor)
            canonical = self._canonical_actor(c, other)
            if canonical == actor:
                raise ValueError("a character cannot have a relationship with itself")
            if canonical == "director":
                raise ValueError("the director does not have relationships")
            now = self._now(c)
            row = c.execute(
                "SELECT * FROM relationships WHERE a = ? AND b = ?", (actor, canonical)
            ).fetchone()
            base = dict(row) if row else {
                "trust": 0.5, "closeness": 0.5, "tension": 0.0, "shared_secret_count": 0
            }
            trust = clamp(base["trust"] + float(trust_delta))
            closeness = clamp(base["closeness"] + float(closeness_delta))
            tension = clamp(base["tension"] + float(tension_delta))
            trust, closeness, tension = (
                round(trust, 4), round(closeness, 4), round(tension, 4)
            )
            c.execute(
                """INSERT INTO relationships(a, b, trust, closeness, tension,
                                             shared_secret_count, last_interaction)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(a, b) DO UPDATE SET
                     trust = excluded.trust,
                     closeness = excluded.closeness,
                     tension = excluded.tension,
                     last_interaction = excluded.last_interaction""",
                (
                    actor, canonical, trust, closeness, tension,
                    base["shared_secret_count"], now,
                ),
            )
            summary = (
                f"{actor} → {canonical}: trust {float(trust_delta):+.2f}, "
                f"closeness {float(closeness_delta):+.2f}, "
                f"tension {float(tension_delta):+.2f}"
                + (f" ({reason})" if reason else "")
            )
            cur = c.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility, created_at)
                   VALUES ('relationship_update', ?, ?, 'private', ?)""",
                (summary, json.dumps([actor, canonical]), now),
            )
            return {
                "edge": {
                    "a": actor, "b": canonical, "trust": trust,
                    "closeness": closeness, "tension": tension,
                    "shared_secret_count": base["shared_secret_count"],
                    "last_interaction": now,
                },
                "event_id": cur.lastrowid,
            }

        return self._write(apply, conn)

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
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        if visibility not in VISIBILITIES:
            raise ValueError("visibility must be one of " + ", ".join(VISIBILITIES))
        actor_key = str(actor).strip().lower()
        if (
            actor_key in CHARACTER_ORDER
            and visibility == "public"
            and kind in DIRECTOR_ONLY_PUBLIC_KINDS
        ):
            # Characters own their dialogue/DM/whisper writes; the shared turn
            # machinery (plans, beats, branches, lifecycle lines) is director-only.
            raise PermissionError(
                f"{actor_key} cannot write a public {kind} event; it is director-only"
            )
        supplied = list(participants or [])
        meta = dict(metadata or {})

        def apply(c):
            resolved = [self._canonical_participant(c, p) for p in supplied]
            now = self._now(c)
            cur = c.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility,
                                     created_at, room_id, message_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    kind, summary, json.dumps(resolved), visibility, now,
                    room_id, message_id, json.dumps(meta, ensure_ascii=False),
                ),
            )
            return {
                "id": cur.lastrowid, "kind": kind, "summary": summary,
                "participants": resolved, "visibility": visibility, "created_at": now,
                "room_id": room_id, "message_id": message_id, "metadata": meta,
            }

        return self._write(apply, conn)

    def advance_time(
        self, actor: str, minutes: int, conn: sqlite3.Connection | None = None
    ) -> dict:
        if actor != "director":
            raise PermissionError("only the director advances the world clock")
        minutes = int(minutes)

        def apply(c):
            clock = self._clock(c)
            current = self._parse_time(clock["now"])
            nxt = current + timedelta(minutes=minutes)
            c.execute(
                "UPDATE clock SET now = ?, day = ?, mode = 'mock', anchor_real = NULL WHERE id = 1",
                (nxt.isoformat(timespec="seconds"), nxt.date().isoformat()),
            )
            return {
                "now": nxt.isoformat(timespec="seconds"),
                "day": nxt.date().isoformat(),
                "mode": "mock",
                "scale": clock["scale"],
                "minutes": minutes,
            }

        return self._write(apply, conn)

    def _bump_revision(self, conn: sqlite3.Connection) -> int:
        value = self._revision(conn) + 1
        conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (REVISION_META, str(value)),
        )
        return value

    def set_paused(
        self, paused: bool, conn: sqlite3.Connection | None = None
    ) -> dict:
        def apply(c):
            if paused:
                c.execute(
                    "INSERT INTO meta(key, value) VALUES (?, '1') "
                    "ON CONFLICT(key) DO UPDATE SET value = '1'",
                    (PAUSE_META,),
                )
            else:
                c.execute("DELETE FROM meta WHERE key = ?", (PAUSE_META,))
            revision = self._bump_revision(c)
            return {"paused": bool(paused), "revision": revision}

        return self._write(apply, conn)

    def set_meta(
        self, key: str, value: str, conn: sqlite3.Connection | None = None
    ) -> None:
        def apply(c):
            c.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

        self._write(apply, conn)

    def record_offscreen(
        self,
        character: str | None = None,
        kind: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict:
        templates = {
            "promise": "{name} promised to sort something out before the next meet-up.",
            "rumor": "Word going around: {name} has been unusually quiet about something.",
            "errand": "{name} slipped out to run an errand and will be back later.",
        }
        kinds = tuple(templates)
        present = sorted(CHARACTER_ORDER, key=lambda cid: CHARACTER_ORDER[cid])
        absent = self.absent_characters(conn=conn)

        def choose(c):
            count = c.execute(
                "SELECT COUNT(*) AS n FROM events WHERE kind = 'offscreen'"
            ).fetchone()["n"]
            chosen_character = character
            if chosen_character:
                chosen_character = self._canonical_actor(c, chosen_character)
                if chosen_character in {"user", "director"}:
                    raise ValueError("off-screen beats belong to a character")
            else:
                pool = absent or present
                chosen_character = pool[int(count) % len(pool)]
            chosen_kind = kind or kinds[int(count) % len(kinds)]
            if chosen_kind not in templates:
                raise ValueError(
                    "offscreen kind must be one of " + ", ".join(kinds)
                )
            return chosen_character, chosen_kind

        chosen_character, chosen_kind = self._read(choose, conn)
        summary = templates[chosen_kind].format(name=chosen_character.title())
        return self.record_event(
            "director",
            "offscreen",
            summary,
            participants=[chosen_character],
            visibility="public",
            metadata={
                "offscreen": True,
                "kind": chosen_kind,
                "character": chosen_character,
            },
            conn=conn,
        )

    def store_idempotent(
        self,
        scope: str,
        request_id: str,
        digest: str,
        response: Mapping[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> None:
        if not request_id:
            return
        payload = json.dumps(response, ensure_ascii=False, default=str)

        def apply(c):
            created = self._now(c)
            c.execute(
                "INSERT INTO idempotency(scope, request_id, digest, response_json, "
                "created_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(scope, request_id) DO UPDATE SET "
                "digest = excluded.digest, response_json = excluded.response_json, "
                "created_at = excluded.created_at",
                (scope, request_id, digest, payload, created),
            )
            c.execute(
                "DELETE FROM idempotency WHERE scope = ? AND rowid NOT IN ("
                "  SELECT rowid FROM idempotency WHERE scope = ? "
                "  ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                (scope, scope, IDEMPOTENCY_KEEP),
            )

        self._write(apply, conn)

    # ---- admin ------------------------------------------------------------

    def reset(self) -> None:
        schema.reset(
            self.db_path,
            self.state_dir,
            world_start=self.world_start,
            world_day=self.world_day,
        )

    def apply_scenario(
        self,
        conn: sqlite3.Connection,
        scenario: dict,
        *,
        now_iso: str,
        mode: str,
        scale: float,
        anchor: str | None,
        cast: list[str],
    ) -> None:
        """Write one validated scenario seed into an existing transaction."""
        conn.execute(
            "UPDATE clock SET now = ?, day = ?, mode = ?, anchor_real = ?, scale = ? "
            "WHERE id = 1",
            (now_iso, now_iso[:10], mode, anchor, scale),
        )
        for character in scenario.get("friends") or []:
            conn.execute(
                "INSERT OR IGNORE INTO friends(character, since) VALUES (?, ?)",
                (character, now_iso),
            )
        for character in scenario.get("absent") or []:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (ABSENT_PREFIX + character, "out of scene"),
            )

        for edge in scenario.get("relationships") or []:
            conn.execute(
                """INSERT INTO relationships(a, b, trust, closeness, tension,
                                             shared_secret_count, last_interaction)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(a, b) DO UPDATE SET
                     trust = excluded.trust,
                     closeness = excluded.closeness,
                     tension = excluded.tension,
                     shared_secret_count = excluded.shared_secret_count,
                     last_interaction = excluded.last_interaction""",
                (
                    edge["a"], edge["b"], float(edge["trust"]),
                    float(edge["closeness"]), float(edge["tension"]),
                    int(edge.get("shared_secret_count", 0)), now_iso,
                ),
            )

        for belief in scenario.get("beliefs") or []:
            holder = belief["holder"]
            key = belief.get("key") or belief.get("proposition_key")
            kind, source_id = self._scenario_source(conn, holder, belief["source"])
            confidence = float(belief.get("confidence", 0.8))
            visibility = belief.get("visibility", "private")
            existing = conn.execute(
                """SELECT id FROM beliefs
                    WHERE holder = ? AND proposition_key = ?
                    ORDER BY id DESC LIMIT 1""",
                (holder, key),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE beliefs
                          SET proposition = ?, source_kind = ?, source_id = ?,
                              confidence = ?, learned_at = ?, visibility = ?,
                              superseded_by = NULL
                        WHERE id = ?""",
                    (
                        belief["proposition"], kind, source_id, confidence,
                        now_iso, visibility, existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO beliefs(holder, proposition, proposition_key,
                                           source_kind, source_id, confidence,
                                           learned_at, visibility)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        holder, belief["proposition"], key, kind, source_id,
                        confidence, now_iso, visibility,
                    ),
                )
            # A belief learned from another character is a secret between the two.
            if kind == "character" and source_id != holder:
                updated = conn.execute(
                    """UPDATE relationships
                          SET shared_secret_count = shared_secret_count + 1,
                              last_interaction = ?
                        WHERE a = ? AND b = ?""",
                    (now_iso, holder, source_id),
                ).rowcount
                if not updated:
                    conn.execute(
                        """INSERT INTO relationships(a, b, trust, closeness, tension,
                                                     shared_secret_count, last_interaction)
                           VALUES (?,?,?,?,?,?,?)""",
                        (holder, source_id, 0.5, 0.5, 0.0, 1, now_iso),
                    )

        # Arm the declared outfits before the loader applies them.
        conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCENARIO_META, json.dumps(scenario, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCENARIO_ID_META, scenario["id"]),
        )

        for spec in _scenario_items(scenario):
            holder = spec.get("holder", "user")
            owner = spec.get("owner", holder)
            conn.execute(
                """INSERT INTO items(id, label, holder, owner, status, created_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     label = excluded.label,
                     holder = excluded.holder,
                     owner = excluded.owner,
                     status = excluded.status,
                     created_at = excluded.created_at""",
                (
                    spec["id"], spec["label"], holder, owner,
                    spec.get("status", "carried"), now_iso,
                ),
            )

        conn.execute(
            """INSERT INTO events(kind, summary, participants_json, visibility,
                                  created_at, metadata_json)
               VALUES ('scenario_load', ?, ?, 'public', ?, ?)""",
            (
                f"Loaded scenario {scenario['id']} — {scenario.get('title', '')}.",
                json.dumps(cast),
                now_iso,
                json.dumps(
                    {
                        "scenario_id": scenario["id"],
                        "cast": cast,
                        "seed": scenario.get("seed"),
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    def _scenario_source(
        self, conn: sqlite3.Connection, holder: str, source: str
    ) -> tuple[str, str]:
        if source == "user":
            return "user", "user"
        if source == "observation":
            return "observation", holder
        kind, source_id = source.split(":", 1)
        row = conn.execute("SELECT 1 FROM characters WHERE id = ?", (source_id,)).fetchone()
        if not row:
            raise ValueError("unknown character in belief source: " + source_id)
        return "character", source_id


# ---- faces ----------------------------------------------------------------


class _Facade:
    """A named view of the store with a fixed method surface."""

    def __init__(self, store: WorldStore, methods: frozenset[str]) -> None:
        self._store = store
        self._methods = methods

    def __getattr__(self, name: str):
        if name not in self._methods:
            raise AttributeError(f"{type(self).__name__} has no method {name!r}")
        return getattr(self._store, name)


class _Reader(_Facade):
    METHODS = frozenset(
        {
            "clock",
            "friends",
            "is_friend",
            "character_exists",
            "characters",
            "current_scenario",
            "current_scenario_id",
            "recorded_ending",
            "outfits",
            "items",
            "item",
            "connections",
            "recall",
            "is_absent",
            "absent_characters",
            "relationship",
            "events",
            "event_by_message_id",
            "latest_event",
            "completed_beats",
            "who_knows",
            "phone_history",
            "matrix",
            "revision",
            "turn",
            "paused",
            "get_meta",
            "get_metas",
            "has_change_event_after",
            "idempotent_replay",
            "snapshot",
        }
    )

    def __init__(self, store: WorldStore) -> None:
        super().__init__(store, self.METHODS)


class _Writer(_Facade):
    METHODS = frozenset(
        {
            "set_clock_mode",
            "add_friend",
            "set_outfit",
            "give_item",
            "remember",
            "mark_absent",
            "mark_present",
            "update_relationship",
            "record_event",
            "advance_time",
            "set_paused",
            "set_meta",
            "record_offscreen",
            "store_idempotent",
        }
    )

    def __init__(self, store: WorldStore) -> None:
        super().__init__(store, self.METHODS)


class _Admin(_Facade):
    METHODS = frozenset({"reset", "apply_scenario"})

    def __init__(self, store: WorldStore) -> None:
        super().__init__(store, self.METHODS)


def _ambient_settings():
    """Resolve defaults lazily so importing this module has no environment access."""
    import os

    from switch_world.config import load_settings

    return load_settings(os.environ)


def _scenario_items(scenario: dict) -> list[dict]:
    """Both the singular ``item`` chip and an optional ``items`` list."""
    candidates: list[Any] = []
    if scenario.get("item") is not None:
        candidates.append(scenario["item"])
    candidates.extend(scenario.get("items") or [])
    out: list[dict] = []
    seen: set[str] = set()
    for spec in candidates:
        if not isinstance(spec, dict):
            continue
        item_id = spec.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            continue
        seen.add(item_id)
        out.append(spec)
    return out
