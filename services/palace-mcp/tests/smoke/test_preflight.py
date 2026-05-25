"""Tests for runtime preflight checks (GIM-839 A6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from palace_mcp.smoke.preflight import (
    PreflightCheck,
    _find_absolute_refs_in_workspace,
    check_docker_available,
    check_embedding_limits,
    check_host_architecture,
    check_ios_sdk_runtime,
    check_local_only_model_mode,
    check_mcp_tools_list,
    check_model_cache_path,
    check_neo4j_reachable,
    check_repo_path,
    check_scip_path_writable,
    check_swiftpm_cache,
    check_workspace_absolute_references,
    check_xcode_license,
    check_xcode_select,
    check_xcodebuild_version,
    run_preflight,
)
from palace_mcp.smoke.recipe import Recipe
from palace_mcp.smoke.runtime_binding import RuntimeBinding


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MCP_URL = "http://localhost:8000/mcp"


def _make_recipe(**overrides: Any) -> Recipe:
    defaults: dict[str, Any] = {
        "slug": "test-project",
        "name": "Test Project",
        "language": "swift",
        "build_system": "xcode_workspace",
        "source_roots": ["Sources"],
        "dependency_roots": [".build"],
        "scip_path": "scip/index.scip",
        "build": {
            "workspace": "Test.xcworkspace",
            "scheme": "TestScheme",
        },
        "extractors": ["symbol_index_swift", "dead_code"],
    }
    defaults.update(overrides)
    return Recipe.model_validate(defaults)


def _make_binding(tmp_path: Path, **overrides: Any) -> RuntimeBinding:
    repo = tmp_path / "repos" / "test-project"
    repo.mkdir(parents=True)
    defaults: dict[str, Any] = {
        "repo_path": repo,
        "parent_mount": tmp_path / "repos",
        "mcp_url": _MCP_URL,
    }
    defaults.update(overrides)
    return RuntimeBinding.model_validate(defaults)


def _proc_mock(
    returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""
) -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# check_repo_path
# ---------------------------------------------------------------------------


class TestCheckRepoPath:
    def test_passes_when_exists(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        result = check_repo_path(binding)
        assert result.passed is True
        assert result.name == "repo_path"

    def test_fails_when_missing(self, tmp_path: Path) -> None:
        (tmp_path / "repos").mkdir(parents=True, exist_ok=True)
        binding = RuntimeBinding(
            repo_path=tmp_path / "repos" / "nonexistent",
            parent_mount=tmp_path / "repos",
            mcp_url=_MCP_URL,
        )
        result = check_repo_path(binding)
        assert result.passed is False
        assert "does not exist" in (result.message or "")


# ---------------------------------------------------------------------------
# check_scip_path_writable
# ---------------------------------------------------------------------------


class TestCheckScipPathWritable:
    def test_passes_when_parent_exists(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        scip_parent = binding.repo_path / "scip"
        scip_parent.mkdir(parents=True)
        result = check_scip_path_writable(recipe, binding)
        assert result.passed is True

    def test_passes_when_parent_can_be_created(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        result = check_scip_path_writable(recipe, binding)
        assert result.passed is True

    def test_fails_when_parent_is_file(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        scip_parent = binding.repo_path / "scip"
        scip_parent.write_text("not a dir")
        result = check_scip_path_writable(recipe, binding)
        assert result.passed is False
        assert "not a directory" in (result.message or "")


# ---------------------------------------------------------------------------
# check_host_architecture
# ---------------------------------------------------------------------------


class TestCheckHostArchitecture:
    @patch("platform.machine", return_value="arm64")
    def test_arm64_passes(self, _mock: Any) -> None:
        recipe = _make_recipe()
        result = check_host_architecture(recipe)
        assert result.passed is True
        assert result.details["resolved_arch"] == "arm64"
        assert result.details["effective_simulator_arch"] == "arm64"

    @patch("platform.machine", return_value="x86_64")
    def test_x86_64_passes(self, _mock: Any) -> None:
        recipe = _make_recipe()
        result = check_host_architecture(recipe)
        assert result.passed is True
        assert result.details["resolved_arch"] == "x86_64"

    @patch("platform.machine", return_value="riscv64")
    def test_unsupported_fails(self, _mock: Any) -> None:
        recipe = _make_recipe()
        result = check_host_architecture(recipe)
        assert result.passed is False
        assert "unsupported" in (result.message or "")

    @patch("platform.machine", return_value="arm64")
    def test_explicit_arch_overrides_auto(self, _mock: Any) -> None:
        recipe = _make_recipe(
            build={
                "workspace": "Test.xcworkspace",
                "scheme": "TestScheme",
                "simulator_arch": "x86_64",
            }
        )
        result = check_host_architecture(recipe)
        assert result.passed is True
        assert result.details["effective_simulator_arch"] == "x86_64"


# ---------------------------------------------------------------------------
# check_docker_available
# ---------------------------------------------------------------------------


class TestCheckDockerAvailable:
    @patch("asyncio.create_subprocess_exec")
    async def test_passes_when_docker_responds(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(stdout=b"24.0.7")
        result = await check_docker_available()
        assert result.passed is True
        assert result.details["server_version"] == "24.0.7"

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_when_docker_errors(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(returncode=1, stderr=b"daemon not running")
        result = await check_docker_available()
        assert result.passed is False
        assert "not available" in (result.message or "")

    @patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError)
    async def test_fails_when_not_installed(self, _mock: AsyncMock) -> None:
        result = await check_docker_available()
        assert result.passed is False
        assert "not found" in (result.message or "")

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_on_timeout(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock()
        mock_exec.return_value.communicate = AsyncMock(side_effect=TimeoutError)
        with patch("asyncio.wait_for", side_effect=TimeoutError):
            pass
        import asyncio as _asyncio

        with patch.object(_asyncio, "wait_for", side_effect=_asyncio.TimeoutError):
            result = await check_docker_available()
        assert result.passed is False
        assert "timed out" in (result.message or "")


# ---------------------------------------------------------------------------
# check_neo4j_reachable
# ---------------------------------------------------------------------------


class TestCheckNeo4jReachable:
    @patch("asyncio.create_subprocess_exec")
    async def test_passes_on_200(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(stdout=b"200")
        result = await check_neo4j_reachable(
            RuntimeBinding(
                repo_path=Path("/tmp/x/y"),
                parent_mount=Path("/tmp/x"),
                mcp_url="http://localhost:8000/mcp",
            )
        )
        assert result.passed is True

    @patch("asyncio.create_subprocess_exec")
    async def test_passes_on_401(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(returncode=0, stdout=b"401")
        result = await check_neo4j_reachable(
            RuntimeBinding(
                repo_path=Path("/tmp/x/y"),
                parent_mount=Path("/tmp/x"),
                mcp_url="http://localhost:8000/mcp",
            )
        )
        assert result.passed is True

    @patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError)
    async def test_fails_when_curl_missing(self, _mock: AsyncMock) -> None:
        result = await check_neo4j_reachable(
            RuntimeBinding(
                repo_path=Path("/tmp/x/y"),
                parent_mount=Path("/tmp/x"),
                mcp_url="http://localhost:8000/mcp",
            )
        )
        assert result.passed is False
        assert "Neo4j" in (result.message or "")


# ---------------------------------------------------------------------------
# check_mcp_tools_list
# ---------------------------------------------------------------------------


class TestCheckMcpToolsList:
    @patch("asyncio.create_subprocess_exec")
    async def test_passes_with_tools(self, mock_exec: AsyncMock) -> None:
        response = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"tools": [{"name": "palace.memory.register_project"}]},
            }
        ).encode()
        mock_exec.return_value = _proc_mock(stdout=response)
        binding = RuntimeBinding(
            repo_path=Path("/tmp/x/y"),
            parent_mount=Path("/tmp/x"),
            mcp_url="http://localhost:8000/mcp",
        )
        result = await check_mcp_tools_list(binding)
        assert result.passed is True
        assert result.details["tool_count"] == 1

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_on_connection_refused(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(returncode=7)
        binding = RuntimeBinding(
            repo_path=Path("/tmp/x/y"),
            parent_mount=Path("/tmp/x"),
            mcp_url="http://localhost:8000/mcp",
        )
        result = await check_mcp_tools_list(binding)
        assert result.passed is False
        assert "unreachable" in (result.message or "").lower()


# ---------------------------------------------------------------------------
# check_model_cache_path
# ---------------------------------------------------------------------------


class TestCheckModelCachePath:
    def test_passes_when_not_configured(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        result = check_model_cache_path(binding)
        assert result.passed is True
        assert result.details["configured"] is False

    def test_passes_when_exists(self, tmp_path: Path) -> None:
        cache = tmp_path / "qodo-cache"
        cache.mkdir()
        binding = _make_binding(tmp_path, qodo_cache_path=cache)
        result = check_model_cache_path(binding)
        assert result.passed is True

    def test_fails_when_missing(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path, qodo_cache_path=tmp_path / "nonexistent")
        result = check_model_cache_path(binding)
        assert result.passed is False
        assert "not found" in (result.message or "")
        assert "download models" in (result.message or "")


# ---------------------------------------------------------------------------
# check_local_only_model_mode
# ---------------------------------------------------------------------------


class TestCheckLocalOnlyModelMode:
    @patch.dict("os.environ", {}, clear=True)
    def test_passes_when_not_set(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        result = check_local_only_model_mode(binding)
        assert result.passed is True

    @patch.dict("os.environ", {"PALACE_EMBEDDING_LOCAL_ONLY": "true"})
    def test_passes_when_set(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        result = check_local_only_model_mode(binding)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_embedding_limits
# ---------------------------------------------------------------------------


class TestCheckEmbeddingLimits:
    @patch.dict("os.environ", {}, clear=True)
    def test_passes_without_limit(self) -> None:
        result = check_embedding_limits()
        assert result.passed is True
        assert result.details["limit"] is None

    @patch.dict("os.environ", {"PALACE_EMBEDDING_LIMIT": "128"})
    def test_passes_with_valid_limit(self) -> None:
        result = check_embedding_limits()
        assert result.passed is True
        assert result.details["limit"] == 128

    @patch.dict("os.environ", {"PALACE_EMBEDDING_LIMIT": "not_a_number"})
    def test_fails_with_invalid_limit(self) -> None:
        result = check_embedding_limits()
        assert result.passed is False
        assert "not a valid integer" in (result.message or "")


# ---------------------------------------------------------------------------
# check_xcode_select
# ---------------------------------------------------------------------------


class TestCheckXcodeSelect:
    @patch("asyncio.create_subprocess_exec")
    async def test_passes(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(
            stdout=b"/Applications/Xcode.app/Contents/Developer"
        )
        result = await check_xcode_select()
        assert result.passed is True
        assert "Developer" in result.details["developer_dir"]

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_when_not_configured(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(
            returncode=2, stderr=b"no developer tools found"
        )
        result = await check_xcode_select()
        assert result.passed is False
        assert "not configured" in (result.message or "")

    @patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError)
    async def test_fails_when_missing(self, _mock: AsyncMock) -> None:
        result = await check_xcode_select()
        assert result.passed is False
        assert "not found" in (result.message or "")


# ---------------------------------------------------------------------------
# check_xcodebuild_version
# ---------------------------------------------------------------------------


class TestCheckXcodebuildVersion:
    @patch("asyncio.create_subprocess_exec")
    async def test_passes(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(stdout=b"Xcode 16.0\nBuild version 16A242d")
        result = await check_xcodebuild_version()
        assert result.passed is True
        assert "16.0" in result.details["output"]

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_on_error(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(returncode=1, stderr=b"error")
        result = await check_xcodebuild_version()
        assert result.passed is False

    @patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError)
    async def test_fails_when_not_installed(self, _mock: AsyncMock) -> None:
        result = await check_xcodebuild_version()
        assert result.passed is False
        assert "not found" in (result.message or "")


# ---------------------------------------------------------------------------
# check_xcode_license
# ---------------------------------------------------------------------------


class TestCheckXcodeLicense:
    @patch("asyncio.create_subprocess_exec")
    async def test_passes_when_accepted(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(returncode=0)
        result = await check_xcode_license()
        assert result.passed is True

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_when_not_accepted(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(
            returncode=69, stderr=b"You have not agreed to the Xcode license"
        )
        result = await check_xcode_license()
        assert result.passed is False
        assert "license" in (result.message or "").lower()
        assert "sudo xcodebuild -license accept" in (result.message or "")

    @patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError)
    async def test_fails_when_xcodebuild_missing(self, _mock: AsyncMock) -> None:
        result = await check_xcode_license()
        assert result.passed is False


# ---------------------------------------------------------------------------
# check_ios_sdk_runtime
# ---------------------------------------------------------------------------


class TestCheckIosSdkRuntime:
    @patch("asyncio.create_subprocess_exec")
    async def test_passes_with_available_runtimes(self, mock_exec: AsyncMock) -> None:
        response = json.dumps(
            {
                "runtimes": [
                    {
                        "platform": "iOS",
                        "version": "17.5",
                        "name": "iOS 17.5",
                        "isAvailable": True,
                    },
                    {
                        "platform": "watchOS",
                        "version": "10.0",
                        "name": "watchOS 10.0",
                        "isAvailable": True,
                    },
                ]
            }
        ).encode()
        mock_exec.return_value = _proc_mock(stdout=response)
        result = await check_ios_sdk_runtime()
        assert result.passed is True
        assert result.details["ios_runtime_count"] == 1
        assert result.details["latest_version"] == "17.5"

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_when_no_ios_runtimes(self, mock_exec: AsyncMock) -> None:
        response = json.dumps(
            {
                "runtimes": [
                    {"platform": "watchOS", "version": "10.0", "isAvailable": True}
                ]
            }
        ).encode()
        mock_exec.return_value = _proc_mock(stdout=response)
        result = await check_ios_sdk_runtime()
        assert result.passed is False
        assert "No available iOS" in (result.message or "")

    @patch("asyncio.create_subprocess_exec")
    async def test_fails_when_simctl_errors(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _proc_mock(returncode=1)
        result = await check_ios_sdk_runtime()
        assert result.passed is False

    @patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError)
    async def test_fails_when_xcrun_missing(self, _mock: AsyncMock) -> None:
        result = await check_ios_sdk_runtime()
        assert result.passed is False
        assert "xcrun not found" in (result.message or "")


# ---------------------------------------------------------------------------
# check_swiftpm_cache
# ---------------------------------------------------------------------------


class TestCheckSwiftpmCache:
    def test_passes_with_locked_and_resolved_file(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        (binding.repo_path / "Test.xcworkspace" / "xcshareddata" / "swiftpm").mkdir(
            parents=True
        )
        (
            binding.repo_path
            / "Test.xcworkspace"
            / "xcshareddata"
            / "swiftpm"
            / "Package.resolved"
        ).write_text("{}")
        result = check_swiftpm_cache(recipe, binding)
        assert result.passed is True

    def test_fails_when_locked_no_resolved(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        result = check_swiftpm_cache(recipe, binding)
        assert result.passed is False
        assert "Package.resolved not found" in (result.message or "")
        assert "locked" in (result.message or "")

    def test_passes_with_automatic_resolution(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe(
            build={
                "workspace": "Test.xcworkspace",
                "scheme": "TestScheme",
                "package_resolution": "automatic",
            }
        )
        result = check_swiftpm_cache(recipe, binding)
        assert result.passed is True

    def test_fails_when_cache_path_missing(self, tmp_path: Path) -> None:
        binding = _make_binding(
            tmp_path, swiftpm_cache_path=tmp_path / "nonexistent-cache"
        )
        recipe = _make_recipe(
            build={
                "workspace": "Test.xcworkspace",
                "scheme": "TestScheme",
                "package_resolution": "automatic",
            }
        )
        result = check_swiftpm_cache(recipe, binding)
        assert result.passed is False
        assert "cache path does not exist" in (result.message or "")

    def test_passes_with_root_package_resolved(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        (binding.repo_path / "Package.resolved").write_text("{}")
        result = check_swiftpm_cache(recipe, binding)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_workspace_absolute_references
# ---------------------------------------------------------------------------


class TestCheckWorkspaceAbsoluteReferences:
    def test_passes_without_workspace(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe(
            build_system="swift_package",
            build={
                "scheme": "TestScheme",
            },
        )
        result = check_workspace_absolute_references(recipe, binding)
        assert result.passed is True

    def test_passes_with_no_absolute_refs(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        ws_dir = binding.repo_path / "Test.xcworkspace"
        ws_dir.mkdir(parents=True)
        (ws_dir / "contents.xcworkspacedata").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Workspace version="1.0">\n'
            '  <FileRef location="group:Sources/App.swift"/>\n'
            '  <FileRef location="container:Packages/Kit"/>\n'
            "</Workspace>\n"
        )
        result = check_workspace_absolute_references(recipe, binding)
        assert result.passed is True

    def test_fails_with_absolute_refs(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        ws_dir = binding.repo_path / "Test.xcworkspace"
        ws_dir.mkdir(parents=True)
        (ws_dir / "contents.xcworkspacedata").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Workspace version="1.0">\n'
            '  <FileRef location="absolute:/Users/dev/Sources/App.swift"/>\n'
            '  <FileRef location="group:Other.swift"/>\n'
            "</Workspace>\n"
        )
        result = check_workspace_absolute_references(recipe, binding)
        assert result.passed is False
        assert "absolute reference" in (result.message or "")
        assert "absolute:/Users/dev/Sources/App.swift" in result.details.get(
            "absolute_refs", []
        )

    def test_passes_when_workspace_dir_missing(self, tmp_path: Path) -> None:
        binding = _make_binding(tmp_path)
        recipe = _make_recipe()
        result = check_workspace_absolute_references(recipe, binding)
        assert result.passed is True


# ---------------------------------------------------------------------------
# _find_absolute_refs_in_workspace helper
# ---------------------------------------------------------------------------


class TestFindAbsoluteRefs:
    def test_empty_workspace(self, tmp_path: Path) -> None:
        f = tmp_path / "contents.xcworkspacedata"
        f.write_text('<?xml version="1.0"?>\n<Workspace version="1.0"></Workspace>\n')
        assert _find_absolute_refs_in_workspace(f) == []

    def test_mixed_refs(self, tmp_path: Path) -> None:
        f = tmp_path / "contents.xcworkspacedata"
        f.write_text(
            '<?xml version="1.0"?>\n'
            '<Workspace version="1.0">\n'
            '  <FileRef location="absolute:/foo/bar"/>\n'
            '  <FileRef location="group:baz"/>\n'
            '  <FileRef location="absolute:/qux"/>\n'
            "</Workspace>\n"
        )
        refs = _find_absolute_refs_in_workspace(f)
        assert refs == ["absolute:/foo/bar", "absolute:/qux"]

    def test_handles_parse_error(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.xml"
        f.write_text("not xml at all")
        assert _find_absolute_refs_in_workspace(f) == []


# ---------------------------------------------------------------------------
# run_preflight integration
# ---------------------------------------------------------------------------


class TestRunPreflight:
    @patch("palace_mcp.smoke.preflight.check_docker_available")
    @patch("palace_mcp.smoke.preflight.check_neo4j_reachable")
    @patch("palace_mcp.smoke.preflight.check_mcp_tools_list")
    @patch("palace_mcp.smoke.preflight.check_xcode_select")
    @patch("palace_mcp.smoke.preflight.check_xcodebuild_version")
    @patch("palace_mcp.smoke.preflight.check_xcode_license")
    @patch("palace_mcp.smoke.preflight.check_ios_sdk_runtime")
    async def test_all_pass(
        self,
        mock_ios: AsyncMock,
        mock_license: AsyncMock,
        mock_version: AsyncMock,
        mock_xcode_select: AsyncMock,
        mock_mcp: AsyncMock,
        mock_neo4j: AsyncMock,
        mock_docker: AsyncMock,
        tmp_path: Path,
    ) -> None:
        mock_docker.return_value = PreflightCheck(
            name="docker_available", passed=True, details={"server_version": "24.0"}
        )
        mock_neo4j.return_value = PreflightCheck(name="neo4j_reachable", passed=True)
        mock_mcp.return_value = PreflightCheck(
            name="mcp_tools_list", passed=True, details={"tool_count": 5}
        )
        mock_xcode_select.return_value = PreflightCheck(
            name="xcode_select", passed=True, details={"developer_dir": "/dev"}
        )
        mock_version.return_value = PreflightCheck(
            name="xcodebuild_version", passed=True, details={"output": "16.0"}
        )
        mock_license.return_value = PreflightCheck(name="xcode_license", passed=True)
        mock_ios.return_value = PreflightCheck(
            name="ios_sdk_runtime", passed=True, details={"ios_runtime_count": 1}
        )

        binding = _make_binding(tmp_path)
        recipe = _make_recipe(
            build={
                "workspace": "Test.xcworkspace",
                "scheme": "TestScheme",
                "package_resolution": "automatic",
            }
        )

        report = await run_preflight(recipe, binding)
        assert report.passed is True
        assert len(report.actionable_failures) == 0
        assert len(report.checks) == 15

    @patch("palace_mcp.smoke.preflight.check_docker_available")
    @patch("palace_mcp.smoke.preflight.check_neo4j_reachable")
    @patch("palace_mcp.smoke.preflight.check_mcp_tools_list")
    @patch("palace_mcp.smoke.preflight.check_xcode_select")
    @patch("palace_mcp.smoke.preflight.check_xcodebuild_version")
    @patch("palace_mcp.smoke.preflight.check_xcode_license")
    @patch("palace_mcp.smoke.preflight.check_ios_sdk_runtime")
    async def test_collects_actionable_failures(
        self,
        mock_ios: AsyncMock,
        mock_license: AsyncMock,
        mock_version: AsyncMock,
        mock_xcode_select: AsyncMock,
        mock_mcp: AsyncMock,
        mock_neo4j: AsyncMock,
        mock_docker: AsyncMock,
        tmp_path: Path,
    ) -> None:
        mock_docker.return_value = PreflightCheck(
            name="docker_available",
            passed=False,
            message="Docker not available: daemon not running",
        )
        mock_neo4j.return_value = PreflightCheck(
            name="neo4j_reachable",
            passed=False,
            message="Neo4j not reachable at http://localhost:7474",
        )
        mock_mcp.return_value = PreflightCheck(
            name="mcp_tools_list", passed=True, details={"tool_count": 5}
        )
        mock_xcode_select.return_value = PreflightCheck(
            name="xcode_select", passed=True, details={"developer_dir": "/dev"}
        )
        mock_version.return_value = PreflightCheck(
            name="xcodebuild_version", passed=True, details={"output": "16.0"}
        )
        mock_license.return_value = PreflightCheck(name="xcode_license", passed=True)
        mock_ios.return_value = PreflightCheck(
            name="ios_sdk_runtime", passed=True, details={"ios_runtime_count": 1}
        )

        binding = _make_binding(tmp_path)
        recipe = _make_recipe(
            build={
                "workspace": "Test.xcworkspace",
                "scheme": "TestScheme",
                "package_resolution": "automatic",
            }
        )

        report = await run_preflight(recipe, binding)
        assert report.passed is False
        assert len(report.actionable_failures) == 2
        assert any("Docker" in f for f in report.actionable_failures)
        assert any("Neo4j" in f for f in report.actionable_failures)

    async def test_no_download_during_preflight(self, tmp_path: Path) -> None:
        """Preflight must not download model files, Docker images, or SwiftPM packages."""
        binding = _make_binding(tmp_path, qodo_cache_path=tmp_path / "no-cache")
        recipe = _make_recipe()

        result = check_model_cache_path(binding)
        assert result.passed is False
        assert "download models" in (result.message or "")

        result2 = check_swiftpm_cache(recipe, binding)
        assert result2.passed is False
        assert "resolve packages" in (result2.message or "")
