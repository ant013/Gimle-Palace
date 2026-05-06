"""Per-file weight scorer.

weight = α × blame_share + (1-α) × recency_churn_share
        per-file shares normalized over non-bot authors.

Bot authors are already filtered upstream (blame_walker / churn_aggregator
via bot_keys). The scorer trusts its inputs to be human-only.

Edges are emitted only for authors with at least one signal — an author
with blame=0 and churn=0 produces no edge.
"""

from __future__ import annotations

from datetime import datetime, timezone

from palace_mcp.extractors.code_ownership.models import (
    BlameAttribution,
    ChurnShare,
    OwnershipEdge,
)


def score_file(
    *,
    project_id: str,
    path: str,
    blame: dict[str, BlameAttribution],
    churn: dict[str, ChurnShare],
    alpha: float,
    known_author_ids: set[str],
) -> list[OwnershipEdge]:
    """Compute per-file ownership edges with normalized shares."""
    all_canonicals = set(blame) | set(churn)
    if not all_canonicals:
        return []

    total_lines = sum(b.lines for b in blame.values())
    total_recency = sum(c.recency_score for c in churn.values())

    edges: list[OwnershipEdge] = []
    for canonical_id in all_canonicals:
        b = blame.get(canonical_id)
        c = churn.get(canonical_id)
        blame_share = (b.lines / total_lines) if (b and total_lines > 0) else 0.0
        churn_share = (
            (c.recency_score / total_recency) if (c and total_recency > 0) else 0.0
        )
        weight = alpha * blame_share + (1.0 - alpha) * churn_share
        if weight == 0.0:
            continue

        if b is not None:
            canonical_name = b.canonical_name
            canonical_email = b.canonical_email
        else:
            assert c is not None
            canonical_name = c.canonical_name
            canonical_email = c.canonical_email

        last_touched_at: datetime
        if c is not None:
            last_touched_at = c.last_touched_at
        else:
            last_touched_at = datetime.now(tz=timezone.utc)

        if canonical_id in known_author_ids:
            canonical_via = "identity"
        else:
            canonical_via = "mailmap_synthetic"

        edges.append(
            OwnershipEdge(
                project_id=project_id,
                path=path,
                canonical_id=canonical_id,
                canonical_email=canonical_email,
                canonical_name=canonical_name,
                weight=weight,
                blame_share=blame_share,
                recency_churn_share=churn_share,
                last_touched_at=last_touched_at,
                lines_attributed=(b.lines if b else 0),
                commit_count=(c.commit_count if c else 0),
                canonical_via=canonical_via,
            )
        )
    return edges
