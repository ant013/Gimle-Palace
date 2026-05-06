"""palace.code.find_owners — top-N owners per file with empty-state diagnostics."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncDriver

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

_QUERY_CYPHER = """
MATCH (f:File {project_id: $proj, path: $path})
OPTIONAL MATCH (st:OwnershipFileState {project_id: $proj, path: $path})
OPTIONAL MATCH (f)-[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
WITH f, st, r, a
ORDER BY r.weight DESC
WITH f, st, collect({r: r, a: a}) AS pairs
RETURN f IS NOT NULL AS file_exists,
       st.status           AS status,
       st.no_owners_reason AS reason,
       st.last_run_id      AS last_run_id,
       pairs
"""

_PROJECT_EXISTS_CYPHER = """
MATCH (p:Project {slug: $slug})
RETURN count(p) AS n
"""

_CHECKPOINT_EXISTS_CYPHER = """
MATCH (c:OwnershipCheckpoint {project_id: $slug})
RETURN c.last_head_sha AS head_sha,
       c.last_completed_at AS completed_at
"""

_RUN_LOOKUP_CYPHER = """
MATCH (r:IngestRun {run_id: $run_id})
RETURN r.alpha_used AS alpha
"""


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message": message}


async def find_owners(
    driver: AsyncDriver,
    *,
    file_path: str,
    project: str,
    top_n: int = 5,
) -> dict[str, Any]:
    if not _SLUG_RE.match(project):
        return _err("slug_invalid", f"invalid slug: {project!r}")
    if not (1 <= top_n <= 100):
        return _err("top_n_out_of_range", f"top_n={top_n} not in [1, 100]")

    async with driver.session() as session:
        proj_row = await (
            await session.run(_PROJECT_EXISTS_CYPHER, slug=project)
        ).single()
    if proj_row is None or proj_row["n"] == 0:
        return _err("project_not_registered", f"unknown project: {project!r}")

    async with driver.session() as session:
        cp_row = await (
            await session.run(_CHECKPOINT_EXISTS_CYPHER, slug=project)
        ).single()
    if cp_row is None:
        return _err(
            "ownership_not_indexed_yet",
            f"run code_ownership extractor for project {project!r} first",
        )

    head_sha = cp_row["head_sha"]
    last_run_at_cp = cp_row["completed_at"]

    async with driver.session() as session:
        result = await session.run(_QUERY_CYPHER, proj=project, path=file_path)
        row = await result.single()
    if row is None:
        return _err("unknown_file", f"no :File at {file_path!r} in {project!r}")

    pairs = row["pairs"] or []
    real_pairs = [p for p in pairs if p["r"] is not None and p["a"] is not None]

    last_run_id = row["last_run_id"]
    alpha = None
    if last_run_id:
        async with driver.session() as session:
            run_row = await (
                await session.run(_RUN_LOOKUP_CYPHER, run_id=last_run_id)
            ).single()
        if run_row:
            alpha = run_row["alpha"]

    if not real_pairs:
        if row["status"] is None:
            no_owners_reason = "file_not_yet_processed"
            last_run_id_resp: str | None = None
        else:
            no_owners_reason = row["reason"]
            last_run_id_resp = last_run_id

        return {
            "ok": True,
            "file_path": file_path,
            "project": project,
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
        "ok": True,
        "file_path": file_path,
        "project": project,
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
