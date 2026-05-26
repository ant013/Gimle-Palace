"""Streamable HTTP helpers for calling palace-mcp tools.

Used by the runtime smoke runner to call ``tools/list``, register
projects, and run extractors without embedding CLI or server internals.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class McpCallError(Exception):
    """An MCP tool call returned an error or unexpected content."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str,
        raw_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.raw_body = raw_body


# ---------------------------------------------------------------------------
# Structured extractor result
# ---------------------------------------------------------------------------


class ExtractorResult(BaseModel, frozen=True):
    """Structured status from ``palace.ingest.run_extractor``."""

    ok: bool
    run_id: str | None = None
    extractor_name: str | None = None
    project: str | None = None
    duration_ms: int | None = None
    nodes_written: int | None = None
    edges_written: int | None = None
    error_code: str | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _open_session(mcp_url: str) -> AsyncIterator[ClientSession]:
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _extract_text(tool_name: str, content: list[Any]) -> str:
    if not content:
        raise McpCallError(
            f"{tool_name} returned empty content",
            tool_name=tool_name,
        )
    first = content[0]
    if not isinstance(first, TextContent):
        raise McpCallError(
            f"{tool_name} returned unexpected content type: {type(first).__name__}",
            tool_name=tool_name,
        )
    return first.text


def _parse_json(tool_name: str, text: str) -> dict[str, Any]:
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpCallError(
            f"{tool_name} returned non-JSON response",
            tool_name=tool_name,
            raw_body=text,
        ) from exc
    if not isinstance(result, dict):
        raise McpCallError(
            f"{tool_name} returned {type(result).__name__}, expected object",
            tool_name=tool_name,
            raw_body=text,
        )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def list_tools(
    mcp_url: str, *, _session: ClientSession | None = None
) -> list[str]:
    """Return tool names available on the MCP server."""
    if _session is not None:
        result = await _session.list_tools()
        return [t.name for t in result.tools]

    async with _open_session(mcp_url) as session:
        result = await session.list_tools()
        return [t.name for t in result.tools]


async def call_tool(
    mcp_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    _session: ClientSession | None = None,
) -> dict[str, Any]:
    """Call an MCP tool and return the parsed JSON response.

    Raises :class:`McpCallError` with ``raw_body`` populated when the
    server returns a non-JSON or error response.
    """
    if _session is not None:
        result = await _session.call_tool(tool_name, arguments)
        text = _extract_text(tool_name, list(result.content))
        return _parse_json(tool_name, text)

    async with _open_session(mcp_url) as session:
        result = await session.call_tool(tool_name, arguments)
        text = _extract_text(tool_name, list(result.content))
        return _parse_json(tool_name, text)


async def register_project(
    mcp_url: str,
    *,
    slug: str,
    name: str,
    tags: list[str] | None = None,
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
    parent_mount: str | None = None,
    relative_path: str | None = None,
    language_profile: str | None = None,
    _session: ClientSession | None = None,
) -> dict[str, Any]:
    """Register a project via ``palace.memory.register_project``.

    Both ``slug`` and ``name`` are always included in the arguments.
    """
    arguments: dict[str, Any] = {"slug": slug, "name": name}
    if tags is not None:
        arguments["tags"] = tags
    if language is not None:
        arguments["language"] = language
    if framework is not None:
        arguments["framework"] = framework
    if repo_url is not None:
        arguments["repo_url"] = repo_url
    if parent_mount is not None:
        arguments["parent_mount"] = parent_mount
    if relative_path is not None:
        arguments["relative_path"] = relative_path
    if language_profile is not None:
        arguments["language_profile"] = language_profile

    return await call_tool(
        mcp_url,
        "palace.memory.register_project",
        arguments,
        _session=_session,
    )


async def run_extractor(
    mcp_url: str,
    *,
    extractor_name: str,
    project: str,
    scip_path: str | None = None,
    _session: ClientSession | None = None,
) -> ExtractorResult:
    """Run an extractor and return structured status."""
    arguments: dict[str, Any] = {"name": extractor_name, "project": project}
    if scip_path is not None:
        arguments["scip_path"] = scip_path
    payload = await call_tool(
        mcp_url,
        "palace.ingest.run_extractor",
        arguments,
        _session=_session,
    )
    return ExtractorResult(
        ok=payload.get("ok", True),
        run_id=payload.get("run_id"),
        extractor_name=extractor_name,
        project=project,
        duration_ms=payload.get("duration_ms"),
        nodes_written=payload.get("nodes_written"),
        edges_written=payload.get("edges_written"),
        error_code=payload.get("error_code"),
        message=payload.get("message"),
    )
