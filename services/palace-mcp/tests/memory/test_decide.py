"""Unit tests for palace.memory.decide() function."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.memory.decide import decide
from palace_mcp.memory.decide_models import DecideRequest

_REQ = DecideRequest(
    title="Adopt edge-based supersession",
    body="Decision nodes use (:Decision)-[:SUPERSEDES]->(:Decision) edges.",
    slice_ref="GIM-96",
    decision_maker_claimed="cto",
)

_REQUIRED_ATTRIBUTE_KEYS = {
    "body",
    "slice_ref",
    "decision_maker_claimed",
    "decision_kind",
    "provenance",
    "confidence",
    "decided_at",
    "extractor",
    "extractor_version",
    "attestation",
    "tags",
    "evidence_ref",
}


@pytest.fixture()
def mock_graphiti() -> MagicMock:
    g = MagicMock()
    g.embedder = MagicMock()
    return g


@pytest.mark.asyncio
async def test_happy_path_returns_ok(mock_graphiti: MagicMock) -> None:
    with patch(
        "palace_mcp.memory.decide.save_entity_node",
        new_callable=AsyncMock,
    ) as mock_save:
        mock_save.side_effect = _set_fake_embedding

        result = await decide(_REQ, g=mock_graphiti, group_id="project/gimle")

    assert result["ok"] is True
    assert "uuid" in result
    assert result["slice_ref"] == "GIM-96"
    assert result["decision_maker_claimed"] == "cto"
    assert result["name_embedding_dim"] == 1024


@pytest.mark.asyncio
async def test_entity_node_labels(mock_graphiti: MagicMock) -> None:
    captured: list = []

    async def _capture(g, node):  # type: ignore[no-untyped-def]
        node.name_embedding = [0.1] * 1024
        captured.append(node)

    with patch("palace_mcp.memory.decide.save_entity_node", side_effect=_capture):
        await decide(_REQ, g=mock_graphiti, group_id="project/gimle")

    node = captured[0]
    assert node.labels == ["Decision"]


@pytest.mark.asyncio
async def test_all_12_attribute_keys_present(mock_graphiti: MagicMock) -> None:
    captured: list = []

    async def _capture(g, node):  # type: ignore[no-untyped-def]
        node.name_embedding = [0.1] * 1024
        captured.append(node)

    with patch("palace_mcp.memory.decide.save_entity_node", side_effect=_capture):
        await decide(_REQ, g=mock_graphiti, group_id="project/gimle")

    attrs = captured[0].attributes
    assert _REQUIRED_ATTRIBUTE_KEYS.issubset(set(attrs.keys()))


@pytest.mark.asyncio
async def test_save_called_exactly_once(mock_graphiti: MagicMock) -> None:
    with patch(
        "palace_mcp.memory.decide.save_entity_node",
        new_callable=AsyncMock,
    ) as mock_save:
        mock_save.side_effect = _set_fake_embedding
        await decide(_REQ, g=mock_graphiti, group_id="project/gimle")

    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_infra_exception_propagates(mock_graphiti: MagicMock) -> None:
    with patch(
        "palace_mcp.memory.decide.save_entity_node",
        side_effect=RuntimeError("Neo4j down"),
    ):
        with pytest.raises(RuntimeError, match="Neo4j down"):
            await decide(_REQ, g=mock_graphiti, group_id="project/gimle")


@pytest.mark.asyncio
async def test_decided_at_is_iso8601_utc(mock_graphiti: MagicMock) -> None:
    import re

    with patch(
        "palace_mcp.memory.decide.save_entity_node",
        new_callable=AsyncMock,
    ) as mock_save:
        mock_save.side_effect = _set_fake_embedding
        result = await decide(_REQ, g=mock_graphiti, group_id="project/gimle")

    iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*\+00:00$")
    assert iso_pattern.match(result["decided_at"]), (
        f"decided_at {result['decided_at']!r} is not UTC ISO8601"
    )


@pytest.mark.asyncio
async def test_defaults_tags_evidence_ref_provenance_attestation(
    mock_graphiti: MagicMock,
) -> None:
    captured: list = []

    async def _capture(g, node):  # type: ignore[no-untyped-def]
        node.name_embedding = [0.1] * 1024
        captured.append(node)

    with patch("palace_mcp.memory.decide.save_entity_node", side_effect=_capture):
        await decide(_REQ, g=mock_graphiti, group_id="project/gimle")

    attrs = captured[0].attributes
    assert attrs["tags"] == []
    assert attrs["evidence_ref"] == []
    assert attrs["provenance"] == "asserted"
    assert attrs["attestation"] == "none"


async def _set_fake_embedding(g, node) -> None:  # type: ignore[no-untyped-def]
    node.name_embedding = [0.1] * 1024
