"""Native git blame walker for HEAD attribution.

Builds dict[path, dict[canonical_id, BlameAttribution]] for the given
DIRTY paths. Skips files where blame fails (binary, symlink, submodule)
and returns no entry for the path.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone

import pygit2

from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver
from palace_mcp.extractors.code_ownership.models import BlameAttribution

logger = logging.getLogger(__name__)


def _parse_line_porcelain(raw: bytes) -> Iterator[tuple[str, str, int]]:
    current_name: bytes | None = None
    current_email: bytes | None = None
    current_time: int | None = None
    in_record = False

    for line in raw.splitlines():
        header = line.split(b" ", 1)[0]
        if len(header) == 40 and all(ch in b"0123456789abcdef" for ch in header.lower()):
            current_name = None
            current_email = None
            current_time = None
            in_record = True
            continue
        if not in_record:
            continue
        if line.startswith(b"\t"):
            if current_name is None or current_email is None or current_time is None:
                raise ValueError("blame porcelain missing author metadata")
            yield (
                current_name.decode("utf-8", errors="replace"),
                current_email.decode("utf-8", errors="replace"),
                current_time,
            )
            in_record = False
            continue

        key, sep, value = line.partition(b" ")
        if not sep:
            continue
        if key == b"author":
            current_name = value
        elif key == b"author-mail":
            current_email = value.removeprefix(b"<").removesuffix(b">")
        elif key == b"author-time":
            current_time = int(value)


def walk_blame(
    repo: pygit2.Repository,
    *,
    paths: Iterable[str],
    mailmap: MailmapResolver,
    bot_keys: set[str],
) -> tuple[dict[str, dict[str, BlameAttribution]], set[str]]:
    """Per-path, per-author blame line counts after mailmap + bot filter.

    Returns (blame_dict, binary_paths). Binary paths are omitted from
    blame_dict so the orchestrator can skip churn scoring for them too.
    """
    result: dict[str, dict[str, BlameAttribution]] = {}
    binary_paths: set[str] = set()
    head_oid = repo.head.target
    head_commit = repo[head_oid]
    workdir = repo.workdir or repo.path
    for path in paths:
        # Skip binary files: check for null bytes in blob content
        try:
            blob = repo[head_commit.tree[path].id]
            if isinstance(blob, pygit2.Blob) and blob.is_binary:
                binary_paths.add(path)
                continue
        except (KeyError, AttributeError):
            pass

        completed = subprocess.run(
            ["git", "-C", workdir, "blame", "--line-porcelain", "HEAD", "--", path],
            check=False,
            capture_output=True,
            shell=False,
        )
        if completed.returncode != 0:
            logger.info(
                "blame_failed: skipping path %s (exit %d)", path, completed.returncode
            )
            binary_paths.add(path)
            continue

        per_author: dict[str, BlameAttribution] = {}
        try:
            for raw_name, raw_email, author_time in _parse_line_porcelain(
                completed.stdout
            ):
                cn, ce = mailmap.canonicalize(raw_name, raw_email)
                canonical_id = ce  # already lowercased by resolver
                if canonical_id in bot_keys:
                    continue
                commit_time = datetime.fromtimestamp(author_time, tz=timezone.utc)
                existing = per_author.get(canonical_id)
                if existing is None:
                    per_author[canonical_id] = BlameAttribution(
                        canonical_id=canonical_id,
                        canonical_name=cn,
                        canonical_email=ce,
                        lines=1,
                        last_commit_at=commit_time,
                    )
                    continue
                per_author[canonical_id] = BlameAttribution(
                    canonical_id=canonical_id,
                    canonical_name=cn,
                    canonical_email=ce,
                    lines=existing.lines + 1,
                    last_commit_at=max(
                        existing.last_commit_at or commit_time, commit_time
                    ),
                )
        except ValueError as exc:
            logger.info("blame_failed: skipping path %s (%s)", path, type(exc).__name__)
            binary_paths.add(path)
            continue
        result[path] = per_author
    return result, binary_paths
