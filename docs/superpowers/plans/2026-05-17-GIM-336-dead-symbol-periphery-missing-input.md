# Implementation plan — GIM-336: dead_symbol_binary_surface MISSING_INPUT fix

**Date:** 2026-05-17
**Spec:** `docs/superpowers/specs/2026-05-17-GIM-336-dead-symbol-periphery-missing-input.md`
**Status:** draft
**Team:** Claude (CTO + CR + MCPEngineer + QA)
**Branch:** `feature/GIM-336-periphery-missing-input`
**Target:** `develop`

---

## Task 1 — RED: unit tests for missing-fixture error path

**Owner:** MCPEngineer
**Files:**
- `services/palace-mcp/tests/extractors/unit/test_dead_symbol_binary_surface_extractor.py` (modify)

**Work:**
1. Add test `test_run_pipeline_raises_when_report_missing` — mock repo_path where `periphery/contract.json` exists but `periphery/periphery-3.7.4-swiftpm.json` does not. Assert `ExtractorError` raised with `error_code=PERIPHERY_FIXTURES_MISSING`.
2. Add test `test_run_pipeline_raises_when_contract_missing` — report exists, contract absent. Same assertion.
3. Add test `test_run_pipeline_raises_when_both_missing` — neither exists. Same assertion.
4. Add test `test_run_error_handler_propagates_extractor_error_code` — mock `_run_pipeline` raising `ExtractorError(error_code=PERIPHERY_FIXTURES_MISSING, ...)`. Assert `finalize_ingest_run` called with `error_code="periphery_fixtures_missing"` (not `neo4j_shadow_write_failed`).
5. Verify existing happy-path test still exercises the `both-present` branch.

**Acceptance:** All 4 new tests FAIL (RED) before Task 2. Existing tests unmodified.

---

## Task 2 — GREEN: implement the fix

**Owner:** MCPEngineer
**Files:**
- `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py` (modify — add enum member)
- `services/palace-mcp/src/palace_mcp/extractors/dead_symbol_binary_surface/extractor.py` (modify — 2 changes)

**Work:**

### 2a. Add error code

In `ExtractorErrorCode` enum, under the `# Config` section, add:
```python
PERIPHERY_FIXTURES_MISSING = "periphery_fixtures_missing"
```

### 2b. Early check in `_run_pipeline`

Replace the silent early-return in `_load_periphery_findings` with an early check at the top of `_run_pipeline` (after `_read_head_sha`, before `check_phase_budget`):

```python
report_path = _dead_symbol_periphery_report_path(settings, repo_path=ctx.repo_path)
contract_path = _dead_symbol_periphery_contract_path(settings, repo_path=ctx.repo_path)
if not report_path.exists() or not contract_path.exists():
    missing = report_path if not report_path.exists() else contract_path
    raise ExtractorError(
        error_code=ExtractorErrorCode.PERIPHERY_FIXTURES_MISSING,
        message=f"periphery fixture not found: {missing}",
        recoverable=False,
        action="manual_cleanup",
    )
```

Remove the `if not ... exists()` guard from `_load_periphery_findings` (lines 263-264) — the method can now assume both files exist.

### 2c. Fix except handler in `run()`

Replace the hardcoded error code in the except block (lines 152-157):

```python
except ExtractorError as e:
    await finalize_ingest_run(
        driver,
        run_id=ctx.run_id,
        success=False,
        error_code=e.error_code.value,
    )
    raise
except Exception:
    await finalize_ingest_run(
        driver,
        run_id=ctx.run_id,
        success=False,
        error_code=ExtractorErrorCode.NEO4J_SHADOW_WRITE_FAILED.value,
    )
    raise
```

**Acceptance:** All 4 RED tests from Task 1 pass. All pre-existing tests pass. `uv run ruff check && uv run mypy src/ && uv run pytest` green.

---

## Sequencing

```
Task 1 (RED) → Task 2 (GREEN) → PR to develop → CR Phase 3.1 → QA Phase 4.1 → Merge
```

Single issue, single PR, serial execution. No inter-slice dependencies.
