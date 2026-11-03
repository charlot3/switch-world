# Demo — 5 minutes

> This is the **submission demo** and requires Switch. For the local prototype, run
> `uv run world-engine` and use the dashboard's **Dev harness** (Tell Alice → Run café
> beat); it exercises the same state writes but not Switch.

The demo must prove four things in this order: **Switch is the world**, **a secret moves**,
**the UI shows why**, and **the artifact persists**. The official brief also requires one
human + at least one AI agent + a real task; the scene card is that task's deliverable.

## Pre-demo checklist

- [ ] Switch up: `docker compose --profile collab --profile gateway ps` shows API, gateway,
      Mattermost healthy.
- [ ] Switch Console connected; **Claude Code** provider shows **Signed in** (OpenCode is
the preferred connector; Console 0.40.1's check is blocked, so the live cast uses Claude Code).
- [ ] Five agents registered: `alice`, `emily`, `sophia`, `mia`, `director`.
- [ ] `#world` public channel with the user and the four character bots; four one-to-one
      Mattermost DMs opened.
- [ ] Mattermost account linked in Console (**This is me**).
- [ ] World engine up on `127.0.0.1:8890`; dashboard open in a second window.
- [ ] `uv run director --loop 60` running **before** recording; one ambient beat has fired
      with no user input.
- [ ] Seed state loaded: private beliefs, relationship edges, empty feed.
- [ ] Scene-card export path works (`data/exports/`).
- [ ] Rehearsal run completed; transcript saved as `docs/demo-transcript.md`.
- [ ] Screen recording at 1440p or higher; notifications off; browser zoom 110%.
- [ ] Fallback: the recorded rehearsal video is on disk.

## Shot list

### 0:00–0:30 — Switch is the world

Open **Switch Console**, not Mattermost first. Show:

- the server status;
- the four character agent cards (`alice`, `emily`, `sophia`, `mia`) with their working
  directories and the live provider, and the `director` among `#world` participants;
- `#world` and the four DM rooms.

Cut to Mattermost. A beat has already fired with no user input; a character is replying.
Say:

> "These are four separate Switch agents in a live room, plus a director that posts the
> beats. Switch is the transport, the rooms and the sessions. Remove it and nothing moves."

### 0:30–1:30 — The user tells Alice a secret

Open the one-to-one DM with Alice (no `@` needed in a DM):

```
I've decided to leave the city at the end of the month. I haven't told the others yet.
```

Alice replies in character. The dashboard's Alice row gains:

```
I am leaving the city at the end of the month
key: user-leaving-city · source: user · confidence 1.00 · visibility private
```

Say: "That belief is written through Alice's scoped MCP token. Emily's token cannot read it."

### 1:30–3:00 — Alice and Emily meet

Switch to `#world`; the director posts:

```
@alice It is 18:30 at the café. Emily is here. You have something on your mind.
```

Alice replies. The director reads the room history, then addresses Emily:

```
@emily Alice says: "…" — how do you respond?
```

Alice decides whether to share. In the rehearsed run she does, with a hedge. Emily records
what she heard:

```
Alice is leaving the city at the end of the month
key: user-leaving-city · source: character:alice · confidence 0.80 · visibility shared
```

Emily calls `world__update_relationship` with a reason. The feed shows the public event.

### 3:00–4:00 — The consequence and the artifact

Dashboard:

- the belief matrix: Alice 1.00 (user), Emily 0.80 (Alice), Sophia/Mia absent;
- the provenance drawer: `user → Alice → Emily`, timestamps, confidence;
- the relationship edge: Emily → Alice trust moved, Emily → user trust moved.

Open the DM with Emily:

```
Hey, are you around?
```

Her reply references the belief and her changed view. Then open the **scene card** exported
by the director: scene summary, who knew what, provenance, relationship deltas, transcript
links.

> "This is the task the human and the agents did together: a scene and its provenance, not
> just a chat log."

### 4:00–4:45 — Switch is core

Back in Switch Console or a terminal:

```sh
docker compose --env-file .env -f deploy/switch/<tag>/docker-compose.yml down
```

Show that the director's next post fails and no agent session starts. The dashboard still
renders the last state.

> "Remove Switch and there is no transport, no rooms, no sessions, no world. The dashboard
> is only a read-only projection of what Switch and the world engine recorded."

Bring it back up:

```sh
docker compose --env-file .env -f deploy/switch/<tag>/docker-compose.yml \
  --profile collab --profile gateway up -d
```

Refresh the dashboard: Emily's 0.80 belief and the relationship delta are still there.

### 4:45–5:00 — Close

Show the README's **Why Switch is core** and **MCP model** sections, and the repo URL.

> "Four characters, one secret, provenance all the way down — built on Switch, with the
> world engine and MCP layer provider-agnostic."

## Recording notes

- Record Switch Console and Mattermost in one take; cut only dead time.
- Keep the model warm and the rehearsal transcript ready; do not debug live.
- If a live model call fails on camera, cut to the recorded rehearsal for that beat and
  keep going.
- Do not show `.env`, API keys, `.switch/`, `opencode.json`, or Mattermost admin pages.
- The director's `--loop` is the proof the world moves without the user; let one beat fire
  on camera before you interact.

## What the judges should remember

1. **Use of Switch:** five Switch agents, rooms and DMs; `docker compose down` stops the
   world.
2. **Technical execution:** one Compose stack, one world-engine command, four character
   registrations plus the director; the README reproduces it.
3. **Creativity/impact:** the secret ledger and provenance panel — a visible model of who
   knows what, not another chat UI.
4. **Presentation:** this shot list, the README's Switch section, and the 5-minute video.
5. **The task:** a human + four agents co-produced a scene and exported its scene card.
