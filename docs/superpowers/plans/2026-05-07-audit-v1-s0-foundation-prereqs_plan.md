# Audit-V1 S0 — Foundation Prerequisites — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:test-driven-development`. Steps use checkbox (`- [ ]`) syntax. Atomic-handoff discipline mandatory: `paperclips/fragments/profiles/handoff.md`.

**Slice:** S0 of Audit-V1 sprint sequence (rev3).
**Spec:** `docs/superpowers/specs/2026-05-07-audit-v1-s0-foundation-prereqs_spec.md`.
**Source branch:** `feature/GIM-228-audit-v1-s0-foundation-prereqs` cut from `origin/develop`.
**Target branch:** `develop`. Squash-merge on APPROVE + QA evidence.
**Team:** Claude. Phase chain: CTO → CR (plan-first) → PythonEngineer → CR (mechanical) → OpusArchitectReviewer → QAEngineer → CTO merge.

S0 is **three parallelisable sub-slices** (S0.1, S0.2, S0.3). Operator may
choose either:
- **(a)** single-PR / single-branch carrying all three — simpler review,
  one issue chain (default for v1).
- **(b)** three independent PRs / branches — maximum parallel throughput
  if 3 different engineers are available, but risks file-overlap on
  registry lines (mitigated by additive-only edits per parallelisation
  rules §5).

This plan assumes **(a)**: one branch, three commits (one per sub-slice),
single PR. CTO swaps if a 2nd Claude engineer is free.

---

## Phase 0 — Prereqs (Board)

### Step 0.1: Resolve issue number + open branch

**Owner:** CTO.

- [ ] Open paperclip issue titled `Audit-V1 S0 — Foundation Prerequisites`.
- [x] Body = link to spec + this plan.
- [x] GIM-NN → GIM-228 edit-pass applied to spec, plan, and branch name.
- [ ] Reassign to CodeReviewer for plan-first review.

**Acceptance:** issue exists, key substituted, CR is assignee.

---

## Phase 1 — Plan-first review (CodeReviewer)

### Step 1.1: Validate plan against spec

**Owner:** CodeReviewer.

- [ ] Verify spec §3 sub-slices map 1-to-1 to Phase 2.{1,2,3} below.
- [ ] Verify each test step has a concrete file path + assertion.
- [ ] Verify acceptance criteria are measurable.
- [ ] Print full review checklist with evidence per
      `feedback_anti_rubber_stamp.md`.
- [ ] On APPROVE: paperclip APPROVE comment + `gh pr review --approve`.
      Reassign to PythonEngineer.

**Acceptance:** APPROVE comment posted; assignee = PythonEngineer.

---

## Phase 2 — Implementation (PythonEngineer)

### Phase 2.1 — Sub-slice S0.1 (IngestRun schema unification)

#### Step 2.1.1: Failing tests first (TDD)

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/tests/extractors/unit/test_ingest_run_schema.py` (new)
- `services/palace-mcp/tests/integration/test_ingest_run_unification.py` (new)

- [ ] Unit: `test_path_a_creates_with_canonical_fields` — call
      `extractors/cypher.py::create_ingest_run(...)` with `source=
      "extractor.hotspot"`, `group_id="project/gimle"`. Read back the
      node; assert `extractor_name == "hotspot"`, `project == "gimle"`.
      Test FAILS until step 2.1.2.
- [ ] Unit: `test_path_b_unchanged` — Path B (`foundation/checkpoint.py`)
      already writes canonical fields; lock that in.
- [ ] Integration: `test_migration_idempotent` — seed 3 Path A rows
      with NULL `extractor_name`; run migration; assert all 3 have
      correct `extractor_name + project`. Re-run — zero net writes.
- [ ] Integration: `test_audit_discovery_sees_both_paths` — seed mixed
      Path A + Path B IngestRuns; query
      `MATCH (r:IngestRun) WHERE r.extractor_name IS NOT NULL` returns
      ALL of them.
- [ ] `uv run pytest services/palace-mcp/tests/extractors/unit/test_ingest_run_schema.py services/palace-mcp/tests/integration/test_ingest_run_unification.py` — confirms 4 tests RED.

**Acceptance:** 4 RED tests, no compilation errors, no other test broken.

#### Step 2.1.2: Make tests green

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/src/palace_mcp/extractors/cypher.py`
- `services/palace-mcp/src/palace_mcp/extractors/runner.py`
- `services/palace-mcp/src/palace_mcp/migrations/2026_05_xx_unify_ingest_run.py` (new)

- [ ] Extend `cypher.py::CREATE_INGEST_RUN` Cypher to write
      `extractor_name` and `project`. Derive `extractor_name` from
      `source` field (strip `extractor.` prefix). Derive `project` from
      `group_id` field (strip `project/` prefix).
- [ ] Update `runner.py::run_extractor()` to pass both fields explicitly
      (don't rely on cypher.py to parse — explicit > implicit).
- [ ] Implement migration as a standalone module (rev4 — was incorrectly
      proposed as `palace_mcp.cli` subcommand which doesn't exist on
      develop): `services/palace-mcp/src/palace_mcp/migrations/2026_05_xx_unify_ingest_run.py`.
      Idempotent Cypher per spec §4. Runnable via
      `python -m palace_mcp.migrations.2026_05_xx_unify_ingest_run`.
- [ ] `uv run pytest services/palace-mcp/tests/extractors/unit/test_ingest_run_schema.py services/palace-mcp/tests/integration/test_ingest_run_unification.py` — 4 GREEN.
- [ ] Run full extractor suite to ensure no regression: `uv run pytest services/palace-mcp/tests/extractors/`.

**Acceptance:** 4 new tests GREEN; existing extractor suite stays GREEN.

#### Step 2.1.3: Commit S0.1

- [ ] `git add` only files in scope.
- [ ] Commit: `feat(GIM-228): unify IngestRun schema across Path A/B (S0.1)`.

---

### Phase 2.2 — Sub-slice S0.2 (3 NEW composite MCP tools — rev4)

> **rev4 correction**: scope reduced from 5 tools → 3.
> `find_owners` already on develop (mcp_server.py:850, GIM-216 `2d6e6c1`).
> `find_version_skew` already on develop (mcp_server.py:790, GIM-218 `603c840`).

#### Step 2.2.1: Failing tests first

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/tests/code/test_composite_find_dead_symbols.py` (new)
- `services/palace-mcp/tests/code/test_composite_find_public_api.py` (new)
- `services/palace-mcp/tests/code/test_composite_find_cross_module_contracts.py` (new)
- `services/palace-mcp/tests/integration/test_audit_composite_e2e.py` (new)

- [ ] For each of 3 tools, create unit test file with 3 cases:
  - empty-graph → returns empty `[]`
  - seeded fixture → returns expected items
  - project-not-registered → raises `ProjectNotRegisteredError`
- [ ] Integration test: seed graph with 1 row per extractor across all 3
      new tools (plus existing 6 already-registered tools), call the 3
      new tools, assert non-empty results with expected shape.
- [ ] `uv run pytest services/palace-mcp/tests/code/ services/palace-mcp/tests/integration/test_audit_composite_e2e.py` — confirms 9 RED tests (3 tools × 3 cases) + 1 integration test.

**Acceptance:** 10 RED tests (rev4: was incorrectly stated as "16").

#### Step 2.2.2: Implement composite tools

**Owner:** PythonEngineer.
**Files:**
- 3 new per-tool modules under `services/palace-mcp/src/palace_mcp/code/`
  (Pattern B — matching existing `find_hotspots.py` / `find_owners.py` /
  `list_functions.py`): `find_dead_symbols.py`, `find_public_api.py`,
  `find_cross_module_contracts.py`.
- 3 new Pydantic response models alongside their tool registration:
  `DeadSymbolList`, `PublicApiList`, `ContractDriftList`.
- `services/palace-mcp/src/palace_mcp/mcp_server.py` — register
  3 new tools on the FastMCP instance (follow existing pattern at
  lines 797 / 824 / 850).
- (test file additions from 2.2.1).

- [ ] Implement each function: thin wrapper around extractor's
      published Cypher. The 3 underlying extractors already exist on
      develop:
      `dead_symbol_binary_surface` (GIM-193 `52cfec5`),
      `public_api_surface` (GIM-190 `2a96786`),
      `cross_module_contract` (GIM-192 `05fe1b7`).
- [ ] Each tool calls `assert_project_registered(project)` first.
- [ ] Pydantic models include `provenance: IngestRunRef` field
      (run_id + completed_at) so audit renderer can cite source.
- [ ] Verify MCP tool registration: `uv run python -c "from palace_mcp.mcp_server import server; print([t.name for t in server.list_tools()])"` includes 3 new names.
- [ ] `uv run pytest services/palace-mcp/tests/code/ services/palace-mcp/tests/integration/test_audit_composite_e2e.py` — 10 GREEN.

**Acceptance:** 10 tests GREEN; all 3 NEW tools listed in MCP server
tool inventory (alongside the 6 already-existing palace.code.* tools).

#### Step 2.2.3: Commit S0.2

- [ ] Commit: `feat(GIM-228): add 3 composite MCP tools for audit (S0.2 — rev4 scope)`.

---

### Phase 2.3 — Sub-slice S0.3 (audit-mode prompt fragment) — rev4-corrected

> **rev4 corrections** (per CR-C2 / OPUS-C2):
> - Real fragment-include syntax is `<!-- @include fragments/<path>.md -->`
>   (with `@`), per `paperclips/build.sh` HEAD on develop.
> - Role file names are kebab-case, NOT camelCase.
> - CX-side `cx-security-auditor.md` / `cx-blockchain-engineer.md` do not
>   exist on develop yet — those are E6 deliverables. S0.3 ships only
>   the Claude side; CX-side audit-mode markers added during E6 file creation.

#### Step 2.3.1: Author audit-mode fragment

**Owner:** PythonEngineer (low Python content; mostly markdown).
**Files:**
- `paperclips/fragments/local/audit-mode.md` (new local fragment;
  located under `local/` because it is project-specific to the audit
  workflow, not a shared cross-project concept).

- [ ] Author the canonical `## Audit mode` section per spec §3.3.
      Include: input format spec, output format spec, severity-grading
      table, hard "no invented findings" rule, example output.
- [ ] Include block at top: "This fragment is included by 3 audit-
      participating role files — keep changes here, not in individual
      role files."

**Acceptance:** fragment file exists at `paperclips/fragments/local/audit-mode.md`;
reviewable as standalone markdown.

#### Step 2.3.2: Wire fragment into 3 Claude role files (kebab-case names)

**Owner:** PythonEngineer.
**Files** (verified against `git ls-tree origin/develop paperclips/roles/`):
- `paperclips/roles/opus-architect-reviewer.md`
- `paperclips/roles/security-auditor.md`
- `paperclips/roles/blockchain-engineer.md`

- [ ] Append `<!-- @include fragments/local/audit-mode.md -->` at an
      appropriate location in each role file body (after the `---`
      YAML frontmatter, in a section thematically aligned with audit
      participation — typically after the role's "Responsibilities"
      section; final placement decided per-file).
- [ ] Run `bash paperclips/build.sh --target claude` to render
      `paperclips/dist/<role>.md` for the 3 affected files.
- [ ] Diff rendered output: `git diff paperclips/dist/` should show
      the audit-mode fragment expanded inline at expected position;
      nothing else changed.

**Acceptance:** rendered `paperclips/dist/opus-architect-reviewer.md`,
`paperclips/dist/security-auditor.md`, and
`paperclips/dist/blockchain-engineer.md` each contain the
`## Audit mode` section verbatim from the fragment file.

#### Step 2.3.3: CX-side mirror — DEFERRED to E6

- [ ] Document in PR body: "CX-side audit-mode wiring is deferred to E6.
      `cx-security-auditor.md` and `cx-blockchain-engineer.md` do not
      exist on develop yet (only Claude side). E6 spec
      (`2026-05-07-cx-team-hire-blockchain-security-pyorch_*.md`) must
      include the `<!-- @include fragments/local/audit-mode.md -->`
      marker at file creation time."
- [ ] No CX file edits in S0.3.

**Acceptance:** PR body explicit about CX-side deferral.

#### Step 2.3.4: Commit S0.3

- [ ] Commit: `feat(GIM-228): add audit-mode fragment + wire to 3 Claude role files (S0.3)`.

---

### Step 2.4: Push branch

- [ ] `git push -u origin feature/GIM-228-audit-v1-s0-foundation-prereqs`.
- [ ] Open PR titled `feat(GIM-228): Audit-V1 S0 foundation prerequisites`.
- [ ] PR body includes:
  - "Closes GIM-228"
  - bullet list mapping commits → S0.1/S0.2/S0.3
  - QA Evidence section will be filled in Phase 4.

**Acceptance:** PR exists; CI runs `lint`, `typecheck`, `test`,
`docker-build`, `qa-evidence-present`.

- [ ] Reassign issue to CodeReviewer for Phase 3.1.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical review (CodeReviewer)

**Owner:** CodeReviewer.
**Required action per `feedback_cr_phase31_ci_verification.md`**:

- [ ] Paste full output of: `gh pr checks <PR-number>` — must show all
      5 required checks GREEN.
- [ ] Paste output of: `uv run ruff check && uv run mypy services/palace-mcp/src/ && uv run pytest services/palace-mcp/tests/` — all GREEN.
- [ ] Verify diff covers ALL files listed in plan §"Files in scope" of
      spec — no silent scope reduction (per
      `feedback_silent_scope_reduction.md`).
- [ ] Audit-mode fragment diff'd against itself in 3 rendered Claude
      role files (`dist/opus-architect-reviewer.md`,
      `dist/security-auditor.md`, `dist/blockchain-engineer.md`):
      same content, no drift. CX-side deferred to E6.

**Acceptance:** APPROVE on paperclip + `gh pr review --approve`. Reassign
to OpusArchitectReviewer.

### Phase 3.2 — Adversarial review (OpusArchitectReviewer)

**Owner:** OpusArchitectReviewer.

- [ ] Probe: does the IngestRun migration handle the case where a Path A
      row was created with `source` NOT starting with `extractor.`
      (e.g., paperclip ingest)?
- [ ] Probe: does composite tool `find_owners` correctly handle an
      empty `:Owner` graph (no extractor has run yet)?
- [ ] Probe: do the 3 rendered Claude audit-mode sections actually
      contain identical text, or did inter-role divergence sneak in?
- [ ] Probe: any of the 3 new composite tools accidentally expose
      data outside the requested project scope?

**Acceptance:** APPROVE / NUDGE / BLOCK comment. If NUDGE/BLOCK, return
to PE for fix; loop until APPROVE.

---

## Phase 4 — QA evidence (QAEngineer on iMac)

### Step 4.1: Live smoke

**Owner:** QAEngineer.

- [ ] SSH iMac.
- [ ] FF-pull develop on `/Users/Shared/Ios/Gimle-Palace`. Pull PR
      branch into a temp worktree.
- [ ] Build palace-mcp container: `docker compose --profile review build`.
- [ ] Up: `docker compose --profile review up -d`.
- [ ] Run migration (rev4 — standalone module, NOT cli.py):
      `docker compose exec palace-mcp python -m palace_mcp.migrations.2026_05_xx_unify_ingest_run`.
      Capture stdout; expect `migrated N rows` (N depends on existing data).
- [ ] Re-run migration; expect `migrated 0 rows` (idempotency check).
- [ ] Live MCP call all 3 NEW composite tools (rev4 — was 5; 2 already on develop) via `npx @modelcontextprotocol/inspector` against the iMac MCP socket. Capture each response.
- [ ] Cypher direct check: `MATCH (r:IngestRun) WHERE r.extractor_name IS NULL RETURN count(r)` → expect 0.
- [ ] Render audit-mode for 3 Claude roles: `bash paperclips/build.sh --target claude` then `grep -c "## Audit mode" paperclips/dist/{opus-architect-reviewer,security-auditor,blockchain-engineer}.md` — expect 1 each.

### Step 4.2: Author QA Evidence comment

**Owner:** QAEngineer.

- [ ] Post comment on paperclip issue + edit PR body to include
      `## QA Evidence` section per
      `paperclips/fragments/profiles/qa-evidence-format.md`. Section
      MUST cite:
  - SHA of branch tip used for evidence.
  - All 4 live commands run + their outputs.
  - Idempotency confirmation.
  - "no fabricated evidence" affirmation per
    `feedback_pe_qa_evidence_fabrication.md`.

**Acceptance:** QA Evidence in PR body satisfies
`qa-evidence-present` CI check; `gh pr checks` GREEN; reassign to CTO.

---

## Phase 5 — Merge (CTO)

**Owner:** CTO.

- [ ] Verify all 5 required CI checks GREEN.
- [ ] Verify CR APPROVE + Opus APPROVE + QA Evidence present.
- [ ] Squash-merge PR.
- [ ] Update `docs/roadmap.md` Audit-V1 row S0: 📋 → ✅ with merge SHA.
- [ ] iMac deploy: `bash paperclips/scripts/imac-deploy.sh` (post-merge
      until C5 auto-deploy lands).
- [ ] Close paperclip issue with merge SHA + roadmap update note.

**Acceptance:** S0 row ✅ on roadmap; CI on develop tip GREEN; iMac
runs `palace.code.find_owners` etc. against live data successfully.

---

## Definition-of-Done checklist

- [ ] S0.1 — IngestRun schema unified; migration idempotent; runnable
      via `python -m palace_mcp.migrations.2026_05_xx_unify_ingest_run`.
- [ ] S0.2 — **3 NEW composite tools** live (rev4 — `find_dead_symbols`,
      `find_public_api`, `find_cross_module_contracts`); all return
      Pydantic-typed responses. Existing `find_owners` + `find_version_skew`
      untouched.
- [ ] S0.3 — `## Audit mode` fragment at
      `paperclips/fragments/local/audit-mode.md` included via
      `<!-- @include fragments/local/audit-mode.md -->` into 3 Claude
      role files (kebab-case). CX-side deferred to E6.
- [ ] All tests GREEN locally + on iMac.
- [ ] PR squash-merged with QA evidence.
- [ ] Roadmap updated.
- [ ] iMac deploy successful.

---

## Risks (carried from spec §7)

- R1 — migration overlap with active extractor runs.
- R2 — Claude/Codex audit-mode prompt drift.
- R3 — composite tool schema breakage (low; all 3 are net-new).

---

## Cross-references

- Spec: `2026-05-07-audit-v1-s0-foundation-prereqs_spec.md`
- Sprint: `D-audit-orchestration.md` §S0
- Roadmap: `docs/roadmap.md` §"Audit-V1" S0 row
- Atomic-handoff: `paperclips/fragments/profiles/handoff.md`
- QA evidence rules: `paperclips/fragments/profiles/qa-evidence-format.md`
