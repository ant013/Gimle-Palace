"""Tests for arch_layer template no-rules branch with module_count (Task 4.4)."""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData
from palace_mcp.audit.renderer import render_section


def _section(findings: list[dict], stats: dict) -> AuditSectionData:
    return AuditSectionData(
        extractor_name="arch_layer",
        run_id="run-arch",
        project="test-project",
        completed_at="2026-05-14T00:00:00+00:00",
        findings=findings,
        summary_stats=stats,
        template_name="arch_layer.md",
    )


def test_no_rules_branch_renders_module_count() -> None:
    stats = {
        "total": 0,
        "module_count": 12,
        "edge_count": 3,
        "rules_declared": False,
        "rule_source": None,
    }
    rendered = render_section(_section([], stats), "severity", 100)
    assert "12" in rendered
    assert "modules" in rendered.lower()
