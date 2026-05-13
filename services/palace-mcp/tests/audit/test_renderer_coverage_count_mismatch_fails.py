"""Unit tests — renderer aborts on coverage count mismatch (Task 2.4).

RED test: when bucket dicts claim entries that conflict with all_statuses
(e.g. not_applicable contains a name that has OK status in all_statuses),
the sum of bucket counts != total_in_all, triggering CoverageCountMismatch.
"""

from __future__ import annotations

import pytest

from palace_mcp.audit.discovery import ExtractorStatus
from palace_mcp.audit.renderer import render_report, CoverageCountMismatch


def test_count_drift_aborts_render() -> None:
    """Bucket dicts that double-count an extractor → CoverageCountMismatch.

    all_statuses has 2 OK extractors.
    not_applicable also claims ext_a (which is OK in all_statuses).
    Bucket sum: 2 (OK) + 0 + 0 + 0 + 1 (not_applicable) = 3 ≠ 2 → mismatch.
    """
    all_statuses = {
        "ext_a": ExtractorStatus("ext_a", "OK", last_run_id="r1"),
        "ext_b": ExtractorStatus("ext_b", "OK", last_run_id="r2"),
    }
    # ext_a is actually OK but we incorrectly put it in not_applicable
    corrupted_not_applicable = {
        "ext_a": ExtractorStatus("ext_a", "NOT_APPLICABLE"),
    }
    with pytest.raises(CoverageCountMismatch):
        render_report(
            project="tron-kit",
            sections={},
            severity_columns={},
            max_findings_per_section={},
            blind_spots=[],
            depth="full",
            generated_at="2026-05-13T12:00:00Z",
            all_statuses=all_statuses,
            run_failed={},
            fetch_failed_statuses={},
            not_applicable=corrupted_not_applicable,  # ext_a double-counted
        )
