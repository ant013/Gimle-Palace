"""Local file-based snippet provider for semantic search context hydration.

Reads source snippets directly from mounted project repos using
palace_mcp.git.path_resolver for path containment — no ad hoc path logic here.

Security contract:
- file_path is treated as untrusted (persisted from extraction, may be stale).
- Absolute paths are rejected before reaching path_resolver.
- path_resolver.validate_rel_path enforces containment, rejects .., symlinks.
- Byte and line limits cap output to bounded slices.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from palace_mcp.git.path_resolver import (
    InvalidPath,
    PathTraversalDetectedError,
    ProjectNotRegistered,
    resolve_project,
    validate_rel_path,
)

_MAX_SNIPPET_LINES: int = 200
_MAX_SNIPPET_BYTES: int = 16_384

_LANGUAGE_MAP: dict[str, str] = {
    ".swift": "swift",
    ".py": "python",
    ".kt": "kotlin",
    ".java": "java",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".m": "objective-c",
    ".h": "c",
    ".c": "c",
    ".cpp": "cpp",
    ".rs": "rust",
    ".go": "go",
}


@dataclass(frozen=True)
class SnippetResult:
    source: str
    language: str
    start_line: int
    end_line: int
    byte_count: int
    line_count: int
    indexed_commit: str | None = None
    commits_behind_head: int | None = None
    truncated: bool = False
    stale: bool = False


@dataclass(frozen=True)
class FreshnessResult:
    indexed_commit: str | None
    commits_behind_head: int | None
    stale: bool = False
    # True/False once `git status` ran; None when undeterminable (non-git / error).
    # Reported separately from `stale`: a dirty tree at the indexed HEAD is not the
    # same as the index being behind committed HEAD (the operator's symptom — a
    # just-created uncommitted symbol — is dirty=true, stale=false).
    dirty_working_tree: bool | None = None


def resolve_snippet(
    *,
    project: str,
    repo_path: Path | None = None,
    file_path: str | None,
    line_start: int | None,
    line_end: int | None,
    commit_sha: str | None = None,
    repos_root: Path | None = None,
    freshness: FreshnessResult | None = None,
) -> tuple[SnippetResult | None, str | None, str | None]:
    """Read and validate a snippet from the local repo filesystem.

    Returns (result, warning_code, warning_message).
    On success, warning_code and warning_message are None.
    On failure, result is None.
    """
    if not file_path:
        return None, "missing_file_path", "symbol has no persisted file_path"

    # Reject absolute paths before touching the filesystem.
    if file_path.startswith("/"):
        return None, "path_traversal_rejected", f"absolute path rejected: {file_path!r}"

    repo_root = repo_path
    if repo_root is None:
        try:
            repo_root = resolve_project(project, repos_root=repos_root)
        except (ProjectNotRegistered, ValueError):
            return (
                None,
                "project_not_mounted",
                f"project {project!r} not mounted locally",
            )

    try:
        abs_path = validate_rel_path(file_path, repo_path=repo_root)
    except (InvalidPath, PathTraversalDetectedError) as exc:
        return None, "path_traversal_rejected", str(exc)

    freshness_result = freshness or inspect_freshness(repo_root, commit_sha)

    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None, "missing_source_file", f"source file not found: {file_path!r}"
    except OSError as exc:
        return None, "snippet_read_error", str(exc)

    all_lines = text.splitlines()
    total = len(all_lines)

    start = max(1, line_start or 1)
    end = min(total, line_end or total)
    if start > end:
        start = 1
        end = min(total, _MAX_SNIPPET_LINES)

    truncated = False
    if (end - start + 1) > _MAX_SNIPPET_LINES:
        end = start + _MAX_SNIPPET_LINES - 1
        truncated = True

    snippet_lines = all_lines[start - 1 : end]
    source = "\n".join(snippet_lines)

    encoded = source.encode("utf-8")
    if len(encoded) > _MAX_SNIPPET_BYTES:
        # Truncate at UTF-8 boundary to honour byte cap.
        source = encoded[:_MAX_SNIPPET_BYTES].decode("utf-8", errors="ignore")
        truncated = True

    language = _LANGUAGE_MAP.get(abs_path.suffix.lower(), "")
    byte_count = len(source.encode("utf-8"))
    line_count = source.count("\n") + 1 if source else 0

    return (
        SnippetResult(
            source=source,
            language=language,
            start_line=start,
            end_line=start + line_count - 1,
            byte_count=byte_count,
            line_count=line_count,
            indexed_commit=freshness_result.indexed_commit,
            commits_behind_head=freshness_result.commits_behind_head,
            truncated=truncated,
            stale=freshness_result.stale,
        ),
        None,
        None,
    )


def _inspect_commit_freshness(
    repo_root: Path | None, commit_sha: str | None
) -> FreshnessResult:
    """Compare an indexed commit against the repo's current HEAD."""
    if not commit_sha:
        return FreshnessResult(
            indexed_commit=None, commits_behind_head=None, stale=False
        )
    if repo_root is None:
        return FreshnessResult(
            indexed_commit=commit_sha,
            commits_behind_head=None,
            stale=False,
        )
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if head_result.returncode != 0:
            return FreshnessResult(
                indexed_commit=commit_sha,
                commits_behind_head=None,
                stale=False,
            )
        head = head_result.stdout.strip()
        if head == commit_sha:
            return FreshnessResult(
                indexed_commit=commit_sha,
                commits_behind_head=0,
                stale=False,
            )

        behind_result = subprocess.run(
            ["git", "rev-list", "--count", f"{commit_sha}..HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if behind_result.returncode != 0:
            return FreshnessResult(
                indexed_commit=commit_sha,
                commits_behind_head=None,
                stale=True,
            )
        behind = int(behind_result.stdout.strip() or "0")
        return FreshnessResult(
            indexed_commit=commit_sha,
            commits_behind_head=behind,
            stale=behind > 0,
        )
    except Exception:  # noqa: BLE001
        return FreshnessResult(
            indexed_commit=commit_sha,
            commits_behind_head=None,
            stale=False,
        )


def _is_working_tree_dirty(repo_root: Path | None) -> bool | None:
    """True if the working tree has uncommitted *tracked* changes.

    Uses `git status --porcelain --untracked-files=no` (untracked files cannot be
    SCIP-indexed, and `-uall` would walk derived-data dirs at ~40x the cost).
    ~20ms warm. Intentionally uncached: an *unstaged* edit (the operator's exact
    symptom) does not touch `.git/index`, so an index-mtime cache would miss it;
    a TTL cache is the right perf follow-up once semantic dedups per project.
    Returns None when undeterminable (not a git repo, git error/timeout) — never
    raises.
    """
    if repo_root is None:
        return None
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode != 0:
            return None
        return bool(res.stdout.strip())
    except Exception:  # noqa: BLE001
        return None


def inspect_freshness(
    repo_root: Path | None, commit_sha: str | None
) -> FreshnessResult:
    """Index freshness: commit lag (vs HEAD) + working-tree dirty bit.

    Composes the committed-state comparison with a separate, cached working-tree
    dirty check so `0 results + stale:false + dirty_working_tree:false` reads as
    "really none" while a pending edit surfaces as `dirty_working_tree:true`.
    """
    base = _inspect_commit_freshness(repo_root, commit_sha)
    return replace(base, dirty_working_tree=_is_working_tree_dirty(repo_root))
