"""Unit tests for SymbolIndexPython extractor (mocked driver + bridge)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.symbol_index_python import SymbolIndexPython
from tests.extractors.fixtures.scip_factory import build_minimal_scip_index, write_scip_fixture


@pytest.fixture
def extractor() -> SymbolIndexPython:
    return SymbolIndexPython()


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    index = build_minimal_scip_index(
        symbols=[
            ("scip-python python example . ClassA .", 1),
            ("scip-python python example . func_b .", 1),
            ("scip-python python example . func_b .", 0),
        ],
    )
    return write_scip_fixture(index, tmp_path / "test.scip")


@pytest.fixture
def run_ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="test-project",
        group_id="project/test-project",
        repo_path=tmp_path,
        run_id="test-run-001",
        duration_ms=0,
        logger=MagicMock(),
    )


def _make_driver() -> MagicMock:
    """Build a mock AsyncDriver with session() returning an async context manager."""
    inner_session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=None)
    inner_session.run = AsyncMock(return_value=result_mock)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=inner_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session.return_value = session_cm
    return driver


class TestSymbolIndexPythonMeta:
    def test_name(self, extractor: SymbolIndexPython) -> None:
        assert extractor.name == "symbol_index_python"

    def test_description_nonempty(self, extractor: SymbolIndexPython) -> None:
        assert len(extractor.description) > 10


class TestSymbolIndexPythonRun:
    @pytest.mark.asyncio
    async def test_missing_scip_path_raises_extractor_error(
        self,
        extractor: SymbolIndexPython,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        """CR F6: must raise ExtractorError with SCIP_PATH_REQUIRED code."""
        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        driver = _make_driver()
        graphiti = AsyncMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch("palace_mcp.extractors.symbol_index_python.ensure_custom_schema", AsyncMock()),
            patch("palace_mcp.extractors.symbol_index_python.create_ingest_run", AsyncMock()),
            patch("palace_mcp.extractors.symbol_index_python.finalize_ingest_run", AsyncMock()),
        ):
            with pytest.raises(ExtractorError) as exc_info:
                await extractor.run(graphiti=graphiti, ctx=run_ctx)
            assert exc_info.value.error_code == ExtractorErrorCode.SCIP_PATH_REQUIRED

    @pytest.mark.asyncio
    async def test_scip_file_not_found_raises(
        self,
        extractor: SymbolIndexPython,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        """CR F6: must raise FileNotFoundError for nonexistent .scip path."""
        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-project": "/nonexistent/path.scip"}
        settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        driver = _make_driver()
        graphiti = AsyncMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch("palace_mcp.extractors.symbol_index_python.ensure_custom_schema", AsyncMock()),
            patch("palace_mcp.extractors.symbol_index_python.create_ingest_run", AsyncMock()),
            patch("palace_mcp.extractors.symbol_index_python.finalize_ingest_run", AsyncMock()),
        ):
            with pytest.raises(FileNotFoundError):
                await extractor.run(graphiti=graphiti, ctx=run_ctx)
