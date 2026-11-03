# Agents

One working directory per Switch agent. **OpenCode is the base connector** for character
sessions; Claude Code is the fallback. Switch Console creates and manages the `.switch/`
subdirectory; the rest is ours.

```
agents/
  alice/
    AGENTS.md       operating rules; OpenCode loads it automatically
    IDENTITY.md     the persona (Alice)
    opencode.json   generated: world MCP server + Alice's literal token (gitignored)
    .switch/        Console-managed credentials/settings (gitignored)
  emily/
  sophia/
  mia/
  opencode.json.example   shared template
```

The director is **not** under `agents/`; it lives at the repo-root `director/` and has no
OpenCode/Claude session.

## Register

In Switch Console: **Your Agents → +**, name `alice`, run location **This computer**,
directory `agents/alice`, provider **OpenCode**, who can talk **Only me and my agents**.
Repeat for the other three. Invite each to `#world`. Open a one-to-one Mattermost DM with
each bot account.

Provider check: Settings → Agent providers → **OpenCode** → `opencode auth login` →
**Recheck**; the status must say **Backend connected**.

## `opencode.json`

Run `scripts/render-agent-configs.sh` to generate one per character from `.env`:

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

The token is **literal**, not `${WORLD_TOKEN}`: Switch passes the session only a fixed set
of environment variables, not the whole shell, so an environment reference resolves to
empty and every world call returns 401. The generated `opencode.json` is gitignored; the
shared [`opencode.json.example`](opencode.json.example) is committed.

OpenCode loads `AGENTS.md` automatically and the `instructions` field adds `IDENTITY.md`.
Use `AGENTS.md` for the operating rules and `IDENTITY.md` for the persona.

Pin the roleplay model you use in `opencode.json` (`"model": "<provider>/<model>"`) and keep
it identical across the four characters. A mixed cast drifts: the same confidence language
and the same willingness to disclose need the same model.

## Claude Code fallback

If OpenCode is unavailable, register the agent with provider **Claude Code** and use
`.mcp.json` instead:

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

Add `{"permissions":{"allow":["mcp__world"]}}` if auto mode asks for approval mid-beat.
The character's persona file is `CLAUDE.md` (or a `CLAUDE.md` that imports `IDENTITY.md`).

## Day-1 test

After registering Alice, address her in `#world`:

```
@alice who are you, and what are you hiding?
```

She must answer in character and call `world__recall` without an approval prompt. If she
answers as a generic assistant, the persona file is not being loaded. If the tool call
fails with 401, the token in `opencode.json` is empty or wrong. Fix this before registering
the other three.

## Do not commit

`.switch/` contains live credentials. `opencode.json` contains the literal token. Both are
gitignored.
