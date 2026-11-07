# v2 status

Branch: `v2-architecture` (draft PR into `geekroom`). **Not deployed.** The
public demo still runs `geekroom`.

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

## Deliberately not done yet

- **Step 9 — modular dashboard.** `web/app.js` is ~5,500 lines. Splitting it
  into modules needs a browser-based visual smoke test first; we have only
  `node --check` today. Left for a dedicated pass so the live dashboard is not
  put at risk.
- **Step 10 — delete the compatibility shims.** `director/`, `world_engine/`
  and `gateway/` still re-export the new modules because the demo entrypoints,
  the director CLI and the tests import them. Deleting them is the last commit,
  after Step 9 and a full test import migration.
- **Env-gate cleanup.** 16 tests assume dev mode and 7 assume switch mode; they
  fail when the whole suite is run with `WORLD_DEV=0` or
  `WORLD_AGENT_MODE=cloud`. CI runs the default mode; the plan's env gate needs
  per-test skips or explicit settings.

## Commands

```bash
make check                       # ruff + compileall + pytest + node --check
uv sync --frozen && uv run pytest -q
python -m world_engine --help
python -m director --status
```

## Design rules

- `domain/` is stdlib-only; `application/` imports domain + ports; `adapters/`
  implements ports; `interfaces/` drives the app; `container.py` is the only
  place that names a concrete adapter.
- The SQLite adapter is the only module with SQL.
- A turn is recorded in one order: user line, plan, delivery, one sanitise
  pass, writes, beats, at most one relay.
- The dashboard is a projection; it must never be a second source of truth.
