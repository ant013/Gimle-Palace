"""CLI entrypoint: python -m palace_mcp.ingest.paperclip"""

from __future__ import annotations

import argparse
import asyncio
import sys

from neo4j import AsyncGraphDatabase

from palace_mcp.config import IngestSettings
from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.runner import run_ingest
from palace_mcp.memory.constraints import ensure_schema
from palace_mcp.memory.logging_setup import configure_json_logging


async def _amain(args: argparse.Namespace) -> int:
    configure_json_logging()

    # Pattern #6: read config via IngestSettings (explicit defaults, SecretStr masking).
    settings = IngestSettings()
    base_url = args.paperclip_url or settings.paperclip_api_url
    token = settings.paperclip_ingest_api_key.get_secret_value()
    company_id = args.company_id or settings.paperclip_company_id
    neo4j_uri = settings.neo4j_uri
    neo4j_password = settings.neo4j_password.get_secret_value()

    default_slug = settings.palace_default_group_id.removeprefix("project/")
    project_slug = args.project_slug or default_slug
    group_id = f"project/{project_slug}"

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", neo4j_password))
    try:
        await ensure_schema(driver, default_group_id=settings.palace_default_group_id)
        async with PaperclipClient(
            base_url=base_url, token=token, company_id=company_id
        ) as client:
            result = await run_ingest(
                client=client,
                driver=driver,
                group_id=group_id,
            )
        return 0 if not result["errors"] else 1
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="palace-mcp-ingest-paperclip")
    parser.add_argument(
        "--paperclip-url", default=None, help="Default: $PAPERCLIP_API_URL"
    )
    parser.add_argument(
        "--company-id", default=None, help="Default: $PAPERCLIP_COMPANY_ID"
    )
    parser.add_argument(
        "--project-slug",
        default=None,
        help="Project slug to ingest into. Default: slug of $PALACE_DEFAULT_GROUP_ID",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
