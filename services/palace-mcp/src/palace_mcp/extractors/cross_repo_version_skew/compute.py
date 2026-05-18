"""Single source of truth for skew detection.

Used by both the extractor (Phase 2-3) and the MCP tool. Per spec rev2
SF3, no other module in `cross_repo_version_skew/` (or anywhere else)
runs the aggregation Cypher — enforced by source-grep regression test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from neo4j import AsyncDriver

from palace_mcp.extractors.cross_repo_version_skew.models import (
    SkewEntry,
    SkewGroup,
    WarningEntry,
)
from palace_mcp.extractors.cross_repo_version_skew.purl_parser import (
    purl_root_for_display,
)
from palace_mcp.extractors.cross_repo_version_skew.semver_classify import (
    max_pairwise_severity,
)

Mode = Literal["project", "bundle"]


@dataclass(frozen=True)
class ComputeResult:
    skew_groups: list[SkewGroup]
    aligned_groups_total: int
    warnings: list[WarningEntry]


_PROJECT_MODE_CYPHER = """
MATCH (p:Project {slug: $slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WHERE d.purl STARTS WITH 'pkg:'
  AND d.resolved_version IS NOT NULL
  AND ($ecosystem IS NULL OR d.ecosystem = $ecosystem)
RETURN d.purl                         AS purl,
       d.ecosystem                    AS ecosystem,
       d.resolved_version             AS version,
       r.declared_in                  AS scope_id,
       r.declared_in                  AS declared_in,
       r.declared_version_constraint  AS declared_constraint
ORDER BY d.purl, scope_id
"""

_BUNDLE_MODE_CYPHER = """
UNWIND $member_slugs AS slug
MATCH (p:Project {slug: slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WHERE d.purl STARTS WITH 'pkg:'
  AND d.resolved_version IS NOT NULL
  AND ($ecosystem IS NULL OR d.ecosystem = $ecosystem)
RETURN d.purl                         AS purl,
       d.ecosystem                    AS ecosystem,
       d.resolved_version             AS version,
       p.slug                         AS scope_id,
       r.declared_in                  AS declared_in,
       r.declared_version_constraint  AS declared_constraint
ORDER BY d.purl, scope_id
"""

_MALFORMED_DIAGNOSTIC_CYPHER = """
MATCH (p:Project)-[:DEPENDS_ON]->(d:ExternalDependency)
WHERE NOT d.purl STARTS WITH 'pkg:'
  AND p.slug IN $target_slugs
RETURN count(*) AS malformed_count
"""


async def _compute_skew_groups(
    driver: AsyncDriver,
    *,
    mode: Mode,
    member_slugs: Sequence[str],
    ecosystem: str | None,
) -> ComputeResult:
    """Aggregate :DEPENDS_ON over targets; group by purl_root; classify.

    The result includes only true-skew groups (>=2 distinct versions).
    Aligned groups (single-version) are counted but not returned as
    SkewGroup; the caller (MCP tool) emits them only on opt-in.
    """
    if mode == "project":
        if len(member_slugs) != 1:
            raise ValueError(
                f"project mode expects exactly 1 member; got {len(member_slugs)}"
            )
        params: dict[str, Any] = {"slug": member_slugs[0], "ecosystem": ecosystem}
        cypher = _PROJECT_MODE_CYPHER
    else:
        params = {"member_slugs": list(member_slugs), "ecosystem": ecosystem}
        cypher = _BUNDLE_MODE_CYPHER

    rows: list[dict[str, Any]] = []
    async with driver.session() as session:
        result = await session.run(cypher, **params)
        async for record in result:
            rows.append(
                {
                    "purl": record["purl"],
                    "ecosystem": record["ecosystem"],
                    "version": record["version"],
                    "scope_id": record["scope_id"],
                    "declared_in": record["declared_in"],
                    "declared_constraint": record["declared_constraint"],
                }
            )

    # Group by (purl_root, ecosystem); each group accumulates entries
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        purl_root = purl_root_for_display(row["purl"])
        key = (purl_root, row["ecosystem"])
        by_group.setdefault(key, []).append(row)

    skew_groups: list[SkewGroup] = []
    aligned_groups_total = 0
    for (purl_root, ecosystem_value), group_rows in by_group.items():
        distinct_versions = sorted({r["version"] for r in group_rows})
        if len(distinct_versions) < 2:
            # Aligned (or single-source). Single-source has 1 entry; >=2 entries
            # with same version is true alignment.
            if len(group_rows) >= 2:
                aligned_groups_total += 1
            continue
        severity = max_pairwise_severity(distinct_versions)
        entries = tuple(
            SkewEntry(
                scope_id=r["scope_id"],
                version=r["version"],
                declared_in=r["declared_in"],
                declared_constraint=r["declared_constraint"] or "",
            )
            for r in group_rows
        )
        skew_groups.append(
            SkewGroup(
                purl_root=purl_root,
                ecosystem=ecosystem_value,
                severity=severity,
                version_count=len(distinct_versions),
                entries=entries,
            )
        )

    # Diagnostic: count malformed purls (those missing pkg: prefix) that
    # would have been ignored above.
    target_slugs = list(member_slugs)
    warnings: list[WarningEntry] = []
    async with driver.session() as session:
        diag = await session.run(
            _MALFORMED_DIAGNOSTIC_CYPHER, target_slugs=target_slugs
        )
        diag_row = await diag.single()
    malformed_count = diag_row["malformed_count"] if diag_row else 0
    if malformed_count > 0:
        warnings.append(
            WarningEntry(
                code="purl_malformed",
                slug=None,
                message=f"{malformed_count} :ExternalDependency rows lacked 'pkg:' prefix; excluded from skew",
            )
        )

    return ComputeResult(
        skew_groups=skew_groups,
        aligned_groups_total=aligned_groups_total,
        warnings=warnings,
    )
