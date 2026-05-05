"""Build a deterministic synthetic git repo for the hotspot fixture.

Usage: python _build_fixture_repo.py <output_dir>

Copies src/ from this fixture into <output_dir>, initialises a git repo,
and creates 8 commits matching the CCN/churn expectations in REGEN.md.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pygit2

BASE_TS = 1746230400  # 2026-05-03 00:00 UTC — within 90-day window

FIXTURE_SRC = Path(__file__).parent / "src"


def _sig(offset_s: int = 0) -> pygit2.Signature:
    return pygit2.Signature("fixture", "fixture@test", BASE_TS + offset_s, 0)


def main(out_dir: str) -> None:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    src_dst = path / "src"
    shutil.copytree(FIXTURE_SRC, src_dst)

    repo = pygit2.init_repository(str(path), bare=False)
    repo.config["user.name"] = "fixture"
    repo.config["user.email"] = "fixture@test"

    def commit(message: str, parent_oids: list, offset_s: int) -> pygit2.Oid:
        repo.index.read()
        tree = repo.index.write_tree()
        return repo.create_commit(
            "refs/heads/main",
            _sig(offset_s),
            _sig(offset_s),
            message,
            tree,
            parent_oids,
        )

    tick = 0

    # Commit 1: python_simple
    repo.index.add("src/python_simple.py")
    repo.index.write()
    c1 = commit("init python_simple", [], tick)
    tick += 60

    # Commit 2: tweak python_simple
    (path / "src" / "python_simple.py").open("a").write("\n")
    repo.index.add("src/python_simple.py")
    repo.index.write()
    c2 = commit("tweak python_simple", [c1], tick)
    tick += 60

    # Commit 3: python_complex
    repo.index.add("src/python_complex.py")
    repo.index.write()
    c3 = commit("init python_complex", [c2], tick)
    tick += 60

    # Commits 4-6: three tweaks to python_complex
    prev = c3
    for i in range(1, 4):
        (path / "src" / "python_complex.py").open("a").write("\n")
        repo.index.add("src/python_complex.py")
        repo.index.write()
        prev = commit(f"tweak python_complex {i}", [prev], tick)
        tick += 60
    c6 = prev

    # Commit 7: main.kt
    repo.index.add("src/main.kt")
    repo.index.write()
    c7 = commit("init kotlin", [c6], tick)
    tick += 60

    # Commit 8: util.ts
    repo.index.add("src/util.ts")
    repo.index.write()
    commit("init ts", [c7], tick)

    repo.set_head("refs/heads/main")
    repo.checkout_head(strategy=pygit2.GIT_CHECKOUT_FORCE)
    print(f"Hotspot fixture repo built at {path} (8 commits)")


if __name__ == "__main__":
    main(sys.argv[1])
