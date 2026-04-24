---
slug: N1a-graphiti-codebase-memory-foundation
status: proposed
branch: feature/GIM-74-n1a-graphiti-cm-foundation
paperclip_issue: 74 (90c9af9e-ee37-4d98-9cb5-2041fb364b87)
predecessor: 67d42dc (develop tip at design time — GIM-71 ruff-format merge)
supersedes:
  - docs/superpowers/specs/2026-04-18-palace-memory-n1-graphiti-substrate.md (deprecated rev1)
  - verbal N+1 brainstorm state captured in memory/project_n1_brainstorm_paused.md
  - earlier "G1+G3" sketch (swap paperclip extractor → Graphiti + semantic_search)
date: 2026-04-24
---

# N+1a Foundation: Graphiti product-layer + Codebase-Memory code-layer

## 1. Context

### 1.1 Where we are

- palace-mcp ships extractor framework substrate (GIM-59 `c0a6bcb`), `heartbeat` reference extractor, git-mcp read-only tools (GIM-54 `85be40e`), async-signal dispatcher (GIM-62 `068014f`), agent watchdog (GIM-63 `053d93f` + fixes).
- `services/palace-mcp/src/palace_mcp/ingest/` contains a test-only paperclip extractor (N+0, `98e9b8d`) writing `:Issue/:Comment/:Agent` to raw Neo4j. **Treated as disposable probe — removed in this slice.**
- `services/palace-mcp/pyproject.toml` has `neo4j>=5.0` only. `graphiti-core` was pulled after N+1a revert (`a4abd28`, 2026-04-18) — broken against graphiti-core 0.4.3 API assumptions. To be re-added against live-verified 0.28.x.
- `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §5 defines target entity/edge taxonomy (13 entities + 9 core + 6 capability edges + 4-axis multi-label faceting + bi-temporal). This slice grounds §5 into a deployable foundation.
- `group_id = "project/<slug>"` pattern established by GIM-52/53 (`PALACE_DEFAULT_GROUP_ID`).

### 1.2 Landscape shift (2026-Q1 → 2026-Q2)

Research `docs/research/agent-context-store-2026-04/` reviewed 15 systems across agent-memory, code-graph, retrieval, and schema discipline. Key signals:

- **Graphiti v1.0 MCP (Nov 2025) + Entity Types (May 2025)** hardens Graphiti as a temporal substrate. Pre-1.0 Python library at 0.28.x — usable with isolation wrapper.
- **Codebase-Memory MCP** (MIT, arXiv 2603.27277, March 2026): tree-sitter + SQLite + 14 MCP tools, 66 languages, zero LLM dependency, sub-ms queries, Louvain communities, git co-change edges, BFS impact analysis, SLSA 3 + 2586 tests + 1809 GitHub stars. Directly addresses the "understand project structure" capability that §5 planned to build from scratch.
- **Multi-graph separation (MAGMA)**, **budget-aware retrieval (CLAUSE)**, **property-vs-edge routing (OntoKG)**, **issue-to-symbol chain (KGCompass)**, **Pydantic graph models (Cognee)**, **reasoning-trace layer (neo4j-labs/agent-memory)**, **MemCube metadata envelope (MemOS)** — each contributes a specific pattern adopted below.
- **Mem0 OSS v3** (April 2026) removed external graph store — general memory libs are drifting away from typed graphs. Reinforces: our direction (structured typed graph) is not obsolete but is a specialist choice distinct from general agent memory.

### 1.3 Anchor insight

"Agent-memory" frameworks (Mem0, Letta, Cognee) treat knowledge as extracted-from-dialogue. They do not model software projects. Code-graph frameworks (Codebase-Memory, RepoGraph, CGM) model code structure but do not model decisions/iterations/findings. Our §5 spec targets **both** — which is why a two-layer approach with a bridge is the right shape, not a single substrate.

## 2. Problem

Paperclip agents (CTO, CodeReviewer, implementers, etc.) working on a target project cannot currently:

1. Ask "where is function `foo` called, what does it read/write, which PR introduced it, why was this decision made, what breaks if I change it" in one flow.
2. Query structural code facts at sub-millisecond latency without burning API tokens per query.
3. Track decisions that are still valid vs superseded, with links to the commits and findings that drove each transition.
4. Support target projects in languages beyond the handful we could hand-extract (current Gimle is Python; Medic target is Kotlin/Swift/KMP — two more projects become two more months of extractor work under a build-it-ourselves plan).

The earlier "G1+G3" plan (swap paperclip extractor → Graphiti + add `semantic_search`) addresses points 3–4 partially at best and ignores 1–2. A foundation that covers all four is the right investment now.

## 3. Solution

### 3.1 Two-layer substrate, connected via a bridge extractor

```
┌────────────────────────────────────────────────────────────────┐
│  Agents (Claude Code / paperclip-agents / MCP clients)         │
└────────────────────────────────────────────────────────────────┘
         │                                        │
         │ palace.memory.*                        │ palace.code.*
         │ (decisions, iterations, episodes,      │ (call-chains, routes,
         │  PRs, owners, hotspots, bi-temporal)   │  impact, dead-code,
         │                                        │  symbols, 66 langs)
         ▼                                        ▼
┌───────────────────────────┐         ┌───────────────────────────┐
│  palace-mcp (ours)        │         │  codebase-memory-mcp      │
│  ─────────────────────    │◄───────►│  ─────────────────────    │
│  Graphiti in-process lib  │ bridge  │  MIT, tree-sitter, C bin  │
│  Custom entity/edge types │ (our    │  SQLite per project       │
│  group_id = project/<s>   │  code)  │  14 MCP tools             │
│  Bi-temporal, metadata    │         │  Zero LLM, sub-ms queries │
│  envelope                 │         │  66 langs + IaC indexing  │
└───────────────────────────┘         └───────────────────────────┘
         │                                        │
         ▼                                        ▼
      Neo4j                                  SQLite file
   (palace-mcp's existing)               ~/.cache/codebase-memory-
                                         mcp/<slug>.db
```

**Split rule (one line):** Code-as-it-is-written lives in Codebase-Memory. Why/when/who/what-next lives in Graphiti.

### 3.2 Graphiti embedding (product/process layer)

- `graphiti-core` **0.28.2 live-verified** (2026-04-18 verification against 0.4.3 is superseded — re-verify on N+1a Phase 2 Task 1).
- In-process Python import inside `palace-mcp`. No separate Graphiti service.
- Backend: existing palace-mcp Neo4j container. No second DB.
- `group_id = "project/<slug>"` — matches established convention.
- **Embedder:** OpenAI `text-embedding-3-small` (1536 dims). User has $11.20 prepaid credit (~500+ years at our projected volume). Privacy trade-off accepted (ingest content is project-internal dev data).
- **LLM:** `None`. Use `add_triplet(source, edge, target)` exclusively — structured writes, no entity extraction. No `add_episode` for now.
- **Cross-encoder:** `None`. Defer to search-quality tuning slice.

### 3.3 Codebase-Memory embedding (code layer)

- Vendored binary via docker-compose profile `code-graph`. Image: `ghcr.io/deusdata/codebase-memory-mcp:v1.x` (pinned; if not published, vendored tar.gz in `vendor/codebase-memory-mcp/`).
- Mounts target project repos read-only (same pattern as `palace-mcp` mounts `/repos/<slug>:ro`).
- SQLite persists to a named Docker volume `codebase-memory-cache`.
- MCP endpoint exposed on internal network; palace-mcp routes `palace.code.*` calls through.
- Auto-index on first connection (`auto_index=true`, configurable limit).

### 3.4 Bridge extractor (our new code)

New extractor under the existing framework (GIM-59):

- **Name:** `codebase_memory_bridge`
- **Schedule:** manual via `palace.ingest.run_extractor` for MVP; automation hooks to git-event wake via GIM-62 async-signal in a followup.
- **Input:** Codebase-Memory MCP via in-container hostname (e.g., `http://codebase-memory:8765/mcp`).
- **Operation:** Incremental, keyed on CM's XXH3 hash per file.
- **Projection rules** (MVP — §4.4):
  - `:Project`, `:Package`, `:Folder`, `:File`, `:Module` → projected 1:1 into Graphiti with `cm_id` external ref, `provenance="asserted"`.
  - `:Function`/`:Method`/`:Class`/`:Interface`/`:Enum`/`:Type` → `:Symbol{kind=...}` in Graphiti (summary only — name, kind, file_path, signature; no body, no call-tree — those live in CM and are fetched via `palace.code.get_code_snippet`).
  - `:Route` → `:APIEndpoint` with method/path/handler_symbol_id.
  - CM edges `DEFINES`, `IMPORTS`, `CALLS` → projected as Graphiti edges (same names) with `confidence=1.0`, `provenance="asserted"`.
  - CM `MEMBER_OF` (Louvain) → Graphiti `:ArchitectureCommunity` nodes with `:MEMBER_OF` edges, `provenance="derived"`, `extractor="codebase_memory.louvain"`, `confidence` from Louvain modularity score.
  - CM `FILE_CHANGES_WITH` co-change top-5% → `:Hotspot` nodes with `:LOCATES_IN` edges to `:File`, `provenance="derived"`, `confidence` from normalized co-change frequency.
- **Skip from projection** (remain in CM only, accessed via pass-through):
  - `THROWS`, `READS`, `WRITES`, `HTTP_CALLS`, `ASYNC_CALLS`, `USES_TYPE`, `IMPLEMENTS`, `INHERITS`, `USAGE`, `TESTS`, raw call-chains — too high-volume, low-product-value to duplicate.
- **Metadata envelope** on every projected node/edge: `confidence`, `provenance`, `extractor`, `extractor_version`, `evidence_ref`, `observed_at`, plus Graphiti-native `valid_at` / `invalid_at` / `expired_at` on edges.

### 3.5 Heartbeat extractor refactor

Existing `heartbeat` (GIM-59) currently writes to raw Neo4j. Refactor to:

- Implement new `BaseExtractor` that accepts `graphiti: Graphiti` ctx instead of `driver: AsyncDriver`.
- Write `:Episode{kind="heartbeat", source="extractor.heartbeat", observed_at, duration_ms}` via Graphiti `add_triplet`.
- Serves as reference implementation for "how an extractor writes to Graphiti."

### 3.6 N+0 paperclip extractor removal

Delete (confirmed disposable by operator 2026-04-24):

- `services/palace-mcp/src/palace_mcp/ingest/paperclip.py`
- `services/palace-mcp/src/palace_mcp/ingest/paperclip_client.py`
- `services/palace-mcp/src/palace_mcp/ingest/transform.py`
- `services/palace-mcp/src/palace_mcp/ingest/runner.py`
- `services/palace-mcp/src/palace_mcp/ingest/__init__.py` (if empty after above)
- Associated `palace.memory.lookup` filtering on `:Issue`/`:Comment` (MCP tool remains but its domain signature changes — documented in §5).
- Tests referencing the removed extractor.

## 4. Schema

### 4.1 Entities in Graphiti (Neo4j via graphiti-core)

Core (from §5.2, retained):

| Entity | Source of truth | Key properties |
|---|---|---|
| `:Project` | Graphiti | slug, name, language, framework, repo_url, root_path |
| `:Iteration` | Graphiti | number, kind (`full`/`incremental`), from_commit_sha, to_commit_sha, commit_count, started_at, ended_at, label |
| `:Decision` | Graphiti | text, scope, tags[], author, decided_at, status |
| `:IterationNote` | Graphiti | iteration_ref, text, tags[], created_at |
| `:Finding` | Graphiti | severity, category, text, file_ref, line, reviewer, source (`static`/`llm`/`hybrid`) |
| `:Module` | Graphiti (projected) | name, path, kind — CM has detail under same name |
| `:File` | Graphiti (projected) | path, hash, loc, cm_id |
| `:Symbol` | Graphiti (projected) | name, kind (`function`/`method`/`class`/`interface`/`enum`/`type`), signature, file_path, cm_id |
| `:APIEndpoint` | Graphiti (projected from CM `:Route`) | method, path, handler_symbol_ref, cm_id |
| `:Model` | Graphiti | name, fields (JSON), db_table (optional) |
| `:Repository` | Graphiti | name, entity_ref, storage_kind |
| `:ExternalLib` | Graphiti | name, version, category |

New (from brainstorm + research):

| Entity | Purpose |
|---|---|
| `:Episode` | First-class event node for any ingest-observable happening (extractor run, heartbeat, git push, agent decision). Replaces the ambiguous "iteration = ingest run" framing from §5.2.1. |
| `:ArchitectureCommunity` | Derived from CM Louvain modularity. Represents an algorithmically detected module cluster. `provenance="derived"`. |
| `:Commit` | sha, message, author, committer, committed_at — N+1c writes this via `git_events_extractor`. |
| `:PR` | number, title, merged_at, merge_commit_sha — N+1c. |
| `:TestCase` | id, name, file_ref, covered_symbol_refs — followup slice. |
| `:BuildRun` | id, ci_system, status, started_at, ended_at, url — followup slice. |
| `:Contract` | kind (`openapi`/`grpc`/etc.), version, source_file_ref, detected_by — followup. |
| `:Owner` | entity (person or agent), role — N+1c aggregates from commit authors. |
| `:Hotspot` | file_ref, score, reason (`co_change`/`complexity`/`churn`), computed_at — derived. |
| `:Trace` | agent_id, task_ref, started_at, ended_at, outcome — paperclip-agent reasoning chain. |
| `:TraceStep` | trace_ref, step_number, tool_called, result, thought (optional) — under Trace. |

Domain concept axis (from §5.4 — **loaded, but not populated in N+1a**; populated progressively by future domain-aware extractors):

- Core: `:HandlesData`, `:HandlesText`, `:HandlesTime`, `:HandlesAmount`, `:HandlesHex`, `:HandlesFile`, `:HandlesNetwork`, `:HandlesError`, `:HandlesCredentials`, `:HandlesUnit`
- Wallet overlay: `:HandlesAddress`, `:HandlesCrypto`, `:HandlesChain`, `:HandlesToken`, `:HandlesMnemonic`, `:HandlesNonce`, `:HandlesGas`
- Healthcare overlay: `:HandlesPatient`, `:HandlesPrescription`, `:HandlesMedicalCard`, `:HandlesMedication`, `:HandlesDose`, `:HandlesKit`, `:HandlesAllergy`, `:HandlesProcedure`
- Capability axis: `:Encodes`, `:Decodes`, `:Validates`, `:Formats`, `:Signs`, `:Hashes`, `:Parses`, `:Fetches`, `:Caches`, `:Transforms`, `:Renders`, `:Authenticates`, `:Authorizes`, `:Observes`, `:Subscribes`, `:Navigates`, `:Persists`, `:Synchronizes`

These are Neo4j multi-labels on `:Symbol` nodes. **Taxonomy YAML files stay in `config/taxonomies/` per §5.4.1**, loaded at extractor init; N+1a bootstraps the loader but attaches zero labels (no domain-aware extractor in this slice).

### 4.2 Edges in Graphiti

Structural (projected from CM):

| Edge | Source → Target | Cardinality |
|---|---|---|
| `:CONTAINS` | `:Project` → `:Package` → `:Folder` → `:File` | 1:N tree |
| `:DEFINES` | `:File` → `:Symbol` | 1:N |
| `:DEFINES_METHOD` | `:Class` → `:Method` (as `:Symbol{kind=method}`) | 1:N |
| `:CALLS` | `:Symbol` → `:Symbol` | N:M |
| `:IMPORTS` | `:File` → `:Module` (or `:ExternalLib`) | N:M |
| `:MEMBER_OF` | `:Symbol` → `:ArchitectureCommunity` | N:M (a symbol can be in communities at multiple levels) |
| `:HANDLES` | `:APIEndpoint` → `:Symbol` (handler) | 1:1 with `confidence` |

Product/process (from §5.3 + new):

| Edge | Source → Target | Cardinality |
|---|---|---|
| `:CONCERNS` | `:Decision` / `:Finding` / `:IterationNote` → `:Module` / `:File` / `:Symbol` / `:APIEndpoint` | N:M |
| `:INFORMED_BY` | `:Decision` → `:Finding` / `:IterationNote` / `:Trace` | N:M |
| `:INVALIDATED_BY` | `:Decision` → `:Decision` | N:1 (via Graphiti bi-temporal) |
| `:APPLIES_TO` | `:Decision` → `:DomainConcept` (on `:Symbol`) / `:Module` | N:M |
| `:RESOLVES` | `:PR` → `:Issue` (when Issue entity lands in followup) / `:Finding` | N:M |
| `:TOUCHES` | `:Commit` / `:PR` → `:File` / `:Symbol` | N:M (KGCompass chain) |
| `:MODIFIES` | `:Commit` → `:File` / `:Symbol` | N:M with `lines_added` / `lines_removed` |
| `:INCLUDES` | `:PR` → `:Commit` | 1:N |
| `:OWNS` | `:Owner` → `:File` / `:Module` | N:M with `ownership_fraction` |
| `:COVERED_BY` | `:Symbol` → `:TestCase` | N:M |
| `:LOCATES_IN` | `:Hotspot` → `:File` / `:Module` | 1:1 |
| `:TRACED_AS` | `:Decision` → `:Trace` | 1:N |
| `:HAS_STEP` | `:Trace` → `:TraceStep` | 1:N |
| `:SIMILAR_TO` | `:Symbol` ↔ `:Symbol` | N:M (pre-computed via embedding cos-sim > 0.85) |
| `:ALIAS_OF` | alias → `:DomainConcept` | N:1 |

### 4.3 Metadata envelope on every node and edge

Following OntoKG property-vs-edge routing and MemOS MemCube envelope:

**Intrinsic properties** (node attributes, "what is this"):
- `uuid: str` — Graphiti-managed.
- `group_id: str = "project/<slug>"`.
- `name: str`.
- `labels: list[str]` — Graphiti multi-label support.
- Type-specific properties (see §4.1 tables).

**Metadata envelope** (every node AND every edge):
- `confidence: float ∈ [0, 1]` — 1.0 for asserted AST facts; Louvain-modularity score for derived community edges; text-match probability for inferred; heuristic score otherwise.
- `provenance: Literal["asserted", "derived", "inferred"]`. **Asserted** = from AST/tree-sitter static analysis (includes CM projections). **Derived** = from algorithm over asserted facts (Louvain, BFS, co-change). **Inferred** = from LLM or heuristic pattern match (none in N+1a — reserved for future domain extractors).
- `extractor: str` — e.g., `"codebase_memory@v1.x"`, `"git_events@0.1"`, `"heartbeat@0.1"`.
- `extractor_version: str` — pinned version tag used at write time.
- `evidence_ref: list[str]` — pointers to originating data: `["cm:func-abc123", "git:sha123", "paperclip:issue-74"]`.
- `observed_at: datetime` — when the extractor first saw this fact.

**Bi-temporal** (edges only, Graphiti-native):
- `valid_at: datetime` — world-time start of validity.
- `invalid_at: datetime | None` — world-time end. `None` means currently valid.
- `expired_at: datetime | None` — transaction-time when superseded.
- `created_at: datetime` — ingest time.

### 4.4 Live in Codebase-Memory (SQLite, not duplicated in Graphiti)

Full detailed AST layer, accessed via `palace.code.*` pass-through — not projected, no duplication:

- All 16 CM edge types (CALLS, HTTP_CALLS, ASYNC_CALLS, IMPORTS, CONTAINS_*, DEFINES, DEFINES_METHOD, IMPLEMENTS, INHERITS, USES_TYPE, USAGE, THROWS, READS, WRITES, HANDLES, TESTS, FILE_CHANGES_WITH, MEMBER_OF).
- Node detail: body, complexity, decorators, receivers, return types, full call-tree.
- Infrastructure-as-code indexing (Dockerfiles, K8s, Kustomize).

The bridge-extractor writes **summaries** of a subset of these (§3.4 projection rules) into Graphiti. Agents fetch details via CM MCP tools.

## 5. API

### 5.1 Read — `palace.memory.*` (Graphiti layer)

- `palace.memory.health()` → counts per entity type in Graphiti, last bridge-extractor run metadata, staleness warning if last run > 2× expected interval.
- `palace.memory.lookup(entity_type: str, filters: dict, project: str | None) → list[Entity]` — direct lookup. Filter fields validated per entity schema; unknown filters surface in `warnings` (GIM-37 pattern).
- `palace.memory.semantic_search(...)` — **N+1b, not this slice**. Signature reserved: `q, top_k=10, project, filters={layer, node_types}, budget={max_hops, max_tokens, max_edges}`.
- `palace.memory.find_context_for_task(...)` — **N+1c or later**. §5.6 retrieval pipeline.

### 5.2 Read — `palace.code.*` (pass-through to Codebase-Memory MCP)

Thin router in palace-mcp that forwards to CM MCP and returns unchanged:

- `palace.code.search_graph(name_pattern, label, qn_pattern, ...)`
- `palace.code.trace_call_path(function_name, direction, depth)`
- `palace.code.query_graph(cypher)` — CM's Cypher-like subset.
- `palace.code.detect_changes()` — git diff impact.
- `palace.code.get_architecture()` — single call returning languages, packages, entry points, routes, hotspots, boundaries, layers, clusters.
- `palace.code.get_code_snippet(qualified_name)` — source body for a symbol.
- `palace.code.search_code(pattern)` — text search (graph-augmented grep).
- `palace.code.manage_adr(...)` — CM's ADR storage. **Scope decision:** palace-mcp's `:Decision` is authoritative; CM's ADR tool stays enabled for direct agent use but bridge-extractor does **not** sync it back (to avoid round-trip authority confusion). Revisit if dual-authoritative becomes a real problem.

### 5.3 Write — `palace.ingest.*`

Existing:
- `palace.ingest.run_extractor(name, project, ...args)`
- `palace.ingest.list_extractors()`

After N+1a:
- `heartbeat` — writes `:Episode` in Graphiti (reference impl).
- `codebase_memory_bridge` — projects from CM SQLite → Graphiti per §3.4.

Removed:
- No direct `palace.ingest.paperclip` (that was the N+0 test extractor).

### 5.4 Deprecated / breaking for this slice

- **`palace.memory.lookup` on `:Issue` / `:Comment` / `:Agent` filters** — these entity types are removed with the N+0 paperclip extractor. MCP tool surface stays; a filter for a removed entity type returns `{error: "unknown entity type", warnings: [...]}`. No backwards-compat shim.
- **`services/palace-mcp/src/palace_mcp/ingest/paperclip*.py`** — deleted.
- **Tests referencing removed entities** — deleted or rewritten against Graphiti schema.

## 6. Phasing

N+1a is this slice. N+1b and N+1c are separate followup slices tracked after this lands.

### 6.1 N+1a (this slice)

Acceptance gates in §7.

- Task 1 — Re-verify graphiti-core 0.28.x API against live import (supersedes `reference_graphiti_core_api_truth.md` 2026-04-18).
- Task 2 — Add `graphiti-core` + pinned version to `services/palace-mcp/pyproject.toml`. Build `build_graphiti(settings) → Graphiti` factory + `ensure_graphiti_schema()` on startup.
- Task 3 — Define all entity types from §4.1 as Pydantic models per Graphiti custom-entity-type pattern. Include metadata-envelope fields.
- Task 4 — Define all edge types from §4.2 as Pydantic edge models. Wire bi-temporal.
- Task 5 — Update `BaseExtractor` in `services/palace-mcp/src/palace_mcp/extractors/base.py` to accept `graphiti: Graphiti` ctx instead of `driver: AsyncDriver`. Deprecate direct driver access.
- Task 6 — Refactor `heartbeat` extractor to write `:Episode` via Graphiti.
- Task 7 — Remove N+0 paperclip extractor (§3.6) + associated tests + MCP filter paths.
- Task 8 — Add docker-compose profile `code-graph` with codebase-memory-mcp sidecar. Named volume `codebase-memory-cache`. Health probe on CM's MCP endpoint.
- Task 9 — `palace.code.*` router: thin pass-through from palace-mcp → CM MCP over internal network. Schema validation at router boundary.
- Task 10 — `codebase_memory_bridge` extractor per §3.4 projection rules. Start with `:Project/:Package/:Folder/:File/:Symbol/:APIEndpoint/:ArchitectureCommunity/:Hotspot` + corresponding edges. Incremental via CM's XXH3 hash + our own last-seen timestamp.
- Task 11 — Unit tests per §7.1.
- Task 12 — Integration tests per §7.2.
- Task 13 — CI job `palace-mcp-graphiti-tests` wired; add to required checks on develop (same pattern as `watchdog-tests` via GIM-70).
- Task 14 — Update `services/palace-mcp/README.md` with new architecture diagram + quickstart + `palace.code.*` tool list.
- Task 15 — iMac live smoke per §7.3.

**Estimated scope:** 1500–1800 LOC product (Python + docker-compose) + ~800–1000 LOC tests. **Bridge extractor ≈ 500 LOC**, Graphiti schema defs ≈ 400 LOC, router + config ≈ 300 LOC, rest is docker/wiring/removals.

### 6.2 N+1b (followup slice, after N+1a merges)

`palace.memory.semantic_search` with CLAUSE-style budget control + Mem0-style multi-signal fusion (vector + BM25 + entity-boost). Routes over Graphiti's `search()` and optionally over CM's `search_graph`. ~400 LOC.

### 6.3 N+1c (followup slice)

`git_events_extractor` — reads git-mcp (GIM-54), writes `:Commit`, `:PR`, `:Owner` with `:TOUCHES`/`:MODIFIES`/`:INCLUDES`/`:OWNS`. Scans commit messages with `^GIM-\d+` regex to link `:Commit` → `:Decision` via `:INFORMED_BY`. Computes `:Hotspot` from git co-change + complexity (cross-referencing CM's `FILE_CHANGES_WITH`). ~600–800 LOC.

### 6.4 Out of N+1 scope, explicitly deferred

- ACE Generator-Reflector-Curator self-improvement.
- MAGMA multi-graph separation into multiple Neo4j DBs.
- Cross-encoder / reranker for search.
- Domain-concept taxonomy population (requires concrete symbol labels; no extractor attaches them in N+1a).
- `:UIComponent` / `:APIEndpoint` domain-level extraction (N+2+).
- Windows platform for codebase-memory-mcp (iMac / Linux only).
- CM's ADR tool bidirectional sync with `:Decision`.

## 7. Tests and acceptance

### 7.1 Unit tests

- `test_graphiti_schema_bootstrap` — asserts all 22+ entity labels and 16+ edge types have Neo4j constraints + indexes after `ensure_graphiti_schema()`.
- `test_entity_types_pydantic_validation` — each entity Pydantic model accepts required fields, rejects shadowed base fields (`uuid`, `name`, `group_id`, `labels`, `created_at`, `summary`, `attributes`, `name_embedding` — per verified-API rules).
- `test_metadata_envelope_on_all_edges` — every edge creation path (projection, heartbeat, API) sets `confidence`, `provenance`, `extractor`, `extractor_version`, `observed_at`.
- `test_bridge_projection_rules` — given a fixture CM SQLite with known nodes/edges, assert projection picks only §3.4-listed facts, skips the others.
- `test_bridge_louvain_derived_confidence` — Louvain `:MEMBER_OF` edges carry `confidence` = normalized modularity score.
- `test_paperclip_extractor_removed` — import of old paperclip modules raises `ModuleNotFoundError`.
- `test_heartbeat_writes_episode` — one tick produces one `:Episode` node with correct metadata.
- `test_code_router_passthrough` — each of 8 `palace.code.*` tools forwards args and returns CM response unchanged.

### 7.2 Integration tests

Fixture: `testcontainers-neo4j` for Graphiti backend + `codebase-memory-mcp` binary as subprocess pointed at a canned sandbox git repo (3 Python files + 1 Go file + 1 Dockerfile, under `tests/fixtures/sandbox-repo/`).

- `test_bridge_full_run` — runs `codebase_memory_bridge` on sandbox repo end-to-end; asserts non-zero counts for `:File`, `:Symbol`, `:Module`, `:ArchitectureCommunity`; asserts each node carries metadata envelope; asserts `cm_id` set.
- `test_bridge_incremental_rerun` — modify one file in sandbox repo → second run updates only that file's subgraph, previous symbols retain `valid_at` untouched.
- `test_palace_memory_health_post_bridge` — `palace.memory.health()` returns non-zero counts.
- `test_palace_code_tools_live` — each `palace.code.*` MCP call returns valid result on sandbox repo.
- `test_crossref_symbol_to_cm` — a `:Symbol` in Graphiti's `cm_id` resolves via `palace.code.get_code_snippet` and returns matching source body.
- `test_heartbeat_episode_flow` — scheduled heartbeat tick → Graphiti contains `:Episode` with matching `observed_at`.

### 7.3 Live acceptance on iMac

1. `docker compose --profile code-graph up -d` → palace-mcp + neo4j + codebase-memory-mcp all healthy.
2. `palace.ingest.run_extractor codebase_memory_bridge --project gimle` → non-zero stats, no errors.
3. `palace.memory.lookup Symbol {name: "build_graphiti"}` → returns at least one row with `cm_id` populated.
4. `palace.code.trace_call_path function_name="build_graphiti" direction="inbound"` → returns call chain.
5. `palace.memory.lookup ArchitectureCommunity {}` → returns at least one community with members.
6. `palace.code.get_architecture` → returns structured `{languages, packages, entry_points, routes, hotspots, ...}`.
7. Watchdog health per GIM-63 — bridge-extractor run does not produce new errors in `~/.paperclip/watchdog.err`.
8. Claude Code external MCP connection (via `/Users/ant013/Android/Gimle-Palace` project) can invoke both `palace.memory.*` and `palace.code.*` tools successfully.

All 8 live-smoke items must pass before Phase 4.2 merge. QA Phase 4.1 evidence comment references the specific commit SHA and includes paste of all 8 tool-call responses.

## 8. Observability

- Extractor framework stats already write `:IngestRun` + `:Extractor` nodes per GIM-59 substrate. Bridge-extractor runs record: `nodes_written_by_type: dict`, `edges_written_by_type: dict`, `cm_source_hash: str`, `duration_ms: int`.
- Health tool surfaces: oldest staleness, bridge-run error count (last 24 h), CM index freshness (from CM's `index_status`).
- No new metrics dashboard in this slice. Existing palace-mcp logs suffice.

## 9. Security

- Codebase-Memory binary is SLSA 3 + signed; we vendor a pinned tag or pin a Docker image digest. Do not auto-update.
- CM mounts target repos **read-only** (same pattern as `palace.git.*`).
- CM's MCP endpoint exposed on docker internal network only; no host port bind unless debugging.
- OpenAI embedder API key stored in `.env` (gitignored) — same pattern as `PAPERCLIP_API_KEY` / `NEO4J_PASSWORD`.
- Graphiti has no auth layer of its own; relies on Neo4j credentials + palace-mcp API boundary. No change from current state.

## 10. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Codebase-Memory project stagnates or changes licensing | Low | MIT irrevocable, 1800+ stars critical mass. Vendor pinned binary, bridge abstracts schema. Escape: fork, or incrementally move critical capabilities into Neo4j. |
| graphiti-core 0.28.x breaks on minor-version bump | Medium | Thin wrapper isolates Graphiti API; pin exact patch; re-verify on each bump. Prior N+1a revert (2026-04-18) teaches: **never trust memory of API shape — verify against live import every time**. |
| SQLite file corruption on CM side | Low | CM uses WAL; rebuilds from source in minutes; Graphiti contains important projections independently. |
| Neo4j storage bloat from metadata envelope | Low | Projections are summaries only (no bodies, no sub-ms-grained edges). Estimated ≤ 50K nodes per project vs ~2M in CM for a large repo. |
| Embedder cost explodes | Very low | OpenAI 3-small at $0.02/1M; full Gimle ≈ 107K tokens; backfill ≈ $0.002. $11.20 prepaid covers decades. |
| Privacy / ingest content leaks to OpenAI | Accepted | User explicitly approved trade-off 2026-04-24; ingest is project-internal dev data. Escape for sensitive future projects: switch embedder to Ollama `nomic-embed-text` (adapter already built-in to graphiti). |
| Dual authority on ADRs (CM `manage_adr` vs `:Decision`) | Medium | Graphiti `:Decision` is authoritative. CM's ADR tool stays callable but bridge does not sync. If operator starts using CM's ADRs in practice, revisit with a followup slice. |
| Bridge-extractor lag between CM index and Graphiti | Low | Manual trigger for MVP; staleness surfaced in `palace.memory.health`. N+1c may add git-event auto-trigger. |
| Linux / macOS-only CM binary blocks Windows operators | Accepted | No Windows target in Gimle plan (per `reference_feature_branch_flow.md` operator env). |

## 11. References

### 11.1 Our existing artifacts

- `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` — §5 is the primary source for entity/edge taxonomy and faceted multi-label model.
- `docs/research/agent-context-store-2026-04/` — outline + fields + 15 JSON files + awareness list.
- `docs/superpowers/specs/2026-04-21-GIM-63-agent-watchdog-design.md` — format reference.
- `docs/superpowers/plans/2026-04-24-GIM-63-agent-watchdog-plan.md` — plan format reference.
- Memory: `reference_graphiti_core_api_truth.md` (2026-04-18, **superseded — re-verify in Phase 2 Task 1**).
- Memory: `project_n1_brainstorm_paused.md` (2026-04-17, **resolved by this spec**).

### 11.2 External — Codebase-Memory MCP

- Paper: Vogel et al., *Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP*, arXiv:2603.27277, 2026-03-28.
- Repo: https://github.com/DeusData/codebase-memory-mcp (MIT, 1809 stars at design time).
- MCP tool surface: 14 tools, 66 languages, SQLite-backed, sub-ms queries, zero LLM.

### 11.3 External — Graphiti

- Repo: https://github.com/getzep/graphiti (graphiti-core 0.28.x, MCP server v1.0 Nov 2025).
- Entity Types guide: https://blog.getzep.com/entity-types-structured-agent-memory/
- Zep paper (LongMemEval baseline): arXiv:2501.13956.

### 11.4 External — steal-pattern inspirations

- OntoKG (intrinsic-vs-relational routing): arXiv:2604.02618.
- KGCompass (issue-to-symbol chain): arXiv:2503.21710.
- MAGMA (multi-axis edges): arXiv:2601.03236.
- LiCoMemory (top-down retrieval): arXiv:2511.01448.
- CLAUSE (budget-aware retrieval): arXiv:2509.21035.
- Cognee (Pydantic Custom Graph Models): https://github.com/topoteretes/cognee.
- neo4j-labs/agent-memory (ReasoningTrace schema): https://github.com/neo4j-labs/agent-memory.
- ACE (GRC self-improvement — followup): arXiv:2510.04618.
- MemOS (MemCube metadata envelope): arXiv:2505.22101.
- Mem0 (rejected as substrate; multi-signal fusion stolen for N+1b): https://github.com/mem0ai/mem0.

### 11.5 Predecessor merges on develop (design-time state)

- `67d42dc` — GIM-71 ruff-format (develop tip at spec write).
- `ed0195a` — GIM-70 required checks (branch protection enforces `watchdog-tests` + `github-scripts-tests`).
- `053d93f` — GIM-63 agent watchdog.
- `068014f` — GIM-62 async-signal dispatcher.
- `c0a6bcb` — GIM-59 extractor framework substrate (this slice extends it).
- `7bdc302` — GIM-53 multi-project `group_id`.
- `85be40e` — GIM-54 git-mcp read-only tools.
