"""Unit tests for the cross_module_contract extractor."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import (
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.cross_module_contract import (
    _DELETE_DELTA_AFFECTED_SYMBOLS,
    _DELETE_DELTA_SNAPSHOT_LINKS,
    _DELETE_SNAPSHOT_CONSUMPTIONS,
    _DELETE_SNAPSHOT_SURFACE_LINKS,
    _DELETE_STALE_PAIR_DELTAS,
    _DELETE_STALE_PAIR_SNAPSHOTS,
    CrossModuleContractExtractor,
    _DeltaRequest,
    _OccurrenceResolution,
    _PlannedContractDelta,
    _PlannedContractSnapshot,
    _load_occurrences_for_surface,
    _plan_requested_deltas,
    _swift_indexstore_lookup_name,
    _swift_qname_from_usr,
    _write_contract_graph,
    _WRITE_CONSUMPTION,
    _WRITE_DELTA,
    _WRITE_DELTA_AFFECTED_SYMBOL,
    _WRITE_SNAPSHOT,
    build_contract_delta,
    plan_contract_snapshots,
)
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    Language,
    ModuleContractAffectedSymbol,
    ModuleContractConsumption,
    ModuleContractDelta,
    ModuleContractSnapshot,
    PublicApiArtifactKind,
    PublicApiSurface,
    PublicApiSymbol,
    PublicApiSymbolKind,
    PublicApiVisibility,
    TantivyOccurrenceMatch,
    build_symbol_occurrence_doc_key,
)
from palace_mcp.extractors.foundation.module_owner import (
    ModuleOwnerMap,
    ModuleOwnerResolution,
    ModuleOwnerRoot,
    resolve_module_owner_from_map,
)
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge

_DEFAULT_QNAME = object()


def _surface() -> PublicApiSurface:
    return _surface_for(commit_sha="commit-current")


def _surface_for(*, commit_sha: str) -> PublicApiSurface:
    return PublicApiSurface(
        id=f"surface-{commit_sha}",
        group_id="project/test",
        project="contract-mini",
        module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha=commit_sha,
        artifact_path=".palace/public-api/swift/ProducerKit.swiftinterface",
        artifact_kind=PublicApiArtifactKind.SWIFTINTERFACE,
        tool_name="swiftc",
        tool_version="6.2.4",
    )


def _symbol(
    *,
    symbol_id: str,
    fqn: str,
    visibility: PublicApiVisibility = PublicApiVisibility.PUBLIC,
    signature_hash: str = "sig",
    symbol_qualified_name: object = _DEFAULT_QNAME,
    commit_sha: str = "commit-current",
) -> PublicApiSymbol:
    return PublicApiSymbol(
        id=symbol_id,
        group_id="project/test",
        project="contract-mini",
        module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha=commit_sha,
        fqn=fqn,
        display_name=fqn,
        kind=PublicApiSymbolKind.FUNCTION,
        visibility=visibility,
        signature=fqn,
        signature_hash=signature_hash,
        source_artifact_path=".palace/public-api/swift/ProducerKit.swiftinterface",
        source_line=1,
        symbol_qualified_name=(
            fqn if symbol_qualified_name is _DEFAULT_QNAME else symbol_qualified_name
        ),
    )


def _planned_snapshot(
    *,
    commit_sha: str,
    consumer_module_name: str,
    symbols: list[PublicApiSymbol],
    consumptions: list[ModuleContractConsumption],
) -> _PlannedContractSnapshot:
    snapshot = ModuleContractSnapshot(
        id=f"snapshot-{consumer_module_name}-{commit_sha}",
        group_id="project/test",
        project="contract-mini",
        consumer_module_name=consumer_module_name,
        producer_module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha=commit_sha,
        include_package=False,
        producer_surface_id=_surface_for(commit_sha=commit_sha).id,
        symbol_count=len(consumptions),
        use_count=sum(consumption.use_count for consumption in consumptions),
        file_count=len({consumption.first_seen_path for consumption in consumptions}),
        skipped_symbol_count=0,
    )
    return _PlannedContractSnapshot(
        snapshot=snapshot,
        consumptions=consumptions,
        symbols_by_fqn={symbol.fqn: symbol for symbol in symbols},
    )


def _occurrence(file_path: str, qname: str) -> TantivyOccurrenceMatch:
    return TantivyOccurrenceMatch(
        doc_key=build_symbol_occurrence_doc_key(
            symbol_id=symbol_id_for(qname),
            file_path=file_path,
            line=4,
            col_start=10,
            commit_sha="commit-current",
        ),
        symbol_id=symbol_id_for(qname),
        file_path=file_path,
        line=4,
        col_start=10,
        col_end=None,
        commit_sha="commit-current",
    )


def test_plan_contract_snapshots_exact_match_and_skips() -> None:
    surface = _surface()
    symbols = [
        _symbol(symbol_id="sym-balance", fqn="Wallet.balance()"),
        _symbol(
            symbol_id="sym-package",
            fqn="packageHelper()",
            visibility=PublicApiVisibility.PACKAGE,
        ),
        _symbol(symbol_id="sym-stale", fqn="staleExport()"),
        _symbol(
            symbol_id="sym-missing",
            fqn="missingQualifiedName()",
            symbol_qualified_name=None,
        ),
    ]

    occurrences_by_symbol = {
        "sym-balance": _OccurrenceResolution(
            status="matched",
            match_symbol_id=symbol_id_for("Wallet.balance()"),
            occurrences=(
                _occurrence(
                    "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                    "Wallet.balance()",
                ),
                _occurrence(
                    "ProducerKit/Sources/ProducerKit/InternalUse.swift",
                    "Wallet.balance()",
                ),
                _occurrence(
                    "UnknownFeature/Sources/UnknownFeature/Loose.swift",
                    "Wallet.balance()",
                ),
            ),
        ),
        "sym-package": _OccurrenceResolution(
            status="matched",
            match_symbol_id=symbol_id_for("packageHelper()"),
            occurrences=(
                _occurrence(
                    "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                    "packageHelper()",
                ),
            ),
        ),
        "sym-stale": _OccurrenceResolution(status="no_consumers"),
        "sym-missing": _OccurrenceResolution(status="unresolved"),
    }

    def resolve_owner(file_path: str) -> ModuleOwnerResolution:
        if file_path.startswith("ConsumerApp/"):
            return ModuleOwnerResolution.resolved("ConsumerApp", source="fixture_map")
        if file_path.startswith("ProducerKit/"):
            return ModuleOwnerResolution.resolved("ProducerKit", source="fixture_map")
        return ModuleOwnerResolution.unresolved("consumer_module_unresolved")

    planned = plan_contract_snapshots(
        surface=surface,
        symbols=symbols,
        occurrences_by_symbol=occurrences_by_symbol,
        resolve_owner=resolve_owner,
        include_package=False,
    )

    assert len(planned) == 1
    snapshot = planned[0].snapshot
    assert snapshot.consumer_module_name == "ConsumerApp"
    assert snapshot.producer_module_name == "ProducerKit"
    assert snapshot.symbol_count == 1
    assert snapshot.use_count == 1
    assert snapshot.file_count == 1
    assert snapshot.skipped_symbol_count == 3

    assert len(planned[0].consumptions) == 1
    edge = planned[0].consumptions[0]
    assert edge.public_symbol_id == "sym-balance"
    assert edge.match_symbol_id == symbol_id_for("Wallet.balance()")
    assert edge.first_seen_path == "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
    assert edge.evidence_paths_sample == [
        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
    ]


def test_plan_contract_snapshots_include_package_when_explicit() -> None:
    surface = _surface()
    symbols = [
        _symbol(symbol_id="sym-balance", fqn="Wallet.balance()"),
        _symbol(
            symbol_id="sym-package",
            fqn="packageHelper()",
            visibility=PublicApiVisibility.PACKAGE,
        ),
    ]
    occurrences_by_symbol = {
        "sym-balance": _OccurrenceResolution(
            status="matched",
            match_symbol_id=symbol_id_for("Wallet.balance()"),
            occurrences=(
                _occurrence(
                    "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                    "Wallet.balance()",
                ),
            ),
        ),
        "sym-package": _OccurrenceResolution(
            status="matched",
            match_symbol_id=symbol_id_for("packageHelper()"),
            occurrences=(
                _occurrence(
                    "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                    "packageHelper()",
                ),
            ),
        ),
    }

    planned = plan_contract_snapshots(
        surface=surface,
        symbols=symbols,
        occurrences_by_symbol=occurrences_by_symbol,
        resolve_owner=lambda _: ModuleOwnerResolution.resolved(
            "ConsumerApp", source="fixture_map"
        ),
        include_package=True,
    )

    assert len(planned) == 1
    snapshot = planned[0].snapshot
    assert snapshot.symbol_count == 2
    assert snapshot.use_count == 2
    assert snapshot.file_count == 1
    assert {edge.public_symbol_id for edge in planned[0].consumptions} == {
        "sym-balance",
        "sym-package",
    }


def test_plan_contract_snapshots_writes_baseline_when_no_consumers_match() -> None:
    surface = _surface()
    symbols = [
        _symbol(symbol_id="sym-balance", fqn="Wallet.balance()"),
        _symbol(
            symbol_id="sym-package",
            fqn="packageHelper()",
            visibility=PublicApiVisibility.PACKAGE,
        ),
        _symbol(
            symbol_id="sym-missing",
            fqn="missingQualifiedName()",
            symbol_qualified_name=None,
        ),
    ]

    planned = plan_contract_snapshots(
        surface=surface,
        symbols=symbols,
        occurrences_by_symbol={
            "sym-balance": _OccurrenceResolution(status="no_consumers"),
            "sym-package": _OccurrenceResolution(status="unresolved"),
            "sym-missing": _OccurrenceResolution(status="unresolved"),
        },
        resolve_owner=lambda _: ModuleOwnerResolution.unresolved(
            "consumer_module_unresolved"
        ),
        include_package=False,
    )

    assert len(planned) == 1
    snapshot = planned[0].snapshot
    assert snapshot.consumer_module_name == "__no_cross_module_consumer__"
    assert snapshot.producer_module_name == "ProducerKit"
    assert snapshot.symbol_count == 0
    assert snapshot.use_count == 0
    assert snapshot.file_count == 0
    assert snapshot.skipped_symbol_count == 3
    assert planned[0].consumptions == []


def test_swift_indexstore_lookup_name_strips_types_to_labels() -> None:
    assert _swift_indexstore_lookup_name("Wallet.init(id: Swift.String)") == "init(id:)"
    assert (
        _swift_indexstore_lookup_name(
            "Wallet.configure(_ value: Swift.Int, label: Wallet)"
        )
        == "configure(_:label:)"
    )


def test_swift_qname_from_usr_matches_scip_descriptor_format() -> None:
    usr = "s:11ProducerKit6WalletV7balanceyyF"
    assert _swift_qname_from_usr(usr) == (
        "ProducerKit s%3A11ProducerKit6WalletV7balanceyyF"
    )


def test_build_contract_delta_counts_added_removed_and_signature_changed() -> None:
    from_snapshot = ModuleContractSnapshot(
        id="snap-from",
        group_id="project/test",
        project="contract-mini",
        consumer_module_name="ConsumerApp",
        producer_module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha="commit-from",
        include_package=False,
        producer_surface_id="surface-from",
        symbol_count=2,
        use_count=3,
        file_count=1,
        skipped_symbol_count=0,
    )
    to_snapshot = ModuleContractSnapshot(
        id="snap-to",
        group_id="project/test",
        project="contract-mini",
        consumer_module_name="ConsumerApp",
        producer_module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha="commit-to",
        include_package=False,
        producer_surface_id="surface-to",
        symbol_count=2,
        use_count=7,
        file_count=1,
        skipped_symbol_count=0,
    )
    from_symbols = {
        "Wallet.balance()": _symbol(
            symbol_id="sym-balance-old",
            fqn="Wallet.balance()",
            signature_hash="sig-old",
        ),
        "staleExport()": _symbol(
            symbol_id="sym-stale-old",
            fqn="staleExport()",
            signature_hash="sig-stale",
        ),
    }
    to_symbols = {
        "Wallet.balance()": _symbol(
            symbol_id="sym-balance-new",
            fqn="Wallet.balance()",
            signature_hash="sig-new",
        ),
        "packageHelper()": _symbol(
            symbol_id="sym-package-new",
            fqn="packageHelper()",
            signature_hash="sig-package",
            visibility=PublicApiVisibility.PACKAGE,
        ),
    }
    from_consumptions = [
        ModuleContractConsumption(
            public_symbol_id="sym-balance-old",
            group_id="project/test",
            commit_sha="commit-from",
            match_symbol_id=symbol_id_for("Wallet.balance()"),
            use_count=2,
            file_count=1,
            first_seen_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
            evidence_paths_sample=[
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
        ),
        ModuleContractConsumption(
            public_symbol_id="sym-stale-old",
            group_id="project/test",
            commit_sha="commit-from",
            match_symbol_id=symbol_id_for("staleExport()"),
            use_count=1,
            file_count=1,
            first_seen_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
            evidence_paths_sample=[
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
        ),
    ]
    to_consumptions = [
        ModuleContractConsumption(
            public_symbol_id="sym-balance-new",
            group_id="project/test",
            commit_sha="commit-to",
            match_symbol_id=symbol_id_for("Wallet.balance()"),
            use_count=4,
            file_count=1,
            first_seen_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
            evidence_paths_sample=[
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
        ),
        ModuleContractConsumption(
            public_symbol_id="sym-package-new",
            group_id="project/test",
            commit_sha="commit-to",
            match_symbol_id=symbol_id_for("packageHelper()"),
            use_count=3,
            file_count=1,
            first_seen_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
            evidence_paths_sample=[
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
        ),
    ]

    delta, affected = build_contract_delta(
        from_snapshot=from_snapshot,
        to_snapshot=to_snapshot,
        from_symbols=from_symbols,
        to_symbols=to_symbols,
        from_consumptions=from_consumptions,
        to_consumptions=to_consumptions,
    )

    assert delta.removed_consumed_symbol_count == 1
    assert delta.signature_changed_consumed_symbol_count == 1
    assert delta.added_consumed_symbol_count == 1
    assert delta.affected_use_count == 8
    assert {(item.change_kind, item.public_symbol_id) for item in affected} == {
        ("removed", "sym-stale-old"),
        ("signature_changed", "sym-balance-new"),
        ("added", "sym-package-new"),
    }


def test_plan_requested_deltas_supports_symbol_delta_requests_with_missing_target() -> (
    None
):
    stale_symbol = _symbol(
        symbol_id="sym-stale-old",
        fqn="staleExport()",
        signature_hash="sig-stale-old",
        commit_sha="commit-from",
    )
    from_consumptions = [
        ModuleContractConsumption(
            public_symbol_id="sym-stale-old",
            group_id="project/test",
            commit_sha="commit-from",
            match_symbol_id=symbol_id_for("staleExport()"),
            use_count=2,
            file_count=1,
            first_seen_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
            evidence_paths_sample=[
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
            ],
        )
    ]
    planned = [
        _planned_snapshot(
            commit_sha="commit-from",
            consumer_module_name="ConsumerApp",
            symbols=[stale_symbol],
            consumptions=from_consumptions,
        )
    ]

    deltas = _plan_requested_deltas(
        project="contract-mini",
        planned=planned,
        delta_requests=[
            _DeltaRequest(
                producer_module_name="ProducerKit",
                language=Language.SWIFT,
                from_commit_sha="commit-from",
                to_commit_sha="commit-to",
                fqn="staleExport()",
                change_kind="removed",
                previous_signature_hash="sig-stale-old",
            )
        ],
    )

    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.delta.consumer_module_name == "ConsumerApp"
    assert delta.delta.producer_module_name == "ProducerKit"
    assert delta.delta.from_commit_sha == "commit-from"
    assert delta.delta.to_commit_sha == "commit-to"
    assert delta.delta.removed_consumed_symbol_count == 1
    assert delta.delta.signature_changed_consumed_symbol_count == 0
    assert delta.delta.added_consumed_symbol_count == 0
    assert delta.delta.affected_use_count == 2
    assert delta.to_snapshot_id != planned[0].snapshot.id
    assert [
        (item.change_kind, item.public_symbol_id) for item in delta.affected_symbols
    ] == [("removed", "sym-stale-old")]


def test_plan_requested_deltas_emits_one_delta_per_consumer_for_symbol_requests() -> (
    None
):
    from_symbol = _symbol(
        symbol_id="sym-balance-old",
        fqn="Wallet.balance()",
        signature_hash="sig-old",
        commit_sha="commit-from",
    )
    to_symbol = _symbol(
        symbol_id="sym-balance-new",
        fqn="Wallet.balance()",
        signature_hash="sig-new",
        commit_sha="commit-to",
    )
    planned = [
        _planned_snapshot(
            commit_sha="commit-from",
            consumer_module_name="ConsumerApp",
            symbols=[from_symbol],
            consumptions=[
                ModuleContractConsumption(
                    public_symbol_id="sym-balance-old",
                    group_id="project/test",
                    commit_sha="commit-from",
                    match_symbol_id=symbol_id_for("Wallet.balance()"),
                    use_count=1,
                    file_count=1,
                    first_seen_path=(
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ),
                    evidence_paths_sample=[
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ],
                )
            ],
        ),
        _planned_snapshot(
            commit_sha="commit-to",
            consumer_module_name="ConsumerApp",
            symbols=[to_symbol],
            consumptions=[
                ModuleContractConsumption(
                    public_symbol_id="sym-balance-new",
                    group_id="project/test",
                    commit_sha="commit-to",
                    match_symbol_id=symbol_id_for("Wallet.balance()"),
                    use_count=3,
                    file_count=1,
                    first_seen_path=(
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ),
                    evidence_paths_sample=[
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ],
                )
            ],
        ),
        _planned_snapshot(
            commit_sha="commit-from",
            consumer_module_name="ConsumerCLI",
            symbols=[from_symbol],
            consumptions=[
                ModuleContractConsumption(
                    public_symbol_id="sym-balance-old",
                    group_id="project/test",
                    commit_sha="commit-from",
                    match_symbol_id=symbol_id_for("Wallet.balance()"),
                    use_count=2,
                    file_count=1,
                    first_seen_path="ConsumerCLI/Sources/ConsumerCLI/Main.swift",
                    evidence_paths_sample=[
                        "ConsumerCLI/Sources/ConsumerCLI/Main.swift"
                    ],
                )
            ],
        ),
        _planned_snapshot(
            commit_sha="commit-to",
            consumer_module_name="ConsumerCLI",
            symbols=[to_symbol],
            consumptions=[
                ModuleContractConsumption(
                    public_symbol_id="sym-balance-new",
                    group_id="project/test",
                    commit_sha="commit-to",
                    match_symbol_id=symbol_id_for("Wallet.balance()"),
                    use_count=5,
                    file_count=1,
                    first_seen_path="ConsumerCLI/Sources/ConsumerCLI/Main.swift",
                    evidence_paths_sample=[
                        "ConsumerCLI/Sources/ConsumerCLI/Main.swift"
                    ],
                )
            ],
        ),
    ]

    deltas = _plan_requested_deltas(
        project="contract-mini",
        planned=planned,
        delta_requests=[
            _DeltaRequest(
                producer_module_name="ProducerKit",
                language=Language.SWIFT,
                from_commit_sha="commit-from",
                to_commit_sha="commit-to",
                fqn="Wallet.balance()",
                change_kind="signature_changed",
                previous_signature_hash="sig-old",
                current_signature_hash="sig-new",
            )
        ],
    )

    assert len(deltas) == 2
    assert {
        delta.delta.consumer_module_name: (
            delta.delta.signature_changed_consumed_symbol_count,
            delta.delta.affected_use_count,
            [
                (item.change_kind, item.public_symbol_id)
                for item in delta.affected_symbols
            ],
        )
        for delta in deltas
    } == {
        "ConsumerApp": (1, 3, [("signature_changed", "sym-balance-new")]),
        "ConsumerCLI": (1, 5, [("signature_changed", "sym-balance-new")]),
    }


def test_plan_requested_deltas_synthesizes_evicted_consumer_target_snapshot() -> None:
    stale_symbol = _symbol(
        symbol_id="sym-stale-old",
        fqn="staleExport()",
        signature_hash="sig-stale-old",
        commit_sha="commit-from",
    )
    planned = [
        _planned_snapshot(
            commit_sha="commit-from",
            consumer_module_name="ConsumerApp",
            symbols=[stale_symbol],
            consumptions=[
                ModuleContractConsumption(
                    public_symbol_id="sym-stale-old",
                    group_id="project/test",
                    commit_sha="commit-from",
                    match_symbol_id=symbol_id_for("staleExport()"),
                    use_count=2,
                    file_count=1,
                    first_seen_path=(
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ),
                    evidence_paths_sample=[
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ],
                )
            ],
        ),
        _planned_snapshot(
            commit_sha="commit-to",
            consumer_module_name="__no_cross_module_consumer__",
            symbols=[_symbol(symbol_id="sym-stale-new", fqn="staleExport()")],
            consumptions=[],
        ),
    ]

    deltas = _plan_requested_deltas(
        project="contract-mini",
        planned=planned,
        delta_requests=[
            _DeltaRequest(
                producer_module_name="ProducerKit",
                language=Language.SWIFT,
                from_commit_sha="commit-from",
                to_commit_sha="commit-to",
                fqn="staleExport()",
                change_kind="removed",
                previous_signature_hash="sig-stale-old",
            )
        ],
    )

    assert len(deltas) == 1
    delta = deltas[0]
    assert delta.delta.consumer_module_name == "ConsumerApp"
    assert delta.delta.removed_consumed_symbol_count == 1
    assert delta.delta.signature_changed_consumed_symbol_count == 0
    assert delta.delta.added_consumed_symbol_count == 0
    assert delta.delta.affected_use_count == 2
    assert delta.to_snapshot_id != planned[1].snapshot.id
    assert [
        (item.change_kind, item.public_symbol_id) for item in delta.affected_symbols
    ] == [("removed", "sym-stale-old")]


class _FakeSessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeDriver:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def session(self) -> _FakeSessionContext:
        return _FakeSessionContext(self._session)


class _FakeTantivyBridge:
    async def __aenter__(self) -> "_FakeTantivyBridge":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_run_uses_prior_surface_when_delta_requests_exist_but_current_is_empty(
    tmp_path: Path,
) -> None:
    stale_symbol = _symbol(
        symbol_id="sym-stale-old",
        fqn="staleExport()",
        signature_hash="sig-stale-old",
        commit_sha="commit-from",
    )
    planned_from = _planned_snapshot(
        commit_sha="commit-from",
        consumer_module_name="ConsumerApp",
        symbols=[stale_symbol],
        consumptions=[
            ModuleContractConsumption(
                public_symbol_id="sym-stale-old",
                group_id="project/test",
                commit_sha="commit-from",
                match_symbol_id=symbol_id_for("staleExport()"),
                use_count=2,
                file_count=1,
                first_seen_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                evidence_paths_sample=[
                    "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                ],
            )
        ],
    )
    ctx = ExtractorRunContext(
        project_slug="contract-mini",
        group_id="project/test",
        repo_path=tmp_path,
        run_id="run-cross-module-contract",
        duration_ms=0,
        logger=logging.getLogger("test.cross_module_contract"),
    )
    settings = SimpleNamespace(
        palace_indexstore_paths={},
        palace_sourcekit_index_store_path=None,
        palace_tantivy_index_path=str(tmp_path / "tantivy"),
        palace_tantivy_heap_mb=50,
    )

    async def fake_load_public_api_surfaces(
        *,
        driver,
        project: str,
        commit_sha: str,
        producer_modules: set[str] | None = None,
    ) -> list[object]:
        del driver, project, producer_modules
        if commit_sha == "commit-current":
            return []
        return [MagicMock()]

    async def fake_plan_snapshots_for_commit(
        **kwargs,
    ) -> list[_PlannedContractSnapshot]:
        if kwargs["commit_sha"] == "commit-current":
            return []
        return [planned_from]

    captured: dict[str, object] = {}

    async def fake_write_contract_graph(
        *,
        driver,
        planned: list[_PlannedContractSnapshot],
        planned_deltas: list[_PlannedContractDelta],
    ) -> ExtractorStats:
        del driver
        captured["planned"] = planned
        captured["planned_deltas"] = planned_deltas
        return ExtractorStats(
            nodes_written=len(planned) + len(planned_deltas), edges_written=6
        )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=MagicMock()),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.cross_module_contract._read_head_sha",
            return_value="commit-current",
        ),
        patch(
            "palace_mcp.extractors.cross_module_contract._load_delta_requests",
            new=AsyncMock(
                return_value=[
                    _DeltaRequest(
                        consumer_module_name="ConsumerApp",
                        producer_module_name="ProducerKit",
                        language=Language.SWIFT,
                        from_commit_sha="commit-from",
                        to_commit_sha="commit-current",
                        include_package=False,
                    )
                ]
            ),
        ),
        patch(
            "palace_mcp.extractors.cross_module_contract._load_public_api_surfaces",
            new=fake_load_public_api_surfaces,
        ),
        patch(
            "palace_mcp.extractors.cross_module_contract._plan_snapshots_for_commit",
            new=fake_plan_snapshots_for_commit,
        ),
        patch(
            "palace_mcp.extractors.cross_module_contract._write_contract_graph",
            new=fake_write_contract_graph,
        ),
        patch(
            "palace_mcp.extractors.foundation.tantivy_bridge.TantivyBridge",
            return_value=_FakeTantivyBridge(),
        ),
    ):
        stats = await CrossModuleContractExtractor().run(
            graphiti=MagicMock(),
            ctx=ctx,
        )

    assert stats.outcome == ExtractorOutcome.OK
    assert stats.nodes_written == 3
    planned = captured["planned"]
    assert isinstance(planned, list)
    assert len(planned) == 2
    current_snapshot = planned[1].snapshot
    assert current_snapshot.commit_sha == "commit-current"
    assert current_snapshot.consumer_module_name == "ConsumerApp"
    assert current_snapshot.symbol_count == 0
    assert current_snapshot.use_count == 0
    planned_deltas = captured["planned_deltas"]
    assert isinstance(planned_deltas, list)
    assert len(planned_deltas) == 1
    delta = planned_deltas[0].delta
    assert delta.removed_consumed_symbol_count == 1
    assert delta.signature_changed_consumed_symbol_count == 0
    assert delta.added_consumed_symbol_count == 0
    assert delta.to_commit_sha == "commit-current"


@pytest.mark.asyncio
async def test_write_contract_graph_persists_synthesized_delta_snapshots() -> None:
    session = AsyncMock()
    driver = _FakeDriver(session)
    stale_symbol = _symbol(
        symbol_id="sym-stale-old",
        fqn="staleExport()",
        signature_hash="sig-stale-old",
        commit_sha="commit-from",
    )
    planned = [
        _planned_snapshot(
            commit_sha="commit-from",
            consumer_module_name="ConsumerApp",
            symbols=[stale_symbol],
            consumptions=[
                ModuleContractConsumption(
                    public_symbol_id="sym-stale-old",
                    group_id="project/test",
                    commit_sha="commit-from",
                    match_symbol_id=symbol_id_for("staleExport()"),
                    use_count=2,
                    file_count=1,
                    first_seen_path=(
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ),
                    evidence_paths_sample=[
                        "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
                    ],
                )
            ],
        )
    ]
    planned_deltas = _plan_requested_deltas(
        project="contract-mini",
        planned=planned,
        delta_requests=[
            _DeltaRequest(
                producer_module_name="ProducerKit",
                language=Language.SWIFT,
                from_commit_sha="commit-from",
                to_commit_sha="commit-to",
                fqn="staleExport()",
                change_kind="removed",
                previous_signature_hash="sig-stale-old",
            )
        ],
    )

    assert len(planned) == 2
    assert planned_deltas[0].to_snapshot_id == planned[1].snapshot.id

    stats = await _write_contract_graph(
        driver=driver,
        planned=planned,
        planned_deltas=planned_deltas,
    )

    assert stats.nodes_written == 3
    assert stats.edges_written == 6
    queries = [call.args[0] for call in session.run.await_args_list]
    assert queries == [
        _DELETE_STALE_PAIR_DELTAS,
        _DELETE_STALE_PAIR_SNAPSHOTS,
        _DELETE_SNAPSHOT_CONSUMPTIONS,
        _DELETE_SNAPSHOT_SURFACE_LINKS,
        _WRITE_SNAPSHOT,
        _WRITE_CONSUMPTION,
        _DELETE_SNAPSHOT_CONSUMPTIONS,
        _DELETE_SNAPSHOT_SURFACE_LINKS,
        _WRITE_SNAPSHOT,
        _DELETE_DELTA_AFFECTED_SYMBOLS,
        _DELETE_DELTA_SNAPSHOT_LINKS,
        _WRITE_DELTA,
        _WRITE_DELTA_AFFECTED_SYMBOL,
    ]
    assert session.run.await_args_list[0].kwargs == {
        "project": "contract-mini",
        "consumer_module_name": "ConsumerApp",
        "producer_module_name": "ProducerKit",
        "language": "swift",
        "keep_delta_id": planned_deltas[0].delta.id,
    }
    assert session.run.await_args_list[1].kwargs == {
        "project": "contract-mini",
        "consumer_module_name": "ConsumerApp",
        "producer_module_name": "ProducerKit",
        "language": "swift",
        "keep_snapshot_ids": [
            planned[0].snapshot.id,
            planned[1].snapshot.id,
        ],
    }


@pytest.mark.asyncio
async def test_write_contract_graph_resets_stale_relationships_before_rewrite() -> None:
    session = AsyncMock()
    driver = _FakeDriver(session)
    balance_symbol = _symbol(symbol_id="sym-balance", fqn="Wallet.balance()")
    consumption = ModuleContractConsumption(
        public_symbol_id="sym-balance",
        group_id="project/test",
        commit_sha="commit-current",
        match_symbol_id=symbol_id_for("Wallet.balance()"),
        use_count=1,
        file_count=1,
        first_seen_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
        evidence_paths_sample=["ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"],
    )
    planned_snapshot = _planned_snapshot(
        commit_sha="commit-current",
        consumer_module_name="ConsumerApp",
        symbols=[balance_symbol],
        consumptions=[consumption],
    )
    planned_delta = _PlannedContractDelta(
        delta=ModuleContractDelta(
            id="delta-1",
            group_id="project/test",
            project="contract-mini",
            consumer_module_name="ConsumerApp",
            producer_module_name="ProducerKit",
            language=Language.SWIFT,
            from_commit_sha="commit-from",
            to_commit_sha="commit-current",
            removed_consumed_symbol_count=0,
            signature_changed_consumed_symbol_count=1,
            added_consumed_symbol_count=0,
            affected_use_count=1,
        ),
        affected_symbols=[
            ModuleContractAffectedSymbol(
                public_symbol_id="sym-balance",
                change_kind="signature_changed",
                affected_use_count=1,
            )
        ],
        from_snapshot_id="snapshot-from",
        to_snapshot_id=planned_snapshot.snapshot.id,
    )

    stats = await _write_contract_graph(
        driver=driver,
        planned=[planned_snapshot],
        planned_deltas=[planned_delta],
    )

    assert stats.nodes_written == 2
    assert stats.edges_written == 5
    queries = [call.args[0] for call in session.run.await_args_list]
    assert queries == [
        _DELETE_SNAPSHOT_CONSUMPTIONS,
        _DELETE_SNAPSHOT_SURFACE_LINKS,
        _WRITE_SNAPSHOT,
        _WRITE_CONSUMPTION,
        _DELETE_DELTA_AFFECTED_SYMBOLS,
        _DELETE_DELTA_SNAPSHOT_LINKS,
        _WRITE_DELTA,
        _WRITE_DELTA_AFFECTED_SYMBOL,
    ]


def test_resolve_module_owner_from_map_reports_ambiguous_match() -> None:
    mapping = ModuleOwnerMap(
        modules=[
            ModuleOwnerRoot(module_name="ConsumerApp", roots=["ConsumerApp/Sources"]),
            ModuleOwnerRoot(module_name="ConsumerShell", roots=["ConsumerApp"]),
        ]
    )

    resolution = resolve_module_owner_from_map(
        mapping, "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
    )

    assert resolution.status == "ambiguous"
    assert resolution.reason == "consumer_module_ambiguous"


@pytest.mark.asyncio
async def test_tantivy_bridge_search_occurrences_filters_commit_and_phase(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "tantivy"
    qname = "Wallet.balance()"
    symbol_id = symbol_id_for(qname)

    async with TantivyBridge(index_path) as bridge:
        await bridge.add_or_replace_async(
            occ=_make_occurrence(
                symbol_id=symbol_id,
                qname=qname,
                file_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                line=8,
                col_start=14,
                col_end=21,
                commit_sha="abc123",
            ),
            phase="phase2_user_uses",
        )
        await bridge.add_or_replace_async(
            occ=_make_occurrence(
                symbol_id=symbol_id,
                qname=qname,
                file_path="ConsumerApp/Sources/ConsumerApp/VendorFeature.swift",
                line=5,
                col_start=4,
                col_end=11,
                commit_sha="abc123",
            ),
            phase="phase3_vendor_uses",
        )
        await bridge.add_or_replace_async(
            occ=_make_occurrence(
                symbol_id=symbol_id,
                qname=qname,
                file_path="ConsumerApp/Sources/ConsumerApp/OldFeature.swift",
                line=5,
                col_start=4,
                col_end=11,
                commit_sha="def456",
            ),
            phase="phase2_user_uses",
        )

    async with TantivyBridge(index_path) as bridge:
        hits = await bridge.search_occurrences_async(
            symbol_id=symbol_id,
            commit_sha="abc123",
            phases=("phase2_user_uses",),
        )

    assert len(hits) == 1
    assert hits[0].file_path == "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
    assert hits[0].line == 8
    assert hits[0].col_start == 14
    assert hits[0].col_end is None
    assert hits[0].commit_sha == "abc123"


@pytest.mark.asyncio
async def test_load_occurrences_for_surface_bridges_swift_fqn_via_indexstore_usr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    index_path = tmp_path / "tantivy"
    commit_sha = "commitcurrent"
    usr = "s:11ProducerKit6WalletV7balanceyyF"
    qname = "ProducerKit s%3A11ProducerKit6WalletV7balanceyyF"
    symbol = _symbol(symbol_id="sym-balance", fqn="Wallet.balance()")

    async with TantivyBridge(index_path) as bridge:
        await bridge.add_or_replace_async(
            occ=_make_occurrence(
                symbol_id=symbol_id_for(qname),
                qname=qname,
                file_path="ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                line=8,
                col_start=14,
                col_end=21,
                commit_sha=commit_sha,
            ),
            phase="phase2_user_uses",
        )

    monkeypatch.setattr(
        "palace_mcp.code.indexstore.find_callers",
        lambda *args, **kwargs: [SimpleNamespace(symbol_usr=usr)],
    )

    async with TantivyBridge(index_path) as bridge:
        resolutions = await _load_occurrences_for_surface(
            bridge=bridge,
            symbols=[symbol],
            commit_sha=commit_sha,
            include_package=False,
            phases=("phase2_user_uses",),
            cache={},
            index_store_path="/tmp/indexstore",
            caller_cache={},
        )

    resolution = resolutions["sym-balance"]
    assert resolution.status == "matched"
    assert resolution.match_symbol_id == symbol_id_for(qname)
    assert len(resolution.occurrences) == 1
    assert (
        resolution.occurrences[0].file_path
        == "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift"
    )


def _make_occurrence(
    *,
    symbol_id: int,
    qname: str,
    file_path: str,
    line: int,
    col_start: int,
    col_end: int,
    commit_sha: str,
) -> object:
    from palace_mcp.extractors.foundation.models import SymbolKind, SymbolOccurrence

    return SymbolOccurrence(
        doc_key=build_symbol_occurrence_doc_key(
            symbol_id=symbol_id,
            file_path=file_path,
            line=line,
            col_start=col_start,
            commit_sha=commit_sha,
        ),
        symbol_id=symbol_id,
        symbol_qualified_name=qname,
        kind=SymbolKind.USE,
        language=Language.SWIFT,
        file_path=file_path,
        line=line,
        col_start=col_start,
        col_end=col_end,
        importance=1.0,
        commit_sha=commit_sha,
        ingest_run_id="run-1",
    )
