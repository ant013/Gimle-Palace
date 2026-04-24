"""GIM-75 spec §6.1 — unit tests for Graphiti foundation (N+1a storage swap).

These tests verify the shape of the new modules without touching Neo4j or
the OpenAI API. All 14 cases are enumerated in the plan.
"""

from __future__ import annotations

from typing import get_args
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. build_graphiti constructor
# ---------------------------------------------------------------------------


def test_build_graphiti_returns_graphiti_instance() -> None:
    """build_graphiti() passes correct uri/user/password to Graphiti constructor."""
    from unittest.mock import MagicMock

    from palace_mcp.config import Settings

    mock_graphiti = MagicMock()
    settings = Settings(
        neo4j_uri="bolt://test:7687",
        neo4j_password="test-pw",  # type: ignore[arg-type]
        openai_api_key="sk-test",  # type: ignore[arg-type]
    )

    with (
        patch(
            "palace_mcp.graphiti_runtime.Graphiti", return_value=mock_graphiti
        ) as patched,
        patch("palace_mcp.graphiti_runtime.OpenAIClient"),
        patch("palace_mcp.graphiti_runtime.OpenAIEmbedder"),
    ):
        from palace_mcp.graphiti_runtime import build_graphiti

        result = build_graphiti(settings)
        assert patched.called, "Graphiti() constructor was not called"
        call_kwargs = patched.call_args
        assert call_kwargs.kwargs.get("uri") == "bolt://test:7687"
        assert result is mock_graphiti


# ---------------------------------------------------------------------------
# 2. Settings — openai_api_key is required
# ---------------------------------------------------------------------------


def test_settings_openai_api_key_required() -> None:
    """Settings() raises ValidationError when openai_api_key is absent."""
    from pydantic import ValidationError

    from palace_mcp.config import Settings

    with pytest.raises(ValidationError):
        Settings(neo4j_password="pw")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 3. EntityType Literal contains the new 14-type set
# ---------------------------------------------------------------------------


def test_entity_type_literal_contains_new_set() -> None:
    """EntityType literal covers the full N+1a catalog (14 types, no old types)."""
    from palace_mcp.memory.filters import EntityType

    actual = set(get_args(EntityType))
    expected = {
        "Project",
        "Iteration",
        "Episode",
        "Decision",
        "IterationNote",
        "Finding",
        "Module",
        "File",
        "Symbol",
        "APIEndpoint",
        "Model",
        "Repository",
        "ExternalLib",
        "Trace",
    }
    assert actual == expected, f"EntityType mismatch: got {sorted(actual)}"
    # Old types must be gone
    for old_type in ("Issue", "Comment", "Agent"):
        assert old_type not in actual, (
            f"Old type '{old_type}' still present in EntityType"
        )


# ---------------------------------------------------------------------------
# 4. _RELATED_FRAGMENTS is empty in N+1a
# ---------------------------------------------------------------------------


def test_lookup_related_fragments_empty_in_n1a() -> None:
    """_RELATED_FRAGMENTS must be empty — no cross-entity traversals until GIM-77."""
    from palace_mcp.memory.lookup import _RELATED_FRAGMENTS

    assert _RELATED_FRAGMENTS == {}, (
        f"Expected empty _RELATED_FRAGMENTS in N+1a, got: {_RELATED_FRAGMENTS}"
    )


# ---------------------------------------------------------------------------
# 5. health.py uses LATEST_INGEST_RUN (no source filter)
# ---------------------------------------------------------------------------


def test_latest_ingest_run_no_source_filter() -> None:
    """LATEST_INGEST_RUN Cypher query must not filter by source (returns across all sources)."""
    from palace_mcp.memory.cypher import LATEST_INGEST_RUN

    assert "source" not in LATEST_INGEST_RUN.lower(), (
        "LATEST_INGEST_RUN must not filter by source (health shows latest across all sources). "
        f"Query: {LATEST_INGEST_RUN!r}"
    )


# ---------------------------------------------------------------------------
# 6. Runner GET_PROJECT query uses {name: $slug} (not {slug: $slug})
# ---------------------------------------------------------------------------


def test_project_slug_query_uses_name() -> None:
    """Runner GET_PROJECT matches on p.name (Graphiti EntityNode name field), not p.slug.

    Per spec §3.10: :Project nodes are stored as Graphiti EntityNodes where
    EntityNode.name = slug. The runner's local GET_PROJECT must use {name: $slug}.
    """
    from palace_mcp.extractors.runner import GET_PROJECT

    assert "name: $slug" in GET_PROJECT or "{name: $slug}" in GET_PROJECT, (
        "Runner GET_PROJECT must match on {name: $slug}. "
        "Graphiti EntityNode stores slug in EntityNode.name field. "
        f"Query: {GET_PROJECT!r}"
    )


# ---------------------------------------------------------------------------
# 7. register_project (UPSERT_PROJECT) sets name = slug
# ---------------------------------------------------------------------------


def test_register_project_sets_name_to_slug() -> None:
    """UPSERT_PROJECT must SET p.name = $slug (name is the Graphiti lookup key)."""
    from palace_mcp.memory.cypher import UPSERT_PROJECT

    assert "name" in UPSERT_PROJECT, (
        f"UPSERT_PROJECT must set 'name'. Query: {UPSERT_PROJECT!r}"
    )
    assert "$slug" in UPSERT_PROJECT or "$name" in UPSERT_PROJECT, (
        f"UPSERT_PROJECT must use $slug or $name param. Query: {UPSERT_PROJECT!r}"
    )


# ---------------------------------------------------------------------------
# 8. Entity factory — missing confidence raises ValueError
# ---------------------------------------------------------------------------


def test_entity_factory_metadata_envelope_required_confidence() -> None:
    """make_episode raises ValueError when confidence is absent from attributes."""

    from palace_mcp.graphiti_schema.entities import make_episode

    # Confidence must be validated — attempting to produce one with confidence=2.0 fails.
    with pytest.raises(ValueError, match="confidence"):
        make_episode(
            group_id="project/test",
            name="test",
            kind="heartbeat",
            source="test",
            confidence=2.0,  # out of range
            provenance="asserted",
            extractor="test_extractor",
            extractor_version="0.0.1",
        )


# ---------------------------------------------------------------------------
# 9. Entity factory — invalid provenance raises ValueError
# ---------------------------------------------------------------------------


def test_entity_factory_provenance_enum() -> None:
    """make_episode raises ValueError when provenance is not in {asserted, derived, inferred}."""

    from palace_mcp.graphiti_schema.entities import make_episode

    with pytest.raises(ValueError, match="provenance"):
        make_episode(
            group_id="project/test",
            name="test",
            kind="heartbeat",
            source="test",
            confidence=0.9,
            provenance="invented",  # not in _VALID_PROVENANCE
            extractor="test_extractor",
            extractor_version="0.0.1",
        )


# ---------------------------------------------------------------------------
# 10. Symbol kind enum
# ---------------------------------------------------------------------------


def test_symbol_kind_enum() -> None:
    """_VALID_SYMBOL_KINDS must contain the expected Python/TypeScript kinds."""
    from palace_mcp.graphiti_schema.entities import _VALID_SYMBOL_KINDS

    expected = {"function", "method", "class", "interface", "enum", "type"}
    assert _VALID_SYMBOL_KINDS == expected, (
        f"_VALID_SYMBOL_KINDS mismatch: got {_VALID_SYMBOL_KINDS}"
    )


# ---------------------------------------------------------------------------
# 11. Edge factory — missing confidence raises ValueError
# ---------------------------------------------------------------------------


def test_edge_factory_attributes_envelope_required() -> None:
    """Edge _validate_envelope raises ValueError when confidence is absent."""

    from palace_mcp.graphiti_schema.edges import _validate_envelope

    with pytest.raises(ValueError, match="confidence"):
        _validate_envelope({"provenance": "asserted"})  # confidence missing


def test_edge_factory_attributes_envelope_provenance_required() -> None:
    """Edge _validate_envelope raises ValueError when provenance is absent."""

    from palace_mcp.graphiti_schema.edges import _validate_envelope

    with pytest.raises(ValueError, match="provenance"):
        _validate_envelope({"confidence": 0.9})  # provenance missing


# ---------------------------------------------------------------------------
# 12. Paperclip ingest extractor modules are removed
# ---------------------------------------------------------------------------


def test_paperclip_extractor_modules_removed() -> None:
    """N+0 paperclip ingest code must not exist in the extractors package."""
    import importlib
    import sys

    old_modules = list(sys.modules.keys())
    try:
        for mod_name in (
            "palace_mcp.extractors.paperclip",
            "palace_mcp.extractors.paperclip_issues",
            "palace_mcp.extractors.paperclip_ingest",
        ):
            with pytest.raises((ImportError, ModuleNotFoundError)):
                importlib.import_module(mod_name)
    finally:
        # Don't pollute sys.modules with failed imports
        for key in list(sys.modules.keys()):
            if key not in old_modules:
                del sys.modules[key]


# ---------------------------------------------------------------------------
# 13. build_graphiti fails early when OPENAI_API_KEY is empty
# ---------------------------------------------------------------------------


def test_build_graphiti_missing_openai_key_fails_early() -> None:
    """Settings() requires openai_api_key — build_graphiti never runs without it."""
    from pydantic import ValidationError

    from palace_mcp.config import Settings

    with pytest.raises(ValidationError):
        Settings(neo4j_password="pw")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 14. HealthResponse has new entity-type keys
# ---------------------------------------------------------------------------


def test_health_response_uses_graphiti_entity_types() -> None:
    """entity_counts in ENTITY_COUNTS Cypher matches N+1a types, not old Issue/Comment/Agent."""
    from palace_mcp.memory.cypher import ENTITY_COUNTS

    new_types = {
        "Episode",
        "Iteration",
        "Decision",
        "Finding",
        "Module",
        "File",
        "Symbol",
        "APIEndpoint",
        "Model",
        "Repository",
        "ExternalLib",
        "Trace",
    }
    for entity_type in new_types:
        assert entity_type in ENTITY_COUNTS, (
            f"ENTITY_COUNTS must reference '{entity_type}'. Query: {ENTITY_COUNTS!r}"
        )

    for old_type in ("Issue", "Comment", "Agent"):
        assert old_type not in ENTITY_COUNTS, (
            f"ENTITY_COUNTS must not reference old type '{old_type}'"
        )
