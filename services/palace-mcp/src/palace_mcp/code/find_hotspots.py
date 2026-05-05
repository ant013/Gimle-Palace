from __future__ import annotations

from typing import Any

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.hotspot_score, 0.0) >= $min_score
  AND coalesce(f.complexity_status, 'stale') = 'fresh'
RETURN f.path AS path,
       f.ccn_total AS ccn_total,
       f.churn_count AS churn_count,
       f.hotspot_score AS hotspot_score,
       f.last_complexity_run_at AS computed_at,
       f.complexity_window_days AS window_days
ORDER BY f.hotspot_score DESC
LIMIT $top_n
""".strip()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def find_hotspots(
    *,
    driver: Any,
    project: str,
    top_n: int = 20,
    min_score: float = 0.0,
) -> dict[str, Any]:
    async with driver.session() as sess:
        row = await (await sess.run(_GET_PROJECT, slug=project)).single()
    if row is None:
        return _error("project_not_registered", f"no :Project {{slug: {project!r}}}", project)
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(
            _QUERY,
            {"project_id": project, "top_n": int(top_n), "min_score": float(min_score)},
        )
        async for rec in result:
            rows.append({
                "path": rec["path"],
                "ccn_total": rec["ccn_total"],
                "churn_count": rec["churn_count"],
                "hotspot_score": rec["hotspot_score"],
                "computed_at": rec["computed_at"].iso_format()
                    if rec["computed_at"] is not None else None,
                "window_days": rec["window_days"],
            })
    return {"ok": True, "result": rows}
