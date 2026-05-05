from __future__ import annotations

from typing import Any

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (f:File {project_id: $project_id, path: $path})-[:CONTAINS]->(fn:Function)
WHERE fn.ccn >= $min_ccn
RETURN fn.name AS name,
       fn.start_line AS start_line,
       fn.end_line AS end_line,
       fn.ccn AS ccn,
       fn.parameter_count AS parameter_count,
       fn.nloc AS nloc,
       fn.language AS language
ORDER BY fn.ccn DESC, fn.start_line ASC
""".strip()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def list_functions(
    *,
    driver: Any,
    project: str,
    path: str,
    min_ccn: int = 0,
) -> dict[str, Any]:
    async with driver.session() as sess:
        row = await (await sess.run(_GET_PROJECT, slug=project)).single()
    if row is None:
        return _error("project_not_registered", f"no :Project {{slug: {project!r}}}", project)
    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(
            _QUERY,
            {"project_id": project, "path": path, "min_ccn": int(min_ccn)},
        )
        async for rec in result:
            rows.append({k: rec[k] for k in (
                "name", "start_line", "end_line", "ccn",
                "parameter_count", "nloc", "language",
            )})
    return {"ok": True, "result": rows}
