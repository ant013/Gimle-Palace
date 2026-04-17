"""MCP tool error handling: maps known exception classes to isError recovery hints.

FastMCP catches exceptions raised by tool handlers and sets isError=True on
the CallToolResult. handle_tool_error() always raises — it converts known
exceptions to a RuntimeError with an actionable recovery hint, which the LLM
client receives as the tool error message.
"""

from __future__ import annotations

import asyncio
import logging
from typing import NoReturn

from neo4j.exceptions import Neo4jError, ServiceUnavailable

logger = logging.getLogger(__name__)

VALID_ENTITY_TYPES: tuple[str, ...] = ("Issue", "Comment", "Agent")


class DriverUnavailableError(Exception):
    """Raised when the Neo4j driver has not been initialised."""


class UnknownEntityTypeError(Exception):
    """Raised when entity_type is not one of the known Paperclip entity types."""

    def __init__(self, entity_type: str) -> None:
        self.entity_type = entity_type
        super().__init__(f"Unknown entity type: {entity_type!r}")


class InvalidFilterError(Exception):
    """Raised when a filter key is not valid for the given entity type."""

    def __init__(
        self,
        filter_key: str,
        entity_type: str,
        valid_keys: tuple[str, ...],
    ) -> None:
        self.filter_key = filter_key
        self.entity_type = entity_type
        self.valid_keys = valid_keys
        super().__init__(
            f"Invalid filter key: {filter_key!r} for entity_type {entity_type!r}"
        )


class RateLimitError(Exception):
    """Raised when an upstream service responds with HTTP 429."""

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__("Rate limited")


def _recovery_hint(exc: Exception) -> str:
    """Return an actionable recovery hint for a known exception class.

    ServiceUnavailable is checked before the generic Neo4jError branch because
    it is a subclass of Neo4jError.
    """
    if isinstance(exc, (ServiceUnavailable, DriverUnavailableError)):
        return "Neo4j is temporarily unavailable. Wait 30s and retry."
    if isinstance(exc, asyncio.TimeoutError):
        return "Query timed out. Try a narrower filter or smaller time range."
    neo4j_msg = str(exc).lower()
    if isinstance(exc, Neo4jError) and (
        "timeout" in neo4j_msg or "timed out" in neo4j_msg
    ):
        return "Query timed out. Try a narrower filter or smaller time range."
    if isinstance(exc, UnknownEntityTypeError):
        available = ", ".join(VALID_ENTITY_TYPES)
        return (
            f"Unknown entity type: {exc.entity_type!r}. Available types: {available}."
        )
    if isinstance(exc, InvalidFilterError):
        valid = ", ".join(exc.valid_keys)
        return (
            f"Invalid filter key: {exc.filter_key!r}. "
            f"Valid keys for {exc.entity_type!r}: {valid}."
        )
    if isinstance(exc, RateLimitError):
        if exc.retry_after is not None:
            return f"Rate limited. Wait {exc.retry_after}s."
        return "Rate limited. Retry after a short delay."
    logger.error("palace.tool_error.unhandled", exc_info=exc)
    return "Internal error. Check palace-mcp logs for details."


def handle_tool_error(exc: Exception) -> NoReturn:
    """Map exc to an MCP-standard isError recovery hint and always raise.

    FastMCP catches the RuntimeError this raises and converts it to a
    CallToolResult with isError=True, surfacing the hint text to the LLM.
    """
    hint = _recovery_hint(exc)
    raise RuntimeError(hint) from exc
