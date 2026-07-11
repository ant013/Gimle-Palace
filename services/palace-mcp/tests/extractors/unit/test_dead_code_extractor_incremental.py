from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import (
    ExtractorExecutionMode,
    ExtractorOutcome,
    ExtractorRunContext,
)
from palace_mcp.extractors.dead_code.extractor import (
    DeadCodeExtractor,
    _diff_findings_against_existing,
    _stable_finding_props,
)
from palace_mcp.extractors.dead_code.models import (
    DeadFinding,
    FindingKind,
    GraphEdge,
    MemberEntry,
    Severity,
    SymbolGraph,
    SymbolNode,
)
from palace_mcp.extractors.dead_code.neo4j_writer import DeadFindingWriteSummary
from palace_mcp.extractors.foundation.delta_resolution import (
    DeltaResolutionBaseline,
    ResolvedDelta,
    SymbolDelta,
)
from palace_mcp.extractors.foundation.incremental_scope import (
    IncrementalMode,
    IncrementalPathScope,
)


def _ctx(
    repo_path: Path,
    *,
    companion_run_id: str | None = None,
) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="tron-kit",
        group_id="project/tron-kit",
        repo_path=repo_path,
        run_id="dead-code-run",
        duration_ms=0,
        logger=logging.getLogger("test.dead_code.incremental"),
        companion_run_id=companion_run_id,
    )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        palace_incremental_ingest=True,
        palace_incremental_deadcode_full_threshold=0.5,
        palace_max_occurrences_total=10_000_000,
    )


def _graph(*, reachable_run_id: str | None = None) -> SymbolGraph:
    graph = SymbolGraph()
    entry = SymbolNode(
        qualified_name="App.Entry",
        kind="class",
        module_name="App",
        file_path="Sources/App/Entry.swift",
        is_public=True,
        is_main_entry=True,
        reachable_run_id=reachable_run_id,
    )
    helper = SymbolNode(
        qualified_name="App.Helper",
        kind="class",
        module_name="App",
        file_path="Sources/App/Helper.swift",
        reachable_run_id=reachable_run_id,
    )
    graph.symbols[entry.qualified_name] = entry
    graph.symbols[helper.qualified_name] = helper
    graph.edges = [
        GraphEdge(
            source=entry.qualified_name,
            target=helper.qualified_name,
            kind="CALLS",
        )
    ]
    graph.build_indexes()
    return graph


def _baseline() -> DeltaResolutionBaseline:
    return DeltaResolutionBaseline(
        group_id="project/tron-kit",
        project="tron-kit",
        previous_commit_sha="commit-before",
        affected_paths=frozenset({"Sources/App/Helper.swift"}),
        symbols=(),
        edges=(),
        public_api_symbols=(),
    )


def _resolved_delta() -> ResolvedDelta:
    return ResolvedDelta(
        symbol_deltas=(
            SymbolDelta(
                qualified_name="App.Helper",
                change_kind="moved",
                previous_file_path="Sources/App/OldHelper.swift",
                current_file_path="Sources/App/Helper.swift",
            ),
        ),
        edge_deltas=(),
        seed_deltas=(),
        public_api_deltas=(),
    )


@pytest.mark.asyncio
async def test_run_pipeline_skips_when_no_relevant_swift_changes(
    tmp_path: Path,
) -> None:
    extractor = DeadCodeExtractor()

    with (
        patch(
            "palace_mcp.extractors.dead_code.extractor.derive_incremental_path_scope",
            new=AsyncMock(
                return_value=IncrementalPathScope(
                    mode=IncrementalMode.SKIP,
                    changed_paths=set(),
                    removed_paths=set(),
                    reason="no_relevant_changes",
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.load_symbol_graph",
            new=AsyncMock(),
        ) as load_symbol_graph,
    ):
        stats = await extractor._run_pipeline(
            driver=MagicMock(),
            settings=_settings(),
            ctx=_ctx(tmp_path),
        )

    assert stats.outcome == ExtractorOutcome.SKIPPED
    assert stats.mode == ExtractorExecutionMode.SKIPPED
    load_symbol_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_pipeline_falls_back_to_full_when_delta_baseline_missing(
    tmp_path: Path,
) -> None:
    extractor = DeadCodeExtractor()
    graph = _graph()

    with (
        patch(
            "palace_mcp.extractors.dead_code.extractor.derive_incremental_path_scope",
            new=AsyncMock(
                return_value=IncrementalPathScope(
                    mode=IncrementalMode.INCREMENTAL,
                    changed_paths={"Sources/App/Helper.swift"},
                    removed_paths=set(),
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.read_delta_resolution_baseline_artifact",
            return_value=None,
        ),
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
        patch(
            "palace_mcp.extractors.dead_code.extractor.load_dead_finding_props",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.compute_all_seeds",
            return_value={"App.Entry"},
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.compute_reachable_set",
            return_value=set(graph.symbols),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.build_findings",
            return_value=[],
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.load_git_history",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.enrich_findings_with_git",
            return_value=[],
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.write_dead_findings",
            new=AsyncMock(return_value=DeadFindingWriteSummary()),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.write_symbol_reachability",
            new=AsyncMock(return_value=None),
        ) as write_symbol_reachability,
    ):
        stats = await extractor._run_pipeline(
            driver=MagicMock(),
            settings=_settings(),
            ctx=_ctx(tmp_path, companion_run_id="symbol-run"),
        )

    assert stats.mode == ExtractorExecutionMode.FULL
    assert stats.message == "incremental fallback to full: delta_baseline_missing"
    assert write_symbol_reachability.await_count == 1
    kwargs = write_symbol_reachability.await_args.kwargs
    assert kwargs["reachable_qnames"] == set(graph.symbols)
    assert kwargs["unreachable_qnames"] == set()


@pytest.mark.asyncio
async def test_run_pipeline_writes_only_affected_reachability_incrementally(
    tmp_path: Path,
) -> None:
    extractor = DeadCodeExtractor()
    graph = _graph(reachable_run_id="old-run")

    with (
        patch(
            "palace_mcp.extractors.dead_code.extractor.derive_incremental_path_scope",
            new=AsyncMock(
                return_value=IncrementalPathScope(
                    mode=IncrementalMode.INCREMENTAL,
                    changed_paths={"Sources/App/Helper.swift"},
                    removed_paths=set(),
                )
            ),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.read_delta_resolution_baseline_artifact",
            return_value=_baseline(),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.resolve_delta_resolution",
            new=AsyncMock(return_value=_resolved_delta()),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor._read_head_sha",
            return_value="commit-after",
        ),
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
        patch(
            "palace_mcp.extractors.dead_code.extractor.load_dead_finding_props",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.compute_all_seeds",
            return_value={"App.Entry"},
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.compute_incremental_reachable",
            return_value=({"App.Entry", "App.Helper"}, {"App.Helper"}),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.build_findings",
            return_value=[],
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.load_git_history",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.enrich_findings_with_git",
            return_value=[],
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor._diff_findings_against_existing",
            return_value=([], ["fd-stale"]),
        ),
        patch(
            "palace_mcp.extractors.dead_code.extractor.write_dead_findings",
            new=AsyncMock(return_value=DeadFindingWriteSummary(nodes_deleted=1)),
        ) as write_dead_findings,
        patch(
            "palace_mcp.extractors.dead_code.extractor.write_symbol_reachability",
            new=AsyncMock(return_value=None),
        ) as write_symbol_reachability,
    ):
        stats = await extractor._run_pipeline(
            driver=MagicMock(),
            settings=_settings(),
            ctx=_ctx(tmp_path, companion_run_id="symbol-run"),
        )

    assert stats.mode == ExtractorExecutionMode.INCREMENTAL
    assert stats.message is None
    kwargs = write_symbol_reachability.await_args.kwargs
    assert kwargs["reachable_qnames"] == {"App.Helper"}
    assert kwargs["unreachable_qnames"] == set()
    assert write_dead_findings.await_args.kwargs["stale_finding_ids"] == ["fd-stale"]


def test_diff_findings_against_existing_is_idempotent_for_stable_props() -> None:
    finding = DeadFinding(
        kind=FindingKind.DEAD_SYMBOL,
        severity=Severity.MEDIUM,
        project="tron-kit",
        members=[
            MemberEntry(
                qualified_name="App.Helper",
                kind="class",
                file_path="Sources/App/Helper.swift",
            )
        ],
        size=1,
        evidence_query="MATCH (n) RETURN n",
    )
    existing = {
        finding.finding_id: {
            **_stable_finding_props(finding, "project/tron-kit"),
            "created_at": "2026-06-22T00:00:00Z",
        }
    }

    changed, stale = _diff_findings_against_existing(
        findings=[finding],
        existing=existing,
        group_id="project/tron-kit",
    )

    assert changed == []
    assert stale == []
