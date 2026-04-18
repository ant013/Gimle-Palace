import asyncio
import logging
import os
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Annotated, cast

from fastapi import Depends, FastAPI, Request, Response
from neo4j import AsyncDriver, AsyncGraphDatabase
from starlette.applications import Starlette

from palace_mcp.config import Settings
from palace_mcp.mcp_server import build_mcp_asgi_app, set_driver
from palace_mcp.memory.constraints import ensure_schema
from palace_mcp.memory.logging_setup import configure_json_logging

# Build once at module level so lifespan can be wired in below.
_mcp_asgi_app: Starlette = build_mcp_asgi_app()

logger = logging.getLogger(__name__)

# Pattern #11: keep a reference so GC doesn't cancel mid-run.
_background_tasks: set[asyncio.Task[None]] = set()


def _fire_and_forget(coro: Coroutine[None, None, None]) -> None:
    """Pattern #11: schedule a coroutine as a background task.

    Keeps a strong reference to prevent GC cancellation and logs
    any exception to avoid silent swallowing.
    """
    task: asyncio.Task[None] = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task[None]) -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error(
                "ensure_schema background task failed: %s",
                t.exception(),
                exc_info=t.exception(),
            )

    task.add_done_callback(_on_done)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_json_logging()
    # Pattern #6: read config via Settings (defaults present — no KeyError).
    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=("neo4j", settings.neo4j_password.get_secret_value())
    )
    app.state.neo4j = driver
    set_driver(driver)
    # Patterns #5 + #11: schema migration is fire-and-forget.
    # Race window: backfill runs in <1s for ~213 nodes; palace-mcp starts
    # behind compose healthcheck so MCP clients only connect after healthy.
    # A slow/unavailable Neo4j must not block startup or cause SIGKILL.
    _fire_and_forget(ensure_schema(driver, default_group_id=settings.palace_default_group_id))
    # Run the MCP sub-app lifespan so StreamableHTTPSessionManager task group is initialized.
    async with _mcp_asgi_app.router.lifespan_context(_mcp_asgi_app):
        yield
    await driver.close()


async def get_neo4j(request: Request) -> AsyncDriver:
    return cast(AsyncDriver, request.app.state.neo4j)


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", _mcp_asgi_app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    async def healthz(driver: Annotated[AsyncDriver, Depends(get_neo4j)]) -> Response:
        try:
            await driver.verify_connectivity()
            return Response(
                content='{"status":"ok","neo4j":"reachable"}',
                media_type="application/json",
            )
        except Exception as exc:
            logger.warning("neo4j verify_connectivity failed: %s", exc)
            return Response(
                content='{"status":"degraded","neo4j":"unreachable"}',
                status_code=503,
                media_type="application/json",
            )

    @app.get("/version")
    async def get_version() -> dict[str, str]:
        return {
            "service": "palace-mcp",
            "version": version("palace-mcp"),
            "git_sha": os.environ.get("PALACE_GIT_SHA", "unknown"),
        }

    return app


app = create_app()
