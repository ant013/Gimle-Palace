"""Resolve project slug → repo path; validate paths under a repo.

Convention (spec §3.4): inside the container, slug `X` is bind-mounted
at `/repos/X`. The FS is the authority for which projects git tools
can address (spec §3.6).

GIM-182 §6.5: parent_mount extension — projects registered with
parent_mount="hs", relative_path="EvmKit.Swift" resolve to
/repos/hs/EvmKit.Swift. Legacy /repos/<slug> fallback unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

from palace_mcp.memory.projects import validate_slug

REPOS_ROOT = Path("/repos")

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
    if repos_root is None:
        repos_root = REPOS_ROOT
    validate_slug(slug)
    candidate = (repos_root / slug).resolve()
    if not candidate.is_dir():
        raise ProjectNotRegistered(slug)
    if not (candidate / ".git").exists():
        raise ProjectNotRegistered(slug)
    # Containment check — resilient to slug being "" or surprising.
    if not _is_within(candidate, repos_root.resolve()):
        raise ProjectNotRegistered(slug)
    return candidate


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
