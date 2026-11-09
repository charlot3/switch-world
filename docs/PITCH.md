# Geek Room pitch deck — outline

A 10-slide deck for **Innovative Solution for AI Agents & Intelligent Systems**.
The Flip the Switch submission does not need this deck; it is the Geek Room extra.

## 1. Title

**Four Hearts — a social world with a memory you can audit**

One human showrunner, four AI characters, a provenance-tracked secret ledger, and a
single scene card that survives the chat.

## 2. The problem

Multi-agent roleplay loses the two things that make it useful:

- **canon** — a character invents a fact, a relationship moves with no record, and the
  story can no longer be continued;
- **provenance** — nobody can say who learned what, from whom, or how confident they were.

A writers' room, a tabletop GM or a social-simulation researcher needs both.

## 3. The product

A small social world:

- four characters with different models, voices, private facts and relationships;
- a **secret ledger** where every belief has a source, confidence and visibility;
- an **authored canon** (five beats, three branches, invariants) so freedom does not
  destroy the worldline;
- a **scene card** exported at the end: who knew what, from whom, and what moved.

## 4. Demo (screenshot)

Use `docs/geekroom-dashboard.png` and `docs/geekroom-ledger.png`.

The human says one thing to Alice. Alice decides whether to tell Emily. The dashboard
shows Alice at 1.00 (user), Emily at 0.00, the branch the ledger chose, and the real-world
event every character just saw.

## 5. Architecture

```
human ── Switch / dashboard ── world engine (MCP) ── beliefs · relationships · events
                                     │
                          Bifrost ───┴─── Tavily
                     (all model calls)   (real-world input)
```

Switch is the transport in the Flip edition and optional in the Geek Room edition. The
world engine and the canon are the same in both.

## 6. Bifrost: the model control plane

- every Alice/Emily model call goes through `POST /v1/chat/completions`;
- per-character model, fallbacks, temperature and token budget in `world/models.json`;
- request log: character, model, tokens, latency, success/error;
- local guard `data/bifrost_budget.json` + gateway UI + `GET /api/bifrost/usage`;
- evidence: `data/logs/bifrost.jsonl`, Bifrost dashboard at `:8080`.

The packaged Four Hearts profile uses DeepSeek V4.1 Flash through Bifrost; swapping one
character to another provider is a config change, not a rewrite.

## 7. Tavily: the real-world input

- the scheduler turns one search into a public `world_event`;
- every character records the same event with source `event:<id>` — shared-event memory;
- `world__search_web` gives characters live retrieval in DMs;
- the World Feed and matrix show the input, the source URL and the confidence;
- without a key the offline fixture is clearly marked, never passed off as live.

## 8. Two editions, one codebase

| Flip the Switch | Geek Room |
| --- | --- |
| Switch is the transport | Bifrost + Tavily are the additions |
| four Switch agents | local Bifrost character runner |
| scene card + canon | same scene card + governance evidence |
| deadline 2026-11-08 | deadline 2026-11-15 |

The branch/tag split keeps the Flip demo frozen while the Geek Room layer evolves.

## 9. Proof

- 426 passing tests and 85% coverage for the world engine, canon, Bifrost client,
  Tavily client and scene;
- a real Bifrost → DeepSeek V4.1 Flash café scene with token logs;
- a labelled offline Tavily fixture event in the matrix and feed; a live key is a drop-in;
- screenshots and a reproducible `docs/GEEKROOM.md` runbook;
- honest scope: no 3D/voice/in-loop image generation; four character profiles share one
  packaged model by default.

## 10. Why it matters / next

Writers, tabletop GMs and social-simulation researchers get a **continuity-safe scene
beat** and a **story-bible artifact**, not another chat log.

Next: provider models per character, a live Tavily key in the demo, a scheduler in the
background, and a deck/video cut for the Geek Room submission.
