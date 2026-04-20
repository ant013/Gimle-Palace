# Test-design discipline fragment — design

**Date:** 2026-04-20
**Slice:** GIM-61 — test-design-discipline shared fragment + Gimle-local addendum.
**Author:** Board (operator-driven).
**Status:** Awaiting formalization (Phase 1.1).
**Branch:** `feature/GIM-61-test-design-discipline-fragment`.
**Predecessors pinned:**
- `develop@144f56a` — GIM-60 retrofit branch-protection JSON + GIM-57 SUPERSEDED banners.
- Submodule `paperclips/fragments/shared@7b9a6ee`.
- Related evidence: GIM-48 postmortem (vector #3 mocked-substrate), GIM-59 `tests/test_startup_hardening.py` regression.

**Scope:** one new shared fragment (project-agnostic, paperclip-aware) + one Gimle-local addendum + `@include` additions in 5 Gimle role files + submodule bump + 11-agent deploy. Zero product code touched.

## 1. Context — what problem this closes

Two independent regressions in four weeks caused by the same root cause — mocked substrate tests passing while real library / driver code path fails:

1. **GIM-48 (2026-04-18)** — mocked `graphiti-core.Graphiti.nodes.*` API surface. `graphiti-core` 0.4.3 has no `.nodes` attribute. All unit tests green; production `/healthz` returned ok because it only did `verify_connectivity()`; every real MCP tool call crashed with `AttributeError`. Reverted same-day after 24h of operator time lost. Three gates failed independently; this slice addresses vector #3 (mocked tests), leaving `qa-evidence-present` check (GIM-57) and admin-bypass closure (GIM-57) as the two closed vectors.
2. **GIM-59 (2026-04-20)** — `tests/test_startup_hardening.py` mocked `neo4j.AsyncDriver` with `AsyncMock` configured for the original `ensure_schema` call path. PE added `await ensure_extractors_schema(driver)` to the lifespan, which uses `async with driver.session() as session:`. The mock wasn't configured as an async context manager, `TypeError: 'coroutine' object does not support the asynchronous context manager protocol`. 4 tests failed on CI. Opus adversarial review timed out (10 min) reviewing code on red CI. PE did not catch locally because they ran scoped `pytest tests/extractors/` not full `pytest tests/`.

These are the **same kind of bug** — a mock that looks like a substrate class but diverges from real behavior. The bug class is not Gimle-specific; it generalizes to any paperclip-consuming project.

**Why a fragment, not a memory-only note:** shared-fragments are normative — included in every relevant agent's bundle, read at every wake. CR checklist items are enforced per-phase. Memory is retrospective (read when an incident happens); fragment is preventative (read every time).

## 2. Goal

After this slice:

- **Every paperclip-consuming project gets a generic test-design rule** in `paperclip-shared-fragments/fragments/test-design-discipline.md`. Medic and any future project consume it unchanged.
- **Gimle has a local addendum** in `paperclips/fragments/local/test-design-gimle.md` with its concrete shared-infra paths + incident refs. Other projects have their own equivalent (or skip).
- **5 Gimle role files** (CR, PE, MCPE, QA, InfraEng) `@include` both fragments, so their deployed bundles carry the rule.
- **CR has explicit enforceable checklist** inside the shared fragment, tied to Phase 1.2 and Phase 3.1.
- **`paperclips/fragments/local/` pattern is established** — first use of the Gimle-local fragment folder. Future Gimle-specific addenda have a documented home.

**Success criterion:** after the deploy,
1. `curl .../api/agents/<code-reviewer-id>/instructions | grep 'Test-design discipline'` → hits both generic + Gimle sections.
2. Same for the 4 engineer roles.
3. `grep 'Test-design' paperclips/dist/*.md` returns exactly 5 files.
4. Retrospective applied to GIM-48 plan + GIM-59 plan: the CR checklist item would have produced a CRITICAL or NUDGE finding. Evidence pasted in PR body.

## 3. Architecture

### 3.1 Shared fragment — generic, project/language agnostic

File: `paperclip-shared-fragments/fragments/test-design-discipline.md` (submodule-level).

Content (~30 LOC):

```markdown
## Test-design discipline (iron rule)

**Substrate** = external library classes (DB drivers, HTTP clients, protocol
libraries), subprocesses, filesystem-as-subject. NOT substrate = your
project's own modules + pure functions + time/random.

### Don't mock substrate in happy-path tests

A type-safe mock (configured to look like an external class) passes
attribute access the real API won't support. Common failure: test passes
against mock, production crashes because mocked methods don't exist in
the installed library version, or a new call path hits a method the mock
never configured.

Use real substrate where feasible: test containers for databases, real
subprocess invocations for CLI tools, temp directories for filesystem,
transport-level mocks for HTTP (not client-class mocks).

**Mock is acceptable** for timeouts, specific exception types, and other
error paths that are hard to reproduce with real substrate.

### Touching shared infrastructure → full test suite, not scoped

When your diff changes entry points (application startup), shared
schema/storage, or framework runners, run the full test suite before
pushing. Scoped runs (single directory, keyword filter) can miss
downstream regressions in tests that depend on the shared code but live
in unrelated directories.

### CR checklist (enforced Phase 1.2 + 3.1)

- [ ] Plan task mocks a substrate class in happy path → CRITICAL finding.
- [ ] Diff adds a new mock of a substrate class → NUDGE; verify a
      real-fixture integration test exists for the same code path.
- [ ] Compliance-comment test output shows scoping (directory filter,
      keyword filter, or similar) when the diff touches shared infrastructure
      → NUDGE, rerun the full suite.

Your project's local test-design addendum lists concrete shared-infra
paths and past incidents.
```

**Language-agnostic.** No Python / pytest / MagicMock / uv tooling refs. "Substrate", "test containers", "transport-level mocks" are generic enough to map onto Go, Ruby, TypeScript, etc. Paperclip specifics kept minimal (mention of Phase 1.2 / Phase 3.1 naming).

### 3.2 Gimle-local addendum — language + project specific

File: `paperclips/fragments/local/test-design-gimle.md` (in Gimle main repo, not submodule).

Content (~20 LOC):

```markdown
## Test-design — Gimle specifics

### Shared-infra paths (touching any = full `uv run pytest tests/`)

- `services/palace-mcp/src/palace_mcp/main.py` (lifespan)
- `services/palace-mcp/src/palace_mcp/memory/` (Cypher + schema)
- `services/palace-mcp/src/palace_mcp/extractors/schema.py` + `runner.py`

### Python+pytest anti-pattern examples

- **Happy-path substrate mock:** `MagicMock(spec=<ExternalClass>)` where
  class is from `graphiti-core`, `neo4j`, `httpx`, `pygit2`. Prefer
  `testcontainers-neo4j`, real `git` subprocess, `tmp_path`,
  `httpx.MockTransport` respectively.
- **Partial async-driver mock:** `AsyncMock()` covering only subset of
  `driver.session()` contract (e.g., without `__aenter__`/`__aexit__`
  when new code adds `async with`). Prefer testcontainers integration.

### Past incidents caught by this rule

- **GIM-48** (2026-04-18) — mocked `Graphiti.nodes.*`; real graphiti-core
  0.4.3 lacks `.nodes`. `docs/postmortems/2026-04-18-GIM-48-n1a-broken-merge.md`.
- **GIM-59** (2026-04-20) — `AsyncMock(driver)` regression in
  `tests/test_startup_hardening.py` after lifespan added
  `ensure_extractors_schema`. Scoped `pytest tests/extractors/` missed it.

See `fragments/shared/fragments/test-design-discipline.md` for generic rule + CR checklist.
```

Gimle-specific: Python+pytest syntax, concrete paths, real GIM-# refs, commit-level evidence. Medic never sees this.

### 3.3 Role file includes

5 role files gain two `@include` lines each (total 10 lines added):

```markdown
<!-- @include fragments/shared/fragments/test-design-discipline.md -->
<!-- @include fragments/local/test-design-gimle.md -->
```

Target files:
- `paperclips/roles/code-reviewer.md` — primary enforcer (Phase 1.2 + 3.1 checklist).
- `paperclips/roles/python-engineer.md` — writes tests under the rule.
- `paperclips/roles/mcp-engineer.md` — same.
- `paperclips/roles/qa-engineer.md` — writes integration tests, likely real-substrate anyway.
- `paperclips/roles/infra-engineer.md` — writes infra tests; benefits from rule.

**Not included** in this slice (could add later if evidence emerges):
- `cto.md` — CTO doesn't write code.
- `technical-writer.md` — docs only.
- `blockchain-engineer.md`, `security-auditor.md`, `research-agent.md` — specialized, low test-writing surface today.
- `opus-architect-reviewer.md` — adversarial backstop; Phase 3.2 runs after CR's mechanical review; CR checklist catches intended cases. Adding Opus would duplicate. If a future regression passes through CR but Opus could have caught with fragment guidance, revisit.

### 3.4 Build + deploy pipeline

**Build:** `paperclips/build.sh` resolver (existing):

```awk
/<!-- @include fragments\/.*\.md -->/ {
  match($0, /fragments\/[^ ]+\.md/)
  frag = substr($0, RSTART + 10, RLENGTH - 10)
  path = frag_dir "/" frag
  # ... reads file at path, inlines content ...
}
```

Universal path matching — `fragments/shared/fragments/<name>.md` and `fragments/local/<name>.md` both resolve. **First actual use of `fragments/local/`** (the directory exists in `paperclips/fragments/local/` but has never been populated). Expected to work without build.sh changes; dry-run verification required (Task 2.8 in plan).

**Deploy:** `paperclips/deploy-agents.sh --local` pushes `paperclips/dist/*.md` bundles to each agent's `AGENTS.md` via paperclip API. No code changes to deploy script.

### 3.5 Order of operations

Submodule PR must merge before Gimle PR can bump pointer:

1. **PR A** in `paperclip-shared-fragments` repo: add `fragments/test-design-discipline.md`. Merge to `main`. Record SHA = `$FRAG_SHA`.
2. **Gimle feature branch** `feature/GIM-61-test-design-discipline-fragment`:
   - Create `paperclips/fragments/local/test-design-gimle.md`.
   - Add 2 `@include` lines to each of 5 role files.
   - Bump submodule `paperclips/fragments/shared` to `$FRAG_SHA`.
   - Run `./paperclips/build.sh` — regenerates `paperclips/dist/*.md`. Commit `dist/` changes.
3. **PR B** in Gimle, merge via standard flow.
4. **Post-merge operator step**: run `./paperclips/deploy-agents.sh --local` — pushes new bundles to 11 agents.
5. **Verification**: API diff on 2 agents (CR + PE) — confirm both sections present.

## 4. Out of scope

1. **Pre-commit / CI lint** for `MagicMock(spec=<substrate>)`. Custom ruff rule or grep hook to catch anti-pattern in diff automatically. MVP relies on CR manual scan. Followup if a third mocked-substrate regression emerges.
2. **OpusArchitectReviewer include.** Opus adversarial at Phase 3.2 = last-mile; CR checklist is primary. Opus would read the same fragment but repeat CR checks — wasted tokens. Add only if evidence of Opus-missed issue appears.
3. **Medic rollout.** Medic consumes the shared fragment as soon as `paperclip-shared-fragments@main` bumps. Medic's own `fragments/local/test-design-medic.md` is their team's followup, not ours.
4. **Language-specific substrate taxonomies.** We list DB / HTTP / subprocess / FS in shared. Specialized categories (gRPC stubs, message brokers, IPC queues) — add as they appear.
5. **Automated full-pytest trigger.** CI could reject PRs that push to shared-infra paths without running full suite — complex to detect reliably; trust CR checklist.
6. **Updating GIM-48 postmortem or GIM-59 documentation.** This slice references them; it doesn't rewrite them.

## 5. Acceptance criteria

- [ ] Shared fragment committed in `paperclip-shared-fragments/fragments/test-design-discipline.md`, ~30 LOC, project-agnostic, no GIM refs, no commit SHAs, no Gimle paths.
- [ ] Gimle-local fragment committed in `paperclips/fragments/local/test-design-gimle.md`, ~20 LOC, Python+pytest specifics + Gimle infra paths + GIM-48 + GIM-59 incident refs.
- [ ] 5 role files have exactly 2 new `@include` lines each (code-reviewer, python-engineer, mcp-engineer, qa-engineer, infra-engineer). No other role files touched.
- [ ] Submodule `paperclips/fragments/shared` bumped to new `main` HEAD containing the generic fragment.
- [ ] `./paperclips/build.sh` run; `paperclips/dist/` updates committed in Gimle PR. 5 agent bundles (matching the 5 `@include`d roles) grow by ~50 LOC of test-design content; other 6 agent bundles unchanged.
- [ ] Dry-run verification of `build.sh` handling `fragments/local/` (expected to work with existing resolver; escalate if breaks).
- [ ] `./paperclips/deploy-agents.sh --local` run post-merge; curl verify on 2 agents shows both test-design sections.
- [ ] Retrospective validation posted in PR body: for each of GIM-48 and GIM-59, show which CR checklist item would have caught it. At least one `CRITICAL` (plan-first) and one `NUDGE` (diff-scan) mapping.
- [ ] PR tagged `micro-slice` (no runtime code, qa-evidence-present waived).
- [ ] CLAUDE.md unchanged — fragment is agent-level behavior, not project-level dev guide content.

## 6. Risks

1. **Over-strict CR** → rejects legitimate edge-case mocks. Mitigation: checklist formulated as NUDGE (not CRITICAL) for Phase 3.1 diff scans; only Phase 1.2 plan-first violations are CRITICAL. CR can override NUDGE with reasoning documented in the compliance comment.
2. **Retrospective mapping weakness.** If GIM-48 / GIM-59 patterns map weakly onto the new checklist text, the rule sounds good but doesn't actually catch bugs in practice. Mitigation: retrospective validation is part of acceptance; Board verifies mapping before merge.
3. **`fragments/local/` first use breaks build.sh.** The resolver is universal, but untested in this subpath. Mitigation: dry-run in Phase 2 Task 2.8 before push — diff the generated `dist/code-reviewer.md` before and after, confirm both fragments appear.
4. **Over-broad substrate definition.** Agents flag too many mocks as violations, friction rises. Mitigation: shared fragment definition is narrow — external library classes + subprocesses + FS-as-subject. Internal modules and pure funcs explicitly excluded.
5. **Submodule bump ordering race.** If PR A in `paperclip-shared-fragments` merges, then another PR merges before Gimle bump, submodule ref drifts. Mitigation: do PR A and PR B in one session, 30-60 minutes apart.

## 7. Decomposition (plan-first ready)

Expected plan: `docs/superpowers/plans/2026-04-20-GIM-61-test-design-discipline-fragment.md` on this same feature branch. CTO swaps `GIM-NN` during Phase 1.1 (no `GIM-NN` placeholders used — branch already named correctly).

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1.1 | 1.1.1 | CTO | Verify spec+plan paths. Reassign CR. |
| 1.2 | 1.2.1 | CodeReviewer | Plan-first review. Verify all §5 acceptance items map to Phase 2 tasks; checklist-in-fragment matches spec §3.1. APPROVE. |
| 2 | 2.1 | TechnicalWriter | Submodule PR A: create `fragments/test-design-discipline.md` in `paperclip-shared-fragments` repo. PR → merge → record `$FRAG_SHA`. |
| 2 | 2.2 | TechnicalWriter | Create `paperclips/fragments/local/test-design-gimle.md` (Gimle-local). |
| 2 | 2.3 | TechnicalWriter | Add 2 `@include` lines to each of 5 role files (code-reviewer, python-engineer, mcp-engineer, qa-engineer, infra-engineer). |
| 2 | 2.4 | InfraEngineer | Bump submodule `paperclips/fragments/shared` to `$FRAG_SHA`. |
| 2 | 2.5 | InfraEngineer | Run `./paperclips/build.sh`. Dry-run check: `grep 'Test-design discipline' paperclips/dist/*.md` → expect 5 files; `grep 'Gimle specifics' paperclips/dist/*.md` → same 5 files. Commit `dist/` changes. |
| 2 | 2.6 | TechnicalWriter | Write retrospective validation: apply CR checklist to GIM-48 plan (vector #3) + GIM-59 plan (`test_startup_hardening.py`). Show which item catches each case. Paste evidence in PR body ready for Phase 4.1. |
| 3.1 | 3.1.1 | CodeReviewer | Mechanical: markdown-lint on new fragments (if lint exists), verify `@include` syntax (lines compile through build.sh without errors), retrospective mapping makes sense. |
| 3.2 | 3.2 | OpusArchitectReviewer | Adversarial: edge cases — over-strict rule producing rejections of legitimate tests; cross-extractor soft contracts at risk; semantic drift between shared fragment and local addendum. |
| 4.1 | 4.1 | QAEngineer | Deploy dry-run to one agent (test bundle locally, not live deploy). Verify fragment content renders correctly. Add `micro-slice` label — qa-evidence-present waived. Compliance-comment text = retrospective validation from Task 2.6. |
| 4.2 | 4.2 | CTO | Squash-merge PR B to develop. |

**Post-merge operator step** (Board, not paperclip): `./paperclips/deploy-agents.sh --local` runs on the iMac, pushes new bundles to 11 agents. Verification via API diff on CR + PE.

## 8. Size estimate

- Shared fragment: ~30 LOC in `paperclip-shared-fragments` repo (separate PR).
- Gimle-local fragment: ~20 LOC.
- 5 role file edits: 10 lines of `@include` additions.
- `dist/*.md` auto-regenerated: +~50 LOC per affected file × 5 files.
- Plan + retrospective text: ~80 LOC.
- 2 PRs (A submodule + B Gimle), 1 deploy step.
- **~2-3 hours agent-time** across 4 phases (smaller than GIM-57 meta-migration — no CI/protection changes; smaller than GIM-59 — no Python code).

## 9. Followups

1. **Pre-commit / ruff custom rule** detecting `MagicMock(spec=<external>)`. Automation; MVP relies on manual CR scan.
2. **OpusArchitectReviewer fragment inclusion** if Opus-missed regression shows up.
3. **Expanded substrate taxonomy** (IPC queues, message brokers) when encountered.
4. **Medic-side `test-design-medic.md` local addendum** when Medic team adopts.
5. **Fragment lint CI** in `paperclip-shared-fragments` repo — markdown syntax, link-check, schema validation. Cross-cutting; not unique to this slice.
