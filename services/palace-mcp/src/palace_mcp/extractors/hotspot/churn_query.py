from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

CHURN_CYPHER = """
UNWIND $paths AS path
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.file_path, f.path) = path
OPTIONAL MATCH (c:Commit)-[:TOUCHED]->(f)
WHERE c.committed_at >= datetime($cutoff)
  AND c.committed_at <= datetime($as_of)
RETURN path, count(c) AS churn
""".strip()


async def fetch_churn(
    driver: Any,
    *,
    project_id: str,
    paths: list[str],
    window_days: int,
    as_of: datetime,
) -> dict[str, int]:
    if not paths:
        return {}
    cutoff = (as_of - timedelta(days=window_days)).isoformat()
    out: dict[str, int] = {p: 0 for p in paths}
    async with driver.session() as session:
        result = await session.run(
            CHURN_CYPHER,
            {
                "project_id": project_id,
                "paths": paths,
                "cutoff": cutoff,
                "as_of": as_of.isoformat(),
            },
        )
        async for record in result:
            out[record["path"]] = int(record["churn"])
    return out
