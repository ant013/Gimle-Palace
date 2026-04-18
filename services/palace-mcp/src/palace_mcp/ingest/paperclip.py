"""CLI entrypoint: python -m palace_mcp.ingest.paperclip"""

from __future__ import annotations

import argparse
import asyncio
import sys

from palace_mcp.config import IngestSettings
from palace_mcp.graphiti_client import build_graphiti
from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.runner import run_ingest
from palace_mcp.memory.logging_setup import configure_json_logging


async def _amain(args: argparse.Namespace) -> int:
    configure_json_logging()

    settings = IngestSettings()
    base_url = args.paperclip_url or settings.paperclip_api_url
    token = settings.paperclip_ingest_api_key.get_secret_value()
    company_id = args.company_id or settings.paperclip_company_id

    graphiti = build_graphiti(settings)
    try:
        async with PaperclipClient(
            base_url=base_url, token=token, company_id=company_id
        ) as client:
            result = await run_ingest(client=client, graphiti=graphiti)
        return 0 if not result["errors"] else 1
    finally:
        await graphiti.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="palace-mcp-ingest-paperclip")
    parser.add_argument(
        "--paperclip-url", default=None, help="Default: $PAPERCLIP_API_URL"
    )
    parser.add_argument(
        "--company-id", default=None, help="Default: $PAPERCLIP_COMPANY_ID"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
