from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData
from palace_mcp.audit.renderer import render_section


def _section(findings: list[dict], stats: dict) -> AuditSectionData:
    return AuditSectionData(
        extractor_name="testability_di",
        run_id="run-testability",
        project="wallet",
        completed_at="2026-05-08T00:00:00+00:00",
        findings=findings,
        summary_stats=stats,
    )


def test_template_renders_empty_state() -> None:
    rendered = render_section(
        _section([], {"patterns": 0, "test_doubles": 0, "untestable_sites": 0}),
        "max_severity",
        100,
    )

    assert "No findings" in rendered
    assert "testability_di" in rendered


def test_template_renders_low_risk_findings() -> None:
    rendered = render_section(
        _section(
            [
                {
                    "module": "WalletKit",
                    "language": "swift",
                    "style": "init_injection",
                    "framework": None,
                    "sample_count": 2,
                    "outliers": 0,
                    "confidence": "heuristic",
                    "test_doubles": [],
                    "untestable_sites": [],
                    "max_severity": "low",
                }
            ],
            {"patterns": 1, "test_doubles": 0, "untestable_sites": 0},
        ),
        "max_severity",
        100,
    )

    assert "WalletKit" in rendered
    assert "INIT_INJECTION" in rendered
    assert "LOW" in rendered


def test_template_renders_high_risk_findings() -> None:
    rendered = render_section(
        _section(
            [
                {
                    "module": "WalletKit",
                    "language": "kotlin",
                    "style": "service_locator",
                    "framework": None,
                    "sample_count": 1,
                    "outliers": 0,
                    "confidence": "heuristic",
                    "test_doubles": [
                        {
                            "kind": "mockk",
                            "language": "kotlin",
                            "target_symbol": None,
                            "test_file": "WalletRepositoryTest.kt",
                        }
                    ],
                    "untestable_sites": [
                        {
                            "file": "app/src/main/kotlin/com/example/WalletRepository.kt",
                            "start_line": 12,
                            "end_line": 12,
                            "category": "service_locator",
                            "symbol_referenced": "SessionManager.getInstance()",
                            "severity": "high",
                            "message": "Service locator usage hides dependencies from tests.",
                        }
                    ],
                    "max_severity": "high",
                }
            ],
            {"patterns": 1, "test_doubles": 1, "untestable_sites": 1},
        ),
        "max_severity",
        100,
    )

    assert "SERVICE_LOCATOR" in rendered
    assert "SessionManager.getInstance()" in rendered
    assert "HIGH" in rendered
