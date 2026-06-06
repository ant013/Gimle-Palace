"""palace.code.find_public_api — list public API symbols for a project or bundle."""

from __future__ import annotations

from typing import Any

from palace_mcp.code_composite import _resolve_slug
from palace_mcp.memory.bundle import bundle_status

_QUERY = """
MATCH (surface:PublicApiSurface)-[:EXPORTS]->(sym:PublicApiSymbol)
WHERE surface.project IN $projects
  AND sym.project IN $projects
RETURN sym.project AS member_project,
       surface.module_name AS module_name,
       sym.fqn AS fqn,
       sym.display_name AS display_name,
       sym.kind AS kind,
       sym.visibility AS visibility,
       sym.commit_sha AS commit_sha,
       sym.signature AS signature,
       sym.language AS language
ORDER BY sym.project, surface.module_name, sym.fqn
LIMIT $limit
""".strip()


def _error(
    code: str,
    message: str,
    *,
    project: str | None = None,
    bundle: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    if bundle is not None:
        out["bundle"] = bundle
    return out


async def find_public_api(
    *,
    driver: Any,
    project: str | None = None,
    bundle: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    if project and bundle:
        return _error(
            "mutually_exclusive_args",
            "specify project= OR bundle=, not both",
        )
    if not project and not bundle:
        return _error("missing_target", "specify project= or bundle=")

    target_slug = project or bundle
    assert target_slug is not None
    resolution = await _resolve_slug(driver, target_slug)
    health: Any | None = None
    project_slugs: list[str]
    if project is not None:
        if resolution.kind != "project":
            return _error(
                "project_not_registered",
                f"no :Project {{slug: {project!r}}}",
                project=project,
            )
        project_slugs = [project]
    else:
        assert bundle is not None
        if resolution.kind != "bundle":
            return _error(
                "bundle_not_registered",
                f"unknown bundle: {bundle!r}",
                bundle=bundle,
            )
        if not resolution.member_slugs:
            return _error(
                "bundle_has_no_members",
                f"bundle {bundle!r} has zero members",
                bundle=bundle,
            )
        project_slugs = list(resolution.member_slugs)
        health = await bundle_status(driver, bundle=bundle)

    rows: list[dict[str, Any]] = []
    async with driver.session() as sess:
        result = await sess.run(_QUERY, projects=project_slugs, limit=int(limit))
        async for rec in result:
            row = {
                "module_name": rec["module_name"],
                "fqn": rec["fqn"],
                "display_name": rec["display_name"],
                "kind": rec["kind"],
                "visibility": rec["visibility"],
                "language": rec["language"],
                "commit_sha": rec["commit_sha"],
                "signature": rec["signature"],
            }
            if bundle is not None:
                row["member_project"] = rec["member_project"]
            rows.append(row)
    if project is not None:
        return {"ok": True, "project": project, "result": rows}

    assert bundle is not None
    assert health is not None
    return {
        "ok": True,
        "mode": "bundle",
        "target_slug": bundle,
        "bundle_health": health.model_dump(mode="json"),
        "result": rows,
    }
