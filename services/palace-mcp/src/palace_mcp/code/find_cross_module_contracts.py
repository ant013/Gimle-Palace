"""palace.code.find_cross_module_contracts — list cross-module contract drift records."""

from __future__ import annotations

from typing import Any

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (d:ModuleContractDelta {project: $project})
RETURN d.consumer_module_name AS consumer_module,
       d.producer_module_name AS producer_module,
       d.language AS language,
       d.from_commit_sha AS from_commit,
       d.to_commit_sha AS to_commit,
       d.removed_consumed_symbol_count AS removed_count,
       d.added_consumed_symbol_count AS added_count,
       d.signature_changed_consumed_symbol_count AS signature_changed_count,
       d.affected_use_count AS affected_use_count
ORDER BY d.to_commit_sha DESC, d.consumer_module_name
LIMIT $limit
""".strip()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def find_cross_module_contracts(
    *,
    driver: Any,
    project: str,
    limit: int = 200,
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
            )
    return {"ok": True, "project": project, "result": rows}
