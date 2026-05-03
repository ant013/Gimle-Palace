"""Integration test: SymbolIndexSwift on real Neo4j + Tantivy.

Verifies end-to-end ingest from synthetic Swift .scip through the extractor's
3-phase bootstrap, including vendor-path routing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
from tests.extractors.fixtures.scip_factory import (
    build_minimal_scip_index,
    write_scip_fixture,
)

_RUN_ID = "swift-integration-run-001"


@pytest.mark.integration
class TestSymbolIndexSwiftIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle_routes_vendor_paths(
        self, driver: object, tmp_path: Path
    ) -> None:
        """Ingest synthetic Swift .scip and verify phase1/2/3 writes."""
        index = build_minimal_scip_index(
            language="swift",
            relative_path="Sources/UwMini/Wallet.swift",
            symbols=[
                ("scip-swift apple UwMini . s%3A6UwMini6WalletV", 1),
                ("scip-swift apple UwMini . s%3A6UwMini11WalletStoreC", 1),
                ("scip-swift apple UwMini . s%3A6UwMini6WalletV", 0),
            ],
        )

        vendor_doc = index.documents.add()
        vendor_doc.relative_path = "Pods/Alamofire/Source/Session.swift"
        vendor_doc.language = "swift"
        vendor_occ = vendor_doc.occurrences.add()
        vendor_occ.range.extend([3, 4, 4])
        vendor_occ.symbol = "scip-swift apple Alamofire . s%3A10Alamofire7SessionC"
        vendor_occ.symbol_roles = 0

        scip_path = write_scip_fixture(index, tmp_path / "swift.scip")

        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_path)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        ctx = ExtractorRunContext(
            project_slug="uw-ios-mini",
            group_id="project/uw-ios-mini",
            repo_path=tmp_path,
            run_id=_RUN_ID,
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexSwift()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=ctx)

        assert stats.nodes_written == 4

        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid=_RUN_ID,
            )
            record = await result.single()
            assert record is not None
            assert record["success"] is True

        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) "
                "RETURN c.phase AS phase, c.expected_doc_count AS count",
                rid=_RUN_ID,
            )
            records = await result.data()
        checkpoints = {row["phase"]: row["count"] for row in records}
        assert checkpoints["phase1_defs"] == 2
        assert checkpoints["phase2_user_uses"] == 3
        assert checkpoints["phase3_vendor_uses"] == 4

        async with TantivyBridge(
            tantivy_dir, heap_size_mb=settings.palace_tantivy_heap_mb
        ) as bridge:
            phase1_docs = await bridge.count_docs_for_run_async(_RUN_ID, "phase1_defs")
            phase2_docs = await bridge.count_docs_for_run_async(
                _RUN_ID, "phase2_user_uses"
            )
            phase3_docs = await bridge.count_docs_for_run_async(
                _RUN_ID, "phase3_vendor_uses"
            )

        assert phase1_docs == 2
        assert phase2_docs == 1
        assert phase3_docs == 1
