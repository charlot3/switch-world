# Scenario protocol — recordable demo worlds (lite)

The demo needs several loadable worlds, not one long café session. The full pack/run/fork
engine is specified in the design notes; this slice ships the part needed for recording:

- a **scenario** is a read-only JSON preset;
- loading a scenario resets the world DB and applies its seed;
- one active scenario at a time;
- switching is a reset + seed, not a second engine on another port;
- a fork is two scenario presets with the same cast and different ledgers.

The existing canon, turn model, whisper, boundary and Studio remain unchanged.

## Scenario JSON

`world/scenarios/<id>.json`:

```json
{
  "id": "w3-quiet-route",
  "title": "The Quiet Route",
  "seed": 3003,
  "clock": {"now": "2026-11-03T19:10:00+09:00", "mode": "mock", "scale": 1.0},
  "cast": ["alice"],
  "friends": ["alice"],
  "absent": [],
  "outfits": {"alice": {"id": "date-skirt", "label": "date skirt", "art": "/static/assets/portraits/alice-date-skirt-cg.jpg", "reason": "because you said you like short skirts", "source_belief": "user-prefers-short-skirt"}},
  "cast_art": {"alice": "/static/assets/portraits/alice-date-skirt-cg.jpg"},
  "scene_art": "/static/assets/portraits/beat-bookshop-evening.jpg",
  "place": "the bookshop, after close",
  "item": {"id": "gift-book", "label": "a wrapped first edition", "holder": "user"},
  "relationships": [
    {"a": "alice", "b": "user", "trust": 0.78, "closeness": 0.72, "tension": 0.08}
  ],
  "beliefs": [
    {"holder": "alice", "proposition": "The user prefers short skirts.", "key": "user-prefers-short-skirt", "source": "user", "confidence": 0.9, "visibility": "private"}
  ],
  "opening": {
    "title": "After close",
    "line": "You came. I saved the window seat.",
    "choices": ["You said Friday. I listened.", "That skirt is unfair.", "Tell me about the book."]
  },
  "ending": {
    "id": "good-confession",
    "label": "GOOD END — The Confession",
    "tone": "good",
    "evidence": ["Alice closeness >= 0.72", "Emily holds the secret from Alice", "no boundary"]
  },
  "notes": "One live Alice session; date outfit; memory callback."
}
```

Rules:

- `cast` is the present set; characters not listed are reachable by phone but not in the
  scene. `absent` starts empty unless a scenario deliberately starts after a walkout.
- Relationship rows are upserts for the listed pairs; other seeded pairs are reset to the
  normal seed.
- Beliefs are upserts by `(holder, key)`; source may be `user`, `observation`, or
  `character:<id>`.
- `outfits` is a small map on the character; its `art` overrides the stage/profile CG.
- `scene_art` overrides the beat CG for the scenario.
- `item` is shown as a chip; no inventory economy yet.
- `ending` is a demo card, not a live predicate engine in this slice. Loading the good or
  bad preset is the fork for recording. `POST /api/endings/evaluate` returns the card and
  records an `ending` event.

## API

- `GET /api/scenarios` → `{scenarios: [{id,title,seed,ending,cast,notes}]}`
- `POST /api/scenarios/{id}/load` → reset + seed, returns `{scenario, state}`
- `GET /api/scenarios/current` → `{scenario}` or `{scenario:null}`
- `GET /api/state` adds `scenario`, `outfits`, `cast_art`, `scene_art`, `item`,
  `connections`
- `POST /api/endings/evaluate` → `{ending, evidence}`, idempotent per scenario

Scenario loading is dev-only (`config.DEV_MODE`), like the demo reset. A switch clears the
dashboard's phone thread, selected cast and turn playback.

## Service

- `load_scenario(scenario: dict)` applies the seed; `reset` first.
- `set_outfit(character, outfit_id, reason, source_belief_id)` validates the belief exists
  and the outfit is declared; writes an `outfit_change` event with metadata.
- `items()` / `give_item(item_id, to)` minimal table.
- `connections()` projects all unordered character↔character pairs from
  `relationships` to `{a,b,affinity,tension,label,shared_secret_count}` with labels
  `close|steady|strained|rival|distant`. `GET /api/state` includes it.
- `clock.scale` (default 1.0); `POST /api/clock/mode {mode, scale}` uses it in realtime.
  The UI must show `REAL x60` when scale != 1.

## UI

- **Worlds** rail view: scenario cards with title, cast dots, seed, ending badge and
  **Load & play**; a current-scenario chip and **Reset**.
- Story uses scenario `scene_art`, `cast_art`, `item`, opening title/line/choices.
- Outfit badge opens the source belief (the memory → outfit chain); the stage CG swaps.
- Ending card overlay with evidence chips.
- World Tree gets a cast↔cast lens toggle; the Connections panel uses `connections`.
- All English; SFW; no visible CJK.

## Demo scenarios to seed first

`w1-gift` (bookshop gift), `w2-two-clocks` (17:40 → 18:30), `w3-quiet-route` (solo date,
outfit + preference), `w4-three-of-us` (three-person night market), `w5-good` and
`w5-bad` (same setup, opposite ending), `w6-long-tuesday` (existing arc fallback).

The exact edge/belief values are in the demo design notes; keep them small and auditable.
