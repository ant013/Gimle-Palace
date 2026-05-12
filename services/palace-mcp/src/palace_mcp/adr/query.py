"""ADR query — Cypher-only keyword + section + project search (GIM-274).

AD-D6: Cypher-only (body_excerpt CONTAINS). No Tantivy — ADR corpus is
small (tens of documents); full-text ranking not needed.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

# Base query — returns all active ADRs with their sections
_QUERY_BASE = """
MATCH (d:AdrDocument)-[:HAS_SECTION]->(s:AdrSection)
WHERE d.status <> 'superseded'
  AND ($keyword IS NULL OR s.body_excerpt CONTAINS $keyword)
  AND ($section_filter IS NULL OR s.section_name = $section_filter)
  AND ($project_filter IS NULL OR d.slug STARTS WITH $project_filter)
RETURN d.slug AS slug, s.section_name AS section_name, s.body_excerpt AS body_excerpt
ORDER BY d.slug, s.section_name
LIMIT 200
"""


async def query_adrs(
    keyword: str | None,
    section_filter: str | None,
    project_filter: str | None,
    driver: AsyncDriver,
) -> dict[str, Any]:
    """Graph-based keyword + section + project-prefix search across ADRs."""
    async with driver.session() as session:
        result = await session.run(
            _QUERY_BASE,
            keyword=keyword,
            section_filter=section_filter,
            project_filter=project_filter,
        )
        rows = await result.values()

    items = [
        {"slug": row[0], "section_name": row[1], "body_excerpt": row[2]} for row in rows
    ]
    logger.debug(
        "adr.query keyword=%r section=%r project=%r hits=%d",
        keyword,
        section_filter,
        project_filter,
        len(items),
    )
    return {"ok": True, "results": items, "count": len(items)}
