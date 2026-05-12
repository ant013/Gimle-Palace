"""ADR supersede — marks old ADR as superseded by new one (GIM-274).

AD-D3: one-way only (no re-revival). file-level banner + graph SUPERSEDED_BY edge.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.adr.models import validate_slug

logger = logging.getLogger(__name__)

_BANNER_PREFIX = "**SUPERSEDED by"

_SET_OLD_SUPERSEDED = """
MERGE (old:AdrDocument {slug: $old_slug})
SET old.status = 'superseded', old.updated_at = datetime()
"""

_ENSURE_NEW_ACTIVE = """
MERGE (new:AdrDocument {slug: $new_slug})
ON CREATE SET
  new.title       = $new_slug,
  new.status      = 'active',
  new.created_at  = datetime(),
  new.updated_at  = datetime(),
  new.head_sha    = 'unknown',
  new.source_path = $new_source_path
ON MATCH SET
  new.status      = 'active',
  new.updated_at  = datetime()
"""

_MERGE_SUPERSEDED_BY = """
MATCH (old:AdrDocument {slug: $old_slug})
MATCH (new:AdrDocument {slug: $new_slug})
MERGE (old)-[r:SUPERSEDED_BY]->(new)
ON CREATE SET r.reason = $reason, r.ts = datetime()
"""


async def supersede_adr(
    old_slug: str,
    new_slug: str,
    reason: str,
    base_dir: Path,
    driver: AsyncDriver,
) -> dict[str, Any]:
    """Mark old_slug as superseded by new_slug."""
    for slug in (old_slug, new_slug):
        try:
            validate_slug(slug)
        except ValueError as exc:
            return {"ok": False, "error_code": "invalid_slug", "message": str(exc)}

    old_path = base_dir / f"{old_slug}.md"
    if not old_path.exists():
        return {
            "ok": False,
            "error_code": "adr_not_found",
            "message": f"Old ADR {old_slug!r} not found; cannot supersede a non-existent ADR",
        }

    # Add banner to old file (idempotent — skip if already present)
    await asyncio.to_thread(_add_supersede_banner, old_path, new_slug, reason)

    new_source_path = f"docs/postulates/{new_slug}.md"
    async with driver.session() as session:
        await session.run(_SET_OLD_SUPERSEDED, old_slug=old_slug)
        await session.run(
            _ENSURE_NEW_ACTIVE, new_slug=new_slug, new_source_path=new_source_path
        )
        await session.run(
            _MERGE_SUPERSEDED_BY, old_slug=old_slug, new_slug=new_slug, reason=reason
        )

    logger.info("adr.supersede old=%s new=%s reason=%r", old_slug, new_slug, reason)
    return {"ok": True, "old_slug": old_slug, "new_slug": new_slug}


def _add_supersede_banner(path: Path, new_slug: str, reason: str) -> None:
    """Prepend supersede banner to file if not already present (idempotent)."""
    with open(path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            content = f.read()
            if _BANNER_PREFIX in content:
                return  # already marked
            banner = f"{_BANNER_PREFIX} {new_slug}** — {reason}\n\n"
            f.seek(0)
            f.write(banner + content)
            f.truncate()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
