"""Unit tests for crypto_domain_model extractor (GIM-239)."""

from __future__ import annotations

import pytest


def test_crypto_domain_model_registered() -> None:
    """B.1: extractor must be present in EXTRACTORS dict."""
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS.get("crypto_domain_model")
    assert extractor is not None
    assert extractor.name == "crypto_domain_model"


def test_audit_contract_returns_valid_contract() -> None:
    """B.2: audit_contract() returns AuditContract with required fields."""
    from palace_mcp.audit.contracts import AuditContract
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS["crypto_domain_model"]
    contract = extractor.audit_contract()

    assert contract is not None
    assert isinstance(contract, AuditContract)
    assert contract.extractor_name == "crypto_domain_model"
    assert contract.template_name == "crypto_domain_model.md"
    assert "$project_id" in contract.query
    assert contract.severity_column == "severity"
    assert contract.severity_mapper is not None


def test_audit_contract_severity_mapper_covers_all_levels() -> None:
    """B.2: severity_mapper maps known severity strings to Severity enum."""
    from palace_mcp.audit.contracts import Severity
    from palace_mcp.extractors.registry import EXTRACTORS

    extractor = EXTRACTORS["crypto_domain_model"]
    mapper = extractor.audit_contract().severity_mapper
    assert mapper is not None

    assert mapper("ERROR") == Severity.HIGH
    assert mapper("WARNING") == Severity.MEDIUM
    assert mapper("INFO") == Severity.INFORMATIONAL
    assert mapper("CRITICAL") == Severity.CRITICAL
    assert mapper("unknown_value") == Severity.INFORMATIONAL


def test_template_renders_without_error() -> None:
    """B.3: audit template renders without Jinja2 errors for findings + empty."""
    from pathlib import Path

    import jinja2

    template_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "palace_mcp"
        / "audit"
        / "templates"
        / "crypto_domain_model.md"
    )
    assert template_path.exists(), f"Template not found: {template_path}"

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        undefined=jinja2.StrictUndefined,
    )
    tmpl = env.get_template("crypto_domain_model.md")

    # Non-empty case
    rendered_findings = tmpl.render(
        kit_name="TronKit",
        findings=[
            {
                "severity": "HIGH",
                "kind": "private_key_string_storage",
                "file": "Sources/Core/Manager.swift",
                "start_line": 79,
                "message": "Mnemonic stored in UserDefaults",
            }
        ],
        critical_high=[
            {
                "severity": "HIGH",
                "kind": "private_key_string_storage",
                "file": "Sources/Core/Manager.swift",
                "start_line": 79,
                "message": "Mnemonic stored in UserDefaults",
            }
        ],
        medium_low=[],
        run_id="test-run-123",
        completed_at="2026-05-08T00:00:00Z",
    )
    assert "TronKit" in rendered_findings
    assert "private_key_string_storage" in rendered_findings

    # Empty-findings case
    rendered_empty = tmpl.render(
        kit_name="CleanKit",
        findings=[],
        critical_high=[],
        medium_low=[],
        run_id="test-run-456",
        completed_at="2026-05-08T00:00:00Z",
        files_scanned=97,
        rules_active=6,
    )
    assert "0 issues" in rendered_empty or "found 0" in rendered_empty
