# Take protocol — the recordable demo layer

A **take** is a short linear recording script on top of a scenario. It is not a second
world engine: loading a take resets the world DB, loads its scenario, and starts scene 0.
The model writes lines; code owns the scene order, cues, fallbacks, endings and state.

## Take JSON

`world/takes/<id>.json`:

```json
{
  "id": "w3-quiet-route",
  "title": "The Quiet Route",
  "scenario": "w3-quiet-route",
  "warm": ["alice"],
  "scenes": [
    {
      "id": "quiet-close",
      "title": "After close",
      "place": "the bookshop, after close",
      "cast": ["alice"],
      "art": "/static/assets/scenes/beat-date-alice.jpg",
      "opening": ["You came. I saved the window seat."],
      "choices": ["You said Friday. I listened.", "That skirt is unfair."],
      "cues": [
        {"on": "user_line", "match": "skirt|friday|wear", "op": "remember_preference",
         "key": "user-prefers-short-skirt", "proposition": "The user prefers short skirts.",
         "tags": ["skirt"]}
      ],
      "fallback_lines": {"alice": "You said Friday. I listened."},
      "next": "quiet-walk",
      "must_change": true
    }
  ],
  "ending": "good-confession"
}
```

- `next` is `null` on the last scene. `POST /api/takes/next` refuses to advance if the
  current scene has no player turn or cue yet (`must_change`), unless `force: true`.
- `fallback_lines` are the authored safety net: if the planned speaker misses the 12s
  deadline, the director records the fallback with `metadata.generator="authored"`.
- `cues` run deterministically after a turn/choice: `remember_preference`, `give_item`,
  `set_outfit`, `advance_time`, `mark_absent`, `ending`. A cue never invents prose.
- `warm` lists speakers to pre-address at load (a tiny prompt to start the session).

## API

- `GET /api/takes` → list (id,title,scenario,scene count, ending)
- `POST /api/takes/{id}/load` → reset + scenario + scene 0; returns `{take,scene,state}`
- `GET /api/takes/current` → `{take,scene,index,state}`
- `POST /api/takes/next {force?}` → advance; applies the next scene's opening/cues; returns
  `{take,scene,index,state,changed}`. `changed` is false if nothing moved.
- `POST /api/takes/cue` is internal; the director applies cues after the group turn.
- Scenario endpoints remain; a take references a scenario.

## Turn idempotency and revision

`POST /api/group/say` and `/api/takes/next` accept optional:

```json
{"request_id": "r_...", "expected_revision": 7}
```

- `request_id` 8–64 chars `[A-Za-z0-9_-]`; the same id + same payload returns the stored
  response with `replayed: true`, no new events.
- `expected_revision` mismatch returns 409 `{error:"STALE_REVISION", revision, ...}`.
- `GET /api/state` returns `revision` (monotonic per DB) and `turn`.
- Store idempotency in a small `idempotency(scope, request_id, digest, response_json,
  created_at)` table; keep the last 500 per scope. This is a demo reliability layer, not
  a full multi-user transaction system.

## Social upgrades borrowed from the reference

1. **Action mode**: classify a user line as `result` (player's own body/speech/item),
   `attempt` (anything affecting an NPC), `continue` (empty/"continue"), or `wait`.
   Attempts on NPCs get an NPC response from the spectrum below; they are never
   auto-success.
2. **Response spectrum**: `refuse`, `negotiate`, `limited`, `surface`, `sincere`.
   Keep our existing `answer/tease/deflect/refuse/hard_refuse` as the *topic* gate; add a
   `response` field to the group plan and prompt. Refusal is a normal outcome.
3. **Scene-change invariant**: every scene/take advance changes at least one recorded
   fact/event; `next` returns 409 if nothing changed and `force` is false.
4. **Context budget**: assemble DM/group prompts through one projection with a hard
   ~12 KB cap; trim old DMs/scene lines first, keep the relationship/social block and
   the latest 6 memories. This reduces latency and drift.
5. **Off-screen beat**: `POST /api/clock/advance {offscreen:true}` records one public
   `offscreen` event for an absent/present NPC (promise maturing, rumor, errand), no model
   call. The time machine can show it; it never changes the user's beliefs by itself.
6. **Safety pause**: `POST /api/safety/pause {paused:true}` stores a DB meta flag; while
   paused, group/DM writes return 423 with a non-judgmental message. The UI has a pause
   control in Studio and resumes explicitly.
7. **Validation**: `scripts/validate-takes.py` checks every take/scenario:
   file id matches, scenario exists, cast ids, scene refs, art paths exist, cues have a
   known op, fallback lines have cast ids, ending exists. `tests/test_takes.py` runs it.

## Connection-based planner

The group planner receives `service.connections()` and the per-character edges:

- named addressee wins;
- otherwise primary = highest affinity to the user, or (for an intimate probe) the
  character with the highest relevant tension;
- reactor = the present character with the highest tension toward the primary (a real
  character↔character stake);
- chorus only for shared facts, max 3;
- everyone else silent; only planned speakers are posted to.

## UI

- **Takes** shelf (or Worlds): load, current take/scene, **Next scene**, rehearsal/fallback
  badge, ending card.
- Story status HUD: scene title, location, turn number, `REAL xN` / `MOCK`.
- `Next scene` is disabled until a turn/cue has changed something.
- Authored fallback lines render with a small `authored` chip, not as an error.
- Pause/resume control in Studio; paused dialog explains the state without scolding.
- Keep the existing turn log, whisper, boundary, outfit and phone drawer.

## Constraints

- SFW 17+, adults, no explicit content; the reference's adult mechanics are used only as
  interaction/engineering patterns.
- English UI, no visible CJK.
- Vanilla JS, no new dependency.
- Backend tests must stay green; new tests for takes, cues, idempotency, revision,
  scene-change, planner, pause.
- Do not edit README/docs in the build agents; the integrator updates them.
