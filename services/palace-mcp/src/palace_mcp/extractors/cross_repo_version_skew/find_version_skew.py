"""palace.code.find_version_skew — live MCP tool over the skew graph.

Rev3: imports SLUG_RE + WarningEntry from models.py (W8 — no regex duplication;
W11 — emit member_invalid_slug warnings in bundle path, not silent drop).
Contains register_version_skew_tools() called from mcp_server.py.
"""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.cross_repo_version_skew.compute import (
    _compute_skew_groups,
)
from palace_mcp.extractors.cross_repo_version_skew.models import (
    SLUG_RE,
    EcosystemEnum,
    WarningEntry,
)
from palace_mcp.extractors.cross_repo_version_skew.semver_classify import (
    severity_rank,
)

_VALID_SEVERITIES = {"patch", "minor", "major", "unknown"}
_VALID_ECOSYSTEMS = {e.value for e in EcosystemEnum}


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message": message}


async def find_version_skew(
    driver: AsyncDriver,
    *,
    project: str | None = None,
    bundle: str | None = None,
    ecosystem: str | None = None,
    min_severity: str | None = None,
    top_n: int = 50,
    include_aligned: bool = False,
) -> dict[str, Any]:
    # 1. Validate top_n + slugs + filters (pre-DB)
    if not (1 <= top_n < 10_000):
        return _err("top_n_out_of_range", f"top_n={top_n} not in [1, 9999]")
    if project and bundle:
        return _err("mutually_exclusive_args", "specify project= OR bundle=, not both")
    if not project and not bundle:
        return _err("missing_target", "specify project= or bundle=")
    if project and not SLUG_RE.match(project):
        return _err("slug_invalid", f"invalid project slug: {project!r}")
    if bundle and not SLUG_RE.match(bundle):
        return _err("bundle_invalid", f"invalid bundle slug: {bundle!r}")
    if min_severity is not None and min_severity not in _VALID_SEVERITIES:
        return _err(
            "invalid_severity_filter",
            f"min_severity={min_severity!r} not in {_VALID_SEVERITIES}",
        )
    if ecosystem is not None and ecosystem not in _VALID_ECOSYSTEMS:
        return _err(
            "invalid_ecosystem_filter",
            f"ecosystem={ecosystem!r} not in {_VALID_ECOSYSTEMS}",
        )

    target_slug = project or bundle
    mode = "project" if project else "bundle"

    # 2. Resolve targets + check registration
    pre_warnings: list[WarningEntry] = []
    if mode == "project":
        assert project is not None
        proj_exists = await _project_exists(driver, project)
        if not proj_exists:
            return _err("project_not_registered", f"unknown project: {project!r}")
        members: list[str] = [project]
        target_status = await _collect_target_status(driver, [project])
    else:
        assert bundle is not None
        bundle_exists = await _bundle_exists(driver, bundle)
        if not bundle_exists:
            return _err("bundle_not_registered", f"unknown bundle: {bundle!r}")
        raw_members = await _bundle_members(driver, bundle)
        if not raw_members:
            return _err("bundle_has_no_members", f"bundle {bundle!r} has zero members")
        members = []
        for m in raw_members:
            if SLUG_RE.match(m):
                members.append(m)
            else:
                pre_warnings.append(
                    WarningEntry(
                        code="member_invalid_slug",
                        slug=m,
                        message=f"member {m!r} fails slug regex; excluded from query",
                    )
                )
        target_status = await _collect_target_status(driver, members)
        for w in pre_warnings:
            if w.slug is not None:
                target_status[w.slug] = "invalid_slug"

    indexed_count = sum(1 for s in target_status.values() if s == "indexed")
    if indexed_count == 0:
        return _err(
            "dependency_surface_not_indexed", "no targets have :DEPENDS_ON data"
        )

    # 3. Compute (live)
    result = await _compute_skew_groups(
        driver,
        mode=mode,  # type: ignore[arg-type]
        member_slugs=members,
        ecosystem=ecosystem,
    )
    groups = list(result.skew_groups)

    # 4. Apply min_severity filter
    if min_severity is not None:
        threshold = severity_rank(min_severity)  # type: ignore[arg-type]
        groups = [g for g in groups if severity_rank(g.severity) >= threshold]

    # 5. Sort: severity desc, version_count desc, purl_root asc
    groups = sorted(
        groups,
        key=lambda g: (-severity_rank(g.severity), -g.version_count, g.purl_root),
    )

    total_skew_groups = len(result.skew_groups)
    summary_by_severity = {
        "major": sum(1 for g in result.skew_groups if g.severity == "major"),
        "minor": sum(1 for g in result.skew_groups if g.severity == "minor"),
        "patch": sum(1 for g in result.skew_groups if g.severity == "patch"),
        "unknown": sum(1 for g in result.skew_groups if g.severity == "unknown"),
    }

    # 6. Aligned-groups inclusion: v1 exposes only the count; full
    #    surfacing of aligned purl_roots when include_aligned=True is a followup.
    aligned_groups_total = result.aligned_groups_total

    return {
        "ok": True,
        "mode": mode,
        "target_slug": target_slug,
        "skew_groups": [
            {
                "purl_root": g.purl_root,
                "ecosystem": g.ecosystem,
                "severity": g.severity,
                "version_count": g.version_count,
                "entries": [
                    {
                        "scope_id": e.scope_id,
                        "version": e.version,
                        "declared_in": e.declared_in,
                        "declared_constraint": e.declared_constraint,
                    }
                    for e in g.entries
                ],
            }
            for g in groups[:top_n]
        ],
        "total_skew_groups": total_skew_groups,
        "summary_by_severity": summary_by_severity,
        "aligned_groups_total": aligned_groups_total,
        "target_status": target_status,
        "warnings": [w.model_dump() for w in pre_warnings + list(result.warnings)],
    }


async def _project_exists(driver: AsyncDriver, slug: str) -> bool:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:Project {slug: $slug}) RETURN count(p) AS n", slug=slug
        )
        row = await result.single()
    return row is not None and row["n"] > 0


async def _bundle_exists(driver: AsyncDriver, name: str) -> bool:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (b:Bundle {name: $name}) RETURN count(b) AS n", name=name
        )
        row = await result.single()
    return row is not None and row["n"] > 0


async def _bundle_members(driver: AsyncDriver, name: str) -> list[str]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (b:Bundle {name: $name})-[:HAS_MEMBER]->(p:Project) RETURN p.slug AS slug",
            name=name,
        )
        return [r["slug"] for r in await result.data()]


def register_version_skew_tools(tool_decorator: Any, default_project: str) -> None:
    """Register palace.code.find_version_skew as an MCP tool.

    Called from mcp_server.py alongside register_code_composite_tools().
    """

    @tool_decorator(  # type: ignore[untyped-decorator]
        name="palace.code.find_version_skew",
        description=(
            "Cross-repo / cross-bundle version skew detection over external "
            "dependencies. Reports purl_roots that have multiple distinct "
            "resolved_versions across modules (project mode) or members "
            "(bundle mode). Read-only; uses GIM-191 dependency_surface graph."
        ),
    )
    async def palace_code_find_version_skew(
        project: str | None = None,
        bundle: str | None = None,
        ecosystem: str | None = None,
        min_severity: str | None = None,
        top_n: int = 50,
        include_aligned: bool = False,
    ) -> dict[str, Any]:
        from palace_mcp.mcp_server import get_driver

        drv = get_driver()
        if drv is None:
            return {
                "ok": False,
                "error_code": "driver_not_initialized",
                "message": "Neo4j driver not available",
            }
        return await find_version_skew(
            driver=drv,
            project=project,
            bundle=bundle,
            ecosystem=ecosystem,
            min_severity=min_severity,
            top_n=top_n,
            include_aligned=include_aligned,
        )


async def _collect_target_status(
    driver: AsyncDriver, slugs: list[str]
) -> dict[str, str]:
    if not slugs:
        return {}
    async with driver.session() as session:
        result = await session.run(
            """
            UNWIND $slugs AS slug
            OPTIONAL MATCH (p:Project {slug: slug})
            OPTIONAL MATCH (p)-[r:DEPENDS_ON]->()
            RETURN slug AS s, p IS NOT NULL AS exists, count(r) AS dep_count
            """,
            slugs=slugs,
        )
        rows = await result.data()
    status: dict[str, str] = {}
    for r in rows:
        if not r["exists"]:
            status[r["s"]] = "not_registered"
        elif r["dep_count"] == 0:
            status[r["s"]] = "not_indexed"
        else:
            status[r["s"]] = "indexed"
    return status
