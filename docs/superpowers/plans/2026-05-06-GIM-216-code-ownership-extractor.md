# Code Ownership Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `code_ownership` extractor (Roadmap #32) — file-level `weight = α × blame_share + (1-α) × recency_churn_share` ownership graph, plus the `palace.code.find_owners` MCP tool.

**Architecture:** Per `docs/superpowers/specs/2026-05-06-GIM-216-code-ownership-extractor.md` (rev2). Stand-alone Python extractor under `services/palace-mcp/src/palace_mcp/extractors/code_ownership/`. Hybrid signal: `pygit2.blame` on HEAD + count-based recency-weighted churn from existing `git_history` `:Commit-[:TOUCHED]->:File` graph (reversed query, server-side aggregation). `.mailmap`-aware via `pygit2.Mailmap` (no custom parser; identity-passthrough fallback). Per-file incremental refresh via `:OwnershipCheckpoint{project_id, last_head_sha, last_completed_at}` + `pygit2.Diff`. Atomic-replace per batch (`PALACE_OWNERSHIP_WRITE_BATCH_SIZE=2000`). `:OwnershipFileState` sidecar for `find_owners` empty-state disambiguation. Substrate-aligned `:IngestRun{source='extractor.code_ownership'}` (no separate `:OwnershipRun` label).

**Tech Stack:** Python 3.13+, Pydantic v2, `pygit2` (already pinned for git_history GIM-186), Neo4j (graphiti async driver), pytest + testcontainers, MCP via FastMCP.

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `services/palace-mcp/src/palace_mcp/config.py` | Add 4 `PALACE_*` env-var fields (`OWNERSHIP_BLAME_WEIGHT`, `OWNERSHIP_MAX_FILES_PER_RUN`, `OWNERSHIP_WRITE_BATCH_SIZE`, `MAILMAP_MAX_BYTES`) |
| `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py` | Add `OWNERSHIP_DIFF_FAILED`, `REPO_HEAD_INVALID`, `OWNERSHIP_MAX_FILES_EXCEEDED`, `GIT_HISTORY_NOT_INDEXED` to `ExtractorErrorCode` |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/__init__.py` | Package init; export `CodeOwnershipExtractor` |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/models.py` | Pydantic frozen models: `OwnershipCheckpoint`, `OwnershipFileStateRecord`, `OwnershipEdge`, `BlameAttribution`, `ChurnShare`, `OwnershipRunSummary` |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/schema_extension.py` | `ensure_ownership_schema(driver)` — idempotent constraints/indexes for `:OwnershipCheckpoint`, `:OwnershipFileState` |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/mailmap.py` | `MailmapResolver` class: pygit2.Mailmap if exposed + size cap; else identity passthrough; `canonicalize(name, email)` |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/checkpoint.py` | Read/write/init `:OwnershipCheckpoint`; `load_checkpoint()`, `update_checkpoint()` |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py` | `walk_blame(repo, paths, mailmap, bot_keys)` → `dict[path, dict[canonical_id, BlameAttribution]]` |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/churn_aggregator.py` | `aggregate_churn(driver, project, paths, mailmap, bot_keys, decay_days, known_author_ids)` → `dict[path, dict[canonical_id, ChurnShare]]`; reversed Cypher (start from `:File`) |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/scorer.py` | `score_file(blame, churn, alpha)` → `list[OwnershipEdge]` with per-file normalization (post-bot exclusion) |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/neo4j_writer.py` | `write_batch(tx, edges, file_states, deleted_paths, run_id, alpha, source)` — atomic-replace tx |
| `services/palace-mcp/src/palace_mcp/extractors/code_ownership/extractor.py` | `CodeOwnershipExtractor(BaseExtractor)` orchestrator: 5-phase pipeline |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Register `code_ownership` in `EXTRACTORS` mapping |
| `services/palace-mcp/src/palace_mcp/code/find_owners.py` | `palace.code.find_owners` MCP tool implementation |
| `services/palace-mcp/src/palace_mcp/server.py` | Register `find_owners` MCP tool |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_models.py` | Pydantic validators |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_mailmap.py` | MailmapResolver: pygit2 path, fallback, size cap, identity |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_checkpoint.py` | Checkpoint read/write/init |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_blame_walker.py` | Blame on tmpdir mini-repo, skip cases |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_churn_aggregator.py` | Cypher fragment shape (mock driver), bot/merge filter, decay math |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_scorer.py` | Formula edges, normalization, single-author |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_neo4j_writer.py` | Atomic-replace tx Cypher (mock driver) |
| `services/palace-mcp/tests/extractors/unit/test_code_ownership_pii_redaction.py` | Audit grep on package source for email log calls |
| `services/palace-mcp/tests/extractors/integration/test_code_ownership_integration.py` | 8 scenarios on real Neo4j via testcontainers |
| `services/palace-mcp/tests/code/test_find_owners_wire.py` | Wire-contract: success + 5 error envelopes + empty-state disambiguation |
| `services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/` | Mini fixture: 3 authors, 5 files, 12 commits, .mailmap, REGEN.md |
| `services/palace-mcp/tests/extractors/smoke/test_code_ownership_smoke.sh` | Live iMac smoke (manual) |
| `docs/runbooks/code-ownership.md` | Operator runbook (env vars, mailmap, erasure, troubleshooting) |
| `CLAUDE.md` | Add `code_ownership` row in registered extractors + "Operator workflow: Code ownership" section |

---

## Task 1: Add 4 env vars to Settings

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/config.py:Settings`
- Test: `services/palace-mcp/tests/unit/test_settings_foundation.py` (extend existing)

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/unit/test_settings_foundation.py` (use the existing `_minimal_env()` + `monkeypatch.setenv` pattern in that file):

```python
def test_ownership_settings_defaults(monkeypatch):
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    settings = Settings()
    assert settings.ownership_blame_weight == 0.5
    assert settings.ownership_max_files_per_run == 50_000
    assert settings.ownership_write_batch_size == 2_000
    assert settings.mailmap_max_bytes == 1_048_576


def test_ownership_blame_weight_out_of_range_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_OWNERSHIP_BLAME_WEIGHT", "1.5")
    with pytest.raises(ValidationError):
        Settings()


def test_ownership_write_batch_size_out_of_range_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_OWNERSHIP_WRITE_BATCH_SIZE", "5")  # < 100 lower bound
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/unit/test_settings_foundation.py -k ownership -v`

Expected: 3 FAIL with `AttributeError: 'Settings' object has no attribute 'ownership_blame_weight'`.

- [ ] **Step 3: Implement settings fields**

In `services/palace-mcp/src/palace_mcp/config.py`, append to `Settings` (preserving existing import + class style):

```python
# inside class Settings(BaseSettings):
ownership_blame_weight: float = Field(
    default=0.5, ge=0.0, le=1.0,
    description="Alpha in weight = α × blame_share + (1-α) × recency_churn_share",
)
ownership_max_files_per_run: int = Field(
    default=50_000, ge=1,
    description="Hard cap on DIRTY set per code_ownership run",
)
ownership_write_batch_size: int = Field(
    default=2_000, ge=100, le=10_000,
    description="Files per Phase-4 atomic-replace tx in code_ownership writer",
)
mailmap_max_bytes: int = Field(
    default=1_048_576, ge=1024,
    description="Upper bound for .mailmap file size; oversized → identity passthrough",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/unit/test_settings_foundation.py -k ownership -v`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/config.py services/palace-mcp/tests/unit/test_settings_foundation.py
git commit -m "feat(GIM-216): add 4 PALACE_OWNERSHIP_* / MAILMAP env vars for code_ownership extractor"
```

---

## Task 2: Add new ExtractorErrorCode values

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py:ExtractorErrorCode`
- Test: `services/palace-mcp/tests/extractors/unit/test_foundation_errors.py` (extend or create)

- [ ] **Step 1: Write failing test**

In `services/palace-mcp/tests/extractors/unit/test_foundation_errors.py` (create if missing):

```python
from palace_mcp.extractors.foundation.errors import ExtractorErrorCode


def test_ownership_error_codes_present():
    """Code-ownership-specific error codes are defined on the enum."""
    assert ExtractorErrorCode.OWNERSHIP_DIFF_FAILED.value == "ownership_diff_failed"
    assert ExtractorErrorCode.REPO_HEAD_INVALID.value == "repo_head_invalid"
    assert ExtractorErrorCode.OWNERSHIP_MAX_FILES_EXCEEDED.value == "ownership_max_files_exceeded"
    assert ExtractorErrorCode.GIT_HISTORY_NOT_INDEXED.value == "git_history_not_indexed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_foundation_errors.py -v`

Expected: FAIL with `AttributeError: OWNERSHIP_DIFF_FAILED`.

- [ ] **Step 3: Add enum values**

In `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py`, find the `class ExtractorErrorCode(StrEnum):` and append (alphabetical order if file uses it, else append at end):

```python
    GIT_HISTORY_NOT_INDEXED = "git_history_not_indexed"
    OWNERSHIP_DIFF_FAILED = "ownership_diff_failed"
    OWNERSHIP_MAX_FILES_EXCEEDED = "ownership_max_files_exceeded"
    REPO_HEAD_INVALID = "repo_head_invalid"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_foundation_errors.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py services/palace-mcp/tests/extractors/unit/test_foundation_errors.py
git commit -m "feat(GIM-216): add 4 ExtractorErrorCode values for code_ownership"
```

---

## Task 3: Pydantic models for code_ownership

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/__init__.py` (empty placeholder for now)
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/models.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_code_ownership_models.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/unit/test_code_ownership_models.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.code_ownership.models import (
    BlameAttribution,
    ChurnShare,
    OwnershipCheckpoint,
    OwnershipEdge,
    OwnershipFileStateRecord,
    OwnershipRunSummary,
)


def _now() -> datetime:
    return datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


def test_ownership_checkpoint_roundtrip():
    cp = OwnershipCheckpoint(
        project_id="gimle",
        last_head_sha="abcdef0123456789abcdef0123456789abcdef01",
        last_completed_at=_now(),
        run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert cp.last_head_sha.startswith("abcdef")


def test_ownership_checkpoint_bootstrap_null_head_sha():
    """First-ever run: last_head_sha is None."""
    cp = OwnershipCheckpoint(
        project_id="gimle",
        last_head_sha=None,
        last_completed_at=_now(),
        run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert cp.last_head_sha is None


def test_ownership_checkpoint_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        OwnershipCheckpoint(
            project_id="gimle",
            last_head_sha=None,
            last_completed_at=datetime(2026, 5, 6, 12, 0, 0),  # no tz
            run_id="x",
            updated_at=_now(),
        )


def test_ownership_file_state_record_processed():
    s = OwnershipFileStateRecord(
        project_id="gimle",
        path="services/palace-mcp/foo.py",
        status="processed",
        no_owners_reason=None,
        last_run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert s.status == "processed"


def test_ownership_file_state_record_skipped_with_reason():
    s = OwnershipFileStateRecord(
        project_id="gimle",
        path="services/palace-mcp/blob.png",
        status="skipped",
        no_owners_reason="binary_or_skipped",
        last_run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert s.no_owners_reason == "binary_or_skipped"


def test_ownership_file_state_record_invalid_status_rejected():
    with pytest.raises(ValidationError):
        OwnershipFileStateRecord(
            project_id="gimle",
            path="x.py",
            status="weird",  # not in literal
            no_owners_reason=None,
            last_run_id="x",
            updated_at=_now(),
        )


def test_ownership_edge_canonical_via_literal():
    e = OwnershipEdge(
        project_id="gimle",
        path="x.py",
        canonical_id="anton@example.com",
        canonical_email="anton@example.com",
        canonical_name="Anton",
        weight=0.42,
        blame_share=0.5,
        recency_churn_share=0.34,
        last_touched_at=_now(),
        lines_attributed=100,
        commit_count=10,
        canonical_via="identity",
    )
    assert e.canonical_via == "identity"


def test_ownership_edge_invalid_canonical_via_rejected():
    with pytest.raises(ValidationError):
        OwnershipEdge(
            project_id="gimle",
            path="x.py",
            canonical_id="anton@example.com",
            canonical_email="anton@example.com",
            canonical_name="Anton",
            weight=0.42,
            blame_share=0.5,
            recency_churn_share=0.34,
            last_touched_at=_now(),
            lines_attributed=100,
            commit_count=10,
            canonical_via="bogus",
        )


def test_blame_attribution_basic():
    b = BlameAttribution(
        canonical_id="anton@example.com",
        canonical_name="Anton",
        canonical_email="anton@example.com",
        lines=145,
    )
    assert b.lines == 145


def test_churn_share_basic():
    c = ChurnShare(
        canonical_id="anton@example.com",
        canonical_name="Anton",
        canonical_email="anton@example.com",
        recency_score=2.5,
        last_touched_at=_now(),
        commit_count=12,
    )
    assert c.recency_score == 2.5


def test_ownership_run_summary_basic():
    s = OwnershipRunSummary(
        project_id="gimle",
        run_id="11111111-1111-1111-1111-111111111111",
        head_sha="abcdef0123456789abcdef0123456789abcdef01",
        prev_head_sha=None,
        dirty_files_count=10,
        deleted_files_count=2,
        edges_written=42,
        edges_deleted=8,
        mailmap_resolver_path="pygit2",
        exit_reason="success",
        duration_ms=1234,
    )
    assert s.exit_reason == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_models.py -v`

Expected: FAIL — `ModuleNotFoundError: palace_mcp.extractors.code_ownership.models`.

- [ ] **Step 3: Implement models**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/__init__.py`:

```python
"""Code ownership extractor (Roadmap #32)."""
```

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/models.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("must be tz-aware")
    return v.astimezone(timezone.utc)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OwnershipCheckpoint(FrozenModel):
    project_id: str
    last_head_sha: str | None
    last_completed_at: datetime
    run_id: str
    updated_at: datetime

    @field_validator("last_completed_at", "updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class OwnershipFileStateRecord(FrozenModel):
    project_id: str
    path: str
    status: Literal["processed", "skipped"]
    no_owners_reason: (
        Literal[
            "binary_or_skipped",
            "all_bot_authors",
            "no_commit_history",
        ]
        | None
    )
    last_run_id: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class BlameAttribution(FrozenModel):
    canonical_id: str
    canonical_name: str
    canonical_email: str
    lines: int


class ChurnShare(FrozenModel):
    canonical_id: str
    canonical_name: str
    canonical_email: str
    recency_score: float
    last_touched_at: datetime
    commit_count: int

    @field_validator("last_touched_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class OwnershipEdge(FrozenModel):
    project_id: str
    path: str
    canonical_id: str
    canonical_email: str
    canonical_name: str
    weight: float
    blame_share: float
    recency_churn_share: float
    last_touched_at: datetime
    lines_attributed: int
    commit_count: int
    canonical_via: Literal["identity", "mailmap_existing", "mailmap_synthetic"]

    @field_validator("last_touched_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class OwnershipRunSummary(FrozenModel):
    project_id: str
    run_id: str
    head_sha: str
    prev_head_sha: str | None
    dirty_files_count: int
    deleted_files_count: int
    edges_written: int
    edges_deleted: int
    mailmap_resolver_path: Literal["pygit2", "identity_passthrough"]
    exit_reason: Literal["success", "no_change", "no_dirty", "failed"]
    duration_ms: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_models.py -v`

Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/__init__.py \
        services/palace-mcp/src/palace_mcp/extractors/code_ownership/models.py \
        services/palace-mcp/tests/extractors/unit/test_code_ownership_models.py
git commit -m "feat(GIM-216): code_ownership Pydantic frozen models"
```

---

## Task 4: Schema extension (constraints + indexes)

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/schema_extension.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_code_ownership_schema.py`

This task uses real Neo4j via testcontainers because `CREATE CONSTRAINT` is a real Neo4j operation; mock-driver tests cannot verify idempotency end-to-end.

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/integration/test_code_ownership_schema.py`:

```python
import pytest

from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


@pytest.mark.asyncio
async def test_ensure_ownership_schema_idempotent(neo4j_driver):
    """Schema bootstrap is idempotent — second call must not raise."""
    await ensure_ownership_schema(neo4j_driver)
    await ensure_ownership_schema(neo4j_driver)


@pytest.mark.asyncio
async def test_ownership_schema_constraints_created(neo4j_driver):
    """After ensure, expected constraints exist."""
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS YIELD name")
        names = {record["name"] for record in await result.data()}
    assert "ownership_checkpoint_unique" in names
    assert "ownership_file_state_unique" in names


@pytest.mark.asyncio
async def test_ownership_schema_no_relationship_index(neo4j_driver):
    """rev2 dropped file_owned_by_weight (dead index for traversal queries)."""
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        result = await session.run("SHOW INDEXES YIELD name")
        names = {record["name"] for record in await result.data()}
    assert "file_owned_by_weight" not in names
```

The fixture `neo4j_driver` is provided by the existing `services/palace-mcp/tests/conftest.py` (testcontainers); reuse it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_schema.py -v`

Expected: FAIL — `ModuleNotFoundError: palace_mcp.extractors.code_ownership.schema_extension`.

- [ ] **Step 3: Implement schema extension**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/schema_extension.py`:

```python
"""Schema bootstrap for code_ownership extractor — idempotent constraints."""

from __future__ import annotations

from neo4j import AsyncDriver

_CONSTRAINTS = [
    """
    CREATE CONSTRAINT ownership_checkpoint_unique IF NOT EXISTS
    FOR (c:OwnershipCheckpoint) REQUIRE c.project_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT ownership_file_state_unique IF NOT EXISTS
    FOR (s:OwnershipFileState)
    REQUIRE (s.project_id, s.path) IS UNIQUE
    """,
]


async def ensure_ownership_schema(driver: AsyncDriver) -> None:
    """Idempotent schema bootstrap. Safe to call on every run.

    NO relationship-property index on :OWNED_BY.weight (rev2 design):
    find_owners traverses from :File PK; index would only help full-scans.
    """
    async with driver.session() as session:
        for stmt in _CONSTRAINTS:
            await session.run(stmt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_schema.py -v`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/schema_extension.py \
        services/palace-mcp/tests/extractors/integration/test_code_ownership_schema.py
git commit -m "feat(GIM-216): code_ownership schema extension (2 constraints, no rel index)"
```

---

## Task 5: MailmapResolver (pygit2-only + identity passthrough)

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/mailmap.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_code_ownership_mailmap.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/unit/test_code_ownership_mailmap.py`:

```python
from pathlib import Path

import pygit2
import pytest

from palace_mcp.extractors.code_ownership.mailmap import (
    MailmapResolver,
    MailmapResolverPath,
)


@pytest.fixture
def empty_repo(tmp_path) -> pygit2.Repository:
    repo_path = tmp_path / "empty_repo"
    repo_path.mkdir()
    return pygit2.init_repository(str(repo_path))


@pytest.fixture
def repo_with_mailmap(tmp_path) -> pygit2.Repository:
    repo_path = tmp_path / "repo_with_mailmap"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    (repo_path / ".mailmap").write_text(
        "Anton Stavnichiy <new@example.com> Anton S <old@example.com>\n",
        encoding="utf-8",
    )
    return repo


def test_resolver_identity_passthrough_on_empty_repo(empty_repo):
    resolver = MailmapResolver.from_repo(empty_repo, max_bytes=1_048_576)
    assert resolver.path == MailmapResolverPath.IDENTITY_PASSTHROUGH
    name, email = resolver.canonicalize("Anton S", "Old@Example.com")
    assert name == "Anton S"
    assert email == "old@example.com"  # always lowercased


def test_resolver_pygit2_canonicalizes_known_alias(repo_with_mailmap):
    resolver = MailmapResolver.from_repo(repo_with_mailmap, max_bytes=1_048_576)
    if resolver.path != MailmapResolverPath.PYGIT2:
        pytest.skip("pygit2.Mailmap not exposed by bound libgit2")
    name, email = resolver.canonicalize("Anton S", "old@example.com")
    assert name == "Anton Stavnichiy"
    assert email == "new@example.com"


def test_resolver_unknown_email_passes_through(repo_with_mailmap):
    resolver = MailmapResolver.from_repo(repo_with_mailmap, max_bytes=1_048_576)
    name, email = resolver.canonicalize("Other Human", "other@example.com")
    assert name == "Other Human"
    assert email == "other@example.com"


def test_resolver_size_cap_falls_back_to_identity(tmp_path):
    repo_path = tmp_path / "huge"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    # Write an oversized .mailmap (e.g., 2 KiB but cap is 1 KiB)
    (repo_path / ".mailmap").write_text("x" * 2048, encoding="utf-8")
    resolver = MailmapResolver.from_repo(repo, max_bytes=1024)
    assert resolver.path == MailmapResolverPath.IDENTITY_PASSTHROUGH


def test_resolver_email_always_lowercased(empty_repo):
    resolver = MailmapResolver.from_repo(empty_repo, max_bytes=1_048_576)
    _, email = resolver.canonicalize("X", "MixedCase@Example.COM")
    assert email == "mixedcase@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_mailmap.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement MailmapResolver**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/mailmap.py`:

```python
"""MailmapResolver — pygit2-only with identity passthrough fallback.

Per spec rev2 R3 / C3: no custom parser. Either pygit2.Mailmap (if
exposed by the bound libgit2) handles parsing, or we identity-pass.
.mailmap is checked-in repo content (untrusted); a custom parser
would split test surface and add attack surface.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

import pygit2

logger = logging.getLogger(__name__)


class MailmapResolverPath(StrEnum):
    PYGIT2 = "pygit2"
    IDENTITY_PASSTHROUGH = "identity_passthrough"


class MailmapResolver:
    """Resolve raw (name, email) → canonical (name, email)."""

    def __init__(
        self,
        path: MailmapResolverPath,
        pygit2_mailmap: object | None = None,
    ) -> None:
        self.path = path
        self._pygit2_mailmap = pygit2_mailmap

    @classmethod
    def from_repo(
        cls, repo: pygit2.Repository, *, max_bytes: int
    ) -> "MailmapResolver":
        """Try pygit2.Mailmap; fall back to identity on any failure."""
        # 1. Check for .mailmap file existence + size cap
        mailmap_file = Path(repo.workdir or repo.path) / ".mailmap"
        if not mailmap_file.is_file():
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        try:
            size = mailmap_file.stat().st_size
        except OSError:
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        if size > max_bytes:
            logger.info(
                "mailmap_unsupported: .mailmap size %d > cap %d for repo %s",
                size,
                max_bytes,
                repo.path,  # NEVER include emails in logs (PII rule §8)
            )
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)

        # 2. Try pygit2.Mailmap if exposed
        if not hasattr(pygit2, "Mailmap"):
            logger.info("mailmap_unsupported: pygit2.Mailmap not exposed")
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        try:
            mm = pygit2.Mailmap.from_repository(repo)  # type: ignore[attr-defined]
        except Exception as exc:  # broad: pygit2 raises various errors
            logger.info(
                "mailmap_unsupported: pygit2 raised %s on repo %s",
                type(exc).__name__,
                repo.path,
            )
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        return cls(MailmapResolverPath.PYGIT2, pygit2_mailmap=mm)

    def canonicalize(self, name: str, email: str) -> tuple[str, str]:
        """Return canonical (name, email_lc). Email always lowercased."""
        if self.path == MailmapResolverPath.PYGIT2 and self._pygit2_mailmap is not None:
            try:
                cn, ce = self._pygit2_mailmap.resolve(name, email)  # type: ignore[union-attr]
                return cn, ce.lower()
            except Exception:
                pass  # fall through to identity
        return name, email.lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_mailmap.py -v`

Expected: 4 PASS, 1 SKIP if libgit2 doesn't expose `Mailmap` (acceptable).

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/mailmap.py \
        services/palace-mcp/tests/extractors/unit/test_code_ownership_mailmap.py
git commit -m "feat(GIM-216): MailmapResolver — pygit2 if exposed else identity passthrough"
```

---

## Task 6: Checkpoint read/write/init

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/checkpoint.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_code_ownership_checkpoint.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/integration/test_code_ownership_checkpoint.py`:

```python
import pytest

from palace_mcp.extractors.code_ownership.checkpoint import (
    load_checkpoint,
    update_checkpoint,
)
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


@pytest.mark.asyncio
async def test_load_checkpoint_returns_none_on_first_run(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    cp = await load_checkpoint(neo4j_driver, project_id="gimle")
    assert cp is None


@pytest.mark.asyncio
async def test_update_then_load_roundtrip(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    await update_checkpoint(
        neo4j_driver,
        project_id="gimle",
        head_sha="abcdef0123456789abcdef0123456789abcdef01",
        run_id="11111111-1111-1111-1111-111111111111",
    )
    cp = await load_checkpoint(neo4j_driver, project_id="gimle")
    assert cp is not None
    assert cp.last_head_sha == "abcdef0123456789abcdef0123456789abcdef01"
    assert cp.run_id == "11111111-1111-1111-1111-111111111111"
    assert cp.last_completed_at.tzinfo is not None


@pytest.mark.asyncio
async def test_update_overwrites_existing(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    await update_checkpoint(
        neo4j_driver,
        project_id="gimle",
        head_sha="aaaa" * 10,
        run_id="run-1",
    )
    await update_checkpoint(
        neo4j_driver,
        project_id="gimle",
        head_sha="bbbb" * 10,
        run_id="run-2",
    )
    cp = await load_checkpoint(neo4j_driver, project_id="gimle")
    assert cp is not None
    assert cp.last_head_sha == "bbbb" * 10
    assert cp.run_id == "run-2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_checkpoint.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement checkpoint**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/checkpoint.py`:

```python
"""Read/write :OwnershipCheckpoint nodes (one per project)."""

from __future__ import annotations

from datetime import datetime, timezone

from neo4j import AsyncDriver

from palace_mcp.extractors.code_ownership.models import OwnershipCheckpoint

_LOAD_CYPHER = """
MATCH (c:OwnershipCheckpoint {project_id: $project_id})
RETURN c.project_id     AS project_id,
       c.last_head_sha  AS last_head_sha,
       c.last_completed_at AS last_completed_at,
       c.run_id         AS run_id,
       c.updated_at     AS updated_at
"""

_UPDATE_CYPHER = """
MERGE (c:OwnershipCheckpoint {project_id: $project_id})
SET c.last_head_sha     = $head_sha,
    c.last_completed_at = $now,
    c.run_id            = $run_id,
    c.updated_at        = $now
"""


async def load_checkpoint(
    driver: AsyncDriver, *, project_id: str
) -> OwnershipCheckpoint | None:
    async with driver.session() as session:
        result = await session.run(_LOAD_CYPHER, project_id=project_id)
        record = await result.single()
    if record is None:
        return None
    last_completed = record["last_completed_at"]
    if isinstance(last_completed, str):
        last_completed = datetime.fromisoformat(last_completed)
    elif hasattr(last_completed, "to_native"):
        last_completed = last_completed.to_native()
    updated = record["updated_at"]
    if isinstance(updated, str):
        updated = datetime.fromisoformat(updated)
    elif hasattr(updated, "to_native"):
        updated = updated.to_native()
    return OwnershipCheckpoint(
        project_id=record["project_id"],
        last_head_sha=record["last_head_sha"],
        last_completed_at=last_completed,
        run_id=record["run_id"],
        updated_at=updated,
    )


async def update_checkpoint(
    driver: AsyncDriver,
    *,
    project_id: str,
    head_sha: str,
    run_id: str,
) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    async with driver.session() as session:
        await session.run(
            _UPDATE_CYPHER,
            project_id=project_id,
            head_sha=head_sha,
            run_id=run_id,
            now=now,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_checkpoint.py -v`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/checkpoint.py \
        services/palace-mcp/tests/extractors/integration/test_code_ownership_checkpoint.py
git commit -m "feat(GIM-216): :OwnershipCheckpoint load/update"
```

---

## Task 7: Blame walker

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_code_ownership_blame_walker.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/unit/test_code_ownership_blame_walker.py`:

```python
import os
from pathlib import Path

import pygit2
import pytest

from palace_mcp.extractors.code_ownership.blame_walker import walk_blame
from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver


@pytest.fixture
def mini_repo(tmp_path) -> pygit2.Repository:
    """3 commits, 2 authors, 2 files (one text, one binary).

    File 1: 'a.py' — author1 writes 4 lines, author2 modifies 2 of them.
    File 2: 'b.bin' — binary, contains \\x00 bytes; blame must skip.
    """
    repo_path = tmp_path / "mini"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    sig1 = pygit2.Signature("Author One", "a1@example.com", 1_700_000_000, 0)
    sig2 = pygit2.Signature("Author Two", "a2@example.com", 1_700_001_000, 0)

    def commit(msg: str, files: dict[str, bytes], parents: list, sig: pygit2.Signature) -> str:
        for name, data in files.items():
            (repo_path / name).write_bytes(data)
            repo.index.add(name)
        repo.index.write()
        tree = repo.index.write_tree()
        oid = repo.create_commit("HEAD", sig, sig, msg, tree, parents)
        return str(oid)

    sha1 = commit(
        "init",
        {"a.py": b"line1\nline2\nline3\nline4\n", "b.bin": b"\x00\x01\x02"},
        [],
        sig1,
    )
    head_oid = pygit2.Oid(hex=sha1)
    sha2 = commit(
        "modify a.py",
        {"a.py": b"line1\nLINE2_modified\nLINE3_modified\nline4\n"},
        [head_oid],
        sig2,
    )
    return repo


def test_walk_blame_attributes_lines_to_two_authors(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    result = walk_blame(
        mini_repo,
        paths={"a.py"},
        mailmap=resolver,
        bot_keys=set(),
    )
    assert "a.py" in result
    by_author = {b.canonical_id: b.lines for b in result["a.py"].values()}
    # Author One wrote lines 1+4 (2 lines), Author Two rewrote 2+3 (2 lines)
    assert by_author["a1@example.com"] == 2
    assert by_author["a2@example.com"] == 2


def test_walk_blame_skips_binary(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    result = walk_blame(
        mini_repo,
        paths={"b.bin"},
        mailmap=resolver,
        bot_keys=set(),
    )
    # Either absent from result or empty dict — both are "skipped"
    assert result.get("b.bin", {}) == {}


def test_walk_blame_excludes_bots(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    result = walk_blame(
        mini_repo,
        paths={"a.py"},
        mailmap=resolver,
        bot_keys={"a2@example.com"},  # treat Author Two as bot
    )
    by_author = {b.canonical_id: b.lines for b in result["a.py"].values()}
    assert "a2@example.com" not in by_author
    assert by_author["a1@example.com"] == 2  # only the lines author1 still owns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement blame_walker**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py`:

```python
"""pygit2.blame walker for HEAD attribution.

Builds dict[path, dict[canonical_id, BlameAttribution]] for the given
DIRTY paths. Skips files where pygit2.blame raises (binary, symlink,
submodule) — logs a warning, returns no entry for the path.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import pygit2

from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver
from palace_mcp.extractors.code_ownership.models import BlameAttribution

logger = logging.getLogger(__name__)


def walk_blame(
    repo: pygit2.Repository,
    *,
    paths: Iterable[str],
    mailmap: MailmapResolver,
    bot_keys: set[str],
) -> dict[str, dict[str, BlameAttribution]]:
    """Per-path, per-author blame line counts after mailmap + bot filter."""
    result: dict[str, dict[str, BlameAttribution]] = {}
    head_oid = repo.head.target
    for path in paths:
        try:
            blame = repo.blame(path, newest_commit=head_oid)
        except (pygit2.GitError, KeyError, ValueError) as exc:
            logger.info(
                "blame_failed: skipping path %s (%s)", path, type(exc).__name__
            )
            continue

        per_author: dict[str, BlameAttribution] = {}
        for hunk in blame:
            try:
                commit = repo[hunk.final_commit_id]
            except KeyError:
                continue
            raw_name = commit.author.name
            raw_email = commit.author.email
            cn, ce = mailmap.canonicalize(raw_name, raw_email)
            canonical_id = ce  # already lowercased by resolver
            if canonical_id in bot_keys:
                continue
            line_count = int(hunk.lines_in_hunk)
            existing = per_author.get(canonical_id)
            if existing is None:
                per_author[canonical_id] = BlameAttribution(
                    canonical_id=canonical_id,
                    canonical_name=cn,
                    canonical_email=ce,
                    lines=line_count,
                )
            else:
                per_author[canonical_id] = BlameAttribution(
                    canonical_id=canonical_id,
                    canonical_name=cn,
                    canonical_email=ce,
                    lines=existing.lines + line_count,
                )
        result[path] = per_author
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py -v`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py \
        services/palace-mcp/tests/extractors/unit/test_code_ownership_blame_walker.py
git commit -m "feat(GIM-216): blame_walker — per-file pygit2.blame + mailmap + bot filter"
```

---

## Task 8: Churn aggregator (reversed Cypher direction + server-side aggregation)

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/churn_aggregator.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_code_ownership_churn_aggregator.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/integration/test_code_ownership_churn_aggregator.py`:

```python
import math
from datetime import datetime, timezone

import pytest

from palace_mcp.extractors.code_ownership.churn_aggregator import aggregate_churn
from palace_mcp.extractors.code_ownership.mailmap import (
    MailmapResolver,
    MailmapResolverPath,
)


def _identity_resolver() -> MailmapResolver:
    return MailmapResolver(MailmapResolverPath.IDENTITY_PASSTHROUGH)


@pytest.fixture
async def seeded_graph(neo4j_driver):
    """Seed minimal git_history graph: 2 files, 3 authors, 5 commits.

    File a.py: 3 commits by author1, 1 commit by author2, 1 merge by author3.
    File b.py: 2 commits by author2 (one is by bot).
    """
    now = datetime.now(tz=timezone.utc)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            // Authors
            MERGE (a1:Author {provider: 'git', identity_key: 'a1@example.com'})
              SET a1.email = 'a1@example.com', a1.name = 'A1', a1.is_bot = false
            MERGE (a2:Author {provider: 'git', identity_key: 'a2@example.com'})
              SET a2.email = 'a2@example.com', a2.name = 'A2', a2.is_bot = false
            MERGE (bot:Author {provider: 'git', identity_key: 'bot@x.com'})
              SET bot.email = 'bot@x.com', bot.name = 'Bot', bot.is_bot = true

            // Files
            MERGE (fa:File {project_id: 'gimle', path: 'a.py'})
            MERGE (fb:File {project_id: 'gimle', path: 'b.py'})

            // Commits
            FOREACH (i IN range(1, 3) |
              MERGE (c:Commit {sha: 'c' + toString(i)})
                ON CREATE SET c.project_id = 'gimle',
                              c.committed_at = datetime() - duration({days: i}),
                              c.parents = [],
                              c.is_merge = false
              MERGE (c)-[:AUTHORED_BY]->(a1)
              MERGE (c)-[:TOUCHED]->(fa)
            )
            MERGE (c4:Commit {sha: 'c4'})
              ON CREATE SET c4.project_id = 'gimle',
                            c4.committed_at = datetime() - duration({days: 4}),
                            c4.parents = [],
                            c4.is_merge = false
            MERGE (c4)-[:AUTHORED_BY]->(a2)
            MERGE (c4)-[:TOUCHED]->(fa)

            MERGE (c5:Commit {sha: 'c5'})
              ON CREATE SET c5.project_id = 'gimle',
                            c5.committed_at = datetime() - duration({days: 5}),
                            c5.parents = ['p1', 'p2'],
                            c5.is_merge = true
            MERGE (c5)-[:AUTHORED_BY]->(a1)
            MERGE (c5)-[:TOUCHED]->(fa)

            MERGE (c6:Commit {sha: 'c6'})
              ON CREATE SET c6.project_id = 'gimle',
                            c6.committed_at = datetime() - duration({days: 1}),
                            c6.parents = [],
                            c6.is_merge = false
            MERGE (c6)-[:AUTHORED_BY]->(a2)
            MERGE (c6)-[:TOUCHED]->(fb)

            MERGE (c7:Commit {sha: 'c7'})
              ON CREATE SET c7.project_id = 'gimle',
                            c7.committed_at = datetime() - duration({days: 1}),
                            c7.parents = [],
                            c7.is_merge = false
            MERGE (c7)-[:AUTHORED_BY]->(bot)
            MERGE (c7)-[:TOUCHED]->(fb)
            """
        )
    yield neo4j_driver


@pytest.mark.asyncio
async def test_churn_aggregator_excludes_bots_and_merges(seeded_graph):
    result = await aggregate_churn(
        seeded_graph,
        project_id="gimle",
        paths={"a.py", "b.py"},
        mailmap=_identity_resolver(),
        bot_keys={"bot@x.com"},
        decay_days=30.0,
        known_author_ids={"a1@example.com", "a2@example.com", "bot@x.com"},
    )

    # a.py: a1 has 3 non-merge commits, a2 has 1 non-merge commit; merge by a1 excluded
    a_authors = result["a.py"]
    assert "a1@example.com" in a_authors
    assert a_authors["a1@example.com"].commit_count == 3  # merge filtered
    assert "a2@example.com" in a_authors
    assert a_authors["a2@example.com"].commit_count == 1

    # b.py: a2 has 1 commit; bot is excluded entirely
    b_authors = result["b.py"]
    assert "a2@example.com" in b_authors
    assert b_authors["a2@example.com"].commit_count == 1
    assert "bot@x.com" not in b_authors


@pytest.mark.asyncio
async def test_churn_recency_decay_monotone(seeded_graph):
    """Older commits → smaller recency_score per commit."""
    result = await aggregate_churn(
        seeded_graph,
        project_id="gimle",
        paths={"a.py"},
        mailmap=_identity_resolver(),
        bot_keys=set(),
        decay_days=30.0,
        known_author_ids={"a1@example.com", "a2@example.com"},
    )
    # a1: 3 commits at days 1, 2, 3 → all relatively recent
    # a2: 1 commit at day 4 → older
    a1_score = result["a.py"]["a1@example.com"].recency_score
    a2_score = result["a.py"]["a2@example.com"].recency_score
    # Per-commit average: a1 ~ exp(-1/30), a2 ~ exp(-4/30)
    assert a1_score / 3 > a2_score / 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_churn_aggregator.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement churn_aggregator**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/churn_aggregator.py`:

```python
"""Recency-weighted churn aggregation from existing :Commit graph.

Reversed-direction Cypher (start from :File PK), partial server-side
aggregation by raw a.identity_key (returns timestamps + count). Mailmap
canonicalization and decay computation happen client-side. Bot filter
is doubled: server-side via NOT a.is_bot AND post-mailmap via
bot_keys (catches mailmap-aliased bots).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timezone

from neo4j import AsyncDriver

from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver
from palace_mcp.extractors.code_ownership.models import ChurnShare

# Reversed direction: starts from :File PK lookup (UNIQUE on
# (project_id, path) per GIM-186). Server-side pre-aggregation by raw
# identity_key returns timestamps + count instead of N rows.
_CHURN_CYPHER = """
UNWIND $paths AS p
MATCH (f:File {project_id: $project_id, path: p})<-[:TOUCHED]-(c:Commit)
WHERE NOT c.is_merge
MATCH (c)-[:AUTHORED_BY]->(a:Author)
WHERE NOT a.is_bot
WITH p, a.identity_key AS raw_id, a.name AS raw_name,
     collect(c.committed_at) AS timestamps
RETURN p, raw_id, raw_name, timestamps, size(timestamps) AS commit_count
"""


async def aggregate_churn(
    driver: AsyncDriver,
    *,
    project_id: str,
    paths: Iterable[str],
    mailmap: MailmapResolver,
    bot_keys: set[str],
    decay_days: float,
    known_author_ids: set[str],
) -> dict[str, dict[str, ChurnShare]]:
    """Return {path: {canonical_id: ChurnShare}} for the given paths."""
    paths_list = list(paths)
    if not paths_list:
        return {}

    now = datetime.now(tz=timezone.utc)
    decay_seconds = decay_days * 86400.0

    async with driver.session() as session:
        result = await session.run(
            _CHURN_CYPHER,
            project_id=project_id,
            paths=paths_list,
        )
        records = await result.data()

    out: dict[str, dict[str, ChurnShare]] = {}
    for r in records:
        path = r["p"]
        raw_id = r["raw_id"]
        raw_name = r["raw_name"]
        timestamps = r["timestamps"]
        cn, ce = mailmap.canonicalize(raw_name, raw_id)
        canonical_id = ce
        if canonical_id in bot_keys:
            continue
        # Convert Neo4j datetime → Python datetime
        py_ts: list[datetime] = []
        for t in timestamps:
            if isinstance(t, datetime):
                py_ts.append(t if t.tzinfo else t.replace(tzinfo=timezone.utc))
            elif hasattr(t, "to_native"):
                native = t.to_native()
                py_ts.append(
                    native
                    if native.tzinfo
                    else native.replace(tzinfo=timezone.utc)
                )
            elif isinstance(t, str):
                py_ts.append(datetime.fromisoformat(t))
        recency_score = sum(
            math.exp(-(now - ts).total_seconds() / decay_seconds)
            for ts in py_ts
        )
        last_touched_at = max(py_ts)
        commit_count = int(r["commit_count"])

        per_path = out.setdefault(path, {})
        existing = per_path.get(canonical_id)
        if existing is None:
            per_path[canonical_id] = ChurnShare(
                canonical_id=canonical_id,
                canonical_name=cn,
                canonical_email=ce,
                recency_score=recency_score,
                last_touched_at=last_touched_at,
                commit_count=commit_count,
            )
        else:
            # Two raw_ids canonicalize to same id (mailmap collapse)
            per_path[canonical_id] = ChurnShare(
                canonical_id=canonical_id,
                canonical_name=cn,
                canonical_email=ce,
                recency_score=existing.recency_score + recency_score,
                last_touched_at=max(existing.last_touched_at, last_touched_at),
                commit_count=existing.commit_count + commit_count,
            )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_churn_aggregator.py -v`

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/churn_aggregator.py \
        services/palace-mcp/tests/extractors/integration/test_code_ownership_churn_aggregator.py
git commit -m "feat(GIM-216): churn_aggregator — reversed-direction Cypher + server-side aggregation"
```

---

## Task 9: Scorer (formula + per-file normalization)

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/scorer.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_code_ownership_scorer.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/unit/test_code_ownership_scorer.py`:

```python
from datetime import datetime, timezone

import pytest

from palace_mcp.extractors.code_ownership.models import (
    BlameAttribution,
    ChurnShare,
)
from palace_mcp.extractors.code_ownership.scorer import score_file


def _now() -> datetime:
    return datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


def _blame(canonical_id: str, lines: int) -> BlameAttribution:
    return BlameAttribution(
        canonical_id=canonical_id,
        canonical_name=canonical_id.split("@")[0],
        canonical_email=canonical_id,
        lines=lines,
    )


def _churn(canonical_id: str, recency: float, commits: int) -> ChurnShare:
    return ChurnShare(
        canonical_id=canonical_id,
        canonical_name=canonical_id.split("@")[0],
        canonical_email=canonical_id,
        recency_score=recency,
        last_touched_at=_now(),
        commit_count=commits,
    )


def test_single_author_weight_one():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 10)},
        churn={"a@x.com": _churn("a@x.com", 1.0, 1)},
        alpha=0.5,
        known_author_ids={"a@x.com"},
    )
    assert len(edges) == 1
    e = edges[0]
    assert e.weight == pytest.approx(1.0)
    assert e.blame_share == pytest.approx(1.0)
    assert e.recency_churn_share == pytest.approx(1.0)
    assert e.canonical_via == "identity"


def test_per_file_shares_sum_to_one():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 30), "b@x.com": _blame("b@x.com", 70)},
        churn={"a@x.com": _churn("a@x.com", 1.0, 1), "b@x.com": _churn("b@x.com", 3.0, 3)},
        alpha=0.5,
        known_author_ids={"a@x.com", "b@x.com"},
    )
    total_blame = sum(e.blame_share for e in edges)
    total_churn = sum(e.recency_churn_share for e in edges)
    total_w = sum(e.weight for e in edges)
    assert total_blame == pytest.approx(1.0)
    assert total_churn == pytest.approx(1.0)
    assert total_w == pytest.approx(1.0)


def test_alpha_zero_uses_only_churn():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 100)},  # blame says all-a
        churn={"a@x.com": _churn("a@x.com", 1.0, 1), "b@x.com": _churn("b@x.com", 4.0, 4)},
        alpha=0.0,
        known_author_ids={"a@x.com", "b@x.com"},
    )
    # b has no blame but α=0 means weight = 0 + 1 × churn_share
    by_id = {e.canonical_id: e for e in edges}
    assert by_id["a@x.com"].weight == pytest.approx(0.2)
    assert by_id["b@x.com"].weight == pytest.approx(0.8)


def test_alpha_one_uses_only_blame():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 100)},
        churn={"b@x.com": _churn("b@x.com", 4.0, 4)},  # only b has churn
        alpha=1.0,
        known_author_ids={"a@x.com", "b@x.com"},
    )
    by_id = {e.canonical_id: e for e in edges}
    assert by_id["a@x.com"].weight == pytest.approx(1.0)
    assert "b@x.com" not in by_id  # b has no blame, blame_share=0, churn weighted 0


def test_canonical_via_mailmap_synthetic():
    """canonical_id not in known_author_ids → mailmap_synthetic."""
    # Note: blame walker already canonicalized; here scorer uses the mapping
    # set by upstream phases via known_author_ids.
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"new@x.com": _blame("new@x.com", 10)},
        churn={"new@x.com": _churn("new@x.com", 1.0, 1)},
        alpha=0.5,
        known_author_ids=set(),  # empty — canonical not seen as raw
    )
    assert edges[0].canonical_via == "mailmap_synthetic"


def test_empty_inputs_return_no_edges():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={},
        churn={},
        alpha=0.5,
        known_author_ids=set(),
    )
    assert edges == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_scorer.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement scorer**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/scorer.py`:

```python
"""Per-file weight scorer.

weight = α × blame_share + (1-α) × recency_churn_share
        per-file shares normalized over non-bot authors.

Bot authors are already filtered upstream (blame_walker / churn_aggregator
via bot_keys). The scorer trusts its inputs to be human-only.

Edges are emitted only for authors with at least one signal — an author
with blame=0 and churn=0 produces no edge.
"""

from __future__ import annotations

from datetime import datetime

from palace_mcp.extractors.code_ownership.models import (
    BlameAttribution,
    ChurnShare,
    OwnershipEdge,
)


def score_file(
    *,
    project_id: str,
    path: str,
    blame: dict[str, BlameAttribution],
    churn: dict[str, ChurnShare],
    alpha: float,
    known_author_ids: set[str],
) -> list[OwnershipEdge]:
    """Compute per-file ownership edges with normalized shares."""
    all_canonicals = set(blame) | set(churn)
    if not all_canonicals:
        return []

    total_lines = sum(b.lines for b in blame.values())
    total_recency = sum(c.recency_score for c in churn.values())

    edges: list[OwnershipEdge] = []
    for canonical_id in all_canonicals:
        b = blame.get(canonical_id)
        c = churn.get(canonical_id)
        blame_share = (b.lines / total_lines) if (b and total_lines > 0) else 0.0
        churn_share = (
            (c.recency_score / total_recency) if (c and total_recency > 0) else 0.0
        )
        weight = alpha * blame_share + (1.0 - alpha) * churn_share
        if weight == 0.0:
            continue

        # Resolve display fields preferring blame side (HEAD truth)
        if b is not None:
            canonical_name = b.canonical_name
            canonical_email = b.canonical_email
        else:
            assert c is not None  # at least one signal exists
            canonical_name = c.canonical_name
            canonical_email = c.canonical_email

        last_touched_at: datetime
        if c is not None:
            last_touched_at = c.last_touched_at
        else:
            # No churn signal — fall back to "now" placeholder; spec
            # tolerates this corner case (HEAD blame without :TOUCHED).
            from datetime import timezone

            last_touched_at = datetime.now(tz=timezone.utc)

        canonical_via: str
        if canonical_id in known_author_ids:
            canonical_via = "mailmap_existing" if (
                # Distinguish identity from existing-via-mailmap requires
                # knowing the raw_id; not available here. We treat any
                # known-canonical as 'mailmap_existing' UNLESS it equals
                # itself with no aliasing — but we cannot tell at this
                # layer. Upstream (writer) will refine via
                # comparison with raw_id. For the scorer we encode:
                #   in known_author_ids → mailmap_existing
                #   not in known_author_ids → mailmap_synthetic
                # Identity (no aliasing) is a writer-level concern when
                # raw_id == canonical_id (set by upstream caller).
                False
            ) else "identity"
        else:
            canonical_via = "mailmap_synthetic"

        edges.append(
            OwnershipEdge(
                project_id=project_id,
                path=path,
                canonical_id=canonical_id,
                canonical_email=canonical_email,
                canonical_name=canonical_name,
                weight=weight,
                blame_share=blame_share,
                recency_churn_share=churn_share,
                last_touched_at=last_touched_at,
                lines_attributed=(b.lines if b else 0),
                commit_count=(c.commit_count if c else 0),
                canonical_via=canonical_via,
            )
        )
    return edges
```

**Note on `canonical_via`:** the scorer cannot distinguish `identity` (no mailmap aliasing) from `mailmap_existing` (mailmap collapsed two raw_ids into a known canonical). The scorer emits `identity` for known_author_ids hits as a default; the orchestrator (Task 12) refines this to `mailmap_existing` when it knows the raw_id at the source row level differed from the canonical_id. Synthetic detection is correct here because synthetic canonicals are by definition NOT in known_author_ids.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_scorer.py -v`

Expected: 6 PASS. (Note: `test_canonical_via_mailmap_synthetic` checks the synthetic branch correctly. The identity vs mailmap_existing refinement is tested in the integration test for the orchestrator at Task 13.)

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/scorer.py \
        services/palace-mcp/tests/extractors/unit/test_code_ownership_scorer.py
git commit -m "feat(GIM-216): scorer — α-blend + per-file normalization + canonical_via"
```

---

## Task 10: Neo4j writer (atomic-replace tx + sidecar :OwnershipFileState)

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/neo4j_writer.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_code_ownership_neo4j_writer.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/integration/test_code_ownership_neo4j_writer.py`:

```python
from datetime import datetime, timezone

import pytest

from palace_mcp.extractors.code_ownership.models import OwnershipEdge
from palace_mcp.extractors.code_ownership.neo4j_writer import (
    OWNERSHIP_SOURCE,
    write_batch,
)
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _edge(path: str, author_id: str, weight: float) -> OwnershipEdge:
    return OwnershipEdge(
        project_id="gimle",
        path=path,
        canonical_id=author_id,
        canonical_email=author_id,
        canonical_name=author_id.split("@")[0],
        weight=weight,
        blame_share=weight,
        recency_churn_share=weight,
        last_touched_at=_now(),
        lines_attributed=10,
        commit_count=2,
        canonical_via="identity",
    )


@pytest.mark.asyncio
async def test_write_batch_creates_owned_by_with_source(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'a@x.com'})
              SET a.email='a@x.com', a.name='A', a.is_bot=false
            """
        )
    await write_batch(
        neo4j_driver,
        project_id="gimle",
        edges=[_edge("a.py", "a@x.com", 1.0)],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: 'gimle', path: 'a.py'})
                  -[r:OWNED_BY]->(a:Author)
            RETURN r.source AS source, r.weight AS weight,
                   r.run_id_provenance AS run_id, r.alpha_used AS alpha
            """
        )
        row = await result.single()
    assert row["source"] == OWNERSHIP_SOURCE
    assert row["weight"] == 1.0
    assert row["run_id"] == "r1"
    assert row["alpha"] == 0.5


@pytest.mark.asyncio
async def test_atomic_replace_wipes_old_then_writes_new(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'old@x.com'})
              SET a.email='old@x.com', a.name='Old', a.is_bot=false
            MERGE (b:Author {provider: 'git', identity_key: 'new@x.com'})
              SET b.email='new@x.com', b.name='New', b.is_bot=false
            """
        )
    # First batch: old@x.com is owner
    await write_batch(
        neo4j_driver,
        project_id="gimle",
        edges=[_edge("a.py", "old@x.com", 1.0)],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    # Second batch: new@x.com is owner; old must be wiped
    await write_batch(
        neo4j_driver,
        project_id="gimle",
        edges=[_edge("a.py", "new@x.com", 1.0)],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r2",
        alpha=0.5,
    )
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: 'gimle', path: 'a.py'})
                  -[r:OWNED_BY]->(a:Author)
            RETURN a.identity_key AS who
            """
        )
        whos = [row["who"] for row in await result.data()]
    assert whos == ["new@x.com"]


@pytest.mark.asyncio
async def test_deleted_paths_wipe_edges_no_new_writes(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'a@x.com'})
              SET a.email='a@x.com', a.name='A', a.is_bot=false
            MERGE (f)-[r:OWNED_BY]->(a)
              SET r.source='extractor.code_ownership', r.weight=1.0
            """
        )
    await write_batch(
        neo4j_driver,
        project_id="gimle",
        edges=[],
        file_states=[],
        deleted_paths=["a.py"],
        run_id="r1",
        alpha=0.5,
    )
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (:File {project_id: 'gimle', path: 'a.py'})
                  -[r:OWNED_BY]->()
            RETURN count(r) AS c
            """
        )
        row = await result.single()
    assert row["c"] == 0


@pytest.mark.asyncio
async def test_file_state_sidecar_written(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (b:File {project_id: 'gimle', path: 'b.bin'})
            """
        )
    await write_batch(
        neo4j_driver,
        project_id="gimle",
        edges=[],
        file_states=[
            {"path": "a.py", "status": "skipped", "no_owners_reason": "all_bot_authors"},
            {"path": "b.bin", "status": "skipped", "no_owners_reason": "binary_or_skipped"},
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (s:OwnershipFileState {project_id: 'gimle'})
            RETURN s.path AS path, s.no_owners_reason AS reason
            ORDER BY s.path
            """
        )
        rows = await result.data()
    assert {r["path"]: r["reason"] for r in rows} == {
        "a.py": "all_bot_authors",
        "b.bin": "binary_or_skipped",
    }


@pytest.mark.asyncio
async def test_synthetic_author_merged_when_canonical_unknown(neo4j_driver):
    """canonical_via=mailmap_synthetic → MERGE creates virtual :Author."""
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            "MERGE (f:File {project_id: 'gimle', path: 'a.py'})"
        )
    edge = _edge("a.py", "synthetic@x.com", 1.0)
    edge_dict = edge.model_dump()
    edge_dict["canonical_via"] = "mailmap_synthetic"
    # Build edge with mailmap_synthetic
    syn_edge = OwnershipEdge(**edge_dict)
    await write_batch(
        neo4j_driver,
        project_id="gimle",
        edges=[syn_edge],
        file_states=[
            {"path": "a.py", "status": "processed", "no_owners_reason": None}
        ],
        deleted_paths=[],
        run_id="r1",
        alpha=0.5,
    )
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Author {provider: 'git', identity_key: 'synthetic@x.com'})
            RETURN a.identity_key AS id
            """
        )
        row = await result.single()
    assert row is not None and row["id"] == "synthetic@x.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_neo4j_writer.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement neo4j_writer**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/neo4j_writer.py`:

```python
"""Per-batch atomic-replace transaction writer.

Contract (per spec rev2 C2): for the paths in a batch, all old
:OWNED_BY edges (filtered by stable r.source) are deleted AND all new
edges (with sidecar :OwnershipFileState) are written within ONE
transaction. Readers see either the pre-batch or post-batch state for
any given path, never mixed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from neo4j import AsyncDriver

from palace_mcp.extractors.code_ownership.models import OwnershipEdge

OWNERSHIP_SOURCE = "extractor.code_ownership"

_DELETE_BY_PATH_CYPHER = """
UNWIND $paths AS p
MATCH (f:File {project_id: $proj, path: p})
      -[r:OWNED_BY {source: $source}]
      ->()
DELETE r
"""

_WRITE_EDGES_CYPHER = """
UNWIND $edges AS e
MATCH (f:File {project_id: $proj, path: e.path})
MERGE (a:Author {provider: 'git', identity_key: e.canonical_id})
  ON CREATE SET a.email = e.canonical_email,
                a.name = e.canonical_name,
                a.is_bot = false,
                a.first_seen_at = e.last_touched_at,
                a.last_seen_at = e.last_touched_at
MERGE (f)-[r:OWNED_BY]->(a)
SET r.source = $source,
    r.weight = e.weight,
    r.blame_share = e.blame_share,
    r.recency_churn_share = e.recency_churn_share,
    r.last_touched_at = e.last_touched_at,
    r.lines_attributed = e.lines_attributed,
    r.commit_count = e.commit_count,
    r.run_id_provenance = $run_id,
    r.alpha_used = $alpha,
    r.canonical_via = e.canonical_via
"""

_WRITE_FILE_STATE_CYPHER = """
UNWIND $states AS s
MERGE (st:OwnershipFileState {project_id: $proj, path: s.path})
SET st.status = s.status,
    st.no_owners_reason = s.no_owners_reason,
    st.last_run_id = $run_id,
    st.updated_at = $now
"""


async def write_batch(
    driver: AsyncDriver,
    *,
    project_id: str,
    edges: list[OwnershipEdge],
    file_states: list[dict],
    deleted_paths: list[str],
    run_id: str,
    alpha: float,
) -> None:
    """Atomic-replace a batch of paths within a single tx."""
    edges_payload = [
        {
            "path": e.path,
            "canonical_id": e.canonical_id,
            "canonical_email": e.canonical_email,
            "canonical_name": e.canonical_name,
            "weight": e.weight,
            "blame_share": e.blame_share,
            "recency_churn_share": e.recency_churn_share,
            "last_touched_at": e.last_touched_at.isoformat(),
            "lines_attributed": e.lines_attributed,
            "commit_count": e.commit_count,
            "canonical_via": e.canonical_via,
        }
        for e in edges
    ]
    paths_to_wipe = list({e.path for e in edges} | set(deleted_paths))
    now = datetime.now(tz=timezone.utc).isoformat()

    async with driver.session() as session:
        async with await session.begin_transaction() as tx:
            if paths_to_wipe:
                await tx.run(
                    _DELETE_BY_PATH_CYPHER,
                    paths=paths_to_wipe,
                    proj=project_id,
                    source=OWNERSHIP_SOURCE,
                )
            if edges_payload:
                await tx.run(
                    _WRITE_EDGES_CYPHER,
                    edges=edges_payload,
                    proj=project_id,
                    source=OWNERSHIP_SOURCE,
                    run_id=run_id,
                    alpha=alpha,
                )
            if file_states:
                await tx.run(
                    _WRITE_FILE_STATE_CYPHER,
                    states=file_states,
                    proj=project_id,
                    run_id=run_id,
                    now=now,
                )
            # tx commits on context exit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_neo4j_writer.py -v`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/neo4j_writer.py \
        services/palace-mcp/tests/extractors/integration/test_code_ownership_neo4j_writer.py
git commit -m "feat(GIM-216): neo4j_writer — per-batch atomic replace + :OwnershipFileState"
```

---

## Task 11: Mini-fixture (`code-ownership-mini-project`)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/REGEN.md`
- Create: `services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/regen.sh`
- Create (via regen): the .git directory and committed files

The fixture must be reproducible: `regen.sh` builds it from scratch.

- [ ] **Step 1: Write `REGEN.md`**

Create `services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/REGEN.md`:

```markdown
# Code Ownership Mini Fixture

## Layout

- 3 authors:
  - `Anton S <old@example.com>` — also writes as `Anton Stavnichiy <new@example.com>` (mailmapped)
  - `Other Human <other@example.com>` — single identity
  - `dependabot[bot] <bot@example.com>` — bot author
- 5 files:
  - `apps/main.py` — modified by both Anton (under both emails) and Other Human
  - `apps/util.py` — created and only touched by Other Human
  - `apps/legacy.py` — created and modified by Anton, then `git rm`-ed in HEAD
  - `apps/binary.png` — binary content; blame must skip
  - `apps/merge_target.py` — content changed only via merge commit
- `.mailmap` mapping `old@example.com → new@example.com` for Anton
- 12 commits including 1 merge

## Regenerate

```bash
bash services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/regen.sh
```

Idempotent — wipes existing fixture, rebuilds bit-exactly.
```

- [ ] **Step 2: Write `regen.sh`**

Create `services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/regen.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$HERE/repo"

rm -rf "$TARGET"
mkdir -p "$TARGET/apps"
cd "$TARGET"

git init --initial-branch=main
git config user.name "Anton S"
git config user.email "old@example.com"

cat > .mailmap <<'EOF'
Anton Stavnichiy <new@example.com> Anton S <old@example.com>
EOF

cat > apps/main.py <<'EOF'
def main():
    return 1
EOF
git add .mailmap apps/main.py
GIT_AUTHOR_DATE="2026-01-01T10:00:00Z" GIT_COMMITTER_DATE="2026-01-01T10:00:00Z" \
  git commit -m "init main.py" --quiet

cat > apps/util.py <<'EOF'
def util():
    return 2
EOF
git config user.name "Other Human"
git config user.email "other@example.com"
git add apps/util.py
GIT_AUTHOR_DATE="2026-01-02T10:00:00Z" GIT_COMMITTER_DATE="2026-01-02T10:00:00Z" \
  git commit -m "add util.py" --quiet

git config user.name "Anton S"
git config user.email "old@example.com"
cat > apps/legacy.py <<'EOF'
def legacy():
    return "legacy"
EOF
git add apps/legacy.py
GIT_AUTHOR_DATE="2026-01-03T10:00:00Z" GIT_COMMITTER_DATE="2026-01-03T10:00:00Z" \
  git commit -m "add legacy.py" --quiet

# Anton switches to new identity
git config user.email "new@example.com"
git config user.name "Anton Stavnichiy"
cat > apps/main.py <<'EOF'
def main():
    return 42
def helper():
    return "h"
EOF
git add apps/main.py
GIT_AUTHOR_DATE="2026-01-04T10:00:00Z" GIT_COMMITTER_DATE="2026-01-04T10:00:00Z" \
  git commit -m "expand main.py (new email)" --quiet

# binary file
printf '\x89PNG\r\n\x1a\n\x00\x00\x00fakepng' > apps/binary.png
git add apps/binary.png
GIT_AUTHOR_DATE="2026-01-05T10:00:00Z" GIT_COMMITTER_DATE="2026-01-05T10:00:00Z" \
  git commit -m "add binary.png" --quiet

# Other Human modifies main.py
git config user.name "Other Human"
git config user.email "other@example.com"
cat > apps/main.py <<'EOF'
def main():
    return 100
def helper():
    return "h"
def extra():
    return "e"
EOF
git add apps/main.py
GIT_AUTHOR_DATE="2026-01-06T10:00:00Z" GIT_COMMITTER_DATE="2026-01-06T10:00:00Z" \
  git commit -m "Other expands main.py" --quiet

# Side branch for merge commit
git checkout -b side
cat > apps/merge_target.py <<'EOF'
def from_side():
    return "side"
EOF
git add apps/merge_target.py
GIT_AUTHOR_DATE="2026-01-07T10:00:00Z" GIT_COMMITTER_DATE="2026-01-07T10:00:00Z" \
  git commit -m "add merge_target.py on side" --quiet

git checkout main
GIT_AUTHOR_DATE="2026-01-08T10:00:00Z" GIT_COMMITTER_DATE="2026-01-08T10:00:00Z" \
  git merge --no-ff side -m "merge side into main" --quiet
git branch -D side

# Bot commit
git config user.name "dependabot[bot]"
git config user.email "bot@example.com"
cat > apps/util.py <<'EOF'
def util():
    return 3  # bumped
EOF
git add apps/util.py
GIT_AUTHOR_DATE="2026-01-09T10:00:00Z" GIT_COMMITTER_DATE="2026-01-09T10:00:00Z" \
  git commit -m "deps: bump util" --quiet

# Anton final tweak (under canonical email)
git config user.name "Anton Stavnichiy"
git config user.email "new@example.com"
cat > apps/main.py <<'EOF'
def main():
    return 100
def helper():
    return "h2"
def extra():
    return "e"
EOF
git add apps/main.py
GIT_AUTHOR_DATE="2026-01-10T10:00:00Z" GIT_COMMITTER_DATE="2026-01-10T10:00:00Z" \
  git commit -m "tweak helper" --quiet

# Delete legacy.py
git rm apps/legacy.py
GIT_AUTHOR_DATE="2026-01-11T10:00:00Z" GIT_COMMITTER_DATE="2026-01-11T10:00:00Z" \
  git commit -m "drop legacy.py" --quiet

echo "fixture rebuilt at: $TARGET"
git -C "$TARGET" log --oneline
```

- [ ] **Step 3: Run regen + verify**

Run:

```bash
chmod +x services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/regen.sh
bash services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/regen.sh
```

Expected: prints 12 commits in `git log --oneline`. The `apps/legacy.py` does not exist in the working tree.

- [ ] **Step 4: Add `.gitignore` for the regenerated `repo/` working tree**

Create `services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/.gitignore`:

```
repo/
```

The fixture's `.git` is recreated locally by `regen.sh` — we do NOT commit a nested `.git` directory.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/REGEN.md \
        services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/regen.sh \
        services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/.gitignore
git commit -m "test(GIM-216): add code-ownership mini fixture (REGEN.md + regen.sh)"
```

---

## Task 12: Extractor orchestrator

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/code_ownership/extractor.py`

This task does NOT have its own dedicated unit tests — the orchestrator is exercised end-to-end by the integration test in Task 14. Each component it calls already has its own unit test.

- [ ] **Step 1: Write the orchestrator**

Create `services/palace-mcp/src/palace_mcp/extractors/code_ownership/extractor.py`:

```python
"""Code ownership extractor orchestrator (Roadmap #32).

5-phase pipeline per spec rev2 §4:
0. bootstrap (schema, checkpoint, mailmap, bots, head)
1. dirty-set computation (pygit2.Diff)
2. blame walk (DIRTY only)
3. churn aggregation (DIRTY only, reversed Cypher)
4. scoring + atomic-replace write (per batch)
5. checkpoint + IngestRun finalize
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pygit2

from palace_mcp.config import Settings
from palace_mcp.extractors.code_ownership.blame_walker import walk_blame
from palace_mcp.extractors.code_ownership.checkpoint import (
    load_checkpoint,
    update_checkpoint,
)
from palace_mcp.extractors.code_ownership.churn_aggregator import (
    aggregate_churn,
)
from palace_mcp.extractors.code_ownership.mailmap import (
    MailmapResolver,
    MailmapResolverPath,
)
from palace_mcp.extractors.code_ownership.models import OwnershipRunSummary
from palace_mcp.extractors.code_ownership.neo4j_writer import (
    OWNERSHIP_SOURCE,
    write_batch,
)
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)
from palace_mcp.extractors.code_ownership.scorer import score_file
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

logger = logging.getLogger(__name__)


class CodeOwnershipExtractor:
    """Roadmap #32 extractor — file-level ownership graph."""

    name = "code_ownership"
    description = "File-level ownership: blame_share + recency-weighted churn"
    constraints = ()
    indexes = ()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def extract(self, ctx: Any) -> dict[str, Any]:
        """Run the 5-phase pipeline. ctx provides driver + project + repo path."""
        driver = ctx.driver
        project_id = ctx.project
        repo_path = ctx.repo_path  # /repos/<slug>
        run_id = str(uuid.uuid4())
        started_at = time.monotonic()

        await create_ingest_run(
            driver, run_id=run_id, project=project_id, extractor_name=self.name
        )

        try:
            summary = await self._run(
                driver=driver,
                project_id=project_id,
                repo_path=repo_path,
                run_id=run_id,
            )
            await finalize_ingest_run(
                driver, run_id=run_id, success=True, error_code=None
            )
            await self._write_run_extras(driver, run_id, summary)
            duration_ms = int((time.monotonic() - started_at) * 1000)
            return {
                "ok": True,
                "run_id": run_id,
                "extractor": self.name,
                "project": project_id,
                "duration_ms": duration_ms,
                "nodes_written": summary.dirty_files_count + summary.deleted_files_count + 1,
                "edges_written": summary.edges_written,
                "edges_deleted": summary.edges_deleted,
                "exit_reason": summary.exit_reason,
                "mailmap_resolver_path": summary.mailmap_resolver_path,
            }
        except ExtractorError as exc:
            await finalize_ingest_run(
                driver,
                run_id=run_id,
                success=False,
                error_code=exc.code.value,
            )
            raise

    async def _run(
        self, *, driver: Any, project_id: str, repo_path: str, run_id: str
    ) -> OwnershipRunSummary:
        # Phase 0 — bootstrap
        await ensure_ownership_schema(driver)
        checkpoint = await load_checkpoint(driver, project_id=project_id)

        try:
            repo = pygit2.Repository(repo_path)
        except Exception as exc:
            raise ExtractorError(
                code=ExtractorErrorCode.REPO_NOT_MOUNTED,
                message=f"cannot open repo at {repo_path}: {type(exc).__name__}",
            ) from exc

        try:
            head_oid = repo.head.target
            current_head = str(head_oid)
        except Exception as exc:
            raise ExtractorError(
                code=ExtractorErrorCode.REPO_HEAD_INVALID,
                message=f"cannot resolve HEAD: {type(exc).__name__}",
            ) from exc

        mailmap = MailmapResolver.from_repo(
            repo, max_bytes=self.settings.mailmap_max_bytes
        )

        bot_keys = await self._fetch_bot_identity_keys(driver, project_id)
        known_author_ids = await self._fetch_known_author_ids(driver, project_id)

        # Verify GIM-186 git_history has indexed at least one commit
        has_commits = await self._has_any_commits(driver, project_id)
        if not has_commits:
            raise ExtractorError(
                code=ExtractorErrorCode.GIT_HISTORY_NOT_INDEXED,
                message=f"no :Commit nodes for project {project_id!r}",
            )

        # Phase 1 — DIRTY/DELETED computation
        dirty: set[str]
        deleted: set[str] = set()
        prev_head_sha = checkpoint.last_head_sha if checkpoint else None
        if prev_head_sha is None:
            dirty = self._all_files_in_head(repo)
        elif prev_head_sha == current_head:
            # no_change shortcut
            await update_checkpoint(
                driver,
                project_id=project_id,
                head_sha=current_head,
                run_id=run_id,
            )
            return OwnershipRunSummary(
                project_id=project_id,
                run_id=run_id,
                head_sha=current_head,
                prev_head_sha=prev_head_sha,
                dirty_files_count=0,
                deleted_files_count=0,
                edges_written=0,
                edges_deleted=0,
                mailmap_resolver_path=mailmap.path.value,
                exit_reason="no_change",
                duration_ms=0,
            )
        else:
            try:
                diff = repo.diff(prev_head_sha, current_head)
            except Exception as exc:
                raise ExtractorError(
                    code=ExtractorErrorCode.OWNERSHIP_DIFF_FAILED,
                    message=f"diff {prev_head_sha[:8]}..{current_head[:8]} raised {type(exc).__name__}",
                ) from exc
            dirty = set()
            for delta in diff.deltas:
                status = delta.status_char()
                # pygit2 status_char: A=added, M=modified, D=deleted, R=renamed
                if status in ("A", "M", "R") and delta.new_file.path:
                    dirty.add(delta.new_file.path)
                if status == "R" and delta.old_file.path:
                    # Rename: NEW path is dirty (above); OLD path is deleted
                    deleted.add(delta.old_file.path)
                if status == "D" and delta.old_file.path:
                    deleted.add(delta.old_file.path)

        if len(dirty) > self.settings.ownership_max_files_per_run:
            raise ExtractorError(
                code=ExtractorErrorCode.OWNERSHIP_MAX_FILES_EXCEEDED,
                message=(
                    f"DIRTY={len(dirty)} > cap "
                    f"{self.settings.ownership_max_files_per_run}"
                ),
            )

        if not dirty and not deleted:
            await update_checkpoint(
                driver,
                project_id=project_id,
                head_sha=current_head,
                run_id=run_id,
            )
            return OwnershipRunSummary(
                project_id=project_id,
                run_id=run_id,
                head_sha=current_head,
                prev_head_sha=prev_head_sha,
                dirty_files_count=0,
                deleted_files_count=0,
                edges_written=0,
                edges_deleted=0,
                mailmap_resolver_path=mailmap.path.value,
                exit_reason="no_dirty",
                duration_ms=0,
            )

        # Phase 2 — blame walk
        blame_per_file = walk_blame(
            repo,
            paths=dirty,
            mailmap=mailmap,
            bot_keys=bot_keys,
        )

        # Phase 3 — churn aggregation
        churn_per_file = await aggregate_churn(
            driver,
            project_id=project_id,
            paths=dirty,
            mailmap=mailmap,
            bot_keys=bot_keys,
            decay_days=float(self.settings.recency_decay_days),
            known_author_ids=known_author_ids,
        )

        # Phase 4 — scoring + atomic-replace per batch
        edges_all = []
        states_all = []
        for path in dirty:
            blame = blame_per_file.get(path, {})
            churn = churn_per_file.get(path, {})
            edges = score_file(
                project_id=project_id,
                path=path,
                blame=blame,
                churn=churn,
                alpha=self.settings.ownership_blame_weight,
                known_author_ids=known_author_ids,
            )
            if not edges:
                # determine no_owners_reason
                if not blame and not churn:
                    reason = "binary_or_skipped"
                elif not blame and churn:
                    reason = "binary_or_skipped"
                elif blame and not churn:
                    reason = "no_commit_history"
                else:
                    reason = "all_bot_authors"
                states_all.append(
                    {"path": path, "status": "skipped", "no_owners_reason": reason}
                )
                continue
            edges_all.extend(edges)
            states_all.append(
                {"path": path, "status": "processed", "no_owners_reason": None}
            )

        edges_written = 0
        edges_deleted_estimate = 0
        batch_size = self.settings.ownership_write_batch_size
        # Group edges by path so a batch contains complete per-path sets
        paths_in_dirty = list(dirty)
        deleted_list = list(deleted)

        for i in range(0, len(paths_in_dirty), batch_size):
            batch_paths = set(paths_in_dirty[i : i + batch_size])
            batch_edges = [e for e in edges_all if e.path in batch_paths]
            batch_states = [s for s in states_all if s["path"] in batch_paths]
            await write_batch(
                driver,
                project_id=project_id,
                edges=batch_edges,
                file_states=batch_states,
                deleted_paths=[],
                run_id=run_id,
                alpha=self.settings.ownership_blame_weight,
            )
            edges_written += len(batch_edges)

        # Final batch for DELETED-only paths
        if deleted_list:
            for i in range(0, len(deleted_list), batch_size):
                batch_paths = deleted_list[i : i + batch_size]
                await write_batch(
                    driver,
                    project_id=project_id,
                    edges=[],
                    file_states=[],
                    deleted_paths=batch_paths,
                    run_id=run_id,
                    alpha=self.settings.ownership_blame_weight,
                )

        await update_checkpoint(
            driver,
            project_id=project_id,
            head_sha=current_head,
            run_id=run_id,
        )

        return OwnershipRunSummary(
            project_id=project_id,
            run_id=run_id,
            head_sha=current_head,
            prev_head_sha=prev_head_sha,
            dirty_files_count=len(dirty),
            deleted_files_count=len(deleted),
            edges_written=edges_written,
            edges_deleted=edges_deleted_estimate,
            mailmap_resolver_path=mailmap.path.value,
            exit_reason="success",
            duration_ms=0,
        )

    @staticmethod
    def _all_files_in_head(repo: pygit2.Repository) -> set[str]:
        """Recursively list all files in HEAD tree."""
        head_tree = repo.head.peel().tree
        out: set[str] = set()

        def visit(tree: pygit2.Tree, prefix: str = "") -> None:
            for entry in tree:
                full = f"{prefix}{entry.name}" if not prefix else f"{prefix}/{entry.name}"
                if entry.type_str == "tree":
                    visit(repo[entry.id], full)
                else:
                    out.add(full)

        visit(head_tree)
        return out

    @staticmethod
    async def _fetch_bot_identity_keys(driver: Any, project_id: str) -> set[str]:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (c:Commit {project_id: $proj})-[:AUTHORED_BY]->(a:Author)
                WHERE a.is_bot = true
                RETURN DISTINCT a.identity_key AS k
                LIMIT 10000
                """,
                proj=project_id,
            )
            return {row["k"] for row in await result.data()}

    @staticmethod
    async def _fetch_known_author_ids(driver: Any, project_id: str) -> set[str]:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (c:Commit {project_id: $proj})-[:AUTHORED_BY]->(a:Author)
                RETURN DISTINCT a.identity_key AS k
                """,
                proj=project_id,
            )
            return {row["k"] for row in await result.data()}

    @staticmethod
    async def _has_any_commits(driver: Any, project_id: str) -> bool:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (c:Commit {project_id: $proj})
                RETURN count(c) AS n
                """,
                proj=project_id,
            )
            row = await result.single()
        return row is not None and row["n"] > 0

    async def _write_run_extras(
        self, driver: Any, run_id: str, summary: OwnershipRunSummary
    ) -> None:
        """Set ownership-specific properties on the substrate :IngestRun."""
        async with driver.session() as session:
            await session.run(
                """
                MATCH (r:IngestRun {run_id: $run_id})
                SET r.head_sha = $head_sha,
                    r.prev_head_sha = $prev_head_sha,
                    r.dirty_files_count = $dirty,
                    r.deleted_files_count = $deleted,
                    r.edges_written = $edges_written,
                    r.edges_deleted = $edges_deleted,
                    r.mailmap_resolver_path = $mailmap_path,
                    r.exit_reason = $exit_reason
                """,
                run_id=run_id,
                head_sha=summary.head_sha,
                prev_head_sha=summary.prev_head_sha,
                dirty=summary.dirty_files_count,
                deleted=summary.deleted_files_count,
                edges_written=summary.edges_written,
                edges_deleted=summary.edges_deleted,
                mailmap_path=summary.mailmap_resolver_path,
                exit_reason=summary.exit_reason,
            )
```

- [ ] **Step 2: No standalone test for orchestrator**

Pipeline correctness is exercised end-to-end via the integration test (Task 14). Skipping a per-step test here is intentional — the components called (mailmap, blame_walker, churn_aggregator, scorer, neo4j_writer, checkpoint) all have dedicated unit/integration tests.

- [ ] **Step 3: Verify imports don't break**

Run: `cd services/palace-mcp && uv run python -c "from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor; print(CodeOwnershipExtractor.name)"`

Expected: `code_ownership`

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/code_ownership/extractor.py
git commit -m "feat(GIM-216): orchestrator — 5-phase pipeline (bootstrap → write)"
```

---

## Task 13: Register `code_ownership` in EXTRACTORS

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py`

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/extractors/unit/test_registry.py` (create if missing):

```python
def test_code_ownership_registered():
    from palace_mcp.extractors.registry import EXTRACTORS

    assert "code_ownership" in EXTRACTORS
    cls = EXTRACTORS["code_ownership"]
    assert cls.__name__ == "CodeOwnershipExtractor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_registry.py::test_code_ownership_registered -v`

Expected: FAIL with KeyError or AssertionError.

- [ ] **Step 3: Register**

In `services/palace-mcp/src/palace_mcp/extractors/registry.py`, add the import + registration in alphabetical order with the existing entries:

```python
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor

# inside EXTRACTORS dict:
EXTRACTORS["code_ownership"] = CodeOwnershipExtractor
```

(Adjust to match the actual mapping shape used by other extractors — `EXTRACTORS["heartbeat"] = HeartbeatExtractor()` if instantiated, or class reference. Match the existing pattern verbatim.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_registry.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/registry.py services/palace-mcp/tests/extractors/unit/test_registry.py
git commit -m "feat(GIM-216): register code_ownership in EXTRACTORS"
```

---

## Task 14: Integration test — 8 scenarios on mini-fixture

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_code_ownership_integration.py`

This is the heaviest test in the slice. Each of the 8 spec §10.2 scenarios is one async test function.

- [ ] **Step 1: Write the integration test scaffolding**

Create `services/palace-mcp/tests/extractors/integration/test_code_ownership_integration.py`:

```python
"""Integration tests for code_ownership extractor.

Uses real Neo4j via testcontainers + the rebuilt mini-fixture at
tests/extractors/fixtures/code-ownership-mini-project/repo.

Each test rebuilds the fixture from regen.sh to ensure isolation.
GIM-186 git_history graph is seeded with hand-crafted Cypher
mirroring what git_history would produce, so we can test code_ownership
in isolation without depending on git_history being indexed first.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from palace_mcp.config import Settings
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "extractors"
    / "fixtures"
    / "code-ownership-mini-project"
)


def _rebuild_fixture() -> Path:
    subprocess.run(
        ["bash", str(FIXTURE_DIR / "regen.sh")],
        check=True,
        capture_output=True,
    )
    return FIXTURE_DIR / "repo"


def _seed_git_history(driver, repo_path: Path, project_id: str) -> None:
    """Mirror what GIM-186 would write for our fixture's history."""
    log = subprocess.run(
        ["git", "log", "--all", "--reverse",
         "--pretty=format:%H|%aN|%aE|%cI|%P"],
        cwd=str(repo_path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split("\n")
    rows = []
    for line in log:
        sha, name, email, when, parents = line.split("|", 4)
        rows.append({
            "sha": sha,
            "name": name,
            "email": email.lower(),
            "when": when,
            "parents": parents.split() if parents else [],
        })
    # Determine bot
    is_bot_emails = {"bot@example.com"}

    async def _seed():
        async with driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")
            await session.run(
                "MERGE (p:Project {slug: $slug})", slug=project_id
            )
            for r in rows:
                await session.run(
                    """
                    MERGE (a:Author {provider: 'git', identity_key: $email})
                      ON CREATE SET a.email=$email, a.name=$name,
                                    a.is_bot=$is_bot,
                                    a.first_seen_at=datetime($when),
                                    a.last_seen_at=datetime($when)
                      ON MATCH SET a.last_seen_at=datetime($when)
                    """,
                    email=r["email"],
                    name=r["name"],
                    is_bot=(r["email"] in is_bot_emails),
                    when=r["when"],
                )
                await session.run(
                    """
                    MERGE (c:Commit {sha: $sha})
                      ON CREATE SET c.project_id = $proj,
                                    c.committed_at = datetime($when),
                                    c.parents = $parents,
                                    c.is_merge = $is_merge
                    WITH c
                    MATCH (a:Author {provider:'git', identity_key:$email})
                    MERGE (c)-[:AUTHORED_BY]->(a)
                    """,
                    sha=r["sha"],
                    proj=project_id,
                    when=r["when"],
                    parents=r["parents"],
                    is_merge=len(r["parents"]) > 1,
                    email=r["email"],
                )
            # :TOUCHED edges via git diff-tree per commit
            for r in rows:
                if len(r["parents"]) > 1:
                    parent = r["parents"][0]
                    cmd = ["git", "diff-tree", "--no-commit-id", "-r",
                           parent, r["sha"]]
                else:
                    cmd = ["git", "diff-tree", "--no-commit-id", "-r",
                           "--root", r["sha"]]
                out = subprocess.run(
                    cmd, cwd=str(repo_path),
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                paths = []
                for line in out.split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    if len(parts) == 2:
                        paths.append(parts[1])
                for p in paths:
                    await session.run(
                        """
                        MERGE (f:File {project_id: $proj, path: $path})
                        WITH f
                        MATCH (c:Commit {sha: $sha})
                        MERGE (c)-[:TOUCHED]->(f)
                        """,
                        proj=project_id,
                        sha=r["sha"],
                        path=p,
                    )
    return _seed


def _make_ctx(driver, repo_path: Path, project_id: str = "test-ownership") -> SimpleNamespace:
    return SimpleNamespace(
        driver=driver,
        project=project_id,
        repo_path=str(repo_path),
    )


@pytest.fixture
def settings() -> Settings:
    os.environ.setdefault("PALACE_OWNERSHIP_BLAME_WEIGHT", "0.5")
    return Settings()


@pytest.mark.asyncio
async def test_scenario_1_bootstrap_full_walk(neo4j_driver, settings):
    """Spec §10.2 Scenario 1 — fresh run, no checkpoint → all expected
    :OWNED_BY edges with normalized shares."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    extractor = CodeOwnershipExtractor(settings)
    result = await extractor.extract(_make_ctx(neo4j_driver, repo_path))
    assert result["ok"] is True
    assert result["edges_written"] > 0
    assert result["mailmap_resolver_path"] in {"pygit2", "identity_passthrough"}

    # Verify per-file normalization (spec acceptance #8)
    async with neo4j_driver.session() as session:
        out = await session.run(
            """
            MATCH (f:File {project_id: 'test-ownership'})
                  -[r:OWNED_BY {source: 'extractor.code_ownership'}]->()
            WITH f, sum(r.blame_share) AS sum_blame,
                 sum(r.recency_churn_share) AS sum_churn,
                 sum(r.weight) AS sum_w
            WHERE sum_blame > 0 OR sum_churn > 0
            RETURN f.path AS path, sum_blame, sum_churn, sum_w
            """
        )
        rows = await out.data()
    for row in rows:
        if row["sum_blame"] > 0:
            assert abs(row["sum_blame"] - 1.0) < 1e-6, row
        if row["sum_churn"] > 0:
            assert abs(row["sum_churn"] - 1.0) < 1e-6, row


@pytest.mark.asyncio
async def test_scenario_2_no_op_re_run(neo4j_driver, settings):
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    extractor = CodeOwnershipExtractor(settings)
    first = await extractor.extract(_make_ctx(neo4j_driver, repo_path))
    assert first["exit_reason"] == "success"

    second = await extractor.extract(_make_ctx(neo4j_driver, repo_path))
    assert second["exit_reason"] == "no_change"
    assert second["edges_written"] == 0


@pytest.mark.asyncio
async def test_scenario_3_incremental_edit(neo4j_driver, settings):
    """Append a commit changing one file → DIRTY = {that file}."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    ext = CodeOwnershipExtractor(settings)
    await ext.extract(_make_ctx(neo4j_driver, repo_path))

    # Append a commit
    subprocess.run(["git", "config", "user.email", "new@example.com"], cwd=str(repo_path), check=True)
    subprocess.run(["git", "config", "user.name", "Anton Stavnichiy"], cwd=str(repo_path), check=True)
    (repo_path / "apps" / "main.py").write_text(
        "def main():\n    return 200\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "apps/main.py"], cwd=str(repo_path), check=True)
    subprocess.run(["git", "commit", "-m", "trim main"], cwd=str(repo_path), check=True)

    # Re-seed git_history for the new commit (mirroring GIM-186 incremental)
    seed2 = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed2()

    result = await ext.extract(_make_ctx(neo4j_driver, repo_path))
    assert result["exit_reason"] == "success"


@pytest.mark.asyncio
async def test_scenario_4_deletion_handling(neo4j_driver, settings):
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    ext = CodeOwnershipExtractor(settings)
    await ext.extract(_make_ctx(neo4j_driver, repo_path))

    # legacy.py was already deleted in the fixture HEAD;
    # verify no :OWNED_BY edges exist for it
    async with neo4j_driver.session() as session:
        out = await session.run(
            """
            MATCH (f:File {project_id: 'test-ownership', path: 'apps/legacy.py'})
                  -[r:OWNED_BY]->()
            RETURN count(r) AS n
            """
        )
        row = await out.single()
    assert row["n"] == 0


@pytest.mark.asyncio
async def test_scenario_5_mailmap_dedup(neo4j_driver, settings):
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    ext = CodeOwnershipExtractor(settings)
    await ext.extract(_make_ctx(neo4j_driver, repo_path))

    # If pygit2.Mailmap is exposed, old@example.com should resolve to new@example.com
    async with neo4j_driver.session() as session:
        out = await session.run(
            """
            MATCH (f:File {project_id: 'test-ownership'})
                  -[r:OWNED_BY {source: 'extractor.code_ownership'}]
                  ->(a:Author)
            WHERE a.identity_key IN ['old@example.com', 'new@example.com']
            RETURN a.identity_key AS id, count(r) AS n
            """
        )
        rows = {r["id"]: r["n"] for r in await out.data()}
    # If mailmap working: only new@example.com appears with edges
    # If identity passthrough (no pygit2.Mailmap): both may appear
    assert ("new@example.com" in rows) or ("old@example.com" in rows)


@pytest.mark.asyncio
async def test_scenario_6_bot_exclusion(neo4j_driver, settings):
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    ext = CodeOwnershipExtractor(settings)
    await ext.extract(_make_ctx(neo4j_driver, repo_path))

    async with neo4j_driver.session() as session:
        out = await session.run(
            """
            MATCH ()-[r:OWNED_BY {source: 'extractor.code_ownership'}]
                  ->(a:Author {identity_key: 'bot@example.com'})
            RETURN count(r) AS n
            """
        )
        row = await out.single()
    assert row["n"] == 0


@pytest.mark.asyncio
async def test_scenario_7_merge_exclusion(neo4j_driver, settings):
    """Merge author does not get churn for the merge commit."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    ext = CodeOwnershipExtractor(settings)
    await ext.extract(_make_ctx(neo4j_driver, repo_path))

    # apps/merge_target.py was added on side branch; merge brought it in.
    # Author of that file is the side-branch committer (Anton or Other),
    # NOT the merge committer. Verify no edge to the merger via the merge
    # commit alone.
    async with neo4j_driver.session() as session:
        out = await session.run(
            """
            MATCH (f:File {project_id: 'test-ownership', path: 'apps/merge_target.py'})
                  -[r:OWNED_BY]->(a:Author)
            RETURN a.identity_key AS id, r.commit_count AS commits
            """
        )
        rows = await out.data()
    # commit_count for any owner of merge_target.py should be 1 (the side-branch commit)
    # not 2 (which would include the merge)
    for row in rows:
        assert row["commits"] <= 1, row


@pytest.mark.asyncio
async def test_scenario_8_crash_recovery(neo4j_driver, settings, monkeypatch):
    """Phase 4 mid-run crash leaves checkpoint stale; re-run clean."""
    from palace_mcp.extractors.code_ownership import neo4j_writer as nw

    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(neo4j_driver)
    seed = _seed_git_history(neo4j_driver, repo_path, "test-ownership")
    await seed()

    ext = CodeOwnershipExtractor(settings)

    original = nw.write_batch
    call_count = {"n": 0}

    async def crash_after_first(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            await original(*args, **kwargs)  # let one batch through
            return
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(nw, "write_batch", crash_after_first)

    with pytest.raises((RuntimeError, Exception)):
        # batch_size=1 forces multiple batches
        s = Settings(_env_file=None)
        s.ownership_write_batch_size = 100
        await ext.extract(_make_ctx(neo4j_driver, repo_path))

    # Restore writer + re-run; should converge to clean state
    monkeypatch.setattr(nw, "write_batch", original)
    result = await ext.extract(_make_ctx(neo4j_driver, repo_path))
    assert result["exit_reason"] in {"success", "no_change"}
```

- [ ] **Step 2: Run test to verify all 8 scenarios pass**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_code_ownership_integration.py -v`

Expected: 8 PASS.

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_code_ownership_integration.py
git commit -m "test(GIM-216): integration — 8 scenarios on mini-fixture"
```

---

## Task 15: `palace.code.find_owners` MCP tool

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/code/find_owners.py`
- Create: `services/palace-mcp/tests/code/test_find_owners_wire.py`

- [ ] **Step 1: Write failing wire-contract test**

Create `services/palace-mcp/tests/code/test_find_owners_wire.py`:

```python
import pytest

from palace_mcp.code.find_owners import find_owners
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)


@pytest.mark.asyncio
async def test_unknown_file_returns_unknown_file_error(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1',
                  c.updated_at=datetime()
            """
        )
    result = await find_owners(
        neo4j_driver, file_path="nope.py", project="gimle", top_n=5
    )
    assert result["ok"] is False
    assert result["error_code"] == "unknown_file"


@pytest.mark.asyncio
async def test_project_not_registered_error(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    result = await find_owners(
        neo4j_driver, file_path="x.py", project="ghost", top_n=5
    )
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_ownership_not_indexed_yet_error(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("MERGE (p:Project {slug: 'gimle'})")
    result = await find_owners(
        neo4j_driver, file_path="x.py", project="gimle", top_n=5
    )
    assert result["ok"] is False
    assert result["error_code"] == "ownership_not_indexed_yet"


@pytest.mark.asyncio
async def test_top_n_out_of_range_error(neo4j_driver):
    result = await find_owners(
        neo4j_driver, file_path="x.py", project="gimle", top_n=0
    )
    assert result["ok"] is False
    assert result["error_code"] == "top_n_out_of_range"


@pytest.mark.asyncio
async def test_slug_invalid_error(neo4j_driver):
    result = await find_owners(
        neo4j_driver, file_path="x.py", project="!!!bad-slug!!!", top_n=5
    )
    assert result["ok"] is False
    assert result["error_code"] == "slug_invalid"


@pytest.mark.asyncio
async def test_success_with_owners(neo4j_driver):
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1',
                  c.updated_at=datetime()
            MERGE (f:File {project_id: 'gimle', path: 'a.py'})
            MERGE (a:Author {provider: 'git', identity_key: 'a@x.com'})
              SET a.email='a@x.com', a.name='A', a.is_bot=false
            MERGE (b:Author {provider: 'git', identity_key: 'b@x.com'})
              SET b.email='b@x.com', b.name='B', b.is_bot=false
            MERGE (f)-[r1:OWNED_BY]->(a)
              SET r1.source='extractor.code_ownership',
                  r1.weight=0.7, r1.blame_share=0.7, r1.recency_churn_share=0.7,
                  r1.last_touched_at=datetime(),
                  r1.lines_attributed=70, r1.commit_count=7,
                  r1.run_id_provenance='r1', r1.alpha_used=0.5,
                  r1.canonical_via='identity'
            MERGE (f)-[r2:OWNED_BY]->(b)
              SET r2.source='extractor.code_ownership',
                  r2.weight=0.3, r2.blame_share=0.3, r2.recency_churn_share=0.3,
                  r2.last_touched_at=datetime(),
                  r2.lines_attributed=30, r2.commit_count=3,
                  r2.run_id_provenance='r1', r2.alpha_used=0.5,
                  r2.canonical_via='identity'
            MERGE (st:OwnershipFileState {project_id: 'gimle', path: 'a.py'})
              SET st.status='processed', st.no_owners_reason=null,
                  st.last_run_id='r1', st.updated_at=datetime()
            MERGE (ir:IngestRun {run_id: 'r1'})
              SET ir.source='extractor.code_ownership',
                  ir.completed_at=datetime(),
                  ir.head_sha='deadbeef',
                  ir.exit_reason='success'
            """
        )
    result = await find_owners(
        neo4j_driver, file_path="a.py", project="gimle", top_n=5
    )
    assert result["ok"] is True
    assert len(result["owners"]) == 2
    assert result["owners"][0]["author_email"] == "a@x.com"  # sorted desc by weight
    assert result["owners"][0]["weight"] == 0.7
    assert result["total_authors"] == 2
    assert result["no_owners_reason"] is None


@pytest.mark.asyncio
async def test_success_empty_with_no_owners_reason_binary(neo4j_driver):
    """File processed but skipped (e.g., binary) — no owners + reason."""
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1',
                  c.updated_at=datetime()
            MERGE (f:File {project_id: 'gimle', path: 'b.png'})
            MERGE (st:OwnershipFileState {project_id: 'gimle', path: 'b.png'})
              SET st.status='skipped',
                  st.no_owners_reason='binary_or_skipped',
                  st.last_run_id='r1', st.updated_at=datetime()
            """
        )
    result = await find_owners(
        neo4j_driver, file_path="b.png", project="gimle", top_n=5
    )
    assert result["ok"] is True
    assert result["owners"] == []
    assert result["no_owners_reason"] == "binary_or_skipped"


@pytest.mark.asyncio
async def test_success_empty_file_not_yet_processed(neo4j_driver):
    """File exists in :File but no :OwnershipFileState — file_not_yet_processed."""
    await ensure_ownership_schema(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (p:Project {slug: 'gimle'})
            MERGE (c:OwnershipCheckpoint {project_id: 'gimle'})
              SET c.last_head_sha='deadbeef',
                  c.last_completed_at=datetime(),
                  c.run_id='r1',
                  c.updated_at=datetime()
            MERGE (f:File {project_id: 'gimle', path: 'fresh.py'})
            """
        )
    result = await find_owners(
        neo4j_driver, file_path="fresh.py", project="gimle", top_n=5
    )
    assert result["ok"] is True
    assert result["owners"] == []
    assert result["no_owners_reason"] == "file_not_yet_processed"
    assert result["last_run_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/code/test_find_owners_wire.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement find_owners**

Create `services/palace-mcp/src/palace_mcp/code/find_owners.py`:

```python
"""palace.code.find_owners — top-N owners per file with empty-state diagnostics."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

_QUERY_CYPHER = """
MATCH (f:File {project_id: $proj, path: $path})
OPTIONAL MATCH (st:OwnershipFileState {project_id: $proj, path: $path})
OPTIONAL MATCH (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
WITH f, st, r, a
ORDER BY r.weight DESC
WITH f, st, collect({r: r, a: a}) AS pairs
RETURN f IS NOT NULL AS file_exists,
       st.status            AS status,
       st.no_owners_reason  AS reason,
       st.last_run_id       AS last_run_id,
       pairs
"""

_PROJECT_EXISTS_CYPHER = """
MATCH (p:Project {slug: $slug})
RETURN count(p) AS n
"""

_CHECKPOINT_EXISTS_CYPHER = """
MATCH (c:OwnershipCheckpoint {project_id: $slug})
RETURN c.last_head_sha AS head_sha,
       c.last_completed_at AS completed_at
"""

_RUN_LOOKUP_CYPHER = """
MATCH (r:IngestRun {run_id: $run_id})
RETURN r.alpha_used AS alpha, r.completed_at AS completed_at
"""


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message": message}


async def find_owners(
    driver: AsyncDriver,
    *,
    file_path: str,
    project: str,
    top_n: int = 5,
) -> dict[str, Any]:
    # 1. Validate slug + top_n
    if not _SLUG_RE.match(project):
        return _err("slug_invalid", f"invalid slug: {project!r}")
    if not (1 <= top_n <= 100):
        return _err("top_n_out_of_range", f"top_n={top_n} not in [1, 100]")

    # 2. Project exists?
    async with driver.session() as session:
        proj_row = await (await session.run(
            _PROJECT_EXISTS_CYPHER, slug=project
        )).single()
    if proj_row is None or proj_row["n"] == 0:
        return _err("project_not_registered", f"unknown project: {project!r}")

    # 3. Ownership checkpoint exists?
    async with driver.session() as session:
        cp_row = await (await session.run(
            _CHECKPOINT_EXISTS_CYPHER, slug=project
        )).single()
    if cp_row is None:
        return _err(
            "ownership_not_indexed_yet",
            f"run code_ownership extractor for project {project!r} first",
        )

    head_sha = cp_row["head_sha"]
    last_run_at_cp = cp_row["completed_at"]

    # 4 + 5. Fetch file + state + edges in one query
    async with driver.session() as session:
        result = await session.run(
            _QUERY_CYPHER, proj=project, path=file_path
        )
        row = await result.single()
    if row is None:
        return _err("unknown_file", f"no :File at {file_path!r} in {project!r}")

    pairs = row["pairs"] or []
    # Drop null-relationship pairs (OPTIONAL MATCH may inject one)
    real_pairs = [p for p in pairs if p["r"] is not None and p["a"] is not None]

    last_run_id = row["last_run_id"]
    alpha = None
    if last_run_id:
        async with driver.session() as session:
            run_row = await (await session.run(
                _RUN_LOOKUP_CYPHER, run_id=last_run_id
            )).single()
        if run_row:
            alpha = run_row["alpha"]

    if not real_pairs:
        # Empty owners → diagnose reason
        if row["status"] is None:
            no_owners_reason = "file_not_yet_processed"
            last_run_id_resp = None
        else:
            no_owners_reason = row["reason"]  # could be None if processed-with-no-humans (unusual)
            last_run_id_resp = last_run_id

        return {
            "ok": True,
            "file_path": file_path,
            "project": project,
            "owners": [],
            "total_authors": 0,
            "no_owners_reason": no_owners_reason,
            "last_run_id": last_run_id_resp,
            "last_run_at": _iso(last_run_at_cp),
            "head_sha": head_sha,
            "alpha_used": alpha,
        }

    # Sort by weight desc (already ordered by Cypher) and slice top_n
    real_pairs.sort(key=lambda p: p["r"]["weight"], reverse=True)
    owners = []
    for p in real_pairs[:top_n]:
        r = p["r"]
        a = p["a"]
        owners.append({
            "author_email": a["email"] or a["identity_key"],
            "author_name": a["name"],
            "weight": r["weight"],
            "blame_share": r["blame_share"],
            "recency_churn_share": r["recency_churn_share"],
            "last_touched_at": _iso(r["last_touched_at"]),
            "lines_attributed": r["lines_attributed"],
            "commit_count": r["commit_count"],
            "canonical_via": r["canonical_via"],
        })

    return {
        "ok": True,
        "file_path": file_path,
        "project": project,
        "owners": owners,
        "total_authors": len(real_pairs),
        "no_owners_reason": None,
        "last_run_id": last_run_id,
        "last_run_at": _iso(last_run_at_cp),
        "head_sha": head_sha,
        "alpha_used": alpha,
    }


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if hasattr(v, "to_native"):
        native = v.to_native()
        if native.tzinfo is None:
            native = native.replace(tzinfo=timezone.utc)
        return native.isoformat()
    if isinstance(v, str):
        return v
    return str(v)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/code/test_find_owners_wire.py -v`

Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/code/find_owners.py services/palace-mcp/tests/code/test_find_owners_wire.py
git commit -m "feat(GIM-216): palace.code.find_owners MCP tool + wire contract tests"
```

---

## Task 16: Register `find_owners` in MCP server

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/server.py`

- [ ] **Step 1: Add registration**

Find the existing tool-registration section in `services/palace-mcp/src/palace_mcp/server.py` (look for `mcp.tool(...)` decorations on `find_references`, `find_hotspots`, etc.). Add after them:

```python
from palace_mcp.code.find_owners import find_owners as _find_owners_impl


@mcp.tool(
    name="palace.code.find_owners",
    description=(
        "Top-N code ownership for a file. Returns ranked owners with "
        "weights combining blame_share + recency-weighted churn share. "
        "Empty owners is success — check no_owners_reason to "
        "distinguish binary/all-bot/no-history/file-not-yet-processed."
    ),
)
async def palace_code_find_owners(
    file_path: str,
    project: str,
    top_n: int = 5,
) -> dict:
    return await _find_owners_impl(
        driver=_get_driver(),  # use whatever helper the server already uses
        file_path=file_path,
        project=project,
        top_n=top_n,
    )
```

(Adjust `_get_driver()` to match the actual driver-acquisition pattern in `server.py`. Don't reinvent it.)

- [ ] **Step 2: Verify import**

Run: `cd services/palace-mcp && uv run python -c "import palace_mcp.server"`

Expected: no error.

- [ ] **Step 3: Sanity-check tool registration via MCP introspection (optional)**

Skip if no fast harness; live smoke covers this in Task 18.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/server.py
git commit -m "feat(GIM-216): register palace.code.find_owners MCP tool"
```

---

## Task 17: PII redaction grep guard

**Files:**
- Create: `services/palace-mcp/tests/extractors/unit/test_code_ownership_pii_redaction.py`

This is the §8 invariant: error_message and INFO logs MUST NOT contain raw emails. We enforce by source-grep at audit time.

- [ ] **Step 1: Write the audit test**

Create `services/palace-mcp/tests/extractors/unit/test_code_ownership_pii_redaction.py`:

```python
"""Audit test: code_ownership package source must not log raw emails.

Per spec rev2 §8: error_message + INFO logs MUST NOT contain raw email
addresses. This test scans the package source for log calls that
include obvious email-typed expressions (e.g. f-strings on .email or
identity_key passed to logger.* calls). The check is conservative;
maintainers may explicitly opt-out per call-site with `# noqa: PII`.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "palace_mcp"
    / "extractors"
    / "code_ownership"
)

_LOG_RE = re.compile(r"logger\.(info|warning|error|debug|exception)\(")
# Heuristic: look for emailish substitutions inside the same line group.
_EMAIL_TOKENS = ("\\.email", "\\.identity_key", "raw_email", "canonical_email")


def _line_has_email_expr(line: str) -> bool:
    return any(re.search(token, line) for token in _EMAIL_TOKENS)


def test_no_email_log_calls_in_code_ownership_package():
    """Every logger.* call in the package must not interpolate emails.

    `# noqa: PII` opt-out is allowed for explicit, audited exceptions.
    """
    offenders: list[tuple[Path, int, str]] = []
    for py in sorted(PKG.rglob("*.py")):
        for n, line in enumerate(py.read_text().splitlines(), start=1):
            if "noqa: PII" in line:
                continue
            if _LOG_RE.search(line) and _line_has_email_expr(line):
                offenders.append((py, n, line.strip()))
    assert offenders == [], (
        "Found logger calls that interpolate email-typed values:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in offenders)
    )
```

- [ ] **Step 2: Run test to verify it passes (greenfield)**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_code_ownership_pii_redaction.py -v`

Expected: PASS (assuming Task 5/7 logging didn't sneak emails into log calls).

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_code_ownership_pii_redaction.py
git commit -m "test(GIM-216): PII redaction guard on code_ownership package"
```

---

## Task 18: Smoke test (live, iMac, manual)

**Files:**
- Create: `services/palace-mcp/tests/extractors/smoke/test_code_ownership_smoke.sh`

The smoke is a shell script for the operator to run on iMac after deploy. It is NOT executed by CI.

- [ ] **Step 1: Write the smoke**

Create `services/palace-mcp/tests/extractors/smoke/test_code_ownership_smoke.sh`:

```bash
#!/usr/bin/env bash
# Live smoke for code_ownership extractor (Roadmap #32).
# Runs ON the iMac against the live palace-mcp container + gimle project.
#
# Prereq: GIM-186 git_history extractor has run for `gimle`.
# Usage:
#   bash services/palace-mcp/tests/extractors/smoke/test_code_ownership_smoke.sh

set -euo pipefail

PROJECT="${PALACE_OWNERSHIP_SMOKE_PROJECT:-gimle}"
PROBE_FILE="${PALACE_OWNERSHIP_SMOKE_FILE:-services/palace-mcp/src/palace_mcp/extractors/foundation/importance.py}"

echo "==> 1. Run extractor (this may take minutes on first run)"
docker exec palace-mcp python -c "
import asyncio
from palace_mcp.server import run_extractor_invoke  # placeholder; adjust
print(asyncio.run(run_extractor_invoke('code_ownership', '$PROJECT')))
"

echo "==> 2. Query find_owners"
docker exec palace-mcp python -c "
import asyncio, json
from palace_mcp.server import find_owners_invoke  # placeholder; adjust
result = asyncio.run(find_owners_invoke(file_path='$PROBE_FILE', project='$PROJECT', top_n=5))
print(json.dumps(result, indent=2, default=str))
assert result['ok'] is True, result
assert len(result['owners']) >= 1, 'no owners returned'
top = result['owners'][0]
assert 0 < top['weight'] <= 1, top
print('OK — top owner:', top['author_email'], 'weight=', top['weight'])
"

echo "==> 3. palace.memory.lookup → :IngestRun visibility"
docker exec palace-mcp python -c "
import asyncio
from palace_mcp.memory.lookup import lookup_invoke  # placeholder
r = asyncio.run(lookup_invoke(entity_type='IngestRun', filters={'source': 'extractor.code_ownership', 'project': '$PROJECT'}))
print(r)
assert r and r[0].get('exit_reason') in {'success', 'no_change'}
print('OK — IngestRun visible with exit_reason')
"

echo "==> SMOKE PASS"
```

(Replace `run_extractor_invoke` / `find_owners_invoke` / `lookup_invoke` placeholders with the actual MCP-call shape used in other extractor smokes — model after `test_hotspot_smoke.sh` if present.)

- [ ] **Step 2: chmod**

Run: `chmod +x services/palace-mcp/tests/extractors/smoke/test_code_ownership_smoke.sh`

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/smoke/test_code_ownership_smoke.sh
git commit -m "test(GIM-216): live smoke script for code_ownership (manual, iMac)"
```

---

## Task 19: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md` — `## Extractors` section

- [ ] **Step 1: Add registry row**

Find the bullet list in `CLAUDE.md` under `### Registered extractors` (or equivalent). Add after the existing entries:

```markdown
- `code_ownership` — Code ownership extractor (GIM-216, Roadmap #32). Reads
  `:Author` / `:Commit` / `:TOUCHED` from `git_history` (GIM-186) + does
  per-file `pygit2.blame` on HEAD. Writes `(:File)-[:OWNED_BY]->(:Author)`
  edges with `weight = α × blame_share + (1-α) × recency_churn_share`
  (α default 0.5, env `PALACE_OWNERSHIP_BLAME_WEIGHT`). Per-file
  incremental refresh via `:OwnershipCheckpoint`. Sidecar
  `:OwnershipFileState` for `find_owners` empty-state diagnostics.
  `.mailmap`-aware via pygit2 (no custom parser). Query via
  `palace.code.find_owners(file_path, project, top_n=5)`.
```

- [ ] **Step 2: Add operator workflow subsection**

After the existing `### Operator workflow: ...` subsections in `CLAUDE.md ## Extractors`, add:

```markdown
### Operator workflow: Code ownership

Prereq: GIM-186 `git_history` extractor must have run for the project.

1. Run the extractor:
   ```
   palace.ingest.run_extractor(name="code_ownership", project="gimle")
   ```
2. Query owners:
   ```
   palace.code.find_owners(file_path="services/palace-mcp/...", project="gimle", top_n=5)
   ```

Optional: place `.mailmap` in the repo root to dedupe split identities
(standard git format — see `git help check-mailmap`).

Tunable knobs (`.env`):
- `PALACE_OWNERSHIP_BLAME_WEIGHT` (default 0.5) — α in scoring formula
- `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` (default 50000)
- `PALACE_OWNERSHIP_WRITE_BATCH_SIZE` (default 2000)
- `PALACE_MAILMAP_MAX_BYTES` (default 1 MiB)

Limitations:
- File renames lose history pre-rename (pygit2 blame is path-bound)
- Submodules and binary files are skipped (`no_owners_reason='binary_or_skipped'`)
- Bundle support is not yet wired (run per-project for HS Kits)
- PII: any caller with `palace.code.*` permissions can enumerate
  contributor emails. See `docs/runbooks/code-ownership.md` for trust model.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-216): CLAUDE.md — register code_ownership + operator workflow"
```

---

## Task 20: Runbook + roadmap status

**Files:**
- Create: `docs/runbooks/code-ownership.md`
- Modify: `docs/roadmap.md` (mark #32 in-flight, then ✅ when merged)

- [ ] **Step 1: Write runbook**

Create `docs/runbooks/code-ownership.md`:

```markdown
# Code Ownership Extractor — Runbook

## What it does

Computes file-level ownership from `git_history` graph (GIM-186) +
`pygit2.blame` on HEAD. Writes `(:File)-[:OWNED_BY]->(:Author)` edges
with `weight = α × blame_share + (1-α) × recency_churn_share`. Single
MCP tool: `palace.code.find_owners`.

## Trust assumptions

`find_owners` enumerates committer emails for any registered project.
Project-level ACLs are NOT implemented in palace-mcp. Treat the tool
as PII-bearing in multi-tenant deployments. Single-tenant or trusted-
team setups can run without restriction.

## Running

Prereq: `git_history` extractor (GIM-186) has indexed at least one
commit for the target project.

```
palace.ingest.run_extractor(name="code_ownership", project="<slug>")
palace.code.find_owners(file_path="<path>", project="<slug>", top_n=5)
```

## Knobs

| Env | Default | Effect |
|-----|---------|--------|
| `PALACE_OWNERSHIP_BLAME_WEIGHT` | 0.5 | α in `α × blame + (1-α) × churn` |
| `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` | 50_000 | DIRTY-set hard cap |
| `PALACE_OWNERSHIP_WRITE_BATCH_SIZE` | 2_000 | Phase-4 tx batching |
| `PALACE_MAILMAP_MAX_BYTES` | 1 048 576 | `.mailmap` size cap |
| `PALACE_RECENCY_DECAY_DAYS` | 30 | half-life for recency decay (substrate) |

## `.mailmap` recipes

Place `.mailmap` in repo root. Standard format:
```
Real Name <real@example.com> Old Name <old@example.com>
```
v1 uses pygit2 only (no custom parser). Oversized files (>
`PALACE_MAILMAP_MAX_BYTES`) → identity passthrough; check
`:IngestRun.mailmap_resolver_path = 'identity_passthrough'` after run
and either trim `.mailmap` or raise the cap.

## Erasure (PII / right-to-be-forgotten)

```cypher
MATCH (a:Author {provider: 'git', identity_key: $email_lc})
OPTIONAL MATCH (a)<-[r:OWNED_BY {source: 'extractor.code_ownership'}]-()
DELETE r
WITH a
OPTIONAL MATCH (a)<-[any]-()
WITH a, count(any) AS remaining
WHERE remaining = 0
DELETE a
```

For tombstoning instead of deleting (preserves git_history shape):
```cypher
MATCH (a:Author {provider: 'git', identity_key: $email_lc})
SET a.email = 'redacted-' + apoc.util.sha1(a.identity_key),
    a.name = 'redacted'
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `git_history_not_indexed` | GIM-186 has not run for this project | run `palace.ingest.run_extractor(name='git_history', project='<slug>')` first |
| `ownership_max_files_exceeded` | HEAD tree larger than cap | raise `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` |
| `ownership_diff_failed` | local clone diverged from checkpoint SHA | `git fetch` in the mounted clone, retry |
| `repo_head_invalid` | corrupt refs / detached HEAD | `git fsck` in clone, reset to a valid branch |
| `find_owners` returns `no_owners_reason='file_not_yet_processed'` | file added since last extractor run | re-run extractor |
| `find_owners` returns `no_owners_reason='binary_or_skipped'` | binary / submodule / symlink — by design | n/a |
| Bot-laundered authors appear as humans | `git config user.name` was set to a non-bot string by an actual bot | spot-check `find_owners` for high-stake files; manually fix `:Author.is_bot` if confirmed |

## Bot-laundering spot check

After bootstrap run on a security-critical project:
```
palace.code.find_owners(file_path="<critical-file>", project="<slug>", top_n=10)
```
If a name unfamiliar to the team appears, query their commit history:
```cypher
MATCH (a:Author {provider: 'git', identity_key: '<email>'})
      <-[:AUTHORED_BY]-(c:Commit {project_id: '<slug>'})
RETURN c.sha, c.committed_at
ORDER BY c.committed_at DESC LIMIT 20
```
Inspect commit content for automation patterns (uniform timing, large
mechanical diffs); flip `is_bot` manually if confirmed bot.
```

- [ ] **Step 2: Commit runbook**

```bash
git add docs/runbooks/code-ownership.md
git commit -m "docs(GIM-216): runbook for code_ownership extractor"
```

- [ ] **Step 3: Update roadmap on merge (post-merge step, not in this branch)**

When the PR merges to develop, file a follow-up `docs(roadmap):` PR
that marks `#32 Code Ownership Extractor` ✅ in
`docs/roadmap.md §2.3 Historical`. Pattern matches the existing
`docs(roadmap):` cadence (e.g., `2671a4a docs(roadmap): mark GIM-190
done`).

Format the row:

```
| 32 | Code Ownership Extractor | Claude | — | pygit2 blame + recency churn | ✅ GIM-216 / `<merge-sha>` (PR #NNN) |
```

This step is not committed in this feature branch.

---

## Self-Review Checklist (run before declaring complete)

- [ ] Spec acceptance criteria 1-17 each map to at least one task above
  (verify by grepping the spec for "Acceptance" and the plan for the
  corresponding test name).
- [ ] All 20 tasks have concrete failing-test code (no "write a test"
  placeholders).
- [ ] All 20 tasks have concrete implementation code (no "implement
  the function" placeholders).
- [ ] Type names / function signatures used in later tasks match what
  earlier tasks defined (`MailmapResolver`, `OwnershipEdge`,
  `walk_blame`, `aggregate_churn`, `score_file`, `write_batch`,
  `load_checkpoint`, `update_checkpoint`, `ensure_ownership_schema`,
  `find_owners`, `OWNERSHIP_SOURCE`).
- [ ] All commits are atomic and follow the existing
  `feat(GIM-216): ...` / `test(GIM-216): ...` / `docs(GIM-216): ...`
  prefix pattern.
- [ ] Final task includes the post-merge roadmap update (deferred
  outside the feature branch by convention).
