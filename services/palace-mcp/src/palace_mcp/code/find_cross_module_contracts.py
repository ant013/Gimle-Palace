"""palace.code.find_cross_module_contracts — list cross-module contract drift records."""

from __future__ import annotations

from typing import Any

from palace_mcp.code_composite import _resolve_slug
from palace_mcp.memory.bundle import bundle_status


_QUERY = """
MATCH (d:ModuleContractDelta)
WHERE d.project IN $projects
RETURN d.project AS member_project,
       d.consumer_module_name AS consumer_module,
       d.producer_module_name AS producer_module,
       d.language AS language,
       d.from_commit_sha AS from_commit,
       d.to_commit_sha AS to_commit,
       d.removed_consumed_symbol_count AS removed_count,
       d.added_consumed_symbol_count AS added_count,
       d.signature_changed_consumed_symbol_count AS signature_changed_count,
       d.affected_use_count AS affected_use_count
ORDER BY d.to_commit_sha DESC, d.project, d.consumer_module_name
LIMIT $limit
""".strip()

_HAS_SNAPSHOTS = """
MATCH (snap:ModuleContractSnapshot)
WHERE snap.project IN $projects
RETURN count(snap) > 0 AS present
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


async def find_cross_module_contracts(
    *,
    driver: Any,
    project: str | None = None,
    bundle: str | None = None,
    limit: int = 200,
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
                "consumer_module": rec["consumer_module"],
                "producer_module": rec["producer_module"],
                "language": rec["language"],
                "from_commit": rec["from_commit"],
                "to_commit": rec["to_commit"],
                "removed_count": rec["removed_count"],
                "added_count": rec["added_count"],
                "signature_changed_count": rec["signature_changed_count"],
                "affected_use_count": rec["affected_use_count"],
            }
            if bundle is not None:
                row["member_project"] = rec["member_project"]
            rows.append(row)
        if not rows:
            snapshot_row = await (
                await sess.run(_HAS_SNAPSHOTS, projects=project_slugs)
            ).single()
            if not (snapshot_row and snapshot_row["present"]):
                return _error(
                    "not_extracted",
                    (
                        "no cross-module contract snapshot/delta records found; "
                        "run public_api_surface and cross_module_contract first"
                    ),
                    project=project,
                    bundle=bundle,
                )
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
