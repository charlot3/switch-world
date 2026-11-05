# Scene protocol — turn model, whisper, boundaries, studio

This is the implementation contract for the next slice. It is deliberately concrete so
the backend and the dashboard can be built in parallel.

## Vocabulary

- **Turn** — one user line and everything the room does in response.
- **Plan** — who speaks, who reacts, who is silent, and whether the reply is a chorus.
- **Beat** — one recorded line/action in a turn.
- **Mode** — `speech`, `action`, `reaction`, `chorus`, `whisper`, `whisper_reply`,
  `silence`.
- **Presence** — who is physically in the scene. A character who leaves is absent until
  the scene ends or a later beat brings them back.

## Turn plan

A user line is classified first (`director/social.py`). The plan is deterministic:

- named addressee (`@alice`, "Alice, ...") → that character is primary; 0–2 others react;
  everyone else is silent.
- shared-fact topics (`small-talk`, `personal`: time, food, weather, "are we still on")
  → a chorus of 2–3 speakers, each ≤12 words, same content with a different texture; at
  least one present character is silent.
- private/intimate topics (`private-emotional`, `body`, `contact`) → one primary and one
  reactor with a different stance; the rest silent. Never a four-person chorus.
- default → one primary, 1–2 reactors, the rest silent.

Every turn records a `turn_plan` event with the plan and a `turn_id`. Every beat records
`metadata`:

```json
{
  "turn_id": "t-...",
  "mode": "speech|action|reaction|chorus|whisper|whisper_reply|silence",
  "role": "primary|reactor|chorus|silent",
  "expression": "neutral|smile|cold|hurt|alarmed",
  "target": "alice",
  "chorus": true
}
```

`events.metadata_json` is added by an idempotent migration. `record_event(..., metadata=...)`
accepts it; `/api/state` returns `metadata` on each event; `phone_history` ignores every
non-DM kind.

## API

### `POST /api/group/say`

Request: `{message, characters?, timeout?}`. Response:

```json
{
  "turn": {
    "id": "t-...",
    "plan": {"primary": "alice", "reactors": ["emily"], "silent": ["sophia", "mia"],
             "chorus": false, "topic": "small-talk"},
    "lines": [
      {"character": "alice", "mode": "speech", "role": "primary",
       "text": "...", "expression": "smile", "event_id": 1}
    ],
    "missing": []
  },
  "verdicts": {"alice": {"stance": "answer", "reason": "..."}},
  "replies": [{"character": "alice", "text": "..."}]
}
```

Keep `replies`/`verdicts` for compatibility. A planned speaker who does not answer becomes
a `silence` beat, not an error. The turn must complete within 35s.

### `POST /api/group/whisper`

Request `{to, message, timeout?}`. Deliver the words only to the target. If a private
Switch room/DM is not available, use the target's private Bifrost/phone model and mark the
response `{"transport": "staged"}`; never claim transport privacy. Record the words as a
private `whisper` event and the target's answer as a private `whisper_reply` event. Post a
public prompt to 1–2 other present characters: they saw the whisper happen, did not hear
the words, and react with an action or at most half a line. Their prompts must not contain
any token from the whispered text. Record their `reaction` beats publicly. UI shows the
private lines with a lock, only to the player.

### `GET /api/studio/summary`

Return:

```json
{
  "health": {"world": true, "switch": true, "mattermost": true, "gateway": true,
             "bifrost": true},
  "clock": {"now": "...", "mode": "mock"},
  "current_beat": {"id": "cafe", "title": "...", "time": "18:30"},
  "next_beat": {"id": "aftermath", "title": "...", "time": "19:20"},
  "agents": [{"id": "alice", "name": "Alice Moreau", "role": "...",
              "friend": false, "absent": false, "last_event": "..."}],
  "rooms": [{"name": "world", "room_id": "..."}],
  "recent": [{"kind": "dialogue", "summary": "..."}],
  "done_beats": ["cafe"],
  "arc_complete": false
}
```

Probe external services with ≤300ms timeouts and never block the dashboard on a failed
probe; a false flag is enough. The world engine itself is always true.

## Boundary consequences

`social.classify(text)["boundary"] == "violation"` for uninvited physical contact
(forced kiss, grabbing, lifting clothing). In a group turn:

1. Do **not** record the user's act text as a `dialogue` event.
2. Record a public `boundary_violation` event: "The user crossed a physical boundary with
   Alice." No act details.
3. The target gets a consequence prompt (no explicit act) and a hard refusal; apply the
   social deltas. The target is marked absent for the rest of the scene.
4. Every other present character records a private belief with
   `proposition_key="user-crossed-a-line"`, `source="observation"`, a distinct confidence
   (Alice 1.0, Emily 0.9, Sophia 0.85, Mia 0.8). They may react publicly.
5. The UI dims/removes the target, shows the reaction, and marks the event distinctly.
   The act is cut; only the consequence is shown.

Add `mark_absent`, `is_absent`, `absent_characters` to `WorldService` (use the `meta`
table; reset clears it). Group sends filter absent characters.

## UI requirements

- **Scene turn log**: a vertical transcript with `【Alice】` speaker plates, full text,
  user lines, and action/reaction lines in italic. A chorus renders as one stacked block
  of 2–3 names; silence dims the portrait. Do not render the scene as phone bubbles.
- **Turn playback**: show the planned stage direction immediately, then beats as they
  arrive; `Next` steps through the turn; typewriter only on the current speech beat.
- **Whisper**: a target picker + whisper toggle on the say bar. Private lines get a lock
  and are visible only in the player's scene log; observers' reactions are public.
- **Boundary**: target leaves/dims, a distinct boundary event in the log, witness beliefs
  appear in the ledger/World view.
- **Studio**: a new rail view with health chips, current/next beat, "Advance & play",
  agents (friend/absent/last event), rooms and a recent feed. Settings remains preferences
  and demo/debug controls.

## Constraints

- SFW, all characters adults, no explicit content, no rendered act, no coercion rewarded.
- English UI; no visible CJK strings.
- Keep the existing phone DM, time machine, group endpoint and tests working.
- Backend: add tests under `tests/`; run `uv run pytest -q`.
- Frontend: vanilla HTML/CSS/JS, no new dependency; `node --check web/app.js`.
- Do not edit README/docs in the implementation branches; the integrator updates docs.
