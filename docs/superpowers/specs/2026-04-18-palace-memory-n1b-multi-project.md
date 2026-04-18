# Palace Memory — N+1b Multi-project + :Project entity

**Date:** 2026-04-18
**Slice:** N+1b (second of three N+1 sub-slices)
**Author:** Board
**Status:** Draft — awaiting CTO formalization as GIM-NN issue
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §5.1, §6; `docs/research/graphiti-core-verification.md`
**Predecessor slice:** N+1a (Graphiti substrate swap) — `docs/superpowers/specs/2026-04-18-palace-memory-n1a-graphiti-substrate-swap.md`
**Successor slice:** N+1c (Agent MCP + record_note + provider)

## 1. Context

N+1a swapped the substrate to Graphiti with hardcoded `group_id="project/gimle"`. This slice introduces a first-class `:Project` entity and extends all existing tools to accept project scoping, unlocking the architectural property the user asked for: *one server hosts many projects; agents working on a new project can find reusable components from previously analyzed related projects*.

Multi-project is substrate-level because group_id choice propagates into every future extractor (N+2…N+6). Deferring it means each extractor would have to handle the switch retroactively. Doing it now, while only Gimle data exists, validates the multi-project path on a 1-project state with schema proof for 2+ projects.

## 2. Goal

After this slice:
- A `:Project` entity node exists for Gimle, with `slug`, `name`, `tags` attributes from a `project.yaml` config.
- All read tools (`lookup`, `search` [coming in N+1c — spec-reserved here], `health`) accept `project: str | list[str] | "*" | None`.
- Two new read tools exist: `list_projects` and `get_project_overview`.
- The ingest CLI takes `--project-slug` (default `gimle`) and writes to `group_id=project/<slug>`.
- Schema and tool surface are validated for multi-project by manually creating a second `:Project` node (`medic` placeholder) via test fixture and verifying scoping behavior.

**Success criterion:** `palace.memory.list_projects()` returns both Gimle (live data) and a test Medic project (no data); `palace.memory.lookup(entity_type="Issue", project="gimle")` returns Gimle issues only; `palace.memory.lookup(entity_type="Issue", project="medic")` returns empty list (no data yet) without error; `palace.memory.lookup(entity_type="Issue", project=["gimle", "medic"])` returns the Gimle issues; `palace.memory.lookup(entity_type="Issue", project="*")` returns the same (all projects).

## 3. Architecture

No new compose services. Schema change on existing Graphiti substrate.

```
┌─────────────────────┐                      ┌──────────────────────────────────┐
│ Paperclip HTTP API  │◄─── ingest ─────────►│ palace-mcp                       │
│                     │   --project-slug=X   │  ├── palace.memory.lookup(..., project=...)
│                     │                      │  ├── palace.memory.health(...)   │
│                     │                      │  ├── palace.memory.list_projects │ NEW
│                     │                      │  └── palace.memory.get_project_overview │ NEW
└─────────────────────┘                      └───────────────┬──────────────────┘
                                                             │ HTTP
                                                             ▼
                                             ┌──────────────────────────────────┐
                                             │ graphiti (unchanged from N+1a)   │
                                             │  Neo4j group_id-scoped reads     │
                                             └──────────────────────────────────┘
```

### 3.1 project.yaml (new)

Per-project config committed to the repo at `projects/<slug>.yaml`. Aligns with spec §6.1 skeleton. This slice ships one: `projects/gimle.yaml`.

```yaml
# projects/gimle.yaml
slug: gimle
name: Gimle Palace Bootstrap
tags: [python, agent-framework, paperclip, bootstrap]
language: python
framework: fastmcp
repo_url: https://github.com/ant013/Gimle-Palace
```

Multiple projects = multiple yaml files, each ingested separately with its own `--project-slug`.

## 4. Graphiti schema (additions)

### 4.1 :Project entity

```python
EntityNode(
    uuid=uuid5(PROJECT_NAMESPACE, project_slug),   # deterministic UUID from slug
    name=project_slug,                              # "gimle"
    labels=["Project", "Entity"],
    group_id=f"project/{project_slug}",            # "project/gimle"
    summary=project.name,                           # "Gimle Palace Bootstrap"
    attributes={
        "slug": project.slug,
        "name": project.name,
        "tags": project.tags,                       # ["python", "agent-framework", ...]
        "language": project.language,
        "framework": project.framework,
        "repo_url": project.repo_url,
        "source_created_at": now_iso(),             # first ingest time
        "source_updated_at": now_iso(),
        "palace_last_seen_at": now_iso(),
    }
)
```

`:Project` is itself scoped to its own group_id (`project/gimle`) — a project describes itself within its own namespace. Cross-project enumeration walks distinct group_ids (§5.3 query).

### 4.2 No `:BELONGS_TO_PROJECT` edges

Per verification `graphiti-core-verification.md` finding: `group_id` is THE namespace mechanism. Explicit `:BELONGS_TO_PROJECT` edges would be double-indexing and introduce divergence risk.

Project association is purely via `group_id`. Cypher queries that need project context filter by `group_id` directly:

```cypher
MATCH (n:Issue {group_id: "project/gimle"}) RETURN n   # direct lookup
```

Or via graphiti-core API:

```python
issues = await graphiti.get_by_group_ids(["project/gimle"], labels=["Issue"])
```

## 5. Multi-project scoping API

### 5.1 `project` parameter semantics

All applicable tools accept `project: str | list[str] | "*" | None`:

| Value | Graphiti call | Meaning |
|---|---|---|
| `None` (default) | `group_ids=[current_project]` from MCP session context, fallback to env `DEFAULT_PROJECT_SLUG` | "Current project" — default behavior |
| `"gimle"` | `group_ids=["project/gimle"]` | Explicit single project |
| `["gimle", "medic"]` | `group_ids=["project/gimle", "project/medic"]` | Explicit subset |
| `"*"` | `group_ids=<enumerate all via get_distinct_group_ids>` | All projects on server |

Invalid values (non-existent slug, mixed types in list, etc.) → tool returns `ok: false` with explanation; no ingress into Cypher.

### 5.2 MCP session project context

External MCP clients don't naturally carry "current project" state. Two implementation paths:

**A (simple, N+1b):** Require explicit `project=...` on every call; `None` falls back to `DEFAULT_PROJECT_SLUG` env (default `gimle`). Documented behavior: "always pass project explicitly or set env."

**B (deferred):** MCP session binding — when client connects, negotiate current project via an init handshake. Requires FastMCP context extension. Deferred to post-multi-project slice.

N+1b ships **A**. Works today, aligns with tool-call explicitness, no session state to manage.

### 5.3 Cross-project query (`project="*"`)

Implementation: at tool invocation time, if `project="*"`:

```python
async def resolve_group_ids(project: str | list[str] | None) -> list[str]:
    if project is None:
        return [f"project/{os.getenv('DEFAULT_PROJECT_SLUG', 'gimle')}"]
    if project == "*":
        # Single cheap query — graphiti-core doesn't ship this, we add a helper
        all_ids = await graphiti.driver.execute_query(
            "MATCH (p:Project:Entity) RETURN DISTINCT p.group_id AS group_id"
        )
        return [r["group_id"] for r in all_ids]
    if isinstance(project, str):
        return [f"project/{project}"]
    return [f"project/{slug}" for slug in project]
```

Result: O(P+N) where P = projects count (≤20 at full server), N = matching entities. Zero overhead when `P=1` (current state).

## 6. MCP tool surface — updates + 2 new

| Tool | N+1b behavior |
|---|---|
| `palace.health.status` | Unchanged |
| `palace.memory.lookup(entity_type, filters, project, limit, order_by)` | `project` param added; `resolve_group_ids` prefix; else N+1a behavior |
| `palace.memory.health()` | Unchanged endpoint; response now includes `projects: list[str]` (all discovered slugs) + `default_project: str` (from env) |
| **NEW** `palace.memory.list_projects()` | Returns `list[ProjectInfo]` — slug, name, tags, last_ingest timestamp, entity_counts by label. |
| **NEW** `palace.memory.get_project_overview(project)` | Returns `ProjectInfo` for specified project + last N ingest runs + recent activity summary. |

Tool signatures (Pydantic):

```python
class ProjectInfo(BaseModel):
    slug: str
    name: str
    tags: list[str]
    language: str | None
    framework: str | None
    repo_url: str | None
    last_ingest_at: str | None
    entity_counts: dict[str, int]   # {"Issue": 31, "Comment": 52, "Agent": 12, "Note": 0}

class ListProjectsResponse(BaseModel):
    projects: list[ProjectInfo]
```

## 7. Ingest pipeline (small delta from N+1a)

### 7.1 CLI changes

```bash
python -m palace_mcp.ingest.paperclip \
    --paperclip-url https://paperclip.ant013.work \
    --company-id 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64 \
    --project-slug gimle \
    --project-config projects/gimle.yaml
```

`--project-slug` defaults to `gimle` (back-compat with N+1a). `--project-config` defaults to `projects/<slug>.yaml`.

### 7.2 Phases (additions to N+1a flow)

```python
async def run_ingest(project_slug: str, project_config: Path):
    # ... N+1a setup unchanged ...
    group_id = f"project/{project_slug}"

    # NEW: read project.yaml, ensure :Project node exists first
    project_yaml = load_project_yaml(project_config)
    project_node = build_project_node(project_yaml, group_id)
    await upsert_with_change_detection(graphiti, project_node)

    # NEW: update project_node.attributes.palace_last_seen_at at ingest end
    # regardless of Issue/Comment counts (proves project is still live)

    # ... rest of N+1a ingest ... all group_id references now = project/{slug}
```

All entity upserts use `group_id` variable (not hardcoded string) — prepared from N+1a `project/gimle` → N+1b `project/{project_slug}`.

## 8. Observability

### 8.1 Log event additions

```
{"event":"ingest.start","source":"paperclip","run_id":"...","project_slug":"gimle","group_id":"project/gimle"}
{"event":"ingest.project.upsert","slug":"gimle","tags":["python","..."]}
{"event":"query.lookup","entity_type":"Issue","filters":...,"project_scope":"gimle","matched":3,"duration_ms":12}
{"event":"query.lookup","entity_type":"Issue","filters":...,"project_scope":"*","group_ids_resolved":["project/gimle","project/medic"],"matched":3,"duration_ms":18}
```

### 8.2 Health tool extension

```json
{
  "ok": true,
  "data": {
    "neo4j_reachable": true, "graphiti_reachable": true, "embedder_reachable": true,
    "embedding_model": "nomic-embed-text",
    "projects": ["gimle"],
    "default_project": "gimle",
    "entity_counts_per_project": {
      "gimle": {"Issue": 31, "Comment": 52, "Agent": 12, "Project": 1}
    },
    "last_ingest_per_project": {
      "gimle": {"started_at": "...", "finished_at": "...", "errors": []}
    }
  }
}
```

## 9. Decomposition (plan-first ready)

Expected plan-file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1b-multi-project.md`.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create GIM-NN issue + plan file. Reassign to CodeReviewer. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance; verify N+1a merged + green on develop. APPROVE → Phase 2. |
| 2 | 2.1 | MCPEngineer | Add `projects/gimle.yaml` + loader. Schema validation via Pydantic. |
| 2 | 2.2 | MCPEngineer | Add `:Project` entity build in ingest; `--project-slug` / `--project-config` CLI params; parameterize group_id. |
| 2 | 2.3 | MCPEngineer | Implement `resolve_group_ids(project)` helper + tests (None, str, list, "*", invalid). |
| 2 | 2.4 | MCPEngineer | Add `project` param to `palace.memory.lookup` + `palace.memory.health`. Preserve N+0 response shape, add fields to meta. |
| 2 | 2.5 | MCPEngineer | Implement `palace.memory.list_projects` + `palace.memory.get_project_overview`. Register in FastMCP. |
| 2 | 2.6 | MCPEngineer | Unit tests — resolve_group_ids, project scoping on lookup, list_projects, get_project_overview, multi-project fixture setup (manually insert test `:Project` node via Cypher). |
| 3 | 3.1 | CodeReviewer | PR review: compliance, no `:BELONGS_TO_PROJECT` edge slippage, whitelist filter resolver handles project param correctly. |
| 3 | 3.2 | OpusArchitectReviewer | (If wired) context7 cross-check on `get_by_group_ids` API usage. |
| 4 | 4.1 | QAEngineer | Live smoke: ingest with `--project-slug=gimle`; verify `list_projects` returns Gimle; insert test `:Project {slug: 'medic'}` node via neo4j-shell; verify `lookup(project="medic")` returns empty, `lookup(project="*")` returns Gimle issues. |
| 4 | 4.2 | MCPEngineer | Squash-merge, update checkboxes, manual iMac deploy. |

## 10. Acceptance criteria

- [ ] PR opened against develop; squash-merged on APPROVE.
- [ ] Plan file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1b-multi-project.md`.
- [ ] `projects/gimle.yaml` committed with slug, name, tags (≥3), language, framework.
- [ ] `:Project` entity created for Gimle during first ingest; `palace.memory.list_projects()` returns Gimle with entity counts matching N+1a live data.
- [ ] `palace.memory.lookup(entity_type="Issue", project="gimle")` returns same results as N+1a without `project` param.
- [ ] `palace.memory.lookup(entity_type="Issue", project="medic")` returns empty list gracefully (no error on non-existent project).
- [ ] Manual fixture: test `:Project {slug: "medic"}` node inserted via Cypher; `palace.memory.list_projects()` returns both Gimle and Medic; `palace.memory.lookup(entity_type="Issue", project=["gimle", "medic"])` returns Gimle's issues; `palace.memory.lookup(entity_type="Issue", project="*")` returns same.
- [ ] `DEFAULT_PROJECT_SLUG` env var respected when `project=None` on tool calls.
- [ ] `palace.memory.health()` response includes `projects: list[str]` and `default_project` fields; `entity_counts_per_project` populated.
- [ ] `palace.memory.get_project_overview("gimle")` returns full `ProjectInfo` with tags, language, framework, last_ingest_at, entity_counts.
- [ ] `uv run mypy --strict` green.
- [ ] CI green on all four jobs.
- [ ] Post-merge: manual iMac deploy; user verifies `palace.memory.list_projects` from Claude Code returns expected data.

## 11. Out of scope (explicit)

- **`:BELONGS_TO_PROJECT` edges.** group_id is sole namespace primitive (per verification doc).
- **MCP session project context (path B).** Explicit `project=` param on every call in N+1b.
- **project.yaml full spec §6.1 schema.** Subset: slug, name, tags, language, framework, repo_url. Fields like `preset`, `extractors`, `team_template`, `paths.exclude` come with their extractor slices.
- **Tag-based fuzzy relatedness auto-expansion.** `project="*"` enumerates all; auto-related-by-tag expansion is a follow-up slice (requires shared tag vocabulary + UX decision: "should find_context_for_task automatically include related projects?").
- **Second live project.** Only Gimle has live data; Medic is a test-fixture `:Project` node.
- **record_note / search / graphiti-mcp / per-agent auth / provider installer UX.** All N+1c.
- **Project-level auth / access control.** Single-operator trust model from N+0 preserved. Per-project tokens land when N+1c auth pattern extends.
- **Cross-project `:RELATED_TO` edges (Variant γ).** Tag-based fuzzy only; explicit relations deferred post-N+6.

## 12. Estimated size

- Code: ~300 LOC (project.yaml loader ~60, :Project node build ~40, resolve_group_ids ~30, tool updates ~80, new tools ~50, tests ~40).
- Plan + docs: ~50 LOC.
- 1 PR, 4-5 handoffs.
- Expected duration: 2 days agent-time.

## 13. Followups

- N+1c starts immediately after merge.
- Evaluate `project="*"` performance at 3+ projects before planning next extractor slice; current O(P+N) may need tuning.
- Consider MCP session project context (path B) if explicit `project=` on every call proves ergonomically painful for Claude Code / Cursor users.
- Extend `projects/gimle.yaml` as extractor slices add new schema (preset, team_template, etc.) — each slice owns its own project.yaml field additions.
