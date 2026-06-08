import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path
from typing import IO, Annotated, cast

from fastapi import Depends, FastAPI, Request, Response
from neo4j import AsyncDriver, AsyncGraphDatabase
from starlette.applications import Starlette

from palace_mcp.adr.schema import ensure_adr_schema
from palace_mcp.cache import init_cache, init_semaphore
from palace_mcp.code_router import start_cm_subprocess, stop_cm_subprocess
from palace_mcp.config import Settings
from palace_mcp.extractors.schema import ensure_extractors_schema
from palace_mcp.graphiti_runtime import (
    build_graphiti,
    close_graphiti,
    ensure_graphiti_schema,
)
from palace_mcp.embeddings import prewarm_dispatcher
from palace_mcp.mcp_server import (
    _write_audit_line,
    build_mcp_asgi_app,
    set_audit_sink,
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


async def _run_qodo_prewarm() -> None:
    """Run Qodo pre-warm in a thread; log + record counter on failure but never raise."""
    t0 = time.monotonic()
    try:
        await asyncio.to_thread(prewarm_dispatcher)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info("palace.startup.qodo_prewarm_ok elapsed_ms=%d", elapsed_ms)
    except Exception as exc:
        logger.error("palace.startup.qodo_prewarm_failed", exc_info=exc)
        _write_audit_line("palace.startup.qodo_prewarm_failures", {}, None, 0, str(exc))


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
    init_cache(settings.palace_cache_max_size, settings.palace_cache_ttl_s)
    init_semaphore(settings.palace_hydration_sem_limit)
    audit_file: IO[str] | None = None
    if settings.palace_audit_sink_path:
        audit_path = Path(settings.palace_audit_sink_path)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_file = audit_path.open("a", encoding="utf-8")
        set_audit_sink(audit_file)
    if settings.palace_qodo_prewarm:
        await _run_qodo_prewarm()
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
    if audit_file is not None:
        audit_file.close()
        set_audit_sink(None)


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
