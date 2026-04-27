"""Unit tests for hard circuit breaker (GIM-101a, T11)."""

from __future__ import annotations

import pytest

from palace_mcp.extractors.foundation.circuit_breaker import check_phase_budget, check_resume_budget
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode


class TestCheckPhaseBudget:
    def test_under_budget_no_raise(self) -> None:
        check_phase_budget(
            nodes_written_so_far=999,
            max_occurrences_total=1000,
            phase="phase1_defs",
        )

    def test_at_budget_raises(self) -> None:
        with pytest.raises(ExtractorError) as exc_info:
            check_phase_budget(
                nodes_written_so_far=1000,
                max_occurrences_total=1000,
                phase="phase1_defs",
            )
        err = exc_info.value
        assert err.error_code == ExtractorErrorCode.BUDGET_EXCEEDED
        assert err.recoverable is False
        assert err.action == "raise_budget"
        assert err.phase == "phase1_defs"
        assert err.partial_writes == 1000

    def test_over_budget_raises(self) -> None:
        with pytest.raises(ExtractorError) as exc_info:
            check_phase_budget(
                nodes_written_so_far=50_000_001,
                max_occurrences_total=50_000_000,
                phase="phase2_user_uses",
            )
        err = exc_info.value
        assert err.error_code == ExtractorErrorCode.BUDGET_EXCEEDED
        assert "50000001" in err.message

    def test_message_contains_phase(self) -> None:
        with pytest.raises(ExtractorError) as exc_info:
            check_phase_budget(
                nodes_written_so_far=100,
                max_occurrences_total=100,
                phase="phase3_vendor_uses",
            )
        assert "phase3_vendor_uses" in exc_info.value.message

    def test_zero_written_under_cap_no_raise(self) -> None:
        check_phase_budget(
            nodes_written_so_far=0,
            max_occurrences_total=50_000_000,
            phase="phase1_defs",
        )


class TestCheckResumeBudget:
    def test_no_previous_error_no_raise(self) -> None:
        check_resume_budget(previous_error_code=None)

    def test_other_error_code_no_raise(self) -> None:
        check_resume_budget(previous_error_code="neo4j_shadow_write_failed")

    def test_budget_exceeded_raises_resume_blocked(self) -> None:
        with pytest.raises(ExtractorError) as exc_info:
            check_resume_budget(previous_error_code="budget_exceeded")
        err = exc_info.value
        assert err.error_code == ExtractorErrorCode.BUDGET_EXCEEDED_RESUME_BLOCKED
        assert err.recoverable is False
        assert err.action == "raise_budget"

    def test_resume_blocked_message_mentions_budget_override(self) -> None:
        with pytest.raises(ExtractorError) as exc_info:
            check_resume_budget(previous_error_code="budget_exceeded")
        assert "PALACE_BUDGET_OVERRIDE" in exc_info.value.message
