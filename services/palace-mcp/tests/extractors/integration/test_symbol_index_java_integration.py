"""Integration test: SymbolIndexJava on real Neo4j + Tantivy.

Verifies end-to-end ingest from synthetic .scip through 3-phase bootstrap
to IngestRun + IngestCheckpoint in Neo4j.

Requires Neo4j running (docker compose --profile review) or testcontainers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.symbol_index_java import SymbolIndexJava
from tests.extractors.fixtures.scip_factory import (
    build_jvm_scip_index,
    write_scip_fixture,
)


@pytest.mark.integration
class TestSymbolIndexJavaIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle(self, driver: object, tmp_path: Path) -> None:
        """Ingest synthetic JVM .scip, verify :IngestRun + :IngestCheckpoint in Neo4j."""
        index = build_jvm_scip_index(
            symbols=[
                ("semanticdb maven com.example 1.0.0 com/example/User#", 1),
                ("semanticdb maven com.example 1.0.0 com/example/User#getName().", 1),
                ("semanticdb maven com.example 1.0.0 com/example/User#getAge().", 1),
                # uses
                ("semanticdb maven com.example 1.0.0 com/example/User#", 0),
                ("semanticdb maven com.example 1.0.0 com/example/User#getName().", 0),
            ],
        )
        scip_path = write_scip_fixture(index, tmp_path / "test.scip")

        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-proj": str(scip_path)}
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
            project_slug="test-proj",
            group_id="project/test-proj",
            repo_path=tmp_path,
            run_id="java-integration-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexJava()
        graphiti = MagicMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        assert stats.nodes_written >= 3  # at least 3 defs

        # Verify IngestRun in Neo4j
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid="java-integration-run-001",
            )
            record = await result.single()
            assert record is not None
            assert record["success"] is True

        # Verify IngestCheckpoint phase1_defs
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) RETURN c.phase AS phase",
                rid="java-integration-run-001",
            )
            records = await result.data()
            phases = {r["phase"] for r in records}
            assert "phase1_defs" in phases

    @pytest.mark.asyncio
    async def test_java_kotlin_language_detection_in_ingest(
        self, driver: object, tmp_path: Path
    ) -> None:
        """Mixed .java and .kt docs produce Language.JAVA and Language.KOTLIN."""
        from palace_mcp.extractors.foundation.models import Language
        from palace_mcp.extractors.scip_parser import (
            iter_scip_occurrences,
            parse_scip_file,
        )
        from palace_mcp.proto import scip_pb2

        index = scip_pb2.Index()  # type: ignore[attr-defined]
        metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
        metadata.project_root = "file:///test"
        index.metadata.CopyFrom(metadata)

        java_doc = index.documents.add()
        java_doc.relative_path = "src/main/java/com/example/App.java"
        java_doc.language = "java"
        java_occ = java_doc.occurrences.add()
        java_occ.range.extend([1, 0, 5])
        java_occ.symbol = "semanticdb maven com.example 1.0.0 com/example/App#."
        java_occ.symbol_roles = 1

        kt_doc = index.documents.add()
        kt_doc.relative_path = "src/main/kotlin/com/example/Utils.kt"
        kt_doc.language = "kotlin"
        kt_occ = kt_doc.occurrences.add()
        kt_occ.range.extend([2, 0, 7])
        kt_occ.symbol = "semanticdb maven com.example 1.0.0 com/example/Utils#helper()."
        kt_occ.symbol_roles = 1

        scip_path = tmp_path / "mixed.scip"
        scip_path.write_bytes(index.SerializeToString())
        parsed = parse_scip_file(scip_path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="abc123"))

        langs = {o.language for o in occs}
        assert Language.JAVA in langs
        assert Language.KOTLIN in langs
