"""Unit tests for the palace.health.status MCP tool.

Tests run against the tool function directly (no HTTP transport needed)
to stay fast and portable.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import palace_mcp.mcp_server as mcp_module
from palace_mcp.mcp_server import HealthStatusResponse, _mcp


@pytest.fixture(autouse=True)
def reset_graphiti():
    """Restore module-level graphiti to None after each test."""
    original = mcp_module._graphiti
    yield
    mcp_module._graphiti = original


def _make_graphiti(*, reachable: bool):
    driver = MagicMock()
    if reachable:
        driver.verify_connectivity = AsyncMock()
    else:
        driver.verify_connectivity = AsyncMock(side_effect=Exception("unreachable"))
    graphiti = MagicMock()
    graphiti.driver = driver
    return graphiti


async def test_health_status_neo4j_reachable(monkeypatch):
    mcp_module._graphiti = _make_graphiti(reachable=True)
    monkeypatch.setenv("PALACE_GIT_SHA", "abc123")

    (content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["neo4j"] == "reachable"
    assert structured["git_sha"] == "abc123"
    assert isinstance(structured["uptime_seconds"], int)
    assert len(content) == 1
    assert "reachable" in content[0].text


async def test_health_status_neo4j_unreachable(monkeypatch):
    mcp_module._graphiti = _make_graphiti(reachable=False)
    monkeypatch.setenv("PALACE_GIT_SHA", "def456")

    (content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["neo4j"] == "unreachable"
    assert structured["git_sha"] == "def456"
    assert "unreachable" in content[0].text


async def test_health_status_no_graphiti(monkeypatch):
    """When graphiti is not set (None), neo4j should be 'unreachable'."""
    mcp_module._graphiti = None
    monkeypatch.setenv("PALACE_GIT_SHA", "ghi789")

    (content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["neo4j"] == "unreachable"


async def test_health_status_git_sha_default(monkeypatch):
    """PALACE_GIT_SHA defaults to 'unknown' when not set."""
    mcp_module._graphiti = _make_graphiti(reachable=True)
    monkeypatch.delenv("PALACE_GIT_SHA", raising=False)

    (_content, structured) = await _mcp.call_tool("palace.health.status", {})

    assert structured["git_sha"] == "unknown"


def test_health_status_response_schema():
    """HealthStatusResponse Pydantic model validates correctly."""
    r = HealthStatusResponse(neo4j="reachable", git_sha="abc", uptime_seconds=42)
    assert r.neo4j == "reachable"
    assert r.git_sha == "abc"
    assert r.uptime_seconds == 42


async def test_tool_registered_in_mcp():
    """palace.health.status must appear in the tool list."""
    tools = [t.name for t in await _mcp.list_tools()]
    assert "palace.health.status" in tools
