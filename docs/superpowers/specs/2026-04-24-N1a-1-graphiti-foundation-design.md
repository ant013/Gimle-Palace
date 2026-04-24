---
slug: N1a-1-graphiti-foundation
status: proposed
branch: feature/GIM-75-graphiti-foundation (to be cut from develop once umbrella spec lands)
paperclip_issue: 75 (0855b069-3e42-4cc8-b644-6dec26660111)
parent_umbrella: 74
predecessor: 67d42dc (develop tip)
date: 2026-04-24
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

### 3.1 Dependency

Add to `services/palace-mcp/pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "graphiti-core==0.28.2",
]
```

Pin exact patch. **Do not rely on `~=0.28` or `>=0.28` — 0.28.x history shows breaking changes between minor patches.**

### 3.2 Factory and bootstrap

```python
# services/palace-mcp/src/palace_mcp/graphiti_runtime.py

from graphiti_core import Graphiti
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
```

Wire `build_graphiti()` into the palace-mcp lifespan startup. Hold a module-level singleton (same pattern as the existing Neo4j driver). Ensure `g.close()` runs on shutdown.

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
        await episode.save(graphiti._driver)  # or public helper
        return ExtractorStats(nodes_written=1, edges_written=0)
```

Heartbeat remains the reference implementation for "how an extractor writes to Graphiti" and the default sanity check in `palace.memory.health`.

### 3.7 N+0 paperclip extractor removal

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
2. Create `services/palace-mcp/src/palace_mcp/graphiti_runtime.py` with `build_graphiti()` + `ensure_graphiti_schema()`.
3. Create `services/palace-mcp/src/palace_mcp/graphiti_schema/entities.py` with Pydantic factory functions (not subclasses — 0.28 `EntityNode.attributes` dict is enough) for each entity type in §3.3.
4. Create `services/palace-mcp/src/palace_mcp/graphiti_schema/edges.py` similarly.
5. Wire `build_graphiti()` into palace-mcp FastMCP lifespan startup; wire `await g.close()` on shutdown.
6. Refactor `BaseExtractor` signature in `services/palace-mcp/src/palace_mcp/extractors/base.py`.
7. Refactor `HeartbeatExtractor` per §3.6.
8. Remove N+0 paperclip extractor files per §3.7.
9. Update `palace.memory.health` and `palace.memory.lookup` MCP tools to work against the new schema (no hard-coded old labels).
10. Update `services/palace-mcp/README.md` with Graphiti-layer architecture note + pointer to `memory/reference_graphiti_core_0_28_api_truth.md`.
11. Unit tests per §7.1.
12. Integration tests per §7.2.
13. Live smoke per §7.3 — iMac.

## 5. API shape after this slice

- `palace.memory.health()` — counts Episode / Iteration / Decision / etc. from Graphiti; reports last run metadata.
- `palace.memory.lookup(entity_type, filters, project?)` — direct lookup into Graphiti.
- `palace.ingest.run_extractor(name="heartbeat", project)` — produces one `:Episode`.
- `palace.ingest.list_extractors()` — lists registered extractors (`heartbeat` after this slice; bridge added in GIM-77).

No new MCP tool is exposed beyond those already present. The surface is unchanged in name; the backing store is now Graphiti instead of raw Neo4j for the product-layer entities.

## 6. Tests

### 7.1 Unit tests

- `test_build_graphiti_constructor` — asserts returned Graphiti has non-None `llm_client`, `embedder`, and `cross_encoder is None`.
- `test_build_graphiti_missing_openai_key_fails_early` — when `OPENAI_API_KEY` is absent in settings, `build_graphiti()` raises a clear `ConfigurationError` at build time (not at first LLM call).
- `test_entity_factory_metadata_envelope_required` — factory for any entity type raises `ValueError` if `confidence` or `provenance` is absent from attributes.
- `test_entity_factory_provenance_enum` — `provenance` must be `"asserted" | "derived" | "inferred"`.
- `test_symbol_kind_enum` — factory for Symbol validates `kind ∈ {function, method, class, interface, enum, type}`.
- `test_edge_factory_attributes_envelope_required` — same for edges.
- `test_paperclip_extractor_modules_removed` — `import services.palace_mcp.ingest.paperclip` raises `ModuleNotFoundError`.

### 7.2 Integration tests

Fixture: `testcontainers-neo4j` + a dummy OPENAI_API_KEY. No real OpenAI call is made (writes via `add_triplet`).

- `test_ensure_graphiti_schema_idempotent` — call twice; no errors, constraints unchanged.
- `test_heartbeat_writes_one_episode` — run heartbeat extractor; `palace.memory.lookup Episode {kind:'heartbeat'}` returns one row with full metadata envelope.
- `test_heartbeat_episode_has_embedding` — the written `:Episode` has `name_embedding` populated (embedder ran). Skippable if CI can't reach OpenAI; mark with `@pytest.mark.needs_openai`.
- `test_memory_health_counts_episodes` — after one heartbeat run, `palace.memory.health()` returns `{Episode: 1, ...}`.
- `test_memory_lookup_unknown_entity_returns_error` — `palace.memory.lookup Issue {}` returns `{error: "unknown entity type", warnings: [...]}` (no silent fallback).

### 7.3 Live smoke on iMac

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

- Graphiti 0.28.2 verified API: `memory/reference_graphiti_core_0_28_api_truth.md`.
- Umbrella decomposition: `docs/superpowers/specs/2026-04-24-N1-decomposition-design.md`.
- GIM-76 sidecar spec: `docs/superpowers/specs/2026-04-24-N1a-2-codebase-memory-sidecar-design.md`.
- GIM-77 bridge spec: `docs/superpowers/specs/2026-04-24-N1a-3-bridge-extractor-design.md`.
- Historical combined spec (deprecated): `docs/superpowers/specs/2026-04-24-N1a-graphiti-codebase-memory-foundation-design.md`.
- Predecessor merge: `67d42dc`.
