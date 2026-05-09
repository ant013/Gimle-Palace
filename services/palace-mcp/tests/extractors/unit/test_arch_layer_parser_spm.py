"""Unit tests for arch_layer SwiftPM parser (GIM-243)."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.arch_layer.parsers.spm import parse_spm

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "arch-layer-mini-project"


class TestSpmParserFixture:
    def test_finds_two_targets(self) -> None:
        result = parse_spm(_FIXTURE, project_id="project/test", run_id="r1")
        names = {m.slug for m in result.modules}
        assert "WalletCore" in names
        assert "WalletUI" in names

    def test_module_kind_is_swift_target(self) -> None:
        result = parse_spm(_FIXTURE, project_id="project/test", run_id="r1")
        for m in result.modules:
            assert m.kind == "swift_target"

    def test_module_manifest_path(self) -> None:
        result = parse_spm(_FIXTURE, project_id="project/test", run_id="r1")
        for m in result.modules:
            assert m.manifest_path == "Package.swift"

    def test_finds_internal_edge(self) -> None:
        result = parse_spm(_FIXTURE, project_id="project/test", run_id="r1")
        edges = {(e.src_slug, e.dst_slug) for e in result.edges}
        assert ("WalletUI", "WalletCore") in edges

    def test_edge_scope(self) -> None:
        result = parse_spm(_FIXTURE, project_id="project/test", run_id="r1")
        for e in result.edges:
            assert e.scope == "target_dep"
            assert e.evidence_kind == "manifest"


class TestSpmParserMissing:
    def test_no_package_swift_returns_warning(self, tmp_path: Path) -> None:
        result = parse_spm(tmp_path, project_id="project/test", run_id="r1")
        assert result.modules == ()
        assert result.edges == ()
        assert any("not found" in w.message for w in result.warnings)


class TestSpmParserExternalDep:
    def test_external_dep_skipped_with_warning(self, tmp_path: Path) -> None:
        (tmp_path / "Package.swift").write_text(
            """
// swift-tools-version:5.7
import PackageDescription
let package = Package(
    name: "Test",
    dependencies: [
        .package(url: "https://github.com/external/lib", from: "1.0.0"),
    ],
    targets: [
        .target(name: "Core", dependencies: ["ExternalLib"]),
    ]
)
""",
            encoding="utf-8",
        )
        result = parse_spm(tmp_path, project_id="p", run_id="r")
        assert any("ExternalLib" in w.message for w in result.warnings)
        assert result.edges == ()


class TestSpmParserUnsupported:
    def test_no_guessed_edges_for_missing_target(self, tmp_path: Path) -> None:
        (tmp_path / "Package.swift").write_text(
            """
import PackageDescription
let package = Package(
    name: "T",
    targets: [
        .target(name: "A", dependencies: ["B"]),
    ]
)
""",
            encoding="utf-8",
        )
        result = parse_spm(tmp_path, project_id="p", run_id="r")
        # B is not an internal target => warning, no edge
        assert result.edges == ()
        assert any("B" in w.message for w in result.warnings)
