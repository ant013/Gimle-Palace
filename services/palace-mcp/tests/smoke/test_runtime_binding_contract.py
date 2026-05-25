"""Contract tests for RuntimeBinding (GIM-839 D0 / A0).

Acceptance:
- Tests reject repo_path outside parent_mount.
- Tests accept repo path only through runtime binding.
- repo_path and parent_mount must be absolute.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from palace_mcp.smoke.runtime_binding import RuntimeBinding


# ---------------------------------------------------------------------------
# Valid bindings
# ---------------------------------------------------------------------------


class TestValidBinding:
    def test_uw_ios_binding(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/ABS/PATH/HorizontalSystems/unstoppable-wallet-ios"),
            parent_mount=Path("/ABS/PATH/HorizontalSystems"),
            mcp_url="http://localhost:8000/mcp",
            qodo_cache_path=Path("/ABS/PATH/hf-cache/huggingface"),
            swiftpm_cache_path=Path("/ABS/PATH/swiftpm-cache"),
            docker_compose_override="docker-compose.macbook-smoke.yml",
        )
        assert binding.repo_path == Path(
            "/ABS/PATH/HorizontalSystems/unstoppable-wallet-ios"
        )
        assert binding.mcp_url == "http://localhost:8000/mcp"

    def test_minimal_binding(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/repos/bitcoin-kit-ios"),
            parent_mount=Path("/repos"),
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.qodo_cache_path is None
        assert binding.swiftpm_cache_path is None
        assert binding.docker_compose_override is None

    def test_repo_path_directly_inside_mount(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/mount/repo"),
            parent_mount=Path("/mount"),
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.repo_path.name == "repo"


# ---------------------------------------------------------------------------
# Reject repo_path outside parent_mount
# ---------------------------------------------------------------------------


class TestRepoPathInsideMount:
    def test_reject_repo_outside_mount(self) -> None:
        with pytest.raises(
            ValidationError, match="does not resolve inside parent_mount"
        ):
            RuntimeBinding(
                repo_path=Path("/elsewhere/repo"),
                parent_mount=Path("/mount"),
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_sibling_path(self) -> None:
        with pytest.raises(
            ValidationError, match="does not resolve inside parent_mount"
        ):
            RuntimeBinding(
                repo_path=Path("/mount-extra/repo"),
                parent_mount=Path("/mount"),
                mcp_url="http://localhost:8000/mcp",
            )


# ---------------------------------------------------------------------------
# Reject relative paths
# ---------------------------------------------------------------------------


class TestRejectRelativePaths:
    def test_reject_relative_repo_path(self) -> None:
        with pytest.raises(ValidationError, match="repo_path must be absolute"):
            RuntimeBinding(
                repo_path=Path("relative/repo"),
                parent_mount=Path("/mount"),
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_relative_parent_mount(self) -> None:
        with pytest.raises(ValidationError, match="parent_mount must be absolute"):
            RuntimeBinding(
                repo_path=Path("/mount/repo"),
                parent_mount=Path("relative/mount"),
                mcp_url="http://localhost:8000/mcp",
            )
