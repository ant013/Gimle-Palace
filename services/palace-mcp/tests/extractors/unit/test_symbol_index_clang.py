"""Unit tests for SymbolIndexClang extractor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import Language
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.symbol_index_clang import (
    SymbolIndexClang,
    _normalize_repo_relative_path,
    _is_vendor_path,
)
from palace_mcp.proto import scip_pb2
from tests.extractors.fixtures.scip_factory import write_scip_fixture


@pytest.fixture
def extractor() -> SymbolIndexClang:
    return SymbolIndexClang()


@pytest.fixture
def run_ctx(tmp_path: Path) -> ExtractorRunContext:
    repo = tmp_path / "uw-ios-clang-mini"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n")
    return ExtractorRunContext(
        project_slug="uw-ios-clang-mini",
        group_id="project/uw-ios-clang-mini",
        repo_path=repo,
        run_id="test-run-clang-001",
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


def _build_clang_index(
    *,
    repo_root: Path,
    vendor_absolute: bool = False,
    app_def_symbol: str = "scip-clang  . . app/main().",
    app_use_symbol: str = "scip-clang  . . math/Vector#length().",
    vendor_use_symbol: str = "scip-clang  . . vendor/Foo#helper().",
) -> scip_pb2.Index:
    index = scip_pb2.Index()  # type: ignore[attr-defined]
    metadata = scip_pb2.Metadata()  # type: ignore[attr-defined]
    metadata.version = scip_pb2.ProtocolVersion.UnspecifiedProtocolVersion  # type: ignore[attr-defined]
    metadata.tool_info.name = "scip-clang"
    metadata.tool_info.version = "0.4.0"
    metadata.project_root = f"file://{repo_root}"
    index.metadata.CopyFrom(metadata)

    docs: list[tuple[str, str, list[tuple[str, int]]]] = [
        (
            "CPP",
            "Sources/UwMiniCore/Math/Vector.cpp",
            [
                ("scip-clang  . . math/Vector#length().", 1),
                ("scip-clang  . . math/Vector#length().", 0),
            ],
        ),
        (
            "C",
            "Sources/UwMiniApp/main.c",
            [
                (app_def_symbol, 1),
                (app_use_symbol, 0),
            ],
        ),
        (
            "C",
            (
                str(repo_root / "Pods/Foo/Foo.c")
                if vendor_absolute
                else "Pods/Foo/Foo.c"
            ),
            [
                ("scip-clang  . . vendor/Foo#helper().", 1),
                (vendor_use_symbol, 0),
            ],
        ),
        (
            "C",
            "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk/usr/include/stdio.h",
            [("scip-clang  . . stdio/printf().", 1)],
        ),
    ]

    for language, relative_path, symbols in docs:
        doc = index.documents.add()
        doc.language = language
        doc.relative_path = relative_path
        for idx, (symbol, role) in enumerate(symbols, start=1):
            occ = doc.occurrences.add()
            occ.range.extend([idx, 0, 4])
            occ.symbol = symbol
            occ.symbol_roles = role

    return index


class TestSymbolIndexClangMeta:
    def test_name_is_correct(self, extractor: SymbolIndexClang) -> None:
        assert extractor.name == "symbol_index_clang"

    def test_description_mentions_clang(self, extractor: SymbolIndexClang) -> None:
        assert "clang" in extractor.description.lower()

    def test_primary_lang_is_cpp(self, extractor: SymbolIndexClang) -> None:
        assert extractor.primary_lang == Language.CPP


class TestSymbolIndexClangPaths:
    @pytest.mark.parametrize(
        ("file_path", "expected"),
        [
            ("Pods/Foo/Foo.c", True),
            ("Carthage/Checkouts/Foo/Foo.cpp", True),
            ("SourcePackages/checkouts/Foo/Foo.cc", True),
            ("third_party/lib/math.c", True),
            ("Vendor/Foo/Foo.cxx", True),
            ("Sources/UwMiniCore/Math/Vector.cpp", False),
        ],
    )
    def test_vendor_markers_match_expected(
        self, file_path: str, expected: bool
    ) -> None:
        assert _is_vendor_path(file_path) is expected

    def test_normalize_relative_path_keeps_app_path(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        assert (
            _normalize_repo_relative_path("Sources/UwMiniCore/Math/Vector.cpp", repo)
            == "Sources/UwMiniCore/Math/Vector.cpp"
        )

    def test_normalize_absolute_repo_vendor_path(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        vendor_file = repo / "Pods/Foo/Foo.c"
        vendor_file.parent.mkdir(parents=True)
        vendor_file.write_text("int foo(void) { return 1; }\n")

        normalized = _normalize_repo_relative_path(str(vendor_file), repo)

        assert normalized == "Pods/Foo/Foo.c"

    def test_normalize_deriveddata_path_that_resolves_back_to_repo(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        repo_file = repo / "Sources/UwMiniApp/main.c"
        repo_file.parent.mkdir(parents=True)
        repo_file.write_text("int main(void) { return 0; }\n")

        derived_file = (
            tmp_path
            / "DerivedData/Build/Intermediates.noindex/UwMini.build/Debug-iphonesimulator/UwMini.build/Objects-normal/arm64/main.c"
        )
        derived_file.parent.mkdir(parents=True)
        derived_file.symlink_to(repo_file)

        normalized = _normalize_repo_relative_path(str(derived_file), repo)

        assert normalized == "Sources/UwMiniApp/main.c"

    def test_normalize_symlinked_project_path_when_feasible(
        self, tmp_path: Path
    ) -> None:
        repo_real = tmp_path / "repo-real"
        repo_file = repo_real / "Sources/UwMiniCore/Math/Vector.cpp"
        repo_file.parent.mkdir(parents=True)
        repo_file.write_text("int vector_length(int x, int y) { return x + y; }\n")

        repo_link = tmp_path / "repo-link"
        try:
            repo_link.symlink_to(repo_real, target_is_directory=True)
        except OSError:
            pytest.skip(
                "symlinked project path normalization is infeasible on this filesystem"
            )

        normalized = _normalize_repo_relative_path(
            str(repo_link / "Sources/UwMiniCore/Math/Vector.cpp"),
            repo_link,
        )

        assert normalized == "Sources/UwMiniCore/Math/Vector.cpp"

    def test_normalize_system_path_returns_none(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        normalized = _normalize_repo_relative_path(
            "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1/vector",
            repo,
        )
        assert normalized is None


class TestSymbolIndexClangErrorHandling:
    @pytest.mark.asyncio
    async def test_missing_scip_path_raises_extractor_error(
        self,
        extractor: SymbolIndexClang,
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
                "palace_mcp.extractors.symbol_index_clang.ensure_custom_schema",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.create_ingest_run",
                AsyncMock(),
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.finalize_ingest_run",
                AsyncMock(),
            ),
        ):
            with pytest.raises(ExtractorError) as exc_info:
                await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        assert exc_info.value.error_code == ExtractorErrorCode.SCIP_PATH_REQUIRED


class TestSymbolIndexClangHappyPath:
    @pytest.mark.asyncio
    async def test_run_filters_system_and_vendor_definitions(
        self,
        extractor: SymbolIndexClang,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        scip_fixture = write_scip_fixture(
            _build_clang_index(repo_root=run_ctx.repo_path, vendor_absolute=True),
            tmp_path / "native.scip",
        )
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-clang-mini": str(scip_fixture)}
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
                "palace_mcp.extractors.symbol_index_clang.TantivyBridge",
                return_value=bridge_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.ensure_custom_schema",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang._get_previous_error_code",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.create_ingest_run",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.write_checkpoint",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.finalize_ingest_run",
                new_callable=AsyncMock,
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        phase_to_paths: dict[str, list[str]] = {}
        for call in bridge_mock.add_or_replace_async.await_args_list:
            occ, phase = call.args
            phase_to_paths.setdefault(phase, []).append(occ.file_path)

        assert stats.nodes_written == 5
        assert phase_to_paths["phase1_defs"] == [
            "Sources/UwMiniCore/Math/Vector.cpp",
            "Sources/UwMiniApp/main.c",
        ]
        assert sorted(phase_to_paths["phase2_user_uses"]) == [
            "Sources/UwMiniApp/main.c",
            "Sources/UwMiniCore/Math/Vector.cpp",
        ]
        assert phase_to_paths["phase3_vendor_uses"] == ["Pods/Foo/Foo.c"]

    @pytest.mark.asyncio
    async def test_same_descriptor_app_vendor_collision_is_documented_v1_limitation(
        self,
        extractor: SymbolIndexClang,
        run_ctx: ExtractorRunContext,
        tmp_path: Path,
    ) -> None:
        shared_symbol = "scip-clang  . . shared/collide()."
        scip_fixture = write_scip_fixture(
            _build_clang_index(
                repo_root=run_ctx.repo_path,
                app_def_symbol=shared_symbol,
                app_use_symbol=shared_symbol,
                vendor_use_symbol=shared_symbol,
            ),
            tmp_path / "collision.scip",
        )
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-clang-mini": str(scip_fixture)}
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
                "palace_mcp.extractors.symbol_index_clang.TantivyBridge",
                return_value=bridge_mock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.ensure_custom_schema",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang._get_previous_error_code",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.create_ingest_run",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.write_checkpoint",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.finalize_ingest_run",
                new_callable=AsyncMock,
            ),
        ):
            stats = await extractor.run(graphiti=MagicMock(), ctx=run_ctx)

        phase_to_occurrences: dict[str, list[object]] = {}
        for call in bridge_mock.add_or_replace_async.await_args_list:
            occ, phase = call.args
            phase_to_occurrences.setdefault(phase, []).append(occ)

        assert stats.nodes_written == 5

        phase1_defs = phase_to_occurrences["phase1_defs"]
        vendor_uses = phase_to_occurrences["phase3_vendor_uses"]

        shared_def = next(
            occ
            for occ in phase1_defs
            if occ.file_path == "Sources/UwMiniApp/main.c"
            and occ.symbol_qualified_name == ". shared/collide()."
        )
        shared_vendor_use = next(
            occ
            for occ in vendor_uses
            if occ.file_path == "Pods/Foo/Foo.c"
            and occ.symbol_qualified_name == ". shared/collide()."
        )

        assert shared_def.symbol_id == shared_vendor_use.symbol_id
        assert shared_def.symbol_qualified_name == shared_vendor_use.symbol_qualified_name

    @pytest.mark.asyncio
    async def test_runner_path_executes_registered_clang_extractor(
        self,
        tmp_path: Path,
    ) -> None:
        repos_root = tmp_path / "repos"
        repo = repos_root / "uw-ios-clang-mini"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text(
            "0123456789abcdef0123456789abcdef01234567\n"
        )

        scip_fixture = write_scip_fixture(
            _build_clang_index(repo_root=repo), tmp_path / "runner.scip"
        )

        result_mock = AsyncMock()
        result_mock.single = AsyncMock(
            return_value={"p": {"slug": "uw-ios-clang-mini"}}
        )

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
        settings.palace_scip_index_paths = {"uw-ios-clang-mini": str(scip_fixture)}
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
                "palace_mcp.extractors.symbol_index_clang.ensure_custom_schema",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang._get_previous_error_code",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.create_ingest_run",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.write_checkpoint",
                new_callable=AsyncMock,
            ),
            patch(
                "palace_mcp.extractors.symbol_index_clang.finalize_ingest_run",
                new_callable=AsyncMock,
            ),
        ):
            res = await run_extractor(
                name="symbol_index_clang",
                project="uw-ios-clang-mini",
                driver=driver,
                graphiti=MagicMock(),
            )

        assert res["ok"] is True
        assert res["extractor"] == "symbol_index_clang"
        assert res["project"] == "uw-ios-clang-mini"
        assert res["success"] is True
        assert res["nodes_written"] == 5
