"""Direct Swift :CALLS edge materialization from IndexStore relations."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from palace_mcp.code.indexstore import collect_call_edges
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorExecutionMode,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.foundation.incremental_scope import (
    IncrementalMode,
    derive_swift_delta_scope,
)

_BATCH_SIZE = 500

_DELETE_INDEXSTORE_CALLS = """
MATCH (:Symbol {group_id: $group_id})-[rel:CALLS {via: 'indexstore'}]->(:Symbol {group_id: $group_id})
DELETE rel
"""

_DELETE_CHANGED_CALLER_CALLS = """
MATCH (source:Symbol {group_id: $group_id})-[rel:CALLS {via: 'indexstore'}]->(:Symbol {group_id: $group_id})
WHERE source.file_path IN $file_paths
DELETE rel
"""

_DELETE_STALE_CHANGED_CALLEE_CALLS = """
MATCH (:Symbol {group_id: $group_id})-[rel:CALLS {via: 'indexstore'}]->(target:Symbol {group_id: $group_id})
WHERE target.file_path IN $file_paths
  AND (target.deleted_at IS NOT NULL OR target:Deprecated)
DELETE rel
"""

_MERGE_INDEXSTORE_CALLS = """
UNWIND $rows AS row
MATCH (a:Symbol {qualified_name: row.source, group_id: row.group_id})
MATCH (b:Symbol {qualified_name: row.target, group_id: row.group_id})
MERGE (a)-[rel:CALLS]->(b)
SET rel.via = 'indexstore',
    rel.last_seen_in_run_id = $run_id,
    rel.last_seen_at = datetime($seen_at)
"""

_ACTIVE_SYMBOLS = """
MATCH (s:Symbol {group_id: $group_id})
WHERE s.deleted_at IS NULL AND NOT s:Deprecated
RETURN s.qualified_name AS qualified_name
"""


def _resolve_store_path(project: str, settings: Any) -> str | None:
    per_project = getattr(settings, "palace_indexstore_paths", {}) or {}
    if project and isinstance(per_project, dict):
        store_path = per_project.get(project)
        if store_path:
            return str(store_path)
    fallback = getattr(settings, "palace_sourcekit_index_store_path", None)
    return str(fallback) if fallback else None


def _detect_store_format(store_path: str) -> str | None:
    path = Path(store_path)
    if not path.exists():
        return None
    if path.is_file() and path.suffix == ".db":
        return "unidb"
    if (path / "v5").is_dir():
        return "v5"
    return None


async def _load_active_symbols(driver: Any, group_id: str) -> set[str]:
    async with driver.session() as session:
        result = await session.run(_ACTIVE_SYMBOLS, group_id=group_id)
        rows = await result.data()
    return {
        str(row["qualified_name"])
        for row in rows
        if row.get("qualified_name") is not None
    }


async def _replace_call_edges(
    driver: Any,
    *,
    group_id: str,
    run_id: str,
    seen_at: datetime,
    rows: list[dict[str, str]],
    full_snapshot: bool,
    caller_file_paths: set[str],
    stale_callee_paths: set[str],
) -> None:
    async with driver.session() as session:
        if full_snapshot:
            await session.run(_DELETE_INDEXSTORE_CALLS, group_id=group_id)
        else:
            if caller_file_paths:
                await session.run(
                    _DELETE_CHANGED_CALLER_CALLS,
                    group_id=group_id,
                    file_paths=sorted(caller_file_paths),
                )
            if stale_callee_paths:
                await session.run(
                    _DELETE_STALE_CHANGED_CALLEE_CALLS,
                    group_id=group_id,
                    file_paths=sorted(stale_callee_paths),
                )
        for i in range(0, len(rows), _BATCH_SIZE):
            await session.run(
                _MERGE_INDEXSTORE_CALLS,
                rows=rows[i : i + _BATCH_SIZE],
                run_id=run_id,
                seen_at=seen_at.isoformat(),
            )


class CallEdgeSwiftExtractor(BaseExtractor):
    name: ClassVar[str] = "call_edge_swift"
    description: ClassVar[str] = (
        "Materialize precise Swift :CALLS edges from IndexStore occurrence relations."
    )
    timeout_s: ClassVar[float] = 1800.0

    async def run(self, *, graphiti: Any, ctx: ExtractorRunContext) -> ExtractorStats:
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()
        if driver is None or settings is None:
            return ExtractorStats(
                outcome=ExtractorOutcome.MISSING_INPUT,
                message="call_edge_swift requires palace-mcp driver + settings",
                next_action="Initialise palace-mcp runtime before running call_edge_swift.",
            )

        store_path = _resolve_store_path(ctx.project_slug, settings)
        if not store_path:
            return ExtractorStats(
                outcome=ExtractorOutcome.MISSING_INPUT,
                message=(
                    "No IndexStore path configured for call_edge_swift; set "
                    "PALACE_INDEXSTORE_PATHS or PALACE_SOURCEKIT_INDEX_STORE_PATH."
                ),
                next_action="Configure an IndexStore DataStore path, then rerun call_edge_swift.",
            )

        fmt = _detect_store_format(store_path)
        if fmt != "v5":
            return ExtractorStats(
                outcome=ExtractorOutcome.MISSING_INPUT,
                message=(
                    f"IndexStore at {store_path} is not a v5 DataStore; "
                    "call_edge_swift requires DerivedData/Index.noindex/DataStore/v5."
                ),
                next_action="Rebuild the project with a v5 IndexStore, then rerun call_edge_swift.",
            )

        scope = await derive_swift_delta_scope(
            driver,
            repo_path=ctx.repo_path,
            project_id=ctx.group_id,
            settings=settings,
            force=ctx.force,
        )
        if scope.mode == IncrementalMode.SKIP:
            return ExtractorStats(
                outcome=ExtractorOutcome.SKIPPED,
                message="Skipped call_edge_swift: no changed Swift caller files.",
                next_action="Modify Swift source or run with force=True before rerunning.",
                mode=ExtractorExecutionMode.SKIPPED,
            )

        incremental_paths = scope.changed_paths | scope.removed_paths
        selected_source_files = (
            {
                str((ctx.repo_path / relative_path).resolve())
                for relative_path in sorted(scope.changed_paths)
            }
            if scope.mode == IncrementalMode.INCREMENTAL
            else None
        )
        scan = await asyncio.to_thread(
            collect_call_edges,
            store_path,
            selected_source_files=selected_source_files,
        )
        active_symbols = await _load_active_symbols(driver, ctx.group_id)

        counters = {
            "calls_seen": scan.counters.get("calls_seen", 0),
            "calls_resolved": 0,
            "missing_caller_symbol": 0,
            "missing_callee_symbol": 0,
            "missing_relation": scan.counters.get("missing_relation", 0),
        }
        edge_rows: list[dict[str, str]] = []
        for edge in scan.edges:
            if edge.source not in active_symbols:
                counters["missing_caller_symbol"] += 1
                continue
            if edge.target not in active_symbols:
                counters["missing_callee_symbol"] += 1
                continue
            edge_rows.append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "group_id": ctx.group_id,
                }
            )
        counters["calls_resolved"] = len(edge_rows)

        seen_at = datetime.now(timezone.utc)
        await _replace_call_edges(
            driver,
            group_id=ctx.group_id,
            run_id=ctx.run_id,
            seen_at=seen_at,
            rows=edge_rows,
            full_snapshot=scope.mode != IncrementalMode.INCREMENTAL,
            caller_file_paths=incremental_paths,
            stale_callee_paths=incremental_paths,
        )
        return ExtractorStats(
            edges_written=len(edge_rows),
            message=(
                "materialized "
                f"{len(edge_rows)} indexstore CALLS edges "
                f"(mode={scope.mode}, "
                f"calls_seen={counters['calls_seen']}, "
                f"calls_resolved={counters['calls_resolved']}, "
                f"missing_caller_symbol={counters['missing_caller_symbol']}, "
                f"missing_callee_symbol={counters['missing_callee_symbol']}, "
                f"missing_relation={counters['missing_relation']}, "
                f"records_scanned={scan.records_scanned}, "
                f"occurrences_scanned={scan.occurrences_scanned}, "
                f"scope_reason={scope.reason}, "
                f"validated_by={scope.validated_by}, "
                f"baseline_state={scope.baseline_state}, "
                f"changed_or_removed_files={len(incremental_paths)})"
            ),
            mode=(
                ExtractorExecutionMode.INCREMENTAL
                if scope.mode == IncrementalMode.INCREMENTAL
                else ExtractorExecutionMode.FULL
            ),
        )
