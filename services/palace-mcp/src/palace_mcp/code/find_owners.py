"""palace.code.find_owners — top-N owners per file with empty-state diagnostics."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver
from palace_mcp.code_composite import _resolve_slug
from palace_mcp.memory.bundle import bundle_status

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

_QUERY_CYPHER = """
MATCH (f:File)
WHERE f.project_id IN $project_ids
  AND f.path = $path
OPTIONAL MATCH (st:OwnershipFileState {project_id: f.project_id, path: $path})
OPTIONAL MATCH (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
WITH f.project_id AS project_id, st, r, a
ORDER BY project_id ASC, r.weight DESC
WITH project_id, st, collect({r: r, a: a}) AS pairs
RETURN project_id,
       st.status           AS status,
       st.no_owners_reason AS reason,
       st.last_run_id      AS last_run_id,
       pairs
ORDER BY project_id ASC
"""

_CHECKPOINTS_CYPHER = """
UNWIND $project_ids AS project_id
OPTIONAL MATCH (c:OwnershipCheckpoint {project_id: project_id})
RETURN project_id,
       c.last_head_sha AS head_sha,
       c.last_completed_at AS completed_at
ORDER BY project_id ASC
"""

_RUN_LOOKUP_CYPHER = """
UNWIND $run_ids AS run_id
MATCH (r:IngestRun {run_id: run_id})
RETURN run_id, r.alpha_used AS alpha
"""


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message": message}


async def find_owners(
    driver: AsyncDriver,
    *,
    file_path: str,
    project: str | None = None,
    bundle: str | None = None,
    top_n: int = 5,
) -> dict[str, Any]:
    if not (1 <= top_n <= 100):
        return _err("top_n_out_of_range", f"top_n={top_n} not in [1, 100]")
    if project and bundle:
        return _err("mutually_exclusive_args", "specify project= OR bundle=, not both")
    if not project and not bundle:
        return _err("missing_target", "specify project= or bundle=")
    if project and not _SLUG_RE.match(project):
        return _err("slug_invalid", f"invalid slug: {project!r}")

    target_slug = project or bundle
    assert target_slug is not None
    resolution = await _resolve_slug(driver, target_slug)
    health: Any | None = None
    project_slugs: list[str]
    if project is not None:
        if resolution.kind != "project":
            return _err("project_not_registered", f"unknown project: {project!r}")
        project_slugs = [project]
    else:
        assert bundle is not None
        if resolution.kind != "bundle":
            return _err("bundle_not_registered", f"unknown bundle: {bundle!r}")
        if not resolution.member_slugs:
            return _err("bundle_has_no_members", f"bundle {bundle!r} has zero members")
        project_slugs = list(resolution.member_slugs)
        health = await bundle_status(driver, bundle=bundle)

    project_ids = [f"project/{slug}" for slug in project_slugs]
    checkpoints = await _checkpoints_by_project_id(driver, project_ids)
    if project is not None and project_ids[0] not in checkpoints:
        return _err(
            "ownership_not_indexed_yet",
            f"run code_ownership extractor for project {project!r} first",
        )

    rows = await _owner_rows(driver, project_ids=project_ids, file_path=file_path)
    if bundle is not None:
        for row in rows:
            if row["project_id"] in checkpoints:
                continue
            member_project = row["project_id"].removeprefix("project/")
            return {
                "ok": False,
                "error_code": "ownership_not_indexed_yet",
                "message": (
                    "run code_ownership extractor for member project "
                    f"{member_project!r} first"
                ),
                "member_project": member_project,
            }
    run_alphas = await _alpha_by_run_id(
        driver, [row["last_run_id"] for row in rows if row["last_run_id"]]
    )
    if project is not None:
        if not rows:
            return _err("unknown_file", f"no :File at {file_path!r} in {project!r}")
        return _project_payload(
            row=rows[0],
            file_path=file_path,
            project_slug=project,
            checkpoint=checkpoints.get(project_ids[0]),
            alpha=run_alphas.get(rows[0]["last_run_id"]),
            top_n=top_n,
        )

    assert bundle is not None
    assert health is not None
    result = [
        _bundle_payload(
            row=row,
            file_path=file_path,
            member_project=row["project_id"].removeprefix("project/"),
            checkpoint=checkpoints.get(row["project_id"]),
            alpha=run_alphas.get(row["last_run_id"]),
            top_n=top_n,
        )
        for row in rows
    ]
    out: dict[str, Any] = {
        "ok": True,
        "mode": "bundle",
        "target_slug": bundle,
        "bundle_health": health.model_dump(mode="json"),
        "result": result,
    }
    if not result:
        out["warning"] = "path_not_found_in_any_member"
    return out


async def _owner_rows(
    driver: AsyncDriver,
    *,
    project_ids: list[str],
    file_path: str,
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            _QUERY_CYPHER, project_ids=project_ids, path=file_path
        )
        return [dict(row) for row in await result.data()]


async def _checkpoints_by_project_id(
    driver: AsyncDriver, project_ids: list[str]
) -> dict[str, dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(_CHECKPOINTS_CYPHER, project_ids=project_ids)
        rows = await result.data()
    return {
        row["project_id"]: {
            "head_sha": row["head_sha"],
            "completed_at": row["completed_at"],
        }
        for row in rows
        if row["head_sha"] is not None or row["completed_at"] is not None
    }


async def _alpha_by_run_id(
    driver: AsyncDriver, run_ids: list[str]
) -> dict[str, Any | None]:
    if not run_ids:
        return {}
    async with driver.session() as session:
        result = await session.run(_RUN_LOOKUP_CYPHER, run_ids=run_ids)
        rows = await result.data()
    return {row["run_id"]: row["alpha"] for row in rows}


def _project_payload(
    *,
    row: dict[str, Any],
    file_path: str,
    project_slug: str,
    checkpoint: dict[str, Any] | None,
    alpha: Any | None,
    top_n: int,
) -> dict[str, Any]:
    payload = _base_payload(
        row=row,
        file_path=file_path,
        checkpoint=checkpoint,
        alpha=alpha,
        top_n=top_n,
    )
    return {"ok": True, "project": project_slug, **payload}


def _bundle_payload(
    *,
    row: dict[str, Any],
    file_path: str,
    member_project: str,
    checkpoint: dict[str, Any] | None,
    alpha: Any | None,
    top_n: int,
) -> dict[str, Any]:
    return {
        "member_project": member_project,
        **_base_payload(
            row=row,
            file_path=file_path,
            checkpoint=checkpoint,
            alpha=alpha,
            top_n=top_n,
        ),
    }


def _base_payload(
    *,
    row: dict[str, Any],
    file_path: str,
    checkpoint: dict[str, Any] | None,
    alpha: Any | None,
    top_n: int,
) -> dict[str, Any]:
    pairs = row["pairs"] or []
    real_pairs = [p for p in pairs if p["r"] is not None and p["a"] is not None]

    last_run_id = row["last_run_id"]
    head_sha = checkpoint["head_sha"] if checkpoint else None
    last_run_at_cp = checkpoint["completed_at"] if checkpoint else None

    if not real_pairs:
        if row["status"] is None:
            no_owners_reason = "file_not_yet_processed"
            last_run_id_resp: str | None = None
        else:
            no_owners_reason = row["reason"]
            last_run_id_resp = last_run_id

        return {
            "file_path": file_path,
            "owners": [],
            "total_authors": 0,
            "no_owners_reason": no_owners_reason,
            "last_run_id": last_run_id_resp,
            "last_run_at": _iso(last_run_at_cp),
            "head_sha": head_sha,
            "alpha_used": alpha,
        }

    real_pairs.sort(key=lambda p: p["r"]["weight"], reverse=True)
    owners = []
    for p in real_pairs[:top_n]:
        r = p["r"]
        a = p["a"]
        owners.append(
            {
                "author_email": a["email"] or a["identity_key"],
                "author_name": a["name"],
                "weight": r["weight"],
                "blame_share": r["blame_share"],
                "recency_churn_share": r["recency_churn_share"],
                "last_touched_at": _iso(r["last_touched_at"]),
                "lines_attributed": r["lines_attributed"],
                "commit_count": r["commit_count"],
                "canonical_via": r["canonical_via"],
            }
        )

    return {
        "file_path": file_path,
        "owners": owners,
        "total_authors": len(real_pairs),
        "no_owners_reason": None,
        "last_run_id": last_run_id,
        "last_run_at": _iso(last_run_at_cp),
        "head_sha": head_sha,
        "alpha_used": alpha,
    }


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return str(v.isoformat())
    if hasattr(v, "to_native"):
        native = v.to_native()
        if native.tzinfo is None:
            native = native.replace(tzinfo=timezone.utc)
        return str(native.isoformat())
    if isinstance(v, str):
        return v
    return str(v)
