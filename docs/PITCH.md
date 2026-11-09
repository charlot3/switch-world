# Geek Room pitch deck — outline

A deck for the official problem statement **Tavily Research Agent** (the **Pre-Meeting
Briefing Agent**). The Flip the Switch submission does not need this deck; it is the Geek
Room extra. The PPTX is `docs/switch-world-geekroom-pitch.pptx`; regenerate it with
`uv run python scripts/make-pitch-deck.py`.

## 1. Title

**Four Hearts — a social research room that prepares a pre-meeting briefing**

One subject, one meeting time, four characters, and a one-page artifact with sources.

## 2. The problem

Pre-meeting research is manual and easy to fake:

- someone skims the last 30 days of news the night before, or walks in unprepared;
- a generic agent answers from stale weights and invents sources — a confident wrong fact
  is worse than no brief;
- the brief is narrow: a company or person plus a meeting time, researched over the last 30
  days, in one page;
- that page needs source-backed findings, discussion points and open questions, not
  another chat log.

## 3. The product

Four characters research, then argue it out:

- give Four Hearts a subject and a meeting time;
- Alice, Emily, Sophia and Mia read the same Tavily findings in character;
- the room argues — Alice anchors, Emily challenges, Sophia frames, Mia pokes;
- every claim carries a source; every reply and silence is recorded;
- output: one page with findings, discussion points, open questions, sources and
  provenance.

## 4. The demo

Subject + meeting → Tavily → room → one page.

- `uv run director --briefing --subject Anthropic --meeting "2026-11-18T10:00:00+09:00"`;
- 2–3 news-shaped Tavily queries cover the last 30 days; each distinct result becomes a
  public `world_event` and a shared belief (`source event:<id>`);
- the four characters discuss the findings through the same group-turn pipeline; silent
  characters are recorded;
- `briefing.py` writes `briefing-<slug>.md` and records a `briefing` event pointing at it;
- the offline fixture is labelled; a live key takes the same path.

Screenshots: `docs/geekroom-dashboard.png` and `docs/geekroom-ledger.png`.
Example page: `docs/briefing-example.md`.

## 5. Architecture

```
room / dashboard ── world engine (MCP) ── beliefs · relationships · events
                         │
              Bifrost ───┴─── Tavily
        (model control plane)  (only web access)
```

- Bifrost is the model control plane for the **Four Hearts profile**: routing, fallbacks,
  per-character token budgets and request logs;
- Tavily is the only web access; the same adapter serves the briefing and
  `world__search_web`;
- the ledger records who learned what, from where; the scene card exports the same
  provenance;
- Switch remains the Flip transport; the briefing demo runs without it.

## 6. Proof

- 435 passing tests and 85% coverage; the briefing has an end-to-end test on the offline
  fixture;
- `docs/briefing-example.md` is a labelled offline-fixture page: findings, room discussion,
  open questions and provenance;
- Bifrost profile: OpenCode Go DeepSeek V4.1 Flash through the gateway, with
  `data/logs/bifrost.jsonl`;
- live Tavily is a drop-in: set `TAVILY_API_KEY` and unset `TAVILY_OFFLINE`; the fixture is
  never presented as live.

## 7. Roadmap

- record the demo with a live Tavily key; keep the labelled fixture as the fallback;
- provider-per-character routing through Bifrost (config, not a rewrite);
- briefing templates per meeting type, and a diff against the last brief;
- ship the one-page artifact and its provenance, not a chat log.

## Submission facts

| Item | Value |
| --- | --- |
| Problem statement | Tavily Research Agent |
| Description | Pre-Meeting Briefing Agent |
| Portal | HackCulture → Manage → Submissions → Problem Statements & Prototype Submission |
| Deadline | 2026-11-15 18:29 UTC = 2026-11-16 03:29 JST |
| Tavily checkbox | Pre-Meeting Briefing Agent |
| Requirements | Public repo + README; PPT required; demo video optional; one final project; team 1–4 |
