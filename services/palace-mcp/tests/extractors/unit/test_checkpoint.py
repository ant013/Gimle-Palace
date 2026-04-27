"""Unit tests for IngestCheckpoint + reconciliation (GIM-101a, T8) — mocked driver."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run,
    finalize_ingest_run,
    reconcile_checkpoint,
    write_checkpoint,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import IngestCheckpoint


def _mock_driver(records: list[dict[str, object]] | None = None) -> MagicMock:
    result = AsyncMock()
    result.data = AsyncMock(return_value=records or [])
    session = AsyncMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def _make_checkpoint(
    expected_doc_count: int = 1000,
    phase: str = "phase1_defs",
) -> IngestCheckpoint:
    return IngestCheckpoint(
        run_id="run-1",
        project="gimle",
        phase=phase,  # type: ignore[arg-type]
        expected_doc_count=expected_doc_count,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestCreateIngestRun:
    @pytest.mark.asyncio
    async def test_creates_run(self) -> None:
        driver = _mock_driver()
        await create_ingest_run(
            driver, run_id="run-1", project="gimle", extractor_name="heartbeat"
        )
        driver.session.return_value.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_id_in_query_params(self) -> None:
        driver = _mock_driver()
        await create_ingest_run(
            driver, run_id="run-abc", project="gimle", extractor_name="heartbeat"
        )
        call_kwargs = driver.session.return_value.run.call_args
        # run_id should appear in the call arguments
        all_args = str(call_kwargs)
        assert "run-abc" in all_args


class TestFinalizeIngestRun:
    @pytest.mark.asyncio
    async def test_finalize_success(self) -> None:
        driver = _mock_driver()
        await finalize_ingest_run(driver, run_id="run-1", success=True)
        driver.session.return_value.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_failure_with_error_code(self) -> None:
        driver = _mock_driver()
        await finalize_ingest_run(
            driver, run_id="run-1", success=False, error_code="budget_exceeded"
        )
        driver.session.return_value.run.assert_called_once()


class TestWriteCheckpoint:
    @pytest.mark.asyncio
    async def test_write_returns_checkpoint(self) -> None:
        driver = _mock_driver()
        cp = await write_checkpoint(
            driver,
            run_id="run-1",
            project="gimle",
            phase="phase1_defs",
            expected_doc_count=500,
        )
        assert cp.expected_doc_count == 500
        assert cp.phase == "phase1_defs"
        assert cp.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_write_calls_merge_cypher(self) -> None:
        driver = _mock_driver()
        await write_checkpoint(
            driver,
            run_id="run-x",
            project="gimle",
            phase="phase2_user_uses",
            expected_doc_count=999,
        )
        driver.session.return_value.run.assert_called_once()


class TestReconcileCheckpoint:
    @pytest.mark.asyncio
    async def test_matching_count_no_error(self) -> None:
        cp = _make_checkpoint(expected_doc_count=1000)
        await reconcile_checkpoint(checkpoint=cp, actual_doc_count=1000)

    @pytest.mark.asyncio
    async def test_mismatch_raises_checkpoint_mismatch_error(self) -> None:
        cp = _make_checkpoint(expected_doc_count=1000)
        with pytest.raises(ExtractorError) as exc_info:
            await reconcile_checkpoint(checkpoint=cp, actual_doc_count=999)
        assert (
            exc_info.value.error_code
            == ExtractorErrorCode.CHECKPOINT_DOC_COUNT_MISMATCH
        )
        assert exc_info.value.recoverable is False
        assert exc_info.value.action == "rebuild_tantivy"
        assert exc_info.value.partial_writes == 999

    @pytest.mark.asyncio
    async def test_mismatch_message_contains_counts(self) -> None:
        cp = _make_checkpoint(expected_doc_count=5000)
        with pytest.raises(ExtractorError) as exc_info:
            await reconcile_checkpoint(checkpoint=cp, actual_doc_count=4999)
        assert "5000" in exc_info.value.message
        assert "4999" in exc_info.value.message
