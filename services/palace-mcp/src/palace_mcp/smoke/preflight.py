"""Runtime preflight checks — verify host environment before smoke execution.

GIM-839 A6: checks Docker, Neo4j, MCP, Qodo, Xcode, iOS SDK, SwiftPM, and
workspace references. Produces actionable failures without downloading
model files, Docker images, or SwiftPM packages.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from palace_mcp.smoke.recipe import Recipe
from palace_mcp.smoke.runtime_binding import RuntimeBinding

logger = logging.getLogger(__name__)

_ABSOLUTE_REF_RE = re.compile(r"absolute:")


class PreflightCheck(BaseModel, frozen=True):
    name: str
    passed: bool
    message: str | None = None
    details: dict[str, Any] = {}


class PreflightReport(BaseModel, frozen=True):
    checks: list[PreflightCheck]
    passed: bool
    actionable_failures: list[str] = []


async def run_preflight(
    recipe: Recipe,
    binding: RuntimeBinding,
) -> PreflightReport:
    checks: list[PreflightCheck] = []

    checks.append(check_repo_path(binding))
    checks.append(check_scip_path_writable(recipe, binding))
    checks.append(check_host_architecture(recipe))
    checks.append(await check_docker_available())
    checks.append(await check_neo4j_reachable(binding))
    checks.append(await check_mcp_tools_list(binding))
    checks.append(check_model_cache_path(binding))
    checks.append(check_local_only_model_mode(binding))
    checks.append(check_embedding_limits())
    checks.append(await check_xcode_select())
    checks.append(await check_xcodebuild_version())
    checks.append(await check_xcode_license())
    checks.append(await check_ios_sdk_runtime())
    checks.append(check_swiftpm_cache(recipe, binding))
    checks.append(check_workspace_absolute_references(recipe, binding))

    actionable = [c.message for c in checks if not c.passed and c.message]
    return PreflightReport(
        checks=checks,
        passed=all(c.passed for c in checks),
        actionable_failures=actionable,
    )


def check_repo_path(binding: RuntimeBinding) -> PreflightCheck:
    if not binding.repo_path.is_dir():
        return PreflightCheck(
            name="repo_path",
            passed=False,
            message=f"repo_path does not exist: {binding.repo_path}",
        )
    return PreflightCheck(
        name="repo_path",
        passed=True,
        details={"path": str(binding.repo_path)},
    )


def check_scip_path_writable(recipe: Recipe, binding: RuntimeBinding) -> PreflightCheck:
    scip_parent = (binding.repo_path / recipe.scip_path).parent
    if scip_parent.exists() and not scip_parent.is_dir():
        return PreflightCheck(
            name="scip_path_writable",
            passed=False,
            message=f"SCIP output parent is not a directory: {scip_parent}",
        )
    return PreflightCheck(
        name="scip_path_writable",
        passed=True,
        details={"scip_parent": str(scip_parent), "exists": scip_parent.is_dir()},
    )


def check_host_architecture(recipe: Recipe) -> PreflightCheck:
    import platform

    machine = platform.machine().lower()
    known = {"arm64", "aarch64", "arm64e", "x86_64", "amd64"}
    if machine not in known:
        return PreflightCheck(
            name="host_architecture",
            passed=False,
            message=f"unsupported host architecture: {machine}",
            details={"machine": machine},
        )
    resolved_arch = "arm64" if machine in {"arm64", "aarch64", "arm64e"} else "x86_64"
    sim_arch = recipe.build.simulator_arch
    effective = resolved_arch if sim_arch == "auto" else sim_arch
    return PreflightCheck(
        name="host_architecture",
        passed=True,
        details={
            "machine": machine,
            "resolved_arch": resolved_arch,
            "simulator_arch_config": sim_arch,
            "effective_simulator_arch": effective,
        },
    )


async def check_docker_available() -> PreflightCheck:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            "--format",
            "{{.ServerVersion}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            msg = (stderr or b"").decode(errors="replace").strip()
            return PreflightCheck(
                name="docker_available",
                passed=False,
                message=f"Docker not available: {msg or 'docker info failed'}",
            )
        version = stdout.decode(errors="replace").strip()
        return PreflightCheck(
            name="docker_available",
            passed=True,
            details={"server_version": version},
        )
    except FileNotFoundError:
        return PreflightCheck(
            name="docker_available",
            passed=False,
            message="Docker CLI not found in PATH — install Docker Desktop",
        )
    except asyncio.TimeoutError:
        return PreflightCheck(
            name="docker_available",
            passed=False,
            message="Docker info timed out — is Docker daemon running?",
        )


async def check_neo4j_reachable(binding: RuntimeBinding) -> PreflightCheck:
    neo4j_url = _derive_neo4j_url(binding.mcp_url)
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl",
            "-sf",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            neo4j_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        code = stdout.decode(errors="replace").strip()
        if proc.returncode == 0 or code.startswith("2") or code.startswith("4"):
            return PreflightCheck(
                name="neo4j_reachable",
                passed=True,
                details={"url": neo4j_url, "http_code": code},
            )
        return PreflightCheck(
            name="neo4j_reachable",
            passed=False,
            message=f"Neo4j not reachable at {neo4j_url} (HTTP {code})",
            details={"url": neo4j_url, "http_code": code},
        )
    except (FileNotFoundError, asyncio.TimeoutError):
        return PreflightCheck(
            name="neo4j_reachable",
            passed=False,
            message=f"Cannot reach Neo4j at {neo4j_url} — is the container running?",
            details={"url": neo4j_url},
        )


def _derive_neo4j_url(mcp_url: str) -> str:
    if "localhost" in mcp_url or "127.0.0.1" in mcp_url:
        return "http://localhost:7474"
    return "http://localhost:7474"


async def check_mcp_tools_list(binding: RuntimeBinding) -> PreflightCheck:
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl",
            "-sf",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            '{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
            binding.mcp_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            return PreflightCheck(
                name="mcp_tools_list",
                passed=False,
                message=f"MCP unreachable at {binding.mcp_url}",
                details={"url": binding.mcp_url},
            )
        import json

        try:
            data = json.loads(stdout.decode(errors="replace"))
            tools = data.get("result", {}).get("tools", [])
            tool_names = [t.get("name", "") for t in tools]
            return PreflightCheck(
                name="mcp_tools_list",
                passed=True,
                details={
                    "url": binding.mcp_url,
                    "tool_count": len(tool_names),
                },
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return PreflightCheck(
                name="mcp_tools_list",
                passed=True,
                details={"url": binding.mcp_url, "note": "response not JSON-RPC"},
            )
    except (FileNotFoundError, asyncio.TimeoutError):
        return PreflightCheck(
            name="mcp_tools_list",
            passed=False,
            message=f"MCP unreachable at {binding.mcp_url} — is palace-mcp running?",
            details={"url": binding.mcp_url},
        )


def check_model_cache_path(binding: RuntimeBinding) -> PreflightCheck:
    if binding.qodo_cache_path is None:
        return PreflightCheck(
            name="model_cache_path",
            passed=True,
            details={"configured": False, "note": "no qodo_cache_path in binding"},
        )
    if not binding.qodo_cache_path.is_dir():
        return PreflightCheck(
            name="model_cache_path",
            passed=False,
            message=(
                f"Qodo model cache not found: {binding.qodo_cache_path} — "
                "download models before running smoke"
            ),
            details={"path": str(binding.qodo_cache_path)},
        )
    return PreflightCheck(
        name="model_cache_path",
        passed=True,
        details={"path": str(binding.qodo_cache_path)},
    )


def check_local_only_model_mode(binding: RuntimeBinding) -> PreflightCheck:
    import os

    local_only = os.environ.get("PALACE_EMBEDDING_LOCAL_ONLY", "").lower()
    if binding.qodo_cache_path and local_only not in ("1", "true", "yes"):
        return PreflightCheck(
            name="local_only_model_mode",
            passed=True,
            details={
                "env_set": bool(local_only),
                "note": "PALACE_EMBEDDING_LOCAL_ONLY not enforced",
            },
        )
    return PreflightCheck(
        name="local_only_model_mode",
        passed=True,
        details={"local_only": local_only or "not set"},
    )


def check_embedding_limits() -> PreflightCheck:
    import os

    limit_str = os.environ.get("PALACE_EMBEDDING_LIMIT", "")
    if limit_str:
        try:
            limit = int(limit_str)
            return PreflightCheck(
                name="embedding_limits",
                passed=True,
                details={"limit": limit, "source": "env"},
            )
        except ValueError:
            return PreflightCheck(
                name="embedding_limits",
                passed=False,
                message=f"PALACE_EMBEDDING_LIMIT is not a valid integer: {limit_str!r}",
            )
    return PreflightCheck(
        name="embedding_limits",
        passed=True,
        details={"limit": None, "note": "no explicit limit configured"},
    )


async def check_xcode_select() -> PreflightCheck:
    try:
        proc = await asyncio.create_subprocess_exec(
            "xcode-select",
            "-p",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            msg = (stderr or b"").decode(errors="replace").strip()
            return PreflightCheck(
                name="xcode_select",
                passed=False,
                message=f"xcode-select not configured: {msg}",
            )
        path = stdout.decode(errors="replace").strip()
        return PreflightCheck(
            name="xcode_select",
            passed=True,
            details={"developer_dir": path},
        )
    except FileNotFoundError:
        return PreflightCheck(
            name="xcode_select",
            passed=False,
            message="xcode-select not found — install Xcode Command Line Tools",
        )
    except asyncio.TimeoutError:
        return PreflightCheck(
            name="xcode_select",
            passed=False,
            message="xcode-select timed out",
        )


async def check_xcodebuild_version() -> PreflightCheck:
    try:
        proc = await asyncio.create_subprocess_exec(
            "xcodebuild",
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            msg = (stderr or b"").decode(errors="replace").strip()
            return PreflightCheck(
                name="xcodebuild_version",
                passed=False,
                message=f"xcodebuild -version failed: {msg}",
            )
        output = stdout.decode(errors="replace").strip()
        return PreflightCheck(
            name="xcodebuild_version",
            passed=True,
            details={"output": output},
        )
    except FileNotFoundError:
        return PreflightCheck(
            name="xcodebuild_version",
            passed=False,
            message="xcodebuild not found — install Xcode",
        )
    except asyncio.TimeoutError:
        return PreflightCheck(
            name="xcodebuild_version",
            passed=False,
            message="xcodebuild -version timed out",
        )


async def check_xcode_license() -> PreflightCheck:
    try:
        proc = await asyncio.create_subprocess_exec(
            "xcodebuild",
            "-checkFirstLaunchStatus",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            msg = (stderr or b"").decode(errors="replace").strip()
            if "license" in msg.lower() or "agree" in msg.lower():
                return PreflightCheck(
                    name="xcode_license",
                    passed=False,
                    message="Xcode license not accepted — run: sudo xcodebuild -license accept",
                )
            return PreflightCheck(
                name="xcode_license",
                passed=False,
                message=f"Xcode first-launch check failed: {msg[:200]}",
            )
        return PreflightCheck(
            name="xcode_license",
            passed=True,
        )
    except FileNotFoundError:
        return PreflightCheck(
            name="xcode_license",
            passed=False,
            message="xcodebuild not found — cannot verify license",
        )
    except asyncio.TimeoutError:
        return PreflightCheck(
            name="xcode_license",
            passed=False,
            message="xcode license check timed out",
        )


async def check_ios_sdk_runtime() -> PreflightCheck:
    try:
        proc = await asyncio.create_subprocess_exec(
            "xcrun",
            "simctl",
            "list",
            "runtimes",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            return PreflightCheck(
                name="ios_sdk_runtime",
                passed=False,
                message="simctl list runtimes failed — no simulator runtimes available",
            )
        import json

        try:
            data = json.loads(stdout.decode(errors="replace"))
            runtimes = data.get("runtimes", [])
            ios_runtimes = [
                r
                for r in runtimes
                if r.get("platform", "").lower() == "ios"
                and r.get("isAvailable", False)
            ]
            if not ios_runtimes:
                return PreflightCheck(
                    name="ios_sdk_runtime",
                    passed=False,
                    message="No available iOS simulator runtimes — install via Xcode > Settings > Platforms",
                    details={"total_runtimes": len(runtimes)},
                )
            latest = ios_runtimes[-1]
            return PreflightCheck(
                name="ios_sdk_runtime",
                passed=True,
                details={
                    "ios_runtime_count": len(ios_runtimes),
                    "latest_version": latest.get("version", "unknown"),
                    "latest_name": latest.get("name", "unknown"),
                },
            )
        except (json.JSONDecodeError, KeyError):
            return PreflightCheck(
                name="ios_sdk_runtime",
                passed=False,
                message="Cannot parse simctl runtimes output",
            )
    except FileNotFoundError:
        return PreflightCheck(
            name="ios_sdk_runtime",
            passed=False,
            message="xcrun not found — Xcode Command Line Tools required",
        )
    except asyncio.TimeoutError:
        return PreflightCheck(
            name="ios_sdk_runtime",
            passed=False,
            message="simctl list runtimes timed out",
        )


def check_swiftpm_cache(recipe: Recipe, binding: RuntimeBinding) -> PreflightCheck:
    if recipe.build.package_resolution == "locked":
        resolved_file = binding.repo_path / "Package.resolved"
        workspace_resolved = None
        if recipe.build.workspace:
            workspace_resolved = (
                binding.repo_path
                / recipe.build.workspace
                / "xcshareddata"
                / "swiftpm"
                / "Package.resolved"
            )

        has_resolved = resolved_file.is_file() or (
            workspace_resolved is not None and workspace_resolved.is_file()
        )
        if not has_resolved:
            return PreflightCheck(
                name="swiftpm_cache",
                passed=False,
                message=(
                    "Package.resolved not found but package_resolution=locked — "
                    "resolve packages first or switch to automatic"
                ),
                details={
                    "checked": [str(resolved_file)]
                    + ([str(workspace_resolved)] if workspace_resolved else []),
                },
            )

    if binding.swiftpm_cache_path and not binding.swiftpm_cache_path.is_dir():
        return PreflightCheck(
            name="swiftpm_cache",
            passed=False,
            message=f"SwiftPM cache path does not exist: {binding.swiftpm_cache_path}",
            details={"path": str(binding.swiftpm_cache_path)},
        )

    return PreflightCheck(
        name="swiftpm_cache",
        passed=True,
        details={
            "package_resolution": recipe.build.package_resolution,
            "cache_path": str(binding.swiftpm_cache_path)
            if binding.swiftpm_cache_path
            else None,
        },
    )


def check_workspace_absolute_references(
    recipe: Recipe, binding: RuntimeBinding
) -> PreflightCheck:
    if not recipe.build.workspace:
        return PreflightCheck(
            name="workspace_absolute_references",
            passed=True,
            details={"note": "no workspace configured"},
        )

    workspace_path = binding.repo_path / recipe.build.workspace
    contents_path = workspace_path / "contents.xcworkspacedata"
    if not contents_path.is_file():
        return PreflightCheck(
            name="workspace_absolute_references",
            passed=True,
            details={"note": "workspace data file not found — skipped"},
        )

    absolute_refs = _find_absolute_refs_in_workspace(contents_path)
    if absolute_refs:
        return PreflightCheck(
            name="workspace_absolute_references",
            passed=False,
            message=(
                f"Workspace contains {len(absolute_refs)} absolute reference(s) — "
                "these break portability. "
                "Convert to group: or container: references."
            ),
            details={"absolute_refs": absolute_refs[:10]},
        )
    return PreflightCheck(
        name="workspace_absolute_references",
        passed=True,
    )


def _find_absolute_refs_in_workspace(contents_path: Path) -> list[str]:
    try:
        tree = ET.parse(contents_path)  # noqa: S314
        root = tree.getroot()
        refs: list[str] = []
        for file_ref in root.iter("FileRef"):
            location = file_ref.get("location", "")
            if location.startswith("absolute:"):
                refs.append(location)
        return refs
    except (ET.ParseError, OSError):
        return []
