---
name: graphiti-core 0.28.2 verified API surface
description: Real public API of graphiti-core 0.28.2, captured 2026-04-24 via pip install + inspect in isolated venv. Supersedes reference_graphiti_core_api_truth.md (0.4.3).
type: reference
originSessionId: 4000a9ae-7527-4813-aa5b-a3544c3ec842
---
Verified against `graphiti-core==0.28.2` on 2026-04-24 via `inspect.signature`
and `dir()` against a fresh `uv venv` install.

**Supersedes:** `reference_graphiti_core_api_truth.md` (0.4.3, 2026-04-18). Old
APIs not documented here are either gone or meaningfully changed.

## Constructor

```python
Graphiti(
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
    llm_client: LLMClient | None = None,      # default OpenAI if None — requires OPENAI_API_KEY
    embedder: EmbedderClient | None = None,   # default OpenAI if None — requires OPENAI_API_KEY
    cross_encoder: CrossEncoderClient | None = None,  # default OpenAI — same
    store_raw_episode_content: bool = True,
    graph_driver: GraphDriver | None = None,
    max_coroutines: int | None = None,
    tracer: Tracer | None = None,
    trace_span_prefix: str = "graphiti",
)
```

**Trap:** All three client args have `None` default in signature but fall through to OpenAI implementations — constructor raises `OpenAIError: api_key must be set` if `OPENAI_API_KEY` missing. **You cannot "just pass None" to disable LLM.**

**Workarounds to run without live LLM calls:**
1. Pass `OpenAIClient(api_key=<real-or-dummy>)` as stub. If you only use `add_triplet` (structured write) and `search` (index-based), no LLM call is ever made — dummy key works for pure-write workloads.
2. Implement `NoopLLMClient(LLMClient)` subclass raising on any method call — safer if you want an explicit tripwire.

For Gimle's scope (structured writes via `add_triplet`, search via `search(...)` without cross-encoder reranker), option 1 with real key is fine.

## Graphiti public methods (all async)

- `add_triplet(source_node, edge, target_node) -> AddTripletResults` — **structured write, no LLM extraction**. Canonical path for projected facts.
- `add_episode(name, episode_body, source_description, reference_time, ..., entity_types, edge_types, ...)` — **LLM-driven extraction**. Accepts `entity_types: dict[str, type[BaseModel]]` and `edge_types: dict[str, type[BaseModel]]` for custom-type steering. Not used in N+1a.
- `add_episode_bulk(...)` — batch LLM ingest.
- `search(query, center_node_uuid, group_ids, num_results=10, search_filter, driver) -> list[EntityEdge]` — hybrid index search **without LLM or cross-encoder**. Returns edges only.
- `search_(query, config: SearchConfig, ...)` — advanced. **Default `SearchConfig` uses `cross_encoder` reranker** — requires configured CrossEncoderClient. Use `search()` unless reranker is wired.
- `retrieve_episodes(reference_time, last_n, group_ids, source, driver, saga)`
- `get_nodes_and_edges_by_episode(...)`
- `remove_episode(...)`
- `build_communities(group_ids, driver) -> tuple[list[CommunityNode], list[CommunityEdge]]` — Louvain-based; requires LLM (community summaries).
- `build_indices_and_constraints(delete_existing=False)` — idempotent bootstrap. Call on startup.
- `close()` — always await on shutdown.

## No namespaced managers

`.nodes`, `.edges`, `.episodes`, `.communities` — **do not exist**. Same absence as 0.4.3. `node.save(driver)` / `edge.save(driver)` are instance methods on EntityNode / EntityEdge themselves.

## EntityNode fields

```python
class EntityNode(BaseModel):
    uuid: str              # auto-generated if absent
    name: str              # REQUIRED
    group_id: str          # REQUIRED
    labels: list[str]      # multi-label support; empty list default
    created_at: datetime   # auto now
    name_embedding: list[float] | None
    summary: str           # free-text summary
    attributes: dict[str, Any]   # *** NEW in 0.28 vs 0.4.3 ***
```

**Key change from 0.4.3:** `attributes: dict` is now a first-class field. You can stuff arbitrary per-node metadata (confidence, provenance, extractor, observed_at, cm_id) **without subclassing or label-abuse**. This is the single biggest schema-design win of 0.28 over 0.4.

`save(driver)` — async method, persists to Neo4j.

## EntityEdge fields

```python
class EntityEdge(BaseModel):
    uuid: str
    group_id: str                  # REQUIRED
    source_node_uuid: str          # REQUIRED
    target_node_uuid: str          # REQUIRED
    created_at: datetime           # REQUIRED — transaction time
    name: str                      # REQUIRED — edge type/relation name
    fact: str                      # REQUIRED — NL description of the fact
    fact_embedding: list[float] | None
    episodes: list[str]            # episode UUIDs that introduced this edge
    expired_at: datetime | None    # when the edge was superseded
    valid_at: datetime | None      # world-time start of validity
    invalid_at: datetime | None    # world-time end of validity
    attributes: dict[str, Any]     # arbitrary metadata (same as EntityNode)
```

**Bi-temporal is native** via `valid_at` + `invalid_at` (world time) plus `created_at` + `expired_at` (transaction time).

`save(driver)` — async.

## EpisodicNode fields

```python
class EpisodicNode(BaseModel):
    uuid: str
    name: str
    group_id: str
    labels: list[str]
    created_at: datetime
    source: EpisodeType            # message | json | text
    source_description: str
    content: str
    valid_at: datetime
    entity_edges: list[str]        # edge UUIDs touched in this episode
```

Use `source=EpisodeType.json` + structured `content` when recording events like heartbeats or git pushes.

## CommunityNode fields

```python
class CommunityNode(BaseModel):
    uuid: str
    name: str
    group_id: str
    labels: list[str]
    created_at: datetime
    name_embedding: list[float] | None
    summary: str
```

Populated by `build_communities()` (needs LLM). For N+1a we don't build Graphiti communities — we project Codebase-Memory's Louvain output as generic `EntityNode` with label `ArchitectureCommunity`.

## What's NOT available

- `g.nodes.entity.get_by_group_ids(...)` — still missing (same as 0.4.3)
- `g.edges.entity.save(edge)` — still missing
- Any namespaced manager — still no

## Integration test pattern

From the 2026-04-18 lesson (N+1a revert): **never rely on memory of Graphiti
API shape without live import**. Re-run this spike before every graphiti-core
version bump.

## Related

- `project_backlog.md` — GIM-52 redesign used this reference (for 0.4.3).
- `feedback_qa_skipped_gim48.md` — incident that drove the first API-truth doc.
- N+1a.1 spec (to be written): `docs/superpowers/specs/2026-04-24-N1a-1-graphiti-foundation-design.md`.
