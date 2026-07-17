"""palace.code.* MCP tool router — pass-through to codebase-memory-mcp subprocess.

Registers 7 enabled tools (forwarded to CM via MCP SDK stdio transport).
palace.code.manage_adr is registered separately via adr/router.py (GIM-274).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.fastmcp.tools.base import Tool
from mcp.server.fastmcp.utilities.func_metadata import (
    ArgModelBase,
    FuncMetadata,
    func_metadata as _func_metadata,
)
from mcp.types import CallToolResult, TextContent
from pydantic import ConfigDict

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM, native_detect_changes
from palace_mcp.code.native_get_architecture import native_get_architecture
from palace_mcp.code.native_get_code_snippet import native_get_code_snippet
from palace_mcp.code.native_search_code import native_search_code
from palace_mcp.code.list_passthrough_projects import (
    build_passthrough_project_listing,
)
from palace_mcp.code.native_query_graph import native_query_graph
from palace_mcp.code.native_search_graph import native_search_graph
from palace_mcp.code.native_trace_call_path import native_trace_call_path
from palace_mcp.code.namespace import resolve as resolve_namespace

logger = logging.getLogger(__name__)

_cm_session: ClientSession | None = None
_cm_exit_stack: AsyncExitStack | None = None


def _set_cm_session(session: ClientSession | None) -> None:
    """DI injection point — used by tests."""
    global _cm_session  # noqa: PLW0603
    _cm_session = session


def get_cm_session() -> ClientSession | None:
    """Public accessor — returns current CM session, None if not started.

    Use from composite tools to read the session at invocation time
    (avoids None-at-import-time of direct imports).
    """
    return _cm_session


def parse_cm_result(result: Any) -> dict[str, Any]:
    """Parse MCP CallToolResult → dict; replaces inline logic in _forward.

    Public so composite tools (code_composite.py) can reuse the same
    result-extraction semantics without duplicating the pattern.

    Note: non-dict JSON is wrapped as {"_raw": value} (intentional rename
    from _forward's {"result": value} — near-unreachable in practice).
    Non-JSON text is wrapped as {"_raw": text}.
    """
    if result.structuredContent is not None:
        return dict(result.structuredContent)
    for block in result.content:
        if isinstance(block, TextContent):
            try:
                parsed = json.loads(block.text)
                return parsed if isinstance(parsed, dict) else {"_raw": parsed}
            except json.JSONDecodeError:
                return {"_raw": block.text}
    return {}


async def start_cm_subprocess(binary: str) -> None:
    """Start CM binary as stdio subprocess and initialize MCP session."""
    global _cm_session, _cm_exit_stack  # noqa: PLW0603
    stack = AsyncExitStack()
    params = StdioServerParameters(command=binary, args=[])
    read, write = await stack.enter_async_context(stdio_client(params))
    session = ClientSession(read, write)
    _cm_session = await stack.enter_async_context(session)
    await session.initialize()
    _cm_exit_stack = stack
    logger.info("codebase-memory-mcp subprocess started: %s", binary)


async def stop_cm_subprocess() -> None:
    """Shut down the CM subprocess and close MCP session."""
    global _cm_session, _cm_exit_stack  # noqa: PLW0603
    if _cm_exit_stack is not None:
        await _cm_exit_stack.aclose()
    _cm_session = None
    _cm_exit_stack = None
    logger.info("codebase-memory-mcp subprocess stopped")


class _OpenArgs(ArgModelBase):
    """Open argument model: accepts any flat fields and returns all as kwargs.

    FastMCP's func_metadata generates a closed schema from typed function
    signatures. This model bypasses that by accepting all extras and returning
    them from model_dump_one_level(), which is what call_fn_with_arg_validation
    unpacks into **kwargs for the underlying function.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    def model_dump_one_level(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


_OPEN_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": True}
_READ_FILTER_DEFAULT_TOOLS = frozenset({"search_graph", "get_code_snippet"})
_MAX_PROJECTS = 64


@dataclass(frozen=True)
class PassthroughEntry:
    description: str
    native_handler: Callable[..., Any] | None = None
    phase2_error_code: str | None = None


def _make_open_fn_metadata(fn: Any) -> FuncMetadata:
    """Build FuncMetadata with open arg schema, preserving the function's output schema."""
    real_meta = _func_metadata(fn)
    return FuncMetadata(
        arg_model=_OpenArgs,
        output_schema=real_meta.output_schema,
        output_model=real_meta.output_model,
        wrap_output=real_meta.wrap_output,
    )


def _open_schema_for_tool(cm_tool_name: str) -> dict[str, Any]:
    if cm_tool_name not in _READ_FILTER_DEFAULT_TOOLS:
        return _OPEN_SCHEMA
    properties: dict[str, Any] = {
        "include_deprecated": {
            "type": "boolean",
            "default": False,
        }
    }
    if cm_tool_name == "get_code_snippet":
        properties["scope"] = {
            "type": "string",
            "enum": ["symbol", "file", "type"],
            "default": "symbol",
            "description": (
                "symbol = narrow window around the symbol (default); "
                "file = the whole file; "
                "type = the type declaration plus all its extension files "
                "(Swift; the fix for extensions being dropped from a class snippet)."
            ),
        }
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }


def _patch_tool_open_schema(
    mcp_instance: Any, name: str, fn_meta: FuncMetadata, schema: dict[str, Any]
) -> None:
    """Replace a registered FastMCP tool with an open-schema variant."""
    original = mcp_instance._tool_manager._tools[name]
    mcp_instance._tool_manager._tools[name] = Tool(
        fn=original.fn,
        name=original.name,
        title=original.title,
        description=original.description,
        parameters=schema,
        fn_metadata=fn_meta,
        is_async=original.is_async,
        context_kwarg=original.context_kwarg,
        annotations=original.annotations,
        icons=original.icons,
        meta=original.meta,
    )


def _project_not_found(message: str) -> dict[str, Any]:
    return {
        "isError": False,
        "error_code": "project_not_found",
        "message": message,
        "available_via": "palace.memory.list_projects",
    }


async def _normalize_project_args(arguments: dict[str, Any]) -> dict[str, Any]:
    has_project = isinstance(arguments.get("project"), str)
    projects = arguments.get("projects")
    has_projects = isinstance(projects, list) and all(
        isinstance(value, str) for value in projects
    )
    if not has_project and not has_projects:
        return arguments

    from palace_mcp.mcp_server import get_driver

    driver = get_driver()
    if driver is None:
        return _project_not_found(
            "project resolution unavailable: Neo4j driver not initialised"
        )

    normalized = dict(arguments)
    if has_project:
        try:
            resolution = await resolve_namespace(driver, arguments["project"])
        except Exception as exc:
            return _project_not_found(str(exc))
        normalized["project"] = resolution.cm_project_name

    if has_projects:
        assert isinstance(projects, list)
        if len(projects) > _MAX_PROJECTS:
            return _project_not_found(
                f"projects accepts at most {_MAX_PROJECTS} entries"
            )
        normalized_projects: list[str] = []
        for value in projects:
            assert isinstance(value, str)
            try:
                resolution = await resolve_namespace(driver, value)
            except Exception as exc:
                return _project_not_found(str(exc))
            normalized_projects.append(resolution.cm_project_name)
        normalized["projects"] = normalized_projects

    return normalized


_PASSTHROUGH_TOOLS: dict[str, PassthroughEntry] = {
    "search_graph": PassthroughEntry(
        "Search code graph nodes by name pattern, label, or file pattern.",
        native_handler=native_search_graph,
    ),
    "trace_call_path": PassthroughEntry(
        "Trace function call chains (inbound/outbound/both).",
        native_handler=native_trace_call_path,
    ),
    "query_graph": PassthroughEntry(
        "Pass through a caller-supplied Cypher-like query against the code graph.",
        native_handler=native_query_graph,
    ),
    "detect_changes": PassthroughEntry(
        "Detect uncommitted changes mapped to symbols.",
        native_handler=native_detect_changes,
    ),
    "get_architecture": PassthroughEntry(
        "Get project architecture: languages, packages, entry points, routes.",
        native_handler=native_get_architecture,
    ),
    "get_code_snippet": PassthroughEntry(
        "Get source code for a qualified symbol name.",
        native_handler=native_get_code_snippet,
    ),
    "search_code": PassthroughEntry(
        "Grep-like code search across indexed repositories.",
        phase2_error_code="phase2_required",
        native_handler=native_search_code,
    ),
}

_DISABLED_CM_TOOLS: dict[str, str] = {
    # manage_adr removed: now registered as native @mcp.tool via adr/router.py (GIM-274)
}


def register_code_tools(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    mcp_instance: Any = None,
) -> None:
    """Register all palace.code.* tools using the provided decorator.

    Accepts `_tool` from mcp_server.py — Pattern #21 dedup-aware decorator
    that appends each name to `_registered_tool_names` before delegating
    to `@_mcp.tool()`.

    Pass `mcp_instance` (the FastMCP server) to enable open-schema patching
    so that MCP clients can call tools with flat arguments (GIM-89 fix).
    """
    for cm_name, entry in _PASSTHROUGH_TOOLS.items():
        _register_passthrough(
            tool_decorator,
            cm_name,
            entry.description,
            entry,
            mcp_instance,
        )
    _register_list_passthrough_projects(tool_decorator)
    for disabled_name, message in _DISABLED_CM_TOOLS.items():
        _register_disabled_tool(tool_decorator, disabled_name, message, mcp_instance)


async def _call_cm_tool(cm_tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    assert _cm_session is not None, (
        "CM subprocess not started; set CODEBASE_MEMORY_MCP_BINARY"
    )
    result: CallToolResult = await _cm_session.call_tool(
        cm_tool_name, arguments=arguments
    )
    if result.isError:
        return {"error": [str(block) for block in result.content]}
    return parse_cm_result(result)


async def _resolve_project(
    arguments: dict[str, Any],
) -> tuple[Any | None, dict[str, Any] | None]:
    project = arguments.get("project")
    if not isinstance(project, str):
        return None, None

    from palace_mcp.mcp_server import get_driver

    driver = get_driver()
    if driver is None:
        return None, None
    try:
        return await resolve_namespace(driver, project), None
    except Exception as exc:
        return None, _project_not_found(str(exc))


def _cm_fallback_unavailable(tool_name: str, project: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "error_code": "cm_fallback_unavailable",
        "message": f"CM fallback unavailable for palace.code.{tool_name}",
    }
    if project is not None:
        result["project"] = project
    return result


def _phase2_required(tool_name: str, project: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": "phase2_required",
        "message": f"native palace.code.{tool_name} is not implemented in this slice",
        "project": project,
    }


async def _dispatch_passthrough(
    cm_tool_name: str,
    entry: PassthroughEntry,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    resolution = None
    project_error = None
    decision = "cm"
    project = (
        arguments.get("project") if isinstance(arguments.get("project"), str) else None
    )
    started = perf_counter()
    try:
        resolution, project_error = await _resolve_project(arguments)
        if resolution is not None and entry.native_handler is not None:
            native_arguments = dict(arguments)
            native_arguments["project"] = resolution.slug
            native_result = await entry.native_handler(**native_arguments)
            if native_result is not FALLBACK_TO_CM:
                assert isinstance(native_result, dict)
                decision = (
                    "native_error" if native_result.get("ok") is False else "native"
                )
                return native_result
            decision = "fallback_to_cm"

        if project_error is not None:
            decision = "project_not_found"
            return project_error

        if _cm_session is None:
            if resolution is not None and entry.phase2_error_code is not None:
                decision = entry.phase2_error_code
                return _phase2_required(cm_tool_name, resolution.slug)
            decision = "cm_fallback_unavailable"
            return _cm_fallback_unavailable(
                cm_tool_name, resolution.slug if resolution else project
            )

        normalized = await _normalize_project_args(arguments)
        if "error_code" in normalized:
            decision = str(normalized["error_code"])
            return normalized
        decision = "cm"
        return await _call_cm_tool(cm_tool_name, normalized)
    finally:
        logger.info(
            "passthrough.dispatch",
            extra={
                "tool": cm_tool_name,
                "decision": decision,
                "project": resolution.slug if resolution is not None else project,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
            },
        )


def _register_passthrough(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    cm_tool_name: str,
    description: str,
    entry: PassthroughEntry,
    mcp_instance: Any = None,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, description)
    async def _forward(**kwargs: Any) -> dict[str, Any]:
        arguments = dict(kwargs)
        if cm_tool_name in _READ_FILTER_DEFAULT_TOOLS:
            arguments.setdefault("include_deprecated", False)
        return await _dispatch_passthrough(cm_tool_name, entry, arguments)

    if mcp_instance is not None:
        _patch_tool_open_schema(
            mcp_instance,
            palace_name,
            _make_open_fn_metadata(_forward),
            _open_schema_for_tool(cm_tool_name),
        )


def _register_list_passthrough_projects(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
) -> None:
    @tool_decorator(
        "palace.code.list_passthrough_projects",
        "List palace.code passthrough tools by native or CM-only routing.",
    )
    async def _list_passthrough_projects() -> dict[str, list[str]]:
        return build_passthrough_project_listing(_PASSTHROUGH_TOOLS)


def _register_disabled_tool(
    tool_decorator: Callable[[str, str], Callable[..., Any]],
    cm_tool_name: str,
    message: str,
    mcp_instance: Any = None,
) -> None:
    palace_name = f"palace.code.{cm_tool_name}"

    @tool_decorator(palace_name, f"[DISABLED] {cm_tool_name}")
    async def _blocked(**kwargs: Any) -> dict[str, Any]:
        return {
            "error": message,
            "hint": "Use palace.memory.lookup Decision {...} instead.",
        }

    if mcp_instance is not None:
        _patch_tool_open_schema(
            mcp_instance,
            palace_name,
            _make_open_fn_metadata(_blocked),
            _OPEN_SCHEMA,
        )
