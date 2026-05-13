"""RED tests for reactive_dependency_tracer audit_contract (Task 1.2).

Asserts that:
- audit_contract() returns a non-None AuditContract.
- extractor_name == "reactive_dependency_tracer".
- template_name points to an existing file in audit/templates/.
- query is non-empty and contains 'MATCH'.
- severity_column is non-empty.
- severity_mapper is present and correctly maps DiagnosticSeverity values.
"""

from __future__ import annotations

import pytest

from palace_mcp.audit.contracts import AuditContract, Severity
from palace_mcp.audit.renderer import _TEMPLATES_DIR
from palace_mcp.extractors.reactive_dependency_tracer.extractor import (
    ReactiveDependencyTracerExtractor,
)


@pytest.fixture
def extractor() -> ReactiveDependencyTracerExtractor:
    return ReactiveDependencyTracerExtractor()


@pytest.fixture
def contract(extractor: ReactiveDependencyTracerExtractor) -> AuditContract:
    result = extractor.audit_contract()
    assert result is not None, "audit_contract() must return non-None"
    return result


def test_extractor_has_audit_contract(extractor: ReactiveDependencyTracerExtractor) -> None:
    assert extractor.audit_contract() is not None


def test_contract_extractor_name(contract: AuditContract) -> None:
    assert contract.extractor_name == "reactive_dependency_tracer"


def test_contract_template_exists(contract: AuditContract) -> None:
    template_path = _TEMPLATES_DIR / contract.template_name
    assert template_path.exists(), (
        f"template {contract.template_name!r} not found at {template_path}"
    )


def test_contract_query_has_match(contract: AuditContract) -> None:
    assert "MATCH" in contract.query


def test_contract_severity_column(contract: AuditContract) -> None:
    assert contract.severity_column, "severity_column must be non-empty"


def test_contract_max_findings_positive(contract: AuditContract) -> None:
    assert contract.max_findings > 0


def test_contract_severity_mapper_present(contract: AuditContract) -> None:
    assert contract.severity_mapper is not None


def test_severity_mapper_error_maps_to_high(contract: AuditContract) -> None:
    assert contract.severity_mapper is not None
    assert contract.severity_mapper("error") == Severity.HIGH


def test_severity_mapper_warning_maps_to_medium(contract: AuditContract) -> None:
    assert contract.severity_mapper is not None
    assert contract.severity_mapper("warning") == Severity.MEDIUM


def test_severity_mapper_info_maps_to_informational(contract: AuditContract) -> None:
    assert contract.severity_mapper is not None
    assert contract.severity_mapper("info") == Severity.INFORMATIONAL
