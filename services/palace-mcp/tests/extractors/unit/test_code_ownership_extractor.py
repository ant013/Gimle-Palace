from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorOutcome, ExtractorRunContext
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
from palace_mcp.extractors.code_ownership.models import (
    OwnershipCheckpoint,
    OwnershipRunSummary,
)


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


class _FakeRepo:
    def __init__(self, head_sha: str) -> None:
        self.head = SimpleNamespace(target=head_sha)


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


@pytest.mark.asyncio
async def test_run_invalidates_same_head_checkpoint_without_file_state_baseline() -> None:
    checkpoint = OwnershipCheckpoint(
        project_id="project/testproj",
        last_head_sha="head-123",
        last_completed_at="2026-06-11T00:00:00+00:00",
        run_id="run-0",
        updated_at="2026-06-11T00:00:00+00:00",
    )
    settings = MagicMock(
        ownership_blame_weight=0.5,
        mailmap_max_bytes=1024,
        ownership_max_files_per_run=10,
    )
    mailmap = SimpleNamespace(path=SimpleNamespace(value="pygit2"))

    async def _run_in_place(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch(
            "palace_mcp.extractors.code_ownership.extractor.ensure_ownership_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.load_checkpoint",
            new=AsyncMock(return_value=checkpoint),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.has_file_state_baseline",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.delete_checkpoint",
            new=AsyncMock(),
        ) as delete_checkpoint,
        patch(
            "palace_mcp.extractors.code_ownership.extractor.update_checkpoint",
            new=AsyncMock(),
        ) as update_checkpoint,
        patch(
            "palace_mcp.extractors.code_ownership.extractor.pygit2.Repository",
            return_value=_FakeRepo("head-123"),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.MailmapResolver.from_repo",
            return_value=mailmap,
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.asyncio.to_thread",
            side_effect=_run_in_place,
        ),
        patch.object(CodeOwnershipExtractor, "_fetch_bot_identity_keys", new=AsyncMock(return_value=set())),
        patch.object(CodeOwnershipExtractor, "_fetch_known_author_ids", new=AsyncMock(return_value=set())),
        patch.object(CodeOwnershipExtractor, "_has_any_commits", new=AsyncMock(return_value=True)),
        patch.object(CodeOwnershipExtractor, "_all_files_in_head", return_value=set()),
    ):
        summary = await CodeOwnershipExtractor()._run(
            driver=MagicMock(),
            project_id="project/testproj",
            repo_path=Path("/tmp/testproj"),
            run_id="run-1",
            settings=settings,
        )

    delete_checkpoint.assert_awaited_once()
    update_checkpoint.assert_awaited_once()
    assert summary.exit_reason == "no_dirty"
    assert summary.prev_head_sha is None


@pytest.mark.asyncio
async def test_run_keeps_same_head_checkpoint_when_file_state_baseline_exists() -> None:
    checkpoint = OwnershipCheckpoint(
        project_id="project/testproj",
        last_head_sha="head-123",
        last_completed_at="2026-06-11T00:00:00+00:00",
        run_id="run-0",
        updated_at="2026-06-11T00:00:00+00:00",
    )
    settings = MagicMock(
        ownership_blame_weight=0.5,
        mailmap_max_bytes=1024,
    )
    mailmap = SimpleNamespace(path=SimpleNamespace(value="pygit2"))

    with (
        patch(
            "palace_mcp.extractors.code_ownership.extractor.ensure_ownership_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.load_checkpoint",
            new=AsyncMock(return_value=checkpoint),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.has_file_state_baseline",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.delete_checkpoint",
            new=AsyncMock(),
        ) as delete_checkpoint,
        patch(
            "palace_mcp.extractors.code_ownership.extractor.update_checkpoint",
            new=AsyncMock(),
        ) as update_checkpoint,
        patch(
            "palace_mcp.extractors.code_ownership.extractor.pygit2.Repository",
            return_value=_FakeRepo("head-123"),
        ),
        patch(
            "palace_mcp.extractors.code_ownership.extractor.MailmapResolver.from_repo",
            return_value=mailmap,
        ),
        patch.object(CodeOwnershipExtractor, "_fetch_bot_identity_keys", new=AsyncMock(return_value=set())),
        patch.object(CodeOwnershipExtractor, "_fetch_known_author_ids", new=AsyncMock(return_value=set())),
        patch.object(CodeOwnershipExtractor, "_has_any_commits", new=AsyncMock(return_value=True)),
    ):
        summary = await CodeOwnershipExtractor()._run(
            driver=MagicMock(),
            project_id="project/testproj",
            repo_path=Path("/tmp/testproj"),
            run_id="run-1",
            settings=settings,
        )

    delete_checkpoint.assert_not_awaited()
    update_checkpoint.assert_awaited_once()
    assert summary.exit_reason == "no_change"
    assert summary.prev_head_sha == "head-123"
