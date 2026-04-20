# Extractor framework substrate — design

**Date:** 2026-04-20
**Slice:** N+2a — extractor framework substrate (decomposed from N+2 roadmap)
**Author:** Board (operator-driven)
**Status:** Awaiting formalization (Phase 1.1)
**Branch:** `feature/GIM-59-extractor-framework-substrate` (first slice cut under feature-branch flow post-GIM-57)
**Predecessors pinned:**
- `develop@41d23d2` — GIM-57 meta-workflow migration merged; single mainline active; branch protection on main + develop.
- Research: `docs/research/extractor-library/report.md §2.1 + §8 + §9` — extractor inventory, N+2 roadmap (4 extractors planned), N+1 implications (cross_extractor_feeds, group_id namespace, SCIP alignment).

**Decomposition context:** N+2 as originally roadmapped bundled 4 extractors (#21 Symbol Index, #22 Git History Harvester, #1 Architecture Layer, #25 Build System) + their substrate. Too large for one spec. This slice (**N+2a**) builds only the substrate — a framework that future extractor slices (N+2b = Git History Harvester, N+2c+ = others) register into. Ships one diagnostic extractor (`heartbeat`) to prove the pipeline end-to-end.

**Scope:** new package `palace_mcp/extractors/` in palace-mcp; 2 new MCP tools (`palace.ingest.run_extractor`, `palace.ingest.list_extractors`); lifecycle-wrapped runner that creates/finalizes `:IngestRun`; declarative schema aggregation; heartbeat extractor. **No real code analysis**; no new external tool dependencies; no new containers. Pure infrastructure.

## 1. Context — why this slice before any real extractor

Research report §8 lists 4 extractors for N+2, each with different tool stacks and data models. Shipping them as one bundle has three problems:

1. **Substrate decisions leak into every extractor.** Where code runs, how Neo4j is accessed, how `:IngestRun` is tracked, how cross-extractor edges work, how schema bootstraps — these get answered ad-hoc in each extractor if no framework exists. Divergence certain.

2. **Risk concentrates.** If one of 4 extractors has a latent bug (pattern from GIM-48 vector #3 — mocked-substrate tests pass, real API fails), the whole bundle reverts. Framework-first splits risk: framework is narrow and low-surface; each following extractor is a small delta.

3. **Testing impossible at substrate level** without at least one real extractor to prove the pipeline. Heartbeat fills that hole — 40 LOC, zero external deps.

Shipping framework alone (with heartbeat as the live-smoke target) gives a merge-ready, testable foundation in ~1 day. Each subsequent extractor (N+2b = Git History Harvester next) becomes ~1-2 days on top.

## 2. Goal

After this slice:

- **Package `palace_mcp/extractors/`** exists on develop, with 4 internal modules (`base`, `registry`, `runner`, `schema`, `heartbeat` — `schemas.py` for Pydantic responses separate).
- **2 MCP tools** on existing `palace-memory` FastMCP app: `palace.ingest.run_extractor(name, project)` and `palace.ingest.list_extractors()`.
- **`:IngestRun{source: "extractor.<name>"}` tracking** for every run — start, finalize with counts, errors captured.
- **`ensure_extractors_schema(driver)`** aggregates `constraints` + `indexes` declared by registered extractors and applies them idempotently at startup.
- **`HeartbeatExtractor` ships** as production code, writes one `:ExtractorHeartbeat` node per run, zero external dependencies.
- **Adding the next extractor (N+2b = Git History Harvester)** is 1 file + 1 import line — no substrate work redone.

**Success criterion** (QA Phase 4.1, live on iMac post-deploy):
1. `palace.ingest.list_extractors()` returns `[{name: "heartbeat", description: "..."}]`.
2. `palace.ingest.run_extractor(name="heartbeat", project="gimle")` returns `{ok: true, run_id: "<uuid>", nodes_written: 1, ...}`.
3. Cypher `MATCH (h:ExtractorHeartbeat {run_id: "<uuid>"}) RETURN h` shows the node with ISO-8601 `ts`, `extractor: "heartbeat"`, `group_id: "project/gimle"`.
4. Cypher `MATCH (r:IngestRun {id: "<same uuid>"}) RETURN r.source, r.success, r.nodes_written` shows `source: "extractor.heartbeat"`, `success: true`, `nodes_written: 1`.
5. Error envelopes correct: unknown extractor → `unknown_extractor`; invalid slug → `invalid_slug`; project not registered → `project_not_registered` or `repo_not_mounted`.
6. Re-run increments `:ExtractorHeartbeat` count (each run unique `run_id`) and creates separate `:IngestRun`.
7. mypy `--strict` + ruff clean across new package; unit + integration tests pass.

## 3. Architecture

### 3.1 Package layout

```
services/palace-mcp/src/palace_mcp/extractors/
├── __init__.py       # empty — use registry for access
├── base.py           # BaseExtractor ABC + ExtractionContext + ExtractorStats + error classes (~80 LOC)
├── registry.py       # EXTRACTORS dict + register/get/list_all (~40 LOC)
├── runner.py         # async run_extractor(name, project) — full lifecycle (~150 LOC)
├── schema.py         # ensure_extractors_schema(driver) aggregator (~30 LOC)
├── schemas.py        # Pydantic response models: ExtractorRunResponse, ExtractorListResponse, etc. (~80 LOC)
├── cypher.py         # CREATE_INGEST_RUN + FINALIZE_INGEST_RUN Cypher statements (~30 LOC)
└── heartbeat.py      # HeartbeatExtractor shipped (~40 LOC)
```

Each file: one clear responsibility. Designed to test independently.

### 3.2 BaseExtractor contract (`base.py`)

```python
class BaseExtractor(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    constraints: ClassVar[list[str]] = []   # CREATE CONSTRAINT ... IF NOT EXISTS
    indexes: ClassVar[list[str]] = []       # CREATE INDEX ... IF NOT EXISTS

    @abstractmethod
    async def extract(self, ctx: ExtractionContext) -> ExtractorStats: ...


@dataclass(frozen=True)
class ExtractionContext:
    driver: AsyncDriver
    project_slug: str
    group_id: str              # "project/<slug>"
    repo_path: Path            # /repos/<slug> (validated by runner)
    run_id: str                # :IngestRun.id, created before extract()
    logger: logging.Logger     # scoped to palace_mcp.extractors.<name>


@dataclass(frozen=True)
class ExtractorStats:
    nodes_written: int = 0
    edges_written: int = 0


class ExtractorError(Exception):
    error_code: str = "extractor_error"


class ExtractorConfigError(ExtractorError):
    error_code = "extractor_config_error"


class ExtractorRuntimeError(ExtractorError):
    error_code = "extractor_runtime_error"
```

Rationale (§2 brainstorm decisions):
- ClassVar `name` — registry keys by class-level name; prevents instance-level mutation.
- ClassVar `constraints`/`indexes` — declarative, framework aggregates at startup.
- Frozen `ExtractionContext` — immutable; extractor can't mutate group_id mid-run.
- `ExtractorStats` return — merged into `:IngestRun` finalize for observability.
- Typed errors with `error_code` — runner maps directly to MCP response `error_code`.

### 3.3 Registry (`registry.py`)

```python
EXTRACTORS: dict[str, BaseExtractor] = {
    "heartbeat": HeartbeatExtractor(),
}


def register(e: BaseExtractor) -> None:
    if e.name in EXTRACTORS:
        raise ValueError(f"extractor already registered: {e.name!r}")
    EXTRACTORS[e.name] = e


def get(name: str) -> BaseExtractor | None:
    return EXTRACTORS.get(name)


def list_all() -> list[BaseExtractor]:
    return list(EXTRACTORS.values())
```

Adding N+2b = 1 import line + 1 dict entry. No framework change.

**Thread-safety:** registration is import-time (module-level EXTRACTORS dict literal). FastMCP tools run in a single asyncio event loop — no parallel register() calls possible in production. `register()` is provided for **test-time dynamic registration only**; production code never calls it at runtime.

### 3.4 Runner lifecycle (`runner.py`)

Split into 3 helper coroutines + one orchestrator. Keeps each function < 50 LOC and independently testable (per reviewer NUDGE — 7-step monolith resisted clean unit-test boundaries).

```python
# --- helper 1 ---
async def _precheck(
    *, name: str, project: str, driver: AsyncDriver
) -> PrecheckResult:
    """Validate slug, lookup extractor, verify :Project + repo_path. Pure
    reads; no :IngestRun written yet. Returns PrecheckResult which is either
    PrecheckOk(extractor, repo_path, group_id) or PrecheckError(error_code, message)."""


# --- helper 2 ---
async def _execute(
    *, extractor: BaseExtractor, ctx: ExtractionContext, timeout_s: float
) -> ExecuteResult:
    """Wrap extractor.extract() in asyncio.wait_for + Exception handling.
    Returns ExecuteOk(stats) or ExecuteError(error_code, errors_list). Never
    raises. Logs extractor.run.start/finish/error structured events."""


# --- helper 3 ---
async def _finalize(
    *, driver: AsyncDriver, run_id: str, result: ExecuteResult,
    started_at: str, duration_ms: int,
) -> None:
    """Write FINALIZE_INGEST_RUN with stats/errors/success. Idempotent if
    called twice (MATCH + SET)."""


# --- orchestrator ---
async def run_extractor(
    name: str,
    project: str,
    *,
    driver: AsyncDriver | None = None,
    timeout_s: float = EXTRACTOR_TIMEOUT_S,  # default 300
) -> dict[str, Any]:
    """Full lifecycle: precheck → create :IngestRun → execute → finalize."""
    driver = driver or get_global_driver()  # from palace_mcp.main

    # 1. Validate slug
    try:
        validate_slug(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", None, project)

    # 2. Look up extractor
    extractor = registry.get(name)
    if extractor is None:
        return _error("unknown_extractor", f"no extractor named {name!r}", None, project)

    # 3. Verify :Project exists
    async with driver.session() as s:
        row = await (await s.run(GET_PROJECT, slug=project)).single()
    if row is None:
        return _error("project_not_registered", f"no :Project {{slug: {project!r}}}", name, project)

    # 4. Verify repo mounted + git-repo
    repo_path = REPOS_ROOT / project
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        return _error("repo_not_mounted", f"no mounted git repo at /repos/{project}", name, project)

    # 5. Create :IngestRun (start)
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    source = f"extractor.{name}"
    group_id = f"project/{project}"
    async with driver.session() as s:
        await s.run(
            CREATE_INGEST_RUN,
            id=run_id, source=source, group_id=group_id, started_at=started_at,
        )

    # 6. Run extract under timeout
    logger = logging.getLogger(f"palace_mcp.extractors.{name}")
    logger.info("extractor.run.start", extra={
        "extractor": name, "project": project, "run_id": run_id, "group_id": group_id,
    })
    ctx = ExtractionContext(
        driver=driver, project_slug=project, group_id=group_id,
        repo_path=repo_path, run_id=run_id, logger=logger,
    )
    start_mono = time.monotonic()
    stats: ExtractorStats | None = None
    errors: list[str] = []
    success = False
    error_code = None
    try:
        stats = await asyncio.wait_for(extractor.extract(ctx), timeout=timeout_s)
        success = True
    except asyncio.TimeoutError:
        errors.append(f"timeout after {timeout_s}s")
        error_code = "extractor_runtime_error"
    except ExtractorError as e:
        errors.append(str(e)[:200])
        error_code = e.error_code
    except Exception as e:  # noqa: BLE001 — unexpected, structured response
        errors.append(f"{type(e).__name__}: {str(e)[:200]}")
        error_code = "unknown"
        logger.exception("extractor.run.unhandled")  # stack trace → stdout only, not in :IngestRun

    duration_ms = int((time.monotonic() - start_mono) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    # 7. Finalize :IngestRun
    async with driver.session() as s:
        await s.run(
            FINALIZE_INGEST_RUN,
            id=run_id,
            finished_at=finished_at,
            duration_ms=duration_ms,
            nodes_written=(stats.nodes_written if stats else 0),
            edges_written=(stats.edges_written if stats else 0),
            errors=errors,
            success=success,
        )

    if success:
        logger.info("extractor.run.finish", extra={
            "extractor": name, "project": project, "run_id": run_id,
            "duration_ms": duration_ms,
            "nodes_written": stats.nodes_written, "edges_written": stats.edges_written,
            "success": True,
        })
        return {
            "ok": True, "run_id": run_id, "extractor": name, "project": project,
            "started_at": started_at, "finished_at": finished_at, "duration_ms": duration_ms,
            "nodes_written": stats.nodes_written, "edges_written": stats.edges_written,
            "success": True,
        }
    logger.error("extractor.run.error", extra={
        "extractor": name, "project": project, "run_id": run_id,
        "duration_ms": duration_ms, "error_code": error_code,
        "error_head": errors[0] if errors else "",
    })
    return _error(error_code or "unknown", errors[0] if errors else "", name, project, run_id=run_id)
```

### 3.5 Schema aggregation (`schema.py`)

```python
async def ensure_extractors_schema(driver: AsyncDriver) -> None:
    """Apply constraints + indexes from all registered extractors. Idempotent."""
    statements: list[str] = []
    for extractor in registry.list_all():
        statements.extend(extractor.constraints)
        statements.extend(extractor.indexes)
    async with driver.session() as session:
        for stmt in statements:
            await session.run(stmt)
```

Called in `main.py` lifespan after `memory.constraints.ensure_schema()`:
```python
await ensure_schema(driver, default_group_id=settings.palace_default_group_id)
await ensure_extractors_schema(driver)
```

### 3.6 Heartbeat extractor (`heartbeat.py`)

```python
class HeartbeatExtractor(BaseExtractor):
    name = "heartbeat"
    description = (
        "Diagnostic probe. Writes one :ExtractorHeartbeat node tagged with "
        "run_id + timestamp. Use to verify extractor pipeline is alive."
    )
    constraints = [
        "CREATE CONSTRAINT extractor_heartbeat_id IF NOT EXISTS "
        "FOR (h:ExtractorHeartbeat) REQUIRE h.run_id IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX extractor_heartbeat_group_id IF NOT EXISTS "
        "FOR (n:ExtractorHeartbeat) ON (n.group_id)",
        "CREATE INDEX extractor_heartbeat_ts IF NOT EXISTS "
        "FOR (n:ExtractorHeartbeat) ON (n.ts)",
    ]

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        ts = datetime.now(timezone.utc).isoformat()
        async with ctx.driver.session() as session:
            await session.run(
                """
                MERGE (h:ExtractorHeartbeat {run_id: $run_id})
                ON CREATE SET h.ts = $ts, h.extractor = $extractor, h.group_id = $group_id
                """,
                run_id=ctx.run_id, ts=ts, extractor=self.name, group_id=ctx.group_id,
            )
        ctx.logger.info("heartbeat.node_written", extra={"run_id": ctx.run_id, "group_id": ctx.group_id})
        return ExtractorStats(nodes_written=1, edges_written=0)
```

`:ExtractorHeartbeat` schema: `{run_id, ts, extractor, group_id}`. MERGE by `run_id` is **defensive good practice**, not a load-bearing idempotency guarantee — runner generates a fresh UUID per call (see §3.4 step 5), so MERGE always dedegenerates to CREATE in normal flow. Framework-level idempotency "re-running heartbeat against same project creates separate runs" is guaranteed by fresh `run_id`, not by MERGE semantics.

## 4. MCP tool surface

### 4.1 `palace.ingest.run_extractor`

**Input:** `name: str, project: str`
**Response on success:**
```json
{
  "ok": true,
  "run_id": "<uuid>",
  "extractor": "heartbeat",
  "project": "gimle",
  "started_at": "2026-04-20T10:00:00+00:00",
  "finished_at": "2026-04-20T10:00:01+00:00",
  "duration_ms": 1000,
  "nodes_written": 1,
  "edges_written": 0,
  "success": true
}
```
**Response on error:**
```json
{
  "ok": false,
  "error_code": "invalid_slug | unknown_extractor | project_not_registered | repo_not_mounted | extractor_config_error | extractor_runtime_error | unknown",
  "message": "<short redacted>",
  "extractor": "heartbeat" | null,
  "project": "gimle" | null,
  "run_id": "<uuid>" | null
}
```
Pydantic `ExtractorRunResponse` / `ExtractorErrorResponse` with `ConfigDict(extra="forbid")` are used **internally** for validation and serialization (e.g., `response.model_dump()` inside runner). The MCP tool signature itself returns `dict[str, Any]` — this matches the established palace-mcp pattern (all `palace.memory.*` / `palace.git.*` tools return `dict[str, Any]`; FastMCP derives the input schema from param type hints, the output shape is documented in the tool's `description` string rather than a JSON Schema).

**Timeout:** 300s default per run. Override via module constant `EXTRACTOR_TIMEOUT_S`. Per-extractor override deferred (followup).

### 4.2 `palace.ingest.list_extractors`

**Input:** none
**Response:**
```json
{
  "ok": true,
  "extractors": [
    {"name": "heartbeat", "description": "Diagnostic probe..."}
  ]
}
```
Used for discovery — clients don't need to hardcode extractor names.

### 4.3 Registration pattern in `mcp_server.py`

Matches `palace.git.*` precedent (GIM-54):

```python
from palace_mcp.extractors.runner import run_extractor as _run_extractor
from palace_mcp.extractors.registry import list_all as _list_extractors

@_mcp.tool(name="palace.ingest.run_extractor", description=(
    "Run a named extractor against a registered project. Writes nodes/edges "
    "scoped by group_id. Creates :IngestRun tracking. Returns run_id + counts. "
    "Default timeout 300s."
))
async def _palace_ingest_run_extractor(name: str, project: str) -> dict[str, Any]:
    return await _run_extractor(name=name, project=project)

@_mcp.tool(name="palace.ingest.list_extractors", description=(
    "List registered extractors with their descriptions. Discovery endpoint."
))
async def _palace_ingest_list_extractors() -> dict[str, Any]:
    return {
        "ok": True,
        "extractors": [
            {"name": e.name, "description": e.description}
            for e in _list_extractors()
        ],
    }
```

## 5. Schema conventions

### 5.1 Extractor-owned labels

Each extractor owns its labels outright. No framework-managed shared labels except `:IngestRun` (tracking, not domain data) and `:ExtractorHeartbeat` (diagnostic).

**Rules:**
- Every node MUST have `group_id`. Runtime integrity invariant — same as existing `memory/constraints.py:57` check for Issue/Comment/Agent/IngestRun.
- MERGE by natural key (extractor-specific: `sha` for `:Commit`, `(module, name)` for `:Symbol`, etc.). Re-runs idempotent.
- Cross-extractor edges (e.g., `:TOUCHED(commit, file)` where both are from different extractors) — soft contract. Operator runs extractors in dependency order. Framework does not enforce DAG — followup if needed.

### 5.2 `:IngestRun` reuse

Existing schema (GIM-34):
```
:IngestRun {id, source, group_id, started_at, finished_at, duration_ms, errors, success}
```

**Extend with 2 optional fields** for extractor runs (nullable — back-compat with paperclip ingest runs):
```
:IngestRun {..., nodes_written: int | null, edges_written: int | null}
```

**Source convention:**
- `source = "paperclip"` — existing paperclip ingest (unchanged).
- `source = "extractor.<name>"` — extractor runs. Health queries via `palace.memory.health()` work unchanged; `source` field shows up per-run.

New Cypher statements in **`extractors/cypher.py`** (isolated from `memory/cypher.py` — extractor concerns stay in extractor package):

```python
# extractors/cypher.py
CREATE_INGEST_RUN = """
CREATE (r:IngestRun {
  id: $id,
  source: $source,
  group_id: $group_id,
  started_at: $started_at,
  finished_at: null,
  duration_ms: null,
  nodes_written: null,
  edges_written: null,
  errors: [],
  success: null
})
RETURN r
"""

FINALIZE_INGEST_RUN = """
MATCH (r:IngestRun {id: $id})
SET r.finished_at = $finished_at,
    r.duration_ms = $duration_ms,
    r.nodes_written = $nodes_written,
    r.edges_written = $edges_written,
    r.errors = $errors,
    r.success = $success
RETURN r
"""
```

### 5.3 Schema diff — what N+2a adds

New in `ensure_extractors_schema()` (aggregated from HeartbeatExtractor):
```sql
CREATE CONSTRAINT extractor_heartbeat_id IF NOT EXISTS
  FOR (h:ExtractorHeartbeat) REQUIRE h.run_id IS UNIQUE

CREATE INDEX extractor_heartbeat_group_id IF NOT EXISTS
  FOR (n:ExtractorHeartbeat) ON (n.group_id)

CREATE INDEX extractor_heartbeat_ts IF NOT EXISTS
  FOR (n:ExtractorHeartbeat) ON (n.ts)
```

Plus 2 new nullable properties on existing `:IngestRun` (no constraint/index — optional properties auto-added by Neo4j).

## 6. Observability

### 6.1 Structured logs

Three runner-level events per call (JSON, stdlib `logging` → stdout):

```json
{"event": "extractor.run.start", "ts": "...", "extractor": "heartbeat", "project": "gimle", "run_id": "<uuid>", "group_id": "project/gimle"}

{"event": "extractor.run.finish", "ts": "...", "extractor": "heartbeat", "project": "gimle", "run_id": "<uuid>", "duration_ms": 123, "nodes_written": 1, "edges_written": 0, "success": true}

{"event": "extractor.run.error", "ts": "...", "extractor": "heartbeat", "project": "gimle", "run_id": "<uuid>", "duration_ms": 23, "error_code": "extractor_config_error", "error_head": "gradle not found in PATH"}
```

Extractor-internal logs via `ctx.logger` (pre-scoped to `palace_mcp.extractors.<name>`). Extractor author chooses format; recommended JSON + `run_id` for correlation.

### 6.2 What is NOT logged

Per GIM-54 §6.1 privacy pattern:
- User-provided `project` slug — OK (validated, safe).
- Commit/file contents, Cypher parameters values, stack traces — **never** in `:IngestRun.errors` or MCP response. Stack trace → stdout only via `logger.exception`.
- Stderr / subprocess output — truncate to 4096 bytes if logged (matches GIM-54 git-mcp practice).

### 6.3 Health integration — current state + decision

**Verified against code** (`memory/health.py:46` at `origin/develop@41d23d2`):

```python
ingest_result = await tx.run(LATEST_INGEST_RUN, source="paperclip")
```

Current `palace.memory.health()` response **hardcodes `source="paperclip"`** — extractor runs do NOT appear in the `last_ingest_*` fields today. My initial "zero code changes" claim was wrong (caught by independent review).

**Decision (MVP):** leave `memory/health.py` unchanged. Extractor runs are queryable via the already-existing `palace.memory.lookup(entity_type="IngestRun", ...)` tool from GIM-52/53, filtered by `source="extractor.<name>"`. The dedicated health summary for extractor runs is a followup (`extractors: {heartbeat: {...}, ...}` grouping in health response).

**Phase 2 task (added to §11):** Verify via a test that `memory.health.LATEST_INGEST_RUN` query still returns accurate paperclip data after this slice ships (regression guard — new `:IngestRun.nodes_written` field is nullable, so paperclip rows should parse unchanged).

## 7. Testing

### 7.1 Unit tests — mock driver (`tests/extractors/unit/`)

- `test_base.py` — ABC subclass without `name`/`extract` raises; ExtractionContext frozen; ExtractorStats defaults.
- `test_registry.py` — register() rejects dup name; get() returns None for unknown; list_all() preserves registration order.
- `test_runner.py` — runner lifecycle with `AsyncMock(AsyncDriver)`: validate→create-IngestRun→extract→finalize order; Exception → error_code mapping; timeout (mocked `asyncio.wait_for`) → `extractor_runtime_error`; slug/name/project/repo pre-check fails early without calling extract().
- `test_heartbeat.py` — extract() uses correct Cypher + params; returns `ExtractorStats(1, 0)`.
- `test_schemas_response.py` — Pydantic models: `extra="forbid"`, required fields, error envelope distinct from success.

Target: ~30 unit tests.

### 7.2 Integration tests — real Neo4j (`tests/extractors/integration/`)

Fixture `neo4j_container` in `tests/extractors/integration/conftest.py`:

```python
# conftest.py (integration)
@pytest.fixture(scope="session")
def neo4j_uri() -> str:
    """Prefer reuse of existing Neo4j via env var; else spin up testcontainers."""
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        # CI and dev with `docker compose --profile review up` set this:
        # COMPOSE_NEO4J_URI=bolt://localhost:7687
        return reuse
    # Fallback: boot a throwaway container for this test session.
    from testcontainers.neo4j import Neo4jContainer
    container = Neo4jContainer("neo4j:5.26.0")
    container.start()
    yield container.get_connection_url()
    container.stop()
```

**Env var contract (documented explicitly):**
- `COMPOSE_NEO4J_URI=bolt://localhost:7687` — set by CI job when a Neo4j service container is available (saves ~30s testcontainers boot per run).
- Absent — tests fall back to `testcontainers-neo4j` auto-boot.
- `testcontainers-neo4j` is a **dev-only** dependency in `pyproject.toml` (`[tool.uv.dependency-groups.dev]`), not shipped to production image.

Plan Task 2.10 covers this conftest + dep + CI wiring explicitly.

- `test_ensure_extractors_schema.py` — on clean Neo4j, creates expected constraint + 2 indexes. Idempotent on re-run.
- `test_heartbeat_integration.py` — full `run_extractor("heartbeat", "<test-project>")` writes `:IngestRun` + `:ExtractorHeartbeat` correctly; re-run with separate run_id produces 2 of each.
- `test_runner_error_paths_integration.py` — unknown extractor / unknown project / repo_not_mounted return error envelopes; failed extractor sets `:IngestRun.success=false` + non-empty `errors`.
- `test_mcp_tool_integration.py` — end-to-end via FastMCP test client; verifies response shape.

Target: ~10-15 integration tests.

### 7.3 Coverage invariants (checklist, not count quota)

- [ ] Every error_code from §4.1 enum exercised in at least one test.
- [ ] `ensure_extractors_schema` creates all declared constraints/indexes and survives re-run.
- [ ] Every registered extractor has ≥1 smoke integration test.
- [ ] Registry duplicate-register throws.
- [ ] Timeout mocked — runner transitions to `extractor_runtime_error`.
- [ ] Unhandled Exception (non-ExtractorError) — runner catches, returns `unknown`, stack trace NOT in response.

### 7.4 What is mocked / not mocked (hybrid per §2 brainstorm)

**Not mocked:**
- Neo4j driver in integration tests — real via testcontainers.
- Heartbeat happy path integration — real Cypher persist.

**Mocked OK:**
- `asyncio.wait_for` raising `TimeoutError` (unit test, hard to reproduce cleanly otherwise).
- Specific Neo4j driver exceptions (`ServiceUnavailable`, `ClientError`) for error-path unit coverage.

### 7.5 mypy + lint

- `mypy --strict` clean on `palace_mcp/extractors/` + all test files.
- `ruff check` + `ruff format --check` green (remember GIM-54 lesson: CI runs both; local `ruff check` alone not enough).

## 8. Out of scope (followups)

1. **Real extractors.** #22 Git History Harvester (N+2b, next slice), #21 Symbol Index, #1 Architecture Layer, #25 Build System — each separate slice.
2. **Scheduler / cron.** Periodic extractor runs via cron-service container. MCP-triggered only in MVP.
3. **Per-extractor `options: dict` parameter.** If Symbol Index wants `since="2026-01-01"`, followup extends tool signature.
4. **`palace.ingest.cancel_run(run_id)`.** Timeout cap covers 95% cases; followup if needed.
5. **`palace.ingest.get_run(run_id)` dedicated tool.** `palace.memory.lookup(entity_type="IngestRun", filters={"source": "extractor.heartbeat"})` already works.
6. **Framework-managed DAG / cross-extractor ordering.** Soft contract (operator's responsibility) in MVP; enforcement is followup.
7. **Concurrent extractor runs.** Serialized by palace-mcp event loop; throughput guarantees not claimed.
8. **Metrics / Prometheus / OTEL.** Observability-integration slice.
9. **CLI wrapper (`just run-extractor`).** MCP tool suffices for operator + agents.
10. **Per-extractor auth scoping** (some extractors require token permission). Pairs with agent-MCP on `:8002` — N+1c-revisited territory.
11. **UI-friendly `extractors: {...}` grouping in `palace.memory.health()`.** Current response already shows per-source runs; grouping is cosmetic.
12. **`:IngestRun` garbage collection** for high-frequency heartbeat runs. Existing `palace.memory.gc` pattern (if shipped) extends naturally.

## 9. Acceptance criteria

- [ ] Package `palace_mcp/extractors/` with 8 files: `__init__.py` (empty), `base.py`, `registry.py`, `runner.py`, `schema.py`, `schemas.py`, `cypher.py`, `heartbeat.py`.
- [ ] `BaseExtractor` ABC with `name`/`description`/`constraints`/`indexes` ClassVars and abstract `extract()` coroutine.
- [ ] `ExtractionContext` frozen dataclass: driver, project_slug, group_id, repo_path, run_id, logger.
- [ ] `ExtractorStats` frozen dataclass: nodes_written, edges_written (both default 0).
- [ ] `ExtractorError` / `ExtractorConfigError` / `ExtractorRuntimeError` with `error_code` class attribute.
- [ ] Registry with register/get/list_all; heartbeat pre-registered.
- [ ] Runner full lifecycle per §3.4 — validate → create :IngestRun → asyncio.wait_for(extract, timeout=300) → finalize — with all 8 error_codes handled.
- [ ] `ensure_extractors_schema()` aggregates declared constraints + indexes; called in `main.py` lifespan.
- [ ] `HeartbeatExtractor` ships: 40 LOC, declares constraint + 2 indexes, writes one `:ExtractorHeartbeat` MERGE by run_id.
- [ ] Pydantic `ExtractorRunResponse` / `ExtractorErrorResponse` / `ExtractorListResponse` with `extra="forbid"`.
- [ ] MCP tools `palace.ingest.run_extractor` and `palace.ingest.list_extractors` registered in `mcp_server.py`.
- [ ] Cypher statements `CREATE_INGEST_RUN` + `FINALIZE_INGEST_RUN` in `extractors/cypher.py` with new optional `nodes_written` / `edges_written` fields (NULL-initialized on create, set on finalize).
- [ ] QA Phase 4.1 evidence (§2 success criteria 1-6 reproduced live on iMac) in PR body `## QA Evidence` section.
- [ ] mypy `--strict` clean on new package; ruff check + format green.
- [ ] Unit + integration tests per §7 coverage checklist; `uv run pytest` all green.
- [ ] CLAUDE.md `## Extractors` section added — framework overview, how to register new extractor.
- [ ] Rollback runbook added — since schema changes (new constraint + 2 indexes), rollback procedure should document `DROP CONSTRAINT extractor_heartbeat_id; DROP INDEX extractor_heartbeat_group_id; DROP INDEX extractor_heartbeat_ts` + `MATCH (n:ExtractorHeartbeat) DETACH DELETE n`.

## 10. Risks

1. **Runner lifecycle bug escapes test coverage.** Complex async/try-except/finalize paths. Mitigation: explicit test per error_code + mocked timeout + integration smoke. Residual: chaos test (extractor panics in the middle) — followup.
2. **Heartbeat schema footprint in production.** 1 new label + constraint + 2 indexes. Diagnostic data accumulates if someone scripts heartbeat in a loop. Mitigation: operator-accepted risk; GC followup.
3. **`:IngestRun` optional new properties (`nodes_written`/`edges_written`) break consumers.** Existing `memory/health.py` reads specific fields; new fields are additive. Verify via `test_mcp_tool_integration.py` that health response still parses.
4. **testcontainers-neo4j CI latency.** Adds ~30s container boot per integration run. Mitigation: offer `COMPOSE_NEO4J_URI` env var so CI with neo4j-service skips boot.
5. **Schema drift across extractor releases.** If N+2b Git History changes `:Commit` schema mid-version, `IF NOT EXISTS` protects constraint but not semantics. Acceptable for MVP; schema-versioning is a larger followup.

6. **`ensure_extractors_schema` startup failure crashes palace-mcp.** If any `CREATE CONSTRAINT`/`CREATE INDEX` fails (insufficient Neo4j permissions, edition incompatibility, pre-existing conflicting constraint with different definition), the lifespan throws — container restarts in a crash loop. No retry / partial-success semantics in MVP. **Acceptable** because: (a) `IF NOT EXISTS` makes re-runs safe, so failure is a legitimate environment misconfiguration that needs human fix; (b) a silent-partial-schema state would be worse (extractors would write to Neo4j thinking constraints are in place). **Fail-loud > fail-silent.** Operator sees clear error in `docker logs` and can investigate (likely: Neo4j version mismatch or restart needed).

## 11. Decomposition (plan-first ready)

Expected plan: `docs/superpowers/plans/2026-04-20-GIM-59-extractor-framework-substrate.md` on this same feature branch. CTO resolves GIM-59 on Phase 1.1 (or operator bootstraps if CTO ban narrowing from GIM-57 hasn't propagated yet — verify).

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1.1 | 1.1.1 | CTO | Verify spec path; rename plan GIM-NN (if any leftover) → GIM-59; commit + push on feature branch (per narrowed `cto-no-code-ban.md` from GIM-57). Reassign CR. |
| 1.2 | 1.2.1 | CodeReviewer | Plan-first: every spec §9 acceptance item maps to a Phase 2 task; Phase 4.1 QA scenarios match §2 success criteria. APPROVE or findings. |
| 2 | 2.1 | PythonEngineer | Scaffold `extractors/` package skeleton (6 files empty). Commit. |
| 2 | 2.2 | PE | `base.py` — BaseExtractor ABC + ExtractionContext + ExtractorStats + errors. Unit tests. |
| 2 | 2.3 | PE | `schemas.py` — Pydantic response models. mypy --strict check. |
| 2 | 2.4 | PE | `registry.py` — EXTRACTORS dict + register/get/list_all + unit tests. |
| 2 | 2.5 | PE | `extractors/cypher.py` — CREATE_INGEST_RUN + FINALIZE_INGEST_RUN statements, isolated from `memory/cypher.py`. New fields `nodes_written` + `edges_written` are nullable so parallel paperclip ingest runs (which don't write counts) are unaffected. |
| 2 | 2.6 | PE | `runner.py` — full lifecycle per §3.4. Unit tests for all error_codes + success + timeout. |
| 2 | 2.7 | PE | `schema.py` — ensure_extractors_schema aggregator. Integration test for constraint + index creation. |
| 2 | 2.8 | PE | `heartbeat.py` — HeartbeatExtractor class + integration test (real Neo4j, verify node persisted). |
| 2 | 2.9 | PE | Wire to `main.py` lifespan + `mcp_server.py` MCP tools. End-to-end integration test. |
| 2 | 2.10 | PE | `testcontainers-neo4j` dev dependency in `pyproject.toml` + `tests/extractors/integration/conftest.py` `neo4j_uri` fixture with `COMPOSE_NEO4J_URI` env-var fallback (see §7.2). Dry-run: fixture boots container when env-var absent; reuses compose Neo4j when set. |
| 2 | 2.10a | PE | Verify **consumer compatibility** with new `:IngestRun` nullable fields. Explicit test: parse existing paperclip ingest rows (e.g., from gimle fixture) through the `memory/health.py` `LATEST_INGEST_RUN` path after schema extension — assert no regression when `nodes_written` / `edges_written` are NULL on paperclip rows. Confirms §6.3 decision "leave health.py unchanged" holds. |
| 2 | 2.11 | **PE → TW handoff.** PE posts paperclip comment `## Phase 2 code complete, handoff to TW for Task 2.12 docs` + reassigns `TechnicalWriter` (`0e8222fd-88b9-4593-98f6-847a448b0aab`). |
| 2 | 2.12 | TechnicalWriter | CLAUDE.md `## Extractors` section — framework overview, how to register new extractor, MCP tool examples. Rollback runbook entry in `docs/runbooks/` (schema-drop + `MATCH (n:ExtractorHeartbeat) DETACH DELETE n`). |
| 3.1 | 3.1 | CodeReviewer | Mechanical: ruff + mypy + pytest output pasted; compliance checklist against §9 acceptance; `gh pr review --approve` (new CR bridge from GIM-57). |
| 3.2 | 3.2 | OpusArchitectReviewer | Adversarial: runner lifecycle edge cases (session leak, partial finalize on panic), Neo4j property drift for `:IngestRun` (new nullable fields vs existing consumers like `memory/health.py:46` hardcoded `source="paperclip"`), `ensure_extractors_schema` startup-crash semantics, extractor exception hierarchy coverage (do we miss `neo4j.exceptions.ServiceUnavailable` / `ClientError`?). Registry thread-safety explicitly **not** in scope — single event loop, import-time registration. |
| 4.1 | 4.1 | QAEngineer | Live smoke on iMac: §2 success criteria 1-7 reproduced. Evidence comment with commit SHA + Cypher-shell outputs + response payloads. Fills `## QA Evidence` in PR body (required check). |
| 4.2 | 4.2 | CTO | Squash-merge via `gh pr merge --squash --delete-branch`. CI green (5 checks incl. qa-evidence-present). Close GIM-59. |

Operator (Board) role for this slice: no Phase 4.3 ritual since this slice doesn't change branch protection — normal close by CTO.

## 12. Size estimate

- Production code: ~450 LOC across 8 files (incl. empty `__init__.py`).
- Tests: ~50 tests, ~600 LOC.
- Docs: ~50 LOC (CLAUDE.md section + rollback entry).
- mypy --strict clean; ruff clean.
- 1 PR on feature branch `feature/GIM-59-extractor-framework-substrate`.
- **1-1.5 days agent-time** (revised up from initial 1-day estimate per reviewer NUDGE — 450 LOC prod + 600 LOC tests at palace-mcp's quality bar likely needs 2 CR rounds, matching GIM-54 precedent). Smaller than GIM-57 (no CI/branch-protection work); larger than a pure-docs slice.

## 13. Followups

1. **N+2b — Git History Harvester** (extractor #22). Uses framework from this slice. Writes `:Commit`, `:File`, `:TOUCHED`. Complementary to `palace.git.*` tools from GIM-54 (ad-hoc reads ↔ structured graph).
2. **release-cut-v2** (from GIM-57 followups) — unrelated but open.
3. **Scheduler / cron service** — periodic extractor runs. Evaluate when 2+ extractors live.
4. **Observability integration** — Prometheus metrics for runner + extractor counts.
5. **Per-extractor options param.** Extend `run_extractor(name, project, options)` when first extractor needs it (Symbol Index likely).
6. **Extractor DAG ordering** — framework-managed cross-extractor dependencies. When 3+ extractors live.
7. **CLI wrapper.** YAGNI; add if Board workflow demands.
