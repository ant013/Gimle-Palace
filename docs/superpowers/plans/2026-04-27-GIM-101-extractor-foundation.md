# GIM-101a — Extractor Foundation + Synthetic Stress Harness

**Spec:** `docs/superpowers/specs/2026-04-27-101a-extractor-foundation-design.md` (rev3a)
**Decisions:** `docs/superpowers/decisions/2026-04-27-pre-extractor-foundation.md` (D1-D9)
**Branch:** `feature/101a-extractor-foundation` (cut from develop `4bdccb4`)
**Predecessor:** GIM-99 release-cut-v2 merge (`4bdccb4`)
**Hard gate:** 101b Python extractor depends on 101a merge

---

## Phase 1.1 — CTO Formalize

**Owner:** CTO
**Status:** this plan

### Steps

1. ✅ Verify spec rev3a, decisions D1-D9, research files (3 voltagent reports)
2. ✅ Cut `feature/101a-extractor-foundation` from develop `4bdccb4`
3. ✅ Cherry-pick spec/decisions/research from Board's draft branch
4. ✅ Update spec frontmatter: `paperclip_issue: GIM-101`, `branch: feature/101a-extractor-foundation`
5. ✅ Write this plan
6. ⏳ Task 0: replicate D1-D9 to Graphiti via `palace.memory.decide` — **BLOCKED** (palace-mcp not available in CTO worktree; delegate to PythonEngineer as first implementation task or execute on iMac)
7. Commit + push
8. Reassign to CodeReviewer for Phase 1.2

### Task 0 decision

D1-D9 replication to Graphiti requires a running palace-mcp instance with `palace.memory.decide` tool. CTO worktree does not have docker access. **Resolution:** Task 0 becomes PythonEngineer's first step in Phase 2, executed on iMac docker stack before any code. Acceptance unchanged: 9 `:Decision` nodes returned by `palace.memory.lookup` filtered by tag `n+2-foundation`.

---

## Phase 1.2 — Plan-First Review

**Owner:** CodeReviewer (`bd2d7e20-7ed8-474c-91fc-353d610f4c52`)
**Acceptance:** Every task has concrete test + impl + commit description; no gaps; APPROVE → reassign to PythonEngineer

---

## Phase 2 — Implementation

**Owner:** PythonEngineer
**Branch:** `feature/101a-extractor-foundation`
**Base path:** `services/palace-mcp/src/palace_mcp/extractors/foundation/`
**Test base:** `tests/extractors/`

### Task 0 — Replicate D1-D9 to Graphiti (iMac docker stack)

- **What:** Call `palace.memory.decide` 9 times (D1-D9) with `tags: ["n+2-foundation"]`
- **Acceptance:** `palace.memory.lookup(entity_type="Decision", filters={"tag": "n+2-foundation"})` returns 9 nodes
- **Affected files:** None (runtime-only MCP calls against Neo4j)
- **Deps:** palace-mcp running with Neo4j

### Task 1 — Pydantic models (`foundation/models.py`)

- **What:** Language enum (9 languages + UNKNOWN), SymbolKind (def/decl/impl/use/assign + EVENT + MODIFIER), Ecosystem enum, SourceType enum, SymbolOccurrence (synthesized_by, schema_version, signed-i64 symbol_id range via `ge=-(2**63), le=2**63-1`), ExternalDependency (purl, required resolved_version with sentinel `"unresolved"`), EvictionRecord, IngestCheckpoint (expected_doc_count), SymbolOccurrenceShadow. @model_validator(mode="after") for cross-field validation.
- **Acceptance:** `uv run mypy src/ --strict` passes; unit tests cover all validators and edge cases
- **Affected files:** `foundation/models.py`, `tests/extractors/unit/test_models.py`
- **Deps:** —
- **Commit:** `feat(101a): T1 — Pydantic foundation models with signed-i64 symbol_id`

### Task 2 — BoundedInDegreeCounter (`foundation/importance.py`)

- **What:** Counter with `most_common()[-N:]` eviction fix, JSON persistence with run_id validation, hard-fail on corruption
- **Acceptance:** (a) uniform-load test: insert 1.1×max entries → eviction removes exactly max//10 entries, (b) corrupt JSON → `counter_state_corrupt` error, (c) stale run_id → reject + False return
- **Affected files:** `foundation/importance.py`, `tests/extractors/unit/test_importance.py`
- **Deps:** T1 (models for error codes)
- **Commit:** `feat(101a): T2 — BoundedInDegreeCounter with fixed eviction + JSON persistence`

### Task 3 — symbol_id_for() helper (`foundation/identifiers.py`)

- **What:** blake2b → signed-i64 mask, big-endian byte order, docstring documenting cross-language invariant
- **Acceptance:** (a) known input → known signed-i64 output (golden test), (b) restart-determinism: same input across process restarts → same output, (c) values spanning both positive and negative i64 range
- **Affected files:** `foundation/identifiers.py`, `tests/extractors/unit/test_identifiers.py`
- **Deps:** T1
- **Commit:** `feat(101a): T3 — symbol_id_for with signed-i64 mask + blake2b`

### Task 4 — Importance score formula (`foundation/importance.py`)

- **What:** `importance_score()` with 5-component formula (centrality 0.35, tier 0.30, kind 0.20, recency 0.10, language 0.05), clamp [0,1], tier_weight regex (9 vendor patterns), KIND_WEIGHT including event=0.55, modifier=0.6
- **Acceptance:** (a) known input → known float output (golden tests), (b) Solidity event/modifier weights verified, (c) output always in [0,1] including extreme inputs
- **Affected files:** `foundation/importance.py`, `tests/extractors/unit/test_importance.py`
- **Deps:** T1, T2, T3
- **Commit:** `feat(101a): T4 — importance score formula with tier + kind + recency + language`

### Task 5 — TantivyBridge (`foundation/tantivy_bridge.py`)

- **What:** Async context manager wrapping ThreadPoolExecutor(max_workers=1), doc_key primary uniqueness via delete-by-term+add, search_by_symbol_id, delete_by_symbol_ids, explicit shutdown in `__aexit__`
- **Acceptance:** (a) add_or_replace_async prevents duplicates on re-add with same doc_key, (b) executor shut down on exception inside `async with` block (integration test), (c) search returns correct results after commit
- **Affected files:** `foundation/tantivy_bridge.py`, `tests/extractors/unit/test_tantivy_bridge.py`, `tests/extractors/integration/test_tantivy_bridge_integration.py`
- **Deps:** T1
- **Commit:** `feat(101a): T5 — TantivyBridge async context manager with doc_key uniqueness`

### Task 6 — ensure_custom_schema (`foundation/schema.py`)

- **What:** SchemaDefinition with 3 constraints + 5 indexes + 1 fulltext = 9 objects, drift detection via SHOW CONSTRAINTS / SHOW INDEXES diff, idempotent CREATE
- **Acceptance:** (a) cold Neo4j → call → 9 schema objects exist, (b) second call → no error, (c) conflicting prior schema → raises `schema_drift_detected`
- **Affected files:** `foundation/schema.py`, `tests/extractors/unit/test_schema.py`, `tests/extractors/integration/test_schema_integration.py`
- **Deps:** T1
- **Commit:** `feat(101a): T6 — ensure_custom_schema with drift detection`

### Task 7 — 3-round eviction (`foundation/eviction.py`)

- **What:** Cypher queries with ON ERROR FAIL, structured EvictionError, per-batch reconciliation (delete from Tantivy after Neo4j confirm), race-safe EvictionRecord MERGE, never-delete-def-decl guard
- **Acceptance:** (a) round ordering: R1 (low-importance uses) → R2 (inactive uses) → R3 (assigns), (b) def/decl never deleted (test with mixed data), (c) EvictionError raised on batch failure, (d) EvictionRecord written per round
- **Affected files:** `foundation/eviction.py`, `tests/extractors/unit/test_eviction.py`
- **Deps:** T1, T6
- **Commit:** `feat(101a): T7 — 3-round eviction with ON ERROR FAIL + EvictionError`

### Task 8 — IngestRun + IngestCheckpoint (`foundation/checkpoint.py`)

- **What:** Write/read :IngestRun, :IngestCheckpoint with expected_doc_count, reconciliation query on restart (count Tantivy docs for run+phase == expected_doc_count), mismatch → `checkpoint_doc_count_mismatch`
- **Acceptance:** (a) checkpoint written after successful phase commit, (b) restart resumes from last completed phase, (c) count mismatch → error + refuse to resume
- **Affected files:** `foundation/checkpoint.py`, `tests/extractors/unit/test_checkpoint.py`
- **Deps:** T1
- **Commit:** `feat(101a): T8 — IngestCheckpoint with expected_doc_count reconciliation`

### Task 9 — Settings extensions

- **What:** 8 env vars: `PALACE_MAX_OCCURRENCES_TOTAL`, `PALACE_MAX_OCCURRENCES_PER_PROJECT`, `PALACE_IMPORTANCE_THRESHOLD_USE`, `PALACE_MAX_OCCURRENCES_PER_SYMBOL`, `PALACE_RECENCY_DECAY_DAYS`, `PALACE_TANTIVY_INDEX_PATH`, `PALACE_TANTIVY_HEAP_MB`, `PALACE_SCIP_INDEX_PATHS` (JSON dict)
- **Acceptance:** (a) all env vars parsed correctly, (b) JSON dict for scip_index_paths works, (c) defaults match spec
- **Affected files:** `src/palace_mcp/config.py` (or Settings class location), `tests/unit/test_settings.py`
- **Deps:** —
- **Commit:** `feat(101a): T9 — Settings extensions for extractor foundation`

### Task 10 — Docker Compose + Dockerfile changes

- **What:** `palace-tantivy-data` named volume, `user: "1000:1000"` in compose, mount at `/var/lib/palace/tantivy`, non-root USER in Dockerfile, startup ownership check with fail-fast
- **Acceptance:** (a) container starts with non-root user, (b) tantivy volume persists across restarts, (c) wrong ownership → fail-fast with clear error
- **Affected files:** `docker-compose.yml`, `services/palace-mcp/Dockerfile`
- **Deps:** —
- **Commit:** `feat(101a): T10 — Tantivy volume + non-root user + ownership check`

### Task 11 — Hard circuit breaker (`foundation/circuit_breaker.py`)

- **What:** `_check_budget_at_phase_boundary` (O(1) indexed count), `_preflight_budget_check` (previous-run failure detection), `PALACE_BUDGET_OVERRIDE=1` escape hatch
- **Acceptance:** (a) budget exceeded at phase boundary → `budget_exceeded` error, (b) previous run failed with budget_exceeded → `budget_exceeded_resume_blocked` on next run, (c) `PALACE_BUDGET_OVERRIDE=1` bypasses pre-flight
- **Affected files:** `foundation/circuit_breaker.py`, `tests/extractors/unit/test_circuit_breaker.py`
- **Deps:** T1, T8
- **Commit:** `feat(101a): T11 — hard circuit breaker at phase boundaries`

### Task 12 — Synthetic 70M-occurrence stress harness (`foundation/synthetic_harness.py`)

- **What:** Generate synthetic shadow nodes + synthetic occurrence stream; run eviction at 70M; write-path stress at 10M and 70M through TantivyBridge + Counter + circuit breaker. Verify: (a) all 3 eviction rounds fire, (b) Counter eviction exactly N, (c) no executor deadlock, (d) near-linear Phase 1 wall-time, (e) restart-survivability
- **Acceptance:** All 5 assertions pass at 70M synthetic scale (or 1M subset in QA Phase 4.1 for time)
- **Affected files:** `foundation/synthetic_harness.py`, `tests/extractors/integration/test_synthetic_harness.py`
- **Deps:** T1-T11 (all foundation components)
- **Commit:** `feat(101a): T12 — synthetic 70M stress harness`

### Task 13 — Restart-survivability integration test

- **What:** Full Phase ingest → kill container → restart → query. Verify blake2b determinism + IngestCheckpoint resume + no duplicates
- **Acceptance:** After kill+restart: (a) no duplicate doc_keys in Tantivy, (b) IngestCheckpoint resumes from correct phase, (c) no silent zero-results
- **Affected files:** `tests/extractors/integration/test_restart_survivability.py`
- **Deps:** T3, T5, T8, T12
- **Commit:** `feat(101a): T13 — restart-survivability integration test`

### Task 14 — Documentation

- **What:** CLAUDE.md: new env vars, tantivy data volume, Phase 1/2/3 bootstrap, GDS plugin caveat. README: foundation-substrate section
- **Acceptance:** CLAUDE.md and README updated and accurate
- **Affected files:** `CLAUDE.md`, `README.md`
- **Deps:** T1-T13
- **Commit:** `docs(101a): T14 — CLAUDE.md + README extractor foundation section`

### Task 0-14 execution order (parallelizable groups)

```
Group A (parallel, no deps):  T1, T9, T10
Group B (parallel, dep T1):   T2, T3, T5, T6, T8
Group C (dep T1+T2+T3):       T4
Group D (dep T1+T6):           T7
Group E (dep T1+T8):           T11
Group F (dep T1-T11):          T12
Group G (dep T3+T5+T8+T12):   T13
Group H (dep T1-T13):          T14
```

PythonEngineer should work through groups sequentially but parallelize within each group where practical.

---

## Phase 3.1 — Mechanical Review (Task 15)

**Owner:** CodeReviewer (`bd2d7e20-7ed8-474c-91fc-353d610f4c52`)
**Acceptance:** Full `uv run ruff check && uv run mypy src/ && uv run pytest` output pasted in APPROVE comment. Anti-rubber-stamp checklist: all 26 round-2 findings cross-referenced against implementation. Scope audit: no out-of-scope code (no scip-python, no find_references, no TS/JS extractors).

---

## Phase 3.2 — Adversarial Opus Review (Task 16)

**Owner:** OpusArchitectReviewer
**Acceptance:** 26 finding-specific evidence checks + new edge cases: schema-drift scenario, executor-leak-on-exception, Counter-uniform-load at boundary. APPROVE or REQUEST CHANGES with specific findings.

---

## Phase 4.1 — QA Live Smoke (Task 17)

**Owner:** QAEngineer
**Execution:** iMac docker stack

### Required evidence:
1. `docker compose --profile review up -d --build --wait` → all containers healthy
2. `ensure_custom_schema` runs cold → 9 schema objects exist (SHOW CONSTRAINTS + SHOW INDEXES)
3. Synthetic harness (T12) at 1M subset → all assertions pass
4. TantivyBridge async context manager teardown: kill mid-extract → no executor leak
5. Restart-survivability: kill container after Phase 1, restart, verify no duplicates
6. `palace.memory.lookup(entity_type="Decision", filters={"tag": "n+2-foundation"})` → 9 Decision nodes (Task 0)
7. Direct Cypher: `MATCH (s:SymbolOccurrenceShadow) RETURN count(s)` consistent with harness output

---

## Phase 4.2 — Merge (Task 18)

**Owner:** CTO (merge-only; per GIM-94 D1)
**Pre-conditions:** CR APPROVE (Phase 3.1) + Opus APPROVE (Phase 3.2) + QA PASS (Phase 4.1) + CI green
**Action:** `gh pr merge --squash` into develop

---

## Dependency graph (summary)

```
Phase 1.1 (CTO) → Phase 1.2 (CR) → Phase 2 (PE: T0-T14)
                                         → Phase 3.1 (CR)
                                              → Phase 3.2 (Opus)
                                                   → Phase 4.1 (QA)
                                                        → Phase 4.2 (CTO merge)
```

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| tantivy-py FFI crashes on macOS ARM | HIGH | T5 integration test on iMac early; fallback: pure-Python in-memory index for dev |
| 70M synthetic harness exceeds iMac RAM (32 GB) | MEDIUM | T12 scales to 1M subset in QA; full 70M optional if resources allow |
| Neo4j schema drift from prior GIM-77 bridge extractor | MEDIUM | T6 drift detection catches conflicts; manual cleanup documented |
| `palace.memory.decide` API shape changed since GIM-96 | LOW | T0 executed against running iMac stack; verify before bulk insert |
