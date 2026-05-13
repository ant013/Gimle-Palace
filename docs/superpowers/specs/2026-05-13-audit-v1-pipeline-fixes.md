# Audit-V1 pipeline fixes — post-S4.1-smoke retrospective

**Date:** 2026-05-13
**Status:** draft
**Owner:** Board (operator + Board Claude session)
**Predecessor:** GIM-277 audit report `docs/audit-reports/2026-05-12-tron-kit.md` (merged PR #151 commit `299102d`), Opus Phase 3.2 review with 6 NUDGEs (`d7c1bb08` thread).

## Problem

S4.1 smoke (GIM-277, tron-kit) produced the first real Audit-V1 report end-to-end. The smoke surfaced 12 pipeline-level bugs across **coverage**, **failure visibility**, **data quality**, **source-context**, and **renderer** dimensions. None blocked v1 close, but every one degrades report value and operator trust. This spec covers all 12 as a single coordinated repair effort, organised into 5 implementation slices so each fix can ship as its own PR.

## Goals

- Restore the missing `testability_di` extractor on `develop`.
- Define typed extractor statuses (`NOT_APPLICABLE` / `NOT_ATTEMPTED` / `RUN_FAILED` / `FETCH_FAILED` / `OK`) and render each distinctly — no silent misses, no failures masked as blind spots. Scope is **profile-matched auditable extractors** (i.e., those with `audit_contract()` and language fit for the project), not every registry entry.
- Fix the false-pass on `hotspot` 0-scan; identify and patch the actual cause (mount path or prerequisite ordering).
- Add `source_context: library | example | test | other` annotation to every finding; let the renderer differentiate severity / display by context.
- Close out Opus N1, N2, N3, N4, N5, N6 from GIM-277 Phase 3.2 review.
- Re-run S4.1 smoke (with explicit re-ingest of extractors, not just re-render) and validate all 10 acceptance criteria pass with NO false-positive HIGH (Opus N4) and NO 0-scan extractor (Opus N3).

## Non-goals

- **Process bugs** (PBUG-1..PBUG-10) — separate track in `docs/BUGS.md`, not in this spec.
- New extractors — only fix / recover existing ones.
- Stricter severity rules in `crypto_domain_model` beyond the source-context distinction (Opus N4 fix is sufficient for v1.1).
- Replacing the heuristic in `error_handling_policy` with full data-flow analysis (Opus N5 is a tuning fix, not a rewrite).
- Watchdog / paperclip-server improvements (separate track).

## Status taxonomy (foundation for B2, B4, B5)

Today `audit/discovery.py` collapses three different conditions into "blind spot":

1. Extractor exists in registry but has no `audit_contract()` → **not part of audit by design**.
2. Extractor has `audit_contract()` but never ran for this project → **never tried**.
3. Extractor ran with `success=false` → **bug to surface**.

The report wording ("run command to populate") fits only case 2. This spec replaces the binary `ok | blind-spot` taxonomy with five typed statuses:

| Status | Meaning | Rendering |
|---|---|---|
| `NOT_APPLICABLE` | Registered, no `audit_contract()` OR language mismatch with project profile (e.g. `symbol_index_python` on a Swift Kit). | Not surfaced in report at all — only in run-log / debug. |
| `NOT_ATTEMPTED` | Has `audit_contract()`, profile match, but no `:IngestRun` exists. | §Blind Spots row with `palace.ingest.run_extractor(...)` invocation hint. |
| `RUN_FAILED` | `:IngestRun.success=false` (extractor errored). | §Failed Extractors row with last `run_id`, `error_code`, error message, suggested next action. |
| `FETCH_FAILED` | `:IngestRun.success=true` but the fetcher (renderer-side Cypher) errored reading findings. | §Data-Quality Issues row with extractor, failed-query trace, suggestion. |
| `OK` | `:IngestRun.success=true` + fetcher OK. | Normal section in report. |

**Profile matching**: `extractors/foundation/profiles.py` defines which extractors apply to which language profile (e.g. `swift_kit`: { arch_layer, error_handling_policy, crypto_domain_model, …, but **not** symbol_index_python }). Project-language matching is a small lookup (already implied by `ingest_swift_kit.sh`'s curated `DEFAULT_EXTRACTORS`; this spec formalises it).

This taxonomy is implemented as part of **Slice 2** (failure visibility). Slices 1 + 3 + 4 + 5 depend on it.

---

## Inventory of concerns

12 items, grouped into 5 slices. Each item lists evidence + proposed fix.

### Slice 1 — Extractor coverage gaps

#### B1: `testability_di` extractor missing from `develop`

**Evidence:**
- `git log --all --oneline | grep -i GIM-242` shows commits `4c4c087`, `5cbd634`, `2465b79`, `a6eac2e`, `23a4d93` ("feat(GIM-242): add testability_di extractor" + fixes).
- `git ls-tree origin/develop services/palace-mcp/src/palace_mcp/extractors/` does **not** include a `testability_di/` directory.
- `docker exec gimle-palace-palace-mcp-1 ls /app/src/palace_mcp/extractors/` shows no `testability_di`.
- Roadmap rev4 (PR #146 merged 2026-05-13) lists GIM-242 as ✅ merged — **but the artefact is not on develop**.

**Root cause (verified 2026-05-13):** GIM-242 PR was **never opened, never merged, never reverted**. The feature branch `origin/feature/GIM-242-testability-di-pattern-extractor` (7 commits, last 2026-05-08) sits stale; develop has moved 39 commits ahead since the branch cut. Implementation chain reached Phase 3.1 (CR mechanical review rounds — last PE fix `23a4d93` is "fix(GIM-242): accept runner-shaped audit runs") but never advanced to Opus / QA / CTO merge. The work is complete on the FB (extractor + spec + plan + runbook + registry wiring + audit/fetcher integration ≈ 1000 LOC) — it just needs the back-half of the chain.

**Note on roadmap rev4 entry:** my own PR #146 marked GIM-242 as ✅ merged based on `git log --all` showing commits exist; that conflated "commits exist in the repo" with "merged to develop". Roadmap rev4 needs a correction (downgrade ✅ → 📋 for the GIM-242 row).

**Proposed fix (operator decision 2026-05-13 — continue GIM-242 chain):**
1. Re-activate the existing paperclip GIM-242 issue (if `status=done` was set incorrectly, reopen). Assign to **CTO** for Phase 3.1 re-check (verify state of feature branch on `2026-05-13` vs the last activity `2026-05-08`).
2. Forward-merge `origin/develop` into `feature/GIM-242-testability-di-pattern-extractor` to absorb the 39 develop-ahead commits and resolve any conflicts.
3. Open the PR from feature branch to develop.
4. Resume the chain from where it stopped: **Phase 3.2 OpusArchitectReviewer adversarial review → Phase 4.1 QAEngineer smoke → Phase 4.2 CTO merge**.
5. Fix roadmap rev4 GIM-242 row in a follow-up `docs(roadmap):` PR (✅ → 📋 while chain resumes, then re-✅ on merge).
6. After GIM-242 merges → testability_di extractor available; can be invoked on tron-kit smoke re-run for verification.

**Acceptance:**
- `git ls-tree origin/develop services/palace-mcp/src/palace_mcp/extractors/testability_di/` returns non-empty.
- `palace.ingest.list_extractors()` MCP call includes `testability_di`.
- Roadmap rev4 accurate.

---

#### B2: `reactive_dependency_tracer` invisible to audit pipeline

**Evidence:**
- `palace.ingest.list_extractors()` returns `reactive_dependency_tracer` (registered).
- Live runtime: `ext.audit_contract() is None` — extractor **has no audit_contract** override.
- `audit/run.py:63` filters `audit_extractors = {name for name, ext in extractor_registry.items() if ext.audit_contract() is not None}`. With `audit_contract=None`, reactive is excluded from `audit_extractors` set entirely.
- Result: `reactive_dependency_tracer` is invisible to discovery, doesn't appear in `:Blind Spots`, no `:IngestRun` exists for tron-kit.
- Runbook `docs/runbooks/reactive-dependency-tracer.md` confirms extractor expects pre-generated `reactive_facts.json` from a Swift helper outside `palace-mcp` runtime — without it, extractor emits only diagnostics, no findings.

**Root cause:** Two issues stack:
1. **No `audit_contract()` override** → status taxonomy classifies it as `NOT_APPLICABLE` (out of audit scope), so even after the taxonomy fix (slice 2) it stays hidden.
2. **Helper-generation prerequisite is out-of-band** → even if we wire it in, without `reactive_facts.json` in tron-kit repo, runs produce zero findings.

**Proposed fix (scoped for v1.1; helper-generation deferred):**

1. Add `audit_contract()` override to `reactive_dependency_tracer` so it joins `audit_extractors` set. Contract declares severity column, max findings cap, and severity mapper based on `:ReactiveDiagnostic` and `:ReactiveEffect` node properties.
2. Add Swift to the extractor's language profile (currently undocumented; verify it's reachable from `swift_kit` profile lookup).
3. Update `ingest_swift_kit.sh` `DEFAULT_EXTRACTORS` to include `reactive_dependency_tracer`.
4. With no `reactive_facts.json` present, extractor emits `swift_helper_unavailable` diagnostic — this is the **expected v1.1 state** until a separate slice ships the helper. Renderer surfaces this as `RUN_FAILED` with helpful error ("install Swift helper from `tools/reactive-helper/`; see runbook") under the taxonomy from §Status taxonomy.

**Deferred to a separate slice (out of scope here):**
- Swift helper to generate `reactive_facts.json` from real source. Will be a new slice in v1.2; tracked in §Followups.

**Acceptance:**
- `palace.audit.run(project="tron-kit")` after re-ingest: `reactive_dependency_tracer` appears in either §Failed Extractors (status=RUN_FAILED, reason=`swift_helper_unavailable`) or — if helper present — populated §Reactive Dependencies section.
- Status is no longer `NOT_APPLICABLE` (audit_contract() returns a contract).

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

**Evidence:** `templates/arch_layer.md` already has two no-findings branches:
- `{% if summary_stats.get("rules_declared") %}` — rules exist + zero violations → renders "rules clean" message
- `{% else %}` — no rule file → renders "No architecture rules declared" + Neo4j note + runbook pointer

**Neither branch renders `module_count`**, even though `module_count` IS rendered in the findings branch. So an operator reading the no-rules report can't tell whether anything was indexed at all (vs the extractor having silently failed).

**Verification needed:** does the `arch_layer` extractor populate `summary_stats.module_count` unconditionally, or only when findings exist? Per the spec inspection: contract appears to set `module_count` in `summary_stats` regardless of findings, but this **must be verified** in Phase 1.2 plan-first review before implementing the template fix.

**Proposed fix (extractor + template, not template-only):**

1. **Verify**: confirm `arch_layer/extractor.py` always emits `summary_stats={"module_count": N, "edge_count": M, "rules_declared": bool, "rule_source": str}` regardless of whether findings exist.
2. **Extractor patch** (if step 1 reveals a gap): always populate `module_count`, `rules_declared`, `rule_source` in `summary_stats`; never omit them.
3. **Fetcher patch** (`audit/fetcher.py`): ensure the no-findings rows carry the `summary_stats` through to the renderer.
4. **Template patch** (`templates/arch_layer.md`): add module-count line to both no-findings branches:

```jinja
{% if summary_stats.get("rules_declared") %}
No architecture violations found — {{ summary_stats.get("module_count", "?") }} modules indexed; all layer rules pass.
**Rule source:** `{{ summary_stats.get("rule_source", "unknown") }}`
{% else %}
No architecture rules declared — {{ summary_stats.get("module_count", "?") }} modules indexed in Neo4j (no rule evaluation possible).
...
{% endif %}
```

**Acceptance:**
- `arch_layer` extractor regression test: `summary_stats.module_count` present in **all** code paths (findings / rules-clean / no-rules).
- Re-run tron-kit audit §1 shows `No architecture rules declared — N modules indexed in Neo4j` with non-`?` N.
- A test fixture project with rule file + zero violations renders `No architecture violations found — N modules indexed; all layer rules pass`.

---

### Slice 5 — Renderer + section ordering

#### B11: section ordering — pinned-then-severity required (Opus N6)

**Evidence:** Two-part bug in `audit/renderer.py`:

1. `_SECTION_ORDER` (lines 25-33) lists 7 extractors but excludes the 3 most audit-critical: `error_handling_policy`, `arch_layer`, `crypto_domain_model`. They fall through to the "extra extractors" catch-all.
2. **Final pass globally sorts everything by severity**: `rendered_sections.sort(key=lambda t: SEVERITY_RANK[t[0]])` (line ~190). This **overrides** any order produced by the `_SECTION_ORDER`-then-extras assembly — adding the 3 missing extractors to the list would still not pin them at the top because the global sort rearranges.

In the committed tron-kit report, sections appear in a severity-sorted order that buries `crypto_domain_model` (HIGH section, semantically the most security-critical) deep down because the final sort doesn't know about audit-critical pinning.

**Proposed fix (renderer code change, not just data):**

Replace the global `sort` with a stable pinned-then-severity strategy:

```python
# 1. Render in pinned order using _SECTION_ORDER (security-first).
_SECTION_ORDER = (
    "crypto_domain_model",          # pinned-top: security
    "error_handling_policy",        # pinned-top: security
    "arch_layer",                   # pinned-top: structural
    "hotspot",                      # pinned-mid: code health
    "dead_symbol_binary_surface",
    "dependency_surface",
    "code_ownership",
    "cross_repo_version_skew",
    "cross_module_contract",
    "public_api_surface",
    "coding_convention",
    "localization_accessibility",
    "reactive_dependency_tracer",
    "testability_di",
    "hot_path_profiler",
)

# 2. Pinned sections in _SECTION_ORDER preserve list order, NOT severity-sorted.
# 3. Any extractor not in _SECTION_ORDER goes to a "remainder" bucket, sorted by severity.
# 4. Final order = pinned[in list order] + remainder[severity desc].
```

The pinned list **completely replaces** the global severity sort for known extractors. New / unknown extractors still sort by severity in the remainder bucket — preserves the paved-path property from Opus N6 commentary.

**Acceptance:**
- Re-run tron-kit audit §Sections (after taxonomy + reactive fixes): order is `crypto_domain_model` → `error_handling_policy` → `arch_layer` → … → `hot_path_profiler`. Verify by reading the `## ` headings sequentially.
- Test fixture: register a "test_extractor" not in `_SECTION_ORDER`; verify it lands in the remainder section sorted by its severity, after the last pinned extractor.

---

## Sequencing — serial, with file-ownership map

Slices share core pipeline files (`audit/discovery.py`, `audit/run.py`, `audit/renderer.py`, `audit/fetcher.py`, `ingest_swift_kit.sh`, several `templates/*.md`). Parallel parallel work creates merge conflicts and a moving target for the verification re-runs. **Run strictly serially**:

| Order | Slice | Why this order | Owns |
|-------|-------|---|---|
| 1 | Slice 2 — Failure visibility + status taxonomy (§Status taxonomy + B4 + B5 + B6) | Establishes the typed status model that every other slice depends on for reporting. Without it, slices 1/3/4/5 can't classify their output correctly. | `audit/discovery.py`, `audit/run.py`, `audit/renderer.py` (status logic), `extractors/foundation/profiles.py` (new), `audit/templates/blind_spots.md` (new) |
| 2 | Slice 1 — Coverage (B1 + B2 + B3) | Now that statuses exist, plug in the missing extractors. B1 (testability_di GIM-242 chain resumption), B2 (reactive `audit_contract()` + helper-unavailable diagnostic), B3 (DEFAULT_EXTRACTORS update). | `extractors/registry.py`, `extractors/testability_di/*` (recovered), `extractors/reactive_dependency_tracer/extractor.py` (audit_contract), `paperclips/scripts/ingest_swift_kit.sh` |
| 3 | Slice 4 — Data quality (B9 + B10) | Small extractor + template patches, no schema change. Cheap to land before the big slice 3. | `extractors/dependency_surface/*`, `extractors/arch_layer/extractor.py`, `audit/templates/dependency_surface.md`, `audit/templates/arch_layer.md` |
| 4 | Slice 3 — Source-context (B7 + B8) | Schema change across 5 extractors. Largest blast radius. Schedule after pipeline correctness is restored. | `extractors/foundation/source_context.py` (new), 5 extractor schemas, all related templates, finding-rendering code in renderer |
| 5 | Slice 5 — Pinned ordering (B11) | Pure renderer change. Run last because it depends on the taxonomy (slice 2 statuses) and source-context column (slice 3). | `audit/renderer.py` only |

**No parallelism**. Reasoning: slices 1, 2, 3, 4, 5 all touch `audit/renderer.py` and at least one of `audit/discovery.py` / `audit/fetcher.py` / `audit/run.py`. Per `feedback_parallel_team_protocol`, shared-file edits in parallel are forbidden.

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

`palace.audit.run()` is **render-only** — it reads existing `:IngestRun` data and renders. It does NOT re-execute extractors. Re-running audit alone after a slice merges will produce the same report as before, even if the underlying bugfix is correct, until extractors are re-ingested. Verification must therefore include explicit ingest steps.

### Per-slice (after each slice merges to develop)

Run the relevant subset based on what the slice touched:

1. **Wipe affected data** (if the slice touched extractor schema, particularly slice 3 source-context):
   ```cypher
   MATCH (n {group_id: "project/tron-kit"})
   WHERE labels(n) IN [["Finding"], ["CatchSite"], ["ErrorFinding"], ["ArchViolation"], ["CryptoFinding"], ["LocResource"], ["A11yIssue"]]
   DETACH DELETE n
   ```
2. **Re-ingest** the relevant extractors:
   ```bash
   bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios \
       --extractors=<comma-separated-list-from-the-slice>
   ```
3. **Re-render audit**:
   ```
   palace.audit.run(project="tron-kit")
   ```
4. Save artifact: `docs/audit-reports/2026-05-13-tron-kit-rerun-after-<slice>.md`.
5. Diff against `docs/audit-reports/2026-05-12-tron-kit.md` to confirm the targeted fix landed and nothing else regressed.

### Final (after all 5 slices merge)

Single full wipe + re-ingest + audit (operator-decision option γ from §Open questions):

```cypher
MATCH (n {group_id: "project/tron-kit"})
WHERE labels(n) IN [["Finding"], ["CatchSite"], ["ErrorFinding"], ["ArchViolation"], ["CryptoFinding"], ["LocResource"], ["A11yIssue"], ["IngestRun"]]
DETACH DELETE n
```

(Keep `:File`, `:Module`, `:Author`, `:Symbol*` — these are foundation data and don't carry the new schema.)

Then:

```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios   # uses NEW DEFAULT_EXTRACTORS
palace.audit.run(project="tron-kit")
```

Save final artifact `docs/audit-reports/2026-05-13-tron-kit-rerun-final.md` and run full Phase 4.1 QA re-validation against all 10 acceptance criteria. If pass → close the parent issue + spawn S4.2 (bitcoin-core smoke).

## Open questions

All four questions resolved during 2026-05-13 review (Gate Call NO-GO via Codex subagent + operator). Capturing decisions for future readers:

- **B1 root cause** — resolved 2026-05-13. GIM-242 was never opened as a PR. Feature branch is stale with completed work. Fix: resume Phase 3.2 → 4.1 → 4.2 chain (see B1 §Proposed fix). No revert / postmortem needed.
- **B7 schema migration** — resolved 2026-05-13 (operator decision: option γ). Single project-wide wipe + re-ingest at the END after all 5 slices land (see §Verification plan). Per-slice wipes would mix old/new schemas across reports (audit selects "latest successful run per extractor"). Schema migration tooling not built; field is required with no fallback default.
- **B8 heuristic regex** — resolved 2026-05-13. List `(signer|key|crypto|hd_wallet|hmac|sign|auth)` is a placeholder; **CR Phase 1.2 of slice 3 must dispatch BlockchainEngineer subagent for completeness check**. Candidate additions: `mnemonic`, `seed`, `pubkey`, `keystore`, `wallet`, `secp`, `ed25519`, `ripemd`, `address.*generate`, `wif`.
- **B11 ordering** — resolved 2026-05-13. Severity-first pinned ordering via _SECTION_ORDER list; renderer's global severity sort is replaced with pinned-then-severity strategy (see B11 §Proposed fix). Crypto/error/arch at top; everything else explicit-listed; unknown extractors sort severity-desc in remainder.

### New (post-Gate-Call) clarifications

- **B6 hotspot stop-list**: B6 §Proposed fix lists (a)/(b)/(c) hypotheses but doesn't pin one. Slice 4 Phase 1.2 must collect the actual root cause through the proposed investigation steps before coding the fix.
- **Status taxonomy field schema**: how are statuses stored — as a property on `:IngestRun` (`run_status: "ok"|"failed"|...`), or computed at discovery time from existing `success` + presence checks? Recommend computed at discovery (no schema change) → simpler.

## Out of scope (explicit)

- Process bugs (PBUG-1..PBUG-10) — see `docs/BUGS.md`.
- New extractors — strictly fix existing.
- Replacing extractor heuristics with model/LLM analysis — post-v1.
- Major schema migrations beyond `source_context` field.
