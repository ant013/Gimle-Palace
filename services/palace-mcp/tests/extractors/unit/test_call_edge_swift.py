from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.code.indexstore import CallEdgeRecord, CallEdgeScanResult
from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.call_edge_swift import CallEdgeSwiftExtractor


def _ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=tmp_path,
        run_id="run-001",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


def test_extractor_registered() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS.get("call_edge_swift")
    assert extractor is not None
    assert extractor.name == "call_edge_swift"
    assert extractor.description


def test_call_edge_swift_in_swift_kit_default_order_after_symbol_index() -> None:
    from palace_mcp.extractors.foundation.profiles import SWIFT_KIT_EXTRACTOR_ORDER

    assert SWIFT_KIT_EXTRACTOR_ORDER.index("call_edge_swift") == (
        SWIFT_KIT_EXTRACTOR_ORDER.index("symbol_index_swift") + 1
    )


@pytest.mark.asyncio
async def test_run_returns_missing_input_without_indexstore_path(tmp_path: Path) -> None:
    extractor = CallEdgeSwiftExtractor()
    graphiti = MagicMock()

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=MagicMock()),
        patch(
            "palace_mcp.mcp_server.get_settings",
            return_value=SimpleNamespace(
                palace_indexstore_paths={},
                palace_sourcekit_index_store_path=None,
            ),
        ),
    ):
        stats = await extractor.run(graphiti=graphiti, ctx=_ctx(tmp_path))

    assert stats.outcome.value == "missing_input"
    assert stats.edges_written == 0
    assert "No IndexStore path configured" in (stats.message or "")


@pytest.mark.asyncio
async def test_run_drops_edges_without_active_symbols(tmp_path: Path) -> None:
    extractor = CallEdgeSwiftExtractor()
    graphiti = MagicMock()
    driver = MagicMock()
    session = AsyncMock()
    session.run = AsyncMock(
        side_effect=[
            MagicMock(data=AsyncMock(return_value=[{"qualified_name": "UwMiniCore caller"}])),
            MagicMock(),
            MagicMock(),
        ]
    )
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver.session = MagicMock(return_value=session)

    store_path = tmp_path / "DataStore"
    (store_path / "v5").mkdir(parents=True)
    scan_result = CallEdgeScanResult(
        edges=(
            CallEdgeRecord(source="UwMiniCore caller", target="UwMiniCore callee"),
            CallEdgeRecord(source="UwMiniCore caller", target="UwMiniCore missing"),
        ),
        counters={"calls_seen": 2, "missing_relation": 0},
        records_scanned=1,
        occurrences_scanned=2,
    )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch(
            "palace_mcp.mcp_server.get_settings",
            return_value=SimpleNamespace(
                palace_indexstore_paths={"gimle": str(store_path)},
                palace_sourcekit_index_store_path=None,
            ),
        ),
        patch(
            "palace_mcp.extractors.call_edge_swift.collect_call_edges",
            return_value=scan_result,
        ),
    ):
        stats = await extractor.run(graphiti=graphiti, ctx=_ctx(tmp_path))

    assert stats.edges_written == 0
    assert "missing_callee_symbol=2" in (stats.message or "")
