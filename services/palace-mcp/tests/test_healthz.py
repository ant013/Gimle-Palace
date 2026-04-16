from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from palace_mcp.main import create_app, get_neo4j


def _make_app(driver):
    app = create_app()
    app.dependency_overrides[get_neo4j] = lambda: driver
    return app


@pytest.fixture
def neo4j_ok():
    driver = MagicMock()
    driver.verify_connectivity = AsyncMock()
    return driver


@pytest.fixture
def neo4j_fail():
    driver = MagicMock()
    driver.verify_connectivity = AsyncMock(side_effect=Exception("connection refused"))
    return driver


async def test_healthz_neo4j_reachable(neo4j_ok):
    app = _make_app(neo4j_ok)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "neo4j": "reachable"}


async def test_healthz_neo4j_unreachable(neo4j_fail):
    app = _make_app(neo4j_fail)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "neo4j": "unreachable"}
