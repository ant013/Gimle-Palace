from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.code_ownership.models import (
    BlameAttribution,
    ChurnShare,
    OwnershipCheckpoint,
    OwnershipEdge,
    OwnershipFileStateRecord,
    OwnershipRunSummary,
)


def _now() -> datetime:
    return datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


def test_ownership_checkpoint_roundtrip():
    cp = OwnershipCheckpoint(
        project_id="gimle",
        last_head_sha="abcdef0123456789abcdef0123456789abcdef01",
        last_completed_at=_now(),
        run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert cp.last_head_sha.startswith("abcdef")


def test_ownership_checkpoint_bootstrap_null_head_sha():
    """First-ever run: last_head_sha is None."""
    cp = OwnershipCheckpoint(
        project_id="gimle",
        last_head_sha=None,
        last_completed_at=_now(),
        run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert cp.last_head_sha is None


def test_ownership_checkpoint_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        OwnershipCheckpoint(
            project_id="gimle",
            last_head_sha=None,
            last_completed_at=datetime(2026, 5, 6, 12, 0, 0),  # no tz
            run_id="x",
            updated_at=_now(),
        )


def test_ownership_file_state_record_processed():
    s = OwnershipFileStateRecord(
        project_id="gimle",
        path="services/palace-mcp/foo.py",
        status="processed",
        no_owners_reason=None,
        last_run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert s.status == "processed"


def test_ownership_file_state_record_skipped_with_reason():
    s = OwnershipFileStateRecord(
        project_id="gimle",
        path="services/palace-mcp/blob.png",
        status="skipped",
        no_owners_reason="binary_or_skipped",
        last_run_id="11111111-1111-1111-1111-111111111111",
        updated_at=_now(),
    )
    assert s.no_owners_reason == "binary_or_skipped"


def test_ownership_file_state_record_invalid_status_rejected():
    with pytest.raises(ValidationError):
        OwnershipFileStateRecord(
            project_id="gimle",
            path="x.py",
            status="weird",  # not in literal
            no_owners_reason=None,
            last_run_id="x",
            updated_at=_now(),
        )


def test_ownership_edge_canonical_via_literal():
    e = OwnershipEdge(
        project_id="gimle",
        path="x.py",
        canonical_id="anton@example.com",
        canonical_email="anton@example.com",
        canonical_name="Anton",
        weight=0.42,
        blame_share=0.5,
        recency_churn_share=0.34,
        last_touched_at=_now(),
        lines_attributed=100,
        commit_count=10,
        canonical_via="identity",
    )
    assert e.canonical_via == "identity"


def test_ownership_edge_invalid_canonical_via_rejected():
    with pytest.raises(ValidationError):
        OwnershipEdge(
            project_id="gimle",
            path="x.py",
            canonical_id="anton@example.com",
            canonical_email="anton@example.com",
            canonical_name="Anton",
            weight=0.42,
            blame_share=0.5,
            recency_churn_share=0.34,
            last_touched_at=_now(),
            lines_attributed=100,
            commit_count=10,
            canonical_via="bogus",
        )


def test_blame_attribution_basic():
    b = BlameAttribution(
        canonical_id="anton@example.com",
        canonical_name="Anton",
        canonical_email="anton@example.com",
        lines=145,
    )
    assert b.lines == 145


def test_churn_share_basic():
    c = ChurnShare(
        canonical_id="anton@example.com",
        canonical_name="Anton",
        canonical_email="anton@example.com",
        recency_score=2.5,
        last_touched_at=_now(),
        commit_count=12,
    )
    assert c.recency_score == 2.5


def test_ownership_run_summary_basic():
    s = OwnershipRunSummary(
        project_id="gimle",
        run_id="11111111-1111-1111-1111-111111111111",
        head_sha="abcdef0123456789abcdef0123456789abcdef01",
        prev_head_sha=None,
        dirty_files_count=10,
        deleted_files_count=2,
        edges_written=42,
        edges_deleted=8,
        mailmap_resolver_path="pygit2",
        exit_reason="success",
        duration_ms=1234,
    )
    assert s.exit_reason == "success"
