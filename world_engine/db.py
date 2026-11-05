"""SQLite schema, seeding and reset.

One file, one writer at a time. WAL so the dashboard can read while a tool writes.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    goals TEXT NOT NULL DEFAULT '',
    voice TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS beliefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    holder TEXT NOT NULL REFERENCES characters(id),
    proposition TEXT NOT NULL,
    proposition_key TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('user','character','event','observation')),
    source_id TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    learned_at TEXT NOT NULL,
    visibility TEXT NOT NULL CHECK (visibility IN ('private','shared','public')),
    superseded_by INTEGER REFERENCES beliefs(id)
);
CREATE INDEX IF NOT EXISTS beliefs_key ON beliefs(proposition_key);
CREATE INDEX IF NOT EXISTS beliefs_holder ON beliefs(holder);

CREATE TABLE IF NOT EXISTS relationships (
    a TEXT NOT NULL REFERENCES characters(id),
    b TEXT NOT NULL,
    trust REAL NOT NULL DEFAULT 0.5,
    closeness REAL NOT NULL DEFAULT 0.5,
    tension REAL NOT NULL DEFAULT 0.0,
    shared_secret_count INTEGER NOT NULL DEFAULT 0,
    last_interaction TEXT NOT NULL,
    PRIMARY KEY (a, b)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    participants_json TEXT NOT NULL DEFAULT '[]',
    visibility TEXT NOT NULL DEFAULT 'public',
    created_at TEXT NOT NULL,
    room_id TEXT,
    message_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    supersedes INTEGER REFERENCES events(id)
);
CREATE INDEX IF NOT EXISTS events_created ON events(created_at);

CREATE TABLE IF NOT EXISTS beats (
    id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    ord INTEGER NOT NULL,
    kind TEXT NOT NULL,
    participants_json TEXT NOT NULL DEFAULT '[]',
    room_id TEXT,
    state TEXT NOT NULL DEFAULT 'pending',
    started_at TEXT,
    finished_at TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS clock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    now TEXT NOT NULL,
    day TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'mock',
    anchor_real TEXT,
    scale REAL NOT NULL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS friends (
    character TEXT PRIMARY KEY REFERENCES characters(id),
    since TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outfits (
    character TEXT PRIMARY KEY REFERENCES characters(id),
    outfit_id TEXT NOT NULL,
    label TEXT NOT NULL,
    art TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    source_belief_id INTEGER REFERENCES beliefs(id),
    changed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    holder TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'carried',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path | str, state_dir: Path = config.STATE_DIR) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', '4') "
            "ON CONFLICT(key) DO UPDATE SET value = '4'"
        )
        conn.execute(
            "INSERT OR IGNORE INTO clock(id, now, day) VALUES (1, ?, ?)",
            (config.WORLD_START, config.WORLD_DAY),
        )
        seeded = conn.execute("SELECT value FROM meta WHERE key='seeded'").fetchone()
        if not seeded:
            _seed(conn, state_dir)
            conn.execute("INSERT INTO meta(key, value) VALUES ('seeded', '1')")
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that older demo databases predate. Safe to run every boot."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(clock)")}
    if "mode" not in columns:
        conn.execute("ALTER TABLE clock ADD COLUMN mode TEXT NOT NULL DEFAULT 'mock'")
    if "anchor_real" not in columns:
        conn.execute("ALTER TABLE clock ADD COLUMN anchor_real TEXT")
    # Scenario protocol: realtime can run at a faster-than-wall-clock scale.
    if "scale" not in columns:
        conn.execute("ALTER TABLE clock ADD COLUMN scale REAL NOT NULL DEFAULT 1.0")

    # Scene protocol: every beat may carry a JSON metadata blob (mode, role, turn_id).
    event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
    if "metadata_json" not in event_columns:
        conn.execute(
            "ALTER TABLE events ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
        )


def _seed(conn: sqlite3.Connection, state_dir: Path) -> None:
    characters = json.loads((state_dir / "characters.json").read_text())
    for c in characters["characters"]:
        conn.execute(
            "INSERT OR IGNORE INTO characters(id, name, role, goals, voice) VALUES (?,?,?,?,?)",
            (c["id"], c["name"], c.get("role", ""), c.get("goals", ""), c.get("voice", "")),
        )

    beliefs = json.loads((state_dir / "beliefs.json").read_text())
    for b in beliefs["beliefs"]:
        conn.execute(
            """INSERT INTO beliefs(holder, proposition, proposition_key, source_kind,
                                   source_id, confidence, learned_at, visibility, superseded_by)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                b["holder"], b["proposition"], b["proposition_key"],
                b["source_kind"], b["source_id"], float(b["confidence"]),
                b["learned_at"], b["visibility"], b.get("superseded_by"),
            ),
        )

    relationships = json.loads((state_dir / "relationships.json").read_text())
    for e in relationships["edges"]:
        conn.execute(
            """INSERT OR IGNORE INTO relationships
               (a, b, trust, closeness, tension, shared_secret_count, last_interaction)
               VALUES (?,?,?,?,?,?,?)""",
            (
                e["from"], e["to"], float(e["trust"]), float(e["closeness"]),
                float(e["tension"]), int(e.get("shared_secret_count", 0)),
                e["last_interaction"],
            ),
        )

    conn.execute(
        "INSERT INTO events(kind, summary, participants_json, visibility, created_at) VALUES (?,?,?,?,?)",
        (
            "world_start",
            "A Tuesday in late autumn. The group has not met yet.",
            json.dumps(["alice", "emily", "sophia", "mia"]),
            "public",
            config.WORLD_START,
        ),
    )


def reset(db_path: Path | str, state_dir: Path = config.STATE_DIR) -> None:
    path = Path(db_path)
    for p in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    init_db(path, state_dir)
