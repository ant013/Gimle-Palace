"""Contract tests for SourceScope classification (GIM-839 D0 / B0).

Acceptance:
- Unit tests can construct fixture symbols with all required metadata.
- Legacy symbols without source_scope are classified from recipe roots
  when recipe metadata exists.
- Unclassifiable legacy symbols are treated as fallback/warning, not
  normal first-party results.
"""

from __future__ import annotations

from palace_mcp.code.source_scope import (
    SourceScope,
    classify_source_scope,
)
from palace_mcp.smoke.recipe import BuildConfig, Recipe


# ---------------------------------------------------------------------------
# Fixture: UW-iOS recipe for classification tests
# ---------------------------------------------------------------------------


def _uw_recipe() -> Recipe:
    return Recipe(
        slug="uw-ios-app",
        name="unstoppable-wallet-ios",
        language="swift",
        build_system="xcode_workspace",
        source_roots=["Unstoppable"],
        workspace_package_roots=["packages/WalletCore"],
        dependency_roots=["Carthage", "Pods", ".build"],
        generated_roots=["Unstoppable/Generated"],
        derived_roots=[".palace-scip-derived-data"],
        scip_path="scip/index.scip",
        build=BuildConfig(
            workspace="Wallet.xcworkspace",
            scheme="Development",
        ),
        extractors=["symbol_index_swift"],
    )


# ---------------------------------------------------------------------------
# Classification with recipe
# ---------------------------------------------------------------------------


class TestClassifyWithRecipe:
    def test_project_source(self) -> None:
        result = classify_source_scope(
            "Unstoppable/Services/BalanceService.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.PROJECT
        assert result.warning is None

    def test_workspace_package(self) -> None:
        result = classify_source_scope(
            "packages/WalletCore/Sources/WalletCore.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.WORKSPACE_PACKAGE
        assert result.warning is None

    def test_dependency_carthage(self) -> None:
        result = classify_source_scope(
            "Carthage/Checkouts/SomeLib/Source.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is None

    def test_dependency_pods(self) -> None:
        result = classify_source_scope(
            "Pods/Alamofire/Source/Alamofire.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is None

    def test_dependency_build(self) -> None:
        result = classify_source_scope(
            ".build/checkouts/swift-collections/Sources/Deque.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is None

    def test_generated(self) -> None:
        result = classify_source_scope(
            "Unstoppable/Generated/Strings.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.GENERATED
        assert result.warning is None

    def test_derived(self) -> None:
        result = classify_source_scope(
            ".palace-scip-derived-data/Build/Products/Debug/Something.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.DERIVED
        assert result.warning is None

    def test_derived_builtin_derived_data(self) -> None:
        result = classify_source_scope(
            "DerivedData/Build/Products/Debug-iphonesimulator/Module.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.DERIVED
        assert result.warning is None

    def test_sdk_path(self) -> None:
        result = classify_source_scope(
            "Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk/"
            "usr/include/stdio.h",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.SDK
        assert result.warning is None

    def test_unknown_path_treated_as_dependency_with_warning(self) -> None:
        result = classify_source_scope(
            "SomeOtherDirectory/Unknown.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is not None
        assert "unclassifiable" in result.warning


# ---------------------------------------------------------------------------
# Precedence: derived > generated > sdk > workspace_package > dependency > project
# ---------------------------------------------------------------------------


class TestPrecedence:
    def test_derived_wins_over_source_root(self) -> None:
        recipe = Recipe(
            slug="overlap-test",
            name="overlap",
            language="swift",
            build_system="swift_package",
            source_roots=["src", ".palace-scip-derived-data"],
            derived_roots=[".palace-scip-derived-data"],
            scip_path="scip/index.scip",
            build=BuildConfig(scheme="Test"),
            extractors=["symbol_index_swift"],
        )
        result = classify_source_scope(
            ".palace-scip-derived-data/Output.swift",
            recipe=recipe,
        )
        assert result.scope == SourceScope.DERIVED

    def test_generated_wins_over_workspace_package(self) -> None:
        recipe = Recipe(
            slug="overlap-test",
            name="overlap",
            language="swift",
            build_system="swift_package",
            source_roots=["Sources"],
            workspace_package_roots=["gen"],
            generated_roots=["gen"],
            scip_path="scip/index.scip",
            build=BuildConfig(scheme="Test"),
            extractors=["symbol_index_swift"],
        )
        result = classify_source_scope("gen/Auto.swift", recipe=recipe)
        assert result.scope == SourceScope.GENERATED


# ---------------------------------------------------------------------------
# Legacy fallback: no recipe
# ---------------------------------------------------------------------------


class TestLegacyFallback:
    def test_no_recipe_sdk_still_detected(self) -> None:
        result = classify_source_scope(
            "Platforms/iPhoneSimulator.platform/SDK/usr/include/objc.h",
        )
        assert result.scope == SourceScope.SDK
        assert result.warning is None

    def test_no_recipe_derived_data_still_detected(self) -> None:
        result = classify_source_scope(
            "DerivedData/Build/Products/Debug/Foo.swift",
        )
        assert result.scope == SourceScope.DERIVED
        assert result.warning is None

    def test_no_recipe_unknown_path_treated_as_project(self) -> None:
        result = classify_source_scope(
            "Sources/MyApp/Main.swift",
        )
        assert result.scope == SourceScope.PROJECT
        assert result.warning is not None
        assert "no-recipe heuristic" in result.warning

    def test_no_recipe_warning_is_not_none(self) -> None:
        result = classify_source_scope("Unknown/Path.swift")
        assert result.warning is not None

    def test_no_recipe_source_packages_is_dependency(self) -> None:
        result = classify_source_scope(
            "SourcePackages/checkouts/SomeLib/Sources/SomeLib.swift",
        )
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is None

    def test_no_recipe_pods_is_dependency(self) -> None:
        result = classify_source_scope("Pods/Alamofire/Source/Alamofire.swift")
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is None

    def test_no_recipe_carthage_is_dependency(self) -> None:
        result = classify_source_scope("Carthage/Checkouts/Nimble/Sources/Nimble.swift")
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is None

    def test_no_recipe_build_checkouts_is_dependency(self) -> None:
        result = classify_source_scope(
            ".build/checkouts/swift-collections/Sources/Deque.swift"
        )
        assert result.scope == SourceScope.DEPENDENCY
        assert result.warning is None

    def test_no_recipe_derived_sources_is_generated(self) -> None:
        result = classify_source_scope("DerivedSources/R.generated.swift")
        assert result.scope == SourceScope.GENERATED
        assert result.warning is None

    def test_no_recipe_app_dir_is_project(self) -> None:
        result = classify_source_scope("Unstoppable/Services/BalanceService.swift")
        assert result.scope == SourceScope.PROJECT
        assert result.warning is not None

    def test_no_recipe_monero_adapter_is_project(self) -> None:
        result = classify_source_scope(
            "MoneroAdapter/Sources/MoneroAdapter/MoneroKit.swift"
        )
        assert result.scope == SourceScope.PROJECT


# ---------------------------------------------------------------------------
# Normalized path handling
# ---------------------------------------------------------------------------


class TestPathNormalization:
    def test_leading_dot_slash_stripped(self) -> None:
        result = classify_source_scope(
            "./Unstoppable/Services/Foo.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.PROJECT

    def test_double_slash_normalized(self) -> None:
        result = classify_source_scope(
            "Unstoppable//Services//Foo.swift",
            recipe=_uw_recipe(),
        )
        assert result.scope == SourceScope.PROJECT
