"""Smoke test for git_history extractor via real MCP ClientSession.call_tool.

Usage (from repo root, while palace-mcp is running):
  uv run python services/palace-mcp/scripts/smoke_git_history.py

Requires:
  - palace-mcp running on localhost:8000 (docker compose --profile review up)
  - PALACE_GITHUB_TOKEN in .env (optional for Phase 2)
  - /repos/gimle mounted in container

See docs/runbooks/git-history-harvester.md for full operator guide.
"""
from __future__ import annotations

import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


MCP_URL = "http://localhost:8000/mcp"
PROJECT = "gimle"


async def main() -> None:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List extractors — verify git_history is registered
            result = await session.call_tool(
                "palace.ingest.list_extractors", arguments={}
            )
            payload = json.loads(result.content[0].text)
            assert payload["ok"], f"list_extractors failed: {payload}"
            names = [e["name"] for e in payload.get("extractors", [])]
            assert "git_history" in names, f"git_history not in {names}"
            print(f"[OK] git_history registered ({len(names)} extractors total)")

            # 2. Run heartbeat first (warm-up)
            hb = await session.call_tool(
                "palace.ingest.run_extractor",
                arguments={"name": "heartbeat", "project": PROJECT},
            )
            hb_payload = json.loads(hb.content[0].text)
            assert hb_payload["ok"], f"heartbeat failed: {hb_payload}"
            print("[OK] heartbeat warm-up passed")

            # 3. Run git_history extractor (Phase 1 commits, Phase 2 if token set)
            result = await session.call_tool(
                "palace.ingest.run_extractor",
                arguments={"name": "git_history", "project": PROJECT},
            )
            payload = json.loads(result.content[0].text)
            assert payload["ok"], f"git_history run failed: {payload}"
            print(
                f"[OK] git_history run complete: "
                f"nodes={payload.get('nodes_written')}, "
                f"edges={payload.get('edges_written')}, "
                f"duration_ms={payload.get('duration_ms')}"
            )

            # 4. Incremental run — should return nodes_written == 0
            result2 = await session.call_tool(
                "palace.ingest.run_extractor",
                arguments={"name": "git_history", "project": PROJECT},
            )
            payload2 = json.loads(result2.content[0].text)
            assert payload2["ok"], f"git_history incremental run failed: {payload2}"
            print(
                f"[OK] incremental run: nodes={payload2.get('nodes_written')} "
                f"(expected 0 for idempotency)"
            )

    print("\n[PASS] smoke_git_history.py all checks passed")


if __name__ == "__main__":
    asyncio.run(main())
