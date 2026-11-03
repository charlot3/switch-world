# Build plan

**Current state (2026-11-03 14:10 JST):** pre-window scaffold. The hackathon build window
opens **2026-11-04 03:31 JST**; the Switch integration and the world engine are built inside
it.

## Rule we are respecting

> "The core build must be completed during the hackathon: 2026-11-04 00:01 IST –
> 2026-11-07 23:59 IST. Existing agents, libraries and templates may be used, but the
> Switch integration and the workflow itself must be built during the event."

Nov 3 is for planning, repo setup, reading the Switch docs, and fixing the scaffold. No
Switch wiring, no world-engine code, no agent sessions until the window opens. The scaffold
includes schemas and pseudocode; commit it as **"docs: pre-window design and seed
templates"**, not as the build. The first code/Switch-integration commit comes after the
window opens.

## Day 0 — Nov 3

- [x] Read both inbox documents (proposal + requirements).
- [x] Check `ideas/` for an existing entry (none).
- [x] Create the submodule `subs/switch-world` and its GitHub repo.
- [x] Scaffold README, proposal, requirements, architecture, Switch setup, demo, decisions,
      submission checklist, cast, seed state, agent directories, scripts.
- [x] Apply the adversarial review fixes: `POST /agents`, user-owned registration key,
      OpenCode config with literal tokens, one deployment path, DB secrets, relationship
      write tool, `proposition_key`, real DMs, scene card.
- [ ] Commit the scaffold as a pre-window design snapshot; do not call it the build.
- [ ] Pre-read the Switch quickstart, self-host and agent-protocol pages; install Docker,
      Console, OpenCode, `oras`.

**Acceptance:** a reviewer can read the README and explain the product and why Switch is
core, without any code running.

## Day 1 — Nov 4: Switch works end to end

- [ ] Self-host Switch with `--profile collab --profile gateway`; pin `SWITCH_VERSION`.
- [ ] Connect Console with **Add a server → Connect to an existing server** (Gateway
      `:3000`, API `:8000`).
- [ ] Link Mattermost: search your handle → **This is me**.
- [ ] Create `#world`; enable bot accounts if needed.
- [ ] Install OpenCode, `opencode auth login`; provider **Backend connected**.
- [ ] Register `alice` with provider **OpenCode**, directory `agents/alice`; invite to
      `#world`; get an in-character reply to `@alice who are you?`.
- [ ] **90-minute spike:** add one world MCP ping to `agents/alice/opencode.json` with a
      literal token; confirm the tool call runs with no approval prompt.
- [ ] **90-minute spike:** register the director with `POST /agents` using your Gateway
      registration key; invite it to `#world`; post `@alice test`; Alice replies.
- [ ] Commit the working setup notes to `docs/SWITCH.md` (what actually happened).

**Acceptance:** `docker compose --env-file .env -f deploy/switch/<tag>/docker-compose.yml
--profile collab --profile gateway down` and the same command with `up -d` brings the
server back; Alice answers again. This is the hard requirement; do not proceed until it
passes. The director's `@alice` post is accepted and answered.

**Fallback:** if self-hosting fails, use Console's local-server path and the bundled
Mattermost, but then replace the `docker compose down` proof with **quit Console / stop the
server** and update the demo. Do not switch to a custom chat transport.

## Day 2 — Nov 5: the world engine and four characters

- [ ] World engine: FastAPI on `127.0.0.1:8890`, SQLite schema, seed loader, scene-card
      export.
- [ ] Seven MCP tools with token scoping; `who_knows` and `advance_time` are director-only.
- [ ] Four character directories; generate `opencode.json` with
      `scripts/render-agent-configs.sh`.
- [ ] Register `emily`, `sophia`, `mia`; invite all to `#world`; open DMs.
- [ ] Test: tell Alice a belief in her DM; `world__recall` returns it only to Alice;
      Emily's recall does not.
- [ ] Dashboard v0: a static table of the belief matrix and the event feed.

**Acceptance:** the token-scoping test passes. A character cannot read another's private
belief through any tool argument. The four-row matrix renders from seed data.

## Day 3 — Nov 6: the demo beat

- [ ] Register the `director` agent (already from Day 1); verify ownership and `#world`
      membership.
- [ ] Implement the room-history read so Alice's reply can be chained into Emily's turn.
      If the route is unavailable, pre-author both lines and label the scene as scripted.
- [ ] Implement beats: café (required), morning/lunch/aftermath/roundup (optional).
- [ ] Café beat: Alice and Emily talk; Alice decides whether to disclose; Emily records
      what she heard with `proposition_key=user-leaving-city`, source and confidence; Emily
      calls `world__update_relationship` with a reason.
- [ ] Feed event + dashboard provenance drawer + scene-card export.
- [ ] Rehearse the 5-minute demo twice; save `docs/demo-transcript.md`.
- [ ] Verify the relationship delta: Emily → Alice trust and Emily → user trust.

**Acceptance:** the full demo runs from a cold start in under 10 minutes, and the dashboard
shows the belief chain `user → Alice → Emily` with confidence 1.00 → 0.80.

## Day 4 — Nov 7: record and submit

- [ ] Record the demo video (one take, cut dead time); follow `docs/DEMO.md`.
- [ ] Final README pass: no "planned" claims for anything the demo uses; Switch usage is
      explicit; quickstart reproduces.
- [ ] Make the repo public (after a secret scan).
- [ ] Submit on the WeMakeDevs page; keep the confirmation.
- [ ] Buffer: 6+ hours before **2026-11-08 03:29 JST**.

## Scope cuts, in order

If a day slips, cut from the top:

1. Optional beats (morning, lunch, aftermath, roundup) → only the café beat.
2. Relationship animation → a static table.
3. Provenance drawer → hover text on the matrix.
4. Live Sophia and Mia → keep them as seeded matrix rows and feed voices; only Alice and
   Emily run sessions.
5. Scene-card export → a printed summary in the README (last resort; the artifact is the
   "real task", so protect it).

Never cut: Switch end-to-end, the café beat, the four-row matrix, the provenance chain, the
demo recording.

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Switch self-host fails or is slow | medium | Console local-server fallback; start Day 1 early; read troubleshooting first |
| The director's messages are refused | high | user-owned registration key; invite to `#world`; Day-1 `@alice test` |
| OpenCode does not read project `opencode.json` | medium | Day-1 spike; fallback to Claude Code + `.mcp.json`; last resort a world CLI over Bash |
| World MCP calls ask for approval mid-beat | medium | OpenCode config; Claude Code allow list `mcp__world` |
| Four sessions are expensive/slow | medium | one beat at a time; short prompts; no background loop beyond `--loop 60` |
| Agents talk over each other | medium | director addresses one character at a time; reads history between turns |
| A character invents a fact | high | `world__recall` is the only source; prompt rule; dashboard shows provenance |
| Memory leaks across characters | medium | token → character mapping; no character id argument; Day-2 test |
| Demo day model outage | medium | recorded fallback; pre-written transcript; dashboard still renders |
| Deadline slip | medium | internal target Nov 7 evening; 6-hour buffer; cuts above |

## Definition of done

- [ ] `docker compose --env-file .env -f deploy/switch/<tag>/docker-compose.yml
      --profile collab --profile gateway down` stops the world; the same command with
      `up -d` restores it.
- [ ] One command starts the world engine; one command runs a beat.
- [ ] Four characters, one user, `#world` plus four DMs.
- [ ] A secret travels from the user to Alice to Emily with provenance.
- [ ] The dashboard shows who knows what and why, and exports the scene card.
- [ ] The 5-minute demo video and the README explain Switch.
- [ ] The repo is public and reproducible.
