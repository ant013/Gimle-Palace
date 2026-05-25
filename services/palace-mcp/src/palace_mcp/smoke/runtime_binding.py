"""Local runtime binding — machine-local absolute paths for smoke execution.

GIM-839 D0 contract: runtime bindings are NOT committed. They supply the
machine-local checkout path, mount root, and service URLs that recipes
intentionally exclude.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, model_validator


class RuntimeBinding(BaseModel, frozen=True):
    """Machine-local binding for a versioned recipe."""

    repo_path: Path
    parent_mount: Path
    mcp_url: str

    qodo_cache_path: Path | None = None
    swiftpm_cache_path: Path | None = None
    docker_compose_override: str | None = None

    @model_validator(mode="after")
    def _validate_paths(self) -> RuntimeBinding:
        if not self.repo_path.is_absolute():
            raise ValueError(f"repo_path must be absolute, got: '{self.repo_path}'")
        if not self.parent_mount.is_absolute():
            raise ValueError(
                f"parent_mount must be absolute, got: '{self.parent_mount}'"
            )

        try:
            resolved_repo = self.repo_path.resolve()
            resolved_mount = self.parent_mount.resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"cannot resolve paths: {exc}") from exc

        if not _is_inside(resolved_repo, resolved_mount):
            raise ValueError(
                f"repo_path '{self.repo_path}' does not resolve inside "
                f"parent_mount '{self.parent_mount}'"
            )

        return self


def _is_inside(child: Path, parent: Path) -> bool:
    """Check if child path is inside parent path (both must be resolved)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
