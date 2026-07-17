import pytest
import httpx
from unittest.mock import patch

import palace_mcp.runtime_identity as runtime_identity
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


async def test_version_git_sha_is_resolved_not_env_label(app, monkeypatch):
    """F5: git_sha is the RESOLVED serving-checkout sha; the env label is
    exposed separately and never presented as the sha."""
    monkeypatch.setenv("PALACE_GIT_SHA", "abc123")
    monkeypatch.setattr(runtime_identity, "_cache", None)
    with patch("palace_mcp.main.version", return_value="0.1.0"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/version")

    data = response.json()
    assert data["git_sha_source"] == "resolved"
    assert data["git_sha"] != "abc123" and len(data["git_sha"]) == 40
    assert data["git_sha_label"] == "abc123"


async def test_version_git_sha_without_env_label(app, monkeypatch):
    monkeypatch.delenv("PALACE_GIT_SHA", raising=False)
    monkeypatch.setattr(runtime_identity, "_cache", None)
    with patch("palace_mcp.main.version", return_value="0.1.0"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/version")

    data = response.json()
    assert data["git_sha_source"] == "resolved"
    assert len(data["git_sha"]) == 40
    assert data["git_sha_label"] is None
