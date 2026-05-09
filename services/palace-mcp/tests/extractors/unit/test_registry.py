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

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
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


def test_symbol_index_solidity_registered() -> None:
    """GIM-124: symbol_index_solidity must be present in EXTRACTORS."""
    extractor = registry.get("symbol_index_solidity")
    assert extractor is not None
    assert extractor.name == "symbol_index_solidity"


def test_dependency_surface_registered() -> None:
    extractor = registry.get("dependency_surface")
    assert extractor is not None
    assert extractor.name == "dependency_surface"


def test_dead_symbol_binary_surface_registered() -> None:
    extractor = registry.get("dead_symbol_binary_surface")
    assert extractor is not None
    assert extractor.name == "dead_symbol_binary_surface"


def test_hotspot_registered() -> None:
    extractor = registry.get("hotspot")
    assert extractor is not None
    assert extractor.name == "hotspot"


def test_code_ownership_registered() -> None:
    """GIM-216: code_ownership extractor must be present in EXTRACTORS."""
    extractor = registry.get("code_ownership")
    assert extractor is not None
    assert extractor.name == "code_ownership"


def test_symbol_index_swift_registered() -> None:
    extractor = registry.get("symbol_index_swift")
    assert extractor is not None
    assert extractor.name == "symbol_index_swift"


def test_reactive_dependency_tracer_registered() -> None:
    extractor = registry.get("reactive_dependency_tracer")
    assert extractor is not None
    assert extractor.name == "reactive_dependency_tracer"


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

        async def run(
            self, *, graphiti: Graphiti, ctx: ExtractorRunContext
        ) -> ExtractorStats:
            return ExtractorStats()

    class B(BaseExtractor):
        name = "__test_b"
        description = "b"

        async def run(
            self, *, graphiti: Graphiti, ctx: ExtractorRunContext
        ) -> ExtractorStats:
            return ExtractorStats()

    registry.register(A())
    registry.register(B())
    all_names = [x.name for x in registry.list_all()]
    a_idx = all_names.index("__test_a")
    b_idx = all_names.index("__test_b")
    assert a_idx < b_idx


def test_cross_repo_version_skew_registered():
    from palace_mcp.extractors.registry import EXTRACTORS

    assert "cross_repo_version_skew" in EXTRACTORS
    cls_or_inst = EXTRACTORS["cross_repo_version_skew"]
    name = cls_or_inst.name if hasattr(cls_or_inst, "name") else cls_or_inst.__name__
    assert name == "cross_repo_version_skew" or name == "CrossRepoVersionSkewExtractor"


def test_arch_layer_registered() -> None:
    """GIM-243: arch_layer must be present in EXTRACTORS."""
    extractor = registry.get("arch_layer")
    assert extractor is not None
    assert extractor.name == "arch_layer"
