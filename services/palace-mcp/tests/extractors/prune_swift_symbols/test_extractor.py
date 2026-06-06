"""Extractor behavior tests for prune_swift_symbols."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorOutcome, ExtractorRunContext
from palace_mcp.extractors.prune_swift_symbols import PruneSwiftSymbols
from palace_mcp.extractors.prune_swift_symbols.cypher import (
    CREATE_DEPRECATION_EVENT,
    APPLY_DEPRECATION_BATCH,
)
from palace_mcp.extractors.prune_swift_symbols.extractor import _apply_deprecation


def _ctx(repo_path: Path, *, companion_run_id: str | None) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=repo_path,
        run_id="run-1",
        duration_ms=0,
        logger=logging.getLogger("test.prune_swift_symbols"),
        companion_run_id=companion_run_id,
    )


@pytest.mark.asyncio
async def test_companion_run_id_none_returns_graceful_noop(tmp_path: Path) -> None:
    graphiti = SimpleNamespace(driver=MagicMock())

    with patch(
        "palace_mcp.extractors.prune_swift_symbols.extractor.get_git_head_sha"
    ) as git_head:
        stats = await PruneSwiftSymbols().run(
            graphiti=graphiti, ctx=_ctx(tmp_path, companion_run_id=None)
        )

    git_head.assert_not_called()
    assert stats.outcome == ExtractorOutcome.SKIPPED
    assert stats.nodes_written == 0
    assert stats.message is not None
    assert "no companion run_id" in stats.message


@pytest.mark.asyncio
async def test_threshold_aborts_before_apply(tmp_path: Path) -> None:
    graphiti = SimpleNamespace(driver=MagicMock())

    with (
        patch(
            "palace_mcp.extractors.prune_swift_symbols.extractor.get_git_head_sha",
            return_value="abc123",
        ),
        patch(
            "palace_mcp.extractors.prune_swift_symbols.extractor._precheck_stale",
            new=AsyncMock(return_value=(6, 10)),
        ),
        patch(
            "palace_mcp.extractors.prune_swift_symbols.extractor._apply_deprecation",
            new=AsyncMock(),
        ) as apply_mock,
    ):
        stats = await PruneSwiftSymbols().run(
            graphiti=graphiti, ctx=_ctx(tmp_path, companion_run_id="companion-1")
        )

    apply_mock.assert_not_awaited()
    assert stats.outcome == ExtractorOutcome.SKIPPED
    assert stats.message is not None
    assert "would deprecate" in stats.message


@pytest.mark.asyncio
async def test_apply_deprecation_accumulates_batches_and_records_event() -> None:
    driver = MagicMock()
    batch_results = [
        SimpleNamespace(
            records=[{"batch_count": 100, "batch_files": 24, "batch_symbols": 76}]
        ),
        SimpleNamespace(
            records=[{"batch_count": 4, "batch_files": 1, "batch_symbols": 3}]
        ),
        SimpleNamespace(records=[{"batch_count": 0}]),
    ]
    event_result = SimpleNamespace(records=[{"event_id": "event-123"}])

    async def execute_query_side_effect(
        query: str, **kwargs: object
    ) -> SimpleNamespace:
        if query == APPLY_DEPRECATION_BATCH:
            return batch_results.pop(0)
        if query == CREATE_DEPRECATION_EVENT:
            return event_result
        raise AssertionError(f"unexpected query: {query}")

    driver.execute_query = AsyncMock(side_effect=execute_query_side_effect)

    result = await _apply_deprecation(
        driver,
        project_id="project/testproj",
        companion_run_id="symbol-run-123",
        head_sha="abc123",
        run_id="run-1",
        threshold_ratio_effective=0.6,
    )

    assert result.deprecated_count == 104
    assert result.deprecated_files == 25
    assert result.deprecated_symbols == 79
    assert result.event_id == "event-123"
    assert not batch_results
