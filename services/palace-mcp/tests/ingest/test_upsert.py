"""Unit tests for palace_mcp.ingest.upsert — graphiti namespace API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

from palace_mcp.ingest.upsert import (
    UpsertResult,
    gc_orphans,
    invalidate_stale_assignments,
    upsert_with_change_detection,
)

RUN_STARTED = "2024-06-01T12:00:00+00:00"
GROUP_ID = "project/gimle"


def _make_node(uuid: str, text_hash: str = "abc123", last_seen: str = RUN_STARTED) -> MagicMock:
    node = MagicMock(spec=EntityNode)
    node.uuid = uuid
    node.labels = ["Entity", "Issue"]
    node.attributes = {
        "text_hash": text_hash,
        "palace_last_seen_at": last_seen,
        "source": "paperclip",
    }
    return node


def _make_graphiti(
    *,
    existing_node: EntityNode | None = None,
    get_by_uuid_error: Exception | None = None,
    nodes_list: list | None = None,
    edges_list: list | None = None,
) -> MagicMock:
    graphiti = MagicMock()

    if get_by_uuid_error:
        graphiti.nodes.entity.get_by_uuid = AsyncMock(side_effect=get_by_uuid_error)
    else:
        graphiti.nodes.entity.get_by_uuid = AsyncMock(return_value=existing_node)

    graphiti.nodes.entity.save = AsyncMock(return_value=None)
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=nodes_list or [])
    graphiti.nodes.entity.delete_by_uuids = AsyncMock(return_value=None)

    graphiti.edges.entity.get_by_node_uuid = AsyncMock(return_value=edges_list or [])
    graphiti.edges.entity.save = AsyncMock(return_value=None)
    return graphiti


# ── upsert_with_change_detection ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_inserts_new_node() -> None:
    graphiti = _make_graphiti(existing_node=None, get_by_uuid_error=LookupError("not found"))
    node = _make_node("uuid-1")
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.INSERTED
    graphiti.nodes.entity.save.assert_called_once_with(node)


@pytest.mark.asyncio
async def test_upsert_skips_unchanged_node() -> None:
    existing = _make_node("uuid-1", text_hash="same-hash")
    node = _make_node("uuid-1", text_hash="same-hash")
    graphiti = _make_graphiti(existing_node=existing)
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.SKIPPED_UNCHANGED
    # Save is called once to update palace_last_seen_at
    graphiti.nodes.entity.save.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_re_embeds_changed_node() -> None:
    existing = _make_node("uuid-1", text_hash="old-hash")
    node = _make_node("uuid-1", text_hash="new-hash")
    graphiti = _make_graphiti(existing_node=existing)
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.RE_EMBEDDED
    graphiti.nodes.entity.save.assert_called_once_with(node)


@pytest.mark.asyncio
async def test_upsert_skipped_refreshes_last_seen_at() -> None:
    existing = _make_node("uuid-1", text_hash="same", last_seen="2024-01-01T00:00:00+00:00")
    node = _make_node("uuid-1", text_hash="same", last_seen="2024-06-01T12:00:00+00:00")
    graphiti = _make_graphiti(existing_node=existing)
    await upsert_with_change_detection(graphiti, node)
    saved_node = graphiti.nodes.entity.save.call_args[0][0]
    assert saved_node.attributes["palace_last_seen_at"] == "2024-06-01T12:00:00+00:00"


@pytest.mark.asyncio
async def test_upsert_handles_value_error_as_not_found() -> None:
    graphiti = _make_graphiti(get_by_uuid_error=ValueError("wrong type"))
    node = _make_node("uuid-1")
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.INSERTED


@pytest.mark.asyncio
async def test_upsert_handles_runtime_error_as_not_found() -> None:
    graphiti = _make_graphiti(get_by_uuid_error=RuntimeError("backend error"))
    node = _make_node("uuid-1")
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.INSERTED


# ── invalidate_stale_assignments ──────────────────────────────────────────────


def _make_edge(
    name: str,
    source: str,
    target: str,
    invalid_at=None,
) -> MagicMock:
    edge = MagicMock(spec=EntityEdge)
    edge.name = name
    edge.source_node_uuid = source
    edge.target_node_uuid = target
    edge.invalid_at = invalid_at
    return edge


@pytest.mark.asyncio
async def test_invalidate_stale_assignments_invalidates_old_edge() -> None:
    old_edge = _make_edge("ASSIGNED_TO", source="issue-1", target="agent-old", invalid_at=None)
    graphiti = _make_graphiti(edges_list=[old_edge])
    count, has_active = await invalidate_stale_assignments(
        graphiti, issue_uuid="issue-1", new_agent_uuid="agent-new", run_started=RUN_STARTED
    )
    assert count == 1
    assert has_active is False
    graphiti.edges.entity.save.assert_called_once_with(old_edge)
    assert old_edge.invalid_at is not None


@pytest.mark.asyncio
async def test_invalidate_stale_assignments_skips_same_agent() -> None:
    """Same-agent active edge: count=0, has_active=True (caller must skip new edge)."""
    same_edge = _make_edge("ASSIGNED_TO", source="issue-1", target="agent-same", invalid_at=None)
    graphiti = _make_graphiti(edges_list=[same_edge])
    count, has_active = await invalidate_stale_assignments(
        graphiti, issue_uuid="issue-1", new_agent_uuid="agent-same", run_started=RUN_STARTED
    )
    assert count == 0
    assert has_active is True  # active same-agent edge found — caller skips new edge
    graphiti.edges.entity.save.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_stale_assignments_skips_already_invalid() -> None:
    from datetime import datetime, timezone

    already_invalid = _make_edge(
        "ASSIGNED_TO", "issue-1", "agent-old",
        invalid_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    graphiti = _make_graphiti(edges_list=[already_invalid])
    count, has_active = await invalidate_stale_assignments(
        graphiti, issue_uuid="issue-1", new_agent_uuid="agent-new", run_started=RUN_STARTED
    )
    assert count == 0
    assert has_active is False


@pytest.mark.asyncio
async def test_invalidate_stale_assignments_skips_non_assigned_to() -> None:
    on_edge = _make_edge("ON", source="comment-1", target="issue-1", invalid_at=None)
    graphiti = _make_graphiti(edges_list=[on_edge])
    count, has_active = await invalidate_stale_assignments(
        graphiti, issue_uuid="issue-1", new_agent_uuid="agent-new", run_started=RUN_STARTED
    )
    assert count == 0
    assert has_active is False


@pytest.mark.asyncio
async def test_invalidate_stale_assignments_none_new_agent_invalidates_all() -> None:
    edge = _make_edge("ASSIGNED_TO", "issue-1", "agent-old", invalid_at=None)
    graphiti = _make_graphiti(edges_list=[edge])
    count, has_active = await invalidate_stale_assignments(
        graphiti, issue_uuid="issue-1", new_agent_uuid=None, run_started=RUN_STARTED
    )
    assert count == 1
    assert has_active is False


@pytest.mark.asyncio
async def test_invalidate_stale_assignments_empty_edges() -> None:
    graphiti = _make_graphiti(edges_list=[])
    count, has_active = await invalidate_stale_assignments(
        graphiti, issue_uuid="issue-1", new_agent_uuid="agent-1", run_started=RUN_STARTED
    )
    assert count == 0
    assert has_active is False


# ── gc_orphans ────────────────────────────────────────────────────────────────


def _make_group_node(
    uuid: str,
    label: str,
    source: str = "paperclip",
    last_seen: str = "2024-01-01T00:00:00+00:00",
) -> MagicMock:
    node = MagicMock(spec=EntityNode)
    node.uuid = uuid
    node.labels = ["Entity", label]
    node.attributes = {"source": source, "palace_last_seen_at": last_seen}
    return node


@pytest.mark.asyncio
async def test_gc_orphans_deletes_stale_nodes() -> None:
    stale = _make_group_node("s1", "Issue", last_seen="2024-01-01T00:00:00+00:00")
    fresh = _make_group_node("f1", "Issue", last_seen="2024-06-02T00:00:00+00:00")
    graphiti = _make_graphiti(nodes_list=[stale, fresh])
    count = await gc_orphans(graphiti, group_id=GROUP_ID, cutoff="2024-06-01T12:00:00+00:00")
    assert count == 1
    graphiti.nodes.entity.delete_by_uuids.assert_called_once_with(["s1"])


@pytest.mark.asyncio
async def test_gc_orphans_skips_non_paperclip() -> None:
    non_pc = _make_group_node("n1", "Issue", source="external", last_seen="2024-01-01T00:00:00+00:00")
    graphiti = _make_graphiti(nodes_list=[non_pc])
    count = await gc_orphans(graphiti, group_id=GROUP_ID, cutoff="2024-06-01T12:00:00+00:00")
    assert count == 0
    graphiti.nodes.entity.delete_by_uuids.assert_not_called()


@pytest.mark.asyncio
async def test_gc_orphans_returns_zero_when_empty() -> None:
    graphiti = _make_graphiti(nodes_list=[])
    count = await gc_orphans(graphiti, group_id=GROUP_ID, cutoff="2024-06-01T12:00:00+00:00")
    assert count == 0


@pytest.mark.asyncio
async def test_gc_orphans_loop_fallback_when_delete_by_uuids_absent() -> None:
    """When delete_by_uuids is absent, falls back to loop delete_by_uuid."""
    stale = _make_group_node("s1", "Issue", last_seen="2024-01-01T00:00:00+00:00")
    graphiti = _make_graphiti(nodes_list=[stale])
    # Remove delete_by_uuids to simulate gap
    del graphiti.nodes.entity.delete_by_uuids
    graphiti.nodes.entity.delete_by_uuid = AsyncMock(return_value=None)

    count = await gc_orphans(graphiti, group_id=GROUP_ID, cutoff="2024-06-01T12:00:00+00:00")
    assert count == 1
    graphiti.nodes.entity.delete_by_uuid.assert_called_once_with("s1")


@pytest.mark.asyncio
async def test_gc_orphans_skips_ingest_run_nodes() -> None:
    """IngestRun nodes are not in PAPERCLIP_LABELS and should be ignored."""
    run_node = _make_group_node("r1", "IngestRun", last_seen="2024-01-01T00:00:00+00:00")
    graphiti = _make_graphiti(nodes_list=[run_node])
    count = await gc_orphans(graphiti, group_id=GROUP_ID, cutoff="2024-06-01T12:00:00+00:00")
    assert count == 0
