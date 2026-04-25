"""Unit tests for codebase_memory_bridge extractor.

Covers Tasks 1-6 acceptance criteria. All CM calls and Graphiti I/O are mocked.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.codebase_memory_bridge import (
    _BridgeState,
    _CM_TO_GRAPHITI_MAP,
    _METADATA_ENVELOPE_KEYS,
    _SKIPPED_CM_EDGES,
    _load_state,
    _save_state,
    CodebaseMemoryBridgeExtractor,
)
from palace_mcp.extractors.registry import EXTRACTORS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="test-proj",
        group_id="project/test-proj",
        repo_path=Path("/repos/test-proj"),  # fixed path → cm_project=repos-test-proj
        run_id="run-001",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


def _graphiti_mock() -> MagicMock:
    g = MagicMock()
    g.embedder = MagicMock()
    g.embedder.create = AsyncMock(return_value=[0.0] * 1024)
    g.driver = MagicMock()
    return g


def _cm_response(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    # Actual CM search_graph shape: {"results": [{"entity": {...}}, ...], "total": N}
    return {
        "results": [{"entity": n} for n in nodes],
        "total": len(nodes),
        "has_more": False,
    }


def _cm_edges_response(edges: list[dict[str, Any]]) -> dict[str, Any]:
    # Actual CM query_graph shape: {"columns": [...], "rows": [...], "total": N}
    if not edges:
        return {"columns": [], "rows": [], "total": 0}
    cols = list(edges[0].keys())
    rows = [[e.get(c) for c in cols] for e in edges]
    return {"columns": cols, "rows": rows, "total": len(edges)}


def _make_cm_node(
    cm_id: str = "uuid-1",
    name: str = "foo",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "uuid": cm_id,
        "name": name,
        "qualified_name": f"proj.{name}",
    }
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Task 1 — Extractor skeleton + registry
# ---------------------------------------------------------------------------


def test_extractor_registered() -> None:
    assert "codebase_memory_bridge" in EXTRACTORS
    assert isinstance(
        EXTRACTORS["codebase_memory_bridge"], CodebaseMemoryBridgeExtractor
    )


def test_extractor_name_and_version() -> None:
    ex = CodebaseMemoryBridgeExtractor()
    assert ex.name == "codebase_memory_bridge"
    assert ex.version == "0.1"


# ---------------------------------------------------------------------------
# Task 2 — Projection rules: coverage + metadata envelope
# ---------------------------------------------------------------------------


def test_projection_rules_coverage() -> None:
    """Every CM type in _CM_TO_GRAPHITI_MAP has target + provenance + confidence."""
    required = {"target", "provenance", "confidence"}
    for cm_type, rule in _CM_TO_GRAPHITI_MAP.items():
        missing = required - rule.keys()
        assert not missing, f"{cm_type!r} rule missing keys: {missing}"
        assert rule["provenance"] in {"asserted", "derived"}
        assert 0.0 <= float(rule["confidence"]) <= 1.0


def test_metadata_envelope_keys_defined() -> None:
    assert _METADATA_ENVELOPE_KEYS == {
        "confidence",
        "provenance",
        "extractor",
        "extractor_version",
        "evidence_ref",
        "observed_at",
    }


@pytest.mark.asyncio
async def test_metadata_envelope_on_every_projection(tmp_path: Path) -> None:
    """All 6 envelope fields present on every projected node."""
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()

    saved_nodes: list[Any] = []

    async def fake_save_node(graphiti: Any, node: Any) -> None:
        saved_nodes.append(node)

    async def fake_save_edge(graphiti: Any, edge: Any) -> None:
        pass

    file_node = _make_cm_node(
        "file-1", "main.py", {"path": "main.py", "xxh3_hash": "abc"}
    )
    sym_node = _make_cm_node(
        "sym-1", "foo_func", {"qualified_name": "test-proj.main.foo_func"}
    )

    cm_responses: dict[tuple[str, str], dict[str, Any]] = {
        ("search_graph", "Project"): _cm_response(
            [_make_cm_node("proj-1", "test-proj")]
        ),
        ("search_graph", "File"): _cm_response([file_node]),
        ("search_graph", "Module"): _cm_response([]),
        ("search_graph", "Function"): _cm_response([sym_node]),
        ("search_graph", "Method"): _cm_response([]),
        ("search_graph", "Class"): _cm_response([]),
        ("search_graph", "Interface"): _cm_response([]),
        ("search_graph", "Enum"): _cm_response([]),
        ("search_graph", "Type"): _cm_response([]),
        ("search_graph", "Route"): _cm_response([]),
        ("query_graph", "hash"): _cm_edges_response(
            [{"cm_id": "file-1", "xxh3": "abc"}]
        ),
        ("query_graph", "edges"): _cm_edges_response([]),
        ("get_architecture", ""): {"clusters": [], "hotspots": []},
    }

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return cm_responses[("get_architecture", "")]
        label = args.get("label", "")
        if tool == "search_graph":
            return cm_responses.get(("search_graph", label), {"nodes": []})
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3_hash" in q or "f.project" in q and "xxh3" in q:
                return cm_responses[("query_graph", "hash")]
            return cm_responses[("query_graph", "edges")]
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node",
            fake_save_node,
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge",
            fake_save_edge,
        ),
    ):
        stats = await ex.run(graphiti=g, ctx=ctx)

    assert stats.nodes_written >= 1
    for node in saved_nodes:
        attrs = node.attributes
        for key in _METADATA_ENVELOPE_KEYS:
            assert key in attrs, f"Node {node.name!r} missing envelope key {key!r}"


@pytest.mark.asyncio
async def test_cm_id_present_on_every_projected_node(tmp_path: Path) -> None:
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()
    saved_nodes: list[Any] = []

    async def fake_save_node(graphiti: Any, node: Any) -> None:
        saved_nodes.append(node)

    file_node = _make_cm_node(
        "file-1", "main.py", {"path": "main.py", "xxh3_hash": "abc"}
    )

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": [], "hotspots": []}
        label = args.get("label", "")
        if tool == "search_graph" and label == "File":
            return _cm_response([file_node])
        if tool == "search_graph":
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response([{"cm_id": "file-1", "xxh3": "abc"}])
            return _cm_edges_response([])
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node",
            fake_save_node,
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge", AsyncMock()
        ),
    ):
        await ex.run(graphiti=g, ctx=ctx)

    assert saved_nodes, "expected at least one node to be saved"
    for node in saved_nodes:
        assert "cm_id" in node.attributes, f"Node {node.name!r} missing cm_id"


@pytest.mark.asyncio
async def test_qualified_name_populated_on_symbol_file_module(tmp_path: Path) -> None:
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()
    saved_nodes: list[Any] = []

    async def fake_save_node(graphiti: Any, node: Any) -> None:
        saved_nodes.append(node)

    file_node = _make_cm_node(
        "f-1",
        "utils.py",
        {
            "path": "utils.py",
            "xxh3_hash": "x1",
            "qualified_name": "test-proj.utils",
        },
    )
    sym_node = _make_cm_node(
        "s-1",
        "helper",
        {
            "qualified_name": "test-proj.utils.helper",
            "file_path": "utils.py",
        },
    )
    mod_node = _make_cm_node(
        "m-1",
        "utils",
        {
            "qualified_name": "test-proj.utils",
            "path": "utils/",
        },
    )

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": [], "hotspots": []}
        label = args.get("label", "")
        if tool == "search_graph":
            if label == "File":
                return _cm_response([file_node])
            if label == "Module":
                return _cm_response([mod_node])
            if label == "Function":
                return _cm_response([sym_node])
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response([{"cm_id": "f-1", "xxh3": "x1"}])
            return _cm_edges_response([])
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node",
            fake_save_node,
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge", AsyncMock()
        ),
    ):
        await ex.run(graphiti=g, ctx=ctx)

    qn_nodes = [
        n
        for n in saved_nodes
        if any(lbl in n.labels for lbl in ["File", "Module", "Symbol"])
    ]
    assert qn_nodes, "expected File/Module/Symbol nodes"
    for node in qn_nodes:
        qn = node.attributes.get("qualified_name", "")
        assert qn, f"Node {node.name!r} has empty qualified_name"
        assert "test-proj" in qn, f"qualified_name {qn!r} doesn't contain project slug"


# ---------------------------------------------------------------------------
# Task 3 — Skipped edges not projected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skipped_edges_not_projected(tmp_path: Path) -> None:
    """CM edges in skip-list produce zero Graphiti edges."""
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()
    saved_edges: list[Any] = []

    file_node = _make_cm_node("f-1", "a.py", {"path": "a.py", "xxh3_hash": "h1"})
    sym_node = _make_cm_node(
        "s-1", "foo", {"file_path": "a.py", "qualified_name": "proj.foo"}
    )

    skipped_edge_rows = [
        {
            "rel_type": skipped,
            "edge_id": f"e-{i}",
            "src_id": "f-1",
            "tgt_id": "s-1",
            "rel_confidence": 1.0,
        }
        for i, skipped in enumerate(_SKIPPED_CM_EDGES)
    ]

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": [], "hotspots": []}
        label = args.get("label", "")
        if tool == "search_graph":
            if label == "File":
                return _cm_response([file_node])
            if label == "Function":
                return _cm_response([sym_node])
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response([{"cm_id": "f-1", "xxh3": "h1"}])
            return _cm_edges_response(skipped_edge_rows)
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node", AsyncMock()
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge",
            AsyncMock(side_effect=lambda g, e: saved_edges.append(e)),
        ),
    ):
        await ex.run(graphiti=g, ctx=ctx)

    assert saved_edges == [], (
        f"Expected zero edges, got {[e.name for e in saved_edges]}"
    )


# ---------------------------------------------------------------------------
# Task 4 — Derived layer: ArchitectureCommunity + Hotspot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_architecture_community_nodes_created(tmp_path: Path) -> None:
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()
    saved_nodes: list[Any] = []

    clusters = [
        {"id": "c0", "name": "community-0", "modularity": 0.72, "members": []},
        {"id": "c1", "name": "community-1", "modularity": 0.6, "members": []},
    ]

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": clusters, "hotspots": []}
        if tool == "search_graph":
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response([])
            return _cm_edges_response([])
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node",
            AsyncMock(side_effect=lambda g, n: saved_nodes.append(n)),
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge", AsyncMock()
        ),
    ):
        await ex.run(graphiti=g, ctx=ctx)

    community_nodes = [n for n in saved_nodes if "ArchitectureCommunity" in n.labels]
    assert len(community_nodes) == 2
    for cn in community_nodes:
        assert cn.attributes["provenance"] == "derived"
        assert 0.0 <= float(cn.attributes["confidence"]) <= 1.0
        assert "cm_id" in cn.attributes


@pytest.mark.asyncio
async def test_member_of_edges_created(tmp_path: Path) -> None:
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()
    saved_edges: list[Any] = []

    sym_node = _make_cm_node(
        "sym-1", "foo_fn", {"qualified_name": "tp.foo_fn", "file_path": "a.py"}
    )
    clusters = [
        {"id": "c0", "name": "community-0", "modularity": 0.8, "members": ["sym-1"]}
    ]

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": clusters, "hotspots": []}
        label = args.get("label", "")
        if tool == "search_graph" and label == "Function":
            return _cm_response([sym_node])
        if tool == "search_graph":
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response([])
            return _cm_edges_response([])
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node", AsyncMock()
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge",
            AsyncMock(side_effect=lambda g, e: saved_edges.append(e)),
        ),
    ):
        await ex.run(graphiti=g, ctx=ctx)

    member_of_edges = [e for e in saved_edges if e.name == "MEMBER_OF"]
    assert len(member_of_edges) == 1
    assert member_of_edges[0].attributes["provenance"] == "derived"


@pytest.mark.asyncio
async def test_hotspot_top_5_percent(tmp_path: Path) -> None:
    """Only top-5% of files become Hotspot nodes."""
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()
    saved_nodes: list[Any] = []

    # 20 files → 5% = 1 hotspot
    file_nodes_data = [
        _make_cm_node(
            f"f-{i}", f"file{i}.py", {"path": f"file{i}.py", "xxh3_hash": f"h{i}"}
        )
        for i in range(20)
    ]
    hotspots = [
        {"path": f"file{i}.py", "score": 100 - i, "cm_id": f"f-{i}"}
        for i in range(
            5
        )  # CM provides 5 hotspots; bridge should take only ceil(20*0.05)=1
    ]

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": [], "hotspots": hotspots}
        label = args.get("label", "")
        if tool == "search_graph" and label == "File":
            return _cm_response(file_nodes_data)
        if tool == "search_graph":
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response(
                    [{"cm_id": f"f-{i}", "xxh3": f"h{i}"} for i in range(20)]
                )
            return _cm_edges_response([])
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node",
            AsyncMock(side_effect=lambda g, n: saved_nodes.append(n)),
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge", AsyncMock()
        ),
    ):
        await ex.run(graphiti=g, ctx=ctx)

    hotspot_nodes = [n for n in saved_nodes if "Hotspot" in n.labels]
    total_files = 20
    max_hotspots = max(1, int(total_files * 0.05))
    assert len(hotspot_nodes) <= max_hotspots


# ---------------------------------------------------------------------------
# Task 5 — Incremental sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incremental_skips_unchanged_files(tmp_path: Path) -> None:
    """Second run on identical CM state writes 0 nodes/edges."""
    ex = CodebaseMemoryBridgeExtractor()
    state_file = tmp_path / "state.json"
    ex._state_path = state_file
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()

    file_node = _make_cm_node(
        "f-1", "a.py", {"path": "a.py", "xxh3_hash": "stable-hash"}
    )

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": [], "hotspots": []}
        label = args.get("label", "")
        if tool == "search_graph" and label == "File":
            return _cm_response([file_node])
        if tool == "search_graph":
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response([{"cm_id": "f-1", "xxh3": "stable-hash"}])
            return _cm_edges_response([])
        return {}

    async def counting_save(g: Any, n: Any) -> None:
        pass

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node",
            counting_save,
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge", AsyncMock()
        ),
    ):
        # First run — populates state
        await ex.run(graphiti=g, ctx=ctx)
        # Second run — same hashes → no writes
        stats2 = await ex.run(graphiti=g, ctx=ctx)

    assert stats2.nodes_written == 0
    assert stats2.edges_written == 0

    state = _load_state("test-proj", state_file)
    assert state.file_hashes == {"f-1": "stable-hash"}


@pytest.mark.asyncio
async def test_incremental_invalidates_removed_edges(tmp_path: Path) -> None:
    """File removed from CM → _invalidate_removed is called."""
    ex = CodebaseMemoryBridgeExtractor()
    state_file = tmp_path / "state.json"
    ex._state_path = state_file
    ctx = _ctx(tmp_path)

    # Pre-seed state with a file
    initial_state = _BridgeState(
        project_slug="test-proj",
        last_run_at="2026-01-01T00:00:00Z",
        file_hashes={"f-removed": "old-hash"},
    )
    _save_state(initial_state, state_file)

    g = _graphiti_mock()
    invalidate_calls: list[set[str]] = []

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "get_architecture":
            return {"clusters": [], "hotspots": []}
        if tool == "search_graph":
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                # f-removed is gone — empty hash result
                return _cm_edges_response([])
            return _cm_edges_response([])
        return {}

    async def fake_invalidate(
        self: Any, graphiti: Any, ctx: Any, removed: set[str]
    ) -> None:
        invalidate_calls.append(set(removed))

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node", AsyncMock()
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge", AsyncMock()
        ),
        patch.object(
            CodebaseMemoryBridgeExtractor, "_invalidate_removed", fake_invalidate
        ),
    ):
        await ex.run(graphiti=g, ctx=ctx)

    assert invalidate_calls, "Expected _invalidate_removed to be called"
    assert "f-removed" in invalidate_calls[0]


@pytest.mark.asyncio
async def test_incremental_uses_hash_compare_not_detect_changes(tmp_path: Path) -> None:
    """detect_changes raising doesn't affect bridge sync (not used for incremental)."""
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "state.json"
    ctx = _ctx(tmp_path)
    g = _graphiti_mock()

    file_node = _make_cm_node("f-1", "a.py", {"path": "a.py", "xxh3_hash": "h"})

    async def fake_call_cm(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "detect_changes":
            raise RuntimeError("detect_changes should NOT be called")
        if tool == "get_architecture":
            return {"clusters": [], "hotspots": []}
        label = args.get("label", "")
        if tool == "search_graph" and label == "File":
            return _cm_response([file_node])
        if tool == "search_graph":
            return {"nodes": []}
        if tool == "query_graph":
            q = args.get("query", "")
            if "xxh3" in q:
                return _cm_edges_response([{"cm_id": "f-1", "xxh3": "h"}])
            return _cm_edges_response([])
        return {}

    with (
        patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call_cm),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_node", AsyncMock()
        ),
        patch(
            "palace_mcp.extractors.codebase_memory_bridge.save_entity_edge", AsyncMock()
        ),
    ):
        # Should not raise even though detect_changes would raise
        stats = await ex.run(graphiti=g, ctx=ctx)

    assert stats.nodes_written >= 0  # bridge ran without error


# ---------------------------------------------------------------------------
# Task 6 — State persistence (health data)
# ---------------------------------------------------------------------------


def test_state_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state = _BridgeState(
        project_slug="proj-x",
        last_run_at="2026-04-25T10:00:00Z",
        last_run_duration_ms=1234,
        nodes_written_by_type={"Symbol": 5, "File": 2},
        edges_written_by_type={"DEFINES": 5},
        file_hashes={"cm-1": "abc123"},
    )
    _save_state(state, state_file)
    loaded = _load_state("proj-x", state_file)
    assert loaded.last_run_at == state.last_run_at
    assert loaded.last_run_duration_ms == 1234
    assert loaded.nodes_written_by_type == {"Symbol": 5, "File": 2}
    assert loaded.file_hashes == {"cm-1": "abc123"}


def test_state_missing_returns_empty(tmp_path: Path) -> None:
    state = _load_state("proj-y", tmp_path / "nonexistent.json")
    assert state.project_slug == "proj-y"
    assert state.file_hashes == {}
    assert state.last_run_at == ""


def test_state_wrong_project_returns_empty(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    _save_state(_BridgeState(project_slug="other"), state_file)
    state = _load_state("proj-z", state_file)
    assert state.project_slug == "proj-z"
    assert state.file_hashes == {}


# ---------------------------------------------------------------------------
# Task 6 — Health reporting: bridge section populated from state file
# ---------------------------------------------------------------------------


def test_health_bridge_section_present(tmp_path: Path) -> None:
    """_build_bridge_health reads state file and returns BridgeHealthInfo."""
    from palace_mcp.memory.health import _build_bridge_health

    state = _BridgeState(
        project_slug="proj-h",
        last_run_at="2026-04-25T10:00:00+00:00",
        last_run_duration_ms=500,
        nodes_written_by_type={"Symbol": 10},
        edges_written_by_type={"DEFINES": 10},
        file_hashes={"f-1": "abc"},
    )

    with patch(
        "palace_mcp.extractors.codebase_memory_bridge._load_state",
        return_value=state,
    ):
        info = _build_bridge_health("proj-h")

    assert info is not None
    assert info.last_run_at == "2026-04-25T10:00:00+00:00"
    assert info.last_run_duration_ms == 500
    assert info.nodes_written_by_type == {"Symbol": 10}
    assert info.edges_written_by_type == {"DEFINES": 10}
    assert info.cm_index_freshness_sec is not None
    assert isinstance(info.staleness_warning, bool)


def test_health_bridge_section_absent_when_no_runs() -> None:
    """_build_bridge_health returns None when no bridge run yet."""
    from palace_mcp.memory.health import _build_bridge_health

    empty_state = _BridgeState(project_slug="never-ran")

    with patch(
        "palace_mcp.extractors.codebase_memory_bridge._load_state",
        return_value=empty_state,
    ):
        info = _build_bridge_health("never-ran")

    assert info is None


def test_health_bridge_staleness_warning() -> None:
    """staleness_warning=True when last_run_at is long ago."""
    from palace_mcp.memory.health import (
        _build_bridge_health,
        _BRIDGE_STALENESS_THRESHOLD_S,
    )

    stale_state = _BridgeState(
        project_slug="stale",
        last_run_at="2020-01-01T00:00:00+00:00",  # very old
    )

    with patch(
        "palace_mcp.extractors.codebase_memory_bridge._load_state",
        return_value=stale_state,
    ):
        info = _build_bridge_health("stale")

    assert info is not None
    assert info.staleness_warning is True
    assert info.cm_index_freshness_sec is not None
    assert info.cm_index_freshness_sec > _BRIDGE_STALENESS_THRESHOLD_S
