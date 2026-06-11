"""Unit tests for ArchLayerExtractor (GIM-243)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.extractors.arch_layer.extractor import (
    ArchLayerExtractor,
    _arch_severity,
    _run_extraction,
)
from palace_mcp.extractors.base import ExtractorOutcome, ExtractorRunContext
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


@pytest.mark.asyncio
async def test_run_extraction_reports_missing_input_when_no_modules_found() -> None:
    ctx = ExtractorRunContext(
        project_slug="testproj",
        group_id="project/testproj",
        repo_path=MagicMock(),
        run_id="run-1",
        duration_ms=0,
        logger=MagicMock(),
    )
    ruleset = SimpleNamespace(
        loader_warnings=[],
        rule_source=None,
        layers=[],
        rules=[],
        rules_declared=0,
        layer_for_module=lambda _slug: None,
    )

    with (
        patch(
            "palace_mcp.extractors.arch_layer.extractor.load_rules",
            return_value=ruleset,
        ),
        patch(
            "palace_mcp.extractors.arch_layer.extractor.parse_spm",
            return_value=SimpleNamespace(modules=[], edges=[], warnings=[]),
        ),
        patch(
            "palace_mcp.extractors.arch_layer.extractor.parse_gradle",
            return_value=SimpleNamespace(modules=[], edges=[], warnings=[]),
        ),
        patch(
            "palace_mcp.extractors.arch_layer.neo4j_writer.replace_project_snapshot",
            new=AsyncMock(return_value=(2, 1)),
        ),
    ):
        stats = await _run_extraction(ctx=ctx, driver=MagicMock())

    assert stats.nodes_written == 2
    assert stats.edges_written == 1
    assert stats.outcome == ExtractorOutcome.MISSING_INPUT
    assert "No SwiftPM or Gradle modules" in (stats.message or "")
    assert (
        stats.next_action
        == "Provide supported project manifests or module metadata before "
        "rerunning arch_layer if module coverage is required."
    )
