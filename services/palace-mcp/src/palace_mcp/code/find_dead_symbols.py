"""palace.code.find_dead_symbols — list dead symbol candidates for a project."""

from __future__ import annotations

from typing import Any

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"

_QUERY = """
MATCH (c:DeadSymbolCandidate {project: $project})
RETURN c.id AS id,
       c.display_name AS display_name,
       c.kind AS kind,
       c.module_name AS module_name,
       c.language AS language,
       c.candidate_state AS candidate_state,
       c.confidence AS confidence,
       c.source_file AS source_file,
       c.source_line AS source_line,
       c.commit_sha AS commit_sha,
       c.evidence_source AS evidence_source
ORDER BY c.module_name, c.display_name
LIMIT $limit
""".strip()


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


async def find_dead_symbols(
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
                    "id": rec["id"],
                    "display_name": rec["display_name"],
                    "kind": rec["kind"],
                    "module_name": rec["module_name"],
                    "language": rec["language"],
                    "candidate_state": rec["candidate_state"],
                    "confidence": rec["confidence"],
                    "source_file": rec["source_file"],
                    "source_line": rec["source_line"],
                    "commit_sha": rec["commit_sha"],
                    "evidence_source": rec["evidence_source"],
                }
            )
    return {"ok": True, "project": project, "result": rows}
