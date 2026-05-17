"""Tests for pinned-then-severity ordering in audit renderer (GIM-283-5, Task 5.1/5.2)."""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData
from palace_mcp.audit.renderer import _SECTION_ORDER, _TEMPLATES_DIR, render_report

_HOTSPOT_STATS = {"file_count": 0, "max_score": 0.0, "window_days": 90}
_HOTSPOT_STATS_WITH_DATA = {"file_count": 1, "max_score": 1.0, "window_days": 90}


def _info_section(name: str) -> AuditSectionData:
    """INFORMATIONAL section using hotspot template (no findings)."""
    return AuditSectionData(
        extractor_name=name,
        run_id=f"run-{name}",
        project="test",
        completed_at="2026-05-14T00:00:00+00:00",
        findings=[],
        summary_stats=_HOTSPOT_STATS,
        template_name="hotspot.md",
    )


def _high_section(name: str) -> AuditSectionData:
    """HIGH severity section using hotspot template."""
    return AuditSectionData(
        extractor_name=name,
        run_id=f"run-{name}",
        project="test",
        completed_at="2026-05-14T00:00:00+00:00",
        findings=[
            {
                "path": "Foo.swift",
                "hotspot_score": 1.0,
                "ccn_total": 5,
                "churn_count": 3,
                "_severity": "high",
            }
        ],
        summary_stats=_HOTSPOT_STATS_WITH_DATA,
        template_name="hotspot.md",
    )


# The 15-entry pinned list from spec §B11 — hardcoded so the test is a strict guard.
_EXPECTED_PINNED_ORDER = (
    "crypto_domain_model",
    "error_handling_policy",
    "arch_layer",
    "hotspot",
    "dead_symbol_binary_surface",
    "dependency_surface",
    "code_ownership",
    "cross_repo_version_skew",
    "cross_module_contract",
    "public_api_surface",
    "coding_convention",
    "localization_accessibility",
    "reactive_dependency_tracer",
    "testability_di",
    "hot_path_profiler",
)


def test_pinned_first_severity_remainder() -> None:
    """All 15 _SECTION_ORDER entries appear before remainder, in list order.

    Remainder has HIGH severity, so the old global sort would put it first.
    The new pinned-then-severity strategy must keep all pinned sections ahead.
    """
    sections: dict[str, AuditSectionData] = {
        name: _info_section(name) for name in _EXPECTED_PINNED_ORDER
    }
    # Remainder: HIGH — under old sort this would appear before INFORMATIONAL pinned sections
    sections["z_unknown_extractor"] = _high_section("z_unknown_extractor")

    report = render_report(
        project="test",
        sections=sections,
        severity_columns={},
        max_findings_per_section={},
        blind_spots=[],
    )

    # Locate each pinned section by its unique run_id marker
    positions = {name: report.find(f"run-{name}") for name in _EXPECTED_PINNED_ORDER}
    remainder_pos = report.find("run-z_unknown_extractor")

    for name in _EXPECTED_PINNED_ORDER:
        assert positions[name] != -1, f"Pinned section {name!r} missing from report"
    assert remainder_pos != -1, "Remainder section missing from report"

    # Pinned sections must appear in exact _SECTION_ORDER sequence
    ordered_positions = [positions[name] for name in _EXPECTED_PINNED_ORDER]
    assert ordered_positions == sorted(ordered_positions), (
        f"Pinned sections out of order. Expected {list(_EXPECTED_PINNED_ORDER)}, "
        f"positions: {list(zip(_EXPECTED_PINNED_ORDER, ordered_positions))}"
    )

    # Remainder (HIGH) must appear after every pinned section
    last_pinned_pos = max(positions.values())
    assert remainder_pos > last_pinned_pos, (
        f"Remainder (HIGH, pos={remainder_pos}) should appear after last pinned "
        f"section (pos={last_pinned_pos})"
    )


def test_section_order_extractors_have_templates() -> None:
    """Every extractor in _SECTION_ORDER has a template in audit/templates/."""
    for name in _SECTION_ORDER:
        template_path = _TEMPLATES_DIR / f"{name}.md"
        assert template_path.exists(), (
            f"Missing template for pinned extractor {name!r}: {template_path}"
        )
