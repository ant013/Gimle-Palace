"""
palace.code.call_hierarchy_v2 — IndexStore direct-read implementation (GIM-1167).

Resolves callers of a Swift symbol by reading the DerivedData IndexStoreDB
directly via libIndexStore.dylib, bypassing sourcekit-lsp entirely.

Env vars:
    PALACE_SOURCEKIT_INDEX_STORE_PATH  - path to IndexStoreDB DataStore
    PALACE_INDEXSTORE_LIB_PATH         - override libIndexStore dylib path
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def call_hierarchy_v2_tool(
    *,
    qualified_name: str,
    project: str | None,
    max_results: int,
    index_store_path: str | None,
) -> dict[str, Any]:
    """Implementation of palace.code.call_hierarchy_v2 MCP tool.

    Args:
        qualified_name:   Symbol name to query (short or qualified, e.g. "BalanceData").
        project:          Project slug for future graph-based file resolution (unused in spike).
        max_results:      Maximum number of caller records to return.
        index_store_path: IndexStoreDB DataStore path. Falls back to
                          PALACE_SOURCEKIT_INDEX_STORE_PATH env var.

    Returns:
        Dict with ``ok: True`` + caller list, or ``ok: False`` + error_code.
    """
    from palace_mcp.code.indexstore import find_callers

    store_path = index_store_path or os.environ.get("PALACE_SOURCEKIT_INDEX_STORE_PATH")
    if not store_path:
        return {
            "ok": False,
            "error_code": "index_store_not_configured",
            "qualified_name": qualified_name,
            "message": (
                "Index store path not set. Pass index_store_path or set "
                "PALACE_SOURCEKIT_INDEX_STORE_PATH to the DerivedData DataStore path."
            ),
        }

    # Short name for the search (e.g. "WalletKit.BalanceData" → "BalanceData")
    short_name = qualified_name.split(".")[-1]

    t0 = time.perf_counter()
    try:
        callers = find_callers(
            short_name,
            store_path,
            max_results=max_results,
        )
    except Exception as exc:
        logger.exception("call_hierarchy_v2 IndexStore error for %s", qualified_name)
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
        "index_store_path": store_path,
        "caller_count": len(caller_list),
        "callers": caller_list,
        "latency_s": round(latency_s, 3),
        "approach": "indexstore_direct",
    }
