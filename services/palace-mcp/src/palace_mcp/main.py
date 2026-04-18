import asyncio
import logging
import os
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Annotated, cast

from fastapi import Depends, FastAPI, Request, Response
from starlette.applications import Starlette

from palace_mcp.config import Settings
from palace_mcp.graphiti_client import build_graphiti
from palace_mcp.mcp_server import build_mcp_asgi_app, set_graphiti
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
                "background task failed: %s",
                t.exception(),
                exc_info=t.exception(),
            )

    task.add_done_callback(_on_done)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_json_logging()
    settings = Settings()
    graphiti = build_graphiti(settings)
    app.state.graphiti = graphiti
    set_graphiti(graphiti, embedder_base_url=settings.embedding_base_url)
    # Run the MCP sub-app lifespan so StreamableHTTPSessionManager task group is initialized.
    async with _mcp_asgi_app.router.lifespan_context(_mcp_asgi_app):
        yield
    await graphiti.close()


async def get_graphiti(request: Request):  # type: ignore[no-untyped-def]
    return cast("object", request.app.state.graphiti)


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", _mcp_asgi_app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    async def healthz(
        graphiti: Annotated[object, Depends(get_graphiti)],
    ) -> Response:
        from graphiti_core import Graphiti  # local to avoid circular at module level

        try:
            if isinstance(graphiti, Graphiti):
                await graphiti.driver.verify_connectivity()
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
