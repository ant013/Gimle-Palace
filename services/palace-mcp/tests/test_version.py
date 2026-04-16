import pytest
import httpx
from unittest.mock import patch

from palace_mcp.main import create_app


@pytest.fixture
def app():
    return create_app()


async def test_version_returns_service_name(app):
    with patch("palace_mcp.main.version", return_value="0.1.0"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/version")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "palace-mcp"
    assert data["version"] == "0.1.0"
    assert "git_sha" in data


async def test_version_git_sha_from_env(app, monkeypatch):
    monkeypatch.setenv("PALACE_GIT_SHA", "abc123")
    with patch("palace_mcp.main.version", return_value="0.1.0"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/version")

    assert response.json()["git_sha"] == "abc123"


async def test_version_git_sha_default(app, monkeypatch):
    monkeypatch.delenv("PALACE_GIT_SHA", raising=False)
    with patch("palace_mcp.main.version", return_value="0.1.0"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/version")

    assert response.json()["git_sha"] == "unknown"
