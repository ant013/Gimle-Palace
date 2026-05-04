"""Unit tests for Gradle dependency parser — Task 4."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from palace_mcp.extractors.dependency_surface.parsers.gradle import parse_gradle

_LIBS_VERSIONS_TOML = textwrap.dedent(
    """
    [versions]
    appcompat = "1.7.1"
    retrofit = "3.0.0"

    [libraries]
    androidx-appcompat = { group = "androidx.appcompat", name = "appcompat", version.ref = "appcompat" }
    retrofit2 = { group = "com.squareup.retrofit2", name = "retrofit", version.ref = "retrofit" }
    """
)

_BUILD_GRADLE_KTS = textwrap.dedent(
    """
    dependencies {
        implementation(libs.androidx.appcompat)
        testImplementation(libs.retrofit2)
    }
    """
)


def test_gradle_parser_libs_versions_and_implementation(tmp_path: Path) -> None:
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(_LIBS_VERSIONS_TOML)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text(_BUILD_GRADLE_KTS)

    r = parse_gradle(tmp_path, project_id="project/x")
    by_purl = {d.purl: d for d in r.deps}
    assert "pkg:maven/androidx.appcompat/appcompat@1.7.1" in by_purl
    assert by_purl["pkg:maven/androidx.appcompat/appcompat@1.7.1"].scope == "compile"
    assert "pkg:maven/com.squareup.retrofit2/retrofit@3.0.0" in by_purl
    assert by_purl["pkg:maven/com.squareup.retrofit2/retrofit@3.0.0"].scope == "test"


def test_gradle_parser_alias_dot_variations(tmp_path: Path) -> None:
    # libs.androidx.appcompat  (dot notation for hyphen-separated alias)
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(
        textwrap.dedent(
            """
            [versions]
            appcompat = "1.7.1"

            [libraries]
            androidx-appcompat = { group = "androidx.appcompat", name = "appcompat", version.ref = "appcompat" }
            """
        )
    )
    (tmp_path / "app").mkdir()
    # Both hyphen and dot accessor forms should resolve
    (tmp_path / "app" / "build.gradle.kts").write_text(
        textwrap.dedent(
            """
            dependencies {
                implementation(libs.androidx.appcompat)
            }
            """
        )
    )
    r = parse_gradle(tmp_path, project_id="project/x")
    purls = {d.purl for d in r.deps}
    assert "pkg:maven/androidx.appcompat/appcompat@1.7.1" in purls


def test_gradle_parser_unknown_alias_warns(tmp_path: Path) -> None:
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(
        textwrap.dedent(
            """
            [versions]
            appcompat = "1.7.1"

            [libraries]
            androidx-appcompat = { group = "androidx.appcompat", name = "appcompat", version.ref = "appcompat" }
            """
        )
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text(
        textwrap.dedent(
            """
            dependencies {
                implementation(libs.does.not.exist)
                implementation(libs.androidx.appcompat)
            }
            """
        )
    )
    r = parse_gradle(tmp_path, project_id="project/x")
    # Should not crash; should warn about unresolved alias
    assert any("does.not.exist" in w or "unresolved" in w.lower() for w in r.parser_warnings)
    # Known dep still resolved
    purls = {d.purl for d in r.deps}
    assert "pkg:maven/androidx.appcompat/appcompat@1.7.1" in purls


def test_gradle_parser_multi_module(tmp_path: Path) -> None:
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(_LIBS_VERSIONS_TOML)
    (tmp_path / "app").mkdir()
    (tmp_path / "core").mkdir()
    # Both modules declare the same dep
    for module in ("app", "core"):
        (tmp_path / module / "build.gradle.kts").write_text(
            "dependencies { implementation(libs.androidx.appcompat) }"
        )
    r = parse_gradle(tmp_path, project_id="project/x")
    # 2 ParsedDep entries with different declared_in paths
    matching = [d for d in r.deps if "appcompat" in d.purl]
    assert len(matching) == 2
    declared_ins = {d.declared_in for d in matching}
    assert len(declared_ins) == 2


def test_gradle_parser_no_libs_versions_toml(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text(
        "dependencies { implementation(libs.some.lib) }"
    )
    r = parse_gradle(tmp_path, project_id="project/x")
    assert r.deps == ()
    assert any("libs.versions.toml" in w for w in r.parser_warnings)


def test_gradle_parser_scope_mapping(tmp_path: Path) -> None:
    (tmp_path / "gradle").mkdir()
    (tmp_path / "gradle" / "libs.versions.toml").write_text(
        textwrap.dedent(
            """
            [versions]
            v = "1.0.0"

            [libraries]
            lib-a = { group = "com.example", name = "lib-a", version.ref = "v" }
            lib-b = { group = "com.example", name = "lib-b", version.ref = "v" }
            lib-c = { group = "com.example", name = "lib-c", version.ref = "v" }
            lib-d = { group = "com.example", name = "lib-d", version.ref = "v" }
            """
        )
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle.kts").write_text(
        textwrap.dedent(
            """
            dependencies {
                implementation(libs.lib.a)
                testImplementation(libs.lib.b)
                compileOnly(libs.lib.c)
                runtimeOnly(libs.lib.d)
            }
            """
        )
    )
    r = parse_gradle(tmp_path, project_id="project/x")
    by_purl = {d.purl: d for d in r.deps}
    assert by_purl["pkg:maven/com.example/lib-a@1.0.0"].scope == "compile"
    assert by_purl["pkg:maven/com.example/lib-b@1.0.0"].scope == "test"
    assert by_purl["pkg:maven/com.example/lib-c@1.0.0"].scope == "compile"
    assert by_purl["pkg:maven/com.example/lib-d@1.0.0"].scope == "runtime"
