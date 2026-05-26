"""B1 contract tests: source_scope flows from classification → :Symbol persistence.

Acceptance (GIM-850):
- build_symbol_node_rows computes source_scope from recipe roots
- Legacy (no recipe) symbols get fallback classification
- Symbols without file_path get null source_scope
- _row_to_symbol (dead_code) remains backward-compatible
- Semantic search vector query returns source_scope
"""

from __future__ import annotations

from palace_mcp.extractors.dead_code.graph_loader import _row_to_symbol
from palace_mcp.extractors.foundation.symbol_node_writer import build_symbol_node_rows
from palace_mcp.extractors.scip_parser import iter_scip_symbol_infos
from palace_mcp.smoke.recipe import BuildConfig, Recipe
from tests.extractors.fixtures.scip_factory import (
    build_swift_scip_index_with_symbol_infos,
)


def _uw_recipe() -> Recipe:
    return Recipe(
        slug="uw-ios-app",
        name="unstoppable-wallet-ios",
        language="swift",
        build_system="xcode_workspace",
        source_roots=["Sources/UwMiniCore", "Sources/UwMiniApp"],
        workspace_package_roots=["packages/WalletCore"],
        dependency_roots=["Pods", ".build"],
        generated_roots=["Sources/Generated"],
        derived_roots=[".palace-scip-derived-data"],
        scip_path="scip/index.scip",
        build=BuildConfig(
            workspace="Wallet.xcworkspace",
            scheme="Development",
        ),
        extractors=["symbol_index_swift"],
    )


# ---------------------------------------------------------------------------
# Classification flows into build_symbol_node_rows
# ---------------------------------------------------------------------------


class TestSourceScopeWithRecipe:
    """build_symbol_node_rows classifies file paths using recipe roots."""

    def _rows_with_recipe(self) -> list[dict]:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))
        from palace_mcp.extractors.foundation.models import SymbolKind
        from palace_mcp.extractors.scip_parser import iter_scip_occurrences

        def_file_paths: dict[str, str] = {}
        for occ in iter_scip_occurrences(scip_index, commit_sha="test"):
            if occ.kind in (SymbolKind.DEF, SymbolKind.DECL):
                def_file_paths.setdefault(occ.symbol_qualified_name, occ.file_path)

        return build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/uw-mini", recipe=_uw_recipe()
        )

    def test_app_source_classified_as_project(self) -> None:
        rows = self._rows_with_recipe()
        store_rows = [
            r
            for r in rows
            if "WalletStore" in r["qualified_name"]
            and "select" not in r["qualified_name"]
        ]
        assert store_rows
        assert store_rows[0]["source_scope"] == "project"

    def test_all_rows_have_source_scope(self) -> None:
        rows = self._rows_with_recipe()
        for row in rows:
            if row["file_path"] is not None:
                assert row["source_scope"] is not None, (
                    f"Row with file_path={row['file_path']} must have source_scope"
                )

    def test_dependency_path_classified(self) -> None:
        """Pods/ paths should classify as dependency."""
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "Pods/Foo/Foo.swift" for si in symbol_infos
        }
        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/test", recipe=_uw_recipe()
        )
        for row in rows:
            assert row["source_scope"] == "dependency"

    def test_generated_path_classified(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "Sources/Generated/Strings.swift" for si in symbol_infos
        }
        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/test", recipe=_uw_recipe()
        )
        for row in rows:
            assert row["source_scope"] == "generated"

    def test_derived_data_path_classified(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "DerivedData/Build/Products/Debug/Module.swift"
            for si in symbol_infos
        }
        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/test", recipe=_uw_recipe()
        )
        for row in rows:
            assert row["source_scope"] == "derived"

    def test_sdk_path_classified(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "Platforms/iPhoneSimulator.platform/SDK/usr/include/stdio.h"
            for si in symbol_infos
        }
        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/test", recipe=_uw_recipe()
        )
        for row in rows:
            assert row["source_scope"] == "sdk"

    def test_workspace_package_path_classified(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "packages/WalletCore/Sources/WalletCore.swift"
            for si in symbol_infos
        }
        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/test", recipe=_uw_recipe()
        )
        for row in rows:
            assert row["source_scope"] == "workspace_package"

    def test_build_dependency_path_classified(self) -> None:
        """.build/ paths classify as dependency."""
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: ".build/checkouts/swift-collections/Sources/Deque.swift"
            for si in symbol_infos
        }
        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/test", recipe=_uw_recipe()
        )
        for row in rows:
            assert row["source_scope"] == "dependency"

    def test_overlapping_roots_precedence(self) -> None:
        """When a path matches both source_root and derived_root, derived wins."""
        recipe = Recipe(
            slug="overlap",
            name="overlap",
            language="swift",
            build_system="swift_package",
            source_roots=["src", ".palace-scip-derived-data"],
            derived_roots=[".palace-scip-derived-data"],
            scip_path="scip/index.scip",
            build=BuildConfig(scheme="Test"),
            extractors=["symbol_index_swift"],
        )
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: ".palace-scip-derived-data/Output.swift"
            for si in symbol_infos
        }
        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/test", recipe=recipe
        )
        for row in rows:
            assert row["source_scope"] == "derived"


# ---------------------------------------------------------------------------
# Legacy fallback: no recipe
# ---------------------------------------------------------------------------


class TestSourceScopeLegacyFallback:
    def test_no_recipe_sdk_still_detected(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "Platforms/iPhoneSimulator.platform/SDK/usr/include/stdio.h"
            for si in symbol_infos
        }
        rows = build_symbol_node_rows(symbol_infos, def_file_paths, "project/test")
        for row in rows:
            assert row["source_scope"] == "sdk"

    def test_no_recipe_derived_data_detected(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "DerivedData/Build/Products/Debug/Foo.swift"
            for si in symbol_infos
        }
        rows = build_symbol_node_rows(symbol_infos, def_file_paths, "project/test")
        for row in rows:
            assert row["source_scope"] == "derived"

    def test_no_recipe_unknown_path_fallback(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        def_file_paths = {
            si.qualified_name: "Sources/MyApp/Main.swift" for si in symbol_infos
        }
        rows = build_symbol_node_rows(symbol_infos, def_file_paths, "project/test")
        for row in rows:
            assert row["source_scope"] == "dependency"


# ---------------------------------------------------------------------------
# Null file_path → null source_scope
# ---------------------------------------------------------------------------


class TestSourceScopeNullFilePath:
    def test_no_file_path_yields_null_source_scope(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        rows = build_symbol_node_rows(
            symbol_infos, {}, "project/test", recipe=_uw_recipe()
        )
        for row in rows:
            assert row["file_path"] is None
            assert row["source_scope"] is None


# ---------------------------------------------------------------------------
# Backward compatibility: _row_to_symbol ignores source_scope
# ---------------------------------------------------------------------------


class TestDeadCodeBackwardCompat:
    def test_row_to_symbol_ignores_source_scope(self) -> None:
        scip_index = build_swift_scip_index_with_symbol_infos()
        symbol_infos = list(iter_scip_symbol_infos(scip_index))

        from palace_mcp.extractors.foundation.models import SymbolKind
        from palace_mcp.extractors.scip_parser import iter_scip_occurrences

        def_file_paths: dict[str, str] = {}
        for occ in iter_scip_occurrences(scip_index, commit_sha="test"):
            if occ.kind in (SymbolKind.DEF, SymbolKind.DECL):
                def_file_paths.setdefault(occ.symbol_qualified_name, occ.file_path)

        rows = build_symbol_node_rows(
            symbol_infos, def_file_paths, "project/uw-mini", recipe=_uw_recipe()
        )
        for row in rows:
            assert "source_scope" in row
            sym = _row_to_symbol(row)
            assert sym.qualified_name == row["qualified_name"]


# ---------------------------------------------------------------------------
# Semantic search query contract
# ---------------------------------------------------------------------------


class TestSemanticSearchExposesSourceScope:
    def test_vector_query_returns_source_scope(self) -> None:
        from palace_mcp.code.find_semantic import _VECTOR_QUERY

        assert "source_scope" in _VECTOR_QUERY
        assert "s.source_scope AS source_scope" in _VECTOR_QUERY
