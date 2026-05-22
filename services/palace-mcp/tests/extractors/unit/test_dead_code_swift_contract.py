"""Contract test: symbol_index_swift output → dead_code consumption (GIM-788).

This test fails if:
- SCIP SymbolInformation is not parsed (iter_scip_symbol_infos returns nothing)
- The :Symbol node schema produced by write_symbol_nodes doesn't match
  what dead_code.graph_loader._row_to_symbol expects
- The dead_code algorithm cannot produce findings from SCIP-sourced data

A passing test means dead_code can consume real symbol_index_swift output,
not just hand-crafted SymbolGraph fixtures.
"""

from __future__ import annotations

from palace_mcp.extractors.dead_code.graph_loader import _row_to_symbol
from palace_mcp.extractors.dead_code.models import SymbolGraph
from palace_mcp.extractors.dead_code.reachability import (
    compute_dead_candidates,
    compute_reachable_set,
)
from palace_mcp.extractors.dead_code.seeds import compute_all_seeds
from palace_mcp.extractors.foundation.symbol_node_writer import build_symbol_node_rows
from palace_mcp.extractors.scip_parser import iter_scip_symbol_infos
from tests.extractors.fixtures.scip_factory import build_swift_scip_index_with_symbol_infos


def _build_graph_from_scip(group_id: str) -> SymbolGraph:
    """Round-trip: SCIP → ScipSymbolInfo → node rows → SymbolGraph."""
    scip_index = build_swift_scip_index_with_symbol_infos()

    # Step that symbol_index_swift performs (Phase 1 DEF occurrences → file_path map)
    from palace_mcp.extractors.scip_parser import iter_scip_occurrences
    from palace_mcp.extractors.foundation.models import SymbolKind

    def_file_paths: dict[str, str] = {}
    for occ in iter_scip_occurrences(scip_index, commit_sha="test"):
        if occ.kind in (SymbolKind.DEF, SymbolKind.DECL):
            def_file_paths.setdefault(occ.symbol_qualified_name, occ.file_path)

    symbol_infos = list(iter_scip_symbol_infos(scip_index))

    # This is the contract: build_symbol_node_rows must return rows that
    # _row_to_symbol (used by dead_code.graph_loader) can parse.
    node_rows = build_symbol_node_rows(symbol_infos, def_file_paths, group_id)

    graph = SymbolGraph()
    for row in node_rows:
        qn = row.get("qualified_name")
        if qn:
            graph.symbols[qn] = _row_to_symbol(row)

    # Edges from symbol_infos
    from palace_mcp.extractors.dead_code.models import GraphEdge

    for si in symbol_infos:
        for target_qname, rel_type in si.relationships:
            graph.edges.append(
                GraphEdge(source=si.qualified_name, target=target_qname, kind=rel_type)
            )

    graph.build_indexes()
    return graph


class TestDeadCodeSwiftContract:
    def test_iter_scip_symbol_infos_extracts_kind(self) -> None:
        """iter_scip_symbol_infos must extract kind from SCIP SymbolInformation.

        Fails if the SCIP fixture has no doc.symbols or if the kind field
        is not read.
        """
        scip_index = build_swift_scip_index_with_symbol_infos()
        infos = list(iter_scip_symbol_infos(scip_index))

        assert len(infos) >= 3, (
            f"Expected ≥3 ScipSymbolInfo (WalletStore, select, DeadHelper), got {len(infos)}"
        )
        kinds = {si.scip_kind_name for si in infos}
        assert "Class" in kinds, f"Expected Class kind in {kinds}"
        assert "Function" in kinds, f"Expected Function kind in {kinds}"

    def test_build_symbol_node_rows_schema_matches_graph_loader(self) -> None:
        """Rows from build_symbol_node_rows must be parseable by _row_to_symbol.

        Fails if the column names or types differ between the writer and loader.
        """
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))
        assert symbol_infos, "Fixture must produce symbol infos"

        group_id = "project/uw-mini"
        rows = build_symbol_node_rows(symbol_infos, {}, group_id)

        assert rows, "Must produce at least one node row"
        for row in rows:
            assert row["group_id"] == group_id
            assert "qualified_name" in row
            assert "kind" in row
            assert "file_path" in row
            assert "module_name" in row
            # _row_to_symbol must not raise
            sym = _row_to_symbol(row)
            assert sym.qualified_name == row["qualified_name"]
            assert sym.kind == row["kind"]

    def test_dead_code_produces_findings_from_scip_symbol_infos(self) -> None:
        """dead_code must produce ≥1 DeadFinding when consuming SCIP-sourced :Symbol data.

        This test fails if:
        - iter_scip_symbol_infos returns nothing (SCIP fixture missing SymbolInformation)
        - build_symbol_node_rows / _row_to_symbol conversion drops all symbols
        - The dead_code algorithm cannot produce any findings

        In the fixture, DeadHelper has no callers and no edges pointing to it,
        so it is always a dead candidate regardless of seed configuration.
        """
        graph = _build_graph_from_scip("project/uw-mini")
        assert graph.symbols, "SymbolGraph must have symbols from SCIP data"

        seeds = compute_all_seeds(graph)
        reachable = compute_reachable_set(graph, seeds)
        dead = compute_dead_candidates(graph, reachable)

        assert dead, (
            "Expected ≥1 dead candidate — DeadHelper has no callers and is not a seed"
        )

        # DeadHelper specifically must be dead (no callers, no public/dynamic flags)
        dead_qnames = {qn for qn in dead}
        dead_helper_qn = next(
            (qn for qn in dead_qnames if "DeadHelper" in qn), None
        )
        assert dead_helper_qn is not None, (
            f"DeadHelper not found in dead candidates; dead={dead_qnames}"
        )

    def test_dead_code_graph_loader_group_id_contract(self) -> None:
        """write_symbol_nodes must set group_id matching what graph_loader queries.

        dead_code.graph_loader._LOAD_SYMBOLS queries:
            MATCH (s:Symbol {group_id: $group_id})

        This test confirms build_symbol_node_rows embeds the group_id in every row.
        """
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))
        group_id = "project/bitcoin-core"
        rows = build_symbol_node_rows(symbol_infos, {}, group_id)

        assert all(r["group_id"] == group_id for r in rows), (
            "Every :Symbol row must carry the project group_id"
        )
