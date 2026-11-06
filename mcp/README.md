# World engine (MCP)

The world engine is the source of truth for beliefs, relationships, events and the clock.
It is an MCP server so that each character can read and write its own state through a
scoped token.

## Why MCP

The characters are agents; a tool surface is how they act. The server maps a bearer token
to a character id. Tool arguments never contain a character id, so a character cannot read
another character's private beliefs — even if the prompt is injected or the model is
confused. "Alice knows something Emily does not" is enforced at the API layer.

## Resources

| URI | Visibility | Contents |
| --- | --- | --- |
| `world://characters/<id>` | public | name, role, goals, voice |
| `world://beliefs/<holder>` | holder + director | that holder's beliefs with provenance |
| `world://relationships/<from>/<to>` | `from` + director | directed relationship values |
| `world://events` | public | the immutable event log |

## Tools

| Tool | Caller | Input | Output |
| --- | --- | --- | --- |
| `world__recall` | character | `query: str`, `limit: int = 8` | ranked beliefs + relationship facts the caller may see |
| `world__remember` | character | `proposition: str`, `source: str`, `confidence: float = 0.8`, `visibility: str = "private"`, `proposition_key: str?` | the stored belief id |
| `world__relationship` | character | `other: str` | trust / closeness / tension from the caller's view |
| `world__update_relationship` | character | `other: str`, `trust_delta: float`, `closeness_delta: float`, `tension_delta: float`, `reason: str` | the updated edge and the event id |
| `world__record_event` | director | `kind, summary, participants, visibility` | event id (characters cannot write arbitrary public lines) |
| `world__who_knows` | director | `proposition_key: str` | every holder, source, confidence, timestamp |
| `world__advance_time` | director | `minutes: int` | the new world clock |

`source` is `user`, `character:<id>`, `event:<id>` or `observation`. The server rejects a
source that is not one of these, and rejects `visibility="public"` from a character for a
belief about a third party.

**`proposition_key`** is the matrix row. Alice's "I am leaving the city" and Emily's "Alice
is leaving the city" must share `user-leaving-city`; otherwise the dashboard cannot show
the same proposition at 1.00 and 0.80. Pass it explicitly in the café beat. The server may
slug when it is absent, but the slug is not reliable across paraphrases.

**`world__update_relationship`** writes the calling character's outgoing edge only. Deltas
clamp to `[0, 1]`. It appends an event with the delta and the reason, so the dashboard can
explain *why* the edge moved. When a belief is recorded with `source_kind=character`, the
receiver's `shared_secret_count` for the source increments.

## HTTP API (dashboard + director)

```
GET  /api/characters              cast
GET  /api/beliefs                 all beliefs (dashboard, read-only)
GET  /api/relationships           all edges
GET  /api/events?since=<id>       event feed
GET  /api/who-knows/<key>         provenance matrix
GET  /api/export/scene-card       latest scene card (markdown)
POST /api/director/beat           director state transitions
GET  /health
```

The dashboard polls these read-only endpoints. It never opens SQLite; the world engine is
the only writer and the only process that opens the database file.

## Storage

SQLite, one file at `data/world.sqlite` (gitignored). Tables:

```
characters(id, name, role, goals, voice, status)
beliefs(id, holder, proposition, proposition_key, source_kind, source_id,
        confidence, learned_at, visibility, superseded_by)
relationships(a, b, trust, closeness, tension, last_interaction, shared_secret_count)
events(id, kind, summary, participants_json, visibility, created_at,
       room_id, message_id, supersedes)
beats(id, day, ord, kind, participants_json, room_id, state, started_at, finished_at)
clock(now, day)
```

Migrations are a numbered list applied at startup; the schema version is stored in
`PRAGMA user_version`. The seed loader maps `world/state/relationships.json` `from`/`to` to
`a`/`b`, defaults `shared_secret_count=0` and `superseded_by=null`, and validates that every
belief has a source.

## Implementation notes

- Python 3.11, FastAPI, `mcp` Python SDK (streamable HTTP), no Node build for the dashboard.
- Bind `127.0.0.1:8890` by default; the OpenCode sessions run on the same machine.
- Auth: `Authorization: Bearer <token>`; constant-time compare; token → character map is
  loaded from the environment at startup.
- Every write is one transaction. Beliefs are append-only; a correction writes a new row
  with `superseded_by` set on the old one.
- `/api/*` is read-only except `/api/director/*`, which requires the director token.
- Log every tool call with caller, tool, and a short argument hash — enough to debug the
  demo without storing secrets.

## Not in the MVP

- Vector search. Retrieval is keyword + recency + importance over a small belief table.
- Multi-user auth. One user, four characters, one director.
- Cross-world or multi-session state.
