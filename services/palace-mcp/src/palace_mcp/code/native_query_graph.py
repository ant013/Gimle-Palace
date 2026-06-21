"""Native read-only query_graph implementation for Palace-known projects."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM

_MAX_ROWS = 200
_MAX_BYTES = 64_000
_RESERVED_PARAMS = frozenset({"group_id", "project_id"})
_FORBIDDEN_PATTERNS = (
    re.compile(r"\bCREATE\b", re.IGNORECASE),
    re.compile(r"\bMERGE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bDETACH\s+DELETE\b", re.IGNORECASE),
    re.compile(r"\bSET\b", re.IGNORECASE),
    re.compile(r"\bREMOVE\b", re.IGNORECASE),
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bLOAD\s+CSV\b", re.IGNORECASE),
    re.compile(r"\bCALL\b", re.IGNORECASE),
    re.compile(r"\bDBMS\b", re.IGNORECASE),
    re.compile(r"\bAPOC\b", re.IGNORECASE),
)
_MATCH_RE = re.compile(r"\bMATCH\b", re.IGNORECASE)
_SCOPE_PREDICATE_RE = re.compile(
    r"(?:\.\s*(?:group_id|project_id)\b|\b(?:group_id|project_id)\s*:)",
    re.IGNORECASE,
)
_ABSOLUTE_PATH_RE = re.compile(r"(/[A-Za-z0-9._-]+)+")
_SCHEMA_RE = re.compile(r"\bdb\.[A-Za-z0-9_]+\([^)]*\)", re.IGNORECASE)


def _error(code: str, message: str, *, project: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        result["project"] = project
    return result


def _analysis_text(query: str) -> str:
    chars: list[str] = []
    i = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    while i < len(query):
        char = query[i]
        nxt = query[i + 1] if i + 1 < len(query) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                chars.append("\n")
            else:
                chars.append(" ")
            i += 1
            continue
        if in_block_comment:
            if char == "*" and nxt == "/":
                chars.extend((" ", " "))
                i += 2
                in_block_comment = False
            else:
                chars.append("\n" if char == "\n" else " ")
                i += 1
            continue
        if in_single:
            chars.append("\n" if char == "\n" else " ")
            if char == "'" and nxt == "'":
                chars.append(" ")
                i += 2
                continue
            if char == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            chars.append("\n" if char == "\n" else " ")
            if char == '"':
                in_double = False
            i += 1
            continue
        if char == "/" and nxt == "/":
            chars.extend((" ", " "))
            i += 2
            in_line_comment = True
            continue
        if char == "/" and nxt == "*":
            chars.extend((" ", " "))
            i += 2
            in_block_comment = True
            continue
        if char == "'":
            chars.append(" ")
            in_single = True
            i += 1
            continue
        if char == '"':
            chars.append(" ")
            in_double = True
            i += 1
            continue
        chars.append(char)
        i += 1
    return "".join(chars)


def _to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_json_safe(item) for item in value]
    return str(value)


def _redact_error(message: str) -> str:
    redacted = _ABSOLUTE_PATH_RE.sub("<redacted-path>", message)
    redacted = _SCHEMA_RE.sub("<redacted-schema>", redacted)
    return " ".join(redacted.split())


async def native_query_graph(
    query: str,
    project: str | None = None,
    max_rows: int | None = None,
    **params: Any,
) -> dict[str, Any] | object:
    if project is None:
        return FALLBACK_TO_CM
    if not query.strip():
        return _error("validation_error", "query is required", project=project)
    reserved = sorted(name for name in _RESERVED_PARAMS if name in params)
    if reserved:
        return _error(
            "reserved_param",
            f"reserved query parameter(s): {', '.join(reserved)}",
            project=project,
        )

    analysis = _analysis_text(query)
    if any(pattern.search(analysis) for pattern in _FORBIDDEN_PATTERNS):
        return _error(
            "write_query_forbidden",
            "native query_graph only permits read-only Cypher",
            project=project,
        )
    match_count = len(_MATCH_RE.findall(analysis))
    scope_count = len(_SCOPE_PREDICATE_RE.findall(analysis))
    if match_count == 0 or scope_count < match_count:
        return _error(
            "scope_predicate_required",
            "each MATCH clause must include a project scope predicate",
            project=project,
        )

    from palace_mcp.mcp_server import get_driver

    driver = get_driver()
    if driver is None:
        return _error(
            "neo4j_unavailable",
            "Neo4j driver not initialised",
            project=project,
        )

    row_cap = _MAX_ROWS
    if isinstance(max_rows, int) and max_rows > 0:
        row_cap = min(max_rows, _MAX_ROWS)

    columns: list[str] = []
    rows: list[list[Any]] = []
    total = 0
    encoded_bytes = 0
    truncated_reason: str | None = None
    try:
        async with driver.session() as session:
            query_result = await session.run(
                query,
                {
                    **params,
                    "group_id": f"project/{project}",
                    "project_id": f"project/{project}",
                },
            )
            async for record in query_result:
                total += 1
                row_dict = {
                    str(key): _to_json_safe(value)
                    for key, value in dict(record).items()
                }
                if not columns:
                    columns = list(row_dict.keys())
                row = [row_dict.get(column) for column in columns]
                if len(rows) >= row_cap:
                    truncated_reason = "row_cap"
                    continue
                row_bytes = len(json.dumps(row, ensure_ascii=True).encode("utf-8"))
                if rows and encoded_bytes + row_bytes > _MAX_BYTES:
                    truncated_reason = "byte_budget"
                    continue
                rows.append(row)
                encoded_bytes += row_bytes
    except Exception as exc:  # noqa: BLE001
        return _error(
            "cypher_error",
            f"cypher query failed: {_redact_error(str(exc))}",
            project=project,
        )

    payload: dict[str, Any] = {"columns": columns, "rows": rows, "total": total}
    if truncated_reason is not None:
        payload["truncated"] = True
        payload["truncated_reason"] = truncated_reason
    return payload
