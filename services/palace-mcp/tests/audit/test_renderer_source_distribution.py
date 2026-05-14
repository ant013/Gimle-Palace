"""Tests: renderer emits source distribution line and library_findings_empty warning.

Task 3.5b RED.
"""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData, Severity
from palace_mcp.audit.renderer import render_report


def _finding(path: str, source_context: str, weight: float = 0.5) -> dict:
    return {
        "path": path,
        "top_owner_email": "test@test.com",
        "top_owner_weight": weight,
        "total_authors": 1,
        "source_context": source_context,
    }


def _section(findings: list[dict]) -> AuditSectionData:
    return AuditSectionData(
        extractor_name="code_ownership",
        run_id="run-test",
        project="test-project",
        completed_at=None,
        findings=findings,
        summary_stats={"files_analysed": len(findings), "diffuse_ownership_count": 0},
    )


def _render(findings: list[dict]) -> str:
    return render_report(
        project="test-project",
        sections={"code_ownership": _section(findings)},
        severity_columns={"code_ownership": "top_owner_weight"},
        max_findings_per_section={"code_ownership": 100},
        blind_spots=[],
        severity_mappers={"code_ownership": lambda v: Severity.LOW},
    )


class TestSourceDistributionLine:
    def test_executive_summary_distribution_line(self) -> None:
        findings = (
            [_finding(f"Sources/S{i}.swift", "library") for i in range(5)]
            + [_finding(f"Example/E{i}.swift", "example") for i in range(3)]
            + [_finding(f"Tests/T{i}.swift", "test") for i in range(2)]
            + [_finding("Scripts/build.sh", "other")]
        )
        result = _render(findings)
        assert "library=5" in result
        assert "example=3" in result
        assert "test=2" in result
        assert "other=1" in result

    def test_distribution_line_format(self) -> None:
        findings = [
            _finding("Sources/A.swift", "library"),
            _finding("Example/B.swift", "example"),
        ]
        result = _render(findings)
        assert "Findings by source:" in result

    def test_library_findings_empty_warning_when_total_over_threshold(self) -> None:
        # 15 findings, 0 library → warning
        findings = [_finding(f"Example/E{i}.swift", "example") for i in range(8)] + [
            _finding(f"Tests/T{i}.swift", "test") for i in range(7)
        ]
        result = _render(findings)
        assert "library_findings_empty" in result

    def test_no_warning_when_library_findings_present(self) -> None:
        # 15 findings, 3 library → no warning
        findings = [_finding(f"Sources/S{i}.swift", "library") for i in range(3)] + [
            _finding(f"Example/E{i}.swift", "example") for i in range(12)
        ]
        result = _render(findings)
        assert "library_findings_empty" not in result

    def test_no_warning_when_total_under_threshold(self) -> None:
        # 8 total findings, 0 library — below threshold (>10) → no warning
        findings = [_finding(f"Example/E{i}.swift", "example") for i in range(8)]
        result = _render(findings)
        assert "library_findings_empty" not in result

    def test_no_warning_with_exactly_ten_findings_no_library(self) -> None:
        # threshold is total > 10, so exactly 10 = no warning
        findings = [_finding(f"Example/E{i}.swift", "example") for i in range(10)]
        result = _render(findings)
        assert "library_findings_empty" not in result
