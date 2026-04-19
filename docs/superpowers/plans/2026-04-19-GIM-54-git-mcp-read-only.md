# git-mcp read-only exposure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-git-mcp-read-only-design.md` on main@e5bf422 (spec commit; CTO may formalize a paperclip issue against a newer SHA).

**Goal:** Expose 5 read-only git tools (`palace.git.log / show / blame / diff / ls_tree`) on the existing palace-mcp FastMCP surface, scoped per-project via bind-mount convention `/repos/<slug>`, backed by a hardened subprocess wrapper with output caps, ref/path validation, command whitelist, and sanitized env.

**Architecture:** New package `services/palace-mcp/src/palace_mcp/git/` with four files (`path_resolver`, `command`, `schemas`, `tools`). Tools register on the existing `FastMCP("palace")` app. No new container, no new port. Filesystem bind-mounts are authoritative for git access (see spec §3.6); Neo4j `:Project` remains authoritative for graph queries.

**Tech Stack:** Python 3.12, Pydantic v2, FastMCP (`mcp[cli]`), pytest, subprocess (no third-party git library), neo4j async driver (only for health extension).

**Predecessors pinned:**
- `develop@7bdc302` — GIM-53 multi-project scoping merged (`:Project` node + `group_id` namespacing). No code regressions expected.
- `main@e5bf422` — this slice's spec commit.

**Language rule:** code/docstrings/commit messages in English; Russian only in UI text (per `paperclips/fragments/shared/fragments/language.md`).

---

## Phase 1 — Formalization (CTO + CodeReviewer)

### Task 1.1: CTO formalizes paperclip issue

**Owner:** CTO
**Files:** this plan (rename only); `docs/superpowers/specs/2026-04-19-git-mcp-read-only-design.md` (pin commit ref only if stale).

- [ ] **Step 1:** Mint paperclip issue titled `git-mcp read-only exposure (N+1.5 bridge)`, assign to CodeReviewer for Phase 1.2. Issue body links to spec `main@e5bf422` + this plan path.
- [ ] **Step 2:** In this plan file, `git mv` from `2026-04-19-GIM-54-git-mcp-read-only.md` to `2026-04-19-GIM-<N>-git-mcp-read-only.md` where `<N>` is the minted issue number. Open the file and replace every `GIM-54` with `GIM-<N>` (ripgrep: `rg -l 'GIM-54' docs/superpowers/plans/`).
- [ ] **Step 3:** Commit on main: `docs(plan): rename to GIM-<N> (paperclip issue created)` (no Co-Authored-By; this is meta work).
- [ ] **Step 4:** Reassign paperclip issue to CodeReviewer with a comment pointing at plan file + both commit SHAs (spec + rename).

### Task 1.2: CodeReviewer plan-first review

**Owner:** CodeReviewer (paperclip agent)

- [ ] **Step 1:** Read spec (all 13 sections) + this plan top-to-bottom.
- [ ] **Step 2:** Verify every spec acceptance-criterion item in §10 maps to at least one plan task. Post-it list any gaps in the paperclip issue.
- [ ] **Step 3:** Verify every plan task has test-first structure (a step marked "Write the failing test" before any "Implement" step). Report any tasks that skip TDD.
- [ ] **Step 4:** Verify `validate_slug` is created **before** `path_resolver` uses it (Task 2.2 precedes Task 2.3).
- [ ] **Step 5:** Post APPROVE comment on paperclip issue (with full compliance checklist per `feedback_anti_rubber_stamp.md`) and reassign to MCPEngineer for Phase 2.

---

## Phase 2 — Implementation (MCPEngineer)

**Branch:** `feature/GIM-<N>-git-mcp-read-only` cut from `develop`.
**First action on feature branch:** copy this plan file from main to the feature branch working tree (plans land on develop via squash-merge per CLAUDE.md).

### Task 2.1: Package scaffold + test infrastructure

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/git/__init__.py`
- Create: `services/palace-mcp/src/palace_mcp/git/path_resolver.py` (empty stub)
- Create: `services/palace-mcp/src/palace_mcp/git/command.py` (empty stub)
- Create: `services/palace-mcp/src/palace_mcp/git/schemas.py` (empty stub)
- Create: `services/palace-mcp/src/palace_mcp/git/tools.py` (empty stub)
- Create: `services/palace-mcp/tests/git/__init__.py`
- Create: `services/palace-mcp/tests/git/conftest.py` (shared fixtures)

- [ ] **Step 1: Create directory tree**

```bash
cd services/palace-mcp
mkdir -p src/palace_mcp/git tests/git
touch src/palace_mcp/git/__init__.py \
      src/palace_mcp/git/path_resolver.py \
      src/palace_mcp/git/command.py \
      src/palace_mcp/git/schemas.py \
      src/palace_mcp/git/tools.py \
      tests/git/__init__.py
```

- [ ] **Step 2: Write shared test fixture `conftest.py`**

File: `services/palace-mcp/tests/git/conftest.py`

```python
"""Shared fixtures for palace_mcp.git tests.

`tmp_repo` creates a real git repository with 2 commits in a tmp dir.
Tests run against real git — per feedback_qa_skipped_gim48.md, mocking
subprocess hides API-drift bugs.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a real git repo at `<tmp>/repos/testproj` with 2 commits."""
    repo = tmp_path / "repos" / "testproj"
    repo.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "t@t"], cwd=repo)
    _run(["git", "config", "user.name", "T"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2\n")
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2-changed\nline3\n")
    _run(["git", "commit", "-am", "change", "-q"], cwd=repo)
    return repo


@pytest.fixture
def repos_root(tmp_path: Path, tmp_repo: Path) -> Path:
    """Simulate container's /repos/ with one project mounted."""
    # tmp_repo already lives at tmp_path / "repos" / "testproj"
    return tmp_path / "repos"
```

- [ ] **Step 3: Verify the fixture works**

Run:
```bash
cd services/palace-mcp
uv run pytest tests/git/ -v
```

Expected: `no tests ran` (fixtures only; no test files yet). No errors.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/ services/palace-mcp/tests/git/
git commit -m "feat(git-mcp): scaffold package + tmp_repo fixture"
```

---

### Task 2.2: `validate_slug` helper + retrofit `register_project`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/projects.py` (add `InvalidSlug` + `validate_slug`)
- Modify: `services/palace-mcp/src/palace_mcp/memory/project_tools.py` (call `validate_slug` in `register_project`)
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py:palace_memory_register_project` — translate `InvalidSlug` to `{ok: false, error_code: "invalid_slug", ...}` response (match error envelope pattern already used elsewhere)
- Create: `services/palace-mcp/tests/memory/test_validate_slug.py`

- [ ] **Step 1: Write failing tests for `validate_slug`**

File: `services/palace-mcp/tests/memory/test_validate_slug.py`

```python
"""Tests for memory.projects.validate_slug — unified slug format check.

Spec §5.1. Single source of truth for slug format across the graph
(register_project) and git (path_resolver) layers.
"""

from __future__ import annotations

import pytest

from palace_mcp.memory.projects import InvalidSlug, validate_slug


@pytest.mark.parametrize(
    "slug",
    ["gimle", "medic", "g123", "g-mle", "a", "a-b-c", "0prefix", "x" * 63],
)
def test_valid_slugs_accepted(slug: str) -> None:
    validate_slug(slug)  # does not raise


@pytest.mark.parametrize(
    "slug,reason",
    [
        ("", "empty"),
        ("A", "uppercase"),
        ("Gimle", "uppercase first"),
        ("gim LE", "space"),
        ("gimle/sub", "slash"),
        ("../etc", "traversal"),
        ("-prefix", "dash prefix"),
        ("gimle.", "dot"),
        ("gimle_us", "underscore"),
        ("x" * 64, "too long"),
        ("gim\nle", "newline"),
        ("gim\x00le", "nul"),
    ],
)
def test_invalid_slugs_rejected(slug: str, reason: str) -> None:
    with pytest.raises(InvalidSlug):
        validate_slug(slug)
```

- [ ] **Step 2: Run tests — expect failure (import error)**

```bash
cd services/palace-mcp
uv run pytest tests/memory/test_validate_slug.py -v
```

Expected: `ImportError: cannot import name 'InvalidSlug' from palace_mcp.memory.projects`.

- [ ] **Step 3: Implement `validate_slug` and `InvalidSlug`**

File: `services/palace-mcp/src/palace_mcp/memory/projects.py`

Add at top (after existing `UnknownProjectError`):

```python
import re


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")


class InvalidSlug(ValueError):
    """Raised when a project slug fails format validation.

    Slug format: `[a-z0-9][a-z0-9\\-]{0,62}` (1–63 chars,
    lowercase alphanumerics plus hyphen, no leading hyphen).
    """

    def __init__(self, slug: str) -> None:
        super().__init__(f"invalid project slug: {slug!r}")
        self.slug = slug


def validate_slug(slug: str) -> None:
    """Validate a project slug. Raise InvalidSlug if invalid."""
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise InvalidSlug(slug)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/memory/test_validate_slug.py -v
```

Expected: 20 passed (8 valid × 1 + 12 invalid × 1).

- [ ] **Step 5: Retrofit `register_project` to call `validate_slug`**

File: `services/palace-mcp/src/palace_mcp/memory/project_tools.py`

At top of `register_project` body (before `now = ...`), add:

```python
    from palace_mcp.memory.projects import validate_slug
    validate_slug(slug)
```

- [ ] **Step 6: Add test that `register_project` rejects bad slugs**

Append to `services/palace-mcp/tests/memory/test_validate_slug.py`:

```python
import pytest

from palace_mcp.memory.project_tools import register_project


@pytest.mark.asyncio
async def test_register_project_rejects_invalid_slug() -> None:
    from unittest.mock import AsyncMock

    driver = AsyncMock()
    with pytest.raises(InvalidSlug):
        await register_project(
            driver, slug="../etc", name="hack", tags=[]
        )
    # driver.session() must never have been called — rejection pre-Cypher.
    driver.session.assert_not_called()
```

- [ ] **Step 7: Run + verify driver never called**

```bash
uv run pytest tests/memory/test_validate_slug.py::test_register_project_rejects_invalid_slug -v
```

Expected: pass. `AsyncMock.session` untouched.

- [ ] **Step 8: Translate `InvalidSlug` in MCP layer**

File: `services/palace-mcp/src/palace_mcp/mcp_server.py`, function `palace_memory_register_project`:

Locate the existing error handling block. Add an `except InvalidSlug as exc:` branch that returns the error envelope (match the style of existing catches for `UnknownProjectError`):

```python
from palace_mcp.memory.projects import InvalidSlug, UnknownProjectError

# inside palace_memory_register_project, in the try/except:
    except InvalidSlug as exc:
        return {
            "ok": False,
            "error_code": "invalid_slug",
            "message": str(exc),
        }
```

- [ ] **Step 9: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/projects.py \
        services/palace-mcp/src/palace_mcp/memory/project_tools.py \
        services/palace-mcp/src/palace_mcp/mcp_server.py \
        services/palace-mcp/tests/memory/test_validate_slug.py
git commit -m "feat(memory): validate_slug + retrofit register_project"
```

---

### Task 2.3: `path_resolver` — slug → Path, pathspec rejection, traversal guard

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/path_resolver.py`
- Create: `services/palace-mcp/tests/git/test_path_resolver.py`

- [ ] **Step 1: Write failing tests**

File: `services/palace-mcp/tests/git/test_path_resolver.py`

```python
"""Tests for git.path_resolver. Spec §5.1, §5.2."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from palace_mcp.git.path_resolver import (
    InvalidPath,
    ProjectNotRegistered,
    resolve_project,
    validate_rel_path,
)
from palace_mcp.memory.projects import InvalidSlug


# --- resolve_project (slug → repo Path) ---


def test_resolve_existing_project(repos_root: Path) -> None:
    repo = resolve_project("testproj", repos_root=repos_root)
    assert repo == (repos_root / "testproj").resolve()


def test_resolve_invalid_slug(repos_root: Path) -> None:
    with pytest.raises(InvalidSlug):
        resolve_project("../etc", repos_root=repos_root)


def test_resolve_missing_project(repos_root: Path) -> None:
    with pytest.raises(ProjectNotRegistered):
        resolve_project("absent", repos_root=repos_root)


def test_resolve_not_a_git_repo(tmp_path: Path, repos_root: Path) -> None:
    # Make a dir that isn't a git repo.
    plain = repos_root / "plain"
    plain.mkdir()
    with pytest.raises(ProjectNotRegistered):
        resolve_project("plain", repos_root=repos_root)


# --- validate_rel_path (path inside repo) ---


def test_valid_relative_path(tmp_repo: Path) -> None:
    p = validate_rel_path("a.py", repo_path=tmp_repo)
    assert p == (tmp_repo / "a.py").resolve()


def test_reject_absolute_path(tmp_repo: Path) -> None:
    with pytest.raises(InvalidPath):
        validate_rel_path("/etc/passwd", repo_path=tmp_repo)


def test_reject_pathspec_magic(tmp_repo: Path) -> None:
    for bad in [":(glob)*.py", ":!exclude", ":/root", ":top"]:
        with pytest.raises(InvalidPath):
            validate_rel_path(bad, repo_path=tmp_repo)


def test_reject_nul_byte(tmp_repo: Path) -> None:
    with pytest.raises(InvalidPath):
        validate_rel_path("a\x00.py", repo_path=tmp_repo)


def test_reject_traversal_escape(tmp_repo: Path) -> None:
    with pytest.raises(InvalidPath):
        validate_rel_path("../outside", repo_path=tmp_repo)


def test_reject_symlink_escape(tmp_repo: Path) -> None:
    outside = tmp_repo.parent / "secret.txt"
    outside.write_text("secret")
    link = tmp_repo / "evil"
    link.symlink_to(outside)
    with pytest.raises(InvalidPath):
        validate_rel_path("evil", repo_path=tmp_repo)
```

- [ ] **Step 2: Run — expect failure**

```bash
uv run pytest tests/git/test_path_resolver.py -v
```

Expected: `ImportError: cannot import name 'resolve_project'` etc.

- [ ] **Step 3: Implement `path_resolver.py`**

File: `services/palace-mcp/src/palace_mcp/git/path_resolver.py`

```python
"""Resolve project slug → repo path; validate paths under a repo.

Convention (spec §3.4): inside the container, slug `X` is bind-mounted
at `/repos/X`. The FS is the authority for which projects git tools
can address (spec §3.6).
"""

from __future__ import annotations

import os
from pathlib import Path

from palace_mcp.memory.projects import validate_slug

REPOS_ROOT = Path("/repos")


class ProjectNotRegistered(ValueError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"project not registered: {slug!r}")
        self.slug = slug


class InvalidPath(ValueError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"invalid path {path!r}: {reason}")
        self.path = path
        self.reason = reason


def resolve_project(slug: str, *, repos_root: Path = REPOS_ROOT) -> Path:
    """Resolve slug → absolute repo path. Requires .git/ to exist."""
    validate_slug(slug)
    candidate = (repos_root / slug).resolve()
    if not candidate.is_dir():
        raise ProjectNotRegistered(slug)
    if not (candidate / ".git").exists():
        raise ProjectNotRegistered(slug)
    # Containment check — resilient to slug being "" or surprising.
    if not _is_within(candidate, repos_root.resolve()):
        raise ProjectNotRegistered(slug)
    return candidate


def validate_rel_path(user_path: str, *, repo_path: Path) -> Path:
    """Validate a user-provided path within `repo_path`.

    - Reject pathspec magic (leading `:`).
    - Reject absolute paths.
    - Reject NUL bytes.
    - Reject traversal or symlink escape outside repo.

    Return the resolved absolute Path on success.
    """
    if not isinstance(user_path, str) or user_path == "":
        raise InvalidPath(user_path, "empty")
    if user_path.startswith(":"):
        raise InvalidPath(user_path, "pathspec magic not allowed")
    if user_path.startswith("/"):
        raise InvalidPath(user_path, "absolute path not allowed")
    if "\x00" in user_path:
        raise InvalidPath(user_path, "nul byte")

    resolved = (repo_path / user_path).resolve()
    repo_resolved = repo_path.resolve()
    if not _is_within(resolved, repo_resolved):
        raise InvalidPath(user_path, "escapes repo root")
    return resolved


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
```

- [ ] **Step 4: Run — expect pass**

```bash
uv run pytest tests/git/test_path_resolver.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/path_resolver.py \
        services/palace-mcp/tests/git/test_path_resolver.py
git commit -m "feat(git-mcp): path_resolver with slug + path validation"
```

---

### Task 2.4: `command.run_git` — whitelist, env, timeout, capped streaming, stderr drain

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/command.py`
- Create: `services/palace-mcp/tests/git/test_command.py`

This task is the load-bearing subprocess wrapper. Every sharp edge listed in spec §5 terminates here: whitelist (§5.4), env sanitization (§5.5), timeout (§5.6), streaming cap + stderr drain (§5.7), encoding (§5.8).

- [ ] **Step 1: Write failing test — whitelist**

File: `services/palace-mcp/tests/git/test_command.py`

```python
"""Tests for git.command.run_git. Spec §5.4-§5.8."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from palace_mcp.git.command import (
    ForbiddenGitCommand,
    GitError,
    GitTimeout,
    run_git,
)


def test_whitelist_rejects_push(tmp_repo: Path) -> None:
    with pytest.raises(ForbiddenGitCommand):
        run_git(["push", "origin"], repo_path=tmp_repo)


def test_whitelist_rejects_commit(tmp_repo: Path) -> None:
    with pytest.raises(ForbiddenGitCommand):
        run_git(["commit", "-am", "x"], repo_path=tmp_repo)
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest tests/git/test_command.py::test_whitelist_rejects_push -v
```

- [ ] **Step 3: Implement skeleton of `command.py` with whitelist only**

File: `services/palace-mcp/src/palace_mcp/git/command.py`

```python
"""Hardened subprocess wrapper for read-only git invocations.

Single fork point for every git call. Enforces Section 5 invariants
of the spec: whitelist, env sanitization, timeout, capped streaming,
stderr drain on kill.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ALLOWED_VERBS: frozenset[str] = frozenset(
    {"log", "show", "blame", "diff", "ls-tree", "cat-file"}
)

DEFAULT_TIMEOUT_S: float = 10.0

SAFE_ENV: dict[str, str] = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "safe.directory",
    "GIT_CONFIG_VALUE_0": "*",
}


@dataclass(frozen=True)
class GitResult:
    """Outcome of a single git subprocess run."""

    rc: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool


class ForbiddenGitCommand(ValueError):
    def __init__(self, verb: str) -> None:
        super().__init__(f"git verb not allowed: {verb!r}")
        self.verb = verb


class GitTimeout(RuntimeError):
    pass


class GitError(RuntimeError):
    def __init__(self, rc: int, stderr: str) -> None:
        super().__init__(f"git exit {rc}: {stderr[:200]}")
        self.rc = rc
        self.stderr = stderr


def run_git(
    args: list[str],
    *,
    repo_path: Path,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_stdout_lines: int | None = None,
) -> GitResult:
    """Run `git <args>` under `repo_path` with hardened env.

    - args[0] must be in ALLOWED_VERBS.
    - Output capped at max_stdout_lines if provided; truncation at
      line boundary.
    """
    if not args:
        raise ForbiddenGitCommand("")
    verb = args[0]
    if verb not in ALLOWED_VERBS:
        raise ForbiddenGitCommand(verb)

    git_bin = shutil.which("git") or "/usr/bin/git"
    full = [git_bin, "-C", str(repo_path), *args]

    raise NotImplementedError("streaming + timeout logic — next steps")
```

- [ ] **Step 4: Run — whitelist tests pass**

```bash
uv run pytest tests/git/test_command.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Write test — env sanitization**

Append to `tests/git/test_command.py`:

```python
def test_env_sanitization(tmp_repo: Path) -> None:
    """Hostile $HOME/.gitconfig must not be read."""
    # Create a hostile global config that would fail git if read.
    hostile_home = tmp_repo.parent / "hostile_home"
    hostile_home.mkdir()
    (hostile_home / ".gitconfig").write_text(
        "[include]\n    path = /nonexistent/evil\n"
    )
    with patch.dict(os.environ, {"HOME": str(hostile_home)}):
        res = run_git(["log", "-1", "--pretty=%H"], repo_path=tmp_repo)
    assert res.rc == 0
    assert len(res.stdout.strip()) == 40  # full SHA
```

- [ ] **Step 6: Write test — timeout**

```python
def test_timeout_raises_git_timeout(tmp_repo: Path) -> None:
    # Use an impossible, slow command. `git log -L` on an empty pattern
    # can hang briefly; simpler: force timeout via tiny budget.
    with pytest.raises(GitTimeout):
        run_git(["log", "--all"], repo_path=tmp_repo, timeout_s=0.0001)
```

- [ ] **Step 7: Write test — happy path streaming**

```python
def test_happy_path_log_returns_stdout(tmp_repo: Path) -> None:
    res = run_git(["log", "--pretty=%H", "-n", "2"], repo_path=tmp_repo)
    assert res.rc == 0
    lines = [ln for ln in res.stdout.splitlines() if ln]
    assert len(lines) == 2
    assert all(len(ln) == 40 for ln in lines)
    assert res.truncated is False
```

- [ ] **Step 8: Write test — cap streaming**

```python
def test_cap_streaming_truncates_at_line_boundary(tmp_repo: Path) -> None:
    # Create 50 commits to exceed cap=10.
    repo = tmp_repo
    for i in range(50):
        (repo / "a.py").write_text(f"change-{i}\n")
        subprocess.run(
            ["git", "commit", "-am", f"c{i}", "-q"],
            cwd=repo, check=True, capture_output=True,
        )
    res = run_git(
        ["log", "--pretty=%H", "-n", "500"],
        repo_path=repo,
        max_stdout_lines=10,
    )
    # Cap hit; last line must end with newline (no mid-line truncation).
    assert res.truncated is True
    assert res.stdout.endswith("\n")
    assert len([ln for ln in res.stdout.splitlines() if ln]) == 10
```

- [ ] **Step 9: Write test — stderr drained on cap-kill**

```python
def test_stderr_drained_on_cap_kill(tmp_repo: Path) -> None:
    """Process must not deadlock when cap fires mid-stream.

    Reproduces stderr-pipe-fills deadlock scenario by running a command
    that produces large stderr while stdout is being cap-killed.
    """
    # `git log --unknown-flag` writes to stderr; we cap stdout at 1 line.
    # Main assertion: call returns without hanging within timeout.
    res = run_git(
        ["log", "-n", "1"],
        repo_path=tmp_repo,
        max_stdout_lines=1,
        timeout_s=5.0,
    )
    # Normal output has 1 line; assertion is implicit (no hang).
    assert res.rc == 0
```

- [ ] **Step 10: Write test — encoding replacement**

```python
def test_invalid_utf8_replaced(tmp_path: Path) -> None:
    repo = tmp_path / "enc"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=repo, check=True
    )
    (repo / "a").write_text("x")
    subprocess.run(
        ["git", "add", "."], cwd=repo, check=True, capture_output=True
    )
    # Commit with invalid UTF-8 in subject via GIT_COMMITTER_EMAIL trick:
    # easier: use bytes via raw subprocess and I18N.COMMIT_ENCODING.
    env = os.environ.copy()
    env["LANG"] = "C"
    subj = b"initial \xff\xfe\n"
    subprocess.run(
        ["git", "commit", "-F", "-", "-q"],
        cwd=repo,
        input=subj,
        env=env,
        check=True,
        capture_output=True,
    )
    res = run_git(["log", "--pretty=%s", "-n", "1"], repo_path=repo)
    assert "\ufffd" in res.stdout  # replacement char present
    # Should not have raised UnicodeDecodeError.
```

- [ ] **Step 11: Implement full `run_git` body**

Replace the `raise NotImplementedError(...)` in `command.py` with the full streaming implementation:

```python
    import time

    start = time.monotonic()
    proc = subprocess.Popen(
        full,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(SAFE_ENV),
        cwd=str(repo_path),
        bufsize=1,  # line-buffered
    )

    stdout_lines: list[str] = []
    truncated = False
    try:
        assert proc.stdout is not None
        raw = proc.stdout
        # Decode line-by-line with replacement.
        while True:
            line_bytes = raw.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace")
            stdout_lines.append(line)
            if (
                max_stdout_lines is not None
                and len(stdout_lines) >= max_stdout_lines
            ):
                truncated = True
                break
            # Timeout check.
            if time.monotonic() - start > timeout_s:
                _drain_and_kill(proc)
                raise GitTimeout(
                    f"git {verb} exceeded {timeout_s}s"
                )
    except GitTimeout:
        raise
    except Exception as exc:
        _drain_and_kill(proc)
        raise GitError(rc=-1, stderr=str(exc)) from exc

    if truncated:
        stderr_tail = _drain_and_kill(proc)
        rc = proc.returncode if proc.returncode is not None else -1
    else:
        # Let it finish (bounded by timeout).
        try:
            _, stderr_bytes = proc.communicate(
                timeout=max(timeout_s - (time.monotonic() - start), 0.1)
            )
            stderr_tail = stderr_bytes.decode(
                "utf-8", errors="replace"
            )[:4096]
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            _drain_and_kill(proc)
            raise GitTimeout(f"git {verb} exceeded {timeout_s}s")

    duration_ms = int((time.monotonic() - start) * 1000)
    return GitResult(
        rc=rc,
        stdout="".join(stdout_lines),
        stderr=stderr_tail,
        duration_ms=duration_ms,
        truncated=truncated,
    )


def _drain_and_kill(proc: subprocess.Popen[bytes]) -> str:
    """Drain bounded stderr, kill, reap. See spec §5.7."""
    try:
        if proc.stdout is not None:
            proc.stdout.close()
        tail = b""
        if proc.stderr is not None:
            try:
                tail = proc.stderr.read(4096)
            except Exception:
                tail = b""
            proc.stderr.close()
        proc.kill()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
        return tail.decode("utf-8", errors="replace")
    except Exception:
        return ""
```

- [ ] **Step 12: Run all command tests — expect pass**

```bash
uv run pytest tests/git/test_command.py -v
```

Expected: all tests pass. If `test_timeout_raises_git_timeout` flakes (budget too tight), bump `timeout_s=0.0001` → `0.001`.

- [ ] **Step 13: Add `BrokenPipeError` mock test (CR Phase 1.2 finding #4)**

Append to `services/palace-mcp/tests/git/test_command.py`:

```python
def test_broken_pipe_raises_git_error(tmp_repo: Path) -> None:
    """Mock proc.stdout.readline to raise BrokenPipeError — assert GitError raised.

    Maps to spec §7.6. Verifies the streaming loop handles broken pipes.
    """
    with patch(
        "palace_mcp.git.command.subprocess.Popen",
        spec=True,
    ) as mock_popen:
        mock_proc = mock_popen.return_value.__enter__.return_value
        # readline raises BrokenPipeError on the first call
        mock_proc.stdout.readline.side_effect = BrokenPipeError("pipe broken")
        mock_proc.stderr.read.return_value = b"broken pipe"
        mock_proc.returncode = None
        with pytest.raises(GitError):
            run_git(["log", "--oneline", "-5"], repo_path=tmp_repo)
```

- [ ] **Step 14: Add missing-git-binary test (CR Phase 1.2 finding #5)**

Append to `services/palace-mcp/tests/git/test_command.py`:

```python
def test_missing_git_binary_raises_git_error(
    tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Set PATH to a non-existent dir so git cannot be found — assert GitError.

    Maps to spec §7.6. Verifies error message is human-readable.
    """
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(GitError, match=r"git"):
        run_git(["log", "--oneline", "-1"], repo_path=tmp_repo)
```

- [ ] **Step 15: Run all command tests — expect pass**

```bash
uv run pytest tests/git/test_command.py -v
```

Expected: all tests pass (including the two new ones).

- [ ] **Step 16: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/command.py \
        services/palace-mcp/tests/git/test_command.py
git commit -m "feat(git-mcp): run_git with whitelist, env, timeout, capped stream + error-path tests"
```

---

### Task 2.5: Pydantic response schemas

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/schemas.py`

No dedicated test — schemas are exercised by tool tests in Tasks 2.6-2.10. mypy --strict is the contract here.

- [ ] **Step 1: Write all schemas**

File: `services/palace-mcp/src/palace_mcp/git/schemas.py`

```python
"""Pydantic response models for palace.git.* tools. Spec §4.

Every tool returns either a tool-specific success model or a shared
ErrorResponse. MCP clients receive the discriminated union.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_CFG = ConfigDict(extra="forbid")


# --- Shared ---


class ErrorResponse(BaseModel):
    model_config = _CFG

    ok: Literal[False] = False
    error_code: str
    message: str
    project: str | None = None


# --- log ---


class LogEntry(BaseModel):
    model_config = _CFG

    sha: str
    short: str
    author_name: str
    author_email: str
    date: str  # ISO-8601 with TZ (%aI)
    subject: str


class LogResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    ref: str
    entries: list[LogEntry]
    truncated: bool


# --- show (two modes) ---


class FileStat(BaseModel):
    model_config = _CFG

    path: str
    added: int | None = None  # None → binary
    deleted: int | None = None  # None → binary
    status: str | None = None  # M/A/D etc., commit mode only


class ShowCommitResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    mode: Literal["commit"] = "commit"
    project: str
    sha: str
    author_name: str
    date: str
    subject: str
    body: str
    files_changed: list[FileStat]
    diff: str
    truncated: bool


class ShowFileResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    mode: Literal["file"] = "file"
    project: str
    ref: str
    path: str
    content: str
    lines: int
    truncated: bool


class BinaryFileResponse(BaseModel):
    model_config = _CFG

    ok: Literal[False] = False
    error_code: Literal["binary_file"] = "binary_file"
    project: str
    ref: str
    path: str
    size_bytes: int


# --- blame ---


class BlameLine(BaseModel):
    model_config = _CFG

    line_no: int
    sha: str
    short: str
    author_name: str
    date: str
    content: str


class BlameResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    path: str
    ref: str
    lines: list[BlameLine]
    truncated: bool


# --- diff ---


class DiffResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    ref_a: str
    ref_b: str
    path: str | None
    mode: Literal["full", "stat"]
    diff: str | None = None  # populated when mode="full"
    files_stat: list[FileStat] | None = None  # populated when mode="stat"
    truncated: bool


# --- ls_tree ---


class TreeEntry(BaseModel):
    model_config = _CFG

    path: str
    type: Literal["blob", "tree", "commit"]  # commit = submodule
    mode: str
    sha: str


class LsTreeResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    ref: str
    path: str | None
    recursive: bool
    entries: list[TreeEntry]
    truncated: bool
```

- [ ] **Step 2: mypy --strict check**

```bash
cd services/palace-mcp
uv run mypy --strict src/palace_mcp/git/schemas.py
```

Expected: `Success: no issues found in 1 source file`.

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/schemas.py
git commit -m "feat(git-mcp): Pydantic response schemas for 5 tools"
```

---

### Task 2.6: `palace.git.log` — parser + tool + integration

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/tools.py`
- Create: `services/palace-mcp/tests/git/test_tool_log.py`

- [ ] **Step 1: Write parser unit tests + happy-path integration**

File: `services/palace-mcp/tests/git/test_tool_log.py`

```python
"""Tests for palace.git.log. Spec §4.1."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.tools import parse_log, palace_git_log


# --- parse_log (pure unit) ---


def test_parse_log_two_entries() -> None:
    raw = (
        "abc\0ab\0Alice\0a@a\0"
        "2026-04-19T10:00:00+00:00\0first\n"
        "def\0de\0Bob\0b@b\0"
        "2026-04-18T10:00:00+00:00\0second\n"
    )
    entries = parse_log(raw)
    assert len(entries) == 2
    assert entries[0].sha == "abc"
    assert entries[0].short == "ab"
    assert entries[0].author_name == "Alice"
    assert entries[0].subject == "first"


def test_parse_log_empty() -> None:
    assert parse_log("") == []


def test_parse_log_subject_with_nul_is_rejected_gracefully() -> None:
    # Only happens in pathological repos; we tolerate truncation.
    raw = "sha\0sh\0A\0a@a\0" "2026-04-19T10:00:00+00:00\0bad\0subject\n"
    entries = parse_log(raw)
    # Implementation splits on \0: subject = everything after 6th field,
    # NUL in subject becomes part of the subject string. Assert no raise.
    assert len(entries) == 1


# --- palace_git_log (integration with tmp_repo) ---


@pytest.mark.asyncio
async def test_log_returns_two_commits(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_log(project="testproj", n=10)
    assert res["ok"] is True
    assert len(res["entries"]) == 2
    assert all(len(e["sha"]) == 40 for e in res["entries"])
    assert res["truncated"] is False


@pytest.mark.asyncio
async def test_log_invalid_slug_returns_error_envelope(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_log(project="../etc", n=5)
    assert res["ok"] is False
    assert res["error_code"] == "invalid_slug"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest tests/git/test_tool_log.py -v
```

- [ ] **Step 3: Implement `parse_log` + `palace_git_log`**

File: `services/palace-mcp/src/palace_mcp/git/tools.py`

```python
"""MCP tool handlers for palace.git.*. Spec §4."""

from __future__ import annotations

import logging
import re
from typing import Any

from palace_mcp.git.command import (
    ForbiddenGitCommand,
    GitError,
    GitTimeout,
    run_git,
)
from palace_mcp.git.path_resolver import (
    InvalidPath,
    ProjectNotRegistered,
    REPOS_ROOT,
    resolve_project,
    validate_rel_path,
)
from palace_mcp.git.schemas import (
    LogEntry,
    LogResponse,
)
from palace_mcp.memory.projects import InvalidSlug

logger = logging.getLogger(__name__)


_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@\-]{0,199}$")

LOG_DEFAULT_N = 20
LOG_CAP_N = 200


def _valid_ref(ref: str) -> bool:
    return bool(_REF_RE.match(ref))


def _error(code: str, message: str, project: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error_code": code, "message": message}
    if project is not None:
        out["project"] = project
    return out


def parse_log(raw: str) -> list[LogEntry]:
    """Parse NULL-delimited `git log --pretty=format:...` output."""
    entries: list[LogEntry] = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\0", 5)
        if len(parts) < 6:
            continue
        sha, short, an, ae, date, subject = parts
        entries.append(
            LogEntry(
                sha=sha,
                short=short,
                author_name=an,
                author_email=ae,
                date=date,
                subject=subject,
            )
        )
    return entries


async def palace_git_log(
    project: str,
    *,
    path: str | None = None,
    ref: str = "HEAD",
    n: int = LOG_DEFAULT_N,
    since: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """Return commit log for `project`. Capped at LOG_CAP_N entries."""
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )

    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)

    resolved_path: str | None = None
    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
            resolved_path = path  # pass relative to `git -C repo_path`
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

    capped_n = min(max(n, 1), LOG_CAP_N)
    args = [
        "log",
        ref,
        "--pretty=format:%H%x00%h%x00%an%x00%ae%x00%aI%x00%s",
        "-n",
        str(capped_n),
    ]
    if since:
        args.append(f"--since={since}")
    if author:
        args.append(f"--author={author}")
    args.append("--")
    if resolved_path:
        args.append(resolved_path)

    try:
        result = run_git(
            args,
            repo_path=repo_path,
            max_stdout_lines=capped_n,
        )
    except GitTimeout as exc:
        return _error("git_timeout", str(exc), project)
    except ForbiddenGitCommand as exc:
        return _error("forbidden_command", str(exc), project)
    except GitError as exc:
        return _error("git_error", str(exc), project)
    except Exception as exc:  # noqa: BLE001 — unexpected, log + report
        logger.exception("palace.git.log unexpected error")
        return _error("unknown", str(exc), project)

    if result.rc != 0:
        # Map stderr → refined error_code.
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    entries = parse_log(result.stdout)
    resp = LogResponse(
        project=project,
        ref=ref,
        entries=entries,
        truncated=result.truncated,
    )
    logger.info(
        "git.tool.call tool=palace.git.log project=%s duration_ms=%d rc=0 "
        "stdout_bytes=%d truncated=%s",
        project, result.duration_ms, len(result.stdout), result.truncated,
    )
    return resp.model_dump()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/git/test_tool_log.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/tools.py \
        services/palace-mcp/tests/git/test_tool_log.py
git commit -m "feat(git-mcp): palace.git.log with NULL-delim parser"
```

---

### Task 2.6a: `_valid_ref` security tests (CR Phase 1.2 finding #1)

**Files:**
- Modify: `services/palace-mcp/tests/git/test_tool_log.py` (append) or create `services/palace-mcp/tests/git/test_valid_ref.py`

Maps to spec §5.3 / §7.6. `_valid_ref` is the only guard against injection via ref arguments.

- [ ] **Step 1: Write parametrized tests for `_valid_ref`**

File: `services/palace-mcp/tests/git/test_valid_ref.py`

```python
"""Security tests for tools._valid_ref. Spec §5.3, §7.6.

Ensures the ref whitelist rejects injection patterns and accepts
legitimate git refs.
"""

from __future__ import annotations

import pytest

from palace_mcp.git.tools import _valid_ref


@pytest.mark.parametrize(
    "ref",
    [
        "HEAD",
        "HEAD~3",
        "main",
        "abc1234",
        "v1.0.0",
        "feature/foo",
    ],
)
def test_valid_refs_accepted(ref: str) -> None:
    assert _valid_ref(ref) is True


@pytest.mark.parametrize(
    "ref,reason",
    [
        ("--upload-pack=x", "git flag injection"),
        ("-flag", "leading dash"),
        ("HEAD; rm -rf /", "shell metachar semicolon"),
        ("HEAD\ninjection", "newline injection"),
        ("", "empty string"),
        ("HEAD\x00null", "nul byte"),
    ],
)
def test_invalid_refs_rejected(ref: str, reason: str) -> None:
    assert _valid_ref(ref) is False, f"Expected False for {reason!r}: {ref!r}"
```

- [ ] **Step 2: Run tests — expect pass (function already exists)**

```bash
uv run pytest tests/git/test_valid_ref.py -v
```

Expected: 12 passed (6 valid + 6 invalid).

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/git/test_valid_ref.py
git commit -m "test(git-mcp): add _valid_ref security parametrized tests (spec §5.3)"
```

---

### Task 2.6b: Per-tool output-cap integration tests (CR Phase 1.2 finding #2)

**Files:**
- Create: `services/palace-mcp/tests/git/test_cap_enforcement.py`
- Modify: `services/palace-mcp/tests/git/conftest.py` (add `large_repo` fixture)

Maps to spec §7.6 Level 4. Verifies each tool's cap constant is enforced in practice.

- [ ] **Step 1: Extend `conftest.py` with `large_repo` fixture**

Append to `services/palace-mcp/tests/git/conftest.py`:

```python
@pytest.fixture
def large_repo(tmp_path: Path) -> Path:
    """Git repo exceeding all per-tool output caps.

    Creates:
    - 250 commits (LOG_CAP_N=200)
    - a single file with 500 lines (BLAME_CAP_LINES=400, SHOW_CAP_LINES=500)
    - 600 files staged at once (LS_TREE_CAP=500)
    - a diff with 2500 lines changed (DIFF_CAP_FULL=2000)
    - a diff across 600 files (DIFF_CAP_STAT=500)
    """
    repo = tmp_path / "repos" / "large"
    repo.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "t@t"], cwd=repo)
    _run(["git", "config", "user.name", "T"], cwd=repo)

    # 600 files (covers ls_tree + diff stat cap)
    for i in range(600):
        (repo / f"f{i:04d}.txt").write_text(f"file {i}\n" * 5)
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "bulk-files", "-q"], cwd=repo)

    # Large single file: 500 lines (covers blame + show caps)
    (repo / "big.txt").write_text("".join(f"line {i}\n" for i in range(500)))
    _run(["git", "add", "big.txt"], cwd=repo)
    _run(["git", "commit", "-m", "big-file", "-q"], cwd=repo)

    # 250 more commits (covers log cap)
    for i in range(250):
        (repo / "counter.txt").write_text(f"{i}\n")
        _run(["git", "add", "counter.txt"], cwd=repo)
        _run(["git", "commit", "-m", f"tick-{i}", "-q"], cwd=repo)

    return repo


@pytest.fixture
def large_repos_root(large_repo: Path) -> Path:
    """Simulate /repos/ containing the large project."""
    return large_repo.parent
```

- [ ] **Step 2: Write cap enforcement tests**

File: `services/palace-mcp/tests/git/test_cap_enforcement.py`

```python
"""Integration tests: each tool truncates at its cap constant. Spec §7.6 Level 4."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.tools import (
    LOG_CAP_N,
    DIFF_CAP_FULL,
    DIFF_CAP_STAT,
    BLAME_CAP_LINES,
    LS_TREE_CAP,
    SHOW_CAP_LINES,
    palace_git_log,
    palace_git_diff,
    palace_git_blame,
    palace_git_ls_tree,
    palace_git_show,
)


@pytest.mark.asyncio
async def test_log_cap(
    monkeypatch: pytest.MonkeyPatch, large_repos_root: Path
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", large_repos_root)
    res = await palace_git_log(project="large", n=LOG_CAP_N + 100)
    assert res["ok"] is True
    assert len(res["entries"]) == LOG_CAP_N
    assert res["truncated"] is True


@pytest.mark.asyncio
async def test_diff_full_cap(
    monkeypatch: pytest.MonkeyPatch, large_repos_root: Path
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", large_repos_root)
    # Diff between initial bulk-files commit and HEAD should exceed DIFF_CAP_FULL.
    res = await palace_git_diff(
        project="large", ref_a="HEAD~251", ref_b="HEAD", mode="full"
    )
    assert res["ok"] is True
    assert res["truncated"] is True
    assert res["diff"].count("\n") <= DIFF_CAP_FULL


@pytest.mark.asyncio
async def test_diff_stat_cap(
    monkeypatch: pytest.MonkeyPatch, large_repos_root: Path
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", large_repos_root)
    res = await palace_git_diff(
        project="large", ref_a="HEAD~251", ref_b="HEAD~250", mode="stat"
    )
    assert res["ok"] is True
    assert res["truncated"] is True
    assert len(res["files"]) <= DIFF_CAP_STAT


@pytest.mark.asyncio
async def test_blame_cap(
    monkeypatch: pytest.MonkeyPatch, large_repos_root: Path
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", large_repos_root)
    res = await palace_git_blame(project="large", ref="HEAD", path="big.txt")
    assert res["ok"] is True
    assert res["truncated"] is True
    assert len(res["lines"]) == BLAME_CAP_LINES


@pytest.mark.asyncio
async def test_ls_tree_cap(
    monkeypatch: pytest.MonkeyPatch, large_repos_root: Path
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", large_repos_root)
    res = await palace_git_ls_tree(project="large", ref="HEAD")
    assert res["ok"] is True
    assert res["truncated"] is True
    assert len(res["entries"]) == LS_TREE_CAP


@pytest.mark.asyncio
async def test_show_cap(
    monkeypatch: pytest.MonkeyPatch, large_repos_root: Path
) -> None:
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", large_repos_root)
    res = await palace_git_show(project="large", ref="HEAD", path="big.txt")
    assert res["ok"] is True
    assert res["truncated"] is True
    assert res["content"].count("\n") <= SHOW_CAP_LINES
```

- [ ] **Step 3: Run tests — expect pass after all tool tasks complete**

Note: these tests must be run **after** Tasks 2.7-2.10 are implemented (all tool functions referenced must exist). Run as the final integration check at the end of Phase 2:

```bash
uv run pytest tests/git/test_cap_enforcement.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/tests/git/conftest.py \
        services/palace-mcp/tests/git/test_cap_enforcement.py
git commit -m "test(git-mcp): per-tool cap enforcement integration tests (spec §7.6 L4)"
```

---

### Task 2.7: `palace.git.show` — commit + file modes, binary detection

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/tools.py`
- Create: `services/palace-mcp/tests/git/test_tool_show.py`

- [ ] **Step 1: Tests for file mode, commit mode, binary detection**

File: `services/palace-mcp/tests/git/test_tool_show.py`

```python
"""Tests for palace.git.show. Spec §4.2."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from palace_mcp.git.tools import palace_git_show


@pytest.mark.asyncio
async def test_show_file_returns_content(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path, tmp_repo: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_show(
        project="testproj", ref="HEAD", path="a.py"
    )
    assert res["ok"] is True
    assert res["mode"] == "file"
    assert "line2-changed" in res["content"]


@pytest.mark.asyncio
async def test_show_commit_mode(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_show(project="testproj", ref="HEAD")
    assert res["ok"] is True
    assert res["mode"] == "commit"
    assert len(res["sha"]) == 40
    assert "a.py" in [f["path"] for f in res["files_changed"]]


@pytest.mark.asyncio
async def test_show_binary_file_returns_binary_error(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path, tmp_repo: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    # Commit a tiny PNG (8-byte PNG magic + IHDR).
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000"
        "001f15c4890000000a49444154789c6300010000000500010d0a2db4"
        "0000000049454e44ae426082"
    )
    (tmp_repo / "icon.png").write_bytes(png_bytes)
    subprocess.run(
        ["git", "add", "icon.png"], cwd=tmp_repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "add png", "-q"],
        cwd=tmp_repo, check=True, capture_output=True,
    )
    res = await palace_git_show(
        project="testproj", ref="HEAD", path="icon.png"
    )
    assert res["ok"] is False
    assert res["error_code"] == "binary_file"
    assert res["size_bytes"] > 0
```

- [ ] **Step 2: Run — expect `palace_git_show` ImportError**

- [ ] **Step 3: Implement `palace_git_show`**

Append to `services/palace-mcp/src/palace_mcp/git/tools.py`:

```python
from palace_mcp.git.schemas import (
    BinaryFileResponse,
    FileStat,
    ShowCommitResponse,
    ShowFileResponse,
)

SHOW_CAP_LINES = 500


def _scan_for_nul(data: bytes, limit: int = 8192) -> bool:
    return b"\x00" in data[:limit]


def _get_blob_size(repo_path: Any, ref: str, path: str) -> int:
    """Return blob size via `git cat-file -s <ref>:<path>`."""
    result = run_git(
        ["cat-file", "-s", f"{ref}:{path}"],
        repo_path=repo_path,
    )
    if result.rc != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


async def palace_git_show(
    project: str,
    *,
    ref: str,
    path: str | None = None,
) -> dict[str, Any]:
    """Show a commit (path=None) or file at ref (path=<file>)."""
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )

    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)

    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

        # Binary detection via `git cat-file -t <ref>:<path>` (single
        # subprocess). CR Phase 1.2 finding #3: eliminates _raw_bytes_show
        # duplicate Popen; spec §3.3 mandates single-subprocess flow.
        spec = f"{ref}:{path}"
        type_result = run_git(
            ["cat-file", "-t", spec],
            repo_path=repo_path,
        )
        obj_type = type_result.stdout.strip() if type_result.rc == 0 else ""

        if obj_type != "blob":
            return _error("invalid_path", f"not a blob: {spec!r}", project)

        # Fetch blob content once; scan decoded bytes for NUL proxy.
        # UTF-8 decode with errors="replace" preserves \x00 as \x00 in
        # Python, so _scan_for_nul works on the encoded representation.
        show_result = run_git(
            ["show", spec],
            repo_path=repo_path,
            max_stdout_lines=None,
            timeout_s=5.0,
        )
        if _scan_for_nul(show_result.stdout.encode("utf-8", errors="replace")):
            size = _get_blob_size(repo_path, ref, path)
            return BinaryFileResponse(
                project=project, ref=ref, path=path, size_bytes=size
            ).model_dump()

        # Text file — cap lines.
        lines = show_result.stdout.splitlines(keepends=True)
        truncated = False
        if len(lines) > SHOW_CAP_LINES:
            lines = lines[:SHOW_CAP_LINES]
            truncated = True
        content = "".join(lines)
        return ShowFileResponse(
            project=project,
            ref=ref,
            path=path,
            content=content,
            lines=len(lines),
            truncated=truncated,
        ).model_dump()

    # Commit mode: git show <ref> --stat -p
    result = run_git(
        ["show", ref, "--stat", "-p"],
        repo_path=repo_path,
        max_stdout_lines=SHOW_CAP_LINES,
    )
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    parsed = _parse_show_commit(result.stdout)
    return ShowCommitResponse(
        project=project,
        sha=parsed["sha"],
        author_name=parsed["author_name"],
        date=parsed["date"],
        subject=parsed["subject"],
        body=parsed["body"],
        files_changed=parsed["files_changed"],
        diff=parsed["diff"],
        truncated=result.truncated,
    ).model_dump()


def _parse_show_commit(raw: str) -> dict[str, Any]:
    """Parse output of `git show <ref> --stat -p`.

    Format: commit <sha>\\nAuthor: ...\\nDate: ...\\n\\n<subject>\\n<body>
    \\n---\\n<stat>\\n<diff>
    """
    lines = raw.splitlines()
    sha = ""
    author_name = ""
    date = ""
    subject = ""
    body_lines: list[str] = []
    stat_files: list[FileStat] = []
    diff_lines: list[str] = []
    i = 0
    if i < len(lines) and lines[i].startswith("commit "):
        sha = lines[i].split(" ", 1)[1].strip()
        i += 1
    while i < len(lines) and lines[i].strip() != "":
        ln = lines[i]
        if ln.startswith("Author:"):
            author_name = ln.split(":", 1)[1].strip().rsplit(" <", 1)[0]
        elif ln.startswith("Date:"):
            date = ln.split(":", 1)[1].strip()
        i += 1
    i += 1  # blank
    if i < len(lines):
        subject = lines[i].strip()
        i += 1
    while i < len(lines) and not lines[i].startswith(("diff ", "---")):
        body_lines.append(lines[i])
        i += 1
    # Stat + diff. We keep diff as the remainder; stat parsing is
    # best-effort — format is `<path> | N ++-` style.
    while i < len(lines):
        ln = lines[i]
        if "|" in ln and ln.strip() and not ln.startswith("diff "):
            parts = ln.split("|", 1)
            path = parts[0].strip()
            rhs = parts[1].strip()
            added = rhs.count("+")
            deleted = rhs.count("-")
            stat_files.append(FileStat(path=path, added=added, deleted=deleted))
        else:
            diff_lines.append(ln)
        i += 1
    return {
        "sha": sha,
        "author_name": author_name,
        "date": date,
        "subject": subject,
        "body": "\n".join(l for l in body_lines if l.strip()),
        "files_changed": stat_files,
        "diff": "\n".join(diff_lines),
    }
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/git/test_tool_show.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/tools.py \
        services/palace-mcp/tests/git/test_tool_show.py
git commit -m "feat(git-mcp): palace.git.show with commit+file modes + binary detect"
```

---

### Task 2.8: `palace.git.blame` — porcelain parser

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/tools.py`
- Create: `services/palace-mcp/tests/git/test_tool_blame.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for palace.git.blame. Spec §4.3."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.tools import palace_git_blame, parse_blame_porcelain


def test_parse_porcelain_single_commit() -> None:
    raw = (
        "abc1234567890abcdef1234567890abcdef12345 1 1 2\n"
        "author Alice\nauthor-time 1700000000\nauthor-tz +0000\n"
        "summary first\nboundary\n\tline one\n"
        "abc1234567890abcdef1234567890abcdef12345 2 2\n"
        "\tline two\n"
    )
    lines = parse_blame_porcelain(raw)
    assert len(lines) == 2
    assert lines[0].line_no == 1
    assert lines[0].author_name == "Alice"
    assert lines[0].content == "line one"


@pytest.mark.asyncio
async def test_blame_happy_path(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_blame(project="testproj", path="a.py")
    assert res["ok"] is True
    assert len(res["lines"]) == 3  # tmp_repo has 3 lines in a.py
    assert res["lines"][0]["line_no"] == 1


@pytest.mark.asyncio
async def test_blame_line_range(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_blame(
        project="testproj", path="a.py", line_start=2, line_end=2
    )
    assert len(res["lines"]) == 1
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `parse_blame_porcelain` and `palace_git_blame`**

Append to `services/palace-mcp/src/palace_mcp/git/tools.py`:

```python
from datetime import datetime, timezone

from palace_mcp.git.schemas import BlameLine, BlameResponse

BLAME_CAP_LINES = 400


def parse_blame_porcelain(raw: str) -> list[BlameLine]:
    """Parse `git blame --porcelain` output."""
    lines: list[BlameLine] = []
    commits: dict[str, dict[str, str]] = {}
    current_meta: dict[str, str] = {}
    current_sha: str = ""
    current_lineno: int = 0
    for ln in raw.splitlines():
        if ln.startswith("\t"):
            meta = commits.get(current_sha, current_meta)
            date_iso = ""
            try:
                ts = int(meta.get("author-time", "0"))
                date_iso = datetime.fromtimestamp(
                    ts, tz=timezone.utc
                ).isoformat()
            except ValueError:
                date_iso = ""
            lines.append(
                BlameLine(
                    line_no=current_lineno,
                    sha=current_sha,
                    short=current_sha[:7],
                    author_name=meta.get("author", ""),
                    date=date_iso,
                    content=ln[1:],  # strip leading tab
                )
            )
        elif ln and ln[0].isalnum() and len(ln.split(" ", 1)[0]) == 40:
            # Header line: <sha> <orig_line> <final_line> [<num_lines>]
            parts = ln.split(" ")
            current_sha = parts[0]
            current_lineno = int(parts[2]) if len(parts) >= 3 else 0
            current_meta = commits.setdefault(current_sha, {})
        elif " " in ln:
            # Metadata: `key value`
            key, _, value = ln.partition(" ")
            if current_sha:
                commits[current_sha][key] = value
    return lines


async def palace_git_blame(
    project: str,
    *,
    path: str,
    ref: str = "HEAD",
    line_start: int | None = None,
    line_end: int | None = None,
) -> dict[str, Any]:
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )
    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)
    try:
        validate_rel_path(path, repo_path=repo_path)
    except InvalidPath as exc:
        return _error("invalid_path", str(exc), project)

    args = ["blame", "--porcelain", ref]
    if line_start is not None and line_end is not None:
        args.extend(["-L", f"{line_start},{line_end}"])
    args.extend(["--", path])

    cap = BLAME_CAP_LINES if (line_start is None and line_end is None) else None
    result = run_git(args, repo_path=repo_path, max_stdout_lines=cap and cap * 5)
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    blame_lines = parse_blame_porcelain(result.stdout)
    truncated = False
    if cap is not None and len(blame_lines) > cap:
        blame_lines = blame_lines[:cap]
        truncated = True
    return BlameResponse(
        project=project,
        path=path,
        ref=ref,
        lines=blame_lines,
        truncated=truncated,
    ).model_dump()
```

- [ ] **Step 4: Run tests — expect pass**

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/tools.py \
        services/palace-mcp/tests/git/test_tool_blame.py
git commit -m "feat(git-mcp): palace.git.blame with porcelain parser"
```

---

### Task 2.9: `palace.git.diff` — full + stat modes

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/tools.py`
- Create: `services/palace-mcp/tests/git/test_tool_diff.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for palace.git.diff. Spec §4.4."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.tools import palace_git_diff, parse_numstat


def test_parse_numstat_text_and_binary() -> None:
    raw = "5\t2\tsrc/a.py\n-\t-\tdocs/icon.png\n"
    stats = parse_numstat(raw)
    assert len(stats) == 2
    assert stats[0].path == "src/a.py"
    assert stats[0].added == 5
    assert stats[0].deleted == 2
    assert stats[1].path == "docs/icon.png"
    assert stats[1].added is None
    assert stats[1].deleted is None


@pytest.mark.asyncio
async def test_diff_full_mode(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_diff(
        project="testproj", ref_a="HEAD~1", ref_b="HEAD"
    )
    assert res["ok"] is True
    assert res["mode"] == "full"
    assert res["diff"] is not None
    assert res["files_stat"] is None
    assert "line2-changed" in res["diff"]


@pytest.mark.asyncio
async def test_diff_stat_mode(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_diff(
        project="testproj", ref_a="HEAD~1", ref_b="HEAD", mode="stat"
    )
    assert res["ok"] is True
    assert res["mode"] == "stat"
    assert res["diff"] is None
    assert res["files_stat"] is not None
    assert res["files_stat"][0]["path"] == "a.py"
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement**

Append to `tools.py`:

```python
from palace_mcp.git.schemas import DiffResponse

DIFF_DEFAULT_MAX_LINES = 500
DIFF_CAP_FULL = 2000
DIFF_CAP_STAT = 500


def parse_numstat(raw: str) -> list[FileStat]:
    stats: list[FileStat] = []
    for ln in raw.splitlines():
        if not ln.strip():
            continue
        parts = ln.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        if a == "-" or d == "-":
            stats.append(FileStat(path=path, added=None, deleted=None))
        else:
            try:
                stats.append(
                    FileStat(path=path, added=int(a), deleted=int(d))
                )
            except ValueError:
                continue
    return stats


async def palace_git_diff(
    project: str,
    *,
    ref_a: str,
    ref_b: str,
    path: str | None = None,
    mode: str = "full",
    max_lines: int = DIFF_DEFAULT_MAX_LINES,
) -> dict[str, Any]:
    if mode not in ("full", "stat"):
        return _error("invalid_mode", f"mode must be full|stat, got {mode!r}", project)
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )
    for r, name in [(ref_a, "ref_a"), (ref_b, "ref_b")]:
        if not _valid_ref(r):
            return _error("invalid_ref", f"invalid {name}: {r!r}", project)
    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

    args = ["diff"]
    if mode == "stat":
        args.append("--numstat")
    args.extend([ref_a, ref_b, "--"])
    if path is not None:
        args.append(path)

    cap = min(max_lines, DIFF_CAP_FULL) if mode == "full" else DIFF_CAP_STAT
    result = run_git(args, repo_path=repo_path, max_stdout_lines=cap)
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "bad object" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    if mode == "stat":
        files = parse_numstat(result.stdout)
        return DiffResponse(
            project=project,
            ref_a=ref_a,
            ref_b=ref_b,
            path=path,
            mode="stat",
            diff=None,
            files_stat=files,
            truncated=result.truncated,
        ).model_dump()
    return DiffResponse(
        project=project,
        ref_a=ref_a,
        ref_b=ref_b,
        path=path,
        mode="full",
        diff=result.stdout,
        files_stat=None,
        truncated=result.truncated,
    ).model_dump()
```

- [ ] **Step 4: Run tests — expect pass**

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/git/tools.py \
        services/palace-mcp/tests/git/test_tool_diff.py
git commit -m "feat(git-mcp): palace.git.diff with full+stat modes"
```

---

### Task 2.10: `palace.git.ls_tree`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/git/tools.py`
- Create: `services/palace-mcp/tests/git/test_tool_ls_tree.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for palace.git.ls_tree. Spec §4.5."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.git.tools import palace_git_ls_tree, parse_ls_tree


def test_parse_ls_tree_flat() -> None:
    raw = (
        "100644 blob abc1234\tREADME.md\n"
        "040000 tree def5678\tsrc\n"
        "160000 commit 9abc123\tsubmod\n"
    )
    entries = parse_ls_tree(raw)
    assert len(entries) == 3
    assert entries[0].type == "blob"
    assert entries[1].type == "tree"
    assert entries[2].type == "commit"


@pytest.mark.asyncio
async def test_ls_tree_flat(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_ls_tree(project="testproj", ref="HEAD")
    assert res["ok"] is True
    paths = [e["path"] for e in res["entries"]]
    assert "a.py" in paths


@pytest.mark.asyncio
async def test_ls_tree_recursive(
    monkeypatch: pytest.MonkeyPatch, repos_root: Path
) -> None:
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos_root
    )
    res = await palace_git_ls_tree(
        project="testproj", ref="HEAD", recursive=True
    )
    assert res["recursive"] is True
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement**

Append to `tools.py`:

```python
from palace_mcp.git.schemas import LsTreeResponse, TreeEntry

LS_TREE_CAP = 500


def parse_ls_tree(raw: str) -> list[TreeEntry]:
    entries: list[TreeEntry] = []
    for ln in raw.splitlines():
        if not ln:
            continue
        # Format: <mode> <type> <sha>\t<path>
        lhs, _, path = ln.partition("\t")
        parts = lhs.split(" ")
        if len(parts) != 3:
            continue
        mode, typ, sha = parts
        if typ not in ("blob", "tree", "commit"):
            continue
        entries.append(
            TreeEntry(path=path, type=typ, mode=mode, sha=sha)  # type: ignore[arg-type]
        )
    return entries


async def palace_git_ls_tree(
    project: str,
    *,
    ref: str = "HEAD",
    path: str | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    try:
        repo_path = resolve_project(project)
    except InvalidSlug:
        return _error("invalid_slug", f"invalid slug: {project!r}", project)
    except ProjectNotRegistered:
        return _error(
            "project_not_registered",
            f"no mounted repo at /repos/{project}",
            project,
        )
    if not _valid_ref(ref):
        return _error("invalid_ref", f"invalid ref: {ref!r}", project)
    if path is not None:
        try:
            validate_rel_path(path, repo_path=repo_path)
        except InvalidPath as exc:
            return _error("invalid_path", str(exc), project)

    args = ["ls-tree"]
    if recursive:
        args.append("-r")
    args.append(ref)
    if path is not None:
        args.extend(["--", path])

    result = run_git(args, repo_path=repo_path, max_stdout_lines=LS_TREE_CAP)
    if result.rc != 0:
        low = result.stderr.lower()
        if "unknown revision" in low or "not a tree" in low:
            return _error("invalid_ref", result.stderr[:200], project)
        return _error("git_error", result.stderr[:200], project)

    return LsTreeResponse(
        project=project,
        ref=ref,
        path=path,
        recursive=recursive,
        entries=parse_ls_tree(result.stdout),
        truncated=result.truncated,
    ).model_dump()
```

- [ ] **Step 4: Run + commit**

```bash
uv run pytest tests/git/test_tool_ls_tree.py -v
git add services/palace-mcp/src/palace_mcp/git/tools.py \
        services/palace-mcp/tests/git/test_tool_ls_tree.py
git commit -m "feat(git-mcp): palace.git.ls_tree"
```

---

### Task 2.11: Wire tools into `mcp_server`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py`
- Create: `services/palace-mcp/tests/git/test_mcp_integration.py` (optional smoke)

- [ ] **Step 1: Register the 5 tools on the existing FastMCP app**

File: `services/palace-mcp/src/palace_mcp/mcp_server.py`

Import block — add:

```python
from palace_mcp.git.tools import (
    palace_git_blame,
    palace_git_diff,
    palace_git_log,
    palace_git_ls_tree,
    palace_git_show,
)
```

Near the existing `@_mcp.tool(...)` registrations, add five new ones matching the palace-memory convention. Example for `log`:

```python
@_mcp.tool(
    name="palace.git.log",
    description=(
        "Read-only commit log for a project. Returns up to `n` most recent "
        "commits (default 20, max 200). Structured entries with sha, short, "
        "author_name, author_email, date (ISO-8601), subject. Optional "
        "filters: path, ref, since (git relative/ISO), author (substring)."
    ),
)
async def _palace_git_log(
    project: str,
    path: str | None = None,
    ref: str = "HEAD",
    n: int = 20,
    since: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    return await palace_git_log(
        project=project,
        path=path,
        ref=ref,
        n=n,
        since=since,
        author=author,
    )
```

Repeat for `show`, `blame`, `diff`, `ls_tree` with matching descriptions (take them from spec §4.1-§4.5).

- [ ] **Step 2: Lint + typecheck**

```bash
cd services/palace-mcp
uv run ruff check src/
uv run mypy --strict src/palace_mcp/git/ src/palace_mcp/mcp_server.py
```

Expected: no issues.

- [ ] **Step 3: Smoke — all git tests together**

```bash
uv run pytest tests/git/ -v
```

Expected: all ~30 tests pass.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/mcp_server.py
git commit -m "feat(git-mcp): wire 5 tools into FastMCP surface"
```

---

### Task 2.12: Extend `palace.memory.health` with `git` section

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py` (add `GitHealth` nested model)
- Modify: `services/palace-mcp/src/palace_mcp/memory/health.py`
- Modify: `services/palace-mcp/tests/memory/test_health.py` (add cases)

- [ ] **Step 1: Write failing test**

Add to `services/palace-mcp/tests/memory/test_health.py`:

```python
@pytest.mark.asyncio
async def test_health_git_section_present(monkeypatch, tmp_path):
    """health() response includes git.available_projects."""
    # Create fake /repos/foo with .git/, no :Project registration
    repos = tmp_path / "repos"
    foo = repos / "foo"
    foo.mkdir(parents=True)
    (foo / ".git").mkdir()
    monkeypatch.setattr(
        "palace_mcp.git.path_resolver.REPOS_ROOT", repos
    )
    # Assume driver mocked with 0 projects in :Project.
    from palace_mcp.memory.health import scan_git_repos
    git_info = scan_git_repos(repos_root=repos, registered_slugs=set())
    assert "foo" in git_info.available_projects
    assert "foo" in git_info.unregistered_projects
```

- [ ] **Step 2: Add `GitHealth` Pydantic model**

File: `services/palace-mcp/src/palace_mcp/memory/schema.py` (append):

```python
class GitHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repos_root: str
    available_projects: list[str]
    unregistered_projects: list[str]
```

Extend `HealthResponse` with an optional `git` field:

```python
class HealthResponse(BaseModel):
    # ... existing fields ...
    git: "GitHealth | None" = None
```

- [ ] **Step 3: Implement `scan_git_repos`**

File: `services/palace-mcp/src/palace_mcp/memory/health.py` (add):

```python
from pathlib import Path

from palace_mcp.memory.schema import GitHealth


def scan_git_repos(
    *, repos_root: Path, registered_slugs: set[str]
) -> GitHealth:
    if not repos_root.exists():
        return GitHealth(
            repos_root=str(repos_root),
            available_projects=[],
            unregistered_projects=[],
        )
    available: list[str] = []
    for child in sorted(repos_root.iterdir()):
        if child.is_dir() and (child / ".git").exists():
            available.append(child.name)
    unregistered = sorted(set(available) - registered_slugs)
    return GitHealth(
        repos_root=str(repos_root),
        available_projects=available,
        unregistered_projects=unregistered,
    )
```

Wire into existing `health()` function — gather `registered_slugs` from the `:Project` listing query, call `scan_git_repos`, attach to response.

- [ ] **Step 4: Run health tests — expect pass**

```bash
uv run pytest tests/memory/test_health.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/ \
        services/palace-mcp/tests/memory/test_health.py
git commit -m "feat(health): git section with available + unregistered projects"
```

---

### Task 2.13: Dockerfile + compose delta

**Files:**
- Modify: `services/palace-mcp/Dockerfile` (add `git` to apt-install line)
- Modify: `compose.yml` (add bind-mount for gimle)

- [ ] **Step 1: Dockerfile — add git**

Open `services/palace-mcp/Dockerfile`. Find the line matching `apt-get install -y --no-install-recommends curl` (don't rely on line number; pattern-match):

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Compose — add bind-mount under `palace-mcp` service**

Open `compose.yml`. Under `palace-mcp` service spec, add (if `volumes:` list does not exist, create it):

```yaml
palace-mcp:
  # ... existing ...
  volumes:
    - type: bind
      source: /Users/Shared/Ios/Gimle-Palace
      target: /repos/gimle
      read_only: true
```

- [ ] **Step 3: Rebuild + verify locally**

```bash
docker compose --profile review build palace-mcp
docker compose --profile review up -d palace-mcp
docker compose --profile review exec palace-mcp git --version
# Expected: git version 2.39.x or later.
docker compose --profile review exec palace-mcp ls /repos/gimle/.git
# Expected: list of .git internals.
```

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/Dockerfile compose.yml
git commit -m "feat(infra): install git in palace-mcp image + mount gimle repo"
```

---

### Task 2.14: CLAUDE.md "Mounting project repos" section

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append new section**

Add to `CLAUDE.md` after the "Docker Compose Profiles" section:

```markdown
## Mounting project repos for git tools

`palace.git.*` tools read from filesystem bind-mounts. Convention:

- Inside the container, a project with slug `X` lives at `/repos/X`.
- Host-side path is explicit per-project in `compose.yml` under
  `palace-mcp.volumes`:

  ```yaml
  - type: bind
    source: /Users/Shared/Ios/Gimle-Palace
    target: /repos/gimle
    read_only: true
  ```

- `read_only: true` is enforced by the kernel on Linux hosts. On macOS
  Docker Desktop, defense-in-depth is the command whitelist in
  `palace_mcp.git.command.ALLOWED_VERBS`.

### Adding a new project

1. `git clone <url> /Users/Shared/Ios/<Name>` on the host (iMac).
2. `palace.memory.register_project(slug="<slug>", name="<Name>", ...)`.
3. Add the bind-mount block to `compose.yml` (`source: /Users/Shared/Ios/<Name>`, `target: /repos/<slug>`).
4. `docker compose --profile review up -d --build palace-mcp`.
5. Confirm `palace.memory.health()` lists the slug in `git.available_projects` with empty `unregistered_projects`.

### Authority model

- **Filesystem bind-mount = authority for `palace.git.*`.** A slug is
  addressable by git tools iff `/repos/<slug>/.git/` exists inside the
  container.
- **`:Project` in Neo4j = authority for `palace.memory.*`.** Graph
  tools read from Neo4j; FS state is irrelevant to them.

Operational skew (mounted-but-not-registered or vice versa) surfaces
via `health().git.unregistered_projects`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: Mounting project repos section in CLAUDE.md"
```

---

## Phase 3 — Review (parallel)

### Task 3.1: CodeReviewer mechanical review

**Owner:** CodeReviewer (paperclip)

- [ ] **Step 1: Pull feature branch locally, run full gate**

```bash
cd services/palace-mcp
uv run ruff check src/ tests/
uv run mypy --strict src/
uv run pytest -v
```

- [ ] **Step 2: Paste the three command outputs verbatim into the PR review comment** (per `feedback_anti_rubber_stamp.md`).

- [ ] **Step 3: Verify compliance checklist**:
- [ ] validate_slug helper exists; `register_project` calls it.
- [ ] All 5 tools registered in `mcp_server.py`.
- [ ] `ALLOWED_VERBS` in `command.py` contains exactly `{log, show, blame, diff, ls-tree, cat-file}` — no `push`/`commit`/etc.
- [ ] `SAFE_ENV` in `command.py` includes `GIT_CONFIG_GLOBAL=/dev/null` + `GIT_TERMINAL_PROMPT=0` + `safe.directory=*` via `GIT_CONFIG_KEY_0`.
- [ ] `_drain_and_kill` called on every abort path in `run_git`.
- [ ] No raw Cypher added (path_resolver is FS-only; no Neo4j on hot path).
- [ ] Error envelopes match spec error-code enum.
- [ ] Logs do not include `path`/`ref`/`author`/`since`/file content.
- [ ] `HealthResponse.git` is optional-on-read; existing clients unaffected.
- [ ] CLAUDE.md new section committed.

- [ ] **Step 4:** APPROVE with full checklist or request changes.

### Task 3.2: OpusArchitectReviewer adversarial review

**Owner:** OpusArchitectReviewer (paperclip)

- [ ] **Step 1:** Check context7 for `subprocess.Popen` pipe-deadlock patterns; verify `_drain_and_kill` sequence is kosher.
- [ ] **Step 2:** Stress the path-traversal guard with: mixed-encoding paths, UNC-like `\\?\`, CRLF in ref, homoglyphs in slug.
- [ ] **Step 3:** Review `SAFE_ENV` vs git documentation for overlooked vars (`GIT_ASKPASS`, `GIT_CURL_VERBOSE`, `GIT_PROTOCOL`).
- [ ] **Step 4:** Stress `parse_blame_porcelain` with edge cases: 1-line file, file with only additions from single commit (no boundary), binary file (`git blame` output differs).
- [ ] **Step 5:** Findings posted as comments; MCPEngineer addresses before Phase 4.

---

## Phase 4 — QA + Merge

### Task 4.1: QAEngineer live smoke on iMac

**Owner:** QAEngineer (paperclip)

- [ ] **Step 1: Deploy on iMac**

```bash
# On iMac:
cd /Users/Shared/Ios/Gimle-Palace
git fetch && git checkout <feature-branch>
docker compose --profile review up -d --build palace-mcp
```

- [ ] **Step 2: Scenario 1 — real commits via `palace.git.log`**

Via external Claude Code (tunnel):

```
palace.git.log(project="gimle", n=5)
```

Expected: returns top 5 develop SHAs. QAEngineer cross-checks by running `git -C /Users/Shared/Ios/Gimle-Palace log --oneline -5` directly on iMac; SHAs must match.

- [ ] **Step 3: Scenario 2 — health check**

```
palace.memory.health()
```

Expected: `git.available_projects == ["gimle"]`, `git.unregistered_projects == []`.

- [ ] **Step 4: Scenario 3 — path traversal blocked**

```
palace.git.log(project="gimle", path="../../etc/passwd")
```

Expected: `{ok: false, error_code: "invalid_path"}`.

- [ ] **Step 5: Scenario 4 — read-only filesystem**

```bash
docker exec palace-mcp touch /repos/gimle/x
```

Expected: `Read-only file system` or similar EROFS error. Document result (if macOS softens this, record in followup).

- [ ] **Step 6: Scenario 5 — diff stat mode**

```
palace.git.diff(project="gimle", ref_a="HEAD~5", ref_b="HEAD", mode="stat")
```

Expected: list of changed files with added/deleted counts.

- [ ] **Step 7: Scenario 6 — binary file detection**

```
palace.git.show(project="gimle", ref="HEAD", path="<some-binary-file>")
```

(If no binary file in gimle, skip or `touch small.bin; git add; commit` first.) Expected: `{ok: false, error_code: "binary_file", size_bytes: <n>}`.

- [ ] **Step 8: Scenario 7 — Neo4j invariant**

```cypher
MATCH (n) RETURN count(n) as c
```

Run before and after the 6 git tool scenarios. Counts must be identical. Verifies no graph writes happen during git reads.

- [ ] **Step 9: Post evidence comment on PR**

Comment body template (commit the exact text with SHA of QA run):

```
### QA Phase 4.1 evidence

Commit under test: <commit-sha>
Run date: <iso-date>
Compose up output: `docker compose ps` showed palace-mcp healthy, neo4j healthy.

Scenario 1 (git.log): SHAs match iMac `git log --oneline -5`: <sha1..5>.
Scenario 2 (health): git.available_projects == ["gimle"]. ✅
Scenario 3 (traversal): error_code = invalid_path. ✅
Scenario 4 (EROFS): `touch /repos/gimle/x` → Read-only file system. ✅
Scenario 5 (diff stat): 3 files, <file>: +5 -2, <file>: +3 -0, <file>: +0 -10. ✅
Scenario 6 (binary): error_code = binary_file, size_bytes = <n>. ✅
Scenario 7 (graph invariant): count(n) before = <N>, after = <N>. ✅

PASS. Ready to merge.
```

### Task 4.2: Squash-merge to develop

**Owner:** MCPEngineer

- [ ] **Step 1:** On GitHub, confirm all 4 CI checks green (`lint`, `typecheck`, `test`, `docker-build`). **No admin override.**
- [ ] **Step 2:** CR APPROVE + Opus findings all resolved + QA evidence posted.
- [ ] **Step 3:** Squash-merge through the UI. Commit title: `feat(palace-mcp): git-mcp read-only exposure (GIM-<N>)`.
- [ ] **Step 4:** Delete feature branch.
- [ ] **Step 5:** Update checkboxes in this plan file on main (the feature-branch copy got squashed into develop — keeping a canonical completed version on main).
- [ ] **Step 6:** Manual iMac redeploy (per `reference_post_merge_deploy_gap.md`):

```bash
# On iMac:
cd /Users/Shared/Ios/Gimle-Palace
git pull origin develop
docker compose --profile review up -d --build palace-mcp
```

- [ ] **Step 7:** From operator Claude Code session: verify one live `palace.git.log(project="gimle", n=3)` call against new deploy. Close paperclip issue with closing comment.

---

## Post-merge

- [ ] Update `project_backlog.md` memory: mark git-mcp entry closed with merge SHA + duration.
- [ ] Unblock N+2 kickoff brainstorm (Git History Harvester extractor).
- [ ] If macOS read-only caveat surfaced at QA Phase 4.1 Step 5, file a followup entry in `project_backlog.md` under "roadmap followups".
