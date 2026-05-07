"""Unit tests for reactive_dependency_tracer Neo4j writer."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.reactive_dependency_tracer.models import (
    DiagnosticSeverity,
    Range,
    ReactiveComponent,
    ReactiveComponentKind,
    ReactiveConfidence,
    ReactiveDiagnostic,
    ReactiveDiagnosticCode,
    ReactiveEdge,
    ReactiveEdgeKind,
    ReactiveEffect,
    ReactiveEffectKind,
    ReactiveResolutionStatus,
    ReactiveState,
    ReactiveStateKind,
    TriggerExpressionKind,
)
from palace_mcp.extractors.reactive_dependency_tracer.neo4j_writer import (
    ReactiveWriteSummary,
    write_reactive_graph,
)
from palace_mcp.extractors.reactive_dependency_tracer.normalizer import (
    NormalizedReactiveFile,
)


@dataclass
class _FakeCounters:
    nodes_created: int = 0
    relationships_created: int = 0
    properties_set: int = 0


@dataclass
class _FakeSummary:
    counters: _FakeCounters


class _FakeResult:
    def __init__(self, counters: _FakeCounters) -> None:
        self._summary = _FakeSummary(counters=counters)

    async def consume(self) -> _FakeSummary:
        return self._summary


class _FakeTx:
    def __init__(self, counters_by_marker: dict[str, _FakeCounters]) -> None:
        self.counters_by_marker = counters_by_marker
        self.queries: list[str] = []

    async def run(self, query: str, **_: object) -> _FakeResult:
        self.queries.append(query)
        marker = "default"
        for candidate in self.counters_by_marker:
            if candidate != "default" and candidate in query:
                marker = candidate
                break
        return _FakeResult(self.counters_by_marker.get(marker, _FakeCounters()))


class _FakeSession:
    def __init__(self, tx: _FakeTx) -> None:
        self.tx = tx
        self.execute_write_calls = 0

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    async def execute_write(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.execute_write_calls += 1
        return await fn(self.tx, *args, **kwargs)


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


def _batch() -> NormalizedReactiveFile:
    component = ReactiveComponent(
        id="component-1",
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        module_name="App",
        file_path="Sources/App/CounterView.swift",
        qualified_name="App.CounterView",
        display_name="CounterView",
        component_kind=ReactiveComponentKind.SWIFTUI_VIEW,
        start_line=1,
        end_line=10,
        range=Range(start_line=1, start_col=1, end_line=10, end_col=1),
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
    )
    state = ReactiveState(
        id="state-1",
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        language=Language.SWIFT,
        module_name="App",
        file_path="Sources/App/CounterView.swift",
        owner_qualified_name="App.CounterView",
        state_name="count",
        declared_type="Int",
        state_kind=ReactiveStateKind.STATE,
        wrapper_or_api="@State",
        macro_expansion_status="not_applicable",
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        confidence=ReactiveConfidence.HIGH,
    )
    effect = ReactiveEffect(
        id="effect-1",
        component_id="component-1",
        effect_kind=ReactiveEffectKind.ON_CHANGE,
        callee_name="onChange",
        file_path="Sources/App/CounterView.swift",
        start_line=7,
        end_line=9,
        range=Range(start_line=7, start_col=1, end_line=9, end_col=1),
        trigger_expression_kind=TriggerExpressionKind.ON_CHANGE_OF,
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
        confidence=ReactiveConfidence.HIGH,
    )
    diagnostic = ReactiveDiagnostic(
        id="diagnostic-1",
        group_id="group/x",
        project="proj",
        commit_sha="abc123",
        run_id="run-1",
        language=Language.SWIFT,
        file_path="Sources/App/CounterView.swift",
        ref="c1",
        diagnostic_code=ReactiveDiagnosticCode.SYMBOL_CORRELATION_UNAVAILABLE,
        severity=DiagnosticSeverity.INFO,
        message_redacted="no exact symbol key",
        range=Range(start_line=1, start_col=1, end_line=1, end_col=5),
    )
    edge = ReactiveEdge(
        id="edge-1",
        owner_component_id="component-1",
        edge_kind=ReactiveEdgeKind.TRIGGERS_EFFECT,
        source_id="state-1",
        target_id="effect-1",
        file_path="Sources/App/CounterView.swift",
        line=7,
        confidence=ReactiveConfidence.HIGH,
        access_path="count",
        trigger_expression_kind=TriggerExpressionKind.ON_CHANGE_OF,
        resolution_status=ReactiveResolutionStatus.SYNTAX_EXACT,
    )
    return NormalizedReactiveFile(
        file_path="Sources/App/CounterView.swift",
        language=Language.SWIFT,
        components=(component,),
        states=(state,),
        effects=(effect,),
        edges=(edge,),
        diagnostics=(diagnostic,),
        ref_to_node_id={"c1": "component-1"},
    )


@pytest.mark.asyncio
async def test_writer_uses_execute_write_per_batch() -> None:
    tx = _FakeTx({"default": _FakeCounters()})
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    await write_reactive_graph(driver=driver, batches=(_batch(), _batch()))

    assert session.execute_write_calls == 2


@pytest.mark.asyncio
async def test_writer_deletes_only_scoped_file_facts() -> None:
    tx = _FakeTx({"MATCH (n)\nWHERE n.source = $source": _FakeCounters()})
    driver = _FakeDriver(_FakeSession(tx))

    await write_reactive_graph(driver=driver, batches=(_batch(),))

    delete_query = next(query for query in tx.queries if "MATCH (n)" in query)
    assert "ReactiveComponent" in delete_query
    assert "ReactiveState" in delete_query
    assert "ReactiveEffect" in delete_query
    assert "ReactiveDiagnostic" in delete_query
    assert "SymbolOccurrenceShadow" not in delete_query
    assert "PublicApiSymbol" not in delete_query


@pytest.mark.asyncio
async def test_writer_merges_nodes_edges_and_diagnostic_relations() -> None:
    tx = _FakeTx(
        {
            "MERGE (node:ReactiveComponent": _FakeCounters(nodes_created=1),
            "MERGE (node:ReactiveState": _FakeCounters(nodes_created=1),
            "MERGE (node:ReactiveEffect": _FakeCounters(nodes_created=1),
            "MERGE (node:ReactiveDiagnostic": _FakeCounters(nodes_created=1),
            "MERGE (src)-[rel:TRIGGERS_EFFECT": _FakeCounters(relationships_created=1),
            "MERGE (diag)-[rel:DIAGNOSTIC_FOR": _FakeCounters(relationships_created=1),
        }
    )
    driver = _FakeDriver(_FakeSession(tx))

    summary = await write_reactive_graph(driver=driver, batches=(_batch(),))

    assert summary.nodes_created == 4
    assert summary.relationships_created == 2
    assert any("ReactiveComponent" in query for query in tx.queries)
    assert any("TRIGGERS_EFFECT" in query for query in tx.queries)
    assert any("DIAGNOSTIC_FOR" in query for query in tx.queries)


@pytest.mark.asyncio
async def test_writer_skips_invalid_batch_without_touching_valid_batch() -> None:
    invalid = NormalizedReactiveFile(
        file_path="Sources/App/Other.swift",
        language=Language.SWIFT,
        components=_batch().components,
        states=(),
        effects=(),
        edges=(),
        diagnostics=(),
        ref_to_node_id={},
    )
    tx = _FakeTx({"MERGE (node:ReactiveComponent": _FakeCounters(nodes_created=1)})
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    summary = await write_reactive_graph(driver=driver, batches=(invalid, _batch()))

    assert summary.nodes_created == 1
    assert session.execute_write_calls == 1


@pytest.mark.asyncio
async def test_writer_rerun_reports_zero_when_counters_zero() -> None:
    tx = _FakeTx({"default": _FakeCounters()})
    driver = _FakeDriver(_FakeSession(tx))

    summary = await write_reactive_graph(driver=driver, batches=(_batch(),))

    assert summary == ReactiveWriteSummary()
