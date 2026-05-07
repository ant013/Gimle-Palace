# Audit-V1 S1 — Audit Orchestration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:test-driven-development` + `superpowers:writing-skills` (S1.7 role file). Atomic-handoff discipline mandatory.

> **Blocked-on-S0**: per operator's "не придумывать" rule, sub-slices
> S1.4 / S1.5 / S1.7 / S1.9 reference S0 outputs that have not yet
> merged. Steps that depend on S0 contracts are tagged
> `<<DEPENDS ON S0.x>>` and intentionally use placeholder language —
> they will be refined to concrete contracts after S0 lands. PR for
> S1 cannot squash-merge until S0 is on develop.

**Slice:** S1 of Audit-V1 sprint sequence (rev3).
**Spec:** `docs/superpowers/specs/2026-05-07-audit-v1-s1-orchestration_spec.md`.
**Source branch:** `feature/GIM-233-audit-v1-s1-orchestration` cut from `origin/develop` (S0 merged `0a02ade`).
**Target branch:** `develop`. Squash-merge after S0 is on develop AND all CI green.
**Team:** Claude (single Claude PE; possibly 2 if S1 splits per S1-D1).
**Wall-time (rev4):** 4-5 weeks (was 3-4w in rev3). +1w buffer per CTO-S1-H1
finding: historical evidence (GIM-216 multi-week Phase 3 review) shows
slice phase-chain overhead is significant. S1.9 (async workflow launcher)
identified as scope-cuttable to v1.1 if margin breaks against 18w envelope.

---

## Phase 0 — Wait for S0

### Step 0.1: Block until S0 lands on develop

**Owner:** CTO.

- [ ] Verify `docs/roadmap.md` Audit-V1 S0 row = ✅ + merge SHA.
- [ ] Verify `git log origin/develop --grep="GIM-228"` returns the squash commit (`0a02ade`).
- [ ] If S0 not yet merged: pause; do NOT cut S1 branch — too much
      drift risk. Re-check daily.

**Acceptance:** S0 ✅ on develop.

### Step 0.2: Resolve issue + branch

**Owner:** CTO.

- [ ] Open paperclip issue `Audit-V1 S1 — Audit Orchestration`.
- [ ] Body = link to spec + this plan; `GIM-233` placeholders.
- [ ] Branch off `origin/develop` (which now carries S0 outputs).
- [ ] Reassign to CodeReviewer for plan-first review.

**Acceptance:** issue exists with substituted key; branch cut; CR is
assignee.

---

## Phase 1 — Plan-first review (CodeReviewer)

### Step 1.1: Validate plan against post-S0 state

**Owner:** CodeReviewer.

- [ ] Verify all `<<DEPENDS ON S0.x>>` markers in this plan have been
      resolved against the actual S0 commit (i.e., the plan has been
      revised to cite concrete S0 contracts, not placeholders).
- [ ] Verify each S1.x sub-slice has a concrete test+impl+commit step.
- [ ] Verify acceptance criteria are measurable.
- [ ] Per `feedback_anti_rubber_stamp.md`: full review checklist
      with evidence.
- [ ] Decide S1-D1: single PR vs split. Default single PR matching
      sprint file shape.
- [ ] APPROVE on paperclip + GitHub `gh pr review --approve`.
      Reassign to PythonEngineer.

**Acceptance:** APPROVE; assignee = PE.

---

## Phase 2 — Implementation (PythonEngineer)

### Phase 2.1 — S1.1 Audit deliverable spec (~1h)

#### Step 2.1.1: Author the contract document

**Owner:** PythonEngineer.
**Files:** `docs/superpowers/specs/2026-05-07-audit-v1-s1-orchestration_spec.md` extended IN-PLACE with §"S1.1 audit deliverable contract" — OR a sibling artefact at `docs/runbooks/audit-deliverable-format.md`. Default sibling.

- [ ] Define the markdown report section list (10 sections).
- [ ] Define severity rank ladder with concrete extractor mappings.
- [ ] Define `BaseExtractor.audit_contract()` Python type signature.
- [ ] Define `:IngestRun` schema contract (consumes S0.1 output).
- [ ] Define empty-section text format.
- [ ] Define provenance trailer format.
- [ ] Add a token budget table (per AV1-D6).

**Acceptance:** runbook exists; 10 sections × severity table × contract
signatures all present.

#### Step 2.1.2: Commit S1.1

- [ ] Commit: `docs(GIM-233): audit deliverable contract spec (S1.1)`.

---

### Phase 2.2 — S1.2 per-extractor templates (~2-3h)

#### Step 2.2.1: Failing test — golden-file match

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/tests/audit/unit/test_templates.py` (new).
- 7 golden files under
  `services/palace-mcp/tests/audit/golden/<extractor>.md`.

- [ ] One test per template: Jinja-render with synthetic findings dict
      → `assert rendered == golden_file_content`.
- [ ] Initially golden files are empty / placeholder; tests RED.

**Acceptance:** 14 RED tests (7 empty + 7 with-findings).

#### Step 2.2.2: Author 7 templates

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/src/palace_mcp/audit/templates/hotspot.md` etc.

- [ ] Each template: severity-grouped finding list, summary stats,
      provenance trailer.
- [ ] Re-run tests; capture rendered output → save as golden.
- [ ] Re-run; tests GREEN.

**Acceptance:** 14 GREEN.

#### Step 2.2.3: Commit S1.2

- [ ] Commit: `feat(GIM-233): per-extractor audit section templates (S1.2)`.

---

### Phase 2.3 — S1.3 renderer + base class (~3-4h)

#### Step 2.3.1: Failing tests

**Owner:** PythonEngineer.
**Files:** `services/palace-mcp/tests/audit/unit/test_audit_renderer.py`.

- [ ] `test_renderer_loads_top_template`.
- [ ] `test_renderer_dispatches_via_audit_contract` — fake extractor
      with `audit_contract()` returning known template path.
- [ ] `test_severity_sort_within_section`.
- [ ] `test_section_order_by_max_severity`.
- [ ] `test_blind_spot_section_lists_missing_extractors`.
- [ ] All RED initially.

**Acceptance:** 5 RED tests.

#### Step 2.3.2: Implement renderer + base class

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/src/palace_mcp/audit/__init__.py` (new).
- `services/palace-mcp/src/palace_mcp/audit/renderer.py` (new).
- `services/palace-mcp/src/palace_mcp/audit/report_template.md` (new).
- `services/palace-mcp/src/palace_mcp/audit/contracts.py` (new) —
  `AuditContract` dataclass, `AuditSectionData` model.
- `services/palace-mcp/src/palace_mcp/extractors/base.py` —
  add `audit_contract()` returning `None` by default.

- [ ] Renderer is pure function; no Neo4j calls.
- [ ] Base class change: `audit_contract(self) -> AuditContract | None: return None`.
- [ ] Tests GREEN.

**Acceptance:** 5 GREEN; existing extractor suite unchanged.

#### Step 2.3.3: Commit S1.3

- [ ] Commit: `feat(GIM-233): audit renderer + BaseExtractor.audit_contract() (S1.3)`.

---

### Phase 2.4 — S1.4 discovery (~1-2h, ‖ 2.3)

#### Step 2.4.1: Failing test (`<<DEPENDS ON S0.1>>`)

**Owner:** PythonEngineer.
**Files:** `services/palace-mcp/tests/audit/integration/test_audit_discovery.py`.

- [ ] Seed Neo4j with `:IngestRun` rows using **S0.1's unified schema**
      (`extractor_name`, `project`).
- [ ] `discovery.find_latest_runs(project="<slug>")` returns the
      latest successful run per `extractor_name`.
- [ ] RED initially.

**Acceptance:** 1 RED test.

#### Step 2.4.2: Implement discovery Cypher

**Owner:** PythonEngineer.
**Files:** `services/palace-mcp/src/palace_mcp/audit/discovery.py`.

- [ ] Cypher per spec §3.4.
- [ ] Test GREEN.

**Acceptance:** GREEN.

#### Step 2.4.3: Commit S1.4

- [ ] Commit: `feat(GIM-233): audit extractor discovery via :IngestRun (S1.4)`.

---

### Phase 2.5 — S1.5 generic fetcher (~2-3h)

#### Step 2.5.1: Failing test (rev4 — NO S0.2 dependency)

**Owner:** PythonEngineer.
**Files:** `services/palace-mcp/tests/audit/integration/test_audit_fetcher.py`.

- [ ] Seed Neo4j; populate registry with 7 fake extractors each
      returning a known `AuditContract`.
- [ ] Call `fetch_audit_data(...)`.
- [ ] Assert (rev4 — direct Cypher, not MCP tool calls):
      response includes 1 `AuditSectionData` per extractor; each
      `AuditSectionData.data` is the result of executing
      `audit_contract().query` against the seeded graph and parsing
      via `audit_contract().response_model`. Cypher executes via the
      Neo4j async driver in the fetcher's process — there are NO
      MCP round-trips inside the fetcher.
- [ ] RED initially.

**Acceptance:** 1 RED test (with multiple sub-assertions).

#### Step 2.5.2: Implement fetcher

**Owner:** PythonEngineer.
**Files:** `services/palace-mcp/src/palace_mcp/audit/fetcher.py`.

- [ ] Generic fetcher per spec §3.5 (no per-extractor dispatch).
- [ ] Tests GREEN.

**Acceptance:** GREEN.

#### Step 2.5.3: Commit S1.5

- [ ] Commit: `feat(GIM-233): generic audit fetcher via audit_contract() (S1.5)`.

---

### Phase 2.6 — S1.6 audit_contract() × 7 (~4-6h)

#### Step 2.6.1: Per-extractor test

**Owner:** PythonEngineer.
**Files:** for each of 7 extractor `.py` files, add a unit test:
`audit_contract()` returns non-None with valid query / response model
/ template path.

- [ ] 7 tests, all RED initially.

**Acceptance:** 7 RED.

#### Step 2.6.2: Implement audit_contract() per extractor

**Owner:** PythonEngineer.
**Files:** 7 extractor `.py` files (per spec §4 table).

- [ ] Each implementation: ~30 LOC method returning `AuditContract`
      with the extractor's existing Cypher (or composite-tool wrapper).
- [ ] Reference template_path under `audit/templates/<name>.md`.
- [ ] Tests GREEN.

**Acceptance:** 7 GREEN.

#### Step 2.6.3: Commit S1.6 (rev4 — boundary correction)

- [ ] Commit: `feat(GIM-233): audit_contract() on 7 existing extractors (S1.6)`.
- [ ] **(rev4)**: do NOT notify CTO that S2.1 can begin — S1.7..S1.10
      are still PE-bound (S1.7 markdown-only could be picked up by Board,
      but S1.8/S1.9/S1.10 require Python work and stay with PE). PE
      continues sequentially: S1.7 → S1.8 → S1.9 → S1.10. After S1.10
      merge, S2.1 starts. Net effect on rev3 critical path: +1w (17-18w
      → 18-19w), tight against 18w envelope. Operator-aware risk.
      Mitigation if margin breaks: cut S1.9 (async workflow launcher)
      from v1 scope — sync `palace.audit.run` MCP tool alone is
      sufficient for v1 smoke. S1.9 lands as v1.1.

---

### Phase 2.7 — S1.7 Auditor role file (~1-2h)

#### Step 2.7.1: Author Auditor role file

**Owner:** PythonEngineer (markdown only).
**Files:**
- `paperclips/roles/auditor.md` (new).
- `paperclips/roles-codex/auditor.md` (new mirror per
  `feedback_slim_both_claude_codex.md`).

- [ ] Standard fragment includes (handoff, qa-evidence, plan-first,
      atomic-handoff, slim-discipline).
- [ ] Audit-mode section using S0.3 fragment (consume, not duplicate).
- [ ] Domain section: "Receives project + fetcher output → produces
      per-domain markdown sub-reports. Hard rule: NO inventing
      findings beyond fetcher data."
- [ ] Re-render bundles; verify Auditor section appears.

**Acceptance:** 2 role files exist; render artefacts validated.

#### Step 2.7.2: Register Auditor in deploy script (rev4 — inline API call)

- [ ] Edit `paperclips/scripts/deploy-agents.sh` (or canonical
      list) to include `auditor` in `AGENT_NAMES`.
- [ ] POST agent identity to paperclip — exact API call (rev4 inline,
      removes forward-reference to E6 plan):
      ```
      curl -X POST \
        -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{
          "companyId": "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
          "name": "Auditor",
          "adapterType": "claude_local",
          "status": "idle",
          "title": "Auditor — Quality + Dependencies + Historical (audit-v1)",
          "icon": "shield-check",
          "reportsTo": "<CTO id 7fb0fdbb-...>"
        }' \
        "$PAPERCLIP_API_URL/api/companies/$COMPANY_ID/agents"
      ```
      Response body contains the new agent's `id` (UUID).
- [ ] Capture UUID; update Board memory `reference_agent_ids.md`.
- [ ] Verify with GET listing: agent appears with `name=Auditor`,
      `status=idle`.

**Acceptance:** Auditor agent listed in
`GET /api/companies/<id>/agents` with `name=Auditor`,
`adapterType=claude_local`.

#### Step 2.7.3: Commit S1.7

- [ ] Commit: `feat(GIM-233): Auditor role file (S1.7)`.

---

### Phase 2.8 — S1.8 `palace.audit.run` MCP tool (~2-4h)

#### Step 2.8.1: Failing E2E test

**Owner:** PythonEngineer.
**Files:** `services/palace-mcp/tests/audit/integration/test_audit_run_e2e.py`.

- [ ] Seed Neo4j with synthetic fixture; set `extractor_registry`
      from S1.6 implementations.
- [ ] Call `palace.audit.run(project="<slug>")` via MCP.
- [ ] Assert: returns `{ok: true, report_markdown: <md>,
      fetched_extractors: [...], blind_spots: [...], provenance: {...}}`.
- [ ] RED initially.

**Acceptance:** 1 RED.

#### Step 2.8.2: Implement run.py + register tool

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/src/palace_mcp/audit/run.py` (new).
- `services/palace-mcp/src/palace_mcp/mcp_server.py` — register tool.

- [ ] Validates args (`project XOR bundle`, slug regex,
      `depth ∈ {quick, full}`).
- [ ] Calls discovery → fetcher → renderer.
- [ ] Returns response per S1-D2 (default inline body).
- [ ] Test GREEN.

**Acceptance:** GREEN; tool listed in MCP server tool inventory.

#### Step 2.8.3: Commit S1.8

- [ ] Commit: `feat(GIM-233): palace.audit.run sync MCP tool (S1.8)`.

---

### Phase 2.9 — S1.9 async workflow launcher (~3-4h)

#### Step 2.9.1: Author CLI wrapper (rev4 — adds CI-compatible tests)

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/src/palace_mcp/cli.py` (new).
- `services/palace-mcp/tests/cli/test_audit_cli_unit.py` (new) — CI-level.
- `services/palace-mcp/tests/cli/test_audit_cli_e2e.py` (existing scope) — QA-level.

- [ ] Subcommand `audit run --project=<slug>` calls MCP via
      streamable-HTTP, returns markdown to stdout.
- [ ] Subcommand `audit launch --project=<slug>` creates parent +
      3 child paperclip issues.
- [ ] **(rev4 — CR-H3)**: CI-compatible unit test
      `test_audit_cli_unit.py`:
  - mocks the streamable-HTTP transport;
  - asserts arg-parse semantics, request payload construction,
    error envelope on missing args, slug regex validation.
  - runs in CI without a live palace-mcp instance.
- [ ] Existing E2E test (live palace-mcp instance, QA-only) covers
      live-stack regression.

**Acceptance:** CLI exits 0; markdown on stdout (E2E); CI unit tests
pass without live stack.

#### Step 2.9.2: Author launcher script (rev4 — adds dry-run mode for CI)

**Owner:** PythonEngineer.
**Files:** `paperclips/scripts/audit-workflow-launcher.sh` (new).

- [ ] Bash script per spec §3.9.
- [ ] Creates parent issue `audit: <slug>` assigned to Auditor.
- [ ] Creates 3 child issues with `blockedByIssueIds` →
      OpusArchitectReviewer, SecurityAuditor, BlockchainEngineer
      (`<<DEPENDS ON S0.3 — audit-mode prompts on these agents
      (Claude side); CX-side audit-mode wired via E6 file creation>>`).
- [ ] **(rev4 — CR-H3)**: support `--dry-run` flag that prints all
      4 issue payloads to stdout WITHOUT calling the paperclip API.
      CI smoke test invokes `--dry-run` and asserts payloads are
      well-formed JSON with expected fields. This gives CI coverage
      of the launcher without needing a live paperclip instance.

**Acceptance:** dry-run on iMac creates 4 real issues; child issues
block parent; parent's `assigneeAgentId` is Auditor. CI dry-run
exits 0 with valid JSON payloads on stdout.

#### Step 2.9.3: Author runbook

**Owner:** PythonEngineer.
**Files:** `docs/runbooks/audit-orchestration.md` (new).

- [ ] Document: how to run sync vs async; troubleshooting; expected
      latency; how to diagnose stuck workflow.

**Acceptance:** runbook exists; covers happy path + 3 failure modes.

#### Step 2.9.4: Commit S1.9

- [ ] Commit: `feat(GIM-233): async audit workflow launcher (S1.9)`.

---

### Phase 2.10 — S1.10 E2E smoke harness (~2-3h)

#### Step 2.10.1: Build synthetic fixture

**Owner:** PythonEngineer.
**Files:**
- `services/palace-mcp/tests/audit/fixtures/audit-mini-project/*`.
- `services/palace-mcp/tests/audit/smoke/test_audit_e2e.sh` (new).

- [ ] Fixture with 7 successful `:IngestRun` rows + sample data
      per extractor.
- [ ] Bash test: bring up palace-mcp + Neo4j (compose), seed fixture,
      run `palace.audit.run`, diff output against golden file.
- [ ] Paved-path regression test: add a new fixture extractor entry
      → re-run → verify a new section appears in output without
      orchestrator code changes.

**Acceptance:** smoke test passes locally; CI gate added.

#### Step 2.10.2: Commit S1.10

- [ ] Commit: `feat(GIM-233): audit E2E smoke + paved-path regression test (S1.10)`.

---

### Step 2.11: Push + open PR

- [ ] `git push -u origin feature/GIM-233-audit-v1-s1-orchestration`.
- [ ] Open PR `feat(GIM-233): Audit-V1 S1 — audit orchestration`.
- [ ] PR body lists 10 commits → S1.1..S1.10 mapping.
- [ ] PR body includes "Closes GIM-233" + QA Evidence placeholder.
- [ ] Reassign issue to CR for Phase 3.1.

**Acceptance:** PR open; CI runs.

---

## Phase 3 — Review

### Phase 3.1 — Mechanical review (CodeReviewer)

- [ ] Paste `gh pr checks` — required CI green.
- [ ] Paste `uv run ruff check && uv run mypy services/palace-mcp/src/ && uv run pytest services/palace-mcp/tests/audit/`.
- [ ] Verify all 10 sub-slices have a corresponding commit + test.
- [ ] Verify all `<<DEPENDS ON S0.x>>` markers are resolved (S0
      contracts now cited concretely).
- [ ] APPROVE on paperclip + `gh pr review --approve`. Reassign to
      Opus.

**Acceptance:** APPROVE.

### Phase 3.2 — Adversarial review (OpusArchitectReviewer)

- [ ] Probe: does the renderer truncate gracefully when an extractor
      returns 1000 findings (report bloat)?
- [ ] Probe: paved-path regression test actually fails if someone
      adds a hard-coded section; or does it silently pass?
- [ ] Probe: child-issue dispatch handles a child timeout correctly
      (parent eventually unblocks)?
- [ ] Probe: Auditor role prompt actually prevents finding-invention;
      give it adversarial input.
- [ ] Probe: `palace.audit.run` returns a sane response when no
      extractors have run yet (empty graph case).

**Acceptance:** APPROVE / NUDGE / BLOCK; loop until APPROVE.

---

## Phase 4 — QA evidence (QAEngineer on iMac)

### Step 4.1: Live smoke

- [ ] SSH iMac.
- [ ] FF-pull develop. Pull PR branch into temp worktree.
- [ ] Build + up palace-mcp container.
- [ ] Live MCP call `palace.audit.run(project="gimle")` — capture
      report markdown.
- [ ] Live execution of `bash audit-workflow-launcher.sh gimle` —
      verify parent + 3 child issues appear in paperclip with correct
      assignees + `blockedByIssueIds`.
- [ ] Wait for child issues to complete (or manually mock domain
      agent responses); verify Auditor wakes and posts final report.

### Step 4.2: QA Evidence comment

- [ ] Edit PR body `## QA Evidence`. Cite SHA + 4 live commands +
      issue numbers + 1 sample report markdown excerpt + affirmation
      per `feedback_pe_qa_evidence_fabrication.md`.

**Acceptance:** Evidence satisfies `qa-evidence-present` CI.

---

## Phase 5 — Merge (CTO)

- [ ] Verify CI green; CR + Opus APPROVE; QA Evidence present.
- [ ] Squash-merge.
- [ ] Update `docs/roadmap.md` Audit-V1 S1 row 📋 → ✅ + merge SHA.
- [ ] iMac deploy: `bash paperclips/scripts/imac-deploy.sh` +
      `bash paperclips/scripts/imac-agents-deploy.sh` (Auditor
      role).
- [ ] Notify Claude PE that S2.1 can begin (was already freed at
      S1.6 commit).

**Acceptance:** S1 ✅; iMac runs `palace.audit.run` against live data.

---

## Definition-of-Done checklist

- [ ] S1.1 contract + S1.2 templates + S1.3 renderer + S1.4 discovery
      + S1.5 fetcher + S1.6 7-extractor `audit_contract()` + S1.7
      Auditor role + S1.8 sync MCP tool + S1.9 async workflow + S1.10
      smoke — all merged.
- [ ] All `<<DEPENDS ON S0.x>>` markers resolved.
- [ ] Auditor agent UUID in `reference_agent_ids.md`.
- [ ] Roadmap S1 row ✅.
- [ ] iMac deploy successful.

---

## Risks (carried from spec §7)

R1 audit_contract drift · R2 finding invention · R3 report bloat ·
R4 paved-path regression · R5 child-issue workflow complexity.

---

## Cross-references

- Spec: `2026-05-07-audit-v1-s1-orchestration_spec.md`
- Sprint: `D-audit-orchestration.md` §S1
- Predecessor: S0 (`2026-05-07-audit-v1-s0-foundation-prereqs_*.md`)
- Successor: S2.1 (`B-audit-extractors.md` §S2.1)
- Roadmap: `docs/roadmap.md` §"Audit-V1" S1 row
- Atomic-handoff: `paperclips/fragments/profiles/handoff.md`
