"""Unit tests for source_context emission in coding_convention (Task 3.4).

Verifies:
1. ConventionFinding and ConventionViolation have source_context field
2. coding_convention audit_contract query includes source_context column (W1)
"""

from __future__ import annotations


def test_convention_finding_has_source_context() -> None:
    """ConventionFinding must include source_context field."""
    from palace_mcp.extractors.coding_convention.models import ConventionFinding

    f = ConventionFinding(
        project_id="test",
        module="TronKit",
        kind="type_naming",
        dominant_choice="UpperCamelCase",
        confidence="heuristic",
        sample_count=10,
        outliers=1,
        run_id="r",
        source_context="library",
    )
    assert f.source_context == "library"


def test_convention_finding_source_context_default_other() -> None:
    """ConventionFinding.source_context defaults to 'other'."""
    from palace_mcp.extractors.coding_convention.models import ConventionFinding

    f = ConventionFinding(
        project_id="test",
        module="TronKit",
        kind="type_naming",
        dominant_choice="UpperCamelCase",
        confidence="heuristic",
        sample_count=10,
        outliers=1,
        run_id="r",
    )
    assert f.source_context == "other"


def test_convention_violation_has_source_context() -> None:
    """ConventionViolation must include source_context field."""
    from palace_mcp.extractors.coding_convention.models import ConventionViolation

    v = ConventionViolation(
        project_id="test",
        module="TronKit",
        kind="type_naming",
        file="Sources/TronKit/Foo.swift",
        start_line=5,
        end_line=5,
        message="violation",
        severity="low",
        run_id="r",
        source_context="library",
    )
    assert v.source_context == "library"


def test_convention_violation_source_context_default_other() -> None:
    """ConventionViolation.source_context defaults to 'other'."""
    from palace_mcp.extractors.coding_convention.models import ConventionViolation

    v = ConventionViolation(
        project_id="test",
        module="TronKit",
        kind="type_naming",
        file="Sources/TronKit/Foo.swift",
        start_line=5,
        end_line=5,
        message="violation",
        severity="low",
        run_id="r",
    )
    assert v.source_context == "other"


def test_coding_convention_query_includes_source_context() -> None:
    """audit_contract query must include source_context column (W1)."""
    from palace_mcp.extractors.coding_convention.extractor import (
        CodingConventionExtractor,
    )

    extractor = CodingConventionExtractor()
    contract = extractor.audit_contract()
    assert contract is not None
    assert "source_context" in contract.query, (
        "coding_convention audit query missing source_context column (W1)"
    )
