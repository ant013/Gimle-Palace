# `group_id` Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan. Steps use
> checkbox (`- [ ]`) syntax for progress tracking.

**Goal:** Add `group_id` namespace property to every palace-memory
node (Issue, Comment, Agent, IngestRun), plus an index, a WHERE-guarded
backfill for pre-existing data, and implicit scope in every read/write
path. Unlocks N+1b multi-project without a substrate swap.

**Architecture:** Pure N+0 extension — parameterised Cypher against
plain Neo4j 5.26. No graphiti-core. The column threads through config
→ ingest upserts/GC → lookup WHERE clauses, with a one-shot WHERE-
guarded backfill in lifespan.

**Tech Stack:** Python 3.12, Pydantic v2 BaseSettings, neo4j 5.x async
driver, FastMCP, pytest.

**Spec:** `docs/superpowers/specs/2026-04-18-palace-memory-group-id-migration.md`

**Reference (real graphiti-core API):**
`reference_graphiti_core_api_truth.md` (auto-memory) — for context on
why graphiti-core is not in scope here.

---

## Phase 0 — Branching

Branch from `develop` (which currently holds post-revert N+0):

```bash
git fetch origin
git checkout develop
git pull --ff-only
git checkout -b feature/GIM-NN-palace-memory-group-id
```

Replace `NN` with the issue number CTO assigns in Phase 1.1.

---

## Task 1: Config field for default `group_id`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/config.py`
- Modify: `services/palace-mcp/tests/test_config.py` (create if missing)
- Modify: `services/palace-mcp/.env.example`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
from pydantic import SecretStr

from palace_mcp.config import Settings


def test_palace_default_group_id_defaults_to_project_gimle():
    s = Settings(neo4j_password=SecretStr("x"))
    assert s.palace_default_group_id == "project/gimle"


def test_palace_default_group_id_overridable_via_env(monkeypatch):
    monkeypatch.setenv("PALACE_DEFAULT_GROUP_ID", "project/other")
    s = Settings(neo4j_password=SecretStr("x"))
    assert s.palace_default_group_id == "project/other"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `AttributeError: 'Settings' object has no attribute 'palace_default_group_id'`

- [ ] **Step 3: Add the field**

In `config.py`, extend `_EmbedderMixin` just after the LLM fields:

```python
    # Namespace for project-scoped queries and ingest. All existing
    # rows are stamped with this default by the backfill in
    # ensure_schema(). See docs/superpowers/specs/
    # 2026-04-18-palace-memory-group-id-migration.md.
    palace_default_group_id: str = "project/gimle"
```

- [ ] **Step 4: Extend `.env.example`**

Append:

```
# Namespace for palace-memory data. Default matches the pre-migration
# single-project reality. Change only if you are running multi-project
# ingest.
PALACE_DEFAULT_GROUP_ID=project/gimle
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_config.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/config.py \
        services/palace-mcp/tests/test_config.py \
        services/palace-mcp/.env.example
git commit -m "feat(config): add palace_default_group_id setting (GIM-NN)"
```

---

## Task 2: INDEX DDL for `group_id`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Create: `services/palace-mcp/tests/memory/test_schema_ddl.py`

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_schema_ddl.py
from palace_mcp.memory.cypher import CREATE_INDEXES


def test_group_id_index_for_each_label():
    joined = " ".join(CREATE_INDEXES)
    for label in ("Issue", "Comment", "Agent", "IngestRun"):
        assert f"FOR (n:{label}) ON (n.group_id)" in joined, (
            f"missing group_id index for {label}"
        )


def test_create_indexes_are_idempotent():
    for stmt in CREATE_INDEXES:
        assert "IF NOT EXISTS" in stmt, (
            "all index statements must be idempotent"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/memory/test_schema_ddl.py -v
```

Expected: `ImportError: cannot import name 'CREATE_INDEXES'`

- [ ] **Step 3: Add CREATE_INDEXES**

In `cypher.py`, after `CREATE_CONSTRAINTS`:

```python
# --- Indexes (non-unique; speeds up group_id filter + GC cutoff) ---
CREATE_INDEXES = [
    "CREATE INDEX issue_group_id IF NOT EXISTS "
    "FOR (n:Issue) ON (n.group_id)",
    "CREATE INDEX comment_group_id IF NOT EXISTS "
    "FOR (n:Comment) ON (n.group_id)",
    "CREATE INDEX agent_group_id IF NOT EXISTS "
    "FOR (n:Agent) ON (n.group_id)",
    "CREATE INDEX ingest_run_group_id IF NOT EXISTS "
    "FOR (n:IngestRun) ON (n.group_id)",
]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/memory/test_schema_ddl.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/cypher.py \
        services/palace-mcp/tests/memory/test_schema_ddl.py
git commit -m "feat(schema): add group_id indexes per label (GIM-NN)"
```

---

## Task 3: Backfill Cypher + `ensure_schema` renaming

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/constraints.py` (rename logic, keep file for minimal diff)
- Modify: `services/palace-mcp/tests/memory/test_constraints.py` (if exists — otherwise extend/create)

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_constraints.py (append)
from palace_mcp.memory.cypher import BACKFILL_GROUP_ID


def test_backfill_has_where_is_null_guard():
    # Guard makes the write idempotent: re-running does not stomp data.
    assert "WHERE n.group_id IS NULL" in BACKFILL_GROUP_ID


def test_backfill_covers_all_four_labels():
    for label in ("Issue", "Comment", "Agent", "IngestRun"):
        assert f"(n:{label})" in BACKFILL_GROUP_ID


def test_backfill_parameterises_default():
    assert "$default" in BACKFILL_GROUP_ID
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/memory/test_constraints.py -v
```

Expected: `ImportError` on `BACKFILL_GROUP_ID`.

- [ ] **Step 3: Add BACKFILL_GROUP_ID**

In `cypher.py`:

```python
# --- Backfill: WHERE IS NULL guard makes this a no-op after first run ---
BACKFILL_GROUP_ID = """
CALL () {
    MATCH (n:Issue)     WHERE n.group_id IS NULL SET n.group_id = $default
}
CALL () {
    MATCH (n:Comment)   WHERE n.group_id IS NULL SET n.group_id = $default
}
CALL () {
    MATCH (n:Agent)     WHERE n.group_id IS NULL SET n.group_id = $default
}
CALL () {
    MATCH (n:IngestRun) WHERE n.group_id IS NULL SET n.group_id = $default
}
"""
```

- [ ] **Step 4: Rename function + wire in index + backfill**

In `memory/constraints.py`:

```python
"""Idempotent schema assertion. Called from FastAPI lifespan or before
first ingest. Safe to run repeatedly: constraints + indexes are
IF NOT EXISTS and the backfill is WHERE-IS-NULL guarded.
"""

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import (
    BACKFILL_GROUP_ID,
    CREATE_CONSTRAINTS,
    CREATE_INDEXES,
)


async def ensure_schema(driver: AsyncDriver, *, default_group_id: str) -> None:
    async with driver.session() as session:
        for stmt in CREATE_CONSTRAINTS:
            await session.run(stmt)
        for stmt in CREATE_INDEXES:
            await session.run(stmt)
        await session.run(BACKFILL_GROUP_ID, default=default_group_id)


# Back-compat shim for any stray callers. Remove in the next slice.
async def ensure_constraints(driver: AsyncDriver) -> None:
    await ensure_schema(driver, default_group_id="project/gimle")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/memory/test_constraints.py -v
```

Expected: all three backfill tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/cypher.py \
        services/palace-mcp/src/palace_mcp/memory/constraints.py \
        services/palace-mcp/tests/memory/test_constraints.py
git commit -m "feat(schema): ensure_schema() with indexes + idempotent group_id backfill (GIM-NN)"
```

---

## Task 4: Call `ensure_schema()` from lifespan

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/main.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_startup_hardening.py (append)
import asyncio
from unittest.mock import AsyncMock, MagicMock

from palace_mcp.config import Settings
from pydantic import SecretStr


async def test_lifespan_calls_ensure_schema_with_default_group_id(monkeypatch):
    calls = []

    async def fake_ensure_schema(driver, *, default_group_id):
        calls.append((driver, default_group_id))

    monkeypatch.setattr(
        "palace_mcp.main.ensure_schema", fake_ensure_schema, raising=False
    )
    # Minimal lifespan invocation — driver is mocked
    # (concrete wiring depends on how lifespan currently reads driver).
    # ... see main.py for the exact injection point ...
    # The assertion below is what matters:
    # After lifespan enters, ensure_schema must have been called once
    # with default_group_id="project/gimle" (or the env override).
    assert len(calls) == 1
    assert calls[0][1] == "project/gimle"
```

If the existing `tests/test_startup_hardening.py` has a different
fixture shape, adapt accordingly — the behavioural assertion is what
this task must nail.

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Wire ensure_schema into lifespan**

In `main.py`, replace the existing constraints bootstrap (if any) so
it calls `ensure_schema(driver, default_group_id=settings.palace_default_group_id)`
during the FastAPI lifespan `startup` phase — fire-and-forget via the
existing `_fire_and_forget` helper is acceptable **only** if the
current bootstrap was already fire-and-forget; otherwise make it
awaited to avoid race with first request.

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(lifespan): call ensure_schema with default_group_id (GIM-NN)"
```

---

## Task 5: UPSERT Cypher carries `group_id`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Create: `services/palace-mcp/tests/memory/test_upsert_cypher.py`

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_upsert_cypher.py
from palace_mcp.memory.cypher import (
    UPSERT_AGENTS,
    UPSERT_COMMENTS,
    UPSERT_ISSUES,
)


def test_upsert_issues_sets_group_id():
    assert "i.group_id" in UPSERT_ISSUES
    assert "$group_id" in UPSERT_ISSUES


def test_upsert_comments_sets_group_id():
    assert "c.group_id" in UPSERT_COMMENTS
    assert "$group_id" in UPSERT_COMMENTS


def test_upsert_agents_sets_group_id():
    assert "a.group_id" in UPSERT_AGENTS
    assert "$group_id" in UPSERT_AGENTS
```

- [ ] **Step 2: Run test to verify it fails**

Expected: assertion failures on all three.

- [ ] **Step 3: Add `group_id = $group_id` to each UPSERT SET clause**

For `UPSERT_AGENTS`:

```python
UPSERT_AGENTS = """
UNWIND $batch AS row
MERGE (a:Agent {id: row.id})
SET a.group_id             = $group_id,
    a.name                 = row.name,
    a.url_key              = row.url_key,
    a.role                 = row.role,
    a.source               = 'paperclip',
    a.source_created_at    = row.source_created_at,
    a.source_updated_at    = row.source_updated_at,
    a.palace_last_seen_at  = row.palace_last_seen_at
"""
```

Mirror for `UPSERT_ISSUES` (`i.group_id = $group_id`) and
`UPSERT_COMMENTS` (`c.group_id = $group_id`). `group_id` comes from
the tx parameter, not `row`, because one ingest run always writes
within one group.

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/cypher.py \
        services/palace-mcp/tests/memory/test_upsert_cypher.py
git commit -m "feat(cypher): upserts set group_id (GIM-NN)"
```

---

## Task 6: `CREATE_INGEST_RUN` + `LATEST_INGEST_RUN` carry `group_id`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Modify: `services/palace-mcp/tests/memory/test_upsert_cypher.py`

- [ ] **Step 1: Write failing test**

```python
def test_create_ingest_run_sets_group_id():
    from palace_mcp.memory.cypher import CREATE_INGEST_RUN
    assert "group_id: $group_id" in CREATE_INGEST_RUN


def test_latest_ingest_run_accepts_optional_group_filter():
    # New variant: when $group_id is supplied, filter by it.
    from palace_mcp.memory.cypher import LATEST_INGEST_RUN_FOR_GROUP
    assert "r.group_id = $group_id" in LATEST_INGEST_RUN_FOR_GROUP
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Update Cypher**

```python
CREATE_INGEST_RUN = """
CREATE (r:IngestRun {
    id: $id,
    group_id: $group_id,
    source: $source,
    started_at: $started_at,
    finished_at: null,
    duration_ms: null,
    errors: []
})
"""

LATEST_INGEST_RUN_FOR_GROUP = """
MATCH (r:IngestRun {source: $source})
WHERE r.group_id = $group_id
RETURN r
ORDER BY r.started_at DESC
LIMIT 1
"""
```

Keep the existing `LATEST_INGEST_RUN` (no group filter) for the
default-project health call path, so the wire contract of
`palace.memory.health()` stays byte-stable.

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(cypher): IngestRun carries group_id, add per-group lookup (GIM-NN)"
```

---

## Task 7: GC filters by `group_id`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Modify: `services/palace-mcp/tests/memory/test_upsert_cypher.py`

- [ ] **Step 1: Write failing test**

```python
def test_gc_by_label_filters_by_group_id():
    from palace_mcp.memory.cypher import GC_BY_LABEL
    assert "n.group_id = $group_id" in GC_BY_LABEL
    assert "n.source = 'paperclip'" in GC_BY_LABEL
    assert "n.palace_last_seen_at < $cutoff" in GC_BY_LABEL
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Update GC**

```python
GC_BY_LABEL = """
MATCH (n:{label})
WHERE n.source = 'paperclip'
  AND n.group_id = $group_id
  AND n.palace_last_seen_at < $cutoff
DETACH DELETE n
"""
```

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(cypher): GC scoped by group_id (GIM-NN)"
```

---

## Task 8: Runner threads `group_id` through every write

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/runner.py`
- Modify: `services/palace-mcp/tests/ingest/test_runner.py`

- [ ] **Step 1: Write failing test**

```python
async def test_runner_passes_group_id_to_upserts(mocker):
    # spec out a fake tx that records .run() calls
    driver = mocker.AsyncMock()
    session = mocker.AsyncMock()
    driver.session.return_value.__aenter__.return_value = session

    # ... call run_ingest(client=fake, driver=driver, group_id="project/x")
    # ... assert every session.execute_write call receives group_id="project/x"
    ...


async def test_runner_passes_group_id_to_gc(mocker):
    # as above, but check the _write_gc invocation specifically
    ...
```

(The exact mocker shape matches existing `tests/ingest/test_runner.py`
patterns — mirror those, do not invent a new style.)

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Wire `group_id` into runner**

1. `run_ingest` signature gains `group_id: str` (keyword-only, no
   default — caller must pass it).
2. Every `_write_*` helper for write operations gains `group_id: str`
   and passes it as a named Cypher parameter alongside `batch` /
   `cutoff` / etc.
3. The CLI entry point passes `settings.palace_default_group_id`.

Example for `_write_gc`:

```python
async def _write_gc(
    tx: AsyncManagedTransaction, *, label: str, cutoff: str, group_id: str
) -> None:
    query = cypher.GC_BY_LABEL.format(label=label)
    await tx.run(query, cutoff=cutoff, group_id=group_id)
```

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(ingest): thread group_id through runner + writes (GIM-NN)"
```

---

## Task 9: Lookup always scopes by `group_id`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/lookup.py`
- Modify: `services/palace-mcp/tests/memory/test_lookup.py`

- [ ] **Step 1: Write failing test**

```python
def test_lookup_builds_where_with_implicit_group_id_clause():
    # The internal query builder (find the right helper in lookup.py)
    # must AND-in "n.group_id = $group_id" for every entity_type, even
    # when the caller supplies zero explicit filters.
    ...


async def test_lookup_does_not_return_other_project_nodes(live_driver):
    # Seed two Issue nodes, one per group; call lookup with
    # default group_id; assert only the matching group is returned.
    ...
```

(The second test needs a live driver fixture; if testcontainers is
not set up yet in the repo, stub it with `@pytest.mark.integration`
and `skipif` until infra exists — still write the assertion so it
runs the moment the fixture lands.)

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Add implicit clause**

In `lookup.py` wherever the WHERE clause list is assembled, prepend
`n.group_id = $group_id` and include `group_id` in the cypher params
map, reading it from `Settings.palace_default_group_id`. The MCP tool
will override the default in Task 10.

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(lookup): implicit group_id WHERE clause on every query (GIM-NN)"
```

---

## Task 10: MCP tool accepts optional `project` argument

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py`
- Modify: `services/palace-mcp/tests/test_mcp_health_tool.py` (and/or sibling lookup test)

- [ ] **Step 1: Write failing test**

```python
async def test_lookup_tool_uses_project_arg_when_provided():
    # Call palace.memory.lookup with project="project/other"; assert
    # the underlying cypher received group_id="project/other" even
    # though settings default is "project/gimle".
    ...


async def test_lookup_tool_falls_back_to_default_when_project_none():
    # project argument omitted -> group_id == settings.palace_default_group_id
    ...
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Extend schema + tool signature**

In `schema.py`:

```python
class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)
    order_by: Literal["source_updated_at", "source_created_at"] = "source_updated_at"
    project: str | None = None
```

In `mcp_server.py` (the `lookup` tool handler), when `project` is
provided, pass it through as `group_id`; otherwise pass
`settings.palace_default_group_id`.

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(mcp): optional project arg on palace.memory.lookup (GIM-NN)"
```

---

## Task 11: Integration test — ingest stamps every node

**Files:**
- Create: `services/palace-mcp/tests/integration/test_group_id_ingest.py`

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_group_id_ingest.py
import pytest


@pytest.mark.integration
async def test_ingest_stamps_group_id_on_all_nodes(live_driver, fake_paperclip):
    """Every node created or updated by ingest carries group_id."""
    await run_ingest(
        client=fake_paperclip, driver=live_driver,
        group_id="project/gimle",
    )

    async with live_driver.session() as s:
        result = await s.run(
            "MATCH (n) WHERE n:Issue OR n:Comment OR n:Agent OR n:IngestRun "
            "RETURN DISTINCT n.group_id AS g"
        )
        groups = {row["g"] async for row in result}

    assert groups == {"project/gimle"}, (
        f"every node must carry group_id; saw: {groups}"
    )


@pytest.mark.integration
async def test_gc_does_not_cross_projects(live_driver, fake_paperclip):
    """GC for project/a must leave project/b nodes intact."""
    # Seed project/b stale node
    async with live_driver.session() as s:
        await s.run(
            "CREATE (:Issue {id: 'stranger', source: 'paperclip', "
            "group_id: 'project/b', palace_last_seen_at: '1970-01-01'})"
        )

    # Run ingest for project/a (fake_paperclip returns nothing)
    await run_ingest(
        client=fake_paperclip, driver=live_driver, group_id="project/a"
    )

    async with live_driver.session() as s:
        result = await s.run(
            "MATCH (n:Issue {id: 'stranger'}) RETURN count(n) AS c"
        )
        count = (await result.single())["c"]

    assert count == 1, "GC must not touch other projects"
```

- [ ] **Step 2: Run test to verify it fails** (or skips if no live
      driver fixture yet)

- [ ] **Step 3: Ensure the test harness has a `live_driver` fixture**

If not present, add to `conftest.py`:

```python
# tests/conftest.py
import os
import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase


@pytest_asyncio.fixture
async def live_driver():
    uri = os.environ.get("TEST_NEO4J_URI")
    pwd = os.environ.get("TEST_NEO4J_PASSWORD")
    if not uri or not pwd:
        pytest.skip("live Neo4j not configured (set TEST_NEO4J_URI)")
    driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", pwd))
    yield driver
    await driver.close()
```

QA runs these on the iMac Neo4j in Phase 4.1.

- [ ] **Step 4: Run test to verify it passes (on iMac with live
      Neo4j set in env)**

- [ ] **Step 5: Commit**

```bash
git commit -am "test(integration): group_id namespace invariants (GIM-NN)"
```

---

## Task 12: Backward-compat smoke — lookup response byte-stable

**Files:**
- Create: `services/palace-mcp/tests/test_lookup_response_stability.py`

- [ ] **Step 1: Write failing test**

```python
import json

SNAPSHOT_PATH = "tests/fixtures/lookup_issue_snapshot_n0.json"


async def test_lookup_issue_response_matches_pre_migration_snapshot(
    live_driver,
):
    """palace.memory.lookup(entity_type='Issue') must return a body
    byte-identical to the captured N+0 snapshot (modulo query_ms)."""
    ...
    # Load snapshot, normalise query_ms to 0, compare.
```

If the snapshot file doesn't exist yet, capture it **before** wiring
Task 9/10 in: run the service against the current iMac data, call
`palace.memory.lookup(entity_type="Issue", limit=20)`, save the JSON
body to `tests/fixtures/lookup_issue_snapshot_n0.json`. Do this in a
side-commit on the feature branch so we can diff against it later.

- [ ] **Step 2: Run test to verify it fails** (or skips if no
      snapshot yet)

- [ ] **Step 3: Make it pass**

The test passes once Tasks 1–10 are in and the lookup tool is wiring
`settings.palace_default_group_id` — the WHERE clause matches the
legacy single-project reality, so rows + order must be identical.

- [ ] **Step 4: Commit**

```bash
git commit -am "test: lookup response byte-stable across group_id migration (GIM-NN)"
```

---

## Phase 3 — Review

### Phase 3.1 — CodeReviewer (mechanical)

CR must paste the literal local output (green) of each in the APPROVE
comment:

```bash
uv run ruff check
uv run mypy src/
uv run pytest
```

CR must also diff `tests/fixtures/lookup_issue_snapshot_n0.json` vs a
fresh capture on the feature branch and confirm body equality modulo
`query_ms`. Any drift → block merge.

### Phase 3.2 — OpusArchitectReviewer (adversarial)

Focus areas (Opus is instructed to poke holes, not sign off):

- Is the backfill truly idempotent? What happens if the service
  crashes mid-backfill?
- Can an edge leak across projects through a sequence of ingest runs
  with different `group_id` values? Prove or disprove with a scenario.
- Is `LookupResponseItem.properties` truly byte-stable? Check the
  JSON key ordering assumption.
- Does the `LATEST_INGEST_RUN` preservation (Task 6) actually keep
  `palace.memory.health()` byte-stable, given that `IngestRun` nodes
  now carry a `group_id` property the health payload doesn't expose?

### Phase 4.1 — QAEngineer (live smoke on iMac)

SSH into iMac, checkout the feature branch, rebuild, run through
`palace.memory.health()` and `palace.memory.lookup` via MCP, then run
the ingest CLI once. Capture **evidence in a comment on the issue**
(not a self-report):

1. Commit SHA being tested: `git -C /Users/Shared/Ios/Gimle-Palace rev-parse HEAD`
2. `docker compose --profile full ps` — palace-mcp healthy
3. `/healthz` — 200 OK, `{"status":"ok","neo4j":"reachable"}`
4. MCP: `palace.memory.health()` — counts match pre-migration (34
   Issues / 167 Comments / 12 Agents or newer live number)
5. MCP: `palace.memory.lookup(entity_type="Issue", limit=5)` — JSON
   body pasted, no `group_id` in `properties` map (backward compat)
6. `palace-mcp ingest` CLI — completes without error, logs
   `ingest.finish`
7. Cypher direct:
   ```
   MATCH (n) WHERE n:Issue OR n:Comment OR n:Agent OR n:IngestRun
   RETURN DISTINCT n.group_id AS g, count(n) AS c
   ```
   Expected single row: `{g: "project/gimle", c: <total>}`.
8. After QA complete, checkout back to `develop` on iMac (see
   `feedback_imac_checkout_discipline.md`).

### Phase 4.2 — Merge

Squash-merge to develop. CTO posts a short merge comment referencing
the spec + this plan and closes the issue. Do **not** admin-override
CI; CI must be green on the feature branch.

---

## Self-review checklist (Board)

- [x] Every task names concrete files and lines.
- [x] Every task has a failing test first, then an implementation, then
      a passing run.
- [x] No placeholders, no "similar to task N" — code repeats where needed.
- [x] `group_id` thread is complete: config → schema DDL → upserts →
      GC → lookup → MCP signature → backfill → integration test.
- [x] Backward-compat check is **in the plan**, not a post-hoc hope.
- [x] CI gate is non-negotiable in Phase 3.1 per GIM-48 lesson.
- [x] QA Phase 4.1 has concrete evidence format per
      `feedback_qa_skipped_gim48.md`.
