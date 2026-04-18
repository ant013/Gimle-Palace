# graphiti-core API verification spike

**Date:** 2026-04-18
**Purpose:** Verify 8 API claims from REJECTED N+1 spec (`docs/superpowers/specs/2026-04-18-palace-memory-n1-graphiti-substrate.md`) before writing replacement atomic specs (N+1a/b/c).
**Source:** context7 MCP server (`/getzep/graphiti`, source reputation High, benchmark 81.1, 221 code snippets) — pulled directly from getzep/graphiti repo + llms.txt.
**Outcome:** All 5 critical hallucinations confirmed. 3 bonus findings unlock cleaner design.

## 1. Claim-by-claim verification

### ❌ Claim 1: `g.compute_embeddings_for(node_labels, text_fields, group_id)`

**Status:** Method does not exist.

**Reality:** Embeddings are auto-generated on `EntityNode.save()`:

```python
class EntityNodeNamespace:
    async def save(self, node: EntityNode, tx: Transaction | None = None) -> EntityNode:
        await node.generate_name_embedding(self._embedder)   # auto-embed BEFORE save
        await self._ops.save(self._driver, node, tx=tx)
        return node
```

Bulk path: `save_bulk(nodes, batch_size=100)`. For loading existing embeddings into nodes already in DB: `load_embeddings(node)` / `load_embeddings_bulk(nodes, batch_size=100)`.

**Implication for spec:** §7.2 ingest pipeline phase 4 must be rewritten — no separate embed step. Embedder is configured on the `Graphiti(...)` constructor; every `add_triplet`/`save` call generates embeddings transparently.

### ❌ Claim 2: bi-temporal fields `valid_from` / `valid_to`

**Status:** Wrong names. There are **three** temporal fields, not two.

**Reality (verified in EntityEdge JSON dumps):**

```python
{
  "uuid": "1055fb8279af4c4c8c3fb78350d610d0",
  "source_node_uuid": "...", "target_node_uuid": "...",
  "created_at": datetime(2024, 8, 31, 11, 37, 39),    # when edge written to DB
  "name": "CAUSES_DISCOMFORT",
  "fact": "John's wide feet cause discomfort with the Men's Couriers shoes",
  "episodes": ["..."],
  "valid_at": datetime(2024, 8, 20, 0, 1, tzinfo=UTC),   # when fact became valid (per content)
  "invalid_at": None,                                     # when fact became invalid (per content)
  "expired_at": None                                      # when graphiti detected contradiction
}
```

- `valid_at` — start of fact validity (extracted from text, e.g., "since August 20").
- `invalid_at` — end of fact validity (e.g., "out of stock until December 25" → `invalid_at=2024-12-25`).
- `expired_at` — set automatically when graphiti's contradiction-detection invalidates the fact (separate from content-derived `invalid_at`).
- `created_at` — DB write timestamp.

**Implication for spec:** §4.4, §4.5, §11 acceptance criteria all need rewrite. Substrate must use `valid_at` / `invalid_at` / `expired_at`. Note: graphiti-core handles temporal lifecycle automatically when edges are written via `add_triplet` or `add_episode`; manual `expired_at` writes are rare (it's the contradiction-detection output).

### ❌ Claim 3: `add_episode(name="note-<uuid>", ...)` creates `:Note` label, applies tags

**Status:** Wrong. `add_episode` triggers LLM extraction into `:Entity` (or `:Speaker`, etc.), not arbitrary user-controlled labels.

**Reality:** `add_episode` is the LLM-extraction path:

```python
result = await graphiti.add_episode(
    name="Purchase Record",
    episode_body="John (Gold member) purchased the Premium Headphones for $299...",
    source_description="Sales system",
    source=EpisodeType.text,
    reference_time=datetime.now(timezone.utc),
    entity_types={"Product": Product, "Customer": Customer},  # Pydantic models for typed extraction
)
# result.nodes are :Entity + custom-typed (Product, Customer) entities
# extracted by LLM from episode_body — NOT arbitrary user labels
```

Even with `entity_types`, the labels come from Pydantic class names (`Product`, `Customer`), not free-form. The episode itself becomes an `:EpisodicNode`; entities extracted from it become `:Entity` + Pydantic-typed labels.

**Correct path for typed `:Note` writes (bypassing LLM):**

```python
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

note_node = EntityNode(
    name="note-<uuid>",
    group_id="project/gimle",
    labels=["Note", "Entity"],   # custom labels supported
    summary="Coordinator pattern used in Gimle bootstrap"
)

# To attach to a project:
edge = EntityEdge(
    source_node_uuid=note_node.uuid,
    target_node_uuid=project_node.uuid,
    name="BELONGS_TO",
    fact="note belongs to project gimle",
    group_id="project/gimle",
    created_at=datetime.now(timezone.utc),
    valid_at=datetime.now(timezone.utc),
)

result = await graphiti.add_triplet(note_node, edge, project_node)
```

**Implication for spec:** §5.2 `record_note` and §7.2 ingest must use `add_triplet` with pre-built `EntityNode(labels=["Note", "Entity"], ...)`. Tags become a `summary` field or custom node attribute via Pydantic typed extraction. §11 acceptance smoke test as written would not find a `:Note` — it would find an LLM-extracted `:Entity` with arbitrary name.

### ❌ Claim 4: MCP tool names `search_memory_nodes` / `search_memory_facts`

**Status:** Wrong. Actual MCP tool names are `search_nodes` and `search_facts`.

**Reality (from `mcp_server/docs/cursor_rules.md` in getzep/graphiti):**

> Use the `search_nodes` tool to find existing preferences and procedures related to your task. Additionally, employ the `search_facts` tool to uncover any factual information or relationships that might be pertinent.

Python abstract API has different (lower-level) names:

```python
class SearchOperations(ABC):
    async def node_fulltext_search(self, executor, query, search_filter, group_ids=None, limit=10) -> list[EntityNode]
    async def node_similarity_search(self, executor, search_vector, search_filter, group_ids=None, limit=10, min_score=0.6) -> list[EntityNode]
    async def node_bfs_search(self, executor, origin_uuids, search_filter, max_depth, group_ids=None, limit=10) -> list[EntityNode]
```

REST endpoint: `POST /search` returns facts (with `query`, `group_ids: list[str]`, `max_facts` body fields).

**Implication for spec:** §8 (graphiti-mcp surface for paperclip agents) and shared-fragments `palace-memory-mcp.md` must use `search_nodes` / `search_facts`. Acceptance §11 smoke test referencing `search_memory_nodes` would fail.

### ❌ Claim 5: Native LiteLLM router integration in graphiti-core

**Status:** No. graphiti-core uses its own `OpenAIGenericClient` + `OpenAIEmbedder` which already cover every OpenAI-compatible endpoint via `base_url`.

**Reality (verified — same pattern works for Ollama, Alibaba DashScope, OpenAI, Voyage AI, Azure):**

```python
# Ollama (local or external)
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

llm_config = LLMConfig(api_key="ollama", model="llama3:8b",
                       base_url="http://your-ollama-host:11434/v1")
llm_client = OpenAIGenericClient(config=llm_config)

embedder = OpenAIEmbedder(config=OpenAIEmbedderConfig(
    api_key="ollama",
    embedding_model="nomic-embed-text",
    embedding_dim=768,
    base_url="http://your-ollama-host:11434/v1"
))

graphiti = Graphiti("bolt://...", "neo4j", "password",
                    llm_client=llm_client, embedder=embedder)
```

For Alibaba DashScope: change `base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"`, `api_key=$DASHSCOPE_KEY`, `embedding_model="text-embedding-v3"`. For OpenAI: omit base_url (defaults to api.openai.com), `api_key=$OPENAI_KEY`, `embedding_model="text-embedding-3-small"`.

Azure has its own client (`AzureOpenAILLMClient` / `AzureOpenAIEmbedderClient`) using `AsyncOpenAI` from `openai` package — different but native.

**Implication for spec:** **Drop LiteLLM dependency entirely** from §6. graphiti-core's `OpenAIGenericClient` IS the provider abstraction. Configuration is 4 env vars: `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`. Same for LLM (when extraction needed in N+5+): `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. No router layer.

## 2. Bonus findings (unlock cleaner design)

### ✅ `EntityNode(labels: list[str])` — first-class custom labels

Confirmed:

```python
EntityNode(name="GPT-4", group_id="tech-companies",
           labels=["Product", "AI Model"],   # multiple custom labels alongside default :Entity
           summary="Large language model")
```

Means `:Note`, `:Issue`, `:Comment`, `:Agent`, `:Project` all achievable via `labels=[...]` parameter. No need for hacks.

### ✅ `get_by_group_ids(group_ids: list[str])` — multi-project query first-class

Native API supports `list[str]` for group_ids — `project: list | "*"` semantics in palace-mcp tools maps directly. `"*"` translates to "fetch all distinct group_ids first, pass list" (one extra query, acceptable).

### ✅ `delete_by_group_id(group_id)` — namespace-scoped delete

Useful for `palace.memory.purge_project(slug)` admin tool (not in N+1 scope, but trivial future addition).

### ⚠️ `Graphiti(llm_client=None, ...)` — embedding-only mode

**Not explicitly verified.** docs suggest llm_client + embedder + cross_encoder are all required constructor args. For pure embedding-only mode (record_note + structured ingest, no LLM extraction), need to either:
- (a) verify via local poke that `llm_client=None` is supported
- (b) instantiate `OpenAIGenericClient` against the same Ollama endpoint as embedder, never call `add_episode` (only `add_triplet`) → llm_client stays connected but unused
- (c) wait for graphiti-core 0.4+ which may add explicit embed-only mode

**Recommend (b)** for first implementation slice — costs nothing if `add_episode` is never called.

## 3. Replacement design implications

### Storage schema (replaces §4.4 of REJECTED spec)

```python
# Project
EntityNode(
    name="gimle",
    labels=["Project", "Entity"],
    group_id="project/gimle",
    summary="Gimle bootstrap project — ...",
    attributes={"slug": "gimle", "tags": ["mobile", "python", "agent-framework"], ...}
)

# Issue (rewrite of N+0 :Issue)
EntityNode(
    name=f"{issue.key}: {issue.title}",
    labels=["Issue", "Entity"],
    group_id="project/gimle",
    summary=issue.description[:500],
    attributes={
        "id": issue.id, "key": issue.key, "title": issue.title,
        "description": issue.description, "status": issue.status,
        "source": "paperclip",
        "source_created_at": issue.created_at, "source_updated_at": issue.updated_at,
        "palace_last_seen_at": run_started, "text_hash": sha256(issue.description),
    }
)

# Note (record_note write tool)
EntityNode(
    name=f"note-{uuid4()}",
    labels=["Note", "Entity"],
    group_id="project/gimle",
    summary=text[:500],
    attributes={
        "text": text, "tags": tags, "scope": scope,
        "author_kind": author_kind, "author_id": author_id,
        "source_created_at": now_iso(), "palace_last_seen_at": now_iso(),
    }
)
```

Project association is via `group_id` (Graphiti namespace) — **no `:BELONGS_TO_PROJECT` edge needed.** Per-project queries use `get_by_group_ids(["project/gimle"])`. Cross-project: `get_by_group_ids(["project/gimle", "project/medic"])`. All projects: enumerate via `get_distinct_group_ids()` then list-query.

### Tool surface (replaces §5 of REJECTED spec — narrower)

Only register tools that **work in N+1c** (after substrate + multi-project + agent-mcp slices land):

| Tool | Path | N+1 status |
|---|---|---|
| `palace.health.status` | (N+0 carryover, GIM-23) | already shipped |
| `palace.memory.lookup` | (N+0 carryover, GIM-34) | preserved + accepts `project` param |
| `palace.memory.health` | (N+0 carryover, GIM-34) | preserved + extends with graphiti/embedder reachability |
| `palace.memory.search` | NEW | semantic via `node_similarity_search` over `:Issue`/`:Comment`/`:Note` |
| `palace.memory.list_projects` | NEW | enumerate distinct group_ids + lookup `:Project` nodes |
| `palace.memory.get_project_overview` | NEW | counts + last-ingest summary per project |
| `palace.memory.record_note` | NEW | `add_triplet` with `EntityNode(labels=["Note", "Entity"])` |
| `palace.memory.get_iteration_notes` | NEW | filter `:Note` by tags/scope |
| `palace.memory.link_items` | NEW (whitelisted relations) | `add_triplet` with `:RELATES_TO` / `:SIMILAR_TO` / `:SEE_ALSO` edge |

**9 tools total in N+1.** All other 16 tools from spec §4.3 deferred to slices N+2…N+6 — registered when their data sources land.

### Provider abstraction (replaces §6 of REJECTED spec)

Drop LiteLLM. Single env-block configuration covers all OpenAI-compat endpoints:

```bash
# Default: external Ollama (your hosted instance)
EMBEDDING_BASE_URL=http://your-ollama-host:11434/v1
EMBEDDING_API_KEY=ollama   # placeholder; Ollama ignores
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768

# Alternative: Alibaba DashScope (free tier 1M tokens/month)
EMBEDDING_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024

# Alternative: OpenAI direct
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

# LLM client (required for graphiti-core constructor; unused in N+1 since add_triplet only)
LLM_BASE_URL=${EMBEDDING_BASE_URL}   # same endpoint
LLM_API_KEY=${EMBEDDING_API_KEY}
LLM_MODEL=llama3:8b   # placeholder; not invoked
```

Installer prompt (`just setup`) chooses preset; advanced users override individual env vars.

**No Ollama compose service in N+1 by default.** External Ollama URL is the primary path (per user clarification). Local Ollama compose is opt-in profile `with-local-ollama` (renamed for clarity), only activated when user explicitly wants it.

### Embed change-detection (point #12 from review)

```python
new_text_hash = sha256(text).hexdigest()
existing_node = await graphiti.get_node(uuid)
if existing_node.attributes.get("text_hash") == new_text_hash:
    skip_embed = True   # save without re-embed
else:
    await node.generate_name_embedding(embedder)
    node.attributes["text_hash"] = new_text_hash
```

Wraps the auto-embed path; only embeds when text changed.

## 4. Open verification gaps (small)

These need a 30-min local poke before N+1c implementation:

1. Confirm `Graphiti(llm_client=None, ...)` works OR confirm path (b) — instantiate llm_client but never call add_episode — does not error on Graphiti init.
2. Confirm `EntityNode.attributes` (custom dict) survives DB round-trip with arbitrary keys (text_hash, tags list, scope, etc.).
3. Confirm `node_similarity_search` accepts `min_score` parameter and returns `EntityNode` with similarity score (or compute distance separately).
4. Confirm graphiti-core supports Neo4j 5.26 (we ship that in N+0).

These are implementation-time concerns, not spec blockers. MCPEngineer validates during 2.1 of plan-file.

## 5. Conclusion

All 5 critical claims from the REJECTED spec are confirmed wrong. graphiti-core's actual API is **simpler and more elegant** than what the REJECTED spec assumed:

- `add_triplet` + custom-labeled `EntityNode` cleanly bypasses LLM extraction
- `OpenAIGenericClient` + `OpenAIEmbedder` natively cover all OpenAI-compat providers — no LiteLLM
- `group_id` is THE namespace mechanism — no parallel edge layer
- `valid_at`/`invalid_at`/`expired_at` triple is mature and battle-tested

Replacement specs (N+1a/b/c) can now be written with confidence. The REJECTED spec preserves as historical artifact + cautionary tale for GIM-30 priority.
