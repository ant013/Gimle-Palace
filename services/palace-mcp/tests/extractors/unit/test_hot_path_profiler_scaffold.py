"""Scaffolding tests for hot_path_profiler."""

from __future__ import annotations


def test_hot_path_profiler_registered() -> None:
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS.get("hot_path_profiler")
    assert extractor is not None
    assert extractor.name == "hot_path_profiler"
    assert extractor.description


def test_hot_path_profiler_declares_indexes() -> None:
    from palace_mcp.extractors.hot_path_profiler import HotPathProfilerExtractor

    extractor = HotPathProfilerExtractor()
    index_text = " ".join(extractor.indexes)
    assert "HotPathSample" in index_text
    assert "HotPathSummary" in index_text
    assert "HotPathSampleUnresolved" in index_text
