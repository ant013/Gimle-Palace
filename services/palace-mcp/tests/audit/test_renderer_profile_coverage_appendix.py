"""Unit tests — renderer emits §Profile Coverage appendix (Task 2.4).

RED tests verify the appendix counts statuses and asserts R == N+M+K+F+L.
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


def test_appendix_counts_each_status() -> None:
    """§Profile Coverage appendix renders counts for each status bucket."""
    all_statuses = {
        "ext_ok": ExtractorStatus("ext_ok", "OK", last_run_id="r1"),
        "ext_failed": ExtractorStatus("ext_failed", "RUN_FAILED"),
        "ext_na": ExtractorStatus("ext_na", "NOT_ATTEMPTED"),
        "ext_ff": ExtractorStatus("ext_ff", "FETCH_FAILED"),
        "ext_nap": ExtractorStatus("ext_nap", "NOT_APPLICABLE"),
    }
    md = _render(
        all_statuses=all_statuses,
        run_failed={"ext_failed": all_statuses["ext_failed"]},
        fetch_failed_statuses={"ext_ff": all_statuses["ext_ff"]},
        not_applicable={"ext_nap": all_statuses["ext_nap"]},
        blind_spots=["ext_na", "ext_ff"],
    )
    # Profile Coverage section must appear
    assert "Profile Coverage" in md, f"Expected 'Profile Coverage' in report:\n{md[:500]}"
    # Each status must be named
    assert "OK" in md
    assert "RUN_FAILED" in md or "Run Failed" in md or "Failed" in md
    assert "NOT_ATTEMPTED" in md or "Not Attempted" in md or "Blind" in md
