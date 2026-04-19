# Palace Memory — N+1 Graphiti substrate + multi-project scoping

> **⚠️ STATUS: REJECTED (2026-04-18) — DO NOT IMPLEMENT**
>
> Board adversarial review identified 5 hallucinated graphiti-core API claims (methods that don't exist or have different names), 4 logical inconsistencies (double-indexing, bi-temporal theatre, 22-stub YAGNI violation, non-atomic slice), and 6 operational/security issues (no agent auth, no embed change-detection, multi-MCP write-boundary leak).
>
> This document is preserved as historical artifact. Replaced by three atomic sub-slices:
> - `TBD — N+1a Graphiti substrate swap`
> - `TBD — N+1b Multi-project + :Project entity`
> - `TBD — N+1c Agent MCP + record_note + provider choice`
>
> Prerequisite for rewrite: hands-on graphiti-core API verification spike (see `docs/research/graphiti-core-verification.md`).
>
> Rewrite blocked until GIM-30 (OpusArchitectReviewer wiring) operational — docs-first adversarial pass via context7 would have caught the 5 API-hallucination failures pre-review.
>
> ---


**Date:** 2026-04-18
**Slice:** N+1 in the palace.memory.* product roadmap
**Author:** Board (via brainstorming session with Claude Opus 4.7, extended with extractor-library research detour)
**Status:** Draft — awaiting CTO formalization as GIM-NN issue
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §4.2, §4.3, §5, §6; extractor research at `docs/research/extractor-library/report.md`
**Predecessor slice:** N+0 (GIM-34) — `docs/superpowers/specs/2026-04-17-palace-memory-paperclip-slice.md`

## 1. Context

N+0 (GIM-34, merged 2026-04-17 as squash `98e9b8da`) proved the end-to-end ingest → Neo4j → MCP tool → client path on plain Neo4j with structured paperclip data. This slice delivers the **substrate swap** to Graphiti and two foundational capabilities required by every downstream extractor slice (N+2…N+6):

1. **Multi-project namespace model** — one Gimle-Palace server hosts multiple unrelated projects (Gimle, future Medic, future Unstoppable Wallet, etc.) with opt-in cross-project retrieval for related projects.
2. **Agent-facing Graphiti MCP surface** — paperclip agents get direct read+write access to their memory via `graphiti-mcp`, unlocking the `record_note → search → find` agent-memory loop that N+0 explicitly deferred.

The extractor-library research (`docs/research/extractor-library/report.md`) surfaced 6 substrate-level requirements that MUST land in N+1 to avoid painful retroactive migrations in N+2+:

- Bi-temporal edge `end_time` semantics (≥6 future extractors use it)
- Faceted classification with explicit **capability** axis
- SCIP-alignment field reserved on `:Symbol` schema (Kotlin-only as of April 2026)
- Namespace `group_id = project/<slug>` per ingest source (confirmed via research)
- Inter-extractor edges (`cross_extractor_feeds`) as first-class graph concept
- LLM provider abstraction via LiteLLM (embedding-only default; extraction skip for this slice)

## 2. Goal

After this slice:

- External AI clients (Claude Code, Cursor, Claude Desktop) query structured project history via palace-mcp with `project: str | list | "*"` scoping.
- Paperclip agents connect to `graphiti-mcp` on a second port and can `record_note` arbitrary memories + search them semantically in subsequent sessions.
- The server hosts ≥2 projects (Gimle today; schema proves adding Medic/Unstoppable does not require migration).
- The full S3 tool surface (22 domain tools from spec §4.3 — 17 read + 5 write — plus 3 infrastructure tools from N+0 carryover: `lookup`, `search`, `health`) is registered on palace-mcp, totaling 25 tools. Most extractor-dependent tools return empty lists with `meta.reason="no_data_yet"` until extractors land in N+2…N+6.

**Success criterion (one sentence):** Claude Code connected to `palace-memory` MCP can call `palace.memory.record_note(text="Coordinator pattern used in Gimle bootstrap", tags=["pattern", "bootstrap"])` from one session, restart, call `palace.memory.search(query="how did Gimle bootstrap work?")` and receive the note with a semantic-match score higher than unrelated Issue/Comment content; separately, a paperclip agent connected to `graphiti-mcp` can `add_episode` memory and retrieve it via `search_memory_nodes`.

## 3. Architecture

Two new compose services (`graphiti`, `ollama` under opt-in profile), one new MCP surface (`graphiti-mcp` on `:8002`), one refactored service (`palace-mcp` substrate swap).

```
┌─────────────────────┐                                 ┌───────────────────────────────┐
│ Paperclip HTTP API  │◄──── ingest (on-demand) ───────►│ palace-mcp (FastAPI+FastMCP)  │
│ (iMac:3100 via      │                                 │  ├── /mcp streamable-HTTP     │
│  paperclip.ant013)  │                                 │  │   └── S3 tool surface     │
└─────────────────────┘                                 │  │       (17 read + 5 write) │
                                                        │  └── ingest CLI moved to     │
                                                        │       Graphiti add_triplet   │
                                                        └───────────────┬───────────────┘
                                                                        │ gRPC/HTTP
                                                                        ▼
                                                        ┌───────────────────────────────┐
                                                        │ graphiti (Python + FastAPI +  │
                                                        │          graphiti-core)       │
                                                        │  ├── internal :8001 HTTP for  │
                                                        │  │   palace-mcp reads         │
                                                        │  └── :8002 Graphiti MCP       │
                                                        │      server for paperclip     │
                                                        │      agents (direct access)   │
                                                        └──────┬────────────────┬───────┘
                                                               │ Bolt/Cypher    │ embeddings
                                                               ▼                ▼
                                                   ┌──────────────────┐  ┌──────────────────┐
                                                   │  Neo4j 5.26      │  │  Ollama          │
                                                   │  (existing svc)  │  │  (profile:       │
                                                   │                  │  │   with-ollama,   │
                                                   └──────────────────┘  │   default ON)    │
                                                               ▲         └──────────────────┘
                                                               │              OR
                                                               │         ┌──────────────────┐
                                                               │         │ External OpenAI- │
                                                               │         │ compat endpoint  │
                                                               │         │ (Alibaba/OpenAI/ │
                                                               │         │  Voyage/Cohere)  │
                                                               │         └──────────────────┘
                                                               │
┌─────────────────────┐                                        │
│ External MCP client │──── MCP streamable-HTTP ───────────────┘
│ (Claude Desktop /   │    :8080 (palace-mcp /mcp; GIM-23 path)
│  Cursor / mcp SDK)  │
└─────────────────────┘

┌─────────────────────┐
│ Paperclip agents    │──── MCP streamable-HTTP ───────────────►  graphiti-mcp :8002
│ (via shared-        │    (direct graph access)                  (add_episode, search_*)
│  fragments MCP cfg) │
└─────────────────────┘
```

**Source of truth:** paperclip HTTPS API (via board-level static token `PAPERCLIP_INGEST_API_KEY`), same as N+0. Not a direct postgres connection.

**Runtime dependencies to add** (`services/palace-mcp/pyproject.toml`, new `services/graphiti/pyproject.toml`):
- `graphiti-core>=0.3` — temporal KG library (getzep/graphiti)
- `litellm>=1.40` — provider-agnostic LLM/embedding router
- `httpx` and `python-json-logger` — already present from N+0

**No LLM extraction in this slice.** Paperclip data is structured; we feed Graphiti via `add_triplet(source_node, edge, target_node)` path directly, bypassing the LLM entity-extraction pipeline. Embedding provider is used only for `record_note` write tool and `search_memory` read tool. See §6 for provider abstraction.

## 4. Graphiti schema

### 4.1 Multi-project namespace

Graphiti `group_id` encodes project scope: `project/<slug>` (default for per-project nodes), `global/decisions` (cross-project ADRs, later slices), `global/patterns` (reusable patterns, later slices).

Every ingest run writes to exactly one `group_id`. Every query accepts a `project: str | list[str] | "*" | None` parameter:
- `None` (default) — current project from MCP client session context (see §7.2)
- `str` — explicit single project slug
- `list[str]` — explicit subset (e.g., `["gimle", "medic"]`)
- `"*"` — all projects on the server

Relatedness is **tag-based fuzzy** — each `:Project` node carries a `tags: list[str]` field from `project.yaml` (§6 of design spec). Cross-project retrieval tools (e.g., `find_context_for_task`) default to searching across all projects sharing at least one tag with the current project, unless overridden. No explicit `:RELATED_TO` edges in this slice — schema-ready to add in later slices if manual control is needed.

### 4.2 Entity types (core — added in this slice)

Note: `group_id` is a Graphiti namespace concept handled by the library (passed as parameter to `add_triplet` / search operations), not stored as a node property. The schema blocks below document logical scoping; in practice Graphiti attaches `group_id` via its own mechanisms.

```cypher
(:Project {
    slug: String,               // "gimle", "medic", "unstoppable-wallet"
    name: String,               // human-readable
    tags: [String],             // ["mobile", "blockchain", "kmp"] — fuzzy relatedness
    language: String,           // primary — "python" for Gimle
    framework: String,          // optional
    repo_url: String,           // optional
    source_created_at: String,  // ISO-8601 UTC
    source_updated_at: String,
    palace_last_seen_at: String
    // group_id handled by Graphiti namespace, not a property
})

// Existing N+0 entities — schema unchanged; Graphiti group_id attached via namespace
(:Issue { id, key, title, description, status, source: "paperclip",
          source_created_at, source_updated_at, palace_last_seen_at })

(:Comment { id, body, source: "paperclip",
            source_created_at, source_updated_at, palace_last_seen_at })

(:Agent { id, name, url_key, role, source: "paperclip",
          source_created_at, source_updated_at, palace_last_seen_at })

// New meta-node — written when agents call record_note
(:Note {
    id: String,                 // generated UUID
    text: String,               // free-form markdown
    tags: [String],
    author_kind: String,        // "agent" | "human" | "external-client"
    author_id: String,          // agent fqn, user email, or client id
    scope: String,              // "project" | "module" | "global"
    source_created_at: String,
    palace_last_seen_at: String
})

// Meta — one per ingest run, read by palace.memory.health
(:IngestRun { id, source: "paperclip", started_at, finished_at,
              duration_ms, errors: [String] })
```

### 4.3 Faceted classification (substrate placeholder — schema only)

Graphiti native multi-label: every content node CAN carry labels from four orthogonal axes (per spec §5.4). This slice **reserves the label machinery** but does not populate beyond N+0 entity types. First real population comes in N+2 with architecture-extractor.

- **Structural axis** — `:Module`, `:File`, `:Class`, `:Method` (populated N+2+)
- **Semantic-kind axis** — `:UIComponent`, `:APIEndpoint`, `:Utility` (populated N+3+)
- **Domain-concept axis** — `:HandlesHex`, `:HandlesAddress`, `:HandlesCrypto` (populated N+5+ via taxonomies from §5.4.1)
- **Capability axis** — `:Encodes`, `:Decodes`, `:Validates`, `:Signs`, `:Audits`, `:Observes` (populated N+2+)

Constraint assertion at startup:

```cypher
CREATE CONSTRAINT project_slug IF NOT EXISTS FOR (p:Project) REQUIRE p.slug IS UNIQUE;
CREATE CONSTRAINT issue_id     IF NOT EXISTS FOR (i:Issue)   REQUIRE i.id IS UNIQUE;
CREATE CONSTRAINT comment_id   IF NOT EXISTS FOR (c:Comment) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT agent_id     IF NOT EXISTS FOR (a:Agent)   REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT note_id      IF NOT EXISTS FOR (n:Note)    REQUIRE n.id IS UNIQUE;
```

### 4.4 Edge types

```cypher
// Existing N+0 edges — unchanged
(:Comment)-[:ON]->(:Issue)
(:Comment)-[:AUTHORED_BY]->(:Agent)
(:Issue)-[:ASSIGNED_TO]->(:Agent)

// New in N+1 — project scoping
(:Issue)-[:BELONGS_TO_PROJECT]->(:Project)
(:Comment)-[:BELONGS_TO_PROJECT]->(:Project)
(:Agent)-[:BELONGS_TO_PROJECT]->(:Project)
(:Note)-[:BELONGS_TO_PROJECT]->(:Project)

// Reserved for later slices (no writers in N+1)
// (:Decision)-[:INVALIDATED_BY {end_time: String}]->(:Decision)  — N+3+
// (:Finding)-[:RESOLVED_BY]->(:GitCommit)                        — N+3+
// (:DeprecatedSymbol)-[:USED_AT]->(:Symbol)                      — N+5+
```

### 4.5 Bi-temporal discipline

Every edge that represents a relationship which can **expire** carries:

- `valid_from: String` (ISO-8601 UTC) — when relationship first observed
- `valid_to: String | null` — null while active; set to observation timestamp when relationship is no longer detected

In N+1, only `:BELONGS_TO_PROJECT` edges exist and they are effectively permanent (projects don't move between slugs). Bi-temporal machinery is **schema-ready** — the Python data model for edges includes the two timestamp fields and Cypher MERGE templates carry them. Downstream extractors (N+2+) will populate `valid_to` on migration completion, smell resolution, cache invalidation breakage, etc.

This is a deliberate N+1 investment per research §9 point 2: ≥6 future extractors require edge end_time semantics; retroactive schema migration is far more expensive than reserving the columns now.

### 4.6 Inter-extractor edge primitive (reserved)

First-class `:EXTRACTOR_PRODUCED_BY` edge type (from spec node types) is reserved but not written in N+1. Research §5 showed extractors form a 5-layer DAG where Layer-2+ extractors consume Layer-0/1 outputs. Having this edge type in schema at substrate time enables downstream extractors to record provenance without breaking additions.

## 5. MCP tool surface — full S3

All 22 domain tools from spec §4.3 (17 read + 5 write) plus 3 N+0-carryover infrastructure tools (`lookup`, `search`, `health`) are registered on palace-mcp — 25 total. Stubs return empty lists with a documented `meta.reason="no_data_yet"` field until extractors land. Real data in this slice: `palace.memory.lookup`, `palace.memory.search`, `palace.memory.health`, `palace.memory.record_note`, `palace.memory.record_iteration_note`, `palace.memory.link_items`, `palace.memory.list_projects`, `palace.memory.get_project_overview`, `palace.memory.get_iteration_notes`.

### 5.1 Read tools (19 — 17 from §4.3 + lookup + health carryover from N+0)

All accept `project: str | list[str] | "*" | None` parameter. Tools that return nothing useful in N+1 (no extractor data yet) surface `meta.reason` explaining why.

| Tool | N+1 behavior |
|---|---|
| `palace.memory.lookup(entity_type, filters, project, limit, order_by)` | N+0 behavior preserved; adds `project` scoping |
| `palace.memory.search(query, project, filters, top_k=10)` | **NEW** — semantic search via Graphiti embeddings on `Issue.title` + `Issue.description` + `Comment.body` + `Note.text` |
| `palace.memory.find_context_for_task(task_description, project)` | Stub — returns empty grouped result with `meta.reason="requires_extractors_N+2"` |
| `palace.memory.find_ui_components(kind, framework, project)` | Stub |
| `palace.memory.find_component_usage(name, project)` | Stub |
| `palace.memory.find_similar_component(description_or_code, project)` | Stub |
| `palace.memory.find_utility(domain_concept, capability, project)` | Stub |
| `palace.memory.find_api_contract(name_or_path, project)` | Stub |
| `palace.memory.find_screen(name_or_description, project)` | Stub |
| `palace.memory.get_layer_dependencies(module, project)` | Stub |
| `palace.memory.get_dependency_usage(library_name, project)` | Stub |
| `palace.memory.get_iteration_notes(project, since_iteration)` | Returns `:Note` nodes with temporal filter |
| `palace.memory.get_iteration_diff(project, from, to)` | Stub |
| `palace.memory.get_recent_iterations(project, limit=5)` | Returns `:IngestRun` list, `:Iteration` post-N+3 |
| `palace.memory.find_decision_by_topic(topic, project)` | Stub |
| `palace.memory.get_architecture_summary(project, depth)` | Stub |
| `palace.memory.list_projects()` | **NEW** — returns all `:Project` nodes on the server |
| `palace.memory.get_project_overview(project)` | **NEW** — entity counts + latest ingest + tags |
| `palace.memory.health()` | N+0 preserved; adds Graphiti `/healthz` probe + Ollama reachability |

### 5.2 Write tools (6 — 5 from §4.3 + record_note NEW in N+1)

| Tool | N+1 behavior |
|---|---|
| `palace.memory.record_note(text, tags, scope, project)` | **NEW** — primary write surface. Calls `graphiti.add_episode(group_id="project/<slug>", episode_body=text, name="note-<uuid>", source_description="palace.memory.record_note")`. Applies tags to the generated `:Note` node. |
| `palace.memory.record_decision(project, scope, text, tags)` | Stub — documented as N+3+ (requires `:Decision` node type). |
| `palace.memory.record_finding(project, scope, severity, text, tags, source)` | Stub — N+3+ (requires reviewer roles). |
| `palace.memory.record_iteration_note(project, text, tags)` | **NEW** — thin wrapper over `record_note` with `scope="iteration"`. |
| `palace.memory.link_items(from_id, to_id, relation)` | **NEW** — creates explicit graph edge between two arbitrary nodes. Used sparingly; guarded by whitelist of safe relation types (`:RELATES_TO`, `:SIMILAR_TO`, `:SEE_ALSO`). |
| `palace.memory.create_paperclip_issue(project, title, description, role_hint)` | Stub — not in N+1 scope (requires paperclip-write auth; deferred to dedicated slice). |

### 5.3 Tool response envelope

All tools return the standard envelope from spec §4.3:

```python
class ToolResponse(Generic[T], BaseModel):
    ok: bool
    data: T | None = None
    error: str | None = None
    meta: ResponseMeta

class ResponseMeta(BaseModel):
    latency_ms: int
    tokens_est: int | None = None
    avoided_tokens_est: int | None = None
    event_id: str
    last_ingest_at: str | None = None
    staleness_warning: str | None = None
    project_scope: str | list[str]   # echoed back for client debuggability
    reason: str | None = None        # "no_data_yet", "requires_extractors_N+2", etc.
```

### 5.4 Cypher parameterization mandate (carried from N+0)

All filter values are passed as named parameters (`$param`), never via string interpolation. Filter whitelisting validates keys; parameterization protects values. No raw user input reaches Cypher as literal syntax.

## 6. LLM provider abstraction

### 6.1 Three supported modes

Per LiteLLM router configuration (spec §4.2):

| Mode | Embedding | Extraction | Default | Use case |
|---|---|---|---|---|
| `local-embed-only` ⭐ | Ollama `nomic-embed-text` | skipped (structured ingest) | **this slice default** | OAuth-consistent, zero pay-per-token, substrate-proven |
| `cloud-embed-only` | OpenAI-compat endpoint (Alibaba / OpenAI / Voyage / Cohere) | skipped | alternative for Intel-Mac deployments where Ollama is slow | low cost ($0.10–0.15 / month at our scale) |
| `full-local` / `full-cloud` / `hybrid` | | | reserved for slices N+5+ where LLM extraction is needed (#10 Domain Glossary, #13 Invariants, #15 Edge-Cases, #35 Taint) | not active in N+1 |

### 6.2 Installer prompt (added to `just setup`)

```
Q: Which embedding provider for Graphiti?
  1. Ollama (local, default — zero API cost, requires ~2 GB RAM)
  2. OpenAI-compatible endpoint (cloud — requires API key; recommended if Ollama is slow on your hardware)
  3. Skip — use palace-memory without semantic search (only structured lookup available)
```

Selection writes to `.env`:

```bash
# Option 1 (default)
LLM_MODE=local-embed-only
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
OLLAMA_URL=http://ollama:11434
COMPOSE_PROFILES=full,with-ollama

# Option 2
LLM_MODE=cloud-embed-only
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-...
COMPOSE_PROFILES=full   # no with-ollama
```

### 6.3 Ollama compose service

```yaml
ollama:
  image: ollama/ollama:0.5.0   # pin SHA in implementation
  restart: unless-stopped
  mem_limit: 4g
  cpus: "2.0"
  profiles: [with-ollama]
  volumes:
    - ollama_models:/root/.ollama
  networks:
    - paperclip-agent-net
  healthcheck:
    test: ["CMD-SHELL", "ollama list | grep -q nomic-embed-text || exit 1"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 120s  # allow time for model pull on first boot
```

Init container (or `depends_on` script) pulls `nomic-embed-text` on first boot via `ollama pull nomic-embed-text`.

### 6.4 Graphiti compose service

```yaml
graphiti:
  build:
    context: services/graphiti
  restart: unless-stopped
  mem_limit: 1g
  cpus: "1.0"
  profiles: [analyze, full]
  environment:
    NEO4J_URI: "bolt://neo4j:7687"
    NEO4J_PASSWORD: "${NEO4J_PASSWORD}"
    LLM_MODE: "${LLM_MODE}"
    EMBEDDING_PROVIDER: "${EMBEDDING_PROVIDER}"
    EMBEDDING_MODEL: "${EMBEDDING_MODEL}"
    EMBEDDING_BASE_URL: "${EMBEDDING_BASE_URL:-}"   # empty for Ollama
    EMBEDDING_API_KEY: "${EMBEDDING_API_KEY:-}"     # empty for Ollama
    OLLAMA_URL: "${OLLAMA_URL:-http://ollama:11434}"
  depends_on:
    neo4j:
      condition: service_healthy
  ports:
    - "8002:8002"   # graphiti-mcp exposed
    # :8001 internal only, not exposed
  networks:
    - paperclip-agent-net
  healthcheck:
    test: ["CMD-SHELL", "curl -fsS http://localhost:8001/healthz || exit 1"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 60s

palace-mcp:
  # existing N+0 service
  depends_on:
    neo4j:
      condition: service_healthy
    graphiti:
      condition: service_healthy   # NEW — palace-mcp needs Graphiti up
```

## 7. Ingest pipeline (substrate swap)

### 7.1 CLI entrypoint (preserved signature)

```bash
python -m palace_mcp.ingest.paperclip \
    --paperclip-url https://paperclip.ant013.work \
    --company-id 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64 \
    --project-slug gimle
```

New `--project-slug` parameter (default `gimle`) sets `group_id = project/<slug>` for all written nodes.

### 7.2 Phases

Phase transformation vs N+0:

1. **Old (N+0):** direct Cypher `MERGE` against Neo4j bolt driver.
2. **New (N+1):** structured feed to Graphiti via `graphiti.add_triplet()` path, bypassing LLM extraction. Graphiti under the hood writes to same Neo4j but also computes embeddings for text fields using the configured provider (§6).

```python
async def run_ingest(project_slug: str):
    started_at = utcnow_iso()
    errors: list[str] = []
    group_id = f"project/{project_slug}"

    async with GraphitiClient(group_id=group_id) as g:
        # 1. Ensure :Project node
        await g.upsert_project(slug=project_slug, tags=[...], ...)

        # 2. Fetch from paperclip API
        issues   = await paperclip_api.list_issues(...)
        agents   = await paperclip_api.list_agents(...)
        comments = await paperclip_api.list_comments(issues=[i["id"] for i in issues])

        # 3. Feed structured entities — no LLM
        for agent in agents:
            await g.add_triplet(
                source_node=agent_node_spec(agent, group_id),
                edge=("BELONGS_TO_PROJECT", {"valid_from": started_at, "valid_to": None}),
                target_node=project_node_ref(project_slug)
            )

        for issue in issues:
            await g.add_triplet(source_node=issue_node_spec(issue, group_id), ...)
            # ASSIGNED_TO edge if assignee present

        for comment in comments:
            await g.add_triplet(...)  # ON + AUTHORED_BY edges

        # 4. Embed text fields for search (embedding provider call)
        await g.compute_embeddings_for(
            node_labels=["Issue", "Comment", "Note"],
            text_fields={"Issue": "description", "Comment": "body", "Note": "text"},
            group_id=group_id
        )

        # 5. GC — unchanged from N+0; scoped to group_id
        if not errors:
            await g.gc_orphans(source="paperclip", cutoff=started_at, group_id=group_id)
```

Idempotency: same as N+0 — MERGE-based upserts are naturally idempotent when re-run without paperclip changes.

### 7.3 Edge cases (preserved from N+0 + new)

- **Human-authored comment** → `AUTHORED_BY` edge not created (unchanged from N+0).
- **Mid-ingest partial failure** → GC skipped; errors recorded in `:IngestRun.errors` (unchanged).
- **Parallel ingest runs for different projects** → allowed (different `group_id`); same-project parallel ingest still undefended (single-operator assumption).
- **NEW: Ollama not ready at ingest start** → retry with 30s backoff up to 3 times, then fail with explicit error pointing to `ollama pull nomic-embed-text` manual step.
- **NEW: Embedding provider returns error** → ingest completes for structural MERGE; `meta.embedding_errors` field on `:IngestRun` lists failed chunks. Search queries on affected nodes return partial results with `staleness_warning`.

## 8. graphiti-mcp surface for paperclip agents

Graphiti-core ships an official MCP server v1.0 exposing `add_episode`, `search_memory_nodes`, `search_memory_facts`, `get_episodes`. This surface is exposed on port `:8002` and added to paperclip agents' MCP configuration via the shared-fragments repository.

### 8.1 Shared-fragments update (ant013/paperclip-shared-fragments)

New fragment `palace-memory-mcp.md`:

```markdown
## palace-memory MCP access

You have direct access to Gimle-Palace memory via two MCP servers:

1. **palace-memory** (curated tools, structured queries)
   - URL: http://localhost:8080/mcp (via SSH tunnel to iMac)
   - Use for: `palace.memory.lookup`, `palace.memory.search`, `palace.memory.record_note`, etc.

2. **graphiti** (raw graph access, advanced)
   - URL: http://localhost:8002/mcp
   - Use for: `add_episode`, `search_memory_nodes`, `get_episodes`
   - Project scoping: pass `group_id="project/gimle"` (or current project) to all operations.

When recording observations, prefer palace.memory.record_note (auto-scopes to current project).
When searching prior knowledge, prefer palace.memory.search — more ergonomic than raw Graphiti search.
Fall back to direct graphiti MCP only for advanced graph traversal the curated tools don't expose.
```

Deployment: `paperclips/deploy-agents.sh` picks up the new fragment on next run; manual re-deploy needed after N+1 merge.

### 8.2 Authentication

graphiti-mcp is exposed on `paperclip-agent-net` (Docker internal network). Paperclip agents running in the same network reach it directly. External MCP clients (Claude Code on user's machine) continue to use palace-mcp only — not graphiti-mcp. This enforces curated-surface discipline for external clients while giving agents full power.

No authentication on graphiti-mcp within the internal network. This is the same trust boundary as N+0. Hardening (per-agent token) is a deliberate post-MVP slice.

## 9. Observability (L3)

### 9.1 Structured JSON logs

Extended from N+0 log schema:

```
{"event":"ingest.start","source":"paperclip","project_slug":"gimle","group_id":"project/gimle","run_id":"..."}
{"event":"ingest.fetch.issues","count":31,"source":"paperclip","project_slug":"gimle"}
{"event":"ingest.triplet","type":"Issue","count":31,"duration_ms":245}
{"event":"ingest.embed","provider":"ollama","model":"nomic-embed-text","chunks":83,"duration_ms":28000}
{"event":"ingest.gc","type":"Issue","deleted":0,"group_id":"project/gimle"}
{"event":"ingest.finish","duration_ms":31500,"errors":[],"embedding_errors":[]}
{"event":"query.search","query":"Coordinator pattern","project_scope":"*","matched":5,"duration_ms":42}
{"event":"query.record_note","tags":["pattern"],"scope":"project","project_scope":"gimle","note_id":"..."}
```

### 9.2 Health tool (updated)

```python
class HealthResponse(BaseModel):
    neo4j_reachable: bool
    graphiti_reachable: bool          # NEW
    ollama_reachable: bool | None     # NEW — None if embedding provider is cloud
    embedding_provider: str           # NEW — "ollama" | "openai" | ...
    embedding_model: str              # NEW
    project_counts: dict[str, dict[str, int]]   # NEW — per-project {Issue, Comment, Agent, Note} counts
    last_ingest_per_project: dict[str, IngestSummary]   # NEW
```

Example response:

```json
{
  "ok": true,
  "data": {
    "neo4j_reachable": true,
    "graphiti_reachable": true,
    "ollama_reachable": true,
    "embedding_provider": "ollama",
    "embedding_model": "nomic-embed-text",
    "project_counts": {
      "gimle": {"Issue": 31, "Comment": 52, "Agent": 12, "Note": 0}
    },
    "last_ingest_per_project": {
      "gimle": {"started_at": "...", "finished_at": "...", "duration_ms": 31500, "errors": []}
    }
  }
}
```

## 10. Decomposition (plan-first ready)

Expected plan-file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1-graphiti.md` — produced by CTO when formalizing the issue. Skeleton matching the GIM-34 pattern:

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create GIM-NN issue + plan file. Reassign to CodeReviewer for plan review. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance check. APPROVE → Phase 2. |
| 2 | 2.1 | MCPEngineer | Add `graphiti` compose service skeleton + `services/graphiti/` Python wrapper + healthcheck. |
| 2 | 2.2 | MCPEngineer | Add `ollama` compose service under `with-ollama` profile + init-container model pull + healthcheck. |
| 2 | 2.3 | MCPEngineer | LiteLLM router integration in graphiti service + env-driven provider selection (§6). |
| 2 | 2.4 | MCPEngineer | Schema migration: add `:Project` entity, `BELONGS_TO_PROJECT` edges, `group_id` property + constraints (§4). |
| 2 | 2.5 | MCPEngineer | Ingest pipeline substrate swap — `palace_mcp.ingest.paperclip` rewritten to use Graphiti `add_triplet` (§7). `--project-slug` CLI param. |
| 2 | 2.6 | MCPEngineer | Register all 22 S3 tools on palace-mcp (§5) — stubs for extractor-dependent ones with `meta.reason`. Real impl for `lookup` (N+0 preserved), `search`, `health`, `record_note`, `record_iteration_note`, `link_items`, `list_projects`, `get_project_overview`. |
| 2 | 2.7 | MCPEngineer | Expose graphiti-mcp on `:8002` + update shared-fragments with `palace-memory-mcp.md` fragment (§8). |
| 2 | 2.8 | MCPEngineer | Unit tests — all new tools, bi-temporal edge schema, multi-project scoping, provider abstraction (≥50 new tests). |
| 3 | 3.1 | CodeReviewer | PR mechanical review: compliance table, plan-first checklist, SDK conformance, no Cypher injection, mypy --strict clean. |
| 3 | 3.2 | OpusArchitectReviewer | (If GIM-30 wiring has landed.) Docs-first adversarial pass via `context7` — Graphiti-core usage, LiteLLM router patterns, Neo4j bi-temporal best practices. Advisory unless CRITICAL. |
| 4 | 4.1 | QAEngineer | Live smoke: `docker compose --profile full,with-ollama up`, run ingest CLI with `--project-slug=gimle`, connect Claude Code to `palace-memory`, call `record_note` → restart session → `search` finds the note. Connect one paperclip agent (e.g., CodeReviewer) to graphiti-mcp directly, verify `add_episode` + `search_memory_nodes` roundtrip. Attach evidence. |
| 4 | 4.2 | MCPEngineer | Merge to `develop` (squash). Update plan-file checkboxes. Close issue with acceptance-criteria evidence table. Post-merge: manual iMac deploy (`docker compose pull && up`) per `reference_post_merge_deploy_gap.md`. |

## 11. Acceptance criteria

- [ ] PR opened against `develop`; squash-merged on APPROVE.
- [ ] Plan file committed under `docs/superpowers/plans/`; PR description links to it.
- [ ] `services/graphiti/` module importable; unit tests green.
- [ ] Compose stack brings up 4 services (neo4j, palace-mcp, graphiti, ollama under `with-ollama` profile) on `docker compose --profile full,with-ollama up`.
- [ ] All 22 S3 tools registered and callable from MCP client; stubs return `meta.reason` explaining data dependency.
- [ ] Schema constraints applied idempotently at startup (`project_slug`, `issue_id`, `comment_id`, `agent_id`, `note_id`).
- [ ] Bi-temporal edge data model present (`valid_from` / `valid_to` on `:BELONGS_TO_PROJECT`); unit test verifies setting `valid_to` on edge revocation.
- [ ] `:Project` node for `gimle` created during first ingest; `palace.memory.list_projects` returns it with tags.
- [ ] Live MCP client smoke test — external: `palace.memory.record_note(text="test N+1 substrate", tags=["smoke"])` then `palace.memory.search(query="test N+1")` returns the note with similarity > 0.5.
- [ ] Live MCP client smoke test — agent: paperclip agent connected to graphiti-mcp calls `add_episode` + `search_memory_nodes`, receives expected result.
- [ ] Idempotency: re-running ingest without paperclip changes leaves entity counts unchanged; updates only `palace_last_seen_at` and `valid_from` unchanged for permanent edges.
- [ ] Multi-project schema smoke: manually create a second `:Project` node (`medic`) via Cypher; `palace.memory.list_projects` returns both; `palace.memory.lookup(entity_type="Issue", project="gimle")` scopes correctly.
- [ ] Cross-project search smoke: `palace.memory.search(query="...", project="*")` returns results across all projects; `project=["gimle"]` constrains to single project.
- [ ] LLM provider abstraction: `docker compose` with `LLM_MODE=cloud-embed-only` and a test OpenAI-compat endpoint env set — ingest completes without Ollama running.
- [ ] `docker compose logs palace-mcp graphiti` produces JSON events matching `ingest.*`, `query.*` patterns with `project_slug` / `project_scope` fields.
- [ ] `uv run mypy --strict` green across `palace-mcp` and `graphiti` modules.
- [ ] CI green on all four jobs (lint, typecheck, test, docker-build) with new Graphiti service included in docker-build.
- [ ] CodeReviewer posts APPROVE with full compliance table (anti-rubber-stamp discipline).
- [ ] QAEngineer attaches smoke evidence for both MCP surfaces (screenshot or curl-equivalent).
- [ ] Post-merge: manual iMac deploy performed and `palace.memory.health` returns `graphiti_reachable: true` from user's Claude Code.

## 12. Out of scope (explicit — Karpathy §2)

- **LLM entity extraction.** Structured paperclip entities only; graphiti-core's LLM extraction pipeline bypassed via `add_triplet` path. LLM extraction activates in slices N+5+ where free-text sources land (GitHub PR bodies, Claude transcripts).
- **palace-serena service.** Deferred to N+2 slice (parallel track); substrate here does not require it.
- **Git History Harvester.** Deferred to N+2 slice (parallel track).
- **Any extractor role.** Architecture-extractor, reviewer roles, etc. — all in N+2…N+6 roadmap from `report.md` §8.
- **Scheduled / cron ingest.** Manual trigger only in this slice; scheduler is a separate slice.
- **Natural-language query (Q-A shape).** Only structured (Q-B) + semantic-search (`palace.memory.search`) in this slice.
- **Paperclip write tools** (`create_paperclip_issue`). Stub in tool surface; real impl needs paperclip write auth design.
- **Explicit `:RELATED_TO` edges** between projects (Variant γ from brainstorming). Tag-based fuzzy relatedness (β) only. Schema does not preclude adding γ later.
- **Concurrent ingest locking per project.** Single-operator assumption preserved from N+0; parallel multi-project ingest allowed via different `group_id`.
- **Cross-source conflict resolution.** Only paperclip source in this slice; conflict resolution via `source_created_at DESC LIMIT 1` is schema-ready but unused.
- **`palace.memory.ingest` MCP tool.** CLI-only trigger in this slice; MCP-wrapper follow-up micro-slice candidate.
- **Pagination > 100 / cursor-based pagination.** MVP limit 100 preserved from N+0.
- **Authentication on graphiti-mcp.** Internal Docker network trust boundary; per-agent token deferred.
- **Graphiti MCP tool exposure on external-facing port.** `palace-memory` MCP remains the only external client surface — curated-tool discipline.
- **SCIP integration / palace-serena MCP tools.** Schema reserves `scip_id: str | null` field on `:Symbol` for N+2+ population; no writer in this slice.
- **Capability-axis labels on existing nodes.** Reserved in schema; actual labels (`:Audits`, `:Observes`, etc.) added by extractors in N+2+.
- **FastMCP `Context` parameter migration** (inherited debt from GIM-23 — see N+0 §10).

## 13. Estimated size

- Code: ~800 LOC (graphiti service ~200, palace-mcp tool registration ~250, schema migration ~100, ingest substrate swap ~150, tests ~200).
- Plan + docs: ~120 LOC plan-file.
- 1 PR, 4-5 handoffs (CTO → CR → MCPEngineer → CR (+ Opus optional) → QAEngineer → MCPEngineer merge).
- Expected duration: 7-9 days of agent work (vs N+0's ~1 day — reflects substrate complexity + 22 tool stubs + two MCP surfaces + provider abstraction).

## 14. Followups (separate issues post-merge)

- **`palace.memory.ingest` MCP wrapper** — thin tool over CLI so external orchestrators can trigger ingest without shell access. Micro-slice.
- **Per-agent auth on graphiti-mcp** — token-based auth within Docker network. Security-hardening slice.
- **Second project bootstrap** — when Medic team adds their paperclip instance, validate multi-project path end-to-end. Likely Medic-driven.
- **Enable OpusArchitectReviewer** on this PR if GIM-30 wiring has landed.
- **N+2 brainstorm** — parallel slice decomposition: palace-serena service + git-harvester + #1 Architecture Layer + #25 Build System (from `report.md` §8).
- **LiteLLM router hardening** — retry/fallback policies for cloud embedding provider outages.
