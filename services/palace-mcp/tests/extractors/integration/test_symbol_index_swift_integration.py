"""Integration test: SymbolIndexSwift runtime path via runner + real Neo4j/Tantivy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.extractors.scip_parser import parse_scip_file
from tests.extractors.fixtures.scip_factory import (
    build_swift_scip_index,
    write_scip_fixture,
)

_RUN_ID = "swift-integration-run-001"
_SELECT_QNAME = (
    "UwMiniCore "
    "s%3A10UwMiniCore11WalletStoreC6select8walletIDySi_tF"
)


@pytest.fixture
async def _project_and_repo(driver: AsyncDriver, tmp_path: Path) -> Path:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = 'project/' + $slug,
                p.name = $name,
                p.tags = []
            """,
            slug="uw-ios-mini",
            name="UwIosMini",
        )
    repo = tmp_path / "repos" / "uw-ios-mini"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n")
    return tmp_path / "repos"


@pytest.mark.integration
class TestSymbolIndexSwiftIntegration:
    @pytest.mark.asyncio
    async def test_run_extractor_registers_and_ingests_all_three_phases(
        self, driver: AsyncDriver, graphiti_mock: MagicMock, _project_and_repo: Path, tmp_path: Path
    ) -> None:
        await ensure_extractors_schema(driver)
        scip_path = write_scip_fixture(build_swift_scip_index(), tmp_path / "swift.scip")
        parsed = parse_scip_file(scip_path)
        assert parsed.metadata.tool_info.name == "palace-swift-scip-emit"
        assert len(parsed.documents) == 3

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

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo),
            patch("palace_mcp.extractors.runner.uuid4", return_value=_RUN_ID),
        ):
            res = await run_extractor(
                name="symbol_index_swift",
                project="uw-ios-mini",
                driver=driver,
                graphiti=graphiti_mock,
            )

        assert res["ok"] is True
        assert res["extractor"] == "symbol_index_swift"
        assert res["project"] == "uw-ios-mini"
        assert res["success"] is True
        assert res["nodes_written"] >= 4

        async with driver.session() as session:
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) "
                "RETURN c.phase AS phase, c.expected_doc_count AS count",
                rid=_RUN_ID,
            )
            rows = await result.data()
        counts = {row["phase"]: row["count"] for row in rows}
        assert counts["phase1_defs"] > 0
        assert counts["phase2_user_uses"] > counts["phase1_defs"]
        assert counts["phase3_vendor_uses"] > counts["phase2_user_uses"]

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
            hits = await bridge.search_by_symbol_id_async(symbol_id_for(_SELECT_QNAME))

        assert phase1_docs > 0
        assert phase2_docs > 0
        assert phase3_docs > 0
        paths = {hit["file_path"][0] for hit in hits}
        assert "Sources/UwMiniCore/State/WalletStore.swift" in paths
        assert "Sources/UwMiniApp/ContentView.swift" in paths
        assert "Pods/Foo/Foo.swift" in paths
