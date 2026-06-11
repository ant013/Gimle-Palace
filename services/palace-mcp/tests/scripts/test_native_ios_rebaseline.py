from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "native_ios_rebaseline.py"
)
_SPEC = importlib.util.spec_from_file_location("native_ios_rebaseline", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
native_ios_rebaseline = importlib.util.module_from_spec(_SPEC)
sys.modules["native_ios_rebaseline"] = native_ios_rebaseline
_SPEC.loader.exec_module(native_ios_rebaseline)


def test_manifest_contains_exact_native_ios_scope() -> None:
    profile = native_ios_rebaseline.load_profile(
        native_ios_rebaseline.DEFAULT_MANIFEST
    )

    assert tuple(project.slug for project in profile.projects) == (
        "bitcoin-core",
        "bitcoin-kit",
        "dash-kit",
        "evm-kit",
        "component-kit",
        "hd-wallet-kit",
        "uw-ios-app",
    )
    assert all("android" not in project.slug for project in profile.projects)


def test_manifest_rejects_extra_android_slug(tmp_path: Path) -> None:
    manifest = {
        "profile_name": "bad",
        "repo_root": str(tmp_path),
        "parent_mount": "hs",
        "projects": [
            {
                "slug": slug,
                "name": slug,
                "relative_path": slug,
                "language": "swift",
                "framework": "swiftpm",
                "language_profile": "swift_kit",
            }
            for slug in native_ios_rebaseline.EXPECTED_SLUGS
        ]
        + [
            {
                "slug": "uw-android",
                "name": "uw-android",
                "relative_path": "uw-android",
                "language": "kotlin",
                "framework": "android",
                "language_profile": "android_kit",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))

    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.load_profile(path)


def test_path_guard_rejects_forbidden_live_repo_root(tmp_path: Path) -> None:
    forbidden = tmp_path / "HorizontalSystems"
    forbidden.mkdir()
    candidate = forbidden / "BitcoinCore.Swift"
    candidate.mkdir()

    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.reject_forbidden_path(
            candidate, forbidden_roots=(forbidden,)
        )


def test_path_guard_rejects_uw_fresh_prefix() -> None:
    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.reject_forbidden_path(
            Path("/Users/ant013/Ios/uw-fresh-2099/unstoppable-wallet-ios")
        )


def test_env_scip_paths_require_dedicated_root(tmp_path: Path) -> None:
    root = tmp_path / "Gimle-Repos" / "HorizontalSystems"
    projects = tuple(
        native_ios_rebaseline.ProjectSpec(
            slug=slug,
            name=slug,
            relative_path=slug,
            language="swift",
            framework="swiftpm",
            language_profile="swift_kit",
        )
        for slug in native_ios_rebaseline.EXPECTED_SLUGS
    )
    profile = native_ios_rebaseline.NativeProfile("test", root, "hs", projects)
    mapping = {
        slug: str(root / slug / "scip" / "index.scip")
        for slug in native_ios_rebaseline.EXPECTED_SLUGS
    }
    mapping["uw-ios-app"] = "/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios/scip/index.scip"

    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.env_scip_paths(
            {"PALACE_SCIP_INDEX_PATHS": json.dumps(mapping)}, profile
        )


def test_periphery_state_requires_contract_keys(tmp_path: Path) -> None:
    periphery = tmp_path / "periphery"
    periphery.mkdir()
    (periphery / "periphery-3.7.4-swiftpm.json").write_text(
        json.dumps(
            [
                {
                    "accessibility": "internal",
                    "attributes": [],
                    "hints": ["unused"],
                    "ids": ["s:test"],
                    "kind": "class",
                    "location": "Sources/File.swift:1:1",
                    "modifiers": ["internal"],
                    "modules": ["Fixture"],
                    "name": "Fixture",
                }
            ]
        )
    )
    (periphery / "contract.json").write_text(
        json.dumps(
            {
                "tool_name": "Periphery",
                "tool_version": "3.7.4",
                "output_format": "json",
                "tool_output_schema_version": "periphery-json-3.7.4",
                "result_count": 1,
            }
        )
    )

    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.periphery_state(tmp_path)

    contract = json.loads((periphery / "contract.json").read_text())
    contract["required_result_keys"] = list(
        native_ios_rebaseline.PERIPHERY_REQUIRED_RESULT_KEYS
    )
    (periphery / "contract.json").write_text(json.dumps(contract))

    assert native_ios_rebaseline.periphery_state(tmp_path)["result_count"] == 1


def test_scip_state_rejects_repo_head_mismatch(tmp_path: Path) -> None:
    native_ios_rebaseline.run_git(tmp_path, ["init", "--initial-branch=main"])
    (tmp_path / "README.md").write_text("fixture\n")
    native_ios_rebaseline.run_git(tmp_path, ["add", "README.md"])
    native_ios_rebaseline.run_git(
        tmp_path,
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "fixture",
        ],
    )
    scip_dir = tmp_path / "scip"
    scip_dir.mkdir()
    (scip_dir / "index.scip").write_bytes(b"scip")
    (scip_dir / "index.scip.meta.json").write_text(
        json.dumps({"repo_head_sha": "not-current-head"})
    )

    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.scip_state(tmp_path)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, args))
        if tool == "palace.ingest.run_extractor":
            return {
                "ok": True,
                "run_id": f"{args['project']}-{args['name']}",
                "nodes_written": 1,
                "edges_written": 0,
            }
        return {"ok": True}


@pytest.mark.asyncio
async def test_run_sequential_extractors_preserves_project_then_extractor_order() -> None:
    projects = (
        native_ios_rebaseline.ProjectSpec(
            slug="bitcoin-core",
            name="BitcoinCore.Swift",
            relative_path="BitcoinCore.Swift",
            language="swift",
            framework="swiftpm",
            language_profile="swift_kit",
        ),
        native_ios_rebaseline.ProjectSpec(
            slug="bitcoin-kit",
            name="BitcoinKit.Swift",
            relative_path="BitcoinKit.Swift",
            language="swift",
            framework="swiftpm",
            language_profile="swift_kit",
        ),
    )
    client = FakeClient()
    profile = native_ios_rebaseline.NativeProfile("test", Path("/tmp/hs"), "hs", projects)

    await native_ios_rebaseline.run_sequential_extractors(
        client, profile, ("symbol_index_swift", "embedding_symbol")
    )

    assert client.calls == [
        (
            "palace.memory.register_project",
            {
                "slug": "bitcoin-core",
                "name": "BitcoinCore.Swift",
                "language": "swift",
                "framework": "swiftpm",
                "parent_mount": "hs",
                "relative_path": "BitcoinCore.Swift",
                "language_profile": "swift_kit",
                "expected_profile": True,
            },
        ),
        (
            "palace.ingest.run_extractor",
            {
                "name": "symbol_index_swift",
                "project": "bitcoin-core",
                "scip_path": "scip/index.scip",
            },
        ),
        (
            "palace.ingest.run_extractor",
            {"name": "embedding_symbol", "project": "bitcoin-core"},
        ),
        (
            "palace.memory.register_project",
            {
                "slug": "bitcoin-kit",
                "name": "BitcoinKit.Swift",
                "language": "swift",
                "framework": "swiftpm",
                "parent_mount": "hs",
                "relative_path": "BitcoinKit.Swift",
                "language_profile": "swift_kit",
                "expected_profile": True,
            },
        ),
        (
            "palace.ingest.run_extractor",
            {
                "name": "symbol_index_swift",
                "project": "bitcoin-kit",
                "scip_path": "scip/index.scip",
            },
        ),
        (
            "palace.ingest.run_extractor",
            {"name": "embedding_symbol", "project": "bitcoin-kit"},
        ),
    ]


@pytest.mark.asyncio
async def test_run_sequential_extractors_can_resume_mid_profile() -> None:
    projects = (
        native_ios_rebaseline.ProjectSpec(
            slug="bitcoin-core",
            name="BitcoinCore.Swift",
            relative_path="BitcoinCore.Swift",
            language="swift",
            framework="swiftpm",
            language_profile="swift_kit",
        ),
        native_ios_rebaseline.ProjectSpec(
            slug="component-kit",
            name="component-kit-ios",
            relative_path="component-kit-ios",
            language="swift",
            framework="swiftpm",
            language_profile="swift_kit",
        ),
        native_ios_rebaseline.ProjectSpec(
            slug="hd-wallet-kit",
            name="hd-wallet-kit-ios",
            relative_path="hd-wallet-kit-ios",
            language="swift",
            framework="swiftpm",
            language_profile="swift_kit",
        ),
    )
    client = FakeClient()
    profile = native_ios_rebaseline.NativeProfile("test", Path("/tmp/hs"), "hs", projects)

    await native_ios_rebaseline.run_sequential_extractors(
        client,
        profile,
        ("symbol_index_swift", "code_ownership", "embedding_symbol"),
        start_project="component-kit",
        start_after_extractor="code_ownership",
    )

    run_calls = [
        args
        for tool, args in client.calls
        if tool == "palace.ingest.run_extractor"
    ]
    assert run_calls == [
        {"name": "embedding_symbol", "project": "component-kit"},
        {
            "name": "symbol_index_swift",
            "project": "hd-wallet-kit",
            "scip_path": "scip/index.scip",
        },
        {"name": "code_ownership", "project": "hd-wallet-kit"},
        {"name": "embedding_symbol", "project": "hd-wallet-kit"},
    ]


def test_resume_args_require_known_project_and_extractor() -> None:
    profile = native_ios_rebaseline.load_profile(native_ios_rebaseline.DEFAULT_MANIFEST)

    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.validate_resume_args(
            profile,
            ("symbol_index_swift",),
            start_project="uw-android",
            start_after_extractor=None,
        )

    with pytest.raises(native_ios_rebaseline.RebaselineError):
        native_ios_rebaseline.validate_resume_args(
            profile,
            ("symbol_index_swift",),
            start_project="bitcoin-core",
            start_after_extractor="missing",
        )
