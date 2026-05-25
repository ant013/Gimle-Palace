"""Pure helpers for xcode_workspace smoke recipes."""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from palace_mcp.smoke.recipe import EnsureConfigFromTemplate, Recipe
from palace_mcp.smoke.runtime_binding import RuntimeBinding


@dataclass(frozen=True)
class XcodeWorkspaceInvocation:
    cwd: Path
    command: tuple[str, ...]


def apply_prepare_steps(recipe: Recipe, binding: RuntimeBinding) -> None:
    for step in recipe.prepare_steps:
        if isinstance(step, EnsureConfigFromTemplate):
            template_path = binding.repo_path / step.template
            destination_path = binding.repo_path / step.destination
            if destination_path.exists():
                continue
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template_path, destination_path)


def build_xcode_workspace_invocation(
    recipe: Recipe,
    binding: RuntimeBinding,
    *,
    host_machine: str | None = None,
    package_resolution: Literal["locked", "automatic"] | None = None,
) -> XcodeWorkspaceInvocation:
    if recipe.build_system != "xcode_workspace" or recipe.build.workspace is None:
        raise ValueError(
            "xcode workspace invocation requires build_system=xcode_workspace"
        )

    resolved_package_resolution = package_resolution or recipe.build.package_resolution
    command: list[str] = [
        "xcrun",
        "xcodebuild",
        "-workspace",
        recipe.build.workspace,
        "-scheme",
        recipe.build.scheme,
        "-destination",
        recipe.build.destination,
        "-derivedDataPath",
        recipe.build.derived_data_path,
    ]
    if resolved_package_resolution == "locked":
        command.extend(
            [
                "-disableAutomaticPackageResolution",
                "-onlyUsePackageVersionsFromResolvedFile",
            ]
        )
    command.extend(
        [
            "-IDEIndexDisable=NO",
            "-IDEBuildLocationStyle=Custom",
            f"ARCHS={resolve_simulator_arch(recipe, host_machine=host_machine)}",
        ]
    )
    if not recipe.build.code_signing_allowed:
        command.extend(["CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO"])
    command.append("build")
    return XcodeWorkspaceInvocation(cwd=binding.repo_path, command=tuple(command))


def resolve_simulator_arch(recipe: Recipe, *, host_machine: str | None = None) -> str:
    simulator_arch = recipe.build.simulator_arch
    if simulator_arch != "auto":
        return simulator_arch

    machine = (host_machine or platform.machine()).lower()
    if machine in {"arm64", "aarch64", "arm64e"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    raise ValueError(f"unsupported host machine for simulator_arch=auto: {machine}")
