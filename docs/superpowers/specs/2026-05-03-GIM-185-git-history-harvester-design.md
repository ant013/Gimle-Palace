---
slug: git-history-harvester
status: proposed
branch: feature/GIM-185-git-history-harvester
paperclip_issue: 185
authoring_team: Claude (Board+Claude brainstorm); Claude implements end-to-end
predecessor: 57545cb (docs(roadmap) PR #82 merge into develop tip)
date: 2026-05-03
---

# GIM-185 — Git History Harvester (Extractor #22)

## 1. Context

Extractor inventory item #22 ("Git History Harvester") is the **prerequisite**
for 6 historical extractors per `docs/research/extractor-library/outline.yaml`
and `docs/roadmap.md` §2.3:

- #11 Decision History Extractor (Claude, LLM)
- #12 Migration Signal Extractor (CX)
- #26 Bug-Archaeology Extractor (Claude, LLM)
- #32 Code Ownership Extractor (Claude)
- #43 PR Review Comment Knowledge Extractor (Claude, LLM)
- #44 Code Complexity × Churn Hotspot Extractor (Claude)

Without #22 producing a structured + full-text dataset of commit / author /
PR / PR-comment data, none of the 6 historical extractors can run. This
slice is therefore the foundation for the entire historical category.

**Phase 2 prerequisite, started in Phase 1**: per `docs/roadmap.md` §2,
Phase 2 deep-analysis extractors do not start until Phase 1 closes. #22 is
the exception — it is treated as a Phase 1 parallel infra item because:

- It enables a whole class of consumers post-launch.
- It is non-LLM (cheap to run, deterministic).
- Its design + implementation cycle is independent of CX queue item 2
  (GIM-184 C/C++/Obj-C iOS) and Claude C2 (GIM-182 Multi-repo SPM ingest).
- Building it in parallel with launch path means the first historical
  extractor (e.g. #44 Churn) can ship immediately when Phase 1 closes,
  rather than starting from scratch.

**Predecessor SHA**: `57545cb` (`develop` tip, docs(roadmap) PR #82 merge).

**Authoring split**: Board + Claude session brainstorms spec + plan;
Claude paperclip team implements end-to-end (per `docs/roadmap.md` §3
Claude queue + operator decision 2026-05-03 to keep Claude-track items
end-to-end).

**Related artefacts** (must read before implementation):
- `docs/research/extractor-library/outline.yaml` — item #22 row + 6 consumers.
- `docs/research/extractor-library/report.md` — §2.3 (Historical) summary.
- `docs/superpowers/specs/2026-04-27-101a-extractor-foundation-design.md` —
  `BaseExtractor`, `:IngestRun`, `TantivyBridge`, `ensure_custom_schema`.
- `docs/superpowers/specs/2026-04-27-101b-symbol-index-python-design.md` —
  reference shape for SCIP-backed extractors; this slice follows the
  same `BaseExtractor` + 3-phase + checkpoint pattern but does not parse
  SCIP (it walks git directly).
- `docs/runbooks/multi-repo-spm-ingest.md` (when GIM-182 ships) — sibling
  pattern for project + bundle ingest.
- ADR §ARCHITECTURE D2 — Hybrid Tantivy + Neo4j; this slice respects the
  boundary (structured in Neo4j, full-text in Tantivy).

## 2. v1 Scope (frozen)

### IN

1. **`git_history` extractor** registered in
   `services/palace-mcp/src/palace_mcp/extractors/registry.py`.
2. **Pydantic v2 schemas** for `Commit`, `Author`, `PR`, `PRComment`,
   plus edge metadata. All `datetime` tz-aware UTC, `email` regex-validated.
3. **Neo4j writes** via existing 101a foundation:
   - `:Commit / :Author / :PR / :PRComment / :File` nodes.
   - `:AUTHORED_BY / :COMMITTED_BY / :TOUCHED / :LINKED_TO / :ON` edges.
   - Constraints created via extension of `ensure_custom_schema()`.
   - `group_id = "project/<slug>"` consistent with existing extractors.
4. **Tantivy `git_history` collection** (separate from symbol-index
   collections) with full-text on `commit.message_full`, `pr.body`,
   `pr_comment.body`. Single index; `doc_kind` field discriminates
   commit / pr / pr_comment.
5. **pygit2-based commit walker** with incremental + resync-fallback.
6. **httpx-based GitHub GraphQL client** (`github_client.py`) with
   pagination, `rateLimit { remaining, resetAt }` adaptive backoff,
   429/5xx retry.
7. **Bot detection regex** on `Author.email` and `Author.name` →
   `Author.is_bot: bool`.
8. **Per-project ingest scope**:
   `palace.ingest.run_extractor(name="git_history", project="<slug>")`.
9. **Mini-fixture** under
   `services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/`
   — synthetic 5-commit + 1-PR history; deterministic regen via `REGEN.md`.
10. **`PALACE_GITHUB_TOKEN` env var** wired into `Settings` (existing
    `PalaceSettings` pattern); operator's existing `gh` PAT reused.
11. **Incremental refresh**: first run = full; subsequent runs walk from
    `last_commit_sha + last_pr_updated_at` checkpoint.
12. **Resync detection**: if `last_commit_sha` not found in current
    history (force-push / rewrite), log `git_history_resync_full` event,
    fall back to full re-walk; idempotent via Cypher `MERGE`.
13. **Operator runbook** at `docs/runbooks/git-history-harvester.md`.
14. **Live smoke**: gimle (developer-side, fast) + uw-android
    (production-realistic, ~10K commits, ~150 PRs) on iMac.

### OUT (deferred follow-ups)

| # | Deferred item | Reactivation trigger |
|---|---|---|
| F1 | `--rebuild` / `--force` flag | Operator hits state corruption; needs explicit retrigger after manual diagnosis |
| F2 | ADR-style file parser (`docs/postmortems/`, `docs/superpowers/specs/`) | Consumer #11 Decision History needs structured ADR ingest |
| F3 | `:REVERTS` edges (commit reverts another commit) | Consumer #26 Bug-Archaeology needs SZZ-style revert tracking |
| F4 | `paperclip.git.*` integration (route through palace.git instead of pygit2 direct) | If pygit2 perf bottleneck observed; v1 keeps pygit2 (fastest local read) |
| F5 | Webhook-based incremental (push event triggers reindex) | After `D4 Webhook async-signal v2` lands |
| F6 | Bundle-aware ingest (`bundle="uw-ios"`) | After GIM-182 ships + operator wants per-Kit history aggregated |
| F7 | LLM-categorization of commit messages (bug-fix / feature / refactor / docs) | Consumer #11 / #15 needs structured commit kind |
| F8 | `:File` move / rename tracking via libgit2 `--follow` | Consumer #44 Churn explicitly asks for rename-aware churn |
| F9 | PR-review-thread structure (head SHA / line / suggestion) | Consumer #43 Review Comment Knowledge needs review-thread reconstruction |
| F10 | Issue (not PR) ingest | Consumer #26 Bug-Archaeology needs `:Issue` nodes for bug labels |

### Silent-scope-reduction guard

CR Phase 3.1 must paste:

```bash
git diff --name-only origin/develop...HEAD | sort -u
```

Output must match the file list declared in §4 verbatim. Any out-of-scope
file → REQUEST CHANGES per `feedback_silent_scope_reduction.md`.

## 3. Architecture

### 3.1 Three-layer summary

1. **Storage**: Neo4j for structured nodes + edges (per ADR D2
   "structured relationships in Neo4j"); Tantivy `git_history`
   collection for full-text body fields (per ADR D2 "positional /
   text content in Tantivy"). Per-project group_id namespacing.
2. **Ingest**: 3-phase per-project run:
   - Phase 1: pygit2 walk commits since `last_commit_sha` → write
     `:Commit + :Touched + :Author` to Neo4j + commit-msg docs to
     Tantivy.
   - Phase 2: GitHub GraphQL paginate PRs since `last_pr_updated_at`
     → write `:PR + :LinkedTo + :PRComment` to Neo4j + body docs to
     Tantivy.
   - Phase 3: write `:IngestRun` checkpoint with new
     `last_commit_sha + last_pr_updated_at`.
3. **Query** (no new MCP tool in this slice): consumers use Cypher
   directly + `palace.code.search_text(collection="git_history", ...)`
   helper that's added when first consumer ships. v1 leaves the
   query surface minimal — write side only.

Boundary (per ADR D2): bodies up to 1 KB stored as truncated
properties on Neo4j nodes for cheap `MATCH ... WHERE x.message_subject
CONTAINS ...` queries; full body stored only in Tantivy. No body
duplication beyond 1 KB.

### 3.2 Diagram

```
┌──────────────────── iMac (Production) ─────────────────────┐
│                                                            │
│  Local clones (already mounted via parent_mount):          │
│    /repos/gimle/.git                                       │
│    /repos/uw-android/.git                                  │
│    (read-only volumes from docker-compose.yml)             │
│                                                            │
│  GitHub API:                                               │
│    https://api.github.com/graphql                          │
│    Auth: PALACE_GITHUB_TOKEN (operator's gh PAT)           │
│    Rate: 5000 req/hour personal token                      │
│                                                            │
│  palace-mcp container:                                     │
│    palace.ingest.run_extractor(name="git_history",         │
│                                 project="gimle")           │
│      ↓                                                     │
│    Phase 1: pygit2 walk commits                            │
│      ↓ async generator                                     │
│      Neo4j: MERGE :Commit, :Author, :Touched               │
│      Tantivy: index commit message + metadata              │
│                                                            │
│    Phase 2: GitHub GraphQL                                 │
│      ↓ cursor-paginated, since last_pr_updated_at          │
│      Neo4j: MERGE :PR, :PRComment, :LinkedTo               │
│      Tantivy: index PR body + comment bodies               │
│                                                            │
│    Phase 3: write_checkpoint                               │
│      :IngestRun {                                          │
│        source: "extractor.git_history",                    │
│        last_commit_sha: "abc123...",                       │
│        last_pr_updated_at: "2026-05-03T12:00:00Z",         │
│        ...                                                 │
│      }                                                     │
└────────────────────────────────────────────────────────────┘
```

### 3.3 Type contracts (Pydantic v2)

```python
# src/palace_mcp/extractors/git_history/models.py
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re

_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Author(FrozenModel):
    email: str           # primary key (Neo4j UNIQUE constraint)
    name: str
    is_bot: bool
    first_seen_at: datetime
    last_seen_at: datetime

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError(f"invalid email: {v!r}")
        return v.lower()

    @field_validator("first_seen_at", "last_seen_at")
    @classmethod
    def _check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("must be tz-aware")
        return v.astimezone(timezone.utc)


class Commit(FrozenModel):
    project_id: str        # "project/<slug>" — group_id namespacing
    sha: str               # 40-char hex; primary key (UNIQUE)
    short_sha: str         # 7-char prefix for human queries
    author_email: str
    committer_email: str
    message_subject: str   # first line, max 200 chars
    message_full_truncated: str  # first 1024 chars; full text in Tantivy
    committed_at: datetime
    parents: tuple[str, ...]    # parent SHAs (immutable)
    is_merge: bool

    @field_validator("sha")
    @classmethod
    def _check_sha(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", v):
            raise ValueError(f"invalid sha: {v!r}")
        return v


class PR(FrozenModel):
    project_id: str
    number: int            # within project (composite UNIQUE with project_id)
    title: str
    body_truncated: str    # first 1024 chars; full in Tantivy
    state: Literal["open", "merged", "closed"]
    author_email: str
    created_at: datetime
    merged_at: datetime | None
    head_sha: str | None   # links to :Commit if merged
    base_branch: str


class PRComment(FrozenModel):
    project_id: str
    id: str                # GitHub comment node id; primary key
    pr_number: int         # FK to PR (composite with project_id)
    body_truncated: str
    author_email: str
    created_at: datetime


class IngestSummary(FrozenModel):
    project_id: str
    run_id: str
    commits_written: int
    authors_written: int
    prs_written: int
    pr_comments_written: int
    files_touched: int
    full_resync: bool       # true if force-push detected → fell back to full
    last_commit_sha: str | None
    last_pr_updated_at: datetime | None
    duration_ms: int
```

All `datetime` values are tz-aware UTC. Validation enforces this at the
Pydantic boundary.

### 3.4 Invariants

1. **Symbol identity is sha-based for Commit, email-based for Author.**
   Two `:Commit` nodes with the same sha collapse via `MERGE`. Two
   `:Author` with same lowercased email collapse. Email lowercasing
   enforced at validator.
2. **Per-project namespacing.** All nodes carry `project_id =
   "project/<slug>"`. Cross-project queries explicitly traverse via
   `MATCH (c:Commit {project_id: $p}) ...`. No cross-project leakage.
3. **Bot detection is deterministic** — pure regex on `email + name`.
   No LLM. Configurable via `PALACE_GIT_HISTORY_BOT_PATTERNS_JSON` env
   var (default = built-in patterns).
4. **Body truncation invariant**. `message_full_truncated.length() <=
   1024 + 3 (ellipsis)`. Full body lives ONLY in Tantivy. Cypher
   queries on full body must hit Tantivy via `palace.code.search_text`
   or follow-up consumer's surface.
5. **Idempotent re-walk.** Cypher `MERGE` guarantees re-walking same
   commit twice produces single `:Commit` node. Tested in
   `test_git_history_idempotent_remerge`.
6. **Force-push survival.** If `last_commit_sha` not findable via
   `pygit2.Repository.get(sha)`, fall back to full walk; emit
   `git_history_resync_full` JSONL event. Operator alerted via log.

## 4. Component layout

```
services/palace-mcp/src/palace_mcp/extractors/git_history/
├── __init__.py                  (NEW ~10 LOC: re-export GitHistoryExtractor)
├── extractor.py                 (NEW ~150 LOC: GitHistoryExtractor(BaseExtractor))
├── pygit2_walker.py             (NEW ~140 LOC: async wrapper around pygit2 walk)
├── github_client.py             (NEW ~180 LOC: httpx GraphQL client + retry/backoff)
├── models.py                    (NEW ~120 LOC: Pydantic v2 schemas)
├── tantivy_writer.py            (NEW ~80 LOC: write to git_history collection)
├── neo4j_writer.py              (NEW ~120 LOC: Cypher MERGE patterns)
├── bot_detector.py              (NEW ~60 LOC: regex classifier)
└── checkpoint.py                (NEW ~70 LOC: last_sha + last_pr_updated_at)

services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py
                                 (EXTEND ~30 LOC: add git_history constraints to ensure_custom_schema())

services/palace-mcp/src/palace_mcp/extractors/registry.py
                                 (EXTEND +2 LOC: import + register)

services/palace-mcp/src/palace_mcp/config.py
                                 (EXTEND +6 LOC: add github_token + git_history_bot_patterns_json fields to PalaceSettings)

services/palace-mcp/tests/extractors/
├── unit/
│   ├── test_git_history_extractor.py          (NEW ~280 LOC)
│   ├── test_git_history_pygit2_walker.py      (NEW ~180 LOC)
│   ├── test_git_history_github_client.py      (NEW ~220 LOC, respx mocks)
│   ├── test_git_history_bot_detector.py       (NEW ~80 LOC, ~25 parametrized cases)
│   └── test_git_history_models.py             (NEW ~120 LOC, Pydantic invariants)
├── integration/
│   └── test_git_history_integration.py        (NEW ~250 LOC, testcontainers Neo4j + respx)
└── fixtures/
    └── git-history-mini-project/              (NEW)
        ├── REGEN.md                           — pygit2 generator instructions
        ├── repo/                              — synthetic .git directory committed
        │   └── ...                            (5 commits, 2 authors incl. 1 bot, 1 file rename)
        └── github_responses/                  — captured GraphQL response fixtures
            ├── prs_page_1.json
            ├── prs_page_2.json
            ├── pr_comments_pr1.json
            └── rate_limit.json

CLAUDE.md                        (EXTEND ~30 LOC: §"Extractors" → add git_history row + operator workflow section)
.env.example                     (EXTEND +1 line: PALACE_GITHUB_TOKEN placeholder)

docs/runbooks/
└── git-history-harvester.md     (NEW ~180 LOC: setup + token + smoke + troubleshooting)
```

**Estimated size**: ~930 LOC prod + ~1130 LOC test + spec + plan + runbook + fixture.

## 5. Data flow

### 5.1 Ingest pipeline

```python
# extractor.py — sketch
class GitHistoryExtractor(BaseExtractor):
    name = "git_history"
    description = "Walks git commit history + GitHub PR/comment data"
    constraints = [...]  # listed below
    indexes = [...]

    async def extract(self, ctx: ExtractorContext) -> ExtractorStats:
        check_resume_budget(...)
        await ensure_custom_schema(ctx.driver)
        check_phase_budget(...)

        ckpt = await load_checkpoint(ctx.project_id)
        run_id = await create_ingest_run(
            ctx.driver, source="extractor.git_history", ...
        )
        summary = IngestSummary(...)

        # Phase 1 — pygit2 commits
        try:
            walker = Pygit2Walker(repo_path=ctx.repo_path)
            new_head = walker.head_sha()
            walk_iter = walker.walk_since(ckpt.last_commit_sha)
        except CommitNotFoundError:
            log.warning("git_history_resync_full",
                        extra={"event": "git_history_resync_full",
                               "project_id": ctx.project_id})
            walk_iter = walker.walk_since(None)
            summary.full_resync = True

        async for batch in batched(walk_iter, size=500):
            await write_commits_to_neo4j(ctx.driver, batch)
            await write_commits_to_tantivy(ctx.tantivy, batch)
            summary.commits_written += len(batch)

        # Phase 2 — GitHub GraphQL
        client = GitHubClient(token=settings.github_token)
        async for pr_batch in client.fetch_prs_since(
            ctx.repo_owner, ctx.repo_name, ckpt.last_pr_updated_at,
        ):
            await write_prs_to_neo4j(ctx.driver, pr_batch)
            await write_prs_to_tantivy(ctx.tantivy, pr_batch)
            summary.prs_written += len(pr_batch)
            for pr in pr_batch:
                async for cmt_batch in client.fetch_pr_comments(pr):
                    await write_comments_to_neo4j(ctx.driver, cmt_batch)
                    await write_comments_to_tantivy(ctx.tantivy, cmt_batch)
                    summary.pr_comments_written += len(cmt_batch)

        # Phase 3 — checkpoint
        new_pr_updated_at = max(
            (pr.updated_at for pr in all_prs), default=ckpt.last_pr_updated_at
        )
        await write_checkpoint(
            ctx.driver, ctx.project_id, source="extractor.git_history",
            last_commit_sha=new_head, last_pr_updated_at=new_pr_updated_at,
        )

        summary.last_commit_sha = new_head
        summary.last_pr_updated_at = new_pr_updated_at
        return ExtractorStats(
            nodes_written=summary.commits_written + summary.authors_written + summary.prs_written + summary.pr_comments_written,
            edges_written=...,
            success=True,
            metadata=summary.model_dump(mode="json"),
        )
```

### 5.2 GitHub GraphQL client

Single `pullRequests` query with nested comments + cursor pagination.
Adaptive backoff using `rateLimit { remaining, resetAt }` returned in
each response.

```graphql
query($owner: String!, $name: String!, $cursor: String, $since: DateTime!) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: 50, after: $cursor,
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage, endCursor }
      nodes {
        number title body state author { email }
        createdAt updatedAt mergedAt
        headRefOid baseRef { name }
        comments(first: 100) {
          nodes {
            id body author { email } createdAt
          }
          pageInfo { hasNextPage, endCursor }
        }
      }
    }
  }
  rateLimit { remaining, resetAt }
}
```

Client stops paginating when `pr.updatedAt < since`. Adaptive backoff
on `rateLimit.remaining < 100`: sleep until `resetAt + 5s`.

### 5.3 JSONL event schema (per ADR observability pattern)

Daemon emits these events to `~/.paperclip/palace-mcp.log`:

| `event` | Fields | When |
|---|---|---|
| `git_history_phase1_complete` | `project_id, commits_written, duration_ms` | After pygit2 walk |
| `git_history_phase2_complete` | `project_id, prs_written, pr_comments_written, duration_ms` | After GraphQL |
| `git_history_resync_full` | `project_id, last_commit_sha_attempted, reason` | Force-push detected; fallback to full walk |
| `git_history_rate_limit_throttled` | `project_id, remaining, reset_at, slept_seconds` | GitHub rate-limit backoff |
| `git_history_phase_failed` | `project_id, phase, error_kind, error_repr` | Per-phase except block |
| `git_history_complete` | `project_id, run_id, total_*` | After Phase 3 checkpoint |

## 6. Bot detection

```python
# bot_detector.py — built-in patterns; configurable via env var
_BOT_EMAIL_PATTERNS = [
    re.compile(r".*\[bot\]@users\.noreply\.github\.com$"),
    re.compile(r".*-bot@.*"),
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

def is_bot(email: str, name: str) -> bool:
    if any(p.match(email) for p in _BOT_EMAIL_PATTERNS):
        return True
    if any(p.match(name or "") for p in _BOT_NAME_PATTERNS):
        return True
    return False
```

Configurable override via `PALACE_GIT_HISTORY_BOT_PATTERNS_JSON` env
var (JSON dict `{"email": [...], "name": [...]}`); default = built-in.

Tests cover ~25 cases:
- positive: GitHub Actions, Dependabot, Renovate, Paperclip bot, generic `*[bot]`
- negative: humans with `bot` substring (`bot-fan@company.com`,
  `Robot Joe`); empty name
- edge: case sensitivity, whitespace, unicode

## 7. Configuration

Extend `PalaceSettings`:

```python
class PalaceSettings(BaseSettings):
    # ... existing fields ...
    github_token: str | None = Field(default=None, alias="PALACE_GITHUB_TOKEN")
    git_history_bot_patterns_json: str | None = Field(
        default=None, alias="PALACE_GIT_HISTORY_BOT_PATTERNS_JSON",
    )
    git_history_max_commits_per_run: int = Field(
        default=50_000, alias="PALACE_GIT_HISTORY_MAX_COMMITS_PER_RUN",
    )
```

Operator sets `PALACE_GITHUB_TOKEN` in `.env`. If unset, Phase 2 (GitHub
GraphQL) is skipped with a warning event; pygit2 phase still runs. This
enables operator to ingest local-only history without GitHub access.

## 8. Acceptance criteria

1. **Extractor registered** — `palace.ingest.list_extractors()` shows
   `git_history`. Verified by contract test.
2. **Pydantic v2 models with validators** — all `datetime` fields
   reject naive values; `email` regex-validated; `sha` 40-char hex
   regex. Verified by `test_git_history_models`.
3. **Neo4j schema constraints** ensured at server startup (`Commit.sha`
   UNIQUE, `Author.email` UNIQUE, `(PR.project_id, PR.number)` composite
   UNIQUE, `(File.project_id, File.path)` composite UNIQUE). Verified
   by `test_git_history_schema_creates_constraints`.
4. **Tantivy `git_history` collection** declared with required schema
   (doc_kind, project_id, doc_id, body, author_email, ts, is_bot).
   Verified by integration test that writes and queries 1 doc per kind.
5. **pygit2 walker incremental** — re-running with same checkpoint
   produces 0 new commits. Verified by `test_git_history_idempotent_remerge`.
6. **pygit2 walker resync** — when `last_commit_sha` not in repo, walker
   falls back to full + emits `git_history_resync_full` event. Verified
   by `test_git_history_force_push_resync`.
7. **GitHub GraphQL pagination** — multi-page response correctly
   exhausted. Verified by respx-based unit test with 3-page fixture.
8. **GitHub rate-limit backoff** — when `rateLimit.remaining < 100`,
   client sleeps until `resetAt`. Verified by
   `test_git_history_rate_limit_backoff`.
9. **Bot detection regex** — 25+ parametrized cases pass. Verified by
   `test_git_history_bot_detector`.
10. **Email lowercasing** — `Foo@Bar.com` and `foo@bar.com` collapse
    to single `:Author`. Verified by `test_git_history_author_email_lowercase`.
11. **Idempotent Cypher MERGE** — re-ingesting same commit twice yields
    1 node, not 2. Verified by `test_git_history_remerge_idempotent`.
12. **Body truncation invariant** — `message_full_truncated` ≤ 1027
    chars (1024 + ellipsis). Verified by `test_git_history_body_truncation`.
13. **Failure isolation per-phase** — Phase 2 GitHub error does NOT
    roll back Phase 1 commits already written. Verified by
    `test_git_history_phase2_failure_preserves_phase1`.
14. **JSONL events emitted** — every event from §5.3 has at least one
    test. Verified by parametrized test across 6 events.
15. **GitHub-disabled mode** — when `PALACE_GITHUB_TOKEN` unset, Phase 2
    is skipped with warning; Phase 1 runs normally; checkpoint records
    `last_pr_updated_at = None`. Verified by
    `test_git_history_no_github_token`.
16. **Backward compatibility** — existing extractors unaffected. Verified
    by regression test that runs `symbol_index_python` after
    `git_history` schema extension.
17. **Per-module 90% coverage** —
    `pytest --cov=palace_mcp.extractors.git_history.extractor --cov-fail-under=90`,
    `--cov=palace_mcp.extractors.git_history.pygit2_walker --cov-fail-under=90`,
    `--cov=palace_mcp.extractors.git_history.github_client --cov-fail-under=90`.
    All green.
18. **Lint / format / mypy / pytest gates** — `uv run ruff check`,
    `uv run ruff format --check`, `uv run mypy src/`, `uv run pytest -q`
    all green.
19. **Live smoke on iMac** — operator-driven smoke per §10.4. **Mandatory
    per §10.4.4: gimle ingest succeeds in <5s; uw-android first run
    succeeds in <60s with rate_limit.remaining > 4500.** SSH-from-iMac
    evidence captured.
20. **CLAUDE.md updated** — §"Extractors" → new `git_history` row +
    operator workflow section.
21. **Runbook present** — `docs/runbooks/git-history-harvester.md`
    covers setup (token), full + incremental ingest, resync recovery,
    bot pattern configuration, troubleshooting.
22. **Mini-fixture committed** with deterministic regen via `REGEN.md`.

## 9. Verification plan

### 9.1 Pre-implementation (CTO Phase 1.1)

1. Confirm branch starts from `57545cb`.
2. Confirm 101a foundation primitives (`BaseExtractor`,
   `TantivyBridge`, `ensure_custom_schema`, `:IngestRun`,
   `write_checkpoint`) are stable on develop.
3. Confirm `pygit2` available in `services/palace-mcp/pyproject.toml`
   or planned to be added.
4. Confirm `respx` available for HTTP mocks in tests.
5. Verify operator's `gh` PAT can be read into container via env var
   (no new secrets infrastructure needed).

### 9.2 Per-task gates

Each implementation task ends with a green test target before next
starts. See implementation plan (authored by CTO in Phase 1.1, or
extended by Board as followup).

### 9.3 Post-implementation gates

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
```

All must exit 0. Output pasted verbatim in CR Phase 3.1 handoff comment.

### 9.4 Live smoke (Phase 4.1, on iMac)

QA executes on iMac via SSH per `feedback_pe_qa_evidence_fabrication.md`.

#### 9.4.1 Pre-flight

1. `ssh imac-ssh.ant013.work 'date -u; hostname; uname -a; uptime'` —
   identity capture.
2. Confirm `PALACE_GITHUB_TOKEN` set in iMac `.env`; redact on capture.
3. Confirm `gimle` and `uw-android` parent_mounts are live in
   `docker-compose.yml` (per existing CLAUDE.md mount table).
4. Restart palace-mcp via `docker compose --profile review up -d
   --force-recreate palace-mcp` after env addition.

#### 9.4.2 Smoke procedure (Python httpx; no mcp-call)

```python
# scripts/smoke_git_history.py — bundled in this slice
import asyncio
import json
import sys
from mcp.client.streamable_http import streamablehttp_client

PALACE_MCP_URL = "http://localhost:8080/mcp"

async def call(tool: str, args: dict) -> dict:
    async with streamablehttp_client(PALACE_MCP_URL) as (read, write, _):
        return await invoke(tool, args)

async def main() -> int:
    # 1. Ingest gimle (small, fast).
    gimle_first = await call("palace.ingest.run_extractor",
                             {"name": "git_history", "project": "gimle"})
    # 2. Re-ingest gimle (incremental — should be ~0 new).
    gimle_second = await call("palace.ingest.run_extractor",
                              {"name": "git_history", "project": "gimle"})
    # 3. Ingest uw-android (real, larger).
    uw_first = await call("palace.ingest.run_extractor",
                          {"name": "git_history", "project": "uw-android"})

    print(json.dumps({
        "gimle_first": gimle_first,
        "gimle_second": gimle_second,
        "uw_first": uw_first,
    }, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

#### 9.4.3 Run smoke

```bash
ssh imac-ssh.ant013.work \
  'cd ~/Gimle-Palace && uv run python services/palace-mcp/scripts/smoke_git_history.py' \
  | tee /tmp/git-history-smoke-$(date +%s).log
```

#### 9.4.4 Smoke gate (mandatory)

Smoke is GREEN iff:

- `gimle_first.success == true` AND `gimle_first.duration_ms < 5000`
- `gimle_first.metadata.commits_written > 0`
- `gimle_second.success == true` AND
  `gimle_second.metadata.commits_written == 0` AND
  `gimle_second.metadata.full_resync == false` (incremental works)
- `uw_first.success == true` AND `uw_first.duration_ms < 60000`
- Tantivy query: `palace.code.search_text(collection="git_history",
  q="GIM-181", project="gimle")` returns ≥ 1 result
- iMac `gh api rate_limit | jq .resources.graphql.remaining` ≥ 4500
  after run (verifies polite GitHub usage)

Any failure → smoke RED → REQUEST CHANGES.

#### 9.4.5 Evidence (full failure logs, not tail -1)

PR body `## QA Evidence` must include verbatim:

```
$ ssh imac-ssh.ant013.work 'date -u; hostname; uname -a'
<output — hostname matches expected iMac>

$ jq '.gimle_first, .gimle_second, .uw_first' /tmp/git-history-smoke-*.log
<full IngestSummary for each>

$ ssh imac-ssh.ant013.work \
  'cat ~/.paperclip/palace-mcp.log | jq -c "select(.event | test(\"git_history_\"))"'
<all git_history_* events with full payload>

$ ssh imac-ssh.ant013.work \
  'gh api rate_limit | jq .resources.graphql.remaining'
<≥4500>
```

#### 9.4.6 Cleanup

If smoke succeeded, ingested data persists for production use. If failed
and operator wants to retry from scratch:

```cypher
MATCH (n) WHERE n.project_id IN ['project/gimle', 'project/uw-android']
  AND any(label IN labels(n) WHERE label IN ['Commit', 'Author', 'PR', 'PRComment', 'File'])
DETACH DELETE n;
```

Plus delete Tantivy `git_history` collection docs scoped to the same
project_ids.

## 10. Out of scope (deferred)

See §2 OUT table for reactivation triggers.

## 11. Risks and mitigations

- **pygit2 perf on UW-android (~10K commits)** — first run ~30 s
  estimated. Mitigation: incremental refresh after first run drops to
  seconds.
- **GitHub rate-limit exhaustion** — 5000 req/hour personal token;
  uw-android has ~150 PRs, ~1000 comments → ~30 GraphQL calls per
  full ingest. Mitigation: GraphQL bulk fetch + adaptive backoff;
  budget remains > 4500 after a full ingest.
- **Force-push silent drift** — local clone diverges from upstream;
  pygit2 walker may miss updates. Mitigation: resync detection logs
  warning; operator periodically `git pull`s mounted clones (existing
  operational pattern).
- **Bot regex false positives** — human with email containing "bot".
  Mitigation: regex is conservative (`[bot]` literal pattern); 25
  parametrized tests cover known false-positive shapes.
- **Tantivy collection conflict** — single `git_history` index shared
  across projects. Mitigation: `project_id` as fast field; queries
  filter by it; no cross-project leakage.
- **GitHub token leak** — `PALACE_GITHUB_TOKEN` in `.env` is plaintext.
  Mitigation: existing operator pattern (`NEO4J_PASSWORD` same shape);
  redact on log capture per QA procedure §9.4.5.
- **`gh` token scope** — operator's existing token may lack `repo`
  scope for private repos. Mitigation: Phase 4.1 Pre-flight verifies
  `gh api user` returns expected user + scopes.
- **Body truncation loses data** — full body lives only in Tantivy;
  Cypher-only consumers see truncated. Mitigation: documented in
  schema section; consumers route full-text queries through Tantivy.
- **Concurrent re-ingest** — palace-mcp event loop already serializes
  MCP tool calls. Mitigation: existing constraint, no change needed
  for v1; concurrency in F5/F6 followups.

## 12. Rollout

1. **Phase 1.1 CTO Formalize** — verify spec + plan paths, swap any
   placeholders, reassign CR.
2. **Phase 1.2 CR Plan-first review** — APPROVE comment must restate
   the 5 key invariants from §3.4 (sha+email primary keys, per-project
   namespacing, bot detection deterministic, body truncation, idempotent
   re-walk). Cross-team transcription drift guard.
3. **Phase 2 Implementation** — TDD through plan tasks.
4. **Phase 3.1 CR Mechanical** — including scope audit, per-module
   coverage gates (3 modules), live-API curl audit (per
   `feedback_pe_qa_evidence_fabrication.md`).
5. **Phase 3.2 OpusArchitectReviewer Adversarial** — required vectors:
   - Force-push silent drift (resync detection).
   - GitHub rate-limit edge cases (429, 5xx, schema change).
   - Bot regex false-positive on humans with `bot` substring.
   - Race: pygit2 walk while local repo is being `git pull`'d.
   - Concurrent ingest (palace-mcp event loop guarantees serialization;
     verify).
   - Cypher injection on commit message containing `'); DROP ...`.
   - Tantivy doc-id collision across projects.
6. **Phase 4.1 QA Live smoke** on iMac with SSH-from-iMac evidence.
7. **Phase 4.2 CTO Merge**.

## 13. Open questions

- **First post-#22 consumer order** — operator picks among
  #44 Churn / #32 Ownership / #43 PR Review (bottom-up by complexity)
  vs #11 Decision History / #26 Bug-Archaeology (top-down by
  business value). Default: #44 first (no LLM, immediate ROI).
  This open question does NOT block merging GIM-185.
- **`PALACE_GITHUB_TOKEN` rotation** — operator's `gh` PAT may need
  rotation periodically. Out of scope; document in runbook + memory
  reference.
- **Multi-repo scope** — when GIM-182 ships, should `git_history`
  ingest a bundle in one call (`bundle="uw-ios"`)? Deferred to F6.
