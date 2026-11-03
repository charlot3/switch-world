# Director

The director is the world clock. It is a deterministic Python script that posts addressed
scene turns into Switch rooms, reads the room history to chain turns, and advances the world
state. It is registered as a Switch agent (`director`) so its messages have a real sender;
it does not run an OpenCode or Claude session.

## Why a script

- The demo needs deterministic ordering: Alice speaks, then Emily, then the feed.
- A beat must not double-fire when the process restarts.
- Cost and latency stay bounded: the LLM is used for dialogue, not for scheduling.

This is "authored beats, model performance."

## Live path (Console-managed)

The live director is a Console-managed Switch agent named `director`, owned by the user and
added to `#world`. It does not run a model session. `SwitchClient` reads
`director/.switch/agents/director.json`, discovers the `world` room with `list_rooms`, posts
with `POST /agents/{id}/message`, and reads
`GET /agents/{id}/rooms/{room_id}/history`.

```sh
uv run director --tell-alice   # seed the user's secret in the world state
uv run director --switch       # live café beat: @alice, wait, @emily, wait
```

`run_switch.py` decides whether Emily learned the secret from the world state
(`source: character:alice`), not from the fact that she replied.

## Manual alternative: register with `POST /agents`

The script can also register once with `POST /agents` using a **registration key created in
the Gateway under the user's account** — not the deployment bootstrap token. An agent
registered with the bootstrap token belongs to a separate account, and the characters will
refuse its messages.

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
```

Store the returned `id` / `api_key` in `DIRECTOR_AGENT_ID` / `DIRECTOR_API_KEY`. Invite the
director to `#world`; it is never a member of a private DM.

## Interface

```sh
uv run director --simulate          # local authored café beat (no Switch)
uv run director --switch            # live Switch beat in #world
uv run director --tell-alice        # seed the user's secret
uv run director --status            # clock and belief matrix
```

Environment: `SWITCH_API`, `DIRECTOR_AGENT_ID`, `DIRECTOR_API_KEY`, `WORLD_ROOM_ID`,
`WORLD_ENGINE_URL`, `WORLD_TOKEN_DIRECTOR`.

## Beat plan for the demo day

| # | Beat | Participants | Room | Purpose |
| --- | --- | --- | --- | --- |
| 1 | Morning shop | Alice | `#world` | establish the day; Alice is distracted (optional) |
| 2 | Truck lunch | Mia | `#world` | ambient life; Mia hints at money trouble (optional) |
| 3 | Café, 18:30 | Alice, Emily | `#world` | **the demo beat**: Alice decides whether to share |
| 4 | Aftermath | Emily | `#world` | optional: Emily reacts in public, not in a DM |
| 5 | Group roundup | all | `#world` | feed recap; Sophia notices the tension |

Beats 1, 2 and 4 are optional if time is short. Beat 3 is the demo. The scene card is
exported after beat 3.

## Eligibility and ordering

Beats run in order; the director **does not skip** the café beat. The café beat is eligible
only when `world__who_knows("user-leaving-city")` shows Alice holding a belief with
`source_kind=user`. Until the user tells Alice the secret, `--loop` runs only the ambient
beats (morning, lunch) and then waits. After the secret is recorded, the café beat becomes
eligible and the loop runs it. The aftermath and roundup wait until the café beat finishes.
This is what makes the "world moves before the user joins" shot safe: the loop cannot run
the demo beat early.

## A beat

```python
beat = world.next_beat()                 # pending beat from SQLite
world.start_beat(beat.id)                # pending -> running under a lock
switch.post(beat.room_id, f"@{beat.character} {beat.prompt}")
reply = switch.read_since(beat.room_id, beat.started_at)   # Alice's actual line
switch.post(beat.room_id, f"@{beat.other} Alice says: {reply!r} — how do you respond?")
world.wait(beat.dwell_seconds)           # bounded wait for the second reply
world.record_event(
    kind="scene_turn",
    participants=beat.participants,
    summary=beat.summary,
    visibility="public",
)
world.export_scene_card(beat.id)         # the artifact
world.advance_clock(beat.minutes)
world.finish_beat(beat.id)               # running -> done
```

`read_since` uses the Switch room-history route
(`GET /agents/{director_id}/rooms/{room_id}/history?since=…`) or the `read_context`
operation. Verify the exact route on Day 3. If it is unavailable on your build, pre-author
both lines and label the scene as scripted; do not claim the model decided the disclosure.

## Turn-taking rule

One character is addressed at a time. A beat prompt must not contain another agent's `@name`
— write "Emily is here", not "@emily is here" — or both sessions wake and the chat becomes
unreadable. The director addresses Emily only after it has read Alice's reply.

## Failure handling

| Failure | Behavior |
| --- | --- |
| Switch post fails | retry twice with backoff; if still failing, mark the beat `blocked` and exit non-zero |
| A character does not reply within the dwell | continue; record `no_reply`; the feed stays honest |
| Alice withholds | run the authored second prompt: Emily asks directly once. If she still withholds, the scene card records a non-disclosure; the demo has a second cue |
| Process killed mid-beat | beat stays `running`; the next run sees the stale lock and offers `--resume` or `--force` |
| Two directors started | a lock file in `director/.lock`; the second exits |
| World engine down | refuse to start; the chat is not the source of truth |
| Director's message refused | the director is not owned by the user or not in `#world`; see "Registration and ownership" |

## What the director does not do

- It does not invent dialogue.
- It does not copy private belief text into a room. It calls `world__who_knows` only to
  decide whether the café beat is eligible (does Alice hold a belief sourced from `user`?),
  and it never uses the private text in a prompt.
- It does not run a real-time clock. The world clock advances by beats.
- It does not read a private DM.
