from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import (
    ExtractorExecutionMode,
    ExtractorOutcome,
    ExtractorRunContext,
)
from palace_mcp.extractors.foundation.incremental_scope import (
    IncrementalMode,
    IncrementalPathScope,
)
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor
from palace_mcp.extractors.hotspot.lizard_runner import LizardRunResult
from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction


def _fake_settings():
    s = MagicMock()
    s.palace_incremental_ingest = False
    s.palace_hotspot_lizard_batch_size = 50
    s.palace_hotspot_lizard_timeout_s = 30
    s.palace_hotspot_lizard_timeout_behavior = "drop_batch"
    s.palace_hotspot_churn_window_days = 90
    return s


@pytest.mark.asyncio
async def test_run_executes_phases_in_order(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def x(): pass\n")

    pf = ParsedFile(
        path="src/a.py",
        language="python",
        functions=(
            ParsedFunction(
                name="x",
                start_line=1,
                end_line=1,
                ccn=1,
                parameter_count=0,
                nloc=1,
            ),
        ),
    )
    fake_run_result = LizardRunResult(parsed=(pf,), skipped_files=())

    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=tmp_path,
        run_id="run-1",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
        patch(
            "palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
            new=AsyncMock(return_value=fake_run_result),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor._head_commit_as_of",
            return_value=__import__("datetime").datetime(
                2026, 5, 4, 12, 0, tzinfo=__import__("datetime").timezone.utc
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.churn_query.fetch_churn",
            new=AsyncMock(return_value={"src/a.py": 5}),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_file_and_functions",
            new=AsyncMock(),
        ) as m_p1,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_hotspot_score",
            new=AsyncMock(),
        ) as m_p3,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.evict_stale_functions",
            new=AsyncMock(),
        ) as m_p4,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.mark_dead_files_zero",
            new=AsyncMock(),
        ) as m_p5,
    ):
        stats = await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    m_p1.assert_awaited_once()
    m_p3.assert_awaited_once()
    m_p4.assert_awaited_once()
    m_p5.assert_awaited_once()

    p3_kwargs = m_p3.await_args.kwargs
    expected = pytest.approx(__import__("math").log(2) * __import__("math").log(6))
    assert p3_kwargs["score"] == expected
    assert p3_kwargs["churn"] == 5
    assert p3_kwargs["window_days"] == 90
    assert stats.nodes_written >= 1
    assert stats.mode == ExtractorExecutionMode.FULL


@pytest.mark.asyncio
async def test_run_preserves_skipped_files_from_destructive_cleanup(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def x(): pass\n")
    (src / "skipped.py").write_text("def y(): pass\n")

    pf = ParsedFile(
        path="src/a.py",
        language="python",
        functions=(
            ParsedFunction(
                name="x",
                start_line=1,
                end_line=1,
                ccn=1,
                parameter_count=0,
                nloc=1,
            ),
        ),
    )
    fake_run_result = LizardRunResult(
        parsed=(pf,),
        skipped_files=("src/skipped.py",),
    )

    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=tmp_path,
        run_id="run-1",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
        patch(
            "palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
            new=AsyncMock(return_value=fake_run_result),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor._head_commit_as_of",
            return_value=__import__("datetime").datetime(
                2026, 5, 4, 12, 0, tzinfo=__import__("datetime").timezone.utc
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.churn_query.fetch_churn",
            new=AsyncMock(return_value={"src/a.py": 5}),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_file_and_functions",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_hotspot_score",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.evict_stale_functions",
            new=AsyncMock(),
        ) as m_p4,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.mark_dead_files_zero",
            new=AsyncMock(),
        ) as m_p5,
    ):
        await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    expected_paths = ["src/a.py", "src/skipped.py"]
    assert m_p4.await_args.kwargs["preserved_paths"] == expected_paths
    assert m_p5.await_args.kwargs["preserved_paths"] == expected_paths


@pytest.mark.asyncio
async def test_run_incremental_only_scans_changed_files_and_zeroes_deleted_files(
    tmp_path: Path,
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def x(): pass\n")
    (src / "deleted.py").write_text("def y(): pass\n")

    settings = _fake_settings()
    settings.palace_incremental_ingest = True
    pf = ParsedFile(
        path="src/a.py",
        language="python",
        functions=(
            ParsedFunction(
                name="x",
                start_line=1,
                end_line=1,
                ccn=1,
                parameter_count=0,
                nloc=1,
            ),
        ),
    )
    fake_run_result = LizardRunResult(parsed=(pf,), skipped_files=())

    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=tmp_path,
        run_id="run-2",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.hotspot.extractor._head_commit_as_of",
            return_value=__import__("datetime").datetime(
                2026, 5, 4, 12, 0, tzinfo=__import__("datetime").timezone.utc
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.derive_incremental_path_scope",
            new=AsyncMock(
                return_value=IncrementalPathScope(
                    mode=IncrementalMode.INCREMENTAL,
                    changed_paths={"src/a.py"},
                    removed_paths={"src/deleted.py"},
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
            new=AsyncMock(return_value=fake_run_result),
        ) as m_lizard,
        patch(
            "palace_mcp.extractors.hotspot.extractor.churn_query.fetch_churn",
            new=AsyncMock(return_value={"src/a.py": 5, "src/untouched.py": 3}),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_file_and_functions",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_hotspot_score",
            new=AsyncMock(),
        ) as m_score,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.fetch_active_file_complexities",
            new=AsyncMock(return_value={"src/a.py": 1, "src/untouched.py": 4}),
        ) as m_complexities,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.evict_stale_functions_for_paths",
            new=AsyncMock(),
        ) as m_evict,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.mark_deleted_files_zero",
            new=AsyncMock(),
        ) as m_zero,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.evict_stale_functions",
            new=AsyncMock(),
        ) as m_full_evict,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.mark_dead_files_zero",
            new=AsyncMock(),
        ) as m_full_zero,
    ):
        stats = await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    batch = m_lizard.await_args.args[0]
    assert batch == [tmp_path / "src" / "a.py"]
    assert m_complexities.await_args.kwargs["excluded_paths"] == ["src/deleted.py"]
    assert {call.kwargs["path"] for call in m_score.await_args_list} == {
        "src/a.py",
        "src/untouched.py",
    }
    assert m_evict.await_args.kwargs["paths"] == ["src/a.py", "src/deleted.py"]
    assert m_zero.await_args.kwargs["paths"] == ["src/deleted.py"]
    m_full_evict.assert_not_awaited()
    m_full_zero.assert_not_awaited()
    assert stats.mode == ExtractorExecutionMode.INCREMENTAL


@pytest.mark.asyncio
async def test_run_incremental_skips_when_no_relevant_changes(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def x(): pass\n")

    settings = _fake_settings()
    settings.palace_incremental_ingest = True
    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=tmp_path,
        run_id="run-3",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.hotspot.extractor._head_commit_as_of",
            return_value=__import__("datetime").datetime(
                2026, 5, 4, 12, 0, tzinfo=__import__("datetime").timezone.utc
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.derive_incremental_path_scope",
            new=AsyncMock(
                return_value=IncrementalPathScope(
                    mode=IncrementalMode.SKIP,
                    changed_paths=set(),
                    removed_paths=set(),
                    reason="no_relevant_changes",
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
            new=AsyncMock(),
        ) as m_lizard,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.fetch_active_file_complexities",
            new=AsyncMock(return_value={}),
        ) as m_complexities,
    ):
        stats = await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    m_lizard.assert_not_awaited()
    m_complexities.assert_awaited_once()
    assert stats.outcome == ExtractorOutcome.SKIPPED
    assert stats.mode == ExtractorExecutionMode.SKIPPED


@pytest.mark.asyncio
async def test_run_incremental_refreshes_scores_when_no_hotspot_files_changed(
    tmp_path: Path,
):
    settings = _fake_settings()
    settings.palace_incremental_ingest = True
    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=tmp_path,
        run_id="run-4",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    existing_complexities = {"src/untouched.py": 4}
    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.hotspot.extractor._head_commit_as_of",
            return_value=__import__("datetime").datetime(
                2026, 5, 5, 12, 0, tzinfo=__import__("datetime").timezone.utc
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.derive_incremental_path_scope",
            new=AsyncMock(
                return_value=IncrementalPathScope(
                    mode=IncrementalMode.SKIP,
                    changed_paths=set(),
                    removed_paths=set(),
                    reason="no_relevant_changes",
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.fetch_active_file_complexities",
            new=AsyncMock(side_effect=[existing_complexities, existing_complexities]),
        ) as m_complexities,
        patch(
            "palace_mcp.extractors.hotspot.extractor.churn_query.fetch_churn",
            new=AsyncMock(return_value={"src/untouched.py": 2}),
        ),
        patch(
            "palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
            new=AsyncMock(),
        ) as m_lizard,
        patch(
            "palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_hotspot_score",
            new=AsyncMock(),
        ) as m_score,
    ):
        stats = await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    m_lizard.assert_not_awaited()
    assert m_complexities.await_count == 2
    m_score.assert_awaited_once()
    assert m_score.await_args.kwargs["path"] == "src/untouched.py"
    assert stats.mode == ExtractorExecutionMode.INCREMENTAL


def test_run_no_try_except_around_inner_phases():
    """invariant 7: extractor.run() must not wrap inner phases in try/except."""
    import re
    from palace_mcp.extractors.hotspot import extractor as ext_mod

    src = Path(ext_mod.__file__).read_text(encoding="utf-8")
    m = re.search(r"async def run\(self,.*?\n(?P<body>(?: {4,}.*\n|\n)+)", src)
    assert m is not None
    body = m.group("body")
    assert "try:" not in body, (
        "extractor.run() must not contain try/except around inner phases (invariant 7)"
    )
