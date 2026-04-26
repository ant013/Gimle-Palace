---
slug: GIM-96-palace-prime-foundation
spec: docs/superpowers/specs/2026-04-26-GIM-95a-palace-prime-foundation.md (rev3, commit dd5b122)
branch: feature/GIM-95a-palace-prime-foundation
predecessor: a82c549 (develop tip after GIM-95 merge)
date: 2026-04-26
owner: PythonEngineer (Tasks 1–12), QAEngineer (Task 13)
reviewers: CodeReviewer (Phase 3.1), OpusArchitectReviewer (Phase 3.2)
paperclip_issue: 96
---

# Plan — GIM-96 `palace.memory.prime` foundation

Universal core + operator role end-to-end. 13 tasks on `feature/GIM-95a-palace-prime-foundation`.

Spec slug is GIM-95a (split from original GIM-95 scope); paperclip issue is GIM-96. Branch retains spec slug per frontmatter decision.

## Hard dependencies (verified at a82c549)

- `palace.memory.decide` (GIM-95) — merged at a82c549. `:Decision` nodes now writable.
- `palace.memory.lookup` — live on develop.
- `palace.memory.health` — live on develop.
- `palace.code.*` — live on develop (post-GIM-89 fix).

## Codebase context (verified at a82c549)

- **`_tool()` wrapper**: `mcp_server.py` — `_registered_tool_names` + Pattern #21 dedup via `assert_unique_tool_names`.
- **Globals**: `mcp_server.py` — `_driver`, `_graphiti`, `_settings`, `_default_group_id`.
- **`palace.memory.lookup`**: read-side tool for `:Decision` and other entity types — prime calls this to fetch recent decisions for slice.
- **`palace.memory.health`**: health summary — prime includes health output in universal core.
- **Git subprocess pattern**: `services/palace-mcp/src/palace_mcp/git/command.py` — `SAFE_ENV` dict at line 25 provides env lockdown (`GIT_CONFIG_NOSYSTEM=1`, `PATH=/usr/bin:/bin`). Note: `command.py` uses synchronous `subprocess.Popen`; for branch detection, import and reuse `SAFE_ENV` but use `asyncio.create_subprocess_exec` (not the sync pattern).
- **Settings**: `services/palace-mcp/src/palace_mcp/config.py` — class `Settings(BaseSettings)`. Add `palace_git_workspace: str = "/repos/gimle"`.
- **Fragments submodule**: `paperclips/fragments/shared` → `paperclip-shared-fragments` repo. Contains `compliance-enforcement.md`. New `role-prime/` dir needed.

## Task 1 — Module scaffold `memory/prime/`

**Owner**: PythonEngineer
**Dependencies**: none
**Affected files**:
- NEW: `services/palace-mcp/src/palace_mcp/memory/prime/__init__.py`
- NEW: `services/palace-mcp/src/palace_mcp/memory/prime/core.py`
- NEW: `services/palace-mcp/src/palace_mcp/memory/prime/roles.py`
- NEW: `services/palace-mcp/src/palace_mcp/memory/prime/deps.py`

**What to do**:

1. Create module directory with `__init__.py` re-exporting public API.
2. `deps.py`: `PrimingDeps` dataclass wrapping graphiti, driver, settings, default_group_id (per spec § PrimingDeps). **No `paperclip_client` field** — paperclip API integration deferred to GIM-95b. Also add `role_prime_dir: Path` derived from `Path(settings.palace_git_workspace) / "paperclips/fragments/shared/fragments/role-prime"`.
3. `core.py`: universal core renderer function signature (implementation in Task 3).
4. `roles.py`: role dispatcher function signature (implementation in Task 4).

**Acceptance**: module importable, `PrimingDeps` instantiable with mock values.

## Task 2 — Branch → slice_id auto-detection

**Owner**: PythonEngineer
**Dependencies**: Task 1
**Affected files**:
- EDIT: `services/palace-mcp/src/palace_mcp/memory/prime/core.py`

**What to do**:

1. `async def detect_slice_id(workspace: str) -> str | None` — run `git rev-parse --abbrev-ref HEAD` via `asyncio.create_subprocess_exec` with:
   - `cwd=workspace` (from `Settings.palace_git_workspace`)
   - `env={"GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin"}`
   - `timeout=2` seconds
2. Parse branch name: `feature/GIM-N-...` → `"GIM-N"`. Non-matching / detached HEAD → `None`.
3. No blocking subprocess calls.

**Acceptance**: returns correct slice_id for feature branches; returns `None` for detached HEAD or non-standard branches.

## Task 3 — Universal core renderer

**Owner**: PythonEngineer
**Dependencies**: Task 1, Task 2
**Affected files**:
- EDIT: `services/palace-mcp/src/palace_mcp/memory/prime/core.py`

**What to do**:

1. `async def render_universal_core(deps: PrimingDeps, role: str, slice_id: str | None) -> str` assembles:
   - Slice header (branch, slice_id, role)
   - Standing instruction (hardcoded ≤ 4 lines per spec § untrusted content policy)
   - `:Decision` lookup — call `palace.memory.lookup(entity_type="Decision", filters={"slice_ref": slice_id})` internally (or equivalent graphiti query). Wrap each decision body in `<untrusted-decision uuid=... claimed-maker=... confidence=... decided-at=...>` band + triple-backtick fence.
   - Health summary — call health function internally (or summarize key metrics).
2. If `slice_id` is `None`, skip slice-specific decisions (return "no slice context" fallback).
3. Target: ≤ 600 tokens for universal core.

**Acceptance**: renders correct universal core with and without slice context; decisions wrapped in untrusted band; health included.

## Task 4 — Role extras dispatcher

**Owner**: PythonEngineer
**Dependencies**: Task 1
**Affected files**:
- EDIT: `services/palace-mcp/src/palace_mcp/memory/prime/roles.py`

**What to do**:

1. `async def render_role_extras(role: str, deps: PrimingDeps) -> str` — reads `role-prime/{role}.md` from `deps.role_prime_dir` at runtime.
2. For `role="operator"`: substitute `{{ placeholders }}` with runtime values:
   - `{{ recent_develop_commits }}` — fetch via `asyncio.create_subprocess_exec` running `git log --oneline -5 origin/develop` with `SAFE_ENV` from `git/command.py`, `cwd=settings.palace_git_workspace`.
   - `{{ in_progress_slices }}` / `{{ backlog_high_priority }}` — **v1: static instructions** ("Run `palace.memory.lookup(entity_type='Issue', filters={...})` to see in-flight slices"). Paperclip API integration deferred to GIM-95b.
   - `{{ paperclip_api_url }}`, `{{ git_workspace }}` — from `deps.settings`.
3. For other 5 roles (cto/codereviewer/pythonengineer/opusarchitectreviewer/qaengineer): return stub content with minimal useful-tools list (5-7 lines per spec Q3 verdict).
4. Unknown role → raise ValueError.
5. Fragment path: `paperclips/fragments/shared/fragments/role-prime/{role}.md` (relative to repo root, via settings or env).

**Acceptance**: operator role returns full content with substituted placeholders; other roles return stubs; unknown role raises error.

## Task 5 — Token budget enforcement

**Owner**: PythonEngineer
**Dependencies**: Task 3, Task 4
**Affected files**:
- EDIT: `services/palace-mcp/src/palace_mcp/memory/prime/core.py` (or new `budget.py`)

**What to do**:

1. `estimate_tokens(text: str) -> int` — `len(text) // 4` approximation.
2. Budget cap: 2000 tokens for v1.
3. If `universal_core + role_extras > budget`: tail-truncate role_extras. Universal core + standing instruction always stay intact.
4. Add truncation marker if content was cut.

**Acceptance**: `estimate_tokens(content) ≤ 2000` for all roles; universal core never truncated.

## Task 6 — MCP tool registration `palace.memory.prime`

**Owner**: PythonEngineer
**Dependencies**: Tasks 1–5
**Affected files**:
- EDIT: `services/palace-mcp/src/palace_mcp/mcp_server.py`

**What to do**:

1. Register `palace.memory.prime` tool with Pattern #21 dedup + `assert_unique_tool_names`.
2. Args: `role: str` (required), `slice_id: str | None` (optional, auto-detected if absent), `budget: int = 2000` (token cap).
3. Validate role against allowed set: `{operator, cto, codereviewer, pythonengineer, opusarchitectreviewer, qaengineer}`.
4. Compose: `render_universal_core() + render_role_extras()` → apply budget → return `{"content": ..., "role": ..., "slice_id": ..., "tokens_estimated": ...}`.
5. Error envelope: `{"ok": false, "error_code": "invalid_role|...", "message": ...}`.

**Acceptance**: tool callable via MCP; returns correct response shape; Pattern #21 dedup passes.

## Task 7 — Standing instruction in `compliance-enforcement.md`

**Owner**: PythonEngineer
**Dependencies**: none (cross-repo: paperclip-shared-fragments)
**Affected files**:
- EDIT: `paperclip-shared-fragments/fragments/compliance-enforcement.md`

**What to do**:

Append "Untrusted content policy" section (≤ 4 lines per spec). Verify post-edit file stays under GIM-94 ≤ 2 KB density cap.

**Cross-repo checklist** (applies to Tasks 7 and 8 — batch into one PR):
1. `cd paperclips/fragments/shared` (submodule root).
2. Create branch `feature/GIM-96-role-prime` in `paperclip-shared-fragments`.
3. Make edits (Task 7 + Task 8 files).
4. Commit, push, open PR in `paperclip-shared-fragments` repo per GIM-94 D3 rule.
5. After merge, return to gimle-palace repo.
6. `git add paperclips/fragments/shared` to bump submodule pointer.
7. Commit submodule pointer bump on `feature/GIM-95a-palace-prime-foundation`.

**Acceptance**: section present; file ≤ 2 KB; submodule pointer bumped in gimle-palace.

## Task 8 — Role-prime markdown files in fragments submodule

**Owner**: PythonEngineer
**Dependencies**: none (cross-repo: paperclip-shared-fragments)
**Affected files**:
- NEW: `paperclip-shared-fragments/fragments/role-prime/operator.md` (full content)
- NEW: `paperclip-shared-fragments/fragments/role-prime/cto.md` (stub)
- NEW: `paperclip-shared-fragments/fragments/role-prime/codereviewer.md` (stub)
- NEW: `paperclip-shared-fragments/fragments/role-prime/pythonengineer.md` (stub)
- NEW: `paperclip-shared-fragments/fragments/role-prime/opusarchitectreviewer.md` (stub)
- NEW: `paperclip-shared-fragments/fragments/role-prime/qaengineer.md` (stub)

**What to do**:

1. Create `operator.md` with full content per spec § Operator role context — paperclip API patterns, git workspace, MCP tools, `{{ placeholder }}` syntax.
2. Create 5 stub files with minimal useful-tools list (5-7 lines per spec Q3 verdict).
3. PR + merge in paperclip-shared-fragments per GIM-94 D3 rule; bump submodule pointer in gimle-palace.

**Acceptance**: all 6 files present; operator has full content with placeholders; stubs have useful-tools.

## Task 9 — `.claude/commands/prime.md` slash command

**Owner**: PythonEngineer
**Dependencies**: Task 6
**Affected files**:
- NEW: `.claude/commands/prime.md`

**What to do**:

Per spec § Task 9 — template with `$ARGUMENTS` parsing: first word = role, optional second word = slice_id. Include validation against allowed roles and usage hint.

**Acceptance**: file present at repo root `.claude/commands/`; content matches spec § Task 9 template verbatim; file contains `$ARGUMENTS` parsing for role + optional slice_id.

## Task 10 — Operator runbook

**Owner**: PythonEngineer
**Dependencies**: Task 9
**Affected files**:
- NEW: `docs/runbooks/operator-claude-code-setup.md`

**What to do**:

Document: SSH tunnel setup, MCP server config for Claude Code, `/prime` usage examples. Per spec.

**Acceptance**: runbook present; covers SSH tunnel + MCP config + /prime usage.

## Task 11 — Unit tests

**Owner**: PythonEngineer
**Dependencies**: Tasks 1–5
**Affected files**:
- NEW: `services/palace-mcp/tests/memory/prime/test_core.py`
- NEW: `services/palace-mcp/tests/memory/prime/test_roles.py`
- NEW: `services/palace-mcp/tests/memory/prime/test_budget.py`

**What to do**:

1. Mock graphiti, paperclip, git subprocess.
2. Test universal core with/without slice_id.
3. Test operator role rendering with placeholder substitution.
4. Test stub rendering for other roles.
5. Test token budget enforcement and truncation.
6. Test untrusted-decision band wrapping.
7. Test branch detection (feature branch, detached HEAD, non-standard).

**Acceptance**: `uv run pytest services/palace-mcp/tests/memory/prime/` green; coverage for all components.

## Task 12 — Integration test (MCP wire-contract)

**Owner**: PythonEngineer
**Dependencies**: Task 6
**Affected files**:
- NEW: `services/palace-mcp/tests/integration/test_prime_wire_contract.py`

**What to do**:

Per GIM-91 wire-contract rule: real MCP HTTP+SSE call to `palace.memory.prime(role="operator")`. Validate response shape, content field presence, token estimate ≤ 2000.

**Acceptance**: integration test passes against running palace-mcp; wire-contract criteria met.

## Task 13 — QA Phase 4.1 live smoke

**Owner**: QAEngineer
**Dependencies**: Tasks 1–12
**Affected files**: none (runtime verification)

**What to do**:

1. On iMac, start `docker compose --profile review up -d`.
2. Run `/prime operator` via Claude Code with at least one `:Decision` recorded for the current slice.
3. Verify: response includes universal core + operator extras + untrusted-decision bands.
4. Verify: `estimate_tokens(content) ≤ 2000`.
5. Run `/prime cto` — verify stub response.
6. Direct Cypher invariant check: `MATCH (d:Decision) WHERE d.group_id = "project/gimle" RETURN count(d)` ≥ 1.

**Acceptance**: per spec § Acceptance (13 criteria); evidence comment authored by QAEngineer.

## Commit grouping guidance

- Tasks 1–2: scaffold + branch detection (1 commit)
- Task 3: universal core renderer (1 commit)
- Tasks 4–5: role dispatcher + budget enforcement (1 commit)
- Task 6: MCP tool registration (1 commit)
- Tasks 7–8: cross-repo submodule PR (separate repo commits + submodule pointer bump)
- Tasks 9–10: slash command + runbook (1 commit)
- Tasks 11–12: unit + integration tests (1 commit)

## Phase sequence

| Phase | Agent | What |
|---|---|---|
| 1.1 Formalize | CTO | This plan (verify paths, rebase, hand to CR) |
| 1.2 Plan-first review | CodeReviewer | Validate all 13 tasks have concrete test + impl + commit criteria |
| 2 Implement | PythonEngineer | TDD Tasks 1–12 on feature branch |
| 3.1 Mechanical review | CodeReviewer | `ruff check + mypy + pytest` output in APPROVE |
| 3.2 Adversarial review | OpusArchitectReviewer | Poke holes on architecture |
| 4.1 Live smoke | QAEngineer | Task 13 on iMac |
| 4.2 Merge | CTO | Squash-merge → develop; chain-trigger GIM-97 |
