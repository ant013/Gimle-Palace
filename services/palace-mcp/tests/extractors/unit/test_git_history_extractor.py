from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from palace_mcp.extractors.git_history.extractor import GitHistoryExtractor
from palace_mcp.extractors.base import ExtractorRunContext, ExtractorStats

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=repo_path,
        run_id="run-1",
        duration_ms=0,
        logger=MagicMock(),
    )


@pytest.mark.asyncio
async def test_run_returns_extractor_stats(tmp_path: Path):
    """Smoke: extractor returns ExtractorStats with both counters set."""
    from tests.extractors.unit.test_git_history_pygit2_walker import _build_synthetic_repo
    repo_path = _build_synthetic_repo(tmp_path, n_commits=2)

    fake_driver = MagicMock()
    fake_driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    fake_settings = MagicMock(github_token=None,
                              git_history_tantivy_index_path=tmp_path / "tnt")

    with patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver), \
         patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings), \
         patch("palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor._get_previous_error_code",
               new=AsyncMock(return_value=None)), \
         patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.create_ingest_run",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
               new=AsyncMock()):
        extractor = GitHistoryExtractor()
        stats = await extractor.run(graphiti=MagicMock(),
                                    ctx=_make_ctx(Path(repo_path)))
    assert isinstance(stats, ExtractorStats)
    assert stats.nodes_written >= 2  # at least 2 commits
    assert stats.edges_written >= 4  # AUTHORED_BY + COMMITTED_BY × 2 commits


@pytest.mark.asyncio
async def test_run_skips_phase2_when_no_github_token(tmp_path: Path, caplog):
    """When PALACE_GITHUB_TOKEN unset, Phase 2 emits skip event + Phase 1 still runs."""
    import logging
    from tests.extractors.unit.test_git_history_pygit2_walker import _build_synthetic_repo
    repo_path = _build_synthetic_repo(tmp_path, n_commits=1)
    fake_driver = MagicMock()
    fake_driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    fake_settings = MagicMock(github_token=None,
                              git_history_tantivy_index_path=tmp_path / "tnt")
    with patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver), \
         patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings), \
         patch("palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor._get_previous_error_code",
               new=AsyncMock(return_value=None)), \
         patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.create_ingest_run",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
               new=AsyncMock()), \
         caplog.at_level(logging.WARNING):
        extractor = GitHistoryExtractor()
        await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(Path(repo_path)))
    skip_events = [r for r in caplog.records
                   if getattr(r, "event", None) == "git_history_phase2_skipped_no_token"]
    assert len(skip_events) == 1


@pytest.mark.asyncio
async def test_run_emits_resync_event_on_invalid_checkpoint(tmp_path: Path, caplog):
    """Force-push scenario: load checkpoint with invalid sha; walker resyncs."""
    import logging
    from tests.extractors.unit.test_git_history_pygit2_walker import _build_synthetic_repo
    repo_path = _build_synthetic_repo(tmp_path, n_commits=2)

    bogus_sha = "f" * 40
    fake_driver = MagicMock()

    async def _fake_execute(query, **kwargs):
        if "MATCH (c:GitHistoryCheckpoint" in query:
            mock_record = MagicMock()
            mock_record.__getitem__ = lambda _, k: {
                "project_id": "project/gimle",
                "last_commit_sha": bogus_sha,
                "last_pr_updated_at": None,
                "last_phase_completed": "phase1",
                "updated_at": UTC_TS,
            }[k]
            return MagicMock(records=[mock_record])
        return MagicMock(records=[])

    fake_driver.execute_query = AsyncMock(side_effect=_fake_execute)
    fake_settings = MagicMock(github_token=None,
                              git_history_tantivy_index_path=tmp_path / "tnt")

    with patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver), \
         patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings), \
         patch("palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor._get_previous_error_code",
               new=AsyncMock(return_value=None)), \
         patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.create_ingest_run",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
               new=AsyncMock()), \
         caplog.at_level(logging.WARNING):
        extractor = GitHistoryExtractor()
        await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(Path(repo_path)))
    resync_events = [r for r in caplog.records
                     if getattr(r, "event", None) == "git_history_resync_full"]
    assert len(resync_events) == 1
