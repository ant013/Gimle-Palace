"""Tests for palace_mcp.errors: handle_tool_error() and recovery hint mapping.

Each test covers one error class from the mapping table in GIM-45.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from neo4j.exceptions import Neo4jError, ServiceUnavailable

import palace_mcp.mcp_server as mcp_module
from palace_mcp.errors import (
    DriverUnavailableError,
    InvalidFilterError,
    RateLimitError,
    UnknownEntityTypeError,
    _recovery_hint,
    handle_tool_error,
)
from palace_mcp.mcp_server import _mcp


# ---------------------------------------------------------------------------
# _recovery_hint — unit tests for each mapped error class
# ---------------------------------------------------------------------------


def test_recovery_hint_service_unavailable() -> None:
    exc = ServiceUnavailable("connection refused")
    assert (
        _recovery_hint(exc) == "Neo4j is temporarily unavailable. Wait 30s and retry."
    )


def test_recovery_hint_driver_unavailable() -> None:
    exc = DriverUnavailableError("Neo4j driver not initialised")
    assert (
        _recovery_hint(exc) == "Neo4j is temporarily unavailable. Wait 30s and retry."
    )


def test_recovery_hint_asyncio_timeout() -> None:
    exc = asyncio.TimeoutError()
    assert (
        _recovery_hint(exc)
        == "Query timed out. Try a narrower filter or smaller time range."
    )


def test_recovery_hint_neo4j_timeout_in_message() -> None:
    # Neo4jError with "timeout" anywhere in str(exc) — covers TransactionTimedOut.
    exc = Neo4jError("Transaction timed out: TransactionTimedOut")
    assert (
        _recovery_hint(exc)
        == "Query timed out. Try a narrower filter or smaller time range."
    )


def test_recovery_hint_neo4j_error_no_timeout() -> None:
    # Generic Neo4jError without "timeout" falls through to internal error.
    exc = Neo4jError("Syntax error in Cypher statement")
    assert _recovery_hint(exc) == "Internal error. Check palace-mcp logs for details."


def test_recovery_hint_unknown_entity_type() -> None:
    exc = UnknownEntityTypeError("Ticket")
    hint = _recovery_hint(exc)
    assert "Ticket" in hint
    assert "Issue" in hint
    assert "Comment" in hint
    assert "Agent" in hint


def test_recovery_hint_invalid_filter() -> None:
    exc = InvalidFilterError("foobar", "Issue", ("key", "status", "assignee_name"))
    hint = _recovery_hint(exc)
    assert "foobar" in hint
    assert "Issue" in hint
    assert "key" in hint
    assert "status" in hint


def test_recovery_hint_rate_limit_with_retry_after() -> None:
    exc = RateLimitError(retry_after=42)
    assert _recovery_hint(exc) == "Rate limited. Wait 42s."


def test_recovery_hint_rate_limit_without_retry_after() -> None:
    exc = RateLimitError()
    hint = _recovery_hint(exc)
    assert "Rate limited" in hint
    assert "42" not in hint


def test_recovery_hint_unhandled() -> None:
    exc = ValueError("something unexpected")
    assert _recovery_hint(exc) == "Internal error. Check palace-mcp logs for details."


# ---------------------------------------------------------------------------
# handle_tool_error — always raises RuntimeError with the recovery hint
# ---------------------------------------------------------------------------


def test_handle_tool_error_raises_runtime_error() -> None:
    exc = DriverUnavailableError("not up")
    with pytest.raises(RuntimeError, match="Neo4j is temporarily unavailable"):
        handle_tool_error(exc)


def test_handle_tool_error_chains_original_exception() -> None:
    original = ServiceUnavailable("gone")
    with pytest.raises(RuntimeError) as exc_info:
        handle_tool_error(original)
    assert exc_info.value.__cause__ is original


def test_handle_tool_error_rate_limit() -> None:
    with pytest.raises(RuntimeError, match=r"Wait 10s"):
        handle_tool_error(RateLimitError(retry_after=10))


def test_handle_tool_error_unknown_entity_type() -> None:
    with pytest.raises(RuntimeError, match="Unknown entity type"):
        handle_tool_error(UnknownEntityTypeError("Widget"))


# ---------------------------------------------------------------------------
# MCP tool integration — graphiti-unavailable and unknown entity_type
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_graphiti() -> object:
    original = mcp_module._graphiti
    yield
    mcp_module._graphiti = original


async def test_lookup_tool_graphiti_none_raises_with_hint() -> None:
    """palace.memory.lookup with no graphiti raises ToolError wrapping recovery hint."""
    mcp_module._graphiti = None
    with pytest.raises(ToolError, match="Neo4j is temporarily unavailable"):
        await _mcp.call_tool("palace.memory.lookup", {"entity_type": "Issue"})


async def test_lookup_tool_unknown_entity_type_raises_with_hint() -> None:
    """palace.memory.lookup with unknown entity_type raises ToolError with hint."""
    graphiti = MagicMock()
    graphiti.driver = MagicMock()
    graphiti.driver.verify_connectivity = AsyncMock()
    mcp_module._graphiti = graphiti

    with pytest.raises(ToolError, match="Unknown entity type"):
        await _mcp.call_tool("palace.memory.lookup", {"entity_type": "Bogus"})


async def test_memory_health_tool_graphiti_none_raises_with_hint() -> None:
    """palace.memory.health with no graphiti raises ToolError wrapping recovery hint."""
    mcp_module._graphiti = None
    with pytest.raises(ToolError, match="Neo4j is temporarily unavailable"):
        await _mcp.call_tool("palace.memory.health", {})
