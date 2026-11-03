# Switch setup and usage

This is the hackathon-critical document: **Switch must be the core of the project**, and the
README must explain how it is used. This page is the long form; the README has the short
version.

Official sources:

- Docs: <https://docs.switchagents.ai/>
- Quickstart: <https://docs.switchagents.ai/switch-rooms/getting-started/>
- Self-host: <https://docs.switchagents.ai/switch-rooms/deploy/self-host>
- Agent protocol: <https://docs.switchagents.ai/switch-rooms/internals/agent-protocol>
- Repo: <https://github.com/sandbox-quantum/switch>

## What Switch is

Switch is a self-hosted layer that puts AI agents into team chat. Each chat channel becomes
a **room**; each human and each agent is a participant. Internally it uses Matrix (Tuwunel)
as the message bus and a collaboration bridge to map rooms to Slack, Teams, Discord,
Telegram or Mattermost channels. It does not supply a model: the agent is Claude Code,
Codex, OpenCode, or a custom client speaking the agent protocol.

In this project every character is a Switch agent and every surface is a Switch room. The
world does not have a separate chat backend.

## 1. Self-host with Docker

The Compose file is published as an OCI artifact. The docs require an explicit version; the
file has no fallback.

```sh
# list published versions
oras repo tags ghcr.io/sandbox-quantum/standalone-compose

# pull the pinned artifact (this script wraps oras pull and shows the contents)
scripts/fetch-switch.sh <tag>

# copy this repo's .env.example, then merge any extra variables from the artifact's sample
cp .env.example .env
$EDITOR .env

# --env-file points Compose at the repo .env; -f points it at the fetched artifact
docker compose --env-file .env -f deploy/switch/<tag>/docker-compose.yml \
  --profile collab --profile gateway up -d
```

`--profile collab` adds and seeds a Mattermost instance (the demo chat surface).
`--profile gateway` adds the admin gateway. Set `COMPOSE_PROFILES=collab,gateway` if you
want a bare `docker compose up -d` to work.

Required environment before the first start:

| Variable | Notes |
| --- | --- |
| `SWITCH_VERSION` | pinned image tag; standalone compose has no fallback |
| `ID_SERVER_NAME` | permanent server name; **cannot be changed later** without orphaning rooms/users |
| `AGENT_REGISTRATION_TOKEN` | deployment bootstrap key; do **not** use it for the director |
| `SWITCH_REGISTRATION_KEY` | a registration key created on the Gateway's **API Keys** page under **your** account; this is what the director uses |
| `SECRET_KEYS` | `<id>:<secret>` pairs, current key first, each ≥ 32 chars |
| `GATEWAY_ADMIN_EMAIL`, `GATEWAY_ADMIN_PASSWORD` | first admin |
| `DB_USER`, `DB_PASSWORD`, `DB_OWNER_USER`, `DB_OWNER_PASSWORD`, `DB_NAME` | Postgres; the standalone sample lists them and `deploy/local/generate-env-secrets.sh` fills them |
| `MATTERMOST_ADMIN_USER`, `MATTERMOST_ADMIN_PASSWORD`, `MATTERMOST_USER`, `MATTERMOST_USER_PASSWORD` | bundled Mattermost |
| `GATEWAY_PUBLIC_URL` | public address of the Switch **API** (scheme + host, no path); optional for a local demo; despite the name, not the Gateway's address |
| `SWITCH_BIND_ADDR` | defaults to `127.0.0.1`; set only if you need remote access |
| `FEATURE_FLAGS_ENABLED` | e.g. `agent_management` if you use managed agents |
| `CONTROLLER_TOKEN_SECRET` | required with `agent_management`; 32+ random chars, separate from `SECRET_KEYS` |

Ports: API `8000`, Gateway `3000`, Mattermost `8065`, Postgres `5432`. All bind to
`127.0.0.1` by default, which is what a local demo wants.

After changing environment variables, `docker compose restart` is not enough; run
`docker compose up -d` so containers are recreated.

If the artifact does not include a `.env.example`, use the official standalone sample and
run `deploy/local/generate-env-secrets.sh .env <label>` (or `just init-env`) to generate the
secrets.

## 2. Connect Switch Console to the server

1. Install **Switch Console** for macOS.
2. **Settings → Agent providers → OpenCode** → `opencode auth login` → **Recheck**. The
   status must say **Backend connected**. (Claude Code is the fallback: `claude auth login`,
   status **Signed in**.)
3. **Add a server → Connect to an existing server**:
   - Gateway URL `http://localhost:3000`
   - API URL `http://localhost:8000`
   - the admin email/password from `.env`
4. Link your messaging account: choose **Mattermost**, search for your handle, select
   **This is me**, then **Done**. Do not skip this. A newly registered agent answers its
   owner and the owner's agents; until the account is linked, the agent cannot recognize
   you and will refuse your messages.
5. Sign in to Mattermost at `http://localhost:8065` with `MATTERMOST_USER` /
   `MATTERMOST_USER_PASSWORD`. If bot account creation is disabled, enable it in Mattermost
   (System Console → Integrations → Bot Accounts).

Console reads `PATH` once at startup. If a provider says "CLI not installed" after you
install it, fully quit and reopen Console.

## 3. Create the surfaces

- Create a public Mattermost channel **`world`**; add the user and all four character bot
  accounts.
- Open a one-to-one Mattermost DM with each character's bot account: `alice`, `emily`,
  `sophia`, `mia`. A DM reaches the agent without an `@` mention; Switch creates a room for
  it. A message in a **channel** must be addressed with `@name`.
- The director belongs to `#world` only. It is never added to a private DM.

## 4. Register the cast (OpenCode)

Repeat for each of `alice`, `emily`, `sophia`, `mia`:

1. **Your Agents → +**.
2. **Name**: lowercase letters, digits, `.`, `-`, `_`; must start with a letter or digit;
   permanent and unique per server.
3. **Run location**: **This computer**.
4. **Directory**: `agents/<name>`. The directory shapes the agent's behavior and is exposed
   to everyone in its rooms, so keep it scoped.
5. **Agent provider**: **OpenCode**.
6. **Settings**: Auto mode is on by default; leave **Bypass permissions** off. The agent
   only needs its own directory and the world MCP server.
7. **Who can talk to your agent**: **Only me and my agents** is enough for the demo.
8. **Add agent**, then invite it to `#world`.

Console writes its own files under `.switch/` in the working directory (credentials and
advanced settings; `.switch/config/<name>.json` is the advanced-settings file on current
releases). Do not commit `.switch/`; `.gitignore` excludes it.

### The world MCP server (OpenCode)

Each character's working directory gets a generated `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["IDENTITY.md"],
  "mcp": {
    "world": {
      "type": "remote",
      "url": "http://127.0.0.1:8890/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer <literal character token>" }
    }
  }
}
```

Run `scripts/render-agent-configs.sh` to write it from `.env` for all four characters. The
token is literal because **Switch passes the agent only a fixed set of environment
variables, not the whole shell**; a `${WORLD_TOKEN}` reference would be empty. The generated
file is gitignored; `opencode.json.example` is committed.

OpenCode loads `AGENTS.md` automatically and the `instructions` array adds `IDENTITY.md`.
Use `AGENTS.md` for the operating rules and `IDENTITY.md` for the persona.

**Claude Code fallback:** use `.mcp.json` instead of `opencode.json`:

```json
{
  "mcpServers": {
    "world": {
      "type": "http",
      "url": "http://127.0.0.1:8890/mcp",
      "headers": { "Authorization": "Bearer <literal character token>" }
    }
  }
}
```

Add `{"permissions":{"allow":["mcp__world"]}}` to the Claude Code settings if auto mode
asks for approval mid-beat. The primary path is OpenCode; keep this as a Day-1 fallback.

## 5. Register the director

The director is a script with no Claude or OpenCode session. It registers once with a
**registration key created under your account**, not with the deployment bootstrap token.
An agent registered with the bootstrap token belongs to a separate account, and the
characters will refuse its messages.

1. In the Gateway, go to **API Keys** and create a key of type **registration**.
2. Register:

```sh
curl -sS -X POST "$SWITCH_API/agents" \
  -H "Authorization: Bearer $SWITCH_REGISTRATION_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "director",
    "description": "world clock and scene runner",
    "connector_type": "custom",
    "integration_profile": {
      "connection_model": "session_passive",
      "message_exchange": true,
      "pre_invocation_mediation": [],
      "post_invocation_mediation": [],
      "event_reporting": []
    }
  }'
# -> {"id":"<director id>","api_key":"<shown once>"}
```

`connector_type` is a free-form label; `custom` is fine. `connection_model` is one of
`always_on`, `session_addressable`, `auto_session`, `session_passive`; `session_passive` fits
a script that only posts and reads history. The API key is shown once; store it in
`DIRECTOR_API_KEY`. Re-registering the same name is a 409; `overwrite: true` issues a new
key and breaks the old one.

3. Invite the director to `#world` (Console or `!invite-agent @director`).
4. Set every character's **Who can talk to your agent** to a rule that admits the director
   (the default **Only me and my agents** admits agents you own, so register the director
   with your own registration key).

Post an addressed scene turn:

```sh
curl -sS -X POST "$SWITCH_API/agents/$DIRECTOR_AGENT_ID/message" \
  -H "Authorization: Bearer $DIRECTOR_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"room_id":"<#world room id>","content":"@alice It is 18:30 at the café. Emily is here. You have something on your mind."}'
```

`POST /agents/{id}/message` needs no open connection, but the director must be a member of
the room. To chain Alice's reply into Emily's turn, the director reads the room history:

```sh
curl -sS "$SWITCH_API/agents/$DIRECTOR_AGENT_ID/rooms/$WORLD_ROOM_ID/history?since=<timestamp>" \
  -H "Authorization: Bearer $DIRECTOR_API_KEY"
```

Verify the exact history route on Day 3. If it is unavailable on your build, pre-author both
lines and label the scene as scripted in the demo; do not claim the model decided.

## 6. Receiving messages (only if you build a custom client)

The director does not need this. For completeness, the current receive path is the
WebSocket:

```http
GET /agents/{agent_id}/connection/ws?connection_id=<uuid>&rooms=<room_id>
Authorization: Bearer <agent API key>
Upgrade: websocket
```

- `connection_id` is a client-generated UUID reused on reconnect.
- The first frame is `connection_state`; read the actual rooms, cursor and
  `heartbeat_interval_seconds` rather than assuming.
- The server pings; answer with a pong carrying the highest processed sequence. Do not
  hard-code the interval — the official docs have advertised 2 s/6 s and current core builds
  advertise 10 s/30 s.
- One **watcher connection per agent**; placements map sessions to rooms; an agent may hold
  at most 32 connections.
- The older SSE stream (`GET /agents/{id}/events`) still exists but is deprecated. Use the
  WebSocket for new clients.
- `gap` means history was lost; re-read before replying. `filter=addressed` drops `command`
  events; use `filter=all` if you need `!reset`/`!compact`.
- There is no separate task protocol; agents delegate work by messaging one another.

## 7. How the world uses Switch

```
director ──POST /agents/{director}/message "@alice …"──▶ Switch ──▶ #world ──▶ Mattermost
                                                              │
                                                              └──▶ Alice's OpenCode session
director ──GET room history──▶ Alice's reply ──@emily …──▶ Switch ──▶ Emily's session
Emily ──world__remember(..., source=alice, proposition_key=… )──▶ world engine
Emily ──world__update_relationship(alice, trust_delta=-0.1)──▶ world engine
director ──world__record_event(...)──▶ world engine ──▶ dashboard feed + scene card
```

The world engine stores state; Switch stores delivery and sessions. Neither duplicates the
other.

## 8. The "remove Switch" test

```sh
docker compose down
```

Then:

- no rooms exist, so no character can be addressed;
- no sessions start, so no character can reply;
- the director's `POST /agents/.../message` calls fail;
- the dashboard still renders the last state, and SQLite still has the beliefs, but the
  world cannot advance.

This is the required proof that Switch is core, not a wrapper. Include it in the demo or
the README.

## 9. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Agent never answers | message not addressed with `@name` in a channel; Console not running; session not started |
| Agent answers everyone with a refusal | your Mattermost account is not linked; Console → Messaging apps → search your handle → **This is me** |
| Agent is "in a room" but silent | registered ≠ connected; address it to start a session |
| Provider shows "CLI not installed" | Console reads `PATH` at startup; quit and reopen |
| `opencode` not found | install OpenCode and recheck; Console reads `PATH` once |
| World MCP returns 401 | the generated `opencode.json` has an empty/literal-var token; rerun `scripts/render-agent-configs.sh` |
| Tool call asks for approval mid-beat | add `mcp__world` to the provider's allow list (Claude Code fallback), or use the OpenCode config |
| Director's post is refused | the director is not owned by you or not in `#world`; register with your Gateway registration key and invite it |
| Room already claimed | one acting connection per agent per room; use `subscribe` with `takeover` or `connect_to_room` |
| Heartbeat evictions | read `heartbeat_interval_seconds` from `connection_state`; don't hard-code 2 s |
| No DM channel | the bridge does not create DMs; a person opens a one-to-one DM with the agent's bot account |
| No `#world` channel | create it in Mattermost and add the four bot accounts; a fresh Mattermost seeds only town-square/off-topic |
| Teams not reachable | Teams is the only adapter needing a public inbound address (port 3978) |
| Env changes ignored | `docker compose restart` is insufficient; `up -d` recreates |

## 10. Limits to design around

- The bridge has no pre-join history: a newly joined agent sees only what happens next.
- Room ↔ channel is one-to-one.
- Capability flags are static, not runtime.
- The bridge must return a real platform message reference for threading/edits/deletes.
- Agent event buffers are bounded; a `gap` is explicit, not silent.
- A DM is created by a person, not by the bridge.
- There is no separate task protocol; agents delegate by messaging.
