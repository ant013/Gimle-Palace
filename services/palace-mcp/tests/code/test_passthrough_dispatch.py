from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from palace_mcp.code.native_detect_changes import FALLBACK_TO_CM
from palace_mcp.code_router import PassthroughEntry, _dispatch_passthrough


@pytest.fixture(autouse=True)
def _patch_namespace_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_resolve_namespace(_driver: object, value: str) -> SimpleNamespace:
        if value == "totally-bogus":
            raise ValueError(value)
        slug = value.removeprefix("repos-") if value.startswith("repos-") else value
        cm_project_name = value if value.startswith("repos-") else f"repos-{value}"
        return SimpleNamespace(slug=slug, cm_project_name=cm_project_name)

    monkeypatch.setattr(
        "palace_mcp.code_router.resolve_namespace", _fake_resolve_namespace
    )
    monkeypatch.setattr("palace_mcp.mcp_server.get_driver", lambda: object())


@pytest.mark.asyncio
async def test_native_known_project_takes_precedence(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _native(**_: object) -> dict[str, object]:
        return {"ok": True, "source": "native"}

    cm_call = AsyncMock(return_value={"ok": True, "source": "cm"})
    monkeypatch.setattr("palace_mcp.code_router._call_cm_tool", cm_call)

    with caplog.at_level(logging.INFO, logger="palace_mcp.code_router"):
        result = await _dispatch_passthrough(
            "detect_changes",
            PassthroughEntry("detect", native_handler=_native),
            {"project": "gimle"},
        )

    assert result == {"ok": True, "source": "native"}
    cm_call.assert_not_awaited()
    assert caplog.records[-1].message == "passthrough.dispatch"
    assert caplog.records[-1].decision == "native"


@pytest.mark.asyncio
async def test_native_fallback_to_cm_invokes_cm_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _native(**_: object) -> object:
        return FALLBACK_TO_CM

    monkeypatch.setattr("palace_mcp.code_router._cm_session", object())
    cm_call = AsyncMock(return_value={"ok": True, "source": "cm"})
    monkeypatch.setattr("palace_mcp.code_router._call_cm_tool", cm_call)

    with caplog.at_level(logging.INFO, logger="palace_mcp.code_router"):
        result = await _dispatch_passthrough(
            "detect_changes",
            PassthroughEntry("detect", native_handler=_native),
            {"project": "gimle"},
        )

    assert result == {"ok": True, "source": "cm"}
    cm_call.assert_awaited_once_with("detect_changes", {"project": "repos-gimle"})
    assert caplog.records[-1].decision == "cm"


@pytest.mark.asyncio
async def test_native_terminal_error_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _native(**_: object) -> dict[str, object]:
        return {"ok": False, "error_code": "invalid_since"}

    cm_call = AsyncMock(return_value={"ok": True, "source": "cm"})
    monkeypatch.setattr("palace_mcp.code_router._call_cm_tool", cm_call)

    with caplog.at_level(logging.INFO, logger="palace_mcp.code_router"):
        result = await _dispatch_passthrough(
            "detect_changes",
            PassthroughEntry("detect", native_handler=_native),
            {"project": "gimle"},
        )

    assert result == {"ok": False, "error_code": "invalid_since"}
    cm_call.assert_not_awaited()
    assert caplog.records[-1].decision == "native_error"


@pytest.mark.asyncio
async def test_search_code_without_cm_returns_phase2_required(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("palace_mcp.code_router._cm_session", None)

    with caplog.at_level(logging.INFO, logger="palace_mcp.code_router"):
        result = await _dispatch_passthrough(
            "search_code",
            PassthroughEntry("search", phase2_error_code="phase2_required"),
            {"project": "uw-ios-baseline", "pattern": "HD"},
        )

    assert result["error_code"] == "phase2_required"
    assert result["project"] == "uw-ios-baseline"
    assert caplog.records[-1].decision == "phase2_required"


@pytest.mark.asyncio
async def test_cm_only_tool_without_cm_returns_fallback_unavailable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("palace_mcp.code_router._cm_session", None)

    with caplog.at_level(logging.INFO, logger="palace_mcp.code_router"):
        result = await _dispatch_passthrough(
            "query_graph",
            PassthroughEntry("query"),
            {"query": "MATCH (n) RETURN n"},
        )

    assert result["error_code"] == "cm_fallback_unavailable"
    assert caplog.records[-1].decision == "cm_fallback_unavailable"
