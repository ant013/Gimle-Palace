"""Unit tests for dead_symbol_binary_surface Neo4j writer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from palace_mcp.extractors.dead_symbol_binary_surface.correlation import (
    BlockedContractSymbol,
    CorrelationResult,
)
from palace_mcp.extractors.dead_symbol_binary_surface.models import (
    BinarySurfaceRecord,
    BinarySurfaceSource,
    CandidateState,
    Confidence,
    DeadSymbolCandidate,
    DeadSymbolEvidenceMode,
    DeadSymbolEvidenceSource,
    DeadSymbolKind,
    DeadSymbolLanguage,
    SkipReason,
    SurfaceKind,
)
from palace_mcp.extractors.dead_symbol_binary_surface.neo4j_writer import (
    DeadSymbolWriteSummary,
    write_dead_symbol_graph,
)
from palace_mcp.extractors.foundation.schema import EXPECTED_SCHEMA


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

    async def execute_write(self, fn: Any, *args: object, **kwargs: object) -> object:
        self.execute_write_calls += 1
        return await fn(self.tx, *args, **kwargs)


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


def _candidate() -> DeadSymbolCandidate:
    return DeadSymbolCandidate(
        id="candidate-1",
        group_id="project/test",
        project="dead-symbol-mini",
        module_name="ProducerKit",
        language=DeadSymbolLanguage.SWIFT,
        commit_sha="commit-1",
        symbol_key="Wallet.balance()",
        display_name="Wallet.balance()",
        kind=DeadSymbolKind.FUNCTION,
        source_file="Sources/ProducerKit/Wallet.swift",
        source_line=10,
        evidence_source=DeadSymbolEvidenceSource.PERIPHERY,
        evidence_mode=DeadSymbolEvidenceMode.STATIC,
        confidence=Confidence.HIGH,
        candidate_state=CandidateState.RETAINED_PUBLIC_API,
        skip_reason=SkipReason.CROSS_MODULE_CONTRACT_CONSUMED,
    )


def _binary_surface() -> BinarySurfaceRecord:
    return BinarySurfaceRecord(
        id="surface-1",
        group_id="project/test",
        project="dead-symbol-mini",
        module_name="ProducerKit",
        language=DeadSymbolLanguage.SWIFT,
        commit_sha="commit-1",
        symbol_key="Wallet.balance()",
        surface_kind=SurfaceKind.PUBLIC_API,
        retention_reason="public/open API symbol retained from public_api_surface",
        source=BinarySurfaceSource.PUBLIC_API_SURFACE,
    )


def _correlation_result(
    *,
    backed_symbol_id: int | None = 42,
    backed_public_api_symbol_id: str | None = "public-1",
    blocked_contract_symbols: tuple[BlockedContractSymbol, ...] | None = None,
) -> CorrelationResult:
    if blocked_contract_symbols is None:
        blocked_contract_symbols = (
            BlockedContractSymbol(
                public_symbol_id="public-1",
                contract_snapshot_id="snapshot-1",
                consumer_module_name="ConsumerApp",
                producer_module_name="ProducerKit",
                commit_sha="commit-1",
                use_count=2,
                evidence_paths_sample=(
                    "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                ),
            ),
        )
    return CorrelationResult(
        candidate=_candidate(),
        binary_surface=_binary_surface(),
        backed_symbol_id=backed_symbol_id,
        backed_public_api_symbol_id=backed_public_api_symbol_id,
        blocked_contract_symbols=blocked_contract_symbols,
    )


def test_writer_creates_candidate_and_binary_surface_constraints() -> None:
    names = EXPECTED_SCHEMA.all_names()
    assert "dead_symbol_candidate_id_unique" in names
    assert "binary_surface_record_id_unique" in names


@pytest.mark.asyncio
async def test_writer_uses_execute_write_for_batch_atomicity() -> None:
    tx = _FakeTx({"default": _FakeCounters()})
    session = _FakeSession(tx)
    driver = _FakeDriver(session)

    await write_dead_symbol_graph(driver=driver, rows=(_correlation_result(),))

    assert session.execute_write_calls == 1


@pytest.mark.asyncio
async def test_writer_merges_candidate_once() -> None:
    tx = _FakeTx(
        {"MERGE (candidate:DeadSymbolCandidate": _FakeCounters(nodes_created=1)}
    )
    driver = _FakeDriver(_FakeSession(tx))

    await write_dead_symbol_graph(driver=driver, rows=(_correlation_result(),))

    assert (
        sum("MERGE (candidate:DeadSymbolCandidate" in query for query in tx.queries)
        == 1
    )


@pytest.mark.asyncio
async def test_writer_merges_binary_surface_once() -> None:
    tx = _FakeTx({"MERGE (surface:BinarySurfaceRecord": _FakeCounters(nodes_created=1)})
    driver = _FakeDriver(_FakeSession(tx))

    await write_dead_symbol_graph(driver=driver, rows=(_correlation_result(),))

    assert (
        sum("MERGE (surface:BinarySurfaceRecord" in query for query in tx.queries) == 1
    )


@pytest.mark.asyncio
async def test_writer_merges_backed_by_symbol_once() -> None:
    tx = _FakeTx({"BACKED_BY_SYMBOL": _FakeCounters(relationships_created=1)})
    driver = _FakeDriver(_FakeSession(tx))

    await write_dead_symbol_graph(driver=driver, rows=(_correlation_result(),))

    assert sum("BACKED_BY_SYMBOL" in query for query in tx.queries) == 1


@pytest.mark.asyncio
async def test_writer_merges_backed_by_public_api_once() -> None:
    tx = _FakeTx({"BACKED_BY_PUBLIC_API": _FakeCounters(relationships_created=1)})
    driver = _FakeDriver(_FakeSession(tx))

    await write_dead_symbol_graph(driver=driver, rows=(_correlation_result(),))

    assert sum("BACKED_BY_PUBLIC_API" in query for query in tx.queries) == 1


@pytest.mark.asyncio
async def test_writer_merges_has_binary_surface_once() -> None:
    tx = _FakeTx({"HAS_BINARY_SURFACE": _FakeCounters(relationships_created=1)})
    driver = _FakeDriver(_FakeSession(tx))

    await write_dead_symbol_graph(driver=driver, rows=(_correlation_result(),))

    assert sum("HAS_BINARY_SURFACE" in query for query in tx.queries) == 1


@pytest.mark.asyncio
async def test_writer_merges_blocked_by_contract_symbol_once() -> None:
    tx = _FakeTx({"BLOCKED_BY_CONTRACT_SYMBOL": _FakeCounters(relationships_created=1)})
    driver = _FakeDriver(_FakeSession(tx))

    await write_dead_symbol_graph(driver=driver, rows=(_correlation_result(),))

    assert sum("BLOCKED_BY_CONTRACT_SYMBOL" in query for query in tx.queries) == 1


@pytest.mark.asyncio
async def test_writer_rerun_reports_zero_nodes_relationships_and_properties() -> None:
    tx = _FakeTx({"default": _FakeCounters()})
    driver = _FakeDriver(_FakeSession(tx))

    summary = await write_dead_symbol_graph(
        driver=driver, rows=(_correlation_result(),)
    )

    assert summary == DeadSymbolWriteSummary(
        nodes_created=0,
        relationships_created=0,
        properties_set=0,
    )


@pytest.mark.asyncio
async def test_writer_third_run_after_upstream_change_updates_only_expected_properties() -> (
    None
):
    tx = _FakeTx(
        {"MERGE (candidate:DeadSymbolCandidate": _FakeCounters(properties_set=1)}
    )
    driver = _FakeDriver(_FakeSession(tx))

    summary = await write_dead_symbol_graph(
        driver=driver, rows=(_correlation_result(),)
    )

    assert summary.nodes_created == 0
    assert summary.relationships_created == 0
    assert summary.properties_set == 1


@pytest.mark.asyncio
async def test_writer_does_not_create_blocker_edge_without_public_symbol() -> None:
    tx = _FakeTx({"BLOCKED_BY_CONTRACT_SYMBOL": _FakeCounters(relationships_created=1)})
    driver = _FakeDriver(_FakeSession(tx))

    await write_dead_symbol_graph(
        driver=driver,
        rows=(
            _correlation_result(
                backed_public_api_symbol_id=None,
                blocked_contract_symbols=(
                    BlockedContractSymbol(
                        public_symbol_id="public-1",
                        contract_snapshot_id="snapshot-1",
                        consumer_module_name="ConsumerApp",
                        producer_module_name="ProducerKit",
                        commit_sha="commit-1",
                        use_count=2,
                        evidence_paths_sample=("ConsumerApp/Sources/Wallet.swift",),
                    ),
                ),
            ),
        ),
    )

    assert not any("BLOCKED_BY_CONTRACT_SYMBOL" in query for query in tx.queries)
