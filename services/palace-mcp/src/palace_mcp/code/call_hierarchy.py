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

import concurrent.futures
import logging
import os
import time
from pathlib import Path
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


def _detect_store_format(store_path: str) -> str | None:
    """Return 'v5' if this looks like an IndexStoreDB v5 DataStore, else None.

    Returns None when the path is missing or has no recognisable layout.
    Returns 'unidb' when the path appears to be a Xcode 16+ UniDB store
    (no v5/ subdirectory but a .db file exists at the root).
    """
    p = Path(store_path)
    if not p.exists():
        return None
    if (p / "v5").is_dir():
        return "v5"
    # Xcode 16+ UniDB: flat .db file instead of v5/ tree
    if any(p.glob("*.db")):
        return "unidb"
    return None


def call_hierarchy_tool(
    *,
    qualified_name: str,
    project: str | None,
    max_results: int,
    index_store_path: str | None,
    indexstore_paths: dict[str, str] | None,
    default_store_path: str | None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Implementation of palace.code.call_hierarchy MCP tool.

    Args:
        qualified_name:    Symbol to query (short or qualified, e.g. "BalanceData").
        project:           Project slug for per-project IndexStore path resolution.
        max_results:       Maximum number of caller records to return.
        index_store_path:  Explicit override for IndexStoreDB DataStore path.
        indexstore_paths:  Dict of project slug → IndexStore path (from settings).
        default_store_path: Single-project fallback path (from settings).
        timeout_s:         Per-call timeout in seconds (default 30). Prevents runaway
                           on corrupt or oversized indexes.

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

    fmt = _detect_store_format(store_path)
    if fmt is None:
        return {
            "ok": False,
            "error_code": "index_store_not_found",
            "qualified_name": qualified_name,
            "project": project,
            "index_store_path": store_path,
            "message": (
                f"IndexStore path does not exist or is empty: {store_path}. "
                "Run symbol_index_swift (or equivalent) to build the index first."
            ),
        }
    if fmt == "unidb":
        return {
            "ok": False,
            "error_code": "index_store_format_unsupported",
            "qualified_name": qualified_name,
            "project": project,
            "index_store_path": store_path,
            "message": (
                f"IndexStore at {store_path} appears to be a Xcode 16+ UniDB format "
                "(flat .db file, no v5/ tree). palace.code.call_hierarchy requires "
                "IndexStoreDB v5 format. Re-index with an older Xcode or use the "
                "ZcashLightClientSample proxy project as a workaround."
            ),
        }

    short_name = qualified_name.split(".")[-1]

    t0 = time.perf_counter()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                find_callers, short_name, store_path, max_results=max_results
            )
            try:
                callers = future.result(timeout=timeout_s)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "call_hierarchy timeout after %.1fs for %s", timeout_s, qualified_name
                )
                return {
                    "ok": False,
                    "error_code": "timeout",
                    "qualified_name": qualified_name,
                    "project": project,
                    "timeout_s": timeout_s,
                    "message": (
                        f"IndexStore query timed out after {timeout_s:.0f}s. "
                        "The index may be corrupt or unusually large. "
                        "Try re-running symbol_index_swift to rebuild the index."
                    ),
                }
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

    result: dict[str, Any] = {
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
    if not caller_list:
        result["message"] = (
            f"No callers found for '{short_name}'. "
            "The symbol may not exist in the index, may be spelled differently, "
            "or the index may be stale — re-run symbol_index_swift to refresh."
        )
    return result
