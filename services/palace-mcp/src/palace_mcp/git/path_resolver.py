"""Resolve project slug → repo path; validate paths under a repo.

Convention (spec §3.4): inside the container, slug `X` is bind-mounted
at `/repos/X`. The FS is the authority for which projects git tools
can address (spec §3.6).

GIM-182 §6.5: parent_mount extension — projects registered with
parent_mount="hs", relative_path="EvmKit.Swift" resolve to
/repos/hs/EvmKit.Swift. Legacy /repos/<slug> fallback unchanged.
"""

from __future__ import annotations

import os
import re
from typing import Any
from pathlib import Path

from palace_mcp.memory.projects import validate_slug

REPOS_ROOT = Path(os.environ.get("PALACE_REPOS_ROOT", "/repos"))

# §6.5 regexes — validated at boundary, before any filesystem access
_PARENT_MOUNT_RE = re.compile(r"^[a-z][a-z0-9-]{0,15}$")
_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")


class ProjectNotRegistered(ValueError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"project not registered: {slug!r}")
        self.slug = slug


class InvalidPath(ValueError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"invalid path {path!r}: {reason}")
        self.path = path
        self.reason = reason


class PathTraversalDetectedError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"path traversal detected: {detail}")
        self.detail = detail


def resolve_project(slug: str, *, repos_root: Path | None = None) -> Path:
    """Resolve slug → absolute repo path. Requires .git/ to exist."""
    return _resolve_project_path(slug, repos_root=repos_root, require_git=True)


def _resolve_project_path(
    slug: str,
    *,
    repos_root: Path | None = None,
    require_git: bool,
) -> Path:
    if repos_root is None:
        repos_root = REPOS_ROOT
    validate_slug(slug)
    candidate = (repos_root / slug).resolve()
    if not candidate.is_dir():
        raise ProjectNotRegistered(slug)
    if require_git and not (candidate / ".git").exists():
        raise ProjectNotRegistered(slug)
    # Containment check — resilient to slug being "" or surprising.
    if not _is_within(candidate, repos_root.resolve()):
        raise ProjectNotRegistered(slug)
    return candidate


def resolve_registered_project(
    slug: str,
    *,
    project_node: Any | None = None,
    repos_root: Path | None = None,
    require_git: bool = True,
) -> Path:
    """Resolve a registered project's on-disk repo path.

    Resolution order:
    1. Explicit absolute repo_path persisted on the Project node.
    2. parent_mount + relative_path sibling-mount layout.
    3. Legacy /repos/<slug> layout.
    """
    if repos_root is None:
        repos_root = REPOS_ROOT
    validate_slug(slug)

    repo_path = _node_value(project_node, "repo_path")
    if repo_path:
        candidate = Path(repo_path)
        if candidate.is_absolute():
            candidate = candidate.resolve()
            if candidate.is_dir() and (
                not require_git or (candidate / ".git").exists()
            ):
                return candidate

    parent_mount = _node_value(project_node, "parent_mount")
    relative_path = _node_value(project_node, "relative_path")
    if parent_mount and relative_path:
        if _PARENT_MOUNT_RE.match(parent_mount) and _RELATIVE_PATH_RE.match(
            relative_path
        ):
            if all(part != ".." for part in relative_path.split("/")):
                mount_root = repos_root.parent / f"{repos_root.name}-{parent_mount}"
                candidate = (mount_root / relative_path).resolve()
                if (
                    candidate.is_dir()
                    and (not require_git or (candidate / ".git").exists())
                    and _is_within(candidate, mount_root.resolve())
                ):
                    return candidate

    return _resolve_project_path(slug, repos_root=repos_root, require_git=require_git)


def validate_rel_path(user_path: str, *, repo_path: Path) -> Path:
    """Validate a user-provided path within `repo_path`.

    - Reject pathspec magic (leading `:`).
    - Reject absolute paths.
    - Reject NUL bytes.
    - Reject traversal or symlink escape outside repo.

    Return the resolved absolute Path on success.
    """
    if not isinstance(user_path, str) or user_path == "":
        raise InvalidPath(user_path, "empty")
    if user_path.startswith(":"):
        raise InvalidPath(user_path, "pathspec magic not allowed")
    if user_path.startswith("/"):
        raise InvalidPath(user_path, "absolute path not allowed")
    if "\x00" in user_path:
        raise InvalidPath(user_path, "nul byte")

    resolved = (repo_path / user_path).resolve()
    repo_resolved = repo_path.resolve()
    if not _is_within(resolved, repo_resolved):
        raise InvalidPath(user_path, "escapes repo root")
    return resolved


def resolve_project_with_parent(
    parent_mount: str,
    relative_path: str,
    *,
    repos_root: Path | None = None,
) -> Path:
    """Resolve a parent-mount project to its absolute repo path.

    parent_mount: short name validated by ^[a-z][a-z0-9-]{0,15}$
    relative_path: path within the mount, validated by ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$

    Container path: repos_root / parent_mount / relative_path.
    Traversal-prevention assert: resolved path must be within repos_root/parent_mount.
    """
    if repos_root is None:
        repos_root = REPOS_ROOT

    if not isinstance(parent_mount, str) or not _PARENT_MOUNT_RE.match(parent_mount):
        raise PathTraversalDetectedError(f"invalid parent_mount name: {parent_mount!r}")
    if not isinstance(relative_path, str) or not _RELATIVE_PATH_RE.match(relative_path):
        raise PathTraversalDetectedError(f"invalid relative_path: {relative_path!r}")
    # Explicit rejection of .. segments — regex allows "." chars but not traversal
    for _part in relative_path.split("/"):
        if _part == "..":
            raise PathTraversalDetectedError(
                f"relative_path contains '..': {relative_path!r}"
            )

    mount_root = (repos_root / parent_mount).resolve()
    candidate = (mount_root / relative_path).resolve()

    # §6.5 traversal-prevention assert
    if not _is_within(candidate, mount_root):
        raise PathTraversalDetectedError(
            f"resolved path {candidate} escapes parent mount {mount_root}"
        )

    if not candidate.is_dir() or not (candidate / ".git").exists():
        raise ProjectNotRegistered(f"{parent_mount}/{relative_path}")

    return candidate


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _node_value(project_node: Any | None, key: str) -> str | None:
    if project_node is None:
        return None
    if hasattr(project_node, "get"):
        value = project_node.get(key)
    else:
        try:
            value = project_node[key]
        except (KeyError, TypeError):
            value = None
    return value if isinstance(value, str) and value else None


def registration_identity_check(
    slug: str,
    *,
    project_node: object | None,
    repos_root: Path | None = None,
) -> str:
    """Cross-check a project's registered repo_path vs its mount layout.

    Returns "ok" | "repo_path_missing" | "path_mismatch" | "unresolved".
    Both sides are symlink-normalized (.resolve()) — this host mounts repos
    through symlink aliases, and naive string comparison would false-positive.
    F3 (Sprint-1 reliability): the hd-wallet-kit defect was repo_path and
    relative_path silently resolving to two different valid repos.
    """
    if repos_root is None:
        repos_root = REPOS_ROOT
    repo_path_value = _node_value(project_node, "repo_path")
    parent_mount = _node_value(project_node, "parent_mount")
    relative_path = _node_value(project_node, "relative_path")

    tier1: Path | None = None
    if repo_path_value:
        candidate = Path(str(repo_path_value))
        if candidate.is_absolute() and candidate.is_dir():
            tier1 = candidate.resolve()

    tier2: Path | None = None
    if (
        parent_mount
        and relative_path
        and _PARENT_MOUNT_RE.match(parent_mount)
        and _RELATIVE_PATH_RE.match(relative_path)
        and all(part != ".." for part in relative_path.split("/"))
    ):
        mount_root = repos_root.parent / f"{repos_root.name}-{parent_mount}"
        candidate = mount_root / relative_path
        if candidate.is_dir():
            tier2 = candidate.resolve()

    if repo_path_value and tier1 is None:
        return "repo_path_missing"
    if tier1 is not None and tier2 is not None:
        return "ok" if tier1 == tier2 else "path_mismatch"
    if tier1 is not None or tier2 is not None:
        return "ok"
    return "unresolved"
