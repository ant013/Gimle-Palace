---
slug: extractor-symbol-index-foundation
status: rev1 (Board-ratified D1-D9 from pre-extractor-foundation decisions)
branch: feature/extractor-symbol-index-foundation
paperclip_issue: TBD
predecessor: 4bdccb4 (develop tip after GIM-99 release-cut-v2 merge)
date: 2026-04-27
parent_initiative: N+2 Extractor cycle — first foundation slice
related: GIM-100 (multi-language research, ratified D1-D9), GIM-77 (bridge extractor pattern)
---

# Extractor Symbol Index Foundation + Python (foundation slice + first real extractor)

## Goal

Ship the **shared substrate for all future extractors** plus the **first real content extractor** (Python via scip-python), validated end-to-end on Gimle-Palace's own Python codebase. After this slice merges:

- All N+2 Cat 2..N+6 extractors build on stable schemas (`:SymbolOccurrence`, `:ExternalDependency`, `:EvictionRecord`)
- `palace.code.find_references(qualified_name)` returns precise file/line/col occurrences for indexed Python symbols, hot-path latency < 50 ms
- Tantivy sidecar operational; Neo4j hybrid query routing in place
- Memory-bounded layer (importance + tier defaults + 3-phase bootstrap + eviction + graceful degradation) live and observable

This is the **foundation slice** — schemas + infrastructure + one validating extractor in a single PR. Subsequent slices (Slice 102+) add scip-typescript / scip-kotlin / swift-symbolkit / palace-scheme generators with ~2-3 day cadence each.

## Sequence

First slice in N+2 Extractor cycle (post-Cat 1 USE-BUILT). Predecessor: develop tip `4bdccb4` after GIM-99 release-cut-v2 merge. No code dependencies; full architectural foundation built here.

## Hard dependencies

- Decisions D1-D9 ratified (this slice's `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md`)
- ResearchAgent + Opus reviews on GIM-100 — done (NUDGE verdict, Findings 1-5 addressed in this spec)
- graphiti-core 0.28.2 — pinned (per ADR TRADEOFFS)
- Neo4j 5.26 + DeusData CM v0.6 — running

## Non-goals (defer to subsequent slices)

- **scip-typescript / scip-kotlin / swift-symbolkit integration** — Slice 102 (TS/JS), Slice 103 (Kotlin/Swift mobile)
- **Solidity / FunC / Anchor custom palace-scheme generators** — Slices 110+ (greenfield, requires custom AST parsing)
- **`palace.code.semantic_search`** — Slice 5 deferred from N+2 Cat 1
- **Vulnerability `:CVE` enrichment** — separate slice, requires CVE database integration
- **GDS PageRank background reconciliation** — followup; CMS approximation acceptable for v1
- **Cross-project `:BRIDGES_TO` edges** (SKIE / IDL / declare_id!) — modeled in schema but not populated until cross-language extractors land
- **Multi-machine export tooling** — backlog
- **Replacing graphiti-core with sidecar v1.0** — deferred per ADR TRADEOFFS

## Architecture

### Component overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    palace-mcp (Python / FastMCP)                 │
│                                                                  │
│  palace.code.find_references (NEW composite tool)                │
│    1. search_graph for resolved Symbol qualified_name            │
│    2. tantivy_session.search(symbol_id) → occurrences            │
│    3. add :EvictionRecord warning if applicable                  │
│                                                                  │
│  extractors/symbol_index.py — first real content extractor       │
│    - Reads SCIP index files produced by scip-python              │
│    - Parses SCIP protobuf → SymbolOccurrence records             │
│    - Writes :Symbol nodes to Graphiti + occurrences to Tantivy   │
│                                                                  │
│  extractors/foundation/                                          │
│    models.py        — Pydantic models                            │
│    importance.py    — score formula + CMS utility                │
│    tier_classifier.py — file path → tier_weight regex            │
│    tantivy_bridge.py — Tantivy session/writer/searcher           │
│    eviction.py      — 3-round Cypher eviction policy             │
│    config.py        — Settings extensions (env vars)             │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
            Neo4j (Graphiti)         Tantivy sidecar (embedded)
            :Symbol                  SymbolOccurrence docs
            :ExternalDependency      Fields: symbol_id, repo_id,
            :EvictionRecord                  file_path, line, col,
            [:CALLS], [:USES], etc.          role, language,
                                             importance, commit_sha
```

### Pydantic schemas

`services/palace-mcp/src/palace_mcp/extractors/foundation/models.py` — defines:

- `Language` enum: PYTHON, JAVASCRIPT, TYPESCRIPT, KOTLIN, SWIFT, RUST, SOLIDITY, FUNC (TON), ANCHOR (Solana)
- `SymbolKind` enum: DEF, DECL, USE, ASSIGN, IMPL
- `SymbolOccurrence` Pydantic model with all fields stored in Tantivy: symbol_id (u64), repo_id, file_path, line, col_start, col_end, role, language, commit_sha, importance (f32). Field validators ensure col_end ≥ col_start.
- `Ecosystem` enum: NPM, CARGO, PYPI, MAVEN, COCOAPODS, SWIFT, GEM, GENERIC, GITHUB
- `SourceType` enum: REGISTRY, GIT, PATH, VENDOR, BINARY
- `ExternalDependency` model: purl (PURL ECMA-427), ecosystem (discriminator), canonical_name, resolved_version (nullable), source_type, registry_url, integrity_hash, license, git_url, git_ref, group_id (Graphiti scoping)
- `EvictionRecord` model: symbol_qualified_name, first_evicted_at, last_evicted_at, total_evicted, eviction_round (Literal["vendor_uses", "inactive_user_uses", "assigns"]), project

All models with mypy strict, Pydantic v2.

### Tantivy field schema (parallel to Pydantic)

```
symbol_id:     FAST + INDEXED (u64)
repo_id:       FAST + INDEXED (u64)
file_path:     TEXT + STORED
line:          FAST + INDEXED (u32)
col_start:     FAST (u16)
col_end:       FAST (u16)
role:          FAST + INDEXED (u8 enum)
language:      FAST + INDEXED (u8 enum)
commit_sha:    STORED
importance:    FAST (f32)
```

Per-document size estimate: 80-120 B compressed. 50M docs ≈ 4-6 GB on disk.

### Importance score formula (D4)

`services/palace-mcp/src/palace_mcp/extractors/foundation/importance.py` exports `importance_score()`:

```
importance = clamp(
    0.35 × log1p(cms_in_degree) / log1p(100)   # centrality (CMS-approximated)
  + 0.30 × tier_weight                          # 1.0 user / 0.5 first-party / 0.1 vendor
  + 0.20 × kind_weight                          # def=1.0, decl=0.8, impl=0.7, assign=0.5, use=0.3
  + 0.10 × exp(-days_since_last_seen / 30.0)   # recency half-life 30d
  + 0.05 × language_weight                      # primary lang=1.0, others=0.7
, 0.0, 1.0)
```

Components:
- `tier_weight()`: regex match against vendor patterns (`node_modules/`, `vendor/`, `.cargo/registry/`, `site-packages/`, `__pycache__/`, `.build/`, `Pods/`, `_vendor/`, `third_party/`) → 0.1 if vendor; first-party regex (`libs/`, `generated/`, `gen/`, `target/generated/`) → 0.5; else → 1.0 (user)
- `KIND_WEIGHT`: dict mapping SymbolKind enum → float (def=1.0, decl=0.8, impl=0.7, assign=0.5, use=0.3)
- `language_weight()`: 1.0 if matches primary repo language (most common file extension), else 0.7
- `recency_decay()`: `exp(-days / half_life)`; half_life=30 days default

### Count-Min Sketch

`CountMinSketch` class with width=300, depth=7 (2100 cells, ~8 KB for u32). Uses `hashlib.blake2b` for hash family. Methods: `increment(key)`, `estimate(key)` returns upper bound. 1% error / 99.9% confidence per Cormode-Muthukrishnan analysis. CMS state is in-process; on container restart, bootstrap from Neo4j: `MATCH (o:SymbolOccurrence) WHERE o.kind='use' RETURN o.symbol_fqn, count(o) LIMIT 1000000`.

### Tantivy bridge

`services/palace-mcp/src/palace_mcp/extractors/foundation/tantivy_bridge.py`:

`TantivyBridge` class with:
- `open()` — initializes schema (10 fields above), opens index at configured path, creates writer with `heap_size_in_bytes`
- `add(occurrence: SymbolOccurrence)` — appends to write buffer
- `commit()` — flushes write buffer (auto-triggers segment flush when heap_size hit)
- `search_by_symbol_id(symbol_id, limit)` — term query, returns list of doc dicts
- `close()` — final commit + cleanup

Uses `tantivy-py` FFI (Rust library). Single writer / multiple readers per Tantivy semantics. Embedded — no separate service. Index path configurable via `PALACE_TANTIVY_INDEX_PATH` env var (default: `/var/lib/palace/tantivy`).

### 3-round eviction policy

`services/palace-mcp/src/palace_mcp/extractors/foundation/eviction.py` — 3 Cypher constants:

**Round 1 (vendor uses):**
```cypher
MATCH (o:SymbolOccurrence)
WHERE o.importance < 0.2 AND o.kind = 'use' AND o.tier_weight <= 0.1
WITH o ORDER BY o.importance ASC, o.last_seen_at ASC
LIMIT $batch_size
WITH collect(o) AS to_delete
UNWIND to_delete AS o
DETACH DELETE o
RETURN size(to_delete) AS deleted_count
```

**Round 2 (inactive user uses):**
```cypher
MATCH (o:SymbolOccurrence)
WHERE o.importance < 0.4 AND o.kind = 'use'
  AND o.last_seen_at < datetime() - duration({days: 90})
WITH o ORDER BY o.importance ASC LIMIT $batch_size
... (same structure)
```

**Round 3 (assigns):**
```cypher
MATCH (o:SymbolOccurrence)
WHERE o.importance < 0.3 AND o.kind = 'assign'
... (same structure)
```

`run_eviction_pass(driver, max_total, batch_size=100_000)` — async function loops rounds 1→2→3 until count ≤ max_total OR all rounds exhausted. After each batch, writes `:EvictionRecord` via `RECORD_EVICTION` Cypher with MERGE on `(symbol_qualified_name, project)`.

**NEVER auto-evict `kind=def` or `kind=decl`** (codified — no Cypher in module touches them).

### Configuration extensions

Extend `services/palace-mcp/src/palace_mcp/config.py` Settings class with 5 new env vars (default values target iMac 64 GB / 32 GB ceiling):

- `palace_max_occurrences_total: int = 50_000_000`
- `palace_max_occurrences_per_project: int = 10_000_000`
- `palace_importance_threshold_use: float = 0.05`
- `palace_max_occurrences_per_symbol: int = 5_000`
- `palace_recency_decay_days: float = 30.0`

Plus Tantivy:
- `palace_tantivy_index_path: str = "/var/lib/palace/tantivy"`
- `palace_tantivy_heap_mb: int = 100`

### Python extractor (scip-python)

`services/palace-mcp/src/palace_mcp/extractors/symbol_index.py` — `SymbolIndexPython(BaseExtractor)` with:

- `name = "symbol_index_python"`, description, no constraints/indexes (managed by foundation)
- Constructor takes `TantivyBridge`; constructs internal `CountMinSketch`
- `extract(ctx)` flow:
  1. Run scip-python via async subprocess (use `asyncio.create_subprocess_exec` per existing pattern in `graphiti_runtime.py:_detect_slice_id`); produces `index.scip` protobuf file
  2. Parse SCIP protobuf → list of `_ScipSymbol` dataclasses (use `scip-protobuf-py` library or generate Python bindings from `.proto`)
  3. **First pass:** build CMS by counting USE occurrences per symbol_string
  4. **Phase 1 ingest:** filter symbols where `kind ∈ (DEF, DECL)`; for each, compute importance and write `:Symbol` to Graphiti + `SymbolOccurrence` to Tantivy
  5. Check current Tantivy doc count; if `< 0.5 × max_occurrences_total`, proceed Phase 2
  6. **Phase 2 ingest:** filter symbols where `kind=USE` AND `importance >= threshold_use`; same dual-write pattern
  7. Phase 3 only on machines where budget remaining (i.e., Phase 2 didn't fill); same pattern with vendor symbols allowed
  8. `tantivy_bridge.commit()` at end

Returns `ExtractorStats` with phase counts in `details`.

### `palace.code.find_references` composite tool

Add to `services/palace-mcp/src/palace_mcp/code_composite.py`:

```python
@tool_decorator("palace.code.find_references", _DESC_FIND_REFERENCES)
async def palace_code_find_references(
    qualified_name: str,
    project: str | None = None,
    max_results: int = 100,
) -> dict[str, Any]:
    ...
```

Algorithm:
1. Capture session: `code_router.get_cm_session()` (TOCTOU-safe per GIM-98 D17)
2. Validate via Pydantic (qualified_name charset, max_results 1..1000)
3. `search_graph(qn_pattern=f".*{re.escape(qualified_name)}$", label="Function|Method", limit=2)` for disambiguation
4. 0 results → `error_code="symbol_not_found"`; >1 → `error_code="ambiguous_qualified_name"` envelope
5. Compute `symbol_id = hash(resolved_qn) & 0xFFFFFFFF`
6. `tantivy_bridge.search_by_symbol_id(symbol_id, limit=max_results+1)` → list of occurrences
7. Truncated detection (rows > max_results)
8. Query `:EvictionRecord` for resolved_qn; if exists → add `warning: "partial_index"`, `eviction_note`, `coverage_pct`
9. Return envelope with `occurrences`, `requested_qualified_name`, `qualified_name`, `total_found`, `truncated`, `coverage_pct?`

`_DESC_FIND_REFERENCES` description includes: "Returns precise positional occurrences (file/line/col). For Python/JS/TS/Kotlin/Swift/Rust real-time queries, prefer Serena LSP. Use this tool for cross-project aggregates and smart contract languages."

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Pydantic models in `extractors/foundation/models.py` (Language/SymbolKind/Ecosystem/SourceType enums + SymbolOccurrence/ExternalDependency/EvictionRecord); unit tests | PE | — |
| 2 | Count-Min Sketch utility + tests (collision rate measurement on synthetic 70M-symbol stream; verify <5% over-estimate at 1M actual) | PE | T1 |
| 3 | Importance score formula + tests (verify weights normalize correctly; verify tier_weight regex catches all 9 vendor patterns; recency decay shape) | PE | T1, T2 |
| 4 | Tantivy bridge module (open/add/commit/search/close); add `tantivy-py>=0.22` to pyproject.toml | PE | T1 |
| 5 | docker-compose.yml: add `palace-tantivy-data` named volume mounted into palace-mcp container at `/var/lib/palace/tantivy` | PE | — |
| 6 | 3-round eviction Cypher module + tests (mock Neo4j driver; verify ordering, batch size, never deletes def/decl, EvictionRecord MERGE behavior) | PE | T1 |
| 7 | Settings extensions (7 new env vars: MAX_OCCURRENCES_*, IMPORTANCE_THRESHOLD_USE, RECENCY_DECAY_DAYS, TANTIVY_INDEX_PATH, TANTIVY_HEAP_MB); validation tests | PE | — |
| 8 | scip-python CLI integration probe; verify `scip-python index --output` round-trip on Gimle-Palace's own Python codebase produces a valid `index.scip` file. Document install: `npm i -g @sourcegraph/scip-python` | PE | — |
| 9 | SCIP protobuf parser → `_ScipSymbol` records; tests against real `index.scip` from T8 | PE | T8 |
| 10 | `SymbolIndexPython` extractor full impl (3-phase bootstrap, CMS-enforced sampling, Tantivy + Graphiti dual-write); unit tests with mock SCIP data + integration test with real scip-python output | PE | T1-T9 |
| 11 | `palace.code.find_references` composite MCP tool registered in `code_composite.py`; integration test via `streamablehttp_client` (real MCP wire-contract per GIM-91) | PE | T4, T10 |
| 12 | Documentation: CLAUDE.md updated with new env vars + tantivy data volume + Phase 1/2/3 bootstrap explanation; README symbol-index extractor section | PE | T1-T11 |
| 13 | Mechanical CR Phase 3.1: full `ruff check && mypy src/ && pytest` output, scope audit, anti-rubber-stamp checklist | CR | T11, T12 |
| 14 | Adversarial Opus Phase 3.2: review against Findings 1-5 from GIM-100 Opus review (composite uniqueness, RESOLVES_TO mapping, memory estimate, SCIP↔ExternalDependency mapping, Hybrid escape detail) | Opus | T13 |
| 15 | QA Phase 4.1 live smoke on iMac: docker stack up --build --wait; run `palace.ingest.run_extractor("symbol_index_python", "gimle")`; verify Symbol nodes count, Tantivy doc count, `palace.code.find_references("register_code_tools")` returns ≥1 occurrence with proper file/line/col | QA | T14 |
| 16 | Phase 4.2 squash-merge — CTO only (per GIM-94 D1) | CTO | T15 |

### Task 10 detail: SymbolIndexPython implementation

PE follows TDD on per-language scip-python integration. Key sub-deliverables:

- Run `scip-python index` on Gimle-Palace itself → produce `services/palace-mcp/.scip/index.scip`
- Parse SCIP protobuf → `_ScipSymbol` records (use `scip-protobuf-py` library or generate from .proto file via `protoc`)
- Phase 1 ingest (defs/decls): writes ~500-1000 Symbol nodes for Gimle-Palace
- Phase 2 ingest (uses with importance threshold 0.05): writes ~5K-15K SymbolOccurrence records (estimated based on local CM index showing 5333 nodes / 9399 edges for Gimle-Palace)
- CMS verifies in-degree estimates correlate with actual Cypher count for top-100 symbols (collision rate < 5%)

### Task 11 detail: find_references wire-contract test

```python
# tests/integration/test_palace_code_find_references_wire.py
async def test_find_references_dogfood(mcp_url):
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.code.find_references", arguments={
                "qualified_name": "register_code_tools",
                "project": "repos-gimle",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert payload["occurrences"], "register_code_tools is referenced from tests + bootstrap"
            for occ in payload["occurrences"]:
                assert "file_path" in occ
                assert occ["line"] >= 1
```

### Task 15 detail: QA Phase 4.1 evidence template

```
## Phase 4.1 — QA PASS ✅

### Evidence
1. Commit SHA tested: <git rev-parse HEAD on FB>
2. docker compose --profile review ps — palace-mcp + neo4j containers healthy
3. /healthz — {"status": "ok"}
4. palace.ingest.run_extractor("symbol_index_python", "gimle") — succeeds
5. After ingest:
   - MATCH (s:Symbol {language: "python"}) RETURN count(s) — ≥500
   - Tantivy index doc count — ≥5000 (via diagnostic endpoint)
6. palace.code.find_references("register_code_tools") — returns ≥1 occurrence
7. 3-round eviction smoke: temporarily set PALACE_MAX_OCCURRENCES_TOTAL=100;
   re-run extractor; verify pruning happens, EvictionRecord nodes created, query
   response includes "warning": "partial_index"
8. Restored PALACE_MAX_OCCURRENCES_TOTAL=50000000 after test
9. After QA — restore production checkout to develop (per worktree-discipline.md)
```

## Acceptance

1. All 9 ratified decisions (D1-D9) realized in code: SCIP-aligned FQN, Hybrid Tantivy+Neo4j, PURL-based ExternalDependency schema, importance score formula, tier-aware defaults, 3-phase bootstrap, 3-round eviction, graceful degradation warnings, Serena complementary scope (Python/JS/TS/Kotlin/Swift/Rust use sampling).
2. Tantivy sidecar operational; integrated into palace-mcp via tantivy-py FFI; data persisted at `/var/lib/palace/tantivy`.
3. Pydantic models (SymbolOccurrence, ExternalDependency, EvictionRecord) in `extractors/foundation/models.py`; full type coverage with mypy strict.
4. Importance score formula matches D4 weights (0.35/0.30/0.20/0.10/0.05); Count-Min Sketch handles 70M+ symbols at ~2 MB RAM with measured collision rate < 5% on synthetic stream.
5. 3-round eviction Cypher executes correctly on full data: vendor uses → inactive user uses → assigns; never deletes def/decl; writes EvictionRecord per evicted batch.
6. Configuration env vars (PALACE_MAX_OCCURRENCES_TOTAL=50000000 default for iMac, etc.) read by Settings; tier-appropriate values documented.
7. SCIP-python integration: `scip-python index` produces valid `.scip` file on Gimle-Palace codebase; protobuf parser extracts ≥500 Python `:Symbol` definitions and ≥5K user-code occurrences after Phase 1+2 ingest.
8. 3-phase bootstrap works: Phase 1 (defs+decls only) completes within 60s on Gimle-Palace; Phase 2 conditional on remaining budget; Phase 3 skipped on small machines.
9. `palace.code.find_references(qualified_name)` returns occurrences with `{file_path, line, col_start, col_end}` for indexed symbols; latency p95 < 50 ms on 5K-occurrence corpus.
10. Graceful degradation: when EvictionRecord exists for queried symbol, response includes `warning: "partial_index"` + `coverage_pct`; integration test verifies.
11. CMS-enforced per-symbol cap (`PALACE_MAX_OCCURRENCES_PER_SYMBOL=5000`): test simulating 10K occurrences for one symbol persists ≤5000 with random sampling.
12. Hard circuit breaker: extractor aborts ingestion with `error_code: budget_exceeded` when live count exceeds 1.1× MAX during a single run.
13. MCP wire-contract test (per GIM-91): `palace.code.find_references` callable via real `streamablehttp_client`, returns valid envelope.
14. Pattern #21 dedup-aware registration: `palace.code.find_references` appears in `tools/list` exactly once.
15. CLAUDE.md updated with new env vars + tantivy data volume documentation.
16. CR Phase 3.1 + Opus Phase 3.2 reviews passed; QA Phase 4.1 live smoke green on iMac.

## Out of scope (defer)

- **JavaScript / TypeScript extractor** — Slice 102 (scip-typescript)
- **Kotlin / Swift extractors** — Slice 103 (scip-kotlin / swift-symbolkit)
- **Solidity / FunC / Anchor custom palace-scheme generators** — Slices 110+
- **Cross-language `:BRIDGES_TO` edges** — populated by language-specific extractors as they land
- **GDS PageRank background reconciliation** — followup; CMS approximation acceptable for v1
- **`palace.code.semantic_search`** — Slice 5 deferred from N+2 Cat 1
- **Multi-machine export tooling** — backlog
- **`palace.code.churn_summary` and similar metrics composites** — separate slice after symbol+occurrence data lands
- **Background scheduler for periodic eviction** — manual trigger via `palace.ops.run_extractor` is sufficient for v1

## Decisions recorded (this rev)

All 9 decisions from `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md` (D1-D9) realized in this slice. No new architectural decisions added at this rev.

Implementation-level details from Opus Phase 3.2 (GIM-100) review applied:

| Opus Finding | Where applied |
|---|---|
| F1 sha256 uid → composite constraint | D3 spec; Pydantic `:ExternalDependency` model uses Neo4j composite unique constraint, no hash-uid |
| F2 RESOLVES_TO edge for Cargo multi-version | Resolved version is on `:ExternalDependency` node; multiple resolved versions = multiple nodes (per PURL identity); no separate RESOLVES_TO edge |
| F3 Memory estimate omits index overhead | Tier defaults table includes 1.2× index overhead in calculation |
| F4 SCIP↔ExternalDependency mapping | Mapping documented in models.py docstring + `models.Ecosystem` enum maps 1:1 to SCIP `manager` field |
| F5 Hybrid escape hatch detail | This spec IS the detail — Tantivy boundary, query routing, consistency model all defined |
| Minor: neo4j-admin import production caveat | Neo4j writes use UNWIND MERGE (production), not offline import |
| Minor: FQN stability across versions | symbol_id hashed from full SCIP symbol string (includes version); version bump = new symbol_id; tombstoning via `last_seen_at` |
| Minor: `ton` ecosystem effectively empty | Documented in D9 + Ecosystem.GENERIC fallback for FunC contract deps |

## Open questions

None at design time. If CR or Opus surface issues during Phase 3, apply rev2 before paperclip Phase 2 starts.

## References

- `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md` — D1-D9 ratified decisions (this commit)
- `docs/superpowers/research/2026-04-27-multi-language-foundation-design.md` — ResearchAgent autonomous output (GIM-100, commit `3d5b5db`)
- `/tmp/voltagent_research/q2_scale_findings.md` — voltagent independent track Q2 (Hybrid recommendation)
- `/tmp/voltagent_research/q3_dependencies_findings.md` — voltagent independent track Q3 (PURL ECMA-427)
- `/tmp/voltagent_research/memory_bounded_index_findings.md` — bounded-memory algorithms research
- `paperclip-shared-fragments@1c76fa9/fragments/compliance-enforcement.md` — Phase 4.2 CTO-only + anti-rubber-stamp + MCP wire-contract test rule
- `paperclip-shared-fragments@1c76fa9/fragments/phase-handoff.md` — handoff matrix
- ECMA-427 Package URL specification (December 2025)
- SCIP proto: github.com/sourcegraph/scip/blob/main/scip.proto
- Tantivy docs: docs.rs/tantivy
- GIM-77 — bridge extractor pattern (precedent for dual-write Neo4j+other)
- GIM-89 — `_OpenArgs` open-schema for `palace.code.*` passthroughs
- GIM-91 — MCP wire-contract test rule
- GIM-94 — Phase 4.2 CTO-only rule
- GIM-100 — multi-language foundation research (predecessor)
