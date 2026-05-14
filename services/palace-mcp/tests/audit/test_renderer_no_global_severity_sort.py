"""Tests that pinned order is not overridden by severity (GIM-283-5, Task 5.1)."""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData
from palace_mcp.audit.renderer import render_report


def _section(name: str, severity: str | None = None) -> AuditSectionData:
    findings = (
        [
            {
                "path": "Foo.swift",
                "hotspot_score": 1.0,
                "ccn_total": 5,
                "churn_count": 3,
                "_severity": severity,
            }
        ]
        if severity
        else []
    )
    return AuditSectionData(
        extractor_name=name,
        run_id=f"run-{name}",
        project="test",
        completed_at="2026-05-14T00:00:00+00:00",
        findings=findings,
        summary_stats={
            "file_count": len(findings),
            "max_score": 1.0 if findings else 0.0,
            "window_days": 90,
        },
        template_name="hotspot.md",
    )


def test_crypto_pinned_top_despite_info_severity() -> None:
    """crypto_domain_model precedes error_handling_policy regardless of severity.

    Under the old global severity sort, error_handling_policy (HIGH) would sort
    before crypto_domain_model (INFORMATIONAL). The pinned list puts crypto first.
    """
    sections = {
        "crypto_domain_model": _section("crypto_domain_model", "informational"),
        "error_handling_policy": _section("error_handling_policy", "high"),
    }

    report = render_report(
        project="test",
        sections=sections,
        severity_columns={},
        max_findings_per_section={},
        blind_spots=[],
    )

    crypto_pos = report.find("run-crypto_domain_model")
    error_pos = report.find("run-error_handling_policy")

    assert crypto_pos != -1, "crypto_domain_model section missing from report"
    assert error_pos != -1, "error_handling_policy section missing from report"
    assert crypto_pos < error_pos, (
        f"crypto_domain_model (INFORMATIONAL, pos={crypto_pos}) must appear before "
        f"error_handling_policy (HIGH, pos={error_pos}) — pinned order violated"
    )
