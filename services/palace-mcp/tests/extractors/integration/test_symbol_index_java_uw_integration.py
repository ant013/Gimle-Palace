"""Integration test: SymbolIndexJava on real fixture .scip + real Neo4j.

NEW PATTERN (GIM-127 Slice 1): unlike test_symbol_index_java_integration.py
which uses synthetic build_jvm_scip_index() factory, this test reads the
committed uw-android-mini-project/scip/index.scip fixture from disk and
runs the full extractor pipeline against real Neo4j (compose-reuse).

Asserts:
- IngestRun success record in Neo4j
- phase1_defs checkpoint present in Neo4j
- Tantivy document count matches oracle (within ±2% drift tolerance)

Skipped if fixture .scip missing (requires_scip_uw_android marker).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.symbol_index_java import SymbolIndexJava
from tests.extractors.unit.test_real_scip_fixtures import (
    _UW_N_OCCURRENCES_TOTAL,
    requires_scip_uw_android,
)

FIXTURE_SCIP = (
    Path(__file__).parent.parent
    / "fixtures"
    / "uw-android-mini-project"
    / "scip"
    / "index.scip"
)

_RUN_ID = "uw-android-integration-001"


@pytest.mark.integration
@requires_scip_uw_android
class TestSymbolIndexJavaUwIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle_real_fixture(
        self, driver: object, tmp_path: Path
    ) -> None:
        """Ingest committed UW-android fixture, verify Neo4j + Tantivy state."""
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-android-mini": str(FIXTURE_SCIP)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 100
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        ctx = ExtractorRunContext(
            project_slug="uw-android-mini",
            group_id="project/uw-android-mini",
            repo_path=tmp_path,
            run_id=_RUN_ID,
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

        # Assert 1: extractor wrote occurrences
        assert stats.nodes_written > 0, "extractor wrote zero occurrences"

        # Assert 2: IngestRun in Neo4j
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid=_RUN_ID,
            )
            record = await result.single()
            assert record is not None, "IngestRun node not found in Neo4j"
            assert record["success"] is True, "IngestRun marked failure"

        # Assert 3: Phase 1 checkpoint persisted
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid, phase: 'phase1_defs'}) "
                "RETURN c.expected_doc_count AS count",
                rid=_RUN_ID,
            )
            record = await result.single()
            assert record is not None, "phase1_defs checkpoint missing"
            assert record["count"] > 0, "phase1_defs wrote zero documents"

        # Assert 4: Tantivy doc count matches oracle ±2% (CR WARNING #1 fix — rev2)
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
        tantivy_total = phase1_docs + phase2_docs + phase3_docs

        lo = int(_UW_N_OCCURRENCES_TOTAL * 0.98)
        hi = int(_UW_N_OCCURRENCES_TOTAL * 1.02)
        assert lo <= tantivy_total <= hi, (
            f"Tantivy doc count {tantivy_total} "
            f"(p1={phase1_docs}, p2={phase2_docs}, p3={phase3_docs}) "
            f"outside oracle {_UW_N_OCCURRENCES_TOTAL}±2% (range [{lo}, {hi}])"
        )
