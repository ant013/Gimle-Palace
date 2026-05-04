from datetime import datetime, timezone
from pathlib import Path
import pytest

from palace_mcp.extractors.git_history.tantivy_writer import GitHistoryTantivyWriter
from palace_mcp.extractors.git_history.models import Commit, PR, PRComment

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_writer_writes_commit_doc(tmp_path: Path):
    writer = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    async with writer:
        commit = Commit(
            project_id="project/gimle", sha="0" * 40,
            author_provider="git", author_identity_key="a@b.com",
            committer_provider="git", committer_identity_key="a@b.com",
            message_subject="subject", message_full_truncated="subject\n\nbody",
            committed_at=UTC_TS, parents=(),
        )
        await writer.add_commit_async(commit, body_full="subject\n\nfull body of commit")
    # Verify by reopening and searching
    by_searcher = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    docs = by_searcher.search_by_doc_id_sync("0" * 40)
    assert len(docs) == 1


@pytest.mark.asyncio
async def test_writer_writes_pr_and_comment(tmp_path: Path):
    writer = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    async with writer:
        pr = PR(project_id="project/gimle", number=42, title="t",
                body_truncated="b", state="merged",
                author_provider="github", author_identity_key="login",
                created_at=UTC_TS, merged_at=UTC_TS, head_sha="0"*40,
                base_branch="develop")
        await writer.add_pr_async(pr, body_full="full PR body")
        cmt = PRComment(project_id="project/gimle", id="cmt1", pr_number=42,
                        body_truncated="c", author_provider="github",
                        author_identity_key="login", created_at=UTC_TS)
        await writer.add_pr_comment_async(cmt, body_full="full comment body")
    reader = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    pr_docs = reader.search_by_doc_id_sync("42")
    cmt_docs = reader.search_by_doc_id_sync("cmt1")
    assert len(pr_docs) == 1
    assert len(cmt_docs) == 1
