"""Task 2.6 — RED: hotspot fails fast when git_history has not run.

Root cause per postmortem 2026-05-13-hotspot-zero-scan-investigation.md:
without git_history data all churn values = 0, so all hotspot_scores = 0,
and the audit query (hotspot_score > 0) silently returns nothing.

Fix: add a prerequisite guard in HotspotExtractor.run() that raises
_HotspotError("prerequisite_missing") before lizard runs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorError, ExtractorRunContext
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor
from palace_mcp.extractors.hotspot.lizard_runner import LizardRunResult
from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction


def _fake_settings():
    s = MagicMock()
    s.palace_hotspot_lizard_batch_size = 50
    s.palace_hotspot_lizard_timeout_s = 30
    s.palace_hotspot_lizard_timeout_behavior = "drop_batch"
    s.palace_hotspot_churn_window_days = 90
    return s


def _make_driver(*, has_git_history: bool) -> MagicMock:
    """Driver whose session returns git_history presence for the prerequisite query."""
    row = {"n": 1} if has_git_history else {"n": 0}
    session = AsyncMock()
    result = AsyncMock()
    result.single = AsyncMock(return_value=row)
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


async def test_hotspot_fails_fast_without_git_history(tmp_path: Path) -> None:
    """Hotspot must raise error_code='prerequisite_missing' when git_history absent."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.swift").write_text("func bar() {}\n")

    graphiti = MagicMock()
    graphiti.driver = _make_driver(has_git_history=False)
    ctx = ExtractorRunContext(
        project_slug="tron-kit",
        group_id="project/tron-kit",
        repo_path=tmp_path,
        run_id="run-prereq-test",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        with pytest.raises(ExtractorError) as exc_info:
            await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    assert exc_info.value.error_code == "prerequisite_missing"


async def test_hotspot_proceeds_when_git_history_present(tmp_path: Path) -> None:
    """Hotspot does NOT raise when git_history has a successful run."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.swift").write_text("func bar() {}\n")

    graphiti = MagicMock()
    graphiti.driver = _make_driver(has_git_history=True)
    ctx = ExtractorRunContext(
        project_slug="tron-kit",
        group_id="project/tron-kit",
        repo_path=tmp_path,
        run_id="run-prereq-ok",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )

    # Lizard result must include ≥1 function to pass the lizard_parser_zero_functions invariant
    one_fn = ParsedFunction(name="bar", start_line=1, end_line=1, ccn=1, parameter_count=0, nloc=1)
    lizard_result = LizardRunResult(
        parsed=(ParsedFile(path="src/foo.swift", language="swift", functions=(one_fn,)),),
        skipped_files=(),
    )

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
        patch("palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
              new=AsyncMock(return_value=lizard_result)),
        patch("palace_mcp.extractors.hotspot.extractor.churn_query.fetch_churn",
              new=AsyncMock(return_value={"src/foo.swift": 3})),
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_file_and_functions",
              new=AsyncMock()),
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_hotspot_score",
              new=AsyncMock()),
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.evict_stale_functions",
              new=AsyncMock()),
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.mark_dead_files_zero",
              new=AsyncMock()),
    ):
        stats = await HotspotExtractor().run(graphiti=graphiti, ctx=ctx)

    assert stats.nodes_written == 2  # 1 :File + 1 :Function
