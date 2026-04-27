"""Integration test: SymbolIndexTypeScript on real Neo4j + Tantivy.

Verifies end-to-end ingest from synthetic .scip through 3-phase bootstrap
to IngestRun + IngestCheckpoint in Neo4j.

Requires Neo4j running (docker compose --profile review) or testcontainers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.symbol_index_typescript import SymbolIndexTypeScript
from tests.extractors.fixtures.scip_factory import (
    build_typescript_scip_index,
    write_scip_fixture,
)


@pytest.mark.integration
class TestSymbolIndexTypeScriptIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle(self, driver: object, tmp_path: Path) -> None:
        """Ingest synthetic .scip, verify :IngestRun + :IngestCheckpoint in Neo4j."""
        index = build_typescript_scip_index(
            symbols=[
                (
                    "scip-typescript npm example 1.0.0 src/`app.ts`/App#.",
                    1,
                ),
                (
                    "scip-typescript npm example 1.0.0 src/`app.ts`/App#render().",
                    1,
                ),
                (
                    "scip-typescript npm example 1.0.0 src/`app.ts`/App#constructor().",
                    1,
                ),
                (
                    "scip-typescript npm example 1.0.0 src/`app.ts`/App#.",
                    0,
                ),
                (
                    "scip-typescript npm example 1.0.0 src/`app.ts`/App#render().",
                    0,
                ),
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
            run_id="ts-integration-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexTypeScript()
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
                rid="ts-integration-run-001",
            )
            record = await result.single()
            assert record is not None
            assert record["success"] is True

        # Verify IngestCheckpoint
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) RETURN c.phase AS phase",
                rid="ts-integration-run-001",
            )
            records = await result.data()
            phases = {r["phase"] for r in records}
            assert "phase1_defs" in phases

    @pytest.mark.asyncio
    async def test_ts_js_language_detection_in_ingest(
        self, driver: object, tmp_path: Path
    ) -> None:
        """Mixed .ts and .js docs in same SCIP produce Language.TYPESCRIPT/JAVASCRIPT."""
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

        ts_doc = index.documents.add()
        ts_doc.relative_path = "src/comp.tsx"
        ts_doc.language = "typescript"
        ts_occ = ts_doc.occurrences.add()
        ts_occ.range.extend([1, 0, 5])
        ts_occ.symbol = "scip-typescript npm ex 1.0.0 src/`comp.tsx`/Comp#."
        ts_occ.symbol_roles = 1

        js_doc = index.documents.add()
        js_doc.relative_path = "utils/helper.js"
        js_doc.language = "javascript"
        js_occ = js_doc.occurrences.add()
        js_occ.range.extend([2, 0, 7])
        js_occ.symbol = "scip-typescript npm ex 1.0.0 utils/`helper.js`/helper()."
        js_occ.symbol_roles = 1

        scip_path = tmp_path / "mixed.scip"
        scip_path.write_bytes(index.SerializeToString())
        parsed = parse_scip_file(scip_path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="abc123"))

        langs = {o.language for o in occs}
        assert Language.TYPESCRIPT in langs
        assert Language.JAVASCRIPT in langs
