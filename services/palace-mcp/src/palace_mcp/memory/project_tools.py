"""Business logic for palace.memory.register_project, list_projects, get_project_overview."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.memory.cypher import (
    CHECK_BUNDLE_NAME_EXISTS,
    CHECK_PROJECT_NAMESPACE_CONFLICT,
    ENTITY_COUNTS_BY_PROJECT,
    GET_PROJECT,
    LIST_PROJECTS,
    PROJECT_ENTITY_COUNTS,
    PROJECT_INDEXED_COMMIT,
    PROJECT_LAST_INGEST,
    UPSERT_PROJECT,
)
from palace_mcp.code.snippet_provider import FreshnessResult, inspect_freshness
from palace_mcp.git.path_resolver import (
    ProjectNotRegistered,
    registration_identity_check,
    resolve_registered_project,
)
from palace_mcp.memory.schema import ProjectInfo
from palace_mcp.swift_scip_provenance import inspect_swift_scip_index_state

logger = logging.getLogger(__name__)

_MEMORY_ENTITY_TYPES = frozenset(
    {"Episode", "Iteration", "Decision", "IterationNote", "Finding"}
)
_CODE_INDEX_TYPES = frozenset(
    {
        "Module",
        "File",
        "Symbol",
        "APIEndpoint",
        "Model",
        "Repository",
        "ExternalLib",
        "Trace",
    }
)


def _project_info_from_row(
    row: Any,
    *,
    entity_counts: dict[str, int] | None = None,
    code_index_stats: dict[str, int] | None = None,
) -> ProjectInfo:
    p = row["p"]
    return ProjectInfo(
        slug=p["slug"],
        cm_project_name=p.get("cm_project_name"),
        name=p["name"],
        tags=list(p.get("tags") or []),
        language=p.get("language"),
        framework=p.get("framework"),
        repo_url=p.get("repo_url"),
        parent_mount=p.get("parent_mount"),
        relative_path=p.get("relative_path"),
        repo_path=p.get("repo_path"),
        language_profile=p.get("language_profile"),
        expected_profile=bool(p.get("expected_profile") or False),
        source_created_at=p["source_created_at"],
        source_updated_at=p["source_updated_at"],
        entity_counts=entity_counts or {},
        code_index_stats=code_index_stats or {},
        indexed_commit=p.get("indexed_commit"),
        indexed_commit_status=p.get("indexed_commit_status"),
        indexed_commit_source="project" if p.get("indexed_commit") else None,
    )


def _split_count(label: str, count: int) -> tuple[dict[str, int], dict[str, int]]:
    if count <= 0:
        return {}, {}
    if label in _MEMORY_ENTITY_TYPES:
        return {label: count}, {}
    if label in _CODE_INDEX_TYPES:
        return {}, {label: count}
    return {}, {}


async def register_project(
    driver: AsyncDriver,
    *,
    slug: str,
    name: str,
    tags: list[str],
    language: str | None = None,
    framework: str | None = None,
    repo_url: str | None = None,
    parent_mount: str | None = None,
    relative_path: str | None = None,
    repo_path: str | None = None,
    language_profile: str | None = None,
    expected_profile: bool = False,
) -> ProjectInfo:
    from palace_mcp.code.namespace import invalidate
    from palace_mcp.memory.bundle import ProjectSlugConflictsWithBundle
    from palace_mcp.memory.projects import (
        derive_cm_project_name,
        validate_parent_mount,
        validate_relative_path,
        validate_slug,
    )

    validate_slug(slug)

    # §6.5: validate parent_mount and relative_path at boundary, before I/O
    if parent_mount is not None:
        validate_parent_mount(parent_mount)
    if relative_path is not None:
        validate_relative_path(relative_path)

    # F3 (Sprint-1 reliability): repo_path must be a real git repo, and when a
    # mount layout is also given, both must resolve to the SAME directory
    # (symlink-normalized — this host mounts through symlink aliases). The
    # hd-wallet-kit defect was repo_path and relative_path pointing at two
    # different valid repos, silently.
    if repo_path is not None:
        rp = Path(repo_path)
        if not rp.is_absolute():
            raise ValueError(f"repo_path must be absolute: {repo_path!r}")
        if not rp.is_dir():
            raise ValueError(f"repo_path does not exist: {repo_path!r}")
        if not (rp / ".git").exists():
            raise ValueError(f"repo_path is not a git repo: {repo_path!r}")
        if parent_mount and relative_path:
            mount_resolved: Path | None = None
            try:
                mount_resolved = resolve_registered_project(
                    slug,
                    project_node={
                        "parent_mount": parent_mount,
                        "relative_path": relative_path,
                    },
                )
            except (ProjectNotRegistered, ValueError):
                mount_resolved = None
            if mount_resolved is not None and mount_resolved.resolve() != rp.resolve():
                raise ValueError(
                    "repo_path and parent_mount/relative_path resolve to "
                    f"different directories: {rp.resolve()} != "
                    f"{mount_resolved.resolve()}"
                )

    now = datetime.now(timezone.utc).isoformat()
    cm_project_name = derive_cm_project_name(
        slug=slug,
        parent_mount=parent_mount,
        relative_path=relative_path,
    )
    async with driver.session() as session:
        # §8.15/16 namespace guard: project slug must not conflict with bundle name
        b_result = await session.run(CHECK_BUNDLE_NAME_EXISTS, name=slug)
        b_row = await b_result.single()
        if b_row is not None:
            raise ProjectSlugConflictsWithBundle(slug)

        conflict_result = await session.run(
            CHECK_PROJECT_NAMESPACE_CONFLICT,
            slug=slug,
            cm_project_name=cm_project_name,
        )
        conflict_row = await conflict_result.single()
        if conflict_row is not None:
            raise ValueError(
                "project namespace conflict: "
                f"slug={slug!r}, cm_project_name={cm_project_name!r}, "
                f"existing_slug={conflict_row['slug']!r}, "
                f"existing_cm_project_name={conflict_row['cm_project_name']!r}"
            )

        await session.run(
            UPSERT_PROJECT,
            slug=slug,
            cm_project_name=cm_project_name,
            name=name,
            tags=list(tags),
            language=language,
            framework=framework,
            repo_url=repo_url,
            parent_mount=parent_mount,
            relative_path=relative_path,
            repo_path=repo_path,
            language_profile=language_profile,
            expected_profile=expected_profile,
            now=now,
        )
        result = await session.run(GET_PROJECT, slug=slug)
        row = await result.single()
    assert row is not None, f"Project not found after upsert: {slug!r}"
    invalidate()
    return _project_info_from_row(row)


async def list_projects(driver: AsyncDriver) -> list[ProjectInfo]:
    """Return all :Project nodes ordered by slug."""
    async with driver.session() as session:
        result = await session.run(LIST_PROJECTS)
        project_rows = [row async for row in result]

        counts_result = await session.run(ENTITY_COUNTS_BY_PROJECT)
        entity_counts_by_slug: dict[str, dict[str, int]] = {}
        code_index_stats_by_slug: dict[str, dict[str, int]] = {}
        async for count_row in counts_result:
            slug = str(count_row["slug"])
            count = int(count_row["cnt"])
            memory_counts, code_counts = _split_count(str(count_row["type"]), count)
            if memory_counts:
                entity_counts_by_slug.setdefault(slug, {}).update(memory_counts)
            if code_counts:
                code_index_stats_by_slug.setdefault(slug, {}).update(code_counts)

        return [
            _project_info_from_row(
                row,
                entity_counts=entity_counts_by_slug.get(row["p"]["slug"]),
                code_index_stats=code_index_stats_by_slug.get(row["p"]["slug"]),
            )
            for row in project_rows
        ]


async def project_integrity_warnings(driver: AsyncDriver) -> list[str]:
    """F3: live registry-identity sweep, surfaced via health payloads.

    Warns only on positive inconsistency (path_mismatch, repo_path_missing) —
    "unresolved" is normal for memory-only projects and would be noise.
    """
    warnings: list[str] = []
    async with driver.session() as session:
        result = await session.run(LIST_PROJECTS)
        rows = [row async for row in result]
    for row in rows:
        node = row["p"]
        slug = str(node["slug"])
        try:
            check = registration_identity_check(slug, project_node=node)
        except Exception as exc:  # noqa: BLE001 — one bad row must not kill the sweep
            warnings.append(f"{slug}: identity_check_failed ({str(exc)[:80]})")
            continue
        if check in ("path_mismatch", "repo_path_missing"):
            warnings.append(
                f"{slug}: {check} (repo_path={node.get('repo_path')!r}, "
                f"parent_mount={node.get('parent_mount')!r}, "
                f"relative_path={node.get('relative_path')!r})"
            )
    return warnings


async def get_project_overview(
    driver: AsyncDriver,
    *,
    slug: str,
    source: str = "paperclip",
) -> ProjectInfo:
    """Return a :Project with memory counts, code index stats, and ingest metadata."""
    from palace_mcp.memory.projects import UnknownProjectError

    group_id = f"project/{slug}"
    project_node: Any | None = None
    async with driver.session() as session:
        result = await session.run(GET_PROJECT, slug=slug)
        row = await result.single()
        if row is None:
            raise UnknownProjectError(slug)
        project_node = row["p"]
        base = _project_info_from_row(row)

        counts_result = await session.run(PROJECT_ENTITY_COUNTS, group_id=group_id)
        entity_counts: dict[str, int] = {}
        code_index_stats: dict[str, int] = {}
        async for count_row in counts_result:
            for lbl in count_row["labels"]:
                memory_counts, code_counts = _split_count(lbl, int(count_row["c"]))
                if memory_counts:
                    for key, value in memory_counts.items():
                        entity_counts[key] = entity_counts.get(key, 0) + value
                if code_counts:
                    for key, value in code_counts.items():
                        code_index_stats[key] = code_index_stats.get(key, 0) + value

        last_ingest: dict[str, Any] | None = None
        try:
            ingest_result = await session.run(
                PROJECT_LAST_INGEST, group_id=group_id, source=source
            )
            lr = await ingest_result.single()
            if lr is not None:
                last_ingest = dict(lr["r"])
        except Exception as exc:
            logger.warning("get_project_overview last_ingest query failed: %s", exc)

        indexed_commit_result = await session.run(
            PROJECT_INDEXED_COMMIT,
            group_id=group_id,
        )
        indexed_commit_row = await indexed_commit_result.single()

    # Dominant per-symbol vote: DIAGNOSTIC ONLY (dominant_symbol_commit).
    # After any incremental ingest the vote is a previous run's sha; feeding
    # it into lag math is how "EvmKit 3 behind" was reported while current.
    dominant_symbol_commit = (
        str(indexed_commit_row["commit_sha"])
        if indexed_commit_row is not None
        and indexed_commit_row["commit_sha"] is not None
        else None
    )
    authoritative_commit = (
        str(project_node.get("indexed_commit"))
        if project_node.get("indexed_commit")
        else None
    )
    indexed_commit_status = (
        str(project_node.get("indexed_commit_status"))
        if project_node.get("indexed_commit_status")
        else None
    )

    identity_check = registration_identity_check(slug, project_node=project_node)
    try:
        repo_path = resolve_registered_project(slug, project_node=project_node)
    except (ProjectNotRegistered, ValueError):
        repo_path = None

    if identity_check not in ("ok", "unchecked"):
        # Never a confident number against a possibly-wrong tree.
        freshness = FreshnessResult(
            indexed_commit=authoritative_commit,
            commits_behind_head=None,
            stale=None,
            freshness_state="unknown",
            freshness_reason="registry_mismatch",
        )
    elif authoritative_commit is not None:
        freshness = inspect_freshness(repo_path, authoritative_commit)
    else:
        freshness = FreshnessResult(
            indexed_commit=None,
            commits_behind_head=None,
            stale=None,
            freshness_state="unknown",
            freshness_reason="indexed_commit_unpopulated_reingest_required",
        )

    if (
        base.language_profile == "swift_kit"
        and repo_path is not None
        and identity_check in ("ok", "unchecked")
    ):
        try:
            swift_index_state = await inspect_swift_scip_index_state(
                driver,
                project_slug=slug,
                project_id=group_id,
                repo_path=repo_path,
            )
        except Exception as exc:
            logger.warning("get_project_overview SCIP state inspection failed: %s", exc)
            swift_index_state = None
        if swift_index_state is None or not swift_index_state.current:
            scip_reason = (
                swift_index_state.reason
                if swift_index_state is not None
                else "scip_index_state_unavailable"
            )
            definitely_stale = freshness.stale is True or (
                swift_index_state is not None and swift_index_state.stale is True
            )
            freshness = FreshnessResult(
                indexed_commit=freshness.indexed_commit,
                commits_behind_head=freshness.commits_behind_head,
                stale=True if definitely_stale else None,
                freshness_state=(
                    "behind_local_tree" if definitely_stale else "unknown"
                ),
                freshness_reason=scip_reason,
                tree_head=freshness.tree_head,
            )

    return base.model_copy(
        update={
            "entity_counts": entity_counts,
            "code_index_stats": code_index_stats,
            "last_ingest_started_at": last_ingest.get("started_at")
            if last_ingest
            else None,
            "last_ingest_finished_at": last_ingest.get("finished_at")
            if last_ingest
            else None,
            "indexed_commit": freshness.indexed_commit,
            "indexed_commit_source": "project" if authoritative_commit else None,
            "indexed_commit_status": indexed_commit_status,
            "dominant_symbol_commit": dominant_symbol_commit,
            "commits_behind_head": freshness.commits_behind_head,
            "commits_behind_local_tree": freshness.commits_behind_head,
            "tree_head": freshness.tree_head,
            "stale": freshness.stale,
            "freshness_state": freshness.freshness_state,
            "freshness_reason": freshness.freshness_reason,
            "origin_checked": False,
            "commits_behind_origin": None,
            "identity_check": identity_check,
        }
    )
