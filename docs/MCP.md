# World engine (MCP)

The world engine is the source of truth for beliefs, relationships, events and the clock.
It is an MCP server so that each character can read and write its own state through a
scoped token.

The MCP surface is implemented in
[`switch_world/interfaces/mcp/`](../switch_world/interfaces/mcp/) (`server.py` builds the
server, `tools.py` registers the tools).

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

The server advertises exactly fourteen tools. The name, argument order, defaults and
result shape are the public MCP contract (enforced by
`tests/interfaces/test_mcp_tools.py`).

| Tool | Caller | Input | Output |
| --- | --- | --- | --- |
| `world__recall` | character | `query: str`, `limit: int = 8` | ranked beliefs + relationship facts the caller may see |
| `world__search_web` | character | `query: str`, `max_results: int = 5`, `topic: str = "news"` | Tavily results (titles, URLs, snippets, offline flag) |
| `world__remember` | character | `proposition: str`, `source: str`, `confidence: float = 0.8`, `visibility: str = "private"`, `proposition_key: str?` | the stored belief |
| `world__relationship` | character | `other: str` | trust / closeness / tension from the caller's view |
| `world__update_relationship` | character | `other: str`, `trust_delta: float`, `closeness_delta: float`, `tension_delta: float`, `reason: str` | the updated edge and the event id |
| `world__record_event` | director | `kind: str`, `summary: str`, `participants: list[str]?`, `visibility: str = "public"` | event id |
| `world__who_knows` | director | `proposition_key: str` | every holder, source, confidence, timestamp |
| `world__set_outfit` | character | `outfit_id: str`, `reason: str`, `source_belief_id: str?` | the stored outfit |
| `world__give_item` | holder or director | `item_id: str`, `to: str`, `note: str?` | the moved item |
| `world__allowed_looks` | character | — | the outfits this scenario declares for the caller |
| `world__connections` | any | — | the cast↔cast relationship projection |
| `world__items` | any | — | the props/items in the world and who holds them |
| `world__ending_status` | any | — | the active scenario's ending card |
| `world__advance_time` | director | `minutes: int` | the new world clock |

`source` is `user`, `character:<id>`, `event:<id>` or `observation`. The server rejects a
source that is not one of these, and rejects `visibility="public"` from a character for a
belief about a third party.

## Authorization

Authentication stays at the edge: `switch_world/interfaces/mcp/tools.py` resolves the
actor from the bearer token with a constant-time compare. Authorization is enforced in the
store, so every caller — MCP, an in-band agent envelope, or a future adapter — gets the
same answer.

- **A non-holder cannot give an item.** `world__give_item` passes the authenticated actor;
  `WorldStore.give_item` accepts the hand-off only when the actor currently holds the item
  (or is the director).
- **A character cannot write a public turn event.** `world__record_event` is director-only
  at the tool edge, and `WorldStore.record_event` independently rejects a character
  writing a public lifecycle/turn event (`scene_start`, `scene_end`, `turn_plan`, `beat`,
  `branch`, `scenario`, system lines). Characters may still write their own dialogue,
  action, silence, DM and whisper events.
- **Visibility and participant rules are unchanged.** Participant ids are canonicalised,
  private beliefs stay with their holder, and the director keeps the broader view because
  it owns the ending check and the scene card.

**`proposition_key`** is the matrix row. Alice's "I am leaving the city" and Emily's "Alice
is leaving the city" must share `user-leaving-city`; otherwise the dashboard cannot show
the same proposition at 1.00 and 0.80. Pass it explicitly in the café beat. The server may
slug when it is absent, but the slug is not reliable across paraphrases.

**`world__update_relationship`** writes the calling character's outgoing edge only. Deltas
clamp to `[0, 1]`. It appends an event with the delta and the reason, so the dashboard can
explain *why* the edge moved. When a belief is recorded with `source_kind=character`, the
receiver's `shared_secret_count` for the source increments.

## HTTP API (dashboard + director)

The same store is projected over typed HTTP routes in
`switch_world/interfaces/http/routes/`. The full route list is pinned by
`tests/interfaces/test_routes_parity.py` and the OpenAPI golden; the main surfaces are:

```
GET  /api/state                     the whole projection in one snapshot()
GET  /api/canon                     the read-only story bible
GET  /api/matrix                    beliefs × characters with provenance
GET  /api/who-knows/<key>           provenance matrix for one proposition key
GET  /api/clock                     clock, current beat, next beat
POST /api/clock/mode                mock / real
POST /api/clock/advance             {run, beat}
GET  /api/scene-card                latest scene card (markdown, read-only)
POST /api/group/say                 a group turn
POST /api/group/whisper             a staged or private whisper
GET  /api/dm/<character>            phone history
POST /api/dm                        a phone turn
GET  /api/friends                   friend gate
POST /api/friends/<character>       add a friend
GET  /api/switch-log                transport history as NDJSON
GET  /api/bifrost/usage             per-character model usage
GET  /api/scenarios                 loadable worlds
POST /api/scenarios/<id>/load       load a scenario
GET  /api/takes                     recording routes
POST /api/takes/cue                 advance a take
GET  /api/studio/summary            studio projection
GET  /health                        liveness
```

`/api/dev/*` routes (tell-alice, run-cafe, run-beat, run-arc, tavily-event, run-bifrost,
reset, scene-card export) exist only when `WORLD_DEV` is on. Every route except the
scenario/take loaders, the scene writes and the dev routes is read-only; `POST /api/dm`,
`POST /api/group/say` and `POST /api/group/whisper` are character-actor paths, and the
loader/dev routes require the director token. `GET /api/state` reads the whole projection
on one SQLite connection, and `GET /api/scene-card` writes nothing.

The dashboard polls these endpoints. It never opens SQLite; the world engine is the only
writer and the only process that opens the database file.

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
clock(id=1, now, day, mode, anchor_real)
friends(character, since)
outfits(character, outfit_id, reason, source_belief_id, updated_at)
items(id, name, holder, note)
meta(key, value)                 -- scenarios, takes and seeded flags
idempotency(scope, request_id, digest, response_json)
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
- `/api/*` is read-only except the scene writes, the scenario/take loaders (director
  token) and `/api/dev/*` (dev mode only).
- The SQLite adapter in `switch_world/adapters/persistence/` is the only module with SQL;
  MCP tools and HTTP routes call the `WorldStore` port through `WorldService`.
- Log every tool call with caller, tool, and a short argument hash — enough to debug the
  demo without storing secrets.

## Not in the MVP

- Vector search. Retrieval is keyword + recency + importance over a small belief table.
- Multi-user auth. One user, four characters, one director.
- Cross-world or multi-session state.
