# Decisions

Append-only. Newest last. A decision record is for *why*, not for a changelog.

## 2026-11-03 — Switch is the core, not an integration

The hackathon's first judging criterion is "Use of Switch: would the project stop without
it?" A chat UI with a Switch adapter would fail that test and would also be the most
crowded version of the idea. We invert it: every character is a Switch agent, every surface
is a Switch room, and the director advances the world by addressing characters in chat. The
`docker compose down` test is now a product property, not a claim.

**Ruled out:** a web app with a Switch notification bridge; a single agent with multiple
personas; a Discord bot with a custom transport.

## 2026-11-03 — OpenCode is the base connector for character sessions

OpenCode's roleplay behavior is better than the alternatives for a four-character scene, and
it reads a project `opencode.json` from the agent's working directory. Character sessions
therefore run on **OpenCode** (`opencode auth login`, provider **Backend connected**).
Claude Code remains the fallback: same world MCP server, `.mcp.json` instead of
`opencode.json`, and `mcp__world` added to the allow list if auto mode prompts.

**Ruled out:** using Claude Code as the default and OpenCode as the experiment; a mixed
provider cast (the prompt and memory behavior would diverge).

## 2026-11-03 — Original, SFW cast; no reuse of the existing character cards

The machine has nine character cards and voice presets, but most are adult-oriented and
bound to a single-user romantic frame. A public hackathon demo needs a cast that is
original, unambiguous and safe to show. We write four new characters — Alice, Emily,
Sophia, Mia — with non-romantic stakes and relationships that exclude the user. This also
keeps the submission's IP clean.

**Ruled out:** reusing `~/.agents/skills/characters/*`; voice cloning; generated portraits.

## 2026-11-03 — Text-first; cut image, voice and 3D

Image and voice generation are the expensive, commoditized half of the idea, and this box
serialises GPU work (~100–150 s per render) through one worker. The differentiator is
information flow, not media. The demo is text and a dashboard. This keeps the build inside
four days and the demo reproducible on a judge's laptop.

**Ruled out:** Z-Image portraits, GPT-SoVITS lines, sprite-map worlds, a 3D world.

## 2026-11-03 — One mechanic: the secret ledger

"AI characters with lives and a feed" is table stakes. The one thing the demo can prove
that a chat app cannot is **provenance**: who knows what, who told them, how confident they
are, and which belief changed a relationship. Every other feature is subordinate to that.

**Cut:** free-roaming schedules, a large cast, a real-time clock, open-ended emergence.

## 2026-11-03 — Deterministic director, LLM only for dialogue

The world clock, beat order, room choice and turn-taking are a Python script. The model
decides what a character says and whether to disclose. This gives deterministic demos,
bounded cost and no double-fired scenes. Authored beats, model performance.

**Ruled out:** an LLM scheduler; a fully autonomous agent loop; background ticks with no
budget.

## 2026-11-03 — Real Mattermost DMs for private conversations

The collaboration bridge does not create DM channels itself, but a person can open a
one-to-one Mattermost DM with an agent's bot account; Switch creates a room and every message
reaches the agent without `@`. That is a better demo than a private channel with an `@` on
every line. `#world` is a public channel and still requires `@name`. The director is a member
of `#world` only and never reads a DM.

**Ruled out:** private channels as DMs; adding the director to every DM.

## 2026-11-03 — The world engine is a scoped MCP server

Characters are agents; a tool surface is how they read and write state. A per-character
bearer token maps to a character id on the server, and the server ignores any character id
in the arguments. This makes "Alice knows something Emily does not" an API property, not a
prompt promise. It also gives the project an MCP-shaped README, consistent with the hub.

**Also:** the token is written **literally** into the generated `opencode.json`, because
Switch passes only a fixed set of environment variables to the session; an environment
reference would be empty and every world call would 401.

## 2026-11-03 — The director registers with a user-owned registration key

`POST /agents/register-known` is for Console-run agent types only; a script must use
`POST /agents` with `name`, `description`, `connector_type` and `integration_profile`. The
bearer credential is a **registration key created in the Gateway under the user's account**,
not the deployment bootstrap token: an agent registered with the bootstrap token belongs to a
separate account, and the characters will refuse its messages. The director is invited to
`#world` and never to a DM.

## 2026-11-03 — A relationship write tool, and a scene-card artifact

The demo needs a visible relationship delta and a deliverable for the "one human + one agent
+ a real task" requirement. Two additions follow:

- `world__update_relationship` writes the calling character's outgoing edge, clamps to
  0..1, and appends an event with the delta and the reason.
- The director exports a **scene card** after the café beat: summary, who knew what, source,
  confidence, relationship deltas, transcript links. That is the artifact the user and the
  agents produced together.

## 2026-11-03 — Repo is private during the build, public before submission

`scripts/subs new` defaults to private, and the build is not finished. The hackathon needs a
GitHub repo the judges can open. Before submitting:

```sh
gh repo edit charlot3/switch-world --visibility public --accept-visibility-change-consequences
```

Do this only after the demo video and README are ready, and after checking for secrets.

## 2026-11-03 — The scaffold is pre-window design, not the build

The hackathon requires the Switch setup and the workflow to be built during the window. The
Nov 3 scaffold commit is docs, schemas and seed data. The first **Switch-integration** commit
comes after **2026-11-04 03:31 JST**. Keep the build log; never present the scaffold as the
build.

## 2026-11-03 — Owner authorized a pre-window prototype

The owner said to start prototypes regardless of the build window. The prototype covers the
non-Switch parts: the world engine (SQLite + MCP + REST + token scoping), the dashboard, the
local café beat, and the tests. The Switch integration and the submission build remain
scheduled for the window; the build log distinguishes the prototype from the in-window work.

The local beat uses **authored dialogue**, not OpenCode sessions. It exercises the same
state writes the Switch-driven director will make, so swapping the transport is the only
remaining variable. Do not describe the local harness as the Switch demo; the submission
video still needs Switch rooms and real agent sessions.

## 2026-11-03 — Live local integration uses Claude Code while Console's OpenCode check is broken

Docker Desktop 29.9.2 + self-hosted Switch 0.31.0 + Switch Console 0.40.1. The four
characters are registered with the **Claude Code** provider, which Console verifies as
signed in. They are in the bridged `#world` Mattermost channel; a message there reaches
Alice, who calls `world__recall` and answers in character (13 s, 3 tool calls).

OpenCode remains the preferred connector. Console's `checkOpencodeSignIn` starts a temporary
OpenCode server with a temporary `XDG_CONFIG_HOME` and requires `/provider` to report a
connected backend. In this environment it returns "Could not verify authentication", and a
session against the stale shared SDK host (`127.0.0.1:51055`) failed with "server did not
start within 60000ms". The world engine and MCP tools are provider-agnostic; switching back
is the provider card plus `scripts/render-agent-configs.sh`.

## 2026-11-03 — The live director is a Console-managed Switch agent

The director is registered in Console as `director` (Claude Code provider) and added to
`#world`, so it is owned by the user and the cast accepts its messages. It does not run a
model session. `SwitchClient` reads the Console credentials from
`.switch/agents/director.json`, discovers the room by name with `list_rooms`, posts
with `POST /agents/{id}/message`, and reads
`GET /agents/{id}/rooms/{room_id}/history`.

`switch_world/application/beat_runners.py` decides whether Emily learned the secret from the **world state**
(`source: character:alice`), not from the fact that she replied. The live take produced
Alice 0.90 (source user) and Emily 0.92 (source character:alice), and Emily's trust in the
user fell from 0.45 to 0.24. The artifact is `docs/scene-card-example.md`.

## 2026-11-04 — Galgame presentation, original vector portraits, 17+ SFW

> Superseded by the ComfyUI portrait decision below; the vector art remains the fallback.

The dashboard is now a four-view visual-novel UI: **Story** (typewriter scene, portrait,
cast cards, chemistry hearts, DM links), **World Tree** (you at the root, the cast as
branches, the secret as a dashed flow), **Secret Ledger** (matrix, relationships, feed), and
**Settings** (theme/motion, links, providers, world controls, deadline).

The cast portraits are **original vector art**, not the existing character cards. The image
backend was not usable for this: the job needed ~22.8 GB plus a 6 GB reserve and only
16.5 GB was available, so it sat in `admitting`. `scripts/make-portraits.py` is
deterministic, has no GPU cost, and keeps the public submission safe.

Tone: **17+ romantic tension, SFW**. All characters are adults, fully clothed, and no
explicit content. The tone rules live in `agents/<name>/AGENTS.md`, flow into each
`CLAUDE.md`, and the galgame profile is in `IDENTITY.md` and `world/characters/`.

The Mattermost bot avatars are updated from the same vector art, and `#world` carries the
line "A small town, four hearts, one secret." The dashboard stays a read-only projection;
Switch remains the transport.

## 2026-11-04 — ComfyUI portraits after freeing the unused backends

The admission failure was not the model. ComfyUI (19GB) and GPT-SoVITS (13GB) were resident
with weights unloaded, leaving 16.7GB available; the image job needed 22.8GB plus a 6GB
reserve. Stopping both through the studio freed 32GB (swap fell from 32.3GB to 1GB), and the
cold image job passed admission. Alice rendered in 190s; Emily, Sophia and Mia followed warm
at 143–150s. The 832×1216 PNGs are now the primary portraits; the SVG generator stays as the
fallback. After the render, GPT-SoVITS is started again and ComfyUI is left up, so the studio
returns to its original usable state.

## 2026-11-04 — Canon, an aligned cast set, and two provenance repairs

**Canon is a read-only story bible, not a prompt.** `world/canon.json` holds public and
private facts, five authored beats, three branches (disclosure / non-disclosure / partial
leak) and the invariants. `switch_world/application/canon.py` gives each character only its own private
facts, classifies the ending from the ledger, and writes the branch and any warning into the
feed. The dashboard shows the same canon in the Story arc strip and Settings. The scene is
free; the worldline is not. See `docs/CANON.md`.

**A suspicion is not a disclosure.** The old live check accepted any belief from
`character:alice`. Emily's 0.45 "Alice is holding something back" was therefore labelled a
disclosure, which contradicted the dialogue and the scene card. The classifier now requires
source `character:alice`, confidence ≥ 0.6 and a content overlap with Alice's own
statement. The tests cover the suspicion, the direct disclosure, a third-party leak and a
misattribution (“Alice is leaving”). The live dashboard's first café event was repaired in
place (`disclosure` → `non_disclosure`), and two validator false-positive warnings caused by
display-name participants were removed; the static live example keeps a historical note.

**One relationship row per pair.** Live agents occasionally called
`world__update_relationship("Emily", ...)` with a display name, which created a second row
next to `"emily"`. The service now resolves ids, names and first names to canonical ids at
the boundary; `scripts/normalize-relationships.py` folds old rows back together. The profile
sheet also deduplicates defensively.

**One art flow, two shot types.** The first ComfyUI set was four good images that did not
read as a set: different crops, light temperatures and head sizes. `scripts/generate-cast-art.py`
now uses one shared scaffold, a fixed seed per shot type, and a character block as the only
variable: bust 832×1216 for cards/scene, full-body 768×1344 for the 立绘, and a 512×512
avatar crop. `PROMPTS.md` and contact sheets make the set reproducible. The first full-body pass
cropped Alice's feet and varied the camera; the scaffold now asks for the entire figure,
shoes and breathing room above/below, and the set was regenerated.

**A card is a character sheet.** Cast cards now carry a two-line intro, affinity, Story and
Profile actions. The profile sheet shows the full-body 立绘, age/height/birthday/specialty,
likes/dislikes, the private canon line (god view), a quote and outgoing relationship bars.
The tone stays 17+ SFW; the product is interactive fiction with a provenance engine, not a
dating sim.

## 2026-11-05 — Five authorial beats, three ways to run them

The project should be demonstrable in parts without turning into a free-roaming agent
world. `world/canon.json` now carries authored local dialogue, prompts and branch-aware
aftermath for all five beats; `switch_world/application/beat_runners.py` runs them locally, through
Bifrost/OpenCode, and through the live Switch
room. The café remains the required beat and owns the branch; aftermath refuses to run
before it. The dashboard adds a **Demo beats** selector and a full local arc; the story
strip marks beats done from the immutable `beat` events. This is the "several partial
demos" version for both the Flip and Geek Room editions.

## 2026-11-05 — Story has two parts: the scene and a phone DM

The Story view is now a two-column composition: the scene card and authored arc on the
left, a phone-shaped private DM on the right. The phone posts to `/api/dm`, runs the
selected character through Bifrost/OpenCode, and records private `dm` events with the
same provenance rules; the header `↗` still opens the live Mattermost conversation. On
mobile the phone stacks below the scene, with **Message this character** scrolling to it.
The visible 17+ badge was removed from the dashboard; the underlying SFW/age rules remain
in the canon and agent prompts. The point is to make the human's input a first-class part
of the product rather than a link out to another app.

## 2026-11-05 — Mattermost DMs are not a reliable private surface in this bridge

Observed live: a DM message starts a Switch session, but the agent's `post_message` is
delivered to its default room (Town Square), not the DM; the DM then shows the session
status ("Worked for 8s. 2 tool calls.") while the actual reply lands in Town Square. The
agent's DM session also came up with only the Switch MCP tools, not the world MCP, so it
could not recall/record beliefs. We did not pretend the DM worked: the Story phone is now
the private-DM surface (Bifrost/OpenCode, with recent DM history and world recall), and
the live Switch path is `#world`. The README and `docs/SWITCH.md` carry the limitation.

## 2026-11-05 — Phone history is 100 + a database cursor

The phone initially loaded three scene lines from `/api/state`; that was too little to
feel like a conversation and it ignored older DMs. It now calls
`GET /api/dm/<character>?limit=100&before_id=...`, which reads the event database directly,
returns scene + private DM messages for that character, and reports `has_more`/`oldest_id`.
The phone shows the recent 100 and a **Load older** control for the rows above; the DM
prompt also carries the last 100 DMs. The user's turn is recorded before the model call so
the auto-refresh cannot remove it while the character is thinking.

## 2026-11-05 — Demo reset, Switch logs, and the layer split

The demo needs a fast reset: `scripts/reset-demo.sh flip|geekroom|all [--artifacts]` posts
the world-engine reset, clearing beliefs/relationships/events, phone DMs and the scene card;
`--artifacts` also clears exports, Bifrost logs and the local token budget. It does not
pretend to erase Mattermost/Switch room history.

Switch's role is intentionally narrow and explicit: rooms, agent identities, sessions and
delivery. The world engine owns provenance/state, the director owns authored beats, Bifrost
owns Geek Room model routing, Tavily owns real-world input, and the dashboard/phone are
projections/write surfaces. `uv run director --switch-log` and `GET /api/switch-log` export
the raw room events (room, event id, sender, timestamp, body) instead of hiding them behind
the world feed.

## 2026-11-05 — Language and voice are part of the prompt contract

The first DM replies mixed English persona instructions with Chinese input; the model
sometimes produced over-complete, translated-sounding Chinese and answered like a support
agent. The system prompt now has an explicit language/voice contract: mirror the user's
language, use natural spoken Chinese for Chinese input, keep DMs to 1-2 sentences, prefer
concrete detail/subtext, avoid therapy-speak and a question after every line. Each
`IDENTITY.md` has a short `中文口吻` register sample; `AGENTS.md`/`CLAUDE.md` carry the same
rules for the live Switch agents. The DM prompt keeps current time, recent café context and
100 DM history, but asks for a direct, human first sentence rather than a formal answer.

## 2026-11-05 — Scene first, phone second; one story datetime

The first build put the phone on the main screen and let the scene be a feed viewer. That
inverted the fiction: people meet in a place before they text. The Story view now leads
with an in-person scene — full-body 立绘, the people present, authored choices, free text —
and the phone is a **friend-gated** second surface. Group lines go through the live Switch
room (`/api/group/say`); private lines stay in the world DB as `dm` events and are
deliberately not mirrored into Mattermost. `friends` is a small gating table, not an
authorization system.

The clock stores **one story datetime** and a mode. Mock time is the demo fast-forward:
`Advance & play` jumps to the first unplayed beat and runs it. Real time aligns to the next
beat whose time of day is ahead of the wall clock and then runs at 1× from that anchor.
That avoids a second calendar model and keeps the story date honest when a demo crosses
midnight.

**Ruled out:** a full calendar/event-scheduler model; auto-running a beat from a timer
(the arc still moves only when the showrunner runs it); mirroring phone DMs into a public
channel.


## 2026-11-05 — Affinity is a gate, not a decoration

The relationship ledger was write-only: agents updated trust/closeness/tension, but no
prompt ever read the result, and `switch_world/application/scene.py` explicitly ordered a plain answer to every direct
question. A two-star character therefore had no reason to refuse an intimate question.
We added a deterministic social appraisal before prose: live edge, tier, topic ladder,
per-character ceiling, authored refusal lines, and a hard refusal for uninvited physical
contact. The model still writes the line; the gate decides whether it may answer, deflect
or refuse, and the ledger records the reason and the delta.

**Ruled out:** relying on a stronger prompt alone (it leaks under pressure); a second LLM
classifier on the critical path (latency and non-determinism); making the meter a
cosmetic UI value with no prompt read path.

## 2026-11-05 — Direct the turn before the agents speak

A group scene is not four independent replies to the user. The director now plans the
turn first: a named addressee gets the floor, a shared fact becomes a short chorus, an
intimate probe stays one primary plus one reactor, and the rest are silent. Only planned
speakers are collected; a miss becomes a recorded silence, not an error. The plan is a
`turn_plan` event, and every beat carries `metadata` (turn, mode, role, expression,
target), which is what lets the UI render a galgame transcript instead of replaying chat.

Whisper is staged honestly: the target answers through its private model when a real
private Switch room is not provisioned, while observers receive a token-scrubbed public
reaction prompt. Boundary violations are cut before the act is written: one detail-free
public event, a hard refusal, the target leaves, and each witness records its own private
belief. Code owns who speaks, what is allowed and what the ending sees; the model owns the
sentence.

**Ruled out:** broadcasting first and sorting replies afterwards; claiming transport
privacy the transport cannot prove; letting a model decide who is silent or whether a
boundary was crossed.

## 2026-11-08 — v2: one package, ports and adapters, and MCP as the product surface

The v1 tree had grown three overlapping packages (`world_engine/`, `director/`,
`gateway/`) plus a local `mcp/`, with audited import cycles and duplicated logic. Each new
feature meant touching four layers, and "which module owns the turn?" had two answers. We
replaced the tree with one `switch_world/` package and the Ports and Adapters rule:
`domain/` is stdlib-only, `application/` depends inward on `domain`, `adapters/` implements
the ports, `interfaces/` is the driving edge, and `container.py` is the only module that
names a concrete adapter. `tests/architecture/test_layering.py`,
`test_no_legacy_imports.py` and `test_no_private_connections.py` make the rule executable,
so a regression fails in CI rather than in a demo.

**One pipeline, not four.** Group, DM and whisper share `application/scene.py` and the
`TurnRecorder` in `application/turns.py`; the four authored-beat runners share
`application/beats.py` and injected strategies. The recorded order is fixed: user line,
plan, delivery, one sanitise pass, writes with the character as actor, beats, at most one
relay. This is what lets an in-band cloud envelope and an out-of-band Switch/MCP write have
the same authority: `AgentReply.writes` is applied with `actor=character`, exactly as
`world__remember` is.

**MCP stays the product surface, not an integration detail.** The fourteen actor-scoped
tools are the cast's only write path. Authentication stays at the edge (token → actor with
a constant-time compare); authorization is domain policy applied inside the store, so
`world__give_item` rejects a non-holder and `world__record_event` rejects a character even
if a caller bypasses the tool edge. The HTTP routes and dashboard are projections of the
same store, not a second source of truth. The README now leads with the tool contract, the
scoped-token guarantee and the adapter map because that is the thing a reviewer or another
agent should be able to read first.

**Delete the shims; keep the compatibility edge in one named place.** `world_engine/`,
`director/`, `gateway/`, the local `mcp/` and `web/app.js` are gone. The only legacy-shaped
surface left is `switch_world/compat.py`, which adapts a caller-supplied Switch client or
`chat_json` client onto the ports for tests and old tooling; it is deliberately named so it
cannot hide. `make check` (ruff + compileall + pytest + node --check/node --test + generated
cast-contract drift) is the single local gate, and coverage is ratcheted to 85%.

**Ship an rc, not a merge.** The work lands on `v2-architecture` and is tagged
`v2.0.0-rc` locally. `main` and `geekroom` are untouched and nothing is deployed: the work
is a structural refactor whose acceptance is the full 3.11/3.12/3.13 matrix, the
`WORLD_DEV=0` and `WORLD_AGENT_MODE=cloud` runs, the wheel-install and Docker `/health`
smokes, and the browser smoke. If the rc is rejected, the tag plus the step commits are the
rollback story.

**Ruled out:** keeping the v1 shims indefinitely (two import paths, two owners); a
big-bang rewrite in one commit; moving authentication into the tools (it would leave
in-band and direct-store callers unaudited); a coverage target that pays for itself only in
untested glue.
