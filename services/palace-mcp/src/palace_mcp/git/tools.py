"""MCP tool handlers for palace.git.*. Spec §4."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from palace_mcp.git.command import (
    ForbiddenGitCommand,
    GitError,
    GitTimeout,
    run_git,
)
from palace_mcp.git.path_resolver import (
    InvalidPath,
    ProjectNotRegistered,
    resolve_project,
    validate_rel_path,
)
from palace_mcp.git.schemas import (
    BinaryFileResponse,
    BlameLine,
    BlameResponse,
    DiffResponse,
    FileStat,
    LogEntry,
    LogResponse,
    LsTreeResponse,
    ShowCommitResponse,
    ShowFileResponse,
    TreeEntry,
)
from palace_mcp.memory.projects import InvalidSlug

logger = logging.getLogger(__name__)

# Ref validation: alphanumeric start, then alphanumeric/._/@/- allowed.
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@\-~^]{0,199}$")

# Per-tool caps
LOG_DEFAULT_N = 20
LOG_CAP_N = 200
SHOW_CAP_LINES = 500
BLAME_CAP_LINES = 400
DIFF_DEFAULT_MAX_LINES = 500
DIFF_CAP_FULL = 2000
DIFF_CAP_STAT = 500
LS_TREE_CAP = 500


def _valid_ref(ref: str) -> bool:
    return bool(_REF_RE.match(ref))


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


# ---------------------------------------------------------------------------
# palace.git.log
# ---------------------------------------------------------------------------


def parse_log(raw: str) -> list[LogEntry]:
    """Parse NULL-delimited `git log --pretty=format:...` output."""
    entries: list[LogEntry] = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\0", 5)
        if len(parts) < 6:
            continue
        sha, short, an, ae, date, subject = parts
        entries.append(
            LogEntry(
                sha=sha,
                short=short,
                author_name=an,
                author_email=ae,
                date=date,
                subject=subject,
            )
        )
    return entries


async def palace_git_log(
    project: str,
    *,
    path: str | None = None,
    ref: str = "HEAD",
    n: int = LOG_DEFAULT_N,
    since: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """Return commit log for `project`. Capped at LOG_CAP_N entries."""
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )

    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)

    resolved_path: str | None = None
    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
            resolved_path = path  # pass relative to `git -C repo_path`
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

    capped_n = min(max(n, 1), LOG_CAP_N)
    args = [
        "log",
        ref,
        "--pretty=format:%H%x00%h%x00%an%x00%ae%x00%aI%x00%s",
        "-n",
        str(capped_n),
    ]
    if since:
        args.append(f"--since={since}")
    if author:
        args.append(f"--author={author}")
    args.append("--")
    if resolved_path:
        args.append(resolved_path)

    try:
        result = run_git(
            args,
            repo_path=repo_path,
            max_stdout_lines=capped_n,
        )
    except GitTimeout as exc:
        return _error("git_timeout", str(exc), project)
    except ForbiddenGitCommand as exc:
        return _error("forbidden_command", str(exc), project)
    except GitError as exc:
        return _error("git_error", str(exc), project)
    except Exception as exc:  # noqa: BLE001
        logger.exception("palace.git.log unexpected error")
        return _error("unknown", str(exc), project)

    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    entries = parse_log(result.stdout)
    resp = LogResponse(
        project=project,
        ref=ref,
        entries=entries,
        truncated=result.truncated,
    )
    logger.info(
        "git.tool.call tool=palace.git.log project=%s duration_ms=%d rc=0 "
        "stdout_bytes=%d truncated=%s",
        project, result.duration_ms, len(result.stdout), result.truncated,
    )
    return resp.model_dump()


# ---------------------------------------------------------------------------
# palace.git.show
# ---------------------------------------------------------------------------


def _scan_for_nul(data: bytes, limit: int = 8192) -> bool:
    return b"\x00" in data[:limit]


def _get_blob_size(repo_path: Any, ref: str, path: str) -> int:
    """Return blob size via `git cat-file -s <ref>:<path>`."""
    result = run_git(
        ["cat-file", "-s", f"{ref}:{path}"],
        repo_path=repo_path,
    )
    if result.rc != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


async def palace_git_show(
    project: str,
    *,
    ref: str,
    path: str | None = None,
) -> dict[str, Any]:
    """Show a commit (path=None) or file at ref (path=<file>)."""
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )

    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)

    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

        # Binary detection via `git cat-file -t <ref>:<path>`.
        spec = f"{ref}:{path}"
        type_result = run_git(
            ["cat-file", "-t", spec],
            repo_path=repo_path,
        )
        obj_type = type_result.stdout.strip() if type_result.rc == 0 else ""

        if obj_type != "blob":
            return _error("invalid_path", f"not a blob: {spec!r}", project)

        # Fetch blob content; scan for NUL to detect binary.
        show_result = run_git(
            ["show", spec],
            repo_path=repo_path,
            max_stdout_lines=None,
            timeout_s=5.0,
        )
        if _scan_for_nul(show_result.stdout.encode("utf-8", errors="replace")):
            size = _get_blob_size(repo_path, ref, path)
            return BinaryFileResponse(
                project=project, ref=ref, path=path, size_bytes=size
            ).model_dump()

        # Text file — cap lines.
        lines = show_result.stdout.splitlines(keepends=True)
        truncated = False
        if len(lines) > SHOW_CAP_LINES:
            lines = lines[:SHOW_CAP_LINES]
            truncated = True
        content = "".join(lines)
        return ShowFileResponse(
            project=project,
            ref=ref,
            path=path,
            content=content,
            lines=len(lines),
            truncated=truncated,
        ).model_dump()

    # Commit mode.
    result = run_git(
        ["show", ref, "--stat", "-p"],
        repo_path=repo_path,
        max_stdout_lines=SHOW_CAP_LINES,
    )
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    parsed = _parse_show_commit(result.stdout)
    return ShowCommitResponse(
        project=project,
        sha=parsed["sha"],
        author_name=parsed["author_name"],
        date=parsed["date"],
        subject=parsed["subject"],
        body=parsed["body"],
        files_changed=parsed["files_changed"],
        diff=parsed["diff"],
        truncated=result.truncated,
    ).model_dump()


def _parse_show_commit(raw: str) -> dict[str, Any]:
    """Parse output of `git show <ref> --stat -p`."""
    lines = raw.splitlines()
    sha = ""
    author_name = ""
    date = ""
    subject = ""
    body_lines: list[str] = []
    stat_files: list[FileStat] = []
    diff_lines: list[str] = []
    i = 0
    if i < len(lines) and lines[i].startswith("commit "):
        sha = lines[i].split(" ", 1)[1].strip()
        i += 1
    while i < len(lines) and lines[i].strip() != "":
        ln = lines[i]
        if ln.startswith("Author:"):
            author_name = ln.split(":", 1)[1].strip().rsplit(" <", 1)[0]
        elif ln.startswith("Date:"):
            date = ln.split(":", 1)[1].strip()
        i += 1
    i += 1  # blank line
    if i < len(lines):
        subject = lines[i].strip()
        i += 1
    while i < len(lines) and not lines[i].startswith(("diff ", "---")):
        body_lines.append(lines[i])
        i += 1
    while i < len(lines):
        ln = lines[i]
        if "|" in ln and ln.strip() and not ln.startswith("diff "):
            parts = ln.split("|", 1)
            path = parts[0].strip()
            rhs = parts[1].strip()
            added = rhs.count("+")
            deleted = rhs.count("-")
            stat_files.append(FileStat(path=path, added=added, deleted=deleted))
        else:
            diff_lines.append(ln)
        i += 1
    return {
        "sha": sha,
        "author_name": author_name,
        "date": date,
        "subject": subject,
        "body": "\n".join(ln for ln in body_lines if ln.strip()),
        "files_changed": stat_files,
        "diff": "\n".join(diff_lines),
    }


# ---------------------------------------------------------------------------
# palace.git.blame
# ---------------------------------------------------------------------------


def parse_blame_porcelain(raw: str) -> list[BlameLine]:
    """Parse `git blame --porcelain` output."""
    lines: list[BlameLine] = []
    commits: dict[str, dict[str, str]] = {}
    current_meta: dict[str, str] = {}
    current_sha: str = ""
    current_lineno: int = 0
    for ln in raw.splitlines():
        if ln.startswith("\t"):
            meta = commits.get(current_sha, current_meta)
            date_iso = ""
            try:
                ts = int(meta.get("author-time", "0"))
                date_iso = datetime.fromtimestamp(
                    ts, tz=timezone.utc
                ).isoformat()
            except ValueError:
                date_iso = ""
            lines.append(
                BlameLine(
                    line_no=current_lineno,
                    sha=current_sha,
                    short=current_sha[:7],
                    author_name=meta.get("author", ""),
                    date=date_iso,
                    content=ln[1:],  # strip leading tab
                )
            )
        elif ln and ln[0].isalnum() and len(ln.split(" ", 1)[0]) == 40:
            parts = ln.split(" ")
            current_sha = parts[0]
            current_lineno = int(parts[2]) if len(parts) >= 3 else 0
            current_meta = commits.setdefault(current_sha, {})
        elif " " in ln:
            key, _, value = ln.partition(" ")
            if current_sha:
                commits[current_sha][key] = value
    return lines


async def palace_git_blame(
    project: str,
    *,
    path: str,
    ref: str = "HEAD",
    line_start: int | None = None,
    line_end: int | None = None,
) -> dict[str, Any]:
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )
    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)
    try:
        validate_rel_path(path, repo_path=repo_path)
    except InvalidPath as exc:
        return _error("invalid_path", str(exc), project)

    args = ["blame", "--porcelain", ref]
    if line_start is not None and line_end is not None:
        args.extend(["-L", f"{line_start},{line_end}"])
    args.extend(["--", path])

    # Each output line is ~5 porcelain lines, cap accordingly.
    raw_line_cap = BLAME_CAP_LINES * 5 if (line_start is None and line_end is None) else None
    result = run_git(args, repo_path=repo_path, max_stdout_lines=raw_line_cap)
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    blame_lines = parse_blame_porcelain(result.stdout)
    truncated = False
    if raw_line_cap is not None and len(blame_lines) > BLAME_CAP_LINES:
        blame_lines = blame_lines[:BLAME_CAP_LINES]
        truncated = True
    return BlameResponse(
        project=project,
        path=path,
        ref=ref,
        lines=blame_lines,
        truncated=truncated,
    ).model_dump()


# ---------------------------------------------------------------------------
# palace.git.diff
# ---------------------------------------------------------------------------


def parse_numstat(raw: str) -> list[FileStat]:
    stats: list[FileStat] = []
    for ln in raw.splitlines():
        if not ln.strip():
            continue
        parts = ln.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        if a == "-" or d == "-":
            stats.append(FileStat(path=path, added=None, deleted=None))
        else:
            try:
                stats.append(
                    FileStat(path=path, added=int(a), deleted=int(d))
                )
            except ValueError:
                continue
    return stats


async def palace_git_diff(
    project: str,
    *,
    ref_a: str,
    ref_b: str,
    path: str | None = None,
    mode: str = "full",
    max_lines: int = DIFF_DEFAULT_MAX_LINES,
) -> dict[str, Any]:
    if mode not in ("full", "stat"):
        return _error("invalid_mode", f"mode must be full|stat, got {mode!r}", project)
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )
    for r, name in [(ref_a, "ref_a"), (ref_b, "ref_b")]:
        if not _valid_ref(r):
            return _error("invalid_ref", f"invalid {name}: {r!r}", project)
    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

    args = ["diff"]
    if mode == "stat":
        args.append("--numstat")
    args.extend([ref_a, ref_b, "--"])
    if path is not None:
        args.append(path)

    cap = min(max_lines, DIFF_CAP_FULL) if mode == "full" else DIFF_CAP_STAT
    result = run_git(args, repo_path=repo_path, max_stdout_lines=cap)
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    if mode == "stat":
        files = parse_numstat(result.stdout)
        return DiffResponse(
            project=project,
            ref_a=ref_a,
            ref_b=ref_b,
            path=path,
            mode="stat",
            diff=None,
            files_stat=files,
            truncated=result.truncated,
        ).model_dump()
    return DiffResponse(
        project=project,
        ref_a=ref_a,
        ref_b=ref_b,
        path=path,
        mode="full",
        diff=result.stdout,
        files_stat=None,
        truncated=result.truncated,
    ).model_dump()


# ---------------------------------------------------------------------------
# palace.git.ls_tree
# ---------------------------------------------------------------------------


def parse_ls_tree(raw: str) -> list[TreeEntry]:
    entries: list[TreeEntry] = []
    for ln in raw.splitlines():
        if not ln:
            continue
        # Format: <mode> <type> <sha>\t<path>
        lhs, _, path = ln.partition("\t")
        parts = lhs.split(" ")
        if len(parts) != 3:
            continue
        mode, typ, sha = parts
        if typ not in ("blob", "tree", "commit"):
            continue
        entries.append(
            TreeEntry(path=path, type=typ, mode=mode, sha=sha)
        )
    return entries


async def palace_git_ls_tree(
    project: str,
    *,
    ref: str = "HEAD",
    path: str | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )
    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)
    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

    args = ["ls-tree"]
    if recursive:
        args.append("-r")
    args.append(ref)
    if path is not None:
        args.extend(["--", path])

    result = run_git(args, repo_path=repo_path, max_stdout_lines=LS_TREE_CAP)
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "not a tree" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    return LsTreeResponse(
        project=project,
        ref=ref,
        path=path,
        recursive=recursive,
        entries=parse_ls_tree(result.stdout),
        truncated=result.truncated,
    ).model_dump()
