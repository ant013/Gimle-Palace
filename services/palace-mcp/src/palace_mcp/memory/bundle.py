"""Bundle CRUD operations and health computation for palace-memory (GIM-182).

Namespace invariant: :Bundle.group_id = "bundle/<name>",
distinct from :Project.group_id = "project/<slug>".

All functions use Cypher parameters — never string interpolation.
Name/slug validation runs before any Cypher is issued.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import (
    CHECK_BUNDLE_NAME_EXISTS,
    CHECK_PROJECT_SLUG_EXISTS,
    COUNT_BUNDLE_MEMBERS,
    DELETE_BUNDLE_CASCADE,
    DELETE_BUNDLE_NO_CASCADE,
    GET_BUNDLE_MEMBERS,
    GET_BUNDLE_MEMBERS_WITH_INGEST,
    MERGE_BUNDLE_CONTAINS_PROJECT,
    UPSERT_BUNDLE,
)
from palace_mcp.memory.models import (
    Bundle,
    BundleStatus,
    IngestRunResult,
    ProjectRef,
    Tier,
)

__all__ = [
    "BundleNameConflictsWithProject",
    "BundleNonEmpty",
    "BundleNotFoundError",
    "ProjectSlugConflictsWithBundle",
    "add_to_bundle",
    "bundle_members",
    "bundle_status",
    "compute_bundle_health",
    "delete_bundle",
    "register_bundle",
]

logger = logging.getLogger(__name__)

_BUNDLE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
_FRESH_WINDOW = timedelta(days=7)


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class BundleNotFoundError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"bundle not found: {name!r}")
        self.name = name


class BundleNameConflictsWithProject(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"bundle name {name!r} conflicts with existing :Project slug")
        self.name = name


class ProjectSlugConflictsWithBundle(ValueError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"project slug {slug!r} conflicts with existing :Bundle name")
        self.slug = slug


class BundleNonEmpty(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"bundle {name!r} is non-empty; use cascade=True to force delete"
        )
        self.name = name


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_bundle_name(name: str) -> None:
    if not isinstance(name, str) or not _BUNDLE_NAME_RE.match(name):
        raise ValueError(f"invalid bundle name: {name!r}")


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_project_ref(row: dict[str, Any]) -> ProjectRef:
    return ProjectRef(
        slug=row["slug"],
        tier=Tier(row["tier"]),
        added_to_bundle_at=_parse_dt(row["added_at"]) or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Public CRUD functions
# ---------------------------------------------------------------------------


async def register_bundle(
    driver: AsyncDriver,
    *,
    name: str,
    description: str,
) -> Bundle:
    """Create a :Bundle node (spec §6.3). Raises on name conflicts."""
    _validate_bundle_name(name)

    async with driver.session() as session:
        # 1. Guard: no :Project with the same slug
        check_result = await session.run(CHECK_PROJECT_SLUG_EXISTS, slug=name)
        existing_project = await check_result.single()
        if existing_project is not None:
            raise BundleNameConflictsWithProject(name)

        # 2. MERGE bundle — constraint enforces uniqueness at DB level too
        now = datetime.now(timezone.utc).isoformat()
        upsert_result = await session.run(
            UPSERT_BUNDLE,
            name=name,
            description=description,
            created_at=now,
        )
        row = await upsert_result.single()

    assert row is not None, f"Bundle not returned after upsert: {name!r}"
    b = row["b"]
    return Bundle(
        name=b["name"],
        description=b["description"],
        group_id=b["group_id"],
        created_at=_parse_dt(b["created_at"]) or datetime.now(timezone.utc),
    )


async def add_to_bundle(
    driver: AsyncDriver,
    *,
    bundle: str,
    project: str,
    tier: Tier,
) -> None:
    """Add project to bundle with :CONTAINS edge (idempotent via MERGE)."""
    async with driver.session() as session:
        # 1. Verify bundle exists
        b_result = await session.run(CHECK_BUNDLE_NAME_EXISTS, name=bundle)
        b_row = await b_result.single()
        if b_row is None:
            raise BundleNotFoundError(bundle)

        # 2. Verify project exists
        p_result = await session.run(CHECK_PROJECT_SLUG_EXISTS, slug=project)
        p_row = await p_result.single()
        if p_row is None:
            from palace_mcp.memory.projects import UnknownProjectError

            raise UnknownProjectError(project)

        # 3. MERGE :CONTAINS edge — idempotent
        added_at = datetime.now(timezone.utc).isoformat()
        await session.run(
            MERGE_BUNDLE_CONTAINS_PROJECT,
            bundle=bundle,
            project=project,
            tier=tier.value,
            added_at=added_at,
        )
        logger.debug(
            "bundle_member_added_or_exists bundle=%s project=%s", bundle, project
        )


async def bundle_members(
    driver: AsyncDriver,
    *,
    bundle: str,
) -> tuple[ProjectRef, ...]:
    """Return sorted ProjectRef tuple for a bundle. Raises BundleNotFoundError."""
    async with driver.session() as session:
        # Check bundle exists first (raises on missing)
        b_result = await session.run(CHECK_BUNDLE_NAME_EXISTS, name=bundle)
        b_row = await b_result.single()
        if b_row is None:
            raise BundleNotFoundError(bundle)

        # Get members ordered by slug ASC
        m_result = await session.run(GET_BUNDLE_MEMBERS, bundle=bundle)
        refs: list[ProjectRef] = []
        async for row in m_result:
            refs.append(_row_to_project_ref(dict(row)))

    return tuple(refs)


async def bundle_status(
    driver: AsyncDriver,
    *,
    bundle: str,
) -> BundleStatus:
    """Return BundleStatus with health metrics and failure classification."""
    async with driver.session() as session:
        b_result = await session.run(CHECK_BUNDLE_NAME_EXISTS, name=bundle)
        b_row = await b_result.single()
        if b_row is None:
            raise BundleNotFoundError(bundle)

        m_result = await session.run(GET_BUNDLE_MEMBERS_WITH_INGEST, bundle=bundle)
        members: list[ProjectRef] = []
        last_runs: dict[str, IngestRunResult] = {}
        async for row in m_result:
            d = dict(row)
            ref = _row_to_project_ref(d)
            members.append(ref)
            completed_at = _parse_dt(d.get("last_run_completed_at"))
            last_run_ok = d.get("last_run_ok")
            if last_run_ok is not None or completed_at is not None:
                last_runs[ref.slug] = IngestRunResult(
                    slug=ref.slug,
                    ok=bool(last_run_ok),
                    run_id=None,
                    error_kind=None,
                    error=None,
                    duration_ms=0,
                    completed_at=completed_at,
                )

    return compute_bundle_health(
        bundle_name=bundle,
        members=tuple(members),
        last_runs=last_runs,
        query_time_failures=[],
    )


async def delete_bundle(
    driver: AsyncDriver,
    *,
    name: str,
    cascade: bool,
) -> None:
    """Delete a bundle.

    cascade=False: raises BundleNonEmpty if any :CONTAINS edges exist.
    cascade=True: DETACH DELETE bundle + all :CONTAINS edges (does NOT
    delete member :Project nodes).
    """
    async with driver.session() as session:
        b_result = await session.run(CHECK_BUNDLE_NAME_EXISTS, name=name)
        b_row = await b_result.single()
        if b_row is None:
            raise BundleNotFoundError(name)

        if cascade:
            await session.run(DELETE_BUNDLE_CASCADE, name=name)
            logger.info("bundle_deleted_cascade name=%s", name)
            return

        # cascade=False: check member count first
        count_result = await session.run(COUNT_BUNDLE_MEMBERS, name=name)
        count_row = await count_result.single()
        member_count = count_row["member_count"] if count_row else 0
        if member_count > 0:
            raise BundleNonEmpty(name)

        await session.run(DELETE_BUNDLE_NO_CASCADE, name=name)
        logger.info("bundle_deleted name=%s", name)


# ---------------------------------------------------------------------------
# Pure health computation (no I/O)
# ---------------------------------------------------------------------------


def compute_bundle_health(
    *,
    bundle_name: str,
    members: tuple[ProjectRef, ...],
    last_runs: dict[str, IngestRunResult],
    query_time_failures: list[str],
    as_of: datetime | None = None,
) -> BundleStatus:
    """Compute BundleStatus from member list + last ingest run results.

    Classifies each member into exactly one of:
    - fresh (success + completed within 7 days)
    - stale (success + completed > 7 days ago)
    - ingest_failed (ok=False — last run did not succeed)
    - never_ingested (absent from last_runs)
    """
    now_utc = as_of or datetime.now(timezone.utc)
    stale_slugs: list[str] = []
    ingest_failed_slugs: list[str] = []
    never_ingested_slugs: list[str] = []
    fresh_count = 0
    oldest: datetime | None = None
    newest: datetime | None = None

    for m in members:
        last_run = last_runs.get(m.slug)
        if last_run is None:
            never_ingested_slugs.append(m.slug)
            continue
        if not last_run.ok:
            ingest_failed_slugs.append(m.slug)
            continue
        # Successful ingest — classify by freshness
        completed = last_run.completed_at
        if completed is None:
            # Treat missing timestamp as stale
            stale_slugs.append(m.slug)
            continue
        if (now_utc - completed) < _FRESH_WINDOW:
            fresh_count += 1
        else:
            stale_slugs.append(m.slug)
        # Track min/max (spec rev2 fix)
        if oldest is None or completed < oldest:
            oldest = completed
        if newest is None or completed > newest:
            newest = completed

    return BundleStatus(
        name=bundle_name,
        members_total=len(members),
        members_fresh_within_7d=fresh_count,
        members_stale=len(stale_slugs),
        query_failed_slugs=tuple(sorted(set(query_time_failures))),
        ingest_failed_slugs=tuple(sorted(set(ingest_failed_slugs))),
        never_ingested_slugs=tuple(sorted(set(never_ingested_slugs))),
        stale_slugs=tuple(sorted(set(stale_slugs))),
        oldest_member_ingest_at=oldest,
        newest_member_ingest_at=newest,
        as_of=now_utc,
    )
