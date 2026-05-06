"""pygit2.blame walker for HEAD attribution.

Builds dict[path, dict[canonical_id, BlameAttribution]] for the given
DIRTY paths. Skips files where pygit2.blame raises (binary, symlink,
submodule) — logs a warning, returns no entry for the path.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import pygit2

from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver
from palace_mcp.extractors.code_ownership.models import BlameAttribution

logger = logging.getLogger(__name__)


def walk_blame(
    repo: pygit2.Repository,
    *,
    paths: Iterable[str],
    mailmap: MailmapResolver,
    bot_keys: set[str],
) -> dict[str, dict[str, BlameAttribution]]:
    """Per-path, per-author blame line counts after mailmap + bot filter."""
    result: dict[str, dict[str, BlameAttribution]] = {}
    head_oid = repo.head.target
    for path in paths:
        # Skip binary files: check for null bytes in blob content
        try:
            head_commit = repo[head_oid]
            blob = repo[head_commit.tree[path].id]
            if isinstance(blob, pygit2.Blob) and blob.is_binary:
                result[path] = {}
                continue
        except (KeyError, AttributeError):
            pass

        try:
            blame = repo.blame(path, newest_commit=head_oid)
        except (pygit2.GitError, KeyError, ValueError) as exc:
            logger.info(
                "blame_failed: skipping path %s (%s)", path, type(exc).__name__
            )
            continue

        per_author: dict[str, BlameAttribution] = {}
        for hunk in blame:
            try:
                commit = repo[hunk.final_commit_id]
            except KeyError:
                continue
            raw_name = commit.author.name
            raw_email = commit.author.email
            cn, ce = mailmap.canonicalize(raw_name, raw_email)
            canonical_id = ce  # already lowercased by resolver
            if canonical_id in bot_keys:
                continue
            line_count = int(hunk.lines_in_hunk)
            existing = per_author.get(canonical_id)
            if existing is None:
                per_author[canonical_id] = BlameAttribution(
                    canonical_id=canonical_id,
                    canonical_name=cn,
                    canonical_email=ce,
                    lines=line_count,
                )
            else:
                per_author[canonical_id] = BlameAttribution(
                    canonical_id=canonical_id,
                    canonical_name=cn,
                    canonical_email=ce,
                    lines=existing.lines + line_count,
                )
        result[path] = per_author
    return result
