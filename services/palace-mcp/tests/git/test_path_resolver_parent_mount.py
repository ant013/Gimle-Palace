"""Tests for parent_mount path resolution in path_resolver (GIM-182 Step 3).

Covers:
- §8.11: legacy /repos/<slug> fallback unchanged
- §8.12: parent_mount resolution to /repos/<mount>/<relative_path>
- §8.21: path traversal prevention on relative_path and parent_mount name
"""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.path_resolver import (
    InvalidPath,
    PathTraversalDetectedError,
    resolve_project_with_parent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path, rel: str) -> Path:
    """Create a fake git repo directory under tmp_path."""
    repo = tmp_path / rel
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir()
    return repo


# ---------------------------------------------------------------------------
# §8.12 — parent mount resolution
# ---------------------------------------------------------------------------


def test_resolve_project_with_parent_basic(tmp_path: Path) -> None:
    """parent_mount='hs', relative_path='EvmKit.Swift' → /repos/hs/EvmKit.Swift."""
    _make_repo(tmp_path, "hs/EvmKit.Swift")

    result = resolve_project_with_parent(
        parent_mount="hs",
        relative_path="EvmKit.Swift",
        repos_root=tmp_path,
    )

    assert result == tmp_path / "hs" / "EvmKit.Swift"


def test_resolve_project_with_parent_nested_relative_path(tmp_path: Path) -> None:
    """Multi-segment relative_path resolves correctly."""
    _make_repo(tmp_path, "hs/a/b/c")

    result = resolve_project_with_parent(
        parent_mount="hs",
        relative_path="a/b/c",
        repos_root=tmp_path,
    )

    assert result == tmp_path / "hs" / "a" / "b" / "c"


def test_resolve_project_with_parent_not_a_directory(tmp_path: Path) -> None:
    """Missing or non-repo path raises ProjectNotRegistered."""
    from palace_mcp.git.path_resolver import ProjectNotRegistered

    with pytest.raises(ProjectNotRegistered):
        resolve_project_with_parent(
            parent_mount="hs",
            relative_path="NoSuchKit",
            repos_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# §8.21 — relative_path traversal prevention
# ---------------------------------------------------------------------------

_TRAVERSAL_RELATIVE_PATHS = [
    "../etc/passwd",
    "../../root",
    "..",
    "sub/../../escape",
    "a/../../../b",
    "/absolute/path",
    "\x00evil",
    ".",
    "",
]


@pytest.mark.parametrize("bad_rel", _TRAVERSAL_RELATIVE_PATHS)
def test_traversal_in_relative_path_is_rejected(bad_rel: str, tmp_path: Path) -> None:
    """Traversal / invalid relative_path must be rejected before filesystem access."""
    with pytest.raises((PathTraversalDetectedError, InvalidPath, ValueError)):
        resolve_project_with_parent(
            parent_mount="hs",
            relative_path=bad_rel,
            repos_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# §8.21 — parent_mount name traversal prevention
# ---------------------------------------------------------------------------

_TRAVERSAL_MOUNT_NAMES = [
    "../etc",
    "../../root",
    "/absolute",
    "..",
    "UPPER",
    "has_underscore",
    "has space",
    "toolongmountname12345",  # > 16 chars
    "",
]


@pytest.mark.parametrize("bad_mount", _TRAVERSAL_MOUNT_NAMES)
def test_traversal_in_parent_mount_name_is_rejected(
    bad_mount: str, tmp_path: Path
) -> None:
    """Invalid parent_mount name must be rejected before filesystem access."""
    with pytest.raises((PathTraversalDetectedError, InvalidPath, ValueError)):
        resolve_project_with_parent(
            parent_mount=bad_mount,
            relative_path="valid/path",
            repos_root=tmp_path,
        )


# ---------------------------------------------------------------------------
# §8.11 — legacy resolution unchanged (no parent_mount path)
# ---------------------------------------------------------------------------


def test_legacy_resolve_project_unchanged(tmp_path: Path) -> None:
    """resolve_project with no parent_mount arg still resolves /repos/<slug>."""
    from palace_mcp.git.path_resolver import resolve_project

    _make_repo(tmp_path, "gimle")

    result = resolve_project("gimle", repos_root=tmp_path)

    assert result == tmp_path / "gimle"
