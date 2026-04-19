"""Resolve project slug → repo path; validate paths under a repo.

Convention (spec §3.4): inside the container, slug `X` is bind-mounted
at `/repos/X`. The FS is the authority for which projects git tools
can address (spec §3.6).
"""

from __future__ import annotations

import os
from pathlib import Path

from palace_mcp.memory.projects import validate_slug

REPOS_ROOT = Path("/repos")


class ProjectNotRegistered(ValueError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"project not registered: {slug!r}")
        self.slug = slug


class InvalidPath(ValueError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"invalid path {path!r}: {reason}")
        self.path = path
        self.reason = reason


def resolve_project(slug: str, *, repos_root: Path = REPOS_ROOT) -> Path:
    """Resolve slug → absolute repo path. Requires .git/ to exist."""
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


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
