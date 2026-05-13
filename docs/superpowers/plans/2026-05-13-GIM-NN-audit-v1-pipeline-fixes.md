# Implementation plan — Audit-V1 pipeline fixes (5 slices)

**Date:** 2026-05-13
**Spec:** `docs/superpowers/specs/2026-05-13-audit-v1-pipeline-fixes.md` (rev2 — addresses Codex-subagent Gate Call NO-GO)
**Status:** draft, awaiting CR Phase 1.2 review
**Team:** Claude (CTO + CR + PythonEngineer + Opus + QA)

This plan splits into **5 paperclip issues** (placeholders `GIM-NN-1` through `GIM-NN-5`); each ships its own FB + PR. **Sequencing is strictly serial** — no two issues run in parallel because each touches `audit/renderer.py` or its neighbours (per spec §Sequencing).

Estimated wall-time (with serial chain + smoke verification between slices): **3-4 weeks total**, dominated by Slice 3 (source_context schema change).

## Slice mapping

| GIM-NN | Slice | Spec items | Tasks | Wall-time |
|--------|-------|-----------|-------|-----------|
| GIM-NN-1 | Slice 2 — Status taxonomy + failure visibility | B4, B5, B6, §Status taxonomy | 8 | ~1 week |
| GIM-NN-2 | Slice 1 — Coverage (testability_di + reactive + ingest defaults) | B1, B2, B3 | 6 (+ GIM-242 chain resumption sub-issue) | ~1 week |
| GIM-NN-3 | Slice 4 — Data quality (deps + arch_layer) | B9, B10 | 5 | ~3-5 days |
| GIM-NN-4 | Slice 3 — Source-context (annotation + try? tuning) | B7, B8 | 8 | ~1.5-2 weeks |
| GIM-NN-5 | Slice 5 — Pinned ordering renderer | B11 | 3 | ~1-2 days |

---

## GIM-NN-1 — Slice 2: Status taxonomy + failure visibility (foundation)

**Goal:** Introduce typed extractor statuses (`NOT_APPLICABLE` / `NOT_ATTEMPTED` / `RUN_FAILED` / `FETCH_FAILED` / `OK`) and render each distinctly. Fix `hotspot` 0-scan as part of the same slice since failure visibility is needed to surface the underlying issue.

**Why first:** Slices 2-5 all consume the taxonomy. Without it, "this extractor failed" is indistinguishable from "this extractor was never invoked".

**Branch:** `feature/GIM-NN-1-audit-status-taxonomy`

**Files owned:**
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py` (NEW)
- `services/palace-mcp/src/palace_mcp/audit/discovery.py`
- `services/palace-mcp/src/palace_mcp/audit/run.py`
- `services/palace-mcp/src/palace_mcp/audit/renderer.py` (status logic only — no ordering changes; that's Slice 5)
- `services/palace-mcp/src/palace_mcp/audit/templates/blind_spots.md` (split into 3 templates: blind_spots, failed_extractors, data_quality_issues)
- `services/palace-mcp/tests/audit/test_discovery_status_taxonomy.py` (NEW)
- `services/palace-mcp/tests/audit/test_renderer_status_sections.py` (NEW)

### Task 2.1 — Language profile lookup

**RED:** `tests/extractors/test_profiles.py::test_swift_kit_profile_returns_audit_extractors` fails — module doesn't exist.

**GREEN:** Implement `extractors/foundation/profiles.py` with:
```python
@dataclass(frozen=True)
class LanguageProfile:
    name: str  # "swift_kit" | "android_kit" | "python_service" | ...
    audit_extractors: frozenset[str]

PROFILES = {
    "swift_kit": LanguageProfile("swift_kit", frozenset({
        "arch_layer", "code_ownership", "coding_convention", "crypto_domain_model",
        "cross_module_contract", "cross_repo_version_skew", "dead_symbol_binary_surface",
        "dependency_surface", "error_handling_policy", "hot_path_profiler", "hotspot",
        "localization_accessibility", "public_api_surface", "reactive_dependency_tracer",
        "testability_di",  # once GIM-NN-2 lands; until then absent
    })),
    "android_kit": ...,  # post-tron-kit work; deferred
}

def resolve_profile(project_slug: str, driver) -> LanguageProfile:
    """Look up :Project.language_profile or infer from manifest."""
```

**Refactor:** N/A.

**Commit:** `feat(extractors): foundation/profiles.py — language → audit-extractor mapping`

### Task 2.2 — Discovery returns typed statuses

**RED:** `tests/audit/test_discovery_status_taxonomy.py::test_discovery_classifies_each_extractor` — 5 fixture extractors (NOT_APPLICABLE / NOT_ATTEMPTED / RUN_FAILED / FETCH_FAILED / OK) and asserts each classified correctly.

**GREEN:** Modify `audit/discovery.py`:
```python
@dataclass(frozen=True)
class ExtractorStatus:
    extractor_name: str
    status: Literal["NOT_APPLICABLE", "NOT_ATTEMPTED", "RUN_FAILED", "FETCH_FAILED", "OK"]
    last_run_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None

async def discover_extractor_statuses(driver, project, profile, registry) -> dict[str, ExtractorStatus]:
    profile_set = profile.audit_extractors  # what SHOULD run
    registry_set = set(registry.keys())     # what IS registered
    
    # For each registered extractor not in profile → NOT_APPLICABLE
    # For each in-profile extractor → check :IngestRun
    # If no IngestRun → NOT_ATTEMPTED
    # If IngestRun.success=False → RUN_FAILED
    # If IngestRun.success=True → fetcher-side test resolves OK or FETCH_FAILED
```

**Refactor:** Existing `find_latest_runs()` becomes private; `discover_extractor_statuses` is the new public API.

**Commit:** `feat(audit): typed extractor statuses (NOT_APPLICABLE / NOT_ATTEMPTED / RUN_FAILED / FETCH_FAILED / OK)`

### Task 2.3 — run.py consumes new discovery

**RED:** `tests/audit/test_run_uses_status_taxonomy.py::test_render_called_with_status_buckets` — mock renderer, verify it receives 5 separate buckets (or one dict keyed by status).

**GREEN:** `audit/run.py:60-90` updated to:
1. Call `discover_extractor_statuses(...)` instead of `find_latest_runs()`.
2. Pass status taxonomy to renderer.
3. Skip `audit_extractors = {... if audit_contract() is not None}` filter (replaced by profile lookup).

**Commit:** `feat(audit): run.py consumes typed statuses from discovery`

### Task 2.4 — Renderer splits Blind Spots into 3 sections

**RED:** `tests/audit/test_renderer_status_sections.py::test_failed_extractors_render_separately` — fixture with one RUN_FAILED + one NOT_ATTEMPTED + one FETCH_FAILED; assert 3 separate report sections produced.

**GREEN:** Modify `audit/renderer.py` to emit:
- §Failed Extractors (RUN_FAILED bucket) — extractor name, last run_id, error_code, error message, "next action"
- §Data-Quality Issues (FETCH_FAILED bucket) — extractor name, failed query trace, suggestion
- §Blind Spots (NOT_ATTEMPTED bucket) — same as today, with `palace.ingest.run_extractor(...)` hint

NOT_APPLICABLE doesn't render — log-only.

Update `audit/templates/`: split `blind_spots.md` into three: `failed_extractors.md`, `data_quality_issues.md`, `blind_spots.md`.

**Commit:** `feat(audit/renderer): split Blind Spots into Failed / Data-Quality / Blind-Spots sections`

### Task 2.5 — B6 hotspot 0-scan investigation

**Investigation tasks (no test/impl yet — discovery work):**

1. Query Neo4j on iMac:
   ```cypher
   MATCH (f:File {group_id: "project/tron-kit"}) RETURN count(f) AS file_count
   MATCH (c:Commit {group_id: "project/tron-kit"})-[t:TOUCHED]->(f:File) RETURN count(t) AS touched_count
   ```
2. `docker logs gimle-palace-palace-mcp-1 --since 2026-05-12T15:00 | grep -iE "hotspot|lizard" | head -50`
3. Check `extractors/hotspot/` source code for stop-list rules vs Swift file paths.

**Output:** Phase 1.2 plan-first review must include findings before approving Task 2.6.

### Task 2.6 — B6 hotspot fix (depends on 2.5 findings)

**RED:** `tests/extractors/test_hotspot_scan_zero_files_with_files_present_fails.py` — fixture with `:File` count > 0 but mount path mismatch, assert extractor returns `success=False, error_code="data_mismatch_zero_scan_with_files_present"`.

**GREEN:** Based on root cause from 2.5:
- (a) mount path mismatch → align path conventions + pre-flight sanity check
- (b) stop-list overzealous → fix stop-list
- (c) ordering bug → enforce `git_history` before `hotspot` in `ingest_swift_kit.sh`

**Commit:** `fix(extractors/hotspot): <root cause-specific message>`

### Task 2.7 — Hotspot tightened success criterion

**RED:** `tests/extractors/test_hotspot_zero_scan_with_files_present_fails_loudly.py` — same fixture as 2.6 but on the WRONG path (extractor previously passed); assert it now fails with the new error code.

**GREEN:** In `extractors/hotspot/extractor.py`:
```python
if scanned_files == 0 and file_count_from_neo4j > 0:
    return ExtractorStats(success=False, error_code="data_mismatch_zero_scan_with_files_present", ...)
```

**Commit:** `fix(extractors/hotspot): fail loudly on 0-scan with files-present mismatch`

### Task 2.8 — End-to-end regression test

**Test:** `tests/audit/test_smoke_taxonomy_e2e.py` — fixture project with one of each status type; full `palace.audit.run()` produces report with all 3 sections (failed / data-quality / blind-spots) + §Sections + §Executive Summary correctly classifying findings.

**Commit:** `test(audit): e2e regression for status taxonomy`

---

## GIM-NN-2 — Slice 1: Coverage (testability_di + reactive + DEFAULT_EXTRACTORS)

**Goal:** Plug all in-profile extractors. Depends on Slice 2 statuses being live.

**Branch:** `feature/GIM-NN-2-audit-coverage-gaps`

**Files owned:**
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py` (adds `testability_di`, `reactive_dependency_tracer` to `swift_kit` once they're audit-ready)
- `services/palace-mcp/src/palace_mcp/extractors/reactive_dependency_tracer/extractor.py` (audit_contract override)
- `paperclips/scripts/ingest_swift_kit.sh` (DEFAULT_EXTRACTORS)
- `docs/runbooks/ingest-swift-kit.md`
- `docs/roadmap.md` (correct GIM-242 row ✅ → 📋 then back to ✅ at chain close)

### Task 1.1 — GIM-242 chain resumption (sub-issue)

This is a chain-resumption, not a code task. Spawn a separate paperclip issue:
- **Title:** "GIM-NN-2.1: resume GIM-242 testability_di chain to merge"
- **Initial assignee:** CTO Phase 1.1
- **Branch:** `feature/GIM-242-testability-di-pattern-extractor` (already exists, stale)
- **First action:** forward-merge `origin/develop` into the branch, resolve conflicts (39 commits ahead).
- **Then:** Phase 3.2 (Opus) → Phase 4.1 (QA, including a real-tron-kit smoke) → Phase 4.2 (CTO merge).
- **Roadmap update:** in PR description, include `docs(roadmap):` change ✅ → 📋 first, then ✅ at merge.

Acceptance: `git ls-tree origin/develop services/palace-mcp/src/palace_mcp/extractors/testability_di/` returns non-empty; registered in `registry.py` on develop.

### Task 1.2 — reactive_dependency_tracer audit_contract

**RED:** `tests/extractors/reactive_dependency_tracer/test_audit_contract_present.py::test_extractor_has_audit_contract` — calls `extractor.audit_contract()`, asserts non-None and validates schema (severity_column, max_findings, severity_mapper present).

**GREEN:** In `extractors/reactive_dependency_tracer/extractor.py`:
```python
def audit_contract(self) -> AuditContract | None:
    return AuditContract(
        severity_column="severity",
        max_findings=50,
        severity_mapper=_reactive_severity_mapper,
        # ...
    )
```

Where `_reactive_severity_mapper` distinguishes:
- `swift_helper_unavailable` diagnostic → INFORMATIONAL (treated as "needs setup")
- Real reactive findings (effect leaks, cycle warnings) → MEDIUM/HIGH per finding props

**Commit:** `feat(extractors/reactive_dependency_tracer): add audit_contract for status taxonomy participation`

### Task 1.3 — Add testability_di + reactive_dependency_tracer to swift_kit profile

**RED:** `tests/extractors/test_profiles.py::test_swift_kit_includes_new_extractors` — asserts both are in `PROFILES["swift_kit"].audit_extractors`.

**GREEN:** Update `extractors/foundation/profiles.py` adding both names. Verify `testability_di` import works (depends on Task 1.1 having merged GIM-242).

**Commit:** `feat(extractors/foundation/profiles): add testability_di + reactive_dependency_tracer to swift_kit`

### Task 1.4 — ingest_swift_kit.sh DEFAULT_EXTRACTORS

**RED:** `tests/scripts/test_ingest_swift_kit_defaults.py::test_default_extractors_includes_audit_critical` — bash-spec test, asserts DEFAULT_EXTRACTORS contains all 15 swift_kit profile members.

**GREEN:** Update `paperclips/scripts/ingest_swift_kit.sh`:
```bash
DEFAULT_EXTRACTORS="${PALACE_SWIFT_KIT_EXTRACTORS:-symbol_index_swift,git_history,dependency_surface,arch_layer,error_handling_policy,crypto_domain_model,hotspot,code_ownership,cross_repo_version_skew,public_api_surface,cross_module_contract,dead_symbol_binary_surface,coding_convention,localization_accessibility,reactive_dependency_tracer,testability_di,hot_path_profiler}"
```

**Commit:** `feat(scripts/ingest-swift-kit): default-extractor list now matches swift_kit profile`

### Task 1.5 — Update ingest-swift-kit runbook

**Test:** N/A (docs-only).

**Impl:** Update `docs/runbooks/ingest-swift-kit.md` to reflect new defaults.

**Commit:** `docs(runbooks/ingest-swift-kit): document expanded default extractor set`

### Task 1.6 — Verification

Re-run extractors on tron-kit (no source-context yet — slice 4 will reset this anyway):
```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios
palace.audit.run(project="tron-kit")
```

Save artifact to `docs/audit-reports/2026-05-13-tron-kit-after-slice-1.md`. Verify:
- `testability_di` appears as section (or RUN_FAILED with reason).
- `reactive_dependency_tracer` appears as RUN_FAILED with `swift_helper_unavailable` diagnostic.
- `coding_convention` + `localization_accessibility` present with their data (or RUN_FAILED if they have unfixed bugs).

---

## GIM-NN-3 — Slice 4: Data quality (deps + arch_layer)

**Goal:** Close Opus N1 + N2 small-template-side fixes.

**Branch:** `feature/GIM-NN-3-audit-data-quality`

**Files owned:**
- `services/palace-mcp/src/palace_mcp/extractors/dependency_surface/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/extractor.py`
- `services/palace-mcp/src/palace_mcp/audit/templates/dependency_surface.md`
- `services/palace-mcp/src/palace_mcp/audit/templates/arch_layer.md`
- `services/palace-mcp/src/palace_mcp/audit/fetcher.py` (if `summary_stats` plumbing needs change for arch_layer no-rules path)

### Task 4.1 — dependency_surface lockfile detection

**RED:** `tests/extractors/dependency_surface/test_lockfile_warning.py::test_missing_package_resolved_emits_warning` — fixture `Package.swift` without `Package.resolved`; assert run output `summary_stats["missing_lockfile"] = True`.

**GREEN:** In `extractors/dependency_surface/extractor.py`: check for `Package.resolved` / `uv.lock` / `gradle.lockfile`; set `summary_stats["missing_lockfile"]` + relevant field per language.

**Commit:** `feat(extractors/dependency_surface): emit missing_lockfile warning in summary_stats`

### Task 4.2 — dependency_surface template Data Quality block

**RED:** `tests/audit/test_dependency_surface_template.py::test_missing_lockfile_renders_warning` — fixture with `summary_stats.missing_lockfile=True`; assert rendered markdown has "No Package.resolved found" warning text.

**GREEN:** Update `audit/templates/dependency_surface.md`:
```jinja
{% if summary_stats.get("missing_lockfile") %}
### ⚠ Data Quality

No `Package.resolved` (or `uv.lock` / `gradle.lockfile`) found in `{{ project }}/`; declared constraints only. CVE / version-freshness checks unavailable.

{% endif %}
```

Also: replace `@unresolved` placeholder with `<declared_constraint>` in the deps table when no lockfile.

**Commit:** `feat(audit/templates/dependency_surface): data-quality warning + declared-constraint fallback`

### Task 4.3 — arch_layer summary_stats unconditional

**Investigation first:** verify the current claim that `summary_stats.module_count` is missing in no-findings paths. Read `extractors/arch_layer/extractor.py` and trace the no-findings code path.

**RED:** `tests/extractors/arch_layer/test_summary_stats_always_populated.py::test_no_rules_path_includes_module_count` — fixture with module structure but no rule file; assert run output `summary_stats["module_count"] > 0`, `summary_stats["rules_declared"] == False`, `summary_stats["rule_source"] in (None, "")`.

**GREEN:** Update `extractors/arch_layer/extractor.py` to always populate `module_count`, `edge_count`, `rules_declared`, `rule_source` in `summary_stats` regardless of findings.

**Commit:** `fix(extractors/arch_layer): always populate summary_stats fields, regardless of findings`

### Task 4.4 — arch_layer template no-rules branch

**RED:** `tests/audit/test_arch_layer_template.py::test_no_rules_branch_renders_module_count` — fixture with `summary_stats.module_count=12, rules_declared=False`; assert rendered markdown contains `12 modules indexed`.

**GREEN:** Patch `audit/templates/arch_layer.md`:
```jinja
{% if not findings %}
{% if summary_stats.get("rules_declared") %}
No architecture violations found — {{ summary_stats.get("module_count", "?") }} modules indexed; all layer rules pass.
**Rule source:** `{{ summary_stats.get("rule_source", "unknown") }}`
{% else %}
No architecture rules declared — {{ summary_stats.get("module_count", "?") }} modules indexed in Neo4j (no rule evaluation possible).
{# ...existing helpful pointer #}
{% endif %}
{% else %}
{# existing findings branch unchanged #}
{% endif %}
```

**Commit:** `feat(audit/templates/arch_layer): render module_count in no-rules + clean-rules branches`

### Task 4.5 — Verification

Re-run extractors on tron-kit:
```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios \
    --extractors=dependency_surface,arch_layer
palace.audit.run(project="tron-kit")
```

Save to `docs/audit-reports/2026-05-13-tron-kit-after-slice-4.md`. Verify:
- §Dependency Surface shows declared constraints + "No Package.resolved found" warning.
- §Architecture rendering shows `(no arch rules declared — N modules indexed)`.

---

## GIM-NN-4 — Slice 3: Source-context annotation (B7 + B8)

**Goal:** Add `source_context: library | example | test | other` to findings; render it; tune `error_handling_policy` `try?` severity. Biggest scope; ~2 weeks.

**Branch:** `feature/GIM-NN-4-audit-source-context`

**Files owned (5 extractors + foundation + templates + renderer):**
- `services/palace-mcp/src/palace_mcp/extractors/foundation/source_context.py` (NEW)
- `services/palace-mcp/src/palace_mcp/extractors/crypto_domain_model/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/code_ownership/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/coding_convention/extractor.py`
- 5 templates in `audit/templates/` to render the source column
- `audit/renderer.py` for executive-summary library-only count

### Task 3.1 — source_context classifier

**RED:** `tests/extractors/foundation/test_source_context.py::test_classifies_paths` — table-driven:
- `Sources/TronKit/Foo.swift` → `library`
- `iOS Example/Sources/Manager.swift` → `example`
- `Tests/FooTests.swift` → `test`
- `Scripts/build.sh` → `other`

**GREEN:** Implement `extractors/foundation/source_context.py`:
```python
def classify(path: str) -> Literal["library", "example", "test", "other"]:
    p = path.replace("\\", "/")
    if re.search(r"(^|/)(Example|Examples|Sample|Samples|Demo|Demos)(/|$)", p):
        return "example"
    if re.search(r"(^|/)(Tests?|tests?|spec)(/|$)", p) or re.search(r"Test(s)?\.swift$|_test\.py$|Test\.kt$", p):
        return "test"
    if re.search(r"(^|/)(Sources|src|lib|libs)(/|$)", p):
        return "library"
    return "other"
```

**Commit:** `feat(extractors/foundation/source_context): library/example/test/other path classifier`

### Task 3.2 — crypto_domain_model emits source_context

**RED:** `tests/extractors/crypto_domain_model/test_finding_includes_source_context.py::test_each_finding_classified` — fixture project with paths in each context; assert every emitted `:CryptoFinding` has the field set.

**GREEN:** In `extractors/crypto_domain_model/extractor.py`, call `classify(finding.file_path)` and set `finding.source_context`.

**Commit:** `feat(extractors/crypto_domain_model): emit source_context per finding`

### Task 3.3 — error_handling_policy emits source_context + B8 try? tuning

**RED:**
- `tests/extractors/error_handling_policy/test_finding_includes_source_context.py` — same shape as 3.2.
- `tests/extractors/error_handling_policy/test_try_optional_severity_critical_path.py::test_crypto_path_yields_medium` — fixture finding in `Sources/TronKit/Crypto/Signer.swift`, assert severity == MEDIUM.
- `tests/extractors/error_handling_policy/test_try_optional_severity_convenience_path.py::test_ui_path_yields_low` — fixture in `Sources/TronKit/UI/View.swift`, assert severity == LOW.

**GREEN:**
1. Set `source_context` on each finding.
2. Add critical-path detection: file or function name matches regex `(?i)(signer|key|crypto|hd_wallet|hmac|sign|auth)` → MEDIUM `try?`; otherwise LOW.
3. **B8 placeholder note:** the regex list is the **starting point**. CR Phase 1.2 review of this PR MUST dispatch a BlockchainEngineer subagent (per spec §Open questions B8) to validate the regex list. Candidate additions to evaluate: `mnemonic|seed|pubkey|keystore|wallet|secp|ed25519|ripemd|address.*generate|wif`. PE adjusts the regex per BlockchainEng recommendation before pushing for Opus.

**Commit:** `feat(extractors/error_handling_policy): source_context + try-optional critical-path severity tuning`

### Task 3.4 — arch_layer + code_ownership + coding_convention emit source_context

**RED:** Same shape as 3.2 for each of the three extractors.

**GREEN:** Same shape as 3.2.

**Commit:** `feat(extractors): source_context per finding in arch_layer + code_ownership + coding_convention`

### Task 3.5 — Renderer adds `source` column to per-section tables

**RED:** `tests/audit/test_renderer_source_column.py::test_finding_table_has_source_column` — fixture findings with mixed contexts; assert rendered table has 4 cols including `source`.

**GREEN:** Update `audit/templates/{crypto_domain_model,error_handling_policy,arch_layer,code_ownership,coding_convention}.md` to include the column.

**Commit:** `feat(audit/templates): add source column to finding tables`

### Task 3.6 — Executive summary library-only count

**RED:** `tests/audit/test_executive_summary_library_only.py::test_high_count_excludes_example_paths` — fixture with 1 HIGH in library + 1 HIGH in example; assert executive summary says "1 HIGH" (library-only), not "2 HIGH".

**GREEN:** In `audit/renderer.py` executive-summary computation, filter to `f["source_context"] == "library"` before computing max severity / top-3.

**Commit:** `feat(audit/renderer): executive summary HIGH count is library-only`

### Task 3.7 — Wipe + re-ingest test fixture

**Test:** `tests/audit/test_smoke_source_context_e2e.py` — using a synthetic project fixture with both library and example findings, run full audit; assert headline severity excludes example HIGHs.

**Commit:** `test(audit): e2e source_context library-only summary regression`

### Task 3.8 — Verification

Final wipe + full re-ingest per spec §Verification:
```cypher
MATCH (n {group_id: "project/tron-kit"})
WHERE labels(n) IN [["Finding"], ["CatchSite"], ["ErrorFinding"], ["ArchViolation"], ["CryptoFinding"], ["LocResource"], ["A11yIssue"]]
DETACH DELETE n
```

```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios
palace.audit.run(project="tron-kit")
```

Save to `docs/audit-reports/2026-05-13-tron-kit-after-slice-3.md`. Verify:
- Every finding row has source column populated.
- §Executive Summary HIGH count excludes example app findings.
- `try_optional_swallow` MEDIUM count on tron-kit ≤ 10 (down from 34).

---

## GIM-NN-5 — Slice 5: Pinned-then-severity ordering

**Goal:** Replace renderer's global severity sort with pinned-then-severity strategy.

**Branch:** `feature/GIM-NN-5-audit-pinned-ordering`

**Files owned:**
- `services/palace-mcp/src/palace_mcp/audit/renderer.py` only.

### Task 5.1 — Replace global severity sort

**RED:**
- `tests/audit/test_renderer_pinned_ordering.py::test_pinned_first_severity_remainder` — fixture with all 15+ extractors mixed in severity; assert section order matches `_SECTION_ORDER` list verbatim for in-list sections; unknown extractor lands after the last pinned and sorts by severity in remainder bucket.
- `tests/audit/test_renderer_no_global_severity_sort.py::test_crypto_pinned_top_despite_info_severity` — fixture where crypto_domain has only INFORMATIONAL but error_handling has HIGH; assert crypto is still first (pinned in list) and error_handling is second.

**GREEN:** Replace the final `rendered_sections.sort(key=lambda t: SEVERITY_RANK[t[0]])` with the pinned-then-severity strategy from spec B11. Roughly:
```python
pinned = []
remainder = []
for sec_name in _SECTION_ORDER:
    if sec_name in sections_by_name:
        pinned.append((sec_name, sections_by_name[sec_name]))
for sec_name, rendered in sections_by_name.items():
    if sec_name not in _SECTION_ORDER_SET:
        remainder.append((sec_name, rendered))
remainder.sort(key=lambda t: SEVERITY_RANK[t[1][0]])  # severity-desc fallback
ordered_sections = [r for _, (_, r) in pinned + remainder]
```

(Exact implementation per Phase 1.2 plan-first review.)

**Commit:** `refactor(audit/renderer): pinned-then-severity ordering replaces global severity sort`

### Task 5.2 — Update _SECTION_ORDER full list

**RED:** Same test as 5.1 verifying the new list.

**GREEN:** Replace `_SECTION_ORDER` with full 15-entry list from spec §B11:
```python
_SECTION_ORDER = (
    "crypto_domain_model",
    "error_handling_policy",
    "arch_layer",
    "hotspot",
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
```

**Commit:** `feat(audit/renderer): _SECTION_ORDER pins all 15 audit-critical extractors`

### Task 5.3 — Final verification — full smoke re-run

After all 5 slices merge:

**Wipe:**
```cypher
MATCH (n {group_id: "project/tron-kit"})
WHERE labels(n) IN [["Finding"], ["CatchSite"], ["ErrorFinding"], ["ArchViolation"],
                    ["CryptoFinding"], ["LocResource"], ["A11yIssue"], ["IngestRun"]]
DETACH DELETE n
```

(Keep `:File`, `:Module`, `:Author`, `:Symbol*` — foundation data.)

**Re-ingest + render:**
```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios
palace.audit.run(project="tron-kit")
```

Save final artifact `docs/audit-reports/2026-05-13-tron-kit-final.md`.

Validate full Phase 4.1 QA acceptance against all 10 spec ACs:

1. **B1**: `palace.ingest.list_extractors()` returns `testability_di`; `:IngestRun` for it with `success=true`.
2. **B2/B3**: `reactive_dependency_tracer` appears in §Failed Extractors (status=RUN_FAILED, reason=`swift_helper_unavailable`) or in OK section if helper present. `coding_convention` + `localization_accessibility` produce sections (or RUN_FAILED with bug-trace).
3. **B4/B5**: `public_api_surface` and `cross_module_contract` failures (if not yet fixed) in §Failed Extractors with last run_id + error_code.
4. **B6**: `palace.code.find_hotspots(project="tron-kit")` returns ≥5; `scanned_files > 0` in IngestRun.
5. **B7**: Every finding has `source_context`; Executive Summary HIGH count = library-only.
6. **B8**: `try_optional_swallow` MEDIUM count ≤ 10 on tron-kit.
7. **B9**: §Dependency Surface shows declared constraints + missing-lockfile warning.
8. **B10**: §Architecture rendering shows `(no arch rules declared — N modules indexed)` with non-`?` N.
9. **B11**: §Sections render `crypto_domain_model` → `error_handling_policy` → `arch_layer` → … (verify by reading `## ` headings).
10. **AC5 spec compliance**: operator + BlockchainEngineer manual review of top-5 in §1/§4/§7 — this requires invocation by operator as the human gate (PBUG-10 / process track).

If all 10 pass → spawn S4.2 (bitcoin-core) audit smoke.

---

## Plan-first review checklist (CR Phase 1.2)

CR must verify before APPROVE:

- [ ] Every task above has explicit RED test, GREEN impl, and Commit.
- [ ] No task overlaps shared files with another task in the same slice (file-ownership map per spec §Sequencing).
- [ ] B8 regex placeholder is flagged for BlockchainEngineer subagent dispatch at Phase 1.2 of GIM-NN-4 (slice 3).
- [ ] B6 investigation (Task 2.5) explicitly precedes Task 2.6 fix — root cause must be identified, not guessed.
- [ ] Final verification (Slice 5 / Task 5.3) wipes the right node labels and re-ingests via `ingest_swift_kit.sh`, NOT `palace.audit.run` alone.
- [ ] Each slice ships its own PR; serial merge order = 1 → 2 → 3 → 4 → 5 (numbered as in this plan, which is reordered from the spec's slice numbering for clarity: spec Slice 2 = plan GIM-NN-1, spec Slice 1 = plan GIM-NN-2, spec Slice 4 = plan GIM-NN-3, spec Slice 3 = plan GIM-NN-4, spec Slice 5 = plan GIM-NN-5).

## Phase chain reminder (per slice)

Standard Gimle 7-phase. Special notes per this plan:

- **Phase 1.2 of GIM-NN-4 (Slice 3)**: CR MUST dispatch BlockchainEngineer subagent for B8 regex completeness review before approving.
- **Phase 2.5 of GIM-NN-1 (Slice 2)**: Investigation task — PE produces a write-up before Task 2.6 coding starts.
- **Phase 4.1 of every slice**: QA performs the slice-specific Verification step from the relevant Slice §Verification subsection. Real `:IngestRun` against tron-kit, real audit report artifact, real diff vs prior. No mocks.
- **Phase 4.2 of every slice**: CTO merges only after the slice's verification artifact exists in `docs/audit-reports/` on the FB.
- **After GIM-NN-5 merge**: operator + BlockchainEngineer perform AC5 manual review (per spec §Acceptance criteria item 10).
