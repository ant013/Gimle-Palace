"""Unit tests for the public_api_surface artifact parser."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.foundation.models import Language, PublicApiVisibility
from palace_mcp.extractors.public_api_surface import (
    _read_head_sha,
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
        assert "com.example.wallet.Wallet.Listener" in fqns
        assert "com.example.wallet.Wallet.Listener.onSynced()" in fqns
        assert "com.example.wallet.Wallet.Nested" in fqns
        assert "com.example.wallet.Wallet.Nested.init()" in fqns
        assert "com.example.wallet.Wallet.Nested.nestedCall()" in fqns
        assert "com.example.wallet.Wallet.Companion" in fqns
        assert "com.example.wallet.Wallet.Companion.fromCache(kotlin.String)" in fqns
        assert "com.example.wallet.Wallet.hiddenInternal()" not in fqns
        assert "com.example.wallet.Wallet.hiddenPrivate()" not in fqns
        assert (
            fqns["com.example.wallet.Wallet.forSubclass(kotlin.Int)"].visibility.value
            == "protected"
        )
        assert fqns["com.example.wallet.Wallet.Listener"].kind.value == "interface"

    def test_does_not_guess_published_api_internal_from_plain_bcv_lines(self) -> None:
        artifact = discover_public_api_artifacts(FIXTURE_ROOT)[0]
        _, symbols = parse_kotlin_api_dump(
            project="public-api-mini",
            group_id="project/public-api-mini",
            artifact=artifact,
            commit_sha="cafebabecafebabecafebabecafebabecafebabe",
        )

        fqns = {symbol.fqn: symbol for symbol in symbols}
        assert "com.example.wallet.PublishedApiBridge" in fqns
        assert (
            "com.example.wallet.PublishedApiBridge.publishedBridge(kotlin.String)"
            in fqns
        )
        assert (
            fqns["com.example.wallet.PublishedApiBridge"].visibility
            is PublicApiVisibility.PUBLIC
        )
        assert (
            fqns[
                "com.example.wallet.PublishedApiBridge.publishedBridge(kotlin.String)"
            ].visibility
            is PublicApiVisibility.PUBLIC
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
        assert "WalletController" in fqns
        assert "WalletController.init(wallet: Wallet)" in fqns
        assert "WalletController.refresh()" in fqns
        assert "WalletState" in fqns
        assert "Syncable" in fqns
        assert "Syncable.sync()" in fqns
        assert "packageHelper()" in fqns
        assert "WalletID" in fqns
        assert "Wallet.extension" in fqns
        assert "Wallet.formatted()" in fqns
        assert "Wallet.hiddenInternal()" not in fqns
        assert "Wallet.hiddenPrivate" not in fqns
        assert fqns["packageHelper()"].visibility.value == "package"
        assert fqns["WalletController"].visibility is PublicApiVisibility.OPEN
        assert fqns["WalletController.refresh()"].visibility is PublicApiVisibility.OPEN
        assert fqns["WalletState"].kind.value == "enum"


class TestReadHeadSha:
    def test_reads_packed_ref_in_standard_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        git_dir = repo / ".git"
        git_dir.mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (git_dir / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted\n"
            "bbc88bba86a494dcfa9b5194a1e2464db56caa3d refs/heads/main\n",
            encoding="utf-8",
        )

        assert _read_head_sha(repo) == "bbc88bba86a494dcfa9b5194a1e2464db56caa3d"

    def test_reads_packed_ref_via_worktree_common_dir(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        worktree_git = tmp_path / "git-meta" / "worktrees" / "gim190"
        common_git = tmp_path / "git-meta"
        repo.mkdir()
        worktree_git.mkdir(parents=True)
        common_git.mkdir(parents=True, exist_ok=True)

        (repo / ".git").write_text(
            f"gitdir: {worktree_git.as_posix()}\n", encoding="utf-8"
        )
        (worktree_git / "HEAD").write_text(
            "ref: refs/heads/feature/GIM-190-public-api-surface-extractor\n",
            encoding="utf-8",
        )
        (worktree_git / "commondir").write_text("../..\n", encoding="utf-8")
        (common_git / "packed-refs").write_text(
            "093c1ebf66662b01be30ad4a82d20a9ac8709104 "
            "refs/heads/feature/GIM-190-public-api-surface-extractor\n",
            encoding="utf-8",
        )

        assert _read_head_sha(repo) == "093c1ebf66662b01be30ad4a82d20a9ac8709104"
