# Four Hearts — Geek Room edition

**Four Hearts** is a social research room that prepares a pre-meeting briefing. It is
submitted to the **Geek Room Global AI Hackathon** under the official problem statement
**Tavily Research Agent**, whose description is the **Pre-Meeting Briefing Agent**:

> Give the agent a company or person and a meeting time. Research the last 30 days and
> produce a one-page briefing with source-backed findings, discussion points and open
> questions.

Four Hearts answers that with four characters instead of one. Alice, Emily, Sophia and Mia
read the same Tavily results, argue about what matters in character, and leave a one-page
artifact whose every finding points back to a source and a provenance record.

It is the same `switch-world` codebase, cast and canon, submitted as one project to two
hackathons:

| Edition | Branch | Core additions | Primary event |
| --- | --- | --- | --- |
| **Flip the Switch** | `main` (tag `flip-2026-11-05`) | Switch rooms/agents, secret ledger, canon, scene card | Flip the Switch, deadline **2026-11-08 03:29 JST** |
| **Four Hearts** | `geekroom` / `v2-architecture` | **Tavily** research briefing + **Bifrost** model gateway | Geek Room Global AI Hackathon, deadline **2026-11-15 18:29 UTC** = **2026-11-16 03:29 JST** |

The Flip edition is unchanged by this branch: Switch remains the transport and the four
Switch agents remain the live cast. Four Hearts runs the same world engine and the same
canon, adds the two integrations the Geek Room brief asks for, and uses the same scene and
ledger machinery to record the briefing.

## The submission brief

| Item | Value |
| --- | --- |
| Problem statement | **Tavily Research Agent** |
| Description | **Pre-Meeting Briefing Agent** — company/person + meeting time, last 30 days, one page with source-backed findings, discussion points, open questions |
| Portal | HackCulture → **Manage** → **Submissions** → **Problem Statements & Prototype Submission** |
| Deadline | **2026-11-15 18:29 UTC** = **2026-11-16 03:29 JST** |
| Tavily integration checkbox | **Pre-Meeting Briefing Agent** |
| Team | 1–4 people |
| Required | Public GitHub repository with a README; **PPT deck** |
| Optional | Demo video |
| Final project | One project only; no second submission |

The deck is [`switch-world-geekroom-pitch.pptx`](switch-world-geekroom-pitch.pptx) (outline
in [`PITCH.md`](PITCH.md)); regenerate it with `uv run python scripts/make-pitch-deck.py`.

## The briefing — the Tavily Research Agent use case

`switch_world/application/briefing.py` implements the brief directly. Given a company or
person and a meeting time it:

1. runs 2–3 news-shaped Tavily queries (`"<subject> news"`, `"<subject> launch"`,
   `"<subject> hiring"` by default) through the same `switch_world/adapters/search/tavily.py`
   adapter that `world__search_web` uses;
2. keeps only distinct results and records one public `world_event` and one `shared` belief
   per result, with source `event:<id>` — so every finding is attributable;
3. posts one group message naming the subject, the meeting and the strongest findings, and
   lets the four characters answer in character through the normal group-turn pipeline;
4. composes a one-page markdown briefing — **Snapshot**, **Recent developments (last 30
   days)**, **Discussion points**, **Open questions**, **Sources**, **Provenance**;
5. writes `briefing-<slug>.md` through the `ArtifactStore` and records a `briefing` event
   whose metadata names the subject, meeting, source list and replies.

The research window is the 30 days before the meeting, inclusive. A result with no date is
kept and labelled `date unknown`; a result outside the window is not presented as recent.
When no transport or model is configured, the research still runs and the page records that
the room did not meet. The offline fixture is labelled in the page itself, so a demo never
presents a fixture item as a live result.

```sh
# CLI: research + the composition root's room discussion
uv run director --briefing --subject Anthropic --meeting "2026-11-18T10:00:00+09:00"

# Dev-gated HTTP write, then the read-only projection
curl -X POST localhost:8891/api/dev/briefing \
  -H 'content-type: application/json' \
  -d '{"subject":"Anthropic","meeting":"2026-11-18T10:00:00+09:00"}'
curl localhost:8891/api/briefing/latest
```

[`briefing-example.md`](briefing-example.md) is the offline-fixture page generated for the
deck: three labelled sources, a four-character discussion, six open questions and the
provenance chain.

## What the Geek Room edition adds

### 1. Bifrost = the model gateway for every character call

`switch_world/adapters/models/bifrost_compat.py` calls Bifrost's OpenAI-compatible
`POST /v1/chat/completions`. In the **Four Hearts profile** (`WORLD_AGENT_MODE=bifrost`)
Alice's and Emily's turns in `switch_world/application/beat_runners.py` — and the
briefing's room discussion — are generated through that client, not through a direct
provider SDK.

- **Per-character model configuration** — `world/models.json` sets a model, temperature,
  max tokens, fallbacks and daily token budget per character. `BIFROST_MODEL_<NAME>` and
  `BIFROST_FALLBACKS_<NAME>` override them without editing the file.
- **Failover** — each character can carry a provider/model fallback chain; Bifrost owns
  the routing and retry.
- **Governance** — the client has a local daily token guard (`data/bifrost_budget.json`)
  and sends optional `x-bf-vk` virtual-key headers. Bifrost's own governance can add
  budgets/rate limits at the gateway.
- **Observability** — Bifrost logs every request; `switch_world/adapters/models/bifrost_compat.py`
  also writes `data/logs/bifrost.jsonl` (character, model, prompt/completion tokens, latency,
  success/error), and `GET /api/bifrost/usage` returns the current budget.
- **OpenCode Go adapter** — OpenCode's v2 API is not an OpenAI endpoint, so
  `scripts/opencode-gateway.py` exposes `/v1/chat/completions` on `:8090` and runs
  `opencode run --model opencode-go/deepseek-v4.1-flash#<variant> --agent roleplay
  --format json`. Bifrost's `openai` provider points at
  `http://host.docker.internal:8090`; the model id in `world/models.json` is
  `openai/deepseek-v4.1-flash`, while the adapter calls the OpenCode Go model. The token
  is `OPENCODE_PROXY_TOKEN`; no paid provider key is used.
- **Two-tier reasoning** — routine calls use the `low` variant. The adapter reads the
  OpenAI `reasoning_effort` field and maps it to an OpenCode variant (`low`, `high`,
  `max`; `mid` maps to `high`). `world/models.json` sets low for the cast and high for the
  `arbiter`; `switch_world/application/scene.py` raises only body/contact DM and whisper
  turns to high, and `switch_world/application/turns.py` can add one bounded high arbiter
  call through `social_arbiter.arbitrate(...)` (`WORLD_ARBITER=1`). The arbiter can
  tighten the deterministic stance but never soften it, and falls back silently on
  timeout or malformed JSON.
- **Agent isolation** — the adapter runs a dedicated `roleplay` agent with every tool
  denied, passes stdin as `/dev/null`, and sets `PWD` to its isolated work directory. This
  prevents OpenCode from reading a parent heredoc or the repository config and turning a
  character reply into a coding-agent turn. The agent session configs use
  `"variant": "low"` for the same reason.
- **Reasoning-model fallback** — the optional Ollama Qwen fallback is a reasoning model.
  For `ollama/*` models the client sends `think: false`, otherwise the whole token budget
  can disappear into hidden reasoning and return an empty content field.

The packaged Four Hearts profile uses **OpenCode Go `opencode-go/deepseek-v4.1-flash`**
(free, already signed in through OpenCode), reached through the adapter. That is one model
with four character profiles, not four vendors. Set `OPENCODE_MODEL` to change it, or add
OpenAI/Anthropic providers in `deploy/bifrost/data/config.json` and point
`world/models.json` at `anthropic/...` or `openai/...` when keys are available. The
request path is identical.

```sh
scripts/run-bifrost.sh          # OpenCode adapter :8090 + Bifrost :8080
uv run director --bifrost       # Alice and Emily generated through Bifrost
```

### 2. Tavily = the real world

`switch_world/adapters/search/tavily.py` is the only web access. It never invents a result:
without `TAVILY_API_KEY` it raises unless `TAVILY_OFFLINE=1`, and the offline fixture is
clearly marked in every event and in the briefing page.

There are three paths, all through the same adapter:

- **Briefing research** — `prepare_briefing(...)` runs the 2–3 queries and records
  the distinct results as world events and shared beliefs (above).
- **World scheduler** — `scripts/world-tick.py` (or `uv run director --tavily-event`)
  searches one topic, records a public `world_event`, and writes a `shared` belief for
  every character with source `event:<id>`. The World Feed and the belief matrix show the
  real-world input; the next scene can reference it.
- **DM retrieval** — the `world__search_web` MCP tool lets any character check the present
  before answering. The agent rules say to use it for news/prices/weather/releases and to
  record what they learn as an observation. A Switch DM therefore gets live retrieval, not
  stale model knowledge.

```sh
# live Tavily
export TAVILY_API_KEY=tvly-...
uv run director --tavily-event --query "AI agents and creative tools this week"

# no-network demo (clearly labelled)
TAVILY_OFFLINE=1 uv run director --tavily-event --query "AI agents this week"
```

## Run the Geek Room demo

The run profile is the Four Hearts profile: Bifrost for model calls and a labelled offline
Tavily fixture unless a key is set.

```sh
export WORLD_AGENT_MODE=bifrost
export BIFROST_URL=http://127.0.0.1:8080/v1
export TAVILY_OFFLINE=1          # packaged demo: labelled offline fixture
# The engine script uses /tmp/geekroom; the director commands below must use the
# same DB and data directory or the dashboard will not show their events.
export WORLD_DB=/tmp/geekroom/world.sqlite
export WORLD_DATA_DIR=/tmp/geekroom
```

`BIFROST_API_KEY` is optional for a local gateway. `BIFROST_MODEL_<NAME>` and
`world/models.json` set the per-character models. `WORLD_DEV` defaults to `1`, so the
`/api/dev/*` write routes are available in the local demo.

### Exact local flow — offline fixture + Bifrost

```sh
# 0. From the repository root, with the exports above.
# 1. Gateway: OpenCode adapter on :8090, Bifrost on :8080.
scripts/run-bifrost.sh

# 2. A Geek Room world instance on :8891 with its own DB (the Flip demo on :8890
#    is untouched). The script defaults TAVILY_OFFLINE=1 and BIFROST_URL.
scripts/run-geekroom-engine.sh

# 3. Subject + meeting -> Tavily -> room -> one page.
#    The room discussion goes through the Bifrost profile.
uv run director --briefing --subject Anthropic --meeting "2026-11-18T10:00:00+09:00"
#    writes /tmp/geekroom/exports/briefing-anthropic.md
#    and records world_event(s) + a briefing event in /tmp/geekroom/world.sqlite

# 4. Read the same artifact through HTTP (optional; proves the projection).
curl -X POST localhost:8891/api/dev/briefing \
  -H 'content-type: application/json' \
  -d '{"subject":"Anthropic","meeting":"2026-11-18T10:00:00+09:00"}'
curl localhost:8891/api/briefing/latest

# 5. Dashboard.
open http://127.0.0.1:8891/?view=story
```

The page is the deliverable: Snapshot, Recent developments (last 30 days), Discussion
points, Open questions, Sources and Provenance. The offline run is labelled at the top of
the page and each fixture source is prefixed `Offline fixture:` — it is never presented as
a live result.

### Live-key drop-in

The commands do not change; only the environment does:

```sh
export TAVILY_API_KEY=tvly-...
unset TAVILY_OFFLINE
uv run director --briefing --subject Anthropic --meeting "2026-11-18T10:00:00+09:00"
```

With the key set and the offline switch unset, the same adapter performs live Tavily
searches, the same `world_event`/belief/provenance path runs, and the briefing page drops
the offline note. If every query fails, the CLI exits with the adapter error rather than
writing an empty brief.

The demo shows:

1. the Settings **Geek Room layer** card and the Bifrost request log;
2. a Tavily event in the World Feed and the shared-event row in the belief matrix;
3. the briefing page produced from the subject and meeting, with its source list and
   provenance;
4. `GET /api/bifrost/usage` and `data/logs/bifrost.jsonl` as governance/observability
   evidence.

The Story view's right-hand **phone** is a private DM through Bifrost/OpenCode. It posts
to `/api/dm` and records private `dm` events, so it works without a Mattermost login; the
`↗` in the phone header opens the live Mattermost conversation. On mobile the phone stacks
below the scene, and **Message this character** scrolls to it.

Screenshots: [`geekroom-dashboard.png`](geekroom-dashboard.png),
[`geekroom-ledger.png`](geekroom-ledger.png),
[`geekroom-settings.png`](geekroom-settings.png). The real run also produced
[`bifrost-log-example.jsonl`](bifrost-log-example.jsonl) (two requests: 1,693 + 1,671
tokens) and [`scene-card-bifrost-example.md`](scene-card-bifrost-example.md).

## Geek Room deliverables

- [ ] Public GitHub repository with a README explaining the **Tavily Research Agent**
      briefing and both integrations.
- [ ] **Pitch deck** (required) — [`switch-world-geekroom-pitch.pptx`](switch-world-geekroom-pitch.pptx);
      outline in [`PITCH.md`](PITCH.md). Regenerate with
      `uv run python scripts/make-pitch-deck.py`.
- [ ] Demo video (optional) — reuse the Flip footage plus the briefing/Bifrost segment.
- [ ] Submission on HackCulture: **Manage** → **Submissions** → **Problem Statements &
      Prototype Submission**. Choose **Tavily Research Agent** as the problem statement and
      tick the Tavily integration box **Pre-Meeting Briefing Agent**.
- [ ] Team of 1–4 people; one final project for the team; no second project.

Deadline: **2026-11-15 18:29 UTC** = **2026-11-16 03:29 JST**. The Flip deadline is earlier
and remains the priority.

## Compliance / honest scope

- The Flip core was built in the Flip window (2026-11-04–07 JST). The Geek Room window is
  2026-11-01–15, so the same work is inside it.
- Neither ruleset read here has an exclusivity clause; one project can be submitted to
  both. The final Geek Room submission is one project only.
- The local default is a single OpenCode Go model with four character profiles, reached
  through the local OpenCode adapter and Bifrost; there is no paid provider key.
  Per-character *different provider models* are a config change, not a claim that the local
  demo already uses four vendors. The README says so.
- The offline Tavily fixture is labelled in the event text and in the briefing page. A live
  submission should set `TAVILY_API_KEY` and unset `TAVILY_OFFLINE`.
- No 3D, voice, or in-loop image generation; the cast art is a pre-generated set.
