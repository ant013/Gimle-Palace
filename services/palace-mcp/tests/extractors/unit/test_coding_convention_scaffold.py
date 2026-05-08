"""Unit tests for coding convention extractor scaffolding."""

from palace_mcp.extractors.coding_convention import CodingConventionExtractor
from palace_mcp.extractors.registry import EXTRACTORS


def test_import_returns_extractor_class() -> None:
    assert CodingConventionExtractor.__name__ == "CodingConventionExtractor"


def test_scaffold_name_matches_registry_key() -> None:
    assert CodingConventionExtractor().name == "coding_convention"


def test_extractor_registered() -> None:
    extractor = EXTRACTORS.get("coding_convention")
    assert extractor is not None
    assert extractor.name == "coding_convention"
