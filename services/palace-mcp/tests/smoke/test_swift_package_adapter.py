from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.smoke import (
    RuntimeBinding,
    build_swift_package_invocation,
)
from palace_mcp.smoke.recipe import load_recipe_yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _binding(repo_path: Path) -> RuntimeBinding:
    return RuntimeBinding(
        repo_path=repo_path,
        parent_mount=repo_path.parent,
        mount_name="test",
        mcp_mount_name="test",
        mcp_url="http://localhost:8000/mcp",
    )


def test_build_invocation_locked_resolution_is_default() -> None:
    recipe = load_recipe_yaml(FIXTURES_DIR / "swift_package_recipe.yaml")
    binding = _binding(FIXTURES_DIR)

    invocation = build_swift_package_invocation(recipe, binding)

    assert invocation.cwd == FIXTURES_DIR
    assert not invocation.scip_reused
    assert invocation.command == (
        "swift",
        "build",
        "--target",
        "BitcoinKit",
        "--build-path",
        ".palace-scip-derived-data",
        "--disable-automatic-resolution",
        "-Xswiftc",
        "-index-store-path",
        "-Xswiftc",
        ".palace-scip-derived-data/Index.noindex/DataStore",
    )


def test_build_invocation_automatic_resolution_omits_locked_flag() -> None:
    recipe = load_recipe_yaml(FIXTURES_DIR / "swift_package_recipe.yaml")

    invocation = build_swift_package_invocation(
        recipe, _binding(FIXTURES_DIR), package_resolution="automatic"
    )

    assert "--disable-automatic-resolution" not in invocation.command
    assert "swift" == invocation.command[0]
    assert "build" == invocation.command[1]


def test_scip_reuse_when_existing_index_present(tmp_path: Path) -> None:
    repo_path = tmp_path / "bitcoin-kit-ios"
    repo_path.mkdir()
    scip_dir = repo_path / "scip"
    scip_dir.mkdir()
    (scip_dir / "index.scip").write_bytes(b"\x00" * 128)

    recipe = load_recipe_yaml(FIXTURES_DIR / "swift_package_recipe.yaml")

    invocation = build_swift_package_invocation(recipe, _binding(repo_path))

    assert invocation.scip_reused is True
    assert invocation.command == ()


def test_scip_not_reused_when_index_empty(tmp_path: Path) -> None:
    repo_path = tmp_path / "bitcoin-kit-ios"
    repo_path.mkdir()
    scip_dir = repo_path / "scip"
    scip_dir.mkdir()
    (scip_dir / "index.scip").write_bytes(b"")

    recipe = load_recipe_yaml(FIXTURES_DIR / "swift_package_recipe.yaml")

    invocation = build_swift_package_invocation(recipe, _binding(repo_path))

    assert invocation.scip_reused is False
    assert len(invocation.command) > 0


def test_scip_not_reused_when_index_missing(tmp_path: Path) -> None:
    repo_path = tmp_path / "bitcoin-kit-ios"
    repo_path.mkdir()

    recipe = load_recipe_yaml(FIXTURES_DIR / "swift_package_recipe.yaml")

    invocation = build_swift_package_invocation(recipe, _binding(repo_path))

    assert invocation.scip_reused is False
    assert len(invocation.command) > 0


def test_rejects_wrong_build_system() -> None:
    recipe = load_recipe_yaml(FIXTURES_DIR / "uw_ios_recipe.yaml")

    with pytest.raises(ValueError, match="requires build_system=swift_package"):
        build_swift_package_invocation(recipe, _binding(FIXTURES_DIR))
