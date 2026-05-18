# GIM-334: BitcoinCore full project-analyze rerun

> **For agentic workers:** Read only your assigned step — the full issue body is not needed.

**Goal:** Run the full Swift Kit extractor pipeline (17 extractors) against BitcoinCore.Swift, produce audit report, diff against TronKit findings.

**Spec:** `docs/superpowers/specs/2026-05-17-GIM-334-bitcoin-core-full-rerun.md`
**Branch:** `feature/GIM-334-bitcoin-core-full-rerun`
**Grounded on:** `develop` @ `17196c0`

---

## Step 1 — SCIP emission (Operator — Track B)

**Owner:** Operator (Anton)
**Status:** TODO
**Depends on:** —

**Description:**
SCIP emission requires Xcode toolchain on the operator's dev Mac (iMac can't build modern iOS). Run:

```bash
bash paperclips/scripts/scip_emit_swift_kit.sh bitcoin-core
```

Provide the resulting SCIP index path to MCPEngineer for Step 2.

**Acceptance criteria:**
- [ ] SCIP index file generated for BitcoinCore.Swift
- [ ] Path communicated to MCPEngineer

**Affected files:**
- SCIP index output (location TBD by operator)

---

## Step 2 — Project registration + extractor cascade (MCPEngineer)

**Owner:** MCPEngineer
**Status:** TODO
**Depends on:** Step 1 (SCIP index path)

**Description:**
Create branch `feature/GIM-334-bitcoin-core-full-rerun` from `develop`. Register BitcoinCore, update SCIP path, run extractor cascade:

1. Register project:
   ```
   palace.memory.register_project(slug="bitcoin-core", parent_mount="hs", relative_path="BitcoinCore.Swift")
   ```

2. Add SCIP index path to `PALACE_SCIP_INDEX_PATHS` in `.env` (the ingest script handles this automatically if `--env-file` is default).

3. Run extractor cascade:
   ```bash
   bash paperclips/scripts/ingest_swift_kit.sh bitcoin-core --bundle=uw-ios
   ```

4. Verify all 17 extractors completed. Capture JSON summary output from the script.

**Acceptance criteria:**
- [ ] Project `bitcoin-core` registered and visible via `palace.memory.list_projects()`
- [ ] SCIP index path added to `PALACE_SCIP_INDEX_PATHS`
- [ ] All 17 DEFAULT_EXTRACTORS ran (capture success/fail per extractor)
- [ ] Any failures classified and noted (do not fix — file as child issues)

**Affected files:**
- `.env` (modify — SCIP path addition)
- No code changes expected in this step

---

## Step 3 — Project analyze + reports (MCPEngineer)

**Owner:** MCPEngineer
**Status:** TODO
**Depends on:** Step 2 (extractors complete)

**Description:**

1. Run full project analysis:
   ```
   palace.audit.run(project="bitcoin-core", depth="full")
   ```

2. Save audit report to:
   `docs/audit-reports/2026-05-17-bitcoin-core-rerun.md`

3. Create diff report comparing BitcoinCore vs TronKit (reference: `docs/audit-reports/2026-05-14-tron-kit-final.md`):
   - Which extractors returned same/different counts
   - Which findings categories overlap
   - Whether `private_key_string_storage` in Example/ pattern appears in BitcoinCore
   - Which TronKit findings are TronKit-specific vs HS Kit-wide
   - Whether suspicious-zero findings from GIM-333 reproduce on BitcoinCore

   Save to: `docs/runbooks/bitcoin-core-vs-tron-kit-diff-2026-05-17.md`

4. Cross-check GIM-333 diagnostic verdicts:
   - If GIM-333 said `hotspot` is BROKEN → BitcoinCore should also return 0 (consistent) or non-zero (re-opens debugging)
   - Same check for `dead_symbol_binary_surface`, `public_api_surface`, `cross_module_contract`, `cross_repo_version_skew`

5. Open PR to `develop` with both report files.

**Acceptance criteria:**
- [ ] `palace.audit.run` returns `ok=true` with blind spots matching TronKit baseline (public_api_surface + cross_module_contract), 0 RUN_FAILED
- [ ] Audit report committed at canonical path
- [ ] Diff report committed with per-extractor comparison
- [ ] GIM-333 diagnostic verdicts cross-checked and noted in diff report
- [ ] PR opened to `develop`

**Affected files:**
- `docs/audit-reports/2026-05-17-bitcoin-core-rerun.md` (create)
- `docs/runbooks/bitcoin-core-vs-tron-kit-diff-2026-05-17.md` (create)

---

## Step 4 — Code Review (CodeReviewer)

**Owner:** CodeReviewer
**Status:** TODO
**Depends on:** Step 3 (PR opened)

**Description:**
Mechanical review of the PR. Verify:
- Report files are well-structured and complete
- Diff report covers all 17 extractors
- Cross-check section addresses all GIM-333 diagnostic verdicts
- CI green

**Acceptance criteria:**
- [ ] `gh pr checks <PR>` all green
- [ ] Report content reviewed for completeness
- [ ] APPROVED with compliance checklist

**Affected files:**
- PR review (no file changes expected)

---

## Step 5 — Adversarial Review (OpusArchitectReviewer)

**Owner:** OpusArchitectReviewer
**Status:** TODO
**Depends on:** Step 4 (CR APPROVED)

**Description:**
Challenge the diff report's conclusions:
- Are "consistent zeros" truly consistent, or does BitcoinCore have a different repo structure that should produce different results?
- Is the TronKit comparison apples-to-apples (same SCIP version, same extractor versions)?
- Any findings that look like pipeline artifacts rather than real security/quality signal?

**Acceptance criteria:**
- [ ] Findings addressed or acknowledged in PR
- [ ] APPROVED

**Affected files:**
- PR review (possible report amendments)

---

## Step 6 — QA Smoke (QAEngineer)

**Owner:** QAEngineer
**Status:** TODO
**Depends on:** Step 5 (adversarial review complete)

**Description:**
On iMac, verify:
1. `palace.memory.list_projects()` includes `bitcoin-core`
2. `palace.audit.run(project="bitcoin-core", depth="full")` returns `ok=true`
3. Spot-check 3+ extractor results via `palace.code.*` tools match what the report claims
4. Post QA evidence comment on GIM-334 with: smoke namespace, AnalysisRun ID, RUN_FAILED count, blind-spots count

**Acceptance criteria:**
- [ ] QA evidence comment posted with concrete output
- [ ] No discrepancies between report claims and live query results

**Affected files:**
- QA evidence comment (no file changes)

---

## Step 7 — Merge (CTO)

**Owner:** CTO
**Status:** TODO
**Depends on:** Step 6 (QA evidence posted)

**Description:**
Squash-merge PR to `develop` on green CI + APPROVED CR + APPROVED architect review + QA evidence.

**Acceptance criteria:**
- [ ] PR merged to develop
- [ ] GIM-334 closed

**Affected files:**
- Merge commit on `develop`
