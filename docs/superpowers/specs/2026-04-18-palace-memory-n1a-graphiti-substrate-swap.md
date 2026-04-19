# Palace Memory — N+1a Graphiti substrate swap

> ⚠ **DEPRECATED 2026-04-18.** N+1a was implemented as GIM-48, merged as
> `9d87fa0`, and **reverted** on the same day as `a4abd28`. The
> implementation used graphiti-core API surfaces that do not exist
> (`Graphiti.nodes`, `Graphiti.edges`, `EntityNode.attributes`). The
> replacement slice is `2026-04-18-palace-memory-group-id-migration.md`
> — a `group_id` column on N+0 that unlocks N+1b without a substrate
> swap. See `feedback_qa_skipped_gim48.md` (auto-memory) for post-mortem
> and `reference_graphiti_core_api_truth.md` for the real API surface.
> This file is kept for historical context; **do not implement**.

**Date:** 2026-04-18 (revision 2 — post extended verification)
**Slice:** N+1a (first of three N+1 sub-slices) — **abandoned**
**Author:** Board
**Status:** DEPRECATED (implemented, reverted, superseded)
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §4.2, §5; `docs/research/graphiti-core-verification.md` (full API verification; revision 2 §5-6 resolves 9 additional API-gap questions from Board review #2)
**Predecessor slice:** N+0 (GIM-34) — `docs/superpowers/specs/2026-04-17-palace-memory-paperclip-slice.md`

## 1. Context

N+0 shipped paperclip ingest + `palace.memory.lookup/health` on plain Neo4j. This slice swaps the write+read substrate to `graphiti-core` while preserving N+0 user-visible behavior byte-for-byte. Multi-project scoping (N+1b) and agent-MCP surface (N+1c) follow as independent slices.

**Why this order:** substrate is the highest-risk change. Shipping in isolation with N+0 acceptance preserved contains risk. N+1b/c build on verified-working substrate.

**Architectural collapse vs revision 1:** graphiti-core is a pure Python library imported into palace-mcp directly — no separate compose service, no "internal RPC" layer, no middleman. All graphiti operations are namespace-API method calls: `graphiti.nodes.entity.save(node)`, `graphiti.edges.entity.save(edge)`, `graphiti.edges.entity.get_between_nodes(src, target)`. Zero raw Cypher in ingest path.

## 2. Goal

After this slice: palace-mcp uses graphiti-core for all writes and reads; paperclip ingest produces `:Issue` / `:Comment` / `:Agent` (auto-prepended `:Entity`) nodes via `graphiti.nodes.entity.save`; `ASSIGNED_TO` edge invalidation exercises genuine bi-temporal via `graphiti.edges.entity.save(edge)` with updated `invalid_at`; `palace.memory.lookup` + `palace.memory.health` return identical results to N+0.

**Success criterion:** `python -m palace_mcp.ingest.paperclip` completes against live Gimle paperclip; `palace.memory.lookup(entity_type="Issue", filters={"status":"done"})` from Claude Code returns same result set as N+0; Neo4j Browser shows nodes with `:Issue:Entity` labels; when an issue assignee changes between ingests, Cypher inspection of the corresponding `ASSIGNED_TO` edge shows `invalid_at` set to prior-run timestamp.

## 3. Architecture

Zero new compose services. palace-mcp gains `graphiti-core` as a Python dependency and embedder client configuration.

```
┌─────────────────────┐                      ┌──────────────────────────────────┐
│ Paperclip HTTP API  │◄──── ingest ────────►│ palace-mcp (FastAPI + FastMCP)   │
│ (iMac:3100)         │   (on-demand CLI)    │  ├── /mcp streamable-HTTP :8080  │
│                     │                      │  │   ├── palace.memory.lookup   │
│                     │                      │  │   ├── palace.memory.health   │
│                     │                      │  │   └── palace.health.status   │
│                     │                      │  └── embeds graphiti-core        │
│                     │                      │      - Graphiti(...)             │
│                     │                      │      - namespace API calls       │
│                     │                      │      - OpenAIGenericClient +     │
│                     │                      │        OpenAIEmbedder            │
│                     │                      └──────┬────────────┬──────────────┘
│                     │                             │ Bolt       │ HTTP
│                     │                             ▼            ▼
│                     │                     ┌─────────────┐  ┌────────────────┐
│                     │                     │ Neo4j 5.26  │  │ External       │
│                     │                     └─────────────┘  │ embedder URL   │
│                     │                                      │ (user's Ollama │
│                     │                                      │  or Alibaba)   │
│                     │                                      └────────────────┘
└─────────────────────┘

┌─────────────────────┐
│ External MCP client │──── :8080 (unchanged from N+0)
└─────────────────────┘
```

Compose delta: `palace-mcp` service gains env vars for embedder. No new services.

```yaml
palace-mcp:
  # existing N+0 service
  environment:
    # N+0 preserved
    NEO4J_URI: "bolt://neo4j:7687"
    NEO4J_PASSWORD: "${NEO4J_PASSWORD}"
    # NEW — embedder/LLM client config for graphiti-core (single block covers
    # external Ollama, Alibaba DashScope, OpenAI, Voyage — all OpenAI-compat)
    EMBEDDING_BASE_URL: "${EMBEDDING_BASE_URL}"
    EMBEDDING_API_KEY: "${EMBEDDING_API_KEY:-placeholder}"
    EMBEDDING_MODEL: "${EMBEDDING_MODEL:-nomic-embed-text}"
    EMBEDDING_DIM: "${EMBEDDING_DIM:-768}"
    # LLM client required by Graphiti constructor; never invoked in N+1a
    LLM_BASE_URL: "${LLM_BASE_URL:-${EMBEDDING_BASE_URL}}"
    LLM_API_KEY: "${LLM_API_KEY:-${EMBEDDING_API_KEY:-placeholder}}"
    LLM_MODEL: "${LLM_MODEL:-llama3:8b}"
```

## 4. Graphiti schema (N+0 entities rewritten via graphiti-core)

### 4.1 Nodes — custom labels, auto-prepended `:Entity`

```python
from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

# Issue
issue_node = EntityNode(
    uuid=issue.id,                           # paperclip UUID as stable ID
    name=f"{issue.key}: {issue.title}",
    labels=["Issue"],                        # :Entity auto-prepended by graphiti
    group_id="project/gimle",                # hardcoded in N+1a; N+1b parameterizes
    summary=issue.description[:500],
    attributes={
        "id": issue.id, "key": issue.key, "title": issue.title,
        "description": issue.description, "status": issue.status,
        "source": "paperclip",
        "source_created_at": issue.createdAt,
        "source_updated_at": issue.updatedAt,
        "palace_last_seen_at": run_started,
        "text_hash": sha256(issue.description.encode()).hexdigest(),
    }
)
# Comment — labels=["Comment"], same attrs pattern
# Agent   — labels=["Agent"],   attrs: id, name, url_key, role, source, three timestamps
```

Uniqueness: `uuid` = paperclip UUID. graphiti handles constraint enforcement.

### 4.2 Edges — native bi-temporal via `graphiti.edges.entity.save`

```python
from graphiti_core.edges import EntityEdge
from datetime import datetime, timezone

# Comment ON Issue (permanent)
on_edge = EntityEdge(
    source_node_uuid=comment.uuid,
    target_node_uuid=issue.uuid,
    name="ON",
    fact=f"Comment {comment.id} is on issue {issue.key}",
    group_id="project/gimle",
    created_at=run_started,
    valid_at=comment.createdAt,
    invalid_at=None,
)

# Issue ASSIGNED_TO Agent (revisited each ingest; bi-temporal)
assign_edge = EntityEdge(
    source_node_uuid=issue.uuid,
    target_node_uuid=agent.uuid,
    name="ASSIGNED_TO",
    fact=f"Issue {issue.key} assigned to {agent.name} as of {run_started}",
    group_id="project/gimle",
    created_at=run_started,
    valid_at=run_started,
    invalid_at=None,
)
```

### 4.3 Idempotency + change detection

```python
async def upsert_with_change_detection(graphiti, node):
    try:
        existing = await graphiti.nodes.entity.get_by_uuid(node.uuid)
    except NotFoundError:
        await graphiti.nodes.entity.save(node)   # new — triggers embed
        return "inserted"

    if existing.attributes.get("text_hash") == node.attributes["text_hash"]:
        # Only refresh palace_last_seen_at — skip embed
        existing.attributes["palace_last_seen_at"] = node.attributes["palace_last_seen_at"]
        await graphiti.nodes.entity.save(existing)   # save without embed regeneration
        return "skipped_unchanged"

    # Text changed — full re-embed
    await graphiti.nodes.entity.save(node)
    return "re_embedded"
```

Per verified API: `graphiti.nodes.entity.save(node)` calls `generate_name_embedding(embedder)` internally. Skipping embed when text unchanged requires bypassing this path — acceptable strategy: set `node.name_embedding` manually from `existing.name_embedding` before `save`. Mini-gap (§10) confirms whether that's the correct idiom.

### 4.4 Native bi-temporal: ASSIGNED_TO invalidation

```python
async def invalidate_stale_assignments(graphiti, issue_node, new_agent_uuid, run_started):
    # Fetch all existing edges touching this issue
    existing_edges = await graphiti.edges.entity.get_by_node_uuid(issue_node.uuid)
    for edge in existing_edges:
        if (edge.name == "ASSIGNED_TO"
            and edge.invalid_at is None
            and edge.target_node_uuid != new_agent_uuid):
            # Assignment changed — invalidate old edge
            edge.invalid_at = run_started
            await graphiti.edges.entity.save(edge)   # native update
```

Then the new edge is created via normal `graphiti.nodes.entity.save(new_edge)` (per §4.2).

**Zero raw Cypher.** Per verification §5.D, this is native graphiti-core path.

## 5. MCP tool surface — N+0 PRESERVED

Three tools. No new tools in N+1a.

| Tool | Status | Changes from N+0 |
|---|---|---|
| `palace.health.status` | Preserved from GIM-23 | None |
| `palace.memory.lookup(entity_type, filters, limit, order_by)` | Preserved | Implementation: `graphiti.nodes.entity.get_by_group_ids(["project/gimle"])` → Python-level filter by `entity_type` (label) + `filters` attribute match. Response shape + `meta` envelope byte-identical to N+0. |
| `palace.memory.health()` | Preserved + extended | New fields: `graphiti_initialized: bool`, `embedder_reachable: bool`, `embedding_model: str`, `embedding_provider_base_url: str` (hostname-only for privacy). |

**Filter pushdown strategy:** current scale (31 issues) uses Python-level filter (O(n)). When extractor slices land (N+2+) and `n` grows to thousands, migrate `palace.memory.lookup` to `graphiti.search_(query="", config=NODE_HYBRID_SEARCH_RRF, search_filter=SearchFilters(node_labels=[entity_type]))` — label pushdown via SearchFilters is native. Attribute-level pushdown (e.g., `status=done`) remains Python-level indefinitely; acceptable.

No `project` param in N+1a — that's N+1b. No `search`, no `record_note`, no agent MCP — that's N+1c.

## 6. Ingest pipeline (substrate swap)

CLI signature unchanged from N+0:

```bash
python -m palace_mcp.ingest.paperclip \
    --paperclip-url https://paperclip.ant013.work \
    --company-id 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
```

### 6.1 Phases (rewrite, uses namespace API + native bi-temporal)

```python
from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

async def run_ingest():
    started_at = utcnow_iso()
    errors: list[str] = []
    run_id = str(uuid4())
    group_id = "project/gimle"   # hardcoded in N+1a; parameterized in N+1b

    graphiti = Graphiti(
        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
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

        # 1. Upsert agents
        for agent in agents:
            node = build_agent_node(agent, started_at, group_id)
            await upsert_with_change_detection(graphiti, node)

        # 2. Upsert issues + invalidate+create ASSIGNED_TO edges per-issue
        for issue in issues:
            issue_node = build_issue_node(issue, started_at, group_id)
            await upsert_with_change_detection(graphiti, issue_node)

            new_assignee_uuid = issue.get("assigneeAgentId")
            await invalidate_stale_assignments(graphiti, issue_node, new_assignee_uuid, started_at)
            if new_assignee_uuid:
                await graphiti.edges.entity.save(
                    build_assigned_to_edge(issue_node, agent_nodes[new_assignee_uuid], started_at)
                )

        # 3. Upsert comments + ON/AUTHORED_BY edges
        for comment in comments:
            comment_node = build_comment_node(comment, started_at, group_id)
            await upsert_with_change_detection(graphiti, comment_node)
            await graphiti.edges.entity.save(build_on_edge(comment_node, issue_nodes[comment.issueId], started_at))
            if comment.get("authoredByAgentId"):
                await graphiti.edges.entity.save(build_authored_by_edge(comment_node, agent_nodes[comment.authoredByAgentId], started_at))

        # 4. GC orphans — via graphiti API, no raw Cypher
        if not errors:
            await gc_orphans(graphiti, group_id=group_id, cutoff=started_at)

    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
        raise
    finally:
        # :IngestRun as a first-class EntityNode
        ingest_run = EntityNode(
            uuid=run_id, name=f"ingest-{run_id[:8]}", labels=["IngestRun"],
            group_id=group_id, summary=f"paperclip ingest {started_at}",
            attributes={
                "source": "paperclip", "started_at": started_at,
                "finished_at": utcnow_iso(), "duration_ms": ...,
                "errors": errors, "run_id": run_id,
            }
        )
        await graphiti.nodes.entity.save(ingest_run)
        await graphiti.close()

async def gc_orphans(graphiti, group_id, cutoff):
    # Fetch all :Issue/:Comment/:Agent nodes in group, filter for stale, delete by uuid
    all_nodes = await graphiti.nodes.entity.get_by_group_ids([group_id])
    stale_uuids = [
        n.uuid for n in all_nodes
        if n.attributes.get("source") == "paperclip"
        and n.attributes.get("palace_last_seen_at", "") < cutoff
        and any(lbl in n.labels for lbl in ["Issue", "Comment", "Agent"])
    ]
    if stale_uuids:
        await graphiti.nodes.entity.delete_by_uuids(stale_uuids)
```

### 6.2 Edge cases (preserved + new)

- Human-authored comment → `AUTHORED_BY` edge not created (N+0 preserved).
- Partial failure → GC skipped; `:IngestRun.attributes.errors` records.
- **NEW:** embedder reachability failure at startup → fast-fail with clear error.
- **NEW:** text_hash match → skip embed (cost control). Text change → full re-embed.
- **NEW:** ASSIGNED_TO invalidation: if an issue had no prior assignee, no invalidation happens; if new assignee is same as previous, no invalidation + no new edge (idempotent); if changed, old edge `invalid_at` set + new edge created.

## 7. Observability

JSON log events:

```
{"event":"ingest.start","source":"paperclip","run_id":"...","group_id":"project/gimle"}
{"event":"ingest.embedder.probe","base_url_host":"ollama-host.example.com","model":"nomic-embed-text","reachable":true}
{"event":"ingest.upsert","type":"Agent","count":12,"inserted":0,"re_embedded":0,"skipped_unchanged":12,"duration_ms":200}
{"event":"ingest.upsert","type":"Issue","count":31,"inserted":0,"re_embedded":5,"skipped_unchanged":26,"duration_ms":1200}
{"event":"ingest.assignment.invalidate","issue_key":"GIM-44","old_edge_uuid":"...","new_target_uuid":"...","duration_ms":50}
{"event":"ingest.edge","type":"ON","count":52,"duration_ms":300}
{"event":"ingest.gc","candidates":0,"deleted":0}
{"event":"ingest.finish","duration_ms":1800,"errors":[],"run_id":"..."}
```

## 8. Decomposition (plan-first ready)

Expected plan-file: `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1a-substrate.md`.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create GIM-NN issue + plan file. Reassign to CodeReviewer. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance; API claims cross-checked against `graphiti-core-verification.md` §5-6. APPROVE → Phase 2. |
| 2 | 2.1 | MCPEngineer | Close 4 mini-gaps from §10 via local poke; append findings to verification doc. |
| 2 | 2.2 | MCPEngineer | Add `graphiti-core` dependency to `services/palace-mcp/pyproject.toml`; init `Graphiti(...)` instance per-process in palace-mcp + ingest module. |
| 2 | 2.3 | MCPEngineer | Rewrite `palace_mcp/ingest/*` — EntityNode/EntityEdge builders, `upsert_with_change_detection`, `invalidate_stale_assignments`, `gc_orphans` (all via graphiti namespace API). |
| 2 | 2.4 | MCPEngineer | Rewrite `palace_mcp/memory/lookup.py` — `graphiti.nodes.entity.get_by_group_ids(["project/gimle"])` + Python-level filter; preserve response envelope. |
| 2 | 2.5 | MCPEngineer | Extend `palace_mcp/memory/health.py` with embedder probe + graphiti init check. |
| 2 | 2.6 | MCPEngineer | `:IngestRun` writer; namespace-scoped. |
| 2 | 2.7 | MCPEngineer | Unit tests — ingest builders, change-detection, ASSIGNED_TO invalidation (bi-temporal), GC orphan filter logic, lookup backward-compat (≥40 new tests). |
| 3 | 3.1 | CodeReviewer | PR mechanical review: compliance, plan-first, **no raw Cypher anywhere** (including GC — spec forbids it now), mypy --strict, API cross-check against verification doc §5. |
| 3 | 3.2 | OpusArchitectReviewer | (If wired) context7 docs-first adversarial pass. Advisory unless CRITICAL. |
| 4 | 4.1 | QAEngineer | Live smoke: compose up with `EMBEDDING_BASE_URL` pointed at user's external Ollama; run ingest CLI; verify same N+0 behavior in `lookup`; verify `invalid_at` set on ASSIGNED_TO when assignee changed between two consecutive ingests (manual paperclip flip + re-ingest). |
| 4 | 4.2 | MCPEngineer | Squash-merge. Update plan-file. Manual iMac deploy (automation lands in N+1c). |

## 9. Acceptance criteria

- [ ] PR against develop; squash-merged on APPROVE.
- [ ] Plan file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1a-substrate.md`.
- [ ] 4 mini-gap verification appendix committed to `graphiti-core-verification.md`.
- [ ] **Zero raw Cypher** in `services/palace-mcp/src/palace_mcp/ingest/**` and `services/palace-mcp/src/palace_mcp/memory/lookup.py` (grep-verifiable).
- [ ] graphiti-core Python dependency added; palace-mcp compose service brings up with `EMBEDDING_BASE_URL` env; embedder probe passes at startup.
- [ ] Ingest CLI runs against live paperclip; produces `:Issue:Entity`, `:Comment:Entity`, `:Agent:Entity`, `:IngestRun:Entity` nodes in group_id `project/gimle`.
- [ ] `text_hash` attribute present on Issue/Comment; re-running ingest reports `skipped_unchanged: N` in logs when text didn't change.
- [ ] **Bi-temporal smoke:** manually reassign one issue in paperclip, re-run ingest, verify via `palace.memory.lookup` (or direct Cypher read-only inspection) that the prior `ASSIGNED_TO` edge has non-null `invalid_at` matching prior run's `started_at`.
- [ ] `palace.memory.lookup(entity_type="Issue", filters={"status":"done"})` returns same issue set as N+0 — byte-for-byte response comparison via captured fixture.
- [ ] `palace.memory.health()` response includes `graphiti_initialized`, `embedder_reachable`, `embedding_model`.
- [ ] `uv run mypy --strict` green.
- [ ] CI green on all four jobs.
- [ ] Post-merge: manual iMac deploy; external Claude Code verifies lookup/health unchanged.

## 10. Mini-gaps to resolve in step 2.1

1. **Skip-embed-on-unchanged idiom.** `graphiti.nodes.entity.save(node)` always embeds. Confirm whether setting `node.name_embedding` manually from `existing.name_embedding` before save bypasses re-embed, OR whether `save_without_embedding` helper exists, OR custom path needed.
2. **`EntityNode.attributes` round-trip.** Verify arbitrary dict keys (text_hash, status, etc.) persist via `save` and return intact via `get_by_uuid`.
3. **`Graphiti(llm_client=OpenAIGenericClient(...))` with LLM never invoked** — confirm no side effects on init or embed-only operation.
4. **graphiti-core ↔ Neo4j 5.26 compatibility.** Currently using 5.26 in N+0 compose; confirm graphiti-core supports.

Resolutions appended to `graphiti-core-verification.md` as §8 (new section).

## 11. Out of scope

- Multi-project scoping (N+1b).
- Agent-facing MCP surface on :8002 + record_note + search (N+1c).
- Ollama compose service — external URL only in N+1a; local compose (profile `with-local-ollama`) lands in N+1c.
- LLM extraction via `add_episode` — bypassed; lands in N+5+ per research roadmap.
- Bi-temporal exercise beyond ASSIGNED_TO — substrate supports all edges; only ASSIGNED_TO triggered in N+1a data flow.
- SCIP-alignment on `:Symbol` — no `:Symbol` nodes exist in N+1a.
- Installer prompt — env-only in N+1a.
- Post-merge deploy automation (N+1c).
- OpusArchitectReviewer wiring (GIM-30).

## 12. Estimated size

- Code: ~350 LOC (ingest rewrite ~150, lookup rewrite ~60, health ext ~30, IngestRun writer ~20, tests ~90).
- Plan + docs: ~60 LOC.
- 1 PR, 4-5 handoffs.
- Duration: 3 days agent-time.

## 13. Followups

- N+1b starts immediately after merge.
- Mini-gap resolutions become verification-doc §8.
- If skip-embed-on-unchanged requires custom graphiti-core patch → upstream PR or local monkey-patch (document choice in mini-gap resolution).
