from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from palace_mcp.memory.schema import ProjectInfo


@pytest.mark.asyncio
async def test_register_project_passes_parent_mount_and_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp import mcp_server

    fake_driver = object()
    monkeypatch.setattr(mcp_server, "_driver", fake_driver)

    fake_register = AsyncMock(
        return_value=ProjectInfo(
            slug="evm-kit",
            name="evm-kit",
            tags=[],
            parent_mount="hs",
            relative_path="EvmKit.Swift",
        )
    )
    monkeypatch.setattr(mcp_server, "register_project", fake_register)

    result = await mcp_server.palace_memory_register_project(
        slug="evm-kit",
        name="evm-kit",
        parent_mount="hs",
        relative_path="EvmKit.Swift",
    )

    assert result["slug"] == "evm-kit"
    assert result["parent_mount"] == "hs"
    assert result["relative_path"] == "EvmKit.Swift"
    fake_register.assert_awaited_once_with(
        fake_driver,
        slug="evm-kit",
        name="evm-kit",
        tags=[],
        language=None,
        framework=None,
        repo_url=None,
        parent_mount="hs",
        relative_path="EvmKit.Swift",
        language_profile=None,
    )


@pytest.mark.asyncio
async def test_register_project_invalid_parent_mount_returns_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp import mcp_server

    monkeypatch.setattr(mcp_server, "_driver", object())

    async def fake_register_project(*args: object, **kwargs: object) -> ProjectInfo:
        raise ValueError("invalid parent_mount name: 'BAD'")

    monkeypatch.setattr(mcp_server, "register_project", fake_register_project)

    result = await mcp_server.palace_memory_register_project(
        slug="evm-kit",
        name="evm-kit",
        parent_mount="BAD",
    )

    assert result == {
        "ok": False,
        "error_code": "invalid_request",
        "message": "invalid parent_mount name: 'BAD'",
    }
