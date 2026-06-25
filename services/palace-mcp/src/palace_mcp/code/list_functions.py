from __future__ import annotations

from typing import Any

from palace_mcp.code_composite import _resolve_slug
from palace_mcp.memory.bundle import bundle_status

_QUERY = """
MATCH (f:File)-[:CONTAINS]->(fn:Function)
WHERE f.project_id IN $project_ids
  AND coalesce(f.file_path, f.path) = $path
  AND coalesce(fn.file_path, fn.path) = $path
  AND ($include_deprecated OR NOT f:Deprecated)
  AND fn.ccn >= $min_ccn
RETURN f.project_id AS project_id,
       fn.name AS name,
       fn.start_line AS start_line,
       fn.end_line AS end_line,
       fn.ccn AS ccn,
       fn.parameter_count AS parameter_count,
       fn.nloc AS nloc,
       fn.language AS language
ORDER BY fn.ccn DESC, fn.start_line ASC
""".strip()

# Fallback when the hotspot extractor has not produced :Function nodes for this file
# (e.g. an incremental analyze skipped hotspot, or hotspot has not run yet). The symbol
# layer still has the functions, so list them — without complexity metrics (ccn/nloc).
_FALLBACK_QUERY = """
MATCH (s:Symbol)
WHERE s.project_id IN $project_ids
  AND coalesce(s.file_path, s.path) = $path
  AND s.kind IN ['function', 'method', 'constructor', 'initializer', 'init']
  AND ($include_deprecated OR NOT s:Deprecated)
RETURN s.project_id AS project_id,
       coalesce(s.short_name, s.name) AS name,
       s.line_start AS start_line,
       s.kind AS kind
ORDER BY coalesce(s.line_start, 0) ASC
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


async def list_functions(
    *,
    driver: Any,
    path: str,
    project: str | None = None,
    bundle: str | None = None,
    min_ccn: int = 0,
    include_deprecated: bool = False,
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
                "path": path,
                "min_ccn": int(min_ccn),
                "include_deprecated": include_deprecated,
            },
        )
        async for rec in result:
            rows.append(
                {
                    "project_id": rec["project_id"].removeprefix("project/"),
                    "name": rec["name"],
                    "start_line": rec["start_line"],
                    "end_line": rec["end_line"],
                    "ccn": rec["ccn"],
                    "parameter_count": rec["parameter_count"],
                    "nloc": rec["nloc"],
                    "language": rec["language"],
                }
            )

    # Fallback to the symbol layer when hotspot produced no :Function nodes for this
    # file (skipped by incremental analyze, or not yet run). min_ccn is ignored here —
    # complexity metrics are unavailable. Keeps list_functions usable on the always-
    # present symbol layer instead of returning an empty result.
    used_symbol_fallback = False
    if not rows:
        async with driver.session() as session:
            fb = await session.run(
                _FALLBACK_QUERY,
                {
                    "project_ids": project_ids,
                    "path": path,
                    "include_deprecated": include_deprecated,
                },
            )
            async for rec in fb:
                rows.append(
                    {
                        "project_id": rec["project_id"].removeprefix("project/"),
                        "name": rec["name"],
                        "start_line": rec["start_line"],
                        "end_line": None,
                        "ccn": None,
                        "parameter_count": None,
                        "nloc": None,
                        "language": None,
                        "kind": rec["kind"],
                    }
                )
        used_symbol_fallback = bool(rows)

    _fallback_warning = (
        "complexity unavailable (ccn/nloc/end_line null) — hotspot has not produced "
        ":Function nodes for this file; run palace.ingest.run_extractor("
        "name='hotspot', project=...) to populate complexity"
    )

    if bundle is not None:
        assert health is not None
        out: dict[str, Any] = {
            "ok": True,
            "mode": "bundle",
            "target_slug": bundle,
            "bundle_health": health.model_dump(mode="json"),
            "result": rows,
        }
        if not rows:
            out["warning"] = "path_not_found_in_any_member"
        elif used_symbol_fallback:
            out["source"] = "symbol_fallback"
            out["warning"] = _fallback_warning
        return out
    for row in rows:
        row.pop("project_id", None)
    out_proj: dict[str, Any] = {"ok": True, "result": rows}
    if used_symbol_fallback:
        out_proj["source"] = "symbol_fallback"
        out_proj["warning"] = _fallback_warning
    return out_proj
