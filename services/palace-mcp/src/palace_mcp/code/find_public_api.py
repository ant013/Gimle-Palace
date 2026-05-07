"""palace.code.find_public_api — list public API symbols for a project."""

from __future__ import annotations

from typing import Any

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (surface:PublicApiSurface {project: $project})
      -[:EXPORTS]->(sym:PublicApiSymbol {project: $project})
RETURN surface.module_name AS module_name,
       sym.fqn AS fqn,
       sym.display_name AS display_name,
       sym.kind AS kind,
       sym.visibility AS visibility,
       sym.commit_sha AS commit_sha,
       sym.signature AS signature,
       sym.language AS language
ORDER BY surface.module_name, sym.fqn
LIMIT $limit
""".strip()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def find_public_api(
    *,
    driver: Any,
    project: str,
    limit: int = 500,
) -> dict[str, Any]:
    async with driver.session() as sess:
        row = await (await sess.run(_GET_PROJECT, slug=project)).single()
    if row is None:
        return _error(
            "project_not_registered", f"no :Project {{slug: {project!r}}}", project
        )
    rows: list[dict[str, Any]] = []
    async with driver.session() as sess:
        result = await sess.run(_QUERY, project=project, limit=int(limit))
        async for rec in result:
            rows.append(
                {
                    "module_name": rec["module_name"],
                    "fqn": rec["fqn"],
                    "display_name": rec["display_name"],
                    "kind": rec["kind"],
                    "visibility": rec["visibility"],
                    "language": rec["language"],
                    "commit_sha": rec["commit_sha"],
                    "signature": rec["signature"],
                }
            )
    return {"ok": True, "project": project, "result": rows}
