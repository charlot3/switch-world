# Architecture

## Shape

```
                         ┌──────────────────────────── Switch ────────────────────────────┐
                         │  #world  ·  DM-alice  ·  DM-emily  ·  DM-sophia  ·  DM-mia       │
                         │  channels ↔ Mattermost channels; DMs ↔ one-to-one Mattermost DMs│
                         └───────▲───────────────▲────────────────▲───────────────▲────────┘
                                 │               │                │               │
                          Switch agent    Switch agent     Switch agent    Switch agent
                            (Alice)         (Emily)          (Sophia)         (Mia)
                          OpenCode        OpenCode         OpenCode        OpenCode
                                 │               │                │               │
                                 └───────────────┴───────┬────────┴───────────────┘
                                                         │  scoped MCP token
                                                 ┌───────▼────────┐
                                                 │  world engine  │  beliefs · relationships · events
                                                 │  FastAPI + MCP │  provenance · visibility
                                                 └───────▲────────┘
                                                         │ reads state, posts beats, exports scene card
                                                 ┌───────┴────────┐
                                                 │    director    │  deterministic beat runner
                                                 └────────────────┘
                                                         │
                                                 ┌───────┴────────┐
                                                 │   dashboard    │  read-only /api/*
                                                 └────────────────┘
```

The **world engine** is the source of truth for state. Switch is the source of truth for
delivery and sessions. The director is the clock. Characters are the only things that write
private beliefs, and they write them through a scoped token.

## Components

### 1. Switch

- One **agent** per character, plus one `director` agent for the beat runner.
- `#world` is a public channel; each character has a one-to-one Mattermost **DM** with the
  user. A DM reaches the agent without `@`; a channel message must be addressed.
- Switch maps each surface to a Mattermost channel or DM. The bundled `collab` profile
  supplies Mattermost, so the demo needs no external workspace.
- See [`SWITCH.md`](SWITCH.md) for the setup and the agent protocol.

### 2. World engine (`mcp/`)

A small FastAPI service on `127.0.0.1:8890` with three surfaces:

| Surface | Path | Consumer |
| --- | --- | --- |
| MCP (streamable HTTP) | `/mcp` | character agents, director |
| JSON API | `/api/*` | dashboard, director |
| Dashboard | `/` | the human, in a browser |

The MCP tools are the only write path for characters:

| Tool | Scope | Notes |
| --- | --- | --- |
| `world__recall(query, limit=8)` | character | the beliefs and relationship facts this character may see, ranked by relevance + importance + recency |
| `world__remember(proposition, source, confidence, visibility, proposition_key?)` | character | writes a belief owned by the calling character; source is `user`, `event:<id>`, `character:<id>` or `observation`; omit `proposition_key` only for an ad-hoc fact |
| `world__relationship(other)` | character | the calling character's view of another character |
| `world__update_relationship(other, trust_delta, closeness_delta, tension_delta, reason)` | character | adjusts the calling character's outgoing edge, clamps to 0..1, appends an event |
| `world__record_event(kind, summary, participants, visibility)` | character / director | append-only event; returns the event id |
| `world__who_knows(proposition_key)` | director | the full matrix with provenance |
| `world__advance_time(minutes)` | director | moves the world clock and enqueues the next beat |

**Token scoping.** Each character's generated config carries a different bearer token. The
server maps token → character id and ignores any `character_id` in the arguments. A
character can only read its own beliefs. `world__who_knows` is director-only. This is the
mechanism that makes "Alice knows something Emily does not" true at the API layer, not just
in the prompt.

### 3. Director (`director/`)

A deterministic Python beat runner, registered as the Switch agent `director`. It does not
hold an OpenCode/Claude session; it posts messages through the Switch agent protocol and
reads room history to chain turns.

A beat:

1. Read the world state and the world clock.
2. Run one authored beat from `world/canon.json` — local, Bifrost or Switch. The café
   is required and owns the branch; aftermath reads it; the other beats are partial
   demos that can run on their own.
3. Post a scene prompt into `#world`, addressed to one character:
   `@alice It is 18:30 at the café. Emily is here. You have something on your mind.`
4. Read the room history for Alice's reply, then address Emily with it:
   `@emily Alice says: "…" — how do you respond?`
5. Wait for Emily's reply, then classify the ending **from the ledger** with
   `director/canon.py`: a `character:alice` source, a confidence floor, and a content
   match against Alice's own statement. A suspicion is not a disclosure.
6. Record the public event, the authored branch, and any canon warning.
7. Export the **scene card** (summary, beliefs, provenance, relationship deltas).
8. Advance the clock; stop after the authored beats for the day.

Why a script and not an LLM scheduler: the demo needs deterministic ordering, bounded
cost, and no double-fired scenes. The LLM is used for dialogue and the disclosure decision,
not for deciding whether the world ticks. Author the beats; let the model act inside them.

The canon is a **read-only story bible** (`world/canon.json`, loaded by
`director/canon.py`), not a database table. It gives each character its public facts, its
own private facts and the invariants; the director keeps the full file. That split is what
lets the scene be free without leaking Emily's private facts into Alice's prompt.

### 4. Characters (`agents/<name>/`)

Each working directory contains:

```
AGENTS.md              operating rules; OpenCode loads it automatically
IDENTITY.md            who I am, my goals, my voice, my relationship priors
opencode.json          generated: world MCP server + this character's literal token
opencode.json.example  committed template
.switch/               Console-managed credentials/settings (gitignored)
```

The character's rules tell it:

- it is in a chat room with other people and agents;
- every claim about another person must come from `world__recall`, not invention;
- when it learns something, it calls `world__remember` with the source and the canonical
  `proposition_key`;
- when it shares something, it says so in the room; the listener records it;
- when its view of someone changes, it calls `world__update_relationship` with a reason;
- it never reveals a belief whose `visibility` is `private` unless its own disclosure policy
  says to.

### 5. Dashboard

A read-only projection of the world state, served by the world engine:

- the belief matrix (characters × propositions), with source and confidence on hover;
- the relationship graph (trust / closeness / tension);
- the event feed, newest first;
- a "provenance" drawer: for one belief, the chain `user → Alice → Emily`, with timestamps;
- a download link for the latest scene card.

The dashboard polls the world engine's read-only `/api/*` endpoints. The world engine is the
only process that opens SQLite.

## Data model

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

Rules:

- **Beliefs are per holder.** Two characters can hold the same `proposition_key` with
  different confidence, source and text. A retelling stores the listener's version, not a
  copy of the speaker's.
- **Provenance is mandatory.** `source_kind` is one of `user`, `character`, `event`,
  `observation`. A belief with no source is a bug.
- **Events are immutable.** Corrections are new events with `supersedes` set.
- **Relationships are directed.** Alice's view of Emily and Emily's view of Alice are
  separate rows; asymmetry is a feature, not a bug.
- **Relationship endpoints are canonical ids.** The service resolves a display name or a
  first name (`"Emily"`, `"Alice Moreau"`, `"you"`) to the id before writing, so one pair
  has one row. `scripts/normalize-relationships.py` repairs older databases that predate
  this rule.
- **Visibility** is `private` (holder only), `shared` (participants of the source event),
  or `public` (feed).
- **Shared secrets:** when a belief is recorded with `source_kind=character`, the receiving
  character's `shared_secret_count` for the source increments.

The seed loader maps the JSON `from`/`to` fields to `a`/`b`, defaults
`shared_secret_count=0` and `superseded_by=null`.

Seed data is in [`../world/state/`](../world/state/).

## The secret ledger in one sequence

```
user  ──DM: "I've decided to leave the city… I haven't told the others yet"──▶  Alice
Alice ──world__remember("I am leaving…", source=user, proposition_key=user-leaving-city)──▶  world engine
director ──@alice "It is 18:30 at the café. Emily is here."──▶  #world
Alice ──reply, decides to tell Emily──▶  #world
director ──reads history, then "@emily Alice says: …"──▶  #world
Emily ──world__remember("Alice is leaving…", source=character:alice, confidence=0.8,
                         proposition_key=user-leaving-city)──▶  world engine
Emily ──world__update_relationship(alice, trust_delta=-0.1, reason="heard second-hand")──▶  world engine
director ──branch_for(ledger) → disclosure (confidence 0.8, content match)──▶  branch
director ──world__record_event(branch, participants=[alice, emily])──▶  feed
dashboard ──Alice 1.0 (user), Emily 0.8 (Alice), Sophia/Mia absent; arc = The Confession──▶  screen
director ──exports scene-card.md + branch event──▶  artifact
user  ──DM Emily: "hey"──▶  Emily
Emily ──world__recall() includes the belief and the changed relationship──▶  reply
```

## Failure modes and guards

| Failure | Guard |
| --- | --- |
| Two agents reply at once and talk over each other | the director addresses one character at a time and reads history between turns |
| Alice withholds and the scene stalls | the director has a second, authored prompt: Emily asks directly once |
| A character invents knowledge | `world__recall` is the only source of relationship facts; the prompt forbids invention; the dashboard shows the source |
| A character reads another's private belief | token → character mapping on the server; no `character_id` parameter |
| A character records a suspicion as a disclosure | `branch_for` requires source `character:alice`, confidence ≥ 0.6 and a content match; a low-confidence "Alice is hiding something" stays `non-disclosure` |
| An agent writes a relationship with a display name | the service resolves names to ids at the boundary; `scripts/normalize-relationships.py` repairs old rows |
| The scene wanders off the worldline | authored beats + `world/canon.json` + `director/canon.py`; the director records the branch and any warning |
| The world double-fires a beat | beats have ids and states; the director is single-writer; a tick is idempotent |
| Switch is down | no rooms and no sessions; the director's posts fail; the dashboard still renders the last state |
| LLM cost/latency blows up | 4 characters, 1 simulated day, 5 authored beats (2 optional), on-demand ticks |
| The demo depends on a live model | pre-record the fallback video; keep a scripted transcript for the dashboard |
| The director's message is refused | the director is registered with the user's own registration key and invited to `#world` |

## Non-goals

- 3D world, animated sprites, maps.
- In-loop image or voice generation; the cast art is a pre-generated set.
- Real-time clock, free-roaming schedules.
- A general agent framework.
- Public multi-user signup.

## Prototype status (2026-11-05)

Runnable now, no Switch required:

- **World engine** (`world_engine/`): SQLite schema, seed loader, the seven MCP tools with
  token scoping, relationship-name normalization, the REST/dashboard API, canon exposure,
  and the scene-card export.
- **Canon** (`world/canon.json`, `director/canon.py`): public/private facts, five authored
  beats, three branches, structural validation, and the branch classifier.
- **Dashboard** (`web/`): the galgame Story view with an authored arc strip and character
  cards, the profile sheet (立绘, intro, stats, private god-view, relationship bars), the
  belief matrix with provenance tooltips, directed relationship bars with a table view, the
  event feed, the World Tree, and the dev harness.
- **Cast art** (`scripts/generate-cast-art.py`): one shared prompt scaffold, fixed seeds,
  bust + full-body + avatar set, `PROMPTS.md` and contact sheets.
- **Beat demos** (`director/beats.py`): all five authored beats run locally, through
  Bifrost, or through the live Switch room; the café owns the branch and aftermath reads
  it, while morning/lunch/roundup are independent partial demos.
- **Local café beat** (`director/simulate.py`): authored dialogue that exercises the same
  state writes as the Switch-driven director, including the branch event.
- **Tests** (`tests/`): `uv run pytest` covers the service, the API, the canon and the beat.

Next (the Switch path):

1. Switch up + Mattermost + one OpenCode agent replies in a room (the hard requirement).
2. Register the other three characters; invite all four to `#world`; open DMs.
3. Swap the local transport for the director's Switch message/history calls.
4. Record the demo; polish the README.

## Build order

1. Switch up + Mattermost + one OpenCode agent replies in a room (the hard requirement).
2. World engine with SQLite and the seven MCP tools; token scoping; dashboard v0.
3. Four character directories and personas; invite all four to `#world`; open DMs.
4. Director: café beat + disclosure decision + relationship delta + scene card.
5. Dashboard: belief matrix + provenance drawer.
6. Demo recording + README polish.
