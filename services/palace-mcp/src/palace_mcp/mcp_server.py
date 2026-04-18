"""MCP server layer for palace-mcp.

Exposes MCP tools via streamable-HTTP transport.
The FastAPI app mounts this at ``/mcp`` and shares the Neo4j driver
through :func:`set_driver`.

Tools registered:
- palace.health.status
- palace.memory.lookup
- palace.memory.health
"""

import logging
import os
import time
from collections.abc import Callable
from typing import Any, Literal, TypeVar

from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver
from pydantic import BaseModel
from starlette.applications import Starlette

from palace_mcp.errors import (
    VALID_ENTITY_TYPES,
    DriverUnavailableError,
    UnknownEntityTypeError,
    handle_tool_error,
)
from palace_mcp.memory.health import get_health
from palace_mcp.memory.lookup import perform_lookup
from palace_mcp.memory.projects import UnknownProjectError
from palace_mcp.memory.schema import HealthResponse as MemoryHealthResponse
from palace_mcp.memory.schema import LookupRequest, LookupResponse

logger = logging.getLogger(__name__)

_mcp = FastMCP("palace", streamable_http_path="/")

# Module-level driver reference — set by FastAPI lifespan before any request.
_driver: AsyncDriver | None = None

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
        "Query Paperclip entities (Issue, Comment, Agent) from the Palace knowledge graph. "
        "Returns matching nodes with one-hop related data (assignee + comments for Issues, "
        "issue + author for Comments). Use palace.health.status to check reachability first. "
        "Optional 'project' scopes results to a specific project group_id; "
        "omit to use the server default (project/gimle)."
    ),
)
async def palace_memory_lookup(
    entity_type: str,
    filters: dict[str, Any] | None = None,
    limit: int = 20,
    order_by: str = "source_updated_at",
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
        resp: MemoryHealthResponse = await get_health(driver)
        return resp.model_dump()
    except Exception as exc:
        handle_tool_error(exc)
