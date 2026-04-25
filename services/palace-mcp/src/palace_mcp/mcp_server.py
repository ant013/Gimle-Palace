"""MCP server layer for palace-mcp.

Exposes MCP tools via streamable-HTTP transport.
The FastAPI app mounts this at ``/mcp`` and shares the Neo4j driver
through :func:`set_driver`.

Tools registered:
- palace.health.status
- palace.memory.lookup
- palace.memory.health
- palace.git.log
- palace.git.show
- palace.git.blame
- palace.git.diff
- palace.git.ls_tree
- palace.code.search_graph
- palace.code.trace_call_path
- palace.code.query_graph
- palace.code.detect_changes
- palace.code.get_architecture
- palace.code.get_code_snippet
- palace.code.search_code
- palace.code.manage_adr  [DISABLED — returns directive error]
"""

import logging
import os
import time
from collections.abc import Callable
from typing import Any, Literal, TypeVar

from graphiti_core import Graphiti
from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver
from pydantic import BaseModel
from starlette.applications import Starlette

from palace_mcp.code_router import register_code_tools
from palace_mcp.extractors import registry as _extractor_registry
from palace_mcp.extractors.runner import run_extractor as _run_extractor
from palace_mcp.errors import (
    VALID_ENTITY_TYPES,
    DriverUnavailableError,
    UnknownEntityTypeError,
    handle_tool_error,
)
from palace_mcp.git.tools import (
    palace_git_blame,
    palace_git_diff,
    palace_git_log,
    palace_git_ls_tree,
    palace_git_show,
)
from palace_mcp.memory.health import get_health
from palace_mcp.memory.lookup import perform_lookup
from palace_mcp.memory.project_tools import (
    get_project_overview,
    list_projects,
    register_project,
)
from palace_mcp.memory.projects import InvalidSlug, UnknownProjectError
from palace_mcp.memory.schema import HealthResponse as MemoryHealthResponse
from palace_mcp.memory.schema import LookupRequest, LookupResponse, ProjectInfo

logger = logging.getLogger(__name__)

_mcp = FastMCP("palace", streamable_http_path="/")

# Module-level driver reference — set by FastAPI lifespan before any request.
_driver: AsyncDriver | None = None

# Module-level Graphiti instance — set by FastAPI lifespan before any request.
_graphiti: Graphiti | None = None

# Default group_id for lookup scoping — set by lifespan from Settings.
_default_group_id: str = "project/gimle"


def set_default_group_id(group_id: str) -> None:
    """Called from FastAPI lifespan to share the default group_id with MCP tools."""
    global _default_group_id  # noqa: PLW0603
    _default_group_id = group_id


# Server start time for uptime_seconds calculation.
_start_time: float = time.monotonic()

# Pattern #21: track registered tool names for startup uniqueness assertion.
_registered_tool_names: list[str] = []


def assert_unique_tool_names(names: list[str]) -> None:
    """Pattern #21: crash immediately on duplicate tool name.

    Call at boot (inside build_mcp_asgi_app) so silent shadowing is
    impossible. A duplicate is a programmer error — fail loud and early.
    """
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise RuntimeError(
                f"Duplicate MCP tool name detected at startup: {name!r}. "
                "Each tool must have a unique name. Crash is intentional."
            )
        seen.add(name)


class HealthStatusResponse(BaseModel):
    neo4j: Literal["reachable", "unreachable"]
    git_sha: str
    uptime_seconds: int


def set_driver(driver: AsyncDriver) -> None:
    """Called from FastAPI lifespan to share the Neo4j driver with MCP tools."""
    global _driver  # noqa: PLW0603
    _driver = driver


def set_graphiti(graphiti: Graphiti) -> None:
    """Called from FastAPI lifespan to share the Graphiti instance with MCP tools."""
    global _graphiti  # noqa: PLW0603
    _graphiti = graphiti


def build_mcp_asgi_app() -> Starlette:
    """Return the MCP streamable-HTTP ASGI app for mounting.

    Pattern #21: asserts all registered tool names are unique before
    returning the app. Crashes immediately on duplicate.
    """
    assert_unique_tool_names(_registered_tool_names)
    return _mcp.streamable_http_app()


_F = TypeVar("_F", bound=Callable[..., Any])


def _tool(name: str, description: str) -> Callable[[_F], _F]:
    """Wrapper around @_mcp.tool that tracks names for Pattern #21 dedup check."""
    _registered_tool_names.append(name)
    return _mcp.tool(name=name, description=description)  # type: ignore[return-value]


@_tool(
    name="palace.health.status",
    description="Return Neo4j reachability, git SHA, and server uptime.",
)
async def palace_health_status() -> HealthStatusResponse:
    """Check Palace service health: Neo4j connectivity, git revision, uptime."""
    neo4j_status: Literal["reachable", "unreachable"] = "unreachable"
    if _driver is not None:
        try:
            await _driver.verify_connectivity()
            neo4j_status = "reachable"
        except Exception as exc:
            logger.warning("MCP palace.health.status neo4j check failed: %s", exc)
            neo4j_status = "unreachable"

    return HealthStatusResponse(
        neo4j=neo4j_status,
        git_sha=os.environ.get("PALACE_GIT_SHA", "unknown"),
        uptime_seconds=int(time.monotonic() - _start_time),
    )


@_tool(
    name="palace.memory.lookup",
    description=(
        "Query Graphiti entities (Episode, Symbol, File, Module, etc.) from the Palace knowledge graph. "
        "Returns matching nodes with metadata. Use palace.memory.health to check reachability first. "
        "Optional 'project' scopes results to a specific project group_id; "
        "omit to use the server default (project/gimle)."
    ),
)
async def palace_memory_lookup(
    entity_type: str,
    filters: dict[str, Any] | None = None,
    limit: int = 20,
    order_by: str = "created_at",
    project: str | None = None,
) -> dict[str, Any]:
    """Look up Paperclip entities from the Neo4j knowledge graph."""
    driver = _driver
    if driver is None:
        handle_tool_error(DriverUnavailableError("Neo4j driver not initialised"))
    if entity_type not in VALID_ENTITY_TYPES:
        handle_tool_error(UnknownEntityTypeError(entity_type))
    try:
        req = LookupRequest(
            entity_type=entity_type,
            project=project,
            filters=filters or {},
            limit=limit,
            order_by=order_by,
        )
        resp: LookupResponse = await perform_lookup(driver, req, _default_group_id)
        return resp.model_dump()
    except UnknownProjectError as exc:
        return {"ok": False, "error": "unknown_project", "message": str(exc)}
    except Exception as exc:
        handle_tool_error(exc)


@_tool(
    name="palace.memory.health",
    description=(
        "Return Neo4j entity counts (Issue/Comment/Agent) and the latest ingest run metadata. "
        "Use to verify data freshness before running palace.memory.lookup."
    ),
)
async def palace_memory_health() -> dict[str, Any]:
    """Return knowledge-graph health: entity counts and last ingest run."""
    driver = _driver
    if driver is None:
        handle_tool_error(DriverUnavailableError("Neo4j driver not initialised"))
    try:
        resp: MemoryHealthResponse = await get_health(
            driver, default_group_id=_default_group_id
        )
        return resp.model_dump()
    except Exception as exc:
        handle_tool_error(exc)


@_tool(
    name="palace.memory.register_project",
    description=(
        "Register a new project namespace in the Palace knowledge graph. "
        "Creates or updates a :Project node with the given slug, name, and tags. "
        "Idempotent — safe to call multiple times; source_created_at is preserved."
    ),
)
async def palace_memory_register_project(
    slug: str,
    name: str,
    tags: list[str] | None = None,
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
) -> dict[str, Any]:
    """Register or update a project in the knowledge graph."""
    driver = _driver
    if driver is None:
        handle_tool_error(DriverUnavailableError("Neo4j driver not initialised"))
    try:
        info: ProjectInfo = await register_project(
            driver,
            slug=slug,
            name=name,
            tags=list(tags or []),
            language=language,
            framework=framework,
            repo_url=repo_url,
        )
        return info.model_dump()
    except InvalidSlug as exc:
        return {
            "ok": False,
            "error_code": "invalid_slug",
            "message": str(exc),
        }
    except Exception as exc:
        handle_tool_error(exc)


@_tool(
    name="palace.memory.list_projects",
    description=(
        "List all registered projects in the Palace knowledge graph. "
        "Returns project slugs, names, and tags ordered alphabetically."
    ),
)
async def palace_memory_list_projects() -> list[dict[str, Any]]:
    """Return all registered :Project nodes."""
    driver = _driver
    if driver is None:
        handle_tool_error(DriverUnavailableError("Neo4j driver not initialised"))
    try:
        infos: list[ProjectInfo] = await list_projects(driver)
        return [i.model_dump() for i in infos]
    except Exception as exc:
        handle_tool_error(exc)


@_tool(
    name="palace.memory.get_project_overview",
    description=(
        "Return detailed overview of a single project including entity counts and last ingest metadata. "
        "Use palace.memory.list_projects to discover available project slugs."
    ),
)
async def palace_memory_get_project_overview(slug: str) -> dict[str, Any]:
    """Return a project overview with entity counts and ingest metadata."""
    driver = _driver
    if driver is None:
        handle_tool_error(DriverUnavailableError("Neo4j driver not initialised"))
    try:
        info: ProjectInfo = await get_project_overview(driver, slug=slug)
        return info.model_dump()
    except UnknownProjectError as exc:
        return {"ok": False, "error": "unknown_project", "message": str(exc)}
    except Exception as exc:
        handle_tool_error(exc)


# ---------------------------------------------------------------------------
# palace.ingest.* — extractor pipeline tools
# ---------------------------------------------------------------------------


@_tool(
    name="palace.ingest.run_extractor",
    description=(
        "Run a named extractor against a registered project. Writes nodes/edges "
        "scoped by group_id. Creates :IngestRun tracking. Returns run_id + "
        "duration_ms + nodes_written + edges_written on success, or error_code "
        "envelope on failure. Default timeout 300s per run."
    ),
)
async def _palace_ingest_run_extractor(name: str, project: str) -> dict[str, Any]:
    driver = _driver
    if driver is None:
        handle_tool_error(DriverUnavailableError("Neo4j driver not initialised"))
    graphiti = _graphiti
    if graphiti is None:
        handle_tool_error(DriverUnavailableError("Graphiti not initialised"))
    return await _run_extractor(
        name=name, project=project, driver=driver, graphiti=graphiti
    )


@_tool(
    name="palace.ingest.list_extractors",
    description=(
        "List registered extractors with their descriptions. Discovery endpoint "
        "so clients don't hardcode extractor names."
    ),
)
async def _palace_ingest_list_extractors() -> dict[str, Any]:
    extractors = [
        {"name": e.name, "description": e.description}
        for e in _extractor_registry.list_all()
    ]
    return {"ok": True, "extractors": extractors}


# ---------------------------------------------------------------------------
# palace.git.* — read-only git tools
# ---------------------------------------------------------------------------


@_tool(
    name="palace.git.log",
    description=(
        "Return commit history for a mounted project repo. "
        "Use palace.git.show to inspect a specific commit SHA or file at a ref. "
        "project: slug of a bind-mounted repo (e.g. 'gimle'). "
        "ref: branch/tag/SHA (default HEAD). n: max entries (capped at 200). "
        "path: optional file filter. since: ISO date filter. author: author filter."
    ),
)
async def _palace_git_log(
    project: str,
    ref: str = "HEAD",
    n: int = 20,
    path: str | None = None,
    since: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    return await palace_git_log(
        project, ref=ref, n=n, path=path, since=since, author=author
    )


@_tool(
    name="palace.git.show",
    description=(
        "Show a commit's diff+metadata (path omitted) or a file's content at a ref (path provided). "
        "Use palace.git.log to find commit SHAs. "
        "project: slug of a bind-mounted repo. ref: branch/tag/SHA. "
        "path: relative file path within the repo (omit for commit mode)."
    ),
)
async def _palace_git_show(
    project: str,
    ref: str,
    path: str | None = None,
) -> dict[str, Any]:
    return await palace_git_show(project, ref=ref, path=path)


@_tool(
    name="palace.git.blame",
    description=(
        "Return per-line blame annotation for a file. "
        "Use palace.git.show to view file content first. "
        "project: slug of a bind-mounted repo. path: relative file path. "
        "ref: branch/tag/SHA (default HEAD). "
        "line_start/line_end: optional 1-based line range."
    ),
)
async def _palace_git_blame(
    project: str,
    path: str,
    ref: str = "HEAD",
    line_start: int | None = None,
    line_end: int | None = None,
) -> dict[str, Any]:
    return await palace_git_blame(
        project, path=path, ref=ref, line_start=line_start, line_end=line_end
    )


@_tool(
    name="palace.git.diff",
    description=(
        "Show diff between two refs. mode='full' returns unified diff text; "
        "mode='stat' returns per-file added/deleted counts (faster). "
        "Use palace.git.log to find ref SHAs. "
        "project: slug of a bind-mounted repo. ref_a/ref_b: refs to compare. "
        "path: optional file filter. max_lines: cap for full mode (default 500, max 2000)."
    ),
)
async def _palace_git_diff(
    project: str,
    ref_a: str,
    ref_b: str,
    path: str | None = None,
    mode: str = "full",
    max_lines: int = 500,
) -> dict[str, Any]:
    return await palace_git_diff(
        project, ref_a=ref_a, ref_b=ref_b, path=path, mode=mode, max_lines=max_lines
    )


@_tool(
    name="palace.git.ls_tree",
    description=(
        "List files and directories in a repo at a given ref. "
        "recursive=true traverses all subdirectories (use for full-tree discovery). "
        "project: slug of a bind-mounted repo. ref: branch/tag/SHA (default HEAD). "
        "path: optional subtree prefix. recursive: whether to recurse (default false)."
    ),
)
async def _palace_git_ls_tree(
    project: str,
    ref: str = "HEAD",
    path: str | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    return await palace_git_ls_tree(project, ref=ref, path=path, recursive=recursive)


# ---------------------------------------------------------------------------
# palace.code.* — codebase-memory pass-through tools
# ---------------------------------------------------------------------------

register_code_tools(_tool, _mcp)
