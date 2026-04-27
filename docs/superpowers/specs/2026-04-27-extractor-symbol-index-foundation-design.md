---
slug: extractor-symbol-index-foundation
status: rev2 (26 multi-reviewer findings applied; ratified D1-D9 unchanged at decision level)
branch: feature/extractor-symbol-index-foundation
paperclip_issue: TBD
predecessor: 4bdccb4 (develop tip after GIM-99 release-cut-v2 merge)
date: 2026-04-27
parent_initiative: N+2 Extractor cycle — first foundation slice
related: GIM-100 (multi-language research, ratified D1-D9), GIM-77 (bridge extractor pattern)
---

# Extractor Symbol Index Foundation + Python (foundation slice + first real extractor)

## Goal

Ship the **shared substrate for all future extractors** plus the **first real content extractor** (Python via scip-python), validated end-to-end on Gimle-Palace's own Python codebase **plus** synthetic 70M-occurrence stress harness for eviction validation. After this slice merges:

- All N+2 Cat 2..N+6 extractors build on stable schemas (`:Symbol`, `:SymbolOccurrenceShadow`, `:ExternalDependency`, `:EvictionRecord`, `:IngestCheckpoint`)
- `palace.code.find_references(qualified_name)` returns precise file/line/col occurrences from Tantivy hot path; latency p95 < 50 ms (warm cache, no concurrent extraction, ≤ 5K-occurrence corpus)
- Tantivy sidecar operational (embedded via tantivy-py + ThreadPoolExecutor wrapper); shadow-node pattern in Neo4j for eviction bookkeeping
- Memory-bounded layer (importance + tier defaults + 3-phase bootstrap + 3-round eviction + graceful degradation) live and observable

This is the **foundation slice** — schemas + infrastructure + one validating extractor + synthetic stress harness in a single PR. Subsequent slices (Slice 102+) add scip-typescript / scip-kotlin / swift-symbolkit / palace-scheme generators with ~2-3 day cadence each.

## Sequence

First slice in N+2 Extractor cycle (post-Cat 1 USE-BUILT). Predecessor: develop tip `4bdccb4` after GIM-99 release-cut-v2 merge. No code dependencies; full architectural foundation built here.

## Hard dependencies

- Decisions D1-D9 ratified (`docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md`)
- ResearchAgent + Opus reviews on GIM-100 — done (NUDGE verdict, Findings 1-5 addressed in this spec)
- Voltagent independent research (Q2/Q3/memory-bounded) — copied into `docs/research/2026-04-27-symbol-index-foundation/`
- graphiti-core 0.28.2 — pinned (per ADR TRADEOFFS)
- Neo4j 5.26 + DeusData CM v0.6 — running

## Non-goals (defer)

- **scip-typescript / scip-kotlin / swift-symbolkit** — Slice 102 (TS/JS), Slice 103 (Kotlin/Swift mobile)
- **Solidity / FunC / Anchor custom palace-scheme generators** — Slices 110+ (greenfield, custom AST parsing)
- **`palace.code.semantic_search`** — Slice 5 deferred from N+2 Cat 1
- **Vulnerability `:CVE` enrichment** — separate slice
- **GDS PageRank background reconciliation** — followup; CMS approximation acceptable for v1; requires NEO4J_PLUGINS GDS install (not in current docker image)
- **Cross-project `:BRIDGES_TO` edges** — modeled in schema but not populated until cross-language extractors land
- **Multi-machine export tooling** — backlog
- **Replacing graphiti-core with sidecar v1.0** — deferred per ADR TRADEOFFS

## Architecture

### Storage model — shadow-node pattern (Finding #3 fix)

Tantivy is **primary** for `SymbolOccurrence` records (full positional payload, fast term query). Neo4j holds **lightweight `:SymbolOccurrenceShadow` nodes** keyed by `symbol_id` carrying only eviction-relevant properties: `{symbol_id, symbol_qualified_name, importance, kind, tier_weight, last_seen_at, group_id}`. No file_path/line/col in shadow.

Reconciliation invariant: **Tantivy is rebuildable by re-running scip-python; Neo4j shadow is authoritative for eviction policy decisions**. On crash mid-Phase, restart logic re-reads `:IngestCheckpoint`, skips completed phases, re-emits remaining records to both stores. After clean shutdown, both stores are consistent.

Eviction = transactional pair: DETACH DELETE shadow in Neo4j + Tantivy delete-by-symbol_id. If Tantivy delete fails after Neo4j commit, log + retry on next eviction pass; eventual consistency acceptable since shadow already gone (find_references can only access via shadow lookup first).

### Symbol identifier — blake2b deterministic hash (Finding #1 fix)

```python
import hashlib

def symbol_id_for(qualified_name: str) -> int:
    """64-bit deterministic identifier; survives process restart.

    Used at write time (extractor) AND query time (find_references) to bridge
    between Tantivy doc and Neo4j shadow. Same string → same int across runs.
    """
    return int.from_bytes(
        hashlib.blake2b(qualified_name.encode("utf-8"), digest_size=8).digest(),
        "big",
    )
```

Replaces broken `hash(qn) & 0xFFFFFFFF`:
- `hash()` randomized per-process (PYTHONHASHSEED=random) — would silently break index after every container restart
- 32-bit truncation = ~12% birthday collision at 1M symbols, ~100% at 5M

64-bit blake2b: collision risk negligible for our scale (10⁹ docs would need 5×10⁹ trials). Used identically at both write and query sites; integration test verifies restart-survivability.

### scip-python integration — pre-generated `.scip` accept (Finding #5 fix)

Container does NOT install npm + scip-python. Instead:
- Operator generates `.scip` index outside container: `npx @sourcegraph/scip-python index --output index.scip`
- `.scip` file path passed via `Settings.palace_scip_index_path` env var OR upload via MCP tool argument to `palace.ingest.run_extractor`
- Container reads protobuf-encoded `.scip` file, no npm trust required, no supply-chain surface

Removes: npm dependency, lockfile-pin requirement, --ignore-scripts flag, multi-stage Dockerfile. v2 (when automation needed) can revisit Option (a) multi-stage approach.

### SCIP parser library — `pip install scip` (Finding #4 fix)

Use Sourcegraph's official Python package: https://pypi.org/project/scip/ (verified exists). Provides pre-generated `scip_pb2.py` Python protobuf bindings. Decode .scip file via standard `scip_pb2.Index.FromString(data)`. **DoS protection (Finding #20):**

```python
import scip.scip_pb2 as scip_pb2

def parse_scip_file(path: Path, max_size_mb: int = 500, timeout_s: int = 60) -> scip_pb2.Index:
    if path.stat().st_size > max_size_mb * 1024 * 1024:
        raise ValueError(f".scip file exceeds {max_size_mb} MB cap")
    # google.protobuf >=4.25 ships recursion-depth limit (DoS fix); pin in pyproject
    # wallclock timeout via signal.alarm or asyncio.wait_for at caller
    return scip_pb2.Index.FromString(path.read_bytes())
```

Pin `protobuf>=4.25` in pyproject.toml.

### Tantivy bridge — sync FFI wrapped in ThreadPoolExecutor (Finding #6 fix)

```python
from concurrent.futures import ThreadPoolExecutor
import asyncio

class TantivyBridge:
    def __init__(self, index_path: Path, heap_size_mb: int = 100) -> None:
        self.index_path = index_path
        self.heap_size = heap_size_mb * 1024 * 1024
        # Single-thread executor preserves Tantivy single-writer semantics
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tantivy")
        self._index = None
        self._writer = None

    async def add_async(self, occ: SymbolOccurrence) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._add_sync, occ)

    async def commit_async(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._commit_sync)

    async def search_by_symbol_id_async(self, symbol_id: int, limit: int = 1000) -> list[dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._search_sync, symbol_id, limit
        )
```

`heap_size_mb` regulates write merge buffer; 5GB index mmap'ed via OS page cache is separate concern (Finding #26). Specify `user: "1000:1000"` in docker-compose for tantivy volume + non-root USER in Dockerfile + ownership check on startup with fail-fast on corruption (Finding #19).

### Importance score — `collections.Counter` for in-degree (Finding #10 fix)

CMS w=300/d=7 has 0.91% × N additive error → fails at tail symbols (Zipf distribution: 99.999% of vocabulary has true count < 634K when N=70M, so error overwhelms signal). Replace with bounded-vocab structure:

```python
from collections import Counter
import heapq

class BoundedInDegreeCounter:
    """Exact counter for top-K symbols by in-degree; bounded memory.

    For 1M distinct symbols: ~12 MB (Counter dict). Bounded vocabulary —
    probabilistic data structure not warranted.
    """

    def __init__(self, max_entries: int = 1_000_000) -> None:
        self._counter: Counter[str] = Counter()
        self._max = max_entries

    def increment(self, qn: str) -> None:
        self._counter[qn] += 1
        if len(self._counter) > self._max:
            # Evict 10% lowest-count entries
            evict_n = self._max // 10
            cutoff = heapq.nsmallest(evict_n, self._counter.values())[-1]
            for k in [k for k, v in self._counter.items() if v <= cutoff]:
                del self._counter[k]

    def estimate(self, qn: str) -> int:
        return self._counter.get(qn, 0)

    def to_disk(self, path: Path) -> None:
        """Persist on shutdown — survives restart (Finding #2 fix)."""
        import pickle
        path.write_bytes(pickle.dumps(dict(self._counter)))

    def from_disk(self, path: Path) -> None:
        import pickle
        if path.exists():
            self._counter = Counter(pickle.loads(path.read_bytes()))
```

Persistence path: `<tantivy_index_path>/in_degree_counter.pkl`. Loaded on extractor startup, saved after each ingest run.

Drops broken Cypher-based bootstrap query (which would return 0 rows since occurrences live in Tantivy not Neo4j).

### Importance score formula — clamp note (Finding #11 fix)

```python
def importance_score(...) -> float:
    """Compute importance ∈ [0, 1].

    NOTE: centrality term `0.35 × log1p(in_degree) / log1p(100)` is unbounded
    above for in_degree > 100; clamp to [0, 1] absorbs overflow. This is
    intentional — popular symbols (vendor stdlib calls) get importance ≈ 1.0
    and are eviction-protected naturally. Documented weights are component
    BUDGETS, not strict ranges.
    """
```

### 3-round eviction — indexed Cypher with batch transactions (Finding #7 + Finding #15 + Finding #17 fix)

`ensure_custom_schema(driver)` async function called on extractor startup creates:

```cypher
-- Composite uniqueness for ExternalDependency (Finding #14: NULL sentinel)
CREATE CONSTRAINT ext_dep_purl_unique IF NOT EXISTS
  FOR (d:ExternalDependency) REQUIRE d.purl IS UNIQUE;

-- EvictionRecord uniqueness
CREATE CONSTRAINT eviction_record_unique IF NOT EXISTS
  FOR (e:EvictionRecord) REQUIRE (e.symbol_qualified_name, e.project) IS UNIQUE;

-- SymbolOccurrenceShadow indexes for eviction predicates
CREATE INDEX shadow_evict_r1 IF NOT EXISTS
  FOR (s:SymbolOccurrenceShadow)
  ON (s.group_id, s.kind, s.importance, s.tier_weight);

CREATE INDEX shadow_evict_r2 IF NOT EXISTS
  FOR (s:SymbolOccurrenceShadow)
  ON (s.group_id, s.kind, s.importance, s.last_seen_at);

-- Symbol disambiguation: indexed qn_suffix for find_references (Finding #13)
CREATE INDEX symbol_qn_suffix IF NOT EXISTS
  FOR (s:Symbol) ON (s.qn_suffix);

-- Optional: full-text on qualified_name for fuzzy fallback
CREATE FULLTEXT INDEX symbol_qn_fulltext IF NOT EXISTS
  FOR (s:Symbol) ON EACH [s.qualified_name];
```

Eviction Cypher uses `CALL ... IN TRANSACTIONS OF 10000 ROWS` to avoid OOM:

```cypher
-- Round 1: vendor uses
MATCH (s:SymbolOccurrenceShadow)
WHERE s.importance < 0.2 AND s.kind = 'use' AND s.tier_weight <= 0.1
WITH s ORDER BY s.importance ASC, s.last_seen_at ASC LIMIT $batch_size
CALL { WITH s DETACH DELETE s } IN TRANSACTIONS OF 10000 ROWS ON ERROR CONTINUE
RETURN count(*) AS deleted_count
```

Same pattern for Round 2 (inactive user uses, >90 days) and Round 3 (assigns). After each batch returns deleted_count > 0:
1. Tantivy-side: `bridge.delete_by_symbol_ids(ids)` for the same symbol_id set
2. Write `:EvictionRecord` MERGE per evicted batch (constraint-backed, race-safe)

Early-exit when `deleted_count == 0`.

### find_references — exact-match-first + qn_suffix index (Finding #13 fix)

```python
async def palace_code_find_references(qualified_name, project=None, max_results=100):
    cm_session = code_router.get_cm_session()  # TOCTOU-safe per GIM-98 D17
    if cm_session is None:
        handle_tool_error(RuntimeError("CM not started"))
        raise

    # Validate via Pydantic (regex charset, length bounds)
    req = FindReferencesRequest(...)

    # Step 1: try exact match first (uses indexed qualified_name in CM)
    raw = await cm_session.call_tool("search_graph", {
        "project": req.project or _DEFAULT_CM_PROJECT,
        "qn_pattern": f"^{re.escape(req.qualified_name)}$",  # exact
        "label": "Function|Method",
        "limit": 2,
    })
    matches = code_router.parse_cm_result(raw).get("results", [])

    # Step 2: fallback to suffix match if exact miss (slower but covers truncated input)
    if not matches:
        raw = await cm_session.call_tool("search_graph", {
            "project": req.project or _DEFAULT_CM_PROJECT,
            "qn_pattern": f".*\\.{re.escape(req.qualified_name)}$",
            "label": "Function|Method",
            "limit": 2,
        })
        matches = code_router.parse_cm_result(raw).get("results", [])

    if not matches:
        return {"ok": False, "error_code": "symbol_not_found", ...}
    if len(matches) > 1:
        return {"ok": False, "error_code": "ambiguous_qualified_name", "matches": [...]}

    resolved = matches[0]
    sym_id = symbol_id_for(resolved["qualified_name"])  # blake2b, restart-safe

    # Step 3: Tantivy term query (async-wrapped)
    occurrences = await tantivy_bridge.search_by_symbol_id_async(
        sym_id, limit=req.max_results + 1
    )
    truncated = len(occurrences) > req.max_results
    occurrences = occurrences[: req.max_results]

    # Step 4: check :EvictionRecord for warning
    eviction_info = await _query_eviction_record(
        cm_session,
        qualified_name=resolved["qualified_name"],
        project=req.project,
    )

    return {
        "ok": True,
        "requested_qualified_name": req.qualified_name,
        "qualified_name": resolved["qualified_name"],
        "project": req.project,
        "occurrences": occurrences,
        "total_found": len(occurrences) + (1 if truncated else 0),
        "truncated": truncated,
        **(_partial_index_envelope(eviction_info) if eviction_info else {}),
    }
```

`_partial_index_envelope` returns `{"warning": "partial_index", "eviction_note": ..., "coverage_pct": N}`.

### Pydantic schemas (extended)

`services/palace-mcp/src/palace_mcp/extractors/foundation/models.py`:

```python
class SymbolKind(str, Enum):
    DEF = "def"
    DECL = "decl"
    USE = "use"
    ASSIGN = "assign"
    IMPL = "impl"
    EVENT = "event"      # Solidity events (Finding #23)
    MODIFIER = "modifier"  # Solidity modifiers (Finding #23)


class SymbolOccurrence(BaseModel):
    symbol_id: int = Field(..., ge=0, description="blake2b 64-bit hash of canonical FQN")
    repo_id: int = Field(..., ge=0)
    file_path: str = Field(..., min_length=1, max_length=500)
    line: int = Field(..., ge=1)
    col_start: int = Field(..., ge=0, le=65535)
    col_end: int = Field(..., ge=0, le=65535)
    role: SymbolKind
    language: Language
    commit_sha: str = Field(..., min_length=7, max_length=40)
    importance: float = Field(..., ge=0.0, le=1.0)
    synthesized_by: str | None = Field(
        None, max_length=200,
        description="Macro-generated symbols: Rust macro name, Solidity inheritance source, etc.",
    )


class ExternalDependency(BaseModel):
    purl: str = Field(..., min_length=1, max_length=500)
    ecosystem: Ecosystem
    canonical_name: str = Field(..., min_length=1, max_length=200)
    # Sentinel "__unresolved__" used at write time when resolved_version unknown,
    # to satisfy Neo4j composite uniqueness "NULL ≠ NULL" semantics (Finding #14).
    resolved_version: str = Field(..., max_length=100)
    source_type: SourceType
    # ... (other fields unchanged)


class IngestCheckpoint(BaseModel):
    """Re-entrancy marker per Phase per run (Finding #9 fix)."""
    run_id: str = Field(..., min_length=1, max_length=64)
    project: str = Field(..., max_length=100)
    phase: Literal["phase1_defs", "phase2_user_uses", "phase3_vendor_uses"]
    completed_at: datetime
    occurrences_written: int = Field(..., ge=0)


class SymbolOccurrenceShadow(BaseModel):
    """Lightweight Neo4j shadow for eviction policy decisions only.

    Per Finding #3: Tantivy holds full positional payload; Neo4j shadow holds
    only what eviction needs to query.
    """
    symbol_id: int = Field(..., ge=0)
    symbol_qualified_name: str = Field(..., max_length=500)
    importance: float = Field(..., ge=0.0, le=1.0)
    kind: SymbolKind
    tier_weight: float = Field(..., ge=0.0, le=1.0)
    last_seen_at: datetime
    group_id: str = Field(..., max_length=100)
```

### Configuration extensions

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # D5: Memory-bounded extractor configuration
    palace_max_occurrences_total: int = 50_000_000
    palace_max_occurrences_per_project: int = 10_000_000
    palace_importance_threshold_use: float = 0.05
    palace_max_occurrences_per_symbol: int = 5_000
    palace_recency_decay_days: float = 30.0

    # Tantivy
    palace_tantivy_index_path: str = "/var/lib/palace/tantivy"
    palace_tantivy_heap_mb: int = 100  # write merge buffer; not runtime mmap

    # SCIP integration (Finding #5: Option b, no npm in container)
    palace_scip_index_path: str | None = None  # absolute path or None to require per-call

    model_config = SettingsConfigDict(env_prefix="", ...)  # Finding #25: env vars match field names verbatim
```

### Python extractor — re-entrancy + DoS limits

`SymbolIndexPython` flow:
1. Read `palace_scip_index_path` from Settings or per-call argument; verify file size ≤ 500 MB; parse via `scip_pb2.Index.FromString` with timeout 60s
2. Build Counter via first pass (only USE occurrences contribute to in-degree)
3. Check `:IngestCheckpoint` for run; resume from last incomplete phase
4. Phase 1 (defs+decls, always): for each, compute importance, write `:Symbol` to Neo4j + `:SymbolOccurrenceShadow` + Tantivy occurrence
5. Commit Tantivy after Phase 1; write `:IngestCheckpoint{phase=phase1_defs}`
6. Phase 2 (conditional): same for USE with importance ≥ threshold
7. Phase 3 (only on large machines): vendor uses
8. Persist Counter to disk before exit
9. Hard circuit breaker: if shadow count >1.1× MAX_OCCURRENCES_TOTAL during a single run, abort with `error_code: budget_exceeded`

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| **0** | **Replicate D1-D9 to Graphiti via `palace.memory.decide` on iMac (CTO Phase 1.1; Finding #22). Acceptance: 9 `:Decision` nodes returned by `palace.memory.lookup` filtered by tag `n+2-foundation`** | CTO | — |
| 1 | Pydantic models in `extractors/foundation/models.py` (Language/SymbolKind extended/Ecosystem/SourceType enums + SymbolOccurrence with synthesized_by + ExternalDependency + EvictionRecord + IngestCheckpoint + SymbolOccurrenceShadow); unit tests | PE | T0 |
| 2 | `BoundedInDegreeCounter` (replaces CMS); persistence to/from `.pkl`; tests including restart-survivability scenario (Findings #2, #10) | PE | T1 |
| 3 | `symbol_id_for()` blake2b helper; tests including restart-determinism (Finding #1: write-then-restart-then-query asserts non-empty result) | PE | T1 |
| 4 | Importance score formula + tests (verify weights, vendor regex catches all 9 patterns, recency decay shape, clamp behavior documented per Finding #11) | PE | T1, T2, T3 |
| 5 | `TantivyBridge` with ThreadPoolExecutor wrapper; async methods (add_async, commit_async, search_by_symbol_id_async, delete_by_symbol_ids_async); tests with mock executor (Finding #6) | PE | T1 |
| 6 | `ensure_custom_schema(driver)` async function (5 indexes + 2 constraints listed above); tests via testcontainers-neo4j (Findings #7, #15, #17) | PE | T1 |
| 7 | 3-round eviction Cypher module with `CALL ... IN TRANSACTIONS OF 10000 ROWS`; mocked-driver tests verify ordering, batch size, never deletes def/decl, EvictionRecord MERGE behavior (Findings #7, #15) | PE | T1, T6 |
| 8 | Settings extensions (8 new env vars including `palace_scip_index_path`); validation tests; ENV_PREFIX verification (Findings #25) | PE | — |
| 9 | docker-compose.yml: `palace-tantivy-data` named volume with `user: "1000:1000"` mounted at `/var/lib/palace/tantivy`; non-root USER in Dockerfile; startup ownership check with fail-fast (Finding #19) | PE | — |
| 10 | scip-python integration probe: generate `.scip` outside container via `npx @sourcegraph/scip-python`; verify decode via `scip_pb2.Index.FromString` with size + timeout limits (Findings #4, #5, #20) | PE | — |
| 11 | `SymbolIndexPython` extractor full impl (3-phase bootstrap, Counter-enforced sampling, shadow-node + Tantivy dual-write, IngestCheckpoint re-entrancy, hard circuit breaker on 1.1× budget overshoot); unit tests + integration test using real `.scip` file from T10 | PE | T1-T10 |
| 12 | **Synthetic 70M-occurrence stress harness (Finding #20 strategic)**: generator script + acceptance test that runs eviction against 70M synthetic shadow nodes, verifies all 3 rounds fire, EvictionRecord nodes created, Counter cap holds, no event-loop block > 1s during eviction | PE | T1-T7 |
| 13 | `palace.code.find_references` composite MCP tool: blake2b symbol_id, exact-match-first + suffix fallback, EvictionRecord warning, latency < 50ms warm cache; integration test via `streamablehttp_client` (Finding #13) | PE | T3, T5, T11 |
| 14 | `:IngestCheckpoint` write/read + re-entrancy logic in extractor; unit tests cover crash mid-Phase-2 + restart resumes from Phase-3 (Finding #9) | PE | T1, T11 |
| 15 | Documentation: CLAUDE.md updated with new env vars + tantivy data volume + Phase 1/2/3 bootstrap explanation + GDS plugin caveat (Finding #16); README symbol-index extractor section; update spec acceptance #4, #11, #12 with caveats (Finding #11, #12) | PE | T1-T14 |
| 16 | CR Phase 3.1 mechanical review: full `ruff check && mypy src/ && pytest` output, scope audit, anti-rubber-stamp checklist | CR | T15 |
| 17 | Opus Phase 3.2 adversarial review against multi-reviewer Findings 1-26 (each Finding has acceptance evidence in this spec); cross-check schema gaps, supply-chain decisions, falsifiability of QA tests | Opus | T16 |
| 18 | QA Phase 4.1 live smoke on iMac: docker stack up --build --wait; place `index.scip` for Gimle-Palace at configured path; run `palace.ingest.run_extractor("symbol_index_python", "gimle")`; verify Symbol count + Tantivy doc count + `palace.code.find_references("register_code_tools")` returns ≥1 occurrence; restart-survivability test (kill container, restart, query → still works); synthetic eviction harness (T12) is part of unit test green | QA | T17 |
| 19 | Phase 4.2 squash-merge — CTO only (per GIM-94 D1) | CTO | T18 |

### Task 0 detail (Finding #22)

CTO Phase 1.1 invokes `palace.memory.decide` 9 times via MCP tool — once per ratified decision D1-D9 from `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md`. Each call shape:

```python
palace.memory.decide(
    title="<D-N name from decisions doc>",
    body="<full body text>",
    decision_kind="design",
    decision_maker_claimed="board",
    confidence=0.85,
    evidence_ref=[
        "docs/research/2026-04-27-symbol-index-foundation/q2-symbol-occurrence-scale.md",
        "docs/research/2026-04-27-symbol-index-foundation/q3-external-dependency-schema.md",
        "docs/research/2026-04-27-symbol-index-foundation/memory-bounded-index.md",
        "GIM-100",
    ],
    tags=["n+2-foundation", "pre-extractor", "GIM-100-followup"],
    project="gimle",
    slice_ref="GIM-100-ratification",
    attestation="Multi-reviewer (Architect+Python-pro+Security+Performance+Database) "
                "rev1→rev2 round; 26 findings applied",
)
```

CTO acceptance for Phase 1.1:
- `palace.memory.lookup(entity_type="Decision", filters={"tags_any": ["n+2-foundation"]})` returns 9 results
- Each has `decision_maker_claimed=board`, `confidence>=0.7`, evidence_ref non-empty

## Acceptance

1. All 9 ratified decisions D1-D9 realized in code: SCIP-aligned FQN via blake2b symbol_id, Hybrid Tantivy+Neo4j (shadow-node pattern), PURL-based ExternalDependency schema with NULL sentinel, importance score formula with Counter-based in-degree, tier-aware defaults, 3-phase bootstrap, 3-round eviction with batch transactions, graceful degradation via EvictionRecord, Serena complementary scope.
2. Tantivy sidecar operational; integrated via tantivy-py FFI behind ThreadPoolExecutor; data persisted at `/var/lib/palace/tantivy` with non-root user 1000:1000.
3. Pydantic models in `extractors/foundation/models.py`; full mypy strict type coverage; SymbolKind includes EVENT + MODIFIER; SymbolOccurrence has synthesized_by; SymbolOccurrenceShadow defined.
4. `BoundedInDegreeCounter` handles 1M+ distinct symbols at ~12 MB; persistence to disk + load on startup verified; restart-survivability test green.
5. Importance score formula matches D4 weights; clamp absorbs centrality overflow at high in_degree (documented in docstring); recency decay half-life 30 days configurable.
6. `ensure_custom_schema(driver)` creates 7 schema objects (2 constraints + 4 indexes + 1 fulltext); idempotent on re-run.
7. 3-round eviction Cypher uses `CALL ... IN TRANSACTIONS OF 10000 ROWS ON ERROR CONTINUE`; never deletes def/decl; writes EvictionRecord with race-safe MERGE; early-exit on deleted_count=0.
8. Configuration env vars (8 new) read by Settings; tier-appropriate defaults documented; `palace_scip_index_path` Setting allows operator-supplied .scip file.
9. SCIP-python integration: pre-generated `.scip` file decoded via `pip install scip` package; size cap 500 MB; timeout 60s; protobuf>=4.25 pinned.
10. 3-phase bootstrap: Phase 1 (defs+decls only) completes within 60s on Gimle-Palace; Phase 2 conditional on remaining budget; Phase 3 skipped on small machines; IngestCheckpoint enables crash-resume.
11. Synthetic stress harness validates eviction at 70M-occurrence scale: Round 1 fires, Round 2 fires, Round 3 fires when configured pressure; EvictionRecord nodes created per round; event loop never blocks > 1s.
12. `palace.code.find_references(qualified_name)` returns occurrences with `{file_path, line, col_start, col_end}`; latency p95 < 50 ms warm cache, no concurrent extraction, ≤ 5K-occurrence corpus (caveat documented).
13. Graceful degradation: when EvictionRecord exists for queried symbol, response includes `warning: "partial_index"` + `coverage_pct`; integration test verifies presence and accuracy.
14. Hard circuit breaker: extractor aborts ingestion with `error_code: budget_exceeded` when shadow count exceeds 1.1× MAX during a single run.
15. MCP wire-contract test (per GIM-91): `palace.code.find_references` callable via real `streamablehttp_client`, returns valid envelope.
16. Pattern #21 dedup-aware registration: `palace.code.find_references` appears in `tools/list` exactly once.
17. Restart-survivability test: kill container after Phase 1 ingest, restart, query find_references → returns expected occurrences (proves blake2b determinism + IngestCheckpoint resume).
18. CLAUDE.md updated with new env vars + tantivy data volume + Phase 1/2/3 bootstrap + GDS plugin caveat.
19. CR Phase 3.1 + Opus Phase 3.2 reviews passed; QA Phase 4.1 live smoke green on iMac.

## Out of scope (defer)

- **JavaScript / TypeScript extractor** — Slice 102
- **Kotlin / Swift extractors** — Slice 103
- **Solidity / FunC / Anchor custom palace-scheme generators** — Slices 110+
- **Cross-project `:BRIDGES_TO` edges** — populated by language-specific extractors
- **GDS PageRank background reconciliation** — followup; requires `NEO4J_PLUGINS=["graph-data-science"]` install
- **`palace.code.semantic_search`** — Slice 5 deferred from N+2 Cat 1
- **Multi-machine export tooling** — backlog
- **`palace.code.churn_summary` and similar metrics composites** — separate slice
- **Background scheduler for periodic eviction** — manual trigger via `palace.ops.run_extractor`
- **CMS poisoning mitigation** (Finding #18) — single-tenant operator mode; revisit if multi-tenant
- **scip-python multi-stage Dockerfile (Option a)** — v1 uses Option (b) pre-generated .scip; v2 if automation needed

## Decisions recorded (rev2)

All 9 decisions from `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md` (D1-D9) realized. Rev1→rev2 changes are implementation-level corrections from multi-reviewer round, NOT new architectural decisions:

| Finding | Severity | Where applied |
|---|---|---|
| 1. blake2b deterministic symbol_id | CRITICAL | symbol_id_for() helper, write+read sites |
| 2. CMS persistence (drop Neo4j bootstrap query) | CRITICAL | BoundedInDegreeCounter + .pkl persistence |
| 3. Storage-location resolved (shadow-node pattern) | CRITICAL | Architecture section + SymbolOccurrenceShadow model |
| 4. SCIP parser via `pip install scip` (real package) | CRITICAL | Task 10 + parse_scip_file() |
| 5. Pre-generated .scip via Settings (no npm in container) | CRITICAL | palace_scip_index_path Setting + Option b |
| 6. TantivyBridge ThreadPoolExecutor async wrapper | CRITICAL | TantivyBridge async methods |
| 7. Eviction indexes + IN TRANSACTIONS | HIGH | ensure_custom_schema + Cypher with CALL...IN TRANSACTIONS |
| 8. Slice scope (Option β single + synthetic harness Task 12) | HIGH | Task 12 added |
| 9. IngestCheckpoint + reconciliation invariant | HIGH | Task 14 + Architecture §Storage model |
| 10. Counter replaces CMS | MEDIUM | BoundedInDegreeCounter |
| 11. Clamp documented for centrality overflow | MEDIUM | importance_score() docstring |
| 12. Latency caveat (warm cache, no concurrent) | MEDIUM | Acceptance #12 |
| 13. exact-match-first + qn_suffix index | MEDIUM | find_references + ensure_custom_schema |
| 14. ExternalDependency NULL sentinel | MEDIUM | resolved_version required + sentinel write convention |
| 15. EvictionRecord composite uniqueness | MEDIUM | ensure_custom_schema CREATE CONSTRAINT |
| 16. GDS plugin caveat documented | MEDIUM | Out-of-scope + CLAUDE.md update |
| 17. ensure_custom_schema function | MEDIUM | Task 6 |
| 18. CMS poisoning vector | LOW | Out-of-scope (single-tenant); revisit multi-tenant |
| 19. Tantivy volume ownership | MEDIUM | Task 9 (user 1000:1000 + non-root + ownership check) |
| 20. protobuf DoS limits | MEDIUM | parse_scip_file() with size+timeout caps |
| 21. /tmp file rot | HIGH | docs/research/2026-04-27-symbol-index-foundation/ in PR |
| 22. palace.memory.decide replication Task | HIGH | Task 0 (CTO Phase 1.1) |
| 23. Smart contract SymbolKind extensions | HIGH | EVENT + MODIFIER + synthesized_by added now |
| 24. _ScipSymbol shape | MEDIUM | Resolves with #4 (pip install scip schema) |
| 25. Settings env_prefix | LOW | Settings model_config explicit |
| 26. Tantivy heap_mb misnomer | LOW | Architecture comment + docstring |

## Open questions

Replacing rev1's premature "None at design time":

1. **`pip install scip` upstream stability.** Sourcegraph publishes the package but minor versions may change generated protobuf. Pin in pyproject; if breaks, fallback to codegen via `protoc` against scip.proto.
2. **Tantivy schema versioning.** When SymbolKind enum adds Solidity event/modifier in Slice 110+, existing Tantivy index has u8-encoded role enum that no longer matches. Need migration strategy: re-index from .scip OR carry old enum mapping forward. Decide before Slice 110.
3. **scip-python invocation outside container — operator UX.** Operator must remember to run `npx scip-python index --output .scip` before triggering ingest. Should we add a `palace.ops.scip_index(repo_path)` helper that shells out for them? Or accept manual workflow? Defer to v2 unless friction surfaces.
4. **EvictionRecord re-fire semantics.** When an evicted symbol's occurrences are re-ingested (extractor re-run), should EvictionRecord be cleared, or kept as historical signal? Current spec: keeps as historical (lifetime via last_evicted_at). Verify QA expectations.
5. **Counter persistence corruption.** If pickle file corrupts, Counter restarts empty → first ingest writes inflated importance scores. Recovery: validate on load (length sanity check), fall back to empty if invalid. Defer fancy recovery to v2.
6. **Restart-survivability for partially evicted symbols.** If eviction completes mid-batch (only Round 1 ran), shadow nodes deleted but Tantivy delete pending. Next startup: detect orphan Tantivy docs (no matching shadow), clean up. Defer "tantivy garbage collection" to v2 unless QA hits actual orphans.

## References

- `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md` — D1-D9 ratified decisions
- `docs/research/2026-04-27-symbol-index-foundation/q2-symbol-occurrence-scale.md` — voltagent track Q2 (Hybrid recommendation)
- `docs/research/2026-04-27-symbol-index-foundation/q3-external-dependency-schema.md` — voltagent track Q3 (PURL ECMA-427)
- `docs/research/2026-04-27-symbol-index-foundation/memory-bounded-index.md` — bounded-memory algorithms
- `feature/research-multi-language-foundation/docs/superpowers/research/2026-04-27-multi-language-foundation-design.md` — ResearchAgent autonomous output (GIM-100, commit `3d5b5db`)
- `paperclip-shared-fragments@1c76fa9/fragments/compliance-enforcement.md` — Phase 4.2 CTO-only + anti-rubber-stamp + MCP wire-contract test rule
- `paperclip-shared-fragments@1c76fa9/fragments/phase-handoff.md` — handoff matrix
- ECMA-427 Package URL specification (December 2025)
- SCIP proto: github.com/sourcegraph/scip/blob/main/scip.proto
- `pip install scip` package: pypi.org/project/scip/
- Tantivy docs: docs.rs/tantivy
- GIM-77 — bridge extractor pattern (precedent for dual-write Neo4j+other)
- GIM-89 — `_OpenArgs` open-schema for `palace.code.*` passthroughs
- GIM-91 — MCP wire-contract test rule
- GIM-94 — Phase 4.2 CTO-only rule
- GIM-100 — multi-language foundation research (predecessor)
