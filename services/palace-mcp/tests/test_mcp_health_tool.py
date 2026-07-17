"""Unit tests for the palace.health.status MCP tool.

Tests run against the tool function directly (no HTTP transport needed)
to stay fast and portable.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import palace_mcp.mcp_server as mcp_module
import palace_mcp.runtime_identity as runtime_identity
from palace_mcp.mcp_server import HealthStatusResponse, _mcp


@pytest.fixture(autouse=True)
def reset_driver():
    """Restore module-level driver to None after each test."""
    original = mcp_module._driver
    yield
    mcp_module._driver = original


def _make_driver(*, reachable: bool):
    driver = MagicMock()
    if reachable:
        driver.verify_connectivity = AsyncMock()
    else:
        driver.verify_connectivity = AsyncMock(side_effect=Exception("unreachable"))
    return driver


async def test_health_status_neo4j_reachable(monkeypatch):
    mcp_module._driver = _make_driver(reachable=True)
    monkeypatch.setenv("PALACE_GIT_SHA", "abc123")

    monkeypatch.setattr(runtime_identity, "_cache", None)
    (content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["neo4j"] == "reachable"
    assert structured["git_sha_source"] == "resolved"
    assert structured["git_sha_label"] == "abc123"
    assert len(structured["git_sha"]) == 40
    assert structured["code_loaded_at"] == mcp_module._code_loaded_at
    assert isinstance(structured["uptime_seconds"], int)
    assert len(content) == 1
    assert "reachable" in content[0].text


async def test_health_status_neo4j_unreachable(monkeypatch):
    mcp_module._driver = _make_driver(reachable=False)
    monkeypatch.setenv("PALACE_GIT_SHA", "def456")

    monkeypatch.setattr(runtime_identity, "_cache", None)
    (content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["neo4j"] == "unreachable"
    assert structured["git_sha_source"] == "resolved"
    assert structured["git_sha_label"] == "def456"
    assert structured["code_loaded_at"] == mcp_module._code_loaded_at
    assert "unreachable" in content[0].text


async def test_health_status_no_driver(monkeypatch):
    """When driver is not set (None), neo4j should be 'unreachable'."""
    mcp_module._driver = None
    monkeypatch.setenv("PALACE_GIT_SHA", "ghi789")

    monkeypatch.setattr(runtime_identity, "_cache", None)
    (content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["neo4j"] == "unreachable"


async def test_health_status_git_sha_resolved_without_env(monkeypatch):
    """F5: without an env label, git_sha is still the RESOLVED sha."""
    mcp_module._driver = _make_driver(reachable=True)
    monkeypatch.delenv("PALACE_GIT_SHA", raising=False)

    monkeypatch.setattr(runtime_identity, "_cache", None)
    (_content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["git_sha_source"] == "resolved"
    assert len(structured["git_sha"]) == 40
    assert structured["git_sha_label"] is None


def test_health_status_response_schema():
    """HealthStatusResponse Pydantic model validates correctly."""
    r = HealthStatusResponse(
        neo4j="reachable",
        git_sha="abc",
        code_loaded_at="2026-06-09T00:00:00Z",
        uptime_seconds=42,
    )
    assert r.neo4j == "reachable"
    assert r.git_sha == "abc"
    assert r.code_loaded_at == "2026-06-09T00:00:00Z"
    assert r.uptime_seconds == 42


def test_health_status_code_loaded_at_is_iso8601() -> None:
    datetime.fromisoformat(mcp_module._code_loaded_at.replace("Z", "+00:00"))


async def test_tool_registered_in_mcp():
    """palace.health.status must appear in the tool list."""
    tools = [t.name for t in await _mcp.list_tools()]
    assert "palace.health.status" in tools
