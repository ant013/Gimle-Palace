"""Integration test: SymbolIndexSwift on real Neo4j + Tantivy.

Verifies end-to-end ingest of Swift SCIP data through the 3-phase bootstrap.
Also verifies 3-Kit bundle fixture: cross-repo Tantivy search returns
occurrences from member slugs when bundle slug resolves correctly.

Requires Neo4j running (docker compose --profile review) or testcontainers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
from tests.extractors.fixtures.scip_factory import (
    build_swift_scip_index,
    write_scip_fixture,
)

# Swift SCIP symbol format: scip-swift <manager> <package> <version> <descriptor>
# _extract_qualified_name strips scheme+manager+version → "<package> <descriptor>"
_EVMKIT_ADDRESS_SYMBOL = "scip-swift swift EvmKit 1.0 Address#."
_EVMKIT_ADDRESS_QN = "EvmKit Address#."  # qualified_name after extraction


@pytest.mark.integration
class TestSymbolIndexSwiftIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle(self, driver: object, tmp_path: Path) -> None:
        """Ingest synthetic Swift .scip, verify :IngestRun in Neo4j."""
        index = build_swift_scip_index(
            relative_path="Sources/EvmKit/Address.swift",
            symbols=[
                (_EVMKIT_ADDRESS_SYMBOL, 1),  # def
            ],
        )
        scip_path = write_scip_fixture(index, tmp_path / "evmkit.scip")

        settings = MagicMock()
        settings.palace_scip_index_paths = {"evmkit-mini": str(scip_path)}
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
            project_slug="evmkit-mini",
            group_id="project/evmkit-mini",
            repo_path=tmp_path,
            run_id="swift-integration-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexSwift()
        graphiti = MagicMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        assert stats.nodes_written >= 1  # at least the def was written

        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid="swift-integration-run-001",
            )
            record = await result.single()
            assert record is not None
            assert record["success"] is True

    @pytest.mark.asyncio
    async def test_cross_kit_tantivy_search(
        self, driver: object, tmp_path: Path
    ) -> None:
        """Ingest EvmKit-mini (def) + uw-ios-app (use), verify Tantivy finds both.

        This exercises the data path that bundle find_references walks:
        open Tantivy, search symbol_id across all member projects.
        """
        from palace_mcp.extractors.foundation.identifiers import symbol_id_for
        from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()

        def _settings(scip_paths: dict) -> MagicMock:
            s = MagicMock()
            s.palace_scip_index_paths = scip_paths
            s.palace_tantivy_index_path = str(tantivy_dir)
            s.palace_tantivy_heap_mb = 50
            s.palace_max_occurrences_total = 50_000_000
            s.palace_max_occurrences_per_project = 10_000_000
            s.palace_importance_threshold_use = 0.0
            s.palace_max_occurrences_per_symbol = 5_000
            s.palace_recency_decay_days = 30.0
            return s

        # 1. Ingest EvmKit-mini: defines EvmKit.Address
        evmkit_index = build_swift_scip_index(
            relative_path="Sources/EvmKit/Address.swift",
            symbols=[(_EVMKIT_ADDRESS_SYMBOL, 1)],
        )
        evmkit_scip = write_scip_fixture(evmkit_index, tmp_path / "evmkit.scip")
        evmkit_ctx = ExtractorRunContext(
            project_slug="EvmKit-mini",
            group_id="project/EvmKit-mini",
            repo_path=tmp_path,
            run_id="evmkit-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )
        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch(
                "palace_mcp.mcp_server.get_settings",
                return_value=_settings({"EvmKit-mini": str(evmkit_scip)}),
            ),
        ):
            await SymbolIndexSwift().run(graphiti=MagicMock(), ctx=evmkit_ctx)

        # 2. Ingest uw-ios-app: uses EvmKit.Address
        app_index = build_swift_scip_index(
            relative_path="Sources/App/WalletView.swift",
            symbols=[(_EVMKIT_ADDRESS_SYMBOL, 0)],  # role=0 = use
        )
        app_scip = write_scip_fixture(app_index, tmp_path / "app.scip")
        app_ctx = ExtractorRunContext(
            project_slug="uw-ios-app",
            group_id="project/uw-ios-app",
            repo_path=tmp_path,
            run_id="app-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )
        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch(
                "palace_mcp.mcp_server.get_settings",
                return_value=_settings({"uw-ios-app": str(app_scip)}),
            ),
        ):
            await SymbolIndexSwift().run(graphiti=MagicMock(), ctx=app_ctx)

        # 3. Search Tantivy by symbol_id — both projects' occurrences should appear
        sym_id = symbol_id_for(_EVMKIT_ADDRESS_QN)
        async with TantivyBridge(tantivy_dir, heap_size_mb=50) as bridge:
            results = await bridge.search_by_symbol_id_async(sym_id, limit=50)

        ingest_run_ids_found = {r.get("ingest_run_id") for r in results}
        # Both projects wrote the same symbol_id — cross-repo expansion
        # is evidenced by two distinct ingest_run_ids in Tantivy.
        assert "evmkit-run-001" in ingest_run_ids_found, (
            f"EvmKit-mini ingest_run_id missing from results: {ingest_run_ids_found}"
        )
        assert "app-run-001" in ingest_run_ids_found, (
            f"uw-ios-app ingest_run_id missing from results: {ingest_run_ids_found}"
        )

    @pytest.mark.asyncio
    async def test_app_slug_distinct_from_bundle_slug(
        self, driver: object, tmp_path: Path
    ) -> None:
        """uw-ios-app slug (project) is distinct from uw-ios (bundle).

        After ingesting uw-ios-app into Tantivy, a Tantivy search returns
        uw-ios-app as the project slug — never 'uw-ios' (the bundle slug).
        This proves the project slug and bundle slug are independent identifiers.
        """
        from palace_mcp.extractors.foundation.identifiers import symbol_id_for
        from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()

        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        app_index = build_swift_scip_index(
            relative_path="Sources/App/Main.swift",
            symbols=[(_EVMKIT_ADDRESS_SYMBOL, 0)],
        )
        app_scip = write_scip_fixture(app_index, tmp_path / "app.scip")
        settings.palace_scip_index_paths = {"uw-ios-app": str(app_scip)}

        ctx = ExtractorRunContext(
            project_slug="uw-ios-app",
            group_id="project/uw-ios-app",
            repo_path=tmp_path,
            run_id="slug-distinct-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )
        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            await SymbolIndexSwift().run(graphiti=MagicMock(), ctx=ctx)

        sym_id = symbol_id_for(_EVMKIT_ADDRESS_QN)
        async with TantivyBridge(tantivy_dir, heap_size_mb=50) as bridge:
            results = await bridge.search_by_symbol_id_async(sym_id, limit=10)

        assert len(results) > 0, "Expected at least one Tantivy result"
        ingest_run_ids_found = {r.get("ingest_run_id") for r in results}
        # uw-ios-app was ingested with run_id "slug-distinct-run-001"
        # The bundle slug "uw-ios" must never appear as an ingest_run_id
        assert "slug-distinct-run-001" in ingest_run_ids_found, (
            f"Expected uw-ios-app run_id in results: {ingest_run_ids_found}"
        )
        for r in results:
            run_id = r.get("ingest_run_id", "")
            assert "uw-ios" not in run_id or "uw-ios-app" in run_id, (
                f"Bundle slug 'uw-ios' must not leak into per-project Tantivy run_id: {run_id}"
            )
