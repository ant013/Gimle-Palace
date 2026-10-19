"""Integration test: SymbolIndexPython on real Neo4j + Tantivy.

Verifies end-to-end ingest from synthetic .scip through 3-phase bootstrap
to IngestRun + IngestCheckpoint in Neo4j.

Requires Neo4j running (docker compose --profile review) or testcontainers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.symbol_index_python import SymbolIndexPython
from palace_mcp.proto import scip_pb2
from tests.extractors.fixtures.scip_factory import (
    build_minimal_scip_index,
    write_scip_fixture,
)


@pytest.mark.integration
class TestSymbolIndexPythonIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle(self, driver: object, tmp_path: Path) -> None:
        """Ingest synthetic .scip, verify :IngestRun + :IngestCheckpoint in Neo4j."""
        index = build_minimal_scip_index(
            symbols=[
                ("scip-python python example . ClassA .", 1),
                ("scip-python python example . ClassA . __init__ .", 1),
                ("scip-python python example . helper .", 1),
                ("scip-python python example . ClassA .", 0),
                ("scip-python python example . helper .", 0),
            ],
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
            run_id="integration-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexPython()
        graphiti = MagicMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        assert stats.nodes_written == 3

        # Verify IngestRun in Neo4j
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid="integration-run-001",
            )
            record = await result.single()
            assert record is not None
            assert record["success"] is True

        # Verify IngestCheckpoint
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) RETURN c.phase AS phase",
                rid="integration-run-001",
            )
            records = await result.data()
            phases = {r["phase"] for r in records}
            assert "phase1_defs" in phases

    @pytest.mark.asyncio
    async def test_symbol_graph_fields_are_persisted(
        self, driver: object, tmp_path: Path
    ) -> None:
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

        scip_path = write_scip_fixture(index, tmp_path / "symbol-info.scip")

        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-symbols": str(scip_path)}
        tantivy_dir = tmp_path / "tantivy-symbols"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        ctx = ExtractorRunContext(
            project_slug="test-symbols",
            group_id="project/test-symbols",
            repo_path=tmp_path,
            run_id="integration-run-symbols",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexPython()
        graphiti = MagicMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        assert stats.nodes_written == 3

        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                """
                MATCH (s:Symbol {group_id: $group_id})
                RETURN s.short_name AS short_name, s.kind AS kind, s.label AS label
                ORDER BY short_name
                """,
                group_id=ctx.group_id,
            )
            rows = await result.data()

        assert rows == [
            {"short_name": "ClassA", "kind": "class", "label": "Class"},
            {"short_name": "__init__", "kind": "method", "label": "Method"},
            {"short_name": "helper", "kind": "function", "label": "Function"},
        ]
