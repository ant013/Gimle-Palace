"""Integration tests for foundation.delta_resolution with real Neo4j."""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.delta_resolution import (
    EdgeDelta,
    EdgeSnapshot,
    PublicApiDelta,
    PublicApiSnapshot,
    ResolvedDelta,
    SeedDelta,
    SymbolDelta,
    SymbolSnapshot,
    capture_delta_resolution_baseline,
    resolve_delta_resolution,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema

_GROUP_ID = "project/delta-mini"
_PROJECT = "delta-mini"
_OLD_COMMIT = "commit-old"
_NEW_COMMIT = "commit-new"
_AFFECTED_PATHS = frozenset(
    {
        "Artifacts/FinanceKit.swiftinterface",
        "Sources/Core/Wallet.swift",
        "Sources/Legacy.swift",
        "Sources/Wallet.swift",
    }
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delta_resolution_matches_from_scratch_diff_for_two_commits(
    driver: AsyncDriver,
) -> None:
    await ensure_custom_schema(driver)

    baseline_symbols = (
        SymbolSnapshot(
            qualified_name="Wallet",
            file_path="Sources/Wallet.swift",
            module_name="FinanceKit",
            access_modifier="public",
        ),
        SymbolSnapshot(
            qualified_name="Wallet.balance()",
            file_path="Sources/Wallet.swift",
            module_name="FinanceKit",
            access_modifier="public",
        ),
        SymbolSnapshot(
            qualified_name="LegacyUtility",
            file_path="Sources/Legacy.swift",
            module_name="FinanceKit",
            access_modifier="internal",
            is_env_key=True,
        ),
    )
    baseline_edges = (
        EdgeSnapshot(
            source="Wallet.balance()",
            target="Formatter.format()",
            relationship_type="CALLS",
        ),
        EdgeSnapshot(
            source="Wallet.balance()",
            target="Money",
            relationship_type="REFERENCES",
        ),
        EdgeSnapshot(
            source="LegacyUtility",
            target="AnyBalanceProtocol",
            relationship_type="EXISTENTIAL_USE",
        ),
    )
    baseline_public_api = (
        PublicApiSnapshot(
            fqn="Wallet",
            module_name="FinanceKit",
            source_artifact_path="Artifacts/FinanceKit.swiftinterface",
            signature_hash="sig-wallet-old",
        ),
        PublicApiSnapshot(
            fqn="Wallet.balance()",
            module_name="FinanceKit",
            source_artifact_path="Artifacts/FinanceKit.swiftinterface",
            signature_hash="sig-balance-old",
        ),
        PublicApiSnapshot(
            fqn="staleExport()",
            module_name="FinanceKit",
            source_artifact_path="Artifacts/FinanceKit.swiftinterface",
            signature_hash="sig-stale-old",
        ),
    )
    await _seed_symbol_snapshot(driver, baseline_symbols, baseline_edges)
    await _seed_public_api_snapshot(
        driver,
        commit_sha=_OLD_COMMIT,
        symbols=baseline_public_api,
    )

    baseline = await capture_delta_resolution_baseline(
        driver,
        group_id=_GROUP_ID,
        project=_PROJECT,
        previous_commit_sha=_OLD_COMMIT,
        changed_paths=set(_AFFECTED_PATHS - {"Sources/Legacy.swift"}),
        removed_paths={"Sources/Legacy.swift"},
    )

    current_symbols = (
        SymbolSnapshot(
            qualified_name="Wallet",
            file_path="Sources/Core/Wallet.swift",
            module_name="CoreKit",
            access_modifier="public",
        ),
        SymbolSnapshot(
            qualified_name="Wallet.balance()",
            file_path="Sources/Core/Wallet.swift",
            module_name="CoreKit",
            access_modifier="internal",
        ),
        SymbolSnapshot(
            qualified_name="Wallet.owner()",
            file_path="Sources/Core/Wallet.swift",
            module_name="CoreKit",
            access_modifier="internal",
        ),
    )
    current_edges = (
        EdgeSnapshot(
            source="Wallet.balance()",
            target="Currency",
            relationship_type="REFERENCES",
        ),
        EdgeSnapshot(
            source="Wallet.owner()",
            target="Wallet",
            relationship_type="EXTENDS",
        ),
    )
    current_public_api = (
        PublicApiSnapshot(
            fqn="Wallet",
            module_name="FinanceKit",
            source_artifact_path="Artifacts/FinanceKit.swiftinterface",
            signature_hash="sig-wallet-new",
        ),
        PublicApiSnapshot(
            fqn="Wallet.balance()",
            module_name="FinanceKit",
            source_artifact_path="Artifacts/FinanceKit.swiftinterface",
            signature_hash="sig-balance-old",
        ),
        PublicApiSnapshot(
            fqn="Wallet.owner()",
            module_name="FinanceKit",
            source_artifact_path="Artifacts/FinanceKit.swiftinterface",
            signature_hash="sig-owner-new",
        ),
    )

    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    await ensure_custom_schema(driver)
    await _seed_symbol_snapshot(driver, current_symbols, current_edges)
    await _seed_public_api_snapshot(
        driver,
        commit_sha=_NEW_COMMIT,
        symbols=current_public_api,
    )

    resolved = await resolve_delta_resolution(
        driver,
        baseline=baseline,
        current_commit_sha=_NEW_COMMIT,
    )

    expected = ResolvedDelta(
        symbol_deltas=(
            SymbolDelta(
                qualified_name="Wallet.owner()",
                change_kind="added",
                current_file_path="Sources/Core/Wallet.swift",
                current_module_name="CoreKit",
            ),
            SymbolDelta(
                qualified_name="Wallet",
                change_kind="moved",
                previous_file_path="Sources/Wallet.swift",
                current_file_path="Sources/Core/Wallet.swift",
                previous_module_name="FinanceKit",
                current_module_name="CoreKit",
            ),
            SymbolDelta(
                qualified_name="Wallet.balance()",
                change_kind="moved",
                previous_file_path="Sources/Wallet.swift",
                current_file_path="Sources/Core/Wallet.swift",
                previous_module_name="FinanceKit",
                current_module_name="CoreKit",
            ),
            SymbolDelta(
                qualified_name="LegacyUtility",
                change_kind="removed",
                previous_file_path="Sources/Legacy.swift",
                previous_module_name="FinanceKit",
            ),
        ),
        edge_deltas=(
            EdgeDelta(
                source="Wallet.owner()",
                target="Wallet",
                relationship_type="EXTENDS",
                change_kind="added",
            ),
        ),
        seed_deltas=(
            SeedDelta(
                qualified_name="Wallet.balance()",
                previous_is_seed=True,
                current_is_seed=False,
            ),
        ),
        public_api_deltas=(
            PublicApiDelta(
                fqn="Wallet.owner()",
                module_name="FinanceKit",
                source_artifact_path="Artifacts/FinanceKit.swiftinterface",
                change_kind="added",
                current_signature_hash="sig-owner-new",
            ),
            PublicApiDelta(
                fqn="staleExport()",
                module_name="FinanceKit",
                source_artifact_path="Artifacts/FinanceKit.swiftinterface",
                change_kind="removed",
                previous_signature_hash="sig-stale-old",
            ),
            PublicApiDelta(
                fqn="Wallet",
                module_name="FinanceKit",
                source_artifact_path="Artifacts/FinanceKit.swiftinterface",
                change_kind="signature_changed",
                previous_signature_hash="sig-wallet-old",
                current_signature_hash="sig-wallet-new",
            ),
        ),
    )

    assert resolved == expected


async def _seed_symbol_snapshot(
    driver: AsyncDriver,
    symbols: Iterable[SymbolSnapshot],
    edges: Iterable[EdgeSnapshot],
) -> None:
    async with driver.session() as session:
        for symbol in symbols:
            await session.run(
                """
                MERGE (s:Symbol {group_id: $group_id, qualified_name: $qualified_name})
                SET s.file_path = $file_path,
                    s.module_name = $module_name,
                    s.access_modifier = $access_modifier,
                    s.is_main_entry = $is_main_entry,
                    s.is_iboutlet = $is_iboutlet,
                    s.is_ibaction = $is_ibaction,
                    s.is_objc_members = $is_objc_members,
                    s.is_ns_managed = $is_ns_managed,
                    s.is_property_wrapper = $is_property_wrapper,
                    s.is_codable = $is_codable,
                    s.is_swift_app_storage = $is_swift_app_storage,
                    s.is_env_key = $is_env_key,
                    s.deleted_at = null
                REMOVE s:Deprecated
                """,
                group_id=_GROUP_ID,
                qualified_name=symbol.qualified_name,
                file_path=symbol.file_path,
                module_name=symbol.module_name,
                access_modifier=symbol.access_modifier,
                is_main_entry=symbol.is_main_entry,
                is_iboutlet=symbol.is_iboutlet,
                is_ibaction=symbol.is_ibaction,
                is_objc_members=symbol.is_objc_members,
                is_ns_managed=symbol.is_ns_managed,
                is_property_wrapper=symbol.is_property_wrapper,
                is_codable=symbol.is_codable,
                is_swift_app_storage=symbol.is_swift_app_storage,
                is_env_key=symbol.is_env_key,
            )
        for edge in edges:
            await session.run(
                f"""
                MATCH (source:Symbol {{group_id: $group_id, qualified_name: $source}})
                MATCH (target:Symbol {{group_id: $group_id, qualified_name: $target}})
                MERGE (source)-[:{edge.relationship_type}]->(target)
                """,
                group_id=_GROUP_ID,
                source=edge.source,
                target=edge.target,
            )


async def _seed_public_api_snapshot(
    driver: AsyncDriver,
    *,
    commit_sha: str,
    symbols: Iterable[PublicApiSnapshot],
) -> None:
    async with driver.session() as session:
        for index, symbol in enumerate(symbols, start=1):
            surface_id = f"surface-{commit_sha}"
            await session.run(
                """
                MERGE (surface:PublicApiSurface {id: $surface_id})
                SET surface.group_id = $group_id,
                    surface.project = $project,
                    surface.module_name = $module_name,
                    surface.language = 'swift',
                    surface.commit_sha = $commit_sha,
                    surface.artifact_path = $artifact_path
                """,
                surface_id=surface_id,
                group_id=_GROUP_ID,
                project=_PROJECT,
                module_name=symbol.module_name,
                commit_sha=commit_sha,
                artifact_path=symbol.source_artifact_path,
            )
            await session.run(
                """
                MATCH (surface:PublicApiSurface {id: $surface_id})
                MERGE (symbol:PublicApiSymbol {id: $symbol_id})
                SET symbol.project = $project,
                    symbol.group_id = $group_id,
                    symbol.commit_sha = $commit_sha,
                    symbol.module_name = $module_name,
                    symbol.fqn = $fqn,
                    symbol.source_artifact_path = $artifact_path,
                    symbol.signature_hash = $signature_hash
                MERGE (surface)-[:EXPORTS]->(symbol)
                """,
                surface_id=surface_id,
                symbol_id=f"{commit_sha}-{index}",
                project=_PROJECT,
                group_id=_GROUP_ID,
                commit_sha=commit_sha,
                module_name=symbol.module_name,
                fqn=symbol.fqn,
                artifact_path=symbol.source_artifact_path,
                signature_hash=symbol.signature_hash,
            )
