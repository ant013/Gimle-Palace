import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Annotated, cast

from fastapi import Depends, FastAPI, Request, Response
from neo4j import AsyncDriver, AsyncGraphDatabase
from starlette.applications import Starlette

from palace_mcp.adr.schema import ensure_adr_schema
from palace_mcp.code_router import start_cm_subprocess, stop_cm_subprocess
from palace_mcp.config import Settings
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.graphiti_runtime import (
    build_graphiti,
    close_graphiti,
    ensure_graphiti_schema,
)
from palace_mcp.mcp_server import (
    build_mcp_asgi_app,
    set_default_group_id,
    set_driver,
    set_graphiti,
    set_settings,
)
from palace_mcp.memory.constraints import ensure_schema
from palace_mcp.memory.logging_setup import configure_json_logging

_mcp_asgi_app: Starlette = build_mcp_asgi_app()

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()


def _fire_and_forget(coro: Coroutine[None, None, None]) -> None:
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


async def wait_for_neo4j_connectivity(
    driver: AsyncDriver,
    *,
    timeout_seconds: int = 60,
    interval_seconds: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            await driver.verify_connectivity()
            return
        except Exception as exc:
            last_error = str(exc)
            await asyncio.sleep(interval_seconds)
    raise RuntimeError(
        f"neo4j did not become reachable within {timeout_seconds}s: {last_error}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_json_logging()
    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    graphiti = build_graphiti(settings)
    app.state.neo4j = driver
    app.state.graphiti = graphiti
    set_driver(driver)
    set_graphiti(graphiti)
    set_settings(settings)
    set_default_group_id(settings.palace_default_group_id)
    if settings.codebase_memory_mcp_binary:
        await start_cm_subprocess(settings.codebase_memory_mcp_binary)
    await wait_for_neo4j_connectivity(driver)
    _fire_and_forget(
        ensure_schema(driver, default_group_id=settings.palace_default_group_id)
    )
    await ensure_extractors_schema(driver)
    await ensure_adr_schema(driver)
    await ensure_graphiti_schema(graphiti)
    async with _mcp_asgi_app.router.lifespan_context(_mcp_asgi_app):
        yield
    if settings.codebase_memory_mcp_binary:
        await stop_cm_subprocess()
    await close_graphiti(graphiti)
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
