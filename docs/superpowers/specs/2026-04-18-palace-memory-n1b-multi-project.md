# Palace Memory — N+1b Multi-project + :Project entity

**Date:** 2026-04-18 (revision 2 — post extended verification)
**Slice:** N+1b (second of three N+1 sub-slices)
**Author:** Board
**Status:** Draft — awaiting CTO formalization as GIM-NN issue
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §5.1, §6; `docs/research/graphiti-core-verification.md` §5.C, §5.E (SearchFilters)
**Predecessor:** N+1a
**Successor:** N+1c

## 1. Context

N+1a shipped substrate with hardcoded `group_id="project/gimle"`. This slice introduces `:Project` entity + project scoping on tools + a registry file (`projects/_registry.yaml`) for cheap enumeration, validating that schema supports N+ projects without migration.

**Architectural choices locked from verification:**
- No raw Cypher for project enumeration — registry file + graphiti API.
- `SearchFilters(node_labels=[...])` for label-pushdown in lookup when we migrate off pure-Python filter at scale.
- No `:BELONGS_TO_PROJECT` edge (double-indexing avoided; `group_id` is sole namespace primitive).
- `palace.memory.register_project(slug, name, tags)` as first-class tool (no manual Cypher fixture).

## 2. Goal

- `:Project` entity exists for Gimle, with slug/name/tags/language/framework from `projects/gimle.yaml`.
- All applicable tools accept `project: str | list[str] | "*" | None`.
- Two new read tools (`list_projects`, `get_project_overview`) + one new write tool (`register_project`).
- `--project-slug` on ingest CLI.
- Multi-project validated via registering a second test `:Project` (`medic` placeholder) and verifying scoping without data.

**Success criterion:** `palace.memory.register_project(slug="medic", name="Medic Healthcare", tags=["mobile", "kmp", "healthcare"])` → `palace.memory.list_projects()` returns both Gimle (live) and Medic (registered, no data). `palace.memory.lookup(entity_type="Issue", project="medic")` returns empty without error. `palace.memory.lookup(entity_type="Issue", project=["gimle", "medic"])` returns Gimle's issues. `palace.memory.lookup(entity_type="Issue", project="*")` returns same.

## 3. Architecture

No new compose services. Schema adds one entity + registry file. Tools gain a parameter.

```
┌─────────────────────┐                      ┌──────────────────────────────────┐
│ Paperclip HTTP API  │◄─── ingest ─────────►│ palace-mcp (graphiti embedded)   │
│                     │  --project-slug=X    │  Tools:                          │
│                     │  --project-config=P  │   ├── lookup(..., project=...)   │
│                     │                      │   ├── health(...)                │
│                     │                      │   ├── list_projects()    NEW     │
│                     │                      │   ├── get_project_overview NEW   │
│                     │                      │   └── register_project   NEW     │
└─────────────────────┘                      │                                  │
                                             │  Uses: projects/_registry.yaml   │
                                             │  for fast enumeration            │
                                             └──────────────────────────────────┘

projects/
├── _registry.yaml     # list of slugs (maintained atomically on register)
├── gimle.yaml         # per-project config
└── (medic.yaml)       # future
```

### 3.1 `projects/_registry.yaml`

```yaml
# Source of truth for all projects known to this palace instance.
# Updated by register_project tool + ingest CLI when new --project-slug seen.
projects:
  - gimle
  - medic     # example, test fixture in N+1b acceptance
```

Registry avoids raw Cypher for project enumeration. Kept simple: one list of slugs. Per-project detail lives in individual yaml files.

### 3.2 `projects/gimle.yaml`

```yaml
slug: gimle
name: Gimle Palace Bootstrap
tags: [python, agent-framework, paperclip, bootstrap]
language: python
framework: fastmcp
repo_url: https://github.com/ant013/Gimle-Palace
```

(Subset of spec §6.1 schema; additional fields land with their extractor slices.)

## 4. Graphiti schema additions

### 4.1 `:Project` entity (auto-prepended `:Entity`)

```python
project_node = EntityNode(
    uuid=str(uuid5(PROJECT_NAMESPACE_UUID, project_slug)),   # deterministic from slug
    name=project_slug,
    labels=["Project"],                                       # :Entity auto-prepended
    group_id=f"project/{project_slug}",
    summary=project_yaml.name,
    attributes={
        "slug": project_yaml.slug,
        "name": project_yaml.name,
        "tags": project_yaml.tags,
        "language": project_yaml.language,
        "framework": project_yaml.framework,
        "repo_url": project_yaml.repo_url,
        "source_created_at": now_iso(),
        "source_updated_at": now_iso(),
        "palace_last_seen_at": now_iso(),
        "provider_config_hash": sha256(
            f"{EMBEDDING_MODEL}:{EMBEDDING_DIM}".encode()
        ).hexdigest()[:16],   # detects embedding-provider change (N+1c uses for warn)
    }
)
await graphiti.nodes.entity.save(project_node)
```

`:Project` scoped to its own `group_id` — each project describes itself within its own namespace. Zero `:BELONGS_TO_PROJECT` edges.

## 5. Multi-project scoping

### 5.1 `project` parameter semantics

All applicable tools accept `project: str | list[str] | "*" | None`.

| Value | Resolver action | Meaning |
|---|---|---|
| `None` | Read `DEFAULT_PROJECT_SLUG` env (default `gimle`) → `["project/<default>"]` | Current / default project |
| `"gimle"` | `["project/gimle"]` | Explicit single |
| `["gimle", "medic"]` | `["project/gimle", "project/medic"]` | Explicit subset |
| `"*"` | Read `projects/_registry.yaml` → `[f"project/{s}" for s in registry]` | All known projects |

### 5.2 Resolver implementation

```python
def load_registry() -> list[str]:
    path = Path("projects/_registry.yaml")
    return yaml.safe_load(path.read_text())["projects"] if path.exists() else []

async def resolve_group_ids(project: str | list[str] | None) -> list[str]:
    if project is None:
        return [f"project/{os.getenv('DEFAULT_PROJECT_SLUG', 'gimle')}"]
    if project == "*":
        return [f"project/{s}" for s in load_registry()]
    if isinstance(project, str):
        # Validate against registry to avoid silent typos
        if project not in load_registry():
            raise ValueError(f"unknown_project: {project}")
        return [f"project/{project}"]
    if isinstance(project, list):
        registry = set(load_registry())
        unknown = [s for s in project if s not in registry]
        if unknown:
            raise ValueError(f"unknown_projects: {unknown}")
        return [f"project/{s}" for s in project]
    raise TypeError(f"project must be str, list, or None; got {type(project)}")
```

### 5.3 Path A vs Path B (MCP session context)

**Path A (ships in N+1b):** explicit `project=` on every tool call; `None` → env default. Documented.

**Path B (deferred to standalone spike):** MCP session-level project context via FastMCP `Context` or URL-scoping (`/mcp/gimle`, `/mcp/medic`). 1-day spike scheduled after N+1b merge, before first real multi-project deployment (Medic team). If spike concludes URL-scoping is clean, retrofit is trivial (mount FastMCP app at `/mcp/<slug>` path prefix + inject project into tool handlers).

## 6. MCP tool surface

### 6.1 Updates

| Tool | N+1b behavior |
|---|---|
| `palace.health.status` | Unchanged |
| `palace.memory.lookup(entity_type, filters, project, limit, order_by)` | `project` param added; calls `resolve_group_ids` → `graphiti.nodes.entity.get_by_group_ids(ids)` → Python-level filter by label + attribute. |
| `palace.memory.health()` | Response gains `projects: list[str]` (from registry) + `default_project: str` + `entity_counts_per_project: dict` + `provider_config_hash_mismatches: list[str]` (slugs where stored hash differs from current env; drives embedding-dim-migration warning). |

### 6.2 New tools

```python
class ProjectInfo(BaseModel):
    slug: str
    name: str
    tags: list[str]
    language: str | None
    framework: str | None
    repo_url: str | None
    last_ingest_at: str | None
    entity_counts: dict[str, int]          # {"Issue": 31, "Comment": 52, "Agent": 12, "Note": 0, "IngestRun": 5}
    provider_config_hash: str | None       # stored at :Project creation

# palace.memory.list_projects() -> list[ProjectInfo]
# palace.memory.get_project_overview(project: str) -> ProjectInfo
# palace.memory.register_project(slug: str, name: str, tags: list[str],
#                                 language: str | None, framework: str | None,
#                                 repo_url: str | None) -> ProjectInfo
```

`register_project` writes `projects/<slug>.yaml` + updates `projects/_registry.yaml` atomically + creates `:Project` node via `graphiti.nodes.entity.save`. Idempotent: re-register same slug → updates existing yaml + bumps `source_updated_at` on the node.

## 7. Ingest pipeline delta from N+1a

### 7.1 CLI changes

```bash
python -m palace_mcp.ingest.paperclip \
    --paperclip-url https://paperclip.ant013.work \
    --company-id 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64 \
    --project-slug gimle
```

- `--project-slug` defaults to `gimle` (back-compat with N+1a).
- Loads `projects/<slug>.yaml` automatically.
- If slug not in `projects/_registry.yaml` → error with actionable message ("run `palace.memory.register_project` first").

### 7.2 Ingest flow delta

```python
group_id = f"project/{project_slug}"

# Upsert :Project node first — before Issue/Comment/Agent
project_node = build_project_node(load_project_yaml(project_slug), group_id)
await upsert_with_change_detection(graphiti, project_node)

# ... existing N+1a flow, all using group_id variable ...
```

All node+edge constructors already accepted `group_id` in N+1a (hardcoded to `project/gimle`). N+1b parameterizes — no API surface changes.

## 8. Observability

```
{"event":"ingest.start","project_slug":"gimle","group_id":"project/gimle","run_id":"..."}
{"event":"ingest.project.upsert","slug":"gimle","tags":["python",...],"provider_config_hash":"abc123..."}
{"event":"query.lookup","entity_type":"Issue","project_scope":"gimle","matched":3,"duration_ms":12}
{"event":"query.lookup","entity_type":"Issue","project_scope":"*","group_ids_resolved":["project/gimle","project/medic"],"matched":3,"duration_ms":18}
{"event":"tool.register_project","slug":"medic","tags":["mobile","kmp","healthcare"]}
```

Health tool `entity_counts_per_project` field example:

```json
{
  "projects": ["gimle", "medic"],
  "default_project": "gimle",
  "entity_counts_per_project": {
    "gimle": {"Issue": 31, "Comment": 52, "Agent": 12, "Project": 1, "IngestRun": 5},
    "medic": {"Project": 1}
  },
  "provider_config_hash_mismatches": []
}
```

## 9. Decomposition (plan-first ready)

Expected plan-file: `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1b-multi-project.md`.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create issue + plan file. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance; verify N+1a merged + green. APPROVE. |
| 2 | 2.1 | MCPEngineer | `projects/_registry.yaml` + `projects/gimle.yaml` + Pydantic loaders. |
| 2 | 2.2 | MCPEngineer | `:Project` node builder; `provider_config_hash` attribute. |
| 2 | 2.3 | MCPEngineer | `--project-slug` / `--project-config` CLI; parameterize `group_id` in all ingest builders. |
| 2 | 2.4 | MCPEngineer | `resolve_group_ids` helper + unit tests (None, str, list, "*", unknown slug, typo protection). |
| 2 | 2.5 | MCPEngineer | Add `project` param to `lookup` and `health`; preserve response shape (add fields to `meta`). |
| 2 | 2.6 | MCPEngineer | Implement `list_projects`, `get_project_overview`, `register_project` tools + registry-yaml atomic write. |
| 2 | 2.7 | MCPEngineer | Unit tests ≥30 new (project node build, register_project idempotency + file write, scoping resolver, multi-project lookup fixture). |
| 3 | 3.1 | CodeReviewer | PR review: compliance, **no raw Cypher** slippage, registry yaml atomic write safe, typo-protection in resolver. |
| 3 | 3.2 | OpusArchitectReviewer | (If wired) context7 cross-check on `get_by_group_ids` API usage. |
| 4 | 4.1 | QAEngineer | Live smoke: ingest `--project-slug=gimle`; verify `list_projects` returns Gimle; call `register_project(slug="medic",...)` → verify yaml file + :Project node + registry updated; `lookup(project="medic")` empty; `lookup(project=["gimle","medic"])` = Gimle issues; `lookup(project="*")` = same. |
| 4 | 4.2 | MCPEngineer | Squash-merge; manual iMac deploy (automation lands N+1c). |

## 10. Acceptance criteria

- [ ] PR against develop; squash-merged on APPROVE.
- [ ] `projects/_registry.yaml` + `projects/gimle.yaml` committed.
- [ ] `:Project:Entity` node created for Gimle during ingest; `provider_config_hash` attribute populated.
- [ ] `palace.memory.register_project(slug="medic", name="Medic Healthcare", tags=["mobile","kmp","healthcare"])` — file written, registry updated, :Project node created, returns `ProjectInfo`.
- [ ] Registry file updates are atomic (write to temp + rename — verified via unit test concurrency simulation).
- [ ] `palace.memory.lookup(entity_type="Issue", project="gimle")` identical to N+1a unscoped.
- [ ] `palace.memory.lookup(entity_type="Issue", project="medic")` returns empty (no error).
- [ ] `palace.memory.lookup(entity_type="Issue", project="nonexistent")` returns `ok: false, error: "unknown_project"`.
- [ ] `palace.memory.lookup(entity_type="Issue", project="*")` returns same as `["gimle", "medic"]` — Gimle's issues since Medic has none.
- [ ] `DEFAULT_PROJECT_SLUG` env respected when `project=None`.
- [ ] `palace.memory.health()` includes `projects`, `default_project`, `entity_counts_per_project`, `provider_config_hash_mismatches`.
- [ ] `palace.memory.get_project_overview("gimle")` returns full `ProjectInfo`.
- [ ] `uv run mypy --strict` green.
- [ ] CI green.
- [ ] Post-merge: manual deploy; user verifies from Claude Code.

## 11. Out of scope

- MCP session project context (Path B URL-scoping). Standalone 1-day spike scheduled after merge.
- Tag-based fuzzy auto-relatedness expansion for `find_context_for_task` — deferred to N+2+.
- `:RELATED_TO` explicit edges (variant γ) — tag-based only.
- Second live project with data — only Gimle has data; Medic is registration fixture.
- Per-project auth / access control — single-operator trust model preserved. (N+1c adds per-agent `allowed_group_ids` map.)
- `record_note`, `search`, graphiti-mcp — N+1c.
- Embedding dim migration CLI (`just reset-embeddings`) — N+1c (installer and provider-swap UX lands there).

## 12. Estimated size

- Code: ~300 LOC (loaders ~40, :Project builder ~30, resolver ~40, tool updates ~80, new tools ~60, tests ~50).
- Plan + docs: ~50 LOC.
- 1 PR, 4-5 handoffs.
- Duration: 2 days agent-time.

## 13. Followups

- **1-day spike on Path B (URL-scoping / session handshake)** before first non-Gimle project deployment.
- N+1c immediately after merge.
- If registry file concurrency becomes a concern at multi-writer scale (unlikely at <20 projects), consider a lightweight SQLite registry.
- Add `taxonomies: [...]` field to `projects/<slug>.yaml` in N+5+ slice when taxonomies start driving faceted classification.
