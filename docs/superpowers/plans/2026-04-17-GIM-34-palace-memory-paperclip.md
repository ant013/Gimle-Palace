# Palace Memory — paperclip slice (N+0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` within your own run. Steps use checkbox (`- [x]`) syntax. Formal paperclip reassign is mandatory on every inter-agent handoff — `@`-mentions alone do not wake agents reliably (see Board memory `reference_paperclip_inbox_lite.md`).

**Goal:** Deliver the first read-capability of `palace-memory`: external MCP clients can query paperclip project history (issues + comments + agents) via two new MCP tools backed by plain Neo4j with idempotent ingest.

**Architecture:** Single-PR slice cut from `origin/develop`. New `memory/` + `ingest/` Python subpackages in `services/palace-mcp`. Paperclip HTTPS API → transform → `MERGE` upsert + `palace_last_seen_at` GC. Two new MCP tools registered on the existing FastMCP server mounted at `/mcp`. Tools read via `session.execute_read()`, ingest writes via `session.execute_write()`. Three timestamps on every node (`source_created_at`, `source_updated_at`, `palace_last_seen_at`). No new compose services. Zero-test-time net-new Docker infrastructure.

**Tech Stack:** Python 3.12, FastAPI, FastMCP (`mcp>=1.6`), Neo4j async driver 5.x, Pydantic v2, httpx, python-json-logger, pytest-asyncio, uv, ruff, mypy --strict.

**Spec:** `docs/superpowers/specs/2026-04-17-palace-memory-paperclip-slice.md` @ `origin/main` HEAD `5a152f9`. Approved by CTO 2026-04-17 06:23 UTC (GIM-33). All 9 MUST-FIX additions already in spec.

**Source branch:** `feature/GIM-34-palace-memory-paperclip` cut from `origin/develop`.

**Target branch:** `develop`. Squash-merge on APPROVE.

---

## Phase 0 — Prereqs (Board)

### Step 0.1: Provision ingest API token

**Owner:** Board (human or board-user script).
**Files:** none in repo; env only.
**Depends on:** nothing.

- [x] Generate a **board-scope static token** for ingest use (distinct from agent run-scoped JWTs). One of:
  - `paperclipai agent local-cli` targeting a dedicated service agent (preferred for audit trail), OR
  - reuse the existing `PAPERCLIP_API_KEY` (the board-user token Board already mints).
- [x] Store on iMac as `PAPERCLIP_INGEST_API_KEY` in the docker-compose environment for `palace-mcp` (add to `/Users/Shared/Ios/Gimle-Palace/.env` on iMac).
- [x] Also expose `PAPERCLIP_API_URL=https://paperclip.ant013.work` and `PAPERCLIP_COMPANY_ID=9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64` in the same `.env`.
- [x] Verify reachability from inside container: `docker compose exec palace-mcp sh -c 'wget -qO- -S --header "Authorization: Bearer $PAPERCLIP_INGEST_API_KEY" "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues" 2>&1 | head -5'` → expect HTTP 200.

**Acceptance:** Container has all three env vars; HTTP 200 on a manual API probe from inside container.

---

## Phase 1 — Issue + Plan + Plan Review (CTO → TechnicalWriter → CodeReviewer)

### Step 1.1: CTO creates issue

**Owner:** CTO.
**Depends on:** Step 0.1 done.

- [x] Create paperclip issue titled `palace.memory paperclip slice (N+0) — implementation`.
- [x] Body = this plan file's contents (copy the whole plan body, from "# Palace Memory — paperclip slice (N+0) Implementation Plan" to the end — leave `GIM-34` placeholders in the body to be replaced with the real key after paperclip assigns it).
- [x] After issue creation, CTO runs one edit pass replacing `GIM-34` with the assigned key (e.g., `GIM-34`) in the issue body.
- [x] Initial assignee = TechnicalWriter. Status = `todo`.

**Acceptance:** Issue exists, key substituted, assigned to TechnicalWriter, status todo.

### Step 1.2: TechnicalWriter cuts branch + mirrors plan

**Owner:** TechnicalWriter.
**Depends on:** Step 1.1.
**Files:**
- Branch: `feature/GIM-34-palace-memory-paperclip` (from `origin/develop`)
- Create: `docs/superpowers/plans/2026-04-17-GIM-34-palace-memory-paperclip.md` (copy from `origin/main:docs/superpowers/plans/2026-04-17-GIM-34-palace-memory-paperclip.md`, substituting `GIM-34` with the real key).

- [x] `git fetch origin && git checkout -b feature/GIM-34-palace-memory-paperclip origin/develop`
- [x] Verify clean tree: `git status` → clean.
- [x] Copy the plan file from `main` to the feature branch, substituting `GIM-34`:

```bash
git show origin/main:docs/superpowers/plans/2026-04-17-GIM-34-palace-memory-paperclip.md \
  | sed 's/GIM-34/GIM-34/g' > docs/superpowers/plans/2026-04-17-GIM-34-palace-memory-paperclip.md
```

(Replace `34` with the actual key assigned at Step 1.1.)

- [x] Commit:

```bash
git add docs/superpowers/plans/2026-04-17-GIM-34-palace-memory-paperclip.md
git commit -m "docs(plans): add palace-memory paperclip slice plan (GIM-34)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
git push -u origin feature/GIM-34-palace-memory-paperclip
```

- [x] **Formal reassign to CodeReviewer** with status=todo for plan review (PATCH via paperclip API or UI — @-mention alone does not wake CR reliably; see `reference_paperclip_inbox_lite.md`).

**Acceptance:** Branch pushed, plan file on branch, CR assigned, status todo.

### Step 1.3: CodeReviewer plan-first review

**Owner:** CodeReviewer.
**Depends on:** Step 1.2.
**Files:** read-only.

Verify the 4 plan-first compliance items (from `paperclips/fragments/shared/fragments/plan-first-review.md`):

- [x] Plan file exists at `docs/superpowers/plans/2026-04-17-GIM-34-palace-memory-paperclip.md` on branch `feature/GIM-34-palace-memory-paperclip` — cite exact commit SHA.
- [x] PR description will reference this plan file — note as requirement for Phase 3 (PR not yet opened).
- [x] All `- [x]` checkboxes are actionable and present — scan for `TODO` / `TBD` / placeholder text.
- [x] Plan not diverging from scope in spec — cross-check Phase 2 against spec §5/§6/§7/§9 sections.

Then verify plan completeness:

- [x] Every file to be created/modified appears in exactly one step.
- [x] Each implementation step has acceptance criteria.
- [x] Out-of-scope items from spec §10 do not appear in plan (no Graphiti, no NL query, no GitHub extractor, etc.).
- [x] All 9 MUST-FIX from GIM-33 review appear as explicit acceptance items (verify each: Cypher parameterization, `related` typing, `execute_read`, httpx + python-json-logger deps, `PAPERCLIP_INGEST_API_KEY`, idempotency note, mcp/mcp[cli] split, `mypy --strict` in acceptance, `author_name: str | None`).

Post verdict comment per spec §9 format:

```
## Plan Review — APPROVE / REQUEST CHANGES

### Plan-first compliance
- [x|[ ]] item 1 ...
...

### Spec coverage
- [x] spec §5 covered by Steps 2.4–2.6
- [x] spec §6 covered by Steps 2.7–2.10
...

### CRITICAL / WARNING / NOTE
... findings ...

### Verdict: APPROVE | REQUEST CHANGES
```

- [x] On APPROVE, formal reassign back to MCPEngineer with status=todo for Phase 2.
- [x] On REQUEST CHANGES, formal reassign to CTO with status=todo; CTO revises plan, loops to Step 1.3.

**Acceptance:** CR verdict posted, assignee + status correctly set for next phase.

---

## Phase 2 — Implementation (MCPEngineer)

All Phase 2 steps happen on branch `feature/GIM-34-palace-memory-paperclip`. MCPEngineer applies internal TDD (write failing test → run → implement → run → commit) within each step.

### Step 2.1: Dependency updates

**Owner:** MCPEngineer.
**Files:**
- Modify: `services/palace-mcp/pyproject.toml`

- [x] Read current `pyproject.toml` on branch (has `mcp[cli]>=1.6` in `[project].dependencies`, `httpx>=0.28.0` in dev).
- [x] Change `[project].dependencies`:

```toml
[project]
name = "palace-mcp"
version = "0.1.0"
description = "Palace MCP Service"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]>=0.115.0",
    "mcp>=1.6",
    "neo4j>=5.0",
    "pydantic>=2.0.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.28.0",
    "python-json-logger>=2.0.7",
]
```

- [x] Move `mcp[cli]` to `[tool.uv].dev-dependencies`:

```toml
[tool.uv]
dev-dependencies = [
    "ruff>=0.9.0",
    "mypy>=1.15.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.25.0",
    "mcp[cli]>=1.6",
]
```

(Removed `httpx>=0.28.0` from dev — it's runtime now.)

- [x] Regenerate lockfile: `cd services/palace-mcp && uv sync`.
- [x] Verify: `uv run python -c "import httpx, pythonjsonlogger, mcp; print('OK')"` → prints OK.
- [x] Commit:

```bash
git add services/palace-mcp/pyproject.toml services/palace-mcp/uv.lock
git commit -m "chore(palace-mcp): add runtime deps (httpx, python-json-logger), move mcp[cli] to dev (GIM-34)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

**Acceptance:** `uv sync` green, imports OK, committed.

### Step 2.2: Package scaffold

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/__init__.py` (empty)
- Create: `services/palace-mcp/src/palace_mcp/ingest/__init__.py` (empty)
- Create: `services/palace-mcp/tests/memory/__init__.py` (empty)
- Create: `services/palace-mcp/tests/ingest/__init__.py` (empty)

- [x] Create empty `__init__.py` in each new dir (package markers).
- [x] `uv run ruff check` + `uv run mypy --strict` — clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/memory services/palace-mcp/src/palace_mcp/ingest services/palace-mcp/tests/memory services/palace-mcp/tests/ingest
git commit -m "chore(palace-mcp): scaffold memory/ and ingest/ subpackages (GIM-34)"
```

**Acceptance:** lint clean, typecheck clean, committed.

### Step 2.3: JSON logging setup

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/logging_setup.py`
- Create: `services/palace-mcp/tests/memory/test_logging_setup.py`

- [x] TDD — write failing test first at `tests/memory/test_logging_setup.py`:

```python
import json
import logging

from palace_mcp.memory.logging_setup import configure_json_logging


def test_json_logger_emits_structured_record(caplog: pytest.LogCaptureFixture) -> None:
    configure_json_logging()
    logger = logging.getLogger("palace_mcp.test")
    with caplog.at_level(logging.INFO, logger="palace_mcp.test"):
        logger.info("ingest.start", extra={"source": "paperclip", "run_id": "abc"})
    record = caplog.records[-1]
    assert record.msg == "ingest.start"
    assert getattr(record, "source") == "paperclip"
    assert getattr(record, "run_id") == "abc"
```

Add `import pytest` at top. Run: `cd services/palace-mcp && uv run pytest tests/memory/test_logging_setup.py -v` → expected FAIL (`configure_json_logging` missing).

- [x] Implement `logging_setup.py`:

```python
"""JSON structured logging configuration.

Attach `pythonjsonlogger.jsonlogger.JsonFormatter` to stdout. Called once
at service startup (or ingest CLI startup) before any log.info().
"""

import logging
import sys

from pythonjsonlogger import jsonlogger


def configure_json_logging(level: int = logging.INFO) -> None:
    """Replace root logger handlers with a JSON stdout formatter.

    Events emitted with `logger.info("event.name", extra={...})` become
    `{"message":"event.name", ...extra fields}` on stdout.
    """
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level", "name": "logger", "message": "event"},
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
```

- [x] Run test → PASS.
- [x] `uv run ruff check` + `uv run mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/memory/logging_setup.py services/palace-mcp/tests/memory/test_logging_setup.py
git commit -m "feat(palace-mcp): JSON structured logging helper (GIM-34)"
```

**Acceptance:** test green, lint/mypy clean, commit.

### Step 2.4: Pydantic schemas

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/schema.py`
- Create: `services/palace-mcp/tests/memory/test_schema.py`

- [x] TDD — write failing test `tests/memory/test_schema.py`:

```python
import pytest
from pydantic import ValidationError

from palace_mcp.memory.schema import (
    HealthResponse,
    LookupRequest,
    LookupResponse,
    LookupResponseItem,
)


def test_lookup_request_rejects_unknown_entity_type() -> None:
    with pytest.raises(ValidationError):
        LookupRequest(entity_type="Bogus")  # type: ignore[arg-type]


def test_lookup_request_limit_bounds() -> None:
    LookupRequest(entity_type="Issue", limit=1)
    LookupRequest(entity_type="Issue", limit=100)
    with pytest.raises(ValidationError):
        LookupRequest(entity_type="Issue", limit=0)
    with pytest.raises(ValidationError):
        LookupRequest(entity_type="Issue", limit=101)


def test_lookup_response_item_related_accepts_none_dict_list() -> None:
    item = LookupResponseItem(
        id="abc",
        type="Comment",
        properties={"body": "..."},
        related={"author": None, "issue": {"id": "i1"}, "comments": [{"id": "c1"}]},
    )
    assert item.related["author"] is None
    assert isinstance(item.related["issue"], dict)
    assert isinstance(item.related["comments"], list)


def test_health_response_shape() -> None:
    h = HealthResponse(
        neo4j_reachable=True,
        entity_counts={"Issue": 31, "Comment": 52, "Agent": 12},
        last_ingest_started_at="2026-04-17T06:00:00+00:00",
        last_ingest_finished_at="2026-04-17T06:00:02+00:00",
        last_ingest_duration_ms=2000,
        last_ingest_errors=[],
    )
    assert h.entity_counts["Issue"] == 31
```

Run: `uv run pytest tests/memory/test_schema.py -v` → FAIL (imports missing).

- [x] Implement `schema.py`:

```python
"""Pydantic v2 schemas for palace-memory MCP tools.

Types here are the wire contract between MCP clients and the palace-mcp
service. Keep them stable — changes are breaking.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["Issue", "Comment", "Agent"]


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)
    order_by: Literal["source_updated_at", "source_created_at"] = "source_updated_at"


class LookupResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: EntityType
    properties: dict[str, Any]
    related: dict[str, dict[str, Any] | list[dict[str, Any]] | None] = Field(default_factory=dict)


class LookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LookupResponseItem]
    total_matched: int
    query_ms: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    neo4j_reachable: bool
    entity_counts: dict[str, int]
    last_ingest_started_at: str | None = None
    last_ingest_finished_at: str | None = None
    last_ingest_duration_ms: int | None = None
    last_ingest_errors: list[str] = Field(default_factory=list)
```

- [x] Run test → PASS.
- [x] `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/memory/schema.py services/palace-mcp/tests/memory/test_schema.py
git commit -m "feat(palace-mcp): memory tool schemas (GIM-34)"
```

**Acceptance:** tests green, types exposed for downstream modules.

### Step 2.5: Paperclip API client

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/ingest/paperclip_client.py`
- Create: `services/palace-mcp/tests/ingest/test_paperclip_client.py`

- [x] TDD — test with `httpx.MockTransport`:

```python
import httpx
import pytest

from palace_mcp.ingest.paperclip_client import PaperclipClient


@pytest.mark.asyncio
async def test_list_issues_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.url.path == "/api/companies/co-1/issues"
        return httpx.Response(200, json={"issues": [{"id": "i1", "identifier": "GIM-1"}]})

    transport = httpx.MockTransport(handler)
    async with PaperclipClient(base_url="https://pc", token="test-token", company_id="co-1", transport=transport) as client:
        issues = await client.list_issues()
    assert issues == [{"id": "i1", "identifier": "GIM-1"}]


@pytest.mark.asyncio
async def test_list_comments_for_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/issues/i1/comments"
        return httpx.Response(200, json=[{"id": "c1", "body": "hi"}])

    transport = httpx.MockTransport(handler)
    async with PaperclipClient(base_url="https://pc", token="test-token", company_id="co-1", transport=transport) as client:
        comments = await client.list_comments_for_issue("i1")
    assert comments == [{"id": "c1", "body": "hi"}]
```

Run: `uv run pytest tests/ingest/test_paperclip_client.py -v` → FAIL.

- [x] Implement `paperclip_client.py`:

```python
"""Async HTTP client for paperclip's public API.

Reads issues, comments, agents — that's the entire surface needed by
this slice. Separate module so the transport can be swapped in tests
via `httpx.MockTransport`.
"""

from types import TracebackType
from typing import Any, Self

import httpx


class PaperclipClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        company_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._company_id = company_id
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
            timeout=timeout,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def list_issues(self) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/api/companies/{self._company_id}/issues")
        resp.raise_for_status()
        data = resp.json()
        # API returns either {"issues":[...]} or a bare list depending on endpoint version.
        if isinstance(data, dict):
            issues = data.get("issues", [])
            return list(issues) if isinstance(issues, list) else []
        if isinstance(data, list):
            return data
        return []

    async def list_comments_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/api/issues/{issue_id}/comments")
        resp.raise_for_status()
        data = resp.json()
        return list(data) if isinstance(data, list) else []

    async def list_agents(self) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/api/companies/{self._company_id}/agents")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            agents = data.get("agents", [])
            return list(agents) if isinstance(agents, list) else []
        if isinstance(data, list):
            return data
        return []
```

- [x] Run tests → PASS.
- [x] `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/ingest/paperclip_client.py services/palace-mcp/tests/ingest/test_paperclip_client.py
git commit -m "feat(palace-mcp): paperclip async HTTP client (GIM-34)"
```

**Acceptance:** tests green, client handles both `{issues: [...]}` and bare list response shapes.

### Step 2.6: Transform module

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/ingest/transform.py`
- Create: `services/palace-mcp/tests/ingest/test_transform.py`

- [x] TDD — test first:

```python
from palace_mcp.ingest.transform import (
    transform_agent,
    transform_comment,
    transform_issue,
)


def test_transform_issue_maps_expected_fields() -> None:
    pc_issue = {
        "id": "uuid-1",
        "identifier": "GIM-1",
        "title": "T",
        "description": "D",
        "status": "done",
        "createdAt": "2026-04-10T00:00:00Z",
        "updatedAt": "2026-04-17T00:00:00Z",
        "assigneeAgentId": "agent-1",
    }
    out = transform_issue(pc_issue, run_started="2026-04-17T06:00:00+00:00")
    assert out["id"] == "uuid-1"
    assert out["key"] == "GIM-1"
    assert out["source"] == "paperclip"
    assert out["source_created_at"] == "2026-04-10T00:00:00Z"
    assert out["source_updated_at"] == "2026-04-17T00:00:00Z"
    assert out["palace_last_seen_at"] == "2026-04-17T06:00:00+00:00"
    assert out["assignee_agent_id"] == "agent-1"


def test_transform_comment_handles_null_author() -> None:
    pc_comment = {
        "id": "c1",
        "body": "hi",
        "issueId": "uuid-1",
        "authorAgentId": None,
        "createdAt": "2026-04-17T05:00:00Z",
    }
    out = transform_comment(pc_comment, run_started="2026-04-17T06:00:00+00:00")
    assert out["author_agent_id"] is None
    assert out["issue_id"] == "uuid-1"
    assert out["source_updated_at"] == "2026-04-17T05:00:00Z"  # fallback to createdAt


def test_transform_agent_basic() -> None:
    pc_agent = {
        "id": "a1",
        "name": "CodeReviewer",
        "urlKey": "codereviewer",
        "role": "Review adversary.",
        "createdAt": "2026-04-13T00:00:00Z",
        "updatedAt": "2026-04-17T00:00:00Z",
    }
    out = transform_agent(pc_agent, run_started="2026-04-17T06:00:00+00:00")
    assert out["name"] == "CodeReviewer"
    assert out["url_key"] == "codereviewer"
```

Run → FAIL.

- [x] Implement `transform.py`:

```python
"""Map paperclip API DTOs to Neo4j node property dicts.

Pure functions — no I/O. Each returns a dict ready for Cypher UNWIND.
Timestamp fallback: if paperclip omits `updatedAt`, use `createdAt`
so `source_updated_at` is always populated (required by schema).
"""

from typing import Any

SOURCE = "paperclip"


def _ts(record: dict[str, Any], key: str, fallback_key: str = "createdAt") -> str:
    val = record.get(key) or record.get(fallback_key)
    if not isinstance(val, str):
        raise ValueError(f"paperclip record missing {key}/{fallback_key}: {record.get('id')}")
    return val


def transform_issue(issue: dict[str, Any], *, run_started: str) -> dict[str, Any]:
    return {
        "id": issue["id"],
        "key": issue.get("identifier") or issue.get("key") or "",
        "title": issue.get("title") or "",
        "description": issue.get("description") or "",
        "status": issue.get("status") or "",
        "source": SOURCE,
        "source_created_at": _ts(issue, "createdAt"),
        "source_updated_at": _ts(issue, "updatedAt"),
        "palace_last_seen_at": run_started,
        "assignee_agent_id": issue.get("assigneeAgentId"),
    }


def transform_comment(comment: dict[str, Any], *, run_started: str) -> dict[str, Any]:
    return {
        "id": comment["id"],
        "body": comment.get("body") or "",
        "issue_id": comment.get("issueId") or "",
        "author_agent_id": comment.get("authorAgentId"),
        "source": SOURCE,
        "source_created_at": _ts(comment, "createdAt"),
        "source_updated_at": _ts(comment, "updatedAt"),
        "palace_last_seen_at": run_started,
    }


def transform_agent(agent: dict[str, Any], *, run_started: str) -> dict[str, Any]:
    return {
        "id": agent["id"],
        "name": agent.get("name") or "",
        "url_key": agent.get("urlKey") or "",
        "role": agent.get("role") or "",
        "source": SOURCE,
        "source_created_at": _ts(agent, "createdAt"),
        "source_updated_at": _ts(agent, "updatedAt"),
        "palace_last_seen_at": run_started,
    }
```

- [x] Tests green. `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/ingest/transform.py services/palace-mcp/tests/ingest/test_transform.py
git commit -m "feat(palace-mcp): paperclip DTO → Neo4j props transform (GIM-34)"
```

**Acceptance:** all three entity types transform; timestamp fallback tested; commit.

### Step 2.7: Cypher queries + schema constraints

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Create: `services/palace-mcp/src/palace_mcp/memory/constraints.py`
- Create: `services/palace-mcp/tests/memory/test_constraints.py` (if testcontainers not available, mark as integration-skipped by default)

- [x] Create `cypher.py` as a module of string constants — all Cypher queries live here in one place for audit:

```python
"""Cypher query strings. Parameters use $name syntax — never string
interpolation. Keys are whitelisted in filters.py; values arrive as
named parameters only.
"""

# --- Constraints (idempotent MERGE-safe uniqueness) ---
CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT issue_id IF NOT EXISTS FOR (i:Issue) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE",
]

# --- Upserts (idempotent — safe to re-run on transient failure retry) ---
UPSERT_AGENTS = """
UNWIND $batch AS row
MERGE (a:Agent {id: row.id})
SET a.name                 = row.name,
    a.url_key              = row.url_key,
    a.role                 = row.role,
    a.source               = 'paperclip',
    a.source_created_at    = row.source_created_at,
    a.source_updated_at    = row.source_updated_at,
    a.palace_last_seen_at  = row.palace_last_seen_at
"""

UPSERT_ISSUES = """
UNWIND $batch AS row
MERGE (i:Issue {id: row.id})
SET i.key                  = row.key,
    i.title                = row.title,
    i.description          = row.description,
    i.status               = row.status,
    i.source               = 'paperclip',
    i.source_created_at    = row.source_created_at,
    i.source_updated_at    = row.source_updated_at,
    i.palace_last_seen_at  = row.palace_last_seen_at
WITH i, row
OPTIONAL MATCH (i)-[old:ASSIGNED_TO]->()
DELETE old
WITH i, row
WHERE row.assignee_agent_id IS NOT NULL
MATCH (a:Agent {id: row.assignee_agent_id})
MERGE (i)-[:ASSIGNED_TO]->(a)
"""

UPSERT_COMMENTS = """
UNWIND $batch AS row
MERGE (c:Comment {id: row.id})
SET c.body                 = row.body,
    c.source               = 'paperclip',
    c.source_created_at    = row.source_created_at,
    c.source_updated_at    = row.source_updated_at,
    c.palace_last_seen_at  = row.palace_last_seen_at
WITH c, row
OPTIONAL MATCH (c)-[oldOn:ON]->()
DELETE oldOn
WITH c, row
MATCH (i:Issue {id: row.issue_id})
MERGE (c)-[:ON]->(i)
WITH c, row
OPTIONAL MATCH (c)-[oldAuth:AUTHORED_BY]->()
DELETE oldAuth
WITH c, row
WHERE row.author_agent_id IS NOT NULL
MATCH (a:Agent {id: row.author_agent_id})
MERGE (c)-[:AUTHORED_BY]->(a)
"""

# --- GC (run only after clean-success upserts) ---
GC_BY_LABEL = """
MATCH (n:{label}) WHERE n.source = 'paperclip' AND n.palace_last_seen_at < $cutoff
DETACH DELETE n
"""  # {label} substituted by enum, NOT user input. Labels hardcoded.

# --- IngestRun meta-node (read by palace.memory.health) ---
CREATE_INGEST_RUN = """
CREATE (r:IngestRun {
    id: $id,
    source: $source,
    started_at: $started_at,
    finished_at: null,
    duration_ms: null,
    errors: []
})
"""

FINALIZE_INGEST_RUN = """
MATCH (r:IngestRun {id: $id})
SET r.finished_at = $finished_at,
    r.duration_ms = $duration_ms,
    r.errors      = $errors
"""

LATEST_INGEST_RUN = """
MATCH (r:IngestRun {source: $source})
RETURN r
ORDER BY r.started_at DESC
LIMIT 1
"""

# --- Entity counts (health) ---
ENTITY_COUNTS = """
CALL () {
    MATCH (n:Issue) RETURN 'Issue' AS type, count(n) AS count
    UNION ALL
    MATCH (n:Comment) RETURN 'Comment' AS type, count(n) AS count
    UNION ALL
    MATCH (n:Agent) RETURN 'Agent' AS type, count(n) AS count
}
RETURN type, count
"""
```

- [x] Create `constraints.py`:

```python
"""Idempotent constraint assertion. Called from FastAPI lifespan or
before first ingest. Safe to run repeatedly (`IF NOT EXISTS` guard).
"""

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import CREATE_CONSTRAINTS


async def ensure_constraints(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        for stmt in CREATE_CONSTRAINTS:
            await session.run(stmt)  # type: ignore[func-returns-value]
```

- [x] Tests for `cypher.py` — parameterization audit using AST introspection (detects f-string constants and `.format()` calls on query constants; does NOT check for raw `{` which is valid Cypher syntax for property maps; `GC_BY_LABEL` is excluded — its `.format(label=...)` uses a closed tuple `("Issue", "Comment", "Agent")`, not user input):

```python
# tests/memory/test_cypher_parameterization.py
import ast
import inspect

from palace_mcp.memory import cypher

_QUERY_CONSTANTS = [
    name for name, val in vars(cypher).items()
    if isinstance(val, str) and name.isupper() and "MATCH" in val
]


def test_no_python_format_interpolation() -> None:
    """Query constants must not use .format() or f-string interpolation."""
    src = inspect.getsource(cypher)
    for name in _QUERY_CONSTANTS:
        assert f"{name}.format" not in src, f"{name} uses .format()"
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets)
            and isinstance(node.value, ast.JoinedStr)
        ):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            raise AssertionError(f"Query constant(s) {names} use f-string")


def test_queries_use_dollar_params() -> None:
    """All user-value slots in query constants must use $name parameters."""
    for name in _QUERY_CONSTANTS:
        q = getattr(cypher, name)
        # Static queries with no params (e.g. ENTITY_COUNTS) are OK
        if "$" not in q and "%" in q:
            raise AssertionError(f"{name} uses %-format instead of $param")
```

Run → PASS (assuming queries are clean — this is a regression guard).

- [x] `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/memory/cypher.py services/palace-mcp/src/palace_mcp/memory/constraints.py services/palace-mcp/tests/memory/test_cypher_parameterization.py
git commit -m "feat(palace-mcp): Cypher queries + constraint assertion (GIM-34)"
```

**Acceptance:** cypher module exports all 7 Cypher constants; constraint function idempotent; parameterization guard verifies no Python interpolation on Cypher constants.

### Step 2.8: Ingest orchestrator + CLI

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/ingest/paperclip.py` (CLI entrypoint)
- Create: `services/palace-mcp/src/palace_mcp/ingest/runner.py` (orchestration logic — pure function, testable)
- Create: `services/palace-mcp/tests/ingest/test_runner.py`

- [x] Implement `runner.py` (extracted from CLI to keep I/O and orchestration separable):

```python
"""Ingest orchestrator. Fetches from paperclip, transforms, upserts via
managed write transactions (idempotent), GC on clean success.

`run_ingest` is the single entry point. Accepts a configured
PaperclipClient and an AsyncDriver — construction happens in the CLI.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.transform import transform_agent, transform_comment, transform_issue
from palace_mcp.memory import cypher

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _write_upsert_agents(tx: AsyncManagedTransaction, batch: list[dict[str, Any]]) -> None:
    await tx.run(cypher.UPSERT_AGENTS, batch=batch)


async def _write_upsert_issues(tx: AsyncManagedTransaction, batch: list[dict[str, Any]]) -> None:
    await tx.run(cypher.UPSERT_ISSUES, batch=batch)


async def _write_upsert_comments(tx: AsyncManagedTransaction, batch: list[dict[str, Any]]) -> None:
    await tx.run(cypher.UPSERT_COMMENTS, batch=batch)


async def _write_gc(tx: AsyncManagedTransaction, *, label: str, cutoff: str) -> None:
    # Label is whitelisted (Issue|Comment|Agent) — not user input.
    query = cypher.GC_BY_LABEL.format(label=label)
    await tx.run(query, cutoff=cutoff)


async def _write_create_ingest_run(tx: AsyncManagedTransaction, *, run_id: str, started_at: str, source: str) -> None:
    await tx.run(cypher.CREATE_INGEST_RUN, id=run_id, started_at=started_at, source=source)


async def _write_finalize_ingest_run(
    tx: AsyncManagedTransaction,
    *,
    run_id: str,
    finished_at: str,
    duration_ms: int,
    errors: list[str],
) -> None:
    await tx.run(
        cypher.FINALIZE_INGEST_RUN,
        id=run_id,
        finished_at=finished_at,
        duration_ms=duration_ms,
        errors=errors,
    )


async def run_ingest(*, client: PaperclipClient, driver: AsyncDriver, source: str = "paperclip") -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    started_at = _utcnow_iso()
    started_monotonic = time.monotonic()
    errors: list[str] = []

    logger.info("ingest.start", extra={"source": source, "run_id": run_id})

    async with driver.session() as session:
        await session.execute_write(_write_create_ingest_run, run_id=run_id, started_at=started_at, source=source)

    try:
        issues_raw = await client.list_issues()
        agents_raw = await client.list_agents()
        logger.info("ingest.fetch.issues", extra={"count": len(issues_raw), "source": source})
        logger.info("ingest.fetch.agents", extra={"count": len(agents_raw), "source": source})

        comments_raw: list[dict[str, Any]] = []
        for issue in issues_raw:
            ic = await client.list_comments_for_issue(issue["id"])
            comments_raw.extend(ic)
        logger.info("ingest.fetch.comments", extra={"count": len(comments_raw), "source": source})

        issues_batch = [transform_issue(x, run_started=started_at) for x in issues_raw]
        agents_batch = [transform_agent(x, run_started=started_at) for x in agents_raw]
        comments_batch = [transform_comment(x, run_started=started_at) for x in comments_raw]

        async with driver.session() as session:
            t0 = time.monotonic()
            await session.execute_write(_write_upsert_agents, agents_batch)
            logger.info("ingest.upsert", extra={"type": "Agent", "count": len(agents_batch), "duration_ms": int((time.monotonic() - t0) * 1000)})

            t0 = time.monotonic()
            await session.execute_write(_write_upsert_issues, issues_batch)
            logger.info("ingest.upsert", extra={"type": "Issue", "count": len(issues_batch), "duration_ms": int((time.monotonic() - t0) * 1000)})

            t0 = time.monotonic()
            await session.execute_write(_write_upsert_comments, comments_batch)
            logger.info("ingest.upsert", extra={"type": "Comment", "count": len(comments_batch), "duration_ms": int((time.monotonic() - t0) * 1000)})

            # GC only on clean success — partial failure leaves stale data.
            for label in ("Issue", "Comment", "Agent"):
                await session.execute_write(_write_gc, label=label, cutoff=started_at)
                logger.info("ingest.gc", extra={"type": label})
    except Exception as e:  # noqa: BLE001 — re-raised after logging
        errors.append(f"{type(e).__name__}: {e}")
        logger.exception("ingest.error", extra={"source": source, "run_id": run_id})
        raise
    finally:
        finished_at = _utcnow_iso()
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        async with driver.session() as session:
            await session.execute_write(
                _write_finalize_ingest_run,
                run_id=run_id,
                finished_at=finished_at,
                duration_ms=duration_ms,
                errors=errors,
            )
        logger.info(
            "ingest.finish",
            extra={"source": source, "run_id": run_id, "duration_ms": duration_ms, "errors": errors},
        )

    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "errors": errors,
    }
```

- [x] Implement `paperclip.py` CLI:

```python
"""CLI entrypoint: python -m palace_mcp.ingest.paperclip"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from neo4j import AsyncGraphDatabase

from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.runner import run_ingest
from palace_mcp.memory.constraints import ensure_constraints
from palace_mcp.memory.logging_setup import configure_json_logging


async def _amain(args: argparse.Namespace) -> int:
    configure_json_logging()

    base_url = args.paperclip_url or os.environ["PAPERCLIP_API_URL"]
    token = os.environ["PAPERCLIP_INGEST_API_KEY"]
    company_id = args.company_id or os.environ["PAPERCLIP_COMPANY_ID"]
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    neo4j_password = os.environ["NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password))
    try:
        await ensure_constraints(driver)
        async with PaperclipClient(base_url=base_url, token=token, company_id=company_id) as client:
            result = await run_ingest(client=client, driver=driver)
        return 0 if not result["errors"] else 1
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="palace-mcp-ingest-paperclip")
    parser.add_argument("--paperclip-url", default=None, help="Default: $PAPERCLIP_API_URL")
    parser.add_argument("--company-id", default=None, help="Default: $PAPERCLIP_COMPANY_ID")
    args = parser.parse_args()
    sys.exit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
```

- [x] Tests for runner in `test_runner.py` — use `httpx.MockTransport` for client + a fake Neo4j driver (pytest-asyncio + Neo4j testcontainer if available; otherwise mock):

```python
# test_runner.py — integration-style; use testcontainers if available.
# If testcontainers unavailable, create a thin neo4j.AsyncDriver mock that records calls.
# Minimum required: verify run_ingest calls each of the 4 write paths in order (agents, issues, comments, GC)
# and that errors=[] in happy path.
```

(If testcontainers-neo4j is not in dev-deps, mock the driver surface: `AsyncDriver.session()`, `session.execute_write(fn, *args, **kw)`. Verify call order via `unittest.mock.AsyncMock`.)

- [x] `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/ingest/paperclip.py services/palace-mcp/src/palace_mcp/ingest/runner.py services/palace-mcp/tests/ingest/test_runner.py
git commit -m "feat(palace-mcp): ingest orchestrator + CLI (GIM-34)"
```

**Acceptance:** CLI runs (offline unit tests green); orchestrator calls transforms + upserts + GC in correct order; JSON events logged on each phase.

### Step 2.9: Filter whitelist resolver

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/filters.py`
- Create: `services/palace-mcp/tests/memory/test_filters.py`

- [x] TDD — test first:

```python
from palace_mcp.memory.filters import resolve_filters


def test_issue_known_keys_pass_through() -> None:
    where_clauses, params, unknown = resolve_filters(
        "Issue",
        {"key": "GIM-23", "status": "done", "source_updated_at_gte": "2026-04-01T00:00:00Z"},
    )
    assert "n.key = $key" in where_clauses
    assert "n.status = $status" in where_clauses
    assert "n.source_updated_at >= $source_updated_at_gte" in where_clauses
    assert params == {"key": "GIM-23", "status": "done", "source_updated_at_gte": "2026-04-01T00:00:00Z"}
    assert unknown == []


def test_issue_unknown_key_returned_separately() -> None:
    where_clauses, params, unknown = resolve_filters("Issue", {"key": "GIM-23", "bogus": "x"})
    assert unknown == ["bogus"]
    assert "bogus" not in params


def test_issue_assignee_name_joins_via_agent() -> None:
    where_clauses, params, unknown = resolve_filters("Issue", {"assignee_name": "CodeReviewer"})
    # assignee_name uses a relationship traversal — marked as a special "join" clause.
    assert any("ASSIGNED_TO" in c for c in where_clauses)
    assert params["assignee_name"] == "CodeReviewer"


def test_agent_whitelist_enforced() -> None:
    _, params, unknown = resolve_filters("Agent", {"name": "X", "foo": "bar"})
    assert "name" in params
    assert unknown == ["foo"]
```

- [x] Implement `filters.py`:

```python
"""Filter whitelist + Cypher WHERE-clause synthesis.

Keys are statically whitelisted per entity type. Values always pass as
named Cypher parameters. Unknown keys are collected separately so the
caller can log a `query.lookup.unknown_filter` warning.
"""

from typing import Literal

EntityType = Literal["Issue", "Comment", "Agent"]


# Per-entity whitelist mapping filter-key → Cypher WHERE clause template.
# `$param` slots in the clause match the filter-key name.
_WHITELIST: dict[EntityType, dict[str, str]] = {
    "Issue": {
        "key": "n.key = $key",
        "status": "n.status = $status",
        "assignee_name": "EXISTS { MATCH (n)-[:ASSIGNED_TO]->(ag:Agent {name: $assignee_name}) }",
        "source_updated_at_gte": "n.source_updated_at >= $source_updated_at_gte",
        "source_updated_at_lte": "n.source_updated_at <= $source_updated_at_lte",
    },
    "Comment": {
        "issue_key": "EXISTS { MATCH (n)-[:ON]->(i:Issue {key: $issue_key}) }",
        "author_name": "EXISTS { MATCH (n)-[:AUTHORED_BY]->(ag:Agent {name: $author_name}) }",
        "source_created_at_gte": "n.source_created_at >= $source_created_at_gte",
    },
    "Agent": {
        "name": "n.name = $name",
        "url_key": "n.url_key = $url_key",
    },
}


def resolve_filters(
    entity_type: EntityType, filters: dict[str, object]
) -> tuple[list[str], dict[str, object], list[str]]:
    """Return (where_clauses, cypher_params, unknown_keys).

    Only keys in the whitelist produce clauses/params. Unknown keys are
    surfaced so the tool can log a structured warning.
    """
    allowed = _WHITELIST[entity_type]
    where_clauses: list[str] = []
    params: dict[str, object] = {}
    unknown: list[str] = []

    for k, v in filters.items():
        clause = allowed.get(k)
        if clause is None:
            unknown.append(k)
            continue
        where_clauses.append(clause)
        params[k] = v

    return where_clauses, params, unknown
```

- [x] Tests green. `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/memory/filters.py services/palace-mcp/tests/memory/test_filters.py
git commit -m "feat(palace-mcp): filter whitelist resolver (GIM-34)"
```

**Acceptance:** unknown keys quarantined; known keys produce parameterized clauses; no interpolation path exists.

### Step 2.10: Lookup implementation + tool registration

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/lookup.py`
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py` (register tool)
- Create: `services/palace-mcp/tests/memory/test_lookup.py`

- [x] Implement `lookup.py`:

```python
"""palace.memory.lookup implementation.

- Filters resolved to parameterized Cypher WHERE clauses (filters.py).
- Read queries via session.execute_read (managed read transaction).
- Related-entity expansion one hop per entity type.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.memory.filters import resolve_filters
from palace_mcp.memory.schema import (
    EntityType,
    LookupRequest,
    LookupResponse,
    LookupResponseItem,
)

logger = logging.getLogger(__name__)

# One-hop related-entity fragments per entity type, returned in `related`.
# Issue fragment uses a CALL subquery to traverse AUTHORED_BY per comment
# so that author_name (nullable — human users are not Agent nodes) is included
# per spec §5.1.
_RELATED_FRAGMENTS: dict[EntityType, str] = {
    "Issue": """
        OPTIONAL MATCH (n)-[:ASSIGNED_TO]->(assignee:Agent)
        CALL (n) {
            OPTIONAL MATCH (c:Comment)-[:ON]->(n)
            OPTIONAL MATCH (c)-[:AUTHORED_BY]->(author:Agent)
            RETURN c, author
            ORDER BY c.source_created_at DESC
            LIMIT 50
        }
        WITH n, assignee,
             collect(CASE WHEN c IS NULL THEN null ELSE {
                 id: c.id, body: c.body,
                 source_created_at: c.source_created_at,
                 author_name: author.name
             } END) AS comments_raw
        WITH n, assignee,
             [x IN comments_raw WHERE x IS NOT NULL] AS comments
        RETURN n AS node,
            CASE WHEN assignee IS NULL THEN null
                 ELSE {id: assignee.id, name: assignee.name, url_key: assignee.url_key}
            END AS assignee,
            comments
    """,
    "Comment": """
        OPTIONAL MATCH (n)-[:ON]->(issue:Issue)
        OPTIONAL MATCH (n)-[:AUTHORED_BY]->(author:Agent)
        RETURN
            n AS node,
            CASE WHEN issue IS NULL THEN null
                 ELSE {id: issue.id, key: issue.key, title: issue.title, status: issue.status}
            END AS issue,
            CASE WHEN author IS NULL THEN null
                 ELSE {id: author.id, name: author.name}
            END AS author
    """,
    "Agent": "RETURN n AS node",
}


def _build_query(entity_type: EntityType, where_clauses: list[str], order_by: str, limit: int) -> str:
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    related = _RELATED_FRAGMENTS[entity_type]
    # NOTE: order_by and limit are restricted to safe values by LookupRequest schema.
    # order_by is a Literal union of known column names; limit is int 1-100.
    return f"""
        MATCH (n:{entity_type})
        {where}
        ORDER BY n.{order_by} DESC
        LIMIT {limit}
        CALL (n) {{
            {related}
        }}
        RETURN *
    """


def _count_query(entity_type: EntityType, where_clauses: list[str]) -> str:
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    return f"MATCH (n:{entity_type}) {where} RETURN count(n) AS c"


async def perform_lookup(driver: AsyncDriver, req: LookupRequest) -> LookupResponse:
    where_clauses, params, unknown = resolve_filters(req.entity_type, req.filters)
    for k in unknown:
        logger.warning(
            "query.lookup.unknown_filter",
            extra={"entity_type": req.entity_type, "filter_key": k},
        )

    query = _build_query(req.entity_type, where_clauses, req.order_by, req.limit)
    count_query = _count_query(req.entity_type, where_clauses)

    t0 = time.monotonic()

    async def _read(tx: AsyncManagedTransaction) -> tuple[list[dict[str, Any]], int]:
        result = await tx.run(query, **params)
        rows: list[dict[str, Any]] = [r.data() async for r in result]  # type: ignore[misc]
        count_result = await tx.run(count_query, **params)
        count_row = await count_result.single()
        count_val = int(count_row["c"]) if count_row else 0
        return rows, count_val

    async with driver.session() as session:
        rows, total = await session.execute_read(_read)

    items: list[LookupResponseItem] = []
    for row in rows:
        node = row["node"]
        related: dict[str, dict[str, Any] | list[dict[str, Any]] | None] = {}
        if req.entity_type == "Issue":
            related["assignee"] = row.get("assignee")
            related["comments"] = row.get("comments") or []
        elif req.entity_type == "Comment":
            related["issue"] = row.get("issue")
            related["author"] = row.get("author")
        items.append(
            LookupResponseItem(
                id=node["id"],
                type=req.entity_type,
                properties=dict(node),
                related=related,
            )
        )

    query_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "query.lookup",
        extra={
            "entity_type": req.entity_type,
            "filters": list(params.keys()),
            "matched": len(items),
            "total_matched": total,
            "duration_ms": query_ms,
        },
    )
    return LookupResponse(items=items, total_matched=total, query_ms=query_ms)
```

- [x] Register tool in `mcp_server.py`. Add at the bottom of the file:

```python
# --- memory tools (GIM-34) ---
from palace_mcp.memory.health import perform_health  # noqa: E402
from palace_mcp.memory.lookup import perform_lookup  # noqa: E402
from palace_mcp.memory.schema import HealthResponse, LookupRequest, LookupResponse  # noqa: E402


@_mcp.tool(
    name="palace.memory.lookup",
    description=(
        "Query paperclip-sourced project history in palace memory. "
        "Returns typed items ordered by source_updated_at DESC. "
        "Filter keys are whitelisted per entity_type; unknown keys "
        "are silently ignored (logged as warnings)."
    ),
)
async def palace_memory_lookup(request: LookupRequest) -> LookupResponse:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized")
    return await perform_lookup(_driver, request)
```

(Note: imports placed at bottom to match the pattern of adding tools without reorganizing existing imports; the `# noqa: E402` lines silence lint for deliberate late-import. MCPEngineer may choose to hoist to top — minor style choice.)

- [x] Write lookup test `test_lookup.py` — minimal unit test for `_build_query` (query-shape snapshot) and a mocked-driver integration:

```python
from palace_mcp.memory.lookup import _build_query


def test_build_query_contains_entity_label_and_limit() -> None:
    q = _build_query("Issue", ["n.status = $status"], "source_updated_at", 20)
    assert "(n:Issue)" in q
    assert "LIMIT 20" in q
    assert "ORDER BY n.source_updated_at DESC" in q
    assert "$status" in q
```

- [x] `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/memory/lookup.py services/palace-mcp/src/palace_mcp/mcp_server.py services/palace-mcp/tests/memory/test_lookup.py
git commit -m "feat(palace-mcp): palace.memory.lookup tool (GIM-34)"
```

**Acceptance:** tool registered; query uses `execute_read`; filters parameterized; unknown-filter warning logged.

### Step 2.11: Health implementation + tool registration

**Owner:** MCPEngineer.
**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/health.py`
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py` (already imported at Step 2.10 — just ensure registration follows)
- Create: `services/palace-mcp/tests/memory/test_health.py`

- [x] Implement `health.py`:

```python
"""palace.memory.health implementation — counts + last IngestRun."""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from palace_mcp.memory import cypher
from palace_mcp.memory.schema import HealthResponse


async def _read_health(tx: AsyncManagedTransaction, source: str = "paperclip") -> dict[str, Any]:
    counts_result = await tx.run(cypher.ENTITY_COUNTS)
    counts: dict[str, int] = {}
    async for row in counts_result:  # type: ignore[misc]
        counts[str(row["type"])] = int(row["count"])

    latest_result = await tx.run(cypher.LATEST_INGEST_RUN, source=source)
    latest_row = await latest_result.single()
    latest = dict(latest_row["r"]) if latest_row else None

    return {"counts": counts, "latest": latest}


async def perform_health(driver: AsyncDriver) -> HealthResponse:
    neo4j_reachable = False
    try:
        await driver.verify_connectivity()
        neo4j_reachable = True
    except Exception:
        return HealthResponse(neo4j_reachable=False, entity_counts={})

    async with driver.session() as session:
        data = await session.execute_read(_read_health)

    latest = data.get("latest") or {}
    return HealthResponse(
        neo4j_reachable=neo4j_reachable,
        entity_counts=data["counts"],
        last_ingest_started_at=latest.get("started_at"),
        last_ingest_finished_at=latest.get("finished_at"),
        last_ingest_duration_ms=latest.get("duration_ms"),
        last_ingest_errors=list(latest.get("errors") or []),
    )
```

- [x] Register tool in `mcp_server.py` (append after the lookup registration):

```python
@_mcp.tool(
    name="palace.memory.health",
    description="Palace memory health: Neo4j reachability, entity counts, last ingest run status.",
)
async def palace_memory_health() -> HealthResponse:
    if _driver is None:
        return HealthResponse(neo4j_reachable=False, entity_counts={})
    return await perform_health(_driver)
```

- [x] Write `test_health.py` — minimum: mock driver returning no ingest run, verify response shape.
- [x] `ruff + mypy --strict` clean.
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/memory/health.py services/palace-mcp/src/palace_mcp/mcp_server.py services/palace-mcp/tests/memory/test_health.py
git commit -m "feat(palace-mcp): palace.memory.health tool (GIM-34)"
```

**Acceptance:** tool registered; unreachable-Neo4j case handled; latest IngestRun exposed when present.

### Step 2.12: Wire lifespan constraints + JSON logging in service startup

**Owner:** MCPEngineer.
**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/main.py`

- [x] In `main.py`, add constraint assertion + JSON logging setup to `lifespan`:

```python
# At top:
from palace_mcp.memory.constraints import ensure_constraints
from palace_mcp.memory.logging_setup import configure_json_logging

# Inside lifespan, after `set_driver(driver)`:
    configure_json_logging()
    await ensure_constraints(driver)
```

- [x] `uv run pytest` → all tests green.
- [x] `uv run ruff check` + `uv run mypy --strict` → clean.
- [x] Verify Docker build: `docker compose build palace-mcp` (run locally or on iMac).
- [x] Commit:

```bash
git add services/palace-mcp/src/palace_mcp/main.py
git commit -m "feat(palace-mcp): wire constraints + json logging in lifespan (GIM-34)"
```

**Acceptance:** full `pytest` suite green; lint + mypy clean; docker build green; constraints asserted on every service start (idempotent).

### Step 2.13: Open PR

**Owner:** MCPEngineer.
**Depends on:** all Step 2.x committed + pushed.

- [x] `git push origin feature/GIM-34-palace-memory-paperclip`
- [x] Open PR against `develop`:
  - Title: `feat(palace-mcp): palace.memory tools + paperclip ingest (GIM-34)`
  - Body: link to plan file + spec file, short summary of changes per Step, acceptance checklist (copy from Phase 4 below to be filled by QA).
- [x] Post comment in paperclip issue linking to PR URL.
- [x] Formal reassign to CodeReviewer with status=todo.

**Acceptance:** PR open; CI running; CR notified via formal reassign.

---

## Phase 3 — PR Review (CodeReviewer → OpusArchitectReviewer)

### Step 3.1: CodeReviewer mechanical review

**Owner:** CodeReviewer.
**Depends on:** Step 2.13.

Run CR's full compliance table including all 9 MUST-FIX checkpoints from GIM-33. Cite exact file:line for each finding. Required table items:

- [x] **Spec §3** — `PAPERCLIP_INGEST_API_KEY` used in `ingest/paperclip.py`, not run-scoped JWT.
- [x] **Spec §3** — `pyproject.toml` has `mcp>=1.6` (not `mcp[cli]`) in `[project].dependencies`; `mcp[cli]` only in dev.
- [x] **Spec §3** — `httpx` and `python-json-logger` in `[project].dependencies`.
- [x] **Spec §5.1** — `LookupResponseItem.related` typed `dict[str, dict[str, Any] | list[dict[str, Any]] | None]`, not bare `dict`.
- [x] **Spec §5.1** — `author_name: str | None` surfaces nullability in Comment `related`.
- [x] **Spec §5.1** — Cypher queries contain zero string interpolation for user values (`%` and `{...}`-format absent from parameter positions; label substitution only for whitelisted `Issue|Comment|Agent`).
- [x] **Spec §5.1** — Lookup uses `session.execute_read()`, not `session.run()` or `execute_write()`.
- [x] **Spec §6.2** — Transaction functions passed to `execute_write` are idempotent (MERGE-only, no side effects outside the transaction function body).
- [x] **Spec §9** — `uv run mypy --strict` green in CI.

Plus plan-first compliance (`plan-first-review.md`):
- [x] Plan file exists + PR description links to it.
- [x] Plan steps reflect actual PR (any deviations must be committed as plan-diff before PR merges).
- [x] Unknown filter key handling: warning logged + value ignored, no Cypher path.

Plus anti-rubber-stamp (`compliance-enforcement.md`):
- [x] Every acceptance criterion in §9 of the spec has a corresponding test or explicit verification in the PR.
- [x] CI green on all four jobs (lint, typecheck, test, docker-build) — cite SHAs.

Verdict: `APPROVE | REQUEST CHANGES`. On APPROVE → formal reassign to OpusArchitectReviewer (if GIM-30 wiring done) or skip to QAEngineer (Step 4.1). On REQUEST CHANGES → formal reassign to MCPEngineer with specific file:line feedback.

### Step 3.2: OpusArchitectReviewer adversarial pass (if available)

**Owner:** OpusArchitectReviewer.
**Depends on:** Step 3.1 APPROVE. **Skippable** if GIM-30 operational wiring is not yet landed at time of this PR.

Docs-first pass via `context7` — fetch current docs for every non-trivial SDK use and cite URL per finding:

- [x] Neo4j async driver session/transaction discipline (`execute_read` vs `execute_write` vs `run`).
- [x] FastMCP tool registration + `Context` parameter use (note inherited tech debt from GIM-23 if absent — not a blocker per spec §10).
- [x] Pydantic v2 `model_validate` vs raw dict construction.
- [x] `httpx.AsyncClient` lifecycle (context-manager, transport override for tests).
- [x] MCP Python SDK tool schema generation from Pydantic models.

Verdict: `APPROVE | NUDGE | REQUEST REDESIGN`. NUDGE findings are advisory; REQUEST REDESIGN blocks merge.

### Step 3.3: Iterate on CI / CR / Opus feedback

**Owner:** MCPEngineer (with CR re-review each round).

- [x] Fix each CRITICAL finding in its own commit with a message citing the finding reference (e.g., `fix(palace-mcp): cypher parameterization in cypher.py:42 (CR CRITICAL #1)`).
- [x] Push + request CR re-review via formal reassign.
- [x] Repeat until CR posts APPROVE without CRITICAL.

---

## Phase 4 — QA Smoke (QAEngineer)

### Step 4.1: Prepare test environment

**Owner:** QAEngineer.
**Depends on:** Step 3.1 APPROVE (+ Step 3.2 if invoked).

- [x] Ensure on iMac: `cd /Users/Shared/Ios/Gimle-Palace && git fetch origin && git checkout feature/GIM-34-palace-memory-paperclip`
- [x] Stop existing compose stack: `docker compose --profile full down`
- [x] Rebuild: `docker compose --profile full build palace-mcp`
- [x] Start: `docker compose --profile full up -d`
- [x] Wait for `/healthz` green: `curl -fsS http://localhost:8080/healthz` returns `{"status":"ok","neo4j":"reachable"}`.
- [x] Verify JSON logging: `docker compose logs palace-mcp | jq 'select(.event != null) | .event' | head` — expect `ingest.*`/`query.*` events absent until first ingest/query, but logs parseable as JSON.

**Acceptance:** compose up green, health endpoint green, logs are JSON.

### Step 4.2: Ingest + health smoke

- [x] Run ingest: `docker compose exec palace-mcp python -m palace_mcp.ingest.paperclip`
- [x] Verify exit code 0 and log events: `ingest.start → ingest.fetch.* → ingest.upsert → ingest.gc → ingest.finish`.
- [x] Connect a real MCP client (Claude Desktop, Cursor, or mcp Python SDK) to `palace-mcp` `/mcp` using the existing GIM-23 config.
- [x] Call `palace.memory.health`. Expect:
  - `neo4j_reachable: true`
  - `entity_counts.Issue ≥ 1`, `Comment ≥ 1`, `Agent ≥ 1`
  - `last_ingest_started_at`, `last_ingest_finished_at`, `last_ingest_duration_ms` populated
  - `last_ingest_errors: []`

- [x] Attach screenshot or curl-equivalent to the PR as comment.

### Step 4.3: Lookup smoke + timestamp check

- [x] Call `palace.memory.lookup(entity_type="Issue", filters={"status":"done"}, limit=5)`.
- [x] Verify response:
  - `items` non-empty.
  - Each item has `properties.source_created_at`, `properties.source_updated_at`, `properties.palace_last_seen_at` — all non-null ISO-8601 strings.
  - `related.assignee` either `null` or `{id, name, url_key}` shape.
  - `related.comments` a list (possibly empty).
  - `total_matched` ≥ `len(items)`.
  - `query_ms` reasonable.
- [x] Call with unknown filter: `filters={"bogus":"x"}`. Expect `items` filtered by remaining keys (or all if no other keys), and JSON log line `{"event":"query.lookup.unknown_filter","filter_key":"bogus"}` visible in `docker compose logs`.
- [x] Attach call + response samples + log snippet to PR.

### Step 4.4: Idempotency + deletion propagation

- [x] Re-run ingest: `docker compose exec palace-mcp python -m palace_mcp.ingest.paperclip` (no paperclip changes between runs).
- [x] Call `palace.memory.health` — `entity_counts` identical to Step 4.2 run.
- [x] Query one specific issue's `palace_last_seen_at` — verify it advanced to the new run's start time.
- [x] Hide or delete a test issue in paperclip (prefer hide — reversible). Re-run ingest. Verify the issue is absent from `palace.memory.lookup` results.
- [x] Un-hide the issue in paperclip. Re-run ingest. Verify issue returns.
- [x] Attach evidence to PR.

### Step 4.5: Post smoke evidence + verdict

- [x] Compile PR comment with:
  - Compose build + up outcome.
  - Ingest run log excerpt.
  - Health tool response.
  - Lookup tool response (with + without unknown filter).
  - Idempotency proof.
  - Deletion propagation proof.
  - Verdict: `QA PASS` or `QA BLOCKER: ...`.

- [x] On QA PASS → formal reassign to MCPEngineer with status=todo for merge.
- [x] On QA BLOCKER → formal reassign to MCPEngineer with status=todo; findings comment with exact reproduction.

---

## Phase 5 — Merge + Close (MCPEngineer)

### Step 5.1: Mark plan done

**Owner:** MCPEngineer.

- [x] On feature branch, edit the plan file in `docs/superpowers/plans/`:
  - All phase/step `- [x]` → `- [x]`.
  - Any deviations in scope: commit a plan-diff commit before merge so CR can verify no silent scope creep.

```bash
git add docs/superpowers/plans/2026-04-17-GIM-34-palace-memory-paperclip.md
git commit -m "docs(plans): GIM-34 — mark all steps complete"
git push origin feature/GIM-34-palace-memory-paperclip
```

### Step 5.2: Squash-merge to develop

- [x] On GitHub PR: **Squash merge** (single commit lands on `develop`).
- [x] Delete the feature branch after merge.
- [x] Verify: `git log origin/develop --oneline -1` shows the squash commit.

### Step 5.3: Close issue with acceptance evidence

**Owner:** MCPEngineer.

Post a final comment on the paperclip issue:

```
## GIM-34 — CLOSED ✅ All acceptance criteria met

### Merge
- Squash commit: <sha> on develop

### Evidence
| Criterion | Status |
|-----------|--------|
| PR merged into `develop` | ✅ <sha> |
| Plan file all steps `[x]` | ✅ |
| `uv run pytest` green | ✅ |
| `uv run ruff check` green | ✅ |
| `uv run mypy --strict` green | ✅ |
| `docker compose build` green | ✅ |
| Real MCP client smoke | ✅ (Step 4.2–4.3 evidence in PR #<n>) |
| Idempotency proof | ✅ (Step 4.4) |
| Deletion propagation proof | ✅ (Step 4.4) |
| Three timestamps on every node | ✅ |
| JSON logging `ingest.*` / `query.*` | ✅ |
| Filter whitelist enforced | ✅ |
| CodeReviewer APPROVE | ✅ (Round <n>) |
| OpusArchitectReviewer | ✅ / SKIPPED (GIM-30 wiring <status>) |
| QAEngineer smoke | ✅ |

### Scope delivered
- `palace.memory.lookup` tool
- `palace.memory.health` tool
- `python -m palace_mcp.ingest.paperclip` CLI
- Neo4j schema: Issue, Comment, Agent, IngestRun + 3 edge types
- Three timestamps on every source-node (source_created_at / source_updated_at / palace_last_seen_at)

### Followups (new issues)
- N+1: Graphiti service (brainstorm already in progress on main — spec TBD)
```

- [x] PATCH status=done on the paperclip issue.
- [x] Release assignee (optional).

**Acceptance:** issue closed, evidence table posted, followups filed as separate issues where needed.

---

## Cross-cutting acceptance (this whole plan closes when)

- [x] Phase 0: `PAPERCLIP_INGEST_API_KEY` provisioned.
- [x] Phase 1: Issue + branch + plan committed; CR plan-first APPROVE.
- [x] Phase 2: All 13 implementation steps committed; CI green on the feature branch head.
- [x] Phase 3: CR mechanical APPROVE; Opus NUDGE (or skipped); any CRITICAL iterated to resolution.
- [x] Phase 4: QA smoke PASS with evidence attached to PR.
- [x] Phase 5: Squash-merged to `develop`; issue closed with acceptance table.

## Estimated size

- Code: ~400 LOC (ingest ~200, memory ~180, tests ~80) — matches spec §11 estimate.
- Plan file: ~800 LOC (this file, ~80 structural + ~720 code/test snippets inlined).
- PR duration: 1-2 days of agent time (comparable to GIM-23).
- Handoffs: 6 (CTO→TW→CR→MCPE→CR→(+Opus)→QA→MCPE).
