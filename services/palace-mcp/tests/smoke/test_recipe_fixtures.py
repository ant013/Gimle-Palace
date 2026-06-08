"""A1 recipe fixture and validation tests (GIM-842).

Acceptance:
- YAML fixtures for Swift Package and UW-iOS load and validate.
- Invalid recipes fail before command execution:
  missing build target, invalid roots, unsafe paths, unsupported build systems.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from palace_mcp.smoke.recipe import BuildConfig, Recipe, load_recipe_yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# A1.1 — YAML fixture loading
# ---------------------------------------------------------------------------


class TestFixtureLoading:
    def test_load_swift_package_fixture(self) -> None:
        recipe = load_recipe_yaml(FIXTURES_DIR / "swift_package_recipe.yaml")
        assert recipe.slug == "bitcoin-kit"
        assert recipe.build_system == "swift_package"
        assert recipe.build.scheme == "BitcoinKit"
        assert "symbol_index_swift" in recipe.extractors

    def test_load_uw_ios_fixture(self) -> None:
        recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")
        assert recipe.slug == "uw-ios-app"
        assert recipe.build_system == "xcode_workspace"
        assert recipe.build.workspace == "Wallet.xcworkspace"
        assert recipe.build.scheme == "Development"
        assert "embedding_symbol" in recipe.extractors

    def test_uw_ios_fixture_source_roots(self) -> None:
        recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")
        assert "Unstoppable" in recipe.source_roots
        assert "packages/WalletCore" in recipe.workspace_package_roots

    def test_swift_package_fixture_no_workspace(self) -> None:
        recipe = load_recipe_yaml(FIXTURES_DIR / "swift_package_recipe.yaml")
        assert recipe.build.workspace is None
        assert recipe.build.project is None


# ---------------------------------------------------------------------------
# A1.2 — Missing build target validation
# ---------------------------------------------------------------------------


class TestMissingBuildTarget:
    def test_xcode_workspace_requires_workspace(self) -> None:
        with pytest.raises(
            ValidationError, match="xcode_workspace.*requires build.workspace"
        ):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="xcode_workspace",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Dev"),
                extractors=["symbol_index_swift"],
            )

    def test_xcode_project_requires_project(self) -> None:
        with pytest.raises(
            ValidationError, match="xcode_project.*requires build.project"
        ):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="xcode_project",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Dev"),
                extractors=["symbol_index_swift"],
            )

    def test_swift_package_no_workspace_required(self) -> None:
        recipe = Recipe(
            slug="ok-recipe",
            name="ok",
            language="swift",
            build_system="swift_package",
            source_roots=["Sources"],
            scip_path="scip/index.scip",
            build=BuildConfig(scheme="MyLib"),
            extractors=["symbol_index_swift"],
        )
        assert recipe.build.workspace is None
        assert recipe.build.project is None


# ---------------------------------------------------------------------------
# A1.3 — Invalid/unsafe root paths
# ---------------------------------------------------------------------------


class TestUnsafePaths:
    def test_reject_traversal_in_source_root(self) -> None:
        with pytest.raises(ValidationError, match="path traversal.*source_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["../../etc/passwd"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_traversal_in_dependency_root(self) -> None:
        with pytest.raises(ValidationError, match="path traversal.*dependency_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                dependency_roots=["deps/../../../secrets"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_traversal_in_scip_path(self) -> None:
        with pytest.raises(ValidationError, match="path traversal.*scip_path"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="../outside/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_traversal_in_workspace(self) -> None:
        with pytest.raises(ValidationError, match="path traversal.*build.workspace"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="xcode_workspace",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(
                    workspace="../other/Wallet.xcworkspace",
                    scheme="Dev",
                ),
                extractors=["symbol_index_swift"],
            )

    def test_reject_traversal_in_derived_data(self) -> None:
        with pytest.raises(
            ValidationError, match="path traversal.*build.derived_data_path"
        ):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(
                    scheme="Bad",
                    derived_data_path="../DerivedData",
                ),
                extractors=["symbol_index_swift"],
            )

    def test_reject_bare_dotdot_root(self) -> None:
        with pytest.raises(ValidationError, match="path traversal.*source_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=[".."],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_traversal_in_generated_root(self) -> None:
        with pytest.raises(ValidationError, match="path traversal.*generated_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                generated_roots=["gen/../../escape"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_traversal_in_prepare_step(self) -> None:
        from palace_mcp.smoke.recipe import EnsureConfigFromTemplate

        with pytest.raises(
            ValidationError, match="path traversal.*prepare_steps.template"
        ):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                prepare_steps=[
                    EnsureConfigFromTemplate(
                        template="../../../etc/template",
                        destination="Config.xcconfig",
                    ),
                ],
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )


# ---------------------------------------------------------------------------
# A1.4 — Unsupported build systems
# ---------------------------------------------------------------------------


class TestUnsupportedBuildSystem:
    def test_reject_gradle(self) -> None:
        with pytest.raises(ValidationError, match="build_system"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="gradle",  # type: ignore[arg-type]
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_cmake(self) -> None:
        with pytest.raises(ValidationError, match="build_system"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="cmake",  # type: ignore[arg-type]
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_bazel(self) -> None:
        with pytest.raises(ValidationError, match="build_system"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="bazel",  # type: ignore[arg-type]
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )


# ---------------------------------------------------------------------------
# A1.5 — Empty required lists
# ---------------------------------------------------------------------------


class TestEmptyRequiredLists:
    def test_reject_empty_source_roots(self) -> None:
        with pytest.raises(ValidationError, match="source_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=[],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_empty_extractors(self) -> None:
        with pytest.raises(ValidationError, match="extractors"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=[],
            )
