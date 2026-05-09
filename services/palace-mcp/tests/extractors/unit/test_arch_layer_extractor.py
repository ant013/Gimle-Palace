"""Unit tests for ArchLayerExtractor (GIM-243)."""

from __future__ import annotations

from palace_mcp.extractors.arch_layer.extractor import (
    ArchLayerExtractor,
    _arch_severity,
)
from palace_mcp.audit.contracts import Severity


class TestArchLayerExtractorContract:
    def test_name(self) -> None:
        assert ArchLayerExtractor.name == "arch_layer"

    def test_audit_contract_shape(self) -> None:
        contract = ArchLayerExtractor().audit_contract()
        assert contract.extractor_name == "arch_layer"
        assert contract.template_name == "arch_layer.md"
        assert "$project_id" in contract.query
        assert contract.severity_column == "severity"

    def test_audit_contract_severity_mapper(self) -> None:
        contract = ArchLayerExtractor().audit_contract()
        assert contract.severity_mapper is not None
        assert contract.severity_mapper("high") == Severity.HIGH

    def test_constraints_declared(self) -> None:
        assert len(ArchLayerExtractor.constraints) == 4
        combined = " ".join(ArchLayerExtractor.constraints)
        assert "Module" in combined
        assert "Layer" in combined
        assert "ArchRule" in combined
        assert "ArchViolation" in combined

    def test_indexes_declared(self) -> None:
        assert len(ArchLayerExtractor.indexes) == 2
        combined = " ".join(ArchLayerExtractor.indexes)
        assert "ArchViolation" in combined


class TestArchSeverityMapper:
    def test_known_values(self) -> None:
        assert _arch_severity("critical") == Severity.CRITICAL
        assert _arch_severity("high") == Severity.HIGH
        assert _arch_severity("medium") == Severity.MEDIUM
        assert _arch_severity("low") == Severity.LOW
        assert _arch_severity("informational") == Severity.INFORMATIONAL

    def test_case_insensitive(self) -> None:
        assert _arch_severity("HIGH") == Severity.HIGH
        assert _arch_severity("Low") == Severity.LOW

    def test_unknown_maps_to_informational(self) -> None:
        assert _arch_severity("unknown_severity") == Severity.INFORMATIONAL
        assert _arch_severity("") == Severity.INFORMATIONAL
        assert _arch_severity(None) == Severity.INFORMATIONAL
