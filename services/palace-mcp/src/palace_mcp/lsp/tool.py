"""palace.code.call_hierarchy — MCP tool for LSP-backed call hierarchy.

Phase 2 spike (GIM-1166): proves callHierarchy end-to-end via sourcekit-lsp,
bypassing HNSW vector ranking entirely.

Resolution order for symbol → file mapping:
1. Neo4j :Symbol nodes (exact qualified_name match)
2. Filesystem search within workspace_root (for symbols not yet in graph)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver
    from palace_mcp.config import Settings

logger = logging.getLogger(__name__)

# Cypher: resolve Symbol → file_path + line_start
_SYMBOL_LOOKUP = """
MATCH (s:Symbol)
WHERE s.qualified_name = $qname
  AND ($group_id IS NULL OR s.group_id = $group_id)
  AND s.file_path IS NOT NULL
  AND s.kind IN ['struct', 'class', 'enum', 'protocol', 'typealias', 'extension']
RETURN s.file_path AS file_path,
       s.line_start AS line_start,
       s.qualified_name AS qualified_name,
       s.kind AS kind,
       s.group_id AS group_id
ORDER BY
  CASE WHEN s.source_scope = 'user' THEN 0 ELSE 1 END,
  s.file_path
LIMIT 1
"""

# Fallback: partial name match for short names like "BalanceData"
_SYMBOL_LOOKUP_PARTIAL = """
MATCH (s:Symbol)
WHERE (s.qualified_name = $qname OR s.qualified_name ENDS WITH $dot_qname)
  AND ($group_id IS NULL OR s.group_id = $group_id)
  AND s.file_path IS NOT NULL
  AND s.kind IN ['struct', 'class', 'enum', 'protocol', 'typealias', 'extension']
RETURN s.file_path AS file_path,
       s.line_start AS line_start,
       s.qualified_name AS qualified_name,
       s.kind AS kind,
       s.group_id AS group_id
ORDER BY
  CASE WHEN s.source_scope = 'user' THEN 0 ELSE 1 END,
  s.file_path
LIMIT 1
"""


async def call_hierarchy_tool(
    *,
    qualified_name: str,
    project: str | None,
    max_results: int,
    driver: "AsyncDriver",
    settings: "Settings",
) -> dict[str, Any]:
    """Implementation of palace.code.call_hierarchy MCP tool."""
    from palace_mcp.lsp.call_hierarchy import detect_sourcekit_lsp_binary, resolve_call_hierarchy

    # 1. Resolve workspace root for the project
    workspace_roots = settings.palace_sourcekit_workspace_roots
    workspace_root = workspace_roots.get(project or "") if workspace_roots else None

    # 2. Look up symbol in Neo4j graph
    group_id: str | None = f"project/{project}" if project else None
    symbol_row = await _lookup_symbol(driver, qualified_name, group_id)

    if symbol_row is None:
        # Try without group_id constraint
        symbol_row = await _lookup_symbol(driver, qualified_name, None)

    file_path: str | None = None
    line_start: int = 1

    if symbol_row is not None:
        file_path = symbol_row["file_path"]
        line_start = int(symbol_row.get("line_start") or 1)
        # Use the group_id from the symbol to infer workspace if not configured
        if workspace_root is None:
            sym_group = symbol_row.get("group_id", "")
            slug = sym_group.removeprefix("project/")
            workspace_root = workspace_roots.get(slug) if workspace_roots else None

    if file_path is None:
        # Filesystem fallback: search workspace_root for a file named after the symbol
        if workspace_root:
            file_path, line_start = _filesystem_fallback(
                qualified_name, workspace_root
            )
        if file_path is None:
            return {
                "ok": False,
                "error_code": "symbol_not_found",
                "qualified_name": qualified_name,
                "message": (
                    f"Symbol '{qualified_name}' not found in graph and not resolvable "
                    "via filesystem. Ensure the project is indexed or set "
                    "PALACE_SOURCEKIT_WORKSPACE_ROOTS."
                ),
            }

    if workspace_root is None:
        # Infer workspace root from file path: walk up to find .xcodeproj/.xcworkspace/Package.swift
        workspace_root = _infer_workspace_root(file_path)
        if workspace_root is None:
            return {
                "ok": False,
                "error_code": "workspace_not_found",
                "qualified_name": qualified_name,
                "file_path": file_path,
                "message": (
                    "Cannot determine workspace root. Set "
                    "PALACE_SOURCEKIT_WORKSPACE_ROOTS or ensure file is inside "
                    "an Xcode project or SwiftPM package."
                ),
            }

    logger.info(
        "call_hierarchy: qn=%s file=%s line=%d workspace=%s",
        qualified_name,
        file_path,
        line_start,
        workspace_root,
    )

    # 3. Run LSP query
    try:
        result = await resolve_call_hierarchy(
            symbol_name=qualified_name,
            file_path=file_path,
            line_start=line_start,
            workspace_root=workspace_root,
            binary=settings.palace_sourcekit_lsp_binary or detect_sourcekit_lsp_binary(),
            scratch_path=settings.palace_sourcekit_scratch_path,
            index_store_path=settings.palace_sourcekit_index_store_path,
            max_results=max_results,
        )
    except Exception as exc:
        logger.exception("call_hierarchy LSP error for %s", qualified_name)
        return {
            "ok": False,
            "error_code": "lsp_error",
            "qualified_name": qualified_name,
            "message": str(exc),
        }

    payload = result.to_dict()
    payload["ok"] = True
    return payload


async def _lookup_symbol(
    driver: "AsyncDriver", qualified_name: str, group_id: str | None
) -> dict[str, Any] | None:
    async with driver.session() as session:
        result = await session.run(
            _SYMBOL_LOOKUP,
            qname=qualified_name,
            group_id=group_id,
        )
        record = await result.single()
        if record is not None:
            return dict(record)

        # Partial: match "BalanceData" to "WalletKit.BalanceData" etc.
        result2 = await session.run(
            _SYMBOL_LOOKUP_PARTIAL,
            qname=qualified_name,
            dot_qname=f".{qualified_name}",
            group_id=group_id,
        )
        record2 = await result2.single()
        return None if record2 is None else dict(record2)


def _filesystem_fallback(
    symbol_name: str, workspace_root: str
) -> tuple[str | None, int]:
    """Search workspace_root for a Swift file that defines symbol_name."""
    short_name = symbol_name.split(".")[-1]
    candidate = Path(workspace_root) / f"{short_name}.swift"
    if candidate.exists():
        line = _find_definition_line(str(candidate), short_name)
        return str(candidate), line

    # Recursive search (limited depth)
    for swift_file in Path(workspace_root).rglob(f"{short_name}.swift"):
        content = swift_file.read_text(encoding="utf-8", errors="replace")
        if f"struct {short_name}" in content or f"class {short_name}" in content:
            line = _find_definition_line(str(swift_file), short_name)
            return str(swift_file), line
    return None, 1


def _find_definition_line(file_path: str, symbol_name: str) -> int:
    """Return 1-based line number of first struct/class/enum/protocol definition."""
    keywords = ("struct ", "class ", "enum ", "protocol ", "typealias ")
    try:
        with open(file_path, encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                stripped = line.strip()
                if any(stripped.startswith(kw + symbol_name) for kw in keywords):
                    return i
    except OSError:
        pass
    return 1


def _infer_workspace_root(file_path: str) -> str | None:
    """Walk up from file_path looking for Xcode/SwiftPM workspace indicators."""
    markers = ("Package.swift", "*.xcworkspace", "*.xcodeproj")
    path = Path(file_path).parent
    for _ in range(10):  # max 10 levels up
        for marker in markers:
            if marker.startswith("*"):
                ext = marker[1:]
                if any(path.glob(f"*{ext}")):
                    return str(path)
            elif (path / marker).exists():
                return str(path)
        if path.parent == path:
            break
        path = path.parent
    return None
