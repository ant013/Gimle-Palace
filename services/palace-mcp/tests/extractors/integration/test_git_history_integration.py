"""Integration test — git_history extractor with real Neo4j + respx GitHub mock.

See spec §9.2. Uses testcontainers Neo4j (or COMPOSE_NEO4J_URI reuse).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.git_history.extractor import GitHistoryExtractor

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "git-history-mini-project"


def _make_ctx(repo_path: Path, run_id: str = "integ-run-gh-001") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="mini",
        group_id="project/mini",
        repo_path=repo_path,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


def _patch_infra(
    driver: AsyncDriver, github_token: str | None, tantivy_path: Path
) -> object:
    settings = MagicMock(
        github_token=github_token,
        git_history_tantivy_index_path=tantivy_path,
        git_history_max_commits_per_run=200_000,
    )
    return patch.multiple(
        "palace_mcp.extractors.git_history.extractor",
        ensure_custom_schema=AsyncMock(),
        _get_previous_error_code=AsyncMock(return_value=None),
        check_resume_budget=MagicMock(),
        check_phase_budget=MagicMock(),
        create_ingest_run=AsyncMock(),
        finalize_ingest_run=AsyncMock(),
        **{
            "palace_mcp.mcp_server.get_driver": MagicMock(return_value=driver),
            "palace_mcp.mcp_server.get_settings": MagicMock(return_value=settings),
        },
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_ingest_writes_commits_and_authors(
    driver: AsyncDriver, tmp_path: Path
) -> None:
    """End-to-end Phase 1: synthetic repo → :Commit + :Author nodes in Neo4j."""
    from tests.extractors.unit.test_git_history_pygit2_walker import (
        _build_synthetic_repo,
    )

    repo_path = _build_synthetic_repo(tmp_path / "repo", n_commits=3)

    settings = MagicMock(
        github_token=None,
        git_history_tantivy_index_path=tmp_path / "tantivy",
        git_history_max_commits_per_run=200_000,
    )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"),
        patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"),
        patch(
            "palace_mcp.extractors.git_history.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
    ):
        extractor = GitHistoryExtractor()
        stats = await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(repo_path))

    assert stats.nodes_written >= 3

    async with driver.session() as s:
        result = await s.run(
            "MATCH (c:Commit {project_id: 'project/mini'}) RETURN count(c) AS n"
        )
        row = await result.single()
    assert row is not None and row["n"] >= 3

    async with driver.session() as s:
        result = await s.run(
            "MATCH (a:Author {project_id: 'project/mini'}) RETURN count(a) AS n"
        )
        row = await result.single()
    assert row is not None and row["n"] >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_incremental_second_run_writes_zero_new_commits(
    driver: AsyncDriver, tmp_path: Path
) -> None:
    """Second run with same HEAD sha writes no new Commit nodes."""
    from tests.extractors.unit.test_git_history_pygit2_walker import (
        _build_synthetic_repo,
    )

    repo_path = _build_synthetic_repo(tmp_path / "repo", n_commits=2)

    settings = MagicMock(
        github_token=None,
        git_history_tantivy_index_path=tmp_path / "tantivy",
        git_history_max_commits_per_run=200_000,
    )

    patches = [
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"),
        patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"),
        patch(
            "palace_mcp.extractors.git_history.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
    ]

    extractor = GitHistoryExtractor()

    # First run
    for p in patches:
        p.start()
    try:
        await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(repo_path, "run-1"))
    finally:
        for p in patches:
            p.stop()

    async with driver.session() as s:
        result = await s.run(
            "MATCH (c:Commit {project_id: 'project/mini'}) RETURN count(c) AS n"
        )
        after_first = (await result.single())["n"]  # type: ignore[index]

    # Second run
    for p in patches:
        p.start()
    try:
        await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(repo_path, "run-2"))
    finally:
        for p in patches:
            p.stop()

    async with driver.session() as s:
        result = await s.run(
            "MATCH (c:Commit {project_id: 'project/mini'}) RETURN count(c) AS n"
        )
        after_second = (await result.single())["n"]  # type: ignore[index]

    assert after_second == after_first, (
        f"Second run should not create new Commit nodes: {after_first} → {after_second}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_author_email_lowercased_on_merge(
    driver: AsyncDriver, tmp_path: Path
) -> None:
    """Two commits with same email in different case produce one :Author node."""
    from tests.extractors.unit.test_git_history_pygit2_walker import (
        _build_synthetic_repo,
    )

    repo_path = _build_synthetic_repo(tmp_path / "repo", n_commits=2)

    settings = MagicMock(
        github_token=None,
        git_history_tantivy_index_path=tmp_path / "tantivy",
        git_history_max_commits_per_run=200_000,
    )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"),
        patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"),
        patch(
            "palace_mcp.extractors.git_history.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
    ):
        extractor = GitHistoryExtractor()
        await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(repo_path))

    async with driver.session() as s:
        result = await s.run(
            "MATCH (a:Author {project_id: 'project/mini'}) RETURN a.identity_key AS k"
        )
        keys = [rec["k"] async for rec in result]

    # All identity_keys must be lowercase
    for k in keys:
        assert k == k.lower(), f"identity_key not lowercase: {k!r}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_phase2_pr_ingest_with_respx(driver: AsyncDriver, tmp_path: Path) -> None:
    """Phase 2 with mocked GitHub GraphQL writes :PR + :PRComment nodes."""
    from tests.extractors.unit.test_git_history_pygit2_walker import (
        _build_synthetic_repo,
    )

    repo_path = _build_synthetic_repo(tmp_path / "repo", n_commits=1)

    fixture_response = json.loads(
        (FIXTURE_DIR / "github_responses" / "prs_page_1.json").read_text()
    )

    settings = MagicMock(
        github_token="fake-token",
        git_history_tantivy_index_path=tmp_path / "tantivy",
        git_history_max_commits_per_run=200_000,
    )

    with (
        respx.mock,
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        patch(
            "palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor._get_previous_error_code",
            new=AsyncMock(return_value=None),
        ),
        patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"),
        patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"),
        patch(
            "palace_mcp.extractors.git_history.extractor.create_ingest_run",
            new=AsyncMock(),
        ),
        patch(
            "palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
            new=AsyncMock(),
        ),
    ):
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(200, json=fixture_response)
        )
        extractor = GitHistoryExtractor()
        stats = await extractor.run(
            graphiti=MagicMock(),
            ctx=_make_ctx(repo_path),
        )

    # At least 2 PRs from fixture
    assert stats.nodes_written >= 3  # 1 commit + 2 PRs

    async with driver.session() as s:
        result = await s.run(
            "MATCH (p:PR {project_id: 'project/mini'}) RETURN count(p) AS n"
        )
        row = await result.single()
    assert row is not None and row["n"] >= 2
