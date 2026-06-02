"""Unit tests for SymbolIndexSwift extractor (mocked driver + bridge)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
)
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.foundation.symbol_node_writer import build_symbol_node_rows
from palace_mcp.extractors.scip_parser import ScipSymbolInfo
from palace_mcp.extractors.symbol_index_swift import (
    SymbolIndexSwift,
    _build_shadow_rows,
    _ingest_batch,
    _is_vendor,
)
from tests.extractors.fixtures.scip_factory import (
    build_swift_scip_index_with_symbol_infos,
    write_scip_fixture,
)


@pytest.fixture
def extractor() -> SymbolIndexSwift:
    return SymbolIndexSwift()


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    # Use the fixture with SymbolInformation so write_symbol_nodes is exercised
    # and nodes_written reflects actual Neo4j :Symbol count (3 symbols).
    index = build_swift_scip_index_with_symbol_infos()
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

    @pytest.mark.asyncio
    async def test_ctx_scip_path_override_bypasses_settings_lookup(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
    ) -> None:
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 50
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        override_ctx = ExtractorRunContext(
            project_slug=run_ctx.project_slug,
            group_id=run_ctx.group_id,
            repo_path=run_ctx.repo_path,
            run_id=run_ctx.run_id,
            duration_ms=run_ctx.duration_ms,
            logger=run_ctx.logger,
            scip_path=scip_fixture,
        )

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
            stats = await extractor.run(graphiti=MagicMock(), ctx=override_ctx)

        assert stats.nodes_written >= 3


class TestSymbolIndexSwiftHappyPath:
    @pytest.mark.asyncio
    async def test_ingest_batch_commits_and_logs_progress(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        occurrences = [
            SymbolOccurrence(
                doc_key=f"{idx}:Sources/App/File.swift:{idx}:0:abc123",
                symbol_id=idx,
                symbol_qualified_name=f"App.Symbol{idx}",
                kind=SymbolKind.USE,
                language=Language.SWIFT,
                file_path="Sources/App/File.swift",
                line=idx,
                col_start=0,
                col_end=1,
                importance=1.0,
                commit_sha="abc123",
                ingest_run_id="run-1",
            )
            for idx in range(5)
        ]
        bridge = AsyncMock()
        caplog.set_level(
            logging.INFO, logger="palace_mcp.extractors.symbol_index_swift"
        )

        written = await _ingest_batch(
            bridge, occurrences, "phase2_user_uses", progress_interval=2
        )

        assert written == 5
        assert bridge.add_or_replace_async.await_count == 5
        assert bridge.commit_async.await_count == 2
        assert "phase2_user_uses progress: 2/5 written" in caplog.text
        assert "phase2_user_uses progress: 4/5 written" in caplog.text

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
    async def test_run_streams_occurrences_without_materializing_lists(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(tmp_path / "test.scip")}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 100
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.5
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        occurrences = [
            SymbolOccurrence(
                doc_key="1:Sources/App/File.swift:1:0:abc123",
                symbol_id=1,
                symbol_qualified_name="App.Def",
                kind=SymbolKind.DEF,
                language=Language.SWIFT,
                file_path="Sources/App/File.swift",
                line=1,
                col_start=0,
                col_end=1,
                importance=0.0,
                commit_sha="abc123",
                ingest_run_id=run_ctx.run_id,
            ),
            SymbolOccurrence(
                doc_key="2:Sources/App/File.swift:2:0:abc123",
                symbol_id=2,
                symbol_qualified_name="App.Use",
                kind=SymbolKind.USE,
                language=Language.SWIFT,
                file_path="Sources/App/File.swift",
                line=2,
                col_start=0,
                col_end=1,
                importance=0.0,
                commit_sha="abc123",
                ingest_run_id=run_ctx.run_id,
            ),
            SymbolOccurrence(
                doc_key="3:Pods/Vendor/File.swift:3:0:abc123",
                symbol_id=3,
                symbol_qualified_name="Vendor.Use",
                kind=SymbolKind.USE,
                language=Language.SWIFT,
                file_path="Pods/Vendor/File.swift",
                line=3,
                col_start=0,
                col_end=1,
                importance=0.0,
                commit_sha="abc123",
                ingest_run_id=run_ctx.run_id,
            ),
        ]

        bridge_mock = AsyncMock()
        bridge_mock.__aenter__ = AsyncMock(return_value=bridge_mock)
        bridge_mock.__aexit__ = AsyncMock(return_value=False)
        bridge_mock.commit_async = AsyncMock()

        async def ingest_batch(
            _bridge: AsyncMock,
            batch: object,
            phase: str,
            *,
            progress_interval: int = 10_000,
        ) -> int:
            assert progress_interval == 10_000
            if phase != "phase1_defs":
                assert not isinstance(batch, list)
            return sum(1 for _ in batch)

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
            patch(
                "palace_mcp.extractors.symbol_index_swift.parse_scip_file",
                return_value=MagicMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.iter_scip_occurrences",
                side_effect=lambda *args, **kwargs: iter(occurrences),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_head_sha",
                return_value="abc123",
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._with_importance",
                side_effect=lambda occ, *_: SymbolOccurrence(
                    doc_key=occ.doc_key,
                    symbol_id=occ.symbol_id,
                    symbol_qualified_name=occ.symbol_qualified_name,
                    kind=occ.kind,
                    language=occ.language,
                    file_path=occ.file_path,
                    line=occ.line,
                    col_start=occ.col_start,
                    col_end=occ.col_end,
                    importance=0.8 if "Pods/" not in occ.file_path else 0.3,
                    commit_sha=occ.commit_sha,
                    ingest_run_id=occ.ingest_run_id,
                ),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._ingest_batch",
                new=AsyncMock(side_effect=ingest_batch),
            ) as ingest_batch_mock,
            patch(
                "palace_mcp.extractors.symbol_index_swift.list",
                side_effect=AssertionError(
                    "run() must not materialize iter_scip_occurrences with list()"
                ),
                create=True,
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        # nodes_written = Neo4j :Symbol count; mock SCIP has no SymbolInformation
        assert stats.nodes_written == 0
        assert ingest_batch_mock.await_count == 3

    @pytest.mark.asyncio
    async def test_run_clears_stale_tantivy_writer_lock_during_counter_recovery(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
    ) -> None:
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        (tantivy_dir / "in_degree_counter.json").write_text(
            "not-json{{{", encoding="utf-8"
        )
        writer_lock_path = tantivy_dir / ".tantivy-writer.lock"
        writer_lock_path.write_bytes(b"")
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
        assert not writer_lock_path.exists()
        assert bridge_mock.add_or_replace_async.await_count > 0

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
        (repo / ".git" / "HEAD").write_text(
            "0123456789abcdef0123456789abcdef01234567\n"
        )

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


class TestSymbolIndexSwiftSourceScope:
    """Verify source_scope tagging of :Symbol nodes written by write_symbol_nodes.

    GIM-1074: without a recipe, app source paths must be tagged 'project',
    not 'dependency'. Uses build_symbol_node_rows directly (no Neo4j needed).
    """

    _GROUP = "project/uw-ios-app"

    def _sym(self, qname: str) -> ScipSymbolInfo:
        return ScipSymbolInfo(
            qualified_name=qname,
            module_name="UwIosApp",
            scip_kind_name="Class",
            relationships=(),
        )

    @pytest.mark.parametrize(
        ("file_path", "expected_scope"),
        [
            # App source — should be project
            ("Unstoppable/Services/BalanceService.swift", "project"),
            ("MoneroAdapter/Sources/MoneroAdapter/MoneroKit.swift", "project"),
            ("Sources/UwMiniCore/State/WalletStore.swift", "project"),
            # External dependencies — should be dependency
            ("SourcePackages/checkouts/SomeLib/Sources/Foo.swift", "dependency"),
            ("Pods/Alamofire/Source/Alamofire.swift", "dependency"),
            ("Carthage/Checkouts/Nimble/Sources/Nimble.swift", "dependency"),
            (".build/checkouts/swift-collections/Sources/Deque.swift", "dependency"),
            # Generated sources — should be generated
            ("DerivedSources/R.generated.swift", "generated"),
        ],
    )
    def test_source_scope_no_recipe(self, file_path: str, expected_scope: str) -> None:
        sym = self._sym("App.Symbol")
        rows = build_symbol_node_rows(
            [sym],
            {sym.qualified_name: file_path},
            self._GROUP,
            recipe=None,
        )
        assert rows[0]["source_scope"] == expected_scope, (
            f"{file_path!r} got {rows[0]['source_scope']!r}, expected {expected_scope!r}"
        )


class TestSymbolIndexSwiftShadowRows:
    def test_build_shadow_rows_emits_non_callable_definitions(self) -> None:
        seen_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        rows = _build_shadow_rows(
            occurrences=[
                SymbolOccurrence(
                    doc_key="101:Sources/UwMiniCore/Models/BalanceData.swift:1:0:abc123",
                    symbol_id=101,
                    symbol_qualified_name="UwMiniCore BalanceData",
                    kind=SymbolKind.DEF,
                    language=Language.SWIFT,
                    file_path="Sources/UwMiniCore/Models/BalanceData.swift",
                    line=1,
                    col_start=0,
                    col_end=11,
                    importance=0.0,
                    commit_sha="abc123",
                    ingest_run_id="run-1",
                ),
                SymbolOccurrence(
                    doc_key="101:Sources/UwMiniApp/ContentView.swift:2:4:abc123",
                    symbol_id=101,
                    symbol_qualified_name="UwMiniCore BalanceData",
                    kind=SymbolKind.USE,
                    language=Language.SWIFT,
                    file_path="Sources/UwMiniApp/ContentView.swift",
                    line=2,
                    col_start=4,
                    col_end=15,
                    importance=0.3,
                    commit_sha="abc123",
                    ingest_run_id="run-1",
                ),
                SymbolOccurrence(
                    doc_key="103:Sources/UwMiniApp/ContentView.swift:1:0:abc123",
                    symbol_id=103,
                    symbol_qualified_name="UwMiniApp renderBalanceData",
                    kind=SymbolKind.DEF,
                    language=Language.SWIFT,
                    file_path="Sources/UwMiniApp/ContentView.swift",
                    line=1,
                    col_start=0,
                    col_end=10,
                    importance=0.0,
                    commit_sha="abc123",
                    ingest_run_id="run-1",
                ),
            ],
            symbol_infos=[
                ScipSymbolInfo(
                    qualified_name="UwMiniCore BalanceData",
                    scip_kind_name="Struct",
                    module_name="UwMiniCore",
                    relationships=(),
                ),
                ScipSymbolInfo(
                    qualified_name="UwMiniApp renderBalanceData",
                    scip_kind_name="Function",
                    module_name="UwMiniApp",
                    relationships=(("UwMiniCore BalanceData", "REFERENCES"),),
                ),
            ],
            group_id="project/uw-ios-mini",
            seen_at=seen_at,
        )

        assert rows == [
            {
                "symbol_id": 101,
                "symbol_qualified_name": "UwMiniCore BalanceData",
                "group_id": "project/uw-ios-mini",
                "language": "swift",
                "importance": 1.0,
                "kind": "def",
                "tier_weight": 1.0,
                "last_seen_at": seen_at.isoformat(),
                "schema_version": 1,
            }
        ]
