"""Unit tests for SymbolIndexPython extractor (mocked driver + bridge)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.symbol_index_python import SymbolIndexPython
from palace_mcp.proto import scip_pb2
from tests.extractors.fixtures.scip_factory import (
    build_minimal_scip_index,
    write_scip_fixture,
)


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


def _write_symbol_info_fixture(path: Path) -> Path:
    index = build_minimal_scip_index(
        symbols=[
            ("scip-python python example . ClassA .", 1),
            ("scip-python python example . ClassA . __init__ .", 1),
            ("scip-python python example . helper .", 1),
        ]
    )
    doc = index.documents[0]

    class_info = doc.symbols.add()
    class_info.symbol = "scip-python python example . ClassA ."
    class_info.kind = scip_pb2.SymbolInformation.Kind.Class  # type: ignore[attr-defined]

    method_info = doc.symbols.add()
    method_info.symbol = "scip-python python example . ClassA . __init__ ."
    method_info.kind = scip_pb2.SymbolInformation.Kind.Method  # type: ignore[attr-defined]

    function_info = doc.symbols.add()
    function_info.symbol = "scip-python python example . helper ."
    function_info.kind = scip_pb2.SymbolInformation.Kind.Function  # type: ignore[attr-defined]

    return write_scip_fixture(index, path)


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
            patch(
                "palace_mcp.extractors.symbol_index_python.ensure_custom_schema",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.create_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.finalize_ingest_run",
                AsyncMock(),
            ),
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
            patch(
                "palace_mcp.extractors.symbol_index_python.ensure_custom_schema",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.create_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.finalize_ingest_run",
                AsyncMock(),
            ),
        ):
            with pytest.raises(FileNotFoundError):
                await extractor.run(graphiti=graphiti, ctx=run_ctx)

    @pytest.mark.asyncio
    async def test_symbol_infos_are_written_to_symbol_graph(
        self,
        extractor: SymbolIndexPython,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        scip_path = _write_symbol_info_fixture(tmp_path / "symbols.scip")

        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-project": str(scip_path)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        driver = _make_driver()
        graphiti = AsyncMock()
        write_symbols = AsyncMock(return_value=3)
        soft_delete = AsyncMock(return_value=0)
        bridge = AsyncMock()
        bridge.commit_async = AsyncMock()
        bridge_cm = MagicMock()
        bridge_cm.__aenter__ = AsyncMock(return_value=bridge)
        bridge_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch(
                "palace_mcp.extractors.symbol_index_python.ensure_custom_schema",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.create_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.finalize_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.write_symbol_nodes",
                write_symbols,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.soft_delete_symbols",
                soft_delete,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python.TantivyBridge",
                return_value=bridge_cm,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_python._ingest_batch",
                AsyncMock(return_value=3),
            ),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=run_ctx)

        assert stats.nodes_written == 3
        write_symbols.assert_awaited_once()
        soft_delete.assert_awaited_once()
        assert write_symbols.await_args.kwargs["project_id"] == run_ctx.group_id
        assert write_symbols.await_args.kwargs["run_id"] == run_ctx.run_id
        assert len(write_symbols.await_args.args[1]) == 3
