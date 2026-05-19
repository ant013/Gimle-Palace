# M0 — Discovery Contract Inventory

**Status:** Draft (Board, 2026-05-19, not yet on feature branch)
**Pin:** develop tip `6e3b7b37 feat(GIM-355): extend stop-list to semgrep-based extractors (#229)`
**Purpose:** ground-truth audit of every MCP call in a hypothetical implementer discovery script — what exists, what's project/bundle-scoped, what needs change. **Without this no UW iOS roadmap acceptance is honest.**

## Scope of the discovery script we want to enable

When operator gives an implementer agent a task (e.g. cryptoPay), the agent should run these calls before writing any code:

1. `palace.code.find_references(qualified_name, project|bundle)` — does class/method already exist?
2. `palace.code.search_code(pattern, project)` — grep-like text search across codebase
3. `palace.code.search_graph(name_pattern|qn_pattern, project)` — symbol graph search
4. `palace.code.get_code_snippet(qualified_name|file:line, project)` — read existing implementation
5. `palace.code.trace_call_path(function_name, mode=calls|data_flow)` — call chain trace
6. `palace.code.find_owners(file_path, project)` — who owns this area
7. `palace.code.find_hotspots(project, path_prefix)` — is this hot code (extra care)
8. `palace.code.list_functions(project, path)` — what's already in this file
9. `palace.code.find_idiom(intent, project, module)` — what's the canonical pattern (e.g. `async_cancel`)
10. `palace.code.find_dead_symbols(project)` — are there abandoned symbols I shouldn't revive
11. `palace.code.find_public_api(project)` — what's the public surface
12. `palace.code.find_cross_module_contracts(project)` — consumer/producer contracts
13. `palace.code.find_version_skew(project|bundle)` — version drift in deps
14. `palace.git.log(project, path, limit)` — recent history of file
15. `palace.git.blame(project, ref, path, line)` — who/when wrote this line
16. `palace.memory.lookup(entity_type, filters)` — broad graph query
17. `palace.memory.get_project_overview(slug)` — sanity counts / freshness
18. `palace.audit.run(project|bundle, depth)` — full audit (not per-task; reference)

## Inventory matrix (against develop tip `6e3b7b37`)

Legend: `✅` works as-is for the noted scope; `❌` doesn't exist or not supported in that scope; `~` partial / via composition.

### palace.code.* — CM passthrough (8 tools, registered in `code_router.py`)

These route through codebase-memory-mcp subprocess. Project scoping comes from CM's mount path → repo identity. No native bundle awareness.

| Tool | exists | project | bundle | slug norm helper | wire test | needed change |
|---|---|---|---|---|---|---|
| `palace.code.search_graph` | ✅ | ~ (via CM mount) | ❌ | ✅ `_slug_to_cm_project` in `code_composite.py:76` (NOT `code_router.py` — rev2 fix M1) | check `tests/code_composite/test_cm_contract.py` | bundle support requires either CM-side bundle awareness OR Palace-layer fan-out across members |
| `palace.code.trace_call_path` | ✅ | ~ | ❌ | ✅ | same | same |
| `palace.code.query_graph` | ✅ | ~ (Cypher targets group_id) | ❌ | ✅ | same | Cypher can target multiple group_ids in one query if agent knows bundle members — workable |
| `palace.code.detect_changes` | ✅ | ~ | ❌ | ✅ | same | same as search_graph |
| `palace.code.get_architecture` | ✅ | ~ | ❌ | ✅ | same | same |
| `palace.code.get_code_snippet` | ✅ | ~ | ❌ | ✅ | same | **decision point**: keep passthrough OR build native composite with usages+owners+hotspot enrichment (operator-asked feature) |
| `palace.code.search_code` | ✅ | ~ | ❌ | ✅ | same | same |
| `palace.code.manage_adr` | ✅ (native via `adr/router.py`) | n/a | n/a | n/a | yes | unrelated to discovery; ignore |

### palace.code.* — native Palace tools

These query Palace's own Neo4j/Tantivy data (written by extractors). Bundle support is uneven.

| Tool | exists | project | bundle | slug norm | wire test | needed change |
|---|---|---|---|---|---|---|
| `palace.code.find_references` | ✅ | ✅ | ✅ (SlugResolution handles both kinds, `code_composite.py`) | ✅ `_slug_to_cm_project` / `_cm_project_to_slug` | ✅ `tests/code_composite/test_find_references_bundle.py` | **none — gold standard for bundle support** |
| `palace.code.find_hotspots` | ✅ | ✅ | ❌ | none | check `tests/extractors/integration/test_hotspot_*` | **add bundle param** OR rely on MCP-layer per-member fan-out helper |
| `palace.code.list_functions` | ✅ | ✅ | ❌ | none | check tests | same |
| `palace.code.find_owners` | ✅ | ✅ | ❌ | none | `tests/extractors/code_ownership/*` | same |
| `palace.code.find_dead_symbols` | ✅ | ✅ | ❌ | none | `tests/code/test_composite_find_dead_symbols.py` | same |
| `palace.code.find_public_api` | ✅ | ✅ | ❌ | none | `tests/code/test_composite_find_public_api.py` | same |
| `palace.code.find_cross_module_contracts` | ✅ | ✅ | ❌ | none | `tests/code/test_composite_find_cross_module_contracts.py` | same |
| `palace.code.find_version_skew` | ✅ | ✅ | ✅ (mutually exclusive args, `extractors/cross_repo_version_skew/find_version_skew.py`) | uses `_project_exists` / `_bundle_exists` + `_bundle_members` | likely | **none** |
| `palace.code.find_idiom` | ❌ | — | — | — | — | **new MCP tool** querying existing `:Convention` / `:ConventionViolation` nodes from `coding_convention` extractor (operator's idea — extend rule set, not new extractor) |
| `palace.code.semantic_query` | ❌ | — | — | — | — | new tool over Graphiti embeddings — **blocked by IB-3 (OpenAI quota)**; consider local embedder fallback |

### palace.memory.* (native, `mcp_server.py:430+`)

| Tool | exists | project | bundle | slug norm | wire test | needed change |
|---|---|---|---|---|---|---|
| `palace.memory.lookup(entity_type, filters)` | ✅ | filter-based | filter-based (can filter on `group_id`) | manual | likely | agent must know `group_id='bundle/<name>'` convention vs `'project/<slug>'` — document it |
| `palace.memory.health` | ✅ | global | global | n/a | n/a | none |
| `palace.memory.register_project` | ✅ | ✅ | n/a | yes | yes | none |
| `palace.memory.list_projects` | ✅ | n/a | n/a | n/a | yes | none |
| `palace.memory.get_project_overview` | ✅ | ✅ | ❌ | none | likely | **add bundle param** OR per-member fan-out at MCP layer |
| `palace.memory.register_bundle` | ✅ | n/a | ✅ | n/a | yes | none |
| `palace.memory.add_to_bundle` | ✅ | ✅ + bundle | ✅ | yes | yes | none |
| `palace.memory.bundle_members` | ✅ | n/a | ✅ | n/a | yes | none |
| `palace.memory.bundle_status` | ✅ | n/a | ✅ | n/a | yes | none |
| `palace.memory.delete_bundle` | ✅ | n/a | ✅ | n/a | yes | none |
| `palace.memory.decide` | ✅ | ✅ | unknown | n/a | yes | unrelated to discovery flow |

### palace.git.* (native, single-repo)

| Tool | exists | project | bundle | slug norm | wire test | needed change |
|---|---|---|---|---|---|---|
| `palace.git.log` | ✅ | ✅ (single repo by slug) | ❌ | uses `/repos/<slug>` mount | yes | bundle queries → MCP-layer per-member iteration (agent calls N times) — acceptable; **document pattern** |
| `palace.git.show` | ✅ | ✅ | ❌ | mount-based | yes | same |
| `palace.git.blame` | ✅ | ✅ | ❌ | mount-based | yes | same |
| `palace.git.diff` | ✅ | ✅ | ❌ | mount-based | yes | same |
| `palace.git.ls_tree` | ✅ | ✅ | ❌ | mount-based | yes | same |

### palace.audit.run

| Tool | exists | project | bundle | slug norm | wire test | needed change |
|---|---|---|---|---|---|---|
| `palace.audit.run` | ✅ | ✅ (`_run_single_project`, `audit/run.py:82`) | ✅ (`_run_bundle` at `audit/run.py:199` iterates `bundle_members` and runs `discover_extractor_statuses(project=slug)` per-member) | uses `bundle_members` API | likely | **none — bundle support works via per-member iteration** |

### palace.ingest.* (admin)

`list_extractors`, `run_extractor`, `bundle_status` — exist, registered. Not part of discovery script. Skipped.

## Cross-cutting analysis

### What I got wrong in the earlier draft (correcting myself)

1. **My claim that `palace.audit.run(bundle=…)` is not bundle-aware was misleading.** Looking at `_run_bundle` (audit/run.py:199), it iterates `bundle_members` and runs `discover_extractor_statuses(project=slug)` per-member. So bundle awareness exists — just via per-member aggregation, not a native bundle query. The acceptance for S1.4 in the original sprint draft was **plausible**, not impossible. Operator's critique pt 1 was partially correct (single-project query is project-scoped) but missed `_run_bundle` does the right loop.

2. **Discovery script size grew once I checked**: from 7 in original "final acceptance" to **18 tools** (matrix above), once I added what's actually in `mcp_server.py` registration. Many of those project-scoped tools need per-member iteration for bundle answers.

### Honest blocker pattern

The dominant gap is: **5 native query tools (`find_hotspots`, `list_functions`, `find_owners`, `find_dead_symbols`, `find_public_api`, `find_cross_module_contracts`) are project-only**. Only `find_references` and `find_version_skew` have native bundle support. For UW iOS bundle discovery to work, **one of two approaches**:

- **Approach A**: extend each project-only tool to accept `bundle` param (mutually exclusive with `project`). Internally fan out to members. ~5 small slices, ~50-100 LOC each.
- **Approach B**: build a single MCP-layer helper `palace.code.fan_out(tool, bundle, args)` that runs any project-scoped tool across members and merges results. ~1 medium slice, ~200 LOC. Less explicit per-tool API, but DRY.

Operator should decide A vs B. (My instinct: **A** — explicit signatures are easier for agent to discover and use correctly than a polymorphic fan-out.)

### CM passthrough scoping gap

The 7 CM passthrough tools (`search_code`, `search_graph`, etc.) currently scope by CM's own mount path. For a bundle query, options:

- Sequential: agent calls per-member (operator pattern from running these manually)
- CM-side bundle awareness: add bundle understanding to codebase-memory-mcp (out of Gimle scope)
- Palace-side wrapping: same fan-out helper as Approach B above could wrap CM tools too

Defer this decision until UW iOS is indexed and we can measure: do agents actually need bundle-level CM queries, or can they do member-by-member?

### Tools that **don't exist** (must be built for full vision)

- `palace.code.find_idiom(intent, project, module=)` — new MCP tool over `:Convention` nodes already produced by `coding_convention` extractor. **Operator's correct framing**: this is a **new tool**, not a new extractor. Extension to rule set in `coding_convention` may also be needed if current rules don't capture intents like `async_cancel`, `error_propagation`, etc.
- `palace.code.semantic_query(text, project)` — new tool over Graphiti embeddings. **Blocked by IB-3** (OpenAI quota exceeded). Either top up quota, integrate local embedding model, or accept that this is M5 optional.
- `palace.code.get_snippet_rich` — composite that combines existing CM `get_code_snippet` + Palace's `find_owners` + `find_hotspots` + recent commits. **Operator-requested feature.** Maybe not a new tool — maybe agent just chains 3-4 calls. Decision: ship as composite tool only if measurable token savings or agent reliability gain.

### What I missed in the original draft besides above

- `palace.code.search_graph`, `palace.code.search_code`, `palace.code.trace_call_path` — pivotal for "search by semantics, not name" pattern (codebase-memory-mcp's bread and butter). These are passthrough — operator can use **today** if codebase-memory-mcp is set up against UW iOS. Original draft mentioned codebase-memory-mcp in passing but didn't put it in the acceptance script.
- `palace.memory.get_project_overview` was missing from my acceptance script — it's the cheap sanity check (counts, freshness) any agent should run first.

## Replacement final acceptance (for the rewritten roadmap)

When all milestones land, operator runs this script against UW iOS bundle:

```
# Sanity / freshness
palace.memory.get_project_overview(slug="uw-ios-app")    # main app
palace.memory.bundle_status(bundle="uw-ios")             # bundle freshness

# Exact-name discovery
palace.code.find_references("scanQR", bundle="uw-ios")
palace.code.find_references("addressFromMnemonic", bundle="uw-ios")

# Semantic / pattern search  (codebase-memory-mcp passthrough)
palace.code.search_code(pattern="bech32", lang="swift", project=<auto>)
palace.code.search_graph(name_pattern="*Parser*", project=<auto>)

# Snippet retrieval
palace.code.get_code_snippet(qualified_name="UriParser.parse")

# Idiomatic patterns
palace.code.find_idiom(intent="async_cancel", project="uw-ios-app", module="Send")
palace.code.find_idiom(intent="error_propagation", project="uw-ios-app", module="Send")
palace.code.find_idiom(intent="uri_parsing", project="uw-ios-app")

# Ownership / risk
palace.code.find_owners(file_path="Modules/Send/SendController.swift", project="uw-ios-app")
palace.code.find_hotspots(project="uw-ios-app", path_prefix="Modules/Send")

# History
palace.git.log(project="uw-ios-app", path="Modules/Send/SendController.swift", limit=10)
palace.git.blame(project="uw-ios-app", ref="HEAD", path="Modules/Send/SendController.swift", line=42)

# Cross-cutting
palace.code.find_version_skew(bundle="uw-ios", min_severity="minor")
palace.code.find_dead_symbols(project="uw-ios-app")
palace.code.find_public_api(project="uw-ios-app")

# Optional (M5, if budget allows)
palace.code.semantic_query("how does the app cancel async tasks", bundle="uw-ios")
```

All return non-empty, structured, actionable. Without an `❌` row from the matrix above remaining unhandled.

## What this inventory unlocks for the rewritten roadmap

- **M0 (this slice + GIM-355/356/357 closure)** — discovery contract pinned, baseline known
- **M1 iOS Bundle Query-Ready** — acceptance now mappable to specific tools: `find_references` works bundle-native, `audit.run` works per-member; remaining 5 project-only tools either fanned out at MCP layer (Approach A/B decision) OR called per-member by agent (acceptable for v1)
- **M2 Android Parity** — same matrix, idem
- **M3 Discovery Primitives** — concrete scope: build `find_idiom` (over existing :Convention), decide on Approach A vs B for bundle support, decide on `get_snippet_rich` composite or chain
- **M4 Enforcement** — extend existing shared `pre-work-discovery.md` fragment with the acceptance script above; CR checks PR body cites ≥5 calls
- **M5 Semantic** — `semantic_query` + IB-3 unlock

## Operator decisions needed

1. **Approach A vs B for bundle support on 6 project-only tools.** A = explicit `bundle=` param per tool (5-6 slices). B = polymorphic fan-out helper (1 medium slice). Affects how agent constructs queries.
2. **Should we ship `palace.code.get_snippet_rich` composite, or accept agent chains 3 calls?** Measure first or ship now?
3. **Find_idiom rule scope.** Operator-curated list of intents that matter for UW (`async_cancel`, `error_propagation`, etc.) — who curates the initial 15-20? Operator solo, or with team?
4. **IB-3 OpenAI quota.** Top up or local embedder? Affects M5 timing.
5. **CM-side bundle support.** Out of scope for Gimle, but worth raising as upstream issue with codebase-memory-mcp maintainers if it becomes a bottleneck.

— Board (Anton), 2026-05-19 (development branch tip `6e3b7b37`)
