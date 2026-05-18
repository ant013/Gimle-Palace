"""Unit tests for arch_layer Gradle parser (GIM-243)."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.arch_layer.parsers.gradle import parse_gradle

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "arch-layer-mini-project"


class TestGradleParserFixture:
    def test_finds_two_modules(self) -> None:
        result = parse_gradle(_FIXTURE, project_id="project/test", run_id="r1")
        slugs = {m.slug for m in result.modules}
        assert "core" in slugs
        assert "ui" in slugs

    def test_module_kind(self) -> None:
        result = parse_gradle(_FIXTURE, project_id="project/test", run_id="r1")
        for m in result.modules:
            assert m.kind == "gradle_module"

    def test_edge_ui_depends_on_core(self) -> None:
        result = parse_gradle(_FIXTURE, project_id="project/test", run_id="r1")
        edges = {(e.src_slug, e.dst_slug): e.scope for e in result.edges}
        assert ("ui", "core") in edges
        assert edges[("ui", "core")] == "implementation"

    def test_no_self_edge(self) -> None:
        result = parse_gradle(_FIXTURE, project_id="project/test", run_id="r1")
        for e in result.edges:
            assert e.src_slug != e.dst_slug


class TestGradleParserMissing:
    def test_no_settings_returns_warning(self, tmp_path: Path) -> None:
        result = parse_gradle(tmp_path, project_id="p", run_id="r")
        assert result.modules == ()
        assert any("settings.gradle" in w.message for w in result.warnings)


class TestGradleParserExternalDep:
    def test_external_maven_dep_skipped(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.gradle.kts"
        settings.write_text('include(":core")\n', encoding="utf-8")
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        (core_dir / "build.gradle.kts").write_text(
            'implementation("com.squareup.okhttp3:okhttp:4.11.0")\n',
            encoding="utf-8",
        )
        result = parse_gradle(tmp_path, project_id="p", run_id="r")
        assert result.edges == ()  # external dep: no edge

    def test_unknown_module_dep_skipped_with_warning(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.gradle.kts"
        settings.write_text('include(":core")\n', encoding="utf-8")
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        (core_dir / "build.gradle.kts").write_text(
            'implementation(project(":nonexistent"))\n',
            encoding="utf-8",
        )
        result = parse_gradle(tmp_path, project_id="p", run_id="r")
        assert result.edges == ()
        assert any("nonexistent" in w.message for w in result.warnings)


class TestGradleParserScopes:
    def test_multiple_scopes_parsed(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.gradle.kts"
        settings.write_text('include(":a")\ninclude(":b")\n', encoding="utf-8")
        a_dir = tmp_path / "a"
        a_dir.mkdir()
        b_dir = tmp_path / "b"
        b_dir.mkdir()
        (b_dir / "build.gradle.kts").write_text(
            'implementation(project(":a"))\ntestImplementation(project(":a"))\n',
            encoding="utf-8",
        )
        (a_dir / "build.gradle.kts").write_text("", encoding="utf-8")
        result = parse_gradle(tmp_path, project_id="p", run_id="r")
        scopes = {
            e.scope for e in result.edges if e.src_slug == "b" and e.dst_slug == "a"
        }
        assert "implementation" in scopes
        assert "testImplementation" in scopes
