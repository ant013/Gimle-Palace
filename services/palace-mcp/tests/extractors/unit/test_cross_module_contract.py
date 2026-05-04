"""Unit tests for the cross_module_contract extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.extractors.cross_module_contract import (
    build_contract_delta,
    plan_contract_snapshots,
)
from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    Language,
    ModuleContractConsumption,
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
    return PublicApiSurface(
        id="surface-1",
        group_id="project/test",
        project="contract-mini",
        module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha="commit-current",
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
) -> PublicApiSymbol:
    return PublicApiSymbol(
        id=symbol_id,
        group_id="project/test",
        project="contract-mini",
        module_name="ProducerKit",
        language=Language.SWIFT,
        commit_sha="commit-current",
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
        symbol_id_for("Wallet.balance()"): [
            _occurrence(
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                "Wallet.balance()",
            ),
            _occurrence(
                "ProducerKit/Sources/ProducerKit/InternalUse.swift", "Wallet.balance()"
            ),
            _occurrence(
                "UnknownFeature/Sources/UnknownFeature/Loose.swift", "Wallet.balance()"
            ),
        ],
        symbol_id_for("packageHelper()"): [
            _occurrence(
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift", "packageHelper()"
            )
        ],
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
        symbol_id_for("Wallet.balance()"): [
            _occurrence(
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift",
                "Wallet.balance()",
            )
        ],
        symbol_id_for("packageHelper()"): [
            _occurrence(
                "ConsumerApp/Sources/ConsumerApp/WalletFeature.swift", "packageHelper()"
            )
        ],
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
