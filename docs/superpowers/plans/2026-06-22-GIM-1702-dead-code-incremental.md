# GIM-1702 Plan: dead_code incremental

Grounded in `feature/GIM-1702-dead-code-incremental` at
`c6d72e5bbd83ef3c73df192dd29729598b5f1fae`.
Authoritative spec:
`docs/superpowers/specs/2026-06-21-incremental-global-extractors.md`
sections `1`, `1.2`, `1.3`, `1.4`, `1.5`, and `1.6`.

## Goal

Ship the Phase 4.3 `dead_code` incremental path behind the existing
incremental gate so bounded reruns reuse persisted reachability state,
rewrite only changed findings, and preserve full fallback when the
affected set is too large or prerequisites are missing.

## Assumptions

- The implementation lives on `feature/GIM-1702-dead-code-incremental`
  and PR `#496` targets `develop`.
- `dead_code` stays guarded by `PALACE_INCREMENTAL_INGEST` until follow-up
  real-Neo4j parity and QA evidence are complete.
- The delta-resolution layer from GIM-1699 is available to provide the
  changed symbol and edge scope consumed by this slice.
- Seed validity still depends on upstream population of symbol access
  metadata; this slice must preserve the fallback path rather than
  silently claim correctness when those prerequisites are absent.

## Acceptance Criteria

- AC-1: `:DeadFinding` writes are batched with `UNWIND` and no longer do
  one Neo4j write transaction per finding.
- AC-2: Incremental writes are non-destructive: they upsert changed
  findings, evict only explicitly stale `finding_id`s, and leave
  unaffected findings intact.
- AC-3: Persisted optional finding props
  (`git_last_external_ref`, `module_coverage_ratio`,
  `target_dead_type`) are cleared when a later incremental result
  removes them, so `_diff_findings_against_existing` becomes
  idempotent instead of re-reporting stale rows forever.
- AC-4: Symbol reachability state is materialized and updated in
  batched writes so incremental runs can reuse prior liveness instead of
  forcing a full dead-code rewrite.
- AC-5: Incremental `dead_code` still falls back to full when the
  affected-set threshold or preflight rules say the delta is unsafe.
- AC-6: Focused unit tests cover fallback, idempotency, dead-module
  boundary behavior, selected stale eviction, and the nullable-prop
  writer regression.

## Work Plan

1. Establish the incremental `dead_code` baseline in tests first.
   - Files:
     `services/palace-mcp/tests/extractors/unit/test_dead_code_incremental.py`,
     `services/palace-mcp/tests/extractors/unit/test_dead_code_extractor_incremental.py`,
     `services/palace-mcp/tests/extractors/unit/test_dead_code_neo4j_writer.py`.
   - Result: failing tests describe the delta planner, fallback rules,
     non-destructive stale eviction, and writer idempotency.

2. Batch the `:DeadFinding` write path and keep it group-scoped.
   - Files:
     `services/palace-mcp/src/palace_mcp/extractors/dead_code/neo4j_writer.py`.
   - Result: one batched finding write plus one batched edge write
     replaces the per-finding transaction loop.

3. Add persisted reachability state and incremental writer hooks.
   - Files:
     `services/palace-mcp/src/palace_mcp/extractors/dead_code/extractor.py`,
     `services/palace-mcp/src/palace_mcp/extractors/dead_code/incremental.py`,
     `services/palace-mcp/src/palace_mcp/extractors/dead_code/graph_loader.py`,
     `services/palace-mcp/src/palace_mcp/extractors/dead_code/models.py`,
     `services/palace-mcp/src/palace_mcp/project_analyze.py`.
   - Result: incremental mode computes the affected frontier, reuses
     stored liveness, and falls back cleanly when the delta is unsafe.

4. Make changed-finding rewrites idempotent.
   - Files:
     `services/palace-mcp/src/palace_mcp/extractors/dead_code/neo4j_writer.py`,
     `services/palace-mcp/tests/extractors/unit/test_dead_code_neo4j_writer.py`.
   - Result: nullable optional props are explicitly overwritten to
     `null` in Neo4j when the current finding no longer carries them.

5. Verify the slice with targeted local checks before review.
   - Verification from `services/palace-mcp`:
     - `uv run ruff check src/palace_mcp/extractors/dead_code/neo4j_writer.py tests/extractors/unit/test_dead_code_neo4j_writer.py`
     - `uv run ruff format --check src/palace_mcp/extractors/dead_code/neo4j_writer.py tests/extractors/unit/test_dead_code_neo4j_writer.py`
     - `uv run pytest tests/extractors/unit/test_dead_code_neo4j_writer.py tests/extractors/unit/test_dead_code_extractor_incremental.py tests/extractors/unit/test_dead_code_incremental.py`
     - `gh pr checks 496`

## Handoff

1. `CXPythonEngineer` updates PR `#496` with this plan reference and the
   latest verification evidence.
2. `CXCodeReviewer` re-runs mechanical review against the updated branch,
   focused on the nullable-prop fix and approval gates.
3. If the branch is mechanically clean, handoff continues to
   `CodexArchitectReviewer`, then `CXQAEngineer`, then `CXCTO`.
