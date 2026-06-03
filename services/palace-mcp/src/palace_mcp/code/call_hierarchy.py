"""
palace.code.call_hierarchy — production IndexStore direct-read (GIM-1168).

Resolves callers of a Swift symbol by reading the DerivedData IndexStoreDB
directly via libIndexStore.dylib, bypassing sourcekit-lsp entirely.

Multi-project path resolution order:
1. Explicit ``index_store_path`` argument (highest priority / override).
2. Per-project path from ``indexstore_paths`` config dict (keyed by project slug).
3. Single-project fallback ``default_store_path`` (PALACE_SOURCEKIT_INDEX_STORE_PATH).
4. ``PALACE_SOURCEKIT_INDEX_STORE_PATH`` env var (lowest priority).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_store_path(
    project: str | None,
    index_store_path: str | None,
    indexstore_paths: dict[str, str] | None,
    default_store_path: str | None,
) -> str | None:
    if index_store_path:
        return index_store_path
    if project and indexstore_paths:
        per_project = indexstore_paths.get(project)
        if per_project:
            return per_project
    if default_store_path:
        return default_store_path
    return os.environ.get("PALACE_SOURCEKIT_INDEX_STORE_PATH")


def call_hierarchy_tool(
    *,
    qualified_name: str,
    project: str | None,
    max_results: int,
    index_store_path: str | None,
    indexstore_paths: dict[str, str] | None,
    default_store_path: str | None,
) -> dict[str, Any]:
    """Implementation of palace.code.call_hierarchy MCP tool.

    Args:
        qualified_name:    Symbol to query (short or qualified, e.g. "BalanceData").
        project:           Project slug for per-project IndexStore path resolution.
        max_results:       Maximum number of caller records to return.
        index_store_path:  Explicit override for IndexStoreDB DataStore path.
        indexstore_paths:  Dict of project slug → IndexStore path (from settings).
        default_store_path: Single-project fallback path (from settings).

    Returns:
        Dict with ``ok: True`` + caller list, or ``ok: False`` + error_code.
    """
    from palace_mcp.code.indexstore import find_callers

    store_path = _resolve_store_path(
        project, index_store_path, indexstore_paths, default_store_path
    )
    if not store_path:
        return {
            "ok": False,
            "error_code": "index_store_not_configured",
            "qualified_name": qualified_name,
            "project": project,
            "message": (
                "No IndexStore path found. Configure PALACE_INDEXSTORE_PATHS as a JSON "
                "dict mapping project slug → DataStore path, or set "
                "PALACE_SOURCEKIT_INDEX_STORE_PATH for single-project setups."
            ),
        }

    short_name = qualified_name.split(".")[-1]

    t0 = time.perf_counter()
    try:
        callers = find_callers(short_name, store_path, max_results=max_results)
    except RuntimeError as exc:
        logger.exception("call_hierarchy IndexStore error for %s", qualified_name)
        return {
            "ok": False,
            "error_code": "indexstore_error",
            "qualified_name": qualified_name,
            "message": str(exc),
        }
    except Exception as exc:
        logger.exception("call_hierarchy unexpected error for %s", qualified_name)
        return {
            "ok": False,
            "error_code": "indexstore_error",
            "qualified_name": qualified_name,
            "message": str(exc),
        }
    latency_s = time.perf_counter() - t0

    caller_list = [
        {
            "source_file": c.source_file,
            "record_name": c.record_name,
            "symbol_name": c.symbol_name,
            "symbol_usr": c.symbol_usr,
            "line": c.line,
            "col": c.col,
            "roles": c.roles,
        }
        for c in callers
    ]

    return {
        "ok": True,
        "qualified_name": qualified_name,
        "short_name": short_name,
        "project": project,
        "index_store_path": store_path,
        "caller_count": len(caller_list),
        "callers": caller_list,
        "latency_s": round(latency_s, 3),
        "approach": "indexstore_direct",
    }
