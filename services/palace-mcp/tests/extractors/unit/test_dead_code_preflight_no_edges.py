"""Regression: dead_code must short-circuit when call graph has zero edges.

Native palace-mcp ingest of uw-ios-baseline produces 250 595 :Symbol nodes
but does NOT materialize Symbol→Symbol call/reference edges — those come
from `codebase_memory_bridge` reading the SCIP graph from the CM sidecar.

Before the pre-flight guard, dead_code hit `timeout_s = 3600` because:
  - load_symbol_graph: 250 595 nodes, 0 edges  → fast
  - compute_all_seeds(graph): iterates 250 595 nodes  → seconds
  - compute_reachable_set(seeds): BFS finds 0 reachable (no out-edges)
  - compute_dead_candidates: ALL 250 595 → dead candidates
  - build_findings(graph, 250 595 candidates) → O(N) iteration, but
    enrichment + neo4j_writer.write_dead_findings on 250 595 rows
    blows the 1 h budget.

After the guard, the extractor returns `outcome=MISSING_INPUT` immediately
with a message pointing the operator to run `codebase_memory_bridge` first.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorOutcome, ExtractorRunContext
from palace_mcp.extractors.dead_code.extractor import DeadCodeExtractor
from palace_mcp.extractors.dead_code.models import SymbolGraph, SymbolNode


def _build_symbol_graph_with_n_symbols_and_no_edges(n: int) -> SymbolGraph:
    g = SymbolGraph()
    for i in range(n):
        qn = f"App.Symbol{i}"
        g.symbols[qn] = SymbolNode(
            qualified_name=qn,
            kind="function",
            file_path=f"src/file{i}.swift",
            module_name="App",
        )
    g.build_indexes()
    return g


@pytest.mark.asyncio
async def test_dead_code_returns_missing_input_when_zero_edges():
    """Pre-flight guard: 250 595 :Symbol nodes + 0 edges → MISSING_INPUT,
    not a 1 h budget burn through BFS/Tarjan/finding builder.
    """
    graph = _build_symbol_graph_with_n_symbols_and_no_edges(n=250_595)
    assert len(graph.symbols) == 250_595
    assert graph.edges == []

    ctx = MagicMock(spec=ExtractorRunContext)
    ctx.run_id = "test-run-id"
    ctx.project_slug = "uw-ios-baseline"
    ctx.group_id = "project/uw-ios-baseline"
    ctx.repo_path = Path("/tmp/uw-ios-baseline")
    ctx.logger = MagicMock()
    ctx.force = False

    settings = MagicMock()
    settings.palace_max_occurrences_total = 10_000_000

    driver = MagicMock()
    extractor = DeadCodeExtractor()

    with (
        patch(
            "palace_mcp.extractors.dead_code.extractor.load_symbol_graph",
            new=AsyncMock(return_value=graph),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.write_checkpoint",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.check_phase_budget",
            return_value=None,
        ),
        # The downstream pipeline (seeds → BFS → finding builder → writer)
        # MUST NOT execute when edges are empty. AsyncMock any of them and
        # assert they are never awaited.
        patch(
            "palace_mcp.extractors.dead_code.extractor.compute_all_seeds",
            new=MagicMock(return_value=set()),
        ) as mock_seeds,
        patch(
            "palace_mcp.extractors.dead_code.extractor.write_dead_findings",
            new=AsyncMock(return_value=0),
        ) as mock_writer,
    ):
        stats = await extractor._run_pipeline(driver=driver, settings=settings, ctx=ctx)

    assert stats.outcome == ExtractorOutcome.MISSING_INPUT
    assert "0 call/reference edges" in stats.message
    assert "codebase_memory_bridge" in stats.message
    # Pipeline downstream MUST be short-circuited.
    mock_seeds.assert_not_called()
    mock_writer.assert_not_called()
