from __future__ import annotations

from palace_mcp.audit.contracts import AuditContract, Severity
from palace_mcp.extractors.registry import EXTRACTORS


def test_audit_contract_returns_valid_contract() -> None:
    extractor = EXTRACTORS["testability_di"]
    contract = extractor.audit_contract()

    assert isinstance(contract, AuditContract)
    assert contract.extractor_name == "testability_di"
    assert contract.template_name == "testability_di.md"
    assert "$project_id" in contract.query
    assert "max_severity" in contract.query
    assert contract.severity_column == "max_severity"
    assert contract.severity_mapper is not None


def test_audit_contract_severity_mapper_uses_canonical_values() -> None:
    mapper = EXTRACTORS["testability_di"].audit_contract().severity_mapper

    assert mapper is not None
    assert mapper("high") == Severity.HIGH
    assert mapper("medium") == Severity.MEDIUM
    assert mapper("low") == Severity.LOW
