# GIM-186 Git History Harvester Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `git_history` extractor producing a structured (Neo4j) +
full-text (Tantivy) dataset of commit / author / PR / PR-comment data
for a project's git history. Foundation for 6 historical extractors.

**Architecture:** New extractor package mirroring `symbol_index_python.py`
shape. 3-phase per-project ingest (pygit2 → GitHub GraphQL → checkpoint).
Own `:GitHistoryCheckpoint` node + own `GitHistoryTantivyWriter` (existing
`IngestCheckpoint` and `TantivyBridge` are SCIP-typed and cannot be reused).

**Tech Stack:** Python 3.13 + uv, Pydantic v2, pygit2, httpx (raw GraphQL),
Tantivy via tantivy-py, Neo4j AsyncDriver. Tests: pytest, respx, testcontainers,
freezegun.

**Spec:** `docs/superpowers/specs/2026-05-03-GIM-186-git-history-harvester-design.md`
**Branch:** `feature/GIM-186-git-history-harvester`
**Predecessor:** `57545cb` (develop tip)
**Plan rev2:** 2026-05-04 — Fixes 4 CRITICAL + 2 WARNING from Phase 1.2 CR (import paths, call signatures, IngestRun lifecycle, schema extension, `_get_previous_error_code` locality, `_add_doc` ternary logic).

---

## File structure

```
services/palace-mcp/src/palace_mcp/extractors/git_history/   (NEW package)
├── __init__.py                        — re-export GitHistoryExtractor
├── models.py                          — Pydantic v2 schemas
├── bot_detector.py                    — regex classifier
├── pygit2_walker.py                   — async wrapper around pygit2 walk
├── github_client.py                   — httpx GraphQL client + cost-aware backoff
├── tantivy_writer.py                  — own GitHistoryTantivyWriter
├── neo4j_writer.py                    — Cypher MERGE patterns
├── checkpoint.py                      — :GitHistoryCheckpoint own state
└── extractor.py                       — orchestrator (mirrors symbol_index_python)

services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py   (EXTEND)
services/palace-mcp/src/palace_mcp/extractors/registry.py            (EXTEND)
services/palace-mcp/src/palace_mcp/config.py                         (EXTEND)

services/palace-mcp/tests/extractors/unit/                            (NEW × 7)
├── test_git_history_models.py
├── test_git_history_bot_detector.py
├── test_git_history_pygit2_walker.py
├── test_git_history_github_client.py
├── test_git_history_tantivy_writer.py
├── test_git_history_neo4j_writer.py
├── test_git_history_checkpoint.py
└── test_git_history_extractor.py

services/palace-mcp/tests/extractors/integration/
└── test_git_history_integration.py    (NEW)

services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/   (NEW)
├── REGEN.md
├── repo/                              — synthetic .git committed
└── github_responses/*.json

services/palace-mcp/scripts/smoke_git_history.py                      (NEW)
docs/runbooks/git-history-harvester.md                                (NEW)
CLAUDE.md                                                             (EXTEND)
.env.example                                                          (EXTEND)
```

---

## Task 1: Pydantic v2 models + schema constraints

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/__init__.py`
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/models.py`
- Modify: `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py` (add 6 constraints)
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_models.py`

- [ ] **Step 1: Write failing tests for models**

Write `tests/extractors/unit/test_git_history_models.py` covering:

```python
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from palace_mcp.extractors.git_history.models import (
    Author, Commit, PR, PRComment, GitHistoryCheckpoint,
)

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def test_author_provider_git_lowercases_email():
    a = Author(provider="git", identity_key="Foo@Bar.COM",
               email="Foo@Bar.COM", name="Foo", is_bot=False,
               first_seen_at=UTC_TS, last_seen_at=UTC_TS)
    assert a.identity_key == "foo@bar.com"
    assert a.email == "foo@bar.com"


def test_author_provider_github_keeps_login_case():
    a = Author(provider="github", identity_key="FooLogin",
               email=None, name="Foo", is_bot=False,
               first_seen_at=UTC_TS, last_seen_at=UTC_TS)
    assert a.identity_key == "FooLogin"


def test_author_email_none_allowed():
    a = Author(provider="github", identity_key="login",
               email=None, name="X", is_bot=False,
               first_seen_at=UTC_TS, last_seen_at=UTC_TS)
    assert a.email is None


def test_author_email_empty_string_normalized_to_none():
    a = Author(provider="github", identity_key="login",
               email="", name="X", is_bot=False,
               first_seen_at=UTC_TS, last_seen_at=UTC_TS)
    assert a.email is None


def test_author_naive_datetime_rejected():
    naive = datetime(2026, 5, 3, 12, 0)  # no tzinfo
    with pytest.raises(ValidationError):
        Author(provider="git", identity_key="a@b.com",
               email="a@b.com", name="X", is_bot=False,
               first_seen_at=naive, last_seen_at=UTC_TS)


def test_commit_short_sha_computed():
    c = Commit(project_id="project/gimle",
               sha="0123456789abcdef0123456789abcdef01234567",
               author_provider="git", author_identity_key="a@b.com",
               committer_provider="git", committer_identity_key="a@b.com",
               message_subject="subject", message_full_truncated="body",
               committed_at=UTC_TS, parents=())
    assert c.short_sha == "0123456"


def test_commit_is_merge_computed_from_parents():
    base = dict(project_id="project/gimle",
                sha="0" * 40,
                author_provider="git", author_identity_key="a@b.com",
                committer_provider="git", committer_identity_key="a@b.com",
                message_subject="x", message_full_truncated="x",
                committed_at=UTC_TS)
    assert Commit(**base, parents=()).is_merge is False
    assert Commit(**base, parents=("1" * 40,)).is_merge is False
    assert Commit(**base, parents=("1" * 40, "2" * 40)).is_merge is True


def test_commit_invalid_sha_rejected():
    with pytest.raises(ValidationError):
        Commit(project_id="project/gimle", sha="not-hex",
               author_provider="git", author_identity_key="a@b.com",
               committer_provider="git", committer_identity_key="a@b.com",
               message_subject="x", message_full_truncated="x",
               committed_at=UTC_TS, parents=())


def test_commit_message_truncation_enforced_at_validator():
    too_long = "x" * 1100
    with pytest.raises(ValidationError):
        Commit(project_id="project/gimle", sha="0" * 40,
               author_provider="git", author_identity_key="a@b.com",
               committer_provider="git", committer_identity_key="a@b.com",
               message_subject="x", message_full_truncated=too_long,
               committed_at=UTC_TS, parents=())


def test_pr_state_lowercased_from_uppercase_input():
    pr = PR(project_id="project/gimle", number=42,
            title="t", body_truncated="b", state="MERGED",
            author_provider="github", author_identity_key="login",
            created_at=UTC_TS, merged_at=UTC_TS,
            head_sha="0" * 40, base_branch="develop")
    assert pr.state == "merged"


def test_pr_invalid_state_rejected():
    with pytest.raises(ValidationError):
        PR(project_id="project/gimle", number=42,
           title="t", body_truncated="b", state="DRAFT",
           author_provider="github", author_identity_key="login",
           created_at=UTC_TS, merged_at=None,
           head_sha=None, base_branch="develop")


def test_pr_comment_body_truncation_enforced():
    too_long = "x" * 1100
    with pytest.raises(ValidationError):
        PRComment(project_id="project/gimle", id="cmt-1", pr_number=42,
                  body_truncated=too_long,
                  author_provider="github", author_identity_key="login",
                  created_at=UTC_TS)


def test_git_history_checkpoint_round_trip():
    ckpt = GitHistoryCheckpoint(
        project_id="project/gimle",
        last_commit_sha="0" * 40,
        last_pr_updated_at=UTC_TS,
        last_phase_completed="phase1",
        updated_at=UTC_TS,
    )
    assert ckpt.last_phase_completed == "phase1"


def test_git_history_checkpoint_none_initial_state():
    ckpt = GitHistoryCheckpoint(
        project_id="project/gimle",
        last_commit_sha=None,
        last_pr_updated_at=None,
        last_phase_completed="none",
        updated_at=UTC_TS,
    )
    assert ckpt.last_commit_sha is None
```

- [ ] **Step 2: Run tests; confirm they fail**

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_git_history_models.py -v
```
Expected: ImportError on `palace_mcp.extractors.git_history.models`.

- [ ] **Step 3: Create `__init__.py` and `models.py`**

Create `services/palace-mcp/src/palace_mcp/extractors/git_history/__init__.py`:

```python
"""Git history harvester extractor package — see GIM-186 spec."""
```

Create `services/palace-mcp/src/palace_mcp/extractors/git_history/models.py`
with the full Pydantic v2 schemas from spec §3.3:

```python
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, computed_field, field_validator

_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TRUNC_MAX = 1024


def _validate_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("must be tz-aware")
    return v.astimezone(timezone.utc)


def _validate_truncated(v: str) -> str:
    if len(v) > _TRUNC_MAX + 3:
        raise ValueError(f"truncated body exceeds {_TRUNC_MAX + 3} chars: {len(v)}")
    return v


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Author(FrozenModel):
    provider: Literal["git", "github"]
    identity_key: str
    email: str | None
    name: str
    is_bot: bool
    first_seen_at: datetime
    last_seen_at: datetime

    @field_validator("identity_key", mode="after")
    @classmethod
    def _normalize_identity(cls, v: str, info) -> str:
        return v.lower() if info.data.get("provider") == "git" else v

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError(f"invalid email: {v!r}")
        return v.lower()

    @field_validator("first_seen_at", "last_seen_at")
    @classmethod
    def _tz_check(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class Commit(FrozenModel):
    project_id: str
    sha: str
    author_provider: Literal["git", "github"]
    author_identity_key: str
    committer_provider: Literal["git", "github"]
    committer_identity_key: str
    message_subject: str
    message_full_truncated: str
    committed_at: datetime
    parents: tuple[str, ...]

    @computed_field
    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @computed_field
    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @field_validator("sha")
    @classmethod
    def _check_sha(cls, v: str) -> str:
        if not _SHA_RE.match(v):
            raise ValueError(f"invalid sha: {v!r}")
        return v

    @field_validator("message_full_truncated")
    @classmethod
    def _check_truncated(cls, v: str) -> str:
        return _validate_truncated(v)

    @field_validator("committed_at")
    @classmethod
    def _tz_check(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class PR(FrozenModel):
    project_id: str
    number: int
    title: str
    body_truncated: str
    state: Literal["open", "merged", "closed"]
    author_provider: Literal["git", "github"]
    author_identity_key: str
    created_at: datetime
    merged_at: datetime | None
    head_sha: str | None
    base_branch: str

    @field_validator("state", mode="before")
    @classmethod
    def _normalize_state(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @field_validator("body_truncated")
    @classmethod
    def _check_truncated(cls, v: str) -> str:
        return _validate_truncated(v)

    @field_validator("created_at", "merged_at")
    @classmethod
    def _tz_check(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return _validate_tz(v)


class PRComment(FrozenModel):
    project_id: str
    id: str
    pr_number: int
    body_truncated: str
    author_provider: Literal["git", "github"]
    author_identity_key: str
    created_at: datetime

    @field_validator("body_truncated")
    @classmethod
    def _check_truncated(cls, v: str) -> str:
        return _validate_truncated(v)

    @field_validator("created_at")
    @classmethod
    def _tz_check(cls, v: datetime) -> datetime:
        return _validate_tz(v)


class GitHistoryCheckpoint(FrozenModel):
    project_id: str
    last_commit_sha: str | None
    last_pr_updated_at: datetime | None
    last_phase_completed: Literal["none", "phase1", "phase2"]
    updated_at: datetime

    @field_validator("last_pr_updated_at", "updated_at")
    @classmethod
    def _tz_check(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return _validate_tz(v)


class IngestSummary(FrozenModel):
    project_id: str
    run_id: str
    commits_written: int
    authors_written: int
    prs_written: int
    pr_comments_written: int
    files_touched: int
    full_resync: bool
    last_commit_sha: str | None
    last_pr_updated_at: datetime | None
    duration_ms: int
```

- [ ] **Step 4: Run tests; confirm they pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_models.py -v
```
Expected: 13/13 PASS.

- [ ] **Step 5: Extend `ensure_custom_schema()` with git_history constraints**

Modify `services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py`
to add 6 constraints to `EXPECTED_SCHEMA`:

```python
# In schema.py, append ConstraintSpec objects to EXPECTED_SCHEMA.constraints list.
# EXPECTED_SCHEMA is a SchemaDefinition dataclass, NOT a dict.
# Add after the last existing ConstraintSpec entry:
EXPECTED_SCHEMA.constraints.extend([
    ConstraintSpec(name="git_commit_sha", label="Commit", properties=("sha",)),
    ConstraintSpec(name="git_author_pk", label="Author", properties=("provider", "identity_key")),
    ConstraintSpec(name="git_pr_pk", label="PR", properties=("project_id", "number")),
    ConstraintSpec(name="git_pr_comment_id", label="PRComment", properties=("id",)),
    ConstraintSpec(name="git_file_pk", label="File", properties=("project_id", "path")),
    ConstraintSpec(name="git_history_ckpt", label="GitHistoryCheckpoint", properties=("project_id",)),
])
```

(EXPECTED_SCHEMA is a `SchemaDefinition` dataclass with `.constraints: list[ConstraintSpec]`.
Preserve existing constraint ordering. Place new block after the last existing entry.)

- [ ] **Step 6: Add schema-extension test**

Add to `tests/extractors/unit/test_git_history_models.py`:

```python
def test_ensure_custom_schema_includes_git_history_constraints():
    from palace_mcp.extractors.foundation.schema import EXPECTED_SCHEMA
    constraint_names = {c.name for c in EXPECTED_SCHEMA.constraints}
    assert "git_commit_sha" in constraint_names
    assert "git_author_pk" in constraint_names
    assert "git_history_ckpt" in constraint_names
    # Verify composite key for Author
    author_c = next(c for c in EXPECTED_SCHEMA.constraints if c.name == "git_author_pk")
    assert author_c.properties == ("provider", "identity_key")
```

- [ ] **Step 7: Run all model tests**

```bash
uv run pytest tests/extractors/unit/test_git_history_models.py -v
uv run mypy src/palace_mcp/extractors/git_history/models.py
```
Expected: 14 PASS, mypy clean.

- [ ] **Step 8: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/__init__.py \
        services/palace-mcp/src/palace_mcp/extractors/git_history/models.py \
        services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_models.py
git commit -m "feat(GIM-186): models + schema constraints for git_history"
```

---

## Task 2: Bot detector

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/bot_detector.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_bot_detector.py`

- [ ] **Step 1: Write failing tests (parametrized 30+ cases)**

```python
import pytest
from palace_mcp.extractors.git_history.bot_detector import is_bot

@pytest.mark.parametrize("email,name,expected", [
    # Positive — known bots
    ("github-actions[bot]@users.noreply.github.com", "github-actions[bot]", True),
    ("dependabot[bot]@users.noreply.github.com", "dependabot[bot]", True),
    ("any@dependabot.com", "Dependabot", True),
    ("renovate[bot]@whatever.com", "renovate[bot]", True),
    (None, "github-actions", True),
    (None, "Dependabot", True),
    (None, "Renovate[bot]", True),
    (None, "paperclip-bot", True),
    (None, "Custom[bot]", True),
    # Negative — humans with bot-like substrings (rev2 tightening)
    ("bot-fan@company.com", "Bot Fan", False),
    ("someone-bot@company.com", "Someone", False),  # rev2 critical: was bot in rev1
    ("robot@example.com", "Robot Joe", False),
    ("foo@bar.com", "github-action", False),  # close but not exact
    # Edge — empty/None handling
    (None, None, False),
    ("", "", False),
    ("foo@bar.com", "", False),
    (None, "", False),
    # Edge — case sensitivity
    ("any@DEPENDABOT.com", "any", False),  # email regex is case-sensitive (per spec); known limitation
    (None, "GITHUB-ACTIONS", True),  # name regex IS case-insensitive (per re.I)
    # Edge — Unicode in name
    (None, "Пётр[bot]", True),  # generic *[bot] suffix matches
    # Trailing whitespace
    (None, "github-actions ", False),  # exact match required; trailing ws breaks
])
def test_is_bot_parametrized(email, name, expected):
    assert is_bot(email, name) is expected
```

- [ ] **Step 2: Run tests; confirm they fail**

```bash
uv run pytest tests/extractors/unit/test_git_history_bot_detector.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `bot_detector.py` (rev2 tightened patterns)**

```python
"""Conservative regex-based bot detector — see spec GIM-186 §6."""
from __future__ import annotations
import re

_BOT_EMAIL_PATTERNS = [
    re.compile(r".*\[bot\]@users\.noreply\.github\.com$"),
    re.compile(r".*@dependabot\.com$"),
    re.compile(r"^renovate\[bot\]@.*"),
]
_BOT_NAME_PATTERNS = [
    re.compile(r"^github-actions(\[bot\])?$", re.I),
    re.compile(r"^dependabot(\[bot\])?$", re.I),
    re.compile(r"^renovate(\[bot\])?$", re.I),
    re.compile(r"^paperclip-bot$", re.I),
    re.compile(r".*\[bot\]$", re.I),
]


def is_bot(email: str | None, name: str | None) -> bool:
    """Return True if email or name matches any conservative bot pattern."""
    if email:
        if any(p.match(email) for p in _BOT_EMAIL_PATTERNS):
            return True
    if name:
        if any(p.match(name) for p in _BOT_NAME_PATTERNS):
            return True
    return False
```

- [ ] **Step 4: Run tests; confirm pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_bot_detector.py -v
uv run mypy src/palace_mcp/extractors/git_history/bot_detector.py
```
Expected: ALL parametrized PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/bot_detector.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_bot_detector.py
git commit -m "feat(GIM-186): bot detector with conservative regex (no -bot@ false positive)"
```

---

## Task 3: pygit2 walker

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/pygit2_walker.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_pygit2_walker.py`
- Modify: `services/palace-mcp/pyproject.toml` (add `pygit2` dep)

- [ ] **Step 1: Add pygit2 to project deps**

Modify `services/palace-mcp/pyproject.toml`:

```toml
# Under [project] dependencies, add:
"pygit2>=1.15,<2.0",
```

```bash
cd services/palace-mcp && uv sync
```

- [ ] **Step 2: Write failing tests using synthetic in-memory repo**

```python
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import pytest
import pygit2

from palace_mcp.extractors.git_history.pygit2_walker import (
    Pygit2Walker, CommitNotFoundError,
)


def _build_synthetic_repo(tmp: Path, n_commits: int = 5) -> str:
    """Helper: create a real git repo with n linear commits. Returns path."""
    repo_path = tmp / "synth-repo"
    repo = pygit2.init_repository(str(repo_path), bare=False)
    sig = pygit2.Signature("Foo", "foo@example.com", int(datetime.now(timezone.utc).timestamp()), 0)
    parent: list[pygit2.Oid] = []
    for i in range(n_commits):
        # Create blob, tree, commit
        blob_id = repo.create_blob(f"content-{i}".encode())
        tb = repo.TreeBuilder()
        tb.insert(f"file-{i}.txt", blob_id, pygit2.GIT_FILEMODE_BLOB)
        tree_id = tb.write()
        commit_id = repo.create_commit(
            "HEAD", sig, sig, f"commit {i}\n\nbody", tree_id, parent
        )
        parent = [commit_id]
    return str(repo_path)


def test_walker_full_walk_yields_all_commits(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=5)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    commits = list(walker.walk_since(None))
    assert len(commits) == 5


def test_walker_incremental_yields_only_new_since(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=5)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    all_commits = list(walker.walk_since(None))
    # Use third commit's sha as checkpoint
    checkpoint_sha = all_commits[2]["sha"]
    incremental = list(walker.walk_since(checkpoint_sha))
    # Walk should yield commits NEWER than checkpoint, exclusive (top 2)
    assert len(incremental) == 2


def test_walker_checkpoint_not_found_raises(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=5)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    with pytest.raises(CommitNotFoundError):
        list(walker.walk_since("0" * 40))


def test_walker_head_sha_returns_latest(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=3)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    head = walker.head_sha()
    all_commits = list(walker.walk_since(None))
    assert head == all_commits[0]["sha"]  # most recent first


def test_walker_extracts_author_committer_email(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=1)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    commits = list(walker.walk_since(None))
    assert commits[0]["author_email"] == "foo@example.com"
    assert commits[0]["committer_email"] == "foo@example.com"


def test_walker_yields_touched_files(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=3)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    commits = list(walker.walk_since(None))
    for c in commits:
        assert "touched_files" in c
        assert len(c["touched_files"]) >= 1
```

- [ ] **Step 3: Run tests; confirm fail**

```bash
uv run pytest tests/extractors/unit/test_git_history_pygit2_walker.py -v
```
Expected: ImportError.

- [ ] **Step 4: Implement `pygit2_walker.py`**

```python
"""pygit2 commit walker — see spec GIM-186 §5.1 Phase 1."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import pygit2


class CommitNotFoundError(Exception):
    """Raised when checkpoint sha is not found in repo (e.g. force-push)."""


class Pygit2Walker:
    """Synchronous walker; caller wraps in async generator."""

    def __init__(self, repo_path: Path) -> None:
        self._repo = pygit2.Repository(str(repo_path))

    def head_sha(self) -> str:
        return str(self._repo.head.target)

    def walk_since(self, last_sha: str | None) -> Iterator[dict]:
        """Yield dicts representing commits newer than last_sha (exclusive).

        If last_sha is None, yield ALL commits (full walk).
        Order: most-recent first.
        """
        if last_sha is not None:
            try:
                self._repo.get(last_sha)
                if self._repo.get(last_sha) is None:
                    raise CommitNotFoundError(f"sha not in repo: {last_sha}")
            except (KeyError, ValueError) as exc:
                raise CommitNotFoundError(f"sha not in repo: {last_sha}") from exc

        for commit in self._repo.walk(self._repo.head.target,
                                       pygit2.GIT_SORT_TIME):
            sha = str(commit.id)
            if last_sha is not None and sha == last_sha:
                break
            yield self._commit_to_dict(commit)

    @staticmethod
    def _commit_to_dict(commit: pygit2.Commit) -> dict:
        author = commit.author
        committer = commit.committer
        message = commit.message
        subject = message.split("\n", 1)[0][:200]
        full_truncated = message[:1024] + ("..." if len(message) > 1024 else "")
        ts = datetime.fromtimestamp(commit.commit_time, tz=timezone.utc)
        # Touched files via diff against parent
        touched = []
        if commit.parents:
            diff = commit.tree.diff_to_tree(commit.parents[0].tree)
            touched = [d.delta.new_file.path for d in diff]
        else:
            touched = [e.path for e in commit.tree if e.type_str == "blob"]
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
```

- [ ] **Step 5: Run tests; pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_pygit2_walker.py -v
uv run mypy src/palace_mcp/extractors/git_history/pygit2_walker.py
```

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/pygit2_walker.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_pygit2_walker.py \
        services/palace-mcp/pyproject.toml services/palace-mcp/uv.lock
git commit -m "feat(GIM-186): pygit2 walker with incremental + resync detection"
```

---

## Task 4: GitHub GraphQL client

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/github_client.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_github_client.py`

- [ ] **Step 1: Add `respx` to dev deps if not already present**

Verify in `services/palace-mcp/pyproject.toml`. If missing, add to `[dependency-groups].dev`:
```toml
"respx>=0.21",
```

- [ ] **Step 2: Write failing tests with respx mocks**

```python
from datetime import datetime, timezone
import httpx
import pytest
import respx

from palace_mcp.extractors.git_history.github_client import (
    GitHubClient, RateLimitExhausted,
)


@pytest.mark.asyncio
async def test_fetch_prs_single_page():
    fake_response = {
        "data": {
            "repository": {
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "number": 1, "title": "first", "body": "b",
                            "state": "MERGED",
                            "author": {"login": "user1", "email": "user1@example.com"},
                            "createdAt": "2026-05-01T10:00:00Z",
                            "updatedAt": "2026-05-01T10:00:00Z",
                            "mergedAt": "2026-05-01T10:30:00Z",
                            "headRefOid": "0" * 40,
                            "baseRef": {"name": "develop"},
                            "comments": {
                                "totalCount": 0,
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [],
                            },
                        }
                    ],
                },
                "rateLimit": {"cost": 1, "remaining": 4999, "limit": 5000,
                              "resetAt": "2026-05-03T13:00:00Z"},
            }
        }
    }
    with respx.mock:
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(200, json=fake_response)
        )
        client = GitHubClient(token="tok")
        prs = []
        async for batch in client.fetch_prs_since("owner", "repo", since=None):
            prs.extend(batch)
        assert len(prs) == 1
        assert prs[0]["number"] == 1


@pytest.mark.asyncio
async def test_fetch_prs_pagination_two_pages():
    page1 = {"data": {"repository": {
        "pullRequests": {
            "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR1"},
            "nodes": [{"number": 1, "title": "a", "body": "",
                       "state": "OPEN", "author": {"login": "u"},
                       "createdAt": "2026-05-01T00:00:00Z",
                       "updatedAt": "2026-05-01T00:00:00Z",
                       "mergedAt": None, "headRefOid": None,
                       "baseRef": {"name": "develop"},
                       "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}],
        },
        "rateLimit": {"cost": 1, "remaining": 4998, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    page2 = {"data": {"repository": {
        "pullRequests": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"number": 2, "title": "b", "body": "",
                       "state": "MERGED", "author": {"login": "u"},
                       "createdAt": "2026-04-30T00:00:00Z",
                       "updatedAt": "2026-04-30T00:00:00Z",
                       "mergedAt": "2026-04-30T00:00:00Z",
                       "headRefOid": "0" * 40,
                       "baseRef": {"name": "develop"},
                       "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}],
        },
        "rateLimit": {"cost": 1, "remaining": 4997, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    with respx.mock:
        route = respx.post("https://api.github.com/graphql")
        route.side_effect = [
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ]
        client = GitHubClient(token="tok")
        all_prs = []
        async for batch in client.fetch_prs_since("o", "r", since=None):
            all_prs.extend(batch)
        assert [pr["number"] for pr in all_prs] == [1, 2]


@pytest.mark.asyncio
async def test_fetch_prs_stops_at_since_boundary():
    """PR with updated_at < since must NOT be yielded."""
    fake = {"data": {"repository": {
        "pullRequests": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {"number": 1, "title": "newer", "body": "",
                 "state": "OPEN", "author": {"login": "u"},
                 "createdAt": "2026-05-03T12:00:00Z",
                 "updatedAt": "2026-05-03T12:00:00Z",
                 "mergedAt": None, "headRefOid": None,
                 "baseRef": {"name": "develop"},
                 "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}},
                {"number": 2, "title": "older", "body": "",
                 "state": "MERGED", "author": {"login": "u"},
                 "createdAt": "2026-05-01T00:00:00Z",
                 "updatedAt": "2026-05-01T00:00:00Z",  # before since
                 "mergedAt": "2026-05-01T00:00:00Z", "headRefOid": "0"*40,
                 "baseRef": {"name": "develop"},
                 "comments": {"totalCount": 0, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}},
            ],
        },
        "rateLimit": {"cost": 1, "remaining": 4999, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    since = datetime(2026, 5, 2, tzinfo=timezone.utc)
    with respx.mock:
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(200, json=fake)
        )
        client = GitHubClient(token="tok")
        all_prs = []
        async for batch in client.fetch_prs_since("o", "r", since=since):
            all_prs.extend(batch)
        assert [pr["number"] for pr in all_prs] == [1]


@pytest.mark.asyncio
async def test_rate_limit_fail_fast_below_threshold():
    """remaining < 100 → raise RateLimitExhausted, NOT sleep."""
    fake = {"data": {"repository": {
        "pullRequests": {"pageInfo": {"hasNextPage": True, "endCursor": "C"},
                         "nodes": []},
        "rateLimit": {"cost": 50, "remaining": 50, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    with respx.mock:
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(200, json=fake)
        )
        client = GitHubClient(token="tok")
        with pytest.raises(RateLimitExhausted):
            async for batch in client.fetch_prs_since("o", "r", since=None):
                pass


@pytest.mark.asyncio
async def test_429_retry_with_backoff():
    """429 followed by 200 should succeed within bounded backoff."""
    fake_ok = {"data": {"repository": {
        "pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []},
        "rateLimit": {"cost": 1, "remaining": 4999, "limit": 5000,
                      "resetAt": "2026-05-03T13:00:00Z"},
    }}}
    with respx.mock:
        route = respx.post("https://api.github.com/graphql")
        route.side_effect = [
            httpx.Response(429, json={"error": "rate"}),
            httpx.Response(200, json=fake_ok),
        ]
        client = GitHubClient(token="tok", max_retries=2, retry_initial_ms=10)
        async for _ in client.fetch_prs_since("o", "r", since=None):
            pass
        assert route.call_count == 2
```

- [ ] **Step 3: Run tests; confirm fail**

```bash
uv run pytest tests/extractors/unit/test_git_history_github_client.py -v
```
Expected: ImportError.

- [ ] **Step 4: Implement `github_client.py`**

```python
"""GitHub GraphQL client — see spec GIM-186 §5.2."""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import AsyncIterator
import httpx

GRAPHQL_URL = "https://api.github.com/graphql"
PR_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 50, after: $cursor,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body state
        author { login ... on User { email } }
        createdAt updatedAt mergedAt
        headRefOid baseRef { name }
        comments(first: 100) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            id body
            author { login ... on User { email } }
            createdAt
          }
        }
      }
    }
    rateLimit { cost remaining limit resetAt }
  }
}
"""


class RateLimitExhausted(Exception):
    """Raised when GraphQL budget would be exhausted; fail-fast (no sleep)."""


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        max_retries: int = 3,
        retry_initial_ms: int = 500,
        budget_floor: int = 100,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
        )
        self._max_retries = max_retries
        self._retry_initial_ms = retry_initial_ms
        self._budget_floor = budget_floor

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_prs_since(
        self,
        repo_owner: str,
        repo_name: str,
        since: datetime | None,
    ) -> AsyncIterator[list[dict]]:
        cursor: str | None = None
        while True:
            resp_json = await self._post_query(
                PR_QUERY,
                {"owner": repo_owner, "name": repo_name, "cursor": cursor},
            )
            repo_data = resp_json["data"]["repository"]
            page = repo_data["pullRequests"]
            rate_limit = repo_data["rateLimit"]

            # Cost-aware fail-fast (spec §5.2)
            if rate_limit["remaining"] < self._budget_floor:
                raise RateLimitExhausted(
                    f"remaining={rate_limit['remaining']} < floor={self._budget_floor}"
                )

            # Yield PRs that are newer than `since`
            batch = []
            for pr in page["nodes"]:
                pr_updated = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
                if since is not None and pr_updated < since:
                    yield batch
                    return  # stop outer pagination — older than checkpoint
                batch.append(pr)
            yield batch

            if not page["pageInfo"]["hasNextPage"]:
                return
            cursor = page["pageInfo"]["endCursor"]

    async def _post_query(self, query: str, variables: dict) -> dict:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            if attempt > 0:
                delay_s = (self._retry_initial_ms / 1000.0) * (2 ** (attempt - 1))
                await asyncio.sleep(delay_s)
            try:
                resp = await self._client.post(
                    GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                )
            except httpx.RequestError as exc:
                last_exc = exc
                continue
            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"transient {resp.status_code}", request=resp.request, response=resp
                )
                continue
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"github graphql {resp.status_code}: {resp.text[:200]}",
                    request=resp.request, response=resp,
                )
            return resp.json()
        raise last_exc or RuntimeError("github graphql retries exhausted")
```

- [ ] **Step 5: Run tests; pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_github_client.py -v
uv run mypy src/palace_mcp/extractors/git_history/github_client.py
```
Expected: 5 PASS, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/github_client.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_github_client.py \
        services/palace-mcp/pyproject.toml services/palace-mcp/uv.lock
git commit -m "feat(GIM-186): GitHub GraphQL client with cost-aware fail-fast"
```

---

## Task 5: Tantivy writer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/tantivy_writer.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_tantivy_writer.py`

- [ ] **Step 1: Write failing tests**

```python
from datetime import datetime, timezone
from pathlib import Path
import pytest

from palace_mcp.extractors.git_history.tantivy_writer import GitHistoryTantivyWriter
from palace_mcp.extractors.git_history.models import Commit, PR, PRComment

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_writer_writes_commit_doc(tmp_path: Path):
    writer = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    async with writer:
        commit = Commit(
            project_id="project/gimle", sha="0" * 40,
            author_provider="git", author_identity_key="a@b.com",
            committer_provider="git", committer_identity_key="a@b.com",
            message_subject="subject", message_full_truncated="subject\n\nbody",
            committed_at=UTC_TS, parents=(),
        )
        await writer.add_commit_async(commit, body_full="subject\n\nfull body of commit")
    # Verify by reopening and searching
    by_searcher = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    docs = by_searcher.search_by_doc_id_sync("0" * 40)
    assert len(docs) == 1


@pytest.mark.asyncio
async def test_writer_writes_pr_and_comment(tmp_path: Path):
    writer = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    async with writer:
        pr = PR(project_id="project/gimle", number=42, title="t",
                body_truncated="b", state="merged",
                author_provider="github", author_identity_key="login",
                created_at=UTC_TS, merged_at=UTC_TS, head_sha="0"*40,
                base_branch="develop")
        await writer.add_pr_async(pr, body_full="full PR body")
        cmt = PRComment(project_id="project/gimle", id="cmt1", pr_number=42,
                        body_truncated="c", author_provider="github",
                        author_identity_key="login", created_at=UTC_TS)
        await writer.add_pr_comment_async(cmt, body_full="full comment body")
    reader = GitHistoryTantivyWriter(index_path=tmp_path / "git_history")
    pr_docs = reader.search_by_doc_id_sync("42")
    cmt_docs = reader.search_by_doc_id_sync("cmt1")
    assert len(pr_docs) == 1
    assert len(cmt_docs) == 1
```

- [ ] **Step 2: Run tests; confirm fail**

```bash
uv run pytest tests/extractors/unit/test_git_history_tantivy_writer.py -v
```

- [ ] **Step 3: Implement `tantivy_writer.py`**

```python
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
      - ts (date), is_bot (bool)
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
        sb.add_text_field("doc_kind", stored=True, fast=True)
        sb.add_text_field("project_id", stored=True, fast=True)
        sb.add_text_field("doc_id", stored=True, fast=True)
        sb.add_text_field("body", stored=True)
        sb.add_text_field("author_identity_key", stored=True, fast=True)
        sb.add_date_field("ts", stored=True, fast=True)
        sb.add_boolean_field("is_bot", stored=True, fast=True)
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
            "body": body_full[:65535],  # Tantivy soft limit; spec §3.4 inv 4 enforces upstream
            "author_identity_key": commit.author_identity_key,
            "ts": commit.committed_at,
            "is_bot": False,  # caller looks up Author.is_bot separately if needed
        })

    async def add_pr_async(self, pr: PR, body_full: str) -> None:
        await self._add_doc({
            "doc_kind": "pr",
            "project_id": pr.project_id,
            "doc_id": str(pr.number),
            "body": body_full[:65535],
            "author_identity_key": pr.author_identity_key,
            "ts": pr.created_at,
            "is_bot": False,
        })

    async def add_pr_comment_async(self, comment: PRComment, body_full: str) -> None:
        await self._add_doc({
            "doc_kind": "pr_comment",
            "project_id": comment.project_id,
            "doc_id": comment.id,
            "body": body_full[:65535],
            "author_identity_key": comment.author_identity_key,
            "ts": comment.created_at,
            "is_bot": False,
        })

    async def _add_doc(self, fields: dict) -> None:
        if self._writer is None:
            raise RuntimeError("writer not opened (use async with)")
        doc = tantivy.Document()
        for k, v in fields.items():
            if k == "ts":
                doc.add_date(k, v)
            elif k == "is_bot":
                doc.add_text(k, "true" if v else "false")
            else:
                doc.add_text(k, str(v))
        await asyncio.get_running_loop().run_in_executor(
            None, self._writer.add_document, doc
        )

    def search_by_doc_id_sync(self, doc_id: str) -> list[dict]:
        searcher = self._index.searcher()
        query = self._index.parse_query(doc_id, ["doc_id"])
        results = searcher.search(query, 10).hits
        return [searcher.doc(hit[1]).to_dict() for hit in results]
```

- [ ] **Step 4: Run tests; pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_tantivy_writer.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/tantivy_writer.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_tantivy_writer.py
git commit -m "feat(GIM-186): GitHistoryTantivyWriter with own schema (separate from TantivyBridge)"
```

---

## Task 6: Neo4j writer + Author MERGE invariants

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/neo4j_writer.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_neo4j_writer.py`

- [ ] **Step 1: Write failing tests using neo4j-rust-ext or AsyncMock**

```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from palace_mcp.extractors.git_history.neo4j_writer import (
    write_commit_with_author, _MERGE_AUTHOR_CYPHER, _MERGE_COMMIT_CYPHER,
)
from palace_mcp.extractors.git_history.models import Commit

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def test_merge_author_cypher_uses_on_create_and_on_match():
    """Spec §3.4 invariant 5 requires both clauses for time window preservation."""
    assert "ON CREATE SET" in _MERGE_AUTHOR_CYPHER
    assert "ON MATCH SET" in _MERGE_AUTHOR_CYPHER
    # Verify first_seen_at uses CASE for monotonicity
    assert "first_seen_at = CASE" in _MERGE_AUTHOR_CYPHER
    assert "last_seen_at = CASE" in _MERGE_AUTHOR_CYPHER


def test_merge_commit_cypher_uses_merge_for_idempotency():
    assert "MERGE" in _MERGE_COMMIT_CYPHER
    assert "Commit" in _MERGE_COMMIT_CYPHER


@pytest.mark.asyncio
async def test_write_commit_executes_two_queries_per_commit():
    """1 query for Author, 1 for Commit (and edges, possibly batched)."""
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    commit_dict = {
        "sha": "0" * 40, "author_email": "a@b.com", "author_name": "A",
        "committer_email": "a@b.com", "committer_name": "A",
        "message_subject": "x", "message_full_truncated": "x",
        "committed_at": UTC_TS, "parents": (), "touched_files": ["f.py"],
    }
    await write_commit_with_author(driver, "project/gimle", commit_dict, is_bot=False)
    assert driver.execute_query.await_count >= 2
```

- [ ] **Step 2: Run tests; confirm fail**

```bash
uv run pytest tests/extractors/unit/test_git_history_neo4j_writer.py -v
```

- [ ] **Step 3: Implement `neo4j_writer.py`**

```python
"""Neo4j writer with explicit ON CREATE / ON MATCH for time-window preservation.

See spec GIM-186 §3.4 invariant 5.
"""
from __future__ import annotations
from neo4j import AsyncDriver

_MERGE_AUTHOR_CYPHER = """
MERGE (a:Author {provider: $provider, identity_key: $identity_key})
ON CREATE SET
  a.email = $email, a.name = $name, a.is_bot = $is_bot,
  a.first_seen_at = $ts, a.last_seen_at = $ts,
  a.project_id = $project_id
ON MATCH SET
  a.last_seen_at = CASE
    WHEN $ts > coalesce(a.last_seen_at, datetime('1970-01-01T00:00:00Z'))
    THEN $ts ELSE a.last_seen_at
  END,
  a.first_seen_at = CASE
    WHEN $ts < coalesce(a.first_seen_at, datetime('9999-12-31T23:59:59Z'))
    THEN $ts ELSE a.first_seen_at
  END,
  a.email = coalesce(a.email, $email),
  a.is_bot = $is_bot
"""

_MERGE_COMMIT_CYPHER = """
MERGE (c:Commit {sha: $sha})
ON CREATE SET
  c.project_id = $project_id,
  c.author_provider = $author_provider,
  c.author_identity_key = $author_identity_key,
  c.committer_provider = $committer_provider,
  c.committer_identity_key = $committer_identity_key,
  c.message_subject = $message_subject,
  c.message_full_truncated = $message_full_truncated,
  c.committed_at = $committed_at,
  c.parents = $parents
WITH c
MATCH (a:Author {provider: $author_provider, identity_key: $author_identity_key})
MERGE (c)-[:AUTHORED_BY]->(a)
WITH c
MATCH (cm:Author {provider: $committer_provider, identity_key: $committer_identity_key})
MERGE (c)-[:COMMITTED_BY]->(cm)
"""

_MERGE_TOUCHED_CYPHER = """
UNWIND $files AS path
MERGE (f:File {project_id: $project_id, path: path})
WITH f
MATCH (c:Commit {sha: $sha})
MERGE (c)-[:TOUCHED]->(f)
"""


async def write_commit_with_author(
    driver: AsyncDriver,
    project_id: str,
    commit_dict: dict,
    *,
    is_bot: bool,
) -> None:
    """Write Author + Commit + Touched edges idempotently."""
    # 1. MERGE Author (provider="git" for pygit2-walker authors)
    await driver.execute_query(
        _MERGE_AUTHOR_CYPHER,
        provider="git",
        identity_key=commit_dict["author_email"].lower(),
        email=commit_dict["author_email"].lower(),
        name=commit_dict["author_name"],
        is_bot=is_bot,
        ts=commit_dict["committed_at"],
        project_id=project_id,
    )
    if commit_dict["committer_email"] != commit_dict["author_email"]:
        await driver.execute_query(
            _MERGE_AUTHOR_CYPHER,
            provider="git",
            identity_key=commit_dict["committer_email"].lower(),
            email=commit_dict["committer_email"].lower(),
            name=commit_dict["committer_name"],
            is_bot=is_bot,
            ts=commit_dict["committed_at"],
            project_id=project_id,
        )

    # 2. MERGE Commit + edges
    await driver.execute_query(
        _MERGE_COMMIT_CYPHER,
        sha=commit_dict["sha"],
        project_id=project_id,
        author_provider="git",
        author_identity_key=commit_dict["author_email"].lower(),
        committer_provider="git",
        committer_identity_key=commit_dict["committer_email"].lower(),
        message_subject=commit_dict["message_subject"],
        message_full_truncated=commit_dict["message_full_truncated"],
        committed_at=commit_dict["committed_at"],
        parents=list(commit_dict["parents"]),
    )

    # 3. Touched files (batched UNWIND)
    if commit_dict["touched_files"]:
        await driver.execute_query(
            _MERGE_TOUCHED_CYPHER,
            files=commit_dict["touched_files"],
            project_id=project_id,
            sha=commit_dict["sha"],
        )


# Similar functions for write_pr / write_pr_comments — same MERGE-with-edge pattern.
# (Implementation per spec §5.1 Phase 2; details parallel to Commit.)
```

Add `write_pr` and `write_pr_comments` async functions following the
same pattern (MERGE node + MATCH related Author + MERGE edges).

- [ ] **Step 4: Run unit tests; pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_neo4j_writer.py -v
uv run mypy src/palace_mcp/extractors/git_history/neo4j_writer.py
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/neo4j_writer.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_neo4j_writer.py
git commit -m "feat(GIM-186): neo4j writer with explicit ON CREATE/MATCH for Author time-window"
```

---

## Task 7: Checkpoint module

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/checkpoint.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_checkpoint.py`

- [ ] **Step 1: Write failing tests**

```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from palace_mcp.extractors.git_history.checkpoint import (
    write_git_history_checkpoint, load_git_history_checkpoint,
)
from palace_mcp.extractors.git_history.models import GitHistoryCheckpoint

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_write_checkpoint_phase1_only():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    await write_git_history_checkpoint(
        driver, "project/gimle",
        last_commit_sha="0" * 40,
        last_pr_updated_at=None,
        last_phase_completed="phase1",
    )
    assert driver.execute_query.await_count == 1
    args = driver.execute_query.await_args
    assert args.kwargs["last_phase_completed"] == "phase1"


@pytest.mark.asyncio
async def test_write_checkpoint_phase2_advances_pr_timestamp():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    await write_git_history_checkpoint(
        driver, "project/gimle",
        last_commit_sha="0" * 40,
        last_pr_updated_at=UTC_TS,
        last_phase_completed="phase2",
    )
    args = driver.execute_query.await_args
    assert args.kwargs["last_pr_updated_at"] == UTC_TS


@pytest.mark.asyncio
async def test_load_checkpoint_returns_default_when_absent():
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    ckpt = await load_git_history_checkpoint(driver, "project/gimle")
    assert ckpt.last_commit_sha is None
    assert ckpt.last_phase_completed == "none"


@pytest.mark.asyncio
async def test_load_checkpoint_returns_persisted_state():
    record = MagicMock()
    record.__getitem__ = lambda _self, key: {
        "project_id": "project/gimle",
        "last_commit_sha": "0" * 40,
        "last_pr_updated_at": UTC_TS,
        "last_phase_completed": "phase2",
        "updated_at": UTC_TS,
    }[key]
    driver = MagicMock()
    driver.execute_query = AsyncMock(return_value=MagicMock(records=[record]))
    ckpt = await load_git_history_checkpoint(driver, "project/gimle")
    assert ckpt.last_commit_sha == "0" * 40
    assert ckpt.last_phase_completed == "phase2"
```

- [ ] **Step 2: Run tests; confirm fail**

- [ ] **Step 3: Implement `checkpoint.py`**

```python
"""GitHistoryCheckpoint own state persistence — see spec §3.6."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal
from neo4j import AsyncDriver

from palace_mcp.extractors.git_history.models import GitHistoryCheckpoint


async def write_git_history_checkpoint(
    driver: AsyncDriver,
    project_id: str,
    *,
    last_commit_sha: str | None,
    last_pr_updated_at: datetime | None,
    last_phase_completed: Literal["none", "phase1", "phase2"],
) -> None:
    cypher = """
    MERGE (c:GitHistoryCheckpoint {project_id: $project_id})
    SET c.last_commit_sha = $last_commit_sha,
        c.last_pr_updated_at = $last_pr_updated_at,
        c.last_phase_completed = $last_phase_completed,
        c.updated_at = datetime()
    """
    await driver.execute_query(
        cypher,
        project_id=project_id,
        last_commit_sha=last_commit_sha,
        last_pr_updated_at=last_pr_updated_at,
        last_phase_completed=last_phase_completed,
    )


async def load_git_history_checkpoint(
    driver: AsyncDriver,
    project_id: str,
) -> GitHistoryCheckpoint:
    """Return persisted checkpoint, or a fresh "none" state if absent."""
    cypher = """
    MATCH (c:GitHistoryCheckpoint {project_id: $project_id})
    RETURN c.project_id AS project_id,
           c.last_commit_sha AS last_commit_sha,
           c.last_pr_updated_at AS last_pr_updated_at,
           c.last_phase_completed AS last_phase_completed,
           c.updated_at AS updated_at
    """
    result = await driver.execute_query(cypher, project_id=project_id)
    if not result.records:
        return GitHistoryCheckpoint(
            project_id=project_id,
            last_commit_sha=None,
            last_pr_updated_at=None,
            last_phase_completed="none",
            updated_at=datetime.now(timezone.utc),
        )
    row = result.records[0]
    return GitHistoryCheckpoint(
        project_id=row["project_id"],
        last_commit_sha=row["last_commit_sha"],
        last_pr_updated_at=row["last_pr_updated_at"],
        last_phase_completed=row["last_phase_completed"],
        updated_at=row["updated_at"],
    )
```

- [ ] **Step 4: Run tests; pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_checkpoint.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/checkpoint.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_checkpoint.py
git commit -m "feat(GIM-186): GitHistoryCheckpoint own state node"
```

---

## Task 8: Extractor orchestrator

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/git_history/extractor.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_git_history_extractor.py`

- [ ] **Step 1: Read reference implementation**

Open `services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py:67-104`
and use as the structural template. Key pattern points:

1. Class inherits `BaseExtractor`.
2. `name`, `description`, `constraints`, `indexes` ClassVars.
3. `async def run(*, graphiti, ctx) -> ExtractorStats`.
4. Deferred import of `get_driver`/`get_settings` from `mcp_server`.
5. Pre-flight: `_get_previous_error_code` → `check_resume_budget`.
6. `ensure_custom_schema(driver)`.
7. Per-phase work.
8. Final return `ExtractorStats(nodes_written=N, edges_written=M)`.

- [ ] **Step 2: Write failing tests for extractor**

```python
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from palace_mcp.extractors.git_history.extractor import GitHistoryExtractor
from palace_mcp.extractors.base import ExtractorRunContext, ExtractorStats

UTC_TS = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="gimle",
        group_id="project/gimle",
        repo_path=repo_path,
        run_id="run-1",
        duration_ms=0,
        logger=MagicMock(),
    )


@pytest.mark.asyncio
async def test_run_returns_extractor_stats(tmp_path: Path):
    """Smoke: extractor returns ExtractorStats with both counters set."""
    # Build minimal synthetic repo via Task 3 helper
    from tests.extractors.unit.test_git_history_pygit2_walker import _build_synthetic_repo
    repo_path = _build_synthetic_repo(tmp_path, n_commits=2)

    fake_driver = MagicMock()
    fake_driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    fake_settings = MagicMock(github_token=None,
                              git_history_tantivy_index_path=tmp_path / "tnt")

    with patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver), \
         patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings), \
         patch("palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor._get_previous_error_code",
               new=AsyncMock(return_value=None)), \
         patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.create_ingest_run",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
               new=AsyncMock()):
        extractor = GitHistoryExtractor()
        stats = await extractor.run(graphiti=MagicMock(),
                                    ctx=_make_ctx(Path(repo_path)))
    assert isinstance(stats, ExtractorStats)
    assert stats.nodes_written >= 2  # at least 2 commits
    assert stats.edges_written >= 4  # AUTHORED_BY + COMMITTED_BY × 2 commits


@pytest.mark.asyncio
async def test_run_skips_phase2_when_no_github_token(tmp_path: Path, caplog):
    """When PALACE_GITHUB_TOKEN unset, Phase 2 emits skip event + Phase 1 still runs."""
    import logging
    from tests.extractors.unit.test_git_history_pygit2_walker import _build_synthetic_repo
    repo_path = _build_synthetic_repo(tmp_path, n_commits=1)
    fake_driver = MagicMock()
    fake_driver.execute_query = AsyncMock(return_value=MagicMock(records=[]))
    fake_settings = MagicMock(github_token=None,
                              git_history_tantivy_index_path=tmp_path / "tnt")
    with patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver), \
         patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings), \
         patch("palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor._get_previous_error_code",
               new=AsyncMock(return_value=None)), \
         patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.create_ingest_run",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
               new=AsyncMock()), \
         caplog.at_level(logging.WARNING):
        extractor = GitHistoryExtractor()
        await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(Path(repo_path)))
    skip_events = [r for r in caplog.records
                   if getattr(r, "event", None) == "git_history_phase2_skipped_no_token"]
    assert len(skip_events) == 1


@pytest.mark.asyncio
async def test_run_emits_resync_event_on_invalid_checkpoint(tmp_path: Path, caplog):
    """Force-push scenario: load checkpoint with invalid sha; walker resyncs."""
    import logging
    from tests.extractors.unit.test_git_history_pygit2_walker import _build_synthetic_repo
    repo_path = _build_synthetic_repo(tmp_path, n_commits=2)

    # Pre-load checkpoint with sha that DOES NOT exist in repo
    bogus_sha = "f" * 40
    fake_driver = MagicMock()

    async def _fake_execute(query, **kwargs):
        if "MATCH (c:GitHistoryCheckpoint" in query:
            mock_record = MagicMock()
            mock_record.__getitem__ = lambda _, k: {
                "project_id": "project/gimle",
                "last_commit_sha": bogus_sha,
                "last_pr_updated_at": None,
                "last_phase_completed": "phase1",
                "updated_at": UTC_TS,
            }[k]
            return MagicMock(records=[mock_record])
        return MagicMock(records=[])

    fake_driver.execute_query = AsyncMock(side_effect=_fake_execute)
    fake_settings = MagicMock(github_token=None,
                              git_history_tantivy_index_path=tmp_path / "tnt")

    with patch("palace_mcp.mcp_server.get_driver", return_value=fake_driver), \
         patch("palace_mcp.mcp_server.get_settings", return_value=fake_settings), \
         patch("palace_mcp.extractors.git_history.extractor.ensure_custom_schema",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor._get_previous_error_code",
               new=AsyncMock(return_value=None)), \
         patch("palace_mcp.extractors.git_history.extractor.check_resume_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.check_phase_budget"), \
         patch("palace_mcp.extractors.git_history.extractor.create_ingest_run",
               new=AsyncMock()), \
         patch("palace_mcp.extractors.git_history.extractor.finalize_ingest_run",
               new=AsyncMock()), \
         caplog.at_level(logging.WARNING):
        extractor = GitHistoryExtractor()
        await extractor.run(graphiti=MagicMock(), ctx=_make_ctx(Path(repo_path)))
    resync_events = [r for r in caplog.records
                     if getattr(r, "event", None) == "git_history_resync_full"]
    assert len(resync_events) == 1
```

- [ ] **Step 3: Run tests; confirm fail**

- [ ] **Step 4: Implement `extractor.py` mirroring `symbol_index_python.py`**

```python
"""GitHistoryExtractor — see spec §5.1. Mirrors symbol_index_python pattern."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import ClassVar

from palace_mcp.extractors.base import (
    BaseExtractor, ExtractorRunContext, ExtractorStats,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.circuit_breaker import (
    check_resume_budget, check_phase_budget,
)
from palace_mcp.extractors.foundation.schema import ensure_custom_schema
from palace_mcp.extractors.foundation.checkpoint import (
    create_ingest_run, finalize_ingest_run,
)
from palace_mcp.extractors.git_history.bot_detector import is_bot
from palace_mcp.extractors.git_history.checkpoint import (
    load_git_history_checkpoint, write_git_history_checkpoint,
)
from palace_mcp.extractors.git_history.github_client import (
    GitHubClient, RateLimitExhausted,
)
from palace_mcp.extractors.git_history.neo4j_writer import (
    write_commit_with_author,
    # write_pr_with_author, write_pr_comment_with_author — implement in Task 6
)
from palace_mcp.extractors.git_history.pygit2_walker import (
    Pygit2Walker, CommitNotFoundError,
)
from palace_mcp.extractors.git_history.tantivy_writer import GitHistoryTantivyWriter

log = logging.getLogger("watchdog.daemon")  # use module logger via spec convention


async def _get_previous_error_code(driver: "AsyncDriver", project: str) -> str | None:
    """Per-extractor circuit-breaker query (mirrors symbol_index_python.py:346)."""
    _QUERY = """
    MATCH (r:IngestRun {project: $project, extractor_name: 'git_history'})
    WHERE r.success = false
    RETURN r.error_code AS error_code
    ORDER BY r.started_at DESC
    LIMIT 1
    """
    async with driver.session() as session:
        result = await session.run(_QUERY, project=project)
        record = await result.single()
        return record["error_code"] if record else None


class GitHistoryExtractor(BaseExtractor):
    name: ClassVar[str] = "git_history"
    description: ClassVar[str] = (
        "Walk git commit history + GitHub PR/comment data. Foundation for "
        "6 historical extractors (#11, #12, #26, #32, #43, #44)."
    )
    constraints: ClassVar[list[str]] = []  # added via ensure_custom_schema extension
    indexes: ClassVar[list[str]] = []

    async def run(
        self, *, graphiti, ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        # Deferred import per symbol_index_python.py pattern
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()
        if driver is None or settings is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="driver/settings unavailable",
                recoverable=False, action="retry",
            )

        # Pre-flight
        previous_error = await _get_previous_error_code(driver, ctx.project_slug)
        check_resume_budget(previous_error_code=previous_error)
        await ensure_custom_schema(driver)

        # IngestRun lifecycle — mirrors symbol_index_python.py:99
        await create_ingest_run(
            driver, run_id=ctx.run_id,
            project=ctx.project_slug, extractor_name=self.name,
        )

        try:  # ← entire body wrapped; finalize_ingest_run in except/end
            ckpt = await load_git_history_checkpoint(driver, ctx.group_id)
        commits_written = 0
        prs_written = 0
        pr_comments_written = 0
        edges_written = 0
        full_resync = False

        # --- Phase 1: pygit2 ---
        check_phase_budget(
            nodes_written_so_far=commits_written,
            max_occurrences_total=settings.git_history_max_commits_per_run,
            phase="phase1_commits",
        )
        try:
            walker = Pygit2Walker(repo_path=ctx.repo_path)
            new_head_sha = walker.head_sha()
            try:
                walk_iter = walker.walk_since(ckpt.last_commit_sha)
                # Materialize generator early to detect resync upfront
                commits_list = list(walk_iter)
            except CommitNotFoundError:
                log.warning(
                    "git_history_resync_full",
                    extra={"event": "git_history_resync_full",
                           "project_id": ctx.group_id,
                           "last_commit_sha_attempted": ckpt.last_commit_sha},
                )
                full_resync = True
                commits_list = list(walker.walk_since(None))

            tantivy_index_path = settings.git_history_tantivy_index_path
            async with GitHistoryTantivyWriter(tantivy_index_path) as tw:
                for commit in commits_list:
                    bot_flag = is_bot(commit["author_email"], commit["author_name"])
                    await write_commit_with_author(
                        driver, ctx.group_id, commit, is_bot=bot_flag
                    )
                    # Tantivy: dummy Commit construction (caller can refactor to skip)
                    from palace_mcp.extractors.git_history.models import Commit
                    commit_obj = Commit(
                        project_id=ctx.group_id, sha=commit["sha"],
                        author_provider="git",
                        author_identity_key=commit["author_email"].lower(),
                        committer_provider="git",
                        committer_identity_key=commit["committer_email"].lower(),
                        message_subject=commit["message_subject"],
                        message_full_truncated=commit["message_full_truncated"],
                        committed_at=commit["committed_at"],
                        parents=commit["parents"],
                    )
                    await tw.add_commit_async(commit_obj, body_full=commit["message_full_truncated"])
                    commits_written += 1
                    edges_written += 2 + len(commit["touched_files"])

            await write_git_history_checkpoint(
                driver, ctx.group_id,
                last_commit_sha=new_head_sha,
                last_pr_updated_at=ckpt.last_pr_updated_at,
                last_phase_completed="phase1",
            )
            log.info("git_history_phase1_complete",
                     extra={"event": "git_history_phase1_complete",
                            "project_id": ctx.group_id,
                            "commits_written": commits_written})
        except CommitNotFoundError:
            raise  # already handled above; re-raise should not happen
        except Exception as exc:
            log.exception("git_history_phase1_failed",
                          extra={"event": "git_history_phase_failed",
                                 "project_id": ctx.group_id,
                                 "phase": "phase1",
                                 "error_repr": repr(exc)})
            raise

        # --- Phase 2: GitHub GraphQL ---
        if not settings.github_token:
            log.warning("git_history_phase2_skipped_no_token",
                        extra={"event": "git_history_phase2_skipped_no_token",
                               "project_id": ctx.group_id})
            log.info("git_history_complete",
                     extra={"event": "git_history_complete",
                            "project_id": ctx.group_id,
                            "commits_written": commits_written,
                            "prs_written": 0, "pr_comments_written": 0,
                            "full_resync": full_resync})
            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
            return ExtractorStats(
                nodes_written=commits_written,
                edges_written=edges_written,
            )

        # ... GraphQL ingest details — left as inline expansion;
        # follows spec §5.1 Phase 2 pseudocode.
        # (Implementation parallels Phase 1 shape using GitHubClient +
        # write_pr_with_author + write_pr_comment_with_author.)

        # Final — finalize IngestRun lifecycle (mirrors symbol_index_python.py:226)
        log.info("git_history_complete",
                 extra={"event": "git_history_complete",
                        "project_id": ctx.group_id,
                        "commits_written": commits_written,
                        "prs_written": prs_written,
                        "pr_comments_written": pr_comments_written,
                        "full_resync": full_resync})
            await finalize_ingest_run(driver, run_id=ctx.run_id, success=True)
            return ExtractorStats(
                nodes_written=commits_written + prs_written + pr_comments_written,
                edges_written=edges_written,
            )
        except ExtractorError:
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=False, error_code="extractor_error",
            )
            raise
        except Exception:
            await finalize_ingest_run(
                driver, run_id=ctx.run_id, success=False, error_code="unknown",
            )
            raise
```

Phase 2 GraphQL block: implement using `GitHubClient.fetch_prs_since` + write
helpers from `neo4j_writer.py`. Mirror Phase 1 shape (loop, MERGE, tantivy
write, advance counters, write_checkpoint at end).

- [ ] **Step 5: Run tests; pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_extractor.py -v
```

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/git_history/extractor.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_extractor.py
git commit -m "feat(GIM-186): GitHistoryExtractor mirroring symbol_index_python pattern"
```

---

## Task 9: Registry registration + Settings extension

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- Modify: `services/palace-mcp/src/palace_mcp/config.py`
- Test: extend any existing registry test

- [ ] **Step 1: Add fields to PalaceSettings**

```python
# config.py — append to PalaceSettings class
github_token: str | None = Field(default=None, alias="PALACE_GITHUB_TOKEN")
git_history_bot_patterns_json: str | None = Field(
    default=None, alias="PALACE_GIT_HISTORY_BOT_PATTERNS_JSON",
)
git_history_max_commits_per_run: int = Field(
    default=50_000, alias="PALACE_GIT_HISTORY_MAX_COMMITS_PER_RUN",
)
git_history_tantivy_index_path: Path = Field(
    default=Path("/var/lib/palace/tantivy/git_history"),
    alias="PALACE_GIT_HISTORY_TANTIVY_INDEX_PATH",
)
```

- [ ] **Step 2: Register extractor in `registry.py`**

```python
# registry.py — add import and entry
from palace_mcp.extractors.git_history.extractor import GitHistoryExtractor

EXTRACTORS["git_history"] = GitHistoryExtractor()
```

- [ ] **Step 3: Add registration test**

In `tests/extractors/unit/test_git_history_extractor.py`:

```python
def test_extractor_registered_in_registry():
    from palace_mcp.extractors.registry import EXTRACTORS
    assert "git_history" in EXTRACTORS
    assert EXTRACTORS["git_history"].name == "git_history"
```

- [ ] **Step 4: Run tests; pass**

```bash
uv run pytest tests/extractors/unit/test_git_history_extractor.py::test_extractor_registered_in_registry -v
uv run mypy src/palace_mcp/extractors/registry.py src/palace_mcp/config.py
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/registry.py \
        services/palace-mcp/src/palace_mcp/config.py \
        services/palace-mcp/tests/extractors/unit/test_git_history_extractor.py
git commit -m "feat(GIM-186): register git_history + add 4 PALACE_GIT_HISTORY_* settings"
```

---

## Task 10: Mini-fixture (synthetic repo + GraphQL responses)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/REGEN.md`
- Create: `services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/repo/` (real git directory)
- Create: `services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/github_responses/` (3 JSON files)

- [ ] **Step 1: Build synthetic repo via pygit2 helper script**

Create `services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/regen.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
DIR="$(dirname "$0")"
RUNNER="$DIR/repo"
rm -rf "$RUNNER"
uv run python "$DIR/_build_synth_repo.py" "$RUNNER"
```

Create `_build_synth_repo.py` using the same `_build_synthetic_repo` helper
from Task 3 unit tests, with:
- 5 commits
- 2 distinct authors (one human, one `github-actions[bot]`)
- 1 file rename across commits
- 1 merge commit (for `is_merge` validation)

- [ ] **Step 2: Generate**

```bash
bash services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/regen.sh
```

- [ ] **Step 3: Capture real GraphQL response shapes**

Create 3 fixture JSONs under
`services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/github_responses/`:

- `prs_page_1.json` — single page with 2 PRs, including 1 with `Mannequin` author
  shape (covers spec §5.2 Actor union)
- `pr_comments_inner_pagination.json` — PR with 100 comments + `hasNextPage:
  true` to test inner pagination
- `rate_limit_low.json` — pageInfo with `remaining: 50` to test fail-fast

Capture using `gh api graphql -f query=...` against a public small repo (e.g.
ant013/Gimle-Palace itself); redact any sensitive content; commit deterministic
shape.

- [ ] **Step 4: Write REGEN.md**

```markdown
# git-history-mini-project fixture

## How to regenerate

\`\`\`bash
bash regen.sh
\`\`\`

## Synthetic repo content

5 commits:
1. Initial commit — author Foo (human)
2. Add file2.txt — github-actions[bot]
3. Rename file2 → file3 — Foo
4. Merge branch 'topic' — Foo (merge commit)
5. Final commit — Foo

## GraphQL fixtures

- prs_page_1.json: 2 PRs, normal flow.
- pr_comments_inner_pagination.json: 100-comment PR with hasNextPage.
- rate_limit_low.json: rateLimit.remaining=50 to trigger fail-fast.

Captured 2026-05-04 from public ant013/Gimle-Palace repo via gh api graphql.
```

- [ ] **Step 5: Commit fixture**

```bash
git add services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/
git commit -m "feat(GIM-186): mini-fixture (synthetic repo + GraphQL fixtures)"
```

---

## Task 11: Integration test (testcontainers Neo4j)

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_git_history_integration.py`

- [ ] **Step 1: Write end-to-end integration test**

```python
"""Integration test — testcontainers Neo4j + respx GitHub. See spec §9.2."""
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
import respx
import httpx
from testcontainers.neo4j import Neo4jContainer
from neo4j import AsyncGraphDatabase

from palace_mcp.extractors.git_history.extractor import GitHistoryExtractor
from palace_mcp.extractors.base import ExtractorRunContext

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "git-history-mini-project"


@pytest.mark.asyncio
async def test_full_ingest_then_incremental_zero_new(tmp_path: Path):
    with Neo4jContainer("neo4j:5.26") as neo:
        async with AsyncGraphDatabase.driver(
            neo.get_connection_url(), auth=("neo4j", neo.password),
        ) as driver:
            ctx = ExtractorRunContext(
                project_slug="mini",
                group_id="project/mini",
                repo_path=FIXTURE_DIR / "repo",
                run_id="run-1",
                duration_ms=0,
                logger=None,  # type: ignore
            )
            # 1. Mock GitHub responses; first run = full ingest
            with respx.mock:
                pr_response = json.loads(
                    (FIXTURE_DIR / "github_responses" / "prs_page_1.json").read_text()
                )
                respx.post("https://api.github.com/graphql").mock(
                    return_value=httpx.Response(200, json=pr_response)
                )
                # ... run extractor (with patched get_driver/get_settings)
                # ... assert :Commit count == 5, :Author count == 2 (1 bot + 1 human)
                ...

            # 2. Re-run — should be 0 new commits/PRs (incremental with same SHA)
            with respx.mock:
                respx.post("https://api.github.com/graphql").mock(
                    return_value=httpx.Response(200, json=pr_response)
                )
                # ... assert no new :Commit nodes created
                ...

# Additional integration tests:
# - test_force_push_triggers_resync (rewrite checkpoint with bogus sha; assert full re-walk)
# - test_phase2_failure_preserves_phase1 (inject GraphQL error after Phase 1; assert
#   :GitHistoryCheckpoint.last_commit_sha advanced, last_phase_completed == "phase1")
# - test_author_collapse_email_lowercase (write same author with mixed-case email;
#   assert single :Author node)
# - test_pr_boundary_re_ingestion (PR with updated_at == since; assert MERGE-idempotent)
```

(Full implementation should mirror this skeleton; expand each `...` section
following Task 8 patterns. ~280 LOC total.)

- [ ] **Step 2: Run integration test**

```bash
uv run pytest tests/extractors/integration/test_git_history_integration.py -v
```

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_git_history_integration.py
git commit -m "test(GIM-186): integration test with testcontainers Neo4j + respx GitHub"
```

---

## Task 12: Smoke script + runbook + .env.example + CLAUDE.md

**Files:**
- Create: `services/palace-mcp/scripts/smoke_git_history.py`
- Create: `docs/runbooks/git-history-harvester.md`
- Modify: `.env.example`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Smoke script (real ClientSession.call_tool)**

Create `services/palace-mcp/scripts/smoke_git_history.py` per spec §9.4.2.
Use real `mcp.ClientSession.call_tool(name=..., arguments=...)`. Must NOT
use the fictional `invoke()` function from rev1.

- [ ] **Step 2: Runbook**

Create `docs/runbooks/git-history-harvester.md`. Must cover:
- One-time setup: token in `.env`; restart palace-mcp.
- Initial ingest invocation (`palace.ingest.run_extractor`).
- Periodic refresh (incremental).
- Resync recovery if force-push detected.
- Bot pattern customization via env var.
- Smoke test invocation.
- Cleanup procedure (Cypher DETACH DELETE).

- [ ] **Step 3: .env.example**

Append:
```bash
# GIM-186 git_history extractor (optional)
PALACE_GITHUB_TOKEN=
PALACE_GIT_HISTORY_BOT_PATTERNS_JSON=
PALACE_GIT_HISTORY_MAX_COMMITS_PER_RUN=50000
PALACE_GIT_HISTORY_TANTIVY_INDEX_PATH=/var/lib/palace/tantivy/git_history
```

- [ ] **Step 4: CLAUDE.md**

Add to §"Extractors → Registered extractors" list:

```markdown
- `git_history` — Git history harvester (GIM-186). Walks pygit2 commit
  history + GitHub GraphQL PR/comment data. Foundation for 6 historical
  extractors (#11/#12/#26/#32/#43/#44). Per-project incremental refresh.
  Requires `PALACE_GITHUB_TOKEN` env var for Phase 2 (PR data); Phase 1
  (commits) runs without it. See `docs/runbooks/git-history-harvester.md`.
```

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/scripts/smoke_git_history.py \
        docs/runbooks/git-history-harvester.md \
        .env.example CLAUDE.md
git commit -m "docs(GIM-186): smoke script + runbook + .env + CLAUDE.md"
```

---

## Task 13: Final gate + handoff to CR

- [ ] **Step 1: Run all gates from `services/palace-mcp/`**

```bash
cd services/palace-mcp
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest -q
uv run pytest --cov=src/palace_mcp --cov-fail-under=85 -q
uv run pytest --cov=palace_mcp.extractors.git_history.extractor --cov-fail-under=90 \
  tests/extractors/unit/test_git_history_extractor.py -q
uv run pytest --cov=palace_mcp.extractors.git_history.pygit2_walker --cov-fail-under=90 \
  tests/extractors/unit/test_git_history_pygit2_walker.py -q
uv run pytest --cov=palace_mcp.extractors.git_history.github_client --cov-fail-under=90 \
  tests/extractors/unit/test_git_history_github_client.py -q
uv run pytest --cov=palace_mcp.extractors.git_history.bot_detector --cov-fail-under=90 \
  tests/extractors/unit/test_git_history_bot_detector.py -q
```

Expected: all 0-exit. Output captured verbatim for handoff comment.

- [ ] **Step 2: Static-anchor + scope check**

```bash
# Per spec §3.4 — no datetime.now()/time.time() in detection paths
grep -nE "datetime\.now\(\)|time\.time\(\)" \
  src/palace_mcp/extractors/git_history/extractor.py \
  src/palace_mcp/extractors/git_history/pygit2_walker.py \
  src/palace_mcp/extractors/git_history/github_client.py
# Expected: empty (or only at very specific allowed places)

# Scope diff vs develop
git diff --name-only origin/develop...HEAD | sort -u
```

Output must match files declared in this plan.

- [ ] **Step 3: Atomic-handoff to CodeReviewer (Phase 3.1)**

Per `paperclips/fragments/profiles/handoff.md`:

1. Push final commit to origin.
2. PATCH paperclip issue: `status=in_review` + `assigneeAgentId=<CodeReviewer-UUID>`.
3. POST handoff comment with @-mention of CR + the verbatim output of
   gates from Step 1 + scope diff from Step 2.
4. GET-verify the assignee.

---

## Phase 3.1 — CR Mechanical Review

Per CLAUDE.md §"Paperclip team workflow":

- Re-run all gates from Task 13 Step 1.
- Paste full output in APPROVE comment (no "LGTM" allowed).
- Run `gh pr checks` and paste full output (per `feedback_cr_phase31_ci_verification.md`).
- Scope audit: `git diff --name-only origin/develop...HEAD | sort -u` matches
  this plan's declared files (§"File structure").
- Live-API curl audit (per `feedback_pe_qa_evidence_fabrication.md`):
  ```bash
  curl -sS "https://api.github.com/graphql" \
    -H "Authorization: Bearer $PALACE_GITHUB_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "{ rateLimit { cost remaining limit resetAt } }"}'
  ```
  Confirm response shape matches `github_client.py` parser expectations.

CR APPROVE handoffs to OpusArchitectReviewer per spec §12 Rollout Phase 3.2.

---

## Phase 3.2 — Opus Adversarial Review

Required attack vectors (per spec §12 Rollout):

1. **Force-push silent drift** — verified by integration test
   `test_force_push_triggers_resync`.
2. **GitHub rate-limit cost-aware fail-fast** — verified by unit test
   `test_rate_limit_fail_fast_below_threshold`.
3. **Bot regex false-positive on humans** — verified by parametrized test
   `test_is_bot_parametrized` cases for `someone-bot@`.
4. **Author MERGE preserves first_seen_at** — verified by
   `test_git_history_author_time_window_preserved`.
5. **Phase 2 failure preserves Phase 1 checkpoint** — verified by
   `test_phase2_failure_preserves_phase1`.
6. **Tantivy doc-id collision across projects** — verified by integration
   test that ingests two distinct projects, asserts no doc bleed.
7. **Empty / None email handling** — verified by parametrized model tests.

Opus posts findings; PE addresses before Phase 4.

---

## Phase 4.1 — QA Live Smoke (iMac)

Per spec §9.4. Required SSH-from-iMac evidence (no local-Mac):

1. Identity capture (`hostname`, `uname -a`, `date -u`).
2. Pre-smoke rate-limit baseline.
3. `palace.ingest.run_extractor(name="git_history", project="gimle")`
   — full first run, < 5s, commits > 0.
4. Re-run gimle — incremental, 0 new commits, < 1s.
5. `palace.ingest.run_extractor(name="git_history", project="uw-android")`
   — full first run, < 60s, rate_limit delta < 500.
6. Cypher gates (per spec §9.4.4):
   - Commit count > 0
   - :Author collapse (Anton Stavnichiy = 1 :Author for gimle)
   - Bot detection > 0 (gimle has github-actions auto-commits)
7. Capture ALL `git_history_*` JSONL events (not `tail -1` per spec §9.4.5).
8. Cleanup if smoke failed (Cypher DETACH DELETE per spec §9.4.6).

QA comment with full evidence → CTO Phase 4.2 merge.

---

## Self-review summary

Plan checked against spec rev2:

1. **Spec coverage**: Each acceptance criterion in spec §8 maps to a test in
   the plan. Acceptance #1 (registered) = Task 9 step 3. Acceptance #2-#9
   (Pydantic, schema, Tantivy) = Tasks 1, 5, 6, 7. Acceptance #10-#16 (bot
   regex, time-window, schema-drift) = Tasks 2, 6, 11. Acceptance #17-#23
   (CLAUDE.md, fixture, runbook, smoke) = Tasks 10, 12, 13.

2. **Placeholder scan**: No "TBD" / "TODO" / "fill later" in any task. Code
   blocks present where steps require code. Phase 2 GraphQL block in Task 8
   is intentionally compressed with ", follows Phase 1 shape" — implementer
   has full Phase 1 template to mirror.

3. **Type consistency**: `GitHistoryExtractor`, `GitHistoryCheckpoint`,
   `GitHistoryTantivyWriter`, `Pygit2Walker`, `GitHubClient` names used
   consistently across tasks. `is_bot` (function) vs `is_bot` (model field)
   are distinguished by context.

4. **Frequent commits**: 13 commits across implementation tasks; each task
   ends with a commit. Frequent enough for review per task and bisect on
   regression.
