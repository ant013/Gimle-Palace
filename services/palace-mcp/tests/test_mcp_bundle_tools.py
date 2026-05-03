"""Tests for palace.memory.bundle.* MCP tools (GIM-182 Step 2).

Tests verify:
- Tool names are registered and unique (Pattern #21)
- Response shapes match spec contracts
- Invalid bundle names return structured errors, not raw exceptions
- Driver-unavailable path returns graceful error
- Tier validation rejects unknown values
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)


def _bundle_dict(name: str = "uw-ios") -> dict[str, Any]:
    return {
        "name": name,
        "description": "iOS wallet",
        "group_id": f"bundle/{name}",
        "created_at": _NOW,
    }


def _project_ref_dict(slug: str = "uw-ios-app") -> dict[str, Any]:
    return {
        "slug": slug,
        "tier": "user",
        "added_to_bundle_at": _NOW,
    }


def _bundle_status_dict(name: str = "uw-ios") -> dict[str, Any]:
    return {
        "name": name,
        "members_total": 1,
        "members_fresh_within_7d": 1,
        "members_stale": 0,
        "query_failed_slugs": (),
        "ingest_failed_slugs": (),
        "never_ingested_slugs": (),
        "stale_slugs": (),
        "oldest_member_ingest_at": _NOW,
        "newest_member_ingest_at": _NOW,
        "as_of": _NOW,
    }


# ---------------------------------------------------------------------------
# Pattern #21 registration tests (no driver needed)
# ---------------------------------------------------------------------------


class TestBundleToolRegistration:
    def test_bundle_tools_registered_unique(self) -> None:
        """All bundle tools pass Pattern #21 uniqueness check."""
        from palace_mcp.mcp_server import _registered_tool_names

        bundle_tools = [n for n in _registered_tool_names if "bundle" in n]
        assert len(bundle_tools) == len(set(bundle_tools)), (
            "duplicate bundle tool names"
        )

    def test_expected_bundle_tools_present(self) -> None:
        """All 5 bundle memory tools are registered."""
        from palace_mcp.mcp_server import _registered_tool_names

        expected = {
            "palace.memory.register_bundle",
            "palace.memory.add_to_bundle",
            "palace.memory.bundle_members",
            "palace.memory.bundle_status",
            "palace.memory.delete_bundle",
        }
        registered = set(_registered_tool_names)
        missing = expected - registered
        assert not missing, f"missing bundle tools: {missing}"

    def test_build_mcp_asgi_app_no_collision(self) -> None:
        """build_mcp_asgi_app() does not crash with bundle tools registered."""
        from palace_mcp.mcp_server import build_mcp_asgi_app

        build_mcp_asgi_app()  # would raise RuntimeError on duplicate


# ---------------------------------------------------------------------------
# palace.memory.register_bundle
# ---------------------------------------------------------------------------


class TestRegisterBundleTool:
    async def test_register_bundle_success(self) -> None:
        """Successful registration returns Bundle dict."""
        from palace_mcp.memory.models import Bundle
        from palace_mcp.mcp_server import palace_memory_register_bundle

        bundle = Bundle(**_bundle_dict())

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.register_bundle",
                new=AsyncMock(return_value=bundle),
            ),
        ):
            result = await palace_memory_register_bundle(
                name="uw-ios", description="iOS wallet"
            )

        assert result["name"] == "uw-ios"
        assert result["group_id"] == "bundle/uw-ios"

    async def test_register_bundle_invalid_name_returns_error_envelope(self) -> None:
        """Invalid bundle name → structured error dict, not raised exception."""
        from palace_mcp.mcp_server import palace_memory_register_bundle

        with patch("palace_mcp.mcp_server._driver", new=MagicMock()):
            result = await palace_memory_register_bundle(
                name="INVALID_NAME", description="test"
            )

        assert result["ok"] is False
        assert result["error_code"] == "invalid_bundle_name"
        assert "INVALID_NAME" in result["message"]

    async def test_register_bundle_conflict_returns_error_envelope(self) -> None:
        """BundleNameConflictsWithProject → structured error, not exception."""
        from palace_mcp.memory.bundle import BundleNameConflictsWithProject
        from palace_mcp.mcp_server import palace_memory_register_bundle

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.register_bundle",
                new=AsyncMock(side_effect=BundleNameConflictsWithProject("uw-ios")),
            ),
        ):
            result = await palace_memory_register_bundle(
                name="uw-ios", description="test"
            )

        assert result["ok"] is False
        assert result["error_code"] == "bundle_name_conflicts_with_project"

    async def test_register_bundle_driver_unavailable(self) -> None:
        """None driver → graceful error (handle_tool_error path)."""
        from palace_mcp.mcp_server import palace_memory_register_bundle

        with patch("palace_mcp.mcp_server._driver", new=None):
            # handle_tool_error raises McpError, which propagates
            with pytest.raises(Exception):
                await palace_memory_register_bundle(name="uw-ios", description="test")


# ---------------------------------------------------------------------------
# palace.memory.add_to_bundle
# ---------------------------------------------------------------------------


class TestAddToBundleTool:
    async def test_add_to_bundle_success(self) -> None:
        """Successful add returns ok=True."""
        from palace_mcp.mcp_server import palace_memory_add_to_bundle

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.add_to_bundle",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await palace_memory_add_to_bundle(
                bundle="uw-ios", project="uw-ios-app", tier="user"
            )

        assert result["ok"] is True

    async def test_add_to_bundle_invalid_tier_returns_error(self) -> None:
        """Unknown tier value → structured error, not raw exception."""
        from palace_mcp.mcp_server import palace_memory_add_to_bundle

        with patch("palace_mcp.mcp_server._driver", new=MagicMock()):
            result = await palace_memory_add_to_bundle(
                bundle="uw-ios", project="uw-ios-app", tier="invalid-tier"
            )

        assert result["ok"] is False
        assert "tier" in result["message"].lower() or "error_code" in result

    async def test_add_to_bundle_bundle_not_found(self) -> None:
        """BundleNotFoundError → structured error."""
        from palace_mcp.memory.bundle import BundleNotFoundError
        from palace_mcp.mcp_server import palace_memory_add_to_bundle

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.add_to_bundle",
                new=AsyncMock(side_effect=BundleNotFoundError("no-such")),
            ),
        ):
            result = await palace_memory_add_to_bundle(
                bundle="no-such", project="p", tier="user"
            )

        assert result["ok"] is False
        assert result["error_code"] == "bundle_not_found"


# ---------------------------------------------------------------------------
# palace.memory.bundle_members
# ---------------------------------------------------------------------------


class TestBundleMembersTool:
    async def test_bundle_members_success(self) -> None:
        """Returns list of project ref dicts."""
        from palace_mcp.memory.models import ProjectRef, Tier
        from palace_mcp.mcp_server import palace_memory_bundle_members

        ref = ProjectRef(slug="uw-ios-app", tier=Tier.USER, added_to_bundle_at=_NOW)

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.bundle_members",
                new=AsyncMock(return_value=(ref,)),
            ),
        ):
            result = await palace_memory_bundle_members(bundle="uw-ios")

        assert isinstance(result, list)
        assert result[0]["slug"] == "uw-ios-app"
        assert result[0]["tier"] == "user"

    async def test_bundle_members_bundle_not_found(self) -> None:
        """BundleNotFoundError → structured error."""
        from palace_mcp.memory.bundle import BundleNotFoundError
        from palace_mcp.mcp_server import palace_memory_bundle_members

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.bundle_members",
                new=AsyncMock(side_effect=BundleNotFoundError("nope")),
            ),
        ):
            result = await palace_memory_bundle_members(bundle="nope")

        assert result["ok"] is False
        assert result["error_code"] == "bundle_not_found"


# ---------------------------------------------------------------------------
# palace.memory.bundle_status
# ---------------------------------------------------------------------------


class TestBundleStatusTool:
    async def test_bundle_status_success(self) -> None:
        """Returns BundleStatus dict with failure taxonomy fields."""
        from palace_mcp.memory.models import BundleStatus
        from palace_mcp.mcp_server import palace_memory_bundle_status

        status = BundleStatus(**_bundle_status_dict())

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.bundle_status",
                new=AsyncMock(return_value=status),
            ),
        ):
            result = await palace_memory_bundle_status(bundle="uw-ios")

        # 3-way failure taxonomy must be present in response
        assert "query_failed_slugs" in result
        assert "ingest_failed_slugs" in result
        assert "never_ingested_slugs" in result
        assert result["members_total"] == 1

    async def test_bundle_status_not_found(self) -> None:
        """BundleNotFoundError → structured error."""
        from palace_mcp.memory.bundle import BundleNotFoundError
        from palace_mcp.mcp_server import palace_memory_bundle_status

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.bundle_status",
                new=AsyncMock(side_effect=BundleNotFoundError("no")),
            ),
        ):
            result = await palace_memory_bundle_status(bundle="no")

        assert result["ok"] is False
        assert result["error_code"] == "bundle_not_found"


# ---------------------------------------------------------------------------
# palace.memory.delete_bundle
# ---------------------------------------------------------------------------


class TestDeleteBundleTool:
    async def test_delete_bundle_cascade_success(self) -> None:
        """cascade=True returns ok=True."""
        from palace_mcp.mcp_server import palace_memory_delete_bundle

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.delete_bundle",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await palace_memory_delete_bundle(name="uw-ios", cascade=True)

        assert result["ok"] is True

    async def test_delete_bundle_non_cascade_non_empty(self) -> None:
        """BundleNonEmpty with cascade=False → structured error."""
        from palace_mcp.memory.bundle import BundleNonEmpty
        from palace_mcp.mcp_server import palace_memory_delete_bundle

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.delete_bundle",
                new=AsyncMock(side_effect=BundleNonEmpty("uw-ios")),
            ),
        ):
            result = await palace_memory_delete_bundle(name="uw-ios", cascade=False)

        assert result["ok"] is False
        assert result["error_code"] == "bundle_non_empty"

    async def test_delete_bundle_not_found(self) -> None:
        """BundleNotFoundError → structured error."""
        from palace_mcp.memory.bundle import BundleNotFoundError
        from palace_mcp.mcp_server import palace_memory_delete_bundle

        with (
            patch("palace_mcp.mcp_server._driver", new=MagicMock()),
            patch(
                "palace_mcp.mcp_server.delete_bundle",
                new=AsyncMock(side_effect=BundleNotFoundError("x")),
            ),
        ):
            result = await palace_memory_delete_bundle(name="x", cascade=False)

        assert result["ok"] is False
        assert result["error_code"] == "bundle_not_found"
