"""Thin MCP JSON-RPC client for operator scripts (GIM-182 §4).

Calls palace-mcp tools via the streamable-HTTP transport endpoint.
Used by register-uw-ios-bundle.sh (via Python subprocess) and smoke_uw_ios_bundle.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx

PALACE_MCP_URL = os.environ.get("PALACE_MCP_URL", "http://localhost:8080/mcp")
_TIMEOUT = httpx.Timeout(60.0)
_RPC_ID = 0


def _next_id() -> int:
    global _RPC_ID
    _RPC_ID += 1
    return _RPC_ID


async def call_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call a palace-mcp MCP tool and return the parsed result."""
    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            PALACE_MCP_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        body = resp.json()

    if "error" in body:
        err = body["error"]
        raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")

    content = body.get("result", {}).get("content", [])
    for item in content:
        if item.get("type") == "text":
            return json.loads(item["text"])

    return body.get("result", {})


def call_tool_sync(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Synchronous wrapper around call_tool."""
    return asyncio.run(call_tool(tool, args))


if __name__ == "__main__":
    # CLI usage: python _mcp_client.py palace.memory.register_bundle '{"name":"uw-ios","description":"..."}'
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <tool-name> <json-args>", file=sys.stderr)
        sys.exit(1)
    tool_name = sys.argv[1]
    tool_args = json.loads(sys.argv[2])
    result = call_tool_sync(tool_name, tool_args)
    print(json.dumps(result, indent=2, default=str))
    if not result.get("ok", True):
        sys.exit(1)
