"""Unit tests for foundation/errors.py (GIM-101a, T1)."""

from __future__ import annotations

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode


class TestExtractorErrorCode:
    def test_has_24_codes(self) -> None:
        assert len(ExtractorErrorCode) == 24

    def test_all_codes_are_strings(self) -> None:
        for code in ExtractorErrorCode:
            assert isinstance(code.value, str)
            assert code == code.value  # str-Enum equality

    def test_budget_codes_present(self) -> None:
        assert ExtractorErrorCode.BUDGET_EXCEEDED == "budget_exceeded"
        assert (
            ExtractorErrorCode.BUDGET_EXCEEDED_RESUME_BLOCKED
            == "budget_exceeded_resume_blocked"
        )

    def test_eviction_codes_present(self) -> None:
        assert ExtractorErrorCode.EVICTION_ROUND_1_FAILED == "eviction_round_1_failed"
        assert ExtractorErrorCode.EVICTION_ROUND_2_FAILED == "eviction_round_2_failed"
        assert ExtractorErrorCode.EVICTION_ROUND_3_FAILED == "eviction_round_3_failed"

    def test_tantivy_codes_present(self) -> None:
        for code in [
            "tantivy_open_failed",
            "tantivy_commit_failed",
            "tantivy_disk_full",
            "tantivy_lock_held",
            "tantivy_delete_failed",
        ]:
            assert ExtractorErrorCode(code)

    def test_schema_codes_present(self) -> None:
        assert ExtractorErrorCode.SCHEMA_DRIFT_DETECTED == "schema_drift_detected"
        assert ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED == "schema_bootstrap_failed"

    def test_public_api_codes_present(self) -> None:
        assert (
            ExtractorErrorCode.PUBLIC_API_ARTIFACTS_REQUIRED
            == "public_api_artifacts_required"
        )
        assert ExtractorErrorCode.PUBLIC_API_PARSE_FAILED == "public_api_parse_failed"

    def test_counter_code_present(self) -> None:
        assert ExtractorErrorCode.COUNTER_STATE_CORRUPT == "counter_state_corrupt"

    def test_checkpoint_mismatch_present(self) -> None:
        assert (
            ExtractorErrorCode.CHECKPOINT_DOC_COUNT_MISMATCH
            == "checkpoint_doc_count_mismatch"
        )


class TestExtractorError:
    def test_basic_construction(self) -> None:
        err = ExtractorError(
            error_code=ExtractorErrorCode.BUDGET_EXCEEDED,
            message="budget exceeded",
            recoverable=False,
            action="raise_budget",
        )
        assert err.error_code == ExtractorErrorCode.BUDGET_EXCEEDED
        assert err.recoverable is False
        assert err.action == "raise_budget"
        assert err.phase is None
        assert err.partial_writes is None
        assert err.context == {}

    def test_with_phase_and_partial_writes(self) -> None:
        err = ExtractorError(
            error_code=ExtractorErrorCode.EVICTION_ROUND_1_FAILED,
            message="round 1 failed",
            recoverable=True,
            action="retry",
            phase="phase1_defs",
            partial_writes=500,
        )
        assert err.phase == "phase1_defs"
        assert err.partial_writes == 500

    def test_context_dict(self) -> None:
        err = ExtractorError(
            error_code=ExtractorErrorCode.COUNTER_STATE_CORRUPT,
            message="corrupt",
            recoverable=False,
            action="restore_backup",
            context={"path": "/var/lib/counter.json"},
        )
        assert err.context["path"] == "/var/lib/counter.json"
