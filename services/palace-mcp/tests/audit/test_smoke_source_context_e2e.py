"""E2E smoke: source_context library-only executive summary regression.

Task 3.7: synthetic project with library + example findings; full render pipeline;
assert headline severity excludes example HIGHs and distribution line is present.
"""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData, Severity
from palace_mcp.audit.renderer import render_report


def _finding(
    path: str,
    source_context: str,
    severity: str = "low",
    weight: float | None = None,
) -> dict:
    if weight is not None:
        return {
            "path": path,
            "top_owner_email": "dev@example.com",
            "top_owner_weight": weight,
            "total_authors": 2,
            "source_context": source_context,
        }
    return {
        "file": path,
        "start_line": 1,
        "kind": "weak_kdf",
        "message": "weak KDF detected",
        "severity": severity,
        "source_context": source_context,
    }


def _render_full_audit(
    library_findings: list[dict],
    example_findings: list[dict],
) -> str:
    """Run full render with two sections: crypto_domain_model + code_ownership."""
    all_findings = library_findings + example_findings

    crypto_section = AuditSectionData(
        extractor_name="crypto_domain_model",
        run_id="run-crypto",
        project="synthetic-project",
        completed_at=None,
        findings=all_findings,
        summary_stats={},
    )
    return render_report(
        project="synthetic-project",
        sections={"crypto_domain_model": crypto_section},
        severity_columns={"crypto_domain_model": "severity"},
        max_findings_per_section={"crypto_domain_model": 100},
        blind_spots=[],
    )


class TestSmokeSourceContextE2E:
    def test_headline_excludes_example_highs(self) -> None:
        """Library LOW + example HIGH → exec summary: no critical/high (only library counted)."""
        library_findings = [
            _finding("Sources/TronKit/Crypto.swift", "library", severity="low"),
            _finding("Sources/TronKit/Signer.swift", "library", severity="low"),
        ]
        example_findings = [
            _finding("iOS Example/Demo.swift", "example", severity="high"),
            _finding("iOS Example/Wallet.swift", "example", severity="high"),
        ]
        result = _render_full_audit(library_findings, example_findings)
        assert "No critical or high severity findings" in result
        assert "⚠" not in result.split("## Executive Summary")[1].split("---")[0].strip().replace(
            "⚠ **data_quality:", ""
        )

    def test_headline_counts_library_highs_only(self) -> None:
        """Library HIGH + example HIGH → exec summary counts 1 section (library only)."""
        library_findings = [
            _finding("Sources/TronKit/Crypto.swift", "library", severity="high"),
        ]
        example_findings = [
            _finding("iOS Example/Demo.swift", "example", severity="high"),
        ]
        result = _render_full_audit(library_findings, example_findings)
        assert "1 section(s) have critical/high findings" in result
        # Should not say 2 sections (example high excluded)
        assert "2 section" not in result

    def test_distribution_line_present(self) -> None:
        """Rendered report always includes Findings by source: line."""
        library_findings = [_finding("Sources/A.swift", "library", severity="low")]
        example_findings = [_finding("iOS Example/B.swift", "example", severity="low")]
        result = _render_full_audit(library_findings, example_findings)
        assert "Findings by source:" in result
        assert "library=1" in result
        assert "example=1" in result

    def test_source_context_appears_in_finding_rows(self) -> None:
        """Source_context renders in the crypto_domain_model section body."""
        library_findings = [
            _finding("Sources/TronKit/Crypto.swift", "library", severity="medium"),
        ]
        example_findings = [
            _finding("iOS Example/Demo.swift", "example", severity="low"),
        ]
        result = _render_full_audit(library_findings, example_findings)
        # Both source contexts appear in the section findings
        assert "library" in result
        assert "example" in result

    def test_library_empty_warning_when_only_example_findings(self) -> None:
        """11+ findings all example → warning block emitted before exec summary."""
        example_findings = [
            _finding(f"iOS Example/Demo{i}.swift", "example", severity="low")
            for i in range(12)
        ]
        result = _render_full_audit([], example_findings)
        assert "library_findings_empty" in result
        # Warning appears before executive summary
        warning_idx = result.index("library_findings_empty")
        exec_idx = result.index("## Executive Summary")
        assert warning_idx < exec_idx

    def test_no_library_empty_warning_when_library_present(self) -> None:
        """Library findings present → no warning even if example count is high."""
        library_findings = [_finding("Sources/A.swift", "library", severity="low")]
        example_findings = [
            _finding(f"iOS Example/Demo{i}.swift", "example", severity="low")
            for i in range(15)
        ]
        result = _render_full_audit(library_findings, example_findings)
        assert "library_findings_empty" not in result
