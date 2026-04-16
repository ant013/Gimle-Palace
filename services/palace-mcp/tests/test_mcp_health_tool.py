"""Unit tests for the palace.health.status MCP tool.

Tests call the tool function directly with a mock Context so they stay
fast, portable, and free of any ASGI/lifespan machinery.
"""

from unittest.mock import AsyncMock, MagicMock

from palace_mcp.mcp_server import HealthStatusResponse, PalaceContext, _mcp, palace_health_status


def _make_driver(*, reachable: bool):
    driver = MagicMock()
    if reachable:
        driver.verify_connectivity = AsyncMock()
    else:
        driver.verify_connectivity = AsyncMock(side_effect=Exception("unreachable"))
    return driver


def _make_ctx(driver):
    """Return a mock Context whose lifespan_context holds the given driver."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = PalaceContext(driver=driver)
    return ctx


async def test_health_status_neo4j_reachable(monkeypatch):
    ctx = _make_ctx(_make_driver(reachable=True))
    monkeypatch.setenv("PALACE_GIT_SHA", "abc123")

    result = await palace_health_status(ctx)

    assert result.neo4j == "reachable"
    assert result.git_sha == "abc123"
    assert isinstance(result.uptime_seconds, int)


async def test_health_status_neo4j_unreachable(monkeypatch):
    ctx = _make_ctx(_make_driver(reachable=False))
    monkeypatch.setenv("PALACE_GIT_SHA", "def456")

    result = await palace_health_status(ctx)

    assert result.neo4j == "unreachable"
    assert result.git_sha == "def456"


async def test_health_status_git_sha_default(monkeypatch):
    """PALACE_GIT_SHA defaults to 'unknown' when not set."""
    ctx = _make_ctx(_make_driver(reachable=True))
    monkeypatch.delenv("PALACE_GIT_SHA", raising=False)

    result = await palace_health_status(ctx)

    assert result.git_sha == "unknown"


async def test_health_status_uptime_non_negative():
    """uptime_seconds is a non-negative integer."""
    ctx = _make_ctx(_make_driver(reachable=True))

    result = await palace_health_status(ctx)

    assert isinstance(result.uptime_seconds, int)
    assert result.uptime_seconds >= 0


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
