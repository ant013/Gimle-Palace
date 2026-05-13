"""Unit tests for bundle-mode per-member discovery in run.py (GIM-283-1 Task 2.3b).

RED tests verify:
1. Bundle mode discovers statuses per-member with its own profile.
2. RUN_FAILED from one member aggregates into status_counts.
3. Single-project mode is unchanged (flat status dict, no member_slug column).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.audit.contracts import AuditContract
from palace_mcp.audit.discovery import ExtractorStatus
from palace_mcp.extractors.base import BaseExtractor, ExtractorStats
from palace_mcp.extractors.foundation.profiles import LanguageProfile
from palace_mcp.memory.models import ProjectRef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extractor(name: str) -> BaseExtractor:
    class _Ext(BaseExtractor):
        description = "test"

        async def run(self, **_: Any) -> ExtractorStats:
            return ExtractorStats()

        def audit_contract(self) -> AuditContract | None:
            return AuditContract(
                extractor_name=name,
                template_name="hotspot.md",
                query="RETURN 1",
                severity_column="sev",
            )

    ext = _Ext.__new__(_Ext)
    return ext


def _project_ref(slug: str) -> ProjectRef:
    from datetime import datetime, timezone
    return ProjectRef(
        slug=slug,
        tier="first-party",
        added_to_bundle_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class _EmptyAsyncResult:
    def __aiter__(self) -> "_EmptyAsyncResult":
        return self

    async def __anext__(self) -> None:
        raise StopAsyncIteration

    async def single(self) -> None:
        return None


def _make_empty_driver() -> Any:
    session = AsyncMock()
    session.run = AsyncMock(return_value=_EmptyAsyncResult())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    drv = MagicMock()
    drv.session = MagicMock(return_value=session)
    return drv


_SWIFT_KIT_PROFILE = LanguageProfile("swift_kit", frozenset({"hotspot"}))
_PYTHON_PROFILE = LanguageProfile("python_service", frozenset({"hotspot"}))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bundle_mode_discovers_per_member() -> None:
    """Bundle with 2 members → discover called once per member, each with own profile."""
    from palace_mcp.audit.run import run_audit

    drv = _make_empty_driver()
    registry = {"hotspot": _make_extractor("hotspot")}
    members = (_project_ref("tron-kit"), _project_ref("oz-v5-mini"))

    # tron-kit → swift_kit profile, oz-v5-mini → python_service profile
    profile_by_slug = {"tron-kit": _SWIFT_KIT_PROFILE, "oz-v5-mini": _PYTHON_PROFILE}

    discover_calls: list[str] = []

    async def _fake_discover_extractor_statuses(
        driver: Any, *, project: str, profile: Any, registry: Any
    ) -> dict[str, ExtractorStatus]:
        discover_calls.append(project)
        # Both members: hotspot = NOT_ATTEMPTED
        return {"hotspot": ExtractorStatus("hotspot", "NOT_ATTEMPTED")}

    async def _fake_resolve_profile(driver: Any, slug: str, repo_path: Any = None) -> LanguageProfile:
        return profile_by_slug[slug]

    with (
        patch("palace_mcp.memory.bundle.bundle_members", new=AsyncMock(return_value=members)),
        patch("palace_mcp.audit.run.resolve_profile", new=_fake_resolve_profile),
        patch("palace_mcp.audit.run.discover_extractor_statuses", new=_fake_discover_extractor_statuses),
    ):
        result = await run_audit(drv, registry, bundle="uw-ios")

    assert result["ok"] is True
    # discover was called once per member
    assert sorted(discover_calls) == ["oz-v5-mini", "tron-kit"]


@pytest.mark.asyncio
async def test_bundle_mode_aggregates_failed_across_members() -> None:
    """RUN_FAILED for hotspot in member-A + OK in member-B → status_counts includes RUN_FAILED."""
    from palace_mcp.audit.run import run_audit

    drv = _make_empty_driver()
    registry = {"hotspot": _make_extractor("hotspot")}
    members = (_project_ref("member-a"), _project_ref("member-b"))

    async def _fake_discover(
        driver: Any, *, project: str, profile: Any, registry: Any
    ) -> dict[str, ExtractorStatus]:
        if project == "member-a":
            return {
                "hotspot": ExtractorStatus(
                    "hotspot", "RUN_FAILED", last_run_id="r-a", error_code="some_err"
                )
            }
        return {
            "hotspot": ExtractorStatus("hotspot", "OK", last_run_id="r-b")
        }

    with (
        patch("palace_mcp.memory.bundle.bundle_members", new=AsyncMock(return_value=members)),
        patch("palace_mcp.audit.run.resolve_profile", new=AsyncMock(return_value=_SWIFT_KIT_PROFILE)),
        patch("palace_mcp.audit.run.discover_extractor_statuses", new=_fake_discover),
    ):
        result = await run_audit(drv, registry, bundle="uw-ios")

    assert result["ok"] is True
    counts = result["status_counts"]
    assert counts.get("RUN_FAILED", 0) >= 1, f"Expected RUN_FAILED; got {counts}"
    assert counts.get("OK", 0) >= 1, f"Expected OK; got {counts}"


@pytest.mark.asyncio
async def test_single_project_mode_unchanged() -> None:
    """Single-project run_audit still returns flat status dict, no member keys."""
    from palace_mcp.audit.run import run_audit

    drv = _make_empty_driver()
    registry = {"hotspot": _make_extractor("hotspot")}
    profile = LanguageProfile("swift_kit", frozenset({"hotspot"}))

    statuses = {"hotspot": ExtractorStatus("hotspot", "NOT_ATTEMPTED")}

    with (
        patch("palace_mcp.audit.run.resolve_profile", new=AsyncMock(return_value=profile)),
        patch("palace_mcp.audit.run.discover_extractor_statuses", new=AsyncMock(return_value=statuses)),
    ):
        result = await run_audit(drv, registry, project="tron-kit")

    assert result["ok"] is True
    # blind_spots contains extractor names, NOT "slug/extractor" compound keys
    for name in result["blind_spots"]:
        assert "/" not in name, f"Expected flat key, got compound: {name!r}"
