---
slug: N1a-3-bridge-extractor
status: proposed
branch: feature/GIM-77-bridge-extractor (to be cut from develop AFTER GIM-75 and GIM-76 merge)
paperclip_issue: 77 (b7198de1-b3d9-469c-a5d9-86c1badb3aaf)
parent_umbrella: 74
depends_on:
  - 75 (N+1a.1 Graphiti foundation) — must be merged before this slice can start implementation
  - 76 (N+1a.2 Codebase-Memory sidecar + pass-through) — must be merged before this slice can start implementation
predecessor: to be set to develop tip at branch creation time
date: 2026-04-24
---

# N+1a.3 — Bridge extractor: project Codebase-Memory facts into Graphiti

## 1. Context and scope boundary

This slice connects the two independent substrates delivered by GIM-75 (Graphiti foundation) and GIM-76 (Codebase-Memory sidecar + `palace.code.*`). It introduces one new extractor, `codebase_memory_bridge`, which reads selected facts from CM via the pass-through router and writes them as Graphiti `EntityNode` / `EntityEdge` with a metadata envelope (`confidence`, `provenance`, `extractor`, `cm_id`, `observed_at`) and Graphiti-native `valid_at`/`invalid_at` edges.

**Dependencies (hard, not soft):**
- GIM-75 must be merged. `BaseExtractor` accepts `graphiti: Graphiti` ctx; entity/edge Pydantic catalog is in place; heartbeat already writes `:Episode`.
- GIM-76 must be merged. `palace.code.*` tools available; CM sidecar healthy.

**In scope:**
- `codebase_memory_bridge` extractor class.
- Projection rules for `:Project`, `:File`, `:Module`, `:Symbol` (with `kind` property), `:APIEndpoint`, `ArchitectureCommunity`, `Hotspot` nodes + structural edges.
- Metadata envelope with `cm_id` cross-ref on every projected node/edge.
- Bi-temporal handling: incremental runs set `invalid_at` on Graphiti edges whose CM source has been removed.
- `palace.memory.health` extended to report bridge-run freshness and CM index staleness.
- Integration and iMac live-smoke acceptance.

**Out of scope:**
- Auto-trigger on git-event via GIM-62 async-signal — followup.
- `semantic_search` (N+1b).
- `git_events_extractor` (N+1c).
- Bi-directional sync of ADRs — explicitly rejected by GIM-76 design.
- Projection of CM's `THROWS`/`READS`/`WRITES`/`HTTP_CALLS`/`ASYNC_CALLS`/`USES_TYPE`/`IMPLEMENTS`/`INHERITS`/`USAGE`/`TESTS` — those stay in CM SQLite, reachable via `palace.code.*`.

## 2. Problem

After GIM-75 and GIM-76, agents can read Graphiti (`palace.memory.*`) and CM (`palace.code.*`) independently, but cannot follow a decision, finding, or iteration *to the code it concerns*. There is no edge in Graphiti pointing at a code symbol because no extractor has written one.

The bridge is the first path that populates code-concerning Graphiti edges. Without it, the two stores sit side-by-side with no mutual value beyond what each offers individually.

## 3. Solution — one new extractor, selective projection, cross-ref by `cm_id`

### 3.1 Extractor signature

```python
# services/palace-mcp/src/palace_mcp/extractors/codebase_memory_bridge.py

from palace_mcp.extractors.base import BaseExtractor, ExtractorRunContext, ExtractorStats
from palace_mcp.graphiti_runtime import build_graphiti  # from GIM-75
from graphiti_core import Graphiti

class CodebaseMemoryBridgeExtractor(BaseExtractor):
    name = "codebase_memory_bridge"
    version = "0.1"
    description = "Project selected facts from codebase-memory-mcp into Graphiti with metadata envelope"

    async def run(self, *, graphiti: Graphiti, ctx: ExtractorRunContext) -> ExtractorStats:
        ...
```

Registered via existing `registry.py` pattern (from GIM-59 substrate).

### 3.2 Projection rules — exact mapping

For each target project (identified by `ctx.project_slug`), the bridge calls `palace.code.get_architecture` to enumerate packages and queries `palace.code.search_graph` / `palace.code.query_graph` per node type.

| CM source | Graphiti target | `provenance` | `confidence` | `attributes` essentials |
|---|---|---|---|---|
| `:Project` | `:Project` (one per slug) | `asserted` | `1.0` | `cm_id`, `slug`, `name`, `language?`, `framework?` |
| `:File` | `:File` | `asserted` | `1.0` | `cm_id`, `path`, `hash` (XXH3 from CM), `loc` |
| `:Module` | `:Module` | `asserted` | `1.0` | `cm_id`, `path`, `kind?` |
| `:Function` | `:Symbol{kind: "function"}` | `asserted` | `1.0` | `cm_id`, `name`, `file_path`, `signature?` |
| `:Method` | `:Symbol{kind: "method"}` | `asserted` | `1.0` | `cm_id`, `name`, `file_path`, `signature?`, `class_cm_id` |
| `:Class` | `:Symbol{kind: "class"}` | `asserted` | `1.0` | `cm_id`, `name`, `file_path` |
| `:Interface` | `:Symbol{kind: "interface"}` | `asserted` | `1.0` | same |
| `:Enum` | `:Symbol{kind: "enum"}` | `asserted` | `1.0` | same |
| `:Type` | `:Symbol{kind: "type"}` | `asserted` | `1.0` | same |
| `:Route` | `:APIEndpoint` | `asserted` | `1.0` (or CM's `HANDLES.confidence` if present) | `cm_id`, `method`, `path`, `handler_cm_id?` |
| CM community node (from Louvain) | `:EntityNode` with `labels=["ArchitectureCommunity"]` | `derived` | Louvain modularity score, clamped [0, 1] | `cm_id`, `name` (auto: `community-<n>`), `modularity`, `member_count` |
| CM hotspot (derived: top-5% co-change frequency, computed by bridge) | `:EntityNode` with `labels=["Hotspot"]` | `derived` | normalized co-change rank, clamped [0, 1] | `cm_id_file`, `cochange_score`, `rank` |

CM edges → Graphiti edges:

| CM edge | Graphiti edge | `provenance` | `confidence` | Extra attrs |
|---|---|---|---|---|
| `CONTAINS_*` (package→file etc.) | `CONTAINS` | `asserted` | `1.0` | `cm_edge_id` |
| `DEFINES` | `DEFINES` | `asserted` | `1.0` | same |
| `CALLS` | `CALLS` | `asserted` | `1.0` | same |
| `IMPORTS` | `IMPORTS` | `asserted` | `1.0` | same |
| `HANDLES` (route→handler) | `HANDLES` | `asserted` | CM's own `confidence` attr | same |
| `MEMBER_OF` (from Louvain) | `MEMBER_OF` | `derived` | community's modularity score | same |
| bridge-computed `LOCATES_IN` (Hotspot→File) | `LOCATES_IN` | `derived` | normalized co-change rank | bridge-synthesized, no `cm_edge_id` |

### 3.3 Not projected (stay in CM only)

`THROWS`, `READS`, `WRITES`, `HTTP_CALLS`, `ASYNC_CALLS`, `USES_TYPE`, `IMPLEMENTS`, `INHERITS`, `USAGE`, `TESTS`, `FILE_CHANGES_WITH` (raw edges — only the derived `:Hotspot` node summarizes them), `DEFINES_METHOD` (superseded by `DEFINES` with `kind=method`).

Rationale: per-node call-tree detail and side-effect edges are high-volume, low-product-value in Graphiti. Agents reach them via `palace.code.*` when needed; they don't belong in the product layer.

### 3.4 Incremental / bi-temporal update logic

- Per-run: query CM's `detect_changes` to get the set of files modified since the bridge's last recorded `observed_at`.
- For each changed file, re-fetch CM facts for it; compute diff against what Graphiti currently has for `cm_id` matching any of the file's symbols.
- **New facts:** `EntityNode.save(driver)` + `EntityEdge.save(driver)` with fresh `valid_at = now`, `invalid_at = None`.
- **Removed facts** (in Graphiti but no longer in CM): set `edge.invalid_at = now`, `edge.save(driver)`. Nodes are not deleted immediately — kept with `attributes["deprecated_at"] = now` for one more run, then can be reaped by a future GC slice.
- **Unchanged facts:** no write. The bridge's own state file (under `~/.paperclip/codebase-memory-bridge-state.json`) tracks last-seen XXH3 per file to skip files whose hash matches Graphiti's stored `attributes["hash"]`.

### 3.5 Cross-resolve contract

Any Graphiti `:Symbol` written by this extractor carries `attributes["cm_id"]`. Agents hydrate full detail by:

```
palace.code.get_code_snippet(qualified_name=<derived from cm_id or name>)
```

The cross-resolve test (§6.2) asserts this path works end-to-end on a sandbox repo.

### 3.6 Health reporting

`palace.memory.health` (extended in this slice) includes:

```json
{
  "bridge": {
    "last_run_at": "<iso>",
    "last_run_duration_ms": 1234,
    "nodes_written_by_type": {"File": 12, "Symbol": 340, ...},
    "edges_written_by_type": {"DEFINES": 340, "CALLS": 890, ...},
    "cm_index_freshness_sec": 45,
    "staleness_warning": false
  }
}
```

`staleness_warning = true` if `now - last_run_at > 2 × expected_interval` (default 10 min MVP — configurable later).

## 4. Tasks

1. Confirm GIM-75 and GIM-76 are merged on develop (blocker check).
2. Cut `feature/GIM-77-bridge-extractor` from develop tip.
3. Create `services/palace-mcp/src/palace_mcp/extractors/codebase_memory_bridge.py`.
4. Register in `services/palace-mcp/src/palace_mcp/extractors/registry.py`.
5. Implement per-node-type projection queries (§3.2).
6. Implement derived-layer computation: ArchitectureCommunity (read CM's Louvain output), Hotspot (read CM's `FILE_CHANGES_WITH`, rank top-5%).
7. Implement incremental logic + bridge state file (§3.4).
8. Extend `palace.memory.health` to include bridge stats (§3.6).
9. Unit tests per §6.1.
10. Integration tests per §6.2.
11. Update `services/palace-mcp/README.md` with bridge extractor section + cross-resolve example.
12. Live smoke on iMac per §6.3.

## 5. API shape after this slice

No new MCP tools beyond what GIM-75/76 delivered. New *behavior*:

- `palace.ingest.run_extractor(name="codebase_memory_bridge", project=<slug>)` — runs the bridge.
- `palace.memory.health` returns extended bridge stats.
- `palace.memory.lookup Symbol {}` / `File {}` / `Module {}` / `APIEndpoint {}` / with `attributes.cm_id` present now return data.

## 6. Tests

### 6.1 Unit tests

- `test_projection_rules_coverage` — each CM node type in the bridge's `_CM_TO_GRAPHITI_MAP` has a corresponding target Graphiti entity + provenance + confidence rule.
- `test_skipped_edges_not_projected` — for each CM edge in the skip-list (`THROWS`/`READS`/`WRITES`/...), the bridge's filter drops it; fixture CM response with one of each produces zero such edges in Graphiti.
- `test_metadata_envelope_on_every_projection` — for every projected entity/edge, `confidence`, `provenance`, `extractor`, `extractor_version`, `evidence_ref`, `observed_at` are all populated.
- `test_cm_id_present_on_every_projected_node` — post-run, all projected nodes carry `attributes["cm_id"]`.
- `test_incremental_skips_unchanged_files` — fixture with two runs on identical CM state; second run writes 0 nodes / 0 edges.
- `test_incremental_invalidates_removed_edges` — fixture with a file whose CM response drops one `CALLS` edge on the second run; the corresponding Graphiti edge has `invalid_at` set.

### 6.2 Integration tests

Fixture: testcontainers-neo4j + `codebase-memory-mcp` subprocess + `tests/fixtures/sandbox-repo/` (same fixture as GIM-76 integration tests).

- `test_bridge_full_run` — run bridge against sandbox repo end-to-end. Assertions:
  - `palace.memory.lookup Symbol {}` returns non-zero rows; each has `attributes.cm_id`.
  - `palace.memory.lookup File {}` returns one row per Python/Go/Dockerfile file in the sandbox.
  - `palace.memory.lookup ArchitectureCommunity {}` returns at least one.
  - `palace.memory.lookup Hotspot {}` returns at most 5% of files (in a small sandbox, likely 1).
  - Every node `attributes.provenance` ∈ `{asserted, derived}`, never `inferred`.
- `test_cross_resolve_symbol_to_cm` — pick a `:Symbol` row at random; extract `attributes["cm_id"]`; call `palace.code.get_code_snippet(qualified_name=<derived>)` and verify returned body matches the on-disk file at `attributes["file_path"]` and line range.
- `test_incremental_rerun_no_op` — run bridge twice on unchanged fixture; second run's `ExtractorStats` reports `nodes_written=0`, `edges_written=0`.
- `test_file_modification_incremental_update` — edit one file in fixture, re-run bridge. Only that file's symbols are updated; other files' `observed_at` unchanged.
- `test_bridge_health_reporting` — after one run, `palace.memory.health()['bridge']` populated with `last_run_at`, `last_run_duration_ms`, `nodes_written_by_type`, etc.

### 6.3 Live smoke on iMac

1. `docker compose --profile code-graph up -d` → all services healthy.
2. `palace.ingest.run_extractor codebase_memory_bridge --project gimle` → `{ok: true, nodes_written_by_type: {...}, edges_written_by_type: {...}}` with non-zero counts.
3. `palace.memory.lookup Symbol {kind: "function"}` returns at least one known Gimle function (e.g., `build_graphiti`).
4. For that returned row, `palace.code.get_code_snippet(qualified_name=<auto>)` returns the function body.
5. `palace.memory.lookup ArchitectureCommunity {}` returns at least one community; at least one `:Symbol` has a `:MEMBER_OF` edge to it.
6. `palace.memory.lookup Hotspot {}` returns at most 5% of Gimle files.
7. Re-run bridge immediately — second run stats show 0 new nodes/edges.
8. `palace.memory.health` reports `bridge.last_run_at` within last minute; `staleness_warning: false`.
9. Watchdog (`~/.paperclip/watchdog.err`) stays empty.

All 9 must pass before Phase 4.2 merge.

## 7. Risks

| Risk | Mitigation |
|---|---|
| CM's internal edge/node types change between GIM-76 merge and GIM-77 work | Pin CM image tag (same as GIM-76). Bridge's `_CM_TO_GRAPHITI_MAP` lives in one file — regression is isolated. Re-run integration tests on any CM version bump. |
| `cm_id` clash between two CM re-indexes (e.g., if CM re-uses IDs across projects) | Compose Graphiti `attributes["cm_id"]` as `"<project_slug>:<cm_internal_id>"` to disambiguate across projects. |
| Incremental logic drops a genuine update because its XXH3 hash collides with a stale cache | XXH3 collision rate is cryptographically negligible (~2^-64). If operator ever sees suspected drift, running bridge with `--force-full` (flag to be added if needed) re-projects everything. Not on this slice's happy path. |
| Hotspot top-5% heuristic misses real hotspots on small repos (3 files → 0 hotspots) | Accept. Document that Hotspot population requires repos with ≥ 20 files. iMac live smoke #6 asserts "≤ 5%", not "≥ 1" for this reason on sandbox. Gimle itself has >> 20 files so production usage is fine. |
| Bridge run takes too long (> 5 min) on large target projects | CM is sub-ms for reads; Graphiti `EntityEdge.save` is the expected bottleneck (one Neo4j transaction per edge). Benchmark on first iMac run; if > 5 min, batch edge writes via `EntityEdge.save_bulk` (if available in 0.28) or manual Cypher. |
| `ArchitectureCommunity` and `Hotspot` labels collide with future Graphiti first-class types | These are plain `:EntityNode` with multi-label, not new Pydantic classes. Standard Graphiti label-query works. No collision risk. |

## 8. References

- GIM-75 foundation spec: `docs/superpowers/specs/2026-04-24-N1a-1-graphiti-foundation-design.md` (provides `BaseExtractor`, Graphiti entity/edge catalog).
- GIM-76 sidecar spec: `docs/superpowers/specs/2026-04-24-N1a-2-codebase-memory-sidecar-design.md` (provides `palace.code.*`).
- Umbrella decomposition: `docs/superpowers/specs/2026-04-24-N1-decomposition-design.md`.
- Graphiti 0.28.2 verified API: `memory/reference_graphiti_core_0_28_api_truth.md`.
- Codebase-Memory paper: arXiv:2603.27277.
- Historical combined spec (deprecated): `docs/superpowers/specs/2026-04-24-N1a-graphiti-codebase-memory-foundation-design.md`.
