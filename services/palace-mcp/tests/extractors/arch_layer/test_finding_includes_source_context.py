"""Unit tests for source_context emission in arch_layer extractor (Task 3.4).

Verifies:
1. ArchViolation model has source_context field
2. _QUERY includes source_context column (W1)
"""

from __future__ import annotations


def test_arch_violation_has_source_context_field() -> None:
    """ArchViolation model must have source_context attribute."""
    from palace_mcp.extractors.arch_layer.models import ArchViolation

    v = ArchViolation(
        project_id="project/test",
        kind="forbidden_import",
        severity="medium",
        src_module="UI",
        dst_module="Data",
        rule_id="r1",
        message="violation",
        evidence="import X",
        file="Sources/UI/View.swift",
        start_line=10,
        run_id="run-1",
        source_context="library",
    )
    assert v.source_context == "library"


def test_arch_violation_source_context_default_other() -> None:
    """ArchViolation.source_context should default to 'other' if not provided."""
    from palace_mcp.extractors.arch_layer.models import ArchViolation

    v = ArchViolation(
        project_id="project/test",
        kind="forbidden_import",
        severity="medium",
        src_module="UI",
        dst_module="Data",
        rule_id="r1",
        message="violation",
        evidence="import X",
        file="Sources/UI/View.swift",
        start_line=10,
        run_id="run-1",
    )
    assert v.source_context == "other"


def test_arch_violation_classifies_library_file() -> None:
    """source_context is 'library' for Sources/ paths."""
    from palace_mcp.extractors.arch_layer.models import ArchViolation
    from palace_mcp.extractors.foundation.source_context import classify

    path = "Sources/TronKit/Core/Kit.swift"
    v = ArchViolation(
        project_id="project/test",
        kind="forbidden_import",
        severity="medium",
        src_module="Core",
        dst_module="UI",
        rule_id="r1",
        message="",
        evidence="",
        file=path,
        start_line=1,
        run_id="r",
        source_context=classify(path),
    )
    assert v.source_context == "library"


def test_arch_violation_classifies_test_file() -> None:
    """source_context is 'test' for Tests/ paths."""
    from palace_mcp.extractors.arch_layer.models import ArchViolation
    from palace_mcp.extractors.foundation.source_context import classify

    path = "Tests/CoreTests/KitTests.swift"
    v = ArchViolation(
        project_id="project/test",
        kind="forbidden_import",
        severity="medium",
        src_module="CoreTests",
        dst_module="Data",
        rule_id="r1",
        message="",
        evidence="",
        file=path,
        start_line=1,
        run_id="r",
        source_context=classify(path),
    )
    assert v.source_context == "test"


def test_arch_query_includes_source_context_column() -> None:
    """_QUERY RETURN clause must include source_context column."""
    from palace_mcp.extractors.arch_layer.extractor import _QUERY

    assert "source_context" in _QUERY, "_QUERY missing source_context column (W1)"
