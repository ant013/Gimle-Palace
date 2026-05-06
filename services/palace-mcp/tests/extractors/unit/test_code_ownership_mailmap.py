from pathlib import Path

import pygit2
import pytest

from palace_mcp.extractors.code_ownership.mailmap import (
    MailmapResolver,
    MailmapResolverPath,
)


@pytest.fixture
def empty_repo(tmp_path) -> pygit2.Repository:
    repo_path = tmp_path / "empty_repo"
    repo_path.mkdir()
    return pygit2.init_repository(str(repo_path))


@pytest.fixture
def repo_with_mailmap(tmp_path) -> pygit2.Repository:
    repo_path = tmp_path / "repo_with_mailmap"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    (repo_path / ".mailmap").write_text(
        "Anton Stavnichiy <new@example.com> Anton S <old@example.com>\n",
        encoding="utf-8",
    )
    return repo


def test_resolver_identity_passthrough_on_empty_repo(empty_repo):
    resolver = MailmapResolver.from_repo(empty_repo, max_bytes=1_048_576)
    assert resolver.path == MailmapResolverPath.IDENTITY_PASSTHROUGH
    name, email = resolver.canonicalize("Anton S", "Old@Example.com")
    assert name == "Anton S"
    assert email == "old@example.com"  # always lowercased


def test_resolver_pygit2_canonicalizes_known_alias(repo_with_mailmap):
    resolver = MailmapResolver.from_repo(repo_with_mailmap, max_bytes=1_048_576)
    if resolver.path != MailmapResolverPath.PYGIT2:
        pytest.skip("pygit2.Mailmap not exposed by bound libgit2")
    name, email = resolver.canonicalize("Anton S", "old@example.com")
    assert name == "Anton Stavnichiy"
    assert email == "new@example.com"


def test_resolver_unknown_email_passes_through(repo_with_mailmap):
    resolver = MailmapResolver.from_repo(repo_with_mailmap, max_bytes=1_048_576)
    name, email = resolver.canonicalize("Other Human", "other@example.com")
    assert name == "Other Human"
    assert email == "other@example.com"


def test_resolver_size_cap_falls_back_to_identity(tmp_path):
    repo_path = tmp_path / "huge"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    # Write an oversized .mailmap (e.g., 2 KiB but cap is 1 KiB)
    (repo_path / ".mailmap").write_text("x" * 2048, encoding="utf-8")
    resolver = MailmapResolver.from_repo(repo, max_bytes=1024)
    assert resolver.path == MailmapResolverPath.IDENTITY_PASSTHROUGH


def test_resolver_email_always_lowercased(empty_repo):
    resolver = MailmapResolver.from_repo(empty_repo, max_bytes=1_048_576)
    _, email = resolver.canonicalize("X", "MixedCase@Example.COM")
    assert email == "mixedcase@example.com"
