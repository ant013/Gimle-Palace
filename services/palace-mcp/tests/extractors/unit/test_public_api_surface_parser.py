"""Unit tests for the public_api_surface artifact parser."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.public_api_surface import (
    discover_public_api_artifacts,
    parse_kotlin_api_dump,
    parse_swift_interface,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "public-api-surface-mini-project"
)


class TestArtifactDiscovery:
    def test_discovers_kotlin_and_swift_artifacts(self) -> None:
        artifacts = discover_public_api_artifacts(FIXTURE_ROOT)

        assert [artifact.module_name for artifact in artifacts] == [
            "UwMiniCore",
            "UwMiniKit",
        ]
        assert [artifact.language for artifact in artifacts] == [
            Language.KOTLIN,
            Language.SWIFT,
        ]


class TestKotlinApiDumpParser:
    def test_parses_public_and_protected_symbols(self) -> None:
        artifact = discover_public_api_artifacts(FIXTURE_ROOT)[0]
        surface, symbols = parse_kotlin_api_dump(
            project="public-api-mini",
            group_id="project/public-api-mini",
            artifact=artifact,
            commit_sha="cafebabecafebabecafebabecafebabecafebabe",
        )

        assert surface.module_name == "UwMiniCore"
        assert surface.language == Language.KOTLIN
        assert surface.tool_name == "kotlin-bcv"
        assert surface.tool_version == "0.18.1"

        fqns = {symbol.fqn: symbol for symbol in symbols}
        assert "com.example.wallet.Wallet" in fqns
        assert "com.example.wallet.Wallet.init(kotlin.String)" in fqns
        assert "com.example.wallet.Wallet.displayName()" in fqns
        assert "com.example.wallet.Wallet.ownerName" in fqns
        assert "com.example.wallet.Wallet.forSubclass(kotlin.Int)" in fqns
        assert "com.example.wallet.BaseWallet.inheritedHook()" in fqns
        assert "com.example.wallet.WalletApiKt.makeWallet(kotlin.String)" in fqns
        assert "com.example.wallet.Wallet.hiddenInternal()" not in fqns
        assert "com.example.wallet.Wallet.hiddenPrivate()" not in fqns
        assert (
            fqns["com.example.wallet.Wallet.forSubclass(kotlin.Int)"].visibility.value
            == "protected"
        )

    def test_stable_ids_are_deterministic(self) -> None:
        artifact = discover_public_api_artifacts(FIXTURE_ROOT)[0]
        first_surface, first_symbols = parse_kotlin_api_dump(
            project="public-api-mini",
            group_id="project/public-api-mini",
            artifact=artifact,
            commit_sha="cafebabecafebabecafebabecafebabecafebabe",
        )
        second_surface, second_symbols = parse_kotlin_api_dump(
            project="public-api-mini",
            group_id="project/public-api-mini",
            artifact=artifact,
            commit_sha="cafebabecafebabecafebabecafebabecafebabe",
        )

        assert first_surface.id == second_surface.id
        assert [symbol.id for symbol in first_symbols] == [
            symbol.id for symbol in second_symbols
        ]
        assert [symbol.signature_hash for symbol in first_symbols] == [
            symbol.signature_hash for symbol in second_symbols
        ]


class TestSwiftInterfaceParser:
    def test_preserves_package_visibility_and_filters_internal_private(self) -> None:
        artifact = discover_public_api_artifacts(FIXTURE_ROOT)[1]
        surface, symbols = parse_swift_interface(
            project="public-api-mini",
            group_id="project/public-api-mini",
            artifact=artifact,
            commit_sha="cafebabecafebabecafebabecafebabecafebabe",
        )

        assert surface.module_name == "UwMiniKit"
        assert surface.language == Language.SWIFT
        assert surface.tool_name == "swiftc"
        assert surface.tool_version.startswith("Apple Swift version 6.2.4")

        fqns = {symbol.fqn: symbol for symbol in symbols}
        assert "Wallet" in fqns
        assert "Wallet.init(id: Swift.String)" in fqns
        assert "Wallet.id" in fqns
        assert "Wallet.balance()" in fqns
        assert "Syncable" in fqns
        assert "Syncable.sync()" in fqns
        assert "packageHelper()" in fqns
        assert "WalletID" in fqns
        assert "Wallet.extension" in fqns
        assert "Wallet.formatted()" in fqns
        assert "Wallet.hiddenInternal()" not in fqns
        assert "Wallet.hiddenPrivate" not in fqns
        assert fqns["packageHelper()"].visibility.value == "package"
