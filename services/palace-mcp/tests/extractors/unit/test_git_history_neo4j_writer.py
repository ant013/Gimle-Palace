from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from palace_mcp.extractors.git_history.neo4j_writer import (
    write_commit_with_author,
    write_pr,
    write_pr_comment,
    _MERGE_AUTHOR_CYPHER,
    _MERGE_COMMIT_CYPHER,
    _MERGE_PR_COMMENT_CYPHER,
    _MERGE_PR_CYPHER,
    _MERGE_TOUCHED_CYPHER,
)

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


async def _write_commit_case(driver, project_id):
    await write_commit_with_author(
        driver,
        project_id,
        {
            "sha": "0" * 40,
            "author_email": "a@b.com",
            "author_name": "A",
            "committer_email": "a@b.com",
            "committer_name": "A",
            "message_subject": "x",
            "message_full_truncated": "x",
            "committed_at": UTC_TS,
            "parents": (),
            "touched_files": ["f.py"],
        },
        is_bot=False,
    )


async def _write_pr_case(driver, project_id):
    await write_pr(
        driver,
        project_id,
        {
            "number": 7,
            "title": "PR",
            "body_truncated": "body",
            "state": "open",
            "created_at": UTC_TS,
            "merged_at": None,
            "head_sha": "1" * 40,
            "base_branch": "develop",
            "author_email": "a@b.com",
            "author_name": "A",
        },
        "a@b.com",
        "github",
        is_bot=False,
    )


async def _write_pr_comment_case(driver, project_id):
    await write_pr_comment(
        driver,
        project_id,
        {
            "id": "comment-1",
            "pr_number": 7,
            "body_truncated": "body",
            "created_at": UTC_TS,
            "author_email": "a@b.com",
            "author_name": "A",
        },
        "a@b.com",
        "github",
        is_bot=False,
    )


def test_merge_author_cypher_uses_on_create_and_on_match():
    """Spec §3.4 invariant 5 requires both clauses for time window preservation."""
    assert "ON CREATE SET" in _MERGE_AUTHOR_CYPHER
    assert "ON MATCH SET" in _MERGE_AUTHOR_CYPHER
    assert "a.group_id = $project_id" in _MERGE_AUTHOR_CYPHER
    # Verify first_seen_at uses CASE for monotonicity
    assert "first_seen_at = CASE" in _MERGE_AUTHOR_CYPHER
    assert "last_seen_at = CASE" in _MERGE_AUTHOR_CYPHER


def test_merge_commit_cypher_uses_merge_for_idempotency():
    assert "MERGE" in _MERGE_COMMIT_CYPHER
    assert "Commit" in _MERGE_COMMIT_CYPHER
    assert "c.group_id = $project_id" in _MERGE_COMMIT_CYPHER


@pytest.mark.parametrize(
    ("label", "alias", "cypher"),
    [
        ("Author", "a", _MERGE_AUTHOR_CYPHER),
        ("Commit", "c", _MERGE_COMMIT_CYPHER),
        ("File", "f", _MERGE_TOUCHED_CYPHER),
        ("PR", "p", _MERGE_PR_CYPHER),
        ("PRComment", "c", _MERGE_PR_COMMENT_CYPHER),
    ],
)
def test_git_history_node_cyphers_set_and_backfill_group_id(label, alias, cypher):
    assert label in cypher
    assert f"{alias}.group_id = $project_id" in cypher
    assert f"{alias}.group_id = coalesce({alias}.group_id, $project_id)" in cypher


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("writer", "expected_cyphers"),
    [
        (_write_commit_case, [_MERGE_AUTHOR_CYPHER, _MERGE_COMMIT_CYPHER, _MERGE_TOUCHED_CYPHER]),
        (_write_pr_case, [_MERGE_AUTHOR_CYPHER, _MERGE_PR_CYPHER]),
        (_write_pr_comment_case, [_MERGE_AUTHOR_CYPHER, _MERGE_PR_COMMENT_CYPHER]),
    ],
)
async def test_git_history_writers_pass_project_id_to_node_queries(
    writer, expected_cyphers
):
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    project_id = "project/gimle"

    await writer(driver, project_id)

    calls_by_cypher = {call.args[0]: call for call in driver.execute_query.await_args_list}
    assert set(expected_cyphers) <= set(calls_by_cypher)
    for cypher in expected_cyphers:
        assert calls_by_cypher[cypher].kwargs["project_id"] == project_id


@pytest.mark.asyncio
async def test_write_commit_executes_two_queries_per_commit():
    """1 query for Author, 1 for Commit (and edges, possibly batched)."""
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    commit_dict = {
        "sha": "0" * 40,
        "author_email": "a@b.com",
        "author_name": "A",
        "committer_email": "a@b.com",
        "committer_name": "A",
        "message_subject": "x",
        "message_full_truncated": "x",
        "committed_at": UTC_TS,
        "parents": (),
        "touched_files": ["f.py"],
    }
    await write_commit_with_author(driver, "project/gimle", commit_dict, is_bot=False)
    assert driver.execute_query.await_count >= 2
