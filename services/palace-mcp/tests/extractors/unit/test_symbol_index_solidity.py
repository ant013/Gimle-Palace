"""Unit tests for SymbolIndexSolidity extractor (mocked driver + bridge)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.symbol_index_solidity import SymbolIndexSolidity
from tests.extractors.fixtures.scip_factory import (
    build_solidity_scip_index,
    write_scip_fixture,
)


@pytest.fixture
def extractor() -> SymbolIndexSolidity:
    return SymbolIndexSolidity()


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    index = build_solidity_scip_index(
        symbols=[
            (
                "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#.",
                1,
            ),
            (
                "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#transfer().",
                1,
            ),
            (
                "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#transfer().",
                0,
            ),
        ],
    )
    return write_scip_fixture(index, tmp_path / "test.scip")


@pytest.fixture
def run_ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="oz-v5-mini",
        group_id="project/oz-v5-mini",
        repo_path=tmp_path,
        run_id="test-run-solidity-001",
        duration_ms=0,
        logger=MagicMock(),
    )


def _make_driver() -> MagicMock:
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


class TestSymbolIndexSolidityMeta:
    def test_name_is_correct(self, extractor: SymbolIndexSolidity) -> None:
        assert extractor.name == "symbol_index_solidity"

    def test_description_mentions_solidity(
        self, extractor: SymbolIndexSolidity
    ) -> None:
        desc = extractor.description.lower()
        assert "solidity" in desc

    def test_primary_lang_is_solidity(self, extractor: SymbolIndexSolidity) -> None:
        assert extractor.primary_lang == Language.SOLIDITY


class TestSymbolIndexSolidityErrorHandling:
    @pytest.mark.asyncio
    async def test_missing_scip_path_raises_extractor_error(
        self,
        extractor: SymbolIndexSolidity,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        driver = _make_driver()
        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_tantivy_heap_mb = 100

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.ensure_custom_schema",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.create_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.finalize_ingest_run",
                AsyncMock(),
            ),
        ):
            with pytest.raises(ExtractorError) as exc_info:
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert exc_info.value.error_code == ExtractorErrorCode.SCIP_PATH_REQUIRED

    @pytest.mark.asyncio
    async def test_no_driver_raises_extractor_error(
        self,
        extractor: SymbolIndexSolidity,
        run_ctx: ExtractorRunContext,
    ) -> None:
        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=None),
            patch("palace_mcp.mcp_server.get_settings", return_value=MagicMock()),
        ):
            with pytest.raises(ExtractorError):
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)


class TestSymbolIndexSolidityHappyPath:
    @pytest.mark.asyncio
    async def test_run_reads_scip_path_from_settings(
        self,
        extractor: SymbolIndexSolidity,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
    ) -> None:
        driver = _make_driver()
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {"oz-v5-mini": str(scip_fixture)}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_tantivy_heap_mb = 100
        settings.palace_recency_decay_days = 30.0

        bridge_mock = AsyncMock()
        bridge_mock.__aenter__ = AsyncMock(return_value=bridge_mock)
        bridge_mock.__aexit__ = AsyncMock(return_value=False)
        bridge_mock.add_or_replace_async = AsyncMock()
        bridge_mock.commit_async = AsyncMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.TantivyBridge",
                return_value=bridge_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.ensure_custom_schema",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.create_ingest_run",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.write_checkpoint",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_solidity.finalize_ingest_run",
                new_callable=AsyncMock,
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert stats.nodes_written >= 1
