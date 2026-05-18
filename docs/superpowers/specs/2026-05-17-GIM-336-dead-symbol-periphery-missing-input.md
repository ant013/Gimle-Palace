# dead_symbol_binary_surface: MISSING_INPUT on absent periphery fixtures

**Date:** 2026-05-17
**Status:** Formalized
**Owner:** CTO
**Parent:** GIM-333 (suspicious-zero diagnostic)
**Branch:** `feature/GIM-336-periphery-missing-input`
**Companion plan:** `docs/superpowers/plans/2026-05-17-GIM-336-dead-symbol-periphery-missing-input.md`

---

## 1. Problem

`dead_symbol_binary_surface` extractor silently returns `success=True, nodes_written=0` when `periphery/periphery-3.7.4-swiftpm.json` or `periphery/contract.json` are absent. The `_load_periphery_findings` helper returns an empty tuple, the pipeline proceeds with 0 findings, and `finalize_ingest_run(success=True)` records a misleading success.

Evidence: `docs/runbooks/suspicious-zero-diagnostic-2026-05-17.md` -- tron-kit IngestRun had `success=TRUE, nodes=0, no error_code`.

## 2. Root cause

`extractor.py:263-264`:
```python
if not report_path.exists() or not contract_path.exists():
    return ()
```

Returns empty tuple silently. No error code, no diagnostic message, no IngestRun metadata indicating the skip.

Additionally, the `run()` except handler (line 152-157) hardcodes `NEO4J_SHADOW_WRITE_FAILED` regardless of actual exception type, masking any future errors raised from the pipeline.

## 3. Fix

Follow the established `SCIP_PATH_REQUIRED` pattern used by all symbol-index extractors:

1. Add `PERIPHERY_FIXTURES_MISSING = "periphery_fixtures_missing"` to `ExtractorErrorCode`.
2. In `_run_pipeline`, check file existence early (before phase work). If absent, raise `ExtractorError` with the new code, a descriptive message naming the missing file, and `action="manual_cleanup"`.
3. Fix the `run()` except handler to propagate the actual `error_code` from caught `ExtractorError` instances instead of hardcoding `NEO4J_SHADOW_WRITE_FAILED`.

## 4. Definition of Done

1. `run_extractor(name="dead_symbol_binary_surface", project=<any>)` returns `ok=false, error_code="periphery_fixtures_missing"` with a message naming the missing file when fixtures are absent.
2. IngestRun node records `success=false, error_code="periphery_fixtures_missing"`.
3. When fixtures ARE present, behavior is unchanged (existing tests pass).
4. The `run()` except handler propagates ExtractorError codes correctly.
5. Unit tests cover: (a) report missing, (b) contract missing, (c) both missing, (d) both present (happy path unchanged).

## 5. Non-goals

- Changing ExtractorStats dataclass (too broad for this fix).
- Adding a general `MISSING_INPUT` outcome taxonomy across all extractors (followup).
- Fixing the IB-2/IB-3/IB-4 infra blockers mentioned in GIM-333 PR #205.

## 6. Scope

~30 LOC across 3 files. Single PR, single implementer.
