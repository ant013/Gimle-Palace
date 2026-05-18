"""ADR writer — idempotent section upsert for palace.code.manage_adr write mode.

AD-D9: file lock via fcntl.flock (stdlib advisory lock, no third-party filelock).
"""

from __future__ import annotations

import asyncio
import fcntl
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

_EMPTY_ADR_TEMPLATE = """\
# {title}

## PURPOSE

## STACK

## ARCHITECTURE

## PATTERNS

## TRADEOFFS

## PHILOSOPHY
"""

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
  d.updated_at   = datetime(),
  d.source_path  = $source_path
"""


async def write_adr(
    slug: str,
    section: str,
    body: str,
    decision_id: str | None,
    base_dir: Path,
    driver: AsyncDriver,
) -> dict[str, Any]:
    """Idempotently upsert a named section in an ADR file + graph."""
    try:
        validate_slug(slug)
    except ValueError as exc:
        return {"ok": False, "error_code": "invalid_slug", "message": str(exc)}

    if section not in CANONICAL_SECTIONS:
        return {
            "ok": False,
            "error_code": "invalid_section",
            "message": (
                f"Section {section!r} is not canonical. "
                f"Valid sections: {', '.join(CANONICAL_SECTIONS)}"
            ),
        }

    new_hash = body_hash_for(body)
    path = base_dir / f"{slug}.md"

    # All file I/O (including flock) runs in a thread to avoid blocking the event loop.
    was_modified = await asyncio.to_thread(
        _write_section_to_file, path, slug, section, body, new_hash
    )

    source_path = f"docs/postulates/{slug}.md"
    title = slug  # derive title from slug; first write uses slug as title
    async with driver.session() as session:
        await session.run(_UPSERT_DOC, slug=slug, title=title, source_path=source_path)
        await session.run(
            CYPHER_UPSERT_SECTION,
            slug=slug,
            section_name=section,
            body_hash=new_hash,
            body_excerpt=body[:500],
        )

    if decision_id is not None:
        from palace_mcp.adr.decision_bridge import create_cited_by_edge

        bridge_result = await create_cited_by_edge(
            decision_id=decision_id, slug=slug, driver=driver
        )
        if not bridge_result["ok"]:
            return bridge_result

    logger.info(
        "adr.writer.write slug=%s section=%s modified=%s", slug, section, was_modified
    )
    return {
        "ok": True,
        "slug": slug,
        "section": section,
        "body_hash": new_hash,
        "modified": was_modified,
    }


def _write_section_to_file(
    path: Path, slug: str, section: str, body: str, new_hash: str
) -> bool:
    """Acquire flock, read existing content, splice section, write back. Returns True if modified."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("")  # create empty file without updating existing mtime

    with open(path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            existing = f.read()
            if not existing.strip():
                existing = _EMPTY_ADR_TEMPLATE.format(title=slug)

            new_content, changed = _splice_section(existing, section, body, new_hash)
            if changed:
                f.seek(0)
                f.write(new_content)
                f.truncate()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return changed


def _splice_section(
    content: str, section_name: str, body: str, new_hash: str
) -> tuple[str, bool]:
    """Replace the body of `section_name` in markdown content. Returns (new_content, changed).

    Idempotency: if the section already has the same body_hash in the ORIGINAL content,
    return (content, False) so the file mtime is unchanged.
    """
    from palace_mcp.adr.reader import _parse_adr_file

    # Check if original content already has the same body
    _, existing_sections = _parse_adr_file(content)
    for sec in existing_sections:
        if sec["name"] == section_name:
            if body_hash_for(sec["body"]) == new_hash:
                return content, False  # already up to date — no write needed
            break

    # Body differs (or section absent) — rebuild with new body
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    in_target = False
    replaced = False

    for line in lines:
        stripped = line.strip()
        if stripped == f"## {section_name}":
            in_target = True
            out.append(line)
        elif stripped.startswith("## ") and in_target:
            if not replaced:
                out.append("\n" + body + "\n\n")
                replaced = True
            in_target = False
            out.append(line)
        elif not in_target:
            out.append(line)
        # else: skip existing body lines of the target section

    if in_target and not replaced:
        out.append("\n" + body + "\n")

    return "".join(out), True
