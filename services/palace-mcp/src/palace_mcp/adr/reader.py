"""ADR reader — file-to-graph projection for palace.code.manage_adr read mode."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.adr.models import (
    CANONICAL_SECTIONS,
    CYPHER_UPSERT_SECTION,
    body_hash_for,
    validate_slug,
)

logger = logging.getLogger(__name__)


async def read_adr(
    slug: str,
    base_dir: Path,
    driver: AsyncDriver | None,
) -> dict[str, Any]:
    """Read an ADR file and project it to the graph. Returns MCP envelope."""
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"ok": False, "error_code": "invalid_slug", "message": str(exc)}

    path = base_dir / f"{slug}.md"
    if not path.exists():
        return {
            "ok": False,
            "error_code": "adr_not_found",
            "message": f"ADR {slug!r} not found at {path}",
        }

    content = await asyncio.to_thread(path.read_text)
    title, sections = _parse_adr_file(content)
    source_path = f"docs/postulates/{slug}.md"

    if driver is not None:
        await _project_to_graph(
            slug=slug,
            title=title,
            source_path=source_path,
            sections=sections,
            driver=driver,
        )

    return {
        "ok": True,
        "slug": slug,
        "title": title,
        "body": content,
        "sections": [s["name"] for s in sections],
    }


def _parse_adr_file(content: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse markdown ADR file → (title, [{name, body}]).

    Recognises lines starting with '# ' as the title and '## SECTION' as
    section headers. Only canonical section names are captured; unknown
    sub-headers are skipped.
    """
    lines = content.splitlines(keepends=True)
    title = ""
    sections: list[dict[str, Any]] = []
    current_section: str | None = None
    current_body: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
        elif stripped.startswith("## "):
            section_name = stripped[3:].strip()
            if current_section is not None:
                sections.append(
                    {"name": current_section, "body": "".join(current_body).strip()}
                )
            current_section = (
                section_name if section_name in CANONICAL_SECTIONS else None
            )
            current_body = []
        elif current_section is not None:
            current_body.append(line)

    if current_section is not None:
        sections.append(
            {"name": current_section, "body": "".join(current_body).strip()}
        )

    return title, sections


_UPSERT_DOC = """
MERGE (d:AdrDocument {slug: $slug})
ON CREATE SET
  d.title        = $title,
  d.status       = 'active',
  d.created_at   = datetime(),
  d.updated_at   = datetime(),
  d.head_sha     = 'unknown',
  d.source_path  = $source_path
ON MATCH SET
  d.title        = $title,
  d.updated_at   = datetime(),
  d.source_path  = $source_path
"""


async def _project_to_graph(
    slug: str,
    title: str,
    source_path: str,
    sections: list[dict[str, Any]],
    driver: AsyncDriver,
) -> None:
    async with driver.session() as session:
        await session.run(_UPSERT_DOC, slug=slug, title=title, source_path=source_path)
        for sec in sections:
            bh = body_hash_for(sec["body"])
            await session.run(
                CYPHER_UPSERT_SECTION,
                slug=slug,
                section_name=sec["name"],
                body_hash=bh,
                body_excerpt=sec["body"][:500],
            )
    logger.debug("adr.reader.projected slug=%s sections=%d", slug, len(sections))
