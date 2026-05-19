# GIM-351 Plan - code_ownership native git blame

**Spec:** `docs/superpowers/specs/2026-05-19-GIM-351-code-ownership-pygit2-subprocess.md`
**Branch:** `feature/GIM-351-code-ownership-pygit2-subprocess`
**Base:** `origin/develop@d259c50c` (GIM-356 merged)
**Issue:** GIM-351
**Status:** PR #232 is open; CXCodeReviewer completed mechanical review and requested follow-up fixes before re-review.

## Goal

Replace the `code_ownership` extractor's slow per-file `pygit2.blame` hot path
with native `git blame --line-porcelain`, preserving current ownership behavior
and completing the BitcoinCore reference smoke in <60s.

## Assumptions

- Native `git` is available wherever `palace-mcp` runs for the review/smoke path.
- GIM-356 remains in place and is not reopened here.
- Existing `MailmapResolver` remains the canonical identity mapper.
- No schema, scoring, or unrelated extractor changes are needed.
- Sequential-thinking MCP is not available in this runtime; decomposition is
  based on issue context, codebase-memory graph search, and current source review.

## Implementation Choice

Use a hand-rolled parser around `git blame --line-porcelain`.

Reject a PyPI dependency for this issue:

- Exact `git-blame-parser` was not available on PyPI at
  `https://pypi.org/project/git-blame-parser/` when checked on 2026-05-19.
- Exact `git_blame_parser` appears as a Rust crate, not an installable Python
  package for this service.
- The repo already has a small parser precedent in
  `services/palace-mcp/src/palace_mcp/git/tools.py::parse_blame_porcelain`.

Minimum-code direction:

- Keep `walk_blame(...)` as the extractor-facing API if possible.
- Add private helpers in
  `services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py`.
- Do not introduce new modules unless the file becomes hard to read.

## Codebase Context

- `CodeOwnershipExtractor._run` filters dirty paths via `_filter_dirty` before
  max-file cap, blame, churn, scoring, and write batching.
- `CodeOwnershipExtractor._all_files_in_head` filters tree directories with
  `should_skip_path`.
- `walk_blame` is the hot path: it currently calls `repo.blame(path,
  newest_commit=head_oid)` for every input path.
- `MailmapResolver.from_repo` uses pygit2 mailmap when available and otherwise
  identity-passes. This issue should preserve that behavior.
- Existing tests already cover binary skip, bot filtering, vendor/build target
  filtering, and mailmap behavior; extend them instead of adding broad fixtures.

## Task 1 - Phase 1.2 plan-first review

**Owner:** CXCodeReviewer
**Dependencies:** Phase 1.1 formalization complete.
**Affected files:** this plan and the spec.

- [x] Verify every acceptance criterion maps to a task below.
- [x] Verify the dependency decision is explicit: no PyPI dependency.
- [x] Verify `.mailmap` parity is required before implementation is accepted.
- [x] Verify out-of-scope items are not silently bundled.

**Acceptance criteria:**

- CXCodeReviewer posts plan-first APPROVE or concrete requested changes.
- If approved, issue is handed to CXPythonEngineer for Task 2.

**Verification:**

```bash
test -f docs/superpowers/specs/2026-05-19-GIM-351-code-ownership-pygit2-subprocess.md
test -f docs/superpowers/plans/2026-05-19-GIM-351-code-ownership-pygit2-subprocess.md
rg -n "mailmap|git blame --line-porcelain|No new runtime dependency|Out of scope" \
  docs/superpowers/specs/2026-05-19-GIM-351-code-ownership-pygit2-subprocess.md \
  docs/superpowers/plans/2026-05-19-GIM-351-code-ownership-pygit2-subprocess.md
```

## Task 2 - Native blame parser tests first

**Owner:** CXPythonEngineer
**Dependencies:** Task 1 approved.
**Affected files:**

- `services/palace-mcp/tests/extractors/unit/test_code_ownership_blame_walker.py`

- [x] Add parser-level test for representative `git blame --line-porcelain`
  output with two authors.
- [x] Add `.mailmap` parity test: an alias commit identity must resolve to the
  canonical identity through existing `MailmapResolver`.
- [x] Add pygit2 parity test on the synthetic repo: native and pygit2-backed
  attribution shares match within +/-2 percent.
- [x] Keep existing binary, bot, and vendor/build filtering tests.

**Acceptance criteria:**

- Tests fail on current `develop` because native helper/parser does not exist.
- Tests assert owner identity, line counts or shares, bot filtering, binary skip,
  and mailmap canonicalization.

**Verification:**

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py -q
```

## Task 3 - Replace the blame hot path

**Owner:** CXPythonEngineer
**Dependencies:** Task 2 failing tests.
**Affected files:**

- `services/palace-mcp/src/palace_mcp/extractors/code_ownership/blame_walker.py`

- [x] Add a private subprocess helper that runs:

  ```bash
  git -C <repo.workdir> blame --line-porcelain HEAD -- <path>
  ```

- [x] Use `subprocess.run(..., shell=False, text=True, capture_output=True)`.
- [x] Parse author metadata from porcelain records.
- [x] Aggregate into existing `BlameAttribution` objects.
- [x] Preserve current skip behavior for binary/unblamable paths.
- [x] Keep pygit2 for repository opening and mailmap only; remove
  `repo.blame(...)` from the hot path.

**Acceptance criteria:**

- `walk_blame(...)` returns the same shape as before:
  `tuple[dict[str, dict[str, BlameAttribution]], set[str]]`.
- No new dependency is added to `pyproject.toml` or `uv.lock`.
- Existing scoring/writer code is untouched.

**Verification:**

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py -q
rg -n "repo\.blame|Repository\.blame|git-blame-parser|git_blame_parser" \
  src/palace_mcp/extractors/code_ownership pyproject.toml uv.lock
```

Expected: no `repo.blame` call remains under `code_ownership`; no new
`git-blame-parser` dependency appears.

## Task 4 - Integration parity and no-regression gate

**Owner:** CXPythonEngineer
**Dependencies:** Task 3.
**Affected files:**

- `services/palace-mcp/tests/extractors/integration/test_code_ownership_integration.py`
- Optional: existing fixture files under
  `services/palace-mcp/tests/extractors/fixtures/code-ownership-mini-project/`

- [x] Add or update an integration assertion that owner-share output stays
  within +/-2 percent of current pygit2 behavior on the existing fixture.
- [x] Confirm scenario 5 mailmap dedup still passes.
- [x] Confirm GIM-356 vendor/build filtering test still passes.

**Acceptance criteria:**

- Existing small-repo integration coverage passes.
- Mailmap dedup is explicitly covered.
- Vendor/build filtering is still covered.

**Verification:**

```bash
cd services/palace-mcp
uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py -q
uv run pytest tests/extractors/integration/test_code_ownership_integration.py -q
```

## Task 5 - Implementation PR

**Owner:** CXPythonEngineer
**Dependencies:** Task 4.
**Affected files:** PR to `develop`.

- [x] Run focused lint/test gate.
- [x] Open PR to `develop` from the feature branch.
- [x] PR body references this plan and the spec, includes command output, and
  includes a `## QA Evidence` placeholder.
- [x] Hand off to CXCodeReviewer for mechanical review.

**Acceptance criteria:**

- PR exists against `develop`.
- PR diff only touches code ownership implementation/tests plus this plan/spec
  if needed for checkbox updates.

**Verification:**

```bash
cd services/palace-mcp
uv run ruff check src/palace_mcp/extractors/code_ownership \
  tests/extractors/unit/test_code_ownership_blame_walker.py \
  tests/extractors/integration/test_code_ownership_integration.py
uv run pytest tests/extractors/unit/test_code_ownership_blame_walker.py -q
uv run pytest tests/extractors/integration/test_code_ownership_integration.py -q
gh pr view --json baseRefName,headRefName,title,url
```

## Task 6 - Mechanical review

**Owner:** CXCodeReviewer
**Dependencies:** Task 5.
**Affected files:** PR diff and issue thread.

- [x] Run the project review gate required by current Gimle instructions.
- [x] Confirm no new dependency.
- [x] Confirm no scoring/schema changes.
- [x] Confirm `.mailmap` parity and pygit2 parity are tested.
- [x] Confirm PR body includes QA evidence placeholder and plan/spec links.
- [ ] Approve only with full compliance checklist and command evidence.

**Acceptance criteria:**

- GitHub PR review is APPROVED by CXCodeReviewer.
- Paperclip comment includes the compliance checklist and evidence.

**Verification:**

```bash
gh pr checks <PR>
gh pr diff <PR> --name-only
```

## Task 7 - Adversarial review

**Owner:** CodexArchitectReviewer
**Dependencies:** Task 6.
**Affected files:** PR diff.

- [ ] Check subprocess safety: argv list, `shell=False`, no content logging.
- [ ] Check parser resilience for one-line files, repeated commit metadata,
  binary files, and malformed porcelain records.
- [ ] Check attribution risk: mailmap behavior, bot filtering, timestamp
  handling, and +/-2 percent parity.
- [ ] Check scope discipline: no cache/sampling/schema/scoring changes.

**Acceptance criteria:**

- Findings are posted.
- Any critical or important finding is fixed before QA.

**Verification:**

```bash
gh pr diff <PR>
```

## Task 8 - QA live smoke

**Owner:** CXQAEngineer
**Dependencies:** Task 7.
**Affected paths:** iMac review runtime.

- [ ] Run the BitcoinCore reference smoke.
- [ ] Capture `code_ownership` runtime.
- [ ] Capture a sample of first-party ownership output.
- [ ] Prove `.build/checkouts/` ownership paths are absent.
- [ ] Post evidence authored by CXQAEngineer.

**Acceptance criteria:**

- `code_ownership` completes in <60s on BitcoinCore.
- Smoke produces real first-party ownership rows.
- No `.build/checkouts/` ownership rows are present.

**Verification:**

```bash
docker compose --profile review up -d --force-recreate palace-mcp
./scripts/ingest_swift_kit.sh bitcoin-core
```

## Task 9 - Merge gate

**Owner:** CXCTO
**Dependencies:** Task 8.
**Affected paths:** PR to `develop`, Paperclip issue.

- [ ] Verify CI green.
- [ ] Verify CXCodeReviewer APPROVED.
- [ ] Verify branch merge state is clean.
- [ ] Verify no conflict markers in diff.
- [ ] Verify PR references this plan file and the spec.
- [ ] Verify QA evidence is present.
- [ ] Merge to `develop`; close GIM-351.

**Acceptance criteria:**

- PR is merged to `develop`.
- GIM-351 is closed with evidence.

**Verification:**

```bash
gh pr checks <PR>
gh pr view <PR> --json reviewDecision,mergeStateStatus,baseRefName,headRefName
gh pr diff <PR> | grep -E '^(<<<<<<<|=======|>>>>>>>)' || true
```
