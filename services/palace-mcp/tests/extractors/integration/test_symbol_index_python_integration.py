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

        assert stats.nodes_written >= 3  # at least 3 defs

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
