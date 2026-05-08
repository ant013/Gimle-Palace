from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.registry import EXTRACTORS
from palace_mcp.extractors.testability_di import TestabilityDiExtractor


def test_import_returns_extractor_class() -> None:
    assert TestabilityDiExtractor.__name__ == "TestabilityDiExtractor"


def test_scaffold_name_matches_registry_key() -> None:
    assert TestabilityDiExtractor().name == "testability_di"


def test_extractor_registered() -> None:
    extractor = EXTRACTORS.get("testability_di")
    assert extractor is not None
    assert extractor.name == "testability_di"


@pytest.mark.asyncio
async def test_run_returns_empty_stats_for_empty_repo(tmp_path: Path) -> None:
    ctx = ExtractorRunContext(
        project_slug="wallet",
        group_id="project/wallet",
        repo_path=tmp_path,
        run_id="run-empty",
        duration_ms=0,
        logger=logging.getLogger("test.testability_di.empty"),
    )

    stats = await TestabilityDiExtractor().run(
        graphiti=MagicMock(),
        ctx=ctx,
    )

    assert stats.nodes_written == 0
    assert stats.edges_written == 0
