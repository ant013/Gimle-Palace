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

### Task 2.0 — Project-language-profile backfill + manifest inference

**Addresses Gate Call C1.**

**RED:**
- `tests/extractors/test_profiles.py::test_register_project_accepts_language_profile` — calls `palace.memory.register_project(slug, language_profile="swift_kit")`, asserts node `:Project {slug, language_profile: "swift_kit"}` exists.
- `tests/extractors/test_profiles.py::test_resolve_profile_explicit_wins` — fixture with `:Project.language_profile="swift_kit"`, no manifest; assert `resolve_profile` returns swift_kit.
- `tests/extractors/test_profiles.py::test_resolve_profile_manifest_inference` — fixture with `Package.swift` but no `:Project.language_profile`; assert resolved to `swift_kit`.
- `tests/extractors/test_profiles.py::test_resolve_profile_unknown_raises` — fixture with neither; assert `unknown_language_profile` error.

**GREEN:**

1. Extend `palace.memory.register_project` MCP tool to accept `language_profile` field (Pydantic schema update + Cypher MERGE).
2. Backfill migration: one-shot Cypher in `services/palace-mcp/scripts/backfill_language_profile.cypher`:
   ```cypher
   MATCH (p:Project) WHERE p.slug IN ['gimle','tron-kit','uw-android','uw-ios','uw-ios-mini','uw-android-mini','oz-v5-mini']
   SET p.language_profile = CASE p.slug
     WHEN 'gimle' THEN 'python_service'
     WHEN 'tron-kit' THEN 'swift_kit'
     WHEN 'uw-ios' THEN 'swift_kit'
     WHEN 'uw-ios-mini' THEN 'swift_kit'
     WHEN 'uw-android' THEN 'android_kit'
     WHEN 'uw-android-mini' THEN 'android_kit'
     WHEN 'oz-v5-mini' THEN 'python_service'
     ELSE p.language_profile END
   ```
   Run as part of slice-2 deploy script with idempotency guard.

3. Manifest inference rules table in `profiles.py`:
   ```python
   _MANIFEST_RULES = (
       ("Package.swift", "swift_kit"),
       ("build.gradle.kts", "android_kit"),
       ("settings.gradle.kts", "android_kit"),
       ("pyproject.toml", "python_service"),
       # ...
   )
   ```

4. `resolve_profile` order: explicit `:Project.language_profile` → manifest inference → `unknown_language_profile` error (NO silent default).

**Commit:** `feat(extractors/foundation/profiles): backfill + manifest inference for project language_profile`

---

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

### Task 2.3 — run.py consumes new discovery (preserve existing fetch_failed semantics)

**Addresses Gate Call FF + N4 — existing mechanism (`run.py:71-77`) must be preserved.**

**RED:**
- `tests/audit/test_run_uses_status_taxonomy.py::test_render_called_with_status_buckets` — mock renderer, verify it receives 5 separate buckets (or one dict keyed by status).
- `tests/audit/test_run_preserves_fetch_failed_path.py::test_fetcher_out_parameter_still_populated` — fixture with extractor that raises in fetcher; assert fetcher's `failed_extractors` out-list contains the name AND the new status taxonomy classifies it as `FETCH_FAILED`.

**GREEN:** `audit/run.py:60-90` updated to:

1. Call `discover_extractor_statuses(...)` instead of `find_latest_runs()`.
2. **Preserve existing fetch_failed plumbing** (out-parameter passed to `fetch_audit_data` per `run.py:71-77`). Map names in `failed_extractors` to `FETCH_FAILED` status in the typed result.
3. Pass typed status to renderer.
4. Replace `audit_extractors = {... if audit_contract() is not None}` filter with profile-based lookup (profile-matched extractors with `audit_contract()`).

**Commit:** `feat(audit): run.py consumes typed statuses; preserves fetcher out-parameter mechanism`

### Task 2.4 — Renderer creates Failed / Data-Quality / Blind-Spots sections + Profile-Coverage appendix

**Addresses Gate Call C5 + N1 — existing blind-spots is inline in `report_template.md` + `run.py:69`, not a templated file; this is a CREATE, not split.**

**RED:**
- `tests/audit/test_renderer_status_sections.py::test_failed_extractors_render_separately` — fixture with one RUN_FAILED + one NOT_ATTEMPTED + one FETCH_FAILED; assert 3 separate report sections produced.
- `tests/audit/test_renderer_profile_coverage_appendix.py::test_appendix_counts_each_status` — fixture with each status present; assert §Profile Coverage appendix renders correct counts and `R == sum(N,M,K,F,L)`.
- `tests/audit/test_renderer_coverage_count_mismatch_fails.py::test_count_drift_aborts_render` — fixture with R ≠ N+M+K+F+L (simulated by registry mutation between discovery + render); assert renderer aborts with `coverage_count_mismatch` error_code.

**GREEN:** Modify `audit/renderer.py` to emit:
- §Failed Extractors (RUN_FAILED bucket) — extractor name, last run_id, error_code, error message, "next action".
- §Data-Quality Issues (FETCH_FAILED bucket) — extractor name, failed query trace, suggestion.
- §Blind Spots (NOT_ATTEMPTED bucket) — same as today's inline blind_spots, with `palace.ingest.run_extractor(...)` hint.
- **§Profile Coverage appendix** (Gate Call C5): table of OK / RUN_FAILED / NOT_ATTEMPTED / FETCH_FAILED / NOT_APPLICABLE with counts + invariant assertion `R == N+M+K+F+L`.

Create three NEW templates in `audit/templates/`: `failed_extractors.md`, `data_quality_issues.md`, `blind_spots.md`. Remove inline blind-spot rendering from `report_template.md`.

**Commit:** `feat(audit/renderer): three new status sections + Profile-Coverage appendix; remove inline blind-spot rendering`

### Task 2.5 — B6 hotspot 0-scan investigation (committed deliverable)

**Investigation tasks (no test/impl yet — discovery work). Addresses Gate Call P10 — deliverable becomes a committed artifact reviewed before Task 2.6 RED.**

**Steps:**

1. Query Neo4j on iMac:
   ```cypher
   MATCH (f:File {group_id: "project/tron-kit"}) RETURN count(f) AS file_count
   MATCH (c:Commit {group_id: "project/tron-kit"})-[t:TOUCHED]->(f:File) RETURN count(t) AS touched_count
   ```
2. `docker logs gimle-palace-palace-mcp-1 --since 2026-05-12T15:00 | grep -iE "hotspot|lizard" | head -50`
3. Check `extractors/hotspot/` source code for stop-list rules vs Swift file paths.

**Deliverable:** committed artifact `docs/postmortems/2026-05-13-hotspot-zero-scan-investigation.md` containing:
- Query outputs.
- Identified condition (a) mount-path mismatch / (b) stop-list / (c) ordering / (d) other.
- Root cause statement with file:line citations.
- Recommended fix scope.

**Gate:** Phase 1.2 plan-first CR review of Task 2.6 MUST cite the postmortem commit SHA in its APPROVE comment. Without the artifact on the FB, Task 2.6 RED tests don't get green-lit.

### Task 2.6 — B6 hotspot fix (depends on 2.5 findings)

**RED:** `tests/extractors/test_hotspot_scan_zero_files_with_files_present_fails.py` — fixture with `:File` count > 0 but mount path mismatch, assert extractor returns `success=False, error_code="data_mismatch_zero_scan_with_files_present"`.

**GREEN:** Based on root cause from 2.5:
- (a) mount path mismatch → align path conventions + pre-flight sanity check
- (b) stop-list overzealous → fix stop-list
- (c) ordering bug → enforce `git_history` before `hotspot` in `ingest_swift_kit.sh`

**Commit:** `fix(extractors/hotspot): <root cause-specific message>`

### Task 2.7 — Hotspot tightened success criteria (multi-invariant)

**Addresses Gate Call P11 — extend invariants beyond the single 0-scan check.**

**RED:**

- `tests/extractors/test_hotspot_zero_scan_with_files_present_fails_loudly.py` — fixture with `:File` count > 0 but `scanned_files == 0`; assert `success=False, error_code="data_mismatch_zero_scan_with_files_present"`.
- `tests/extractors/test_hotspot_zero_parsed_with_scanned_files_fails.py` — fixture where `scanned_files > 0` (lizard reads files) but `parsed_functions == 0` (lizard finds zero functions — likely parser breakage); assert `success=False, error_code="lizard_parser_zero_functions"`.
- `tests/extractors/test_hotspot_empty_project_fails_distinctly.py` — fixture where both `scanned_files == 0` AND `file_count_from_neo4j == 0` (genuinely empty project); assert `success=False, error_code="empty_project"` (distinct error so operator can tell "really empty" from "mount mismatch").

**GREEN:** In `extractors/hotspot/extractor.py`:
```python
file_count = await self._query_file_count(driver, project)
if scanned_files == 0 and file_count > 0:
    return ExtractorStats(success=False, error_code="data_mismatch_zero_scan_with_files_present", ...)
if scanned_files == 0 and file_count == 0:
    return ExtractorStats(success=False, error_code="empty_project", message="No :File nodes for project; run symbol_index_swift first.")
if scanned_files > 0 and parsed_functions == 0:
    return ExtractorStats(success=False, error_code="lizard_parser_zero_functions", ...)
# OK path
```

**Commit:** `fix(extractors/hotspot): three loud-fail invariants (mount-mismatch / parser / empty-project)`

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

### Task 1.1 — GIM-242 chain resumption (sub-issue + blocker)

**Addresses Gate Call P9 — GIM-NN-2 Phase 4.2 merge MUST block until GIM-242 chain merges to develop.**

This is a chain-resumption, not a code task. Spawn a separate paperclip issue:
- **Title:** "GIM-NN-2.1: resume GIM-242 testability_di chain to merge"
- **Initial assignee:** CTO Phase 1.1
- **Branch:** `feature/GIM-242-testability-di-pattern-extractor` (already exists, stale)
- **First action:** forward-merge `origin/develop` into the branch, resolve conflicts (39 commits ahead).
- **Then:** Phase 3.2 (Opus) → Phase 4.1 (QA, including a real-tron-kit smoke) → Phase 4.2 (CTO merge).
- **Roadmap update:** in PR description, include `docs(roadmap):` change ✅ → 📋 first, then ✅ at merge.

**Blocker invariant:** GIM-NN-2 Phase 4.2 (CTO merge of slice 1) MUST verify GIM-242 is merged-to-develop via `git ls-tree origin/develop -- services/palace-mcp/src/palace_mcp/extractors/testability_di/` returning non-empty before approving its own merge. Documented in `§Phase chain reminder` below.

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

### Task 3.3 — error_handling_policy emits source_context + B8 try? tuning + word-boundary regex

**Addresses Gate Call C3 (enforcement) + P12 (fixtures explicit + false-positive coverage).**

**RED — explicit fixture inventory:**

| Fixture file | Expected severity | What it tests |
|---|---|---|
| `Sources/TronKit/Crypto/Signer.swift` (with `try?`) | MEDIUM | crypto path → MEDIUM |
| `Sources/TronKit/HDWallet/HDWalletKit.swift` (with `try?`) | MEDIUM | hd_wallet path → MEDIUM |
| `Sources/TronKit/Network/Auth.swift` (with `try?`) | MEDIUM | auth path → MEDIUM |
| `Sources/TronKit/UI/Authorization.swift` (with `try?`) | LOW | **false-positive guard**: word `Authorization` substring-matches `auth`, but with word-boundary regex `\bauth\b` should NOT match. Severity = LOW. |
| `Sources/TronKit/UI/View.swift` (with `try?`) | LOW | UI path → LOW |
| `iOS Example/Sources/Manager.swift` (with `try?` in `signer/` subdir) | LOW | source_context=example → downgrade despite crypto regex match |
| `Tests/CryptoTests.swift` (with `try?`) | LOW | source_context=test → downgrade despite crypto regex match |

**Plus** test for each finding having `source_context` set (shape from 3.2).

**GREEN:**

1. Set `source_context` on each finding.
2. Add critical-path detection: file or function name matches regex `(?i)\b(signer|key|crypto|hd_wallet|hmac|sign|auth)\b` (word-boundary, case-insensitive) → MEDIUM `try?`; otherwise LOW.
3. Source-context downgrade: when `source_context in {"example", "test"}`, force severity ≤ LOW (overrides path-regex MEDIUM).
4. **B8 enforcement** (spec §B8 acceptance):
   - The regex list is a **placeholder** starting from `(signer|key|crypto|hd_wallet|hmac|sign|auth)`.
   - CR Phase 1.2 review MUST dispatch a BlockchainEngineer subagent per spec §B8.
   - BlockchainEng output → committed artifact `docs/research/2026-05-NN-try-optional-critical-path-keywords.md`. The artifact specifies the final regex + rationale + operator/BlockchainEng sign-off.
   - PE Phase 2 adjusts the regex per the committed artifact's spec.
   - **CR Phase 3.1 paste**: artifact's commit SHA + grep showing the regex matches the artifact's recommended list. Without paste → REQUEST CHANGES, slice blocks at Phase 3.1.
   - Phase 4.2 verifies the SHA exists on the FB.

**Commit:** `feat(extractors/error_handling_policy): source_context + word-boundary critical-path tuning + per-artifact regex`

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

### Task 5.2b — Stub templates for reactive_dependency_tracer + testability_di

**Addresses Gate Call N2 — these two extractors are in `_SECTION_ORDER` (slice 5) but have no templates in `audit/templates/`. Renderer's `TemplateNotFound` fallback (`renderer.py:182-184`) produces a stub heading + "no template available" message. AC11 ("verify by reading ## headings") would pass but the sections look broken.**

**RED:** `tests/audit/test_renderer_minimum_template_coverage.py::test_section_order_extractors_have_templates` — iterate over `_SECTION_ORDER`, assert a template exists in `audit/templates/<name>.md` for each.

**GREEN:** Create stub templates at minimum:

- `audit/templates/reactive_dependency_tracer.md` — renders the helper-unavailable diagnostic + reactive findings table when present + Provenance line.
- `audit/templates/testability_di.md` — renders DI-pattern findings table + per-extractor severity + Provenance line.

Both follow the same shape as `code_ownership.md` / similar minimal templates.

**Commit:** `feat(audit/templates): stub templates for reactive_dependency_tracer + testability_di`

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
- [ ] **No-rebase-overwrite guard** (addresses Gate Call P15): each task's `Files` declaration explicitly notes if a file is touched by a prior slice. Specifically: `profiles.py` is owned by Slice 1 (created), modified by Slice 2 (additions). `arch_layer/extractor.py` is owned by Slice 4 (summary_stats), modified by Slice 3 (source_context). Slice 3/4 PEs MUST `git pull` + verify content before pushing additive edits.
- [ ] **C3 enforcement gates** are spelled out in implementation tasks (not just intentions):
  - GIM-NN-4 Task 3.3 requires committed `docs/research/2026-05-NN-try-optional-critical-path-keywords.md` BEFORE CR Phase 3.1 APPROVE. CR Phase 3.1 paste includes the artifact SHA.
  - GIM-NN-5 Task 5.3 requires committed `docs/research/2026-05-NN-tron-kit-ac5-manual-review.md` BEFORE CTO Phase 4.2 merge. QA Phase 4.1 paste includes the artifact SHA.
- [ ] **C1 backfill landed**: GIM-NN-1 Task 2.0 includes the language_profile backfill Cypher for all 4 currently-mounted projects. Verify the migration script is in `services/palace-mcp/scripts/` and idempotent.
- [ ] **C2 bundle-mode**: `discover_extractor_statuses` signature accommodates bundle traversal (per-member). Even if v1.1 only smokes single-Kit, the API surface must support `bundle=` consumption for S4.3 forward-compat.
- [ ] **C5 coverage appendix**: Task 2.4 §Profile Coverage appendix has a render-time `R == N+M+K+F+L` assertion (raises `coverage_count_mismatch` error on drift).
- [ ] **C4 source_context**: Task 3.5 (renderer) emits `library=X example=Y test=Z other=W` summary, supports `.gimle/source-context-overrides.yaml`, and emits `library_findings_empty` warning when applicable.
- [ ] B6 investigation (Task 2.5) explicitly precedes Task 2.6 fix — root cause must be in committed `docs/postmortems/2026-05-13-hotspot-zero-scan-investigation.md` artifact.
- [ ] Final verification (Slice 5 / Task 5.3) wipes the right node labels and re-ingests via `ingest_swift_kit.sh`, NOT `palace.audit.run` alone.
- [ ] Each slice ships its own PR; serial merge order = 1 → 2 → 3 → 4 → 5 (numbered as in this plan, which is reordered from the spec's slice numbering for clarity: spec Slice 2 = plan GIM-NN-1, spec Slice 1 = plan GIM-NN-2, spec Slice 4 = plan GIM-NN-3, spec Slice 3 = plan GIM-NN-4, spec Slice 5 = plan GIM-NN-5).
- [ ] **GIM-NN-2 Phase 4.2 blocker** (Gate Call P9): CTO verifies `testability_di/` is in `origin/develop` before Phase 4.2 merge of slice 1.

## Phase chain reminder (per slice)

Standard Gimle 7-phase. Special notes per this plan:

- **Phase 1.2 of GIM-NN-4 (Slice 3)**: CR MUST dispatch BlockchainEngineer subagent for B8 regex completeness review before approving.
- **Phase 2.5 of GIM-NN-1 (Slice 2)**: Investigation task — PE produces a write-up before Task 2.6 coding starts.
- **Phase 4.1 of every slice**: QA performs the slice-specific Verification step from the relevant Slice §Verification subsection. Real `:IngestRun` against tron-kit, real audit report artifact, real diff vs prior. No mocks.
- **Phase 4.2 of every slice**: CTO merges only after the slice's verification artifact exists in `docs/audit-reports/` on the FB.
- **After GIM-NN-5 merge**: operator + BlockchainEngineer perform AC5 manual review (per spec §Acceptance criteria item 10).
