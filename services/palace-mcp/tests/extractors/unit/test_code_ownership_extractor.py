from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorOutcome, ExtractorRunContext
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
from palace_mcp.extractors.code_ownership.models import OwnershipRunSummary


def _make_summary(exit_reason: str) -> OwnershipRunSummary:
    return OwnershipRunSummary(
        project_id="project/testproj",
        run_id="run-1",
        head_sha="abc123",
        prev_head_sha="def456",
        dirty_files_count=0,
        deleted_files_count=0,
        edges_written=0,
        edges_deleted=0,
        mailmap_resolver_path="pygit2",
        exit_reason=exit_reason,
        duration_ms=0,
        alpha_used=0.5,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exit_reason", "expected_next_action"),
    [
        (
            "no_change",
            "Commit source changes or reset the ownership checkpoint before "
            "rerunning if a fresh baseline is required.",
        ),
        (
            "no_dirty",
            "Change tracked source files or reset the ownership checkpoint "
            "before rerunning if ownership output is expected.",
        ),
    ],
)
async def test_run_marks_non_work_exit_reasons_as_skipped(
    exit_reason: str, expected_next_action: str
) -> None:
    ctx = ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=Path("/tmp/testproj"),
        run_id="run-1",
        duration_ms=0,
        logger=MagicMock(),
    )
    graphiti = MagicMock(driver=MagicMock())

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=MagicMock()),
        patch.object(
            CodeOwnershipExtractor,
            "_run",
            new=AsyncMock(return_value=_make_summary(exit_reason)),
        ),
        patch.object(
            CodeOwnershipExtractor,
            "_write_run_extras",
            new=AsyncMock(),
        ),
    ):
        stats = await CodeOwnershipExtractor().run(graphiti=graphiti, ctx=ctx)

    assert stats.outcome == ExtractorOutcome.SKIPPED
    assert stats.edges_written == 0
    assert stats.message is not None
    assert stats.next_action == expected_next_action
