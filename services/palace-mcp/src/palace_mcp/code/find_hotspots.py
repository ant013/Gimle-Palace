from __future__ import annotations

from typing import Any

from palace_mcp.code_composite import _resolve_slug
from palace_mcp.memory.bundle import bundle_status

_QUERY = """
MATCH (f:File)
WHERE coalesce(f.hotspot_score, 0.0) >= $min_score
  AND f.project_id IN $project_ids
  AND coalesce(f.complexity_status, 'stale') = 'fresh'
  AND ($include_deprecated OR NOT f:Deprecated)
  AND (
    $path_prefix IS NULL
    OR coalesce(f.file_path, f.path) STARTS WITH $path_prefix
  )
RETURN f.project_id AS project_id,
       coalesce(f.file_path, f.path) AS path,
       f.ccn_total AS ccn_total,
       f.churn_count AS churn_count,
       f.hotspot_score AS hotspot_score,
       f.last_complexity_run_at AS computed_at,
       f.complexity_window_days AS window_days
ORDER BY f.hotspot_score DESC
LIMIT $top_n
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


async def find_hotspots(
    *,
    driver: Any,
    project: str | None = None,
    bundle: str | None = None,
    top_n: int = 20,
    min_score: float = 0.0,
    path_prefix: str | None = None,
    include_deprecated: bool = True,
) -> dict[str, Any]:
    if project and bundle:
        return _error(
            "mutually_exclusive_args",
            "specify project= OR bundle=, not both",
            project=project,
            bundle=bundle,
        )
    if not project and not bundle:
        return _error("missing_target", "specify project= or bundle=")

    target_slug = project or bundle
    assert target_slug is not None
    resolution = await _resolve_slug(driver, target_slug)
    project_ids: list[str]
    health: Any | None = None
    if project is not None:
        if resolution.kind != "project":
            return _error(
                "project_not_registered",
                f"no :Project {{slug: {project!r}}}",
                project=project,
            )
        project_ids = [f"project/{project}"]
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
        project_ids = [f"project/{slug}" for slug in resolution.member_slugs]
        health = await bundle_status(driver, bundle=bundle)

    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(
            _QUERY,
            {
                "project_ids": project_ids,
                "top_n": int(top_n),
                "min_score": float(min_score),
                "path_prefix": path_prefix,
                "include_deprecated": include_deprecated,
            },
        )
        async for rec in result:
            rows.append(
                {
                    "project_id": rec["project_id"].removeprefix("project/"),
                    "path": rec["path"],
                    "ccn_total": rec["ccn_total"],
                    "churn_count": rec["churn_count"],
                    "hotspot_score": rec["hotspot_score"],
                    "computed_at": rec["computed_at"].iso_format()
                    if rec["computed_at"] is not None
                    else None,
                    "window_days": rec["window_days"],
                }
            )
    if bundle is not None:
        assert health is not None
        return {
            "ok": True,
            "mode": "bundle",
            "target_slug": bundle,
            "bundle_health": health.model_dump(mode="json"),
            "result": rows,
        }
    for row in rows:
        row.pop("project_id", None)
    return {"ok": True, "result": rows}
