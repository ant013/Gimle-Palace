"""Serving-checkout git identity for health endpoints.

F5 (Sprint-1 reliability, GIM-RUNTIME-ID): `git_sha` used to be the
PALACE_GIT_SHA env label ("native-dev") regardless of the checkout actually
serving requests — builds could not be tied to source commits. This resolves
the REAL sha of the checkout palace_mcp is imported from.

Contract (silent-failure hardened):
- resolution failure never masquerades as a sha: `git_sha` is None and
  `git_sha_source`/`git_sha_error` say why; the env label is exposed
  separately as `git_sha_label`, never as the sha value;
- short-TTL cache, NOT resolve-once: live deploys hot-patch files into the
  running worktree, so `git_dirty` + `git_sha_resolved_at` must track reality;
- worktree-safe: `rev-parse --show-toplevel` handles the `.git`-FILE layout
  (the production server runs from a detached worktree).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from palace_mcp.git.command import (
    ForbiddenGitCommand,
    GitError,
    GitTimeout,
    run_git,
)

logger = logging.getLogger(__name__)

_TTL_S = 60.0
_cache: tuple[float, "GitIdentity"] | None = None


@dataclass(frozen=True)
class GitIdentity:
    git_sha: str | None
    git_sha_source: str  # "resolved" | "env" | "unknown"
    git_sha_label: str | None
    git_dirty: bool | None
    git_sha_resolved_at: str | None
    git_sha_error: str | None
    source_checkout: str | None


def resolve_git_identity(*, ttl_s: float = _TTL_S) -> GitIdentity:
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < ttl_s:
        return _cache[1]
    identity = _resolve()
    _cache = (now, identity)
    return identity


def _resolve() -> GitIdentity:
    env_label = os.environ.get("PALACE_GIT_SHA")
    pkg_dir = Path(__file__).resolve().parent
    resolved_at = datetime.now(timezone.utc).isoformat()
    try:
        # Caps are N+1 for expected N lines: run_git flags truncated when
        # output EXACTLY fills the cap (see PR #507).
        top = run_git(
            ["rev-parse", "--show-toplevel"], repo_path=pkg_dir, max_stdout_lines=2
        )
        checkout = top.stdout.strip()
        if top.rc != 0 or not checkout:
            raise GitError(rc=top.rc, stderr=top.stderr[:200])
        head = run_git(
            ["rev-parse", "HEAD"], repo_path=Path(checkout), max_stdout_lines=2
        )
        sha = head.stdout.strip()
        if head.rc != 0 or not sha:
            raise GitError(rc=head.rc, stderr=head.stderr[:200])
        # Dirty = any porcelain output. Cap reached (truncated) still means
        # output existed -> dirty; a clean tree produces zero lines.
        status = run_git(
            ["status", "--porcelain"], repo_path=Path(checkout), max_stdout_lines=2
        )
        dirty: bool | None = bool(status.stdout.strip()) if status.rc == 0 else None
        return GitIdentity(
            git_sha=sha,
            git_sha_source="resolved",
            git_sha_label=env_label,
            git_dirty=dirty,
            git_sha_resolved_at=resolved_at,
            git_sha_error=None,
            source_checkout=checkout,
        )
    except (GitError, GitTimeout, ForbiddenGitCommand, OSError) as exc:
        logger.debug("git identity resolution failed: %s", exc)
        return GitIdentity(
            git_sha=None,
            git_sha_source="env" if env_label else "unknown",
            git_sha_label=env_label or "unknown",
            git_dirty=None,
            git_sha_resolved_at=resolved_at,
            git_sha_error=str(exc)[:200],
            source_checkout=None,
        )
