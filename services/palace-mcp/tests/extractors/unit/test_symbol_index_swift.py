"""Unit tests for SymbolIndexSwift extractor (mocked driver + bridge)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift, _is_vendor
from tests.extractors.fixtures.scip_factory import (
    build_swift_scip_index,
    write_scip_fixture,
)


@pytest.fixture
def extractor() -> SymbolIndexSwift:
    return SymbolIndexSwift()


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    index = build_swift_scip_index()
    return write_scip_fixture(index, tmp_path / "test.scip")


@pytest.fixture
def run_ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="uw-ios-mini",
        group_id="project/uw-ios-mini",
        repo_path=tmp_path,
        run_id="test-run-swift-001",
        duration_ms=0,
        logger=MagicMock(),
    )


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
        assert "swift" in extractor.description.lower()

    def test_primary_lang_is_swift(self, extractor: SymbolIndexSwift) -> None:
        assert extractor.primary_lang == Language.SWIFT


class TestSymbolIndexSwiftVendorClassification:
    @pytest.mark.parametrize(
        ("file_path", "expected"),
        [
            ("Pods/Foo/Foo.swift", True),
            ("Carthage/Checkouts/Foo/Foo.swift", True),
            ("SourcePackages/checkouts/Foo/Foo.swift", True),
            (".build/checkouts/Foo/Foo.swift", True),
            (".swiftpm/xcode/package.xcworkspace", True),
            ("DerivedData/Foo/Build/Products/A.swift", True),
            ("Sources/UwMiniApp/ContentView.swift", False),
            ("Sources/UwMiniCore/State/WalletStore.swift", False),
        ],
    )
    def test_vendor_paths_match_expected(self, file_path: str, expected: bool) -> None:
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
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=_make_driver()),
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
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)
        assert exc_info.value.error_code == ExtractorErrorCode.SCIP_PATH_REQUIRED

    @pytest.mark.asyncio
    async def test_scip_file_not_found_raises(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": "/nonexistent/path.scip"}
        settings.palace_tantivy_index_path = str(tmp_path / "tantivy")
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=_make_driver()),
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
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)


class TestSymbolIndexSwiftHappyPath:
    @pytest.mark.asyncio
    async def test_run_reads_scip_path_from_settings(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
    ) -> None:
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_fixture)}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 100
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        bridge_mock = AsyncMock()
        bridge_mock.__aenter__ = AsyncMock(return_value=bridge_mock)
        bridge_mock.__aexit__ = AsyncMock(return_value=False)
        bridge_mock.add_or_replace_async = AsyncMock()
        bridge_mock.commit_async = AsyncMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=_make_driver()),
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
                "palace_mcp.extractors.symbol_index_swift._get_previous_error_code",
                new_callable=AsyncMock,
                return_value=None,
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

        assert stats.nodes_written >= 3

    @pytest.mark.asyncio
    async def test_runner_path_executes_registered_swift_extractor(
        self,
        scip_fixture: Path,
        tmp_path: Path,
    ) -> None:
        repos_root = tmp_path / "repos"
        repo = repos_root / "uw-ios-mini"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n")

        result_mock = AsyncMock()
        result_mock.single = AsyncMock(return_value={"p": {"slug": "uw-ios-mini"}})

        session = AsyncMock()
        session.run = AsyncMock(return_value=result_mock)
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        driver = MagicMock()
        driver.session.return_value = session_cm

        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_fixture)}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch("palace_mcp.extractors.runner.REPOS_ROOT", repos_root),
            patch(
                "palace_mcp.extractors.symbol_index_swift.ensure_custom_schema",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._get_previous_error_code",
                new_callable=AsyncMock,
                return_value=None,
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
            res = await run_extractor(
                name="symbol_index_swift",
                project="uw-ios-mini",
                driver=driver,
                graphiti=MagicMock(),
            )

        assert res["ok"] is True
        assert res["extractor"] == "symbol_index_swift"
        assert res["project"] == "uw-ios-mini"
        assert res["success"] is True
        assert res["nodes_written"] >= 3
