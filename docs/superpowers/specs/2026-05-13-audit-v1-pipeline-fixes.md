# Audit-V1 pipeline fixes — post-S4.1-smoke retrospective

**Date:** 2026-05-13
**Status:** draft
**Owner:** Board (operator + Board Claude session)
**Predecessor:** GIM-277 audit report `docs/audit-reports/2026-05-12-tron-kit.md` (merged PR #151 commit `299102d`), Opus Phase 3.2 review with 6 NUDGEs (`d7c1bb08` thread).

## Problem

S4.1 smoke (GIM-277, tron-kit) produced the first real Audit-V1 report end-to-end. The smoke surfaced 12 pipeline-level bugs across **coverage**, **failure visibility**, **data quality**, **source-context**, and **renderer** dimensions. None blocked v1 close, but every one degrades report value and operator trust. This spec covers all 12 as a single coordinated repair effort, organised into 5 implementation slices so each fix can ship as its own PR.

## Goals

- Restore the missing `testability_di` extractor on `develop`.
- Make the pipeline call every registered extractor on every project, with explicit failure / skip reporting — no silent misses, no failures masked as blind spots.
- Fix the false-pass on `hotspot` 0-scan; identify and patch the actual cause (mount path or prerequisite ordering).
- Add `source_context: library | example | test | other` annotation to every finding; let the renderer differentiate severity / display by context.
- Close out Opus N1, N2, N3, N4, N5, N6 from GIM-277 Phase 3.2 review.
- Re-run S4.1 smoke and validate all 8 acceptance criteria pass with NO false-positive HIGH (Opus N4) and NO 0-scan extractor (Opus N3).

## Non-goals

- **Process bugs** (PBUG-1..PBUG-10) — separate track in `docs/BUGS.md`, not in this spec.
- New extractors — only fix / recover existing ones.
- Stricter severity rules in `crypto_domain_model` beyond the source-context distinction (Opus N4 fix is sufficient for v1.1).
- Replacing the heuristic in `error_handling_policy` with full data-flow analysis (Opus N5 is a tuning fix, not a rewrite).
- Watchdog / paperclip-server improvements (separate track).

## Inventory of concerns

12 items, grouped into 5 slices. Each item lists evidence + proposed fix.

### Slice 1 — Extractor coverage gaps

#### B1: `testability_di` extractor missing from `develop`

**Evidence:**
- `git log --all --oneline | grep -i GIM-242` shows commits `4c4c087`, `5cbd634`, `2465b79`, `a6eac2e`, `23a4d93` ("feat(GIM-242): add testability_di extractor" + fixes).
- `git ls-tree origin/develop services/palace-mcp/src/palace_mcp/extractors/` does **not** include a `testability_di/` directory.
- `docker exec gimle-palace-palace-mcp-1 ls /app/src/palace_mcp/extractors/` shows no `testability_di`.
- Roadmap rev4 (PR #146 merged 2026-05-13) lists GIM-242 as ✅ merged — **but the artefact is not on develop**.

**Root cause (to verify):** PR for GIM-242 was either never merged to develop, or was merged then reverted in a subsequent commit. Need bisect.

**Proposed fix:**
1. `git log origin/develop --diff-filter=A -- services/palace-mcp/src/palace_mcp/extractors/testability_di/ -- 'services/palace-mcp/src/palace_mcp/extractors/testability_di*'` — find add commit if any.
2. If no add commit ever landed → cherry-pick from the GIM-242 feature branch as a standard CR → PE chain slice; treat as completion of GIM-242.
3. If add commit + later revert exists → write postmortem (`docs/postmortems/2026-05-13-GIM-242-testability-di-revert.md`), re-merge with revert annotation.
4. Update roadmap rev4 row to reflect actual state (downgrade ✅ → 🚧 until restored, then re-✅).

**Acceptance:**
- `git ls-tree origin/develop services/palace-mcp/src/palace_mcp/extractors/testability_di/` returns non-empty.
- `palace.ingest.list_extractors()` MCP call includes `testability_di`.
- Roadmap rev4 accurate.

---

#### B2: `reactive_dependency_tracer` silent miss in audit pipeline

**Evidence:**
- `palace.ingest.list_extractors()` returns `reactive_dependency_tracer` (registered).
- No `:IngestRun` for `extractor.reactive_dependency_tracer` exists with `group_id="project/tron-kit"`.
- `docs/audit-reports/2026-05-12-tron-kit.md` "Blind Spots" section **does not** list `reactive_dependency_tracer`.
- Audit pipeline does not call it for Swift Kits even though SwiftUI/Combine patterns are exactly its target.

**Root cause hypothesis:** `audit/discovery.py` enumerates only extractors that have an existing `:IngestRun` for the project. Extractors never invoked are invisible. There is no "expected vs actual" diff against the registry.

**Proposed fix:**
1. In `audit/discovery.py`, after gathering existing `:IngestRun` data, compute `registered − ran` and emit each missing entry as a `NOT_ATTEMPTED` blind-spot row with the suggested invocation command (matches current blind-spot format for known-not-run extractors).
2. Update `ingest_swift_kit.sh` `DEFAULT_EXTRACTORS` to explicitly include `reactive_dependency_tracer` for Swift Kits (alongside `arch_layer`, `error_handling_policy`, `crypto_domain_model`).
3. Add a defensive log warning when an extractor is in the registry but neither in DEFAULT_EXTRACTORS for any language profile nor reachable via `--extractors=`.

**Acceptance:**
- `audit/discovery.py` returns blind-spot rows for every registered extractor that has no run, even those not in the operator-curated list.
- Re-running `palace.audit.run(project="tron-kit")` lists `reactive_dependency_tracer` in §Blind Spots (or under §Reactive Dependencies once it runs).

---

#### B3: `coding_convention` and `localization_accessibility` not run for tron-kit

**Evidence:**
- Both registered (`palace.ingest.list_extractors()`).
- Neither in `:IngestRun` records for `tron-kit`.
- Both in audit report "Blind Spots" with the same "run command to populate" suggestion → confirms pipeline labelled them NOT_ATTEMPTED, not FAILED.

**Root cause:** `ingest_swift_kit.sh` `DEFAULT_EXTRACTORS` doesn't include them. Operator added `--extractors=...` override for the 12 audit-relevant set in CR's Phase 1.2 review of GIM-277, but those two were not in the list.

**Proposed fix:**
- Update `ingest_swift_kit.sh` `DEFAULT_EXTRACTORS` to include both for Swift Kit projects.
- Update `docs/runbooks/ingest-swift-kit.md` to reflect new default set.
- Per slice 2 (B4 / B5), audit report should call them out under their own sections (not just blind-spot listing).

**Acceptance:**
- Re-running `ingest_swift_kit.sh tron-kit` produces `:IngestRun` records for both.
- Audit report has populated §Coding convention and §Localization & accessibility (or explicit "no findings" with citation per AC pattern).

---

### Slice 2 — Failure visibility (FAILED vs NOT_ATTEMPTED)

#### B4: `public_api_surface` failure mislabeled as "blind spot"

**Evidence:**
- `:IngestRun {source="extractor.public_api_surface", group_id="project/tron-kit"}` exists with `success=false`.
- Audit report "Blind Spots" includes `public_api_surface` with text "run command to populate" — same wording used for never-run extractors.
- Operator cannot tell from the report that this extractor has a bug.

**Root cause:** `audit/discovery.py` treats `success=false` runs as equivalent to no-run. Blind-spot rendering is identical.

**Proposed fix:**
1. Discovery returns separate `failed_runs` and `not_attempted` sets.
2. Renderer adds a §Failed Extractors section (or sub-section under Blind Spots) with: extractor name, last failed run_id, error_code, error message, suggested next action.
3. Failed extractors do **not** appear under "Blind Spots" — they have their own clearly-named category.

**Acceptance:**
- Re-running tron-kit audit produces a §Failed Extractors entry for both `public_api_surface` and `cross_module_contract` (assuming the underlying bugs are not yet fixed).
- Report distinguishes "extractor never run for this project" from "extractor failed last run".

---

#### B5: `cross_module_contract` failure mislabeled as "blind spot"

**Evidence:** Identical pattern to B4 — `:IngestRun success=false` for `cross_module_contract` on `tron-kit`, but report labels it "blind spot".

**Fix:** Same fix as B4 (single change to discovery + renderer covers both).

**Acceptance:** Covered by B4 acceptance.

**Note:** B4 + B5 are visibility fixes only. The actual bugs causing `public_api_surface` and `cross_module_contract` to fail on `tron-kit` need separate investigation (out of scope for this spec; spawn from §Followups). Without the visibility fix they stay hidden indefinitely.

---

#### B6: `hotspot` 0-scan false-pass

**Evidence (per Opus N3):**
- Audit report §Code Hotspots: "scanned 0 files, found 0 issues".
- §Code Ownership lists 100+ Swift files with blame data.
- `lizard` supports Swift; not a tool limitation.
- `:IngestRun success=true` for hotspot — extractor thinks it succeeded.

**Root cause hypothesis:** Either
- (a) `git_history` extractor wrote `:Commit-[:TOUCHED]->:File` edges under one host path (`/repos-hs-stage/...` per staging mount) but `hotspot` reads under a different container path, or
- (b) `hotspot` stop-list / file-filter excluded everything, or
- (c) prerequisite-ordering: `hotspot` ran before `git_history` produced edges.

**Proposed investigation:**
1. Query `:File {group_id="project/tron-kit"}` count.
2. Query `(:Commit)-[:TOUCHED]->(:File) where File.group_id="project/tron-kit"` count.
3. Inspect `hotspot` extractor logs (`docker logs gimle-palace-palace-mcp-1 --since 2026-05-12T15:00`).
4. Identify which condition (a/b/c) hits.

**Proposed fix:**
- If (a): align mount path conventions; document required mount layout for hotspot's repo-walk; add a path-mismatch sanity check in extractor pre-flight (compare repo-walk count to `:File` count from prior extractor's output).
- If (b): audit stop-list, fix.
- If (c): add ordering rule in `ingest_swift_kit.sh` to run `git_history` before `hotspot`.

**Acceptance:**
- Re-running `palace.ingest.run_extractor(name="hotspot", project="tron-kit")` produces `scanned_files > 0` (at least 50 for tron-kit which has ~100 Swift files).
- `palace.code.find_hotspots(project="tron-kit", top_n=10)` returns at least 5 entries.
- Extractor success criterion strengthened: if `scanned_files==0` on a project that has `:File` count > 0, return `success=false` with error code `data_mismatch_zero_scan_with_files_present`.

---

### Slice 3 — Source-context annotation (Opus N4 + N5)

#### B7: No `library | example | test` distinction in findings

**Evidence (Opus N4):**
- Headline HIGH `private_key_string_storage` is at `iOS Example/Sources/Core/Manager.swift:79` — demo app, not the TronKit library.
- 8 of 34 `try_optional_swallow` and 2 of 2 `catch_only_logs` findings are in `iOS Example/...` — same problem.
- 25+ ownership entries in `iOS Example/` shown alongside library files with no distinction.

**Root cause:** `crypto_domain_model`, `error_handling_policy`, and `code_ownership` extractors record `file_path` for each finding but do not classify the path's source context. Renderer treats all findings identically.

**Proposed fix:**
1. Add `source_context: "library" | "example" | "test" | "other"` to the finding schema across all extractors that produce file-keyed findings (`crypto_domain_model`, `error_handling_policy`, `arch_layer`, `code_ownership`, `coding_convention`).
2. Classification function in `extractors/foundation/source_context.py`:
   - `example` if path matches `(^|/)(Example|Examples|Sample|Samples|Demo|Demos)(/|$)`.
   - `test` if path matches `(^|/)(Tests?|tests?|spec/)(/|$)` or filename ends `Tests.swift` / `_test.py` / `Test.kt`.
   - `library` if path is under conventional source dir (`Sources/`, `src/`, `lib/`).
   - `other` otherwise.
3. Renderer: per-section table gains a `source` column; severity in the executive summary is computed only over `source_context="library"` findings (example/test downgraded one severity level by default; configurable per extractor).
4. AC5 (false-positive rate) measurement also gains `library`-only filter.

**Acceptance:**
- Every finding in re-run tron-kit audit has a `source_context` value.
- Executive summary "1 HIGH" claim is computed only over library findings (so the `iOS Example/` HIGH no longer counts as v1 headline).
- §Crypto domain table has a `source` column visible to operators.
- Audit-report renderer documents the classification rules in the §Known Limitations appendix.

---

#### B8: `error_handling_policy` blanket `try?` MEDIUM noise (Opus N5)

**Evidence:**
- 34 of 43 findings (79%) are identical `try_optional_swallow` at MEDIUM.
- Most are convenience patterns (JSON parsing, UI display) — not critical-path issues.

**Proposed fix:** narrow severity rule:
- MEDIUM `try?` → only when in a key-derivation, signing, balance-arithmetic, or network-auth path (heuristic: file path matches `(?i)(signer|key|crypto|hd_wallet|hmac|sign|auth)` OR function name matches the same).
- LOW `try?` → in all other paths.
- Source-context (from B7) further demotes example/test findings.

This is a pragmatic tuning; final solution (per-call-site critical-path analysis) is post-v1.

**Acceptance:**
- Re-run tron-kit `try_optional_swallow` finding count: ≤10 MEDIUM (down from 34), with the remaining MEDIUMs in identifiable crypto/auth paths.
- LOW `try?` findings present but not on the §Executive Summary's top-3.
- Operator + BlockchainEngineer manual review of the new MEDIUM set hits the AC5 false-positive threshold (≤2 of top-5 FP).

---

### Slice 4 — Data quality + template gaps

#### B9: `dependency_surface` `@unresolved` versions (Opus N2)

**Evidence:** All 9 deps in §5 show `@unresolved` — no `Package.resolved` in `tron-kit` repo. Report makes no statement about this; operator can't tell whether `@unresolved` is the extractor failing or a data limitation.

**Proposed fix:**
1. `dependency_surface` extractor detects missing lockfile (Package.resolved / uv.lock / build.gradle "implementation 'group:artifact:VERSION'") and emits a `data_quality: missing_lockfile` warning in the per-run stats.
2. Renderer's §Dependency Surface template adds a "Data Quality" subhead that surfaces the warning: "No Package.resolved found in `tron-kit/`; declared constraints only. CVE/version-freshness checks unavailable."
3. The `@unresolved` placeholder is replaced with `<declared_constraint>` (e.g. `>= 5.0.0`) where possible.

**Acceptance:**
- Re-run tron-kit audit §5 shows declared constraints (not `@unresolved`) and the missing-lockfile warning.
- A test fixture with a real lockfile produces resolved versions correctly (regression guard for non-tron-kit projects like UW iOS app which DOES have Package.resolved).

---

#### B10: `arch_layer` module DAG missing when no rules declared (Opus N1)

**Evidence:** `templates/arch_layer.md` has a `Module DAG summary` block only in the `{% if findings %}` branch. The `{% else %}` (no rules → no findings) branch omits `summary_stats.module_count` entirely. AC3 borderline because of this.

**Proposed fix:** one-line template fix:

```diff
- (rules clean — no architecture violations)
+ (rules clean — {{ summary_stats.get("module_count", "?") }} modules indexed; no architecture violations)
```

Plus: when no rule file exists in the project (vs rules exist + clean), distinguish the two cases in the template; today both render identically.

**Acceptance:**
- Re-run tron-kit audit §1 shows `(no arch rules declared — N modules indexed in Neo4j)`.
- A future project with a rule file + zero violations renders as `(rules clean — N modules indexed; no architecture violations)`.

---

### Slice 5 — Renderer + section ordering

#### B11: `_SECTION_ORDER` incomplete (Opus N6)

**Evidence:** `audit/renderer.py:25-33` `_SECTION_ORDER` lists 7 extractors but excludes the 3 most audit-critical:
- `error_handling_policy`
- `arch_layer`
- `crypto_domain_model`

They fall through to the "extra extractors" catch-all and sort by severity AFTER the ordered set. In the committed report, they appear in the wrong position because of a separate severity-sort bug (pre-fix renderer).

**Proposed fix:** add the 3 to `_SECTION_ORDER` explicitly:

```python
_SECTION_ORDER = (
    "crypto_domain_model",       # NEW — top, security-critical
    "error_handling_policy",     # NEW — second, security-adjacent
    "arch_layer",                # NEW — third, structural
    "hotspot",
    "dead_symbol_binary_surface",
    "dependency_surface",
    "code_ownership",
    "cross_repo_version_skew",
    # ...rest unchanged
)
```

(Operator: validate exact ordering; current proposal puts security findings first.)

**Acceptance:**
- Re-run tron-kit audit produces sections in the new order.
- Section header table reflects the same.

---

## Sequencing

Recommend implementation order:

| Order | Slice | Reason |
|-------|-------|--------|
| 1 | Slice 1 (B1–B3) | Pipeline coverage gaps — pre-requisite for re-running smoke; otherwise every fix is unverifiable. |
| 2 | Slice 2 (B4–B6) | Failure visibility — without this, B5/B6 work is invisible. Slice 2 ALSO triggers ad-hoc investigation of public_api_surface / cross_module_contract / hotspot underlying bugs as follow-on PRs. |
| 3 | Slice 4 (B9–B10) | Small, easy data-quality wins. Cheap to land while harder slices brew. |
| 4 | Slice 3 (B7–B8) | Source-context — bigger schema change, ~2 weeks of work, needs careful testing per extractor. Schedule after pipeline correctness is restored (Slices 1+2). |
| 5 | Slice 5 (B11) | Pure renderer cosmetic. Last because it depends on B7 (source_context column in tables). |

**Parallelism:** Slices 1, 2, 4 can run in parallel (no shared files). Slice 3 + 5 are sequential.

## Acceptance criteria (whole spec)

Repeat tron-kit smoke with all fixes landed and validate:

1. **B1**: `palace.ingest.list_extractors()` returns `testability_di`; `:IngestRun` for `testability_di` on `tron-kit` exists with `success=true`.
2. **B2/B3**: Every registered extractor either appears in audit report sections or in `:NOT_ATTEMPTED` blind-spots with explicit rationale; `:IngestRun` for `coding_convention`, `localization_accessibility`, `reactive_dependency_tracer` on `tron-kit` exist.
3. **B4/B5**: `public_api_surface` and `cross_module_contract` failures appear under §Failed Extractors (not Blind Spots), with last run_id + error message.
4. **B6**: `palace.code.find_hotspots(project="tron-kit")` returns ≥5 entries; `scanned_files > 0` on the IngestRun.
5. **B7**: Every finding has `source_context`; Executive Summary HIGH count is computed only over library context; example app HIGH no longer appears in the top-3.
6. **B8**: `try_optional_swallow` MEDIUM count ≤10 on tron-kit; LOW handled separately.
7. **B9**: §Dependency Surface shows declared constraints + missing-lockfile warning, not `@unresolved`.
8. **B10**: §Architecture rendering shows `(no arch rules declared — N modules indexed)`.
9. **B11**: §Sections render in the new `_SECTION_ORDER` with security findings first.
10. **AC5 spec compliance**: operator + BlockchainEngineer perform manual review of top-5 in §1, §4, §7 (this is the Phase 4.1 step that was skipped on GIM-277; refer to PBUG-10 fix track).

## Followups (out of scope for this spec)

- **public_api_surface bug fix** — investigate why it failed on tron-kit (separate slice).
- **cross_module_contract bug fix** — same (separate slice).
- **testability_di postmortem** — if revert is found (B1 path 3), write `docs/postmortems/2026-05-13-GIM-242-testability-di-revert.md`.
- **AC5 process compliance** — codify Phase 4.1 operator + BlockchainEngineer top-5 review as required step (PBUG-10 / process track).
- **Hotspot mount-path convention** — once root cause is identified (B6 investigation), document in `docs/runbooks/ingest-swift-kit.md`.

## Verification plan

After each slice merges:

1. Re-run `palace.audit.run(project="tron-kit")` from iMac MCP.
2. Save new audit report to `docs/audit-reports/2026-05-13-tron-kit-rerun-after-<slice>.md`.
3. Diff against `docs/audit-reports/2026-05-12-tron-kit.md` to confirm the targeted change landed and nothing else regressed.
4. After all 5 slices merge: full Phase 4.1 QA re-validation with all 10 acceptance criteria; if pass, close the parent issue + spawn S4.2 (bitcoin-core smoke).

## Open questions

- **B1 root cause** — is it never-merged, or merge-then-reverted? Answer dictates fix complexity (cherry-pick vs revert investigation + postmortem).
- **B7 schema migration** — how do we handle existing `:Finding` nodes in Neo4j without `source_context`? Add as optional field, default `library` for back-compat? Or run a one-shot reclassification pass?
- **B8 heuristic regex** — the proposed list `(signer|key|crypto|hd_wallet|hmac|sign|auth)` is a first cut; needs review by BlockchainEngineer for completeness.
- **B11 ordering** — should `crypto_domain_model` come before `error_handling_policy` (severity-first) or after (alphabetical with intentional category grouping)? Trade-off: readability vs convention.

## Out of scope (explicit)

- Process bugs (PBUG-1..PBUG-10) — see `docs/BUGS.md`.
- New extractors — strictly fix existing.
- Replacing extractor heuristics with model/LLM analysis — post-v1.
- Major schema migrations beyond `source_context` field.
