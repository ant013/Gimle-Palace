"""pygit2 commit walker — see spec GIM-186 §5.1 Phase 1."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pygit2

# Allow opening repos owned by other users — bind mounts in Docker often present
# as root-owned inside the container even when the process runs as non-root.
# Mirrors the GIT_CONFIG_VALUE_0=* safe.directory approach used by palace.git.* tools.
pygit2.option(pygit2.GIT_OPT_SET_OWNER_VALIDATION, False)  # type: ignore[call-overload]


class CommitNotFoundError(Exception):
    """Raised when checkpoint sha is not found in repo (e.g. force-push)."""


class Pygit2Walker:
    """Synchronous walker; caller wraps in async generator."""

    def __init__(self, repo_path: Path) -> None:
        self._repo = pygit2.Repository(str(repo_path))

    def head_sha(self) -> str:
        return str(self._repo.head.target)

    def walk_since(self, last_sha: str | None) -> Iterator[dict]:  # type: ignore[type-arg]
        """Yield dicts representing commits newer than last_sha (exclusive).

        If last_sha is None, yield ALL commits (full walk).
        Order: most-recent first.
        """
        if last_sha is not None:
            try:
                obj = self._repo.get(last_sha)
                if obj is None:
                    raise CommitNotFoundError(f"sha not in repo: {last_sha}")
            except (KeyError, ValueError) as exc:
                raise CommitNotFoundError(f"sha not in repo: {last_sha}") from exc

        for commit in self._repo.walk(self._repo.head.target, pygit2.GIT_SORT_TIME):  # type: ignore[arg-type]
            sha = str(commit.id)
            if last_sha is not None and sha == last_sha:
                break
            yield self._commit_to_dict(commit)

    @staticmethod
    def _commit_to_dict(commit: pygit2.Commit) -> dict:  # type: ignore[type-arg]
        author = commit.author
        committer = commit.committer
        message = commit.message
        subject = message.split("\n", 1)[0][:200]
        full_truncated = message[:1024] + ("..." if len(message) > 1024 else "")
        ts = datetime.fromtimestamp(commit.commit_time, tz=timezone.utc)
        # Touched files via diff against parent
        touched: list[str]
        if commit.parents:
            diff = commit.tree.diff_to_tree(commit.parents[0].tree)
            touched = [d.delta.new_file.path for d in diff if d is not None]
        else:
            # Root commit: iterate tree entries directly
            touched = [entry.name for entry in commit.tree if entry.name is not None]
        return {
            "sha": str(commit.id),
            "author_email": author.email,
            "author_name": author.name,
            "committer_email": committer.email,
            "committer_name": committer.name,
            "message_subject": subject,
            "message_full_truncated": full_truncated,
            "committed_at": ts,
            "parents": tuple(str(p) for p in commit.parent_ids),
            "touched_files": touched,
        }
