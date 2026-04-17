"""MCP server layer for palace-mcp.

Exposes MCP tools via streamable-HTTP transport.
The FastAPI app mounts this at ``/mcp`` and shares the Neo4j driver
through :func:`set_driver`.

Tools registered:
- palace.health.status
- palace.memory.lookup
"""

import logging
import os
import time
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver
from pydantic import BaseModel
from starlette.applications import Starlette

from palace_mcp.memory.health import get_health
from palace_mcp.memory.lookup import perform_lookup
from palace_mcp.memory.schema import HealthResponse as MemoryHealthResponse
from palace_mcp.memory.schema import LookupRequest, LookupResponse

logger = logging.getLogger(__name__)

_mcp = FastMCP("palace", streamable_http_path="/")

# Module-level driver reference — set by FastAPI lifespan before any request.
_driver: AsyncDriver | None = None

# Server start time for uptime_seconds calculation.
_start_time: float = time.monotonic()


class HealthStatusResponse(BaseModel):
    neo4j: Literal["reachable", "unreachable"]
    git_sha: str
    uptime_seconds: int


def set_driver(driver: AsyncDriver) -> None:
    """Called from FastAPI lifespan to share the Neo4j driver with MCP tools."""
    global _driver  # noqa: PLW0603
    _driver = driver


def build_mcp_asgi_app() -> Starlette:
    """Return the MCP streamable-HTTP ASGI app for mounting."""
    return _mcp.streamable_http_app()


@_mcp.tool(
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


@_mcp.tool(
    name="palace.memory.lookup",
    description=(
        "Query Paperclip entities (Issue, Comment, Agent) from the Palace knowledge graph. "
        "Returns matching nodes with one-hop related data (assignee + comments for Issues, "
        "issue + author for Comments). Use palace.health.status to check reachability first."
    ),
)
async def palace_memory_lookup(
    entity_type: str,
    filters: dict[str, Any] | None = None,
    limit: int = 20,
    order_by: str = "source_updated_at",
) -> dict[str, Any]:
    """Look up Paperclip entities from the Neo4j knowledge graph."""
    if _driver is None:
        return {
            "error": {
                "code": "driver_unavailable",
                "message": "Neo4j driver not initialised",
            }
        }
    req = LookupRequest(
        entity_type=entity_type,
        filters=filters or {},
        limit=limit,
        order_by=order_by,
    )
    resp: LookupResponse = await perform_lookup(_driver, req)
    return resp.model_dump()


@_mcp.tool(
    name="palace.memory.health",
    description=(
        "Return Neo4j entity counts (Issue/Comment/Agent) and the latest ingest run metadata. "
        "Use to verify data freshness before running palace.memory.lookup."
    ),
)
async def palace_memory_health() -> dict[str, Any]:
    """Return knowledge-graph health: entity counts and last ingest run."""
    if _driver is None:
        return {
            "error": {
                "code": "driver_unavailable",
                "message": "Neo4j driver not initialised",
            }
        }
    resp: MemoryHealthResponse = await get_health(_driver)
    return resp.model_dump()
