"""The world state: beliefs, provenance, relationships, events and the scene card.

This module is deliberately framework-free. The MCP tools and the REST API are thin
adapters over it, which is what keeps the dashboard/director and the agents consistent.
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

from . import config, db

VISIBILITIES = ("private", "shared", "public")
SOURCE_KINDS = ("user", "character", "event", "observation")
CHARACTER_ORDER = {"alice": 0, "emily": 1, "sophia": 2, "mia": 3}
CONNECTION_LABELS = ("close", "steady", "strained", "rival", "distant")

SCENARIO_META = "scenario"
SCENARIO_ID_META = "scenario_id"

LABELS = {
    "user-leaving-city": "The user is leaving the city",
    "bookshop-lease": "Alice's bookshop lease is not being renewed",
    "bookshop-trouble": "Alice's bookshop is in trouble",
    "alice-hiding-shop": "Alice is hiding something about the shop",
    "emily-distracted": "Emily has seemed distracted",
    "emily-new-job": "Emily applied for a job in another city",
    "emily-leaving": "Emily is planning to leave",
    "emily-change": "Emily is about to make a big change",
    "sophia-book": "Sophia is writing a book",
    "sophia-watching": "Sophia is watching the group closely",
    "alice-money": "Alice is worried about money",
    "truck-debt": "Mia's truck is in debt",
    "tuesday-cafe": "The group meets at the café on Tuesdays at 18:30",
}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "proposition"


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1]


class WorldService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        tokens: Mapping[str, str] | None = None,
        state_dir: Path | str | None = None,
    ):
        self.db_path = Path(db_path or config.DB_PATH)
        self.state_dir = Path(state_dir or config.STATE_DIR)
        self.tokens = dict(tokens or config.token_map())
        db.init_db(self.db_path, self.state_dir)

    # ---- plumbing ---------------------------------------------------------

    @contextmanager
    def _conn(self):
        conn = db.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def actor_for_token(self, token: str) -> str:
        actor = self.tokens.get(token)
        if not actor:
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

    @classmethod
    def _clock_from_row(cls, row: sqlite3.Row) -> dict[str, Any]:
        """Resolve the story clock. In `realtime` the stored `now` is an anchor and the
        story advances from the real time recorded in `anchor_real`, multiplied by
        `scale` (1.0 is wall-clock speed; 60.0 is one story hour per real minute)."""
        now = cls._parse_time(row["now"])
        mode = row["mode"] or "mock"
        scale = float(row["scale"] or 1.0) if "scale" in row.keys() else 1.0
        if mode == "realtime" and row["anchor_real"]:
            anchor = cls._parse_time(row["anchor_real"])
            elapsed = (cls._real_now() - anchor).total_seconds() * scale
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
        return self._clock_from_row(row)

    def _now(self, conn: sqlite3.Connection) -> str:
        return self._clock(conn)["now"]

    def _character_exists(self, conn: sqlite3.Connection, cid: str) -> bool:
        return conn.execute("SELECT 1 FROM characters WHERE id = ?", (cid,)).fetchone() is not None

    def _canonical_actor(self, conn: sqlite3.Connection, value: str) -> str:
        """Resolve an id, a display name, a first name, or 'you' to a canonical actor.

        Agents write relationship calls in prose. Before this, `other="Emily"` created a
        second row next to `other="emily"`; the two histories then diverged and the
        dashboard showed two Emilys. Normalising at the boundary keeps one edge per pair.
        """
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

    def clock(self) -> dict[str, Any]:
        with self._conn() as conn:
            return self._clock(conn)

    def set_clock_mode(
        self,
        mode: str,
        now: str | None = None,
        scale: float | None = None,
    ) -> dict[str, Any]:
        """Switch between the mock time machine and a real-time clock.

        `now` is the alignment point used when entering realtime: the story jumps to the
        next authored beat and then runs with the wall clock from that anchor. `scale`
        multiplies the real-time delta (60 means one story hour per real minute); it is
        kept across a mock<->realtime switch unless explicitly changed.
        """
        if mode not in {"mock", "realtime"}:
            raise ValueError("clock mode must be mock or realtime")
        with self._conn() as conn:
            current = self._clock(conn)
            target = (
                self._parse_time(now) if now
                else self._parse_time(current["now"])
            )
            target_scale = self._validate_scale(current["scale"] if scale is None else scale)
            anchor = self._real_now().isoformat(timespec="seconds") if mode == "realtime" else None
            conn.execute(
                "UPDATE clock SET now = ?, day = ?, mode = ?, anchor_real = ?, scale = ? "
                "WHERE id = 1",
                (
                    target.isoformat(timespec="seconds"), target.date().isoformat(),
                    mode, anchor, target_scale,
                ),
            )
        return self.clock()

    @staticmethod
    def _validate_scale(value: Any) -> float:
        try:
            scale = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("clock scale must be a number greater than zero") from exc
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("clock scale must be a number greater than zero")
        return scale

    # ---- friends (phone gating) ------------------------------------------

    def friends(self) -> list[dict[str, str]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT character, since FROM friends ORDER BY since, character"
            ).fetchall()
            return [dict(r) for r in rows]

    def is_friend(self, character: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM friends WHERE character = ?", (character,)
            ).fetchone()
            return row is not None

    def add_friend(self, character: str) -> dict[str, str]:
        with self._conn() as conn:
            if not self._character_exists(conn, character):
                raise ValueError("unknown character: " + character)
            now = self._now(conn)
            conn.execute(
                "INSERT OR IGNORE INTO friends(character, since) VALUES (?, ?)",
                (character, now),
            )
            row = conn.execute(
                "SELECT character, since FROM friends WHERE character = ?", (character,)
            ).fetchone()
        return dict(row)

    def character_exists(self, character: str) -> bool:
        with self._conn() as conn:
            return self._character_exists(conn, character)

    def characters(self) -> list[dict]:
        with self._conn() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM characters")]
            return sorted(rows, key=lambda c: CHARACTER_ORDER.get(c["id"], 99))

    # ---- scenarios (loadable demo worlds) --------------------------------

    def current_scenario(self) -> dict | None:
        """The scenario that seeded the current database, or None for the base seed."""
        with self._conn() as conn:
            return self._current_scenario(conn)

    def current_scenario_id(self) -> str | None:
        with self._conn() as conn:
            return self._scenario_id(conn)

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

    def recorded_ending(self, scenario_id: str | None = None) -> dict | None:
        """The ending event already recorded for this scenario, if any.

        One scenario can only end once; this is what makes `/api/endings/evaluate`
        idempotent inside a run. A reset or a new scenario load removes the event.
        """
        scenario_id = scenario_id or self.current_scenario_id()
        if not scenario_id:
            return None
        for event in reversed(self.events("ending")):
            if event.get("metadata", {}).get("scenario_id") == scenario_id:
                return event
        return None

    # ---- outfits ----------------------------------------------------------

    def outfits(self) -> dict[str, dict]:
        """Current outfit per character, keyed by character id."""
        with self._conn() as conn:
            rows = [
                dict(r) for r in conn.execute(
                    """SELECT o.*, b.proposition_key AS source_belief_key
                         FROM outfits o
                         LEFT JOIN beliefs b ON b.id = o.source_belief_id"""
                )
            ]
        rows.sort(key=lambda row: CHARACTER_ORDER.get(row["character"], 99))
        return {row["character"]: row for row in rows}

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
    ) -> dict:
        """Put a declared scenario outfit on a character, with its memory source.

        The scenario declares which outfits exist (id, label, art, default reason).
        A runtime change must name one of those ids, and a source belief must already
        exist. The item is a memory -> outfit chain, not a free-text costume.
        """
        with self._conn() as conn:
            character = self._canonical_actor(conn, character)
            if character == "user":
                raise ValueError("outfits belong to a character, not the user")
            scenario = self._current_scenario(conn) or {}
            declared = (scenario.get("outfits") or {}).get(character)
            if not isinstance(declared, dict) or declared.get("id") != outfit_id:
                raise ValueError(
                    f"outfit {outfit_id!r} is not declared for {character}"
                )
            belief = None
            if source_belief_id is not None:
                belief = self._resolve_belief_id(conn, source_belief_id)
            label = label or declared.get("label") or outfit_id
            art = art if art is not None else declared.get("art", "")
            reason = reason if reason else declared.get("reason", "")
            changed_at = self._now(conn)
            conn.execute(
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
                    character, outfit_id, label, art, reason,
                    belief["id"] if belief else None, changed_at,
                ),
            )
            row = conn.execute(
                """SELECT o.*, b.proposition_key AS source_belief_key
                     FROM outfits o
                     LEFT JOIN beliefs b ON b.id = o.source_belief_id
                    WHERE o.character = ?""",
                (character,),
            ).fetchone()
            metadata = {
                "character": character,
                "outfit_id": outfit_id,
                "label": label,
                "art": art,
                "reason": reason,
                "source_belief_id": belief["id"] if belief else None,
                "source_belief_key": belief["proposition_key"] if belief else None,
            }
            suffix = f" ({reason})" if reason else ""
            conn.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility,
                                      created_at, metadata_json)
                   VALUES ('outfit_change', ?, ?, 'public', ?, ?)""",
                (
                    f"{character.title()} changed into {label}{suffix}",
                    json.dumps([character]),
                    changed_at,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            return dict(row)

    # ---- items ------------------------------------------------------------

    def items(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM items ORDER BY created_at, id"
            ).fetchall()
        return [dict(r) for r in rows]

    def item(self, item_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def give_item(
        self,
        item_id: str,
        to: str,
        label: str | None = None,
        owner: str | None = None,
        status: str = "carried",
    ) -> dict:
        """Move (or create) one item and record the hand-off. No inventory economy."""
        item_id = (item_id or "").strip()
        if not item_id:
            raise ValueError("item id is required")
        with self._conn() as conn:
            to = self._canonical_actor(conn, to)
            if to == "director":
                raise ValueError("the director cannot hold an item")
            if owner is not None:
                owner = self._canonical_actor(conn, owner)
                if owner == "director":
                    raise ValueError("the director cannot own an item")
            now = self._now(conn)
            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                if not label:
                    raise ValueError("unknown item: " + item_id)
                owner = owner or to
                conn.execute(
                    """INSERT INTO items(id, label, holder, owner, status, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (item_id, label, to, owner, status, now),
                )
            else:
                owner = owner if owner is not None else row["owner"]
                conn.execute(
                    "UPDATE items SET holder = ?, owner = ?, status = ? WHERE id = ?",
                    (to, owner, status, item_id),
                )
            item = dict(
                conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            )
            verb = "took" if to == "user" else "gave"
            target = "" if to == "user" else f" to {to.title()}"
            conn.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility,
                                      created_at, metadata_json)
                   VALUES ('item_given', ?, ?, 'public', ?, ?)""",
                (
                    f"You {verb} {item['label']}{target}.",
                    json.dumps([to]),
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

    # ---- connections ------------------------------------------------------

    @staticmethod
    def _connection_label(affinity: float, tension: float) -> str:
        if tension > 0.55:
            return "rival"
        if affinity >= 0.70:
            return "close"
        if affinity >= 0.42:
            return "steady"
        if affinity >= 0.24:
            return "strained"
        return "distant"

    def connections(self) -> list[dict]:
        """Unordered character↔character pairs with one affinity/tension projection.

        Relationships are directed (alice→emily is not emily→alice), but the World
        Tree paints an edge, not two arrows. Scores average the available directions;
        a shared secret is counted once per pair.
        """
        characters = sorted(CHARACTER_ORDER, key=lambda cid: CHARACTER_ORDER[cid])
        with self._conn() as conn:
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
                        "affinity": round(_clamp(affinity), 4),
                        "tension": round(_clamp(tension), 4),
                        "label": self._connection_label(affinity, tension),
                        "shared_secret_count": shared,
                    }
                )
        return out

    # ---- beliefs ----------------------------------------------------------

    def _parse_source(self, conn: sqlite3.Connection, actor: str, source: str, now: str) -> tuple[str, str]:
        source = (source or "").strip()
        if source == "user":
            return "user", "user"
        if source == "observation":
            return "observation", actor
        if ":" in source:
            kind, sid = source.split(":", 1)
            if kind not in SOURCE_KINDS:
                raise ValueError("source must be user, observation, character:<id> or event:<id>")
            if kind == "character" and not self._character_exists(conn, sid):
                raise ValueError("unknown character in source: " + sid)
            if kind == "event":
                row = conn.execute("SELECT 1 FROM events WHERE id = ?", (int(sid),)).fetchone()
                if not row:
                    raise ValueError("unknown event in source: " + sid)
            return kind, sid
        raise ValueError("source must be user, observation, character:<id> or event:<id>")

    def remember(
        self,
        actor: str,
        proposition: str,
        source: str,
        confidence: float = 0.8,
        visibility: str = "private",
        proposition_key: str | None = None,
    ) -> dict:
        if actor == "director":
            raise ValueError("the director records events, not beliefs")
        if not proposition or not proposition.strip():
            raise ValueError("proposition is required")
        if visibility not in VISIBILITIES:
            raise ValueError("visibility must be one of " + ", ".join(VISIBILITIES))
        confidence = _clamp(confidence)

        with self._conn() as conn:
            if not self._character_exists(conn, actor):
                raise ValueError("unknown character: " + actor)
            kind, sid = self._parse_source(conn, actor, source, self._now(conn))
            now = self._now(conn)
            key = (proposition_key or slugify(proposition)).strip()
            cur = conn.execute(
                """INSERT INTO beliefs(holder, proposition, proposition_key, source_kind,
                                       source_id, confidence, learned_at, visibility)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (actor, proposition.strip(), key, kind, sid, confidence, now, visibility),
            )
            belief_id = cur.lastrowid
            if kind == "character" and sid != actor:
                updated = conn.execute(
                    """UPDATE relationships
                          SET shared_secret_count = shared_secret_count + 1, last_interaction = ?
                        WHERE a = ? AND b = ?""",
                    (now, actor, sid),
                ).rowcount
                if not updated:
                    conn.execute(
                        """INSERT INTO relationships(a, b, trust, closeness, tension,
                                                     shared_secret_count, last_interaction)
                           VALUES (?,?,?,?,?,?,?)""",
                        (actor, sid, 0.5, 0.5, 0.0, 1, now),
                    )
            return self._belief(conn, int(belief_id))

    def _belief(self, conn: sqlite3.Connection, belief_id: int) -> dict:
        row = conn.execute(
            """SELECT b.*, c.name AS holder_name
                 FROM beliefs b JOIN characters c ON c.id = b.holder
                WHERE b.id = ?""",
            (belief_id,),
        ).fetchone()
        return dict(row) if row else {}

    def recall(self, actor: str, query: str = "", limit: int = 8) -> dict:
        """The actor's own beliefs plus public facts from the others."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT b.*, c.name AS holder_name
                     FROM beliefs b JOIN characters c ON c.id = b.holder
                    WHERE b.superseded_by IS NULL
                      AND (b.holder = ? OR b.visibility = 'public')
                    ORDER BY b.id""",
                (actor,),
            ).fetchall()

        now = self._parse_time(self.clock()["now"])
        q = _tokens(query)
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

    # ---- presence ---------------------------------------------------------
    ABSENT_PREFIX = "absent:"

    def mark_absent(self, character: str, reason: str = "") -> dict:
        """Take a character out of the scene until it ends or `reset` clears presence.

        Presence lives in the generic `meta` table, so a reset (which recreates the
        database) restores the whole cast without a separate migration.
        """
        with self._conn() as conn:
            if not self._character_exists(conn, character):
                raise ValueError("unknown character: " + character)
            value = (reason or "out of scene").strip() or "out of scene"
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (self.ABSENT_PREFIX + character, value),
            )
        return {"character": character, "absent": True, "reason": value}

    def is_absent(self, character: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM meta WHERE key = ?", (self.ABSENT_PREFIX + character,)
            ).fetchone()
            return row is not None

    def absent_characters(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key FROM meta WHERE key LIKE ?", (self.ABSENT_PREFIX + "%",)
            ).fetchall()
        ids = {str(row["key"]).split(":", 1)[1] for row in rows}
        return sorted(
            (cid for cid in ids if cid in CHARACTER_ORDER),
            key=lambda cid: CHARACTER_ORDER[cid],
        )

    # ---- relationships ----------------------------------------------------

    def relationship(self, actor: str, other: str) -> dict:
        with self._conn() as conn:
            other = self._canonical_actor(conn, other)
            row = conn.execute(
                "SELECT * FROM relationships WHERE a = ? AND b = ?", (actor, other)
            ).fetchone()
            if not row:
                return {
                    "a": actor, "b": other, "trust": 0.5,
                    "closeness": 0.5, "tension": 0.0,
                    "shared_secret_count": 0, "last_interaction": self._now(conn),
                    "exists": False,
                }
            item = dict(row)
            item["exists"] = True
            return item

    def update_relationship(
        self,
        actor: str,
        other: str,
        trust_delta: float = 0.0,
        closeness_delta: float = 0.0,
        tension_delta: float = 0.0,
        reason: str = "",
    ) -> dict:
        if actor == "director":
            raise ValueError("the director does not have relationships")
        with self._conn() as conn:
            if not self._character_exists(conn, actor):
                raise ValueError("unknown character: " + actor)
            other = self._canonical_actor(conn, other)
            if other == actor:
                raise ValueError("a character cannot have a relationship with itself")
            if other == "director":
                raise ValueError("the director does not have relationships")
            now = self._now(conn)
            row = conn.execute(
                "SELECT * FROM relationships WHERE a = ? AND b = ?", (actor, other)
            ).fetchone()
            base = dict(row) if row else {
                "trust": 0.5, "closeness": 0.5, "tension": 0.0, "shared_secret_count": 0
            }
            trust = _clamp(base["trust"] + float(trust_delta))
            closeness = _clamp(base["closeness"] + float(closeness_delta))
            tension = _clamp(base["tension"] + float(tension_delta))
            trust, closeness, tension = round(trust, 4), round(closeness, 4), round(tension, 4)
            conn.execute(
                """INSERT INTO relationships(a, b, trust, closeness, tension,
                                             shared_secret_count, last_interaction)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(a, b) DO UPDATE SET
                     trust = excluded.trust,
                     closeness = excluded.closeness,
                     tension = excluded.tension,
                     last_interaction = excluded.last_interaction""",
                (actor, other, trust, closeness, tension, base["shared_secret_count"], now),
            )
            summary = (
                f"{actor} → {other}: trust {float(trust_delta):+.2f}, "
                f"closeness {float(closeness_delta):+.2f}, "
                f"tension {float(tension_delta):+.2f}"
                + (f" ({reason})" if reason else "")
            )
            cur = conn.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility, created_at)
                   VALUES ('relationship_update', ?, ?, 'private', ?)""",
                (summary, json.dumps([actor, other]), now),
            )
            return {
                "edge": {
                    "a": actor, "b": other, "trust": trust, "closeness": closeness,
                    "tension": tension, "shared_secret_count": base["shared_secret_count"],
                    "last_interaction": now,
                },
                "event_id": cur.lastrowid,
            }

    # ---- events -----------------------------------------------------------

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict:
        """One event row in API shape: participants and metadata are decoded."""
        event = dict(row)
        event["participants"] = json.loads(event.pop("participants_json", None) or "[]")
        raw = event.pop("metadata_json", None)
        try:
            event["metadata"] = json.loads(raw or "{}")
        except (TypeError, ValueError):
            event["metadata"] = {}
        return event

    def _canonical_participant(self, conn: sqlite3.Connection, value: str) -> str:
        """Normalise a participant when it is a known actor; leave unknown labels alone."""
        try:
            return self._canonical_actor(conn, value)
        except ValueError:
            return str(value).strip()

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
        if visibility not in VISIBILITIES:
            raise ValueError("visibility must be one of " + ", ".join(VISIBILITIES))
        participants = list(participants or [])
        meta = dict(metadata or {})
        with self._conn() as conn:
            participants = [self._canonical_participant(conn, p) for p in participants]
            now = self._now(conn)
            cur = conn.execute(
                """INSERT INTO events(kind, summary, participants_json, visibility,
                                     created_at, room_id, message_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    kind, summary, json.dumps(participants), visibility, now,
                    room_id, message_id, json.dumps(meta, ensure_ascii=False),
                ),
            )
            return {
                "id": cur.lastrowid, "kind": kind, "summary": summary,
                "participants": participants, "visibility": visibility, "created_at": now,
                "room_id": room_id, "message_id": message_id, "metadata": meta,
            }

    def events(self, kind: str | None = None) -> list[dict]:
        """Every event, oldest first. The dashboard's `/api/state` only needs the tail,
        but branch and arc checks must not lose an event older than the last 50."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE (? IS NULL OR kind = ?) ORDER BY id",
                (kind, kind),
            ).fetchall()
        return [self._event_dict(row) for row in rows]

    def event_by_message_id(self, message_id: str) -> dict | None:
        if not message_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE message_id = ? ORDER BY id DESC LIMIT 1",
                (message_id,),
            ).fetchone()
        return self._event_dict(row) if row else None

    def latest_event(self, kind: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,)
            ).fetchone()
        return self._event_dict(row) if row else None

    def completed_beats(self) -> list[str]:
        with self._conn() as conn:
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

    def who_knows(self, proposition_key: str) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT b.*, c.name AS holder_name
                     FROM beliefs b JOIN characters c ON c.id = b.holder
                    WHERE b.proposition_key = ? AND b.superseded_by IS NULL
                    ORDER BY b.confidence DESC""",
                (proposition_key,),
            ).fetchall()
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
            "label": LABELS.get(proposition_key, holders[0]["proposition"] if holders else proposition_key),
            "holders": holders,
        }

    # ---- phone history -----------------------------------------------------
    def phone_history(
        self,
        character: str,
        limit: int = 100,
        before_id: int | None = None,
        include_scene: bool = False,
    ) -> dict:
        """Recent DMs for one character, newest last.

        The phone is a private mailbox: public scene lines are deliberately excluded so a
        group conversation never leaks into a one-to-one thread. `include_scene=True` is
        for the DM prompt's context, not for the phone UI.

        The dashboard asks for 100 at a time; `before_id` is the pagination cursor. The
        query walks backwards in batches until it has one more matching message than the
        limit, so `has_more` is honest even when other characters' DMs dominate the log.
        """
        limit = max(1, min(int(limit), 200))
        kind_clause = "kind IN ('dialogue', 'dm')" if include_scene else "kind = 'dm'"
        messages: list[dict] = []
        cursor = before_id
        batch = max(limit * 2, 200)
        while len(messages) <= limit:
            with self._conn() as conn:
                rows = conn.execute(
                    f"""SELECT id, kind, summary, participants_json, created_at
                          FROM events
                         WHERE {kind_clause}
                           AND (? IS NULL OR id < ?)
                         ORDER BY id DESC
                         LIMIT ?""",
                    (cursor, cursor, batch),
                ).fetchall()
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
                    # Group scenes address the room as "You: ..."; the phone must not
                    # paint the user's own line as the selected character's.
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

    # ---- state and projections -------------------------------------------

    def state(self) -> dict:
        with self._conn() as conn:
            characters = [dict(r) for r in conn.execute("SELECT * FROM characters")]
            characters.sort(key=lambda c: CHARACTER_ORDER.get(c["id"], 99))
            beliefs = [
                dict(r) for r in conn.execute(
                    """SELECT b.*, c.name AS holder_name
                         FROM beliefs b JOIN characters c ON c.id = b.holder
                        WHERE b.superseded_by IS NULL ORDER BY b.id"""
                )
            ]
            relationships = [dict(r) for r in conn.execute("SELECT * FROM relationships")]
            events = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT 50"
                )
            ]
            clock = self._clock(conn)
            friends = [
                r["character"] for r in conn.execute(
                    "SELECT character FROM friends ORDER BY since, character"
                )
            ]
            scenario = self._current_scenario(conn)
        events = [self._event_dict(row) for row in events]
        items = self.items()
        item = self._scenario_item(items, scenario)
        cast_art = dict((scenario or {}).get("cast_art") or {})
        scene_art = (scenario or {}).get("scene_art")
        return {
            "clock": clock,
            "characters": characters,
            "beliefs": beliefs,
            "relationships": relationships,
            "events": list(reversed(events)),
            "friends": friends,
            "absent_characters": self.absent_characters(),
            "done_beats": self.completed_beats(),
            "branch": self.latest_event("branch"),
            "matrix": self.matrix(),
            "scenario": scenario,
            "outfits": self.outfits(),
            "items": items,
            "item": item,
            "cast_art": cast_art,
            "scene_art": scene_art,
            "connections": self.connections(),
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
        with self._conn() as conn:
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
        order = ["user-leaving-city", "bookshop-lease", "bookshop-trouble", "alice-hiding-shop",
                 "emily-new-job", "emily-leaving", "emily-change", "emily-distracted",
                 "alice-money", "sophia-book", "sophia-watching", "truck-debt", "tuesday-cafe"]
        return sorted(
            by_key.values(),
            key=lambda row: (order.index(row["key"]) if row["key"] in order else 999, row["key"]),
        )

    def advance_time(self, actor: str, minutes: int) -> dict:
        """Jump the story clock. A deliberate jump leaves realtime and returns to mock."""
        if actor != "director":
            raise PermissionError("only the director advances the world clock")
        minutes = int(minutes)
        with self._conn() as conn:
            clock = self._clock(conn)
            current = self._parse_time(clock["now"])
            nxt = current + timedelta(minutes=minutes)
            conn.execute(
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

        config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = config.EXPORT_DIR / f"scene-card-{stamp}.md"
        path.write_text(text)
        return {"path": str(path), "text": text}

    # ---- dev --------------------------------------------------------------

    def reset(self) -> None:
        db.reset(self.db_path, self.state_dir)

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value)
