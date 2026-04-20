"""Unit tests for BaseExtractor ABC + ExtractionContext + ExtractorStats + errors.

Per spec §3.2 — validates the contract independently of Neo4j.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorConfigError,
    ExtractorError,
    ExtractorRuntimeError,
    ExtractorStats,
)


def test_base_extractor_abstract_cannot_instantiate() -> None:
    """BaseExtractor is ABC — cannot instantiate directly."""
    with pytest.raises(TypeError):
        BaseExtractor()  # type: ignore[abstract]


def test_subclass_without_name_and_extract_fails() -> None:
    """Subclass missing abstract members cannot be instantiated."""

    class Incomplete(BaseExtractor):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_valid_subclass_instantiates() -> None:
    """Subclass with name + extract instantiates."""

    class MyExtractor(BaseExtractor):
        name = "my_ext"
        description = "test"

        async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
            return ExtractorStats()

    e = MyExtractor()
    assert e.name == "my_ext"
    assert e.description == "test"
    assert e.constraints == []  # class defaults
    assert e.indexes == []


def test_extraction_context_frozen() -> None:
    """ExtractionContext is immutable (frozen dataclass)."""
    ctx = ExtractionContext(
        driver=AsyncMock(),
        project_slug="test",
        group_id="project/test",
        repo_path=Path("/repos/test"),
        run_id="abc-123",
        logger=logging.getLogger("test"),
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        ctx.project_slug = "other"  # type: ignore[misc]


def test_extractor_stats_defaults() -> None:
    stats = ExtractorStats()
    assert stats.nodes_written == 0
    assert stats.edges_written == 0


def test_extractor_stats_custom() -> None:
    stats = ExtractorStats(nodes_written=42, edges_written=10)
    assert stats.nodes_written == 42


def test_extractor_error_hierarchy() -> None:
    """ExtractorConfigError and ExtractorRuntimeError inherit from ExtractorError."""
    assert issubclass(ExtractorConfigError, ExtractorError)
    assert issubclass(ExtractorRuntimeError, ExtractorError)


def test_extractor_error_codes() -> None:
    """error_code class attribute present for MCP response mapping."""
    assert ExtractorError.error_code == "extractor_error"
    assert ExtractorConfigError.error_code == "extractor_config_error"
    assert ExtractorRuntimeError.error_code == "extractor_runtime_error"
