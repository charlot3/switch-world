# v2 status

Branch: `v2-architecture`. Tag: **`v2.0.0-rc`** (local; not pushed, not merged, not
deployed). `main` and `geekroom` are unchanged and the public demo still runs the
`geekroom` edition.

## Landed

| Step | What | Gate |
| --- | --- | --- |
| 0 | Hermetic tests, ruff E/F, `make check`, free GitHub Actions (3.11-3.13, lint, web, wheel smoke) | CI green |
| 1 | `switch_world` package: frozen `Settings` + `load_settings`, `Container`, `create_app(service, settings)`; no import-time app | 210 tests |
| 2 | `WorldStore` (reader/writer/admin) is the only SQLite code; `WorldService` is a facade; no raw SQL in scenarios/takes; `/api/state` one snapshot | 228 tests + 168-op differential |
| 3 | Ports for transport/model/clock/content/artifacts; Scripted/Bifrost/DeepSeek models; Switch/CloudRoom/Local transports; contract tests | 282 tests |
| 4 | One turn pipeline (`TurnRecorder`); group is a shim; cloud group writes beliefs/relationships; duplicate id = silence | 295 tests + 36-case differential |
| 5 | DM and whisper on the same pipeline; one sanitiser; capability-driven private rooms; observer silence | 331 tests + DM/whisper differential |
| 6 | One beat pipeline (`run_beat`); four runners are wrappers; cloud beats need no Switch | 350 tests + beat differential |
| 7 | Typed HTTP schemas, route package, one error mapper, no client construction in handlers; MCP 14 tools with actor scoping | 383 tests + route/OpenAPI/authz |
| 8 | Wheel ships world/web/IDENTITY; Settings content root; real CLIs; Docker installs the wheel; CI wheel smoke | 389 tests + clean-venv smoke |
| 9 | Modular dashboard: `web/js/{main,api,state,format,vocab}.js`, `web/js/render/*`, `node --test`, generated `cast.js`/`vocab.js`; no build step | node --check + node --test + contract drift |
| 10a | Port the last real logic out of the v1 packages into `switch_world` (`facade`, `scenarios`, `takes`, `studio`, `social`, `canon`, `clock`, `prompts`, `beat_runners`, `simulate`, `tavily_beat`, `switch_log`, cloud/Switch/Bifrost adapters) | 402 tests + `make check` |
| 10b | Migrate every caller to `switch_world`; delete `world_engine/`, `director/`, `gateway/`, the local `mcp/` and `web/app.js`; point console scripts and the wheel at `switch_world`; add architecture guards | 414 tests + `make check` + wheel smoke |
| 10c | Docs are MCP-first and match the tree; in-process CLI tests; tag `v2.0.0-rc` | **423 tests, 85% coverage**, full gate below |

## Coverage

`pytest --cov=switch_world --cov-report=term` reports **85%** (6076 / 7126 statements).

The largest remaining gaps are long-tail branches, not missing surfaces:

- `adapters/persistence/store.py` (90%) — rare migration and idempotency branches;
- `application/takes.py` (77%) and `application/scenarios.py` (74%) — loader error paths;
- `interfaces/mcp/tools.py` (62%) — thin `world__*` wrappers whose logic is covered through
  the store contract; the tool contract itself is pinned by `test_mcp_tools.py`;
- `application/beat_runners.py` (74%) — Bifrost/Switch/cloud runner branches that need a
  provider fake;
- `interfaces/cli/director.py` (55%) — the `--switch`, `--tavily-event`, `--bifrost` and
  `--arc` operator paths, exercised by the subprocess smoke rather than in-process.

## Deliberately not done yet

- **Env-gate cleanup.** Some legacy tests assume dev mode and some assume switch mode, so
  they fail when the whole suite is run with `WORLD_DEV=0` or
  `WORLD_AGENT_MODE=cloud`. These are pre-existing and recorded in the step 10 gate
  report; CI runs the default mode. The fix is per-test skips or explicit settings, not a
  code change.
- **Merge and deploy.** The rc is local. Promoting it means pushing the tag, opening the
  draft PR into the target branch and re-running the Docker/browser smokes against that
  environment.

## Commands

```bash
make check                       # ruff + compileall + pytest + node --check/node --test + contract drift
make cov                         # pytest --cov=switch_world (85%)
uv sync --frozen && uv run pytest -q
python -m switch_world.interfaces.cli.world --help
python -m switch_world.interfaces.cli.director --status
```

## Design rules

- `domain/` is stdlib-only; `application/` imports domain + ports; `adapters/` implements
  ports; `interfaces/` drives the app; `container.py` is the only place that names a
  concrete adapter.
- The SQLite adapter is the only module with SQL.
- A turn is recorded in one order: user line, plan, delivery, one sanitise pass, writes,
  beats, at most one relay.
- The dashboard is a projection; it must never be a second source of truth.
- MCP is the cast's only write path, and token → actor is resolved at the edge while
  authorization stays in the store.
