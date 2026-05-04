from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from palace_mcp.extractors.git_history.neo4j_writer import (
    write_commit_with_author, _MERGE_AUTHOR_CYPHER, _MERGE_COMMIT_CYPHER,
)

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def test_merge_author_cypher_uses_on_create_and_on_match():
    """Spec §3.4 invariant 5 requires both clauses for time window preservation."""
    assert "ON CREATE SET" in _MERGE_AUTHOR_CYPHER
    assert "ON MATCH SET" in _MERGE_AUTHOR_CYPHER
    # Verify first_seen_at uses CASE for monotonicity
    assert "first_seen_at = CASE" in _MERGE_AUTHOR_CYPHER
    assert "last_seen_at = CASE" in _MERGE_AUTHOR_CYPHER


def test_merge_commit_cypher_uses_merge_for_idempotency():
    assert "MERGE" in _MERGE_COMMIT_CYPHER
    assert "Commit" in _MERGE_COMMIT_CYPHER


@pytest.mark.asyncio
async def test_write_commit_executes_two_queries_per_commit():
    """1 query for Author, 1 for Commit (and edges, possibly batched)."""
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    commit_dict = {
        "sha": "0" * 40, "author_email": "a@b.com", "author_name": "A",
        "committer_email": "a@b.com", "committer_name": "A",
        "message_subject": "x", "message_full_truncated": "x",
        "committed_at": UTC_TS, "parents": (), "touched_files": ["f.py"],
    }
    await write_commit_with_author(driver, "project/gimle", commit_dict, is_bot=False)
    assert driver.execute_query.await_count >= 2
