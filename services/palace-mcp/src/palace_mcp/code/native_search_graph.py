"""Native search_graph implementation for Palace-known projects."""

from __future__ import annotations

import re
from typing import Any, cast

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.pagination import pagination_envelope
from palace_mcp.symbol_identity import (
    canonical_symbol_kind,
    canonical_symbol_label,
    canonical_symbol_short_name,
)

_SUPPORTED_LABELS = frozenset(
    {
        "Project",
        "File",
        "Module",
        "Symbol",
        "Function",
        "Method",
        "Class",
        "Struct",
        "Protocol",
        "Property",
        "Interface",
        "Enum",
        "Type",
        "TypeAlias",
        "Extension",
        "Initializer",
        "Accessor",
        "Actor",
        "Route",
    }
)

_MATCH_FILTERS = """
MATCH (n)
WHERE (
    (n:Symbol AND n.group_id = $group_id)
    OR ((n:File OR n:Module OR n:Route) AND coalesce(n.group_id, n.project_id) = $project_id)
    OR (n:Project AND n.slug = $project)
)
  AND ($include_deprecated OR NOT n:Deprecated)
WITH
    CASE
        WHEN n:Project THEN 'Project'
        WHEN n:File THEN 'File'
        WHEN n:Module THEN 'Module'
        WHEN n:Route THEN 'Route'
        WHEN n:Symbol THEN
            CASE toLower(coalesce(n.kind, ''))
                WHEN 'function' THEN 'Function'
                WHEN 'method' THEN 'Method'
                WHEN 'class' THEN 'Class'
                WHEN 'struct' THEN 'Struct'
                WHEN 'protocol' THEN 'Protocol'
                WHEN 'interface' THEN 'Interface'
                WHEN 'property' THEN 'Property'
                WHEN 'enum' THEN 'Enum'
                WHEN 'type' THEN 'Type'
                WHEN 'typealias' THEN 'TypeAlias'
                WHEN 'extension' THEN 'Extension'
                WHEN 'initializer' THEN 'Initializer'
                WHEN 'accessor' THEN 'Accessor'
                WHEN 'actor' THEN 'Actor'
                WHEN 'route' THEN 'Route'
                ELSE coalesce(n.label, 'Symbol')
            END
        ELSE ''
    END AS result_label,
    CASE
        WHEN n:File THEN last(split(coalesce(n.file_path, n.path, ''), '/'))
        WHEN n:Project THEN coalesce(n.slug, n.name, '')
        WHEN n:Module THEN coalesce(
            n.name,
            n.slug,
            last(split(coalesce(n.qualified_name, ''), '.')),
            ''
        )
        ELSE coalesce(
            n.short_name,
            n.name,
            n.display_name,
            last(split(coalesce(n.qualified_name, ''), '.')),
            n.slug,
            last(split(coalesce(n.file_path, n.path, ''), '/')),
            ''
        )
    END AS result_name,
    coalesce(
        n.short_name,
        n.display_name,
        n.qualified_name,
        n.path,
        n.file_path,
        n.slug,
        n.name,
        ''
    ) AS result_short_name,
    coalesce(
        n.qualified_name,
        n.path,
        n.file_path,
        n.slug,
        n.name,
        ''
    ) AS result_qn,
    coalesce(n.file_path, n.path, '') AS result_file_path,
    coalesce(
        n.kind,
        CASE
            WHEN n:Project THEN 'project'
            WHEN n:File THEN 'file'
            WHEN n:Module THEN 'module'
            WHEN n:Route THEN 'route'
            ELSE ''
        END
    ) AS result_kind,
    n:Symbol AS result_is_symbol,
    size([(n)--() | 1]) AS degree
WHERE result_label <> ''
  AND ($label = 'Symbol' OR result_label <> 'Symbol')
  AND (
      $label IS NULL
      OR ($label = 'Symbol' AND result_is_symbol)
      OR result_label = $label
  )
  AND ($name_pattern IS NULL OR result_name =~ $name_pattern)
  AND ($qn_pattern IS NULL OR result_qn =~ $qn_pattern)
  AND ($file_pattern IS NULL OR result_file_path =~ $file_pattern)
  AND ($min_degree IS NULL OR degree >= $min_degree)
  AND ($max_degree IS NULL OR degree <= $max_degree)
""".strip()

_COUNT_QUERY = f"""
{_MATCH_FILTERS}
RETURN count(*) AS total
""".strip()

_RESULTS_QUERY = f"""
{_MATCH_FILTERS}
RETURN result_name AS name,
       result_qn AS qualified_name,
       result_label AS label,
       result_file_path AS file_path,
       result_short_name AS short_name,
       result_kind AS kind
ORDER BY qualified_name ASC,
         file_path ASC,
         name ASC,
         label ASC
SKIP $offset
LIMIT $fetch_limit
""".strip()


def _error(code: str, message: str, *, project: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": code,
        "message": message,
        "project": project,
    }


def _phase2_required(project: str) -> dict[str, Any]:
    return _error(
        "phase2_required",
        "native search_graph only supports pattern-mode filters; query= requires Phase 2 full-text support",
        project=project,
    )


def _canonical_label(value: str | None, *, project: str) -> str | None | dict[str, Any]:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    normalized = next(
        (label for label in _SUPPORTED_LABELS if label.lower() == candidate.lower()),
        None,
    )
    if normalized is None:
        supported = ", ".join(sorted(_SUPPORTED_LABELS))
        return _error(
            "validation_error",
            f"unsupported label {value!r}; supported labels: {supported}",
            project=project,
        )
    return normalized


def _validated_regex(
    value: str | None, field_name: str, *, project: str
) -> str | None | dict[str, Any]:
    if value is None:
        return None
    if value == "":
        return None
    try:
        re.compile(value)
    except re.error as exc:
        return _error(
            "validation_error",
            f"invalid {field_name}: {exc}",
            project=project,
        )
    # Cypher `=~` anchors the regex to the FULL string, so a bare token like
    # "failPending" only matches a name equal to it (not "failPendingTransactions").
    # Callers expect substring ("*_pattern") search. Treat a plain token — one with
    # no regex syntax — as a case-insensitive literal substring; honour deliberate
    # regex (anchors / metacharacters) as-is. A lone "." (e.g. "Kit.swift") is kept
    # literal so file/name patterns work intuitively.
    if not any(ch in value for ch in "^$*+?()[]{}|\\"):
        return f"(?i).*{re.escape(value)}.*"
    return value


def _validated_int(
    value: Any,
    field_name: str,
    *,
    project: str,
    minimum: int = 0,
) -> int | None | dict[str, Any]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return _error(
            "validation_error",
            f"{field_name} must be an integer",
            project=project,
        )
    if value < minimum:
        return _error(
            "validation_error",
            f"{field_name} must be >= {minimum}",
            project=project,
        )
    return cast(int, value)


async def _rows(session: Any, query: str, **params: Any) -> list[dict[str, Any]]:
    result = await session.run(query, **params)
    return cast(list[dict[str, Any]], await result.data())


async def native_search_graph(
    project: str | None = None,
    query: str | None = None,
    label: str | None = None,
    name_pattern: str | None = None,
    qn_pattern: str | None = None,
    file_pattern: str | None = None,
    min_degree: int | None = None,
    max_degree: int | None = None,
    offset: int = 0,
    limit: int | None = 50,
    include_deprecated: bool = False,
    **_: Any,
) -> dict[str, Any] | object:
    if project is None:
        return FALLBACK_TO_CM
    if query is not None and query.strip():
        return _phase2_required(project)

    normalized_label = _canonical_label(label, project=project)
    if isinstance(normalized_label, dict):
        return normalized_label
    validated_name_pattern = _validated_regex(
        name_pattern, "name_pattern", project=project
    )
    if isinstance(validated_name_pattern, dict):
        return validated_name_pattern
    validated_qn_pattern = _validated_regex(qn_pattern, "qn_pattern", project=project)
    if isinstance(validated_qn_pattern, dict):
        return validated_qn_pattern
    validated_file_pattern = _validated_regex(
        file_pattern, "file_pattern", project=project
    )
    if isinstance(validated_file_pattern, dict):
        return validated_file_pattern
    validated_offset = _validated_int(offset, "offset", project=project)
    if isinstance(validated_offset, dict):
        return validated_offset
    validated_limit = _validated_int(limit, "limit", project=project)
    if isinstance(validated_limit, dict):
        return validated_limit
    validated_min_degree = _validated_int(min_degree, "min_degree", project=project)
    if isinstance(validated_min_degree, dict):
        return validated_min_degree
    validated_max_degree = _validated_int(max_degree, "max_degree", project=project)
    if isinstance(validated_max_degree, dict):
        return validated_max_degree
    if (
        validated_min_degree is not None
        and validated_max_degree is not None
        and validated_min_degree > validated_max_degree
    ):
        return _error(
            "validation_error",
            "min_degree must be <= max_degree",
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

    params = {
        "project": project,
        "project_id": f"project/{project}",
        "group_id": f"project/{project}",
        "include_deprecated": include_deprecated,
        "label": normalized_label,
        "name_pattern": validated_name_pattern,
        "qn_pattern": validated_qn_pattern,
        "file_pattern": validated_file_pattern,
        "min_degree": validated_min_degree,
        "max_degree": validated_max_degree,
    }
    try:
        async with driver.session() as session:
            count_rows = await _rows(session, _COUNT_QUERY, **params)
            total = int(count_rows[0]["total"]) if count_rows else 0
            if validated_limit == 0:
                raw_rows: list[dict[str, Any]] = []
            else:
                fetch_limit = (
                    total + 1 if validated_limit is None else validated_limit + 1
                )
                raw_rows = await _rows(
                    session,
                    _RESULTS_QUERY,
                    **params,
                    offset=validated_offset,
                    fetch_limit=fetch_limit,
                )
    except Exception as exc:  # noqa: BLE001
        return _error(
            "cypher_error", f"search_graph query failed: {exc}", project=project
        )

    trimmed_rows = raw_rows
    if validated_limit is not None:
        trimmed_rows = raw_rows[:validated_limit]

    results: list[dict[str, Any]] = []
    for raw_row in trimmed_rows:
        row = dict(raw_row)
        qualified_name = str(row.get("qualified_name") or "")
        kind = canonical_symbol_kind(str(row.get("kind") or row.get("label") or ""))
        label_value = canonical_symbol_label(str(row.get("label") or kind))
        short_name = canonical_symbol_short_name(
            qualified_name,
            short_name=str(row.get("short_name") or ""),
            name=str(row.get("name") or ""),
        )
        name = str(row.get("name") or short_name or qualified_name)
        results.append(
            {
                **row,
                "name": short_name or name,
                "qualified_name": qualified_name,
                "label": label_value or str(row.get("label") or ""),
                "file_path": str(row.get("file_path") or ""),
                "short_name": short_name or name,
                "kind": kind or str(row.get("kind") or ""),
            }
        )
    return {
        "results": results,
        **pagination_envelope(
            total=total,
            returned=len(results),
            offset=validated_offset or 0,
        ),
    }
