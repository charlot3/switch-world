# switch-world v2 — final refactor plan

Worktree: `/Users/charlot3/orca/workspaces/hackathon/handfish/subs/switch-world/.claude/worktrees/v2-architecture`
Branch: `v2-architecture` (HEAD 007f409). Target: push to `origin` (public `charlot3/switch-world`), open a draft PR into `main`. `main` and `geekroom` are not modified, nothing is deployed from v2. Paths below are relative to the worktree root unless absolute.

**Decision:** adopt **“Ports and Adapters core”** (2 of 3 judges), amended with the feature-change advantage from the vertical-slices proposal and the staged no-break discipline from the Layered Modulith proposal. Amendments that address the judges’ criticisms:

- Six ports, not seven: drop `AuthPort` (token lookup is a 20-line edge concern in `interfaces/http/deps.py` and `interfaces/mcp/tools.py`; authorization is a *domain* policy). Keep `Clock`, `ArtifactStore` and `ContentStore` because each fixes a verified defect (untestable time, getter-side-effect exports, per-call canon/social re-reads).
- Split `WorldStore` into `WorldReader` / `WorldWriter` / `WorldAdmin` so it is not one 35-method god protocol.
- Split the big-bang step 4 into three shippable commits (group, then DM, then whisper), and split packaging (step 8) from shim deletion (step 10).
- Keep the final layout under one package, `switch_world/`, with feature-shaped application modules so a feature is one module + one router file + tests, not four layers.

---

## 1. Chosen architecture

### 1.1 Dependency rule (enforced in CI)

```
domain/        -> stdlib only. No sqlite3, httpx, fastapi, os.environ.
application/   -> domain + domain.ports only. No adapters, no interfaces.
adapters/      -> domain.ports + stdlib/third-party HTTP/SQL clients.
interfaces/    -> application + container (FastAPI, MCP, CLI are driving adapters).
config.py      -> Settings only. container.py -> the ONLY module that names concrete adapters.
```

This makes the three audited cycles impossible: `world_engine/api.py -> director.*`, `world_engine/mcp_server.py -> gateway.tavily`, and `gateway/bifrost.py -> world_engine.config`.

### 1.2 Final directory tree

```
switch-world/                                  # worktree v2-architecture
├── pyproject.toml                             # packages = ["switch_world"]; force-include resources
├── uv.lock                                    # CI uses uv sync --frozen
├── Makefile                                   # check = lint + test + web
├── ruff.toml
├── mypy.ini                                   # ratchet: domain + application first
├── .github/workflows/ci.yml                   # tracked (currently '?? .github/')
├── README.md                                  # MCP-first; edited in every step
├── docs/{ARCHITECTURE.md,MCP.md,DECISIONS.md}
│
├── switch_world/
│   ├── __init__.py
│   ├── config.py                              # frozen Settings + load_settings(env) - no import reads
│   ├── container.py                           # Container + build_container(settings)
│   ├── errors.py                              # Error taxonomy used by interfaces
│   │
│   ├── domain/                                # stdlib only
│   │   ├── ids.py                             # CharacterId, RoomId, TurnId, MessageId (NewType)
│   │   ├── models.py                          # Actor, Character, Belief, Event, Item, Outfit,
│   │   │                                      # Relationship, WorldWrite, WorldSnapshot, ClockReading
│   │   ├── protocol.py                        # SCENE_PROTOCOL, event vocabulary, cast/beat/take order
│   │   ├── plan.py                            # plan_turn, addressing, roles, one-hop relay rules
│   │   ├── policy.py                          # sanitise_reply, stance/leak/refusal, EventPolicy
│   │   ├── casting.py                         # resolve_cast(snapshot) - scenario-aware (w3, w7)
│   │   ├── agents.py                          # TurnContext, AgentReply, CharacterAgent protocol
│   │   └── ports/
│   │       ├── world_store.py                 # WorldReader + WorldWriter + WorldAdmin + transaction
│   │       ├── transport.py                   # CharacterTransport, TransportCapabilities, RoomHandle
│   │       ├── model.py                       # ModelClient, ModelReply, ModelFormat, Usage
│   │       ├── clock.py                       # Clock
│   │       ├── artifacts.py                   # ArtifactStore
│   │       └── content.py                     # ContentStore
│   │
│   ├── application/                           # use cases; feature-shaped modules
│   │   ├── turns.py                           # TurnRecorder (user line first -> plan -> respond_many
│   │   │                                      # -> sanitise -> apply writes -> record -> relay)
│   │   ├── scene.py                           # say_in_group, dm, whisper use cases
│   │   ├── beats.py                           # ONE run_beat used by every transport
│   │   ├── scenarios.py                       # load/evaluate; atomic; no raw SQL
│   │   ├── takes.py                           # take state/cues; no raw SQL
│   │   ├── ledger.py                          # beliefs, relationships, who_knows, matrix
│   │   ├── world.py                           # read projections; snapshot() feeds /api/state once
│   │   ├── safety.py                          # pause/resume, dev reset
│   │   ├── export.py                          # explicit scene-card artifact use case
│   │   └── facade.py                          # WorldService compatibility facade
│   │
│   ├── adapters/
│   │   ├── persistence/
│   │   │   ├── schema.py                      # DDL + migrations (from world_engine/db.py)
│   │   │   ├── seed.py
│   │   │   ├── sqlite_store.py                # the ONLY module with SQL
│   │   │   └── memory_store.py                # in-memory double for contract tests
│   │   ├── models/{bifrost.py,deepseek.py,scripted.py}
│   │   ├── transports/{switch.py,cloud_room.py,local.py}
│   │   ├── content/files.py                   # mtime cache, injected content root
│   │   ├── artifacts/files.py                 # export_dir injected
│   │   ├── clock/system.py
│   │   └── search/tavily.py                   # plain adapter, no port yet (one consumer)
│   │
│   ├── interfaces/                            # driving adapters
│   │   ├── http/
│   │   │   ├── app.py                         # create_app(container)
│   │   │   ├── deps.py                        # container + actor resolution (tokens)
│   │   │   ├── errors.py                      # DomainError -> 400/403/404/409/423/502/503
│   │   │   ├── schemas.py                     # pydantic models for all 39 routes
│   │   │   └── routes/{world,scene,director,scenarios,takes,studio,dev,health}.py
│   │   ├── mcp/{server.py,tools.py}           # 14 tools, actor-scoped
│   │   └── cli/{world.py,director.py}         # console entry points, argparse --help
│   │
│   └── resources/                             # wheel-only, force-included
│       ├── world/{canon.json,social.json,state/,scenarios/,takes/,characters/}
│       ├── web/{index.html,js/,cast.js}
│       └── agents/
│
├── world/  web/  agents/                      # source copies until step 8
├── world_engine/ director/ gateway/ mcp/      # import-only shims until step 10
├── tests/
│   ├── conftest.py                            # hermetic env, tmp dirs, container, fakes
│   ├── fakes/{transport,model,store,clock,content,artifacts}.py
│   ├── architecture/test_layering.py
│   ├── contract/{test_store,test_transport,test_model,test_content}_contract.py
│   ├── unit/{test_plan,test_policy,test_casting,test_protocol,test_settings,test_sanitise_parity}.py
│   ├── adapters/{test_migrations,test_switch_wire,test_content_cache}.py
│   ├── interfaces/{test_app_factory,test_routes_parity,test_openapi_golden,test_mcp_tools,test_cli}.py
│   ├── integration/{test_group_flow,test_cloud_group_writes,test_whisper_capability,
│   │                test_duplicate_event,test_beats_parity,test_state_connection_count}.py
│   ├── golden/{group/,dm/,whisper/,beats/,api/,scene_cards/}
│   └── packaging/test_wheel.py
├── scripts/  deploy/  data/                   # data/ gitignored incl. data/exports/
```

### 1.3 Adapter contracts

```python
# switch_world/domain/ports/world_store.py  (stdlib only)
from __future__ import annotations
from contextlib import AbstractContextManager
from typing import Iterator, Mapping, Protocol, Sequence

class WorldReader(Protocol):
    def snapshot(self) -> WorldSnapshot: ...                 # ONE connection, feeds /api/state
    def clock(self) -> ClockReading: ...
    def characters(self) -> list[Character]: ...
    def beliefs(self, holder: CharacterId) -> list[Belief]: ...
    def relationship(self, a: CharacterId, b: CharacterId) -> Relationship: ...
    def events(self, *, kind: str | None = None, after_id: int = 0,
               limit: int | None = None) -> list[Event]: ...
    def event_by_message_id(self, message_id: MessageId) -> Event | None: ...
    def items(self) -> list[Item]: ...
    def outfits(self) -> dict[CharacterId, Outfit]: ...
    def absent(self) -> list[CharacterId]: ...
    def completed_beats(self) -> list[str]: ...
    def meta(self, key: str) -> str | None: ...
    def revision(self) -> int: ...
    def idempotent(self, scope: str, request_id: str) -> IdempotentRecord | None: ...

class WorldWriter(Protocol):
    # Every mutator takes the authenticated actor; EventPolicy decides legality.
    def record_event(self, draft: EventDraft, *, actor: Actor) -> Event: ...
    def remember(self, draft: BeliefDraft, *, actor: Actor) -> Belief: ...
    def update_relationship(self, change: RelationshipChange, *, actor: Actor) -> Relationship: ...
    def set_outfit(self, change: OutfitChange, *, actor: Actor) -> Outfit: ...
    def give_item(self, item_id: ItemId, to: CharacterId, *, actor: Actor) -> Item: ...
    def set_presence(self, character: CharacterId, present: bool, *,
                     actor: Actor, reason: str = "") -> None: ...
    def add_friend(self, character: CharacterId, *, actor: Actor) -> Friend: ...
    def advance_time(self, minutes: int, *, actor: Actor) -> ClockReading: ...
    def set_clock(self, mode: str, *, actor: Actor, scale: float = 1.0,
                  anchor: datetime | None = None) -> ClockReading: ...
    def record_beat(self, beat: BeatRecord) -> None: ...
    def set_meta(self, key: str, value: str) -> None: ...
    def store_idempotent(self, scope: str, request_id: str, digest: str,
                         response: Mapping[str, Any]) -> None: ...
    def reset(self, *, actor: Actor) -> None: ...
    def transaction(self) -> AbstractContextManager["WorldWriter"]: ...

class WorldAdmin(Protocol):
    def load_scenario(self, spec: ScenarioSpec, *, actor: Actor) -> None: ...
    def begin_take(self, spec: TakeSpec, *, actor: Actor) -> None: ...
    def advance_take(self, *, actor: Actor) -> TakeState: ...

class WorldStore(WorldReader, WorldWriter, WorldAdmin, Protocol): ...
```

```python
# switch_world/domain/ports/transport.py
@dataclass(frozen=True)
class TransportCapabilities:
    response_format: Literal["text", "json"]
    write_mode: Literal["out_of_band", "in_band", "none"]
    private_rooms: bool
    non_blocking_post: bool
    addressing: bool
    event_id_field: Literal["id", "event_id", "synthetic"]

@dataclass(frozen=True)
class RoomHandle:
    room_id: str
    name: str
    private_for: CharacterId | None = None

@dataclass(frozen=True)
class Prompt:
    speaker: CharacterId
    text: str

@dataclass(frozen=True)
class InboundTurn:
    sender: CharacterId
    text: str
    event_id: MessageId
    received_at: datetime

@dataclass(frozen=True)
class Delivery:
    room: RoomHandle
    turn_id: TurnId
    cursor: str                              # captured BEFORE posting; the only valid "since"
    inline: tuple[InboundTurn, ...] = ()     # in-band transports return replies here

class CharacterTransport(Protocol):
    name: str
    def capabilities(self) -> TransportCapabilities: ...
    def open_room(self, *, name: str,
                  private_for: CharacterId | None = None) -> RoomHandle: ...
    def deliver_many(self, room: RoomHandle, prompts: Sequence[Prompt],
                     *, turn: TurnContext) -> Delivery: ...
    def collect(self, delivery: Delivery, *, speakers: Sequence[CharacterId],
                deadline: float) -> list[InboundTurn]: ...
    def history(self, room: RoomHandle) -> list[InboundTurn]: ...
    def close(self) -> None: ...
```

```python
# switch_world/domain/ports/model.py
class ModelFormat(StrEnum):
    TEXT = "text"
    JSON = "json"

@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

@dataclass(frozen=True)
class ModelReply:
    text: str
    data: dict[str, Any] | None
    usage: Usage
    model: str
    raw: Mapping[str, Any]

class ModelClient(Protocol):
    def generate(self, character: CharacterId, messages: Sequence[Message], *,
                 format: ModelFormat = ModelFormat.JSON,
                 reasoning: str | None = None,
                 temperature: float | None = None,
                 max_tokens: int | None = None) -> ModelReply: ...
    def usage(self, character: CharacterId | None = None) -> UsageSummary: ...

class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...

class ArtifactStore(Protocol):
    def write(self, name: str, content: str, *,
              media_type: str = "text/markdown") -> ArtifactRef: ...
    def read(self, name: str) -> str: ...
    def list(self, prefix: str = "") -> list[ArtifactRef]: ...

class ContentStore(Protocol):
    def canon(self) -> Canon: ...
    def social(self) -> SocialPolicy: ...
    def characters(self) -> list[CharacterSeed]: ...
    def scenario(self, scenario_id: str) -> ScenarioSpec: ...
    def takes(self) -> list[TakeSpec]: ...
```

```python
# switch_world/domain/agents.py
@dataclass(frozen=True)
class TurnContext:
    turn_id: TurnId
    character: CharacterId
    room: RoomHandle | None
    user_message: str
    role: Literal["primary", "reactor", "silent", "relay", "dm", "whisper", "beat"]
    verdict: SocialVerdict
    present: tuple[CharacterId, ...]
    canon: Canon
    recent: tuple[SceneLine, ...]
    memories: tuple[str, ...]
    policy: SocialPolicy

@dataclass(frozen=True)
class AgentReply:
    character: CharacterId
    text: str
    writes: tuple[WorldWrite, ...] = ()      # empty for out-of-band/MCP
    usage: Usage = Usage()
    source: Literal["envelope", "mcp", "scripted"] = "envelope"

class CharacterAgent(Protocol):
    def respond(self, ctx: TurnContext) -> AgentReply: ...
    def respond_many(self, contexts: Sequence[TurnContext], *,
                     deadline: float) -> list[AgentReply]: ...
```

Implementations: `RoomAgent(transport)` (posts all prompts, then collects once), `InBandAgent(model, prompt_builder)` (generates JSON concurrently and parses the envelope), `ScriptedAgent` (tests/demo). `respond_many` is the chorus-safe primitive. One `TurnRecorder` applies `AgentReply.writes` with `actor=character`, so authorization is identical whether writes came from MCP or an envelope.

**Auth decision:** authentication stays at the edges. `interfaces/http/deps.py` and `interfaces/mcp/tools.py` resolve `Actor` from `Settings.tokens` with constant-time compare. Authorization is `domain/policy.py::EventPolicy`, applied inside `WorldWriter`:

- character may write `dialogue`/`dm`/`silence`, remember about self or public facts, update its own outgoing relationship edge, set its own outfit;
- `scene_start`, `turn_plan`, `beat`, `scenario`, public system events are director/system only;
- `give_item` requires `actor.id == item.holder` or `actor.role == "director"`;
- private writes require `actor.id == holder`.

### 1.4 Port → adapter map

| Port | Local/dev | Cloud | Tests |
|---|---|---|---|
| WorldStore | SqliteWorldStore | SqliteWorldStore | InMemoryWorldStore |
| CharacterTransport | LocalRoomTransport / SwitchTransport | CloudRoomTransport | FakeTransport |
| ModelClient | BifrostModelClient | DeepSeekModelClient | ScriptedModelClient |
| Clock | SystemClock | SystemClock | FakeClock |
| ArtifactStore | FileArtifactStore(export_dir) | FileArtifactStore | InMemoryArtifactStore |
| ContentStore | FileContentStore(content_root) | same | DictContentStore |

| capability | SwitchTransport | CloudRoomTransport | LocalRoomTransport |
|---|---|---|---|
| response_format | text | json | json/text |
| write_mode | out_of_band (MCP) | in_band (envelope) | in_band/scripted |
| private_rooms | false, explicit | false | true |
| non_blocking_post | true | true (`deliver_many` generates concurrently) | true |
| event_id_field | normalized from `id`/`event_id` | synthetic | synthetic |

### 1.5 Composition root

```python
@dataclass(frozen=True)
class Settings:
    repo_root: Path
    content_root: Path
    web_root: Path
    data_dir: Path
    db_path: Path
    export_dir: Path
    host: str
    port: int
    dev_mode: bool
    agent_mode: Literal["switch", "cloud", "local"]
    world_start: datetime
    world_day: str
    tokens: Mapping[str, str]
    switch: SwitchSettings
    bifrost: BifrostSettings
    cloud: CloudSettings

def load_settings(env: Mapping[str, str]) -> Settings: ...   # pure; no globals
def build_container(settings: Settings) -> Container: ...     # only place adapters are named
```

`create_app(container)` stores the container on `app.state`; it never constructs a client and never runs at import. `Container` exposes `http_app()`, `mcp_server()`, `cli()`, `scene()`, `world()`. Tests build a container with fakes; no `dependency_overrides` needed.

---

## 2. Ordered, shippable steps

Each step is one commit (or an explicitly split pair) on `v2-architecture`, enters through a short-lived `v2/step-N` branch, and must pass `make check`. Every step keeps the 203 tests green. Rollback for all steps is `git revert <step-commit>`; no step before 8 changes a deployable entrypoint, and step 2’s only schema change is additive.

### Step 0 — Green, hermetic baseline (no architecture)

**Create**
- `.github/workflows/ci.yml` (commit the currently untracked one, rewritten from section 3; `package` and `docker` jobs initially `continue-on-error: true`).
- `Makefile` (`check: lint test web`; `lint` = ruff check + ruff format --check + compileall; `test` = pytest; `web` = node --check + node --test).
- `ruff.toml` (target py311, `E,F,I,UP,B,SIM,RUF`, line-length 100), `mypy.ini`.
- `tests/conftest.py`: autouse fixture pins `WORLD_DEV=1`, `WORLD_AGENT_MODE=switch`, `WORLD_DATA_DIR`/`WORLD_DB`/export dir to `tmp_path`, clears `WORLD_TOKEN_*`, `BIFROST_*`, `SWITCH_*`, `TAVILY_*`; `settings`, `service`, `store`, `app` fixtures.
- `tests/fakes/{switch,transport,model,tavily,clock,content,artifacts}.py` — move the 7 `FakeSwitch`/4 `FakeBifrost`/`FakeTavily` variants here.
- `tests/golden/` plus `scripts/capture_goldens.py`: snapshot all 39 routes, one group turn per mode, one DM, one whisper, the cafe beat, and the scene card with a frozen clock and fakes. These goldens are the parity gate for every later step.

**Edit**
- `pyproject.toml`: add `pytest-cov`, `pytest-timeout`, `ruff`, `mypy` to the dev group; remove `pytest-asyncio` (zero async tests) or set `asyncio_default_fixture_loop_scope = "function"`; `--cov-fail-under=75`.
- `director/social.py`: remove F841 `imperative` (classify) and `policy` (appraise), F401 `record_branch`/`advance_to`/`field` plus the two unused test imports — the 8 findings that currently make CI red.
- `tests/test_group.py::test_group_say_records_both_sides`: add `timeout=1`; suite drops ~59s → ~23s.
- `.gitignore`: add `data/exports/`; delete the 43+ committed scene cards.

**Run:** `make check`; `WORLD_DEV=0 uv run pytest -q`; `WORLD_AGENT_MODE=cloud WORLD_CLOUD_KEY=test uv run pytest -q`; `uv run pytest -q --durations=10` (assert < 25s); `uv run ruff check .`.

**Rollback:** revert; no runtime behavior changed.

### Step 1 — Settings and composition root; remove import-time config and app construction

**Create:** `switch_world/__init__.py`, `switch_world/config.py` (frozen `Settings`, pure `load_settings(env)`; absorbs env reads from `world_engine/config.py:16-29`, `studio.py:27-39`, `tavily_beat.py:19`), `switch_world/container.py`, `switch_world/errors.py`, `switch_world/interfaces/http/app.py` (`create_app(container)`).

**Edit:** `world_engine/api.py` — delete the module-level `app = create_app()` at line 629; re-export `create_app`; keep a `create_app(container=None)` compatibility wrapper that builds a default container when called with none. `world_engine/__main__.py`, `director/__main__.py`, `deploy/demo/entrypoint.py` build settings + container and call the factory (uvicorn updated to `--factory`). `world_engine/config.py` becomes a lazy shim using module `__getattr__` over `load_settings(os.environ)`, so old monkeypatch tests and imports keep working. `studio.py` and `tavily_beat.py` take settings instead of reading env.

**New tests:** `tests/unit/test_settings.py`; `tests/interfaces/test_app_factory.py` (two containers on different tmp dirs do not interfere); `tests/architecture/test_no_import_side_effects.py` (subprocess imports every module in a temp cwd and asserts no file, DB or socket is created).

**Rollback:** revert; module-level app returns and the shim disappears.

### Step 2 — WorldStore port, SQLite adapter, and removal of raw SQL / `_conn()` leakage

**Create:** `switch_world/domain/{ids,models,errors}.py`; `domain/ports/world_store.py`; `adapters/persistence/{schema.py,seed.py,sqlite_store.py,memory_store.py}`. Move `world_engine/db.py` DDL, migrations and seed into the adapter; leave `world_engine/db.py` as a re-export shim.

**Edit:** `world_engine/service.py` becomes a facade delegating all 66 methods (names and signatures unchanged) to store objects. Rewrite `world_engine/scenarios.py:383-518` and `takes.py:422,480,487,684,701,781` as store calls inside `transaction()`; delete every `service._conn()`. `/api/state` (service.py:1015 currently opens a connection per subprojection) calls `store.snapshot()` once.

**Schema bump (additive):** a partial unique index `ON events(message_id) WHERE message_id IS NOT NULL` and a per-turn cursor table/key; verify the current `schema_version` constant rather than assuming.

**New tests:** `tests/contract/test_store_contract.py` (parametrized sqlite + in-memory over every method, EventPolicy, give_item scoping, idempotency replay/conflict, atomic scenario rollback, duplicate message id); `tests/adapters/test_migrations.py` (old DB upgrades in place); `tests/integration/test_state_connection_count.py` (wrapped connect counter == 1); architecture test: no `sqlite3` outside `adapters/persistence`, no `_conn(` anywhere else.

**Rollback:** revert. The migration only adds an index and a table; a v(N-1) binary ignores them safely.

### Step 3 — Ports and adapter implementations (unwired)

**Create:** `domain/ports/{transport,model,clock,content,artifacts}.py`; `adapters/models/{bifrost.py,deepseek.py,scripted.py}`; `adapters/transports/{switch.py,cloud_room.py,local.py}`; `adapters/content/files.py`; `adapters/artifacts/files.py`; `adapters/clock/system.py`; `adapters/search/tavily.py`.

Copy, do not move yet: `gateway/bifrost.py` logic → `BifrostModelClient` with one `generate()` accepting `temperature`/`max_tokens`/`reasoning`; `director/cloud_switch.py` splits into `DeepSeekModelClient` (tolerant fence/preamble JSON, usage, per-character daily budget and request log) and `CloudRoomTransport` (concurrent generation in `deliver_many`, `ModelError` propagated instead of silent empty string, no same-millisecond cutoff); `director/switch_client.py` → `SwitchTransport` with an injected `httpx.Client`, explicit timeouts, cursor captured before posting, and a single normalized event id from `id` or `event_id`. Old modules keep running the app.

**New tests:** `tests/contract/test_transport_contract.py` parametrized over Switch (respx), CloudRoom (ScriptedModel), Local; `test_model_contract.py` (Bifrost/DeepSeek/Scripted: TEXT, JSON, fenced JSON, kwargs, usage, budget); `test_content_contract.py` (missing file, mtime cache, parse-once counter).

**Rollback:** adapters are unused; delete the new directories.

### Step 4 — One turn pipeline: group

**Create:** `domain/{protocol,plan,policy,casting}.py` and `domain/agents.py`. Move planning/addressing/roles/chorus from `director/group.py:44-465`, `_sanitise_reply`, `_prompt_for` and `SCENE_PROTOCOL` into these modules. `application/{turns,scene}.py` implements `TurnRecorder` (user line first → plan → `respond_many` with deadline → sanitise once → apply writes with actor → record → one-hop relay).

**Edit:** `director/group.py::say_in_group` becomes a shim over `application.scene.say_in_group`; keep its public name and signature. Wire transport/model selection through the container on `Settings.agent_mode` (no client construction in routes). Enable `EventPolicy` and actor-scoped writes at the store; a duplicate `message_id` now records a silence beat instead of dropping the line. Cloud group writes now land: `CloudRoomTransport` returns inline replies, the envelope parser produces `AgentReply.writes`, and the recorder applies memory/relationships.

**New tests:** `tests/unit/test_plan.py`, `test_policy.py`, `test_casting.py`; `tests/integration/test_group_flow.py` across switch/bifrost/cloud/local; `test_duplicate_event.py`; `test_cloud_group_writes.py` (belief count changes); golden group turns unchanged.

**Rollback:** revert; the old `group.py` body is restored intact.

### Step 5 — DM and whisper on the same pipeline (two commits)

**5a DM:** `director/dm.py` → `application.scene.dm`; delete the inline sanitiser (dm.py:150-156) and private imports (line 15). Golden DM unchanged.
**5b Whisper:** `director/whisper.py` → `application.scene.whisper`; delete the inline sanitiser (161-170) and `bifrost_scene`/`group` private imports (20-24); replace `hasattr(switch, "find_private_room")` with `capabilities.private_rooms`; the Switch private-room path applies `clean_scene_line`/placeholder filtering and reads `history()` once (399-409); the observer path applies `_strip_meta`; cloud switch-client identity import removed.

**New tests:** `tests/unit/test_sanitise_parity.py` (same input → identical sanitised output and identical metadata shape for group/DM/whisper/beat); `tests/integration/test_whisper_capability.py` (staged result when false; private path when a fake supports it); golden DM and whisper.

**Rollback:** two independent reverts.

### Step 6 — One beat pipeline

**Create:** `application/beats.py` with `run_beat(spec, agent, store, clock)` doing scene_start → turns → branch_for → validate → record_branch → advance_time → scene_end → get_beat → card. Each transport’s prompts stay as injected strategies (the three cafés already differ in prompts; only scaffold collapses).

**Edit:** `director/beats.py:189`, `bifrost_scene.py:171,295`, `run_switch.py:49,151`, `simulate.py:49` become thin wrappers with the same public names; delete the `CloudSwitch` class and make `cloud_switch.py` a shim over `DeepSeekModelClient`/`CloudRoomTransport`. Cloud beats use `ModelClient`, so no `wait_for` is required and `AGENT_MODE=cloud` covers `/api/dev/run-beat` and `director --beat`.

**New tests:** `tests/integration/test_beats_parity.py` (same branch/effects/assertions through local/Bifrost/Switch/cloud fakes); golden scene cards; cloud beat test; cafe beat completes in seconds with fakes (no production timeout).

**Rollback:** revert; the four runners return.

### Step 7 — Typed HTTP, route split, MCP hardening

**Create:** `interfaces/http/{schemas,deps,errors}.py`, `interfaces/http/routes/{world,scene,director,scenarios,takes,studio,dev,health}.py`, `interfaces/mcp/{server,tools}.py`. `world_engine/api.py` becomes a re-export shim.

**Edit:** replace 15 `payload: dict | None` with pydantic models and add response models for all 39 routes; remove `CloudSwitch`/`BifrostClient`/`SwitchClient` construction from handlers (api.py:490-499, 608-617); switch-log goes through `transport.history()` instead of private `_op('list_rooms')`; an absent provider returns 503 with a reason. `GET /api/scene-card` renders from `snapshot()` and writes nothing; new `POST /api/dev/scene-card/export` uses `ArtifactStore`. MCP: 14 tools; `world__give_item` and `world__record_event` pass the authenticated actor and are enforced in the store. Move `mcp/README.md` to `docs/MCP.md` and delete `mcp/`.

**New tests:** `tests/interfaces/test_routes_parity.py` (all 39 old paths present), `test_openapi_golden.py` (snapshot; field renames fail), `test_error_mapping.py` (400/403/404/409/423/502/503), `test_mcp_tools.py` (advertised list == 14 == docs), `test_authz.py` (give_item from a non-holder token → 403; record_event denied for a character writing a public turn event; dev routes 404 with `WORLD_DEV=0`); `/api/scene-card` writes no file.

**Rollback:** revert; `world_engine/mcp_server.py` shim remains.

### Step 8 — Packaging, entry points and CLI (this is the step where the deployable entrypoint changes)

**Edit:** `pyproject.toml` — `packages = ["switch_world"]`; hatch force-include `world/` → `switch_world/resources/world`, `web/` → `.../web`, `agents/` → `.../agents`; console scripts `world-engine`/`director` point at `switch_world.interfaces.cli.*`. `Settings` resolves the content root from the repo when present, else `importlib.resources`, with `WORLD_ROOT`/`WORLD_DATA_DIR` overrides. `deploy/demo/Dockerfile` installs the wheel (not separate COPYs of world/web) and uses the new entrypoint.

**New tests:** `tests/packaging/test_wheel.py` — build, install into a clean venv, assert `canon.json`, `social.json` and `web/index.html` resolve from the wheel, `TestClient` gets 200 on `/health`, `/api/state`, `/`; `world-engine --help` and `director --help`; `tests/interfaces/test_cli.py` subprocess tests for `--status`, `--reset`, `--beat local` on tmp data. CI `package` job becomes required.

**Rollback:** revert `pyproject.toml` and entry points; nothing is deployed.

### Step 9 — Modular dashboard, no build step

**Create:** `web/js/{main,api,state,format,vocab}.js`, `web/js/render/{stage,phone,ledger,studio}.js`, `web/js/*.test.js`, `web/package.json` (`test: node --test`), `scripts/gen-js-contract.py`. `index.html` loads one module script. `state.js` owns a store with `subscribe()` (no global mutable blob); `api.js` is the single fetch layer mirroring `schemas.py`; `render/*` are view functions. Generate `web/cast.js` and `web/js/vocab.js` from `domain/protocol.py` so cast/beat/take order exists once.

**New tests:** `node --check` every module; `node --test web/js` for formatting, state reducer, event-vocabulary mapping, take boundaries, sanitised-text rendering, API field mapping; a Python/CI drift check that `vocab.js` matches the backend contract. Manual dashboard smoke at phone and desktop widths against `LocalRoomTransport`.

**Rollback:** `index.html` is a one-line revert; delete `web/js/`. Keep `web/app.js` until step 10.

### Step 10 — Delete shims, enforce the architecture, docs

**Delete:** `world_engine/`, `director/`, `gateway/`, `mcp/`, `web/app.js`. All tests import `switch_world`. Architecture tests fail on any legacy import and on any `from x import _private` across package boundaries. Raise coverage to 85. Rewrite `README.md` MCP-first (14-tool table, scoped-token guarantee, adapter map, `make check`, v2 status), update `docs/ARCHITECTURE.md` (currently points at the empty `mcp/`), `docs/MCP.md`, `docs/DECISIONS.md`.

**Gate:** full 3.11/3.12/3.13 matrix, `WORLD_DEV=0` and `WORLD_AGENT_MODE=cloud` runs, wheel smoke, Docker `/health` smoke, `grep -r 'world_engine\|director\|gateway' switch_world tests` empty, `make run` geekroom demo smoke. Tag `v2.0.0-rc`. Do not merge to `main` and do not deploy.

**Rollback:** tag first; revert the delete commit restores every shim.

### Parallel dispatch after step 2

| Stream | Owns | Steps | Depends on |
|---|---|---|---|
| A | `domain/ports/world_store.py`, `domain/models.py`, `adapters/persistence/**` | 2 | — |
| B | `domain/ports/{transport,model,clock,content,artifacts}.py`, `adapters/{models,transports,content,artifacts,clock}/**` | 3 | A’s model dataclasses |
| C | `domain/{plan,policy,protocol,casting}.py`, `application/{turns,scene,beats}.py` | 4-6 | B contracts |
| D | `interfaces/**`, `web/**` | 7-9 | C signatures |
| E | `.github/`, `pyproject.toml`, `Makefile`, docs, packaging | 0, 8, 10 | continuous |

Exclusive file ownership: `config.py`, `container.py`, `pyproject.toml`, `README.md` are edited only by the integrator (E). Merge order A → B → C → D, E continuous. Rebase daily; never two agents editing `pyproject.toml` or `world/*.json` at once.

---

## 3. Free GitHub Actions CI (public repo)

All jobs use standard GitHub-hosted `ubuntu-latest` runners, which are free for public repositories. No Codecov, no paid service; coverage is uploaded as an Actions artifact. The Docker job runs only on push to `main`/`v2-architecture` to keep PR latency down.

```yaml
name: ci

on:
  push:
    branches: [main, geekroom, v2-architecture, "v2/**"]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHONDONTWRITEBYTECODE: "1"

jobs:
  lint:
    name: lint + architecture
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
      - run: uv sync --frozen --group dev
      - name: Ruff
        run: uv run ruff check .
      - name: Format
        run: uv run ruff format --check switch_world tests
      - name: Layering contracts
        run: uv run pytest -q tests/architecture/test_layering.py tests/architecture/test_no_import_side_effects.py
      - name: Types on the new seams
        run: uv run mypy switch_world/domain switch_world/application switch_world/interfaces/http/schemas.py
      - name: py_compile every module
        run: uv run python -m compileall -q switch_world scripts deploy

  test:
    name: test (py${{ matrix.python-version }})
    runs-on: ubuntu-latest
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true
      - run: uv sync --frozen --group dev
      - name: Tests + coverage
        env:
          WORLD_DEV: "1"
          WORLD_AGENT_MODE: "switch"
          WORLD_DATA_DIR: ${{ runner.temp }}/data
          WORLD_DB: ${{ runner.temp }}/data/world.sqlite
        run: >
          uv run pytest -q --timeout=20
          --cov=switch_world --cov-report=term-missing --cov-report=xml
          --cov-fail-under=75
      - name: Env hermeticity (dev off)
        if: matrix.python-version == '3.12'
        env:
          WORLD_DEV: "0"
          WORLD_DATA_DIR: ${{ runner.temp }}/data-dev0
          WORLD_DB: ${{ runner.temp }}/data-dev0/world.sqlite
        run: uv run pytest -q -x --timeout=20
      - name: Env hermeticity (cloud mode)
        if: matrix.python-version == '3.12'
        env:
          WORLD_AGENT_MODE: "cloud"
          WORLD_CLOUD_KEY: "test-key-not-used"
          WORLD_DATA_DIR: ${{ runner.temp }}/data-cloud
          WORLD_DB: ${{ runner.temp }}/data-cloud/world.sqlite
        run: uv run pytest -q -x --timeout=20
      - name: Upload coverage
        if: matrix.python-version == '3.12'
        uses: actions/upload-artifact@v4
        with:
          name: coverage-xml
          path: coverage.xml
          if-no-files-found: warn

  web:
    name: dashboard
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: node --check every module
        run: |
          set -e
          if [ -d web/js ]; then
            find web/js -name '*.js' -print0 | xargs -0 -n1 node --check
          else
            node --check web/app.js
          fi
          node --check web/cast.js
      - name: Unit tests (no dependencies)
        run: |
          if [ -d web/js ]; then node --test web/js; fi
      - name: Contract file is current
        run: |
          if [ -f scripts/gen-js-contract.py ]; then
            python3 scripts/gen-js-contract.py --check
            git diff --exit-code -- web/js/vocab.js web/cast.js
          fi

  package:
    name: wheel install smoke
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
      - run: uv build
      - name: Install wheel in a clean venv
        run: |
          uv venv .wheel-venv
          uv pip install --python .wheel-venv/bin/python dist/*.whl
      - name: Import + packaged resources + app smoke
        env:
          WORLD_DEV: "1"
          WORLD_DATA_DIR: ${{ runner.temp }}/pkg-data
          WORLD_DB: ${{ runner.temp }}/pkg-data/world.sqlite
        run: |
          .wheel-venv/bin/python - <<'PY'
          import os
          from fastapi.testclient import TestClient
          from switch_world.config import load_settings
          from switch_world.container import build_container
          from switch_world.interfaces.http.app import create_app

          settings = load_settings(os.environ)
          assert (settings.content_root / "canon.json").is_file(), "canon.json missing from wheel"
          assert (settings.web_root / "index.html").is_file(), "web/ missing from wheel"
          client = TestClient(create_app(build_container(settings)))
          assert client.get("/health").status_code == 200
          assert client.get("/api/state").status_code == 200
          assert client.get("/").status_code == 200
          print("package smoke ok")
          PY
      - name: Console scripts start
        env:
          WORLD_DATA_DIR: ${{ runner.temp }}/pkg-data
          WORLD_DB: ${{ runner.temp }}/pkg-data/world.sqlite
        run: |
          .wheel-venv/bin/world-engine --help
          .wheel-venv/bin/director --help

  docker:
    name: docker health smoke
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -f deploy/demo/Dockerfile -t switch-world:ci .
      - name: Run and probe /health
        run: |
          docker run -d --name sw -p 8890:8890 \
            -e WORLD_DEV=1 -e WORLD_DATA_DIR=/tmp/data switch-world:ci
          for i in $(seq 1 30); do
            if curl -fsS http://127.0.0.1:8890/health; then exit 0; fi
            sleep 1
          done
          docker logs sw
          exit 1
      - name: Dump logs on failure
        if: failure()
        run: docker logs sw || true
```

**Staged activation:** in step 0, only `lint`, `test` (with the 75% gate) and `web` are required; `package` and `docker` are `continue-on-error: true`. `package` becomes required at step 8, `docker` at step 10. Coverage ratchet: 75 at step 0, 80 at step 2, 85 at step 10.

---

## 4. Test matrix: module → tests → gaps

| Module | Tests | Existing state | Gap / new coverage |
|---|---|---|---|
| `domain/models.py`, `ids.py` | `unit/test_models.py` | none (types inline in service) | frozen dataclasses, NewType boundaries |
| `domain/protocol.py` | `unit/test_protocol.py`, OpenAPI/vocab parity | vocabulary repeated 4 times | single source; JS parity test |
| `domain/plan.py` | `unit/test_plan.py`, golden group turns | buried in group.py, indirect | named addressee wins; chorus; intimacy probe; relay |
| `domain/policy.py` | `unit/test_policy.py`, `test_sanitise_parity.py` | 3 copied sanitisers | refusals, leaks, placeholders, `_strip_meta` |
| `domain/casting.py` | `unit/test_casting.py` | global `CHARACTER_ORDER` | w3 alice-only, w7 mia-only; order from content |
| `domain/agents.py` | fakes + `integration/test_group_flow.py` | no abstraction | ScriptedAgent, RoomAgent, InBandAgent |
| `application/turns.py` | golden + integration | metadata hand-built per path | one metadata shape; user-first ordering |
| `application/scene.py` | `test_group_flow`, `test_whisper_capability`, golden | group only; DM/whisper drift | parity across group/DM/whisper |
| `application/beats.py` | `test_beats_parity.py`, golden scene cards | 4 divergent runners | one pipeline, 4 transports |
| `application/scenarios.py` | `tests/test_scenarios.py`, atomic rollback | 60 missed lines, raw SQL | no SQL; rollback |
| `application/takes.py` | `tests/test_takes.py`, cue authz | 47 missed lines, raw SQL | no SQL; cue authorization |
| `application/ledger.py`, `world.py` | unit projections, connection counter | inside 1,389-line object | pure projections; one snapshot |
| `adapters/persistence/*` | `contract/test_store_contract.py`, `test_migrations.py` | db.py tested indirectly | every method; v(N-1) upgrade; unique message id |
| `adapters/transports/switch.py` | `contract/test_transport_contract.py` (respx) | switch_client 32% | id normalization; cursor; non-200; wait |
| `adapters/transports/cloud_room.py` | same contract suite | CloudSwitch untested | same-ms visibility; concurrent generate; errors |
| `adapters/models/{bifrost,deepseek}.py` | `contract/test_model_contract.py` | Bifrost tested; cloud partial | fenced JSON parity; kwargs; budget; usage |
| `adapters/content/files.py` | `test_content_contract.py`, cache counter | social/canon re-read per call | parse once per container |
| `adapters/artifacts/files.py` | export test | `scene_card` writes in a getter | explicit export only |
| `interfaces/http/*` | `test_routes_parity`, `test_openapi_golden`, `test_error_mapping` | 39 untyped routes | typed models for all 39; 15 payloads |
| `interfaces/mcp/*` | `test_mcp_tools`, `test_authz` | 61%; give_item bypass | 14 tools; actor scoping; record_event policy |
| `interfaces/cli/*` | `test_cli.py` subprocess | 0 | `--help`, `--status`, `--reset`, `--beat local` |
| `web/js/*` | `node --test`, `node --check` | 0 (197 KB app.js) | format, state, vocab, take boundaries, API mapping |
| packaging | `test_wheel.py` | 0; wheel broken at first start | resources + console scripts + TestClient |
| legacy shims | full existing suite | 203 tests, 82% | import-only; deleted step 10 |

**Regression tests mapped to audited bugs**

- Cloud group writes nothing → `test_cloud_group_writes.py` (step 4).
- Cloud beat missing / `wait_for` AttributeError → `test_beats_parity.py` cloud case (step 6).
- Whisper Switch path unreachable → `test_whisper_capability.py` (step 5).
- `id` vs `event_id` → transport contract with both wire shapes (step 3).
- Duplicate Switch event drops a line → `test_duplicate_event.py` (step 4).
- `give_item`/`record_event` bypass → `test_authz.py` (step 7).
- `/api/state` fans out to ~8 connections → `test_state_connection_count.py` (step 2).
- `GET /api/scene-card` writes files → route test asserts no file (step 7).
- Wheel omits `world/`, `web/`, `agents/` → `test_wheel.py` (step 8).
- Ambient env breaks suite → conftest + two CI env runs (step 0).
- 35s test → timeout=1; suite budget assertion (step 0).

**Budgets:** overall coverage 75 → 80 → 85; `switch_client`/Switch transport and `mcp_server` each ≥ 80%; public suite < 25s on 3.12; `pytest-timeout=20`; no test touches the network (respx/MockTransport) or the repo `data/`.

---

## 5. Feature change/cut rules

A **feature unit** is: one module in `application/`, its domain rules (if any) in `domain/`, one router file in `interfaces/http/routes/`, and its tests (unit + integration + golden). The router include list in `interfaces/http/app.py` is the registry.

| Feature | application module | router | tests |
|---|---|---|---|
| world/state | `world.py` | `routes/world.py` | unit projections, route tests |
| ledger | `ledger.py` | `routes/world.py` (`/api/matrix`, `/api/who-knows`) | ledger unit + contract |
| scenarios | `scenarios.py` | `routes/scenarios.py` | scenario unit + integration |
| takes | `takes.py` | `routes/takes.py` | take unit + golden |
| group scene | `scene.py`, `turns.py` | `routes/scene.py` (`/api/group/say`) | group integration + golden |
| phone (DM/whisper) | `scene.py` (dm/whisper) | `routes/scene.py` (dm/whisper/friend) | whisper capability + parity |
| beats | `beats.py` | `routes/director.py` | beats parity + golden |
| studio/dev | (thin) | `routes/studio.py`, `routes/dev.py` | route tests, dev-only 404 |
| health | — | `routes/health.py` | smoke |

**Add a feature**
1. Reuse an existing port if possible. Only add a port to `domain/ports/` if a second real implementation or a test double is required; otherwise add a plain adapter module (like Tavily).
2. Create `application/<feature>.py` using the ports injected through `Container`; never import another application module.
3. Add `interfaces/http/routes/<feature>.py` with pydantic schemas and one line in the `app.py` include list.
4. Add tests: unit with fakes, one integration through the container, golden if it renders.
5. No edits to `domain/models.py` unless a genuinely shared term appears; shared vocabulary goes to `domain/protocol.py`.

**Cut a feature**
1. Remove its line from the `app.py` include list and delete the router file.
2. Delete the application module and its domain-only helpers; delete its adapter only if it has no other consumer.
3. Delete its tests and golden files. Run `make check`; the route-parity test is updated in the same commit.
4. Leave tables in place unless a migration is justified; a cut feature must not require a schema change to stop running.
5. One commit, fully green. No core edits.

**Example cut — whisper:** remove `application.scene.whisper`, the whisper handler in `routes/scene.py`, `test_whisper_capability.py` and golden whisper; `CloudRoomTransport`/`SwitchTransport` remain because group and DM use them.

**Forbidden edges** (enforced by `tests/architecture/test_layering.py` and CI): application → application; application → adapters; adapters → interfaces; core → `world_engine`/`director`/`gateway` after step 10; any `from x import _private` across packages; feature-specific vocabulary hardcoded in `web/` (must be generated from `domain/protocol.py`).

---

## 6. No-break guardrails

**Must not change during migration**
- 39 route paths and their response field names — OpenAPI golden is the contract; a rename is a deliberate commit that also updates `web/api.js`.
- 14 MCP tool names and arguments — the README contract.
- Console script names `world-engine` and `director`; env var names (`WORLD_DEV`, `WORLD_AGENT_MODE`, `WORLD_DATA_DIR`, `WORLD_DB`, `WORLD_TOKEN_*`, `BIFROST_*`, `SWITCH_*`, `TAVILY_*`).
- Content file paths under `world/` until step 8, and repo layout support after it (Settings resolves both).
- Public function names in `director/group.py`, `director/dm.py`, `director/whisper.py`, `director/beats.py`, `simulate.py`, `run_switch.py`, `bifrost_scene.py`, `gateway/bifrost.py`, `gateway/tavily.py` while a shim exists.
- `main` and `geekroom` branches; no deploy; no Docker/compose default changes; no merge to `main` before the demo is frozen.

**Step gates (all must be green before the next step starts)**
- Step 0: 203 tests, ruff clean, both env-hermetic runs, suite < 25s, CI tracked.
- Step 1: no import side effects, app factory test, existing suite.
- Step 2: store contract + migration + single-connection state; no `_conn(` outside adapters.
- Step 3: transport/model/content contract suites.
- Step 4: group golden parity across four modes; cloud writes; duplicate event.
- Step 5: DM and whisper golden parity; one sanitiser; no private imports.
- Step 6: four-transport beat parity; cloud beat; golden scene cards.
- Step 7: 39-route parity; OpenAPI golden; MCP 14 tools; authz denials; scene-card read-only.
- Step 8: wheel install + resources + both console scripts + TestClient smoke.
- Step 9: node --check + node --test + contract drift check.
- Step 10: full matrix, env runs, wheel, Docker /health, shim grep empty, `make run`.

**Safety rules**
- Tests never touch the network (respx/`httpx.MockTransport`) and never write the repository data directory (Settings/ArtifactStore point at `tmp_path`; `data/exports/` is gitignored).
- Shims are import-only; they contain no logic and are deleted only after the shim grep is empty.
- Behaviour fixes (cloud writes, duplicate event, give_item/record_event authorization, event-id normalization) are separate commits with their own tests and a clear PR note; do not hide them inside a move.
- Worktree discipline: never use bare `git stash`/`git stash pop` (shared stack); set work aside as a WIP commit on a `v2/step-*` branch. One workstream per branch; daily rebase onto `v2-architecture`.
- Rollback: every step is a single revert; the only schema change is additive; no step before 8 changes the deployable entrypoint; the v2 branch is never deployed.

**Definition of done for v2:** `make check` is the single local command; the architecture test and import contracts pass; the wheel installs and serves `/health`, `/api/state` and `/`; all four reply paths share one pipeline with parity goldens; a feature can be added or removed by one module, one router file and its tests; `README.md` is MCP-first and matches the tree; `main`/`geekroom` are unchanged and nothing was deployed.