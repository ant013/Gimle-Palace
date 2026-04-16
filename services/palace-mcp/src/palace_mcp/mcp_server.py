"""MCP server layer for palace-mcp.

Exposes the ``palace.health.status`` tool via streamable-HTTP transport.
The FastAPI app mounts this at ``/mcp`` and shares the Neo4j driver
through :func:`set_driver`.
"""

import os
import time
from typing import Literal

from mcp.server.fastmcp import FastMCP
from neo4j import AsyncDriver
from pydantic import BaseModel
from starlette.applications import Starlette

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


@_mcp.tool(name="palace.health.status", description="Return Neo4j reachability, git SHA, and server uptime.")
async def palace_health_status(verbose: bool = False) -> HealthStatusResponse:  # noqa: ARG001
    """Check Palace service health: Neo4j connectivity, git revision, uptime."""
    neo4j_status: Literal["reachable", "unreachable"] = "unreachable"
    if _driver is not None:
        try:
            await _driver.verify_connectivity()
            neo4j_status = "reachable"
        except Exception:
            neo4j_status = "unreachable"

    return HealthStatusResponse(
        neo4j=neo4j_status,
        git_sha=os.environ.get("PALACE_GIT_SHA", "unknown"),
        uptime_seconds=int(time.monotonic() - _start_time),
    )
