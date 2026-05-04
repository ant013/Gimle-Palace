"""Unit tests for SPM (Swift Package Manager) parser — Task 3."""

from __future__ import annotations

import textwrap
from pathlib import Path

from palace_mcp.extractors.dependency_surface.parsers.spm import parse_spm

_PACKAGE_SWIFT_2DEPS = textwrap.dedent(
    """
    // swift-tools-version: 5.9
    import PackageDescription
    let package = Package(
        name: "X",
        dependencies: [
            .package(url: "https://github.com/horizontalsystems/EvmKit.Swift.git", from: "1.5.0"),
            .package(url: "https://github.com/apple/swift-collections", exact: "1.1.4"),
        ],
        targets: [.target(name: "X")]
    )
    """
)

_RESOLVED_V3_JSON = textwrap.dedent(
    """
    {
      "originHash" : "abc123",
      "pins" : [
        {
          "identity" : "evmkit-swift",
          "kind" : "remoteSourceControl",
          "location" : "https://github.com/horizontalsystems/EvmKit.Swift.git",
          "state" : {
            "revision" : "abc123def456",
            "version" : "1.5.3"
          }
        },
        {
          "identity" : "swift-collections",
          "kind" : "remoteSourceControl",
          "location" : "https://github.com/apple/swift-collections",
          "state" : {
            "revision" : "def789abc012",
            "version" : "1.1.4"
          }
        }
      ],
      "version" : 3
    }
    """
)

_RESOLVED_V2_JSON = textwrap.dedent(
    """
    {
      "object": {
        "pins": [
          {
            "package": "EvmKit.Swift",
            "repositoryURL": "https://github.com/horizontalsystems/EvmKit.Swift.git",
            "state": {
              "branch": null,
              "revision": "abc123def456",
              "version": "1.5.3"
            }
          },
          {
            "package": "swift-collections",
            "repositoryURL": "https://github.com/apple/swift-collections",
            "state": {
              "branch": null,
              "revision": "def789abc012",
              "version": "1.1.4"
            }
          }
        ]
      },
      "version": 1
    }
    """
)


def test_spm_parser_package_swift_only(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(_PACKAGE_SWIFT_2DEPS)
    # No Package.resolved → resolved_version="unresolved" for both
    r = parse_spm(tmp_path, project_id="project/x")
    purl_bases = {d.purl.split("@")[0] for d in r.deps}
    assert purl_bases == {
        "pkg:github/horizontalsystems/EvmKit.Swift",
        "pkg:github/apple/swift-collections",
    }
    assert all(d.resolved_version == "unresolved" for d in r.deps)
    assert any("Package.resolved missing" in w for w in r.parser_warnings)


def test_spm_parser_with_resolved_v3(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(_PACKAGE_SWIFT_2DEPS)
    (tmp_path / "Package.resolved").write_text(_RESOLVED_V3_JSON)
    r = parse_spm(tmp_path, project_id="project/x")
    assert r.parser_warnings == ()
    versions = {d.resolved_version for d in r.deps}
    assert versions == {"1.5.3", "1.1.4"}


def test_spm_parser_with_resolved_v2_object_pins(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(_PACKAGE_SWIFT_2DEPS)
    (tmp_path / "Package.resolved").write_text(_RESOLVED_V2_JSON)
    r = parse_spm(tmp_path, project_id="project/x")
    versions = {d.resolved_version for d in r.deps}
    assert versions == {"1.5.3", "1.1.4"}


def test_spm_parser_branch_pin_unresolved(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(
        textwrap.dedent(
            """
            // swift-tools-version: 5.9
            import PackageDescription
            let package = Package(
                name: "X",
                dependencies: [
                    .package(url: "https://github.com/apple/swift-log.git", branch: "main"),
                ],
                targets: [.target(name: "X")]
            )
            """
        )
    )
    (tmp_path / "Package.resolved").write_text(
        textwrap.dedent(
            """
            {
              "pins": [
                {
                  "identity": "swift-log",
                  "location": "https://github.com/apple/swift-log.git",
                  "state": { "branch": "main", "revision": "abc123def456" }
                }
              ],
              "version": 3
            }
            """
        )
    )
    r = parse_spm(tmp_path, project_id="project/x")
    assert len(r.deps) == 1
    # Branch pin: no version in state → resolved_version="unresolved"
    assert r.deps[0].resolved_version == "unresolved"


def test_spm_parser_no_package_swift(tmp_path: Path) -> None:
    r = parse_spm(tmp_path, project_id="project/x")
    assert r.deps == ()
    assert any("Package.swift not found" in w for w in r.parser_warnings)


def test_spm_parser_declared_in_is_package_swift(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(_PACKAGE_SWIFT_2DEPS)
    r = parse_spm(tmp_path, project_id="project/x")
    assert all(d.declared_in == "Package.swift" for d in r.deps)


def test_spm_parser_project_id_set(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(_PACKAGE_SWIFT_2DEPS)
    r = parse_spm(tmp_path, project_id="project/myproject")
    assert all(d.project_id == "project/myproject" for d in r.deps)
