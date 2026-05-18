"""Tests for lockfile detection in dep_surface summary_stats (Task 4.1)."""

from __future__ import annotations

from palace_mcp.audit.fetcher import _build_summary_stats


def test_missing_lockfile_detected_when_all_unresolved() -> None:
    findings = [
        {
            "purl": "pkg:github/foo/bar@unresolved",
            "scope": "compile",
            "declared_in": "Package.swift",
            "declared_version_constraint": "5.0.0",
            "resolved_version": "unresolved",
        },
        {
            "purl": "pkg:github/foo/baz@unresolved",
            "scope": "compile",
            "declared_in": "Package.swift",
            "declared_version_constraint": "",
            "resolved_version": "unresolved",
        },
    ]
    stats = _build_summary_stats("dependency_surface", findings)
    assert stats["missing_lockfile"] is True


def test_lockfile_present_when_some_resolved() -> None:
    findings = [
        {
            "purl": "pkg:github/foo/bar@1.0.0",
            "scope": "compile",
            "declared_in": "Package.swift",
            "declared_version_constraint": "",
            "resolved_version": "1.0.0",
        },
        {
            "purl": "pkg:github/foo/baz@unresolved",
            "scope": "compile",
            "declared_in": "Package.swift",
            "declared_version_constraint": "",
            "resolved_version": "unresolved",
        },
    ]
    stats = _build_summary_stats("dependency_surface", findings)
    assert stats["missing_lockfile"] is False


def test_empty_findings_no_lockfile_false() -> None:
    stats = _build_summary_stats("dependency_surface", [])
    assert stats["missing_lockfile"] is False
