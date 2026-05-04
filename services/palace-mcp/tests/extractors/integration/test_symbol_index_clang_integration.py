"""Integration test: SymbolIndexClang runtime path via runner + real Neo4j/Tantivy."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.extractors.scip_parser import parse_scip_file

_RUN_ID = "clang-integration-run-001"
_CLANG_TOOL_NAME = "scip-clang"
_SELECT_QNAME = ". math/Vector#length()."
_VENDOR_DEF_QNAME = ". vendor/Foo#helper()."
FIXTURE_SCIP = (
    Path(__file__).parent.parent
    / "fixtures"
    / "uw-ios-clang-mini-project"
    / "scip"
    / "index.scip"
)
_HAS_NEO4J_RUNTIME = (
    bool(os.environ.get("COMPOSE_NEO4J_URI")) or Path("/var/run/docker.sock").exists()
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
            slug="uw-ios-clang-mini",
            name="UwIosClangMini",
        )
    repo = tmp_path / "repos" / "uw-ios-clang-mini"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n")
    return tmp_path / "repos"


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_NEO4J_RUNTIME,
    reason="requires Docker socket or COMPOSE_NEO4J_URI for Neo4j integration",
)
class TestSymbolIndexClangIntegration:
    @pytest.mark.asyncio
    async def test_run_extractor_ingests_native_fixture_with_vendor_filtering(
        self,
        driver: AsyncDriver,
        graphiti_mock: MagicMock,
        _project_and_repo: Path,
        tmp_path: Path,
    ) -> None:
        await ensure_extractors_schema(driver)
        parsed = parse_scip_file(FIXTURE_SCIP)
        assert parsed.metadata.tool_info.name == _CLANG_TOOL_NAME
        assert len(parsed.documents) == 4

        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-clang-mini": str(FIXTURE_SCIP)}
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
                name="symbol_index_clang",
                project="uw-ios-clang-mini",
                driver=driver,
                graphiti=graphiti_mock,
            )

        assert res["ok"] is True
        assert res["extractor"] == "symbol_index_clang"
        assert res["project"] == "uw-ios-clang-mini"
        assert res["success"] is True
        assert res["nodes_written"] == 5

        async with driver.session() as session:
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) "
                "RETURN c.phase AS phase, c.expected_doc_count AS count",
                rid=_RUN_ID,
            )
            rows = await result.data()
        counts = {row["phase"]: row["count"] for row in rows}
        assert counts == {
            "phase1_defs": 2,
            "phase2_user_uses": 4,
            "phase3_vendor_uses": 5,
        }

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
            vector_hits = await bridge.search_by_symbol_id_async(
                symbol_id_for(_SELECT_QNAME)
            )
            vendor_def_hits = await bridge.search_by_symbol_id_async(
                symbol_id_for(_VENDOR_DEF_QNAME)
            )

        assert phase1_docs == 2
        assert phase2_docs == 2
        assert phase3_docs == 1

        paths = {hit["file_path"][0] for hit in vector_hits}
        assert paths == {
            "Pods/Foo/Foo.c",
            "Sources/UwMiniApp/main.c",
            "Sources/UwMiniCore/Math/Vector.cpp",
        }
        assert vendor_def_hits == []
