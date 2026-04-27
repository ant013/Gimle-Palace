"""Restart-survivability integration test (GIM-101a, T13) — mocked driver.

Validates the full checkpoint → reconcile → resume path without real Neo4j.
Three scenarios:

1. Clean restart: checkpoint matches actual count → resume allowed.
2. Dirty restart: checkpoint mismatch → CHECKPOINT_DOC_COUNT_MISMATCH raised.
3. Budget-exceeded restart: previous error_code=budget_exceeded →
   BUDGET_EXCEEDED_RESUME_BLOCKED raised before any work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.foundation.checkpoint import reconcile_checkpoint, write_checkpoint
from palace_mcp.extractors.foundation.circuit_breaker import check_resume_budget
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import IngestCheckpoint


def _mock_write_driver() -> MagicMock:
    result = AsyncMock()
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


class TestCleanRestart:
    @pytest.mark.asyncio
    async def test_matching_counts_allow_resume(self) -> None:
        driver = _mock_write_driver()
        checkpoint = await write_checkpoint(
            driver,
            run_id="run-clean",
            project="gimle",
            phase="phase1_defs",
            expected_doc_count=1000,
        )
        # Simulate: actual Tantivy count == expected
        await reconcile_checkpoint(checkpoint=checkpoint, actual_doc_count=1000)
        # No exception → resume is allowed


class TestDirtyRestart:
    @pytest.mark.asyncio
    async def test_count_mismatch_blocks_resume(self) -> None:
        driver = _mock_write_driver()
        checkpoint = await write_checkpoint(
            driver,
            run_id="run-dirty",
            project="gimle",
            phase="phase2_user_uses",
            expected_doc_count=5000,
        )
        with pytest.raises(ExtractorError) as exc_info:
            await reconcile_checkpoint(checkpoint=checkpoint, actual_doc_count=4999)
        err = exc_info.value
        assert err.error_code == ExtractorErrorCode.CHECKPOINT_DOC_COUNT_MISMATCH
        assert err.recoverable is False
        assert err.partial_writes == 4999

    @pytest.mark.asyncio
    async def test_mismatch_message_contains_both_counts(self) -> None:
        cp = IngestCheckpoint(
            run_id="run-x",
            project="gimle",
            phase="phase1_defs",  # type: ignore[arg-type]
            expected_doc_count=9999,
            completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(ExtractorError) as exc_info:
            await reconcile_checkpoint(checkpoint=cp, actual_doc_count=8888)
        assert "9999" in exc_info.value.message
        assert "8888" in exc_info.value.message


class TestBudgetExceededRestart:
    def test_budget_exceeded_error_blocks_resume(self) -> None:
        with pytest.raises(ExtractorError) as exc_info:
            check_resume_budget(previous_error_code="budget_exceeded")
        err = exc_info.value
        assert err.error_code == ExtractorErrorCode.BUDGET_EXCEEDED_RESUME_BLOCKED
        assert err.recoverable is False
        assert "PALACE_MAX_OCCURRENCES_TOTAL" in err.message

    def test_no_previous_error_allows_resume(self) -> None:
        # Must not raise
        check_resume_budget(previous_error_code=None)

    def test_non_budget_error_allows_resume(self) -> None:
        # Other terminal errors (e.g. neo4j failure) don't block resume
        check_resume_budget(previous_error_code="neo4j_shadow_write_failed")


class TestPhaseCheckpointOrdering:
    @pytest.mark.asyncio
    async def test_multiple_phases_write_and_reconcile(self) -> None:
        driver = _mock_write_driver()

        cp1 = await write_checkpoint(
            driver,
            run_id="run-multi",
            project="gimle",
            phase="phase1_defs",
            expected_doc_count=100,
        )
        cp2 = await write_checkpoint(
            driver,
            run_id="run-multi",
            project="gimle",
            phase="phase2_user_uses",
            expected_doc_count=500,
        )

        # Both checkpoints reconcile cleanly
        await reconcile_checkpoint(checkpoint=cp1, actual_doc_count=100)
        await reconcile_checkpoint(checkpoint=cp2, actual_doc_count=500)

    @pytest.mark.asyncio
    async def test_phase1_mismatch_blocks_phase2(self) -> None:
        driver = _mock_write_driver()
        cp1 = await write_checkpoint(
            driver,
            run_id="run-fail",
            project="gimle",
            phase="phase1_defs",
            expected_doc_count=100,
        )
        with pytest.raises(ExtractorError) as exc_info:
            await reconcile_checkpoint(checkpoint=cp1, actual_doc_count=99)
        assert exc_info.value.error_code == ExtractorErrorCode.CHECKPOINT_DOC_COUNT_MISMATCH
