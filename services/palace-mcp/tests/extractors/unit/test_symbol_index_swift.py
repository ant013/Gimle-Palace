"""Unit tests for SymbolIndexSwift extractor (mocked driver + bridge)."""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import (
    ExtractorExecutionMode,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.baseline import (
    BASELINE_STATUS_VALID,
    ExtractorBaseline,
)
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
)
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.foundation.symbol_node_writer import build_symbol_node_rows
from palace_mcp.extractors.scip_parser import (
    ScipSymbolInfo,
    iter_scip_occurrences,
    iter_scip_symbol_infos,
)
from palace_mcp.extractors.symbol_index_swift import (
    SymbolIndexSwift,
    _GitChangeSet,
    _body_hash_manifest_digest,
    _build_file_body_hashes,
    _build_shadow_rows,
    _derive_incremental_graph_scope,
    _infer_swift_access_modifier,
    _ingest_batch,
    _is_vendor,
    _read_swift_symbol_baseline_commit,
    _write_file_body_hashes,
    _with_access_modifiers,
)
from palace_mcp.swift_scip_provenance import (
    SWIFT_SCIP_EMITTER_NAME,
    SWIFT_SCIP_EMITTER_VERSION,
    swift_scip_file_digest,
    swift_scip_metadata_path,
)
from tests.extractors.fixtures.scip_factory import (
    build_swift_scip_index_with_symbol_infos,
    write_scip_fixture,
)


@pytest.fixture
def extractor() -> SymbolIndexSwift:
    return SymbolIndexSwift()


def _ensure_test_repo(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    _run(["git", "init", "-q", "-b", "main"], cwd=repo_path)
    _run(["git", "config", "user.email", "t@t"], cwd=repo_path)
    _run(["git", "config", "user.name", "T"], cwd=repo_path)
    (repo_path / "Package.swift").write_text("// swift-tools-version: 6.0\n")
    _run(["git", "add", "Package.swift"], cwd=repo_path)
    _run(["git", "commit", "-q", "-m", "initial"], cwd=repo_path)
    return _run_text(["git", "rev-parse", "HEAD"], cwd=repo_path)


def _write_test_scip_metadata(
    *, repo_path: Path, scip_path: Path, slug: str = "uw-ios-mini"
) -> str:
    head = _ensure_test_repo(repo_path)
    metadata = {
        "slug": slug,
        "repo_head_sha": head,
        "emitter_name": SWIFT_SCIP_EMITTER_NAME,
        "emitter_version": SWIFT_SCIP_EMITTER_VERSION,
        "artifact_origin": "local",
        "package_path": "Package.swift",
        "generator_host": socket.gethostname(),
        "source_repo_path": str(repo_path.resolve()),
        "destination_repo_path": str(repo_path.resolve()),
    }
    swift_scip_metadata_path(scip_path).write_text(json.dumps(metadata))
    return head


@pytest.fixture
def scip_fixture(tmp_path: Path) -> Path:
    # Use the fixture with SymbolInformation so write_symbol_nodes is exercised
    # and nodes_written reflects actual Neo4j :Symbol count (3 symbols).
    index = build_swift_scip_index_with_symbol_infos()
    scip_path = write_scip_fixture(index, tmp_path / "test.scip")
    _write_test_scip_metadata(repo_path=tmp_path, scip_path=scip_path)
    return scip_path


@pytest.fixture
def run_ctx(tmp_path: Path) -> ExtractorRunContext:
    _ensure_test_repo(tmp_path)
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
    result_mock.consume = AsyncMock()
    result_mock.data = AsyncMock(return_value=[])
    inner_session.run = AsyncMock(return_value=result_mock)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=inner_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session.return_value = session_cm
    return driver


def _swift_symbol_baseline(
    *,
    status: str = BASELINE_STATUS_VALID,
    state_version: int = 1,
    commit_sha: str = "baseline-sha",
    body_hash_manifest_digest: str = "sha256:manifest",
    scip_digest: str = "sha256:scip",
    invalid_reason: str | None = None,
) -> ExtractorBaseline:
    return ExtractorBaseline(
        project_id="project/uw-ios-mini",
        project_slug="uw-ios-mini",
        extractor=SymbolIndexSwift.name,
        baseline_kind="swift_symbol_scope",
        state_version=state_version,
        commit_sha=commit_sha,
        indexed_commit=commit_sha,
        scip_digest=scip_digest,
        scip_path="index.scip",
        scip_document_count=1,
        scip_occurrence_count=2,
        body_hash_manifest_digest=body_hash_manifest_digest,
        file_count=1,
        successful_run_id="run-baseline",
        status=status,
        invalid_reason=invalid_reason,
        updated_at=datetime.now(tz=timezone.utc),
    )


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _run_text(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class TestSymbolIndexSwiftMeta:
    def test_name_is_correct(self, extractor: SymbolIndexSwift) -> None:
        assert extractor.name == "symbol_index_swift"

    def test_description_mentions_swift(self, extractor: SymbolIndexSwift) -> None:
        assert "swift" in extractor.description.lower()

    def test_primary_lang_is_swift(self, extractor: SymbolIndexSwift) -> None:
        assert extractor.primary_lang == Language.SWIFT


class TestSymbolIndexSwiftBaseline:
    @pytest.mark.asyncio
    async def test_read_baseline_commit_returns_present_valid_commit(self) -> None:
        with patch(
            "palace_mcp.extractors.symbol_index_swift.load_extractor_baseline",
            new=AsyncMock(return_value=_swift_symbol_baseline()),
        ):
            commit_sha, reason = await _read_swift_symbol_baseline_commit(
                _make_driver(),
                project_id="project/uw-ios-mini",
                extractor_name=SymbolIndexSwift.name,
            )

        assert commit_sha == "baseline-sha"
        assert reason is None

    @pytest.mark.asyncio
    async def test_read_baseline_commit_reports_missing_for_migration(self) -> None:
        with patch(
            "palace_mcp.extractors.symbol_index_swift.load_extractor_baseline",
            new=AsyncMock(return_value=None),
        ):
            commit_sha, reason = await _read_swift_symbol_baseline_commit(
                _make_driver(),
                project_id="project/uw-ios-mini",
                extractor_name=SymbolIndexSwift.name,
            )

        assert commit_sha is None
        assert reason == "baseline_missing"

    @pytest.mark.asyncio
    async def test_read_baseline_commit_rejects_invalid_baseline(self) -> None:
        with patch(
            "palace_mcp.extractors.symbol_index_swift.load_extractor_baseline",
            new=AsyncMock(
                return_value=_swift_symbol_baseline(
                    status="invalid",
                    invalid_reason="baseline_invalidated_by_schema",
                )
            ),
        ):
            commit_sha, reason = await _read_swift_symbol_baseline_commit(
                _make_driver(),
                project_id="project/uw-ios-mini",
                extractor_name=SymbolIndexSwift.name,
            )

        assert commit_sha is None
        assert reason == "baseline_invalidated_by_schema"

    @pytest.mark.asyncio
    async def test_read_baseline_commit_rejects_schema_mismatch(self) -> None:
        with patch(
            "palace_mcp.extractors.symbol_index_swift.load_extractor_baseline",
            new=AsyncMock(return_value=_swift_symbol_baseline(state_version=999)),
        ):
            commit_sha, reason = await _read_swift_symbol_baseline_commit(
                _make_driver(),
                project_id="project/uw-ios-mini",
                extractor_name=SymbolIndexSwift.name,
            )

        assert commit_sha is None
        assert reason == "baseline_schema_mismatch"


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


class TestSymbolIndexSwiftAccessModifiers:
    @pytest.mark.parametrize(
        ("source", "line_start", "expected"),
        [
            ("public class PublicThing {}\nclass InternalThing {}\n", 2, "internal"),
            ("func send(_ public: String) {}\n", 1, "internal"),
            ("class Box { public let value: Int }\n", 1, "internal"),
            ('class Box { let label = "public" }\n', 1, "internal"),
            ("class Box {} // public\n", 1, "internal"),
            ("public\nclass Box {}\n", 2, "public"),
            ("public class Box {}\n", 1, "public"),
        ],
    )
    def test_infer_access_modifier_ignores_non_leading_tokens(
        self, tmp_path: Path, source: str, line_start: int, expected: str
    ) -> None:
        source_path = tmp_path / "Sources" / "Example.swift"
        source_path.parent.mkdir(parents=True)
        source_path.write_text(source, encoding="utf-8")

        assert (
            _infer_swift_access_modifier(
                repo_path=tmp_path,
                file_path="Sources/Example.swift",
                line_start=line_start,
                file_lines_cache={},
            )
            == expected
        )

    def test_with_access_modifiers_reads_source_visibility(
        self, tmp_path: Path
    ) -> None:
        index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = tuple(iter_scip_symbol_infos(index))
        def_file_paths: dict[str, str] = {}
        for occ in iter_scip_occurrences(index, commit_sha="test"):
            if occ.kind in (SymbolKind.DEF, SymbolKind.DECL):
                def_file_paths.setdefault(occ.symbol_qualified_name, occ.file_path)

        wallet_store_path = tmp_path / "Sources" / "UwMiniCore" / "State"
        wallet_store_path.mkdir(parents=True)
        (wallet_store_path / "WalletStore.swift").write_text(
            "public class WalletStore {}\npublic func select(walletID: Int) {}\n",
            encoding="utf-8",
        )
        dead_helper_path = tmp_path / "Sources" / "UwMiniCore"
        dead_helper_path.mkdir(parents=True, exist_ok=True)
        (dead_helper_path / "DeadHelper.swift").write_text(
            "class DeadHelper {}\n",
            encoding="utf-8",
        )

        # Synthetic fixture ranges are not sourced from the real emitter, so pin
        # the declaration lines to the file content we just wrote.
        def_line_starts = {
            qname: 1
            for qname in def_file_paths
            if "WalletStore" in qname and "select" not in qname
        }
        def_line_starts.update(
            {qname: 2 for qname in def_file_paths if "select" in qname}
        )
        def_line_starts.update(
            {qname: 1 for qname in def_file_paths if "DeadHelper" in qname}
        )

        enriched = _with_access_modifiers(
            symbol_infos,
            repo_path=tmp_path,
            def_file_paths=def_file_paths,
            def_line_starts=def_line_starts,
        )
        access_by_qname = {
            sym_info.qualified_name: sym_info.access_modifier for sym_info in enriched
        }

        wallet_store_qname = next(
            qname
            for qname in access_by_qname
            if "WalletStore" in qname and "select" not in qname
        )
        select_qname = next(qname for qname in access_by_qname if "select" in qname)
        dead_helper_qname = next(
            qname for qname in access_by_qname if "DeadHelper" in qname
        )

        assert access_by_qname[wallet_store_qname] == "public"
        assert access_by_qname[select_qname] == "public"
        assert access_by_qname[dead_helper_qname] == "internal"


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
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/App/File.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            with pytest.raises(ExtractorError) as exc_info:
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)
        assert exc_info.value.error_code == ExtractorErrorCode.SCIP_PATH_REQUIRED

    @pytest.mark.asyncio
    async def test_scip_file_not_found_fails_before_schema_setup(
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

        schema_mock = AsyncMock()
        create_run_mock = AsyncMock()
        previous_error_mock = AsyncMock()
        parse_mock = MagicMock()
        bridge_mock = MagicMock()
        refresh_mock = AsyncMock()
        write_baseline_mock = AsyncMock()
        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=_make_driver()),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
            patch(
                "palace_mcp.extractors.symbol_index_swift.ensure_custom_schema",
                schema_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.create_ingest_run",
                create_run_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._get_previous_error_code",
                previous_error_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.parse_scip_file",
                parse_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.TantivyBridge",
                bridge_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._refresh_graph_state",
                refresh_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._write_swift_symbol_baseline",
                write_baseline_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.finalize_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/App/File.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            with pytest.raises(ExtractorError) as exc_info:
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert exc_info.value.error_code == ExtractorErrorCode.SCIP_ARTIFACT_STALE
        assert exc_info.value.context["reason"] == "scip_artifact_missing"
        schema_mock.assert_not_awaited()
        create_run_mock.assert_not_awaited()
        previous_error_mock.assert_not_awaited()
        parse_mock.assert_not_called()
        bridge_mock.assert_not_called()
        refresh_mock.assert_not_awaited()
        write_baseline_mock.assert_not_awaited()

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
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/App/File.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
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
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/UwMiniCore/State/WalletStore.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert stats.nodes_written >= 3

    def test_build_file_body_hashes_uses_sha256_of_file_content(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        file_path = repo / "Sources" / "App" / "File.swift"
        file_path.parent.mkdir(parents=True)
        file_path.write_text('print("hello")\n')
        occurrence = SymbolOccurrence(
            doc_key="1:Sources/App/File.swift:1:0:abc123",
            symbol_id=1,
            symbol_qualified_name="App.hello",
            kind=SymbolKind.DEF,
            language=Language.SWIFT,
            file_path="Sources/App/File.swift",
            line=1,
            col_start=0,
            col_end=5,
            importance=1.0,
            commit_sha="abc123",
            ingest_run_id="run-1",
        )

        result = _build_file_body_hashes(repo, [occurrence])

        assert result == {
            "Sources/App/File.swift": hashlib.sha256(b'print("hello")\n').hexdigest()
        }

    @pytest.mark.asyncio
    async def test_run_skips_reingest_when_file_body_hashes_match(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
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
        finalize_mock = AsyncMock()
        write_symbol_nodes_mock = AsyncMock(return_value=3)
        write_shadow_rows_mock = AsyncMock(return_value=1)
        write_file_body_hashes_mock = AsyncMock(return_value=1)
        soft_delete_symbols_mock = AsyncMock(return_value=0)

        caplog.set_level(
            logging.INFO, logger="palace_mcp.extractors.symbol_index_swift"
        )

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
                finalize_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.write_symbol_nodes",
                write_symbol_nodes_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._write_shadow_rows",
                write_shadow_rows_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._write_file_body_hashes",
                write_file_body_hashes_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.soft_delete_symbols",
                soft_delete_symbols_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/App/File.swift": "stable-hash"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={"Sources/App/File.swift": "stable-hash"},
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert stats.outcome.value == "skipped"
        assert stats.nodes_written == 0
        assert stats.edges_written == 0
        assert "symbol_index_swift.freshness.skip" in caplog.text
        bridge_mock.add_or_replace_async.assert_not_called()
        write_shadow_rows_mock.assert_awaited_once()
        assert write_symbol_nodes_mock.await_count > 0
        write_file_body_hashes_mock.assert_awaited_once()
        await_args = write_file_body_hashes_mock.await_args
        assert await_args is not None
        assert await_args.kwargs["run_id"] == run_ctx.run_id
        soft_delete_symbols_mock.assert_awaited_once()
        finalize_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_fast_skips_graph_refresh_when_valid_baseline_matches(
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

        current_hashes = {"Sources/App/File.swift": "stable-hash"}
        bridge_mock = AsyncMock()
        bridge_mock.__aenter__ = AsyncMock(return_value=bridge_mock)
        bridge_mock.__aexit__ = AsyncMock(return_value=False)
        refresh_mock = AsyncMock(return_value=(3, 1, 0))
        write_baseline_mock = AsyncMock()
        finalize_mock = AsyncMock()

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
                "palace_mcp.extractors.symbol_index_swift.finalize_ingest_run",
                finalize_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value=current_hashes,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value=dict(current_hashes),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.load_extractor_baseline",
                new=AsyncMock(
                    return_value=_swift_symbol_baseline(
                        commit_sha=_run_text(
                            ["git", "rev-parse", "HEAD"], cwd=run_ctx.repo_path
                        ),
                        body_hash_manifest_digest=_body_hash_manifest_digest(
                            current_hashes
                        ),
                        scip_digest=swift_scip_file_digest(scip_fixture) or "missing",
                    )
                ),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._refresh_graph_state",
                refresh_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._write_swift_symbol_baseline",
                write_baseline_mock,
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert stats.outcome == ExtractorOutcome.SKIPPED
        refresh_mock.assert_not_awaited()
        write_baseline_mock.assert_not_awaited()
        bridge_mock.add_or_replace_async.assert_not_called()
        finalize_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_fully_reprocesses_same_head_replacement_scip(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
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
        settings.palace_incremental_ingest = True

        current_hashes = {"Sources/App/File.swift": "stable-hash"}
        current_scip_digest = swift_scip_file_digest(scip_fixture)
        assert current_scip_digest is not None
        bridge_mock = AsyncMock()
        bridge_mock.__aenter__ = AsyncMock(return_value=bridge_mock)
        bridge_mock.__aexit__ = AsyncMock(return_value=False)
        refresh_mock = AsyncMock(return_value=(3, 1, 0))
        write_baseline_mock = AsyncMock()
        caplog.set_level(
            logging.INFO, logger="palace_mcp.extractors.symbol_index_swift"
        )

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
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value=current_hashes,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value=dict(current_hashes),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.load_extractor_baseline",
                new=AsyncMock(
                    return_value=_swift_symbol_baseline(
                        commit_sha=_run_text(
                            ["git", "rev-parse", "HEAD"], cwd=run_ctx.repo_path
                        ),
                        body_hash_manifest_digest=_body_hash_manifest_digest(
                            current_hashes
                        ),
                        scip_digest="sha256:replaced-artifact",
                    )
                ),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._refresh_graph_state",
                refresh_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._write_swift_symbol_baseline",
                write_baseline_mock,
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert stats.mode == ExtractorExecutionMode.FULL
        assert any(
            getattr(record, "freshness_reason", None) == "scip_digest_mismatch"
            for record in caplog.records
        )
        assert bridge_mock.add_or_replace_async.await_count > 0
        bridge_mock.delete_by_file_paths_async.assert_not_awaited()
        refresh_mock.assert_awaited_once()
        assert refresh_mock.await_args.kwargs["selected_paths"] is None
        write_baseline_mock.assert_awaited_once()
        assert (
            write_baseline_mock.await_args.kwargs["scip_digest"] == current_scip_digest
        )

    @pytest.mark.asyncio
    async def test_run_logs_hash_mismatch_and_reingests(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        scip_fixture: Path,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
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

        caplog.set_level(
            logging.INFO, logger="palace_mcp.extractors.symbol_index_swift"
        )

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
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/App/File.swift": "new-hash"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={"Sources/App/File.swift": "old-hash"},
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert stats.nodes_written >= 3
        assert "symbol_index_swift.freshness.reingest" in caplog.text
        assert bridge_mock.add_or_replace_async.await_count > 0

    @pytest.mark.asyncio
    async def test_run_reingests_only_changed_file_when_incremental_enabled(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        scip_path = tmp_path / "test.scip"
        scip_path.write_bytes(b"incremental")
        _write_test_scip_metadata(repo_path=run_ctx.repo_path, scip_path=scip_path)
        settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_path)}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 100
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0
        settings.palace_incremental_ingest = True

        occurrences = [
            SymbolOccurrence(
                doc_key="1:Sources/App/Stable.swift:1:0:abc123",
                symbol_id=1,
                symbol_qualified_name="App.StableDef",
                kind=SymbolKind.DEF,
                language=Language.SWIFT,
                file_path="Sources/App/Stable.swift",
                line=1,
                col_start=0,
                col_end=1,
                importance=0.0,
                commit_sha="abc123",
                ingest_run_id=run_ctx.run_id,
            ),
            SymbolOccurrence(
                doc_key="2:Sources/App/Stable.swift:2:0:abc123",
                symbol_id=2,
                symbol_qualified_name="App.StableUse",
                kind=SymbolKind.USE,
                language=Language.SWIFT,
                file_path="Sources/App/Stable.swift",
                line=2,
                col_start=0,
                col_end=1,
                importance=0.0,
                commit_sha="abc123",
                ingest_run_id=run_ctx.run_id,
            ),
            SymbolOccurrence(
                doc_key="3:Sources/App/Changed.swift:1:0:abc123",
                symbol_id=3,
                symbol_qualified_name="App.ChangedDef",
                kind=SymbolKind.DEF,
                language=Language.SWIFT,
                file_path="Sources/App/Changed.swift",
                line=1,
                col_start=0,
                col_end=1,
                importance=0.0,
                commit_sha="abc123",
                ingest_run_id=run_ctx.run_id,
            ),
            SymbolOccurrence(
                doc_key="4:Sources/App/Changed.swift:2:0:abc123",
                symbol_id=4,
                symbol_qualified_name="App.ChangedUse",
                kind=SymbolKind.USE,
                language=Language.SWIFT,
                file_path="Sources/App/Changed.swift",
                line=2,
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
        bridge_mock.add_or_replace_async = AsyncMock()
        bridge_mock.commit_async = AsyncMock()
        bridge_mock.delete_by_file_paths_async = AsyncMock(return_value=1)
        refresh_mock = AsyncMock(return_value=(0, 0, 0))
        derive_scope_mock = AsyncMock(
            return_value=({"Sources/App/Changed.swift"}, set(), None)
        )
        legacy_commit_mock = AsyncMock(return_value="legacy-sha")

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
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={
                    "Sources/App/Stable.swift": "stable",
                    "Sources/App/Changed.swift": "new",
                },
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={
                    "Sources/App/Stable.swift": "stable",
                    "Sources/App/Changed.swift": "old",
                },
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_head_sha",
                return_value="abc123",
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift.load_extractor_baseline",
                new=AsyncMock(return_value=_swift_symbol_baseline()),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_commit_sha",
                legacy_commit_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._derive_incremental_graph_scope",
                derive_scope_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._refresh_graph_state",
                refresh_mock,
            ),
        ):
            await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        bridge_mock.delete_by_file_paths_async.assert_awaited_once_with(
            ["Sources/App/Changed.swift"]
        )
        changed_paths = {
            call.args[0].file_path
            for call in bridge_mock.add_or_replace_async.await_args_list
        }
        assert changed_paths == {"Sources/App/Changed.swift"}
        refresh_mock.assert_awaited_once()
        legacy_commit_mock.assert_not_awaited()
        derive_scope_mock.assert_awaited_once()
        assert (
            derive_scope_mock.await_args.kwargs["previous_commit_sha"] == "baseline-sha"
        )

    @pytest.mark.asyncio
    async def test_failed_run_does_not_advance_swift_symbol_baseline(
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
        finalize_mock = AsyncMock()
        write_baseline_mock = AsyncMock()
        driver = _make_driver()

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
                finalize_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/App/File.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._refresh_graph_state",
                new=AsyncMock(side_effect=RuntimeError("graph refresh failed")),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._write_swift_symbol_baseline",
                write_baseline_mock,
            ),
        ):
            with pytest.raises(RuntimeError, match="graph refresh failed"):
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        write_baseline_mock.assert_not_awaited()
        finalize_mock.assert_any_await(
            driver, run_id=run_ctx.run_id, success=False, error_code="unknown"
        )

    @pytest.mark.asyncio
    async def test_run_falls_back_to_full_reprocess_when_threshold_exceeded(
        self,
        extractor: SymbolIndexSwift,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        scip_path = tmp_path / "test.scip"
        scip_path.write_bytes(b"threshold")
        _write_test_scip_metadata(repo_path=run_ctx.repo_path, scip_path=scip_path)
        settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_path)}
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 100
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0
        settings.palace_incremental_ingest = True

        occurrences = [
            SymbolOccurrence(
                doc_key="1:Sources/App/A.swift:1:0:abc123",
                symbol_id=1,
                symbol_qualified_name="App.ADef",
                kind=SymbolKind.DEF,
                language=Language.SWIFT,
                file_path="Sources/App/A.swift",
                line=1,
                col_start=0,
                col_end=1,
                importance=0.0,
                commit_sha="abc123",
                ingest_run_id=run_ctx.run_id,
            ),
            SymbolOccurrence(
                doc_key="2:Sources/App/B.swift:1:0:abc123",
                symbol_id=2,
                symbol_qualified_name="App.BDef",
                kind=SymbolKind.DEF,
                language=Language.SWIFT,
                file_path="Sources/App/B.swift",
                line=1,
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
        bridge_mock.add_or_replace_async = AsyncMock()
        bridge_mock.commit_async = AsyncMock()
        bridge_mock.delete_by_file_paths_async = AsyncMock(return_value=2)

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
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={
                    "Sources/App/A.swift": "new-a",
                    "Sources/App/B.swift": "new-b",
                },
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={
                    "Sources/App/A.swift": "old-a",
                    "Sources/App/B.swift": "old-b",
                },
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_head_sha",
                return_value="abc123",
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._refresh_graph_state",
                new_callable=AsyncMock,
                return_value=(0, 0, 0),
            ),
        ):
            await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        bridge_mock.delete_by_file_paths_async.assert_not_awaited()
        reingested_paths = {
            call.args[0].file_path
            for call in bridge_mock.add_or_replace_async.await_args_list
        }
        assert reingested_paths == {"Sources/App/A.swift", "Sources/App/B.swift"}

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
        scip_path = tmp_path / "test.scip"
        scip_path.write_bytes(b"streaming")
        _write_test_scip_metadata(repo_path=run_ctx.repo_path, scip_path=scip_path)
        settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_path)}
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
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/App/File.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
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
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/UwMiniCore/State/WalletStore.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
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
            patch(
                "palace_mcp.extractors.symbol_index_swift._build_file_body_hashes",
                return_value={"Sources/UwMiniCore/State/WalletStore.swift": "hash-1"},
            ),
            patch(
                "palace_mcp.extractors.symbol_index_swift._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value={},
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
                "doc_key": "101:Sources/UwMiniCore/Models/BalanceData.swift:1:0:abc123",
                "file_path": "Sources/UwMiniCore/Models/BalanceData.swift",
                "line": 1,
                "col_start": 0,
                "col_end": 11,
                "ingest_run_id": "run-1",
            }
        ]


def _force_settings(scip_fixture: Path, tantivy_dir: Path) -> MagicMock:
    settings = MagicMock()
    settings.palace_scip_index_paths = {"uw-ios-mini": str(scip_fixture)}
    settings.palace_tantivy_index_path = str(tantivy_dir)
    settings.palace_tantivy_heap_mb = 100
    settings.palace_max_occurrences_total = 50_000_000
    settings.palace_max_occurrences_per_project = 10_000_000
    settings.palace_importance_threshold_use = 0.0
    settings.palace_max_occurrences_per_symbol = 5_000
    settings.palace_recency_decay_days = 30.0
    return settings


_FORCE_HASHES = {"Sources/UwMiniCore/State/WalletStore.swift": "hash-1"}


@pytest.mark.asyncio
async def test_derive_incremental_graph_scope_uses_git_intersection(
    tmp_path: Path,
) -> None:
    with patch(
        "palace_mcp.extractors.symbol_index_swift._read_git_change_set",
        new=AsyncMock(
            return_value=_GitChangeSet(
                changed={"Sources/App/Changed.swift"},
                added={"Sources/App/Added.swift"},
                removed={"Sources/App/Removed.swift"},
                truncated=False,
            )
        ),
    ):
        selected, removed, reason = await _derive_incremental_graph_scope(
            repo_path=tmp_path,
            previous_commit_sha="base-sha",
            scip_paths={
                "Sources/App/Changed.swift",
                "Sources/App/Added.swift",
            },
            changed_files={
                "Sources/App/Changed.swift",
                "Sources/App/Added.swift",
            },
            removed_files={"Sources/App/Removed.swift"},
        )

    assert selected == {
        "Sources/App/Added.swift",
        "Sources/App/Changed.swift",
    }
    assert removed == {"Sources/App/Removed.swift"}
    assert reason is None


@pytest.mark.asyncio
async def test_derive_incremental_graph_scope_uses_git_diff_for_clean_commits(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    swift_path = repo / "Sources" / "App" / "Changed.swift"
    swift_path.parent.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "t@t"], cwd=repo)
    _run(["git", "config", "user.name", "T"], cwd=repo)
    swift_path.write_text('print("old")\n')
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo)
    previous_commit_sha = _run_text(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
    )
    swift_path.write_text('print("new")\n')
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "change", "-q"], cwd=repo)

    selected, removed, reason = await _derive_incremental_graph_scope(
        repo_path=repo,
        previous_commit_sha=previous_commit_sha,
        scip_paths={"Sources/App/Changed.swift"},
        changed_files={"Sources/App/Changed.swift"},
        removed_files=set(),
    )

    assert selected == {"Sources/App/Changed.swift"}
    assert removed == set()
    assert reason is None


@pytest.mark.asyncio
async def test_derive_incremental_graph_scope_falls_back_on_truncated_git_diff(
    tmp_path: Path,
) -> None:
    with patch(
        "palace_mcp.extractors.symbol_index_swift._read_git_change_set",
        new=AsyncMock(
            return_value=_GitChangeSet(
                changed={"Sources/App/Changed.swift"},
                added=set(),
                removed=set(),
                truncated=True,
            )
        ),
    ):
        selected, removed, reason = await _derive_incremental_graph_scope(
            repo_path=tmp_path,
            previous_commit_sha="base-sha",
            scip_paths={"Sources/App/Changed.swift"},
            changed_files={"Sources/App/Changed.swift"},
            removed_files=set(),
        )

    assert selected is None
    assert removed == set()
    assert reason == "git_diff_truncated"


async def _async_run_with_matching_hashes(
    extractor: SymbolIndexSwift,
    ctx: ExtractorRunContext,
    scip_fixture: Path,
    tmp_path: Path,
) -> ExtractorStats:
    """Run the extractor with previous == current body_hashes (would skip unless
    ctx.force). All side-effecting collaborators are mocked."""
    import contextlib

    tantivy_dir = tmp_path / "tantivy"
    tantivy_dir.mkdir(exist_ok=True)
    bridge_mock = AsyncMock()
    bridge_mock.__aenter__ = AsyncMock(return_value=bridge_mock)
    bridge_mock.__aexit__ = AsyncMock(return_value=False)
    bridge_mock.add_or_replace_async = AsyncMock()
    bridge_mock.commit_async = AsyncMock()
    p = "palace_mcp.extractors.symbol_index_swift"
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("palace_mcp.mcp_server.get_driver", return_value=_make_driver())
        )
        stack.enter_context(
            patch(
                "palace_mcp.mcp_server.get_settings",
                return_value=_force_settings(scip_fixture, tantivy_dir),
            )
        )
        stack.enter_context(patch(f"{p}.TantivyBridge", return_value=bridge_mock))
        for fn in (
            "ensure_custom_schema",
            "create_ingest_run",
            "write_checkpoint",
            "finalize_ingest_run",
        ):
            stack.enter_context(patch(f"{p}.{fn}", new_callable=AsyncMock))
        stack.enter_context(
            patch(
                f"{p}._get_previous_error_code",
                new_callable=AsyncMock,
                return_value=None,
            )
        )
        stack.enter_context(
            patch(f"{p}._build_file_body_hashes", return_value=dict(_FORCE_HASHES))
        )
        stack.enter_context(
            patch(
                f"{p}._read_existing_file_body_hashes",
                new_callable=AsyncMock,
                return_value=dict(_FORCE_HASHES),
            )
        )
        return await extractor.run(graphiti=MagicMock(), ctx=ctx)


def _force_ctx(tmp_path: Path, *, force: bool) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="uw-ios-mini",
        group_id="project/uw-ios-mini",
        repo_path=tmp_path,
        run_id=f"force-test-{force}",
        duration_ms=0,
        logger=MagicMock(),
        force=force,
    )


class TestSymbolIndexSwiftForceFlag:
    """dogfood #6: a writer/schema change must be roll-out-able over unchanged
    source without hand-clearing :File.body_hash. ctx.force bypasses the body_hash
    skip; the default still skips when content is unchanged.
    """

    @pytest.mark.asyncio
    async def test_matching_hashes_skip_without_force(
        self, extractor: SymbolIndexSwift, scip_fixture: Path, tmp_path: Path
    ) -> None:
        stats = await _async_run_with_matching_hashes(
            extractor, _force_ctx(tmp_path, force=False), scip_fixture, tmp_path
        )
        assert stats.outcome == ExtractorOutcome.SKIPPED

    @pytest.mark.asyncio
    async def test_force_bypasses_body_hash_skip(
        self, extractor: SymbolIndexSwift, scip_fixture: Path, tmp_path: Path
    ) -> None:
        stats = await _async_run_with_matching_hashes(
            extractor, _force_ctx(tmp_path, force=True), scip_fixture, tmp_path
        )
        assert stats.outcome != ExtractorOutcome.SKIPPED
        assert stats.nodes_written >= 3


def test_build_file_body_hashes_skips_missing_files(tmp_path: Path) -> None:
    """A stale SCIP may reference files that no longer exist on disk (cleaned
    DerivedData build-intermediates); the missing file must be skipped, not abort
    the symbol_index run, while present files are still hashed."""
    from types import SimpleNamespace

    (tmp_path / "present.swift").write_text("let x = 1\n")
    occurrences = [
        SimpleNamespace(file_path="present.swift"),
        SimpleNamespace(file_path="missing.swift"),
    ]
    hashes = _build_file_body_hashes(tmp_path, occurrences)  # type: ignore[arg-type]
    assert set(hashes) == {"present.swift"}


@pytest.mark.asyncio
async def test_write_file_body_hashes_prunes_absent_paths_after_full_refresh() -> None:
    driver = _make_driver()
    observed_at = datetime(2026, 7, 11, tzinfo=timezone.utc)

    written = await _write_file_body_hashes(
        driver,
        project_id="project/uw-ios-mini",
        run_id="run-1",
        file_body_hashes={"Sources/App/Current.swift": "hash-current"},
        observed_at=observed_at,
        commit_sha="commit-1",
        prune_absent_paths=True,
        removed_paths=set(),
    )

    session = driver.session.return_value.__aenter__.return_value
    assert written == 1
    assert session.run.await_count == 2
    prune_call = session.run.await_args_list[1]
    assert "NOT f.path IN $current_paths" in prune_call.args[0]
    assert prune_call.kwargs["current_paths"] == ["Sources/App/Current.swift"]
    assert prune_call.kwargs["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_write_file_body_hashes_clears_incremental_removed_paths() -> None:
    driver = _make_driver()
    observed_at = datetime(2026, 7, 11, tzinfo=timezone.utc)

    written = await _write_file_body_hashes(
        driver,
        project_id="project/uw-ios-mini",
        run_id="run-2",
        file_body_hashes={},
        observed_at=observed_at,
        commit_sha="commit-2",
        prune_absent_paths=False,
        removed_paths={"Sources/App/Removed.swift"},
    )

    session = driver.session.return_value.__aenter__.return_value
    assert written == 0
    assert session.run.await_count == 1
    removed_call = session.run.await_args_list[0]
    assert "f.path IN $removed_paths" in removed_call.args[0]
    assert removed_call.kwargs["removed_paths"] == ["Sources/App/Removed.swift"]
    assert removed_call.kwargs["run_id"] == "run-2"
