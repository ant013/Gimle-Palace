from __future__ import annotations


def test_get_architecture_tool_has_native_handler() -> None:
    from palace_mcp.code_router import _PASSTHROUGH_TOOLS

    assert _PASSTHROUGH_TOOLS["get_architecture"].native_handler is not None
