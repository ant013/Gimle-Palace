"""Contract tests for the versioned recipe schema (GIM-839 D0 / A0).

Acceptance:
- Tests reject repo_path inside versioned recipes.
- Tests reject absolute paths in recipe path fields.
- Tests accept repo path only through RuntimeBinding.
- unstoppable-wallet-ios can be represented without hardcoding a home directory.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.smoke.recipe import BuildConfig, EnsureConfigFromTemplate, Recipe


# ---------------------------------------------------------------------------
# Fixtures: UW-iOS recipe (spec §7.1 example)
# ---------------------------------------------------------------------------


def _uw_ios_recipe() -> Recipe:
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
        prepare_steps=[
            EnsureConfigFromTemplate(
                template="Config.template.xcconfig",
                destination="Config.xcconfig",
            ),
        ],
        build=BuildConfig(
            workspace="Wallet.xcworkspace",
            scheme="Development",
            destination="generic/platform=iOS Simulator",
            simulator_arch="auto",
            derived_data_path=".palace-scip-derived-data",
            code_signing_allowed=False,
            package_resolution="locked",
        ),
        extractors=["symbol_index_swift", "dead_code", "embedding_symbol"],
    )


def _swift_package_recipe() -> Recipe:
    return Recipe(
        slug="bitcoin-kit",
        name="bitcoin-kit-ios",
        language="swift",
        build_system="swift_package",
        source_roots=["Sources"],
        dependency_roots=[".build"],
        scip_path="scip/index.scip",
        build=BuildConfig(
            scheme="BitcoinKit",
            package_resolution="locked",
        ),
        extractors=["symbol_index_swift", "dead_code"],
    )


# ---------------------------------------------------------------------------
# A0.1 — UW-iOS representable without hardcoded home directory
# ---------------------------------------------------------------------------


class TestUwIosRepresentable:
    def test_uw_ios_recipe_contains_no_absolute_paths(self) -> None:
        recipe = _uw_ios_recipe()
        assert recipe.slug == "uw-ios-app"
        assert recipe.build.workspace == "Wallet.xcworkspace"
        assert recipe.build.scheme == "Development"

    def test_uw_ios_workspace_not_project(self) -> None:
        recipe = _uw_ios_recipe()
        assert recipe.build_system == "xcode_workspace"
        assert recipe.build.workspace == "Wallet.xcworkspace"
        assert recipe.build.project is None

    def test_swift_package_recipe_valid(self) -> None:
        recipe = _swift_package_recipe()
        assert recipe.slug == "bitcoin-kit"
        assert recipe.build_system == "swift_package"


# ---------------------------------------------------------------------------
# A0.2 — Reject absolute paths in versioned recipes
# ---------------------------------------------------------------------------


class TestRejectAbsolutePaths:
    def test_reject_absolute_source_root(self) -> None:
        with pytest.raises(ValidationError, match="absolute path.*source_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["/Users/someone/Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_absolute_scip_path(self) -> None:
        with pytest.raises(ValidationError, match="absolute path.*scip_path"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="/tmp/scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_absolute_dependency_root(self) -> None:
        with pytest.raises(ValidationError, match="absolute path.*dependency_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                dependency_roots=["/opt/deps"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_absolute_workspace_path(self) -> None:
        with pytest.raises(ValidationError, match="absolute path.*build.workspace"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="xcode_workspace",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(
                    workspace="/Users/dev/Wallet.xcworkspace",
                    scheme="Dev",
                ),
                extractors=["symbol_index_swift"],
            )

    def test_reject_absolute_derived_data_path(self) -> None:
        with pytest.raises(
            ValidationError, match="absolute path.*build.derived_data_path"
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
                    derived_data_path="/tmp/DerivedData",
                ),
                extractors=["symbol_index_swift"],
            )

    def test_reject_absolute_prepare_step_template(self) -> None:
        with pytest.raises(
            ValidationError, match="absolute path.*prepare_steps.template"
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
                        template="/etc/secrets/Config.template.xcconfig",
                        destination="Config.xcconfig",
                    ),
                ],
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_absolute_generated_root(self) -> None:
        with pytest.raises(ValidationError, match="absolute path.*generated_roots"):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                generated_roots=["/tmp/generated"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )


# ---------------------------------------------------------------------------
# A0.3 — Recipe has no repo_path field
# ---------------------------------------------------------------------------


class TestNoRepoPathOnRecipe:
    def test_recipe_has_no_repo_path_attribute(self) -> None:
        recipe = _uw_ios_recipe()
        assert not hasattr(recipe, "repo_path")

    def test_recipe_rejects_repo_path_as_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            Recipe(
                slug="bad-recipe",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
                repo_path="/Users/someone/repos/bad",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# A0.4 — Slug validation
# ---------------------------------------------------------------------------


class TestSlugValidation:
    def test_valid_slug(self) -> None:
        recipe = _swift_package_recipe()
        assert recipe.slug == "bitcoin-kit"

    def test_reject_uppercase_slug(self) -> None:
        with pytest.raises(ValidationError, match="slug"):
            Recipe(
                slug="Bitcoin-Kit",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )

    def test_reject_slug_starting_with_hyphen(self) -> None:
        with pytest.raises(ValidationError, match="slug"):
            Recipe(
                slug="-bitcoin-kit",
                name="bad",
                language="swift",
                build_system="swift_package",
                source_roots=["Sources"],
                scip_path="scip/index.scip",
                build=BuildConfig(scheme="Bad"),
                extractors=["symbol_index_swift"],
            )
