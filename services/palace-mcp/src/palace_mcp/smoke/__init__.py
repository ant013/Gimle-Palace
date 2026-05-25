"""Productized runtime smoke contracts (GIM-839 D0)."""

from palace_mcp.smoke.recipe import BuildConfig, EnsureConfigFromTemplate, Recipe
from palace_mcp.smoke.runner import (
    SMOKE_STAGES,
    RunReport,
    SmokeRunner,
    StageResult,
    StageStatus,
    write_report_json,
)
from palace_mcp.smoke.runtime_binding import RuntimeBinding
from palace_mcp.smoke.swift_package import (
    SwiftPackageInvocation,
    build_swift_package_invocation,
)
from palace_mcp.smoke.xcode_workspace import (
    XcodeWorkspaceInvocation,
    apply_prepare_steps,
    build_xcode_workspace_invocation,
    resolve_simulator_arch,
)

__all__ = [
    "BuildConfig",
    "EnsureConfigFromTemplate",
    "Recipe",
    "RunReport",
    "RuntimeBinding",
    "SMOKE_STAGES",
    "SmokeRunner",
    "StageResult",
    "StageStatus",
    "SwiftPackageInvocation",
    "XcodeWorkspaceInvocation",
    "apply_prepare_steps",
    "build_swift_package_invocation",
    "build_xcode_workspace_invocation",
    "resolve_simulator_arch",
    "write_report_json",
]
