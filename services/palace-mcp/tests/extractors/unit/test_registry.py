"""Unit tests for extractor registry (spec §3.3)."""

from __future__ import annotations

import pytest
from graphiti_core import Graphiti

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)


class _FakeExtractor(BaseExtractor):
    name = "__test_fake"
    description = "fake for tests only"

    async def run(self, *, graphiti: Graphiti, ctx: ExtractorRunContext) -> ExtractorStats:
        return ExtractorStats()


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Snapshot + restore module-level EXTRACTORS across tests."""
    snapshot = dict(registry.EXTRACTORS)
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snapshot)


def test_get_unknown_returns_none() -> None:
    assert registry.get("definitely_not_registered") is None


def test_register_and_get() -> None:
    e = _FakeExtractor()
    registry.register(e)
    assert registry.get("__test_fake") is e


def test_register_duplicate_raises() -> None:
    e = _FakeExtractor()
    registry.register(e)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(e)


def test_list_all_returns_registered() -> None:
    e = _FakeExtractor()
    registry.register(e)
    names = [x.name for x in registry.list_all()]
    assert "__test_fake" in names


def test_list_all_preserves_insertion_order() -> None:
    class A(BaseExtractor):
        name = "__test_a"
        description = "a"

        async def run(self, *, graphiti: Graphiti, ctx: ExtractorRunContext) -> ExtractorStats:
            return ExtractorStats()

    class B(BaseExtractor):
        name = "__test_b"
        description = "b"

        async def run(self, *, graphiti: Graphiti, ctx: ExtractorRunContext) -> ExtractorStats:
            return ExtractorStats()

    registry.register(A())
    registry.register(B())
    all_names = [x.name for x in registry.list_all()]
    a_idx = all_names.index("__test_a")
    b_idx = all_names.index("__test_b")
    assert a_idx < b_idx
