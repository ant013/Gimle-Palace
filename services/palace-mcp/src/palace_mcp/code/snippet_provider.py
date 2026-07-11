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
from dataclasses import dataclass
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
    total_lines: int = 0
    truncated_lines: int = 0
    truncated_reason: str | None = None
    indexed_commit: str | None = None
    commits_behind_head: int | None = None
    truncated: bool = False
    stale: bool = False


@dataclass(frozen=True)
class FreshnessResult:
    indexed_commit: str | None
    commits_behind_head: int | None
    stale: bool = False


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
    max_lines: int | None = None,
    max_bytes: int | None = None,
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

    line_cap = max_lines if max_lines is not None else _MAX_SNIPPET_LINES
    byte_cap = max_bytes if max_bytes is not None else _MAX_SNIPPET_BYTES

    all_lines = text.splitlines()
    total = len(all_lines)

    truncated = False
    truncated_reason: str | None = None
    truncated_lines = 0

    if total == 0:
        # Empty file: no inverted range, no truncation.
        return (
            SnippetResult(
                source="",
                language=_LANGUAGE_MAP.get(abs_path.suffix.lower(), ""),
                start_line=1,
                end_line=0,
                byte_count=0,
                line_count=0,
                total_lines=0,
                indexed_commit=freshness_result.indexed_commit,
                commits_behind_head=freshness_result.commits_behind_head,
                stale=freshness_result.stale,
            ),
            None,
            None,
        )

    start = max(1, line_start or 1)
    end = min(total, line_end or total)
    if start > end:
        start = 1
        end = min(total, line_cap)

    if (end - start + 1) > line_cap:
        truncated_lines = (end - start + 1) - line_cap
        end = start + line_cap - 1
        truncated = True
        truncated_reason = "lines"

    range_lines = end - start + 1
    snippet_lines = all_lines[start - 1 : end]
    source = "\n".join(snippet_lines)

    encoded = source.encode("utf-8")
    if len(encoded) > byte_cap:
        # Truncate at UTF-8 boundary to honour byte cap.
        source = encoded[:byte_cap].decode("utf-8", errors="ignore")
        truncated = True
        if truncated_reason is None:
            truncated_reason = "bytes"

    language = _LANGUAGE_MAP.get(abs_path.suffix.lower(), "")
    byte_count = len(source.encode("utf-8"))
    line_count = source.count("\n") + 1 if source else 0
    if truncated_reason == "bytes":
        truncated_lines = max(truncated_lines, range_lines - line_count)

    return (
        SnippetResult(
            source=source,
            language=language,
            start_line=start,
            end_line=start + line_count - 1 if line_count else start - 1,
            byte_count=byte_count,
            line_count=line_count,
            total_lines=total,
            truncated_lines=truncated_lines,
            truncated_reason=truncated_reason,
            indexed_commit=freshness_result.indexed_commit,
            commits_behind_head=freshness_result.commits_behind_head,
            truncated=truncated,
            stale=freshness_result.stale,
        ),
        None,
        None,
    )


def inspect_freshness(
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
