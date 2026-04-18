# Palace Memory — N+1b Multi-project + `:Project` entity (rev3)

**Date:** 2026-04-18 (revision 3 — post group_id migration, post N+1a revert)
**Slice:** N+1b (second of three N+1 sub-slices)
**Author:** Board
**Status:** Draft — awaiting CTO formalization
**Predecessor:** GIM-52 group_id micro-slice (`e629d97` on develop)
**Supersedes:** `2026-04-18-palace-memory-n1b-multi-project.md` (rev2, graphiti-substrate-based)

**Reference:** `reference_graphiti_core_api_truth.md` (auto-memory) —
why graphiti-core is not in scope; `feedback_qa_skipped_gim48.md` — why
gates are non-negotiable.

## 1. Why rev3

rev2 assumed N+1a Graphiti substrate. After N+1a revert, the foundation is
now N+0 + `group_id` column (GIM-52). This spec preserves the user-visible
design from rev2 (`:Project` entity, `project: str | list | "*" | None`
MCP argument, 3 new tools) but rebuilds the implementation on raw
parameterised Cypher — consistent with everything else in palace-mcp
post-revert.

Two rev2 ideas are dropped as no longer fitting:

- **No `projects/_registry.yaml`.** `:Project` nodes in Neo4j are the
  single source of truth. One fewer moving part, one fewer atomic-write
  concern, no yaml-vs-graph drift.
- **No `provider_config_hash`.** This was a graphiti-embedding-dim
  signal. We are not embedding anything in this slice. Will return when
  search lands in a future slice, probably with a dedicated mechanism.

## 2. Goal

Turn `group_id` from "hardcoded default" into a first-class namespace
dimension with self-describing `:Project` entities and scoped tool
surface. Concretely:

- `:Project {slug, name, tags, language?, framework?, repo_url?}`
  nodes exist — one per project.
- Ingest CLI and MCP tools accept a `project` / `--project-slug`
  argument, validated against the set of registered projects.
- Three new MCP tools: `list_projects`, `get_project_overview`,
  `register_project`.
- `palace.memory.health()` gains `projects`, `default_project`,
  `entity_counts_per_project`.

**Success criterion:** After this slice lands,
`palace.memory.register_project(slug="medic", name="Medic Healthcare",
tags=["mobile","kmp","healthcare"])` creates a second `:Project` node;
`list_projects()` returns both Gimle and Medic; `lookup(project="medic")`
returns empty without error; `lookup(project=["gimle","medic"])` and
`lookup(project="*")` both return Gimle's issues (Medic has none yet).

## 3. Architecture

Pure N+0 + group_id extension. No substrate change. No new compose
services. Schema adds one label plus a constraint and an index. Tools
gain a parameter.

```
┌──────────────────────┐                      ┌──────────────────────────────┐
│ Paperclip HTTP API   │◄── ingest CLI ──────►│ palace-mcp (raw Cypher)      │
│                      │  --project-slug=X    │  Tools:                      │
│                      │                      │   lookup(..., project=...)   │
│                      │                      │   health()  ← enriched       │
│                      │                      │   list_projects()     NEW    │
│                      │                      │   get_project_overview NEW   │
│                      │                      │   register_project    NEW    │
│                      │                      │                              │
│                      │                      │  :Project nodes = SOR for    │
│                      │                      │  project registry            │
└──────────────────────┘                      └──────────────────────────────┘
```

## 4. Schema additions

### 4.1 `:Project` label

Stored in Neo4j via the same raw-Cypher pattern as other entities.

Required properties:

- `slug: str` — UNIQUE, user-facing short name (`"gimle"`, `"medic"`)
- `group_id: str` — `f"project/{slug}"`. Matches the group_id used by
  that project's issues/comments/agents. The `:Project` node lives in
  its own group (self-hosted namespace).
- `name: str` — human-readable (`"Gimle Palace Bootstrap"`)
- `tags: list[str]` — free-form tags
- `source: "paperclip"` — consistent with other N+0 entities, lets
  existing GC query ignore Project nodes (they have no
  `palace_last_seen_at`).
- `source_created_at`, `source_updated_at` — ISO timestamps.

Optional properties:

- `language: str | None`
- `framework: str | None`
- `repo_url: str | None`

### 4.2 Cypher

```cypher
-- Constraint: slug is globally unique.
CREATE CONSTRAINT project_slug IF NOT EXISTS
  FOR (p:Project) REQUIRE p.slug IS UNIQUE;

-- Index: group_id for fast scope filter (even though :Project is
-- typically in its own group).
CREATE INDEX project_group_id IF NOT EXISTS
  FOR (p:Project) ON (p.group_id);

-- Upsert (register_project and default-project bootstrap).
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
"""
```

`source_created_at` preserved across re-registration via `coalesce` —
re-registering doesn't rewrite the original creation timestamp.

### 4.3 Bootstrap default project

`ensure_schema()` (the function GIM-52 introduced) is extended to:

1. Create the `:Project` constraint + index.
2. Apply the group_id backfill (existing GIM-52 behavior).
3. **New:** upsert a `:Project` node for
   `settings.palace_default_group_id`'s slug (extracted via
   `group_id.removeprefix("project/")`) if no `:Project` node exists
   for that slug yet. Minimal bootstrap so the registry is never empty
   on an existing install.
4. **New:** fail loud if any entity (`Issue`, `Comment`, `Agent`,
   `IngestRun`) has a `group_id` that does not correspond to a
   registered `:Project`. This is the N+1b invariant: every
   group_id-stamped entity belongs to a known project.

The bootstrap fields for the default project:

- `slug` = default slug (e.g. `"gimle"`)
- `name` = `f"Gimle Palace Bootstrap"` (hardcoded default for the
  bootstrap slug; can be updated later via `register_project`)
- `tags` = `["bootstrap"]`
- other optional fields `None`

Rationale: operators should not have to call `register_project` before
first ingest. The default slug self-registers.

## 5. Multi-project scoping

### 5.1 `project` parameter semantics

All applicable tools accept `project: str | list[str] | "*" | None`.

| Value | Resolver action | Meaning |
|---|---|---|
| `None` | → `[settings.palace_default_group_id]` | Current / default project (single-project back-compat) |
| `"medic"` | Validate slug exists as `:Project`; → `["project/medic"]` | Explicit single |
| `["gimle", "medic"]` | Validate each; → `["project/gimle", "project/medic"]` | Explicit subset |
| `"*"` | Query all `:Project` nodes; → `["project/<s>" for s in slugs]` | All registered |

### 5.2 Resolver (pseudocode — real code in plan Task 4)

```python
async def resolve_group_ids(
    tx: AsyncManagedTransaction,
    project: str | list[str] | None,
    default_group_id: str,
) -> list[str]:
    if project is None:
        return [default_group_id]

    known_slugs = await _load_known_slugs(tx)   # MATCH (p:Project) RETURN p.slug

    if project == "*":
        return [f"project/{s}" for s in known_slugs]

    if isinstance(project, str):
        if project not in known_slugs:
            raise UnknownProjectError(project)
        return [f"project/{project}"]

    if isinstance(project, list):
        unknown = [s for s in project if s not in known_slugs]
        if unknown:
            raise UnknownProjectError(", ".join(unknown))
        return [f"project/{s}" for s in project]

    raise TypeError(f"project must be str, list, or None; got {type(project).__name__}")
```

`UnknownProjectError` becomes a structured MCP-tool error (4xx-equivalent),
not an exception trace.

### 5.3 Lookup WHERE clause

Instead of the GIM-52 `n.group_id = $group_id` (single value), lookup
becomes `n.group_id IN $group_ids` with `$group_ids` supplied by
`resolve_group_ids`. The clause is a single-group list for the default
case — Neo4j's `IN` with one element is identical in cost to `=`.

### 5.4 Path A vs Path B (session context)

**Path A — ships in this slice.** Explicit `project=` on every tool
call; `None` → default from settings.

**Path B — deferred.** FastMCP session context or URL-scoped mounting
(`/mcp/gimle`, `/mcp/medic`). Not in scope. Will be reconsidered after
the first real second-project deployment (Medic) — retrofit is cheap
because tool handlers already take an explicit `project`.

## 6. MCP tool surface

### 6.1 Updates

| Tool | Change |
|---|---|
| `palace.memory.lookup` | Gains `project: str \| list[str] \| "*" \| None = None` param. Internal WHERE uses `n.group_id IN $group_ids`. Unknown project returns structured error. |
| `palace.memory.health` | Response gains `projects: list[str]`, `default_project: str`, `entity_counts_per_project: dict[str, dict[str, int]]`. Existing `entity_counts: dict[str, int]` kept as sum-across-projects for byte-stability. |

### 6.2 New tools

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
    entity_counts: dict[str, int]         # Issue/Comment/Agent/IngestRun for this project
    last_ingest_started_at: str | None
    last_ingest_finished_at: str | None


# palace.memory.list_projects() -> list[ProjectInfo]
# palace.memory.get_project_overview(project: str) -> ProjectInfo
# palace.memory.register_project(
#     slug: str,
#     name: str,
#     tags: list[str],
#     language: str | None = None,
#     framework: str | None = None,
#     repo_url: str | None = None,
# ) -> ProjectInfo
```

`register_project` is the sole project-lifecycle write surface. It is
idempotent on `slug`: re-calling with the same slug updates mutable
fields (`name`, `tags`, `language`, `framework`, `repo_url`,
`source_updated_at`) but preserves `source_created_at`. No project
delete tool in this slice — registering is additive.

## 7. Ingest CLI delta

Add `--project-slug <slug>` flag. Default: the slug of
`settings.palace_default_group_id`.

Behavior:

- Slug must exist as a `:Project` node. If not, fail with an actionable
  message pointing at `palace.memory.register_project`.
- Runner receives `group_id = f"project/{slug}"` and passes to every
  `_write_*` (same threading GIM-52 already did, just parameterised).
- GC is scoped to that `group_id` — same as GIM-52.

## 8. Observability

Structured log events (added/changed):

```json
{"event":"ingest.start","project_slug":"gimle","group_id":"project/gimle","run_id":"..."}
{"event":"ingest.project.ensure","slug":"gimle","registered":true}
{"event":"query.lookup","entity_type":"Issue","project_scope":"gimle","group_ids":["project/gimle"],"matched":3,"duration_ms":12}
{"event":"query.lookup","entity_type":"Issue","project_scope":"*","group_ids":["project/gimle","project/medic"],"matched":3,"duration_ms":18}
{"event":"tool.register_project","slug":"medic","tags":["mobile","kmp","healthcare"]}
{"event":"tool.unknown_project","project":"typo","known":["gimle","medic"]}
```

## 9. Decomposition (plan-first ready)

Expected plan-file: `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1b-multi-project-rev3.md`.

Workflow per `phase-handoff.md` fragment (shared-fragments `e32f6b8`).
CI green at every phase. CR must paste `uv run ruff check && uv run
mypy src/ && uv run pytest` output in APPROVE. QA Phase 4.1 follows
the GIM-52 evidence template.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Formalize issue, verify spec+plan paths on main, reassign. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance against fragment rules. APPROVE → MCPEngineer. |
| 2 | 2.1 | MCPEngineer | `:Project` constraint + index + UPSERT_PROJECT cypher. |
| 2 | 2.2 | MCPEngineer | `ensure_schema` default-project bootstrap + invariant check. |
| 2 | 2.3 | MCPEngineer | `resolve_group_ids` helper + typed `UnknownProjectError`. |
| 2 | 2.4 | MCPEngineer | `palace.memory.lookup` project param — WHERE `IN $group_ids`. |
| 2 | 2.5 | MCPEngineer | `palace.memory.health` response extension (back-compat). |
| 2 | 2.6 | MCPEngineer | `register_project`, `list_projects`, `get_project_overview`. |
| 2 | 2.7 | MCPEngineer | `--project-slug` CLI flag + validation. |
| 2 | 2.8 | MCPEngineer | Integration test: register Medic, assert isolation. |
| 3 | 3.1 | CodeReviewer | Mechanical review; assert no raw Cypher slippage beyond the N+0 pattern; resolver typo-protection has tests. |
| 3 | 3.2 | OpusArchitectReviewer | Adversarial: can an unregistered group_id slip into the graph? Can `"*"` ever include a deleted project? Can `register_project` race with concurrent upsert? |
| 4 | 4.1 | QAEngineer | Live smoke on iMac — evidence template (see §10). |
| 4 | 4.2 | MCPEngineer (or CTO) | Squash-merge develop; manual iMac rebuild. No admin CI override. |

## 10. Acceptance criteria (hard gates)

- [ ] `:Project` constraint and index exist after startup.
- [ ] `ensure_schema` registered default project (`gimle`) idempotently
      — re-running the service doesn't rewrite `source_created_at`.
- [ ] `MATCH (n) WHERE n:Issue OR n:Comment OR n:Agent OR n:IngestRun
      WITH DISTINCT n.group_id AS g MATCH (p:Project) WHERE p.group_id
      = g RETURN count(*)` equals the count of distinct entity
      group_ids. (Invariant: every entity belongs to a registered
      project.)
- [ ] `palace.memory.register_project(slug="medic", ...)` returns
      `ProjectInfo`, creates `:Project {slug:"medic"}` node, is
      idempotent.
- [ ] `palace.memory.lookup(entity_type="Issue", project="medic")` —
      empty list, no error.
- [ ] `palace.memory.lookup(entity_type="Issue", project="typo")` —
      structured `UnknownProjectError`, not stack trace.
- [ ] `palace.memory.lookup(entity_type="Issue", project="*")` returns
      same items as `project=["gimle","medic"]` (Gimle's issues only).
- [ ] `palace.memory.lookup(entity_type="Issue", project=None)`
      byte-identical to pre-slice response (back-compat invariant).
- [ ] `palace.memory.health()` includes `projects`, `default_project`,
      `entity_counts_per_project`; `entity_counts` field still present
      as sum-across-projects.
- [ ] `palace.memory.get_project_overview("gimle")` returns full
      ProjectInfo with `entity_counts`.
- [ ] `--project-slug=nonexistent` ingest fails with actionable message.
- [ ] CI green on all four jobs. CR APPROVE cites CI URL + local
      `ruff/mypy/pytest` output. **No admin override.**
- [ ] QA Phase 4.1 evidence comment authored by QAEngineer, includes
      the register-Medic + isolation demo per §10 acceptance list.
- [ ] iMac deploy post-merge: `docker compose --profile full ps`
      healthy, `palace.memory.list_projects()` via MCP returns
      `["gimle","medic"]`, iMac checkout returned to `develop`.

## 11. Out of scope

- FastMCP session / URL-scoped project context (Path B). Separate
  spike after first real second-project deployment.
- Project `delete` / `archive` tools. Additive-only lifecycle in this
  slice.
- Per-agent `allowed_group_ids` authorization (N+1c or later).
- Search, `record_note`, embedding-dim migration (N+1c / future).
- `:RELATED_TO` cross-entity edges (N+2+).
- Multi-tenant auth for MCP clients (single-operator trust model).
- Cross-project edge validation (e.g. rejecting `ASSIGNED_TO` across
  groups). The `ensure_schema` invariant asserts nodes but not edges —
  a future slice can add `MATCH (a)-[r]->(b) WHERE a.group_id <>
  b.group_id RETURN count(r)` as a health check.

## 12. Size estimate

- Code: ~350 LOC (schema + resolver ~100, tools ~120, CLI ~30,
  settings ~10, tests ~90).
- Plan + docs: ~60 LOC.
- 1 PR, 4–5 handoffs.
- Duration: ~1.5 days agent-time (paperclip team pace benchmark:
  GIM-52 at ~350 LOC ran in 70 min; N+1b is ~20% larger + one
  invariant check + one more tool).

## 13. Followups

- 1-day spike on Path B after Medic deployment.
- Cross-project edge validation — health-tool invariant check.
- `palace.memory.archive_project(slug)` — set a `archived_at` on the
  `:Project` node to hide from `list_projects()` default output, when
  product churn actually produces an archive need.
