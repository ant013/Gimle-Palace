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
            mount_name="hs",
            mcp_mount_name="hs",
            mcp_url="http://localhost:8000/mcp",
            qodo_cache_path=Path("/ABS/PATH/hf-cache/huggingface"),
            swiftpm_cache_path=Path("/ABS/PATH/swiftpm-cache"),
            docker_compose_override="docker-compose.macbook-smoke.yml",
        )
        assert binding.repo_path == Path(
            "/ABS/PATH/HorizontalSystems/unstoppable-wallet-ios"
        )
        assert binding.mcp_url == "http://localhost:8000/mcp"
        assert binding.mount_name == "hs"
        assert binding.mcp_mount_name == "hs"

    def test_minimal_binding(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/repos/bitcoin-kit-ios"),
            parent_mount=Path("/repos"),
            mount_name="repos",
            mcp_mount_name="repos",
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.qodo_cache_path is None
        assert binding.swiftpm_cache_path is None
        assert binding.docker_compose_override is None

    def test_repo_path_directly_inside_mount(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/mount/repo"),
            parent_mount=Path("/mount"),
            mount_name="mount",
            mcp_mount_name="mount",
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.repo_path.name == "repo"

    def test_mcp_mount_name_can_differ_from_mount_name(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/host/ios/repo"),
            parent_mount=Path("/host/ios"),
            mount_name="ios",
            mcp_mount_name="hs",
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.mount_name == "ios"
        assert binding.mcp_mount_name == "hs"


# ---------------------------------------------------------------------------
# mount_name validation
# ---------------------------------------------------------------------------


class TestMountNameValidation:
    def test_valid_short_name(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/hs/repo"),
            parent_mount=Path("/hs"),
            mount_name="hs",
            mcp_mount_name="hs",
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.mount_name == "hs"

    def test_valid_name_with_digits_and_dashes(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/mount123/repo"),
            parent_mount=Path("/mount123"),
            mount_name="mount-123",
            mcp_mount_name="mount-123",
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.mount_name == "mount-123"

    def test_reject_uppercase(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeBinding(
                repo_path=Path("/mount/repo"),
                parent_mount=Path("/mount"),
                mount_name="HS",
                mcp_mount_name="hs",
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_starts_with_digit(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeBinding(
                repo_path=Path("/mount/repo"),
                parent_mount=Path("/mount"),
                mount_name="1mount",
                mcp_mount_name="mount",
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_too_long(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeBinding(
                repo_path=Path("/mount/repo"),
                parent_mount=Path("/mount"),
                mount_name="a" * 17,
                mcp_mount_name="ok",
                mcp_url="http://localhost:8000/mcp",
            )


# ---------------------------------------------------------------------------
# mcp_mount_name validation (GIM-852)
# ---------------------------------------------------------------------------


class TestMcpMountNameValidation:
    def test_valid_mcp_mount_name(self) -> None:
        binding = RuntimeBinding(
            repo_path=Path("/ios/repo"),
            parent_mount=Path("/ios"),
            mount_name="ios",
            mcp_mount_name="ios",
            mcp_url="http://localhost:8000/mcp",
        )
        assert binding.mcp_mount_name == "ios"

    def test_reject_absolute_path_as_mcp_mount_name(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeBinding(
                repo_path=Path("/ios/repo"),
                parent_mount=Path("/ios"),
                mount_name="ios",
                mcp_mount_name="/Users/Shared/Ios",
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_mcp_mount_name_with_uppercase(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeBinding(
                repo_path=Path("/ios/repo"),
                parent_mount=Path("/ios"),
                mount_name="ios",
                mcp_mount_name="IOS",
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_mcp_mount_name_too_long(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeBinding(
                repo_path=Path("/ios/repo"),
                parent_mount=Path("/ios"),
                mount_name="ios",
                mcp_mount_name="a" * 17,
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_mcp_mount_name_with_slashes(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeBinding(
                repo_path=Path("/ios/repo"),
                parent_mount=Path("/ios"),
                mount_name="ios",
                mcp_mount_name="ios/hs",
                mcp_url="http://localhost:8000/mcp",
            )


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
                mount_name="mount",
                mcp_mount_name="mount",
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_sibling_path(self) -> None:
        with pytest.raises(
            ValidationError, match="does not resolve inside parent_mount"
        ):
            RuntimeBinding(
                repo_path=Path("/mount-extra/repo"),
                parent_mount=Path("/mount"),
                mount_name="mount",
                mcp_mount_name="mount",
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
                mount_name="mount",
                mcp_mount_name="mount",
                mcp_url="http://localhost:8000/mcp",
            )

    def test_reject_relative_parent_mount(self) -> None:
        with pytest.raises(ValidationError, match="parent_mount must be absolute"):
            RuntimeBinding(
                repo_path=Path("/mount/repo"),
                parent_mount=Path("relative/mount"),
                mount_name="mount",
                mcp_mount_name="mount",
                mcp_url="http://localhost:8000/mcp",
            )
