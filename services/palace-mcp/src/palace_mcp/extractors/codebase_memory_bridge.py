"""codebase_memory_bridge extractor — projects CM facts into Graphiti.

Reads selected facts from codebase-memory-mcp via palace.code.* and writes
them as Graphiti EntityNode/EntityEdge with a metadata envelope
(confidence, provenance, extractor, cm_id, observed_at).

Projection rules per spec §3.2:
  CM :Project/:File/:Module  → Graphiti same-named nodes (asserted, 1.0)
  CM :Function/:Method/...   → Graphiti :Symbol{kind=...} (asserted, 1.0)
  CM :Route                  → Graphiti :APIEndpoint (asserted, 1.0)
  CM Louvain clusters        → :ArchitectureCommunity (derived, modularity)
  CM top-5% co-change files  → :Hotspot (derived, normalized rank)

Skipped CM edges: THROWS, READS, WRITES, HTTP_CALLS, ASYNC_CALLS,
  USES_TYPE, IMPLEMENTS, INHERITS, USAGE, TESTS, FILE_CHANGES_WITH.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

from palace_mcp import code_router
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.graphiti_runtime import save_entity_edge, save_entity_node
from palace_mcp.graphiti_schema.edges import (
    make_calls,
    make_contains,
    make_defines,
    make_handles,
    make_imports,
    make_locates_in,
    make_member_of,
)
from palace_mcp.graphiti_schema.entities import (
    make_api_endpoint,
    make_file,
    make_module,
    make_project,
    make_symbol,
)

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATE_PATH = Path.home() / ".paperclip" / "codebase-memory-bridge-state.json"

# CM node label → Graphiti Symbol.kind
_SYMBOL_KINDS: dict[str, str] = {
    "Function": "function",
    "Method": "method",
    "Class": "class",
    "Interface": "interface",
    "Enum": "enum",
    "Type": "type",
}

# CM edge types that must NOT be projected into Graphiti
_SKIPPED_CM_EDGES: frozenset[str] = frozenset(
    {
        "THROWS",
        "READS",
        "WRITES",
        "HTTP_CALLS",
        "ASYNC_CALLS",
        "USES_TYPE",
        "IMPLEMENTS",
        "INHERITS",
        "USAGE",
        "TESTS",
        "FILE_CHANGES_WITH",
        "DEFINES_METHOD",
    }
)

# Projection rules table — consumed by unit tests for coverage checks
_CM_TO_GRAPHITI_MAP: dict[str, dict[str, Any]] = {
    "Project": {"target": "Project", "provenance": "asserted", "confidence": 1.0},
    "File": {"target": "File", "provenance": "asserted", "confidence": 1.0},
    "Module": {"target": "Module", "provenance": "asserted", "confidence": 1.0},
    "Function": {
        "target": "Symbol",
        "kind": "function",
        "provenance": "asserted",
        "confidence": 1.0,
    },
    "Method": {
        "target": "Symbol",
        "kind": "method",
        "provenance": "asserted",
        "confidence": 1.0,
    },
    "Class": {
        "target": "Symbol",
        "kind": "class",
        "provenance": "asserted",
        "confidence": 1.0,
    },
    "Interface": {
        "target": "Symbol",
        "kind": "interface",
        "provenance": "asserted",
        "confidence": 1.0,
    },
    "Enum": {
        "target": "Symbol",
        "kind": "enum",
        "provenance": "asserted",
        "confidence": 1.0,
    },
    "Type": {
        "target": "Symbol",
        "kind": "type",
        "provenance": "asserted",
        "confidence": 1.0,
    },
    "Route": {"target": "APIEndpoint", "provenance": "asserted", "confidence": 1.0},
}

_METADATA_ENVELOPE_KEYS: frozenset[str] = frozenset(
    {
        "confidence",
        "provenance",
        "extractor",
        "extractor_version",
        "evidence_ref",
        "observed_at",
    }
)

# ---------------------------------------------------------------------------
# Bridge state (persisted between runs for incremental sync)
# ---------------------------------------------------------------------------


@dataclass
class _BridgeState:
    """Per-project state file for incremental sync."""

    project_slug: str
    last_run_at: str = ""
    last_run_duration_ms: int = 0
    nodes_written_by_type: dict[str, int] = field(default_factory=dict)
    edges_written_by_type: dict[str, int] = field(default_factory=dict)
    file_hashes: dict[str, str] = field(default_factory=dict)  # cm_id → xxh3


def _load_state(project_slug: str, state_path: Path = _STATE_PATH) -> _BridgeState:
    try:
        raw = json.loads(state_path.read_text())
        if raw.get("project_slug") == project_slug:
            return _BridgeState(
                project_slug=raw["project_slug"],
                last_run_at=raw.get("last_run_at", ""),
                last_run_duration_ms=raw.get("last_run_duration_ms", 0),
                nodes_written_by_type=raw.get("nodes_written_by_type", {}),
                edges_written_by_type=raw.get("edges_written_by_type", {}),
                file_hashes=raw.get("file_hashes", {}),
            )
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return _BridgeState(project_slug=project_slug)


def _save_state(state: _BridgeState, state_path: Path = _STATE_PATH) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "project_slug": state.project_slug,
                "last_run_at": state.last_run_at,
                "last_run_duration_ms": state.last_run_duration_ms,
                "nodes_written_by_type": state.nodes_written_by_type,
                "edges_written_by_type": state.edges_written_by_type,
                "file_hashes": state.file_hashes,
            }
        )
    )


# ---------------------------------------------------------------------------
# CM helpers
# ---------------------------------------------------------------------------


async def _call_cm(
    tool: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call a CM MCP tool directly via the shared _cm_session."""
    from mcp.types import CallToolResult, TextContent  # local import avoids circular

    session = code_router._cm_session
    if session is None:
        return {}
    result: CallToolResult = await session.call_tool(tool, arguments=arguments or {})
    if result.isError:
        return {}
    if result.structuredContent is not None:
        return dict(result.structuredContent)
    for block in result.content:
        if isinstance(block, TextContent):
            try:
                parsed = json.loads(block.text)
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except json.JSONDecodeError:
                return {"text": block.text}
    return {}


def _iter_nodes(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract list of node dicts from various CM response shapes."""
    if "nodes" in result and isinstance(result["nodes"], list):
        return [n for n in result["nodes"] if isinstance(n, dict)]
    if "result" in result and isinstance(result["result"], list):
        return [n for n in result["result"] if isinstance(n, dict)]
    return []


def _iter_edges(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract list of edge dicts from CM query_graph response."""
    if "result" in result and isinstance(result["result"], list):
        return [e for e in result["result"] if isinstance(e, dict)]
    if "edges" in result and isinstance(result["edges"], list):
        return [e for e in result["edges"] if isinstance(e, dict)]
    return []


def _get_id(node_data: dict[str, Any]) -> str:
    return str(node_data.get("uuid", node_data.get("id", node_data.get("name", ""))))


def _find_file_by_path(
    file_nodes: dict[str, EntityNode], path: str
) -> EntityNode | None:
    for node in file_nodes.values():
        if node.attributes.get("path") == path:
            return node
    return None


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class CodebaseMemoryBridgeExtractor(BaseExtractor):
    """Bridge extractor: projects selected CM facts into Graphiti."""

    name = "codebase_memory_bridge"
    version = "0.1"
    description = (
        "Project selected facts from codebase-memory-mcp into Graphiti "
        "with metadata envelope (cm_id, confidence, provenance, observed_at)."
    )

    # Overridable in tests for state-file isolation
    _state_path: Path = _STATE_PATH

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    def _tag(self) -> str:
        return f"{self.name}@{self.version}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _envelope(
        self, *, cm_id: str, confidence: float, provenance: str
    ) -> dict[str, Any]:
        return {
            "confidence": confidence,
            "provenance": provenance,
            "extractor": self._tag(),
            "extractor_version": self.version,
            "evidence_ref": [f"cm:{cm_id}"],
            "observed_at": self._now(),
        }

    # ---------------------------------------------------------------------------
    # run() — entry point called by runner
    # ---------------------------------------------------------------------------

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        state = _load_state(ctx.project_slug, self._state_path)

        # 1. Fetch current per-file XXH3 hashes from CM (incremental key)
        hash_result = await _call_cm(
            "query_graph",
            {
                "query": (
                    f"MATCH (f:File) WHERE f.project = '{ctx.project_slug}' "
                    "RETURN f.uuid AS cm_id, f.path AS path, f.xxh3_hash AS xxh3"
                )
            },
        )
        current_hashes: dict[str, str] = {}
        for row in _iter_edges(hash_result):  # query_graph rows are generic dicts
            cm_id = str(row.get("cm_id", ""))
            xxh3 = str(row.get("xxh3", ""))
            if cm_id:
                current_hashes[cm_id] = xxh3

        removed_cm_ids = set(state.file_hashes) - set(current_hashes)
        changed_cm_ids = {
            cid
            for cid, xxh3 in current_hashes.items()
            if state.file_hashes.get(cid) != xxh3
        }
        # First run (no prior state) → project everything
        if not state.file_hashes:
            changed_cm_ids = set(current_hashes)

        t0 = time.monotonic()
        nodes_written = 0
        edges_written = 0
        nodes_by_type: dict[str, int] = {}
        edges_by_type: dict[str, int] = {}

        # 2. Only re-project when there are changes (or first run)
        if changed_cm_ids or not state.last_run_at:
            n, e, nbt, ebt = await self._project_all(graphiti, ctx)
            nodes_written += n
            edges_written += e
            for k, v in nbt.items():
                nodes_by_type[k] = nodes_by_type.get(k, 0) + v
            for k, v in ebt.items():
                edges_by_type[k] = edges_by_type.get(k, 0) + v

        # 3. Invalidate edges for removed files (set invalid_at via Cypher)
        if removed_cm_ids and graphiti.driver is not None:
            await self._invalidate_removed(graphiti, ctx, removed_cm_ids)

        duration_ms = int((time.monotonic() - t0) * 1000)

        # 4. Persist updated state
        state.last_run_at = self._now()
        state.last_run_duration_ms = duration_ms
        state.nodes_written_by_type = nodes_by_type
        state.edges_written_by_type = edges_by_type
        state.file_hashes = current_hashes
        _save_state(state, self._state_path)

        return ExtractorStats(nodes_written=nodes_written, edges_written=edges_written)

    # ---------------------------------------------------------------------------
    # Projection — all nodes + edges
    # ---------------------------------------------------------------------------

    async def _project_all(
        self, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> tuple[int, int, dict[str, int], dict[str, int]]:
        """Project all CM node/edge types into Graphiti. Returns (n, e, nbt, ebt)."""
        nodes = 0
        edges = 0
        nbt: dict[str, int] = {}
        ebt: dict[str, int] = {}

        def inc_n(t: str) -> None:
            nonlocal nodes
            nodes += 1
            nbt[t] = nbt.get(t, 0) + 1

        def inc_e(t: str) -> None:
            nonlocal edges
            edges += 1
            ebt[t] = ebt.get(t, 0) + 1

        tag = self._tag()
        ver = self.version
        now = self._now()
        slug = ctx.project_slug

        # --- :Project ---
        proj_res = await _call_cm("search_graph", {"label": "Project", "project": slug})
        for nd in _iter_nodes(proj_res):
            cm_id = _get_id(nd)
            node = make_project(
                group_id=ctx.group_id,
                slug=slug,
                extractor=tag,
                extractor_version=ver,
                observed_at=now,
                extra={
                    **self._envelope(
                        cm_id=cm_id, confidence=1.0, provenance="asserted"
                    ),
                    "cm_id": f"{slug}:{cm_id}",
                    "name": nd.get("name", slug),
                },
            )
            await save_entity_node(graphiti, node)
            inc_n("Project")

        # --- :File ---
        file_nodes: dict[str, EntityNode] = {}
        file_res = await _call_cm("search_graph", {"label": "File", "project": slug})
        for nd in _iter_nodes(file_res):
            cm_id = _get_id(nd)
            path = nd.get("path", nd.get("name", ""))
            qualified_name = nd.get(
                "qualified_name",
                f"{slug}.{path.replace('/', '.').lstrip('.')}",
            )
            node = make_file(
                group_id=ctx.group_id,
                path=path,
                extractor=tag,
                extractor_version=ver,
                observed_at=now,
                extra={
                    **self._envelope(
                        cm_id=cm_id, confidence=1.0, provenance="asserted"
                    ),
                    "cm_id": f"{slug}:{cm_id}",
                    "qualified_name": qualified_name,
                    "xxh3": nd.get("xxh3_hash", ""),
                    "loc": nd.get("loc", 0),
                },
            )
            await save_entity_node(graphiti, node)
            file_nodes[cm_id] = node
            inc_n("File")

        # --- :Module ---
        mod_res = await _call_cm("search_graph", {"label": "Module", "project": slug})
        for nd in _iter_nodes(mod_res):
            cm_id = _get_id(nd)
            nm = nd.get("name", cm_id)
            qualified_name = nd.get("qualified_name", f"{slug}.{nm}")
            node = make_module(
                group_id=ctx.group_id,
                name=nm,
                extractor=tag,
                extractor_version=ver,
                observed_at=now,
                extra={
                    **self._envelope(
                        cm_id=cm_id, confidence=1.0, provenance="asserted"
                    ),
                    "cm_id": f"{slug}:{cm_id}",
                    "qualified_name": qualified_name,
                    "path": nd.get("path", ""),
                },
            )
            await save_entity_node(graphiti, node)
            inc_n("Module")

        # --- :Symbol (Function/Method/Class/Interface/Enum/Type) ---
        symbol_nodes: dict[str, EntityNode] = {}
        for cm_label, sym_kind in _SYMBOL_KINDS.items():
            sym_res = await _call_cm(
                "search_graph", {"label": cm_label, "project": slug}
            )
            for nd in _iter_nodes(sym_res):
                cm_id = _get_id(nd)
                nm = nd.get("name", cm_id)
                qualified_name = nd.get("qualified_name", f"{slug}.{nm}")
                node = make_symbol(
                    group_id=ctx.group_id,
                    name=nm,
                    kind=sym_kind,
                    extractor=tag,
                    extractor_version=ver,
                    observed_at=now,
                    extra={
                        **self._envelope(
                            cm_id=cm_id, confidence=1.0, provenance="asserted"
                        ),
                        "cm_id": f"{slug}:{cm_id}",
                        "qualified_name": qualified_name,
                        "file_path": nd.get("file_path", ""),
                        "signature": nd.get("signature", ""),
                    },
                )
                await save_entity_node(graphiti, node)
                symbol_nodes[cm_id] = node
                inc_n("Symbol")

        # --- :APIEndpoint (Route) ---
        route_res = await _call_cm("search_graph", {"label": "Route", "project": slug})
        for nd in _iter_nodes(route_res):
            cm_id = _get_id(nd)
            method = nd.get("method", "GET")
            path = nd.get("path", "/")
            node = make_api_endpoint(
                group_id=ctx.group_id,
                name=f"{method} {path}",
                method=method,
                path=path,
                extractor=tag,
                extractor_version=ver,
                observed_at=now,
                extra={
                    **self._envelope(
                        cm_id=cm_id, confidence=1.0, provenance="asserted"
                    ),
                    "cm_id": f"{slug}:{cm_id}",
                    "handler_cm_id": nd.get("handler_cm_id", ""),
                },
            )
            await save_entity_node(graphiti, node)
            inc_n("APIEndpoint")

        # --- Derived: ArchitectureCommunity (Louvain clusters from get_architecture) ---
        arch_res = await _call_cm("get_architecture")
        clusters = arch_res.get("clusters", [])
        community_nodes: dict[str, EntityNode] = {}
        if isinstance(clusters, list):
            for i, cluster in enumerate(clusters):
                if not isinstance(cluster, dict):
                    continue
                cm_id = str(cluster.get("id", i))
                modularity = max(0.0, min(1.0, float(cluster.get("modularity", 0.5))))
                members: list[str] = cluster.get("members", [])
                nm = cluster.get("name", f"community-{i}")
                attrs: dict[str, Any] = {
                    "cm_id": f"{slug}:{cm_id}",
                    "modularity": modularity,
                    "member_count": len(members),
                    "confidence": modularity,
                    "provenance": "derived",
                    "extractor": tag,
                    "extractor_version": ver,
                    "evidence_ref": [f"cm:{cm_id}"],
                    "observed_at": now,
                }
                community_node = EntityNode(
                    name=nm,
                    group_id=ctx.group_id,
                    labels=["ArchitectureCommunity"],
                    attributes=attrs,
                )
                await save_entity_node(graphiti, community_node)
                community_nodes[cm_id] = community_node
                inc_n("ArchitectureCommunity")

                for member_cm_id in members:
                    if member_cm_id not in symbol_nodes:
                        continue
                    edge = make_member_of(
                        group_id=ctx.group_id,
                        source_uuid=symbol_nodes[member_cm_id].uuid,
                        target_uuid=community_node.uuid,
                        fact=f"{member_cm_id} MEMBER_OF {nm}",
                        extractor=tag,
                        extractor_version=ver,
                        confidence=modularity,
                        provenance="derived",
                        extra={"cm_edge_id": f"member_of:{member_cm_id}:{cm_id}"},
                    )
                    await save_entity_edge(graphiti, edge)
                    inc_e("MEMBER_OF")

        # --- Derived: Hotspot (top-5% co-change files from get_architecture) ---
        hotspots = arch_res.get("hotspots", [])
        if isinstance(hotspots, list) and hotspots:
            total = len(file_nodes) or 1
            cutoff = max(1, int(total * 0.05))
            for rank, hs in enumerate(hotspots[:cutoff]):
                if not isinstance(hs, dict):
                    continue
                file_path = hs.get("path", "")
                _sc = hs.get("score") if hs.get("score") is not None else hs.get("cochange_score")
                score = float(_sc) if _sc is not None else 1.0
                norm_rank = max(0.0, min(1.0, 1.0 - rank / max(1, cutoff)))
                hs_cm_id = hs.get("cm_id", f"hotspot-{rank}")
                hs_attrs: dict[str, Any] = {
                    "cm_id_file": f"{slug}:{hs_cm_id}",
                    "cochange_score": score,
                    "rank": rank,
                    "confidence": norm_rank,
                    "provenance": "derived",
                    "extractor": tag,
                    "extractor_version": ver,
                    "evidence_ref": [f"cm:{hs_cm_id}"],
                    "observed_at": now,
                }
                hotspot_node = EntityNode(
                    name=f"hotspot-{file_path or rank}",
                    group_id=ctx.group_id,
                    labels=["Hotspot"],
                    attributes=hs_attrs,
                )
                await save_entity_node(graphiti, hotspot_node)
                inc_n("Hotspot")

                target = _find_file_by_path(file_nodes, file_path)
                if target is not None:
                    edge = make_locates_in(
                        group_id=ctx.group_id,
                        source_uuid=hotspot_node.uuid,
                        target_uuid=target.uuid,
                        fact=f"Hotspot {file_path} locates in file",
                        extractor=tag,
                        extractor_version=ver,
                        confidence=norm_rank,
                        provenance="derived",
                    )
                    await save_entity_edge(graphiti, edge)
                    inc_e("LOCATES_IN")

        # --- Asserted edges from CM ---
        all_nodes: dict[str, EntityNode] = {**file_nodes, **symbol_nodes}
        edges_res = await _call_cm(
            "query_graph",
            {
                "query": (
                    f"MATCH (a)-[r]->(b) WHERE a.project = '{slug}' "
                    "RETURN type(r) AS rel_type, id(r) AS edge_id, "
                    "id(a) AS src_id, id(b) AS tgt_id, r.confidence AS rel_confidence"
                )
            },
        )
        for ed in _iter_edges(edges_res):
            rel_type = str(ed.get("rel_type", ""))
            if not rel_type or rel_type in _SKIPPED_CM_EDGES:
                continue
            src_id = str(ed.get("src_id", ""))
            tgt_id = str(ed.get("tgt_id", ""))
            edge_id = str(ed.get("edge_id", ""))
            src_node = all_nodes.get(src_id)
            tgt_node = all_nodes.get(tgt_id)
            if src_node is None or tgt_node is None:
                continue
            _rc = ed.get("rel_confidence")
            rel_conf = float(_rc) if _rc is not None else 1.0
            extra: dict[str, Any] = {"cm_edge_id": f"{slug}:{edge_id}"}

            if rel_type.startswith("CONTAINS"):
                await save_entity_edge(
                    graphiti,
                    make_contains(
                        group_id=ctx.group_id,
                        source_uuid=src_node.uuid,
                        target_uuid=tgt_node.uuid,
                        fact="contains",
                        extractor=tag,
                        extractor_version=ver,
                        extra=extra,
                    ),
                )
                inc_e("CONTAINS")
            elif rel_type == "DEFINES":
                await save_entity_edge(
                    graphiti,
                    make_defines(
                        group_id=ctx.group_id,
                        source_uuid=src_node.uuid,
                        target_uuid=tgt_node.uuid,
                        fact="defines",
                        extractor=tag,
                        extractor_version=ver,
                        extra=extra,
                    ),
                )
                inc_e("DEFINES")
            elif rel_type == "CALLS":
                await save_entity_edge(
                    graphiti,
                    make_calls(
                        group_id=ctx.group_id,
                        source_uuid=src_node.uuid,
                        target_uuid=tgt_node.uuid,
                        fact="calls",
                        extractor=tag,
                        extractor_version=ver,
                        extra=extra,
                    ),
                )
                inc_e("CALLS")
            elif rel_type == "IMPORTS":
                await save_entity_edge(
                    graphiti,
                    make_imports(
                        group_id=ctx.group_id,
                        source_uuid=src_node.uuid,
                        target_uuid=tgt_node.uuid,
                        fact="imports",
                        extractor=tag,
                        extractor_version=ver,
                        extra=extra,
                    ),
                )
                inc_e("IMPORTS")
            elif rel_type == "HANDLES":
                await save_entity_edge(
                    graphiti,
                    make_handles(
                        group_id=ctx.group_id,
                        source_uuid=src_node.uuid,
                        target_uuid=tgt_node.uuid,
                        fact="handles",
                        extractor=tag,
                        extractor_version=ver,
                        confidence=rel_conf,
                        extra=extra,
                    ),
                )
                inc_e("HANDLES")

        return nodes, edges, nbt, ebt

    # ---------------------------------------------------------------------------
    # Incremental: invalidate edges for removed CM files
    # ---------------------------------------------------------------------------

    async def _invalidate_removed(
        self,
        graphiti: Graphiti,
        ctx: ExtractorRunContext,
        removed_cm_ids: set[str],
    ) -> None:
        """Set invalid_at on Graphiti edges whose CM source file was removed."""
        now = self._now()
        slug = ctx.project_slug
        for cm_id in removed_cm_ids:
            full_cm_id = f"{slug}:{cm_id}"
            # Mark edges with this cm_id in attributes as invalid
            async with graphiti.driver._async_driver.session() as session:  # type: ignore[attr-defined]
                await session.run(
                    "MATCH ()-[r]->() "
                    "WHERE r.cm_edge_id STARTS WITH $prefix "
                    "AND r.invalid_at IS NULL "
                    "SET r.invalid_at = $now",
                    prefix=f"{full_cm_id}",
                    now=now,
                )
