"""Unit tests — renderer emits separate sections for each status bucket (Task 2.4).

RED tests verify that render_report produces:
- §Failed Extractors for RUN_FAILED bucket
- §Data-Quality Issues for FETCH_FAILED bucket
- §Blind Spots / NOT_ATTEMPTED as templated section
"""

from __future__ import annotations

from palace_mcp.audit.discovery import ExtractorStatus
from palace_mcp.audit.renderer import render_report


def _render(**kwargs: object) -> str:
    base: dict = dict(
        project="tron-kit",
        sections={},
        severity_columns={},
        max_findings_per_section={},
        blind_spots=[],
        depth="full",
        generated_at="2026-05-13T12:00:00Z",
        run_failed={},
        fetch_failed_statuses={},
        not_applicable={},
        all_statuses={},
    )
    base.update(kwargs)
    return render_report(**base)  # type: ignore[arg-type]


def test_failed_extractors_section_renders_for_run_failed() -> None:
    """RUN_FAILED extractors appear in §Failed Extractors section."""
    run_failed = {
        "public_api_surface": ExtractorStatus(
            "public_api_surface",
            "RUN_FAILED",
            last_run_id="run-99",
            error_code="extractor_runtime_error",
            error_message="Timeout after 60s",
        )
    }
    md = _render(run_failed=run_failed)
    assert "Failed Extractor" in md, "Expected §Failed Extractors section"
    assert "public_api_surface" in md
    assert "run-99" in md
    assert "extractor_runtime_error" in md


def test_data_quality_section_renders_for_fetch_failed() -> None:
    """FETCH_FAILED extractors appear in §Data-Quality Issues section."""
    fetch_failed = {
        "cross_module_contract": ExtractorStatus(
            "cross_module_contract",
            "FETCH_FAILED",
            last_run_id="run-77",
        )
    }
    md = _render(fetch_failed_statuses=fetch_failed)
    assert "Data-Quality" in md or "Data Quality" in md, (
        "Expected §Data-Quality Issues section"
    )
    assert "cross_module_contract" in md


def test_blind_spots_not_attempted_renders_correctly() -> None:
    """NOT_ATTEMPTED extractors appear in §Blind Spots section."""
    md = _render(blind_spots=["testability_di", "reactive_dependency_tracer"])
    assert "Blind Spot" in md or "blind_spots" in md.lower()
    assert "testability_di" in md
    assert "reactive_dependency_tracer" in md


def test_three_separate_sections_all_present() -> None:
    """All three status sections present when all three buckets non-empty."""
    run_failed = {
        "ext_a": ExtractorStatus("ext_a", "RUN_FAILED", error_code="err")
    }
    fetch_failed = {
        "ext_b": ExtractorStatus("ext_b", "FETCH_FAILED")
    }
    md = _render(
        blind_spots=["ext_c"],
        run_failed=run_failed,
        fetch_failed_statuses=fetch_failed,
    )
    assert "ext_a" in md
    assert "ext_b" in md
    assert "ext_c" in md
