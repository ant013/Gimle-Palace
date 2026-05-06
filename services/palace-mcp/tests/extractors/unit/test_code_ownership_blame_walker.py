import pygit2
import pytest

from palace_mcp.extractors.code_ownership.blame_walker import walk_blame
from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver


@pytest.fixture
def mini_repo(tmp_path) -> pygit2.Repository:
    """3 commits, 2 authors, 2 files (one text, one binary).

    File 1: 'a.py' — author1 writes 4 lines, author2 modifies 2 of them.
    File 2: 'b.bin' — binary, contains \\x00 bytes; blame must skip.
    """
    repo_path = tmp_path / "mini"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    sig1 = pygit2.Signature("Author One", "a1@example.com", 1_700_000_000, 0)
    sig2 = pygit2.Signature("Author Two", "a2@example.com", 1_700_001_000, 0)

    def commit(
        msg: str, files: dict[str, bytes], parents: list, sig: pygit2.Signature
    ) -> str:
        for name, data in files.items():
            (repo_path / name).write_bytes(data)
            repo.index.add(name)
        repo.index.write()
        tree = repo.index.write_tree()
        oid = repo.create_commit("HEAD", sig, sig, msg, tree, parents)
        return str(oid)

    sha1 = commit(
        "init",
        {"a.py": b"line1\nline2\nline3\nline4\n", "b.bin": b"\x00\x01\x02"},
        [],
        sig1,
    )
    head_oid = pygit2.Oid(hex=sha1)
    commit(
        "modify a.py",
        {"a.py": b"line1\nLINE2_modified\nLINE3_modified\nline4\n"},
        [head_oid],
        sig2,
    )
    return repo


def test_walk_blame_attributes_lines_to_two_authors(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    blame_dict, binary_paths = walk_blame(
        mini_repo,
        paths={"a.py"},
        mailmap=resolver,
        bot_keys=set(),
    )
    assert "a.py" in blame_dict
    by_author = {b.canonical_id: b.lines for b in blame_dict["a.py"].values()}
    # Author One wrote lines 1+4 (2 lines), Author Two rewrote 2+3 (2 lines)
    assert by_author["a1@example.com"] == 2
    assert by_author["a2@example.com"] == 2
    assert "a.py" not in binary_paths


def test_walk_blame_skips_binary(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    blame_dict, binary_paths = walk_blame(
        mini_repo,
        paths={"b.bin"},
        mailmap=resolver,
        bot_keys=set(),
    )
    # Binary path reported in binary_paths, not in blame_dict
    assert "b.bin" in binary_paths
    assert "b.bin" not in blame_dict


def test_walk_blame_excludes_bots(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    blame_dict, binary_paths = walk_blame(
        mini_repo,
        paths={"a.py"},
        mailmap=resolver,
        bot_keys={"a2@example.com"},  # treat Author Two as bot
    )
    by_author = {b.canonical_id: b.lines for b in blame_dict["a.py"].values()}
    assert "a2@example.com" not in by_author
    assert by_author["a1@example.com"] == 2  # only the lines author1 still owns
