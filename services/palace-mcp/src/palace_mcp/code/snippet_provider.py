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
    truncated: bool = False
    stale: bool = False


def resolve_snippet(
    *,
    project: str,
    file_path: str | None,
    line_start: int | None,
    line_end: int | None,
    commit_sha: str | None = None,
    repos_root: Path | None = None,
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

    try:
        repo_root = resolve_project(project, repos_root=repos_root)
    except (ProjectNotRegistered, ValueError):
        return None, "project_not_mounted", f"project {project!r} not mounted locally"

    try:
        abs_path = validate_rel_path(file_path, repo_path=repo_root)
    except (InvalidPath, PathTraversalDetectedError) as exc:
        return None, "path_traversal_rejected", str(exc)

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
    stale = _check_stale(repo_root, commit_sha)
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
            truncated=truncated,
            stale=stale,
        ),
        None,
        None,
    )


def _check_stale(repo_root: Path, commit_sha: str | None) -> bool:
    """Return True if commit_sha differs from the current HEAD of the repo."""
    if not commit_sha:
        return False
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False
        head = result.stdout.strip()
        return head != commit_sha
    except Exception:  # noqa: BLE001
        return False
