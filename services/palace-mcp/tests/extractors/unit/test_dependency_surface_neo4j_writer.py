"""Unit-only tests for neo4j_writer argument shapes — Task 6.

Counter-based idempotency tests (which need real Neo4j) live in:
  tests/extractors/integration/test_dependency_surface_integration.py
"""

from __future__ import annotations

from palace_mcp.extractors.dependency_surface.neo4j_writer import write_to_neo4j  # noqa: F401


def test_write_to_neo4j_is_importable() -> None:
    """Smoke: module imports cleanly and exposes write_to_neo4j."""
    assert callable(write_to_neo4j)
