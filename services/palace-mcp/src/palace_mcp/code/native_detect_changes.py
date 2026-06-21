"""Native detect_changes implementation for Palace-known projects."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from palace_mcp.git.command import (
    ForbiddenGitCommand,
    GitError,
    GitTimeout,
    run_git,
)
from palace_mcp.git.path_resolver import (
    ProjectNotRegistered,
    resolve_registered_project,
)
from palace_mcp.memory.projects import InvalidSlug

logger = logging.getLogger(__name__)

_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_APPROXIDATE_RE = re.compile(
    r"^(?:now|today|yesterday|tomorrow|\d+\s+"
    r"(?:second|minute|hour|day|week|month|year)s?\s+ago)$",
    re.IGNORECASE,
)


class _FallbackToCM:
    pass


FALLBACK_TO_CM = _FallbackToCM()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        result["project"] = project
    return result


def _valid_since(value: str) -> bool:
    candidate = value.strip()
    if not candidate or candidate.startswith("-") or "\x00" in candidate:
        return False
    if _COMMIT_SHA_RE.fullmatch(candidate):
        return True
    if _APPROXIDATE_RE.fullmatch(candidate):
        return True
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


async def _resolve_since_base(repo_path: Path, since: str) -> str:
    candidate = since.strip()
    if _COMMIT_SHA_RE.fullmatch(candidate):
        result = await asyncio.to_thread(
            run_git,
            ["cat-file", "-e", f"{candidate}^{{commit}}"],
            repo_path=repo_path,
            max_stdout_lines=1,
        )
        if result.rc != 0:
            raise GitError(result.rc, result.stderr[:200] or "git cat-file failed")
        return candidate

    result = await asyncio.to_thread(
        run_git,
        ["rev-list", "-n", "1", f"--before={since}", "HEAD"],
        repo_path=repo_path,
        max_stdout_lines=1,
    )
    if result.rc != 0:
        raise GitError(result.rc, result.stderr[:200] or "git rev-list failed")
    return result.stdout.strip() or _EMPTY_TREE


async def _resolve_repo_path(project: str) -> Path:
    from palace_mcp.mcp_server import get_driver
    from palace_mcp.memory.cypher import GET_PROJECT

    driver = get_driver()
    project_node: Any | None = None
    if driver is not None:
        async with driver.session() as session:
            result = await session.run(GET_PROJECT, slug=project)
            row = await result.single()
        if row is not None:
            project_node = row["p"]
    return resolve_registered_project(project, project_node=project_node)


async def native_detect_changes(
    project: str | None = None,
    since: str | None = None,
    **_: Any,
) -> dict[str, Any] | _FallbackToCM:
    if project is None:
        return FALLBACK_TO_CM
    if since is not None and not _valid_since(since):
        return _error("invalid_since", f"invalid since value: {since!r}", project)

    try:
        repo_path = await _resolve_repo_path(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo path for project {project!r}",
            project,
        )

    args = ["diff", "--name-only"]
    try:
        if since is not None:
            args.append(await _resolve_since_base(repo_path, since))
        else:
            args.append("HEAD")
        args.append("--")
        result = await asyncio.to_thread(
            run_git,
            args,
            repo_path=repo_path,
            max_stdout_lines=500,
        )
    except GitTimeout as exc:
        return _error("git_timeout", str(exc), project)
    except ForbiddenGitCommand as exc:
        return _error("forbidden_command", str(exc), project)
    except GitError as exc:
        return _error("git_error", str(exc), project)
    except Exception as exc:  # noqa: BLE001
        logger.exception("native_detect_changes unexpected error")
        return _error("unknown", str(exc), project)

    if result.rc != 0:
        return _error("git_error", result.stderr[:200], project)

    files = [line for line in result.stdout.splitlines() if line]
    return {
        "ok": True,
        "project": project,
        "since": since,
        "files": files,
        "truncated": result.truncated,
    }
