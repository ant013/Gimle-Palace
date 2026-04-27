---
slug: 101a-extractor-foundation
status: rev3a (split from earlier rev2; 26 round-2 findings applied)
branch: feature/101a-extractor-foundation
paperclip_issue: GIM-101
predecessor: 4bdccb4 (develop tip after GIM-99 release-cut-v2 merge)
date: 2026-04-27
parent_initiative: N+2 Extractor cycle — first foundation slice (split from earlier monolithic spec)
related: GIM-100 (multi-language research, ratified D1-D9), 101b (Python extractor — depends on 101a merge)
---

# Slice 101a — Extractor Foundation + Synthetic Stress Harness

## Goal

Ship the **shared substrate for all future extractors** + **synthetic 70M-occurrence stress harness** validating the foundation end-to-end **without requiring any real-language extractor**. After 101a merges, all subsequent slices (101b Python, 102 TS/JS, 103 Kotlin/Swift, 110+ smart contracts) build on stable schemas, deterministic identifiers, async-safe Tantivy bridge, idempotent eviction, and graceful-degradation guarantees that have been proven against synthetic 70M-occurrence load.

This is the **falsifiable foundation slice** — schema + infrastructure validated against synthetic stress, no real extractor. Slice 101b adds the first real content extractor (Python via scip-python) on the merged substrate.

## Sequence

First slice in N+2 Extractor cycle. Predecessor: develop tip `4bdccb4` after GIM-99 release-cut-v2 merge. **Hard gate before 101b.**

## Hard dependencies

- Decisions D1-D9 ratified (`docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md`)
- ResearchAgent + Opus reviews on GIM-100 — done
- 26 multi-reviewer findings round 2 — applied (see Decisions section)
- graphiti-core 0.28.2 — pinned
- Neo4j 5.26 + DeusData CM v0.6 — running

## Non-goals (defer)

- **scip-python integration / SymbolIndexPython extractor** — Slice 101b
- **palace.code.find_references composite tool** — Slice 101b
- **scip-typescript / scip-kotlin / swift-symbolkit** — Slices 102/103
- **Solidity / FunC / Anchor custom palace-scheme generators** — Slices 110+
- **GDS PageRank background reconciliation** — followup; requires NEO4J_PLUGINS install
- **Multi-machine export tooling** — backlog

## Architecture

### Storage model — shadow-node pattern + reconciliation invariant

Tantivy is **primary** for `SymbolOccurrence` records. Neo4j holds lightweight `:SymbolOccurrenceShadow` nodes keyed by `symbol_id`: `{symbol_id, symbol_qualified_name, importance, kind, tier_weight, last_seen_at, group_id, schema_version}`.

**Strict ordering invariant for dual-write (Architect F1, Silent-failure F2):**

```
Phase boundary commit sequence (per phase):
  1. tantivy.add_document(...) for all phase records
  2. tantivy.commit_async() — REQUIRED to succeed before next step
  3. neo4j MERGE all :SymbolOccurrenceShadow nodes (idempotent on symbol_id)
  4. neo4j MERGE :IngestCheckpoint{phase, expected_doc_count, run_id} (only after 1+2+3 ack'd)
```

If step 2 fails → no shadow writes, no checkpoint → restart re-runs phase from scratch (idempotent). If step 3 fails after step 2 succeeded → no checkpoint → restart re-runs phase, MERGE on shadow is idempotent, Tantivy idempotent via primary-key uniqueness (see Tantivy schema below). If step 4 fails after 2+3 succeeded → no checkpoint → same recovery path.

**Reconciliation invariant**: Tantivy is rebuildable by re-running scip-python; Neo4j shadow is authoritative for eviction policy decisions; IngestCheckpoint is the source of truth for "this phase is complete in BOTH stores."

### Symbol identifier — blake2b → signed i64 (Python-pro F-A fix)

```python
import hashlib

def symbol_id_for(qualified_name: str) -> int:
    """64-bit deterministic identifier; signed i64 range; survives process restart.

    Byte order: big-endian (network order). All language bindings (future Kotlin,
    Swift, Rust extractors per Slice 102+) MUST use big-endian + signed-i64
    interpretation when reimplementing this function, or cross-language
    symbol_id joins (e.g. via :BRIDGES_TO edges) will silently produce zero
    matches.
    """
    raw = int.from_bytes(
        hashlib.blake2b(qualified_name.encode("utf-8"), digest_size=8).digest(),
        "big",
    )
    # Reinterpret as signed i64 (two's complement) — Tantivy stores integer
    # fast fields as i64 (Python-pro Finding F-A); raw u64 overflows on ~50%
    # of hashes.
    return raw if raw < 2**63 else raw - 2**64
```

Pydantic constraint: `symbol_id: int = Field(..., ge=-(2**63), le=2**63 - 1)`.

### Tantivy schema with primary-key uniqueness (Silent-failure F4 + F6 fixes)

```
schema_version:  FAST + INDEXED (u8) — for forward compat (Slice 110+ enum extension)
doc_key:         TEXT + STORED + INDEXED — primary key: f"{symbol_id}:{file_path}:{line}:{col_start}"
symbol_id:       FAST + INDEXED (i64, signed)
repo_id:         FAST + INDEXED (i64)
file_path:       TEXT + STORED
line:            FAST + INDEXED (u32)
col_start:       FAST (u16)
col_end:         FAST (u16)
role:            FAST + INDEXED (u8 enum, see Symbol kind table)
language:        FAST + INDEXED (u8 enum)
commit_sha:      STORED
importance:      FAST (f32)
ingest_run_id:   STORED — for reconciliation
```

**Write semantics: delete-by-doc_key + add (Silent-failure F4):** every Tantivy write deletes any prior doc with same `doc_key` then adds new one. Prevents duplicates after Phase rerun on crash. tantivy-py supports `writer.delete_term(Term(doc_key))` then `writer.add_document(...)`.

**schema_version current = 1.** Slice 110+ that extends SymbolKind enum bumps to 2; queries include `WHERE schema_version >= MIN_SUPPORTED` filter.

### TantivyBridge — async-safe with explicit lifecycle (Python-pro F-F fix)

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tantivy

class TantivyBridge:
    """Async wrapper with explicit lifecycle. Use as async context manager."""

    def __init__(self, index_path: Path, heap_size_mb: int = 100) -> None:
        self.index_path = index_path
        self.heap_size = heap_size_mb * 1024 * 1024
        self._executor: ThreadPoolExecutor | None = None
        self._index = None
        self._writer = None

    async def __aenter__(self) -> "TantivyBridge":
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tantivy")
        await self._open_async()
        return self

    async def __aexit__(self, exc_type, exc_val, tb) -> None:
        try:
            if self._writer is not None and exc_type is None:
                await self._commit_async()
        finally:
            await self._close_async()
            if self._executor is not None:
                self._executor.shutdown(wait=True)
                self._executor = None

    async def _open_async(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._open_sync)

    def _open_sync(self) -> None:
        # Build schema with all 12 fields including doc_key for uniqueness
        ...

    async def add_or_replace_async(self, occ: "SymbolOccurrence") -> None:
        """Delete-by-doc_key + add (Silent-failure F4: prevents duplicates on rerun)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._add_or_replace_sync, occ)

    async def commit_async(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._commit_sync)

    async def search_by_symbol_id_async(self, symbol_id: int, limit: int = 1000) -> list[dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._search_sync, symbol_id, limit
        )

    async def delete_by_symbol_ids_async(self, symbol_ids: list[int]) -> int:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._delete_by_ids_sync, symbol_ids
        )

    async def _close_async(self) -> None:
        if self._executor is None:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._close_sync)
```

**MUST be used as async context manager** (`async with TantivyBridge(...) as bridge`). On exception inside with-block, executor is shut down via `__aexit__`. Test case for executor leak on extract() exception is part of acceptance.

### BoundedInDegreeCounter — fixed eviction + JSON persistence (Python-pro F-C, F-D, F-E fixes)

```python
from collections import Counter
import heapq
import json
from pathlib import Path

class BoundedInDegreeCounter:
    """Exact in-degree counter for top-K symbols with bounded memory.

    Fixes from rev2:
    - F-C: eviction removes EXACTLY evict_n entries, not "all entries with count <= cutoff"
      which under uniform load wipes the counter.
    - F-D: JSON persistence (not pickle); RCE-safe + faster for str→int dict.
    - F-E: run_id validation on load; mismatch = discard, not silent-stale-load.
    """

    def __init__(self, max_entries: int = 1_000_000) -> None:
        self._counter: Counter[str] = Counter()
        self._max = max_entries
        self._next_evict_at = max_entries + max_entries // 10  # batched trigger

    def increment(self, qn: str) -> None:
        self._counter[qn] += 1
        # F-C: trigger eviction every N increments past cap, not every increment
        if len(self._counter) > self._next_evict_at:
            self._evict_lowest_n(self._max // 10)
            self._next_evict_at = len(self._counter) + self._max // 10

    def _evict_lowest_n(self, n: int) -> None:
        """Remove EXACTLY n lowest-count entries, regardless of ties (F-C fix)."""
        if n <= 0 or n >= len(self._counter):
            return
        # most_common returns sorted desc; reverse-slice gets lowest-count keys
        # ties broken by insertion order (Counter inherits dict ordering)
        lowest_keys = [k for k, _ in self._counter.most_common()[-n:]]
        for k in lowest_keys:
            del self._counter[k]

    def estimate(self, qn: str) -> int:
        return self._counter.get(qn, 0)

    def to_disk(self, path: Path, run_id: str) -> None:
        """JSON persistence with run_id (F-D + F-E fix)."""
        payload = {
            "version": 1,
            "run_id": run_id,
            "counts": dict(self._counter),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def from_disk(self, path: Path, expected_run_id: str) -> bool:
        """Load if run_id matches; return False if discarded (corrupt or stale).

        Caller must call hard-fail if False is returned and a Counter is
        required for correct ingest semantics. F-D: never silent-fall-back-to-empty
        as that destroys importance ranking on next eviction pass.
        """
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False
            if payload.get("version") != 1:
                return False
            if payload.get("run_id") != expected_run_id:
                return False
            counts = payload.get("counts")
            if not isinstance(counts, dict):
                return False
            self._counter = Counter({k: int(v) for k, v in counts.items()})
            return True
        except (json.JSONDecodeError, ValueError, TypeError):
            return False
```

**Hard-fail on corruption** (Silent-failure F3): if `from_disk` returns False AND extractor requires correct importance scoring, return `error_code: counter_state_corrupt` envelope from extract(). Operator must either (a) restore counter.json from backup or (b) set `PALACE_COUNTER_RESET=1` to explicitly accept rebuild-from-empty.

### Importance score — clamp documented + recency decay (rev2 unchanged + F-11 doc clarification)

```python
def importance_score(*, cms_in_degree: int, file_path: str, kind: SymbolKind,
                     last_seen_at: datetime, language: Language,
                     primary_lang: Language | None) -> float:
    """Compute importance ∈ [0, 1].

    NOTE: centrality term `0.35 × log1p(in_degree) / log1p(100)` is unbounded
    above for in_degree > 100; clamp to [0, 1] absorbs overflow. This is
    intentional — popular symbols get importance ≈ 1.0 and are eviction-protected
    naturally. Documented weights are component BUDGETS, not strict ranges.
    """
    centrality = math.log1p(cms_in_degree) / math.log1p(100)
    tier = tier_weight(file_path)
    kind_w = KIND_WEIGHT[kind]
    days = max(0.0, (datetime.utcnow() - last_seen_at).total_seconds() / 86400)
    recency = recency_decay(days)
    lang_w = language_weight(language, primary_lang)

    raw = (
        0.35 * centrality
        + 0.30 * tier
        + 0.20 * kind_w
        + 0.10 * recency
        + 0.05 * lang_w
    )
    return max(0.0, min(1.0, raw))
```

`KIND_WEIGHT`: `def=1.0, decl=0.8, impl=0.7, modifier=0.6, event=0.55, assign=0.5, use=0.3` (Solidity event/modifier per Architect F23 already added; weighted between assign and decl).

### ensure_custom_schema — explicit call site + drift detection (Python-pro F-G + Architect F4 fixes)

```python
async def ensure_custom_schema(driver: AsyncDriver) -> None:
    """Idempotent schema bootstrap. Called from extract() top BEFORE any
    Cypher reads/writes (Python-pro F-G).

    Drift detection (Architect F4): pre-flight SHOW CONSTRAINTS and SHOW INDEXES;
    diff against expected; raise schema_drift_detected if mismatch.
    """
    async with driver.session() as session:
        # 1. Drift detection
        existing = await _list_existing_constraints_indexes(session)
        diff = _diff_against_expected(existing, EXPECTED_SCHEMA)
        if diff.has_conflicts:
            raise SchemaDriftError(diff.report)
        # 2. Idempotent CREATE statements
        for stmt in EXPECTED_SCHEMA.create_statements:
            await session.run(stmt)


EXPECTED_SCHEMA = SchemaDefinition(
    constraints=[
        ConstraintSpec(
            name="ext_dep_purl_unique",
            label="ExternalDependency",
            properties=("purl",),
            type="UNIQUE",
        ),
        ConstraintSpec(
            name="eviction_record_unique",
            label="EvictionRecord",
            properties=("symbol_qualified_name", "project"),
            type="UNIQUE",
        ),
        ConstraintSpec(
            name="ingest_checkpoint_unique",
            label="IngestCheckpoint",
            properties=("run_id", "phase", "project"),
            type="UNIQUE",
        ),
    ],
    indexes=[
        IndexSpec(name="shadow_evict_r1", label="SymbolOccurrenceShadow",
                  properties=("group_id", "kind", "importance", "tier_weight")),
        IndexSpec(name="shadow_evict_r2", label="SymbolOccurrenceShadow",
                  properties=("group_id", "kind", "importance", "last_seen_at")),
        IndexSpec(name="shadow_count_by_group", label="SymbolOccurrenceShadow",
                  properties=("group_id",)),  # for circuit breaker per-group count
        IndexSpec(name="symbol_qn_suffix", label="Symbol",
                  properties=("qn_suffix",)),
        IndexSpec(name="ingest_run_lookup", label="IngestRun",
                  properties=("project", "extractor_name", "success")),
    ],
    fulltext_indexes=[
        FulltextSpec(name="symbol_qn_fulltext", label="Symbol", properties=("qualified_name",)),
    ],
)
```

`extract()` calls `ensure_custom_schema(driver)` as first action (cheap idempotent on warm Neo4j; ~7 round-trips on cold). Acceptance test: cold Neo4j → call → all 9 schema objects exist; second call → no error, no changes.

### 3-round eviction — ON ERROR FAIL + reconciliation (Silent-failure F1 + F2 fixes)

Replace `ON ERROR CONTINUE` with `ON ERROR FAIL`. On batch failure, exception bubbles up; outer extractor catches with structured error_code:

```python
EVICTION_ROUND_1 = """
MATCH (s:SymbolOccurrenceShadow)
WHERE s.group_id = $group_id
  AND s.importance < 0.2 AND s.kind = 'use' AND s.tier_weight <= 0.1
WITH s ORDER BY s.importance ASC, s.last_seen_at ASC LIMIT $batch_size
WITH collect(s) AS to_delete, [s IN collect(s) | s.symbol_id] AS ids
CALL {
  WITH to_delete UNWIND to_delete AS s DETACH DELETE s
} IN TRANSACTIONS OF 10000 ROWS ON ERROR FAIL
RETURN ids AS deleted_ids
"""

# Round 2 (inactive user uses): s.importance < 0.4 AND kind='use' AND last_seen_at < datetime()-duration({days:90})
# Round 3 (assigns): s.importance < 0.3 AND kind='assign'
# NEVER touch kind='def' or 'decl'

async def run_eviction_pass(driver, bridge, max_total, group_id, batch_size=10_000):
    """Returns dict[round_name, deleted_count]; raises EvictionError on batch fail."""
    results = {"round_1": 0, "round_2": 0, "round_3": 0}
    error_codes = {
        "round_1": "eviction_round_1_failed",
        "round_2": "eviction_round_2_failed",
        "round_3": "eviction_round_3_failed",
    }
    async with driver.session() as session:
        for round_name, query in [
            ("round_1", EVICTION_ROUND_1),
            ("round_2", EVICTION_ROUND_2),
            ("round_3", EVICTION_ROUND_3),
        ]:
            while True:
                count_result = await session.run(
                    "MATCH (s:SymbolOccurrenceShadow {group_id: $g}) RETURN count(s) AS n",
                    g=group_id,
                )
                n = (await count_result.single())["n"]
                if n <= max_total:
                    return results
                try:
                    delete_result = await session.run(
                        query, group_id=group_id, batch_size=batch_size
                    )
                    deleted_record = await delete_result.single()
                    if not deleted_record or not deleted_record["deleted_ids"]:
                        break  # nothing more in this round
                    deleted_ids = deleted_record["deleted_ids"]
                except Exception as e:
                    raise EvictionError(
                        error_code=error_codes[round_name],
                        round_name=round_name,
                        cause=str(e),
                    ) from e
                # Tantivy delete for confirmed-deleted IDs
                await bridge.delete_by_symbol_ids_async(deleted_ids)
                # Write EvictionRecord per round (constraint-backed, race-safe)
                await _record_eviction(session, round_name, deleted_ids, group_id)
                results[round_name] += len(deleted_ids)
    return results
```

### Error code enumeration — explicit dual-write failure surface (Silent-failure F2 fix)

```python
class ExtractorErrorCode(str, Enum):
    # Config
    SCIP_PATH_REQUIRED = "scip_path_required"  # 101b only
    INVALID_PROJECT = "invalid_project"

    # Schema
    SCHEMA_DRIFT_DETECTED = "schema_drift_detected"
    SCHEMA_BOOTSTRAP_FAILED = "schema_bootstrap_failed"

    # Counter
    COUNTER_STATE_CORRUPT = "counter_state_corrupt"

    # Tantivy
    TANTIVY_OPEN_FAILED = "tantivy_open_failed"
    TANTIVY_COMMIT_FAILED = "tantivy_commit_failed"
    TANTIVY_DISK_FULL = "tantivy_disk_full"
    TANTIVY_LOCK_HELD = "tantivy_lock_held"
    TANTIVY_DELETE_FAILED = "tantivy_delete_failed"

    # Neo4j
    NEO4J_SHADOW_WRITE_FAILED = "neo4j_shadow_write_failed"
    CHECKPOINT_WRITE_FAILED = "checkpoint_write_failed"
    EVICTION_ROUND_1_FAILED = "eviction_round_1_failed"
    EVICTION_ROUND_2_FAILED = "eviction_round_2_failed"
    EVICTION_ROUND_3_FAILED = "eviction_round_3_failed"

    # Budget
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_EXCEEDED_RESUME_BLOCKED = "budget_exceeded_resume_blocked"


@dataclass
class ExtractorError:
    error_code: ExtractorErrorCode
    message: str
    recoverable: bool
    action: Literal["retry", "rebuild_tantivy", "manual_cleanup", "raise_budget", "restore_backup"]
    phase: str | None = None
    partial_writes: int | None = None
```

### Hard circuit breaker — per-phase boundary (Python-pro F-L + Silent-failure F7 fixes)

Circuit breaker fires at **phase boundaries only** (3 times max per run), not per-occurrence. Pre-flight on extractor startup checks for prior `:IngestRun{success: false, error_code: budget_exceeded}` and refuses to start unless either (a) operator runs explicit eviction OR (b) `PALACE_BUDGET_OVERRIDE=1`.

```python
async def _check_budget_at_phase_boundary(driver, group_id, max_total) -> None:
    """O(1) indexed count via shadow_count_by_group index. ~0.5ms even at 70M."""
    result = await driver.execute_query(
        "MATCH (s:SymbolOccurrenceShadow {group_id: $g}) RETURN count(s) AS n",
        {"g": group_id},
    )
    n = result.records[0]["n"]
    if n > int(max_total * 1.1):
        raise BudgetExceededError(
            error_code=ExtractorErrorCode.BUDGET_EXCEEDED,
            shadow_count=n, cap=int(max_total * 1.1),
        )


async def _preflight_budget_check(driver, group_id) -> None:
    """Refuse to start if previous run aborted with budget_exceeded.

    Operator action: run eviction OR set PALACE_BUDGET_OVERRIDE=1.
    """
    if os.environ.get("PALACE_BUDGET_OVERRIDE") == "1":
        return
    result = await driver.execute_query(
        "MATCH (r:IngestRun) "
        "WHERE r.project = $g AND r.extractor_name = 'symbol_index_python' "
        "  AND r.success = false AND r.error_code = $code "
        "RETURN r ORDER BY r.created_at DESC LIMIT 1",
        {"g": group_id, "code": "budget_exceeded"},
    )
    if result.records:
        raise BudgetExceededResumeBlockedError(
            error_code=ExtractorErrorCode.BUDGET_EXCEEDED_RESUME_BLOCKED,
            previous_run=result.records[0]["r"],
            actions=["run eviction", "set PALACE_BUDGET_OVERRIDE=1"],
        )
```

### IngestCheckpoint with expected_doc_count (Architect F5 + Silent-failure F4 fixes)

```python
class IngestCheckpoint(BaseModel):
    run_id: str
    project: str
    phase: Literal["phase1_defs", "phase2_user_uses", "phase3_vendor_uses"]
    expected_doc_count: int  # Tantivy docs we believe were committed for this phase
    completed_at: datetime
```

On restart, after loading checkpoint, reconciliation query: `tantivy.count_docs_for_run(run_id, phase) == checkpoint.expected_doc_count`. Mismatch → `error_code: checkpoint_doc_count_mismatch`, refuse to resume; require operator manual intervention or `PALACE_FORCE_REINGEST=1`.

### Configuration — multi-project palace_scip_index_paths (Architect F3 fix)

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Memory-bounded extractor configuration
    palace_max_occurrences_total: int = 50_000_000
    palace_max_occurrences_per_project: int = 10_000_000
    palace_importance_threshold_use: float = 0.05
    palace_max_occurrences_per_symbol: int = 5_000
    palace_recency_decay_days: float = 30.0

    # Tantivy
    palace_tantivy_index_path: str = "/var/lib/palace/tantivy"
    palace_tantivy_heap_mb: int = 100  # write merge buffer; not runtime mmap

    # SCIP integration (101b, but pathing decided in 101a Settings):
    # multi-project dict keyed by project slug → .scip path
    # JSON-encoded env var: PALACE_SCIP_INDEX_PATHS='{"gimle":"/repos/gimle/.scip/index.scip"}'
    palace_scip_index_paths: dict[str, str] = Field(default_factory=dict)

    model_config = SettingsConfigDict(env_prefix="PALACE_", env_nested_delimiter="__", ...)
```

For 101b: extract() resolves `.scip` path via `settings.palace_scip_index_paths.get(project)`. If missing → error_code: scip_path_required.

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 0 | Replicate D1-D9 to Graphiti via `palace.memory.decide` on iMac (CTO Phase 1.1; Architect F22 fix) | CTO | — |
| 1 | Pydantic models in `extractors/foundation/models.py` (Language, SymbolKind extended with EVENT+MODIFIER, Ecosystem, SourceType; SymbolOccurrence with synthesized_by + schema_version + signed-i64 symbol_id range; ExternalDependency with required resolved_version + sentinel; EvictionRecord; IngestCheckpoint with expected_doc_count; SymbolOccurrenceShadow); cross-field validators via @model_validator (Python-pro F-I); unit tests | PE | T0 |
| 2 | `BoundedInDegreeCounter` with FIXED eviction (most_common[-N:] not threshold-share) + JSON persistence + run_id validation; tests including: uniform-load eviction (verifies exact N removed), corrupt JSON (verifies hard-fail), stale run_id (verifies reject) | PE | T1 |
| 3 | `symbol_id_for()` helper with signed-i64 mask + big-endian byte order docstring; restart-determinism integration test (write → kill container → restart → query returns same int) | PE | T1 |
| 4 | Importance score formula with documented clamp + tier_weight regex (9 vendor patterns); tests verify Solidity event/modifier kind weights | PE | T1, T2, T3 |
| 5 | TantivyBridge with async context manager + ThreadPoolExecutor lifecycle; doc_key primary uniqueness via delete-by-term + add; tests including executor-leak-on-exception case | PE | T1 |
| 6 | `ensure_custom_schema(driver)` with drift detection (SHOW CONSTRAINTS diff); 3 constraints + 5 indexes + 1 fulltext; idempotent on second call; tests against testcontainers-neo4j with conflicting prior schema | PE | T1 |
| 7 | 3-round eviction Cypher with ON ERROR FAIL + structured EvictionError envelope; per-batch reconciliation; race-safe EvictionRecord MERGE; mocked-driver tests verify ordering, never-delete-def-decl, error propagation | PE | T1, T6 |
| 8 | `:IngestRun` write/read + `:IngestCheckpoint` write with expected_doc_count + reconciliation query on restart; tests for crash-mid-Phase + restart resumes correctly | PE | T1 |
| 9 | Settings extensions (8 env vars including `palace_scip_index_paths` JSON dict); validation tests | PE | — |
| 10 | docker-compose.yml: `palace-tantivy-data` named volume, `user: "1000:1000"`, mounted at `/var/lib/palace/tantivy`; non-root USER in Dockerfile; startup ownership check with fail-fast (Architect F19) | PE | — |
| 11 | Hard circuit breaker at phase boundaries + pre-flight `_preflight_budget_check` for previous-run failure detection; tests for budget_exceeded_resume_blocked path | PE | T1, T8 |
| 12 | **Synthetic 70M-occurrence stress harness** (extended per Architect F2): generates synthetic shadow nodes AND synthetic .scip-equivalent stream; runs eviction at 70M; runs write-path stress at 10M and 70M end-to-end through TantivyBridge + Counter + circuit breaker; asserts (a) all 3 eviction rounds fire correctly, (b) Counter eviction removes exactly N entries under uniform load, (c) ThreadPoolExecutor backpressure doesn't deadlock, (d) Phase 1 wall-time scales near-linearly, (e) restart-survivability test (kill container after Phase 1, restart, verify no duplicate occurrences in Tantivy) | PE | T1-T11 |
| 13 | Restart-survivability integration test: full Phase ingest → kill container → restart → query — verifies blake2b determinism + IngestCheckpoint resume + no duplicates (Silent-failure F4) | PE | T3, T5, T8, T12 |
| 14 | Documentation: CLAUDE.md updated with new env vars, tantivy data volume, Phase 1/2/3 bootstrap, GDS plugin caveat (Silent-failure F-G); README foundation-substrate section | PE | T1-T13 |
| 15 | Mechanical CR Phase 3.1: full `ruff check && mypy src/ && pytest` output, scope audit, anti-rubber-stamp checklist with all 26 round-2 findings cross-referenced | CR | T14 |
| 16 | Adversarial Opus Phase 3.2: 26 finding-specific evidence checks + new schema-drift / executor-leak / Counter-uniform-load edge cases | Opus | T15 |
| 17 | QA Phase 4.1 live smoke on iMac: docker stack up --build --wait; ensure_custom_schema runs cold; synthetic harness (T12) executes against real Neo4j+Tantivy at 1M (subset for time); verify all schema objects, EvictionRecord nodes, no duplicates after restart | QA | T16 |
| 18 | Phase 4.2 squash-merge — CTO only | CTO | T17 |

## Acceptance

1. All 9 ratified decisions D1-D9 + all 26 round-2 findings realized in code (cross-reference table at end of spec).
2. Tantivy sidecar with primary-key uniqueness via `doc_key`; delete-by-term+add semantics prevent duplicates after Phase rerun.
3. Pydantic models with mypy strict; @model_validator for cross-field validation; SymbolKind includes EVENT + MODIFIER; SymbolOccurrence has synthesized_by + schema_version.
4. `symbol_id_for()` returns signed-i64; restart-determinism integration test green; big-endian byte-order documented.
5. `BoundedInDegreeCounter` eviction removes EXACTLY n entries under uniform synthetic load (test asserts post-eviction len = max - n, not 0); JSON persistence with run_id; corrupt-load → hard-fail with `counter_state_corrupt` error_code.
6. TantivyBridge MUST use async context manager; executor shut down on exception path verified by integration test.
7. `ensure_custom_schema` called from extract() top; drift detection raises schema_drift_detected on conflicting prior schema; 9 schema objects (3 constraints + 5 indexes + 1 fulltext) exist after cold call.
8. 3-round eviction Cypher uses `ON ERROR FAIL`; failure raises EvictionError with structured error_code; never deletes def/decl; reconciles deleted_ids between Neo4j shadow and Tantivy; EvictionRecord written per round (race-safe via constraint).
9. IngestCheckpoint includes expected_doc_count; restart reconciliation: count(Tantivy docs for run+phase) == expected_doc_count; mismatch → error_code: checkpoint_doc_count_mismatch.
10. Hard circuit breaker fires at phase boundaries only; per-phase O(1) count via shadow_count_by_group index; budget_exceeded_resume_blocked refuses next run unless PALACE_BUDGET_OVERRIDE=1.
11. Synthetic stress harness validates eviction AT 70M scale + write-path stress at 10M and 70M end-to-end; runs in QA Phase 4.1 at 1M subset for time.
12. Restart-survivability integration test: kill mid-Phase, restart, query → no duplicates, no silent zero-results.
13. CLAUDE.md updated with new env vars + tantivy volume + Phase 1/2/3 + GDS plugin caveat.
14. CR Phase 3.1 + Opus Phase 3.2 reviews passed; QA Phase 4.1 live smoke green on iMac with synthetic harness at 1M.

## Out of scope (defer to 101b)

- scip-python integration (`pip install scip` + protobuf 250 MiB CI fixture)
- SymbolIndexPython extractor (3-phase bootstrap with real .scip)
- `palace.code.find_references` composite tool with 3-state distinction (`:IngestRun` lookup + EvictionRecord warning)
- Dogfood test on Gimle-Palace's own Python codebase

## Decisions recorded (rev3a)

All 9 D1-D9 unchanged. Rev2→rev3a applies 26 round-2 multi-reviewer findings:

| Round 2 Finding | Severity | 101a application |
|---|---|---|
| Architect F1 dual-write atomicity | HIGH | Strict ordering invariant in §Storage model |
| Architect F2 harness write-path | HIGH | T12 extended to write-path stress at 10M+70M |
| Architect F3 multi-project scip path | HIGH | `palace_scip_index_paths` dict in Settings |
| Architect F4 schema drift | MEDIUM | ensure_custom_schema pre-flight diff |
| Architect F5 IngestCheckpoint partial-Phase | MEDIUM | expected_doc_count + reconciliation |
| Architect F6 pickle security/durability | MEDIUM | JSON + run_id validation + hard-fail (overlaps Python-pro F-D, F-E) |
| Architect F7 synthesized_by pre-emptive | MEDIUM | Kept in schema (per F23); behavioral test deferred to 101b's first synthesized scenario |
| Architect F8 slicing | HIGH | RESOLVED — split into 101a + 101b |
| Silent-failure F1 ON ERROR CONTINUE | HIGH | ON ERROR FAIL + structured EvictionError |
| Silent-failure F2 generic error_code | HIGH | ExtractorErrorCode enum (16 codes) |
| Silent-failure F3 Counter pickle fallback | HIGH | Hard-fail with counter_state_corrupt |
| Silent-failure F4 Tantivy duplicates on rerun | HIGH | doc_key primary uniqueness + delete-by-term+add |
| Silent-failure F5 find_references 3-state | HIGH | Deferred to 101b (composite tool); :IngestRun index added in 101a |
| Silent-failure F6 schema_version field | MEDIUM | Added to Tantivy schema + Pydantic model |
| Silent-failure F7 budget_exceeded recovery | MEDIUM | Pre-flight check + resume_blocked error |
| Silent-failure F8 scip_path None | MEDIUM | Deferred to 101b extract() handler |
| Python-pro F-A i64/u64 | HIGH | symbol_id_for signed-i64 mask |
| Python-pro F-B endianness | LOW | Big-endian documented in docstring |
| Python-pro F-C Counter eviction bug | HIGH | most_common[-N:] fix + batched trigger |
| Python-pro F-D pickle RCE | MEDIUM | JSON persistence (overlaps Architect F6) |
| Python-pro F-E stale Counter | MEDIUM | run_id validation (overlaps Architect F5) |
| Python-pro F-F executor leak | HIGH | async context manager + shutdown |
| Python-pro F-G ensure_custom_schema call site | MEDIUM | Called from extract() top (documented) |
| Python-pro F-I Pydantic v2 validator | MEDIUM | @model_validator(mode="after") |
| Python-pro F-J protobuf 200 MiB cap | HIGH | Deferred to 101b (parse_scip_file lives there); CI fixture for 250 MiB decode |
| Python-pro F-L circuit breaker granularity | MEDIUM | Per-phase boundary + indexed count query |

## Open questions

1. **Counter persistence corruption recovery operator UX.** Hard-fail blocks ingestion until operator runs PALACE_COUNTER_RESET=1. Should we provide a `palace.ops.counter_rebuild` helper tool? Defer to v2 unless friction.
2. **Tantivy primary-key uniqueness performance cost.** Every write becomes delete-by-term + add. At 70M occurrences this is 70M term deletes. Tantivy Term operations are ~µs but cumulative cost vs. naive append needs benchmarking. Open question for T12 stress harness.
3. **schema_version migration story for Slice 110+.** When SymbolKind extends, do we re-index from .scip OR write a forward-compat translation layer? Decide before 101c (smart contracts).
4. **Multi-project EvictionRecord namespacing.** `:EvictionRecord{symbol_qualified_name, project}` — but project key is graphiti `group_id` or extractor's project slug? Unify in 101a.

## References

- `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md` — D1-D9 ratified
- `docs/research/2026-04-27-symbol-index-foundation/` — 3 voltagent independent track findings (Q2 + Q3 + memory-bounded)
- `paperclip-shared-fragments@1c76fa9/fragments/compliance-enforcement.md` — Phase 4.2 CTO-only + anti-rubber-stamp + MCP wire-contract test rule
- ECMA-427 Package URL specification (December 2025)
- SCIP proto: github.com/sourcegraph/scip/blob/main/scip.proto
- Tantivy docs: docs.rs/tantivy
- Sourcegraph "Ranking in a Week" (PageRank undirected)
- SOSP 2023 S3-FIFO + NSDI 2024 SIEVE (cache eviction algorithms cited)
- GIM-77 — bridge extractor pattern (precedent for dual-write Neo4j+other)
- GIM-89 — `_OpenArgs` open-schema for `palace.code.*` passthroughs
- GIM-91 — MCP wire-contract test rule
- GIM-94 — Phase 4.2 CTO-only rule
- GIM-100 — multi-language foundation research
