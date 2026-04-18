# Palace Memory — N+1a Graphiti substrate swap

**Date:** 2026-04-18
**Slice:** N+1a (first of three N+1 sub-slices)
**Author:** Board
**Status:** Draft — awaiting CTO formalization as GIM-NN issue
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §4.2, §5; `docs/research/graphiti-core-verification.md`; successor slices N+1b (multi-project) + N+1c (agent-MCP + record_note)
**Predecessor slice:** N+0 (GIM-34) — `docs/superpowers/specs/2026-04-17-palace-memory-paperclip-slice.md`
**Supersedes:** `2026-04-18-palace-memory-n1-graphiti-substrate.md` (REJECTED — API hallucinations)

## 1. Context

N+0 shipped paperclip ingest + `palace.memory.lookup/health` on plain Neo4j with direct Cypher `MERGE`. N+1 was originally drafted as a single combined slice (substrate + multi-project + agent-MCP) which the Board rejected for non-atomicity and API hallucinations. This slice (N+1a) ships **only the substrate swap** — N+0 user-visible behavior is 100% preserved, but writes go through `graphiti-core.add_triplet` with typed `EntityNode` + bi-temporal `EntityEdge`. Multi-project scoping (N+1b) and agent-MCP surface (N+1c) follow as independent slices.

Why this order: substrate is the highest-risk change (wrong API choice = rework of all downstream). By shipping it in isolation with N+0 acceptance preserved, risk is contained. N+1b/N+1c build on verified-working substrate.

## 2. Goal

After this slice, `palace-mcp` uses `graphiti-core` under the hood for all writes and reads; paperclip ingest produces `:Issue`/`:Comment`/`:Agent` nodes via `add_triplet` (bypassing LLM extraction); `palace.memory.lookup` and `palace.memory.health` return identical results to N+0.

**Success criterion:** `python -m palace_mcp.ingest.paperclip` completes against the live Gimle paperclip; `palace.memory.lookup(entity_type="Issue", filters={"status":"done"})` from Claude Code returns the same result set as N+0; Neo4j Browser shows nodes carry `labels=["Issue", "Entity"]` (graphiti-core format) instead of plain `:Issue`.

## 3. Architecture

One new compose service (`graphiti`), one refactored service (`palace-mcp`). No Ollama compose service in this slice — embedding provider is **external URL only** (user's hosted Ollama, Alibaba DashScope, OpenAI, etc.) via env config. Local Ollama compose is deferred to N+1c `with-local-ollama` profile.

```
┌─────────────────────┐                      ┌──────────────────────────────────┐
│ Paperclip HTTP API  │◄──── ingest ────────►│ palace-mcp (FastAPI+FastMCP)     │
│ (iMac:3100)         │     (on-demand CLI)  │  ├── /mcp  streamable-HTTP       │
└─────────────────────┘                      │  │   ├── palace.memory.lookup   │
                                             │  │   ├── palace.memory.health   │
                                             │  │   └── palace.health.status   │
                                             │  └── ingest CLI uses             │
                                             │      graphiti_core.add_triplet   │
                                             └───────────────┬──────────────────┘
                                                             │ HTTP (internal)
                                                             ▼
                                             ┌──────────────────────────────────┐
                                             │ graphiti (Python 3.11 + FastAPI  │
                                             │  + graphiti-core + uvicorn)      │
                                             │  ├── /healthz                    │
                                             │  ├── internal RPC for palace-mcp │
                                             │  │   (add_triplet, search, get)  │
                                             │  └── graphiti-core OpenAIGeneric │
                                             │      + OpenAIEmbedder pointing   │
                                             │      at EMBEDDING_BASE_URL       │
                                             └──────┬──────────────────┬────────┘
                                                    │ Bolt             │ HTTP
                                                    ▼                  ▼
                                        ┌──────────────────┐  ┌──────────────────┐
                                        │  Neo4j 5.26      │  │ External         │
                                        │  (existing)      │  │ embedding server │
                                        └──────────────────┘  │ (user's Ollama / │
                                                              │  Alibaba / etc.) │
                                                              └──────────────────┘
┌─────────────────────┐
│ External MCP client │──── MCP streamable-HTTP :8080 (unchanged from N+0)
└─────────────────────┘
```

Compose additions:

```yaml
graphiti:
  build:
    context: services/graphiti
  restart: unless-stopped
  mem_limit: 1g
  cpus: "1.0"
  profiles: [review, analyze, full]
  environment:
    NEO4J_URI: "bolt://neo4j:7687"
    NEO4J_USER: "neo4j"
    NEO4J_PASSWORD: "${NEO4J_PASSWORD}"
    EMBEDDING_BASE_URL: "${EMBEDDING_BASE_URL}"
    EMBEDDING_API_KEY: "${EMBEDDING_API_KEY:-placeholder}"
    EMBEDDING_MODEL: "${EMBEDDING_MODEL:-nomic-embed-text}"
    EMBEDDING_DIM: "${EMBEDDING_DIM:-768}"
    # LLM client required by Graphiti constructor; N+1a never calls add_episode
    LLM_BASE_URL: "${LLM_BASE_URL:-${EMBEDDING_BASE_URL}}"
    LLM_API_KEY: "${LLM_API_KEY:-${EMBEDDING_API_KEY:-placeholder}}"
    LLM_MODEL: "${LLM_MODEL:-llama3:8b}"
  depends_on:
    neo4j:
      condition: service_healthy
  networks:
    - paperclip-agent-net
  healthcheck:
    test: ["CMD-SHELL", "curl -fsS http://localhost:8001/healthz || exit 1"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 60s

palace-mcp:
  # existing N+0 service; ONE change — new dependency
  depends_on:
    neo4j:
      condition: service_healthy
    graphiti:
      condition: service_healthy
  environment:
    GRAPHITI_URL: "http://graphiti:8001"
    # existing NEO4J_* vars kept for direct read-path fallback if needed
```

## 4. Graphiti schema (N+0 entities rewritten)

All nodes use graphiti-core `EntityNode` with custom `labels: list[str]`. Graphiti always prepends `:Entity`, so labels like `["Issue", "Entity"]` produce `:Issue:Entity` in Cypher — both are queryable.

`group_id` hardcoded to `"project/gimle"` in this slice (multi-project comes in N+1b). This is a single-line change when N+1b lands.

### 4.1 Nodes

```python
# Issue
EntityNode(
    uuid=issue.id,                           # paperclip UUID as stable ID
    name=f"{issue.key}: {issue.title}",
    labels=["Issue", "Entity"],
    group_id="project/gimle",
    summary=issue.description[:500],
    attributes={
        "id": issue.id, "key": issue.key, "title": issue.title,
        "description": issue.description, "status": issue.status,
        "source": "paperclip",
        "source_created_at": issue.createdAt,
        "source_updated_at": issue.updatedAt,
        "palace_last_seen_at": run_started,
        "text_hash": sha256(issue.description).hexdigest(),
    }
)

# Comment — labels=["Comment", "Entity"], attributes: id, body, source, three timestamps, text_hash
# Agent — labels=["Agent", "Entity"], attributes: id, name, url_key, role, source, three timestamps
```

Uniqueness guaranteed via `uuid` = paperclip UUID (graphiti uses `uuid` as primary identifier).

### 4.2 Edges

```python
# Comment ON Issue
EntityEdge(
    source_node_uuid=comment.uuid,
    target_node_uuid=issue.uuid,
    name="ON",
    fact=f"Comment {comment.id} is on issue {issue.key}",
    group_id="project/gimle",
    created_at=run_started,
    valid_at=comment.createdAt,
    invalid_at=None,      # never invalidated for comment-on-issue
)

# Comment AUTHORED_BY Agent (when authored_by_agent_id present)
EntityEdge(source=comment, target=agent, name="AUTHORED_BY", ...)

# Issue ASSIGNED_TO Agent (when assignee present; refreshed per ingest)
EntityEdge(source=issue, target=agent, name="ASSIGNED_TO", valid_at=run_started, ...)
```

Bi-temporal discipline: `valid_at` is set to the source-system timestamp where meaningful; `invalid_at` left null for permanent relationships. When ingest detects that an assignment has changed (same issue now has a different assignee), the old edge gets `invalid_at = run_started`; new edge created with fresh `valid_at`. This is the first slice actually exercising bi-temporal semantics.

### 4.3 Idempotency + change detection

On each ingest pass, per node:

1. Look up existing node by `uuid`.
2. If missing → build full `EntityNode` → `graphiti.add_node(node)` (triggers embedding).
3. If present and `attributes.text_hash == new_text_hash` → skip embedding, only update `palace_last_seen_at`.
4. If present and `text_hash` differs → rebuild node → save (re-embed new text).

Change detection is implemented in the ingest transform module, not in graphiti-core itself. Critical for cost control on cloud-embedding providers.

## 5. MCP tool surface — N+0 PRESERVED

Three tools only. No new tools in N+1a.

| Tool | Status | Changes from N+0 |
|---|---|---|
| `palace.health.status` | Preserved from GIM-23 | None |
| `palace.memory.lookup(entity_type, filters, limit, order_by)` | Preserved | Implementation switches from direct Cypher to `graphiti.get_by_group_ids(["project/gimle"])` + filter pushdown; identical response shape + `meta` envelope |
| `palace.memory.health()` | Preserved | Extended: response includes `graphiti_reachable: bool`, `embedder_reachable: bool`, `embedding_model: str`, `embedding_provider_base_url: str (hostname only)` |

No `project` param in N+1a tools — that's N+1b. No `search`, `record_note`, or anything agent-MCP — that's N+1c.

## 6. Ingest pipeline (substrate swap)

CLI signature unchanged from N+0:

```bash
python -m palace_mcp.ingest.paperclip \
    --paperclip-url https://paperclip.ant013.work \
    --company-id 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
```

### 6.1 Phases (rewrite of N+0 §6)

```python
async def run_ingest():
    started_at = utcnow_iso()
    errors: list[str] = []
    run_id = str(uuid4())

    # Initialize graphiti-core client (external URL from env)
    graphiti = Graphiti(
        neo4j_uri=NEO4J_URI, neo4j_user=NEO4J_USER, neo4j_password=NEO4J_PASSWORD,
        llm_client=OpenAIGenericClient(LLMConfig(
            api_key=LLM_API_KEY, model=LLM_MODEL, base_url=LLM_BASE_URL
        )),
        embedder=OpenAIEmbedder(OpenAIEmbedderConfig(
            api_key=EMBEDDING_API_KEY, embedding_model=EMBEDDING_MODEL,
            embedding_dim=EMBEDDING_DIM, base_url=EMBEDDING_BASE_URL
        )),
    )

    try:
        issues   = await paperclip_api.list_issues(company_id=...)
        agents   = await paperclip_api.list_agents(company_id=...)
        comments = await paperclip_api.list_comments(issues=[i["id"] for i in issues])

        # Upsert agents first (Issues/Comments reference them via FK-like edges)
        for agent in agents:
            node = build_agent_node(agent, started_at)
            await upsert_with_change_detection(graphiti, node)

        # Upsert issues — each as a triplet (Issue, ASSIGNED_TO-or-null, Agent)
        for issue in issues:
            issue_node = build_issue_node(issue, started_at)
            await upsert_with_change_detection(graphiti, issue_node)
            if issue.get("assigneeAgentId"):
                edge = build_assigned_to_edge(issue_node, agent_nodes[issue.assigneeAgentId], started_at)
                await graphiti.add_triplet(issue_node, edge, agent_nodes[issue.assigneeAgentId])

        # Comments — triplet (Comment, ON, Issue) + optional (Comment, AUTHORED_BY, Agent)
        for comment in comments:
            comment_node = build_comment_node(comment, started_at)
            await upsert_with_change_detection(graphiti, comment_node)
            edge_on = build_on_edge(comment_node, issue_nodes[comment.issueId], started_at)
            await graphiti.add_triplet(comment_node, edge_on, issue_nodes[comment.issueId])
            if comment.get("authoredByAgentId"):
                edge_auth = build_authored_by_edge(comment_node, agent_nodes[comment.authoredByAgentId], started_at)
                await graphiti.add_triplet(comment_node, edge_auth, agent_nodes[comment.authoredByAgentId])

        # Invalidate stale ASSIGNED_TO edges where assignee changed
        await invalidate_stale_assignments(graphiti, issues, started_at)

        # GC — delete nodes whose palace_last_seen_at < run_started (graphiti has no native GC,
        # drop to raw Cypher scoped to group_id for this operation)
        if not errors:
            await gc_orphans(graphiti, source="paperclip", cutoff=started_at, group_id="project/gimle")

    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
        raise
    finally:
        await record_ingest_run(graphiti, run_id, started_at, utcnow_iso(), errors)
        await graphiti.close()
```

### 6.2 Edge cases (preserved from N+0 + new)

- Human-authored comment → `AUTHORED_BY` edge not created (N+0 preserved).
- Mid-ingest partial failure → GC skipped; errors recorded in `:IngestRun` node.
- **NEW:** embedder reachability failure → ingest aborts with explicit error; no partial state.
- **NEW:** text_hash mismatch → re-embed. Same hash → skip embed (cost control on cloud).

## 7. Observability

JSON log events extended from N+0:

```
{"event":"ingest.start","source":"paperclip","run_id":"...","group_id":"project/gimle"}
{"event":"ingest.embedder.probe","base_url":"http://ollama-host.example.com:11434/v1","model":"nomic-embed-text","reachable":true}
{"event":"ingest.upsert","type":"Agent","count":12,"embedded":12,"skipped_unchanged":0,"duration_ms":4800}
{"event":"ingest.upsert","type":"Issue","count":31,"embedded":5,"skipped_unchanged":26,"duration_ms":1200}
{"event":"ingest.triplet","type":"ON","count":52,"duration_ms":300}
{"event":"ingest.invalidate","type":"ASSIGNED_TO","count":2,"duration_ms":50}
{"event":"ingest.gc","type":"Issue","deleted":0}
{"event":"ingest.finish","duration_ms":6400,"errors":[],"embedded_total":17,"skipped_total":26}
```

Health tool extensions per §5 table.

## 8. Decomposition (plan-first ready)

Expected plan-file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1a-substrate.md`.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create GIM-NN issue + plan file. Reassign to CodeReviewer. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance + design sanity check. APPROVE → Phase 2. |
| 2 | 2.1 | MCPEngineer | Resolve 4 mini-gaps via local poke (see `graphiti-core-verification.md` §4); commit findings as appendix. |
| 2 | 2.2 | MCPEngineer | Add `services/graphiti/` — Python 3.11 FastAPI wrapper exposing `/healthz` + internal RPC; graphiti-core initialized with OpenAIGenericClient + OpenAIEmbedder from env. |
| 2 | 2.3 | MCPEngineer | Rewrite `palace_mcp/ingest/*` modules to build `EntityNode` / `EntityEdge` and call `graphiti.add_triplet` / `add_node`; implement `upsert_with_change_detection` (text_hash). |
| 2 | 2.4 | MCPEngineer | Rewrite `palace_mcp/memory/lookup.py` to read via graphiti-core (`get_by_group_ids`); preserve response envelope byte-for-byte; preserve whitelisted filter resolver. |
| 2 | 2.5 | MCPEngineer | Extend `palace_mcp/memory/health.py` with graphiti + embedder reachability probes. |
| 2 | 2.6 | MCPEngineer | Unit tests — ingest with mocked graphiti client, change-detection logic, stale-assignment invalidation, health extensions, lookup backward-compat (≥30 new tests). |
| 3 | 3.1 | CodeReviewer | PR mechanical review: compliance, plan-first, no raw Cypher in ingest path, mypy --strict, no Graphiti API hallucinations (cross-check against `graphiti-core-verification.md`). |
| 3 | 3.2 | OpusArchitectReviewer | (If GIM-30 wired) docs-first adversarial pass via context7; advisory unless CRITICAL. |
| 4 | 4.1 | QAEngineer | Live smoke: compose up, set EMBEDDING_BASE_URL to external Ollama (or Alibaba for Intel-Mac path), run ingest CLI, verify `palace.memory.lookup(entity_type="Issue", filters={"status":"done"})` returns same ≥1 issue with three timestamps; Cypher inspection confirms `:Issue:Entity` labels. |
| 4 | 4.2 | MCPEngineer | Squash-merge to develop. Update plan-file checkboxes. Manual iMac deploy. |

## 9. Acceptance criteria

- [ ] PR against develop, squash-merged on APPROVE.
- [ ] Plan file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1a-substrate.md`.
- [ ] 4 mini-gap verification appendix committed (Graphiti(llm_client=None) behavior, EntityNode.attributes round-trip, similarity score return, Neo4j 5.26 compatibility).
- [ ] `services/graphiti/` importable; `/healthz` returns 200 within start_period.
- [ ] Compose stack brings up 3 services (neo4j, palace-mcp, graphiti) in profile `full` without ollama compose service.
- [ ] `EMBEDDING_BASE_URL` env drives embedder; documented paths for external Ollama, Alibaba DashScope, OpenAI direct.
- [ ] Ingest CLI runs to completion against live paperclip; produces ≥31 `:Issue:Entity` nodes, ≥52 `:Comment:Entity`, ≥12 `:Agent:Entity` in group_id `project/gimle`.
- [ ] Nodes carry `text_hash` attribute; re-running ingest without paperclip changes reports `embedded: 0, skipped_unchanged: N` in logs.
- [ ] Stale `ASSIGNED_TO` edge gets `invalid_at` set when assignee changes between ingests (unit test + smoke scenario).
- [ ] `palace.memory.lookup(entity_type="Issue", filters={"status":"done"})` returns identical result set to N+0 (same issue IDs, same three timestamp fields).
- [ ] `palace.memory.health()` returns `graphiti_reachable: true` + `embedder_reachable: true` + `embedding_model: nomic-embed-text` (or configured).
- [ ] `uv run mypy --strict` green across palace-mcp and services/graphiti.
- [ ] CI green (lint, typecheck, test, docker-build).
- [ ] Post-merge: manual iMac deploy; external Claude Code verifies `palace.memory.lookup` works end-to-end.

## 10. Out of scope (explicit)

- **Multi-project.** `group_id` hardcoded `project/gimle`; `:Project` entity, project param on tools, multi-project query — all N+1b.
- **Agent-facing MCP.** graphiti-mcp exposure on :8002, per-agent auth — all N+1c.
- **record_note / search / any new tool.** N+0 surface preserved only.
- **Ollama compose service.** External URL only in N+1a. Local compose service (profile `with-local-ollama`) lands in N+1c.
- **LLM extraction.** `add_episode` never called; `add_triplet` path exclusively. LLM extraction lands in N+5+ per research roadmap.
- **Bi-temporal demo beyond ASSIGNED_TO invalidation.** Schema supports `valid_at`/`invalid_at`/`expired_at` on all edges; only ASSIGNED_TO invalidation is exercised in N+1a.
- **Faceted classification axes.** Only `labels: ["Issue", "Entity"]` / `["Comment", "Entity"]` / `["Agent", "Entity"]` in N+1a; capability axis + domain-concept labels from spec §5.4 land with first extractor in N+2.
- **SCIP-alignment field on `:Symbol`.** No `:Symbol` nodes in N+1a; reserved for palace-serena slice.
- **`:Iteration` node type.** Reserved for code-ingest slices.
- **Installer prompt for embedding provider choice.** Env-only in N+1a; interactive installer UI lands in N+1c.
- **OpusArchitectReviewer enablement.** Advisory only; GIM-30 still unwired unless separately landed.
- **Post-merge deploy automation.** Still manual in N+1a; automation lands in N+1c (same slice as installer UX).

## 11. Estimated size

- Code: ~400 LOC (graphiti service wrapper ~100, ingest rewrite ~150, lookup/health updates ~80, tests ~70).
- Plan + docs: ~60 LOC.
- 1 PR, 4-5 handoffs.
- Expected duration: 3 days agent-time.

## 12. Followups

- N+1b multi-project slice starts immediately after merge.
- Document 4 mini-gap resolutions in `graphiti-core-verification.md` appendix.
- If `Graphiti(llm_client=None)` proves unsupported, note the workaround (reuse embedder client, never call add_episode) in slice architecture comments for future reference.
