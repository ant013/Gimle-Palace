"""Hardened subprocess helpers for prune_swift_symbols."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_DEFAULT_ROOTS = (
    "/Users/ant013/Ios",
    "/Users/Shared/Ios",
    "/Users/anton/Ios",
)


def _allowed_roots() -> tuple[Path, ...]:
    raw = os.environ.get("PALACE_ALLOWED_REPO_ROOTS", ":".join(_DEFAULT_ROOTS))
    return tuple(Path(root).resolve() for root in raw.split(":") if root)


def get_git_head_sha(repo_path: Path | str) -> str:
    """Return git HEAD SHA for an allowlisted repo path."""
    resolved = Path(repo_path).resolve()
    allowed = _allowed_roots()
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ValueError(f"repo_path {resolved} not under allowed roots: {allowed}")

    result = subprocess.run(
        ["/usr/bin/git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(resolved),
        shell=False,
        timeout=10,
        check=True,
    )
    return result.stdout.strip()
