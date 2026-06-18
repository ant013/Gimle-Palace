"""palace.code.find_dead_symbols — list dead symbol candidates for a project."""

from __future__ import annotations

from typing import Any

from palace_mcp.pagination import pagination_envelope

_GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p LIMIT 1"
_DEPENDENCY_MARKERS = (
    "SourcePackages/",
    "checkouts/",
    "Pods/",
    "Carthage/",
    ".build/",
    ".swiftpm/",
)

_FILTER = """
WHERE $include_dependencies
   OR NOT any(
       marker IN $dependency_markers
       WHERE coalesce(c.source_file, '') CONTAINS marker
   )
""".strip()

_COUNT_QUERY = f"""
MATCH (c:DeadSymbolCandidate {{project: $project}})
{_FILTER}
RETURN count(c) AS total
""".strip()

_QUERY = f"""
MATCH (c:DeadSymbolCandidate {{project: $project}})
{_FILTER}
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
SKIP $offset
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
    include_dependencies: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    page_limit = max(int(limit), 0)
    page_offset = max(int(offset), 0)
    async with driver.session() as sess:
        row = await (await sess.run(_GET_PROJECT, slug=project)).single()
    if row is None:
        return _error(
            "project_not_registered", f"no :Project {{slug: {project!r}}}", project
        )
    rows: list[dict[str, Any]] = []
    async with driver.session() as sess:
        count_row = await (
            await sess.run(
                _COUNT_QUERY,
                project=project,
                include_dependencies=include_dependencies,
                dependency_markers=_DEPENDENCY_MARKERS,
            )
        ).single()
        total = int(count_row["total"]) if count_row is not None else 0
        result = await sess.run(
            _QUERY,
            project=project,
            include_dependencies=include_dependencies,
            dependency_markers=_DEPENDENCY_MARKERS,
            offset=page_offset,
            limit=page_limit,
        )
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
    return {
        "ok": True,
        "project": project,
        "result": rows,
        **pagination_envelope(total=total, returned=len(rows), offset=page_offset),
    }
