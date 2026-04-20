# Extractor framework substrate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-20-extractor-framework-substrate-design.md` on `feature/GIM-59-extractor-framework-substrate` @ `4294708` (rev2 + submodule fix `2ca129c`).

**Goal:** Ship the extractor framework substrate in palace-mcp — package layout, BaseExtractor contract, registry, lifecycle runner with `:IngestRun` tracking, schema aggregator, 2 MCP tools, HeartbeatExtractor as live smoke target. Zero real extractors, zero external tool dependencies, zero new containers.

**Architecture:** New package `palace_mcp/extractors/` (8 files) inside existing palace-mcp Python service. MCP tools register on existing `FastMCP("palace-memory")` app on `:8080`. Schema aggregates from registered extractors at startup. Runner orchestrates via `_precheck / _execute / _finalize` helpers. Tests use mock driver for units, `testcontainers-neo4j` (or existing compose Neo4j via `COMPOSE_NEO4J_URI`) for integration.

**Tech Stack:** Python 3.12, Pydantic v2, FastMCP (`mcp[cli]`), Neo4j async driver, `testcontainers-neo4j` (dev-only), pytest.

**Predecessors pinned:**
- `develop@41d23d2` — GIM-57 meta-workflow migration; single mainline; branch protection active.
- `feature/GIM-59-extractor-framework-substrate@4294708` — spec rev2.
- Submodule `paperclips/fragments/shared@7b9a6ee` — GIM-57 fragments deployed to 11 agents.

**Language rule:** code / tests / commits / docstrings in English; Russian only in UI (per `language.md` fragment).

**Agents used:** CTO (`7fb0fdbb-...`), CodeReviewer (`bd2d7e20-...`), PythonEngineer (`127068ee-...`), TechnicalWriter (`0e8222fd-...`), OpusArchitectReviewer (`8d6649e2-...`), QAEngineer (`58b68640-...`).

---

## File structure

### New files

```
services/palace-mcp/src/palace_mcp/extractors/
├── __init__.py         # empty — consumers import from explicit submodules
├── base.py             # BaseExtractor ABC + ExtractionContext + ExtractorStats + errors
├── registry.py         # EXTRACTORS dict + register/get/list_all
├── schemas.py          # Pydantic response models (ExtractorRunResponse etc.)
├── cypher.py           # CREATE_INGEST_RUN + FINALIZE_INGEST_RUN Cypher
├── runner.py           # _precheck / _execute / _finalize + run_extractor orchestrator
├── schema.py           # ensure_extractors_schema aggregator
└── heartbeat.py        # HeartbeatExtractor (shipped)

services/palace-mcp/tests/extractors/
├── __init__.py
├── unit/
│   ├── __init__.py
│   ├── test_base.py
│   ├── test_registry.py
│   ├── test_schemas_response.py
│   ├── test_runner.py
│   └── test_heartbeat.py
└── integration/
    ├── __init__.py
    ├── conftest.py                      # neo4j_uri fixture with COMPOSE_NEO4J_URI fallback
    ├── test_ensure_extractors_schema.py
    ├── test_heartbeat_integration.py
    ├── test_runner_error_paths_integration.py
    ├── test_mcp_tool_integration.py
    └── test_ingest_run_back_compat.py   # Task 2.10a consumer regression

docs/runbooks/2026-04-20-GIM-59-extractor-framework-rollback.md
```

### Modified files

```
services/palace-mcp/src/palace_mcp/main.py                # + ensure_extractors_schema call
services/palace-mcp/src/palace_mcp/mcp_server.py          # + 2 MCP tools
services/palace-mcp/pyproject.toml                        # + testcontainers-neo4j dev-dep
CLAUDE.md                                                  # + ## Extractors section
```

### File responsibilities

- `base.py` — pure contract (ABC + dataclasses + exceptions). Zero deps on palace-mcp internals, zero Neo4j direct.
- `registry.py` — mutable module-level dict; only `HeartbeatExtractor` registered in production.
- `schemas.py` — Pydantic models used internally by runner; `.model_dump()` out to MCP tool return.
- `cypher.py` — extractor-scoped Cypher statements; separate from `memory/cypher.py` to keep concerns isolated.
- `runner.py` — single fork point for extractor lifecycle; 4 coroutines (`_precheck`, `_execute`, `_finalize`, `run_extractor`).
- `schema.py` — aggregator; called at startup and optionally before extract() as defence.
- `heartbeat.py` — shipped production extractor; diagnostic probe; template for future extractor authors.

---

## Phase 1 — Formalization

### Task 1.1: CTO formalize

**Owner:** CTO (per narrowed `cto-no-code-ban.md` — may `Edit` / `git commit` on `docs/superpowers/**` files).

**Files:**
- Modify: `docs/superpowers/plans/2026-04-20-GIM-59-extractor-framework-substrate.md` (this file)

- [ ] **Step 1: Fresh-fetch on wake** (per `git-workflow.md` fragment)

```bash
git fetch origin --prune
git switch feature/GIM-59-extractor-framework-substrate
git pull --ff-only
git log --oneline -4
# Expected: 2ca129c (submodule fix), 4294708 (spec rev2), 3b70db0 (spec rev1), 41d23d2 (develop tip)
```

- [ ] **Step 2: Verify spec path + issue number**

```bash
test -f docs/superpowers/specs/2026-04-20-extractor-framework-substrate-design.md && echo "spec OK"
test -f docs/superpowers/plans/2026-04-20-GIM-59-extractor-framework-substrate.md && echo "plan OK"
rg -l 'GIM-NN' docs/superpowers/plans/2026-04-20-GIM-59-extractor-framework-substrate.md || echo "no GIM-NN placeholders"
# Expected: 3 OKs + no GIM-NN
```

- [ ] **Step 3: Hand off to CR**

Post paperclip comment:
```
## Phase 1.1 — Formalization complete

Spec + plan paths verified on feature/GIM-59-extractor-framework-substrate.
Draft PR: https://github.com/ant013/Gimle-Palace/pull/28
Latest commit: <HEAD sha>

@CodeReviewer your turn — Phase 1.2 plan-first review.
```

Reassign to CR via API:
```bash
set -a; source .env; set +a
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"bd2d7e20-7ed8-474c-91fc-353d610f4c52"}' \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

### Task 1.2: CR plan-first review

**Owner:** CodeReviewer

- [ ] **Step 1: Fetch + checkout + read spec + plan**

```bash
git fetch origin --prune
git switch feature/GIM-59-extractor-framework-substrate
git pull --ff-only
```

- [ ] **Step 2: Compliance walk — every §9 acceptance → plan task**

Walk spec §9 (16 items). For each, find the Phase 2 or Phase 4 task that implements it. List gaps.

- [ ] **Step 3: Concreteness check**

No `TBD` / `TODO` / "similar to Task X" / placeholder types. Every task has file paths, code blocks, exact commands with expected output.

- [ ] **Step 4: Runner lifecycle ordering check**

Task 2.6 (runner.py) implements `_precheck` → `_execute` → `_finalize` / `run_extractor`. Task 2.5 (`cypher.py`) must precede 2.6 — runner imports CREATE/FINALIZE statements. Task 2.7 (schema.py) must precede 2.9 (wiring into main.py lifespan). Verify ordering.

- [ ] **Step 5: Post paperclip APPROVE comment**

Full compliance checklist per `feedback_anti_rubber_stamp.md`. Example structure:
```
## Phase 1.2 plan-first review — APPROVE

### Spec §9 → plan tasks

| # | §9 acceptance | Task |
|---|---|---|
| 1 | Package with 8 files | 2.1 |
| 2 | BaseExtractor ABC + context + stats + errors | 2.2 |
... (15 more rows)

All 16 acceptance items mapped.

### Concreteness
- [x] All tasks have file paths
- [x] All code steps include code blocks
- [x] No TBD / TODO / unresolved refs
- [x] Ordering correct: cypher.py (2.5) before runner.py (2.6); schema.py (2.7) before main.py wiring (2.9)

APPROVE.

@PythonEngineer your turn — Phase 2 implementation.
```

- [ ] **Step 6: `gh pr review --approve` bridge** (per §3.9 of GIM-57 meta-migration)

```bash
PR_NUM=28
gh pr review $PR_NUM --approve --body "Plan-first APPROVE — see paperclip comment <ID>. Ready for Phase 2 implementation."
```

- [ ] **Step 7: Reassign to PythonEngineer**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"127068ee-b564-4b37-9370-616c81c63f35"}' \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

---

## Phase 2 — Implementation

All Phase 2 work on `feature/GIM-59-extractor-framework-substrate`. Fresh-fetch at every phase start.

### Task 2.1: Package scaffold

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/__init__.py`
- Create: `services/palace-mcp/tests/extractors/__init__.py`
- Create: `services/palace-mcp/tests/extractors/unit/__init__.py`
- Create: `services/palace-mcp/tests/extractors/integration/__init__.py`

- [ ] **Step 1: Create empty package dirs**

```bash
cd services/palace-mcp
mkdir -p src/palace_mcp/extractors tests/extractors/unit tests/extractors/integration
touch src/palace_mcp/extractors/__init__.py \
      tests/extractors/__init__.py \
      tests/extractors/unit/__init__.py \
      tests/extractors/integration/__init__.py
```

- [ ] **Step 2: Verify imports work**

```bash
cd services/palace-mcp
uv run python -c "import palace_mcp.extractors; print('pkg OK')"
# Expected: pkg OK
```

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/ \
        services/palace-mcp/tests/extractors/
git commit -m "feat(extractors): package scaffold (GIM-59)"
```

### Task 2.2: BaseExtractor contract (`base.py`)

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/base.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_base.py`

- [ ] **Step 1: Write failing tests**

File: `services/palace-mcp/tests/extractors/unit/test_base.py`

```python
"""Unit tests for BaseExtractor ABC + ExtractionContext + ExtractorStats + errors.

Per spec §3.2 — validates the contract independently of Neo4j.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorConfigError,
    ExtractorError,
    ExtractorRuntimeError,
    ExtractorStats,
)


def test_base_extractor_abstract_cannot_instantiate() -> None:
    """BaseExtractor is ABC — cannot instantiate directly."""
    with pytest.raises(TypeError):
        BaseExtractor()  # type: ignore[abstract]


def test_subclass_without_name_and_extract_fails() -> None:
    """Subclass missing abstract members cannot be instantiated."""
    class Incomplete(BaseExtractor):
        pass
    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_valid_subclass_instantiates() -> None:
    """Subclass with name + extract instantiates."""
    class MyExtractor(BaseExtractor):
        name = "my_ext"
        description = "test"

        async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
            return ExtractorStats()

    e = MyExtractor()
    assert e.name == "my_ext"
    assert e.description == "test"
    assert e.constraints == []  # class defaults
    assert e.indexes == []


def test_extraction_context_frozen() -> None:
    """ExtractionContext is immutable (frozen dataclass)."""
    ctx = ExtractionContext(
        driver=AsyncMock(),
        project_slug="test",
        group_id="project/test",
        repo_path=Path("/repos/test"),
        run_id="abc-123",
        logger=logging.getLogger("test"),
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        ctx.project_slug = "other"  # type: ignore[misc]


def test_extractor_stats_defaults() -> None:
    stats = ExtractorStats()
    assert stats.nodes_written == 0
    assert stats.edges_written == 0


def test_extractor_stats_custom() -> None:
    stats = ExtractorStats(nodes_written=42, edges_written=10)
    assert stats.nodes_written == 42


def test_extractor_error_hierarchy() -> None:
    """ExtractorConfigError and ExtractorRuntimeError inherit from ExtractorError."""
    assert issubclass(ExtractorConfigError, ExtractorError)
    assert issubclass(ExtractorRuntimeError, ExtractorError)


def test_extractor_error_codes() -> None:
    """error_code class attribute present for MCP response mapping."""
    assert ExtractorError.error_code == "extractor_error"
    assert ExtractorConfigError.error_code == "extractor_config_error"
    assert ExtractorRuntimeError.error_code == "extractor_runtime_error"
```

- [ ] **Step 2: Run tests — fail**

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_base.py -v
# Expected: ImportError (module doesn't exist yet)
```

- [ ] **Step 3: Implement `base.py`**

File: `services/palace-mcp/src/palace_mcp/extractors/base.py`

```python
"""Extractor protocol — BaseExtractor ABC + ExtractionContext + errors.

Contract for all palace-mcp extractors (spec §3.2). Extractors implement
extract() and declare their Cypher constraints + indexes as class attributes.
Framework (runner.py) handles :IngestRun lifecycle; extractor only writes
its domain nodes/edges via ctx.driver.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from neo4j import AsyncDriver


class BaseExtractor(ABC):
    """Contract for an extractor. Subclass + implement extract()."""

    # Required class attributes
    name: ClassVar[str]
    description: ClassVar[str]

    # Schema declaration — aggregated by ensure_extractors_schema
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []

    @abstractmethod
    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        """Run the extractor. Write nodes/edges via ctx.driver.

        Returns ExtractorStats with counts (for :IngestRun finalize).
        Raise ExtractorError subclass or any Exception on failure —
        runner catches + finalizes :IngestRun as errored.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class ExtractionContext:
    """Per-run context passed by runner into extractor.extract()."""

    driver: AsyncDriver
    project_slug: str
    group_id: str
    repo_path: Path
    run_id: str
    logger: logging.Logger


@dataclass(frozen=True)
class ExtractorStats:
    """What extract() returns. Merged into :IngestRun for observability."""

    nodes_written: int = 0
    edges_written: int = 0


class ExtractorError(Exception):
    """Base class for extractor-originating errors the runner should surface."""

    error_code: ClassVar[str] = "extractor_error"


class ExtractorConfigError(ExtractorError):
    """Extractor misconfigured (missing tool, bad params). Non-retryable."""

    error_code: ClassVar[str] = "extractor_config_error"


class ExtractorRuntimeError(ExtractorError):
    """Extractor ran but data was invalid / partial. Retryable."""

    error_code: ClassVar[str] = "extractor_runtime_error"
```

- [ ] **Step 4: Run tests — pass**

```bash
uv run pytest tests/extractors/unit/test_base.py -v
# Expected: 8 passed
```

- [ ] **Step 5: mypy strict check**

```bash
uv run mypy --strict src/palace_mcp/extractors/base.py
# Expected: Success: no issues found in 1 source file
```

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/base.py \
        services/palace-mcp/tests/extractors/unit/test_base.py
git commit -m "feat(extractors): BaseExtractor ABC + context + errors (GIM-59)"
```

### Task 2.3: Pydantic response schemas (`schemas.py`)

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/schemas.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_schemas_response.py`

- [ ] **Step 1: Write failing tests**

File: `services/palace-mcp/tests/extractors/unit/test_schemas_response.py`

```python
"""Unit tests for extractor Pydantic response models (spec §4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.schemas import (
    ExtractorDescriptor,
    ExtractorErrorResponse,
    ExtractorListResponse,
    ExtractorRunResponse,
)


def test_run_response_success() -> None:
    r = ExtractorRunResponse(
        run_id="abc-123",
        extractor="heartbeat",
        project="gimle",
        started_at="2026-04-20T10:00:00+00:00",
        finished_at="2026-04-20T10:00:01+00:00",
        duration_ms=1000,
        nodes_written=1,
        edges_written=0,
        success=True,
    )
    assert r.ok is True


def test_run_response_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ExtractorRunResponse(
            run_id="abc",
            extractor="heartbeat",
            project="gimle",
            started_at="2026-04-20T10:00:00+00:00",
            finished_at="2026-04-20T10:00:01+00:00",
            duration_ms=1,
            nodes_written=0,
            edges_written=0,
            success=True,
            unknown_field="x",  # type: ignore[call-arg]
        )


def test_error_response_minimal() -> None:
    r = ExtractorErrorResponse(
        error_code="invalid_slug",
        message="invalid slug: '../etc'",
    )
    assert r.ok is False
    assert r.extractor is None
    assert r.project is None
    assert r.run_id is None


def test_error_response_full() -> None:
    r = ExtractorErrorResponse(
        error_code="extractor_runtime_error",
        message="timeout",
        extractor="heartbeat",
        project="gimle",
        run_id="abc-123",
    )
    assert r.ok is False
    assert r.extractor == "heartbeat"


def test_error_response_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ExtractorErrorResponse(
            error_code="x",
            message="y",
            bogus="z",  # type: ignore[call-arg]
        )


def test_descriptor_and_list() -> None:
    d = ExtractorDescriptor(name="heartbeat", description="diagnostic probe")
    lst = ExtractorListResponse(extractors=[d])
    assert lst.ok is True
    assert lst.extractors[0].name == "heartbeat"
```

- [ ] **Step 2: Run tests — fail**

```bash
uv run pytest tests/extractors/unit/test_schemas_response.py -v
# Expected: ImportError
```

- [ ] **Step 3: Implement `schemas.py`**

File: `services/palace-mcp/src/palace_mcp/extractors/schemas.py`

```python
"""Pydantic response models for palace.ingest.* MCP tools.

Used internally by runner to validate + serialize responses. MCP tool
signatures return dict[str, Any] (matching palace-mcp convention from
GIM-34/52/53/54/57); these models are the internal contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


_CFG = ConfigDict(extra="forbid")


class ExtractorRunResponse(BaseModel):
    """Successful extractor run response."""

    model_config = _CFG

    ok: Literal[True] = True
    run_id: str
    extractor: str
    project: str
    started_at: str
    finished_at: str
    duration_ms: int
    nodes_written: int
    edges_written: int
    success: Literal[True] = True


class ExtractorErrorResponse(BaseModel):
    """Failed extractor run / validation error response."""

    model_config = _CFG

    ok: Literal[False] = False
    error_code: str
    message: str
    extractor: str | None = None
    project: str | None = None
    run_id: str | None = None


class ExtractorDescriptor(BaseModel):
    """One entry in palace.ingest.list_extractors response."""

    model_config = _CFG

    name: str
    description: str


class ExtractorListResponse(BaseModel):
    """palace.ingest.list_extractors response."""

    model_config = _CFG

    ok: Literal[True] = True
    extractors: list[ExtractorDescriptor]
```

- [ ] **Step 4: Run tests + mypy**

```bash
uv run pytest tests/extractors/unit/test_schemas_response.py -v
# Expected: 6 passed
uv run mypy --strict src/palace_mcp/extractors/schemas.py
# Expected: Success
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/schemas.py \
        services/palace-mcp/tests/extractors/unit/test_schemas_response.py
git commit -m "feat(extractors): Pydantic response schemas (GIM-59)"
```

### Task 2.4: Registry (`registry.py`)

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_registry.py`

Note: HeartbeatExtractor is imported here; since heartbeat.py doesn't exist yet (Task 2.8), this task starts with an empty registry and heartbeat.py is wired in Task 2.8.

- [ ] **Step 1: Write failing tests (registry with no pre-registered extractors)**

File: `services/palace-mcp/tests/extractors/unit/test_registry.py`

```python
"""Unit tests for extractor registry (spec §3.3)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorStats,
)


class _FakeExtractor(BaseExtractor):
    name = "__test_fake"
    description = "fake for tests only"

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        return ExtractorStats()


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Snapshot + restore module-level EXTRACTORS across tests."""
    snapshot = dict(registry.EXTRACTORS)
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snapshot)


def test_get_unknown_returns_none() -> None:
    assert registry.get("definitely_not_registered") is None


def test_register_and_get() -> None:
    e = _FakeExtractor()
    registry.register(e)
    assert registry.get("__test_fake") is e


def test_register_duplicate_raises() -> None:
    e = _FakeExtractor()
    registry.register(e)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(e)


def test_list_all_returns_registered() -> None:
    e = _FakeExtractor()
    registry.register(e)
    names = [x.name for x in registry.list_all()]
    assert "__test_fake" in names


def test_list_all_preserves_insertion_order() -> None:
    class A(BaseExtractor):
        name = "__test_a"
        description = "a"

        async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
            return ExtractorStats()

    class B(BaseExtractor):
        name = "__test_b"
        description = "b"

        async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
            return ExtractorStats()

    registry.register(A())
    registry.register(B())
    all_names = [x.name for x in registry.list_all()]
    a_idx = all_names.index("__test_a")
    b_idx = all_names.index("__test_b")
    assert a_idx < b_idx
```

- [ ] **Step 2: Run — fail**

```bash
uv run pytest tests/extractors/unit/test_registry.py -v
```

- [ ] **Step 3: Implement `registry.py`**

File: `services/palace-mcp/src/palace_mcp/extractors/registry.py`

```python
"""Extractor registry — module-level dict of registered extractors.

Production registration is import-time (EXTRACTORS dict literal). Runtime
register() is test-only (for fixtures). Single-event-loop semantics mean
no thread-safety needed.
"""

from __future__ import annotations

from palace_mcp.extractors.base import BaseExtractor

EXTRACTORS: dict[str, BaseExtractor] = {}


def register(extractor: BaseExtractor) -> None:
    """Add an extractor to the registry.

    Production use: module-level (import-time). Test use: in fixture.
    Raises ValueError if name already registered.
    """
    if extractor.name in EXTRACTORS:
        raise ValueError(f"extractor already registered: {extractor.name!r}")
    EXTRACTORS[extractor.name] = extractor


def get(name: str) -> BaseExtractor | None:
    """Look up extractor by name. Returns None if not registered."""
    return EXTRACTORS.get(name)


def list_all() -> list[BaseExtractor]:
    """All registered extractors, in insertion order."""
    return list(EXTRACTORS.values())
```

- [ ] **Step 4: Run + mypy**

```bash
uv run pytest tests/extractors/unit/test_registry.py -v
# Expected: 5 passed
uv run mypy --strict src/palace_mcp/extractors/registry.py
# Expected: Success
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/registry.py \
        services/palace-mcp/tests/extractors/unit/test_registry.py
git commit -m "feat(extractors): registry with register/get/list_all (GIM-59)"
```

### Task 2.5: Extractor Cypher statements (`cypher.py`)

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cypher.py`

Pure module of SQL-like strings. Tested implicitly by runner tests; no dedicated test file.

- [ ] **Step 1: Implement**

File: `services/palace-mcp/src/palace_mcp/extractors/cypher.py`

```python
"""Cypher statements for extractor :IngestRun lifecycle.

Isolated from memory/cypher.py — extractor concerns stay in extractor
package. The new nullable fields (nodes_written, edges_written) are
additive on :IngestRun; existing paperclip ingest rows parse unchanged
(NULL for these fields).
"""

from __future__ import annotations

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
SET r.finished_at  = $finished_at,
    r.duration_ms  = $duration_ms,
    r.nodes_written = $nodes_written,
    r.edges_written = $edges_written,
    r.errors       = $errors,
    r.success      = $success
RETURN r
"""
```

- [ ] **Step 2: mypy check**

```bash
uv run mypy --strict src/palace_mcp/extractors/cypher.py
# Expected: Success
```

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cypher.py
git commit -m "feat(extractors): CREATE_INGEST_RUN + FINALIZE_INGEST_RUN Cypher (GIM-59)"
```

### Task 2.6: Runner lifecycle (`runner.py`)

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/runner.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_runner.py`

Implements `_precheck`, `_execute`, `_finalize`, `run_extractor` (spec §3.4 split). Extensive unit-test coverage per §7.1.

- [ ] **Step 1: Write failing tests — precheck errors**

File: `services/palace-mcp/tests/extractors/unit/test_runner.py`

```python
"""Unit tests for extractor runner (spec §3.4)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorConfigError,
    ExtractorRuntimeError,
    ExtractorStats,
)
from palace_mcp.extractors.runner import run_extractor


class _Ok(BaseExtractor):
    name = "__test_ok"
    description = "returns stats"

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        return ExtractorStats(nodes_written=5, edges_written=2)


class _ConfigFail(BaseExtractor):
    name = "__test_config_fail"
    description = "raises ExtractorConfigError"

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        raise ExtractorConfigError("missing tool X")


class _Unhandled(BaseExtractor):
    name = "__test_unhandled"
    description = "raises generic Exception"

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        raise RuntimeError("boom")


class _Slow(BaseExtractor):
    name = "__test_slow"
    description = "takes too long"

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        await asyncio.sleep(10.0)
        return ExtractorStats()


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    snap = dict(registry.EXTRACTORS)
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snap)


@pytest.fixture
def mock_driver(tmp_path: Path) -> AsyncMock:
    """Driver that returns :Project row when queried."""
    # Create a fake /repos/test-project with .git/
    repo = tmp_path / "repos" / "testproj"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()

    driver = AsyncMock()

    # session context manager
    session = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session

    # run() returns result with single() → a row dict
    result = AsyncMock()
    result.single.return_value = {"p": {"slug": "testproj"}}
    session.run.return_value = result

    return driver


@pytest.mark.asyncio
async def test_invalid_slug_returns_error(mock_driver: AsyncMock) -> None:
    res = await run_extractor(name="__test_ok", project="../etc", driver=mock_driver)
    assert res["ok"] is False
    assert res["error_code"] == "invalid_slug"
    # driver session must not be called for :IngestRun creation
    # (but may be called during project lookup — check that no IngestRun created)
    # Simplest: no session called at all since validate_slug fails first.
    mock_driver.session.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_extractor_returns_error(mock_driver: AsyncMock) -> None:
    res = await run_extractor(name="does_not_exist", project="testproj", driver=mock_driver)
    assert res["ok"] is False
    assert res["error_code"] == "unknown_extractor"


@pytest.mark.asyncio
async def test_project_not_registered_returns_error(tmp_path: Path) -> None:
    registry.register(_Ok())
    # Driver returns None for :Project lookup
    driver = AsyncMock()
    session = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    result = AsyncMock()
    result.single.return_value = None
    session.run.return_value = result

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(name="__test_ok", project="testproj", driver=driver)

    assert res["ok"] is False
    assert res["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_repo_not_mounted_returns_error(tmp_path: Path) -> None:
    registry.register(_Ok())
    # Driver returns :Project but /repos/testproj doesn't exist
    driver = AsyncMock()
    session = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session
    result = AsyncMock()
    result.single.return_value = {"p": {"slug": "testproj"}}
    session.run.return_value = result

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "no_such"):
        res = await run_extractor(name="__test_ok", project="testproj", driver=driver)

    assert res["ok"] is False
    assert res["error_code"] == "repo_not_mounted"


@pytest.mark.asyncio
async def test_happy_path_success(mock_driver: AsyncMock, tmp_path: Path) -> None:
    registry.register(_Ok())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(name="__test_ok", project="testproj", driver=mock_driver)

    assert res["ok"] is True
    assert res["success"] is True
    assert res["nodes_written"] == 5
    assert res["edges_written"] == 2
    assert res["extractor"] == "__test_ok"
    assert res["project"] == "testproj"
    assert "run_id" in res
    assert res["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_extractor_config_error_returns_mapped_code(
    mock_driver: AsyncMock, tmp_path: Path
) -> None:
    registry.register(_ConfigFail())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_config_fail", project="testproj", driver=mock_driver
        )
    assert res["ok"] is False
    assert res["error_code"] == "extractor_config_error"


@pytest.mark.asyncio
async def test_unhandled_exception_returns_unknown(
    mock_driver: AsyncMock, tmp_path: Path
) -> None:
    registry.register(_Unhandled())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_unhandled", project="testproj", driver=mock_driver
        )
    assert res["ok"] is False
    assert res["error_code"] == "unknown"
    assert "RuntimeError" in res.get("message", "")


@pytest.mark.asyncio
async def test_timeout_returns_runtime_error(
    mock_driver: AsyncMock, tmp_path: Path
) -> None:
    registry.register(_Slow())
    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__test_slow",
            project="testproj",
            driver=mock_driver,
            timeout_s=0.05,
        )
    assert res["ok"] is False
    assert res["error_code"] == "extractor_runtime_error"
    assert "timeout" in res["message"].lower()
```

- [ ] **Step 2: Run — fail (ImportError)**

```bash
uv run pytest tests/extractors/unit/test_runner.py -v
```

- [ ] **Step 3: Implement `runner.py`**

File: `services/palace-mcp/src/palace_mcp/extractors/runner.py`

```python
"""Extractor runner — lifecycle orchestration.

Split into _precheck / _execute / _finalize + run_extractor orchestrator
(spec §3.4). Each helper is independently testable.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union
from uuid import uuid4

from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorError,
    ExtractorStats,
)
from palace_mcp.extractors.cypher import CREATE_INGEST_RUN, FINALIZE_INGEST_RUN
from palace_mcp.extractors.schemas import (
    ExtractorErrorResponse,
    ExtractorRunResponse,
)
from palace_mcp.memory.projects import InvalidSlug, validate_slug

REPOS_ROOT = Path("/repos")
EXTRACTOR_TIMEOUT_S = 300.0

GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p"


# --- precheck ---

@dataclass(frozen=True)
class _PrecheckOk:
    extractor: BaseExtractor
    repo_path: Path
    group_id: str


@dataclass(frozen=True)
class _PrecheckError:
    error_code: str
    message: str
    extractor: str | None = None


_PrecheckResult = Union[_PrecheckOk, _PrecheckError]


async def _precheck(
    *, name: str, project: str, driver: AsyncDriver, repos_root: Path
) -> _PrecheckResult:
    """Validate slug, look up extractor, verify :Project + repo mount."""
    try:
        validate_slug(project)
    except InvalidSlug as e:
        return _PrecheckError(error_code="invalid_slug", message=str(e))

    extractor = registry.get(name)
    if extractor is None:
        return _PrecheckError(
            error_code="unknown_extractor",
            message=f"no extractor named {name!r}",
        )

    async with driver.session() as session:
        result = await session.run(GET_PROJECT, slug=project)
        row = await result.single()
    if row is None:
        return _PrecheckError(
            error_code="project_not_registered",
            message=f"no :Project {{slug: {project!r}}}",
            extractor=name,
        )

    repo_path = repos_root / project
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        return _PrecheckError(
            error_code="repo_not_mounted",
            message=f"no mounted git repo at {repo_path}",
            extractor=name,
        )

    group_id = f"project/{project}"
    return _PrecheckOk(extractor=extractor, repo_path=repo_path, group_id=group_id)


# --- execute ---

@dataclass(frozen=True)
class _ExecuteOk:
    stats: ExtractorStats


@dataclass(frozen=True)
class _ExecuteError:
    error_code: str
    errors: list[str]


_ExecuteResult = Union[_ExecuteOk, _ExecuteError]


async def _execute(
    *, extractor: BaseExtractor, ctx: ExtractionContext, timeout_s: float
) -> _ExecuteResult:
    """Wrap extract() in timeout + Exception handling. Never raises."""
    logger = ctx.logger
    try:
        stats = await asyncio.wait_for(extractor.extract(ctx), timeout=timeout_s)
        return _ExecuteOk(stats=stats)
    except asyncio.TimeoutError:
        msg = f"timeout after {timeout_s}s"
        logger.error("extractor.execute.timeout", extra={"run_id": ctx.run_id})
        return _ExecuteError(error_code="extractor_runtime_error", errors=[msg])
    except ExtractorError as e:
        logger.error(
            "extractor.execute.extractor_error",
            extra={"run_id": ctx.run_id, "error_code": e.error_code},
        )
        return _ExecuteError(error_code=e.error_code, errors=[str(e)[:200]])
    except Exception as e:  # noqa: BLE001 — unexpected, structured response
        logger.exception("extractor.execute.unhandled")  # stack → stdout only
        return _ExecuteError(
            error_code="unknown",
            errors=[f"{type(e).__name__}: {str(e)[:200]}"],
        )


# --- finalize ---

async def _finalize(
    *,
    driver: AsyncDriver,
    run_id: str,
    result: _ExecuteResult,
    finished_at: str,
    duration_ms: int,
) -> tuple[int, int, list[str], bool]:
    """Write FINALIZE_INGEST_RUN. Returns (nodes, edges, errors, success)."""
    if isinstance(result, _ExecuteOk):
        nodes, edges, errors, success = (
            result.stats.nodes_written,
            result.stats.edges_written,
            [],
            True,
        )
    else:
        nodes, edges, errors, success = 0, 0, result.errors, False

    async with driver.session() as session:
        await session.run(
            FINALIZE_INGEST_RUN,
            id=run_id,
            finished_at=finished_at,
            duration_ms=duration_ms,
            nodes_written=nodes,
            edges_written=edges,
            errors=errors,
            success=success,
        )
    return nodes, edges, errors, success


# --- orchestrator ---

async def run_extractor(
    name: str,
    project: str,
    *,
    driver: AsyncDriver,
    timeout_s: float = EXTRACTOR_TIMEOUT_S,
) -> dict[str, Any]:
    """Full lifecycle: precheck → create :IngestRun → execute → finalize."""
    # 1. Precheck
    pre = await _precheck(
        name=name, project=project, driver=driver, repos_root=REPOS_ROOT
    )
    if isinstance(pre, _PrecheckError):
        return ExtractorErrorResponse(
            error_code=pre.error_code,
            message=pre.message,
            extractor=pre.extractor,
            project=project,
        ).model_dump()

    # 2. Create :IngestRun
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    source = f"extractor.{name}"

    async with driver.session() as session:
        await session.run(
            CREATE_INGEST_RUN,
            id=run_id,
            source=source,
            group_id=pre.group_id,
            started_at=started_at,
        )

    # 3. Execute
    logger = logging.getLogger(f"palace_mcp.extractors.{name}")
    logger.info(
        "extractor.run.start",
        extra={
            "extractor": name,
            "project": project,
            "run_id": run_id,
            "group_id": pre.group_id,
        },
    )
    ctx = ExtractionContext(
        driver=driver,
        project_slug=project,
        group_id=pre.group_id,
        repo_path=pre.repo_path,
        run_id=run_id,
        logger=logger,
    )
    start_mono = time.monotonic()
    exec_result = await _execute(
        extractor=pre.extractor, ctx=ctx, timeout_s=timeout_s
    )
    duration_ms = int((time.monotonic() - start_mono) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    # 4. Finalize
    nodes, edges, errors, success = await _finalize(
        driver=driver,
        run_id=run_id,
        result=exec_result,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )

    # 5. Return response
    if success:
        logger.info(
            "extractor.run.finish",
            extra={
                "extractor": name,
                "project": project,
                "run_id": run_id,
                "duration_ms": duration_ms,
                "nodes_written": nodes,
                "edges_written": edges,
                "success": True,
            },
        )
        return ExtractorRunResponse(
            run_id=run_id,
            extractor=name,
            project=project,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            nodes_written=nodes,
            edges_written=edges,
        ).model_dump()

    assert isinstance(exec_result, _ExecuteError)
    logger.error(
        "extractor.run.error",
        extra={
            "extractor": name,
            "project": project,
            "run_id": run_id,
            "duration_ms": duration_ms,
            "error_code": exec_result.error_code,
            "error_head": errors[0] if errors else "",
        },
    )
    return ExtractorErrorResponse(
        error_code=exec_result.error_code,
        message=errors[0] if errors else "",
        extractor=name,
        project=project,
        run_id=run_id,
    ).model_dump()
```

- [ ] **Step 4: Run tests — pass**

```bash
uv run pytest tests/extractors/unit/test_runner.py -v
# Expected: 8 passed
```

- [ ] **Step 5: mypy check**

```bash
uv run mypy --strict src/palace_mcp/extractors/runner.py
# Expected: Success
```

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/runner.py \
        services/palace-mcp/tests/extractors/unit/test_runner.py
git commit -m "feat(extractors): runner with precheck/execute/finalize split (GIM-59)"
```

### Task 2.7: Schema aggregator (`schema.py`)

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/schema.py`
- Create: `services/palace-mcp/tests/extractors/integration/conftest.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_ensure_extractors_schema.py`

Integration test — needs real Neo4j.

- [ ] **Step 1: Add `testcontainers-neo4j` dev-dep**

```bash
cd services/palace-mcp
uv add --dev testcontainers[neo4j]
# pyproject.toml [tool.uv.dependency-groups.dev] gains the entry
```

- [ ] **Step 2: Create integration conftest**

File: `services/palace-mcp/tests/extractors/integration/conftest.py`

```python
"""Integration test fixtures — real Neo4j via testcontainers or compose reuse.

Per spec §7.2: COMPOSE_NEO4J_URI env-var selects reuse of an existing
compose Neo4j; absent, spin up a throwaway container.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from neo4j import AsyncGraphDatabase, AsyncDriver


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    if reuse := os.environ.get("COMPOSE_NEO4J_URI"):
        yield reuse
        return

    # Fallback: boot a throwaway Neo4j container.
    from testcontainers.neo4j import Neo4jContainer  # type: ignore[import]

    with Neo4jContainer("neo4j:5.26.0") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def neo4j_auth() -> tuple[str, str]:
    """Default auth for testcontainers; override if using compose reuse."""
    user = os.environ.get("COMPOSE_NEO4J_USER", "neo4j")
    pw = os.environ.get("COMPOSE_NEO4J_PASSWORD", "password")
    return user, pw


@pytest.fixture
async def driver(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[AsyncDriver]:
    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        yield drv
    finally:
        await drv.close()


@pytest.fixture(autouse=True)
async def clean_db(driver: AsyncDriver) -> None:
    """Clean all nodes between tests for hermetic runs."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
```

- [ ] **Step 3: Write failing test**

File: `services/palace-mcp/tests/extractors/integration/test_ensure_extractors_schema.py`

```python
"""Integration test — ensure_extractors_schema creates declared constraints + indexes."""

from __future__ import annotations

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorStats,
)
from palace_mcp.extractors.schema import ensure_extractors_schema


class _SchemaTest(BaseExtractor):
    name = "__schema_test"
    description = "declares schema for testing"
    constraints = [
        "CREATE CONSTRAINT __schema_test_id IF NOT EXISTS "
        "FOR (n:__SchemaTestNode) REQUIRE n.id IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX __schema_test_ts IF NOT EXISTS "
        "FOR (n:__SchemaTestNode) ON (n.ts)",
    ]

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        return ExtractorStats()


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    snap = dict(registry.EXTRACTORS)
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snap)


@pytest.mark.asyncio
async def test_ensure_extractors_schema_creates_declared(driver: AsyncDriver) -> None:
    registry.register(_SchemaTest())
    await ensure_extractors_schema(driver)

    async with driver.session() as s:
        result = await s.run("SHOW CONSTRAINTS YIELD name")
        names = [row["name"] async for row in result]
    assert "__schema_test_id" in names

    async with driver.session() as s:
        result = await s.run("SHOW INDEXES YIELD name")
        names = [row["name"] async for row in result]
    assert "__schema_test_ts" in names


@pytest.mark.asyncio
async def test_ensure_extractors_schema_idempotent(driver: AsyncDriver) -> None:
    """Re-run succeeds without errors (IF NOT EXISTS)."""
    registry.register(_SchemaTest())
    await ensure_extractors_schema(driver)
    await ensure_extractors_schema(driver)  # second run should not raise


@pytest.mark.asyncio
async def test_ensure_extractors_schema_empty_registry(driver: AsyncDriver) -> None:
    """Empty registry → no-op, no errors."""
    await ensure_extractors_schema(driver)  # empty, should succeed
```

- [ ] **Step 4: Run — fail (ImportError)**

```bash
COMPOSE_NEO4J_URI=bolt://localhost:7687 \
COMPOSE_NEO4J_PASSWORD=<from .env> \
uv run pytest tests/extractors/integration/test_ensure_extractors_schema.py -v
# OR without env — testcontainers boots a container (slower)
```

- [ ] **Step 5: Implement `schema.py`**

File: `services/palace-mcp/src/palace_mcp/extractors/schema.py`

```python
"""Aggregate + apply constraints/indexes declared by registered extractors.

Called in main.py lifespan after memory.constraints.ensure_schema().
Idempotent — extractor declarations use IF NOT EXISTS.
"""

from __future__ import annotations

import logging

from neo4j import AsyncDriver

from palace_mcp.extractors import registry

logger = logging.getLogger(__name__)


async def ensure_extractors_schema(driver: AsyncDriver) -> None:
    """Apply all declared constraints + indexes from registered extractors."""
    statements: list[str] = []
    for extractor in registry.list_all():
        statements.extend(extractor.constraints)
        statements.extend(extractor.indexes)
    if not statements:
        logger.info("extractors.schema.noop", extra={"registered": 0})
        return
    async with driver.session() as session:
        for stmt in statements:
            await session.run(stmt)
    logger.info(
        "extractors.schema.applied",
        extra={"statement_count": len(statements)},
    )
```

- [ ] **Step 6: Run tests — pass**

```bash
uv run pytest tests/extractors/integration/test_ensure_extractors_schema.py -v
# Expected: 3 passed
```

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/pyproject.toml \
        services/palace-mcp/uv.lock \
        services/palace-mcp/src/palace_mcp/extractors/schema.py \
        services/palace-mcp/tests/extractors/integration/conftest.py \
        services/palace-mcp/tests/extractors/integration/test_ensure_extractors_schema.py
git commit -m "feat(extractors): ensure_extractors_schema aggregator + integration test (GIM-59)"
```

### Task 2.8: HeartbeatExtractor (`heartbeat.py`)

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/heartbeat.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_heartbeat.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_heartbeat_integration.py`
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py` (add import + register)

- [ ] **Step 1: Write failing unit test**

File: `services/palace-mcp/tests/extractors/unit/test_heartbeat.py`

```python
"""Unit tests for HeartbeatExtractor — mock driver."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from palace_mcp.extractors.base import ExtractionContext
from palace_mcp.extractors.heartbeat import HeartbeatExtractor


@pytest.mark.asyncio
async def test_heartbeat_extract_writes_and_returns_stats() -> None:
    driver = AsyncMock()
    session = AsyncMock()
    driver.session.return_value.__aenter__.return_value = session

    ctx = ExtractionContext(
        driver=driver,
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=Path("/repos/gimle"),
        run_id="test-run-123",
        logger=logging.getLogger("test"),
    )

    extractor = HeartbeatExtractor()
    stats = await extractor.extract(ctx)

    assert stats.nodes_written == 1
    assert stats.edges_written == 0

    session.run.assert_called_once()
    call_args = session.run.call_args
    cypher, kwargs = call_args.args[0], call_args.kwargs
    assert "MERGE (h:ExtractorHeartbeat" in cypher
    assert kwargs["run_id"] == "test-run-123"
    assert kwargs["extractor"] == "heartbeat"
    assert kwargs["group_id"] == "project/gimle"
    assert "ts" in kwargs  # ISO-8601 string
```

- [ ] **Step 2: Write failing integration test**

File: `services/palace-mcp/tests/extractors/integration/test_heartbeat_integration.py`

```python
"""Integration test — real Neo4j, full heartbeat flow."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractionContext
from palace_mcp.extractors.heartbeat import HeartbeatExtractor
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.extractors import registry


@pytest.fixture(autouse=True)
def _heartbeat_in_registry() -> None:
    """Ensure heartbeat registered for schema bootstrap."""
    if "heartbeat" not in registry.EXTRACTORS:
        registry.register(HeartbeatExtractor())
    yield


@pytest.mark.asyncio
async def test_heartbeat_writes_to_neo4j(driver: AsyncDriver) -> None:
    await ensure_extractors_schema(driver)

    run_id = str(uuid.uuid4())
    ctx = ExtractionContext(
        driver=driver,
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=Path("/tmp"),
        run_id=run_id,
        logger=logging.getLogger("test"),
    )

    extractor = HeartbeatExtractor()
    stats = await extractor.extract(ctx)
    assert stats.nodes_written == 1

    async with driver.session() as s:
        result = await s.run(
            "MATCH (h:ExtractorHeartbeat {run_id: $run_id}) RETURN h",
            run_id=run_id,
        )
        row = await result.single()
    assert row is not None
    node = row["h"]
    assert node["run_id"] == run_id
    assert node["extractor"] == "heartbeat"
    assert node["group_id"] == "project/testproj"
    assert node["ts"]  # ISO-8601 string populated
```

- [ ] **Step 3: Run — fail (ImportError)**

```bash
uv run pytest tests/extractors/unit/test_heartbeat.py \
              tests/extractors/integration/test_heartbeat_integration.py -v
```

- [ ] **Step 4: Implement `heartbeat.py`**

File: `services/palace-mcp/src/palace_mcp/extractors/heartbeat.py`

```python
"""HeartbeatExtractor — diagnostic probe, shipped in production.

Writes one :ExtractorHeartbeat node per run. Zero external dependencies.
Verifies extractor pipeline is alive; template for future extractor authors.

Idempotency: each runner call generates a fresh run_id → MERGE dedegenerates
to CREATE; actual idempotency of the framework is guaranteed by unique run_id,
not by MERGE semantics here (see spec §3.6).
"""

from __future__ import annotations

from datetime import datetime, timezone

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorStats,
)

_CYPHER_MERGE = """
MERGE (h:ExtractorHeartbeat {run_id: $run_id})
ON CREATE SET
    h.ts = $ts,
    h.extractor = $extractor,
    h.group_id = $group_id
"""


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
                _CYPHER_MERGE,
                run_id=ctx.run_id,
                ts=ts,
                extractor=self.name,
                group_id=ctx.group_id,
            )
        ctx.logger.info(
            "heartbeat.node_written",
            extra={"run_id": ctx.run_id, "group_id": ctx.group_id},
        )
        return ExtractorStats(nodes_written=1, edges_written=0)
```

- [ ] **Step 5: Wire heartbeat into registry**

Modify `services/palace-mcp/src/palace_mcp/extractors/registry.py`:

```python
from palace_mcp.extractors.base import BaseExtractor
from palace_mcp.extractors.heartbeat import HeartbeatExtractor

EXTRACTORS: dict[str, BaseExtractor] = {
    "heartbeat": HeartbeatExtractor(),
}
# ... rest of file unchanged
```

- [ ] **Step 6: Run tests — pass**

```bash
uv run pytest tests/extractors/unit/test_heartbeat.py \
              tests/extractors/integration/test_heartbeat_integration.py -v
# Expected: 2 passed
```

- [ ] **Step 7: mypy check**

```bash
uv run mypy --strict src/palace_mcp/extractors/heartbeat.py \
                    src/palace_mcp/extractors/registry.py
# Expected: Success
```

- [ ] **Step 8: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/heartbeat.py \
        services/palace-mcp/src/palace_mcp/extractors/registry.py \
        services/palace-mcp/tests/extractors/unit/test_heartbeat.py \
        services/palace-mcp/tests/extractors/integration/test_heartbeat_integration.py
git commit -m "feat(extractors): HeartbeatExtractor + register in production (GIM-59)"
```

### Task 2.9: Wire to main.py lifespan + MCP tools in mcp_server.py

**Owner:** PythonEngineer

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/main.py`
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_mcp_tool_integration.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_runner_error_paths_integration.py`

- [ ] **Step 1: Wire ensure_extractors_schema in lifespan**

Open `services/palace-mcp/src/palace_mcp/main.py`. Locate the lifespan context manager. Add after the existing `ensure_schema(driver, default_group_id=...)` call:

```python
from palace_mcp.extractors.schema import ensure_extractors_schema

# inside lifespan, after memory.constraints.ensure_schema(...):
await ensure_extractors_schema(driver)
```

- [ ] **Step 2: Add MCP tools in mcp_server.py**

Open `services/palace-mcp/src/palace_mcp/mcp_server.py`. Add imports:

```python
from palace_mcp.extractors.runner import run_extractor as _run_extractor
from palace_mcp.extractors import registry as _extractor_registry
```

Add two new tool registrations (near other `palace.*` tools):

```python
@_mcp.tool(
    name="palace.ingest.run_extractor",
    description=(
        "Run a named extractor against a registered project. Writes nodes/edges "
        "scoped by group_id. Creates :IngestRun tracking. Returns run_id + "
        "duration_ms + nodes_written + edges_written on success, or error_code "
        "envelope on failure. Default timeout 300s per run."
    ),
)
async def _palace_ingest_run_extractor(name: str, project: str) -> dict[str, Any]:
    driver = _get_driver_from_global()
    return await _run_extractor(name=name, project=project, driver=driver)


@_mcp.tool(
    name="palace.ingest.list_extractors",
    description=(
        "List registered extractors with their descriptions. Discovery endpoint "
        "so clients don't hardcode extractor names."
    ),
)
async def _palace_ingest_list_extractors() -> dict[str, Any]:
    extractors = [
        {"name": e.name, "description": e.description}
        for e in _extractor_registry.list_all()
    ]
    return {"ok": True, "extractors": extractors}
```

Note: `_get_driver_from_global()` — use the same pattern as existing palace.memory tools (they access driver via an existing accessor or module-global; follow that convention).

- [ ] **Step 3: Write integration test — MCP tool end-to-end**

File: `services/palace-mcp/tests/extractors/integration/test_mcp_tool_integration.py`

```python
"""Integration test — end-to-end via MCP tool handler.

Calls the tool function directly (bypassing MCP transport) to verify
the wire-up between run_extractor runner and the tool decorator works
and returns the expected dict shape.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from palace_mcp.extractors.heartbeat import HeartbeatExtractor
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.extractors.runner import run_extractor


@pytest.fixture(autouse=True)
def _heartbeat_ready() -> None:
    if "heartbeat" not in registry.EXTRACTORS:
        registry.register(HeartbeatExtractor())
    yield


@pytest.fixture
async def _project_and_repo(driver: AsyncDriver, tmp_path: Path) -> Path:
    """Set up :Project and /repos/<slug> with .git/."""
    async with driver.session() as s:
        await s.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = 'project/' + $slug,
                p.name = $name,
                p.tags = []
            """,
            slug="testproj",
            name="TestProj",
        )
    repo = tmp_path / "repos" / "testproj"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return tmp_path / "repos"


@pytest.mark.asyncio
async def test_run_extractor_end_to_end(
    driver: AsyncDriver, _project_and_repo: Path
) -> None:
    await ensure_extractors_schema(driver)

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo):
        res = await run_extractor(
            name="heartbeat", project="testproj", driver=driver
        )

    assert res["ok"] is True
    assert res["extractor"] == "heartbeat"
    assert res["project"] == "testproj"
    assert res["nodes_written"] == 1

    # Verify :ExtractorHeartbeat persisted
    async with driver.session() as s:
        result = await s.run(
            "MATCH (h:ExtractorHeartbeat {run_id: $run_id}) RETURN h",
            run_id=res["run_id"],
        )
        row = await result.single()
    assert row is not None

    # Verify :IngestRun finalized
    async with driver.session() as s:
        result = await s.run(
            "MATCH (r:IngestRun {id: $id}) RETURN r",
            id=res["run_id"],
        )
        row = await result.single()
    assert row is not None
    r = dict(row["r"])
    assert r["source"] == "extractor.heartbeat"
    assert r["success"] is True
    assert r["nodes_written"] == 1


@pytest.mark.asyncio
async def test_rerun_creates_separate_records(
    driver: AsyncDriver, _project_and_repo: Path
) -> None:
    await ensure_extractors_schema(driver)

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo):
        res1 = await run_extractor(
            name="heartbeat", project="testproj", driver=driver
        )
        res2 = await run_extractor(
            name="heartbeat", project="testproj", driver=driver
        )

    assert res1["run_id"] != res2["run_id"]

    async with driver.session() as s:
        result = await s.run(
            "MATCH (h:ExtractorHeartbeat) RETURN count(h) AS c"
        )
        row = await result.single()
    assert row["c"] == 2
```

- [ ] **Step 4: Write integration test — error paths**

File: `services/palace-mcp/tests/extractors/integration/test_runner_error_paths_integration.py`

```python
"""Integration tests for runner error paths with real Neo4j."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorConfigError,
    ExtractorStats,
)
from palace_mcp.extractors.heartbeat import HeartbeatExtractor
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema


class _FailingExtractor(BaseExtractor):
    name = "__integration_failing"
    description = "raises ExtractorConfigError"
    constraints = []
    indexes = []

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        raise ExtractorConfigError("test-triggered config error")


@pytest.fixture(autouse=True)
def _registry_setup() -> None:
    """Register heartbeat + failing extractor; clean up after."""
    snap = dict(registry.EXTRACTORS)
    if "heartbeat" not in registry.EXTRACTORS:
        registry.register(HeartbeatExtractor())
    registry.register(_FailingExtractor())
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snap)


@pytest.mark.asyncio
async def test_unknown_extractor_no_ingest_run_created(
    driver: AsyncDriver,
) -> None:
    """Unknown extractor returns early before creating :IngestRun."""
    await ensure_extractors_schema(driver)
    # count IngestRuns before
    async with driver.session() as s:
        r1 = await s.run("MATCH (n:IngestRun) RETURN count(n) AS c")
        before = (await r1.single())["c"]

    res = await run_extractor(
        name="does_not_exist", project="gimle", driver=driver
    )
    assert res["ok"] is False
    assert res["error_code"] == "unknown_extractor"

    async with driver.session() as s:
        r2 = await s.run("MATCH (n:IngestRun) RETURN count(n) AS c")
        after = (await r2.single())["c"]
    assert before == after  # no new IngestRun


@pytest.mark.asyncio
async def test_failing_extractor_finalizes_as_errored(
    driver: AsyncDriver, tmp_path: Path
) -> None:
    """When extractor raises, :IngestRun finalized with success=false + errors."""
    await ensure_extractors_schema(driver)

    # set up :Project + repo
    async with driver.session() as s:
        await s.run(
            "MERGE (p:Project {slug: $slug}) SET p.group_id='project/'+$slug, p.name=$slug, p.tags=[]",
            slug="errtest",
        )
    repo = tmp_path / "repos" / "errtest"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__integration_failing", project="errtest", driver=driver
        )

    assert res["ok"] is False
    assert res["error_code"] == "extractor_config_error"
    assert res["run_id"] is not None  # IngestRun was created

    # Verify :IngestRun has success=false + errors populated
    async with driver.session() as s:
        r = await s.run("MATCH (r:IngestRun {id: $id}) RETURN r", id=res["run_id"])
        row = await r.single()
    assert row is not None
    ir = dict(row["r"])
    assert ir["success"] is False
    assert len(ir["errors"]) >= 1
    assert "test-triggered" in ir["errors"][0]
```

- [ ] **Step 5: Run all extractor tests**

```bash
uv run pytest tests/extractors/ -v
# Expected: all pass (previously-added ~20 unit + 8 integration)
```

- [ ] **Step 6: mypy check**

```bash
uv run mypy --strict src/palace_mcp/
# Expected: Success (no regressions on main.py / mcp_server.py)
```

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/main.py \
        services/palace-mcp/src/palace_mcp/mcp_server.py \
        services/palace-mcp/tests/extractors/integration/test_mcp_tool_integration.py \
        services/palace-mcp/tests/extractors/integration/test_runner_error_paths_integration.py
git commit -m "feat(extractors): wire MCP tools + lifespan schema bootstrap (GIM-59)"
```

### Task 2.10: Testcontainers + CI wiring

**Owner:** PythonEngineer

Already covered during Task 2.7 Step 1 (`uv add --dev testcontainers[neo4j]`). Verify and finalize.

- [ ] **Step 1: Verify pyproject.toml dev-dep present**

```bash
grep -A 3 'dependency-groups' services/palace-mcp/pyproject.toml | head -10
# Expected: testcontainers[neo4j] in dev deps
```

- [ ] **Step 2: Verify local-dev + CI run both work**

```bash
# Mode 1 — testcontainers auto (slower, hermetic)
cd services/palace-mcp
uv run pytest tests/extractors/integration/ -v

# Mode 2 — reuse compose Neo4j (fast, requires `docker compose --profile review up -d neo4j`)
export COMPOSE_NEO4J_URI=bolt://localhost:7687
export COMPOSE_NEO4J_PASSWORD=<from .env NEO4J_PASSWORD>
uv run pytest tests/extractors/integration/ -v
unset COMPOSE_NEO4J_URI COMPOSE_NEO4J_PASSWORD
```

Both modes must pass. The conftest auto-detects which path to use.

- [ ] **Step 3: Update CI workflow if needed**

Check `.github/workflows/` for any existing pytest config. If CI already spins up Neo4j as a service container for pytest, add:

```yaml
env:
  COMPOSE_NEO4J_URI: bolt://localhost:7687
  COMPOSE_NEO4J_PASSWORD: ${{ secrets.TEST_NEO4J_PASSWORD }}
```

to the test job. If not, CI falls back to testcontainers (slower but hermetic).

- [ ] **Step 4: Commit (if CI changed)**

```bash
git add .github/workflows/*.yml
git commit -m "ci: wire COMPOSE_NEO4J_URI env for extractor integration tests (GIM-59)"
```

### Task 2.10a: Consumer-compat regression test

**Owner:** PythonEngineer

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_ingest_run_back_compat.py`

Reviewer-surfaced concern (§6.3 of spec): new nullable fields on `:IngestRun` must not break existing `memory/health.py` query which hardcodes `source="paperclip"`.

- [ ] **Step 1: Write the regression test**

File: `services/palace-mcp/tests/extractors/integration/test_ingest_run_back_compat.py`

```python
"""Regression test — new :IngestRun nullable fields don't break existing consumers.

Per spec §6.3: memory/health.py:46 hardcodes source='paperclip' and parses
:IngestRun rows. Adding nullable nodes_written / edges_written must not
disturb that query.
"""

from __future__ import annotations

import pytest
from neo4j import AsyncDriver


@pytest.mark.asyncio
async def test_paperclip_ingest_row_parses_with_new_nullable_fields(
    driver: AsyncDriver,
) -> None:
    """Insert a paperclip :IngestRun (old shape) + an extractor one (new fields);
    verify LATEST_INGEST_RUN query returns paperclip row cleanly."""
    async with driver.session() as s:
        # Paperclip-style ingest run (old shape — no new fields)
        await s.run(
            """
            CREATE (r:IngestRun {
              id: 'paperclip-1',
              source: 'paperclip',
              group_id: 'project/gimle',
              started_at: '2026-04-20T09:00:00+00:00',
              finished_at: '2026-04-20T09:01:00+00:00',
              duration_ms: 60000,
              errors: [],
              success: true
            })
            """
        )
        # Extractor-style run (new nullable fields populated)
        await s.run(
            """
            CREATE (r:IngestRun {
              id: 'extractor-1',
              source: 'extractor.heartbeat',
              group_id: 'project/gimle',
              started_at: '2026-04-20T10:00:00+00:00',
              finished_at: '2026-04-20T10:00:01+00:00',
              duration_ms: 1000,
              nodes_written: 1,
              edges_written: 0,
              errors: [],
              success: true
            })
            """
        )

    # Replicate memory/health.py:46 call:
    from palace_mcp.memory.cypher import LATEST_INGEST_RUN

    async with driver.session() as s:
        result = await s.run(LATEST_INGEST_RUN, source="paperclip")
        row = await result.single()
    assert row is not None
    r = dict(row["r"])
    assert r["source"] == "paperclip"
    assert r["success"] is True
    # Old rows don't have nodes_written — absent from dict or None
    assert r.get("nodes_written") is None
```

- [ ] **Step 2: Run test — pass**

```bash
uv run pytest tests/extractors/integration/test_ingest_run_back_compat.py -v
# Expected: 1 passed
```

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_ingest_run_back_compat.py
git commit -m "test(extractors): :IngestRun back-compat with paperclip consumers (GIM-59)"
```

### Task 2.11: PE → TW handoff

**Owner:** PythonEngineer

- [ ] **Step 1: Verify all Phase 2 code complete**

```bash
cd services/palace-mcp
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy --strict src/
uv run pytest tests/extractors/ -v
# All must be green
```

- [ ] **Step 2: Push final Phase 2 code**

```bash
git push origin feature/GIM-59-extractor-framework-substrate
```

- [ ] **Step 3: Post paperclip handoff comment**

```
## Phase 2 code complete — handoff to TW for Task 2.12 docs

All Phase 2.1-2.10a tasks done. Commits on feature/GIM-59-extractor-framework-substrate:
- 2.1 scaffold
- 2.2 BaseExtractor + tests
- 2.3 Pydantic schemas
- 2.4 registry
- 2.5 Cypher
- 2.6 runner + extensive tests
- 2.7 schema aggregator + integration
- 2.8 HeartbeatExtractor + registered
- 2.9 MCP tools + lifespan wiring + integration
- 2.10 testcontainers dev-dep
- 2.10a IngestRun back-compat test

Test status: ruff green, mypy --strict green, pytest all green.
Branch HEAD: <sha>

@TechnicalWriter your turn — Phase 2.12 docs (CLAUDE.md Extractors section + rollback runbook).
```

- [ ] **Step 4: Reassign to TechnicalWriter**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"0e8222fd-88b9-4593-98f6-847a448b0aab"}' \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

### Task 2.12: CLAUDE.md section + rollback runbook

**Owner:** TechnicalWriter

**Files:**
- Modify: `CLAUDE.md` (append `## Extractors` section)
- Create: `docs/runbooks/2026-04-20-GIM-59-extractor-framework-rollback.md`

- [ ] **Step 1: Append `## Extractors` section to CLAUDE.md**

Open `CLAUDE.md`. Append at end (after `## Pinning`):

```markdown

## Extractors

Palace-mcp ships a pluggable extractor framework under
`services/palace-mcp/src/palace_mcp/extractors/`. Each extractor writes
domain nodes/edges to Neo4j scoped by `group_id = "project/<slug>"` and is
invoked via MCP tool `palace.ingest.run_extractor(name, project)`.

### Registered extractors

- `heartbeat` — diagnostic probe. Writes one `:ExtractorHeartbeat` node per
  run. Use to verify the pipeline is alive before running heavy extractors.

### Running an extractor

From Claude Code (or any MCP client connected to palace-mcp):

```
palace.ingest.list_extractors()
palace.ingest.run_extractor(name="heartbeat", project="gimle")
```

Response shape (success):
```json
{"ok": true, "run_id": "<uuid>", "extractor": "heartbeat",
 "project": "gimle", "duration_ms": 42,
 "nodes_written": 1, "edges_written": 0, "success": true}
```

Error envelope on failure:
```json
{"ok": false, "error_code": "invalid_slug | unknown_extractor |
 project_not_registered | repo_not_mounted | extractor_config_error |
 extractor_runtime_error | unknown", "message": "<short>",
 "extractor": "...", "project": "...", "run_id": "..."}
```

### Adding a new extractor

1. Create `src/palace_mcp/extractors/<name>.py` with a class inheriting
   `BaseExtractor`. Declare `name`, `description`, `constraints`, `indexes`
   class attributes. Implement `async def extract(self, ctx) -> ExtractorStats`.
2. Import and register in `registry.py`:
   ```python
   from palace_mcp.extractors.<name> import <ClassName>
   EXTRACTORS["<name>"] = <ClassName>()
   ```
3. Unit test in `tests/extractors/unit/test_<name>.py` (mock driver).
4. Integration test in `tests/extractors/integration/test_<name>_integration.py`
   (real Neo4j via testcontainers or compose reuse).

### Known limitations

- **`palace.memory.health()` shows only paperclip ingest runs**, not
  extractor runs (`memory/health.py:46` hardcodes `source="paperclip"`).
  Query extractor runs via `palace.memory.lookup(entity_type="IngestRun",
  filters={"source": "extractor.<name>"})`. UI-friendly health grouping
  is a followup.
- **No scheduler** — extractor runs are manual via MCP tool. Cron trigger
  is a followup.
- **No concurrent runs** — palace-mcp's event loop serializes MCP tool
  calls. A heavy extractor blocks other tools during its run.
```

- [ ] **Step 2: Create rollback runbook**

File: `docs/runbooks/2026-04-20-GIM-59-extractor-framework-rollback.md`

```markdown
# GIM-59 extractor framework rollback

**Spec:** `docs/superpowers/specs/2026-04-20-extractor-framework-substrate-design.md`

**Trigger conditions:**
- `ensure_extractors_schema` fails at palace-mcp startup, crash-looping.
- `palace.ingest.run_extractor` or `list_extractors` breaks existing
  `palace.memory.*` tools (regression).
- Neo4j schema drift after `:ExtractorHeartbeat` constraint / indexes cause
  migration issues.

## Pre-rollback snapshot

```bash
PRE_SHA=$(git rev-parse origin/develop)
echo "PRE_SHA=$PRE_SHA" | tee /tmp/extractor-framework-rollback.env
```

## Steps

### 1. Revert the merge commit on develop

```bash
MERGE_SHA=$(git log origin/develop --oneline | grep 'GIM-59' | head -1 | awk '{print $1}')
git fetch origin
git switch -c rollback/GIM-59-extractor-framework origin/develop
git revert -m 1 $MERGE_SHA
git push origin rollback/GIM-59-extractor-framework
```

Open PR `rollback: GIM-59 extractor framework` against develop and merge.

### 2. Clean up Neo4j schema

On the iMac neo4j container:

```cypher
// Drop heartbeat schema
DROP CONSTRAINT extractor_heartbeat_id IF EXISTS;
DROP INDEX extractor_heartbeat_group_id IF EXISTS;
DROP INDEX extractor_heartbeat_ts IF EXISTS;

// Delete any heartbeat nodes produced during testing
MATCH (n:ExtractorHeartbeat) DETACH DELETE n;

// Optional: delete extractor-source IngestRun records
MATCH (r:IngestRun) WHERE r.source STARTS WITH 'extractor.' DETACH DELETE r;
```

### 3. Rebuild palace-mcp container

```bash
# On iMac:
cd /Users/Shared/Ios/Gimle-Palace
git pull origin develop
docker compose --profile review up -d --build palace-mcp
docker compose --profile review logs palace-mcp --tail 50
# Verify ensure_schema runs cleanly; no ensure_extractors_schema log entries.
```

### 4. Smoke test

From Claude Code:
```
palace.memory.health()
```
Expected: response matches pre-migration shape (no extractor-related fields, if any).

## Post-rollback

- Record in `project_backlog.md`: slice rolled back with reason + pre/post SHAs.
- Investigate root cause; open followup slice to re-attempt with fix.
- Do not re-apply before root cause confirmed.

## Time budget

Steps 1-4: ~15-20 min total.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/runbooks/2026-04-20-GIM-59-extractor-framework-rollback.md
git commit -m "docs: CLAUDE.md Extractors section + GIM-59 rollback runbook"
git push origin feature/GIM-59-extractor-framework-substrate
```

- [ ] **Step 4: Handoff to CR for Phase 3.1**

Post paperclip comment:
```
## Phase 2 complete (all tasks 2.1-2.12)

Code + tests + docs + rollback runbook on feature/GIM-59-extractor-framework-substrate.

@CodeReviewer your turn — Phase 3.1 mechanical review.
```

Reassign to CR.

---

## Phase 3 — Review

### Task 3.1: CR mechanical review + GitHub review bridge

**Owner:** CodeReviewer

- [ ] **Step 1: Fetch + checkout**

```bash
git fetch origin --prune
git switch feature/GIM-59-extractor-framework-substrate
git pull --ff-only
```

- [ ] **Step 2: Run full gate**

```bash
cd services/palace-mcp
uv run ruff check src/ tests/ 2>&1 | tee /tmp/cr-ruff.txt
uv run ruff format --check src/ tests/ 2>&1 | tee /tmp/cr-format.txt
uv run mypy --strict src/ 2>&1 | tee /tmp/cr-mypy.txt
uv run pytest tests/ -v 2>&1 | tee /tmp/cr-pytest.txt
```

- [ ] **Step 3: Paste outputs + compliance table in paperclip comment**

Use format from `feedback_anti_rubber_stamp.md`. Compliance table maps spec §9 (16 items) to actual Phase 2 commits.

- [ ] **Step 4: `gh pr review --approve` on GitHub PR**

```bash
PR_NUM=28
gh pr review $PR_NUM --approve --body "Phase 3.1 mechanical APPROVE — see paperclip comment <ID>.

- ruff check: green
- ruff format --check: green
- mypy --strict: green
- pytest: <N> passed, <M> skipped in <T>s

Full output pasted in paperclip comment. This GitHub review satisfies
branch-protection 'Require PR reviews' rule."
```

- [ ] **Step 5: Reassign to Opus**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"8d6649e2-2df6-412a-a6bc-2d94bab3b73f"}' \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

### Task 3.2: Opus adversarial

**Owner:** OpusArchitectReviewer

Adversarial checklist per spec §11 Phase 3.2:

- [ ] **Step 1: Runner lifecycle edge cases**
  - Session leak if Neo4j driver raises mid-lifecycle (unclosed session context)?
  - Partial finalize if process crashes between _execute and _finalize?
  - What happens if `asyncio.wait_for` timeout fires while extract() is in the middle of a Neo4j write? (Check: the write is atomic at Neo4j level; the pending transaction is rolled back on session close.)

- [ ] **Step 2: Neo4j property drift**
  - New nullable fields on `:IngestRun` (nodes_written, edges_written) — verify all existing consumers still parse.
  - `memory/health.py:46` — does it fail if `nodes_written` appears on the row it reads?
  - Task 2.10a regression test covers this; review its assertions.

- [ ] **Step 3: Schema bootstrap crash semantics**
  - What if `ensure_extractors_schema` runs before neo4j container is reachable? Current code will raise; palace-mcp lifespan fails; container restart-loops.
  - Is this the right behavior? (Yes — fail-loud per spec §10 Risk 6.)

- [ ] **Step 4: Exception hierarchy coverage**
  - Does runner catch `neo4j.exceptions.ServiceUnavailable` / `ClientError`?
  - Currently caught by generic `except Exception:` → `error_code="unknown"`.
  - Is that acceptable? (Yes for MVP; refinement is followup.)

- [ ] **Step 5: Context7 verification**
  - Check FastMCP async patterns — no regressions vs existing palace.* tools.
  - Verify Pydantic v2 `model_dump()` usage is canonical.

- [ ] **Step 6: Post adversarial review comment**

Structure:
```
## Phase 3.2 adversarial review

### NUDGEs (non-blocking)
1. ...
2. ...

### No CRITICAL findings / (or list if any).

APPROVE / request-changes.

@QAEngineer your turn — Phase 4.1 live smoke.
```

- [ ] **Step 7: Reassign to QAEngineer**

```bash
curl -sS -X PATCH -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assigneeAgentId":"58b68640-1e83-4d5d-978b-51a5ca9080e0"}' \
  "$PAPERCLIP_API_URL/api/issues/<issue-id>"
```

---

## Phase 4 — QA + Merge

### Task 4.1: QAEngineer live smoke

**Owner:** QAEngineer

Reproduces spec §2 success criteria 1-7 live on iMac.

- [ ] **Step 1: Pull feature branch on iMac + rebuild**

```bash
ssh imac-ssh.ant013.work
cd /Users/Shared/Ios/Gimle-Palace
git fetch origin
git switch feature/GIM-59-extractor-framework-substrate
git pull --ff-only
docker compose --profile review up -d --build palace-mcp
docker compose --profile review logs palace-mcp --tail 30
# Expected: lifespan logs show ensure_schema + ensure_extractors_schema
```

- [ ] **Step 2: Scenario 1 — list_extractors**

From Claude Code (tunneled to palace-mcp :8080):
```
palace.ingest.list_extractors()
```
Expected: `{"ok": true, "extractors": [{"name": "heartbeat", "description": "..."}]}`

Record response.

- [ ] **Step 3: Scenario 2 — run_extractor happy path**

```
palace.ingest.run_extractor(name="heartbeat", project="gimle")
```
Expected:
```json
{"ok": true, "run_id": "<uuid>", "extractor": "heartbeat",
 "project": "gimle", "duration_ms": <small>,
 "nodes_written": 1, "edges_written": 0, "success": true}
```

Record `run_id`.

- [ ] **Step 4: Scenario 3 — Neo4j persist invariants**

```bash
docker compose --profile review exec neo4j cypher-shell \
  -u neo4j -p <NEO4J_PASSWORD> << 'EOF'
MATCH (h:ExtractorHeartbeat {run_id: '<uuid from step 3>'}) RETURN h;
MATCH (r:IngestRun {id: '<same uuid>'}) RETURN r.source, r.success, r.nodes_written, r.duration_ms;
EOF
```

Expected:
- `:ExtractorHeartbeat` node with `run_id`, `ts`, `extractor: "heartbeat"`, `group_id: "project/gimle"`.
- `:IngestRun` with `source: "extractor.heartbeat"`, `success: true`, `nodes_written: 1`, `duration_ms` matching.

- [ ] **Step 5: Scenario 4 — error: unknown extractor**

```
palace.ingest.run_extractor(name="nonexistent", project="gimle")
```
Expected: `{"ok": false, "error_code": "unknown_extractor", ...}`.

- [ ] **Step 6: Scenario 5 — error: invalid slug**

```
palace.ingest.run_extractor(name="heartbeat", project="../etc")
```
Expected: `{"ok": false, "error_code": "invalid_slug", ...}`.

- [ ] **Step 7: Scenario 6 — error: unregistered project / repo not mounted**

```
palace.ingest.run_extractor(name="heartbeat", project="medic")
```
(Assuming medic is not registered OR /repos/medic not mounted.) Expected: `{"ok": false, "error_code": "project_not_registered" | "repo_not_mounted"}`.

- [ ] **Step 8: Scenario 7 — re-run creates separate records**

```
palace.ingest.run_extractor(name="heartbeat", project="gimle")
```
Different `run_id` from step 3. Then:

```cypher
MATCH (h:ExtractorHeartbeat) RETURN count(h);
```
Expected: count ≥ 2 (one from step 3, one from step 8).

- [ ] **Step 9: Fill PR body with QA Evidence section**

```bash
gh pr view 28 --json body --jq '.body' > /tmp/pr-body-current.md
```

Edit to include:
```markdown
## QA Evidence

Commit: <latest sha on feature branch>
iMac deploy: `docker compose --profile review up -d --build palace-mcp` @ <timestamp>

### Scenarios
- S1 list_extractors: 1 extractor ("heartbeat") returned. ✅
- S2 run_extractor(heartbeat, gimle): run_id=`<uuid>`, nodes_written=1, duration_ms=<n>. ✅
- S3 Cypher invariants: :ExtractorHeartbeat persisted with correct fields; :IngestRun finalized with source="extractor.heartbeat", success=true. ✅
- S4 unknown_extractor → correct error envelope. ✅
- S5 invalid_slug → correct error envelope. ✅
- S6 project_not_registered / repo_not_mounted → correct error envelope. ✅
- S7 re-run: distinct run_ids, 2 heartbeat nodes, 2 IngestRun records. ✅

All 5 required CI checks green (lint, typecheck, test, docker-build, qa-evidence-present).
```

```bash
gh pr edit 28 --body-file /tmp/pr-body-updated.md
```

- [ ] **Step 10: Post Phase 4.1 PASS comment**

```
## Phase 4.1 QA PASS

Evidence posted in PR #28 body. All 7 scenarios green. Neo4j invariants verified via cypher-shell.

@CTO your turn — Phase 4.2 squash-merge.
```

Reassign to CTO.

### Task 4.2: CTO squash-merge

**Owner:** CTO

- [ ] **Step 1: Verify all 5 CI checks green on PR 28**

```bash
gh pr checks 28 --required
# Expected: all 5 pass (lint, typecheck, test, docker-build, qa-evidence-present)
```

- [ ] **Step 2: Verify CR review present**

```bash
gh pr view 28 --json reviews -q '.reviews[] | select(.state == "APPROVED") | {login: .author.login}'
# Expected: at least 1 approving review
```

- [ ] **Step 3: Squash-merge**

```bash
gh pr merge 28 --squash --delete-branch \
  --subject "feat(palace-mcp): extractor framework substrate (GIM-59)"
```

- [ ] **Step 4: Verify merge landed**

```bash
git fetch origin
git log origin/develop -2 --oneline
# Expected: top commit is the GIM-59 squash
```

- [ ] **Step 5: Close issue with final comment**

```
## GIM-59 closed

- Squash-commit: <sha> on develop
- Feature branch deleted
- All 5 CI checks green at merge
- QA Phase 4.1 evidence attached to PR

Next recommended slice: N+2b — Git History Harvester (extractor #22) uses this framework.
```

---

## Post-merge operator tasks (Board, not paperclip)

- [ ] **Step 1: iMac deploy**

```bash
ssh imac-ssh.ant013.work
cd /Users/Shared/Ios/Gimle-Palace
git switch develop
git pull origin develop
docker compose --profile review up -d --build palace-mcp
docker compose --profile review logs palace-mcp --tail 30
```

Verify lifespan logs show `extractors.schema.applied` with `statement_count: 3` (heartbeat's 1 constraint + 2 indexes).

- [ ] **Step 2: Update memory**

- `project_backlog.md` — mark GIM-59 closed with SHA + duration.
- Add `reference_extractor_framework.md` if non-obvious invariants surfaced during QA.
- Update `MEMORY.md` index.

- [ ] **Step 3: Unblock N+2b (Git History Harvester) brainstorm when ready.**

---

## Self-review (run at plan completion, fix inline)

### Spec §9 coverage

| # | §9 criterion | Task |
|---|---|---|
| 1 | 8 files in extractors/ | 2.1 + 2.2 + 2.3 + 2.4 + 2.5 + 2.6 + 2.7 + 2.8 |
| 2 | BaseExtractor ABC + ClassVars + abstract extract | 2.2 |
| 3 | ExtractionContext frozen dataclass | 2.2 |
| 4 | ExtractorStats frozen dataclass | 2.2 |
| 5 | Error hierarchy | 2.2 |
| 6 | Registry with register/get/list_all + heartbeat pre-registered | 2.4 + 2.8 Step 5 |
| 7 | Runner full lifecycle + 8 error_codes | 2.6 |
| 8 | ensure_extractors_schema + lifespan wiring | 2.7 + 2.9 Step 1 |
| 9 | HeartbeatExtractor shipped | 2.8 |
| 10 | Pydantic response models | 2.3 |
| 11 | 2 MCP tools registered | 2.9 Step 2 |
| 12 | Cypher statements in extractors/cypher.py | 2.5 |
| 13 | QA Phase 4.1 evidence in PR body | 4.1 |
| 14 | mypy --strict + ruff clean | across all Phase 2 + 3.1 gate |
| 15 | Unit + integration tests per §7 | 2.2, 2.3, 2.4, 2.6, 2.7, 2.8, 2.9, 2.10a |
| 16 | CLAUDE.md Extractors section + rollback runbook | 2.12 |

All 16 mapped. No gaps.

### Placeholder scan

- No `TBD` / `TODO` / "similar to Task X" / "fill in".
- `<issue-id>` is a legitimate runtime variable (paperclip issue UUID), resolved by CTO at Phase 1.1.
- `<HEAD sha>` is a runtime value resolved during Phase 1.1 Step 3 comment composition.
- `<uuid from step 3>` / `<latest sha>` in Phase 4 — runtime values resolved by QA.

### Type consistency

- `ExtractionContext` fields match between `base.py` (Task 2.2) and `runner.py` (Task 2.6): driver, project_slug, group_id, repo_path, run_id, logger.
- `ExtractorStats` fields: nodes_written, edges_written — same signature across all tasks.
- Error response fields: `ok, error_code, message, extractor, project, run_id` — consistent in schemas.py (2.3) and runner.py (2.6).
- `:IngestRun` schema: fields (`id, source, group_id, started_at, finished_at, duration_ms, nodes_written, edges_written, errors, success`) consistent between cypher.py (2.5) and Cypher in test 2.10a.
- MCP tool names: `palace.ingest.run_extractor` + `palace.ingest.list_extractors` consistent across spec §4, plan §2.9, QA §4.1.

No type/name drift found.

---

## Size estimate

- Production code: ~450 LOC across 8 files.
- Tests: ~60 tests (30 unit + 20 integration + 10 error-path), ~800 LOC.
- Docs (CLAUDE.md section + rollback runbook): ~120 LOC.
- Plan (this file): ~1600 LOC.
- 1 PR on `feature/GIM-59-extractor-framework-substrate`.
- **1-1.5 day agent-time** across 4 phases (per spec §12 revised estimate).
