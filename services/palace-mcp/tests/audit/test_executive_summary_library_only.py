"""Tests: executive summary HIGH count is library-only.

Task 3.6 RED.
"""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData, Severity
from palace_mcp.audit.renderer import render_report


def _section(name: str, findings: list[dict], stats: dict | None = None) -> AuditSectionData:
    return AuditSectionData(
        extractor_name=name,
        run_id=f"run-{name}",
        project="test-project",
        completed_at=None,
        findings=findings,
        summary_stats=stats or {},
    )


class TestLibraryOnlyHighCount:
    def test_high_count_excludes_example_paths(self) -> None:
        """One section with library HIGH, one with example HIGH.
        Executive summary should report 1 section, not 2.
        """
        library_finding = {
            "path": "Sources/TronKit/Foo.swift",
            "top_owner_email": "alice@a.com",
            "top_owner_weight": 0.05,
            "total_authors": 1,
            "source_context": "library",
        }
        example_finding = {
            "file": "iOS Example/Demo.swift",
            "start_line": 1,
            "kind": "try_optional_swallow",
            "message": "try? swallows error silently",
            "severity": "high",
            "source_context": "example",
        }

        result = render_report(
            project="test-project",
            sections={
                "code_ownership": _section(
                    "code_ownership",
                    [library_finding],
                    {"files_analysed": 1, "diffuse_ownership_count": 1},
                ),
                "error_handling_policy": _section(
                    "error_handling_policy",
                    [example_finding],
                ),
            },
            severity_columns={
                "code_ownership": "top_owner_weight",
                "error_handling_policy": "severity",
            },
            max_findings_per_section={
                "code_ownership": 100,
                "error_handling_policy": 100,
            },
            blind_spots=[],
            severity_mappers={
                "code_ownership": lambda v: (
                    Severity.HIGH if v is not None and float(v) < 0.1 else Severity.LOW
                ),
            },
        )
        # Library HIGH section (code_ownership) → counted
        # Example HIGH section (error_handling_policy has only example finding) → not counted
        assert "1 section" in result
        assert "2 section" not in result

    def test_all_library_high_sections_counted(self) -> None:
        """Two sections, both with library HIGH → 2 counted."""
        f1 = {"path": "Sources/A.swift", "top_owner_email": "a@a.com", "top_owner_weight": 0.05, "total_authors": 1, "source_context": "library"}
        f2 = {
            "file": "Sources/B.swift",
            "start_line": 1,
            "kind": "try_optional_swallow",
            "message": "...",
            "severity": "high",
            "source_context": "library",
        }

        result = render_report(
            project="test-project",
            sections={
                "code_ownership": _section("code_ownership", [f1], {"files_analysed": 1, "diffuse_ownership_count": 1}),
                "error_handling_policy": _section("error_handling_policy", [f2]),
            },
            severity_columns={"code_ownership": "top_owner_weight", "error_handling_policy": "severity"},
            max_findings_per_section={"code_ownership": 100, "error_handling_policy": 100},
            blind_spots=[],
            severity_mappers={
                "code_ownership": lambda v: Severity.HIGH if v is not None and float(v) < 0.1 else Severity.LOW,
            },
        )
        assert "2 section" in result

    def test_no_critical_when_all_findings_are_example(self) -> None:
        """Section with only example HIGH findings → no critical/high in exec summary."""
        example_finding = {
            "file": "iOS Example/Demo.swift",
            "start_line": 1,
            "kind": "weak_kdf",
            "message": "weak KDF",
            "severity": "high",
            "source_context": "example",
        }
        result = render_report(
            project="test-project",
            sections={"crypto_domain_model": _section("crypto_domain_model", [example_finding])},
            severity_columns={"crypto_domain_model": "severity"},
            max_findings_per_section={"crypto_domain_model": 100},
            blind_spots=[],
        )
        assert "No critical or high severity findings" in result
