# Palace Memory — Paperclip slice (N+0) design

**Date:** 2026-04-17
**Slice:** N+0 in the palace.memory.* product roadmap
**Author:** Board (via brainstorming session with Claude Opus 4.7)
**Status:** Draft — awaiting CTO formalization as GIM-NN issue
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §4.2, §4.3, §5, §10

## 1. Context

GIM-23 proved the end-to-end architecture for a single MCP tool (`palace.health.status`): FastAPI + FastMCP + streamable-HTTP + real MCP client connect (QAEngineer live smoke in GIM-27, merged as `e78bc3d` on `develop`). Architecture validated; tool catalogue expansion unblocked.

This slice is the **next product step** after GIM-23, delivering the first meaningful read-capability to external AI clients: **structured access to project history**. It corresponds to the spec §4.2 (Graphiti service) and §5 (data model) capability, but intentionally scoped below both — plain Neo4j, single source (paperclip), minimal schema — to prove the source → extractor → graph → MCP tool → client path with one low-risk source before introducing Graphiti or more complex sources.

## 2. Goal

External AI clients can ask the Gimle-Palace MCP server **structured questions about the project's paperclip history** — issues, comments, agent assignments — and receive typed responses ordered by authoritative timestamps from the source system.

**Success criterion (one sentence):** A Claude Desktop or Cursor instance connected to `palace-mcp` can call `palace.memory.lookup(entity_type="Issue", filters={"status":"done"})` and receive a JSON list of paperclip issues with all three timestamps per node (`source_created_at`, `source_updated_at`, `palace_last_seen_at`), and can separately call `palace.memory.health()` to see entity counts and last ingest status.

## 3. Architecture

Zero new compose services. Uses the existing `palace-mcp` (FastAPI + FastMCP) and `neo4j` services from GIM-5/9. Graphiti is **explicitly deferred to slice N+1**.

```
┌─────────────────────┐                  ┌──────────────────────────────┐
│ Paperclip HTTP API  │◄─── ingest ─────►│ palace-mcp (FastAPI+FastMCP) │
│ (iMac:3100 via      │   on demand      │  ├── /mcp  streamable-HTTP   │
│  paperclip.ant013)  │                  │  │   ├── palace.memory.lookup│
└─────────────────────┘                  │  │   ├── palace.memory.health│
                                         │  │   └── palace.health.status│ (GIM-23)
                                         │  └── CLI: palace_mcp.ingest. │
                                         │       paperclip              │
                                         └──────────────┬───────────────┘
                                                        │ Cypher
                                                        ▼
                                              ┌──────────────────┐
                                              │  Neo4j 5.26      │
                                              │  (existing       │
                                              │   compose svc)   │
                                              └──────────────────┘
                                                        ▲
                                                        │ Cypher
                                                        │
┌─────────────────────┐                                 │
│ External MCP client │──── MCP streamable-HTTP ────────┘
│ (Claude Desktop /   │      /mcp endpoint (same as
│  Cursor / mcp SDK)  │       GIM-23)
└─────────────────────┘
```

**Source of truth:** paperclip HTTPS API (via a board-level static token — env var `PAPERCLIP_INGEST_API_KEY`, **not** the run-scoped JWT the agents receive). Not a direct postgres connection — the API path keeps us decoupled from embedded-postgres internals and reuses established auth.

**Runtime dependencies** (to add to `services/palace-mcp/pyproject.toml` `[project].dependencies` if not already present):
- `httpx` — async HTTP client for paperclip API
- `python-json-logger` — structured JSON stdout formatter
- Production `mcp` extras: use `"mcp>=1.6"` (core) in `[project].dependencies`; move `mcp[cli]` (CLI tooling: click/rich/typer) to `[tool.uv].dev-dependencies` only — not needed at runtime in the container.

**Data flow — ingest:**
1. Operator runs CLI (`python -m palace_mcp.ingest.paperclip`).
2. CLI reads all issues, comments, agents for the Gimle company via paperclip API.
3. Transforms each record into Neo4j node properties + edges.
4. `MERGE` by natural key (paperclip UUID), updates three timestamps.
5. Post-cleanup: `DETACH DELETE` nodes with `palace_last_seen_at < run_started`.

**Data flow — query:**
1. External MCP client connects to `palace-mcp` `/mcp` streamable-HTTP endpoint.
2. Calls `palace.memory.lookup(entity_type, filters, limit)`.
3. palace-mcp resolves filters against a whitelist, builds a parameterized Cypher query, executes against Neo4j.
4. Returns typed JSON ordered by `source_updated_at DESC`.

## 4. Neo4j schema

### 4.1 Nodes

```cypher
(:Issue {
    id: String,              // paperclip UUID — primary/natural key
    key: String,             // "GIM-23" — identifier shown to users
    title: String,
    description: String,     // full markdown body
    status: String,          // "todo" | "in_progress" | "done" | "backlog" | "blocked"
    source: String,          // "paperclip"
    source_created_at: String,  // ISO-8601 UTC — from paperclip.issues.createdAt
    source_updated_at: String,  // ISO-8601 UTC — from paperclip.issues.updatedAt
    palace_last_seen_at: String // ISO-8601 UTC — set by ingest run
})

(:Comment {
    id: String,              // paperclip UUID
    body: String,            // markdown
    source: String,          // "paperclip"
    source_created_at: String,
    source_updated_at: String,
    palace_last_seen_at: String
})

(:Agent {
    id: String,              // paperclip UUID
    name: String,            // "CodeReviewer", "CTO", ...
    url_key: String,         // "codereviewer"
    role: String,            // agent.role field from paperclip
    source: String,          // "paperclip"
    source_created_at: String,
    source_updated_at: String,
    palace_last_seen_at: String
})

// Meta-node — single row per ingest run, read by palace.memory.health.
(:IngestRun {
    id: String,              // generated UUID
    source: String,          // "paperclip"
    started_at: String,      // ISO-8601 UTC
    finished_at: String,     // ISO-8601 UTC (null while running)
    duration_ms: Integer,
    errors: [String]         // populated if exceptions occurred
})
```

### 4.2 Constraints (asserted on startup / before first ingest)

```cypher
CREATE CONSTRAINT issue_id   IF NOT EXISTS FOR (i:Issue)   REQUIRE i.id IS UNIQUE;
CREATE CONSTRAINT comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT agent_id   IF NOT EXISTS FOR (a:Agent)   REQUIRE a.id IS UNIQUE;
```

### 4.3 Edges

```
(:Comment)-[:ON]->(:Issue)                // comment belongs to issue
(:Comment)-[:AUTHORED_BY]->(:Agent)       // null authored_by_agent = authored by human user — edge not created
(:Issue)-[:ASSIGNED_TO]->(:Agent)         // current assignee at time of last ingest
```

Edges carry no properties in this slice. History of assignments (who was assigned before) requires `:Assignment` nodes and belongs to slice N+2+ when temporal conflict resolution across sources becomes necessary.

### 4.4 Timestamp discipline (applies to all current and future slices)

Every node storing extracted content MUST carry three timestamps:

- **`source_created_at`** — when the record was first created in the source system.
- **`source_updated_at`** — when the record was last modified in the source system.
- **`palace_last_seen_at`** — when the most recent ingest run observed the record.

Rationale: enables temporal queries (`source_updated_at_gte` filter), idempotent re-ingest (MERGE-then-cleanup by `palace_last_seen_at`), and future conflict resolution across sources (`ORDER BY source_created_at DESC LIMIT 1` to pick the most recent claim).

## 5. MCP tool surface

### 5.1 `palace.memory.lookup`

```python
class LookupRequest(BaseModel):
    entity_type: Literal["Issue", "Comment", "Agent"]
    filters: dict[str, Any] = {}
    limit: int = Field(default=20, ge=1, le=100)
    order_by: Literal["source_updated_at", "source_created_at"] = "source_updated_at"

class LookupResponseItem(BaseModel):
    id: str
    type: Literal["Issue", "Comment", "Agent"]
    properties: dict[str, Any]                                                   # all node properties
    related: dict[str, dict[str, Any] | list[dict[str, Any]] | None] = {}        # one-hop related — see §5.1 table below
    # Note: `related["author"]["name"]` may be None (when comment author is a human user, not an agent).
    # Comment.author_name typed `str | None` in resolver output.

class LookupResponse(BaseModel):
    items: list[LookupResponseItem]
    total_matched: int                   // before limit
    query_ms: int
```

**Supported filters (whitelisted — no ad-hoc Cypher):**

| entity_type | Filter keys |
|---|---|
| `Issue`   | `key`, `status`, `assignee_name`, `source_updated_at_gte`, `source_updated_at_lte` |
| `Comment` | `issue_key`, `author_name`, `source_created_at_gte` |
| `Agent`   | `name`, `url_key` |

Unknown filter keys emit a `query.lookup.unknown_filter` warning in logs and are silently ignored. This gives forward-compat with future filter expansions without 500-ing on clients.

**Cypher parameterization mandate (required for all tool queries):** All filter values pass into Cypher as **named parameters** (`$param` syntax), never via string interpolation. Filter whitelisting validates the **keys**; parameterization protects the **values**. No raw user input reaches Cypher as literal syntax.

**Query transaction discipline:** Lookup queries execute via `session.execute_read()` (Neo4j async-driver managed read transaction) — not `session.run()` (auto-commit) and not `execute_write()`. Managed reads enable read-replica routing in cluster deployments, provide automatic retry on transient errors, and declare intent explicitly. Ingest writes use `session.execute_write()` (already covered in §6.2).

**Related (one-hop expansion)** is inlined per entity type:
- `Issue` → `comments: [{id, body, source_created_at, author_name}]` (up to 50 comments), `assignee: {id, name, url_key}` (nullable).
- `Comment` → `issue: {id, key, title, status}`, `author: {id, name}`.
- `Agent` → no expansion in MVP (agents are leaves).

### 5.2 `palace.memory.health`

```python
class HealthResponse(BaseModel):
    neo4j_reachable: bool
    entity_counts: dict[str, int]         # {"Issue":31, "Comment":52, "Agent":12}
    last_ingest_started_at: str | None
    last_ingest_finished_at: str | None
    last_ingest_duration_ms: int | None
    last_ingest_errors: list[str]
```

Read-only tool. Queries Neo4j for node counts and the most recent `IngestRun` node with `source = 'paperclip'`.

## 6. Ingest pipeline

### 6.1 CLI entrypoint

```bash
python -m palace_mcp.ingest.paperclip \
    --paperclip-url https://paperclip.ant013.work \
    --company-id 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
```

Env defaults: `PAPERCLIP_API_URL`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_API_KEY`.

### 6.2 Phases (logically atomic — not a single transaction)

**Idempotency requirement (Neo4j async driver contract):** All transaction functions passed to `session.execute_write()` must be idempotent — the driver may invoke the function more than once on transient failures. The MERGE-based upserts in §6.3 are naturally idempotent (re-applying SET with the same values is a no-op). The implementer MUST NOT add side-effects inside the transaction function — no counters, no external event emission, no HTTP calls. Side-effects belong outside the transaction (before/after the `execute_write` call).


```python
async def run_ingest():
    started_at = utcnow_iso()
    errors: list[str] = []
    run_id = await create_ingest_run(started_at=started_at, source="paperclip")

    try:
        issues   = await paperclip_api.list_issues(company_id=...)
        agents   = await paperclip_api.list_agents(company_id=...)
        comments = await paperclip_api.list_comments(issues=[i["id"] for i in issues])

        async with driver.session() as session:
            await session.execute_write(upsert_agents,   agents,   run_started=started_at)
            await session.execute_write(upsert_issues,   issues,   run_started=started_at)
            await session.execute_write(upsert_comments, comments, run_started=started_at)

            # GC runs only on clean success — partial failures leave stale data rather than deleting alive records.
            if not errors:
                await session.execute_write(gc_orphans, source="paperclip", cutoff=started_at)

    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
        raise
    finally:
        await finalize_ingest_run(run_id, finished_at=utcnow_iso(),
                                   duration_ms=..., errors=errors)
```

### 6.3 Upsert pattern (UNWIND + MERGE)

```cypher
// Issues upsert + ASSIGNED_TO edge refresh
UNWIND $batch AS row
MERGE (i:Issue {id: row.id})
SET i.key                 = row.key,
    i.title               = row.title,
    i.description         = row.description,
    i.status              = row.status,
    i.source              = 'paperclip',
    i.source_created_at   = row.source_created_at,
    i.source_updated_at   = row.source_updated_at,
    i.palace_last_seen_at = $run_started

// Refresh ASSIGNED_TO edge — remove stale, add current if present.
WITH i, row
OPTIONAL MATCH (i)-[old:ASSIGNED_TO]->()
DELETE old
WITH i, row
WHERE row.assignee_agent_id IS NOT NULL
MATCH (a:Agent {id: row.assignee_agent_id})
MERGE (i)-[:ASSIGNED_TO]->(a);
```

Same shape for `upsert_comments` (with `ON` + `AUTHORED_BY` edges) and `upsert_agents` (nodes only, no outbound edges).

### 6.4 Garbage collection

```cypher
MATCH (n:Issue)   WHERE n.source = 'paperclip' AND n.palace_last_seen_at < $cutoff DETACH DELETE n;
MATCH (n:Comment) WHERE n.source = 'paperclip' AND n.palace_last_seen_at < $cutoff DETACH DELETE n;
MATCH (n:Agent)   WHERE n.source = 'paperclip' AND n.palace_last_seen_at < $cutoff DETACH DELETE n;
```

GC runs **only on clean-success** ingest (no errors). Partial-failure runs leave stale data visible — safer than deleting alive records because the current run couldn't see them.

### 6.5 Edge cases

- **Comment author is a human user, not an agent.** `authored_by_agent_id` is null in paperclip → `AUTHORED_BY` edge is not created. The comment body itself contains the author context from paperclip when rendered.
- **Mid-ingest partial failure.** GC is skipped, leaving the DB in the pre-failure state. Errors are recorded in the `IngestRun.errors` array and surface through `palace.memory.health`.
- **Parallel ingest runs.** Not defended against in this slice. Manual trigger, single operator. If it becomes a risk (e.g., when `palace.memory.ingest` MCP tool lands), add a `(:IngestLock)` node with atomic `MERGE` check.

## 7. Observability (L3)

### 7.1 Structured JSON logs

`palace-mcp` switches to JSON-formatted stdout via `python-json-logger`. Events emitted at `INFO` for happy path, `WARNING` for unknown filters or data anomalies, `ERROR` for exceptions:

```
{"event":"ingest.start","source":"paperclip","run_id":"..."}
{"event":"ingest.fetch.issues","count":31,"source":"paperclip"}
{"event":"ingest.upsert","type":"Issue","count":31,"duration_ms":245}
{"event":"ingest.gc","type":"Issue","deleted":0}
{"event":"ingest.finish","duration_ms":980,"errors":[]}
{"event":"query.lookup","entity_type":"Issue","filters":{"status":"done"},"matched":3,"duration_ms":12}
{"event":"query.lookup.unknown_filter","entity_type":"Issue","filter_key":"xyz"}
```

Inspected via `docker compose logs -f palace-mcp | jq 'select(.event != null)'`.

### 7.2 Health tool

`palace.memory.health` — described in §5.2. Provides the same observability surface to MCP clients (who typically cannot tail server logs).

## 8. Decomposition (plan-first ready)

Expected plan-file at `docs/superpowers/plans/2026-04-17-GIM-NN-palace-memory-paperclip.md` — produced by CTO when formalizing the issue. Skeleton matching the GIM-23 / GIM-30 pattern:

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create GIM-NN issue + plan file. Reassign to CodeReviewer for plan review. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance check (4 items). APPROVE → Phase 2. |
| 2 | 2.1 | MCPEngineer | Ingest module: paperclip API client, transform, MERGE + GC Cypher, CLI entrypoint, unit tests. |
| 2 | 2.2 | MCPEngineer | Two MCP tools: `palace.memory.lookup`, `palace.memory.health` with Pydantic v2 schemas + unit tests. |
| 2 | 2.3 | MCPEngineer | JSON logging + `IngestRun` meta-node + whitelisted filter resolver + Neo4j constraints on startup. |
| 3 | 3.1 | CodeReviewer | PR mechanical review: compliance table, plan-first checklist, SDK conformance, whitelist enforcement (no Cypher injection path). |
| 3 | 3.2 | OpusArchitectReviewer | (If GIM-30 wiring has landed.) Docs-first adversarial pass via `context7` — Neo4j driver patterns, MCP SDK, FastMCP lifespan, Pydantic v2. Advisory unless CRITICAL. |
| 4 | 4.1 | QAEngineer | Live smoke: `docker compose up`, run ingest CLI, connect Claude Desktop / Cursor / mcp SDK to `/mcp`, call both new tools, attach evidence (screenshot or curl-equivalent) to PR. |
| 4 | 4.2 | MCPEngineer | Merge to `develop` (squash), update plan-file checkboxes to `[x]`, close issue with acceptance-criteria evidence table. |

## 9. Acceptance criteria

- [ ] PR opened against `develop`; squash-merged on APPROVE.
- [ ] Plan file committed under `docs/superpowers/plans/`; PR description links to it.
- [ ] `palace_mcp.ingest.paperclip` module importable; unit tests green.
- [ ] Two new MCP tools registered via `@_mcp.tool(...)` with Pydantic v2 schemas.
- [ ] Neo4j uniqueness constraints (`issue_id`, `comment_id`, `agent_id`) asserted idempotently at startup or first ingest.
- [ ] Live MCP client smoke test: `palace.memory.health` returns `entity_counts` with at least one non-zero bucket; `palace.memory.lookup(entity_type="Issue", filters={"status":"done"})` returns at least one `Issue` with all three timestamps populated.
- [ ] Idempotency: re-running ingest without paperclip changes leaves `entity_counts` unchanged and updates only `palace_last_seen_at`.
- [ ] Deletion propagation: deleting or hiding an issue in paperclip and re-running ingest makes that issue absent from `palace.memory.lookup`.
- [ ] Three timestamps (`source_created_at`, `source_updated_at`, `palace_last_seen_at`) present on every node and returned in `lookup` responses.
- [ ] `docker compose logs palace-mcp` produces JSON events matching `ingest.*` and `query.*` patterns.
- [ ] Filter whitelist enforced: unknown filter keys produce a `query.lookup.unknown_filter` warning and do not leak into the Cypher query.
- [ ] `uv run mypy --strict` green — no new `Any`-valued return types, no bare container types (`dict`, `list`) without parameters.
- [ ] CI green on all four jobs (lint, typecheck, test, docker-build).
- [ ] CodeReviewer posts APPROVE with the full compliance table (anti-rubber-stamp discipline).
- [ ] QAEngineer attaches smoke evidence (screenshot or curl-equivalent) in the PR thread (GIM-23 / GIM-27 pattern).

## 10. Out of scope (explicit — Karpathy §2)

- Graphiti service — deferred to slice N+1.
- GitHub extractor (commits, PRs) — slice N+2.
- Claude-transcripts extractor (chat history) — slice N+3.
- Scheduled / cron ingest — spec §11 scheduled update flow, separate slice.
- Natural language query (`Q-A` shape) — only `Q-B` (structured) in this slice.
- `palace.memory.ingest` MCP tool — possible follow-up, trivial wrapper over the CLI.
- Concurrent ingest locking.
- Additional entity types (Runs, Activities, Approvals) — add when a specific product need emerges.
- Pagination > 100 / cursor-based pagination — MVP limit 100.
- Edges with properties (history of assignments, edit logs) — temporal model belongs to slice N+2+.
- Authentication on palace-mcp tools — stays internal-only behind the docker network for this slice.
- **FastMCP `Context` parameter migration** (inherited tech debt from GIM-23). Current tools read `_driver` from module-level global set by `set_driver()` in lifespan. FastMCP idiom: tools accept `ctx: Context` and read `ctx.lifespan_context["driver"]`. Migration reduces defensive null-checks, unlocks MCP-framework structured logging per tool invocation. Defer to a dedicated slice when tool catalogue grows past ~5 tools, since refactor is cross-cutting.
- **Client-visible unknown-filter feedback** (non-blocking UX improvement). Currently unknown filter keys are logged as warning + silently ignored. A `warnings: list[str]` field on `LookupResponse` could surface them to the client. Implementation-time decision; not gating.

## 11. Estimated size

- Code: ~400 LOC (ingest ~200, tools ~120, tests ~80).
- Plan + docs: ~80 LOC plan-file.
- 1 PR, 4-5 handoffs (CTO → CR → MCPEngineer → CR (+ Opus optional) → QAEngineer → MCPEngineer merge).
- Expected duration: 1-2 days of agent work (GIM-23 was ~1 day).

## 12. Followups (to file as separate issues once this slice merges)

- Enable OpusArchitectReviewer on this PR if GIM-30 wiring landed.
- Start brainstorming slice N+1 (Graphiti service) — lock in spec §4.2 direction before more sources are added.
- Consider a `palace.memory.ingest` MCP tool wrapper so external orchestrators can trigger ingest without shell access.
