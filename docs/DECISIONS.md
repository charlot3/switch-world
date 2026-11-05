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
`director/.switch/agents/director.json`, discovers the room by name with `list_rooms`, posts
with `POST /agents/{id}/message`, and reads
`GET /agents/{id}/rooms/{room_id}/history`.

`run_switch.py` decides whether Emily learned the secret from the **world state**
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
leak) and the invariants. `director/canon.py` gives each character only its own private
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
