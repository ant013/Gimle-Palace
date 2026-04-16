"""MCP server layer for palace-mcp.

Exposes the ``palace.health.status`` tool via streamable-HTTP transport.
The FastAPI app mounts this at ``/mcp``; Neo4j connectivity is owned by
:func:`palace_lifespan` and injected into each tool call via :class:`Context`.
"""

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from neo4j import AsyncDriver, AsyncGraphDatabase
from pydantic import BaseModel
from starlette.applications import Starlette

logger = logging.getLogger(__name__)

# Server start time for uptime_seconds calculation.
_start_time: float = time.monotonic()


@dataclass
class PalaceContext:
    driver: AsyncDriver


@asynccontextmanager
async def palace_lifespan(server: FastMCP) -> AsyncIterator[PalaceContext]:
    """FastMCP lifespan: open and close the Neo4j driver for MCP tool requests."""
    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    password = os.environ.get("NEO4J_PASSWORD", "")
    driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", password))
    try:
        yield PalaceContext(driver=driver)
    finally:
        await driver.close()


_mcp = FastMCP("palace", streamable_http_path="/", lifespan=palace_lifespan)


class HealthStatusResponse(BaseModel):
    neo4j: Literal["reachable", "unreachable"]
    git_sha: str
    uptime_seconds: int


def build_mcp_asgi_app() -> Starlette:
    """Return the MCP streamable-HTTP ASGI app for mounting."""
    return _mcp.streamable_http_app()


@_mcp.tool(
    name="palace.health.status",
    description="Return Neo4j reachability, git SHA, and server uptime.",
)
async def palace_health_status(ctx: Context[Any, PalaceContext, Any]) -> HealthStatusResponse:
    """Check Palace service health: Neo4j connectivity, git revision, uptime."""
    driver: AsyncDriver = ctx.request_context.lifespan_context.driver
    neo4j_status: Literal["reachable", "unreachable"] = "unreachable"
    try:
        await driver.verify_connectivity()
        neo4j_status = "reachable"
    except Exception as exc:
        logger.warning("MCP palace.health.status neo4j check failed: %s", exc)

    return HealthStatusResponse(
        neo4j=neo4j_status,
        git_sha=os.environ.get("PALACE_GIT_SHA", "unknown"),
        uptime_seconds=int(time.monotonic() - _start_time),
    )
