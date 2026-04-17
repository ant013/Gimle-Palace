"""CLI entrypoint: python -m palace_mcp.ingest.paperclip"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from neo4j import AsyncGraphDatabase

from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.runner import run_ingest
from palace_mcp.memory.constraints import ensure_constraints
from palace_mcp.memory.logging_setup import configure_json_logging


async def _amain(args: argparse.Namespace) -> int:
    configure_json_logging()

    base_url = args.paperclip_url or os.environ["PAPERCLIP_API_URL"]
    token = os.environ["PAPERCLIP_INGEST_API_KEY"]
    company_id = args.company_id or os.environ["PAPERCLIP_COMPANY_ID"]
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    neo4j_password = os.environ["NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password))
    try:
        await ensure_constraints(driver)
        async with PaperclipClient(base_url=base_url, token=token, company_id=company_id) as client:
            result = await run_ingest(client=client, driver=driver)
        return 0 if not result["errors"] else 1
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="palace-mcp-ingest-paperclip")
    parser.add_argument("--paperclip-url", default=None, help="Default: $PAPERCLIP_API_URL")
    parser.add_argument("--company-id", default=None, help="Default: $PAPERCLIP_COMPANY_ID")
    args = parser.parse_args()
    sys.exit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
