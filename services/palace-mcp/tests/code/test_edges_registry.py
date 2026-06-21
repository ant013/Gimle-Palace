from __future__ import annotations

import re
from pathlib import Path

from palace_mcp.code.edges import CALL_EDGES, KNOWN_NON_CALL_EDGES
from palace_mcp.extractors.codebase_memory_bridge import _SKIPPED_CM_EDGES


def test_graphiti_relationship_types_are_classified() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "palace_mcp"
        / "graphiti_schema"
        / "edges.py"
    ).read_text()
    relation_names = set(re.findall(r'relation_name="([^"]+)"', source))

    assert CALL_EDGES.isdisjoint(KNOWN_NON_CALL_EDGES)
    assert relation_names
    assert relation_names <= CALL_EDGES | KNOWN_NON_CALL_EDGES


def test_skipped_cm_edges_are_known_non_call_relationships() -> None:
    assert _SKIPPED_CM_EDGES <= KNOWN_NON_CALL_EDGES
