# Gimle freshness & identity integrity fixes (Sprint-1 reliability response)

**Date:** 2026-07-17
**Author:** Anton + Claude (Board)
**Status:** Design **v2** — voltAgent panel folded in (architect: APPROVE-WITH-CHANGES; code: REQUEST-CHANGES; silent-failure: REVISE — all findings addressed below). Ready to implement.
**Trigger:** thorchain Sprint-1 report (Trust RED). All defects independently verified live 2026-07-17.

## Verified root causes (panel-corrected citations)

1. **Unknown freshness reported as fresh.** `inspect_freshness` (`snippet_provider.py:203-263`) returns `stale=False` on four non-positive branches incl. blanket `except Exception` (`:258-263`). Consumers: semantic row `status` via truthiness (`find_semantic.py:796`), snippet payloads (`native_get_code_snippet.py:285,455,476`). NB (panel correction): overview never serialized `stale` — its defect is #2's wrong lag base, not a stale flag.
2. **Project "indexed commit" is a dominant vote** (`PROJECT_INDEXED_COMMIT`, `cypher.py:372-382`) over per-symbol `last_seen_in_commit`; incremental leaves unchanged symbols on old shas (live: evm 44,216/44,717 on the pre-update sha) → overview computed lag against the wrong base ("EvmKit 3 behind" while current). No writer sets `:Project.indexed_commit`. **The same vote also drives incremental-vs-full planning** (`_read_project_indexed_commit`, `project_analyze.py:363-372`).
3. **Registry identity inconsistent.** Live: `tron-kit.repo_path=NULL`; `hd-wallet-kit` repo_path→`hd-wallet-kit-ios` (indexed `1bc214b25`) vs relative_path→`HdWalletKit.Swift` (different repo, own scip). `register_project` (`project_tools.py:79`) accepts no repo_path, cross-checks nothing; `resolve_registered_project` (`path_resolver.py:72-116`) silently falls through 3 tiers.
4. **"Lag" = index-vs-local-tree without fetch**; consumers read "lag 0" as "current with upstream".
5. **`git_sha` is an env label** (`main.py:173`, `mcp_server.py:508`).

Out of scope: GIM-SEMANTIC-UNDERFILL (separate repro-first task); any origin fetch in read paths (panel: mutates the shared checkout under live ingest — `check_origin` CUT from this slice); bulk rewrite of `last_seen_in_commit` (per-symbol provenance stays; consumers stop reading it as project currency).

## F1 — Tri-state freshness (no fresh without positive evidence)

- `FreshnessResult` AND `SnippetResult` (`snippet_provider.py:62,69`): `stale: bool | None = None`; add `freshness_state: "current" | "behind" | "unknown"` and `freshness_reason: "no_indexed_commit" | "repo_unresolved" | "indexed_commit_not_in_tree" | "git_error" | "timeout" | None`. `inspect_freshness` maps every non-positive branch to `unknown` + reason + debug log. `indexed_commit_not_in_tree` (rev-list failure) is the read-time signature of an F3 identity mismatch — distinct reason, not generic error.
- **Unconditional emission**: every payload that today can carry `stale` emits `stale` (nullable) + `freshness_state` + `freshness_reason` ALWAYS — including `_error()` payloads (`native_get_code_snippet.py:88-104`: remove omit-if-None for these fields). No `.get("stale", False)` footgun.
- **Truthiness collapse sites (exhaustive, from panel grep)** — each becomes `is True` + explicit unknown handling:
  - `find_semantic.py:796` `if snippet.stale:` → `stale is True` → `status="stale_source"`; `stale is None` → `status="freshness_unknown"` (third value, never silent omission).
  - Serializers `native_get_code_snippet.py:285,455,476`; `snippet_scope.py:124` consumer; `project_tools.py` overview/list.
- **Test migration (pinned)**: `tests/code/test_snippet_provider.py:309` (no commit_sha → `stale is None`), `test_native_get_code_snippet.py:399-401` (repo-unresolved → `None`/`unknown`, not `False`), `:510` and `test_find_semantic.py:771` (`stale is True` stays). New: unknown does NOT yield `stale_source`; unknown yields `freshness_unknown` status.

## F2 — Authoritative `:Project.indexed_commit` (panel-rebased source of truth)

- **Source = the extractor's ingest-time tree HEAD** — what symbols were actually stamped with (`_read_head_sha(ctx.repo_path)`, `symbol_index_swift.py:249`, same pattern in ts/java/python extractors). Language-agnostic; zero emit-vs-ingest skew. **NOT the scip sidecar meta** (Swift-only writer `cli.py:662`; emit-time sha diverges from ingest when the tree moved between emit and analyze — writing it would create a new vote-vs-fact split). The meta's `repo_head_sha`, when present, is used ONLY for a rate-limited cross-check warning ("scip emitted at X, ingested tree at Y — regen scip"), plus propagate `artifact_origin` when present (e.g. `local_partial_xcode_index`).
- **Wiring:** extractor result gains optional `indexed_commit` (plumbed via `ExtractorAttemptResult`); `project_analyze` SETs `p.indexed_commit`, `p.indexed_at` **inside the same durable checkpoint write** for any `symbol_index_*` (generic match, not the hardcoded `"symbol_index_swift"` literal at `:1550`) with status **OK only** (never SKIPPED/MISSING_INPUT). Fallback derivation if plumbing unavailable: `:ExtractorBaseline.indexed_commit` (already persisted, `foundation/baseline.py:66-71`). **Monotonic guard:** a resumed/older run never regresses the field (compare `indexed_at`).
- **Writer outcome is persisted, not just logged** (absence must be payload-diagnosable): `p.indexed_commit_status = "ok" | "unavailable"` + `p.indexed_commit_checked_at`; a decline also lands as `message` on the symbol_index checkpoint (checkpoints already carry error_code/message).
- **Readers:** `get_project_overview`/`list_projects` AND `_read_project_indexed_commit` (run-mode planner!) prefer `p.indexed_commit`. **Dominant vote is dead as a value source**: when `p.indexed_commit` is null → `indexed_commit: null`, `freshness_state="unknown"`, `freshness_reason="indexed_commit_unpopulated_reingest_required"`, and `commits_behind_*` are NEVER computed from the vote. The vote survives only as a clearly-named diagnostic `dominant_symbol_commit` that no lag math consumes (safe-by-omission, not safe-by-annotation).
- **Deploy backfill:** one-time script sets `p.indexed_commit` for all 17 live projects from `:ExtractorBaseline.indexed_commit` (fallback: scip meta where the pairing check passes; else leave null+reason). After backfill the null-path is legacy-only.
- Semantic rows/snippets compute freshness against the project-level commit (not per-symbol `commit_sha`).

## F3 — Registry integrity: validate + repair + surface (symlink-safe)

- **register_project:** accept optional `repo_path` (validated: absolute, exists, dir, has `.git`). Cross-check when both present: `Path(repo_path).resolve()` vs `resolve(parent_mount, relative_path).resolve()` — **symlink-normalized on BOTH sides** (this host mounts through symlinks; naive string equality would false-positive and flood logs). Mismatch → `validation_error`. Requires: `UPSERT_PROJECT` (`cypher.py:278-295`) gains `repo_path` (coalesce-preserving); `register_project` signature; `ProjectInfo` field — in lockstep.
- **Read-time disagreement signal:** `resolve_registered_project` detects tier-1 vs tier-2 resolving to different (resolved) dirs → returns/logs-once a flag; overview sets per-payload `identity_check: "ok" | "repo_path_missing" | "path_mismatch" | "unresolved"`. **When ≠ ok, freshness is NOT computed** (`freshness_state="unknown"`, `freshness_reason="registry_mismatch"`) — never a confident number against a possibly-wrong tree. The existing silent swallow at `project_tools.py:249-250` becomes the `repo_unresolved` reason.
- **Surfacing:** startup sweep + re-check on every `register_project` write; results in a NEW named field `project_integrity_warnings: list[str]` on BOTH `HealthResponse` (`schema.py:99`, extra=forbid — schema change required) and the MCP `palace.health.status` response (`mcp_server.py:198`).
- **Data repair (deploy, gated on before/after sweep):** `tron-kit.repo_path = …/TronKit.Swift`; `hd-wallet-kit.relative_path = hd-wallet-kit-ios`; sweep all 17.

## F4 — Honest lag semantics (no fetch, no rename)

- `freshness_state` values carry the basis in the value itself: `"current_local_tree" | "behind_local_tree" | "unknown"` (a bare "current" reproduces the ambiguity).
- Payload additions: `tree_head`, `origin_checked: false`, `commits_behind_origin: null` — **always present as null** (present-null forces confrontation; absence invites `.get()` fallback).
- `commits_behind_head` is NOT renamed/removed: additive duplicate `commits_behind_local_tree` with the same value; both tri-state (null on unknown). Panel grep: **no in-repo programmatic reader** of `commits_behind_head` (CM bridge/bench clean) — alias needed only for external MCP callers.
- `check_origin` — CUT (see out-of-scope). Follow-up may use `git ls-remote` (no `.git` mutation) if ever needed.

## F5 — Real `git_sha` in health

- Resolve via `run_git(["rev-parse", "--show-toplevel"])`+`["rev-parse","HEAD"]` from the package dir — handles the worktree `.git`-FILE case (live server runs from a detached worktree; naive walk-up would find the wrong root). `max_stdout_lines=2` (PR #507 cap rule).
- One shared resolver for `main.py:173` + `mcp_server.py:508`, **short-TTL cache (60s), not resolve-once** — the deploy reality is hot-patched files in a running worktree; add `git_dirty` (status --porcelain) + `git_sha_resolved_at` so "sha X + dirty" is visible.
- Fallback shape is distinct, not a lookalike: resolution failed → `git_sha: null`, `git_sha_label: <env or "unknown">`, `git_sha_source: "env"|"unknown"`, `git_sha_error: <reason>`. `HealthResponse`/`HealthStatusResponse` schema fields added accordingly.

## Files (lockstep list — panel-completed)

`code/snippet_provider.py`, `code/native_get_code_snippet.py`, `code/find_semantic.py`, `code/snippet_scope.py`, `memory/schema.py` (**ProjectInfo + HealthResponse, extra=forbid — additive fields**), `memory/cypher.py` (UPSERT_PROJECT repo_path; SET_PROJECT_INDEXED_COMMIT; integrity sweep), `memory/project_tools.py`, `project_analyze.py` (generic symbol_index_* hook + durable SET + planner reader), `extractors/foundation/*` (result plumbing), `git/path_resolver.py` (disagreement signal), `memory/constraints.py` (startup sweep hook), `main.py`, `mcp_server.py`, deploy scripts (backfill + repair).

## Test matrix (panel-expanded)

F1: tri-state at FreshnessResult/SnippetResult level; unknown ≠ stale_source (`find_semantic`); `freshness_unknown` status emitted; error payloads carry the three fields; pinned migrations of the 5 existing assertions. F2: writer from tree-HEAD for swift AND one non-Swift path; SKIPPED does not advance; monotonic guard vs resumed run; planner prefers p.indexed_commit; vote never feeds lag; `indexed_commit_status` persisted on decline. F3: symlink fixture (repo_path + mount resolving through symlink to same dir → NO error/warning); mismatch → validation_error; identity_check≠ok suppresses freshness; round-trip of new ProjectInfo fields through model_dump (model_copy bypasses validation — explicit test). F4: null-on-unknown for both lag fields; basis-carrying state values. F5: worktree .git-file fixture; dirty flag; fallback shape distinct.

## Deploy note

Lands on **develop** via PR. Live deploy = operator's call (server currently runs a detached worktree ahead of develop). Independently deployable to the live graph before code: F3 data repair (2 SETs) + F2 backfill (from `:ExtractorBaseline`) — both immediately fix GIM-HDWALLET/GIM-TRON/GIM-EVM-LAG for current consumers.
