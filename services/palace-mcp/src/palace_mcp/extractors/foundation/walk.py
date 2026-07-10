"""Shared repository-walker for palace-mcp extractors (GIM-348).

Two public entry points:
  - walk_repo()        — os.walk-based generator with upfront dir pruning
  - should_skip_path() — predicate for pygit2/tree-based walkers
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path

DEFAULT_STOP_DIRS: frozenset[str] = frozenset(
    {
        ".build",
        ".git",
        ".gradle",
        ".idea",
        ".kotlin",
        ".mypy_cache",
        ".pytest_cache",
        ".swiftpm",
        ".tantivy",
        ".venv",
        "__MACOSX",
        "__pycache__",
        "build",
        "Carthage",
        "DerivedData",
        "dist",
        "node_modules",
        "Pods",
        "SourcePackages",
        "target",
        "vendor",
    }
)

DEFAULT_STOP_PREFIXES: tuple[str, ...] = (
    ".palace-xcb-",
    ".palace-scip-",
)


def should_skip_path(
    parts: list[str] | tuple[str, ...],
    *,
    extra_excludes: frozenset[str] = frozenset(),
    extra_prefixes: tuple[str, ...] = (),
    exclude_globs: frozenset[str] = frozenset(),
) -> bool:
    """Return True if any path component belongs to a stop-list directory.

    Designed for tree walkers that don't use os.walk (e.g., pygit2).
    """
    stop_dirs = DEFAULT_STOP_DIRS | extra_excludes
    stop_prefixes = DEFAULT_STOP_PREFIXES + extra_prefixes
    for part in parts:
        if part in stop_dirs:
            return True
        if any(part.startswith(prefix) for prefix in stop_prefixes):
            return True
    if exclude_globs and is_repo_relative_path_excluded(
        Path(*parts).as_posix(),
        exclude_globs=exclude_globs,
    ):
        return True
    return False


def project_exclude_globs(settings: object, project_slug: str) -> frozenset[str]:
    configured = getattr(settings, "palace_project_exclude_globs", {}) or {}
    if not isinstance(configured, dict):
        return frozenset()
    raw_patterns = configured.get(project_slug) or []
    if not isinstance(raw_patterns, list):
        return frozenset()
    return frozenset(str(pattern) for pattern in raw_patterns if str(pattern).strip())


def is_repo_relative_path_excluded(
    relative_path: str | Path,
    *,
    exclude_globs: frozenset[str],
) -> bool:
    path = _normalize_repo_relative_path(relative_path)
    return any(_matches_repo_relative_glob(path, pattern) for pattern in exclude_globs)


def walk_repo(
    root: Path,
    *,
    suffixes: frozenset[str] | None = None,
    extra_excludes: frozenset[str] = frozenset(),
    extra_prefixes: tuple[str, ...] = (),
    exclude_globs: frozenset[str] = frozenset(),
) -> Iterator[Path]:
    """Yield regular files under *root*, pruning stop-list directories before descent.

    Uses os.walk with in-place dirnames[:] mutation so excluded subtrees are
    never traversed — O(relevant files), not O(all files).

    Args:
        root: Repository root path.
        suffixes: If provided, only yield files whose suffix is in this set.
        extra_excludes: Additional directory names to prune (additive to DEFAULT_STOP_DIRS).
        extra_prefixes: Additional directory name prefixes to prune (additive to DEFAULT_STOP_PREFIXES).
        exclude_globs: Repo-relative glob patterns anchored at root.
    """
    stop_dirs = DEFAULT_STOP_DIRS | extra_excludes
    stop_prefixes = DEFAULT_STOP_PREFIXES + extra_prefixes

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune in-place — os.walk will not descend into removed entries.
        dirnames[:] = [
            d
            for d in dirnames
            if d not in stop_dirs
            and not any(d.startswith(pfx) for pfx in stop_prefixes)
            and not is_repo_relative_path_excluded(
                Path(dirpath, d).relative_to(root),
                exclude_globs=exclude_globs,
            )
        ]
        for filename in filenames:
            if suffixes is not None and Path(filename).suffix not in suffixes:
                continue
            full = Path(dirpath) / filename
            if not full.is_file():
                continue
            if is_repo_relative_path_excluded(
                full.relative_to(root),
                exclude_globs=exclude_globs,
            ):
                continue
            yield full


def _normalize_repo_relative_path(relative_path: str | Path) -> str:
    return Path(relative_path).as_posix().lstrip("./")


def _matches_repo_relative_glob(path: str, pattern: str) -> bool:
    normalized_pattern = _normalize_repo_relative_path(pattern)
    if fnmatchcase(path, normalized_pattern):
        return True
    if normalized_pattern.endswith("/**"):
        root = normalized_pattern[:-3].rstrip("/")
        return path == root or path.startswith(f"{root}/")
    return False
