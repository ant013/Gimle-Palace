"""Unit tests for SymbolIndexSwift extractor (mocked driver + bridge)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.symbol_index_swift import (
    SymbolIndexSwift,
    _is_vendor,
    _read_head_sha,
)
from tests.extractors.fixtures.scip_factory import (
    build_minimal_scip_index,
    write_scip_fixture,
)


@pytest.fixture
def extractor() -> SymbolIndexSwift:
    return SymbolIndexSwift()


@pytest.fixture
def run_ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="test-project",
        group_id="project/test-project",
        repo_path=tmp_path,
        run_id="test-run-swift-001",
        duration_ms=0,
        logger=MagicMock(),
    )


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    index = build_minimal_scip_index(
        language="swift",
        relative_path="Sources/UwMini/Wallet.swift",
        symbols=[
            ("scip-swift apple UwMini . s%3A6UwMini6WalletV", 1),
            ("scip-swift apple UwMini . s%3A6UwMini6WalletV7balanceSivp", 1),
            ("scip-swift apple UwMini . s%3A6UwMini6WalletV7balanceSivp", 0),
        ],
    )
    return write_scip_fixture(index, tmp_path / "test.scip")


def _make_driver() -> MagicMock:
    inner_session = AsyncMock()
    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=None)
    inner_session.run = AsyncMock(return_value=result_mock)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=inner_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session.return_value = session_cm
    return driver


class TestSymbolIndexSwiftMeta:
    def test_name_is_correct(self, extractor: SymbolIndexSwift) -> None:
        assert extractor.name == "symbol_index_swift"

    def test_description_mentions_swift(self, extractor: SymbolIndexSwift) -> None:
        desc = extractor.description.lower()
        assert "swift" in desc

    def test_primary_lang_is_swift(self, extractor: SymbolIndexSwift) -> None:
        assert extractor.primary_lang == Language.SWIFT

    def test_read_head_sha_from_git_worktree_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        git_dir = tmp_path / "gitdir"
        refs_heads = git_dir / "refs" / "heads"
        refs_heads.mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        expected_sha = "1234567890abcdef1234567890abcdef12345678"
        (refs_heads / "main").write_text(f"{expected_sha}\n")
        (repo_path / ".git").write_text(f"gitdir: {git_dir}\n")

        assert _read_head_sha(repo_path) == expected_sha

    def test_read_head_sha_from_packed_refs(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        git_dir = repo_path / ".git"
        refs_heads = git_dir / "refs" / "heads"
        refs_heads.mkdir(parents=True)
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        expected_sha = "abcdef1234567890abcdef1234567890abcdef12"
        (git_dir / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted\n"
            f"{expected_sha} refs/heads/main\n"
        )

        assert _read_head_sha(repo_path) == expected_sha

    @pytest.mark.parametrize(
        ("file_path", "expected"),
        [
            ("Sources/UwMini/Wallet.swift", False),
            ("Pods/Alamofire/Source/Session.swift", True),
            ("Carthage/Checkouts/Foo/Sources/Foo.swift", True),
            ("SourcePackages/checkouts/Foo/Sources/Foo.swift", True),
            (".build/checkouts/Foo/Sources/Foo.swift", True),
            (".swiftpm/x/Foo.swift", True),
            ("DerivedData/App/Foo.swift", True),
        ],
    )
    def test_vendor_path_detection(self, file_path: str, expected: bool) -> None:
        assert _is_vendor(file_path) is expected


class TestSymbolIndexSwiftErrorHandling:
    @pytest.mark.asyncio
    async def test_missing_scip_path_raises_extractor_error(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        driver = _make_driver()
        graphiti = AsyncMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch(
                "palace_mcp.extractors.symbol_index_swift.ensure_custom_schema",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.create_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.finalize_ingest_run",
                AsyncMock(),
            ),
        ):
            with pytest.raises(ExtractorError) as exc_info:
                await extractor.run(graphiti=graphiti, ctx=run_ctx)
            assert exc_info.value.error_code == ExtractorErrorCode.SCIP_PATH_REQUIRED

    @pytest.mark.asyncio
    async def test_scip_file_not_found_raises(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-project": "/nonexistent/path.scip"}
        settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        driver = _make_driver()
        graphiti = AsyncMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch(
                "palace_mcp.extractors.symbol_index_swift.ensure_custom_schema",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.create_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.finalize_ingest_run",
                AsyncMock(),
            ),
        ):
            with pytest.raises(FileNotFoundError):
                await extractor.run(graphiti=graphiti, ctx=run_ctx)


class TestSymbolIndexSwiftHappyPath:
    @pytest.mark.asyncio
    async def test_run_reads_scip_path_from_settings(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
    ) -> None:
        driver = _make_driver()
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {"test-project": str(scip_fixture)}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.05
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        bridge_mock = AsyncMock()
        bridge_mock.__aenter__ = AsyncMock(return_value=bridge_mock)
        bridge_mock.__aexit__ = AsyncMock(return_value=False)
        bridge_mock.add_or_replace_async = AsyncMock()
        bridge_mock.commit_async = AsyncMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch(
                "palace_mcp.extractors.symbol_index_swift.TantivyBridge",
                return_value=bridge_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.ensure_custom_schema",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.create_ingest_run",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.write_checkpoint",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.finalize_ingest_run",
                new_callable=AsyncMock,
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert stats.nodes_written >= 1
