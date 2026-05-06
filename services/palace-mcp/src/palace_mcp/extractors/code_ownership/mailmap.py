"""MailmapResolver — pygit2-only with identity passthrough fallback.

Per spec rev2 R3 / C3: no custom parser. Either pygit2.Mailmap (if
exposed by the bound libgit2) handles parsing, or we identity-pass.
.mailmap is checked-in repo content (untrusted); a custom parser
would split test surface and add attack surface.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import pygit2
from pathlib import Path

logger = logging.getLogger(__name__)


class MailmapResolverPath(StrEnum):
    PYGIT2 = "pygit2"
    IDENTITY_PASSTHROUGH = "identity_passthrough"


class MailmapResolver:
    """Resolve raw (name, email) → canonical (name, email)."""

    def __init__(
        self,
        path: MailmapResolverPath,
        pygit2_mailmap: object | None = None,
    ) -> None:
        self.path = path
        self._pygit2_mailmap = pygit2_mailmap

    @classmethod
    def from_repo(cls, repo: pygit2.Repository, *, max_bytes: int) -> "MailmapResolver":
        """Try pygit2.Mailmap; fall back to identity on any failure."""
        mailmap_file = Path(repo.workdir or repo.path) / ".mailmap"
        if not mailmap_file.is_file():
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        try:
            size = mailmap_file.stat().st_size
        except OSError:
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        if size > max_bytes:
            logger.info(
                "mailmap_unsupported: .mailmap size %d > cap %d for repo %s",
                size,
                max_bytes,
                repo.path,  # NEVER include emails in logs (PII rule §8)
            )
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)

        if not hasattr(pygit2, "Mailmap"):
            logger.info("mailmap_unsupported: pygit2.Mailmap not exposed")
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        try:
            mm = pygit2.Mailmap.from_repository(repo)
        except Exception as exc:  # broad: pygit2 raises various errors
            logger.info(
                "mailmap_unsupported: pygit2 raised %s on repo %s",
                type(exc).__name__,
                repo.path,
            )
            return cls(MailmapResolverPath.IDENTITY_PASSTHROUGH)
        return cls(MailmapResolverPath.PYGIT2, pygit2_mailmap=mm)

    def canonicalize(self, name: str, email: str) -> tuple[str, str]:
        """Return canonical (name, email_lc). Email always lowercased."""
        if self.path == MailmapResolverPath.PYGIT2 and self._pygit2_mailmap is not None:
            try:
                cn, ce = self._pygit2_mailmap.resolve(name, email)  # type: ignore[attr-defined]
                return cn, ce.lower()
            except Exception:
                pass  # fall through to identity
        return name, email.lower()
