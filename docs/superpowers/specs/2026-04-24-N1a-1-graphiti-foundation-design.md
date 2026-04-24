---
slug: N1a-1-graphiti-foundation
status: proposed (rev2 after CR Phase 1.2 REQUEST CHANGES 2026-04-24)
branch: feature/GIM-75-graphiti-foundation
paperclip_issue: 75 (0855b069-3e42-4cc8-b644-6dec26660111)
parent_umbrella: 74
predecessor: 766629d (develop tip after umbrella merge)
date: 2026-04-24
revisions:
  - rev1 2026-04-24 — initial (merged as part of umbrella PR #36, `766629d`).
  - rev2 2026-04-24 — CR Phase 1.2 REQUEST CHANGES addressed:
      - CRITICAL-1: `openai_api_key` added to `Settings` + `.env.example`.
      - CRITICAL-2: `palace.memory.lookup` adaptation pinned down — filters.py/schema.py EntityType literal replaced, `_RELATED_FRAGMENTS` emptied for N+1a, Cypher adapted to Graphiti labels + attributes.
      - CRITICAL-3: `palace.memory.health` adaptation pinned down — ENTITY_COUNTS label list updated, LATEST_INGEST_RUN source filter generalized, HealthResponse keys renamed.
      - WARNING-1: runner dual-dependency (graphiti + driver for `:IngestRun` writes) explicit.
      - WARNING-2: `:Project` node stores slug in `name` field so `(p:Project {name: $slug})` works.
      - WARNING-3: unbounded Episode growth explicitly documented as known limitation.
      - WARNING-4: §6 "Tests" section renumbered consistently.
      - WARNING-5: frontmatter predecessor updated.
---

# N+1a.1 — Graphiti foundation (storage swap only)

## 1. Context and scope boundary

This slice embeds `graphiti-core==0.28.2` inside `palace-mcp` as the product/process memory layer. It replaces the raw-Neo4j driver path used by the N+0 test extractor with a Graphiti-mediated path, defines the Pydantic entity/edge catalog, and proves the pipeline end-to-end with the refactored `heartbeat` extractor writing one `:Episode` per tick.

**Explicitly out of scope (other sub-slices or later work):**

- Codebase-Memory sidecar — **GIM-76**.
- Bridge extractor — **GIM-77**.
- `semantic_search` MCP tool — later followup (N+1b).
- `git_events_extractor` — later followup (N+1c).
- Domain-concept taxonomy loader — later.
- UI / APIEndpoint / Model rich extractors — N+2+.

## 2. Problem

After the 2026-04-18 N+1a revert, `graphiti-core` is no longer in `palace-mcp` deps. The only extractor is a disposable paperclip-issue probe writing `:Issue/:Comment/:Agent` to raw Neo4j. Before anything else can be built on top of Graphiti (bridge, semantic_search, etc.), the runtime contract needs to be wired against the *current* 0.28.2 API — not the 0.4.3 API we reverted from.

## 3. Solution — one new foundation layer inside palace-mcp

### 3.1 Dependency + config

Add to `services/palace-mcp/pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "graphiti-core==0.28.2",
]
```

Pin exact patch. **Do not rely on `~=0.28` or `>=0.28` — 0.28.x history shows breaking changes between minor patches.**

**Add to `services/palace-mcp/src/palace_mcp/config.py` (addresses CR CRITICAL-1):**

```python
class Settings(BaseSettings):
    # ... existing fields ...
    openai_api_key: SecretStr    # NEW — required by graphiti-core 0.28 for
                                 # constructor (even though add_triplet does
                                 # not call LLM on the hot path).
```

**Add to `.env.example`:**

```
# Graphiti: used by graphiti-core 0.28 constructor (LLM/embedder stubs).
# Writes go via add_triplet — LLM is never invoked, but constructor requires
# a valid client, so the key must be present. Embedder (text-embedding-3-small)
# IS invoked on EntityNode.save for name_embedding.
OPENAI_API_KEY=sk-...
```

### 3.2 Factory and bootstrap

```python
# services/palace-mcp/src/palace_mcp/graphiti_runtime.py

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

def build_graphiti(settings: Settings) -> Graphiti:
    """Construct Graphiti wired to the existing palace-mcp Neo4j container.

    graphiti-core 0.28.2 trap: llm_client=None at constructor still spawns
    a default OpenAI client, which raises if OPENAI_API_KEY is absent. We
    pass an explicit OpenAIClient stub; writes go through add_triplet which
    does not invoke LLM, so the stub is never called on the hot path.
    """
    llm_stub = OpenAIClient(config=LLMConfig(api_key=settings.openai_api_key))
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=settings.openai_api_key,
            embedding_model="text-embedding-3-small",
        )
    )
    return Graphiti(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        llm_client=llm_stub,
        embedder=embedder,
        cross_encoder=None,   # we use search(), not search_()
    )

async def ensure_graphiti_schema(g: Graphiti) -> None:
    """Idempotent bootstrap. Safe to call on every startup."""
    await g.build_indices_and_constraints(delete_existing=False)

# --- Public helpers — extractors MUST use these, never g._driver directly ---

async def save_entity_node(g: Graphiti, node: EntityNode) -> None:
    """Persist an EntityNode. Encapsulates driver access so extractors
    never touch g._driver."""
    await node.save(g._driver)  # _driver is library-internal; helper is the stable contract

async def save_entity_edge(g: Graphiti, edge: EntityEdge) -> None:
    """Persist an EntityEdge."""
    await edge.save(g._driver)

async def close_graphiti(g: Graphiti) -> None:
    """Shutdown helper. Always await."""
    await g.close()
```

Wire `build_graphiti()` into the palace-mcp lifespan startup. Hold a module-level singleton (same pattern as the existing Neo4j driver). Ensure `close_graphiti(g)` runs on shutdown.

**Public API contract (load-bearing for GIM-77):** `save_entity_node`, `save_entity_edge`, `close_graphiti`, `ensure_graphiti_schema` are the stable interface. Direct `g._driver` access is reserved for this module. Extractor code that touches `g._driver` fails review.

### 3.3 Pydantic entity catalog

**Flat schema.** `:Symbol{kind=...}` instead of `:Function`, `:Class`, `:Method`, etc. Rationale: avoid schema drift between CM (full detail) and Graphiti (summaries), keep Graphiti surface compact.

Entity catalog (in `services/palace-mcp/src/palace_mcp/graphiti_schema/entities.py`):

| Graphiti label | Purpose | Required attrs (in `attributes` dict) |
|---|---|---|
| `Project` | Root scope entity | `slug`, `name`, `language?`, `framework?`, `repo_url?` |
| `Iteration` | Ingest run / milestone | `number`, `kind` (`full`\|`incremental`), `from_sha?`, `to_sha?`, `commit_count?` |
| `Episode` | First-class event (ingest tick, heartbeat, git push, agent decision) | `kind` (`heartbeat`\|`git_push`\|`extractor_run`\|...), `source` (extractor name) |
| `Decision` | ADR-style architectural decision | `text`, `scope?`, `tags?`, `author?`, `decided_at?`, `status` |
| `IterationNote` | Free-form note scoped to an iteration | `iteration_ref`, `text`, `tags?` |
| `Finding` | Reviewer-produced finding | `severity`, `category`, `text`, `file_ref?`, `line?`, `reviewer?`, `source` (`static`\|`llm`\|`hybrid`) |
| `Module` | Projected later by bridge (GIM-77); schema class exists now | `path?`, `kind?` |
| `File` | Projected later | `path`, `hash?`, `loc?`, `cm_id?` |
| `Symbol` | Projected later | `kind` (`function`\|`method`\|`class`\|`interface`\|`enum`\|`type`), `name`, `file_path?`, `signature?`, `cm_id?` |
| `APIEndpoint` | Projected later | `method`, `path`, `handler_cm_id?` |
| `Model` | Domain data-model entity | `fields?`, `db_table?` |
| `Repository` | Data-access layer entity | `entity_ref?`, `storage_kind?` |
| `ExternalLib` | Third-party dep | `version?`, `category?` |
| `Trace` | Paperclip-agent reasoning chain (populated by followup slices) | `agent_id`, `task_ref?`, `outcome?`, `started_at?`, `ended_at?` |

**All entities share a metadata envelope in `attributes` dict:**

- `confidence: float ∈ [0, 1]`
- `provenance: "asserted" | "derived" | "inferred"`
- `extractor: str`
- `extractor_version: str`
- `evidence_ref: list[str]`
- `observed_at: ISO-8601 datetime string`
- Plus whatever entity-specific keys are listed above.

**Rule:** `attributes["confidence"]` is required on every write; `attributes["provenance"]` is required. Absence → extractor bug.

**Not implemented in this slice:** `:Commit`, `:PR`, `:Owner`, `:Hotspot`, `:TestCase`, `:BuildRun`, `:Contract`, `:ArchitectureCommunity` — these are declared in the Pydantic catalog (so GIM-77 can write them immediately) but **not populated** by any extractor in GIM-75. Pydantic classes + factory functions ship in this slice.

### 3.4 Pydantic edge catalog

Edges in `services/palace-mcp/src/palace_mcp/graphiti_schema/edges.py`. Same `attributes` envelope rules as entities. `EntityEdge` native `valid_at`/`invalid_at`/`expired_at` used for bi-temporal.

Structural (bridge-populated in GIM-77; classes ship here):

- `CONTAINS` (`Project→Module`, `Module→File`)
- `DEFINES` (`File→Symbol`)
- `CALLS` (`Symbol→Symbol`)
- `IMPORTS` (`File→Module`, `File→ExternalLib`)
- `MEMBER_OF` (`Symbol→ArchitectureCommunity`)
- `LOCATES_IN` (`Hotspot→File`)
- `HANDLES` (`APIEndpoint→Symbol`)

Product/process:

- `CONCERNS` (`Decision|Finding|IterationNote → Module|File|Symbol|APIEndpoint`)
- `INFORMED_BY` (`Decision → Finding|IterationNote|Trace`)
- `INVALIDATED_BY` (`Decision → Decision`)
- `APPLIES_TO` (`Decision → Symbol` with target label filter — domain concepts are multi-labels, not nodes)
- `RESOLVES` (`PR → Finding`)
- `TOUCHES` (`Commit|PR → File|Symbol`)
- `MODIFIES` (`Commit → File|Symbol` with `lines_added`/`lines_removed` attrs)
- `INCLUDES` (`PR → Commit`)
- `OWNS` (`Owner → File|Module` with `ownership_fraction`)
- `COVERED_BY` (`Symbol → TestCase`)
- `TRACED_AS` (`Decision → Trace`)
- `HAS_STEP` (`Trace → TraceStep`)

**Populated in this slice:** none from bridge. Only `:Episode` (from heartbeat) — which has **no outgoing edges** — is written in GIM-75. All other edge classes are declared but unused until GIM-77 / later slices. This is intentional and testable (see §7).

### 3.5 BaseExtractor refactor

`services/palace-mcp/src/palace_mcp/extractors/base.py` currently takes `driver: AsyncDriver`. Change signature to:

```python
class BaseExtractor:
    async def run(self, *, graphiti: Graphiti, ctx: ExtractorRunContext) -> ExtractorStats:
        raise NotImplementedError
```

Extractors write via `graphiti.add_triplet(...)` for edges or construct `EntityNode` / `EntityEdge` directly and call `.save(driver)` (the Graphiti-managed driver is exposed via `graphiti._driver` or a public helper we add).

**Existing extractor fallout:** `heartbeat` refactored in §3.6 below. Any other extractor that directly used `driver` — at time of design only `heartbeat` exists — is updated or deleted.

### 3.6 Heartbeat refactor

`services/palace-mcp/src/palace_mcp/extractors/heartbeat.py` currently writes a `:Heartbeat` node to raw Neo4j via `driver.session()`. New implementation:

```python
class HeartbeatExtractor(BaseExtractor):
    name = "heartbeat"
    version = "0.2"

    async def run(self, *, graphiti: Graphiti, ctx: ExtractorRunContext) -> ExtractorStats:
        now = datetime.now(timezone.utc)
        episode = EntityNode(
            name=f"heartbeat-{now.isoformat()}",
            group_id=ctx.group_id,
            labels=["Episode"],
            attributes={
                "kind": "heartbeat",
                "source": "extractor.heartbeat",
                "duration_ms": ctx.duration_ms,
                "confidence": 1.0,
                "provenance": "asserted",
                "extractor": f"heartbeat@{self.version}",
                "extractor_version": self.version,
                "evidence_ref": [],
                "observed_at": now.isoformat(),
            },
        )
        await save_entity_node(graphiti, episode)   # helper, never graphiti._driver
        return ExtractorStats(nodes_written=1, edges_written=0)
```

Heartbeat remains the reference implementation for "how an extractor writes to Graphiti" and the default sanity check in `palace.memory.health`.

### 3.7 `palace.memory.lookup` / `filters.py` / `schema.py` adaptation (addresses CR CRITICAL-2)

Current state (commit `766629d`):

```python
# services/palace-mcp/src/palace_mcp/memory/filters.py
EntityType = Literal["Issue", "Comment", "Agent"]
_WHITELIST: dict[EntityType, dict[str, str]] = { ... }   # Issue/Comment/Agent props

# services/palace-mcp/src/palace_mcp/memory/lookup.py
_RELATED_FRAGMENTS: dict[EntityType, str] = { ... }      # :ASSIGNED_TO, :ON, :AUTHORED_BY Cypher
```

**Rev2 changes — concrete replacements:**

1. **`filters.py` / `schema.py` — `EntityType` literal:**

   ```python
   # Replacement after N+1a:
   EntityType = Literal[
       "Project",
       "Iteration",
       "Episode",
       "Decision",
       "IterationNote",
       "Finding",
       "Module",       # projected later by bridge (GIM-77), classes exist now
       "File",
       "Symbol",
       "APIEndpoint",
       "Model",
       "Repository",
       "ExternalLib",
       "Trace",
       # Declared but no extractor populates in N+1a: Commit, PR, Owner,
       # Hotspot, TestCase, BuildRun, Contract, ArchitectureCommunity.
       # Add them to the literal here when GIM-77 / N+1c land, not earlier,
       # to keep `lookup` filter validation honest.
   ]
   ```

2. **`filters.py` — `_WHITELIST`:** per-type filter whitelist maps to Graphiti properties. Graphiti persists `EntityNode.attributes` values as **flat Neo4j node properties** (verified in spike — see `docs/research/graphiti-core-0-28-spike/README.md` — `attributes` is spread onto the node via `SET n += $attrs` inside graphiti-core's Cypher). So filters work against top-level node props, same shape as before:

   ```python
   _WHITELIST: dict[EntityType, dict[str, str]] = {
       "Episode": {"kind": "kind", "source": "source"},
       "Decision": {"author": "author", "status": "status"},
       "Symbol":   {"kind": "kind", "name": "name", "file_path": "file_path"},
       "File":     {"path": "path", "language": "language"},
       # ... one entry per entity in the literal, starting conservative
       # (a handful of safe filters each) and growing per use case.
   }
   ```

   `group_id`, `uuid`, `name` are always valid filter keys (always present) — handle at the resolver level, not in the per-type whitelist.

3. **`lookup.py` — `_RELATED_FRAGMENTS`:**

   ```python
   _RELATED_FRAGMENTS: dict[EntityType, str] = {}     # EMPTY in N+1a
   ```

   The old "related-entity expansion" idiom (Issue → Comments via `:ON`, Agent → assigned issues via `:ASSIGNED_TO`) is out of scope for the foundation slice. Cross-entity traversals arrive with GIM-77 (bridge edges: `DEFINES`, `CALLS`) and N+1c (`:TOUCHES`/`:MODIFIES`). Keep the dict as-is (empty) and document it in-code.

4. **`lookup.py` main Cypher:** becomes a simple label match — `MATCH (n:{entity_type}) WHERE ... RETURN n`. No related-node collection. Use the `EntityType` string to pick the label dynamically — same pattern as before, minus the related fragment injection.

5. **`schema.py`:** update `EntityType` literal identically (single-source refactor: export once from `filters.py`, import in `schema.py`).

6. **Tests:** `tests/memory/test_lookup.py` and `test_filters.py` — rewrite parametrized cases against the new entity literal. Old `test_lookup_issue_returns_comments` etc. delete.

### 3.8 `palace.memory.health` adaptation (addresses CR CRITICAL-3)

Current state at `services/palace-mcp/src/palace_mcp/memory/health.py:46`:

```python
ingest_result = await tx.run(LATEST_INGEST_RUN, source="paperclip")
```

**Rev2 changes — concrete replacements:**

1. **`LATEST_INGEST_RUN`:** drop the `source` parameter. Return the latest `:IngestRun` across all sources. If the caller wants per-source filtering later, add a second tool (or a parameter) — not in N+1a scope.

   ```cypher
   MATCH (r:IngestRun)
   RETURN r ORDER BY r.started_at DESC LIMIT 1
   ```

2. **`ENTITY_COUNTS`:** the old label list `[:Issue, :Comment, :Agent]` → the new literal from §3.7:

   ```cypher
   UNWIND $labels AS lbl
   CALL { WITH lbl
     CALL apoc.cypher.run('MATCH (n:' + lbl + ') RETURN count(n) AS cnt', {}) YIELD value
     RETURN value.cnt AS cnt
   }
   RETURN lbl AS type, cnt AS count
   ```

   (Same pattern as current. `$labels` becomes the new EntityType set.)

3. **`ENTITY_COUNTS_BY_PROJECT`:** same pattern, grouped by `group_id`.

4. **`HealthResponse`** (pydantic model): expose the new entity set. Keys that previously were `{issues, comments, agents}` become `{episodes, iterations, decisions, findings, files, symbols, modules, api_endpoints, models, repositories, external_libs, traces, projects}`. Drop old keys — no shim, per GIM-74 removal policy.

5. **Tests** in `tests/memory/test_health.py` — rewrite assertions against new response shape.

### 3.9 Runner dual-dependency (addresses CR WARNING-1)

`services/palace-mcp/src/palace_mcp/extractors/runner.py` creates `:IngestRun` + `:Extractor` nodes via direct Cypher (lines ~200). These are palace-mcp's internal ops-log, **not** Graphiti product-layer entities.

**Rev2 decision:** runner keeps direct `driver` access for `:IngestRun` writes. The runner receives **both** `graphiti: Graphiti` (to pass into extractor.run) and `driver: AsyncDriver` (for its own ops log). `ExtractorRunContext` carries only `graphiti`; the driver stays in the runner's own closure.

Rationale: `:IngestRun` is a Neo4j-native ops construct, not a Graphiti-native entity. Forcing it through Graphiti would bring no benefit and would couple our ops log to graphiti-core's internal schema. Reserve that refactor for a followup if `:IngestRun` ever becomes cross-project or temporal.

### 3.10 `:Project` slug query (addresses CR WARNING-2)

`runner.py:77` current query:

```python
GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p"
```

`EntityNode.name` is required and top-level in Graphiti. `attributes` values are persisted as flat Neo4j props (§3.7 point 2), so `{slug: $slug}` would technically work post-write — but relying on that is fragile. **Explicit rule:** `:Project` nodes store `slug` in `EntityNode.name`. So:

```python
GET_PROJECT = "MATCH (p:Project {name: $slug}) RETURN p"
```

The `name` field is guaranteed top-level by Graphiti schema. Update `projects.py` `register_project()` to pass `name=slug` when constructing the Project EntityNode.

### 3.11 Unbounded Episode growth — known limitation (addresses CR WARNING-3)

Heartbeat creates a new `:Episode` per tick. With a 2-minute tick cadence that's ~720 episodes/day/project. In N+1a we do **not** implement GC. Documented limitation; a future "palace retention" slice will add TTL/compaction. Operator may clear manually with Cypher if it ever becomes a problem.

### 3.12 N+0 paperclip extractor removal

Delete (paperclip team has already confirmed — 2026-04-24):

- `services/palace-mcp/src/palace_mcp/ingest/paperclip.py`
- `services/palace-mcp/src/palace_mcp/ingest/paperclip_client.py`
- `services/palace-mcp/src/palace_mcp/ingest/transform.py`
- `services/palace-mcp/src/palace_mcp/ingest/runner.py`
- `services/palace-mcp/src/palace_mcp/ingest/__init__.py` (if empty)
- Any tests referencing these modules.
- Any branches in MCP tools (`palace.memory.lookup`, `palace.memory.health`) that hard-coded `:Issue`/`:Comment` filters.

Handle removal of `:Issue`/`:Comment`/`:Agent` filter support: the tools stay, but filtering by a removed entity type returns `{error: "unknown entity type", warnings: [...]}` — explicit, no silent fallback.

## 4. Tasks

1. Add `graphiti-core==0.28.2` to `services/palace-mcp/pyproject.toml` + `uv lock`.
2. Create `services/palace-mcp/src/palace_mcp/graphiti_runtime.py` with `build_graphiti()`, `ensure_graphiti_schema()`, and public helpers `save_entity_node()`, `save_entity_edge()`, `close_graphiti()`. Helpers are the stable contract — consumed by GIM-77 bridge extractor.
3. Create `services/palace-mcp/src/palace_mcp/graphiti_schema/entities.py` with Pydantic factory functions (not subclasses — 0.28 `EntityNode.attributes` dict is enough) for each entity type in §3.3.
4. Create `services/palace-mcp/src/palace_mcp/graphiti_schema/edges.py` similarly.
5. Wire `build_graphiti()` into palace-mcp FastMCP lifespan startup; wire `await close_graphiti(g)` on shutdown.
6. Refactor `BaseExtractor` in `services/palace-mcp/src/palace_mcp/extractors/base.py`: change signature from `extract(ctx)` to `run(graphiti, ctx)`. Define `ExtractorRunContext` (group_id, duration_ms, config, ...) replacing the old `ExtractionContext(driver=...)`.
7. **Update the extractor runner orchestrator** at `services/palace-mcp/src/palace_mcp/extractors/runner.py`:
   - Lines around 115, 121, 225 currently call `extractor.extract(ctx)` with `ExtractionContext(driver=...)` — replace with `extractor.run(graphiti=<module-level g>, ctx=ExtractorRunContext(group_id=..., ...))`.
   - **Keep `driver` in the runner's own scope** — needed for writing `:IngestRun` + `:Extractor` ops-log nodes (per §3.9). Only product-layer entities flow through Graphiti.
   - `GET_PROJECT` query at line 77 changes from `{slug: $slug}` to `{name: $slug}` (per §3.10 — `:Project` stores slug in `name`).
   - `ExtractionContext` is deleted; `ExtractorRunContext` is the only context class.
   - Verify all imports resolve; update tests in `tests/extractors/*_test.py`.
8. Refactor `HeartbeatExtractor` per §3.6 — use `save_entity_node()` helper.
9. **Adapt `palace.memory.lookup` / `filters.py` / `schema.py`** per §3.7 — replace EntityType literal, empty `_RELATED_FRAGMENTS`, update `_WHITELIST` per-type, rewrite tests.
10. **Adapt `palace.memory.health`** per §3.8 — drop `source` filter on LATEST_INGEST_RUN, new label list for ENTITY_COUNTS, update HealthResponse keys + tests.
11. Remove N+0 paperclip extractor files per §3.12.
12. **Add `openai_api_key: SecretStr`** to `services/palace-mcp/src/palace_mcp/config.py`; add env var line to `.env.example` (per §3.1).
13. Update `services/palace-mcp/README.md` with Graphiti-layer architecture note + pointer to `docs/research/graphiti-core-0-28-spike/README.md`.
14. Unit tests per §6.1.
15. Integration tests per §6.2.
16. Live smoke per §6.3 — iMac.

## 5. API shape after this slice

- `palace.memory.health()` — counts Episode / Iteration / Decision / etc. from Graphiti; reports last run metadata.
- `palace.memory.lookup(entity_type, filters, project?)` — direct lookup into Graphiti.
- `palace.ingest.run_extractor(name="heartbeat", project)` — produces one `:Episode`.
- `palace.ingest.list_extractors()` — lists registered extractors (`heartbeat` after this slice; bridge added in GIM-77).

No new MCP tool is exposed beyond those already present. The surface is unchanged in name; the backing store is now Graphiti instead of raw Neo4j for the product-layer entities.

## 6. Tests

### 6.1 Unit tests

- `test_build_graphiti_constructor` — asserts returned Graphiti has non-None `llm_client`, `embedder`, and `cross_encoder is None`.
- `test_build_graphiti_missing_openai_key_fails_early` — when `OPENAI_API_KEY` is absent in settings, `build_graphiti()` raises a clear `ConfigurationError` at build time (not at first LLM call).
- `test_settings_openai_api_key_required` — `Settings()` without `OPENAI_API_KEY` env var raises `pydantic.ValidationError` (per §3.1).
- `test_entity_type_literal_contains_new_set` — `filters.EntityType.__args__` matches the §3.7 list; does NOT contain `"Issue"`, `"Comment"`, `"Agent"`.
- `test_lookup_related_fragments_empty_in_n1a` — `lookup._RELATED_FRAGMENTS == {}` after refactor.
- `test_health_response_has_new_keys` — `HealthResponse` fields include `episodes`, `decisions`, `symbols`, `files`, ...; do NOT include `issues`, `comments`, `agents`.
- `test_latest_ingest_run_no_source_filter` — `LATEST_INGEST_RUN` Cypher has no `WHERE r.source = $source` clause (per §3.8).
- `test_project_slug_query_uses_name` — `runner.GET_PROJECT` matches `(p:Project {name: $slug})`, not `{slug: $slug}` (per §3.10).
- `test_register_project_sets_name_to_slug` — `register_project(slug="gimle")` creates an EntityNode with `name="gimle"`.
- `test_entity_factory_metadata_envelope_required` — factory for any entity type raises `ValueError` if `confidence` or `provenance` is absent from attributes.
- `test_entity_factory_provenance_enum` — `provenance` must be `"asserted" | "derived" | "inferred"`.
- `test_symbol_kind_enum` — factory for Symbol validates `kind ∈ {function, method, class, interface, enum, type}`.
- `test_edge_factory_attributes_envelope_required` — same for edges.
- `test_paperclip_extractor_modules_removed` — `import services.palace_mcp.ingest.paperclip` raises `ModuleNotFoundError`.

### 6.2 Integration tests

Fixture: `testcontainers-neo4j` + a dummy OPENAI_API_KEY. No real OpenAI call is made (writes via `add_triplet`).

- `test_ensure_graphiti_schema_idempotent` — call twice; no errors, constraints unchanged.
- `test_heartbeat_writes_one_episode` — run heartbeat extractor; `palace.memory.lookup Episode {kind:'heartbeat'}` returns one row with full metadata envelope.
- `test_heartbeat_episode_has_embedding` — the written `:Episode` has `name_embedding` populated (embedder ran). Skippable if CI can't reach OpenAI; mark with `@pytest.mark.needs_openai`.
- `test_memory_health_counts_episodes` — after one heartbeat run, `palace.memory.health()` returns `{Episode: 1, ...}`.
- `test_memory_lookup_unknown_entity_returns_error` — `palace.memory.lookup Issue {}` returns `{error: "unknown entity type", warnings: [...]}` (no silent fallback).

### 6.3 Live smoke on iMac

1. `docker compose --profile review up -d` (existing profile, still sufficient — no code-graph needed for this slice).
2. `palace.ingest.run_extractor heartbeat --project gimle` succeeds with `nodes_written=1`.
3. `palace.memory.lookup Episode {kind: "heartbeat"}` returns at least one row with attributes envelope populated.
4. `palace.memory.health` returns non-zero Episode count.
5. Watchdog (`~/.paperclip/watchdog.err`) stays empty for the duration.

All five must pass before Phase 4.2 merge. QA Phase 4.1 evidence comment references commit SHA and pastes tool-call responses for items 2–4.

## 7. Risks

| Risk | Mitigation |
|---|---|
| `graphiti-core==0.28.2` patches break something between now and merge | Lock exact version; CI pins same; re-run spike on any planned bump. |
| `EntityNode.attributes` schema-less dict allows typo drift (`confidance` vs `confidence`) | Factory functions validate keys on every construction; unit test `test_entity_factory_metadata_envelope_required` enforces. |
| OPENAI_API_KEY leaks in logs or tracebacks | Config uses pydantic `SecretStr`; log formatter strips secret repr. Constructor failure message masks key value. |
| Embedder silently fails offline → `name_embedding` is `None` on production writes | Unit test `test_heartbeat_episode_has_embedding` is `needs_openai`-gated but integration run on iMac always has network. Alert surfaces if `name_embedding is None` on any write we care about searching by. |
| Removing `:Issue`/`:Comment` filters breaks an unknown downstream consumer | grep before delete; Claude Code's external MCP path uses `palace.memory.lookup` without entity-type filter in README examples → low risk. |

## 8. References

- Graphiti 0.28.2 verified API: `docs/research/graphiti-core-0-28-spike/README.md` (repo-tracked copy of memory reference).
- Umbrella decomposition: `docs/superpowers/specs/2026-04-24-N1-decomposition-design.md`.
- GIM-76 sidecar spec: `docs/superpowers/specs/2026-04-24-N1a-2-codebase-memory-sidecar-design.md`.
- GIM-77 bridge spec: `docs/superpowers/specs/2026-04-24-N1a-3-bridge-extractor-design.md`.
- Historical combined spec (deprecated): `docs/superpowers/specs/2026-04-24-N1a-graphiti-codebase-memory-foundation-design.md`.
- Predecessor merge: `67d42dc`.
