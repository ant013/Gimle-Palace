import os
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from neo4j import AsyncDriver, AsyncGraphDatabase


@asynccontextmanager
async def lifespan(app: FastAPI):
    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    password = os.environ.get("NEO4J_PASSWORD", "")
    driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", password))
    app.state.neo4j = driver
    yield
    await driver.close()


async def get_neo4j(request: Request) -> AsyncDriver:
    return request.app.state.neo4j


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

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
        except Exception:
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
