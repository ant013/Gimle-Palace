"""Build a deterministic synthetic git repository for git_history fixture.

Usage: python _build_synth_repo.py <output_dir>

Produces:
  5 commits, 2 authors (1 human + github-actions[bot])
  1 merge commit (c4 has 2 parents)
"""

import sys
from pathlib import Path

import pygit2

BASE_TS = 1746230400  # 2025-05-03 12:00 UTC


def _sig(name: str, email: str, offset_s: int = 0) -> pygit2.Signature:
    return pygit2.Signature(name, email, BASE_TS + offset_s, 0)


def main(out_dir: str) -> None:
    path = Path(out_dir)
    repo = pygit2.init_repository(str(path), bare=False)

    human = ("Foo Human", "foo@example.com")
    bot = ("github-actions[bot]", "github-actions[bot]@users.noreply.github.com")

    # Commit 1: initial — human
    (path / "file1.txt").write_text("hello\n")
    repo.index.add("file1.txt")
    repo.index.write()
    tree1 = repo.index.write_tree()
    c1 = repo.create_commit(
        "refs/heads/main",
        _sig(*human, 0),
        _sig(*human, 0),
        "Initial commit",
        tree1,
        [],
    )

    # Commit 2: add file2 — bot
    (path / "file2.txt").write_text("world\n")
    repo.index.add("file2.txt")
    repo.index.write()
    tree2 = repo.index.write_tree()
    c2 = repo.create_commit(
        "refs/heads/main",
        _sig(*bot, 60),
        _sig(*bot, 60),
        "Add file2.txt",
        tree2,
        [c1],
    )

    # Commit 3 (topic tip): human adds file3 starting from tree1 (separate branch)
    builder = repo.TreeBuilder(repo.get(tree1))
    blob3 = repo.create_blob(b"file3 content\n")
    builder.insert("file3.txt", blob3, pygit2.GIT_FILEMODE_BLOB)
    tree3 = builder.write()
    c3 = repo.create_commit(
        "refs/heads/topic",
        _sig(*human, 90),
        _sig(*human, 90),
        "Add file3.txt on topic",
        tree3,
        [c1],
    )

    # Commit 4 — merge (2 parents: c2 + c3); use tree2 content
    c4 = repo.create_commit(
        "refs/heads/main",
        _sig(*human, 180),
        _sig(*human, 180),
        "Merge branch 'topic'",
        tree2,
        [c2, c3],
    )

    # Commit 5 — human, normal commit
    repo.index.read_tree(repo.get(tree2))
    (path / "final.txt").write_text("final\n")
    repo.index.add("final.txt")
    repo.index.write()
    tree5 = repo.index.write_tree()
    c5 = repo.create_commit(
        "refs/heads/main",
        _sig(*human, 240),
        _sig(*human, 240),
        "Final commit",
        tree5,
        [c4],
    )

    # Point HEAD to main
    repo.set_head("refs/heads/main")
    repo.checkout_head(strategy=pygit2.GIT_CHECKOUT_FORCE)

    print(f"Synthetic repo created at {path} with HEAD {c5}")


if __name__ == "__main__":
    main(sys.argv[1])
