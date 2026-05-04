"""GitHistoryTantivyWriter — own schema (see spec §3.7)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import tantivy

from palace_mcp.extractors.git_history.models import Commit, PR, PRComment


class GitHistoryTantivyWriter:
    """Async-friendly writer for the dedicated git_history Tantivy index.

    Schema fields:
      - doc_kind: "commit" | "pr" | "pr_comment"
      - project_id, doc_id, body, author_identity_key
      - ts (date), is_bot (stored as text "true"/"false")
    """

    def __init__(self, index_path: Path, heap_mb: int = 100) -> None:
        index_path.mkdir(parents=True, exist_ok=True)
        self._schema = self._build_schema()
        self._index = tantivy.Index(self._schema, str(index_path))
        self._heap_mb = heap_mb
        self._writer: tantivy.IndexWriter | None = None

    @staticmethod
    def _build_schema() -> tantivy.Schema:
        sb = tantivy.SchemaBuilder()
        sb.add_text_field("doc_kind", stored=True)
        sb.add_text_field("project_id", stored=True)
        sb.add_text_field("doc_id", stored=True, tokenizer_name="raw")
        sb.add_text_field("body", stored=True)
        sb.add_text_field("author_identity_key", stored=True)
        sb.add_date_field("ts", stored=True)
        sb.add_text_field("is_bot", stored=True)
        return sb.build()

    async def __aenter__(self) -> "GitHistoryTantivyWriter":
        self._writer = self._index.writer(self._heap_mb * 1_000_000)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._writer is not None:
            await asyncio.get_running_loop().run_in_executor(None, self._writer.commit)
            self._writer = None

    async def add_commit_async(self, commit: Commit, body_full: str) -> None:
        await self._add_doc({
            "doc_kind": "commit",
            "project_id": commit.project_id,
            "doc_id": commit.sha,
            "body": body_full[:65535],
            "author_identity_key": commit.author_identity_key,
            "ts": commit.committed_at,
            "is_bot": "false",
        })

    async def add_pr_async(self, pr: PR, body_full: str) -> None:
        await self._add_doc({
            "doc_kind": "pr",
            "project_id": pr.project_id,
            "doc_id": str(pr.number),
            "body": body_full[:65535],
            "author_identity_key": pr.author_identity_key,
            "ts": pr.created_at,
            "is_bot": "false",
        })

    async def add_pr_comment_async(self, comment: PRComment, body_full: str) -> None:
        await self._add_doc({
            "doc_kind": "pr_comment",
            "project_id": comment.project_id,
            "doc_id": comment.id,
            "body": body_full[:65535],
            "author_identity_key": comment.author_identity_key,
            "ts": comment.created_at,
            "is_bot": "false",
        })

    async def _add_doc(self, fields: dict) -> None:  # type: ignore[type-arg]
        if self._writer is None:
            raise RuntimeError("writer not opened (use async with)")
        doc = tantivy.Document()
        for k, v in fields.items():
            if k == "ts":
                doc.add_date(k, v)
            else:
                doc.add_text(k, str(v))
        await asyncio.get_running_loop().run_in_executor(
            None, self._writer.add_document, doc
        )

    def search_by_doc_id_sync(self, doc_id: str) -> list[dict]:  # type: ignore[type-arg]
        self._index.reload()
        searcher = self._index.searcher()
        query = self._index.parse_query(doc_id, ["doc_id"])
        results = searcher.search(query, 10).hits
        return [searcher.doc(hit[1]).to_dict() for hit in results]
