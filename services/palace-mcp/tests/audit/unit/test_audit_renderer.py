"""Unit tests for audit renderer (S1.3).

Tests:
- Renderer loads the top-level report template.
- Renderer dispatches to template via audit_contract().
- Findings are severity-sorted within a section (critical first).
- Sections are ordered by max severity.
- Blind spot section lists missing extractors.
"""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData, Severity
from palace_mcp.audit.renderer import render_report, render_section


def _hotspot_section(findings: list[dict] | None = None) -> AuditSectionData:
    return AuditSectionData(
        extractor_name="hotspot",
        run_id="run-001",
        project="test-project",
        completed_at="2026-05-07T12:00:00+00:00",
        findings=findings or [],
        summary_stats={"file_count": 0, "max_score": 0.0, "window_days": 90},
    )


def _dead_section(findings: list[dict] | None = None) -> AuditSectionData:
    return AuditSectionData(
        extractor_name="dead_symbol_binary_surface",
        run_id="run-002",
        project="test-project",
        completed_at="2026-05-07T12:00:00+00:00",
        findings=findings or [],
        summary_stats={
            "total": 0,
            "confirmed_dead": 0,
            "unused_candidate": 0,
            "skipped": 0,
        },
    )


class TestRendererLoadsTopTemplate:
    def test_renders_project_in_header(self) -> None:
        report = render_report(
            project="gimle",
            sections={},
            severity_columns={},
            max_findings_per_section={},
            blind_spots=[],
        )
        assert "# Audit Report — gimle" in report

    def test_renders_provenance_section(self) -> None:
        report = render_report(
            project="gimle",
            sections={},
            severity_columns={},
            max_findings_per_section={},
            blind_spots=[],
        )
        assert "## Provenance" in report
        assert "gimle" in report

    def test_renders_blind_spots_section(self) -> None:
        report = render_report(
            project="gimle",
            sections={},
            severity_columns={},
            max_findings_per_section={},
            blind_spots=["hotspot", "dead_symbol_binary_surface"],
        )
        assert "## Blind Spots" in report
        assert "`hotspot`" in report
        assert "`dead_symbol_binary_surface`" in report


class TestRendererDispatchesViaAuditContract:
    def test_hotspot_section_appears_in_report(self) -> None:
        section = _hotspot_section()
        report = render_report(
            project="gimle",
            sections={"hotspot": section},
            severity_columns={"hotspot": "hotspot_score"},
            max_findings_per_section={"hotspot": 100},
            blind_spots=[],
        )
        assert "## Code Hotspots" in report

    def test_empty_section_shows_no_findings_message(self) -> None:
        section = _hotspot_section(findings=[])
        rendered = render_section(
            section, severity_column="hotspot_score", max_findings=100
        )
        assert "No findings" in rendered
        assert "run-001" in rendered

    def test_section_with_findings_shows_table(self) -> None:
        findings = [
            {
                "path": "src/foo.py",
                "hotspot_score": 3.5,
                "ccn_total": 25,
                "churn_count": 10,
                "hotspot_score_severity": "high",
            }
        ]
        section = AuditSectionData(
            extractor_name="hotspot",
            run_id="run-001",
            project="test-project",
            completed_at=None,
            findings=findings,
            summary_stats={"file_count": 1, "max_score": 3.5, "window_days": 90},
        )
        rendered = render_section(
            section, severity_column="hotspot_score_severity", max_findings=100
        )
        assert "src/foo.py" in rendered
        assert "3.50" in rendered

    def test_coding_convention_section_renders_dominant_choice_and_violations(
        self,
    ) -> None:
        findings = [
            {
                "module": "WalletKit",
                "kind": "naming.test_class",
                "dominant_choice": "*Tests",
                "confidence": "certain",
                "sample_count": 12,
                "outliers": 2,
                "outlier_ratio": 0.17,
                "violations": [
                    {
                        "file": "Tests/WalletKit/WalletKitTest.swift",
                        "start_line": 3,
                        "message": "Module uses *Tests suffix.",
                        "severity": "medium",
                    }
                ],
            }
        ]
        section = AuditSectionData(
            extractor_name="coding_convention",
            run_id="run-cc",
            project="test-project",
            completed_at="2026-05-08T08:00:00+00:00",
            findings=findings,
            summary_stats={"total": 1},
            template_name="coding_convention.md",
        )
        rendered = render_section(
            section,
            severity_column="outlier_ratio",
            max_findings=100,
            severity_mapper=lambda value: (
                Severity.HIGH
                if float(value) >= 0.1
                else Severity.MEDIUM
                if float(value) > 0
                else Severity.LOW
            ),
        )
        assert "## Coding Conventions" in rendered
        assert "WalletKit" in rendered
        assert "`*Tests`" in rendered
        assert "WalletKitTest.swift" in rendered
        assert "HIGH" in rendered


class TestSeveritySortWithinSection:
    def test_critical_findings_before_low(self) -> None:
        findings = [
            {
                "path": "low.py",
                "hotspot_score": 0.5,
                "ccn_total": 1,
                "churn_count": 1,
                "sev": "low",
            },
            {
                "path": "critical.py",
                "hotspot_score": 5.0,
                "ccn_total": 50,
                "churn_count": 20,
                "sev": "critical",
            },
            {
                "path": "medium.py",
                "hotspot_score": 1.5,
                "ccn_total": 10,
                "churn_count": 5,
                "sev": "medium",
            },
        ]
        section = AuditSectionData(
            extractor_name="hotspot",
            run_id="run-x",
            project="p",
            completed_at=None,
            findings=findings,
            summary_stats={"file_count": 3, "max_score": 5.0, "window_days": 90},
        )
        rendered = render_section(section, severity_column="sev", max_findings=100)
        critical_pos = rendered.index("critical.py")
        medium_pos = rendered.index("medium.py")
        low_pos = rendered.index("low.py")
        assert critical_pos < medium_pos < low_pos


class TestSectionOrderByMaxSeverity:
    def test_high_severity_section_before_informational(self) -> None:
        hotspot_section = AuditSectionData(
            extractor_name="hotspot",
            run_id="run-h",
            project="p",
            completed_at=None,
            findings=[
                {
                    "path": "x.py",
                    "hotspot_score": 5.0,
                    "ccn_total": 50,
                    "churn_count": 20,
                    "sev": "critical",
                }
            ],
            summary_stats={"file_count": 1, "max_score": 5.0, "window_days": 90},
            max_severity=Severity.CRITICAL,
        )
        dead_section = AuditSectionData(
            extractor_name="dead_symbol_binary_surface",
            run_id="run-d",
            project="p",
            completed_at=None,
            findings=[],
            summary_stats={
                "total": 0,
                "confirmed_dead": 0,
                "unused_candidate": 0,
                "skipped": 0,
            },
            max_severity=Severity.INFORMATIONAL,
        )
        report = render_report(
            project="p",
            sections={
                "hotspot": hotspot_section,
                "dead_symbol_binary_surface": dead_section,
            },
            severity_columns={
                "hotspot": "sev",
                "dead_symbol_binary_surface": "candidate_state",
            },
            max_findings_per_section={
                "hotspot": 100,
                "dead_symbol_binary_surface": 100,
            },
            blind_spots=[],
        )
        hotspot_pos = report.index("## Code Hotspots")
        dead_pos = report.index("## Dead Symbols")
        assert hotspot_pos < dead_pos


class TestBlindSpotSection:
    def test_missing_extractors_listed_in_blind_spots(self) -> None:
        report = render_report(
            project="my-project",
            sections={},
            severity_columns={},
            max_findings_per_section={},
            blind_spots=["cross_module_contract", "public_api_surface"],
        )
        assert "`cross_module_contract`" in report
        assert "`public_api_surface`" in report

    def test_no_blind_spots_shows_all_present_message(self) -> None:
        section = _hotspot_section()
        report = render_report(
            project="p",
            sections={"hotspot": section},
            severity_columns={"hotspot": "sev"},
            max_findings_per_section={"hotspot": 100},
            blind_spots=[],
        )
        assert "No blind spots" in report or "All registered" in report


class TestExtractorPluralization:
    def test_singular_extractor_label(self) -> None:
        section = _hotspot_section()
        report = render_report(
            project="p",
            sections={"hotspot": section},
            severity_columns={"hotspot": "sev"},
            max_findings_per_section={"hotspot": 100},
            blind_spots=[],
        )
        assert "1 extractor contributed data" in report
        assert "1 extractors" not in report

    def test_plural_extractor_label(self) -> None:
        sections = {
            "hotspot": _hotspot_section(),
            "dead_symbol_binary_surface": AuditSectionData(
                extractor_name="dead_symbol_binary_surface",
                run_id="run-d",
                project="p",
                completed_at=None,
                findings=[],
                summary_stats={
                    "total": 0,
                    "confirmed_dead": 0,
                    "unused_candidate": 0,
                    "skipped": 0,
                },
                max_severity=Severity.INFORMATIONAL,
            ),
        }
        report = render_report(
            project="p",
            sections=sections,
            severity_columns={
                "hotspot": "sev",
                "dead_symbol_binary_surface": "candidate_state",
            },
            max_findings_per_section={
                "hotspot": 100,
                "dead_symbol_binary_surface": 100,
            },
            blind_spots=[],
        )
        assert "2 extractors contributed data" in report
        assert "{ '' if" not in report
