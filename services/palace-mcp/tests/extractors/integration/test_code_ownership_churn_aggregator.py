import math
from datetime import datetime, timezone

import pytest

from palace_mcp.extractors.code_ownership.churn_aggregator import aggregate_churn
from palace_mcp.extractors.code_ownership.mailmap import (
    MailmapResolver,
    MailmapResolverPath,
)


def _identity_resolver() -> MailmapResolver:
    return MailmapResolver(MailmapResolverPath.IDENTITY_PASSTHROUGH)


@pytest.fixture
async def seeded_graph(driver):
    """Seed minimal git_history graph: 2 files, 3 authors, 5 commits.

    File a.py: 3 commits by author1, 1 commit by author2, 1 merge by author3.
    File b.py: 2 commits by author2 (one is by bot).
    """
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            // Authors
            MERGE (a1:Author {provider: 'git', identity_key: 'a1@example.com'})
              SET a1.email = 'a1@example.com', a1.name = 'A1', a1.is_bot = false
            MERGE (a2:Author {provider: 'git', identity_key: 'a2@example.com'})
              SET a2.email = 'a2@example.com', a2.name = 'A2', a2.is_bot = false
            MERGE (bot:Author {provider: 'git', identity_key: 'bot@x.com'})
              SET bot.email = 'bot@x.com', bot.name = 'Bot', bot.is_bot = true

            // Files
            MERGE (fa:File {project_id: 'gimle', path: 'a.py'})
            MERGE (fb:File {project_id: 'gimle', path: 'b.py'})

            // Commits
            FOREACH (i IN range(1, 3) |
              MERGE (c:Commit {sha: 'c' + toString(i)})
                ON CREATE SET c.project_id = 'gimle',
                              c.committed_at = datetime() - duration({days: i}),
                              c.parents = [],
                              c.is_merge = false
              MERGE (c)-[:AUTHORED_BY]->(a1)
              MERGE (c)-[:TOUCHED]->(fa)
            )
            MERGE (c4:Commit {sha: 'c4'})
              ON CREATE SET c4.project_id = 'gimle',
                            c4.committed_at = datetime() - duration({days: 4}),
                            c4.parents = [],
                            c4.is_merge = false
            MERGE (c4)-[:AUTHORED_BY]->(a2)
            MERGE (c4)-[:TOUCHED]->(fa)

            MERGE (c5:Commit {sha: 'c5'})
              ON CREATE SET c5.project_id = 'gimle',
                            c5.committed_at = datetime() - duration({days: 5}),
                            c5.parents = ['p1', 'p2'],
                            c5.is_merge = true
            MERGE (c5)-[:AUTHORED_BY]->(a1)
            MERGE (c5)-[:TOUCHED]->(fa)

            MERGE (c6:Commit {sha: 'c6'})
              ON CREATE SET c6.project_id = 'gimle',
                            c6.committed_at = datetime() - duration({days: 1}),
                            c6.parents = [],
                            c6.is_merge = false
            MERGE (c6)-[:AUTHORED_BY]->(a2)
            MERGE (c6)-[:TOUCHED]->(fb)

            MERGE (c7:Commit {sha: 'c7'})
              ON CREATE SET c7.project_id = 'gimle',
                            c7.committed_at = datetime() - duration({days: 1}),
                            c7.parents = [],
                            c7.is_merge = false
            MERGE (c7)-[:AUTHORED_BY]->(bot)
            MERGE (c7)-[:TOUCHED]->(fb)
            """
        )
    yield driver


@pytest.mark.asyncio
async def test_churn_aggregator_excludes_bots_and_merges(seeded_graph):
    result = await aggregate_churn(
        seeded_graph,
        project_id="gimle",
        paths={"a.py", "b.py"},
        mailmap=_identity_resolver(),
        bot_keys={"bot@x.com"},
        decay_days=30.0,
        known_author_ids={"a1@example.com", "a2@example.com", "bot@x.com"},
    )

    # a.py: a1 has 3 non-merge commits, a2 has 1 non-merge commit; merge by a1 excluded
    a_authors = result["a.py"]
    assert "a1@example.com" in a_authors
    assert a_authors["a1@example.com"].commit_count == 3  # merge filtered
    assert "a2@example.com" in a_authors
    assert a_authors["a2@example.com"].commit_count == 1

    # b.py: a2 has 1 commit; bot is excluded entirely
    b_authors = result["b.py"]
    assert "a2@example.com" in b_authors
    assert b_authors["a2@example.com"].commit_count == 1
    assert "bot@x.com" not in b_authors


@pytest.mark.asyncio
async def test_churn_recency_decay_monotone(seeded_graph):
    """Older commits → smaller recency_score per commit."""
    result = await aggregate_churn(
        seeded_graph,
        project_id="gimle",
        paths={"a.py"},
        mailmap=_identity_resolver(),
        bot_keys=set(),
        decay_days=30.0,
        known_author_ids={"a1@example.com", "a2@example.com"},
    )
    # a1: 3 commits at days 1, 2, 3 → all relatively recent
    # a2: 1 commit at day 4 → older
    a1_score = result["a.py"]["a1@example.com"].recency_score
    a2_score = result["a.py"]["a2@example.com"].recency_score
    # Per-commit average: a1 ~ exp(-1/30), a2 ~ exp(-4/30)
    assert a1_score / 3 > a2_score / 1
