from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from palace_mcp.smoke import (
    BuildConfig,
    Recipe,
    RuntimeBinding,
    apply_prepare_steps,
    build_xcode_workspace_invocation,
    resolve_simulator_arch,
)
from palace_mcp.smoke.recipe import load_recipe_yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_TEMPLATE_REL = "Unstoppable/Unstoppable/Configuration/Config.template.xcconfig"
_DEST_REL = "Unstoppable/Unstoppable/Configuration/Config.xcconfig"


def _binding(repo_path: Path) -> RuntimeBinding:
    return RuntimeBinding(
        repo_path=repo_path,
        parent_mount=repo_path.parent,
        mount_name="test",
        mcp_url="http://localhost:8000/mcp",
    )


def test_build_invocation_uses_workspace_and_locked_package_flags() -> None:
    repo_path = FIXTURES_DIR
    recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")

    invocation = build_xcode_workspace_invocation(
        recipe,
        _binding(repo_path),
        host_machine="arm64",
    )

    assert invocation.cwd == repo_path
    assert invocation.command == (
        "xcrun",
        "xcodebuild",
        "-workspace",
        "Wallet.xcworkspace",
        "-scheme",
        "Development",
        "-destination",
        "generic/platform=iOS Simulator",
        "-derivedDataPath",
        ".palace-scip-derived-data",
        "-disableAutomaticPackageResolution",
        "-onlyUsePackageVersionsFromResolvedFile",
        "-IDEIndexDisable=NO",
        "-IDEBuildLocationStyle=Custom",
        "ARCHS=arm64",
        "CODE_SIGNING_ALLOWED=NO",
        "CODE_SIGNING_REQUIRED=NO",
        "build",
    )
    assert "-project" not in invocation.command


def test_build_invocation_automatic_resolution_omits_locked_flags() -> None:
    recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")

    invocation = build_xcode_workspace_invocation(
        recipe,
        _binding(FIXTURES_DIR),
        host_machine="x86_64",
        package_resolution="automatic",
    )

    assert "-disableAutomaticPackageResolution" not in invocation.command
    assert "-onlyUsePackageVersionsFromResolvedFile" not in invocation.command
    assert "ARCHS=x86_64" in invocation.command


def test_explicit_simulator_arch_wins_over_host_machine() -> None:
    recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")
    recipe = recipe.model_copy(
        update={"build": recipe.build.model_copy(update={"simulator_arch": "x86_64"})}
    )

    assert resolve_simulator_arch(recipe, host_machine="arm64") == "x86_64"


def test_apply_prepare_steps_copies_template_when_missing(tmp_path: Path) -> None:
    repo_path = tmp_path / "unstoppable-wallet-ios"
    template_path = repo_path / _TEMPLATE_REL
    template_path.parent.mkdir(parents=True)
    template_path.write_text("FROM_TEMPLATE=1\n")
    recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")

    apply_prepare_steps(recipe, _binding(repo_path))

    assert (repo_path / _DEST_REL).read_text() == "FROM_TEMPLATE=1\n"


def test_apply_prepare_steps_does_not_overwrite_existing_destination(
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "unstoppable-wallet-ios"
    template_path = repo_path / _TEMPLATE_REL
    template_path.parent.mkdir(parents=True)
    template_path.write_text("FROM_TEMPLATE=1\n")
    destination = repo_path / _DEST_REL
    destination.write_text("KEEP_ME=1\n")
    recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")

    apply_prepare_steps(recipe, _binding(repo_path))

    assert destination.read_text() == "KEEP_ME=1\n"


def test_recipe_rejects_absolute_workspace_reference() -> None:
    with pytest.raises(ValidationError, match="absolute path.*build.workspace"):
        Recipe(
            slug="uw-ios-app",
            name="unstoppable-wallet-ios",
            language="swift",
            build_system="xcode_workspace",
            source_roots=["Unstoppable"],
            scip_path="scip/index.scip",
            build=BuildConfig(
                workspace="absolute:/Users/dev/Wallet.xcworkspace",
                scheme="Development",
            ),
            extractors=["symbol_index_swift"],
        )
