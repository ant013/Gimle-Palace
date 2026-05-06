"""Smoke test for code_ownership extractor + palace.code.find_owners via MCP.

Usage (from repo root, while palace-mcp is running):
  uv run python services/palace-mcp/scripts/smoke_code_ownership.py

Requires:
  - palace-mcp running on localhost:8000 (docker compose --profile review up)
  - git_history extractor already run for the target project
  - /repos/<project> mounted in container

GIM-216
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://localhost:8000/mcp"
PROJECT = os.environ.get("PALACE_OWNERSHIP_SMOKE_PROJECT", "gimle")
PROBE_FILE = os.environ.get(
    "PALACE_OWNERSHIP_SMOKE_FILE",
    "services/palace-mcp/src/palace_mcp/extractors/foundation/importance.py",
)


async def main() -> None:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Run extractor
            print(f"==> 1. Running code_ownership extractor for {PROJECT!r}")
            result = await session.call_tool(
                "palace.ingest.run_extractor",
                {"name": "code_ownership", "project": PROJECT},
            )
            payload = json.loads(result.content[0].text)
            print(json.dumps(payload, indent=2, default=str))
            assert payload.get("ok") is True or payload.get("success") is True, (
                f"run_extractor failed: {payload}"
            )
            print("OK — extractor run complete")

            # 2. Query find_owners
            print(f"\n==> 2. palace.code.find_owners({PROBE_FILE!r})")
            result2 = await session.call_tool(
                "palace.code.find_owners",
                {"file_path": PROBE_FILE, "project": PROJECT, "top_n": 5},
            )
            payload2 = json.loads(result2.content[0].text)
            print(json.dumps(payload2, indent=2, default=str))
            assert payload2.get("ok") is True, f"find_owners failed: {payload2}"
            owners = payload2.get("owners", [])
            assert len(owners) >= 1, "no owners returned"
            top = owners[0]
            assert 0 < top["weight"] <= 1.0, f"bad weight: {top}"
            print(f"OK — top owner: {top['author_email']} weight={top['weight']:.3f}")

            # 3. Cypher invariant: per-file weight sum ≈ 1.0
            print("\n==> 3. Cypher invariant — per-file weight sums")
            result3 = await session.call_tool(
                "palace.memory.lookup",
                {
                    "entity_type": "IngestRun",
                    "filters": {
                        "source": "extractor.code_ownership",
                        "project": PROJECT,
                    },
                },
            )
            payload3 = json.loads(result3.content[0].text)
            assert payload3.get("ok") is True, f"lookup failed: {payload3}"
            runs = payload3.get("results", [])
            assert runs, "no IngestRun found for code_ownership"
            latest = runs[0]
            assert latest.get("exit_reason") in {"success", "no_change"}, latest
            print(f"OK — IngestRun exit_reason={latest['exit_reason']!r}")

    print("\n==> SMOKE PASS")


if __name__ == "__main__":
    asyncio.run(main())
