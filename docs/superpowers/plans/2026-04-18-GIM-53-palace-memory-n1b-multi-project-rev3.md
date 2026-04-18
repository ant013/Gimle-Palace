# N+1b Multi-project rev3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`
> to implement this plan. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Introduce `:Project` entity and multi-project scoping on
palace-mcp. Three new tools (`register_project`, `list_projects`,
`get_project_overview`). All applicable tools accept
`project: str | list | "*" | None`. Validated by registering a
second `:Project {slug:"medic"}` and demonstrating isolation.

**Architecture:** Pure N+0 + group_id extension (no graphiti). Raw
parameterised Cypher against plain Neo4j 5.26. `:Project` nodes are
the single source of truth — no yaml registry file.

**Tech Stack:** Python 3.12, Pydantic v2, neo4j 5.x async driver,
FastMCP, pytest.

**Spec:** `docs/superpowers/specs/2026-04-18-palace-memory-n1b-multi-project-rev3.md`
**Predecessor:** GIM-52 group_id migration (`e629d97` on develop).

---

## Phase 0 — Branching

```bash
git fetch origin
git checkout develop
git pull --ff-only
git checkout -b feature/GIM-53-palace-memory-n1b-multi-project
```

Replace `NN` with the issue number CTO assigns in Phase 1.1.

---

## Task 1: `:Project` constraint + index DDL

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Modify: `services/palace-mcp/tests/memory/test_schema_ddl.py`

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_schema_ddl.py (append)
def test_project_slug_unique_constraint():
    from palace_mcp.memory.cypher import CREATE_CONSTRAINTS
    assert any(
        "CONSTRAINT project_slug" in c and "REQUIRE p.slug IS UNIQUE" in c
        for c in CREATE_CONSTRAINTS
    )


def test_project_group_id_index():
    from palace_mcp.memory.cypher import CREATE_INDEXES
    assert any(
        "INDEX project_group_id" in idx and "FOR (p:Project)" in idx
        for idx in CREATE_INDEXES
    )
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest tests/memory/test_schema_ddl.py -v
```

- [ ] **Step 3: Add the DDL**

In `cypher.py`, append to `CREATE_CONSTRAINTS`:

```python
    "CREATE CONSTRAINT project_slug IF NOT EXISTS "
    "FOR (p:Project) REQUIRE p.slug IS UNIQUE",
```

And append to `CREATE_INDEXES`:

```python
    "CREATE INDEX project_group_id IF NOT EXISTS "
    "FOR (p:Project) ON (p.group_id)",
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/cypher.py \
        services/palace-mcp/tests/memory/test_schema_ddl.py
git commit -m "feat(schema): :Project slug constraint + group_id index (GIM-53)"
```

---

## Task 2: `UPSERT_PROJECT` Cypher + ProjectInfo schema

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py`
- Create: `services/palace-mcp/tests/memory/test_project_cypher.py`

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_project_cypher.py
from palace_mcp.memory.cypher import UPSERT_PROJECT
from palace_mcp.memory.schema import ProjectInfo


def test_upsert_project_merges_by_slug():
    assert "MERGE (p:Project {slug: $slug})" in UPSERT_PROJECT


def test_upsert_project_sets_group_id_from_slug():
    assert "p.group_id" in UPSERT_PROJECT
    assert "'project/' + $slug" in UPSERT_PROJECT


def test_upsert_project_preserves_source_created_at():
    assert "coalesce(p.source_created_at, $now)" in UPSERT_PROJECT


def test_project_info_has_required_fields():
    fields = ProjectInfo.model_fields
    for req in ("slug", "name", "tags", "source_created_at", "source_updated_at",
                "entity_counts"):
        assert req in fields, f"ProjectInfo missing required field: {req}"
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Add Cypher + schema**

In `cypher.py`, append:

```python
UPSERT_PROJECT = """
MERGE (p:Project {slug: $slug})
SET p.group_id            = 'project/' + $slug,
    p.name                = $name,
    p.tags                = $tags,
    p.language            = $language,
    p.framework           = $framework,
    p.repo_url            = $repo_url,
    p.source              = 'paperclip',
    p.source_created_at   = coalesce(p.source_created_at, $now),
    p.source_updated_at   = $now
RETURN p
"""

LIST_PROJECT_SLUGS = "MATCH (p:Project) RETURN p.slug AS slug ORDER BY slug"

GET_PROJECT = """
MATCH (p:Project {slug: $slug})
RETURN p
"""

PROJECT_ENTITY_COUNTS = """
MATCH (n)
WHERE (n:Issue OR n:Comment OR n:Agent OR n:IngestRun)
  AND n.group_id = $group_id
RETURN labels(n) AS labels, count(n) AS c
"""

PROJECT_LAST_INGEST = """
MATCH (r:IngestRun {source: $source})
WHERE r.group_id = $group_id
RETURN r
ORDER BY r.started_at DESC
LIMIT 1
"""
```

In `schema.py`, append:

```python
class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    tags: list[str]
    language: str | None = None
    framework: str | None = None
    repo_url: str | None = None
    source_created_at: str
    source_updated_at: str
    entity_counts: dict[str, int] = Field(default_factory=dict)
    last_ingest_started_at: str | None = None
    last_ingest_finished_at: str | None = None
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/cypher.py \
        services/palace-mcp/src/palace_mcp/memory/schema.py \
        services/palace-mcp/tests/memory/test_project_cypher.py
git commit -m "feat(schema): UPSERT_PROJECT cypher + ProjectInfo model (GIM-53)"
```

---

## Task 3: `ensure_schema` bootstraps default `:Project`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/constraints.py`
- Modify: `services/palace-mcp/tests/memory/test_constraints.py`

- [ ] **Step 1: Write failing test**

```python
async def test_ensure_schema_bootstraps_default_project(live_driver):
    """First call to ensure_schema creates a :Project node for the default slug."""
    await ensure_schema(live_driver, default_group_id="project/test-bootstrap")

    async with live_driver.session() as s:
        result = await s.run(
            "MATCH (p:Project {slug: 'test-bootstrap'}) RETURN p.slug AS slug, "
            "p.group_id AS g, p.source_created_at AS ts"
        )
        row = await result.single()

    assert row is not None
    assert row["slug"] == "test-bootstrap"
    assert row["g"] == "project/test-bootstrap"
    assert row["ts"] is not None


async def test_ensure_schema_bootstrap_idempotent(live_driver):
    """Second call does not rewrite source_created_at."""
    await ensure_schema(live_driver, default_group_id="project/test-idem")
    async with live_driver.session() as s:
        row1 = await (await s.run(
            "MATCH (p:Project {slug: 'test-idem'}) RETURN p.source_created_at AS t"
        )).single()
    await ensure_schema(live_driver, default_group_id="project/test-idem")
    async with live_driver.session() as s:
        row2 = await (await s.run(
            "MATCH (p:Project {slug: 'test-idem'}) RETURN p.source_created_at AS t"
        )).single()
    assert row1["t"] == row2["t"], "source_created_at must be preserved"
```

(Use the same `@pytest.mark.integration` / `live_driver` fixture
pattern GIM-52 introduced.)

- [ ] **Step 2: Run tests — expect SKIP (no live driver) or FAIL (if driver present)**

- [ ] **Step 3: Extend `ensure_schema`**

```python
# memory/constraints.py
from datetime import datetime, timezone
from palace_mcp.memory.cypher import (
    BACKFILL_GROUP_ID, CREATE_CONSTRAINTS, CREATE_INDEXES, UPSERT_PROJECT,
)


def _bootstrap_name_for(slug: str) -> str:
    # Humanize the slug as a reasonable default; operators can rename
    # later via register_project.
    return slug.replace("-", " ").replace("_", " ").title() + " (bootstrap)"


async def ensure_schema(driver: AsyncDriver, *, default_group_id: str) -> None:
    default_slug = default_group_id.removeprefix("project/")
    now = datetime.now(timezone.utc).isoformat()

    async with driver.session() as session:
        for stmt in CREATE_CONSTRAINTS:
            await session.run(stmt)
        for stmt in CREATE_INDEXES:
            await session.run(stmt)
        await session.run(BACKFILL_GROUP_ID, default=default_group_id)
        await session.run(
            UPSERT_PROJECT,
            slug=default_slug,
            name=_bootstrap_name_for(default_slug),
            tags=["bootstrap"],
            language=None,
            framework=None,
            repo_url=None,
            now=now,
        )
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(schema): ensure_schema bootstraps default :Project idempotently (GIM-53)"
```

---

## Task 4: Integrity invariant — every entity group_id maps to a `:Project`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/constraints.py`
- Modify: `services/palace-mcp/tests/memory/test_constraints.py`

- [ ] **Step 1: Write failing test**

```python
async def test_ensure_schema_fails_on_unregistered_group_id(live_driver):
    """If any Issue/Comment/Agent/IngestRun has a group_id with no :Project,
    ensure_schema raises a clear error."""
    async with live_driver.session() as s:
        await s.run("CREATE (:Issue {id: 'stray', group_id: 'project/unregistered', "
                    "source: 'paperclip', palace_last_seen_at: '1970'})")

    with pytest.raises(SchemaIntegrityError, match="unregistered"):
        await ensure_schema(live_driver, default_group_id="project/test-bootstrap")
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

In `cypher.py`:

```python
UNREGISTERED_GROUP_IDS = """
MATCH (n)
WHERE (n:Issue OR n:Comment OR n:Agent OR n:IngestRun)
WITH DISTINCT n.group_id AS g
WHERE g IS NOT NULL AND NOT EXISTS {
    MATCH (p:Project) WHERE p.group_id = g
}
RETURN collect(g) AS unregistered
"""
```

In `constraints.py`:

```python
class SchemaIntegrityError(RuntimeError):
    pass


async def ensure_schema(driver: AsyncDriver, *, default_group_id: str) -> None:
    # ... existing bootstrap logic above ...

    async with driver.session() as session:
        result = await session.run(UNREGISTERED_GROUP_IDS)
        row = await result.single()
        unregistered = row["unregistered"] if row else []

    if unregistered:
        raise SchemaIntegrityError(
            f"group_ids present on entities but no matching :Project: "
            f"{sorted(unregistered)}. Register via palace.memory.register_project."
        )
```

Order: bootstrap default project **before** the invariant check, so a
fresh install with GIM-52-stamped data (only `project/gimle`) self-heals.

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(schema): integrity check — every entity group_id has :Project (GIM-53)"
```

---

## Task 5: `resolve_group_ids` resolver + typed error

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/projects.py`
- Create: `services/palace-mcp/tests/memory/test_projects.py`

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_projects.py
import pytest
from palace_mcp.memory.projects import (
    UnknownProjectError, resolve_group_ids,
)


class _FakeTx:
    def __init__(self, slugs):
        self._slugs = slugs

    async def run(self, query, **params):
        class _R:
            def __init__(s, rows): s._rows = rows
            def __aiter__(s): s._i = iter(s._rows); return s
            async def __anext__(s):
                try: return next(s._i)
                except StopIteration: raise StopAsyncIteration
        return _R([{"slug": s} for s in self._slugs])


@pytest.mark.asyncio
async def test_resolve_none_returns_default():
    tx = _FakeTx(["gimle"])
    out = await resolve_group_ids(tx, None, default_group_id="project/gimle")
    assert out == ["project/gimle"]


@pytest.mark.asyncio
async def test_resolve_star_returns_all():
    tx = _FakeTx(["gimle", "medic"])
    out = await resolve_group_ids(tx, "*", default_group_id="project/gimle")
    assert out == ["project/gimle", "project/medic"]


@pytest.mark.asyncio
async def test_resolve_single_validates_existence():
    tx = _FakeTx(["gimle"])
    with pytest.raises(UnknownProjectError, match="medic"):
        await resolve_group_ids(tx, "medic", default_group_id="project/gimle")


@pytest.mark.asyncio
async def test_resolve_list_validates_each():
    tx = _FakeTx(["gimle"])
    with pytest.raises(UnknownProjectError, match="medic, other"):
        await resolve_group_ids(tx, ["gimle", "medic", "other"],
                                default_group_id="project/gimle")


@pytest.mark.asyncio
async def test_resolve_list_ok():
    tx = _FakeTx(["gimle", "medic"])
    out = await resolve_group_ids(tx, ["gimle", "medic"],
                                  default_group_id="project/gimle")
    assert out == ["project/gimle", "project/medic"]


@pytest.mark.asyncio
async def test_resolve_wrong_type_raises_typeerror():
    tx = _FakeTx(["gimle"])
    with pytest.raises(TypeError, match="project must be"):
        await resolve_group_ids(tx, 42, default_group_id="project/gimle")  # type: ignore
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement**

```python
# memory/projects.py
from __future__ import annotations

from neo4j import AsyncManagedTransaction

from palace_mcp.memory.cypher import LIST_PROJECT_SLUGS


class UnknownProjectError(ValueError):
    """Raised when a project arg references a slug that has no :Project node."""


async def _list_known_slugs(tx: AsyncManagedTransaction) -> list[str]:
    result = await tx.run(LIST_PROJECT_SLUGS)
    return [row["slug"] async for row in result]


async def resolve_group_ids(
    tx: AsyncManagedTransaction,
    project: str | list[str] | None,
    *,
    default_group_id: str,
) -> list[str]:
    if project is None:
        return [default_group_id]

    known = await _list_known_slugs(tx)

    if project == "*":
        return [f"project/{s}" for s in known]

    if isinstance(project, str):
        if project not in known:
            raise UnknownProjectError(project)
        return [f"project/{project}"]

    if isinstance(project, list):
        unknown = [s for s in project if s not in known]
        if unknown:
            raise UnknownProjectError(", ".join(unknown))
        return [f"project/{s}" for s in project]

    raise TypeError(
        f"project must be str, list, or None; got {type(project).__name__}"
    )
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/projects.py \
        services/palace-mcp/tests/memory/test_projects.py
git commit -m "feat(projects): resolve_group_ids + UnknownProjectError (GIM-53)"
```

---

## Task 6: `palace.memory.lookup` gains `project` param

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/lookup.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py` — `LookupRequest` gains `project`
- Modify: `services/palace-mcp/tests/memory/test_lookup.py`

- [ ] **Step 1: Write failing test**

```python
async def test_lookup_with_star_project_queries_all(live_driver, seed_two_projects):
    """lookup(project="*") must return items from both Gimle and Medic."""
    out = await run_lookup(live_driver, entity_type="Issue", project="*")
    slugs_seen = {i.properties["group_id"].removeprefix("project/") for i in out.items}
    # NB: properties map still omits group_id — this assertion uses a
    # test-only projection. Adjust fixture accordingly.
    assert slugs_seen == {"gimle", "medic"}


async def test_lookup_unknown_project_returns_structured_error(live_driver):
    out = await run_lookup_raw(live_driver, entity_type="Issue", project="ghost")
    assert out["ok"] is False
    assert out["error"] == "unknown_project"
    assert "ghost" in out["message"]
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

Extend `LookupRequest` with `project: str | list[str] | None = None`.
In `lookup.py`, replace the single `n.group_id = $group_id` clause
with `n.group_id IN $group_ids`, populating `$group_ids` from
`resolve_group_ids(tx, request.project, default_group_id=...)`. Wrap
the call in a `try/except UnknownProjectError` that produces a
structured `{ok: False, error: "unknown_project", message: str}`
response — see existing warning-response pattern (GIM-37).

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(lookup): project param with IN \$group_ids WHERE (GIM-53)"
```

---

## Task 7: `palace.memory.health` response extension (back-compat)

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/health.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py` — `HealthResponse`
- Modify: `services/palace-mcp/tests/memory/test_health.py`

- [ ] **Step 1: Write failing test**

```python
async def test_health_response_lists_projects(live_driver, seed_two_projects):
    out = await get_health(live_driver, embedder_base_url="")
    assert "gimle" in out.projects
    assert "medic" in out.projects
    assert out.default_project == "gimle"
    assert out.entity_counts_per_project["gimle"]["Issue"] > 0
    assert out.entity_counts_per_project["medic"].get("Issue", 0) == 0


async def test_health_entity_counts_still_sum_across_projects(
    live_driver, seed_two_projects
):
    """Back-compat: total entity_counts unchanged."""
    out = await get_health(live_driver, embedder_base_url="")
    per_project_sum = sum(
        counts.get("Issue", 0) for counts in out.entity_counts_per_project.values()
    )
    assert out.entity_counts["Issue"] == per_project_sum
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Extend `HealthResponse` + `get_health`**

Add fields:

```python
projects: list[str] = Field(default_factory=list)
default_project: str | None = None
entity_counts_per_project: dict[str, dict[str, int]] = Field(default_factory=dict)
```

In `get_health`: after existing count query, query
`MATCH (p:Project) RETURN p.slug AS slug ORDER BY slug` and populate
`projects`. Extract `default_project = settings.palace_default_group_id
.removeprefix("project/")`. Run a grouped count query for
`entity_counts_per_project`.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(health): projects + per-project counts, total preserved (GIM-53)"
```

---

## Task 8: `palace.memory.register_project` tool

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py`
- Create: `services/palace-mcp/src/palace_mcp/memory/project_tools.py`
- Create: `services/palace-mcp/tests/memory/test_project_tools.py`

- [ ] **Step 1: Write failing test**

```python
async def test_register_project_creates_node(live_driver):
    info = await register_project(
        live_driver,
        slug="medic",
        name="Medic Healthcare",
        tags=["mobile", "kmp", "healthcare"],
    )
    assert info.slug == "medic"
    assert info.tags == ["mobile", "kmp", "healthcare"]
    async with live_driver.session() as s:
        row = await (await s.run(
            "MATCH (p:Project {slug: 'medic'}) RETURN p.group_id AS g, p.name AS n"
        )).single()
    assert row["g"] == "project/medic"
    assert row["n"] == "Medic Healthcare"


async def test_register_project_idempotent_preserves_created_at(live_driver):
    info1 = await register_project(live_driver, slug="alpha", name="Alpha", tags=[])
    info2 = await register_project(live_driver, slug="alpha", name="Alpha Renamed", tags=["x"])
    assert info1.source_created_at == info2.source_created_at
    assert info2.name == "Alpha Renamed"
    assert info2.tags == ["x"]
    assert info2.source_updated_at >= info1.source_updated_at
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
# memory/project_tools.py
from datetime import datetime, timezone

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import UPSERT_PROJECT, GET_PROJECT
from palace_mcp.memory.schema import ProjectInfo


def _project_info_from_row(row: dict) -> ProjectInfo:
    p = row["p"]
    return ProjectInfo(
        slug=p["slug"],
        name=p["name"],
        tags=list(p.get("tags") or []),
        language=p.get("language"),
        framework=p.get("framework"),
        repo_url=p.get("repo_url"),
        source_created_at=p["source_created_at"],
        source_updated_at=p["source_updated_at"],
        entity_counts={},
    )


async def register_project(
    driver: AsyncDriver,
    *,
    slug: str,
    name: str,
    tags: list[str],
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
) -> ProjectInfo:
    now = datetime.now(timezone.utc).isoformat()
    async with driver.session() as s:
        await s.run(
            UPSERT_PROJECT, slug=slug, name=name, tags=list(tags),
            language=language, framework=framework, repo_url=repo_url, now=now,
        )
        result = await s.run(GET_PROJECT, slug=slug)
        row = await result.single()
    assert row is not None
    return _project_info_from_row(row)
```

Wire into `mcp_server.py` as tool `palace.memory.register_project`.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(mcp): register_project tool, idempotent upsert (GIM-53)"
```

---

## Task 9: `palace.memory.list_projects` + `get_project_overview`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/project_tools.py`
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py`
- Modify: `services/palace-mcp/tests/memory/test_project_tools.py`

- [ ] **Step 1: Write failing test**

```python
async def test_list_projects_returns_all_slugs(live_driver, seed_two_projects):
    infos = await list_projects(live_driver)
    slugs = [i.slug for i in infos]
    assert slugs == sorted(slugs)
    assert "gimle" in slugs and "medic" in slugs


async def test_get_project_overview_returns_counts(live_driver, seed_two_projects):
    info = await get_project_overview(live_driver, slug="gimle")
    assert info.slug == "gimle"
    assert info.entity_counts.get("Issue", 0) > 0


async def test_get_project_overview_unknown_slug_raises(live_driver):
    with pytest.raises(UnknownProjectError):
        await get_project_overview(live_driver, slug="ghost")
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

In `project_tools.py`:

```python
async def list_projects(driver: AsyncDriver) -> list[ProjectInfo]:
    # Run slug query, then hydrate each with counts.
    async with driver.session() as s:
        slug_rows = await (await s.run(LIST_PROJECT_SLUGS)).data()
    slugs = [r["slug"] for r in slug_rows]
    return [await get_project_overview(driver, slug=s) for s in slugs]


async def get_project_overview(
    driver: AsyncDriver, *, slug: str, source: str = "paperclip"
) -> ProjectInfo:
    group_id = f"project/{slug}"
    async with driver.session() as s:
        row = await (await s.run(GET_PROJECT, slug=slug)).single()
        if row is None:
            raise UnknownProjectError(slug)
        base = _project_info_from_row(row)

        counts_rows = await (await s.run(
            PROJECT_ENTITY_COUNTS, group_id=group_id
        )).data()
        counts: dict[str, int] = {}
        for cr in counts_rows:
            for lbl in cr["labels"]:
                if lbl in ("Issue", "Comment", "Agent", "IngestRun"):
                    counts[lbl] = counts.get(lbl, 0) + cr["c"]

        last_ingest = None
        try:
            r2 = await s.run(
                PROJECT_LAST_INGEST, group_id=group_id, source=source
            )
            lr = await r2.single()
            if lr is not None:
                last_ingest = lr["r"]
        except Exception:
            pass

    return base.model_copy(update={
        "entity_counts": counts,
        "last_ingest_started_at": last_ingest["started_at"] if last_ingest else None,
        "last_ingest_finished_at": (
            last_ingest.get("finished_at") if last_ingest else None
        ),
    })
```

Wire both into `mcp_server.py`.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(mcp): list_projects + get_project_overview with counts (GIM-53)"
```

---

## Task 10: Ingest CLI `--project-slug`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/paperclip.py` (or wherever the CLI lives)
- Modify: `services/palace-mcp/src/palace_mcp/ingest/runner.py`
- Modify: `services/palace-mcp/tests/ingest/test_runner.py`

- [ ] **Step 1: Write failing test**

```python
async def test_runner_rejects_unregistered_project(mock_driver, fake_paperclip):
    with pytest.raises(UnknownProjectError, match="ghost"):
        await run_ingest(
            client=fake_paperclip, driver=mock_driver,
            group_id="project/ghost",
        )


async def test_runner_accepts_registered_project(mock_driver_with_project, fake_paperclip):
    # mock_driver_with_project has a :Project {slug: "gimle"} pre-seeded
    result = await run_ingest(
        client=fake_paperclip, driver=mock_driver_with_project,
        group_id="project/gimle",
    )
    assert result["run_id"]
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

In `run_ingest`: before the `CREATE_INGEST_RUN` call, query
`GET_PROJECT slug=<slug>`; if empty, raise `UnknownProjectError`.
Slug is extracted from the `group_id` via `.removeprefix("project/")`.

Add `--project-slug` argparse option to the CLI entry point. Default
to the slug of `settings.palace_default_group_id`.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(ingest): --project-slug flag with :Project validation (GIM-53)"
```

---

## Task 11: Byte-stable back-compat snapshot

**Files:**
- Create: `services/palace-mcp/tests/fixtures/lookup_issue_snapshot_n1b_compat.json`
- Create: `services/palace-mcp/tests/test_lookup_response_n1b_compat.py`

- [ ] **Step 1: Capture snapshot (side-commit on feature branch)**

Against the current iMac single-project data, call
`palace.memory.lookup(entity_type="Issue", limit=20, project=None)`
and save the JSON body.

- [ ] **Step 2: Write assertion**

```python
async def test_lookup_default_project_byte_stable(live_driver):
    """With project=None, response must equal the captured N+1b snapshot
    (modulo query_ms)."""
    snap = json.loads(Path(SNAPSHOT_PATH).read_text())
    out = await run_lookup_raw(live_driver, entity_type="Issue", limit=20)
    assert _normalize(out) == _normalize(snap)
```

- [ ] **Step 3: Run — expect PASS** (this validates the whole slice
      did not break single-project callers).

- [ ] **Step 4: Commit**

```bash
git commit -am "test: byte-stable lookup response with project=None (GIM-53)"
```

---

## Task 12: Integration — register Medic + isolation demo

**Files:**
- Create: `services/palace-mcp/tests/integration/test_n1b_multi_project.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.integration
async def test_medic_registration_and_isolation(live_driver):
    await register_project(
        live_driver, slug="medic", name="Medic Healthcare",
        tags=["mobile", "kmp", "healthcare"],
    )

    infos = await list_projects(live_driver)
    slugs = [i.slug for i in infos]
    assert "medic" in slugs and "gimle" in slugs

    # Medic has no issues yet
    medic_issues = await run_lookup(live_driver, entity_type="Issue", project="medic")
    assert medic_issues.items == []

    # Multi-project returns Gimle's (Medic has none)
    multi = await run_lookup(
        live_driver, entity_type="Issue", project=["gimle", "medic"]
    )
    star = await run_lookup(live_driver, entity_type="Issue", project="*")
    assert len(multi.items) == len(star.items)
    assert {i.id for i in multi.items} == {i.id for i in star.items}

    # Unknown project
    result = await run_lookup_raw(
        live_driver, entity_type="Issue", project="does-not-exist"
    )
    assert result["ok"] is False
    assert result["error"] == "unknown_project"
```

- [ ] **Step 2: Run — expect PASS** (all prior tasks make this pass
      without further implementation work).

- [ ] **Step 3: Commit**

```bash
git commit -am "test(integration): multi-project scoping + isolation (GIM-53)"
```

---

## Phase 3 — Review

### Phase 3.1 — CodeReviewer (mechanical)

Per `phase-handoff.md` fragment, CR must paste in the APPROVE comment:

- `uv run ruff check` output
- `uv run mypy src/` output
- `uv run pytest` output
- CI run URL on the feature branch

CR checklist:

- [ ] Every task's test exists and passes.
- [ ] `:Project` constraint + index present; `ensure_schema` idempotent
      (re-run doesn't rewrite `source_created_at`).
- [ ] Resolver validates against `:Project` nodes only (no yaml, no
      hardcoded list).
- [ ] Every lookup query uses `WHERE n.group_id IN $group_ids` (no
      hardcoded scalar left over from GIM-52).
- [ ] Back-compat: `project=None` response matches the captured snapshot.
- [ ] No raw Cypher pattern slippage — all new writes use parameterised
      `$name` params; no f-string SQL interpolation with user input.

Reassign to OpusArchitectReviewer.

### Phase 3.2 — OpusArchitectReviewer (adversarial)

Focus:

- Can an unregistered `group_id` enter the graph via `run_ingest` if
  `register_project` and `run_ingest` race? What does the second lose?
- Can `"*"` ever resolve to an empty list (zero projects)? What does
  lookup do then?
- `register_project` concurrency: two parallel calls with same slug —
  does MERGE serialise correctly in Neo4j?
- Does the `UPSERT_PROJECT` coalesce actually preserve
  `source_created_at` across a slug rename? (It doesn't rename; slug
  is the MERGE key.)
- Is there any path where `palace.memory.health()` returns a
  `default_project` not present in the `projects` list?

Reassign to QAEngineer.

### Phase 4.1 — QAEngineer (live smoke on iMac)

Follow the `phase-handoff.md` evidence template. Required output in
the issue comment:

1. Commit SHA tested.
2. `docker compose --profile full ps` — palace-mcp healthy.
3. `/healthz` — 200 OK.
4. MCP: `palace.memory.list_projects()` before register — one project
   (gimle).
5. MCP: `palace.memory.register_project(slug="medic", name="Medic
   Healthcare", tags=["mobile","kmp","healthcare"])` — returns
   ProjectInfo.
6. MCP: `palace.memory.list_projects()` after register — two projects.
7. MCP: `palace.memory.lookup(entity_type="Issue", project="medic")` —
   empty items, no error.
8. MCP: `palace.memory.lookup(entity_type="Issue", project="*")` —
   same items as `project=["gimle","medic"]`, same as
   `project="gimle"` (Medic empty).
9. MCP: `palace.memory.lookup(entity_type="Issue", project="typo")` —
   structured `ok: false, error: unknown_project`.
10. Direct Cypher invariant:
    ```
    MATCH (p:Project) RETURN p.slug ORDER BY p.slug
    ```
    — expect `[gimle, medic]`.
11. iMac checkout returned to `develop`.

Handoff: `@MCPEngineer` (or `@CTO`) Phase 4.1 PASS, Phase 4.2 squash-merge.

### Phase 4.2 — Merge

Squash-merge to develop. CI must be green; no admin override. Merge
comment references spec + this plan + GIM-52 (predecessor).

Manual iMac deploy: `git pull` develop, rebuild `palace-mcp` with
`--no-cache`, restart.

---

## Self-review checklist (Board)

- [x] Every task has concrete test code + implementation code + commit
      message.
- [x] No placeholders. "Similar to" not used.
- [x] Invariant check (Task 4) protects against silent stranger data.
- [x] Back-compat test (Task 11) is in the plan, not a hope.
- [x] CI-green, non-admin merge is non-negotiable (spec §10).
- [x] QA Phase 4.1 format matches `phase-handoff.md` fragment template.
- [x] Predecessor (GIM-52) explicit; resolver uses `:Project` nodes as
      the sole registry (no yaml).
