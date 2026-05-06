from datetime import datetime, timezone

import pytest

from palace_mcp.extractors.code_ownership.models import (
    BlameAttribution,
    ChurnShare,
)
from palace_mcp.extractors.code_ownership.scorer import score_file


def _now() -> datetime:
    return datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


def _blame(canonical_id: str, lines: int) -> BlameAttribution:
    return BlameAttribution(
        canonical_id=canonical_id,
        canonical_name=canonical_id.split("@")[0],
        canonical_email=canonical_id,
        lines=lines,
    )


def _churn(canonical_id: str, recency: float, commits: int) -> ChurnShare:
    return ChurnShare(
        canonical_id=canonical_id,
        canonical_name=canonical_id.split("@")[0],
        canonical_email=canonical_id,
        recency_score=recency,
        last_touched_at=_now(),
        commit_count=commits,
    )


def test_single_author_weight_one():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 10)},
        churn={"a@x.com": _churn("a@x.com", 1.0, 1)},
        alpha=0.5,
        known_author_ids={"a@x.com"},
    )
    assert len(edges) == 1
    e = edges[0]
    assert e.weight == pytest.approx(1.0)
    assert e.blame_share == pytest.approx(1.0)
    assert e.recency_churn_share == pytest.approx(1.0)
    assert e.canonical_via == "identity"


def test_per_file_shares_sum_to_one():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 30), "b@x.com": _blame("b@x.com", 70)},
        churn={
            "a@x.com": _churn("a@x.com", 1.0, 1),
            "b@x.com": _churn("b@x.com", 3.0, 3),
        },
        alpha=0.5,
        known_author_ids={"a@x.com", "b@x.com"},
    )
    total_blame = sum(e.blame_share for e in edges)
    total_churn = sum(e.recency_churn_share for e in edges)
    total_w = sum(e.weight for e in edges)
    assert total_blame == pytest.approx(1.0)
    assert total_churn == pytest.approx(1.0)
    assert total_w == pytest.approx(1.0)


def test_alpha_zero_uses_only_churn():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 100)},  # blame says all-a
        churn={
            "a@x.com": _churn("a@x.com", 1.0, 1),
            "b@x.com": _churn("b@x.com", 4.0, 4),
        },
        alpha=0.0,
        known_author_ids={"a@x.com", "b@x.com"},
    )
    # b has no blame but α=0 means weight = 0 + 1 × churn_share
    by_id = {e.canonical_id: e for e in edges}
    assert by_id["a@x.com"].weight == pytest.approx(0.2)
    assert by_id["b@x.com"].weight == pytest.approx(0.8)


def test_alpha_one_uses_only_blame():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"a@x.com": _blame("a@x.com", 100)},
        churn={"b@x.com": _churn("b@x.com", 4.0, 4)},  # only b has churn
        alpha=1.0,
        known_author_ids={"a@x.com", "b@x.com"},
    )
    by_id = {e.canonical_id: e for e in edges}
    assert by_id["a@x.com"].weight == pytest.approx(1.0)
    assert "b@x.com" not in by_id  # b has no blame, blame_share=0, churn weighted 0


def test_canonical_via_mailmap_synthetic():
    """canonical_id not in known_author_ids → mailmap_synthetic."""
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={"new@x.com": _blame("new@x.com", 10)},
        churn={"new@x.com": _churn("new@x.com", 1.0, 1)},
        alpha=0.5,
        known_author_ids=set(),  # empty — canonical not seen as raw
    )
    assert edges[0].canonical_via == "mailmap_synthetic"


def test_empty_inputs_return_no_edges():
    edges = score_file(
        project_id="gimle",
        path="x.py",
        blame={},
        churn={},
        alpha=0.5,
        known_author_ids=set(),
    )
    assert edges == []
