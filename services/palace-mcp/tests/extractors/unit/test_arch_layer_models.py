"""Unit tests for arch_layer models (GIM-243)."""

from __future__ import annotations

import pytest

from palace_mcp.extractors.arch_layer.models import (
    ArchRule,
    ArchViolation,
    Module,
    ModuleEdge,
    ParseResult,
    ParserWarning,
)


class TestModule:
    def test_valid_swift_target(self) -> None:
        m = Module(
            project_id="project/test",
            slug="WalletCore",
            name="WalletCore",
            kind="swift_target",
            manifest_path="Package.swift",
            source_root="Sources/WalletCore",
            run_id="run-1",
        )
        assert m.slug == "WalletCore"
        assert m.kind == "swift_target"

    def test_valid_gradle_module(self) -> None:
        m = Module(
            project_id="project/test",
            slug="core",
            name="core",
            kind="gradle_module",
            manifest_path="core/build.gradle.kts",
            source_root="core/src/main",
            run_id="run-1",
        )
        assert m.kind == "gradle_module"

    def test_frozen(self) -> None:
        m = Module(
            project_id="p",
            slug="Foo",
            name="Foo",
            kind="swift_target",
            manifest_path="Package.swift",
            source_root="",
            run_id="r",
        )
        with pytest.raises(Exception):
            m.slug = "Bar"  # type: ignore[misc]


class TestArchViolation:
    def test_valid_severity(self) -> None:
        v = ArchViolation(
            project_id="p",
            kind="forbidden_dependency",
            severity="high",
            src_module="Core",
            dst_module="UI",
            rule_id="rule-1",
            message="test",
            evidence="edge Core -> UI",
            file="",
            start_line=0,
            run_id="r",
        )
        assert v.severity == "high"

    def test_invalid_severity_normalised(self) -> None:
        v = ArchViolation(
            project_id="p",
            kind="forbidden_dependency",
            severity="CRITICAL_SUPER",
            src_module="A",
            dst_module="B",
            rule_id="r1",
            message="test",
            evidence="e",
            file="",
            start_line=0,
            run_id="r",
        )
        assert v.severity == "informational"

    def test_frozen(self) -> None:
        v = ArchViolation(
            project_id="p",
            kind="k",
            severity="low",
            src_module="A",
            dst_module="B",
            rule_id="r",
            message="m",
            evidence="e",
            file="",
            start_line=0,
            run_id="r",
        )
        with pytest.raises(Exception):
            v.severity = "high"  # type: ignore[misc]


class TestArchRule:
    def test_unknown_severity_normalised(self) -> None:
        r = ArchRule(
            project_id="p",
            rule_id="r1",
            kind="forbidden_dependency",
            severity="SUPER_BAD",
            rule_source=".palace/architecture-rules.yaml",
            run_id="r",
        )
        assert r.severity == "informational"

    def test_known_severities_preserved(self) -> None:
        for sev in ("critical", "high", "medium", "low", "informational"):
            r = ArchRule(
                project_id="p",
                rule_id="r",
                kind="no_circular_module_deps",
                severity=sev,
                rule_source="",
                run_id="r",
            )
            assert r.severity == sev


class TestParseResult:
    def test_empty_result(self) -> None:
        pr = ParseResult(modules=(), edges=(), warnings=())
        assert pr.modules == ()
        assert pr.edges == ()

    def test_with_data(self) -> None:
        m = Module(
            project_id="p",
            slug="A",
            name="A",
            kind="swift_target",
            manifest_path="Package.swift",
            source_root="",
            run_id="r",
        )
        e = ModuleEdge(
            src_slug="A",
            dst_slug="B",
            scope="target_dep",
            declared_in="Package.swift",
            evidence_kind="manifest",
            run_id="r",
        )
        w = ParserWarning(message="missing target")
        pr = ParseResult(modules=(m,), edges=(e,), warnings=(w,))
        assert len(pr.modules) == 1
        assert len(pr.edges) == 1
        assert pr.warnings[0].message == "missing target"
