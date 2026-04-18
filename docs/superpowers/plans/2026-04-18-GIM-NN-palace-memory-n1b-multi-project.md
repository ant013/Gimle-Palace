# N+1b Multi-project + :Project entity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `:Project` entity, project-registry file, and `project: str | list[str] | "*" | None` scoping on all applicable palace-mcp tools. Validate multi-project schema via registering a test Medic `:Project` node without full data ingest.

**Architecture:** `projects/_registry.yaml` as source of truth for known slugs. Per-project `projects/<slug>.yaml` holds metadata. `:Project` EntityNode in each project's own `group_id`. Zero raw Cypher — all operations via `graphiti.nodes.entity.*` namespace API (consistent with N+1a substrate). `:BELONGS_TO_PROJECT` edges explicitly NOT added (per verification §5.C: `group_id` is sole namespace primitive).

**Tech Stack:** Python 3.12, graphiti-core>=0.3 (already in deps from N+1a), Pydantic v2, pytest-asyncio, mypy --strict.

**Spec:** `docs/superpowers/specs/2026-04-18-palace-memory-n1b-multi-project.md`
**Predecessor:** N+1a (GIM-48) merged as squash `9d87fa0` on develop 2026-04-18
**Successor:** N+1c (GIM-NN+1)

---

## File Structure

**Create:**
- `projects/_registry.yaml` — source of truth for known project slugs (committed)
- `projects/gimle.yaml` — per-project config for Gimle
- `services/palace-mcp/src/palace_mcp/projects/__init__.py`
- `services/palace-mcp/src/palace_mcp/projects/registry.py` — read/write `_registry.yaml`, atomic ops
- `services/palace-mcp/src/palace_mcp/projects/schema.py` — Pydantic `ProjectConfig`, `ProjectInfo`, `ListProjectsResponse`
- `services/palace-mcp/src/palace_mcp/projects/resolver.py` — `resolve_group_ids(project)` + typo protection
- `services/palace-mcp/src/palace_mcp/projects/tools.py` — `list_projects`, `get_project_overview`, `register_project` MCP tool handlers
- `services/palace-mcp/tests/projects/__init__.py`
- `services/palace-mcp/tests/projects/test_registry.py`
- `services/palace-mcp/tests/projects/test_resolver.py`
- `services/palace-mcp/tests/projects/test_tools.py`

**Modify:**
- `services/palace-mcp/src/palace_mcp/ingest/builders.py` — add `build_project_node`; `GROUP_ID` constant stays as default but callers pass explicit slug-derived value
- `services/palace-mcp/src/palace_mcp/ingest/runner.py` — accept `group_id` param, upsert `:Project` node first, use slug-derived group_id throughout
- `services/palace-mcp/src/palace_mcp/ingest/paperclip.py` — add `--project-slug` / `--project-config` CLI params
- `services/palace-mcp/src/palace_mcp/memory/lookup.py` — accept `project` param → resolve → `get_by_group_ids(ids)`
- `services/palace-mcp/src/palace_mcp/memory/health.py` — add `projects: list[str]`, `default_project`, `entity_counts_per_project`, `provider_config_hash_mismatches`
- `services/palace-mcp/src/palace_mcp/memory/schema.py` — `LookupRequest` gains `project`; `HealthResponse` gains new fields; add `ProjectInfo`/`ListProjectsResponse`/`RegisterProjectRequest`
- `services/palace-mcp/src/palace_mcp/mcp_server.py` — register 3 new tool handlers
- `services/palace-mcp/src/palace_mcp/config.py` — add `default_project_slug: str = "gimle"`

---

## Phase 0 — Registry + project.yaml foundation

### Task 1: `projects/` directory + gimle.yaml + registry

**Files:**
- Create: `projects/_registry.yaml`
- Create: `projects/gimle.yaml`

- [ ] **Step 1: Create files at repo root**

```bash
mkdir -p projects
```

Create `projects/_registry.yaml`:

```yaml
# Source of truth for all projects known to this palace instance.
# Updated atomically by palace.memory.register_project + ingest CLI.
# See docs/superpowers/specs/2026-04-18-palace-memory-n1b-multi-project.md §3.1
projects:
  - gimle
```

Create `projects/gimle.yaml`:

```yaml
slug: gimle
name: Gimle Palace Bootstrap
tags: [python, agent-framework, paperclip, bootstrap]
language: python
framework: fastmcp
repo_url: https://github.com/ant013/Gimle-Palace
```

- [ ] **Step 2: Commit**

```bash
git add projects/_registry.yaml projects/gimle.yaml
git commit -m "feat(projects): _registry.yaml + gimle.yaml for N+1b multi-project"
```

### Task 2: ProjectConfig + ProjectInfo Pydantic schema

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/projects/__init__.py` (empty)
- Create: `services/palace-mcp/src/palace_mcp/projects/schema.py`
- Test: `services/palace-mcp/tests/projects/test_schema.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/projects/__init__.py` (empty file) and `services/palace-mcp/tests/projects/test_schema.py`:

```python
import pytest

from palace_mcp.projects.schema import (
    ListProjectsResponse,
    ProjectConfig,
    ProjectInfo,
    RegisterProjectRequest,
)


def test_project_config_minimal() -> None:
    cfg = ProjectConfig(slug="gimle", name="Gimle")
    assert cfg.slug == "gimle"
    assert cfg.tags == []
    assert cfg.language is None


def test_project_config_from_yaml_dict() -> None:
    raw = {
        "slug": "gimle",
        "name": "Gimle Palace Bootstrap",
        "tags": ["python", "bootstrap"],
        "language": "python",
        "framework": "fastmcp",
        "repo_url": "https://github.com/ant013/Gimle-Palace",
    }
    cfg = ProjectConfig(**raw)
    assert cfg.tags == ["python", "bootstrap"]
    assert cfg.framework == "fastmcp"


def test_project_info_entity_counts_default() -> None:
    info = ProjectInfo(slug="x", name="X", tags=[], entity_counts={})
    assert info.entity_counts == {}
    assert info.last_ingest_at is None


def test_register_project_request_rejects_bad_slug() -> None:
    with pytest.raises(ValueError):
        RegisterProjectRequest(slug="Has Spaces", name="X")
    with pytest.raises(ValueError):
        RegisterProjectRequest(slug="UPPER", name="X")


def test_list_projects_response_shape() -> None:
    resp = ListProjectsResponse(projects=[
        ProjectInfo(slug="gimle", name="Gimle", tags=[], entity_counts={})
    ])
    assert len(resp.projects) == 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd services/palace-mcp
uv run pytest tests/projects/test_schema.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement schema**

Create `services/palace-mcp/src/palace_mcp/projects/__init__.py` (empty).

Create `services/palace-mcp/src/palace_mcp/projects/schema.py`:

```python
"""Pydantic schemas for multi-project support (N+1b)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ProjectConfig(BaseModel):
    """Per-project config loaded from projects/<slug>.yaml."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    tags: list[str] = Field(default_factory=list)
    language: str | None = None
    framework: str | None = None
    repo_url: str | None = None

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase alphanumeric + hyphens (start with letter/digit)"
            )
        return v


class ProjectInfo(BaseModel):
    """Runtime state of a project — returned by list_projects / get_project_overview."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    tags: list[str]
    language: str | None = None
    framework: str | None = None
    repo_url: str | None = None
    last_ingest_at: str | None = None
    entity_counts: dict[str, int]
    provider_config_hash: str | None = None


class RegisterProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    tags: list[str] = Field(default_factory=list)
    language: str | None = None
    framework: str | None = None
    repo_url: str | None = None

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase alphanumeric + hyphens (start with letter/digit)"
            )
        return v


class ListProjectsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projects: list[ProjectInfo]
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/projects/test_schema.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/projects/__init__.py services/palace-mcp/src/palace_mcp/projects/schema.py services/palace-mcp/tests/projects/__init__.py services/palace-mcp/tests/projects/test_schema.py
git commit -m "feat(projects): Pydantic schemas for ProjectConfig/Info/Register/List"
```

### Task 3: Registry reader + atomic writer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/projects/registry.py`
- Test: `services/palace-mcp/tests/projects/test_registry.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/projects/test_registry.py`:

```python
from pathlib import Path

import pytest
import yaml

from palace_mcp.projects.registry import (
    ProjectNotFoundError,
    add_slug,
    load_project_config,
    load_slugs,
)
from palace_mcp.projects.schema import ProjectConfig


def _write_registry(path: Path, slugs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"projects": slugs}))


def test_load_slugs_empty_registry_returns_empty_list(tmp_path: Path) -> None:
    reg = tmp_path / "_registry.yaml"
    _write_registry(reg, [])
    assert load_slugs(reg) == []


def test_load_slugs_reads_yaml(tmp_path: Path) -> None:
    reg = tmp_path / "_registry.yaml"
    _write_registry(reg, ["gimle", "medic"])
    assert load_slugs(reg) == ["gimle", "medic"]


def test_load_slugs_missing_file_returns_empty(tmp_path: Path) -> None:
    reg = tmp_path / "_registry.yaml"
    assert load_slugs(reg) == []


def test_add_slug_writes_atomically(tmp_path: Path) -> None:
    reg = tmp_path / "_registry.yaml"
    _write_registry(reg, ["gimle"])
    add_slug(reg, "medic")
    assert load_slugs(reg) == ["gimle", "medic"]
    # No stray .tmp files left over
    assert not any(reg.parent.iterdir() - {reg})


def test_add_slug_idempotent(tmp_path: Path) -> None:
    reg = tmp_path / "_registry.yaml"
    _write_registry(reg, ["gimle"])
    add_slug(reg, "gimle")
    assert load_slugs(reg) == ["gimle"]


def test_load_project_config_reads_yaml(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "gimle.yaml").write_text(yaml.safe_dump({
        "slug": "gimle", "name": "Gimle", "tags": ["bootstrap"],
    }))
    cfg = load_project_config("gimle", projects_dir)
    assert isinstance(cfg, ProjectConfig)
    assert cfg.slug == "gimle"
    assert cfg.tags == ["bootstrap"]


def test_load_project_config_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        load_project_config("nonexistent", tmp_path / "projects")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/projects/test_registry.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement registry**

Create `services/palace-mcp/src/palace_mcp/projects/registry.py`:

```python
"""Registry file read/write with atomic updates.

projects/_registry.yaml lists all known project slugs on this palace instance.
projects/<slug>.yaml holds per-project metadata.

Atomic write pattern: write to <path>.tmp.<pid>, then os.replace() to final name.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from palace_mcp.projects.schema import ProjectConfig


class ProjectNotFoundError(FileNotFoundError):
    """Raised when projects/<slug>.yaml does not exist."""


def load_slugs(registry_path: Path) -> list[str]:
    """Read the slug list from _registry.yaml. Missing file → empty list."""
    if not registry_path.exists():
        return []
    data = yaml.safe_load(registry_path.read_text()) or {}
    return list(data.get("projects") or [])


def add_slug(registry_path: Path, slug: str) -> None:
    """Atomically append slug to registry (idempotent if already present)."""
    current = load_slugs(registry_path)
    if slug in current:
        return
    current.append(slug)
    tmp = registry_path.with_name(f"{registry_path.name}.tmp.{os.getpid()}")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(yaml.safe_dump({"projects": current}))
    os.replace(tmp, registry_path)


def load_project_config(slug: str, projects_dir: Path) -> ProjectConfig:
    """Load projects/<slug>.yaml as ProjectConfig."""
    path = projects_dir / f"{slug}.yaml"
    if not path.exists():
        raise ProjectNotFoundError(f"projects/{slug}.yaml not found at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return ProjectConfig(**data)


def write_project_config(cfg: ProjectConfig, projects_dir: Path) -> None:
    """Atomically write projects/<slug>.yaml."""
    projects_dir.mkdir(parents=True, exist_ok=True)
    path = projects_dir / f"{cfg.slug}.yaml"
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(yaml.safe_dump(
        cfg.model_dump(exclude_none=False), sort_keys=False
    ))
    os.replace(tmp, path)
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/projects/test_registry.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/projects/registry.py services/palace-mcp/tests/projects/test_registry.py
git commit -m "feat(projects): registry reader + atomic writer"
```

---

## Phase 1 — `:Project` entity + resolver

### Task 4: `build_project_node` builder

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/builders.py`
- Test: `services/palace-mcp/tests/ingest/test_builders.py`

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/ingest/test_builders.py`:

```python
from uuid import UUID

from palace_mcp.ingest.builders import PROJECT_NAMESPACE_UUID, build_project_node
from palace_mcp.projects.schema import ProjectConfig


def test_build_project_node_uuid_deterministic() -> None:
    cfg = ProjectConfig(slug="gimle", name="Gimle")
    n1 = build_project_node(cfg, run_started="2026-04-18T00:00:00+00:00",
                             provider_config_hash="abc123")
    n2 = build_project_node(cfg, run_started="2026-04-18T01:00:00+00:00",
                             provider_config_hash="abc123")
    assert n1.uuid == n2.uuid  # same slug → same uuid5
    # uuid5 from fixed namespace is deterministic
    expected = str(UUID(hex=n1.uuid.replace("-", "")))
    assert n1.uuid == expected


def test_build_project_node_group_id_matches_slug() -> None:
    cfg = ProjectConfig(slug="medic", name="Medic Healthcare", tags=["mobile"])
    node = build_project_node(cfg, run_started="2026-04-18T00:00:00+00:00",
                               provider_config_hash="x")
    assert node.group_id == "project/medic"
    assert node.labels == ["Project"]
    assert node.attributes["slug"] == "medic"
    assert node.attributes["name"] == "Medic Healthcare"
    assert node.attributes["tags"] == ["mobile"]
    assert node.attributes["provider_config_hash"] == "x"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/ingest/test_builders.py::test_build_project_node_group_id_matches_slug -v
```

Expected: ImportError / attribute missing.

- [ ] **Step 3: Implement `build_project_node`**

Append to `services/palace-mcp/src/palace_mcp/ingest/builders.py`:

```python
from uuid import UUID, uuid5

from palace_mcp.projects.schema import ProjectConfig

# Stable namespace UUID for :Project node derivation. Do NOT change — changing
# would invalidate all existing Project node uuids.
PROJECT_NAMESPACE_UUID = UUID("b7a3c0e0-1234-5678-9abc-def012345678")


def build_project_node(
    cfg: ProjectConfig,
    *,
    run_started: str,
    provider_config_hash: str,
) -> EntityNode:
    """Build :Project EntityNode. Deterministic uuid5 from slug."""
    return EntityNode(
        uuid=str(uuid5(PROJECT_NAMESPACE_UUID, cfg.slug)),
        name=cfg.slug,
        labels=["Project"],
        group_id=f"project/{cfg.slug}",
        summary=cfg.name,
        attributes={
            "slug": cfg.slug,
            "name": cfg.name,
            "tags": cfg.tags,
            "language": cfg.language,
            "framework": cfg.framework,
            "repo_url": cfg.repo_url,
            "source_created_at": run_started,
            "source_updated_at": run_started,
            "palace_last_seen_at": run_started,
            "provider_config_hash": provider_config_hash,
        },
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/test_builders.py -v
```

Expected: all PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/builders.py services/palace-mcp/tests/ingest/test_builders.py
git commit -m "feat(ingest): build_project_node with deterministic uuid5 from slug"
```

### Task 5: `resolve_group_ids` helper

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/projects/resolver.py`
- Test: `services/palace-mcp/tests/projects/test_resolver.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/projects/test_resolver.py`:

```python
from pathlib import Path

import pytest
import yaml

from palace_mcp.projects.resolver import UnknownProjectError, resolve_group_ids


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    reg = tmp_path / "_registry.yaml"
    reg.write_text(yaml.safe_dump({"projects": ["gimle", "medic"]}))
    return reg


def test_resolve_none_returns_default_slug(registry: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_PROJECT_SLUG", "gimle")
    assert resolve_group_ids(None, registry_path=registry) == ["project/gimle"]


def test_resolve_none_with_custom_default_env(registry: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_PROJECT_SLUG", "medic")
    assert resolve_group_ids(None, registry_path=registry) == ["project/medic"]


def test_resolve_str_known(registry: Path) -> None:
    assert resolve_group_ids("medic", registry_path=registry) == ["project/medic"]


def test_resolve_str_unknown_raises(registry: Path) -> None:
    with pytest.raises(UnknownProjectError):
        resolve_group_ids("nonexistent", registry_path=registry)


def test_resolve_list(registry: Path) -> None:
    assert resolve_group_ids(["gimle", "medic"], registry_path=registry) == [
        "project/gimle",
        "project/medic",
    ]


def test_resolve_list_partial_unknown_raises(registry: Path) -> None:
    with pytest.raises(UnknownProjectError, match="nonexistent"):
        resolve_group_ids(["gimle", "nonexistent"], registry_path=registry)


def test_resolve_star_all_projects(registry: Path) -> None:
    assert resolve_group_ids("*", registry_path=registry) == [
        "project/gimle",
        "project/medic",
    ]


def test_resolve_rejects_bad_type(registry: Path) -> None:
    with pytest.raises(TypeError):
        resolve_group_ids(42, registry_path=registry)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/projects/test_resolver.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement resolver**

Create `services/palace-mcp/src/palace_mcp/projects/resolver.py`:

```python
"""resolve_group_ids — tool param → Graphiti group_ids list.

Semantics (spec §5.1):
- None → current / default project from DEFAULT_PROJECT_SLUG env (falls to "gimle")
- str → single project; validated against registry (typo protection)
- list[str] → subset; all slugs validated
- "*" → all projects in registry
"""

from __future__ import annotations

import os
from pathlib import Path

from palace_mcp.projects.registry import load_slugs


class UnknownProjectError(ValueError):
    """Raised when a requested project slug is not in the registry."""


def resolve_group_ids(
    project: str | list[str] | None, *, registry_path: Path
) -> list[str]:
    known = set(load_slugs(registry_path))

    if project is None:
        slug = os.getenv("DEFAULT_PROJECT_SLUG", "gimle")
        return [f"project/{slug}"]
    if project == "*":
        return [f"project/{s}" for s in load_slugs(registry_path)]
    if isinstance(project, str):
        if project not in known:
            raise UnknownProjectError(f"unknown project slug: {project!r}")
        return [f"project/{project}"]
    if isinstance(project, list):
        unknown = [s for s in project if s not in known]
        if unknown:
            raise UnknownProjectError(f"unknown project slugs: {unknown}")
        return [f"project/{s}" for s in project]
    raise TypeError(f"project must be str|list|None; got {type(project).__name__}")
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/projects/test_resolver.py -v
```

Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/projects/resolver.py services/palace-mcp/tests/projects/test_resolver.py
git commit -m "feat(projects): resolve_group_ids with typo-protection"
```

---

## Phase 2 — Ingest parameterization

### Task 6: Ingest CLI `--project-slug` param

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/paperclip.py`
- Modify: `services/palace-mcp/src/palace_mcp/ingest/runner.py`

- [ ] **Step 1: Update CLI parser**

Replace argparse section in `services/palace-mcp/src/palace_mcp/ingest/paperclip.py`:

```python
def main() -> None:
    parser = argparse.ArgumentParser(prog="palace-mcp-ingest-paperclip")
    parser.add_argument("--paperclip-url", default=None)
    parser.add_argument("--company-id", default=None)
    parser.add_argument("--project-slug", default="gimle",
                        help="Project slug. Must exist in projects/_registry.yaml.")
    parser.add_argument("--project-config", default=None,
                        help="Path to projects/<slug>.yaml (default: projects/<slug>.yaml).")
    args = parser.parse_args()
    sys.exit(asyncio.run(_amain(args)))
```

Update `_amain` to load project config and pass to `run_ingest`:

```python
async def _amain(args: argparse.Namespace) -> int:
    configure_json_logging()
    settings = IngestSettings()
    base_url = args.paperclip_url or settings.paperclip_api_url
    token = settings.paperclip_ingest_api_key.get_secret_value()
    company_id = args.company_id or settings.paperclip_company_id

    from pathlib import Path
    from hashlib import sha256
    from palace_mcp.projects.registry import load_project_config, load_slugs

    registry_path = Path("projects/_registry.yaml")
    known = load_slugs(registry_path)
    if args.project_slug not in known:
        raise SystemExit(
            f"unknown --project-slug '{args.project_slug}'; known: {known}. "
            f"Run palace.memory.register_project first, or add to _registry.yaml."
        )

    projects_dir = Path("projects")
    project_cfg = load_project_config(args.project_slug, projects_dir)
    group_id = f"project/{args.project_slug}"
    provider_hash = sha256(
        f"{settings.embedding_model}:{settings.embedding_dim}".encode()
    ).hexdigest()[:16]

    graphiti = build_graphiti(settings)
    try:
        async with PaperclipClient(
            base_url=base_url, token=token, company_id=company_id
        ) as client:
            result = await run_ingest(
                client=client, graphiti=graphiti,
                group_id=group_id,
                project_cfg=project_cfg,
                provider_config_hash=provider_hash,
            )
        return 0 if not result["errors"] else 1
    finally:
        await graphiti.close()
```

- [ ] **Step 2: Update `run_ingest` signature to upsert `:Project` first**

In `services/palace-mcp/src/palace_mcp/ingest/runner.py`:

1. Add imports at top:
```python
from palace_mcp.ingest.builders import build_project_node
from palace_mcp.projects.schema import ProjectConfig
```

2. Change function signature and body (first phase):

```python
async def run_ingest(
    *,
    client: PaperclipClient,
    graphiti: Graphiti,
    group_id: str = "project/gimle",   # back-compat default
    project_cfg: ProjectConfig | None = None,
    provider_config_hash: str = "",
    source: str = "paperclip",
) -> dict[str, Any]:
    # ... existing started_at / run_id setup ...

    # NEW: upsert :Project node first (before Issue/Comment/Agent)
    if project_cfg is not None:
        project_node = build_project_node(
            project_cfg,
            run_started=started_at,
            provider_config_hash=provider_config_hash,
        )
        await upsert_with_change_detection(graphiti, project_node)
        logger.info(
            "ingest.project.upsert",
            extra={
                "slug": project_cfg.slug,
                "tags": project_cfg.tags,
                "provider_config_hash": provider_config_hash,
            },
        )

    # ... rest of existing flow, with all builders passing group_id= parameter ...
```

Also update all existing `build_*_node` / `build_*_edge` callers in `run_ingest` to pass `group_id=group_id` explicitly instead of relying on the default.

- [ ] **Step 3: Add simple smoke unit test for runner signature**

Append to `services/palace-mcp/tests/ingest/test_upsert.py` (repurpose for runner smoke) OR create `services/palace-mcp/tests/ingest/test_runner_n1b.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.ingest.runner import run_ingest
from palace_mcp.projects.schema import ProjectConfig


@pytest.mark.asyncio
async def test_run_ingest_upserts_project_first() -> None:
    client = MagicMock()
    client.list_issues = AsyncMock(return_value=[])
    client.list_agents = AsyncMock(return_value=[])
    client.list_comments_for_issue = AsyncMock(return_value=[])

    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_uuid = AsyncMock(side_effect=Exception("NotFound"))
    graphiti.nodes.entity.save = AsyncMock()
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=[])

    cfg = ProjectConfig(slug="gimle", name="Gimle", tags=["bootstrap"])
    result = await run_ingest(
        client=client,
        graphiti=graphiti,
        group_id="project/gimle",
        project_cfg=cfg,
        provider_config_hash="hash123",
    )
    assert result["errors"] == []
    # :Project node must be first save
    first_saved = graphiti.nodes.entity.save.await_args_list[0].args[0]
    assert first_saved.labels == ["Project"]
    assert first_saved.group_id == "project/gimle"
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/ -v
```

Expected: all PASS (existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/paperclip.py services/palace-mcp/src/palace_mcp/ingest/runner.py services/palace-mcp/tests/ingest/
git commit -m "feat(ingest): --project-slug CLI + upsert :Project node first"
```

---

## Phase 3 — `project` param on lookup + health

### Task 7: `project` param on `palace.memory.lookup`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/lookup.py`
- Test: `services/palace-mcp/tests/memory/test_lookup.py`

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/memory/test_lookup.py`:

```python
from pathlib import Path

import yaml


@pytest.mark.asyncio
async def test_lookup_project_none_uses_default_slug(
    monkeypatch, tmp_path: Path
) -> None:
    # Arrange registry
    reg = tmp_path / "_registry.yaml"
    reg.write_text(yaml.safe_dump({"projects": ["gimle"]}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEFAULT_PROJECT_SLUG", "gimle")

    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=[])
    graphiti.edges.entity.get_by_node_uuid = AsyncMock(return_value=[])

    req = LookupRequest(entity_type="Issue", filters={}, limit=10)  # project=None
    resp = await perform_lookup(graphiti, req)
    # Called with default project group_id
    graphiti.nodes.entity.get_by_group_ids.assert_awaited_once_with(["project/gimle"])


@pytest.mark.asyncio
async def test_lookup_project_list_resolves(monkeypatch, tmp_path: Path) -> None:
    reg = tmp_path / "_registry.yaml"
    reg.write_text(yaml.safe_dump({"projects": ["gimle", "medic"]}))
    monkeypatch.chdir(tmp_path)

    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=[])
    graphiti.edges.entity.get_by_node_uuid = AsyncMock(return_value=[])

    req = LookupRequest(entity_type="Issue", filters={},
                        project=["gimle", "medic"], limit=10)
    await perform_lookup(graphiti, req)
    graphiti.nodes.entity.get_by_group_ids.assert_awaited_once_with(
        ["project/gimle", "project/medic"]
    )


@pytest.mark.asyncio
async def test_lookup_project_unknown_returns_error(
    monkeypatch, tmp_path: Path
) -> None:
    reg = tmp_path / "_registry.yaml"
    reg.write_text(yaml.safe_dump({"projects": ["gimle"]}))
    monkeypatch.chdir(tmp_path)

    graphiti = MagicMock()

    req = LookupRequest(entity_type="Issue", filters={}, project="nonexistent",
                        limit=10)
    from palace_mcp.projects.resolver import UnknownProjectError
    with pytest.raises(UnknownProjectError):
        await perform_lookup(graphiti, req)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/memory/test_lookup.py -v
```

Expected: fails — `project` not on LookupRequest.

- [ ] **Step 3: Add `project` to `LookupRequest`**

In `services/palace-mcp/src/palace_mcp/memory/schema.py`:

```python
from typing import Any, Literal, Union

class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    filters: dict[str, Any] = Field(default_factory=dict)
    # N+1b: project scoping — None defaults to DEFAULT_PROJECT_SLUG env
    project: Union[str, list[str], None] = None  # noqa: UP007
    limit: int = Field(default=20, ge=1, le=100)
    order_by: Literal["source_updated_at", "source_created_at"] = "source_updated_at"
```

- [ ] **Step 4: Update `perform_lookup` to use resolver**

In `services/palace-mcp/src/palace_mcp/memory/lookup.py`:

1. Add import:
```python
from pathlib import Path
from palace_mcp.projects.resolver import resolve_group_ids
```

2. Change `perform_lookup` body's group_ids source:

Replace the line that calls `graphiti.nodes.entity.get_by_group_ids([GROUP_ID])` (or similar hardcoded path) with:

```python
    # Resolve project scoping
    group_ids = resolve_group_ids(
        req.project,
        registry_path=Path("projects/_registry.yaml"),
    )
    t0 = time.monotonic()
    all_nodes = await graphiti.nodes.entity.get_by_group_ids(group_ids)
```

(The existing filter + sort + related-entity expansion logic stays unchanged.)

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/memory/test_lookup.py -v
```

Expected: all PASS (existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/schema.py services/palace-mcp/src/palace_mcp/memory/lookup.py services/palace-mcp/tests/memory/test_lookup.py
git commit -m "feat(memory): lookup accepts project: str|list|\"*\"|None via resolve_group_ids"
```

### Task 8: Extend `get_health` with per-project counts

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/health.py`
- Test: `services/palace-mcp/tests/memory/test_health.py`

- [ ] **Step 1: Extend `HealthResponse` schema**

In `services/palace-mcp/src/palace_mcp/memory/schema.py`, add to `HealthResponse`:

```python
    # N+1b multi-project
    projects: list[str] = Field(default_factory=list)
    default_project: str | None = None
    entity_counts_per_project: dict[str, dict[str, int]] = Field(default_factory=dict)
    provider_config_hash_mismatches: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Write failing test**

Append to `services/palace-mcp/tests/memory/test_health.py`:

```python
from pathlib import Path
import yaml


@pytest.mark.asyncio
async def test_health_includes_projects_list_and_default(
    monkeypatch, tmp_path: Path
) -> None:
    reg = tmp_path / "_registry.yaml"
    reg.write_text(yaml.safe_dump({"projects": ["gimle", "medic"]}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEFAULT_PROJECT_SLUG", "gimle")

    graphiti = MagicMock()
    graphiti.driver.verify_connectivity = AsyncMock()
    graphiti.embedder.config.embedding_model = "text-embedding-3-small"
    graphiti.embedder.config.base_url = "https://api.openai.com/v1"
    # Two projects — each returns its own node set
    gimle_issue = EntityNode(uuid="u1", name="n", labels=["Issue"],
                              group_id="project/gimle", summary="s",
                              attributes={"source": "paperclip"})
    medic_empty: list = []
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(side_effect=[[gimle_issue], medic_empty])

    resp = await get_health(graphiti)
    assert "gimle" in resp.projects
    assert "medic" in resp.projects
    assert resp.default_project == "gimle"
    assert resp.entity_counts_per_project["gimle"]["Issue"] == 1
    assert resp.entity_counts_per_project["medic"] == {}
```

- [ ] **Step 3: Update `get_health`**

In `services/palace-mcp/src/palace_mcp/memory/health.py`:

1. Imports:
```python
import os
from pathlib import Path
from palace_mcp.projects.registry import load_slugs
```

2. Replace the body to iterate per-project counts:

```python
async def get_health(graphiti: Graphiti) -> HealthResponse:
    neo4j_ok = False
    try:
        await graphiti.driver.verify_connectivity()
        neo4j_ok = True
    except Exception as exc:
        logger.warning("palace.memory.health neo4j unreachable: %s", exc)

    embedding_model: str | None = None
    base_url: str | None = None
    try:
        embedding_model = graphiti.embedder.config.embedding_model  # type: ignore[attr-defined]
        base_url = _hostname_only(graphiti.embedder.config.base_url)  # type: ignore[attr-defined]
    except Exception:
        pass

    registry_path = Path("projects/_registry.yaml")
    slugs = load_slugs(registry_path)
    default_slug = os.getenv("DEFAULT_PROJECT_SLUG", "gimle")
    entity_counts_per_project: dict[str, dict[str, int]] = {}
    provider_mismatches: list[str] = []

    if neo4j_ok:
        for slug in slugs:
            gid = f"project/{slug}"
            nodes = await graphiti.nodes.entity.get_by_group_ids([gid])
            counts: dict[str, int] = {}
            project_stored_hash: str | None = None
            for n in nodes:
                for lbl in n.labels:
                    if lbl == "Entity":
                        continue
                    counts[lbl] = counts.get(lbl, 0) + 1
                if "Project" in n.labels:
                    project_stored_hash = n.attributes.get("provider_config_hash")
            entity_counts_per_project[slug] = counts

            # Dim-mismatch detection
            if project_stored_hash and embedding_model:
                current_hash = _current_provider_hash(graphiti)
                if current_hash != project_stored_hash:
                    provider_mismatches.append(slug)

    # Legacy fields — use default project counts for backward-compat
    legacy_counts = entity_counts_per_project.get(default_slug, {})

    return HealthResponse(
        neo4j_reachable=neo4j_ok,
        graphiti_initialized=neo4j_ok,
        embedder_reachable=embedding_model is not None,
        embedding_model=embedding_model,
        embedding_provider_base_url=base_url,
        entity_counts=legacy_counts,
        projects=slugs,
        default_project=default_slug if default_slug in slugs else None,
        entity_counts_per_project=entity_counts_per_project,
        provider_config_hash_mismatches=provider_mismatches,
        # legacy last_ingest_* fields: find latest IngestRun across all projects
        last_ingest_started_at=None,
        last_ingest_finished_at=None,
        last_ingest_duration_ms=None,
        last_ingest_errors=[],
    )


def _current_provider_hash(graphiti: Graphiti) -> str:
    from hashlib import sha256
    model = graphiti.embedder.config.embedding_model  # type: ignore[attr-defined]
    dim = getattr(graphiti.embedder.config, "embedding_dim", 0)  # type: ignore[attr-defined]
    return sha256(f"{model}:{dim}".encode()).hexdigest()[:16]
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/memory/test_health.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/schema.py services/palace-mcp/src/palace_mcp/memory/health.py services/palace-mcp/tests/memory/test_health.py
git commit -m "feat(memory): health exposes per-project counts + dim-mismatch detection"
```

---

## Phase 4 — New tools: list_projects, get_project_overview, register_project

### Task 9: Tool handlers

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/projects/tools.py`
- Test: `services/palace-mcp/tests/projects/test_tools.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/projects/test_tools.py`:

```python
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from graphiti_core.nodes import EntityNode

from palace_mcp.projects.schema import RegisterProjectRequest
from palace_mcp.projects.tools import (
    get_project_overview,
    list_projects,
    register_project,
)


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "_registry.yaml").write_text(yaml.safe_dump({"projects": ["gimle"]}))
    (projects_dir / "gimle.yaml").write_text(yaml.safe_dump({
        "slug": "gimle", "name": "Gimle", "tags": ["bootstrap"],
        "language": "python", "framework": "fastmcp", "repo_url": None,
    }))
    return tmp_path


@pytest.mark.asyncio
async def test_list_projects_returns_registry(project_tree: Path) -> None:
    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=[
        EntityNode(uuid="p1", name="gimle", labels=["Project"],
                    group_id="project/gimle", summary="Gimle",
                    attributes={
                        "slug": "gimle", "name": "Gimle", "tags": ["bootstrap"],
                        "language": "python", "framework": "fastmcp",
                        "provider_config_hash": "abc",
                    }),
        EntityNode(uuid="i1", name="issue", labels=["Issue"],
                    group_id="project/gimle", summary="i",
                    attributes={"source": "paperclip"}),
    ])

    resp = await list_projects(graphiti)
    assert len(resp.projects) == 1
    info = resp.projects[0]
    assert info.slug == "gimle"
    assert info.entity_counts["Project"] == 1
    assert info.entity_counts["Issue"] == 1
    assert info.provider_config_hash == "abc"


@pytest.mark.asyncio
async def test_register_project_writes_files_and_node(project_tree: Path) -> None:
    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_uuid = AsyncMock(side_effect=Exception("NotFound"))
    graphiti.nodes.entity.save = AsyncMock()

    req = RegisterProjectRequest(
        slug="medic", name="Medic Healthcare",
        tags=["mobile", "kmp", "healthcare"],
    )
    info = await register_project(graphiti, req)
    assert info.slug == "medic"
    assert info.tags == ["mobile", "kmp", "healthcare"]

    # Files written
    assert (project_tree / "projects" / "medic.yaml").exists()
    registry = yaml.safe_load((project_tree / "projects" / "_registry.yaml").read_text())
    assert "medic" in registry["projects"]

    # :Project node saved
    graphiti.nodes.entity.save.assert_awaited_once()
    saved = graphiti.nodes.entity.save.await_args.args[0]
    assert saved.labels == ["Project"]
    assert saved.group_id == "project/medic"


@pytest.mark.asyncio
async def test_get_project_overview_returns_info(project_tree: Path) -> None:
    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=[
        EntityNode(uuid="p1", name="gimle", labels=["Project"],
                    group_id="project/gimle", summary="Gimle",
                    attributes={
                        "slug": "gimle", "name": "Gimle", "tags": ["bootstrap"],
                        "language": "python",
                    }),
    ])
    info = await get_project_overview(graphiti, "gimle")
    assert info.slug == "gimle"
    assert info.entity_counts["Project"] == 1
```

- [ ] **Step 2: Implement tools**

Create `services/palace-mcp/src/palace_mcp/projects/tools.py`:

```python
"""MCP tool handlers for palace.memory.list_projects / get_project_overview / register_project."""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path

from graphiti_core import Graphiti

from palace_mcp.ingest.builders import build_project_node
from palace_mcp.projects.registry import (
    ProjectNotFoundError,
    add_slug,
    load_project_config,
    load_slugs,
    write_project_config,
)
from palace_mcp.projects.schema import (
    ListProjectsResponse,
    ProjectConfig,
    ProjectInfo,
    RegisterProjectRequest,
)


def _projects_dir() -> Path:
    return Path(os.getenv("PALACE_PROJECTS_DIR", "projects"))


def _registry_path() -> Path:
    return _projects_dir() / "_registry.yaml"


async def _collect_entity_counts(
    graphiti: Graphiti, group_id: str
) -> tuple[dict[str, int], str | None]:
    """Return (label→count, stored_provider_hash) for a given project group."""
    nodes = await graphiti.nodes.entity.get_by_group_ids([group_id])
    counts: dict[str, int] = {}
    stored_hash: str | None = None
    for n in nodes:
        for lbl in n.labels:
            if lbl == "Entity":
                continue
            counts[lbl] = counts.get(lbl, 0) + 1
        if "Project" in n.labels:
            stored_hash = n.attributes.get("provider_config_hash")
    return counts, stored_hash


async def _build_project_info(
    graphiti: Graphiti, cfg: ProjectConfig
) -> ProjectInfo:
    counts, hash_ = await _collect_entity_counts(graphiti, f"project/{cfg.slug}")
    return ProjectInfo(
        slug=cfg.slug,
        name=cfg.name,
        tags=cfg.tags,
        language=cfg.language,
        framework=cfg.framework,
        repo_url=cfg.repo_url,
        entity_counts=counts,
        provider_config_hash=hash_,
    )


async def list_projects(graphiti: Graphiti) -> ListProjectsResponse:
    slugs = load_slugs(_registry_path())
    projects: list[ProjectInfo] = []
    for slug in slugs:
        try:
            cfg = load_project_config(slug, _projects_dir())
        except ProjectNotFoundError:
            continue
        projects.append(await _build_project_info(graphiti, cfg))
    return ListProjectsResponse(projects=projects)


async def get_project_overview(graphiti: Graphiti, slug: str) -> ProjectInfo:
    cfg = load_project_config(slug, _projects_dir())
    return await _build_project_info(graphiti, cfg)


async def register_project(
    graphiti: Graphiti, req: RegisterProjectRequest
) -> ProjectInfo:
    from datetime import datetime, timezone

    projects_dir = _projects_dir()
    registry_path = _registry_path()

    # 1. Build + persist ProjectConfig
    cfg = ProjectConfig(
        slug=req.slug, name=req.name, tags=req.tags,
        language=req.language, framework=req.framework, repo_url=req.repo_url,
    )
    write_project_config(cfg, projects_dir)

    # 2. Add to registry (atomic)
    add_slug(registry_path, req.slug)

    # 3. Upsert :Project node
    provider_hash = sha256(
        f"{graphiti.embedder.config.embedding_model}:{graphiti.embedder.config.embedding_dim}".encode()  # type: ignore[attr-defined]
    ).hexdigest()[:16]
    node = build_project_node(
        cfg,
        run_started=datetime.now(timezone.utc).isoformat(),
        provider_config_hash=provider_hash,
    )
    try:
        await graphiti.nodes.entity.get_by_uuid(node.uuid)
        # Already exists — overwrite
        await graphiti.nodes.entity.save(node)
    except Exception:
        await graphiti.nodes.entity.save(node)

    return await _build_project_info(graphiti, cfg)
```

- [ ] **Step 3: Run — expect PASS**

```bash
uv run pytest tests/projects/test_tools.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/projects/tools.py services/palace-mcp/tests/projects/test_tools.py
git commit -m "feat(projects): list_projects, get_project_overview, register_project tools"
```

### Task 10: Register tools in mcp_server.py

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py`

- [ ] **Step 1: Register 3 new tool handlers**

Add to `mcp_server.py` next to existing tool registrations (find the `_mcp.tool()` decorator pattern and add three more):

```python
from palace_mcp.projects.schema import (
    ListProjectsResponse,
    ProjectInfo,
    RegisterProjectRequest,
)
from palace_mcp.projects.tools import (
    get_project_overview as _get_project_overview,
    list_projects as _list_projects,
    register_project as _register_project,
)


@_mcp.tool(name="palace.memory.list_projects")
@handle_tool_error
async def palace_memory_list_projects() -> ListProjectsResponse:
    if _graphiti is None:
        raise DriverUnavailableError()
    return await _list_projects(_graphiti)


@_mcp.tool(name="palace.memory.get_project_overview")
@handle_tool_error
async def palace_memory_get_project_overview(slug: str) -> ProjectInfo:
    if _graphiti is None:
        raise DriverUnavailableError()
    return await _get_project_overview(_graphiti, slug)


@_mcp.tool(name="palace.memory.register_project")
@handle_tool_error
async def palace_memory_register_project(
    req: RegisterProjectRequest,
) -> ProjectInfo:
    if _graphiti is None:
        raise DriverUnavailableError()
    return await _register_project(_graphiti, req)
```

Update `_registered_tool_names` to include the three new names (spec §assertion at boot):

```python
_registered_tool_names = [
    "palace.health.status",
    "palace.memory.lookup",
    "palace.memory.health",
    "palace.memory.list_projects",
    "palace.memory.get_project_overview",
    "palace.memory.register_project",
]
```

- [ ] **Step 2: Write MCP-server-level smoke test**

Append to `services/palace-mcp/tests/test_mcp_server.py` (or create `test_mcp_server_n1b.py`):

```python
@pytest.mark.asyncio
async def test_mcp_server_registers_n1b_tools() -> None:
    from palace_mcp.mcp_server import _registered_tool_names
    assert "palace.memory.list_projects" in _registered_tool_names
    assert "palace.memory.get_project_overview" in _registered_tool_names
    assert "palace.memory.register_project" in _registered_tool_names
```

- [ ] **Step 3: Run + verify**

```bash
uv run pytest tests/test_mcp_server.py -v
uv run mypy --strict src
```

Expected: PASS + mypy clean.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/mcp_server.py services/palace-mcp/tests/test_mcp_server.py
git commit -m "feat(mcp): register list_projects/get_project_overview/register_project tools"
```

---

## Phase 5 — Final verification + PR

### Task 11: Full test suite + mypy + no-raw-Cypher gate

- [ ] **Step 1: Run all quality gates**

```bash
cd services/palace-mcp
uv run mypy --strict src
uv run ruff check src tests
uv run pytest -v
```

Expected: mypy clean, ruff clean, all tests PASS (including existing N+1a `test_no_raw_cypher.py` still green).

- [ ] **Step 2: Verify registry file ends up in git**

```bash
cd ..  # back to repo root
git status projects/
# expected: clean (both _registry.yaml and gimle.yaml already committed in Task 1)
```

### Task 12a: QAEngineer live smoke on iMac production checkout (Phase 4.1 explicit)

**Owner:** QAEngineer (paperclip agent).
**Trigger:** After CR APPROVE on PR, BEFORE squash-merge.

QA runs smoke on the iMac production checkout so the same environment used for production deployment is validated. This prevents the N+1a gap where smoke ran on ephemeral compose and iMac was left stale until Board manually rebuilt.

- [ ] **Step 1: SSH to iMac + check out feature branch**

```bash
ssh imac-ssh.ant013.work
cd /Users/Shared/Ios/Gimle-Palace
git fetch origin
git checkout feature/GIM-NN-palace-memory-n1b-multi-project  # use actual issue number
git log --oneline -3  # verify latest feature branch HEAD
```

- [ ] **Step 2: Rebuild compose with new code**

```bash
docker compose pull
docker compose up -d --build
sleep 45
docker compose ps  # all healthy
```

- [ ] **Step 3: Smoke — multi-project scoping**

```bash
# Health should show projects=["gimle"] + default_project="gimle"
curl -sS http://localhost:8080/mcp -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"palace.memory.health","arguments":{}}}' | jq '.result'

# Lookup with project="gimle" explicit
curl -sS http://localhost:8080/mcp ... \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"palace.memory.lookup",
                 "arguments":{"entity_type":"Issue","project":"gimle","limit":5}}}' | jq '.result.items | length'

# Register test Medic project
curl -sS http://localhost:8080/mcp ... \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call",
       "params":{"name":"palace.memory.register_project",
                 "arguments":{"slug":"medic","name":"Medic Healthcare",
                              "tags":["mobile","kmp","healthcare"]}}}'

# list_projects must return both
curl -sS http://localhost:8080/mcp ... \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call",
       "params":{"name":"palace.memory.list_projects","arguments":{}}}' | jq '.result.projects[].slug'

# Cross-project lookup — empty for medic (no data), Gimle issues for "*"
curl -sS http://localhost:8080/mcp ... \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call",
       "params":{"name":"palace.memory.lookup",
                 "arguments":{"entity_type":"Issue","project":"*","limit":5}}}' | jq '.result.items | length'
```

- [ ] **Step 4: Post evidence as comment in GIM-NN issue**

Attach:
- Full output of each curl above (redact sensitive values)
- `docker compose logs --tail 30 palace-mcp` output
- git SHA of feature branch HEAD tested

Comment format:
```
QA Phase 4.1 evidence (GIM-NN, iMac production checkout):

Feature SHA: <sha>
Health: projects=["gimle"], default_project="gimle", embedder_reachable=true ✅
Lookup(project="gimle"): 31 items ✅
register_project(medic): 200 OK, :Project node created ✅
list_projects: [gimle, medic] ✅
Lookup(project="*"): 31 items (Gimle issues, Medic empty) ✅

PASS — ready for CR mechanical review + merge.
```

- [ ] **Step 5: LEAVE iMac on feature branch until merge, then reset**

After squash-merge to develop, QA returns to iMac:

```bash
ssh imac-ssh.ant013.work
cd /Users/Shared/Ios/Gimle-Palace
git fetch origin
git checkout develop
git reset --hard origin/develop  # takes the squash-merge commit
docker compose pull
docker compose up -d --build
sleep 45
curl -sS http://localhost:8080/healthz   # must return 200 ok
exit
```

This closes the discipline gap: QA leaves iMac on `develop` matching origin, ready for next slice. Per `feedback_imac_checkout_discipline.md`.

### Task 12b: Open PR + handoff to CodeReviewer

- [ ] **Step 1: Push branch**

```bash
git push -u origin feature/GIM-NN-palace-memory-n1b-multi-project
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base develop --title "N+1b Multi-project + :Project entity (GIM-NN)" --body "$(cat <<'EOF'
## Summary
- Introduce `:Project` entity and project-registry file (`projects/_registry.yaml`).
- Add `project: str | list[str] | "*" | None` scoping to `palace.memory.lookup` and `palace.memory.health`.
- New MCP tools: `palace.memory.list_projects`, `palace.memory.get_project_overview`, `palace.memory.register_project`.
- Validate multi-project schema via live `register_project(slug="medic", ...)` — no data ingest, schema-proof only.
- Zero raw Cypher (inherited from N+1a; test_no_raw_cypher.py still green).

## Spec
docs/superpowers/specs/2026-04-18-palace-memory-n1b-multi-project.md

## Plan
docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1b-multi-project.md

## Test plan
- [ ] mypy --strict green
- [ ] ruff clean
- [ ] All unit tests pass (existing N+1a tests + new N+1b tests)
- [ ] tests/test_no_raw_cypher.py still passes
- [ ] Live smoke (QA): `register_project(slug="medic",...)` creates yaml + node; `list_projects` returns both; `lookup(entity_type="Issue", project="medic")` empty; `lookup(project="*")` same as Gimle issues

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Reassign to CodeReviewer per workflow**

Via paperclip UI or CLI.

---

## Self-Review Notes

- **Spec coverage:** every spec §9 acceptance item mapped to a task:
  - `:Project` entity build → Task 4
  - Lookup scoping → Task 7
  - Health fields → Task 8
  - list_projects/get_project_overview/register_project → Task 9+10
  - Registry atomic write → Task 3
  - `DEFAULT_PROJECT_SLUG` respected → Task 5 resolver test
  - Unknown slug graceful error → Task 5 + Task 7 tests
  - `*` enumeration → Task 5 + Task 7
  - Zero raw Cypher — inherited from N+1a, `test_no_raw_cypher.py` still green (Task 11 step 1)
  - mypy --strict → Task 11

- **Type consistency:** `ProjectConfig`, `ProjectInfo`, `RegisterProjectRequest`, `ListProjectsResponse`, `resolve_group_ids`, `load_slugs`, `add_slug`, `build_project_node`, `PROJECT_NAMESPACE_UUID` — all consistent across tasks.

- **No placeholders:** every step has concrete code or command.

---

## Execution Handoff

Plan complete. Handoff via paperclip per canonical workflow: Board creates GIM-NN issue referencing spec + plan → CTO formalizes (feature branch off develop, copy plan file, rename NN → issue number) → reassign to CodeReviewer for plan-first compliance → MCPEngineer executes Tasks 1-12.

Predecessor: N+1a (GIM-48) merged as `9d87fa0` on develop.
