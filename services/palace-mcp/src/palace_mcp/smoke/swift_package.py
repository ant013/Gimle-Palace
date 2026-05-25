"""Pure helpers for swift_package smoke recipes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from palace_mcp.smoke.recipe import Recipe
from palace_mcp.smoke.runtime_binding import RuntimeBinding


@dataclass(frozen=True)
class SwiftPackageInvocation:
    cwd: Path
    command: tuple[str, ...]
    scip_reused: bool = False


def build_swift_package_invocation(
    recipe: Recipe,
    binding: RuntimeBinding,
    *,
    package_resolution: Literal["locked", "automatic"] | None = None,
) -> SwiftPackageInvocation:
    if recipe.build_system != "swift_package":
        raise ValueError("swift package invocation requires build_system=swift_package")

    scip_path = binding.repo_path / recipe.scip_path
    if scip_path.exists() and scip_path.stat().st_size > 0:
        return SwiftPackageInvocation(
            cwd=binding.repo_path, command=(), scip_reused=True
        )

    resolved = package_resolution or recipe.build.package_resolution

    command: list[str] = ["swift", "build"]
    command.extend(["--target", recipe.build.scheme])
    command.extend(["--build-path", recipe.build.derived_data_path])

    if resolved == "locked":
        command.append("--disable-automatic-resolution")

    index_store_path = f"{recipe.build.derived_data_path}/Index.noindex/DataStore"
    command.extend(["-Xswiftc", "-index-store-path", "-Xswiftc", index_store_path])

    return SwiftPackageInvocation(cwd=binding.repo_path, command=tuple(command))
