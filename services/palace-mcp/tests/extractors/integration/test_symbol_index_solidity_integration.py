"""Integration test: SymbolIndexSolidity on real Neo4j + Tantivy.

Verifies end-to-end ingest from synthetic .scip through 3-phase bootstrap
to IngestRun + IngestCheckpoint in Neo4j.

Requires Neo4j running (docker compose --profile review) or testcontainers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.symbol_index_solidity import SymbolIndexSolidity
from tests.extractors.fixtures.scip_factory import (
    build_solidity_scip_index,
    write_scip_fixture,
)


@pytest.mark.integration
class TestSymbolIndexSolidityIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle(self, driver: object, tmp_path: Path) -> None:
        """Ingest synthetic Solidity .scip, verify :IngestRun + :IngestCheckpoint in Neo4j."""
        # Minimal ERC20-like fixture: contract def + two functions (one public with ABI selector)
        index = build_solidity_scip_index(
            symbols=[
                # Contract def — DEF
                (
                    "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#.",
                    1,
                ),
                # Constructor — DEF
                (
                    "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#Token(string).",
                    1,
                ),
                # Public function transfer — DEF
                (
                    "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#transfer(address,uint256).",
                    1,
                ),
                # USE occurrence of the contract
                (
                    "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#.",
                    0,
                ),
                # USE occurrence of transfer
                (
                    "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#transfer(address,uint256).",
                    0,
                ),
            ],
        )
        scip_path = write_scip_fixture(index, tmp_path / "test.scip")

        settings = MagicMock()
        settings.palace_scip_index_paths = {"sol-proj": str(scip_path)}
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
            project_slug="sol-proj",
            group_id="project/sol-proj",
            repo_path=tmp_path,
            run_id="sol-integration-run-001",
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexSolidity()
        graphiti = MagicMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        assert stats.nodes_written >= 3  # at least 3 DEF occurrences

        # Verify IngestRun written to Neo4j
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid="sol-integration-run-001",
            )
            record = await result.single()
            assert record is not None
            assert record["success"] is True

        # Verify at least phase1_defs checkpoint created
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid}) RETURN c.phase AS phase",
                rid="sol-integration-run-001",
            )
            records = await result.data()
            phases = {r["phase"] for r in records}
            assert "phase1_defs" in phases

    @pytest.mark.asyncio
    async def test_solidity_language_detection_in_ingest(
        self, driver: object, tmp_path: Path
    ) -> None:
        """SCIP with language='solidity' produces Language.SOLIDITY occurrences."""
        from palace_mcp.extractors.foundation.models import Language
        from palace_mcp.extractors.scip_parser import (
            iter_scip_occurrences,
            parse_scip_file,
        )

        index = build_solidity_scip_index(
            symbols=[
                (
                    "scip-solidity ethereum contracts/Token.sol . contracts/Token.sol/`Token`#.",
                    1,
                ),
            ],
        )
        scip_path = write_scip_fixture(index, tmp_path / "sol.scip")
        parsed = parse_scip_file(scip_path)
        occs = list(iter_scip_occurrences(parsed, commit_sha="test"))

        langs = {o.language for o in occs}
        assert Language.SOLIDITY in langs
