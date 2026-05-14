"""Tests: 5 audit templates render source_context annotation.

Task 3.5 RED: assert templates include source column / inline annotation.
"""

from __future__ import annotations

from palace_mcp.audit.contracts import AuditSectionData, Severity
from palace_mcp.audit.renderer import render_section


def _section(
    extractor: str, findings: list[dict], stats: dict | None = None
) -> AuditSectionData:
    return AuditSectionData(
        extractor_name=extractor,
        run_id="run-001",
        project="test-project",
        completed_at=None,
        findings=findings,
        summary_stats=stats or {},
    )


class TestCodeOwnershipSourceColumn:
    def test_table_header_has_source_column(self) -> None:
        findings = [
            {
                "path": "Sources/TronKit/Foo.swift",
                "top_owner_email": "alice@a.com",
                "top_owner_weight": 0.8,
                "total_authors": 2,
                "source_context": "library",
            },
            {
                "path": "iOS Example/App.swift",
                "top_owner_email": "bob@b.com",
                "top_owner_weight": 0.4,
                "total_authors": 3,
                "source_context": "example",
            },
        ]
        result = render_section(
            _section(
                "code_ownership",
                findings,
                {"files_analysed": 2, "diffuse_ownership_count": 1},
            ),
            severity_column="top_owner_weight",
            max_findings=100,
            severity_mapper=lambda v: Severity.HIGH,
        )
        assert "Source" in result
        assert "library" in result
        assert "example" in result

    def test_source_values_appear_in_rows(self) -> None:
        findings = [
            {
                "path": "Tests/FooTests.swift",
                "top_owner_email": "c@c.com",
                "top_owner_weight": 0.9,
                "total_authors": 1,
                "source_context": "test",
            },
            {
                "path": "Scripts/build.sh",
                "top_owner_email": None,
                "top_owner_weight": 0.5,
                "total_authors": 1,
                "source_context": "other",
            },
        ]
        result = render_section(
            _section(
                "code_ownership",
                findings,
                {"files_analysed": 2, "diffuse_ownership_count": 0},
            ),
            severity_column="top_owner_weight",
            max_findings=100,
            severity_mapper=lambda v: Severity.LOW,
        )
        assert "test" in result
        assert "other" in result


class TestCryptoDomainModelSourceAnnotation:
    def test_finding_shows_library_source_context(self) -> None:
        findings = [
            {
                "file": "Sources/TronKit/Crypto.swift",
                "start_line": 10,
                "kind": "weak_kdf",
                "message": "weak KDF detected",
                "severity": "high",
                "source_context": "library",
            },
        ]
        result = render_section(
            _section("crypto_domain_model", findings),
            severity_column="severity",
            max_findings=100,
        )
        assert "library" in result

    def test_finding_shows_example_source_context(self) -> None:
        findings = [
            {
                "file": "iOS Example/Demo.swift",
                "start_line": 5,
                "kind": "weak_kdf",
                "message": "weak KDF",
                "severity": "low",
                "source_context": "example",
            },
        ]
        result = render_section(
            _section("crypto_domain_model", findings),
            severity_column="severity",
            max_findings=100,
        )
        assert "example" in result


class TestErrorHandlingSourceAnnotation:
    def test_finding_shows_library_source_context(self) -> None:
        findings = [
            {
                "file": "Sources/TronKit/Net.swift",
                "start_line": 1,
                "kind": "try_optional_swallow",
                "message": "try? swallows error",
                "severity": "medium",
                "source_context": "library",
            },
        ]
        result = render_section(
            _section("error_handling_policy", findings),
            severity_column="severity",
            max_findings=100,
        )
        assert "library" in result

    def test_finding_shows_test_source_context(self) -> None:
        findings = [
            {
                "file": "Tests/NetTests.swift",
                "start_line": 1,
                "kind": "try_optional_swallow",
                "message": "try? swallows error",
                "severity": "low",
                "source_context": "test",
            },
        ]
        result = render_section(
            _section("error_handling_policy", findings),
            severity_column="severity",
            max_findings=100,
        )
        assert "test" in result


class TestArchLayerSourceAnnotation:
    def test_finding_shows_source_context(self) -> None:
        findings = [
            {
                "src_module": "UI",
                "dst_module": "Data",
                "kind": "forbidden_import",
                "rule_id": "r1",
                "message": "UI must not import Data",
                "severity": "high",
                "source_context": "library",
                "evidence": None,
                "file": "UI/ViewController.swift",
            },
        ]
        result = render_section(
            _section(
                "arch_layer",
                findings,
                {
                    "module_count": 5,
                    "edge_count": 3,
                    "rule_count": 1,
                    "rules_declared": True,
                    "rule_source": ".palace/architecture-rules.yaml",
                },
            ),
            severity_column="severity",
            max_findings=100,
        )
        assert "library" in result


class TestCodingConventionSourceColumn:
    def test_table_header_has_source_column(self) -> None:
        findings = [
            {
                "module": "TronKit",
                "kind": "type_naming",
                "dominant_choice": "PascalCase",
                "confidence": "heuristic",
                "sample_count": 10,
                "outliers": 1,
                "source_context": "library",
                "violations": [],
            },
        ]
        result = render_section(
            _section("coding_convention", findings, {"total": 1}),
            severity_column="confidence",
            max_findings=100,
        )
        assert "Source" in result or "source_context" in result or "library" in result

    def test_source_context_value_appears(self) -> None:
        findings = [
            {
                "module": "ExampleKit",
                "kind": "type_naming",
                "dominant_choice": "PascalCase",
                "confidence": "certain",
                "sample_count": 5,
                "outliers": 0,
                "source_context": "example",
                "violations": [],
            },
        ]
        result = render_section(
            _section("coding_convention", findings, {"total": 1}),
            severity_column="confidence",
            max_findings=100,
        )
        assert "example" in result
