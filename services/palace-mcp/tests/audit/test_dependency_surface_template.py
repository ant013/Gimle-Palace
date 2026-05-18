"""Tests for dependency_surface template data-quality block (Task 4.2)."""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData
from palace_mcp.audit.renderer import render_section


def _section(findings: list[dict], stats: dict) -> AuditSectionData:
    return AuditSectionData(
        extractor_name="dependency_surface",
        run_id="run-dep",
        project="test-project",
        completed_at="2026-05-14T00:00:00+00:00",
        findings=findings,
        summary_stats=stats,
        template_name="dependency_surface.md",
    )


def test_missing_lockfile_renders_warning() -> None:
    stats = {"total": 1, "scopes": ["compile"], "missing_lockfile": True}
    findings = [
        {
            "purl": "pkg:github/foo/bar@unresolved",
            "scope": "compile",
            "declared_in": "Package.swift",
            "declared_version_constraint": "5.0.0",
            "resolved_version": "unresolved",
        }
    ]
    rendered = render_section(_section(findings, stats), "purl", 100)
    assert "Package.resolved" in rendered or "lockfile" in rendered.lower()


def test_declared_constraint_shown_when_lockfile_missing() -> None:
    stats = {"total": 1, "scopes": ["compile"], "missing_lockfile": True}
    findings = [
        {
            "purl": "pkg:github/foo/bar@unresolved",
            "scope": "compile",
            "declared_in": "Package.swift",
            "declared_version_constraint": "5.0.0",
            "resolved_version": "unresolved",
        }
    ]
    rendered = render_section(_section(findings, stats), "purl", 100)
    # Should show declared constraint, not @unresolved
    assert "5.0.0" in rendered
