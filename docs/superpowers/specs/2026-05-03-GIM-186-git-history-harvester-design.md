---
slug: git-history-harvester
status: proposed (rev2)
branch: feature/GIM-186-git-history-harvester
paperclip_issue: 186
authoring_team: Claude (Board+Claude brainstorm); Claude implements end-to-end
predecessor: 57545cb (docs(roadmap) PR #82 merge into develop tip)
date: 2026-05-03
rev2_changes: |
  - §3.5 NEW Foundation Extensions: explicit list of what we reuse vs extend.
    Real BaseExtractor contract verified against
    services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py:67-104.
  - §3.6 NEW Checkpoint state node: separate :GitHistoryCheckpoint with
    state dict (existing :IngestCheckpoint cannot be reused — its phase
    Literal is SCIP-specific and expected_doc_count is doc-count-specific).
  - §3.7 NEW Tantivy writer: own GitHistoryTantivyWriter with own schema
    (existing TantivyBridge is typed to SymbolOccurrence — cannot reuse).
  - Author primary key changed from email to composite (provider, identity_key)
    to handle pygit2-vs-GraphQL email mismatch + GitHub noreply emails.
  - GraphQL fixed: author { login ... on User { email } } (Actor interface).
  - rateLimit { cost remaining limit resetAt } requested + fail-fast on
    budget exhaustion (no sleep beyond EXTRACTOR_TIMEOUT_S = 300s).
  - Checkpoint write after EACH phase (not only end).
  - Smoke gate dropped palace.code.search_text query (tool doesn't exist
    — moved to F11 deferred); replaced with Cypher MATCH count + :Author
    collapse + bot detection assertions.
  - Rate-limit gate measures delta (consumed by smoke), not absolute.
  - Smoke script template uses ClientSession.call_tool (real MCP API).
  - Smoke anchor changed to deterministic (latest commit subject).
  - @field_validator added on body_truncated fields + is_merge consistency.
  - Cypher snippet for MERGE Author with ON CREATE / ON MATCH first/last_seen.
  - bot_detector regex tightened (drop ".*-bot@.*" — false positives).
  - Per-module 90% gate extended to bot_detector.
  - F11 deferred: palace.code.search_text MCP tool surface.
  - F12 deferred: cross-provider Author identity merge heuristic pass.
  - F13 deferred: PR review-thread structure (head SHA / line / suggestion).
  - §13 cleaned: removed roadmap-level "consumer ordering" question.
  - :ON edge renamed to :COMMENTED_ON for Cypher readability.
  - PR.state lowercased via BeforeValidator (GraphQL returns UPPER).
  - short_sha computed (not stored) to avoid drift.
  - §11 Risks: added 5min EXTRACTOR_TIMEOUT_S risk for full UW history.
---

# GIM-186 — Git History Harvester (Extractor #22) — rev2

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
slice is the foundation for the entire historical category.

**Phase 2 prerequisite, started in Phase 1**: per `docs/roadmap.md` §2,
Phase 2 deep-analysis extractors do not start until Phase 1 closes. #22 is
the exception — Phase 1 parallel infra item because:

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

**Reference implementation pattern** (must read before implementation):
- `services/palace-mcp/src/palace_mcp/extractors/symbol_index_python.py`
  — canonical extractor pattern. This slice MIRRORS its shape: deferred
  import of `get_driver`/`get_settings`, `check_resume_budget`,
  `ensure_custom_schema` extension, `create_ingest_run`, per-phase
  budgets, `write_checkpoint` after each phase.

**Related artefacts**:
- `docs/research/extractor-library/outline.yaml` — item #22 row + 6
  consumers.
- `docs/research/extractor-library/report.md` — §2.3 (Historical) summary.
- `docs/superpowers/specs/2026-04-27-101a-extractor-foundation-design.md` —
  `BaseExtractor`, `:IngestRun`, `TantivyBridge`,
  `ensure_custom_schema`. Authoritative for the substrate parts we
  reuse.
- ADR §ARCHITECTURE D2 — Hybrid Tantivy + Neo4j boundary.

## 2. v1 Scope (frozen)

### IN

1. **`git_history` extractor** registered in
   `services/palace-mcp/src/palace_mcp/extractors/registry.py`. Inherits
   `BaseExtractor` and implements
   `async def run(*, graphiti, ctx: ExtractorRunContext) -> ExtractorStats`
   per existing contract.
2. **Pydantic v2 schemas** for `Commit`, `Author`, `PR`, `PRComment`,
   plus edge metadata. All `datetime` tz-aware UTC; truncated body fields
   length-validated; `email` regex-validated where applicable.
3. **Neo4j writes** for nodes + edges, scoped by
   `group_id = "project/<slug>"`. Idempotent `MERGE` with explicit
   `ON CREATE` / `ON MATCH` for time-window properties (see §3.4 inv. 5).
4. **`ensure_custom_schema()` extension** to add git_history constraints
   (Commit.sha UNIQUE, composite Author PK UNIQUE, etc.). Tested for
   backward-compat against legacy `:Commit` nodes from other sources
   (acceptance #16).
5. **NEW `:GitHistoryCheckpoint` node** with `state: JSON map` field
   storing `last_commit_sha + last_pr_updated_at`. Existing
   `:IngestCheckpoint` is NOT reused — its `phase` Literal is SCIP-
   specific. See §3.6.
6. **NEW `GitHistoryTantivyWriter`** with own schema (`doc_kind`,
   `project_id`, `doc_id`, `body`, `author_email`, `ts`, `is_bot`).
   Existing `TantivyBridge` is NOT reused — typed to `SymbolOccurrence`.
   Separate Tantivy index file under same per-host Tantivy data
   directory. See §3.7.
7. **pygit2-based commit walker** with incremental + resync-fallback.
8. **httpx-based GitHub GraphQL client** with cursor pagination,
   `rateLimit { cost remaining limit resetAt }` budget enforcement,
   429/5xx retry, fail-fast (NOT sleep) when next page would exceed
   remaining budget under `EXTRACTOR_TIMEOUT_S = 300s`.
9. **Bot detection regex** on `Author.email` and `Author.name` →
   `Author.is_bot: bool`. Conservative patterns only (`[bot]` literal,
   not generic substring `bot`).
10. **Composite Author primary key** `(provider, identity_key)`:
    - For pygit2-walker authors: `provider="git"`, `identity_key=email_lowercased`
    - For GraphQL PR authors: `provider="github"`, `identity_key=login`
    - Cross-provider merge is OUT (F12 deferred).
11. **Per-project ingest scope**:
    `palace.ingest.run_extractor(name="git_history", project="<slug>")`.
12. **Mini-fixture** under
    `services/palace-mcp/tests/extractors/fixtures/git-history-mini-project/`
    — synthetic 5-commit + 1-PR history; deterministic regen via
    `REGEN.md`.
13. **`PALACE_GITHUB_TOKEN` env var** wired into `Settings`; operator's
    existing `gh` PAT reused.
14. **Incremental refresh**: first run = full; subsequent runs walk
    from `last_commit_sha + last_pr_updated_at`.
15. **Per-phase checkpoint writes**: Phase 1 success advances
    `last_commit_sha`; Phase 2 success advances `last_pr_updated_at`.
    Phase 2 failure leaves Phase 1 checkpoint persisted (next run only
    retries Phase 2). See §5.1 + acceptance #13.
16. **Resync detection**: if `last_commit_sha` not findable in current
    repo, log `git_history_resync_full` event, fall back to full re-walk;
    idempotent via Cypher `MERGE` (acceptance #6).
17. **Operator runbook** at `docs/runbooks/git-history-harvester.md`.
18. **Live smoke**: gimle (developer-side, fast) + uw-android
    (production-realistic, ~10K commits, ~150 PRs) on iMac (§9.4).

### OUT (deferred follow-ups)

| # | Deferred item | Reactivation trigger |
|---|---|---|
| F1 | `--rebuild` / `--force` flag | Operator hits state corruption |
| F2 | ADR-style file parser (`docs/postmortems/`, `docs/superpowers/specs/`) | Consumer #11 Decision History needs structured ADR ingest |
| F3 | `:REVERTS` edges | Consumer #26 Bug-Archaeology needs SZZ-style revert tracking |
| F4 | `paperclip.git.*` integration | If pygit2 perf bottleneck observed |
| F5 | Webhook-based incremental | After `D4 Webhook async-signal v2` lands |
| F6 | Bundle-aware ingest (`bundle="uw-ios"`) | After GIM-182 ships + operator wants per-Kit history |
| F7 | LLM-categorization of commit messages | Consumer #11 / #15 needs structured commit kind |
| F8 | `:File` rename / move tracking via libgit2 `--follow` | Consumer #44 Churn explicitly asks for rename-aware churn |
| F9 | PR review-thread structure (head SHA / line / suggestion) | Consumer #43 needs review-thread reconstruction |
| F10 | Issue (not PR) ingest | Consumer #26 needs `:Issue` nodes for bug labels |
| **F11** | **`palace.code.search_text` MCP tool** for full-text Tantivy query | First Tantivy-consuming consumer (#43 / #11) lands |
| **F12** | Cross-provider Author identity merge heuristic (collapse `git:foo@bar.com` with `github:foologin` when correlation is unambiguous) | Consumer reports duplicate-author noise on real UW data |

### Silent-scope-reduction guard

CR Phase 3.1 must paste:

```bash
git diff --name-only origin/develop...HEAD | sort -u
```

Output must match the file list declared in §4 verbatim **including
docs/CLAUDE.md changes**. Any out-of-scope file → REQUEST CHANGES per
`feedback_silent_scope_reduction.md`.

## 3. Architecture

### 3.1 Three-layer summary

1. **Storage**: Neo4j for structured nodes + edges; new
   `GitHistoryTantivyWriter` writes commit/PR/comment full-text to a
   separate Tantivy index. Per-project group_id namespacing.
2. **Ingest**: 3-phase per-project run (Phase 1 pygit2, Phase 2 GitHub
   GraphQL, Phase 3 verify+complete). Per-phase checkpoint writes.
3. **Query** (no new MCP tool in this slice): consumers use Cypher
   directly. Full-text Tantivy query surface deferred to F11.

### 3.2 Diagram

(Same as rev1 — operator → palace-mcp → pygit2 + GitHub GraphQL →
Neo4j + Tantivy. Diagram unchanged.)

### 3.3 Type contracts (Pydantic v2)

```python
# src/palace_mcp/extractors/git_history/models.py
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, computed_field
import re

_EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TRUNC_MAX = 1024  # bytes; ellipsis adds 3 chars on truncation

class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _validate_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("must be tz-aware")
    return v.astimezone(timezone.utc)


def _validate_truncated(v: str) -> str:
    if len(v) > _TRUNC_MAX + 3:  # 3 for the ellipsis
        raise ValueError(f"truncated body exceeds {_TRUNC_MAX + 3} chars: {len(v)}")
    return v


class Author(FrozenModel):
    """Composite primary key: (provider, identity_key).
    - provider="git" for pygit2-walker authors; identity_key=email_lowercased.
    - provider="github" for GraphQL PR/comment authors; identity_key=login.
    Cross-provider merge is OUT in v1 (F12)."""
    provider: Literal["git", "github"]
    identity_key: str
    email: str | None  # may be None for GitHub authors with private email
    name: str
    is_bot: bool
    first_seen_at: datetime
    last_seen_at: datetime

    @field_validator("identity_key")
    @classmethod
    def _normalize_identity(cls, v: str, info) -> str:
        # For provider="git" (email-based) lowercase; for "github" (login) keep as-is
        return v.lower() if info.data.get("provider") == "git" else v

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
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
    project_id: str        # "project/<slug>" — group_id namespacing
    sha: str               # 40-char hex; primary key (UNIQUE)
    author_provider: Literal["git", "github"]
    author_identity_key: str
    committer_provider: Literal["git", "github"]
    committer_identity_key: str
    message_subject: str   # first line, max 200 chars
    message_full_truncated: str  # max 1027 chars (1024 + ellipsis)
    committed_at: datetime
    parents: tuple[str, ...]    # parent SHAs

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
    number: int            # within project (composite UNIQUE with project_id)
    title: str
    body_truncated: str    # max 1027 chars
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
        # GraphQL returns OPEN | CLOSED | MERGED; we want lowercase
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
    id: str                # GitHub comment node id; primary key
    pr_number: int         # FK to PR (composite with project_id)
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
    """Own checkpoint shape (does NOT reuse foundation IngestCheckpoint).
    See §3.6."""
    project_id: str  # "project/<slug>"
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
    full_resync: bool       # true if force-push detected → fell back to full
    last_commit_sha: str | None
    last_pr_updated_at: datetime | None
    duration_ms: int
```

Edges (Cypher labels):

- `(:Commit)-[:AUTHORED_BY]->(:Author)`
- `(:Commit)-[:COMMITTED_BY]->(:Author)`
- `(:Commit)-[:TOUCHED]->(:File {project_id, path})`
- `(:PR)-[:LINKED_TO]->(:Commit)` — by `head_sha` resolution
- `(:PRComment)-[:COMMENTED_ON]->(:PR)` — was `:ON` in rev1, renamed
- `(:PRComment)-[:AUTHORED_BY]->(:Author)`

### 3.4 Invariants

1. **Sha-based identity for Commit; composite for Author.** Two `:Commit`
   with same sha collapse via `MERGE`. Two `:Author` collapse only when
   `(provider, identity_key)` matches. Cross-provider merge is OUT (F12).
2. **Per-project namespacing.** All nodes carry `project_id =
   "project/<slug>"`. Cross-project queries explicitly traverse via
   `MATCH (c:Commit {project_id: $p}) ...`. No cross-project leakage.
3. **Bot detection is deterministic** — pure regex on `email + name`.
   No LLM. Configurable via `PALACE_GIT_HISTORY_BOT_PATTERNS_JSON` env
   var (default = built-in conservative patterns).
4. **Body truncation invariant** enforced at Pydantic validator boundary
   (not post-hoc): `len(field) <= 1027` (1024 + 3 ellipsis). Full body
   lives ONLY in Tantivy. Cypher queries on full body must use Tantivy
   query surface (deferred to F11).
5. **Idempotent re-walk** with proper time-window semantics. Cypher
   `MERGE` for `:Author` MUST use `ON CREATE` / `ON MATCH` to preserve
   first_seen_at and advance last_seen_at correctly:

   ```cypher
   MERGE (a:Author {provider: $provider, identity_key: $identity_key})
   ON CREATE SET
     a.email = $email, a.name = $name, a.is_bot = $is_bot,
     a.first_seen_at = $ts, a.last_seen_at = $ts,
     a.project_id = $project_id
   ON MATCH SET
     a.last_seen_at = CASE
       WHEN $ts > coalesce(a.last_seen_at, datetime('1970-01-01T00:00:00Z'))
       THEN $ts
       ELSE a.last_seen_at
     END,
     a.first_seen_at = CASE
       WHEN $ts < coalesce(a.first_seen_at, datetime('9999-12-31T23:59:59Z'))
       THEN $ts
       ELSE a.first_seen_at
     END
   ```

   Tested by `test_git_history_author_time_window_preserved`.
6. **Force-push survival.** If `last_commit_sha` not findable via
   `pygit2.Repository.get(sha)`, fall back to full walk; emit
   `git_history_resync_full` JSONL event.
7. **Per-phase checkpoint write.** After Phase 1 success, write
   `last_commit_sha = new_head, last_phase_completed = "phase1"`. After
   Phase 2 success, advance `last_pr_updated_at` and set
   `last_phase_completed = "phase2"`. Phase 2 failure preserves Phase 1
   checkpoint — next run only retries Phase 2.

### 3.5 Foundation extensions (NEW in rev2)

This section is the single source of truth for what reaches into the
existing 101a foundation and what is brand-new in this slice.

| Foundation primitive | Reuse / Extend | Note |
|---|---|---|
| `BaseExtractor.run(*, graphiti, ctx)` | **Reuse** as-is | Method signature MUST match; mirror `symbol_index_python.py:67` |
| `ExtractorRunContext` (project_slug, group_id, repo_path, run_id, duration_ms, logger) | **Reuse** as-is | Driver/settings via deferred `from palace_mcp.mcp_server import get_driver, get_settings` |
| `ExtractorStats(nodes_written, edges_written)` | **Reuse** as-is | NO `success` or `metadata` fields — return summary via JSONL events instead (§5.3) |
| `check_resume_budget(previous_error_code)` | **Reuse** as-is | Pre-flight at start of run() |
| `ensure_custom_schema(driver)` | **Extend** (~30 LOC) | Add Commit/Author/PR/PRComment/File constraints |
| `check_phase_budget(...)` | **Reuse** with new phase names ("phase1_commits", "phase2_prs", "phase3_complete") | Per-phase pre-flight |
| `create_ingest_run(driver, extractor_name="git_history", ...)` | **Reuse** | Note: `extractor_name=` (not `source=`); see fixture symbol_index_python.py |
| `IngestCheckpoint` model in foundation | **NOT reuse** | SCIP-specific (`expected_doc_count`, phase Literal); we ship our own (§3.6) |
| `TantivyBridge` | **NOT reuse** | Typed to `SymbolOccurrence`; we ship our own writer (§3.7) |
| `BoundedInDegreeCounter`, `importance_score` | Skip in v1 | Not relevant to git data |

**Critical**: implementation MUST mirror the structure of
`symbol_index_python.py` for the run() body, especially:

- Deferred import of `get_driver`/`get_settings` to avoid circular
  import (mcp_server → registry → here → mcp_server).
- Pre-flight checks: `_get_previous_error_code` → `check_resume_budget`
  → `ensure_custom_schema` → `create_ingest_run`.
- Per-phase guarded by `check_phase_budget`.
- Final return constructs `ExtractorStats(nodes_written=N, edges_written=M)`
  — with both numbers concrete and accurate per Cypher write counters.

### 3.6 Checkpoint state — `:GitHistoryCheckpoint` (NEW in rev2)

Existing `:IngestCheckpoint` (foundation/checkpoint.py:18) cannot be
reused for git_history because:

- Its `phase: Literal["phase1_defs", "phase2_user_uses", "phase3_vendor_uses"]`
  is hard-coded SCIP.
- Its `expected_doc_count: int` is doc-count-specific.

Adding new fields and broadening `phase` Literal would touch all
existing extractors (migration concern + uniqueness constraint
re-creation). The cleaner path is a separate node type:

```python
# checkpoint.py — own implementation
async def write_checkpoint(
    driver: AsyncDriver,
    project_id: str,
    *,
    last_commit_sha: str | None,
    last_pr_updated_at: datetime | None,
    last_phase_completed: Literal["none", "phase1", "phase2"],
) -> None:
    """Idempotent write to :GitHistoryCheckpoint via MERGE."""
    cypher = """
    MERGE (c:GitHistoryCheckpoint {project_id: $project_id})
    SET c.last_commit_sha = $last_commit_sha,
        c.last_pr_updated_at = $last_pr_updated_at,
        c.last_phase_completed = $last_phase_completed,
        c.updated_at = datetime()
    """
    await driver.execute_query(cypher, project_id=project_id, ...)
```

Constraint added to `ensure_custom_schema()` extension:

```cypher
CREATE CONSTRAINT git_history_checkpoint_unique IF NOT EXISTS
FOR (c:GitHistoryCheckpoint) REQUIRE c.project_id IS UNIQUE
```

Tests: `test_git_history_checkpoint_round_trip`,
`test_git_history_checkpoint_phase1_advance_only`.

### 3.7 Tantivy writer — `GitHistoryTantivyWriter` (NEW in rev2)

Existing `TantivyBridge` (foundation/tantivy_bridge.py) cannot be
reused — its schema and `add_or_replace_async(SymbolOccurrence)` API
are typed for SCIP occurrences. We ship a parallel writer:

```python
# tantivy_writer.py — own implementation
class GitHistoryTantivyWriter:
    """Writes commit/PR/comment full-text to a dedicated Tantivy index.
    Separate from TantivyBridge — different schema, different document type."""

    def __init__(self, index_path: Path, heap_mb: int = 100) -> None:
        self._schema = self._build_schema()
        self._index = tantivy.Index(self._schema, str(index_path))
        ...

    @staticmethod
    def _build_schema() -> tantivy.Schema:
        sb = tantivy.SchemaBuilder()
        sb.add_text_field("doc_kind", indexed=True, fast=True, stored=True)  # "commit"|"pr"|"pr_comment"
        sb.add_text_field("project_id", indexed=True, fast=True, stored=True)
        sb.add_text_field("doc_id", indexed=True, stored=True)  # sha or PR-number or comment-id
        sb.add_text_field("body", indexed=True, stored=True)
        sb.add_text_field("author_identity_key", indexed=True, fast=True, stored=True)
        sb.add_date_field("ts", indexed=True, fast=True, stored=True)
        sb.add_bool_field("is_bot", indexed=True, fast=True, stored=True)
        return sb.build()

    async def add_commit_async(self, commit: Commit, body_full: str) -> None: ...
    async def add_pr_async(self, pr: PR, body_full: str) -> None: ...
    async def add_pr_comment_async(self, comment: PRComment, body_full: str) -> None: ...
    async def commit_async(self) -> None: ...
```

Index path: configurable via `PALACE_GIT_HISTORY_TANTIVY_INDEX_PATH`
env var; defaults to `<PALACE_TANTIVY_INDEX_PATH>/git_history/`.

**Note**: full-text query surface is OUT in v1 (F11 deferred). Tantivy
data is written and unit-test-verified; no MCP query tool in this
slice. Smoke gate verifies via Cypher count, not Tantivy query.

## 4. Component layout

```
services/palace-mcp/src/palace_mcp/extractors/git_history/
├── __init__.py                  (NEW ~10 LOC)
├── extractor.py                 (NEW ~180 LOC: GitHistoryExtractor mirrors symbol_index_python pattern)
├── pygit2_walker.py             (NEW ~140 LOC)
├── github_client.py             (NEW ~200 LOC: graphql + rateLimit cost-aware)
├── models.py                    (NEW ~180 LOC: Pydantic v2 schemas with validators)
├── tantivy_writer.py            (NEW ~130 LOC: own GitHistoryTantivyWriter)
├── neo4j_writer.py              (NEW ~150 LOC: Cypher MERGE patterns including ON CREATE/MATCH)
├── bot_detector.py              (NEW ~70 LOC)
└── checkpoint.py                (NEW ~80 LOC: :GitHistoryCheckpoint own shape)

services/palace-mcp/src/palace_mcp/extractors/foundation/schema.py
                                 (EXTEND ~40 LOC: add 6 git_history constraints to ensure_custom_schema())

services/palace-mcp/src/palace_mcp/extractors/registry.py
                                 (EXTEND +2 LOC)

services/palace-mcp/src/palace_mcp/config.py
                                 (EXTEND +8 LOC: PALACE_GITHUB_TOKEN +
                                    PALACE_GIT_HISTORY_BOT_PATTERNS_JSON +
                                    PALACE_GIT_HISTORY_MAX_COMMITS_PER_RUN +
                                    PALACE_GIT_HISTORY_TANTIVY_INDEX_PATH)

services/palace-mcp/tests/extractors/
├── unit/
│   ├── test_git_history_extractor.py          (NEW ~280 LOC)
│   ├── test_git_history_pygit2_walker.py      (NEW ~180 LOC)
│   ├── test_git_history_github_client.py      (NEW ~250 LOC, respx mocks; covers rateLimit cost)
│   ├── test_git_history_bot_detector.py       (NEW ~100 LOC, ~30 parametrized cases)
│   ├── test_git_history_models.py             (NEW ~200 LOC, including email edge cases T2)
│   ├── test_git_history_neo4j_writer.py       (NEW ~120 LOC, ON CREATE/MATCH semantics)
│   └── test_git_history_checkpoint.py         (NEW ~100 LOC, phase advance + round-trip)
├── integration/
│   └── test_git_history_integration.py        (NEW ~280 LOC, testcontainers Neo4j + respx)
└── fixtures/
    └── git-history-mini-project/              (NEW)
        ├── REGEN.md
        ├── repo/                              — synthetic .git directory committed
        └── github_responses/                  — captured GraphQL response fixtures

services/palace-mcp/scripts/
└── smoke_git_history.py                       (NEW ~140 LOC, real ClientSession.call_tool)

CLAUDE.md                        (EXTEND ~30 LOC: §"Extractors" → add git_history row + workflow)
.env.example                     (EXTEND +4 lines: 4 new env vars)

docs/runbooks/
└── git-history-harvester.md     (NEW ~200 LOC: setup + token + smoke + troubleshooting + bot patterns)
```

**Estimated size**: ~1,140 LOC prod + ~1,510 LOC test + spec + plan + runbook + fixture.

## 5. Data flow

### 5.1 Ingest pipeline (rewritten against real BaseExtractor contract)

```python
# extractor.py — actual contract per symbol_index_python.py:67-104
class GitHistoryExtractor(BaseExtractor):
    name: ClassVar[str] = "git_history"
    description: ClassVar[str] = "Walks git commit history + GitHub PR/comment data."
    constraints: ClassVar[list[str]] = [...]  # SCHEMA constraint Cypher
    indexes: ClassVar[list[str]] = [...]

    async def run(
        self, *, graphiti: Graphiti, ctx: ExtractorRunContext
    ) -> ExtractorStats:
        # Deferred import — same pattern as symbol_index_python.py
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()
        if driver is None or settings is None:
            raise ExtractorError(...)

        # 0. Pre-flight
        previous_error = await _get_previous_error_code(driver, ctx.project_slug)
        check_resume_budget(previous_error_code=previous_error)

        # 1. Schema bootstrap
        await ensure_custom_schema(driver)

        # 2. NOTE: create_ingest_run is the foundation primitive — call it
        # the same way symbol_index_python.py does (passing ctx.run_id).
        # See foundation/checkpoint.py:44 for actual signature.
        # If runner already creates IngestRun, this is the no-op-update path.

        ckpt = await load_git_history_checkpoint(driver, ctx.project_slug)
        commits_written = 0
        prs_written = 0
        pr_comments_written = 0
        edges_written = 0
        full_resync = False

        # === Phase 1: pygit2 commit walk ===
        check_phase_budget(commits_written, settings.max_commits_per_run, ...)
        try:
            walker = Pygit2Walker(repo_path=ctx.repo_path)
            new_head_sha = walker.head_sha()
            try:
                walk_iter = walker.walk_since(ckpt.last_commit_sha)
            except CommitNotFoundError:
                logger.warning(
                    "git_history_resync_full",
                    extra={"event": "git_history_resync_full",
                           "project_id": ctx.group_id,
                           "last_commit_sha_attempted": ckpt.last_commit_sha},
                )
                full_resync = True
                walk_iter = walker.walk_since(None)

            tantivy_writer = GitHistoryTantivyWriter(settings.git_history_tantivy_index_path)
            async with tantivy_writer:
                async for batch in batched(walk_iter, size=500):
                    await write_commits_to_neo4j(driver, batch, ctx.group_id)
                    for commit in batch:
                        await tantivy_writer.add_commit_async(commit, body_full=...)
                        commits_written += 1
                        edges_written += 2 + len(commit.touched_files)  # AUTHORED_BY + COMMITTED_BY + TOUCHED*
                await tantivy_writer.commit_async()

            # Per-phase checkpoint write (rev2 fix)
            await write_git_history_checkpoint(
                driver, ctx.project_slug,
                last_commit_sha=new_head_sha,
                last_pr_updated_at=ckpt.last_pr_updated_at,  # unchanged at this phase
                last_phase_completed="phase1",
            )
            logger.info("git_history_phase1_complete",
                        extra={"event": "git_history_phase1_complete",
                               "project_id": ctx.group_id,
                               "commits_written": commits_written})

        except Exception as exc:
            logger.exception("git_history_phase1_failed",
                             extra={"event": "git_history_phase_failed",
                                    "project_id": ctx.group_id,
                                    "phase": "phase1",
                                    "error_repr": repr(exc)})
            raise

        # === Phase 2: GitHub GraphQL ===
        if not settings.github_token:
            logger.warning("git_history_no_github_token",
                           extra={"event": "git_history_phase2_skipped_no_token",
                                  "project_id": ctx.group_id})
            return ExtractorStats(nodes_written=commits_written, edges_written=edges_written)

        check_phase_budget(prs_written, settings.max_prs_per_run, ...)
        try:
            github_client = GitHubClient(token=settings.github_token)
            new_pr_max_updated = ckpt.last_pr_updated_at
            tantivy_writer = GitHistoryTantivyWriter(settings.git_history_tantivy_index_path)
            async with tantivy_writer:
                async for pr_batch in github_client.fetch_prs_since(
                    repo_owner=settings.gh_repo_owner_for_project(ctx.project_slug),
                    repo_name=settings.gh_repo_name_for_project(ctx.project_slug),
                    since=ckpt.last_pr_updated_at,
                ):
                    await write_prs_to_neo4j(driver, pr_batch, ctx.group_id)
                    for pr in pr_batch:
                        await tantivy_writer.add_pr_async(pr, body_full=...)
                        async for cmt_batch in github_client.fetch_pr_comments(pr):
                            await write_comments_to_neo4j(driver, cmt_batch, ctx.group_id)
                            for cmt in cmt_batch:
                                await tantivy_writer.add_pr_comment_async(cmt, body_full=...)
                                pr_comments_written += 1
                        prs_written += 1
                        if pr.updated_at > new_pr_max_updated:
                            new_pr_max_updated = pr.updated_at
                await tantivy_writer.commit_async()

            # Per-phase checkpoint write (rev2 fix)
            await write_git_history_checkpoint(
                driver, ctx.project_slug,
                last_commit_sha=new_head_sha,
                last_pr_updated_at=new_pr_max_updated,
                last_phase_completed="phase2",
            )
            logger.info("git_history_phase2_complete",
                        extra={"event": "git_history_phase2_complete",
                               "project_id": ctx.group_id,
                               "prs_written": prs_written,
                               "pr_comments_written": pr_comments_written})

        except Exception as exc:
            logger.exception("git_history_phase2_failed",
                             extra={"event": "git_history_phase_failed",
                                    "project_id": ctx.group_id,
                                    "phase": "phase2",
                                    "error_repr": repr(exc)})
            # Phase 1 checkpoint persists — next run only retries Phase 2.
            raise

        # === Phase 3: complete ===
        logger.info("git_history_complete",
                    extra={"event": "git_history_complete",
                           "project_id": ctx.group_id,
                           "commits_written": commits_written,
                           "prs_written": prs_written,
                           "pr_comments_written": pr_comments_written,
                           "full_resync": full_resync})

        return ExtractorStats(
            nodes_written=commits_written + prs_written + pr_comments_written,
            edges_written=edges_written,
        )
```

### 5.2 GitHub GraphQL (rev2 corrections)

```graphql
query($owner: String!, $name: String!, $cursor: String, $since: DateTime!) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: 50, after: $cursor,
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage, endCursor }
      nodes {
        number title body state
        author {
          login
          ... on User { email }
          ... on Bot { id }
          ... on Mannequin { id }
        }
        createdAt updatedAt mergedAt
        headRefOid baseRef { name }
        comments(first: 100) {
          totalCount
          pageInfo { hasNextPage, endCursor }
          nodes {
            id body
            author {
              login
              ... on User { email }
              ... on Bot { id }
            }
            createdAt
          }
        }
      }
    }
  }
  rateLimit { cost remaining limit resetAt }
}
```

Client logic:

- Stop outer paginating when `pr.updatedAt < since`.
- Inner comment pagination: if `pr.comments.pageInfo.hasNextPage`, fall
  back to a separate cursored query for that PR's remaining comments.
  Most PRs in UW-android have <100 comments; inline 100 covers the
  common case. Outer + inner cursor are independent.
- **Cost-aware budget enforcement**: every response carries
  `rateLimit { cost remaining limit resetAt }`. If
  `remaining - estimated_next_cost < 100`, **fail fast** with
  `ExtractorRuntimeError(error_code="rate_limit_exhausted")` rather
  than sleep — sleeping until `resetAt` would exceed
  `EXTRACTOR_TIMEOUT_S = 300s` (typically resetAt is up to 1 hour
  away). Operator retries after an hour.
- Retry on transient 5xx/429: bounded backoff (3 attempts, jittered
  500ms / 2s / 5s) within timeout budget.

### 5.3 JSONL event schema

Daemon emits these events to `~/.paperclip/palace-mcp.log`:

| `event` | Fields | When |
|---|---|---|
| `git_history_phase1_complete` | `project_id, commits_written` | After pygit2 walk |
| `git_history_phase2_complete` | `project_id, prs_written, pr_comments_written` | After GraphQL |
| `git_history_phase2_skipped_no_token` | `project_id` | `PALACE_GITHUB_TOKEN` unset |
| `git_history_resync_full` | `project_id, last_commit_sha_attempted` | Force-push detected |
| `git_history_rate_limit_throttled` | `project_id, cost, remaining, reset_at` | Backoff on 429/transient |
| `git_history_phase_failed` | `project_id, phase, error_repr` | Per-phase except block |
| `git_history_complete` | `project_id, commits_written, prs_written, pr_comments_written, full_resync` | After successful run |

## 6. Bot detection

Conservative regex-only patterns. **Removed in rev2**: `r".*-bot@.*"`
(matched humans like `someone-bot@company.com`).

```python
# bot_detector.py — built-in patterns (rev2 tightened)
_BOT_EMAIL_PATTERNS = [
    re.compile(r".*\[bot\]@users\.noreply\.github\.com$"),  # *[bot]@... only
    re.compile(r".*@dependabot\.com$"),
    re.compile(r"^renovate\[bot\]@.*"),
]
_BOT_NAME_PATTERNS = [
    re.compile(r"^github-actions(\[bot\])?$", re.I),
    re.compile(r"^dependabot(\[bot\])?$", re.I),
    re.compile(r"^renovate(\[bot\])?$", re.I),
    re.compile(r"^paperclip-bot$", re.I),
    re.compile(r".*\[bot\]$", re.I),  # explicit [bot] suffix
]

def is_bot(email: str | None, name: str | None) -> bool:
    if email:
        if any(p.match(email) for p in _BOT_EMAIL_PATTERNS):
            return True
    if name:
        if any(p.match(name) for p in _BOT_NAME_PATTERNS):
            return True
    return False
```

Override via `PALACE_GIT_HISTORY_BOT_PATTERNS_JSON` env var (JSON dict
`{"email": [...], "name": [...]}`).

Tests cover ~30 cases:
- Positive: GitHub Actions, Dependabot, Renovate, Paperclip bot,
  generic `*[bot]`.
- Negative: humans with `bot` substring (`bot-fan@company.com`,
  `Robot Joe`); empty email; None email; humans like `someone-bot@`
  (this MUST be human now, was bot in rev1).
- Edge: case sensitivity, whitespace, unicode in name.

## 7. Configuration

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
    git_history_tantivy_index_path: Path = Field(
        default=Path("/var/lib/palace/tantivy/git_history"),
        alias="PALACE_GIT_HISTORY_TANTIVY_INDEX_PATH",
    )
```

Phase 2 (GitHub) is OPTIONAL. If `PALACE_GITHUB_TOKEN` unset, Phase 2
is skipped with `git_history_phase2_skipped_no_token` event; Phase 1
runs normally. Operator can ingest local-only history without token.

## 8. Acceptance criteria

1. **Extractor registered** — `palace.ingest.list_extractors()` shows `git_history`.
2. **Pydantic v2 models with validators** — every truncated body has a
   length validator; every datetime has tz-aware validator;
   email validator allows None/empty (returns None).
3. **Composite Author PK** — `(provider, identity_key)` UNIQUE
   constraint; tests assert two `:Author` for the same person under
   different providers (no cross-provider merge in v1).
4. **Neo4j schema constraints** ensured at server startup, including
   `:GitHistoryCheckpoint.project_id` UNIQUE.
5. **Tantivy `git_history` index** writes commit/PR/comment docs;
   verified by integration test that writes 1 doc per kind and reads
   them back via direct Tantivy `Searcher` (NOT via MCP — that's F11).
6. **pygit2 walker incremental + resync** — re-running with same
   checkpoint produces 0 new commits; invalid `last_commit_sha`
   triggers `git_history_resync_full` event + full re-walk.
7. **GitHub GraphQL pagination** — outer + inner cursor handled;
   3-page outer fixture exhausted; 200-comment inner pagination tested.
8. **GitHub rate-limit cost-aware fail-fast** — when
   `remaining - estimated_next_cost < 100`, raise
   `ExtractorRuntimeError(rate_limit_exhausted)`; do NOT sleep beyond
   `EXTRACTOR_TIMEOUT_S = 300s`.
9. **GraphQL `author { ... on User { email } }` syntax** — verified by
   schema-validating the query against GitHub introspection (test asserts
   query parses).
10. **Bot detection regex** — 30+ parametrized cases pass, including
    `someone-bot@company.com` is HUMAN (rev2 tightening).
11. **Email lowercasing** — `Foo@Bar.com` and `foo@bar.com` collapse to
    single `:Author` when both have `provider="git"`.
12. **`MERGE` Author preserves time-window** —
    `test_git_history_author_time_window_preserved`: re-walking older
    commit does NOT overwrite `first_seen_at`; advances `last_seen_at`
    only when newer.
13. **Per-phase checkpoint write + Phase 2 failure preserves Phase 1** —
    inject failure in Phase 2 GraphQL, assert
    `:GitHistoryCheckpoint.last_commit_sha == new_head_sha` AND
    `last_phase_completed == "phase1"`. Re-run skips Phase 1.
14. **PR re-ingestion at boundary** — PR with `updatedAt == since`
    re-ingested, MERGE-idempotent (single `:PR` node).
15. **JSONL events emitted** — every event from §5.3 has at least one
    test (7 events × 1 test minimum).
16. **GitHub-disabled mode** — when `PALACE_GITHUB_TOKEN` unset, Phase 2
    skipped with `git_history_phase2_skipped_no_token` event; Phase 1
    runs; checkpoint records `last_phase_completed == "phase1"`.
17. **Backward compatibility** — existing extractors unaffected;
    `symbol_index_python` runs after git_history schema extension on a
    fresh Neo4j; ALSO `:Commit` from non-git_history source (legacy
    third-party node accidentally pre-existing) does NOT block schema
    bootstrap (graceful — UNIQUE constraint creation skips if duplicate
    exists, logs warning, operator notified via JSONL).
18. **Per-module 90% coverage** —
    `palace_mcp.extractors.git_history.{extractor, pygit2_walker,
    github_client, bot_detector}`. All four green.
19. **Lint / format / mypy / pytest gates** — `uv run ruff check`,
    `uv run ruff format --check`, `uv run mypy src/`, `uv run pytest -q`
    all green.
20. **Live smoke on iMac** — operator-driven smoke per §9.4 with
    SSH-from-iMac evidence.
21. **CLAUDE.md updated** — §"Extractors" → new `git_history` row +
    operator workflow section.
22. **Runbook present** — `docs/runbooks/git-history-harvester.md`
    covers setup (token), full + incremental ingest, resync recovery,
    bot pattern configuration, troubleshooting, smoke procedure.
23. **Mini-fixture committed** with deterministic regen via `REGEN.md`.

## 9. Verification plan

### 9.1 Pre-implementation (CTO Phase 1.1)

1. Confirm branch starts from `57545cb`.
2. Confirm 101a foundation primitives stable (`BaseExtractor`,
   `ExtractorRunContext`, `ExtractorStats`, `ensure_custom_schema`,
   `:IngestRun`, `create_ingest_run`).
3. Confirm `pygit2` available in `services/palace-mcp/pyproject.toml`
   or planned to be added (likely added in Phase 2 by PE).
4. Confirm `respx` available for HTTP mocks in tests.
5. Verify operator's `gh` PAT can be read via env var in container.

### 9.2 Per-task gates

Each implementation task ends with a green test target before next
starts. See implementation plan.

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
uv run pytest --cov=palace_mcp.extractors.git_history.bot_detector --cov-fail-under=90 \
  tests/extractors/unit/test_git_history_bot_detector.py -q
```

All must exit 0.

### 9.4 Live smoke (Phase 4.1, on iMac)

#### 9.4.1 Pre-flight

1. `ssh imac-ssh.ant013.work 'date -u; hostname; uname -a; uptime'` —
   identity capture.
2. Confirm `PALACE_GITHUB_TOKEN` set in iMac `.env`; redact on capture.
3. Capture **pre-smoke** rate-limit baseline:
   ```bash
   ssh imac-ssh.ant013.work 'gh api rate_limit | jq .resources.graphql.remaining' \
     | tee /tmp/rate-limit-pre.txt
   ```
4. Confirm `gimle` and `uw-android` parent_mounts live in `docker-compose.yml`.
5. Restart palace-mcp via `docker compose --profile review up -d
   --force-recreate palace-mcp` after env-var changes.
6. Determine deterministic anchor for Tantivy verification (latest
   commit subject):
   ```bash
   ssh imac-ssh.ant013.work \
     "git -C /Users/Shared/Ios/Gimle-Palace log -1 --pretty=%s" \
     | tee /tmp/anchor-subject.txt
   ```

#### 9.4.2 Smoke procedure (real `mcp.ClientSession.call_tool`)

```python
# scripts/smoke_git_history.py — bundled in this slice
import asyncio
import json
import os
import sys

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

PALACE_MCP_URL = os.environ.get("PALACE_MCP_URL", "http://localhost:8080/mcp")

async def call(session: ClientSession, tool: str, args: dict) -> dict:
    result = await session.call_tool(name=tool, arguments=args)
    return json.loads(result.content[0].text)

async def main() -> int:
    async with streamablehttp_client(PALACE_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Ingest gimle (small).
            gimle_first = await call(session, "palace.ingest.run_extractor",
                                     {"name": "git_history", "project": "gimle"})
            # 2. Re-ingest gimle (incremental — should be ~0 new commits).
            gimle_second = await call(session, "palace.ingest.run_extractor",
                                      {"name": "git_history", "project": "gimle"})
            # 3. Ingest uw-android (real, larger).
            uw_first = await call(session, "palace.ingest.run_extractor",
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

Smoke is GREEN iff ALL of the following:

- `gimle_first.success` (interpreted via JSONL events captured during run)
- `gimle_first.duration_ms < 5000` (3s typical for ~60 commits + ~10 PRs)
- Cypher gate post-smoke (NO Tantivy MCP query — that's F11):
  ```cypher
  MATCH (c:Commit {project_id:'project/gimle'}) RETURN count(c) AS n
  ```
  Must return `n > 0`.
- `:Author collapse` check:
  ```cypher
  MATCH (a:Author {project_id:'project/gimle', provider:'git'})
    WHERE toLower(a.email) = toLower($operator_email)
  RETURN count(a) AS n
  ```
  Must return `n == 1` (Anton Stavnichiy collapses to single :Author).
- `Bot detection` check:
  ```cypher
  MATCH (a:Author {project_id:'project/gimle', is_bot:true}) RETURN count(a) AS n
  ```
  Must return `n >= 1` (assuming gimle history contains
  github-actions[bot] or similar).
- Phase 2 `gimle_second` ingest: `commits_written == 0` (incremental
  works on stable history); incremental run completes in < 1 s.
- `uw_first.duration_ms < 60000` (1 min target for ~10K commits).
- **Rate-limit DELTA gate**:
  ```bash
  ssh imac-ssh.ant013.work 'gh api rate_limit | jq .resources.graphql.remaining' \
    | tee /tmp/rate-limit-post.txt
  start=$(cat /tmp/rate-limit-pre.txt)
  end=$(cat /tmp/rate-limit-post.txt)
  consumed=$((start - end))
  test "$consumed" -lt 500 || echo "FAIL: consumed $consumed > 500"
  ```
  Smoke must consume < 500 GraphQL points (most uw-android PRs ingest
  in single GraphQL pages; ~150 PRs × cost ~3 = ~450 budget).

Any failure → smoke RED → REQUEST CHANGES.

#### 9.4.5 Evidence (full failure logs)

PR body `## QA Evidence` must include verbatim:

```
$ ssh imac-ssh.ant013.work 'date -u; hostname; uname -a'
<output>

$ jq '.gimle_first, .gimle_second, .uw_first' /tmp/git-history-smoke-*.log
<full ingest summaries>

$ ssh imac-ssh.ant013.work \
  'cat ~/.paperclip/palace-mcp.log | jq -c "select(.event | test(\"git_history_\"))"'
<all git_history_* events>

$ # Cypher counts
$ ssh imac-ssh.ant013.work \
  'docker exec palace-neo4j cypher-shell ... <queries from §9.4.4>'
<results>

$ # Rate limit delta
start=$(cat /tmp/rate-limit-pre.txt); end=$(cat /tmp/rate-limit-post.txt)
echo "consumed=$((start - end)) (<500 required)"
<output>
```

#### 9.4.6 Cleanup

If smoke succeeded, ingested data persists for production use. If failed
and operator wants to retry from scratch:

```cypher
MATCH (n) WHERE n.project_id IN ['project/gimle', 'project/uw-android']
  AND any(label IN labels(n) WHERE label IN
    ['Commit', 'Author', 'PR', 'PRComment', 'File', 'GitHistoryCheckpoint'])
DETACH DELETE n;
```

Plus delete the `git_history` Tantivy index directory scoped to the
same project_ids.

## 10. Out of scope (deferred)

See §2 OUT table for reactivation triggers.

## 11. Risks and mitigations

- **pygit2 perf on UW-android (~10K commits)** — first run ~30 s
  estimated; incremental drops to seconds.
- **`EXTRACTOR_TIMEOUT_S = 300s` ceiling** — full UW history with
  thousands of PRs + comments could exceed timeout. Mitigation:
  `PALACE_GIT_HISTORY_MAX_COMMITS_PER_RUN=50_000` cap; for repos
  exceeding it, operator chunks via repeated invocations (incremental
  picks up where left off). Documented in runbook.
- **GitHub rate-limit budget exhaustion** — Mitigation: cost-aware
  fail-fast (§5.2); operator retries after 1 hour. NEVER sleep beyond
  EXTRACTOR_TIMEOUT_S.
- **Force-push silent drift** — Mitigation: resync detection emits
  `git_history_resync_full` event; operator periodically `git pull`s
  mounted clones.
- **Bot regex false positives** — Mitigation: tightened regex (rev2
  removed `.*-bot@.*` which matched humans); 30 parametrized tests
  cover known cases.
- **Author identity heuristic limits** — Mitigation: composite PK
  documented; cross-provider merge is F12 deferred. Risk: same human
  shows as 2 `:Author` (one git, one github). Acceptable for v1; F12
  ships when consumer (e.g. #32 Code Ownership) reports duplication.
- **Tantivy collection conflict** — Mitigation: separate index
  directory; `project_id` as fast field; queries filter by it.
- **GitHub token leak** — Mitigation: existing operator pattern;
  redact on log capture per QA procedure §9.4.5.
- **`gh` token scope** — Mitigation: Phase 4.1 Pre-flight verifies
  `gh api user` returns expected user + scopes.
- **Body truncation loses data** — Mitigation: documented; full body
  in Tantivy; Cypher-only consumers see truncated subset.
- **Concurrent re-ingest** — Mitigation: palace-mcp event loop
  serializes MCP tool calls. No change needed for v1.
- **Schema drift on existing legacy `:Commit`** — Mitigation:
  acceptance #17 explicitly tests bootstrap with pre-existing legacy
  node; UNIQUE constraint creation logs warning rather than crash if
  duplicate detected.

## 12. Rollout

1. **Phase 1.1 CTO Formalize** — verify spec + plan paths, swap any
   placeholders, reassign CR.
2. **Phase 1.2 CR Plan-first review** — APPROVE comment must restate
   these 6 invariants (§3.4):
   - Sha-based PK for Commit; composite (provider, identity_key) for Author.
   - Per-project namespacing (group_id = "project/<slug>").
   - Bot detection deterministic regex (no LLM).
   - Body truncation enforced at validator boundary (`<= 1027` chars).
   - MERGE Author with explicit `ON CREATE` / `ON MATCH` for
     first_seen_at / last_seen_at (cypher snippet in §3.4).
   - Per-phase checkpoint write (Phase 2 failure preserves Phase 1
     advance).
3. **Phase 2 Implementation** — TDD through plan tasks.
4. **Phase 3.1 CR Mechanical** — including scope audit (CLAUDE.md
   counted in scope-guard diff), per-module coverage gates (4
   modules), foundation-extension review (§3.5).
5. **Phase 3.2 OpusArchitectReviewer Adversarial** — required vectors:
   - Force-push silent drift (resync detection works).
   - GitHub rate-limit cost-aware fail-fast (does NOT sleep beyond
     EXTRACTOR_TIMEOUT_S).
   - Bot regex false-positive on humans with `bot` substring.
   - Race: pygit2 walk while local repo is being `git pull`'d.
   - Author MERGE preserves first_seen_at when re-walking older commit.
   - Phase 2 failure preserves Phase 1 checkpoint advance.
   - Tantivy doc-id collision across projects.
   - Empty / None email handling in pygit2 commits.
6. **Phase 4.1 QA Live smoke** with SSH-from-iMac evidence.
7. **Phase 4.2 CTO Merge**.

## 13. Open questions

- **`PALACE_GITHUB_TOKEN` rotation** — operator's `gh` PAT may need
  rotation periodically. Document in runbook + memory reference.
- **Author identity merge across providers** — F12 deferred; revisit
  when first consumer reports duplication.
- **gh repo owner/name resolution** — `Settings.gh_repo_owner_for_project`
  and `Settings.gh_repo_name_for_project` must be wired. v1 uses a
  static map in `config.py` (e.g. `{"gimle": ("ant013",
  "Gimle-Palace"), "uw-android": ("horizontalsystems",
  "unstoppable-wallet-android")}`). Consumer ordering and roadmap
  questions are out of scope of this spec.
