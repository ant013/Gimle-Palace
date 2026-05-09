# Audit-V1 S2.3 — Error Handling Policy extractor — Implementation Plan

**Issue:** GIM-257
**Spec:** `docs/superpowers/specs/2026-05-09-GIM-257-error-handling-policy_spec.md`
**Branch:** `feature/GIM-257-error-handling-policy`
**Target:** `develop`
**Source sprint:** `docs/superpowers/sprints/B-audit-extractors.md` §S2.3
**Predecessor:** GIM-243 merged to `develop` at `42e2894584fecdbc623ab1c8257004b3063a571e`
**Reroute:** Board comment `5e7f4bf1-d909-4f1d-bd61-9dff9c8e8e6b` moves this issue to the CX chain:
`CXCodeReviewer -> CXPythonEngineer -> CXCodeReviewer -> CodexArchitectReviewer -> CXQAEngineer -> CXCTO`.
**Formal handoff targets:** `[@CXCodeReviewer](agent://45e3b24d-a444-49aa-83bc-69db865a1897?i=eye)`,
`[@CXPythonEngineer](agent://e010d305-22f7-4f5c-9462-e6526b195b19?i=code)`,
`[@CodexArchitectReviewer](agent://fec71dea-7dba-4947-ad1f-668920a02cb6?i=eye)`,
`[@CXQAEngineer](agent://99d5f8f8-822f-4ddb-baaa-0bdaec6f9399?i=bug)`,
`[@CXCTO](agent://da97dbd9-6627-48d0-b421-66af0750eacf?i=crown)`.

---

## File Structure

Phase 3.1 must compare implementation scope mechanically:

```bash
git diff --name-only origin/develop..HEAD | sort
```

Expected planned implementation scope is **23 files** (**20 NEW + 3 MOD**):

| Status | Path |
|--------|------|
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/__init__.py` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/empty_catch_block.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/empty_catch_in_crypto_path.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/try_optional_swallow.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/try_optional_in_crypto_path.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/catch_only_logs.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/generic_catch_all.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/error_as_string.yaml` |
| NEW | `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/nil_coalesce_swallows_error.yaml` |
| MOD | `services/palace-mcp/src/palace_mcp/extractors/registry.py` |
| NEW | `services/palace-mcp/src/palace_mcp/audit/templates/error_handling_policy.md` |
| NEW | `services/palace-mcp/tests/extractors/unit/test_error_handling_policy.py` |
| NEW | `services/palace-mcp/tests/extractors/integration/test_error_handling_policy_integration.py` |
| MOD | `services/palace-mcp/tests/extractors/unit/test_registry.py` |
| MOD | `services/palace-mcp/tests/audit/unit/test_templates.py` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/EmptyCatch.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/TryOptionalSwallow.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/CatchOnlyLogs.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/CryptoSigner.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Good/ProperCatch.swift` |
| NEW | `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Good/TypedErrors.swift` |
| NEW | `docs/runbooks/error-handling-policy.md` |

If implementation needs a different file, the implementer must update this
table in the same PR before Phase 3.1 handoff and explain why the scope changed.

## Phase 1.1 — CXCTO formalisation

### Step 1.1.1: Verify S2.3 against current develop

**Owner:** CXCTO
**Affected paths:** `docs/superpowers/specs/2026-05-09-GIM-257-error-handling-policy_spec.md`,
this plan.
**Dependencies:** GIM-243 merged.

Description:

- Check `origin/develop` after GIM-243.
- Confirm current `AuditContract` shape.
- Confirm semgrep is already pinned.
- Resolve sprint ambiguity around tech stack (SwiftSyntax/detekt/ast-grep
  claims vs reality of semgrep-only).
- Confirm pattern from crypto_domain_model applies.

Acceptance criteria:

- Spec cites current `AuditContract` fields.
- Spec explicitly scopes to Swift + semgrep only.
- Plan has explicit external-tooling spike gate.
- Issue is handed to CXCodeReviewer for plan-first review.

## Phase 1.2 — Plan-first review

### Step 1.2.1: Review architecture and acceptance criteria

**Owner:** CXCodeReviewer
**Affected paths:** spec and plan only.
**Dependencies:** Step 1.1.1.

Description:

- Review spec/plan before implementation.
- Verify no unsupported external API commitments.
- Verify semgrep rule patterns are valid Swift patterns (spot-check).
- Verify each implementation step has measurable acceptance criteria.

Acceptance criteria:

- Paperclip comment says APPROVE or REQUEST CHANGES.
- If approved, issue is reassigned to CXPythonEngineer for Phase 2.
- If changes are requested, comments cite exact spec/plan lines.

## Phase 2 — Implementation

### Step 2.1: Scaffold package, fixtures, and first rule

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/__init__.py`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/empty_catch_block.yaml`
- `services/palace-mcp/tests/extractors/unit/test_error_handling_policy.py`
- `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/EmptyCatch.swift`
- `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Good/ProperCatch.swift`

**Dependencies:** Phase 1.2 APPROVE.

Description:

- Create extractor package following crypto_domain_model pattern.
- Implement `ErrorHandlingPolicyExtractor(BaseExtractor)` with:
  - `name = "error_handling_policy"`
  - `constraints` and `indexes` for `:CatchSite` and `:ErrorFinding` (spec §7.2).
  - `async run()` that invokes semgrep, deduplicates, writes findings.
  - `audit_contract()` returning current `AuditContract` shape.
- Add first rule: `empty_catch_block.yaml` with semgrep Swift pattern
  for `catch { }` and variants.
- Add bad/good fixtures for this rule.
- Add unit test verifying rule fires on bad fixture, not on good fixture.
- Add dedup unit tests (coalesce same location, keep highest severity).
- Add severity mapper tests.

Acceptance criteria:

- `empty_catch_block` rule fires on `EmptyCatch.swift` bad fixture.
- `empty_catch_block` rule does NOT fire on `ProperCatch.swift` good fixture.
- Dedup tests pass.
- Severity mapper covers all `Severity` enum values + unknown → INFORMATIONAL.
- `audit_contract()` returns valid `AuditContract`.
- No registry changes yet.

### Step 2.2: Add remaining 7 rules with fixtures

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/empty_catch_in_crypto_path.yaml`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/try_optional_swallow.yaml`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/try_optional_in_crypto_path.yaml`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/catch_only_logs.yaml`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/generic_catch_all.yaml`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/error_as_string.yaml`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/rules/nil_coalesce_swallows_error.yaml`
- `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/TryOptionalSwallow.swift`
- `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/CatchOnlyLogs.swift`
- `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Bad/CryptoSigner.swift`
- `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Good/TypedErrors.swift`
- `services/palace-mcp/tests/extractors/unit/test_error_handling_policy.py` (extend)

**Dependencies:** Step 2.1.

Description:

- Add 7 remaining semgrep YAML rules per spec §6.2.
- Add the non-finding catch-site inventory surface required by spec §6.2:
  either an informational semgrep pattern bundled with an existing rule file,
  or bounded source-line inventory in `extractor.py`. This inventory writes
  `:CatchSite` only and must not create standalone `:ErrorFinding` rows.
- `empty_catch_in_crypto_path` and `try_optional_in_crypto_path` use semgrep
  `paths.include` with crypto file patterns — separate rules, not post-processing.
- `catch_only_logs` matches `catch { print(...) }` / `catch { logger.error(...) }`
  patterns without rethrow.
- `generic_catch_all` matches `catch` without error type binding.
- `error_as_string` matches throw/return of `String` typed errors.
- `nil_coalesce_swallows_error` matches `try? x ?? default` pattern.
- Each rule has a bad fixture in `Sources/Bad/` and is verified against good
  fixtures (existing `ProperCatch.swift` + new `TypedErrors.swift`).
- `CryptoSigner.swift` fixture exercises crypto-path severity escalation.

Acceptance criteria:

- Each rule fires on its bad fixture.
- No rule fires on good fixtures.
- Crypto-path rules fire only on files matching the path pattern.
- All rule YAML files are valid semgrep syntax.

### Step 2.3: Add deliberate-suppression post-processing

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py` (extend)
- `services/palace-mcp/tests/extractors/unit/test_error_handling_policy.py` (extend)
- `services/palace-mcp/tests/extractors/fixtures/error-handling-mini-project/Sources/Good/ProperCatch.swift` (extend)

**Dependencies:** Step 2.2.

Description:

- After semgrep scan, for each finding check if matched line range contains
  `// ehp:ignore` or `// MARK: deliberate` comment.
- If found, downgrade finding severity to `informational`.
- Read source file lines for matched range only (bounded read, no full file).
- Add fixtures with suppression comments.

Acceptance criteria:

- Finding on line with `// ehp:ignore` is downgraded to `informational`.
- Finding on line with `// MARK: deliberate` is downgraded.
- Finding without suppression comment keeps original severity.
- Suppression check is bounded (does not read entire file).

### Step 2.4: Add Neo4j writer, integration tests, and registry

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py` (extend)
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/tests/extractors/unit/test_registry.py`
- `services/palace-mcp/tests/extractors/integration/test_error_handling_policy_integration.py`

**Dependencies:** Step 2.3.

Description:

- Neo4j writer uses MERGE per `:CatchSite` and per `:ErrorFinding` (spec §7.4).
- Register `error_handling_policy` in `EXTRACTORS`.
- Integration test runs extractor against fixture with real Neo4j
  (testcontainers) and verifies expected `:CatchSite` and `:ErrorFinding` node counts.
- Idempotency test: second run writes zero duplicate nodes for both labels.

Acceptance criteria:

- `EXTRACTORS["error_handling_policy"]` exists.
- Integration test writes expected catch-site and finding counts.
- Second run creates zero duplicates for `:CatchSite` or `:ErrorFinding`.
- Constraints + indexes are safe to run repeatedly.
- Registry test includes `error_handling_policy`.

### Step 2.5: Add audit template and runbook

**Owner:** CXPythonEngineer
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/audit/templates/error_handling_policy.md`
- `services/palace-mcp/tests/audit/unit/test_templates.py`
- `docs/runbooks/error-handling-policy.md`

**Dependencies:** Step 2.4.

Description:

- Add Jinja2 template following crypto_domain_model/arch_layer pattern:
  summary stats (files scanned, `:CatchSite` count, swallowed/rethrows
  breakdown, finding breakdown), critical/high section, medium/low/informational
  section, clean state, provenance.
- Template golden tests in `test_templates.py`.
- Runbook: prerequisites (semgrep in container — already there), how to run,
  expected findings, rule descriptions, suppression markers, troubleshooting.

Acceptance criteria:

- Template renders without error for empty and non-empty findings.
- Template displays catch-site aggregate count and swallowed/rethrows breakdown.
- Runbook names all 8 rules with descriptions.
- Runbook documents the non-finding `:CatchSite` inventory/smoke evidence.
- Runbook documents `// ehp:ignore` suppression mechanism.

### Step 2.6: Local implementation validation and PR

**Owner:** CXPythonEngineer
**Affected paths:** implementation files from Phase 2.
**Dependencies:** Steps 2.1 through 2.5.

Description:

- Run the exact validation commands below from `services/palace-mcp`.
- Push the branch and open/update PR into `develop`.

Acceptance criteria:

- Targeted tests are green or failures are documented with exact blocker.
- PR includes spec + plan links.
- Paperclip handoff includes branch, commit SHA and test evidence.

Validation commands:

```bash
cd services/palace-mcp

uv run pytest \
  tests/extractors/unit/test_error_handling_policy.py \
  -v

uv run pytest \
  tests/extractors/unit/test_registry.py \
  tests/audit/unit/test_templates.py \
  -v

uv run pytest \
  tests/extractors/integration/test_error_handling_policy_integration.py \
  -m integration \
  -v

uv run ruff check \
  src/palace_mcp/extractors/error_handling_policy \
  tests/extractors/unit/test_error_handling_policy.py \
  tests/extractors/integration/test_error_handling_policy_integration.py

uv run mypy src/palace_mcp/extractors/error_handling_policy
```

## Phase 3.1 — Mechanical code review

### Step 3.1.1: Review implementation against plan

**Owner:** CXCodeReviewer
**Affected paths:** all files changed by Phase 2.
**Dependencies:** Phase 2 handoff.

Description:

- Verify changed files are within declared scope.
- Run `git diff --name-only origin/develop..HEAD | sort` and compare against
  the `File Structure` table above, including the expected 23-file count.
- Verify semgrep rules use valid Swift patterns.
- Verify no external tooling dependency was added without spike.
- Verify tests cover all 8 finding rules, catch-site inventory, and idempotent
  writes for both labels.
- Verify dedup and suppression logic.

Acceptance criteria:

- APPROVE or REQUEST CHANGES in Paperclip and GitHub.
- Any requested changes cite exact file/line and plan/spec requirement.

## Phase 3.2 — Architect adversarial review

### Step 3.2.1: Review architecture risk

**Owner:** CodexArchitectReviewer
**Affected paths:** implementation and docs.
**Dependencies:** Phase 3.1 APPROVE.

Description:

- Check graph contract compatibility with Audit-V1 S1, GIM-239, GIM-243.
- Check `:CatchSite` smoke surface compatibility with
  `docs/superpowers/sprints/E-smoke.md` §4 Security gate.
- Check false-positive controls (suppression, severity mapping, critical-path
  heuristic accuracy).
- Check no schema collisions with existing `:CryptoFinding` or `:ArchViolation`.
- Check semgrep rule quality (Swift grammar coverage, pattern accuracy).

Acceptance criteria:

- APPROVE or REQUEST CHANGES.
- If approved, issue is reassigned to CXQAEngineer.

## Phase 4.1 — QA live smoke

### Step 4.1.1: Run required QA evidence

**Owner:** CXQAEngineer
**Affected paths:** runtime only; no implementation changes unless returned.
**Dependencies:** Phase 3.2 APPROVE.

Description:

- Run required quality gates from project instructions.
- Run live smoke on `tronkit-swift`.
- Verify a real MCP/tool path: `palace.ingest.run_extractor(name="error_handling_policy", project="tronkit-swift")`.
- Verify `:CatchSite` count > 0.
- Verify `:ErrorFinding` count > 0 or explicit "no critical-path swallowed catches"
  with scanned file count cited.
- Verify audit report renders error handling section.
- Restore production checkout per checkout discipline.

Acceptance criteria:

- QA PASS comment includes commit SHA, container health, extractor run output,
  `:CatchSite` count, finding count or explicit clean rationale, report evidence,
  and production checkout restoration.
- If failed, issue returns to implementer with exact failing command/output.

## Phase 4.2 — CXCTO merge and queue propagation

### Step 4.2.1: Merge readiness and close

**Owner:** CXCTO
**Affected paths:** Paperclip/GitHub only.
**Dependencies:** Phase 4.1 QA PASS by CXQAEngineer.

Description:

- Run mandatory merge-readiness reality check.
- Squash-merge to `develop` if checks/reviews allow.
- Confirm merge SHA.
- This is the final slice in the Audit-V1 Claude queue (position 5/5). No
  further queue propagation unless Board adds S2.4+ slices.

Acceptance criteria:

- `gh pr view --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid`
  output is posted before claiming merge readiness/blocker.
- PR merged to `develop`.
- Issue closed only after QA evidence exists and merge/deploy state is documented.
- Board notified that Audit-V1 S2 (all 3 extractors) is complete.

## External tooling gate

Implementation may not add ast-grep, detekt, SwiftSyntax, tree-sitter,
SourceKit-LSP or a new semgrep plugin in this issue unless a fresh
`docs/research/<tool>-error-handling-spike/` artifact is added first and
reviewed by CXCodeReviewer. Default plan uses semgrep (already pinned) only.
