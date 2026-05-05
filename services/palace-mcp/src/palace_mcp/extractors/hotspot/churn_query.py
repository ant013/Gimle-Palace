from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

CHURN_CYPHER = """
UNWIND $paths AS path
MATCH (f:File {project_id: $project_id, path: path})
OPTIONAL MATCH (c:Commit)-[:TOUCHED]->(f)
WHERE c.committed_at >= datetime($cutoff)
RETURN path, count(c) AS churn
""".strip()


async def fetch_churn(
    driver: Any,
    *,
    project_id: str,
    paths: list[str],
    window_days: int,
    run_started_at: datetime,
) -> dict[str, int]:
    if not paths:
        return {}
    cutoff = (run_started_at - timedelta(days=window_days)).isoformat()
    out: dict[str, int] = {p: 0 for p in paths}
    async with driver.session() as session:
        result = await session.run(
            CHURN_CYPHER,
            {"project_id": project_id, "paths": paths, "cutoff": cutoff},
        )
        async for record in result:
            out[record["path"]] = int(record["churn"])
    return out
