"""Task 2.7 — RED: three loud-fail invariants for hotspot 0-scan detection.

Three mutually exclusive cases:

1. scanned_files == 0, db_file_count > 0 → data_mismatch_zero_scan_with_files_present
   (mount or stop-list mismatch; files present in Neo4j from prior run but walker finds nothing)

2. scanned_files == 0, db_file_count == 0 → empty_project
   (no source files found anywhere — repo genuinely empty or wrong mount)

3. scanned_files > 0, parsed_functions == 0 → lizard_parser_zero_functions
   (lizard ran but extracted 0 functions from all files — parser likely broken)
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from palace_mcp.extractors.base import ExtractorError, ExtractorRunContext
from palace_mcp.extractors.hotspot.extractor import HotspotExtractor
from palace_mcp.extractors.hotspot.lizard_runner import LizardRunResult
from palace_mcp.extractors.hotspot.models import ParsedFile


def _fake_settings():
    s = MagicMock()
    s.palace_hotspot_lizard_batch_size = 50
    s.palace_hotspot_lizard_timeout_s = 30
    s.palace_hotspot_lizard_timeout_behavior = "drop_batch"
    s.palace_hotspot_churn_window_days = 90
    return s


def _driver_with_git_history(db_file_count: int = 0) -> MagicMock:
    """Driver that passes the prerequisite check and returns db_file_count for the file query."""
    prereq_row = {"n": 1}  # git_history present
    file_count_row = {"n": db_file_count}

    results = [
        _single_result(prereq_row),   # prerequisite query
        _single_result(file_count_row),  # db file count query
    ]
    session = AsyncMock()
    session.run = AsyncMock(side_effect=results)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


def _single_result(row: dict) -> AsyncMock:
    result = AsyncMock()
    result.single = AsyncMock(return_value=row)
    return result


def _make_ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="tron-kit",
        group_id="project/tron-kit",
        repo_path=tmp_path,
        run_id="run-invariant-test",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


async def test_zero_scan_with_files_present_raises(tmp_path: Path) -> None:
    """file_walker returns 0 files but db has ≥1 File nodes → data_mismatch error."""
    # tmp_path has no source files (so file_walker finds nothing)
    graphiti = MagicMock()
    graphiti.driver = _driver_with_git_history(db_file_count=5)

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
    ):
        with pytest.raises(ExtractorError) as exc_info:
            await HotspotExtractor().run(graphiti=graphiti, ctx=_make_ctx(tmp_path))

    assert exc_info.value.error_code == "data_mismatch_zero_scan_with_files_present"


async def test_empty_project_raises(tmp_path: Path) -> None:
    """file_walker returns 0 files AND db has 0 File nodes → empty_project error."""
    graphiti = MagicMock()
    graphiti.driver = _driver_with_git_history(db_file_count=0)

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
    ):
        with pytest.raises(ExtractorError) as exc_info:
            await HotspotExtractor().run(graphiti=graphiti, ctx=_make_ctx(tmp_path))

    assert exc_info.value.error_code == "empty_project"


async def test_lizard_parser_zero_functions_raises(tmp_path: Path) -> None:
    """lizard scans files but finds 0 functions → lizard_parser_zero_functions error."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.swift").write_text("func bar() {}\n")

    graphiti = MagicMock()
    # Driver passes prerequisite; file count query unused (scanned_files > 0 short-circuits)
    graphiti.driver = _driver_with_git_history(db_file_count=0)

    empty_result = LizardRunResult(
        parsed=(ParsedFile(path="src/foo.swift", language="swift", functions=()),),
        skipped_files=(),
    )

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
        patch(
            "palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
            new=AsyncMock(return_value=empty_result),
        ),
    ):
        with pytest.raises(ExtractorError) as exc_info:
            await HotspotExtractor().run(graphiti=graphiti, ctx=_make_ctx(tmp_path))

    assert exc_info.value.error_code == "lizard_parser_zero_functions"
