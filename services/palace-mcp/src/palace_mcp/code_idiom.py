"""palace.code.find_idiom MCP tool — query :Convention and :ConventionViolation nodes.

Read-only. Queries nodes written by the coding_convention extractor.
Returns {conventions, outlier_samples} structured response for a given kind pattern.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from palace_mcp.errors import handle_tool_error


_QUERY_CONVENTIONS = """
MATCH (c:Convention {project_id: $project_id})
WHERE c.kind CONTAINS $kind_pattern
AND ($module IS NULL OR c.module = $module)
RETURN c.module AS module,
       c.kind AS kind,
       c.dominant_choice AS dominant,
       c.confidence AS confidence,
       c.sample_count AS sample_count,
       c.outliers AS outliers,
       c.source_context AS source_context
ORDER BY c.module, c.kind
"""

_QUERY_VIOLATIONS = """
MATCH (v:ConventionViolation {project_id: $project_id})
WHERE v.kind CONTAINS $kind_pattern
AND ($module IS NULL OR v.module = $module)
RETURN v.module AS module,
       v.kind AS kind,
       v.file AS file,
       v.start_line AS start_line,
       v.end_line AS end_line,
       v.message AS message,
       v.severity AS severity
ORDER BY v.file, v.start_line
LIMIT $limit
"""

_QUERY_VIOLATIONS_COUNT = """
MATCH (v:ConventionViolation {project_id: $project_id})
WHERE v.kind CONTAINS $kind_pattern
AND ($module IS NULL OR v.module = $module)
RETURN count(v) AS total
"""

_DESC = (
    "Query coding conventions recorded by the coding_convention extractor. "
    "Returns dominant choice, confidence, and sample/outlier counts per module. "
    "kind is a substring pattern (e.g. 'idiom.collection_init'). "
    "Optionally filter by project and module."
)


class FindIdiomRequest(BaseModel):
    kind: str = Field(..., min_length=1, max_length=200)
    project: str | None = None
    module: str | None = None
    max_outliers: int = Field(20, ge=1, le=200)


def register_code_idiom_tools(
    tool_decorator: Any,
    default_project: str,
) -> None:
    """Register palace.code.find_idiom MCP tool."""

    @tool_decorator("palace.code.find_idiom", _DESC)  # type: ignore[untyped-decorator]
    async def palace_code_find_idiom(
        kind: str,
        project: str | None = None,
        module: str | None = None,
        max_outliers: int = 20,
        include_deprecated: bool = True,
    ) -> dict[str, Any]:
        from palace_mcp.mcp_server import get_driver

        driver = get_driver()
        if driver is None:
            handle_tool_error(RuntimeError("Neo4j driver not initialised"))
            raise  # unreachable

        try:
            req = FindIdiomRequest(
                kind=kind,
                project=project,
                module=module,
                max_outliers=max_outliers,
            )
        except ValidationError as e:
            return {
                "ok": False,
                "error_code": "validation_error",
                "kind": kind,
                "message": str(e),
            }

        resolved_project = (req.project or default_project).removeprefix("repos-")
        project_id = f"project/{resolved_project}"
        module_param = req.module  # None passes through to Cypher as NULL

        async with driver.session() as session:
            conv_result = await session.run(
                _QUERY_CONVENTIONS,
                project_id=project_id,
                kind_pattern=req.kind,
                module=module_param,
            )
            conv_records = await conv_result.data()

            if not conv_records:
                return {
                    "ok": False,
                    "error_code": "no_conventions_found",
                    "kind": req.kind,
                    "project": resolved_project,
                    "message": (
                        f"No :Convention nodes matching kind '{req.kind}' "
                        f"in project '{resolved_project}'"
                    ),
                }

            count_result = await session.run(
                _QUERY_VIOLATIONS_COUNT,
                project_id=project_id,
                kind_pattern=req.kind,
                module=module_param,
            )
            count_record = await count_result.single()
            total_outlier_samples = int(
                count_record["total"] if count_record is not None else 0
            )

            viol_result = await session.run(
                _QUERY_VIOLATIONS,
                project_id=project_id,
                kind_pattern=req.kind,
                module=module_param,
                limit=req.max_outliers,
            )
            viol_records = await viol_result.data()

        conventions = [
            {
                "module": r["module"],
                "kind": r["kind"],
                "dominant": r["dominant"],
                "confidence": r["confidence"],
                "sample_count": r["sample_count"],
                "outliers": r["outliers"],
                "source_context": r["source_context"],
            }
            for r in conv_records
        ]

        outlier_samples = [
            {
                "module": r["module"],
                "kind": r["kind"],
                "file": r["file"],
                "start_line": r["start_line"],
                "end_line": r["end_line"],
                "message": r["message"],
                "severity": r["severity"],
            }
            for r in viol_records
        ]

        return {
            "ok": True,
            "kind": req.kind,
            "project": resolved_project,
            "conventions": conventions,
            "outlier_samples": outlier_samples,
            "total_outlier_samples": total_outlier_samples,
            "truncated": total_outlier_samples > req.max_outliers,
        }
