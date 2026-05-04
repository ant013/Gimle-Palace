from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from palace_mcp.extractors.git_history.models import (
    Author,
    Commit,
    PR,
    PRComment,
    GitHistoryCheckpoint,
)

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def test_author_provider_git_lowercases_email():
    a = Author(
        provider="git",
        identity_key="Foo@Bar.COM",
        email="Foo@Bar.COM",
        name="Foo",
        is_bot=False,
        first_seen_at=UTC_TS,
        last_seen_at=UTC_TS,
    )
    assert a.identity_key == "foo@bar.com"
    assert a.email == "foo@bar.com"


def test_author_provider_github_keeps_login_case():
    a = Author(
        provider="github",
        identity_key="FooLogin",
        email=None,
        name="Foo",
        is_bot=False,
        first_seen_at=UTC_TS,
        last_seen_at=UTC_TS,
    )
    assert a.identity_key == "FooLogin"


def test_author_email_none_allowed():
    a = Author(
        provider="github",
        identity_key="login",
        email=None,
        name="X",
        is_bot=False,
        first_seen_at=UTC_TS,
        last_seen_at=UTC_TS,
    )
    assert a.email is None


def test_author_email_empty_string_normalized_to_none():
    a = Author(
        provider="github",
        identity_key="login",
        email="",
        name="X",
        is_bot=False,
        first_seen_at=UTC_TS,
        last_seen_at=UTC_TS,
    )
    assert a.email is None


def test_author_naive_datetime_rejected():
    naive = datetime(2026, 5, 3, 12, 0)  # no tzinfo
    with pytest.raises(ValidationError):
        Author(
            provider="git",
            identity_key="a@b.com",
            email="a@b.com",
            name="X",
            is_bot=False,
            first_seen_at=naive,
            last_seen_at=UTC_TS,
        )


def test_commit_short_sha_computed():
    c = Commit(
        project_id="project/gimle",
        sha="0123456789abcdef0123456789abcdef01234567",
        author_provider="git",
        author_identity_key="a@b.com",
        committer_provider="git",
        committer_identity_key="a@b.com",
        message_subject="subject",
        message_full_truncated="body",
        committed_at=UTC_TS,
        parents=(),
    )
    assert c.short_sha == "0123456"


def test_commit_is_merge_computed_from_parents():
    base = dict(
        project_id="project/gimle",
        sha="0" * 40,
        author_provider="git",
        author_identity_key="a@b.com",
        committer_provider="git",
        committer_identity_key="a@b.com",
        message_subject="x",
        message_full_truncated="x",
        committed_at=UTC_TS,
    )
    assert Commit(**base, parents=()).is_merge is False
    assert Commit(**base, parents=("1" * 40,)).is_merge is False
    assert Commit(**base, parents=("1" * 40, "2" * 40)).is_merge is True


def test_commit_invalid_sha_rejected():
    with pytest.raises(ValidationError):
        Commit(
            project_id="project/gimle",
            sha="not-hex",
            author_provider="git",
            author_identity_key="a@b.com",
            committer_provider="git",
            committer_identity_key="a@b.com",
            message_subject="x",
            message_full_truncated="x",
            committed_at=UTC_TS,
            parents=(),
        )


def test_commit_message_truncation_enforced_at_validator():
    too_long = "x" * 1100
    with pytest.raises(ValidationError):
        Commit(
            project_id="project/gimle",
            sha="0" * 40,
            author_provider="git",
            author_identity_key="a@b.com",
            committer_provider="git",
            committer_identity_key="a@b.com",
            message_subject="x",
            message_full_truncated=too_long,
            committed_at=UTC_TS,
            parents=(),
        )


def test_pr_state_lowercased_from_uppercase_input():
    pr = PR(
        project_id="project/gimle",
        number=42,
        title="t",
        body_truncated="b",
        state="MERGED",
        author_provider="github",
        author_identity_key="login",
        created_at=UTC_TS,
        merged_at=UTC_TS,
        head_sha="0" * 40,
        base_branch="develop",
    )
    assert pr.state == "merged"


def test_pr_invalid_state_rejected():
    with pytest.raises(ValidationError):
        PR(
            project_id="project/gimle",
            number=42,
            title="t",
            body_truncated="b",
            state="DRAFT",
            author_provider="github",
            author_identity_key="login",
            created_at=UTC_TS,
            merged_at=None,
            head_sha=None,
            base_branch="develop",
        )


def test_pr_comment_body_truncation_enforced():
    too_long = "x" * 1100
    with pytest.raises(ValidationError):
        PRComment(
            project_id="project/gimle",
            id="cmt-1",
            pr_number=42,
            body_truncated=too_long,
            author_provider="github",
            author_identity_key="login",
            created_at=UTC_TS,
        )


def test_git_history_checkpoint_round_trip():
    ckpt = GitHistoryCheckpoint(
        project_id="project/gimle",
        last_commit_sha="0" * 40,
        last_pr_updated_at=UTC_TS,
        last_phase_completed="phase1",
        updated_at=UTC_TS,
    )
    assert ckpt.last_phase_completed == "phase1"


def test_git_history_checkpoint_none_initial_state():
    ckpt = GitHistoryCheckpoint(
        project_id="project/gimle",
        last_commit_sha=None,
        last_pr_updated_at=None,
        last_phase_completed="none",
        updated_at=UTC_TS,
    )
    assert ckpt.last_commit_sha is None


def test_ensure_custom_schema_includes_git_history_constraints():
    from palace_mcp.extractors.foundation.schema import EXPECTED_SCHEMA

    constraint_names = {c.name for c in EXPECTED_SCHEMA.constraints}
    assert "git_commit_sha" in constraint_names
    assert "git_author_pk" in constraint_names
    assert "git_history_ckpt" in constraint_names
    # Verify composite key for Author
    author_c = next(c for c in EXPECTED_SCHEMA.constraints if c.name == "git_author_pk")
    assert author_c.properties == ("provider", "identity_key")
