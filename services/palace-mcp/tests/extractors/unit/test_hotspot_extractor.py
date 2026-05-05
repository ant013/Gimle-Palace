from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
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


@pytest.mark.asyncio
async def test_run_executes_phases_in_order(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def x(): pass\n")

    pf = ParsedFile(
        path="src/a.py", language="python",
        functions=(ParsedFunction(
            name="x", start_line=1, end_line=1, ccn=1,
            parameter_count=0, nloc=1,
        ),),
    )
    fake_run_result = LizardRunResult(parsed=(pf,), skipped_files=())

    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    ctx = ExtractorRunContext(
        project_slug="testproj", group_id="project/testproj",
        repo_path=tmp_path, run_id="run-1", duration_ms=0,
        logger=logging.getLogger("test"),
    )

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
        patch("palace_mcp.extractors.hotspot.extractor.lizard_runner.run_batch",
              new=AsyncMock(return_value=fake_run_result)),
        patch("palace_mcp.extractors.hotspot.extractor.churn_query.fetch_churn",
              new=AsyncMock(return_value={"src/a.py": 5})),
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_file_and_functions",
              new=AsyncMock()) as m_p1,
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.write_hotspot_score",
              new=AsyncMock()) as m_p3,
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.evict_stale_functions",
              new=AsyncMock()) as m_p4,
        patch("palace_mcp.extractors.hotspot.extractor.neo4j_writer.mark_dead_files_zero",
              new=AsyncMock()) as m_p5,
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
