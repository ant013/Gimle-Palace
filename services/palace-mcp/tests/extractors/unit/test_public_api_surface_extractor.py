"""Unit tests for public_api_surface missing-input handling."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorOutcome, ExtractorRunContext
from palace_mcp.extractors.public_api_surface import PublicApiSurfaceExtractor


def _ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="tron-kit",
        group_id="project/tron-kit",
        repo_path=repo_path,
        run_id="run-public-api",
        duration_ms=0,
        logger=logging.getLogger("test.public_api_surface"),
    )


@pytest.mark.asyncio
async def test_run_reports_missing_input_when_public_api_artifacts_are_absent(
    tmp_path: Path,
) -> None:
    with patch("palace_mcp.mcp_server.get_driver", return_value=MagicMock()):
        stats = await PublicApiSurfaceExtractor().run(
            graphiti=MagicMock(),
            ctx=_ctx(tmp_path),
        )

    assert stats.outcome == ExtractorOutcome.MISSING_INPUT
    assert stats.message is not None
    assert ".palace/public-api" in stats.message
    assert stats.next_action is not None
