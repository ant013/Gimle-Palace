"""Scaffolding tests for prune_swift_symbols."""

from __future__ import annotations


def test_prune_swift_symbols_registered() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS.get("prune_swift_symbols")
    assert extractor is not None
    assert extractor.name == "prune_swift_symbols"
    assert extractor.description


def test_prune_swift_symbols_not_in_swift_kit_default_order() -> None:
    from palace_mcp.extractors.foundation.profiles import SWIFT_KIT_EXTRACTOR_ORDER

    assert "prune_swift_symbols" not in SWIFT_KIT_EXTRACTOR_ORDER
