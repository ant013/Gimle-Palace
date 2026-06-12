"""Unit tests for the arch_layer Xcode project parser."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.arch_layer.parsers.xcodeproj import parse_xcodeproj


class TestXcodeprojParser:
    def test_finds_targets_source_roots_and_edges(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "Sample.xcodeproj"
        project_dir.mkdir()
        (project_dir / "project.pbxproj").write_text(
            """
// !$*UTF8*$!
{
  objects = {
    AAAAAAAAAAAAAAAAAAAAAAAA /* Project object */ = {
      isa = PBXProject;
      mainGroup = BBBBBBBBBBBBBBBBBBBBBBBB /* Root */;
    };
    BBBBBBBBBBBBBBBBBBBBBBBB /* Root */ = {
      isa = PBXGroup;
      children = (
        CCCCCCCCCCCCCCCCCCCCCCCC /* App */,
        DDDDDDDDDDDDDDDDDDDDDDDD /* Widget */,
      );
      sourceTree = "<group>";
    };
    CCCCCCCCCCCCCCCCCCCCCCCC /* App */ = {
      isa = PBXGroup;
      children = (
        EEEEEEEEEEEEEEEEEEEEEEEE /* AppDelegate.swift */,
        FFFFFFFFFFFFFFFFFFFFFFFF /* Scene.swift */,
      );
      path = App;
      sourceTree = "<group>";
    };
    DDDDDDDDDDDDDDDDDDDDDDDD /* Widget */ = {
      isa = PBXGroup;
      children = (
        111111111111111111111111 /* WidgetEntry.swift */,
      );
      path = Widget;
      sourceTree = "<group>";
    };
    EEEEEEEEEEEEEEEEEEEEEEEE /* AppDelegate.swift */ = {
      isa = PBXFileReference;
      lastKnownFileType = sourcecode.swift;
      path = AppDelegate.swift;
      sourceTree = "<group>";
    };
    FFFFFFFFFFFFFFFFFFFFFFFF /* Scene.swift */ = {
      isa = PBXFileReference;
      lastKnownFileType = sourcecode.swift;
      path = Scene.swift;
      sourceTree = "<group>";
    };
    111111111111111111111111 /* WidgetEntry.swift */ = {
      isa = PBXFileReference;
      lastKnownFileType = sourcecode.swift;
      path = WidgetEntry.swift;
      sourceTree = "<group>";
    };
    222222222222222222222222 /* AppDelegate.swift in Sources */ = {
      isa = PBXBuildFile;
      fileRef = EEEEEEEEEEEEEEEEEEEEEEEE /* AppDelegate.swift */;
    };
    333333333333333333333333 /* Scene.swift in Sources */ = {
      isa = PBXBuildFile;
      fileRef = FFFFFFFFFFFFFFFFFFFFFFFF /* Scene.swift */;
    };
    444444444444444444444444 /* WidgetEntry.swift in Sources */ = {
      isa = PBXBuildFile;
      fileRef = 111111111111111111111111 /* WidgetEntry.swift */;
    };
    555555555555555555555555 /* App Sources */ = {
      isa = PBXSourcesBuildPhase;
      files = (
        222222222222222222222222 /* AppDelegate.swift in Sources */,
        333333333333333333333333 /* Scene.swift in Sources */,
      );
    };
    666666666666666666666666 /* Widget Sources */ = {
      isa = PBXSourcesBuildPhase;
      files = (
        444444444444444444444444 /* WidgetEntry.swift in Sources */,
      );
    };
    777777777777777777777777 /* App Depends On Widget */ = {
      isa = PBXTargetDependency;
      target = 999999999999999999999999 /* Widget */;
    };
    888888888888888888888888 /* App */ = {
      isa = PBXNativeTarget;
      buildPhases = (
        555555555555555555555555 /* App Sources */,
      );
      dependencies = (
        777777777777777777777777 /* App Depends On Widget */,
      );
      name = App;
      productType = "com.apple.product-type.application";
    };
    999999999999999999999999 /* Widget */ = {
      isa = PBXNativeTarget;
      buildPhases = (
        666666666666666666666666 /* Widget Sources */,
      );
      name = Widget;
      productType = "com.apple.product-type.app-extension";
    };
  };
}
""",
            encoding="utf-8",
        )

        result = parse_xcodeproj(tmp_path, project_id="project/test", run_id="r1")

        source_roots = {module.slug: module.source_root for module in result.modules}
        assert source_roots == {"App": "App", "Widget": "Widget"}
        assert {
            (edge.src_slug, edge.dst_slug, edge.scope, edge.declared_in)
            for edge in result.edges
        } == {
            (
                "App",
                "Widget",
                "target_dep",
                "Sample.xcodeproj/project.pbxproj",
            )
        }
        assert result.warnings == ()

    def test_missing_project_returns_warning(self, tmp_path: Path) -> None:
        result = parse_xcodeproj(tmp_path, project_id="project/test", run_id="r1")
        assert result.modules == ()
        assert result.edges == ()
        assert any(
            "project.pbxproj not found" in warning.message
            for warning in result.warnings
        )

    def test_ignores_generated_xcode_projects(self, tmp_path: Path) -> None:
        root_project = tmp_path / "App.xcodeproj"
        generated_project = (
            tmp_path
            / ".palace-scip-derived-data-app"
            / "SourcePackages"
            / "checkouts"
            / "Dependency"
            / "Dependency.xcodeproj"
        )
        root_project.mkdir()
        generated_project.mkdir(parents=True)

        pbxproj = """
// !$*UTF8*$!
{
  objects = {
    BBBBBBBBBBBBBBBBBBBBBBBB /* Root */ = {
      isa = PBXGroup;
      children = (
        CCCCCCCCCCCCCCCCCCCCCCCC /* App */,
      );
      sourceTree = "<group>";
    };
    CCCCCCCCCCCCCCCCCCCCCCCC /* App */ = {
      isa = PBXGroup;
      children = (
        DDDDDDDDDDDDDDDDDDDDDDDD /* AppDelegate.swift */,
      );
      path = App;
      sourceTree = "<group>";
    };
    DDDDDDDDDDDDDDDDDDDDDDDD /* AppDelegate.swift */ = { isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = AppDelegate.swift; sourceTree = "<group>"; };
    EEEEEEEEEEEEEEEEEEEEEEEE /* AppDelegate.swift in Sources */ = { isa = PBXBuildFile; fileRef = DDDDDDDDDDDDDDDDDDDDDDDD /* AppDelegate.swift */; };
    FFFFFFFFFFFFFFFFFFFFFFFF /* App Sources */ = {
      isa = PBXSourcesBuildPhase;
      files = (
        EEEEEEEEEEEEEEEEEEEEEEEE /* AppDelegate.swift in Sources */,
      );
    };
    111111111111111111111111 /* App */ = {
      isa = PBXNativeTarget;
      buildPhases = (
        FFFFFFFFFFFFFFFFFFFFFFFF /* App Sources */,
      );
      name = App;
      productType = "com.apple.product-type.application";
    };
  };
}
"""
        (root_project / "project.pbxproj").write_text(pbxproj, encoding="utf-8")
        (generated_project / "project.pbxproj").write_text(
            pbxproj.replace("name = App;", "name = Dependency;"),
            encoding="utf-8",
        )

        result = parse_xcodeproj(tmp_path, project_id="project/test", run_id="r1")

        assert [module.slug for module in result.modules] == ["App"]
        assert result.modules[0].manifest_path == "App.xcodeproj/project.pbxproj"

    def test_uses_file_system_synchronized_group_roots(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "Unstoppable" / "Unstoppable.xcodeproj"
        project_dir.mkdir(parents=True)
        swift_dir = tmp_path / "Unstoppable" / "Widget"
        swift_dir.mkdir()
        (swift_dir / "WidgetView.swift").write_text(
            "import SwiftUI\n", encoding="utf-8"
        )
        (project_dir / "project.pbxproj").write_text(
            """
// !$*UTF8*$!
{
  objects = {
    BBBBBBBBBBBBBBBBBBBBBBBB /* Widget */ = {
      isa = PBXFileSystemSynchronizedRootGroup;
      path = Widget;
      sourceTree = "<group>";
    };
    CCCCCCCCCCCCCCCCCCCCCCCC /* Widget Sources */ = {
      isa = PBXSourcesBuildPhase;
      files = (
      );
    };
    DDDDDDDDDDDDDDDDDDDDDDDD /* WidgetExtension */ = {
      isa = PBXNativeTarget;
      buildPhases = (
        CCCCCCCCCCCCCCCCCCCCCCCC /* Widget Sources */,
      );
      fileSystemSynchronizedGroups = (
        BBBBBBBBBBBBBBBBBBBBBBBB /* Widget */,
      );
      name = WidgetExtension;
      productType = "com.apple.product-type.app-extension";
    };
  };
}
""",
            encoding="utf-8",
        )

        result = parse_xcodeproj(tmp_path, project_id="project/test", run_id="r1")

        assert len(result.modules) == 1
        assert result.modules[0].slug == "WidgetExtension"
        assert result.modules[0].source_root == "Unstoppable/Widget"

    def test_prefers_target_named_root_when_sources_mix_shared_files(
        self, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "Sample.xcodeproj"
        project_dir.mkdir()
        (project_dir / "project.pbxproj").write_text(
            """
// !$*UTF8*$!
{
  objects = {
    BBBBBBBBBBBBBBBBBBBBBBBB /* Root */ = {
      isa = PBXGroup;
      children = (
        CCCCCCCCCCCCCCCCCCCCCCCC /* Widget */,
        DDDDDDDDDDDDDDDDDDDDDDDD /* Shared */,
      );
      sourceTree = "<group>";
    };
    CCCCCCCCCCCCCCCCCCCCCCCC /* Widget */ = {
      isa = PBXGroup;
      children = (
        EEEEEEEEEEEEEEEEEEEEEEEE /* WidgetEntry.swift */,
      );
      path = Widget;
      sourceTree = "<group>";
    };
    DDDDDDDDDDDDDDDDDDDDDDDD /* Shared */ = {
      isa = PBXGroup;
      children = (
        FFFFFFFFFFFFFFFFFFFFFFFF /* SharedSupport.swift */,
      );
      path = Shared;
      sourceTree = "<group>";
    };
    EEEEEEEEEEEEEEEEEEEEEEEE /* WidgetEntry.swift */ = { isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = WidgetEntry.swift; sourceTree = "<group>"; };
    FFFFFFFFFFFFFFFFFFFFFFFF /* SharedSupport.swift */ = { isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = SharedSupport.swift; sourceTree = "<group>"; };
    111111111111111111111111 /* WidgetEntry.swift in Sources */ = { isa = PBXBuildFile; fileRef = EEEEEEEEEEEEEEEEEEEEEEEE /* WidgetEntry.swift */; };
    222222222222222222222222 /* SharedSupport.swift in Sources */ = { isa = PBXBuildFile; fileRef = FFFFFFFFFFFFFFFFFFFFFFFF /* SharedSupport.swift */; };
    333333333333333333333333 /* Widget Sources */ = {
      isa = PBXSourcesBuildPhase;
      files = (
        111111111111111111111111 /* WidgetEntry.swift in Sources */,
        222222222222222222222222 /* SharedSupport.swift in Sources */,
      );
    };
    444444444444444444444444 /* WidgetExtension Dev */ = {
      isa = PBXNativeTarget;
      buildPhases = (
        333333333333333333333333 /* Widget Sources */,
      );
      name = "WidgetExtension Dev";
      productType = "com.apple.product-type.app-extension";
    };
  };
}
""",
            encoding="utf-8",
        )

        result = parse_xcodeproj(tmp_path, project_id="project/test", run_id="r1")

        assert len(result.modules) == 1
        assert result.modules[0].source_root == "Widget"
