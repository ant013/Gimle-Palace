"""Native search_code: grep over a registered project's on-disk repo.

Replaces the codebase-memory passthrough (whose subprocess index is path-named and
diverges from the canonical Gimle-Repos tree palace ingests). Resolves the repo via
the :Project node's repo_path — the same native layout palace.git.* and the code
graph use — so search_code works by palace slug, against the same tree as every other
native tool.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.git.path_resolver import (
    ProjectNotRegistered,
    resolve_registered_project,
)
from palace_mcp.memory.projects import InvalidSlug

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RESULTS = 200
_RESULT_CAP = 1000
_GREP_TIMEOUT_S = 20
_LINE_TEXT_CAP = 300
# Heavy non-source trees that would otherwise drown real matches.
_EXCLUDE_DIRS = (
    ".git",
    ".build",
    ".palace-scip-derived-data-app",
    ".palace-scip-derived-data",
    "scip",
    "DerivedData",
)


def _error(code: str, message: str, *, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def _resolve_repo_path(project: str) -> Any:
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


async def native_search_code(
    *,
    project: str | None = None,
    pattern: str | None = None,
    query: str | None = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
    case_sensitive: bool = True,
    **_: Any,
) -> dict[str, Any] | object:
    """Grep-like search over `project`'s repo. Returns file_path/line/text matches.

    Falls back to the codebase-memory passthrough only when no project is given.
    """
    if project is None:
        return FALLBACK_TO_CM

    pat = (pattern or query or "").strip()
    if not pat:
        return _error("validation_error", "pattern (or query) is required", project=project)

    try:
        repo_path = await _resolve_repo_path(project)
    except (InvalidSlug, ProjectNotRegistered):
        return _error(
            "project_not_registered",
            f"no resolvable on-disk repo for project {project!r}",
            project=project,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("native_search_code resolve failed: %s", exc)
        return _error("resolve_failed", str(exc), project=project)

    try:
        cap = min(max(int(max_results), 1), _RESULT_CAP)
    except (TypeError, ValueError):
        cap = _DEFAULT_MAX_RESULTS

    grep_bin = shutil.which("grep") or "/usr/bin/grep"
    args = [grep_bin, "-rnIE"]
    if not case_sensitive:
        args.append("-i")
    for d in _EXCLUDE_DIRS:
        args.append(f"--exclude-dir={d}")
    # `--` guards a pattern that begins with '-'; repo_path is a trusted resolved path.
    args += ["-e", pat, "--", str(repo_path)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_GREP_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        return _error("timeout", f"search timed out after {_GREP_TIMEOUT_S}s", project=project)
    except Exception as exc:  # pragma: no cover - defensive
        return _error("grep_failed", str(exc), project=project)

    # grep exit: 0 = matches, 1 = no matches, >1 = error.
    if proc.returncode not in (0, 1):
        return _error(
            "grep_error",
            (stderr.decode(errors="replace")[:200] or "grep failed"),
            project=project,
        )

    base = str(repo_path).rstrip("/")
    results: list[dict[str, Any]] = []
    truncated = False
    for line in stdout.decode(errors="replace").splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        fpath, lineno, text = parts
        rel = fpath[len(base):].lstrip("/") if fpath.startswith(base) else fpath
        results.append(
            {
                "file_path": rel,
                "line": int(lineno) if lineno.isdigit() else None,
                "text": text[:_LINE_TEXT_CAP],
            }
        )
        if len(results) >= cap:
            truncated = True
            break

    return {
        "ok": True,
        "project": project,
        "pattern": pat,
        "results": results,
        "total": len(results),
        "truncated": truncated,
    }
