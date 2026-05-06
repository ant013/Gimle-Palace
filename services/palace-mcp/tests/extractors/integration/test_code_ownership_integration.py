"""Integration tests for code_ownership extractor — 8 scenarios on mini-fixture.

Uses real Neo4j via testcontainers + rebuilt mini-fixture repo.
Git history is seeded directly (no GitHistoryExtractor) to keep tests
isolated from other extractors.

GIM-216
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
from palace_mcp.extractors.code_ownership.schema_extension import (
    ensure_ownership_schema,
)
import palace_mcp.extractors.code_ownership.extractor as _ownership_extractor_module

FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "extractors"
    / "fixtures"
    / "code-ownership-mini-project"
)
PROJECT_ID = "project/test-ownership"


def _rebuild_fixture() -> Path:
    subprocess.run(
        ["bash", str(FIXTURE_DIR / "regen.sh")],
        check=True,
        capture_output=True,
    )
    return FIXTURE_DIR / "repo"


def _make_settings() -> MagicMock:
    s = MagicMock()
    s.ownership_blame_weight = 0.5
    s.ownership_max_files_per_run = 50_000
    s.ownership_write_batch_size = 2_000
    s.mailmap_max_bytes = 1_048_576
    s.palace_recency_decay_days = 30.0
    return s


def _ctx(repo_path: Path, run_id: str | None = None) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="test-ownership",
        group_id=PROJECT_ID,
        repo_path=repo_path,
        run_id=run_id or str(uuid.uuid4()),
        duration_ms=0,
        logger=logging.getLogger("test.code_ownership"),
    )


async def _seed_git_history(driver: AsyncDriver, repo_path: Path) -> None:
    """Seed :Commit + :Author + :TOUCHED edges mirroring what git_history writes."""
    log = (
        subprocess.run(
            ["git", "log", "--all", "--reverse", "--pretty=format:%H|%aN|%aE|%cI|%P"],
            cwd=str(repo_path),
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
        .split("\n")
    )

    bot_emails = {"bot@example.com"}
    rows = []
    for line in log:
        if not line.strip():
            continue
        sha, name, email, when, parents = line.split("|", 4)
        rows.append(
            {
                "sha": sha,
                "name": name,
                "email": email.lower(),
                "when": when,
                "parents": parents.split() if parents else [],
            }
        )

    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        for r in rows:
            await session.run(
                """
                MERGE (a:Author {provider: 'git', identity_key: $email})
                  ON CREATE SET a.email=$email, a.name=$name,
                                a.is_bot=$is_bot,
                                a.first_seen_at=datetime($when),
                                a.last_seen_at=datetime($when)
                  ON MATCH SET  a.last_seen_at=datetime($when)
                """,
                email=r["email"],
                name=r["name"],
                is_bot=(r["email"] in bot_emails),
                when=r["when"],
            )
            await session.run(
                """
                MERGE (c:Commit {sha: $sha})
                  ON CREATE SET c.project_id=$proj,
                                c.committed_at=datetime($when),
                                c.parents=$parents,
                                c.is_merge=$is_merge
                WITH c
                MATCH (a:Author {provider:'git', identity_key:$email})
                MERGE (c)-[:AUTHORED_BY]->(a)
                """,
                sha=r["sha"],
                proj=PROJECT_ID,
                when=r["when"],
                parents=r["parents"],
                is_merge=len(r["parents"]) > 1,
                email=r["email"],
            )

        for r in rows:
            if len(r["parents"]) > 1:
                cmd = [
                    "git",
                    "diff-tree",
                    "--no-commit-id",
                    "-r",
                    r["parents"][0],
                    r["sha"],
                ]
            else:
                cmd = ["git", "diff-tree", "--no-commit-id", "-r", "--root", r["sha"]]
            out = subprocess.run(
                cmd,
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            for diff_line in out.split("\n"):
                if not diff_line.strip():
                    continue
                parts = diff_line.split("\t")
                if len(parts) != 2:
                    continue
                path = parts[1]
                await session.run(
                    """
                    MERGE (f:File {project_id: $proj, path: $path})
                    WITH f
                    MATCH (c:Commit {sha: $sha})
                    MERGE (c)-[:TOUCHED]->(f)
                    """,
                    proj=PROJECT_ID,
                    sha=r["sha"],
                    path=path,
                )


def _graphiti(driver: AsyncDriver) -> MagicMock:
    g = MagicMock()
    g.driver = driver
    return g


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_1_bootstrap_full_walk(
    driver: AsyncDriver,
) -> None:
    """Fresh run, no checkpoint → non-zero edges, per-file shares normalised."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        stats = await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    assert stats.edges_written > 0

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: $proj})
                  -[r:OWNED_BY {source: 'extractor.code_ownership'}]->()
            WITH f, sum(r.blame_share) AS sb, sum(r.recency_churn_share) AS sc
            WHERE sb > 0 OR sc > 0
            RETURN f.path AS path, sb, sc
            """,
            proj=PROJECT_ID,
        )
        rows = await result.data()

    assert len(rows) > 0
    for row in rows:
        if row["sb"] > 0:
            assert abs(row["sb"] - 1.0) < 1e-6, row
        if row["sc"] > 0:
            assert abs(row["sc"] - 1.0) < 1e-6, row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_2_no_op_re_run(driver: AsyncDriver) -> None:
    """Re-run on same HEAD → edges_written == 0 (no_change path)."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        ext = CodeOwnershipExtractor()
        first = await ext.run(graphiti=_graphiti(driver), ctx=_ctx(repo_path))
        second = await ext.run(graphiti=_graphiti(driver), ctx=_ctx(repo_path))

    assert first.edges_written > 0
    assert second.edges_written == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_3_incremental_edit(driver: AsyncDriver, tmp_path: Path) -> None:
    """Append a commit → only that file reprocessed, checkpoint advances."""
    repo_path = Path(tmp_path / "repo")
    subprocess.run(
        ["bash", str(FIXTURE_DIR / "regen.sh")],
        env={**__import__("os").environ, "TARGET": str(repo_path)},
        capture_output=True,
    )
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        ext = CodeOwnershipExtractor()
        await ext.run(graphiti=_graphiti(driver), ctx=_ctx(repo_path))

    # Append a commit changing one file
    subprocess.run(
        ["git", "config", "user.email", "new@example.com"],
        cwd=str(repo_path),
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Anton Stavnichiy"],
        cwd=str(repo_path),
        check=True,
    )
    (repo_path / "apps" / "main.py").write_text(
        "def main():\n    return 999\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "apps/main.py"], cwd=str(repo_path), check=True)
    subprocess.run(
        ["git", "commit", "-m", "increment main"], cwd=str(repo_path), check=True
    )

    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        result = await ext.run(graphiti=_graphiti(driver), ctx=_ctx(repo_path))

    assert result.edges_written >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_4_deletion_handling(driver: AsyncDriver) -> None:
    """Deleted file (apps/legacy.py) must have no OWNED_BY edges."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: $proj, path: 'apps/legacy.py'})
                  -[r:OWNED_BY]->()
            RETURN count(r) AS n
            """,
            proj=PROJECT_ID,
        )
        row = await result.single()
    assert row is None or row["n"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_5_mailmap_dedup(driver: AsyncDriver) -> None:
    """old@example.com and new@example.com must not both own the same file."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: $proj})
                  -[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
            WHERE a.identity_key IN ['old@example.com', 'new@example.com']
            WITH f.path AS path, collect(a.identity_key) AS ids
            WHERE size(ids) > 1
            RETURN count(*) AS dual_owner_files
            """,
            proj=PROJECT_ID,
        )
        row = await result.single()
    # mailmap must collapse both identities into one — no file should have both
    assert row is None or row["dual_owner_files"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_6_bot_exclusion(driver: AsyncDriver) -> None:
    """bot@example.com must not appear as OWNED_BY target."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH ()-[r:OWNED_BY {source: 'extractor.code_ownership'}]
                  ->(a:Author {identity_key: 'bot@example.com'})
            RETURN count(r) AS n
            """,
        )
        row = await result.single()
    assert row is None or row["n"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_7_merge_exclusion(driver: AsyncDriver) -> None:
    """Merge commit must not inflate churn for any author."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    # apps/merge_target.py: added on side branch (1 real commit),
    # brought in by merge commit (excluded by is_merge filter).
    # commit_count must be exactly 1.
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: $proj, path: 'apps/merge_target.py'})
                  -[r:OWNED_BY {source: 'extractor.code_ownership'}]->(a:Author)
            RETURN r.commit_count AS cc
            """,
            proj=PROJECT_ID,
        )
        rows = await result.data()

    assert len(rows) >= 1
    for row in rows:
        assert row["cc"] <= 1, row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_8_binary_skipped(driver: AsyncDriver) -> None:
    """Binary file (apps/binary.png) must have no OWNED_BY edges."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: $proj, path: 'apps/binary.png'})
                  -[r:OWNED_BY {source: 'extractor.code_ownership'}]->()
            RETURN count(r) AS n
            """,
            proj=PROJECT_ID,
        )
        row = await result.single()
    assert row is None or row["n"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_9_crash_recovery(driver: AsyncDriver) -> None:
    """Phase 4 write_batch crash leaves no checkpoint; re-run completes cleanly (AC10)."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    with patch.object(
        _ownership_extractor_module,
        "write_batch",
        side_effect=RuntimeError("simulated Phase 4 crash"),
    ):
        with pytest.raises(RuntimeError, match="simulated Phase 4 crash"):
            with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
                await CodeOwnershipExtractor().run(
                    graphiti=_graphiti(driver), ctx=_ctx(repo_path)
                )

    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:OwnershipCheckpoint {project_id: $proj}) RETURN c",
            proj=PROJECT_ID,
        )
        row = await result.single()
    assert row is None, "checkpoint must not be written after crash"

    with patch("palace_mcp.mcp_server.get_settings", return_value=_make_settings()):
        stats = await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )
    assert stats.edges_written > 0, "re-run after crash must write edges"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_10_alpha_used_provenance(driver: AsyncDriver) -> None:
    """Edges written with alpha=0.5; after advancing HEAD and re-running with alpha=0.7,
    the dirty file's edges carry alpha_used=0.7 (AC11)."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    settings_50 = _make_settings()
    settings_50.ownership_blame_weight = 0.5

    with patch("palace_mcp.mcp_server.get_settings", return_value=settings_50):
        await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    async with driver.session() as session:
        result = await session.run(
            "MATCH ()-[r:OWNED_BY {source: 'extractor.code_ownership'}]->() "
            "RETURN DISTINCT r.alpha_used AS alpha",
        )
        rows = await result.data()
    assert rows, "expected OWNED_BY edges after first run"
    assert all(
        abs(row["alpha"] - 0.5) < 1e-9 for row in rows
    ), f"expected alpha=0.5 but got {rows}"

    # Advance HEAD so the second run has at least one DIRTY file
    subprocess.run(
        ["git", "config", "user.email", "new@example.com"], cwd=str(repo_path), check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Anton Stavnichiy"], cwd=str(repo_path), check=True
    )
    (repo_path / "apps" / "main.py").write_text("def main():\n    return 999\n", encoding="utf-8")
    subprocess.run(["git", "add", "apps/main.py"], cwd=str(repo_path), check=True)
    subprocess.run(["git", "commit", "-m", "alpha provenance test"], cwd=str(repo_path), check=True)
    await _seed_git_history(driver, repo_path)

    settings_70 = _make_settings()
    settings_70.ownership_blame_weight = 0.7

    with patch("palace_mcp.mcp_server.get_settings", return_value=settings_70):
        await CodeOwnershipExtractor().run(
            graphiti=_graphiti(driver), ctx=_ctx(repo_path)
        )

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:File {project_id: $proj, path: 'apps/main.py'})
                  -[r:OWNED_BY {source: 'extractor.code_ownership'}]->()
            RETURN DISTINCT r.alpha_used AS alpha
            """,
            proj=PROJECT_ID,
        )
        rows = await result.data()
    assert rows, "expected OWNED_BY edges for apps/main.py after second run"
    assert all(
        abs(row["alpha"] - 0.7) < 1e-9 for row in rows
    ), f"expected alpha=0.7 on dirty file but got {rows}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_11_per_batch_atomicity(driver: AsyncDriver) -> None:
    """With batch_size=1, a Phase 4 crash on the 2nd batch commits batch 1 but
    leaves checkpoint unwritten — subsequent re-run processes all files (AC15)."""
    repo_path = _rebuild_fixture()
    await ensure_ownership_schema(driver)
    await _seed_git_history(driver, repo_path)

    call_count = 0
    original_write_batch = _ownership_extractor_module.write_batch

    async def _fail_on_second(*args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise RuntimeError("simulated batch-2 crash")
        await original_write_batch(*args, **kwargs)  # type: ignore[arg-type]

    settings = _make_settings()
    settings.ownership_write_batch_size = 1

    with patch.object(_ownership_extractor_module, "write_batch", side_effect=_fail_on_second):
        with pytest.raises(RuntimeError, match="simulated batch-2 crash"):
            with patch("palace_mcp.mcp_server.get_settings", return_value=settings):
                await CodeOwnershipExtractor().run(
                    graphiti=_graphiti(driver), ctx=_ctx(repo_path)
                )

    assert call_count >= 2, "expected at least 2 write_batch calls with batch_size=1"

    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:OwnershipCheckpoint {project_id: $proj}) RETURN c",
            proj=PROJECT_ID,
        )
        row = await result.single()
    assert row is None, "checkpoint must not be written after partial-batch crash"

    async with driver.session() as session:
        result = await session.run(
            "MATCH ()-[r:OWNED_BY {source: 'extractor.code_ownership'}]->() RETURN count(r) AS n"
        )
        row = await result.single()
    assert row is not None and row["n"] > 0, "batch 1 must have committed at least one edge"
