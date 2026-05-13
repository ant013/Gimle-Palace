# Implementation plan — Audit-V1 pipeline fixes (5 slices)

**Date:** 2026-05-13
**Spec:** `docs/superpowers/specs/2026-05-13-audit-v1-pipeline-fixes.md` (rev2 — addresses Codex-subagent Gate Call NO-GO)
**Status:** rev3 — addresses CR Phase 1.2 REQUEST CHANGES on GIM-283-3 (3 CRITICALs)
**Team:** Claude (CTO + CR + PythonEngineer + Opus + QA)

### Rev3 changelog (2026-05-14)

Addresses CodeReviewer Phase 1.2 findings from [GIM-288 comment 33f63caf](/GIM/issues/GIM-288#comment-33f63caf-189a-448b-a255-193f66d89033):

| # | Type | Finding | Fix |
|---|------|---------|-----|
| C1 | CRITICAL | `summary_stats` plumbing gap — Tasks 4.1/4.3 say "set in extractor" but `ExtractorStats` has no `summary_stats` field; `_build_summary_stats()` is findings-only, no driver access | Task 4.1: lockfile detection moved to `_build_summary_stats` dep_surface branch (derives from all-unresolved findings + audit query extended with `resolved_version`). Task 4.3: arch_layer module_count fetched via secondary Cypher query in new `_fetch_arch_layer_supplement()` async helper in `fetcher.py` |
| C2 | CRITICAL | `fetcher.py` listed as conditional in Files-owned | Made unconditional — both Task 4.1 and 4.3 require `fetcher.py` changes |
| C3 | CRITICAL | SPM parser hard-codes `declared_version_constraint=""` — B9 acceptance ("shows declared constraints, not @unresolved") unsatisfiable | Added Task 4.1b: fix `parsers/spm.py` to populate `declared_version_constraint` from captured regex group `ver` + add `parsers/spm.py` to Files-owned |

### Rev2 changelog (2026-05-13)

Addresses CodeReviewer Phase 1.2 findings from [GIM-285 comment c01add93](/GIM/issues/GIM-285#comment-c01add93-606a-4982-ae17-69504f50d12e):

| # | Type | Finding | Fix |
|---|------|---------|-----|
| C1 | CRITICAL | Bundle-mode discovery missing from Slice 2 | Added **Task 2.3b** — per-member discovery via `(:Bundle)-[:HAS_MEMBER]->(:Project)` traversal, 3 RED tests |
| C2 | CRITICAL | Last-attempt-wins edge case untested | Added `test_latest_failed_overrides_earlier_success` to Task 2.2 RED |
| C3 | CRITICAL | Task 2.6/2.7 duplicate RED test | Task 2.6 RED now targets root cause (mount-path/stop-list/prerequisite per 2.5 findings); `data_mismatch_zero_scan_with_files_present` test lives exclusively in Task 2.7 |
| W1 | WARNING | Files-owned misattributes `blind_spots.md` as existing | Fixed: `report_template.md` (modify) + 3 NEW templates listed separately |
| W2 | WARNING | Backfill Cypher includes non-mounted `uw-android-mini` | Removed from slug list (6 projects now); added explanatory comment |
| W3 | WARNING | Task 2.4 test files missing from Files-owned | Added all test file paths to Files-owned section |

This plan splits into **5 paperclip issues** (placeholders `GIM-283-1` through `GIM-283-5`); each ships its own FB + PR. **Sequencing is strictly serial** — no two issues run in parallel because each touches `audit/renderer.py` or its neighbours (per spec §Sequencing).

Estimated wall-time (with serial chain + smoke verification between slices): **3-4 weeks total**, dominated by Slice 3 (source_context schema change).

## Slice mapping

| GIM-283 | Slice | Spec items | Tasks | Wall-time |
|--------|-------|-----------|-------|-----------|
| GIM-283-1 | Slice 2 — Status taxonomy + failure visibility | B4, B5, B6, §Status taxonomy | 9 (rev2: +Task 2.3b bundle-mode) | ~1 week |
| GIM-283-2 | Slice 1 — Coverage (testability_di + reactive + ingest defaults) | B1, B2, B3 | 6 (+ GIM-242 chain resumption sub-issue) | ~1 week |
| GIM-283-3 | Slice 4 — Data quality (deps + arch_layer) | B9, B10 | 5 | ~3-5 days |
| GIM-283-4 | Slice 3 — Source-context (annotation + try? tuning) | B7, B8 | 8 | ~1.5-2 weeks |
| GIM-283-5 | Slice 5 — Pinned ordering renderer | B11 | 3 | ~1-2 days |

---

## GIM-283-1 — Slice 2: Status taxonomy + failure visibility (foundation)

**Goal:** Introduce typed extractor statuses (`NOT_APPLICABLE` / `NOT_ATTEMPTED` / `RUN_FAILED` / `FETCH_FAILED` / `OK`) and render each distinctly. Fix `hotspot` 0-scan as part of the same slice since failure visibility is needed to surface the underlying issue.

**Why first:** Slices 2-5 all consume the taxonomy. Without it, "this extractor failed" is indistinguishable from "this extractor was never invoked".

**Branch:** `feature/GIM-283-1-audit-status-taxonomy`

**Files owned:**
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py` (NEW)
- `services/palace-mcp/src/palace_mcp/audit/discovery.py`
- `services/palace-mcp/src/palace_mcp/audit/run.py`
- `services/palace-mcp/src/palace_mcp/audit/renderer.py` (status logic only — no ordering changes; that's Slice 5)
- `services/palace-mcp/src/palace_mcp/audit/report_template.md` (remove inline blind-spots section, lines 20-30)
- `services/palace-mcp/src/palace_mcp/audit/templates/blind_spots.md` (NEW)
- `services/palace-mcp/src/palace_mcp/audit/templates/failed_extractors.md` (NEW)
- `services/palace-mcp/src/palace_mcp/audit/templates/data_quality_issues.md` (NEW)
- `services/palace-mcp/tests/audit/test_discovery_status_taxonomy.py` (NEW)
- `services/palace-mcp/tests/audit/test_renderer_status_sections.py` (NEW)
- `services/palace-mcp/tests/audit/test_renderer_profile_coverage_appendix.py` (NEW)
- `services/palace-mcp/tests/audit/test_renderer_coverage_count_mismatch_fails.py` (NEW)
- `services/palace-mcp/tests/audit/test_run_uses_status_taxonomy.py` (NEW)
- `services/palace-mcp/tests/audit/test_run_preserves_fetch_failed_path.py` (NEW)
- `services/palace-mcp/tests/audit/test_bundle_mode_discovery.py` (NEW)

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
   MATCH (p:Project) WHERE p.slug IN ['gimle','tron-kit','uw-android','uw-ios','uw-ios-mini','oz-v5-mini']
   SET p.language_profile = CASE p.slug
     WHEN 'gimle' THEN 'python_service'
     WHEN 'tron-kit' THEN 'swift_kit'
     WHEN 'uw-ios' THEN 'swift_kit'
     WHEN 'uw-ios-mini' THEN 'swift_kit'
     WHEN 'uw-android' THEN 'android_kit'
     WHEN 'oz-v5-mini' THEN 'python_service'
     ELSE p.language_profile END
   -- Note: uw-android-mini excluded — test fixture only, not mounted in docker-compose.yml
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
        "testability_di",  # once GIM-283-2 lands; until then absent
    })),
    "android_kit": ...,  # post-tron-kit work; deferred
}

def resolve_profile(project_slug: str, driver) -> LanguageProfile:
    """Look up :Project.language_profile or infer from manifest."""
```

**Refactor:** N/A.

**Commit:** `feat(extractors): foundation/profiles.py — language → audit-extractor mapping`

### Task 2.2 — Discovery returns typed statuses

**RED:**
- `tests/audit/test_discovery_status_taxonomy.py::test_discovery_classifies_each_extractor` — 5 fixture extractors (NOT_APPLICABLE / NOT_ATTEMPTED / RUN_FAILED / FETCH_FAILED / OK) and asserts each classified correctly.
- `tests/audit/test_discovery_status_taxonomy.py::test_latest_failed_overrides_earlier_success` — **(CR C2 fix)** fixture with 2 IngestRuns for the same extractor: first `success=True, completed_at=T1`; second `success=False, completed_at=T2` where `T2 > T1`. Assert status == `RUN_FAILED`, not `OK`. Validates last-attempt-wins discovery per spec §Last-attempt-wins — the `WHERE r.success` filter must be dropped in favor of ordering by `completed_at DESC LIMIT 1`.

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

### Task 2.3b — Bundle-mode discovery in run.py (CR C1 fix)

**Addresses spec §Status taxonomy "Bundle mode" + Plan checklist C2.** Spec requires per-member discovery when `bundle=` is passed: _"for each (:Bundle{name})-[:HAS_MEMBER]->(:Project), run discover_extractor_statuses(...) separately; each member has its own profile."_

Current `run.py:30` accepts `bundle=` but line 61 passes it as a plain slug to `find_latest_runs(driver, project=target)` — no per-member iteration, no `member_slug` column.

**RED:**
- `tests/audit/test_bundle_mode_discovery.py::test_bundle_mode_discovers_per_member` — fixture bundle with 2 members (`tron-kit` profile=swift_kit, `oz-v5-mini` profile=python_service); call `run_audit(bundle="uw-ios")`; assert discovery returns per-member status dicts keyed by `(member_slug, extractor_name)`, each member resolved against its own profile.
- `tests/audit/test_bundle_mode_discovery.py::test_bundle_mode_aggregates_failed_across_members` — fixture where member-A has `hotspot=RUN_FAILED` and member-B has `hotspot=OK`; assert §Failed Extractors section includes the member-A failure with `member_slug` column.
- `tests/audit/test_bundle_mode_discovery.py::test_single_project_mode_unchanged` — `run_audit(project="tron-kit")` still works as before (no `member_slug` column, flat status dict).

**GREEN:** In `audit/run.py`:

1. When `bundle` argument is provided:
   ```python
   members = await resolve_bundle_members(driver, bundle)  # query (:Bundle{name})-[:HAS_MEMBER]->(:Project)
   all_statuses = {}
   for member in members:
       profile = resolve_profile(member.slug, driver)
       member_statuses = await discover_extractor_statuses(driver, member.slug, profile, registry)
       for name, status in member_statuses.items():
           all_statuses[(member.slug, name)] = status
   ```
2. Pass `member_slug` dimension to renderer when in bundle mode — renderer adds column.
3. §Profile Coverage appendix in bundle mode: per-member subtotals + grand total with same `R == N+M+K+F+L` invariant per member.
4. Single-project path (`bundle=None`) unchanged — call `discover_extractor_statuses` once, flat dict.

**Commit:** `feat(audit): bundle-mode per-member discovery in run.py`

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

### Task 2.6 — B6 hotspot root-cause fix (depends on 2.5 findings) (CR C3 fix — scope clarified)

**Scope:** This task fixes the ROOT CAUSE identified in the 2.5 investigation postmortem. It does NOT add the defensive multi-invariant checks — those belong exclusively to Task 2.7. The RED test here targets the specific root cause, not the generic `data_mismatch_zero_scan_with_files_present` invariant.

**RED (exact test depends on 2.5 root cause — one of the following):**
- If (a) mount-path mismatch: `tests/extractors/test_hotspot_mount_path_resolution.py::test_hotspot_resolves_correct_repo_mount` — fixture with `:Project` slug mapped to `/repos/<slug>`; assert hotspot walks the correct mount path, not a stale/wrong one.
- If (b) stop-list overzealous: `tests/extractors/test_hotspot_stoplist_swift.py::test_swift_source_files_not_excluded` — fixture repo with `.swift` files under `Sources/`; assert hotspot does NOT stop-list them (currently excludes too aggressively).
- If (c) ordering/prerequisite: `tests/extractors/test_hotspot_prerequisite_check.py::test_hotspot_fails_fast_without_git_history` — run hotspot on project with no `:Commit` nodes; assert `error_code="prerequisite_missing"` instead of silently returning 0 scanned files.

PE selects the matching test based on the committed postmortem finding. If root cause is a combination, PE writes tests for each contributing factor.

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

## GIM-283-2 — Slice 1: Coverage (testability_di + reactive + DEFAULT_EXTRACTORS)

**Goal:** Plug all in-profile extractors. Depends on Slice 2 statuses being live.

**Branch:** `feature/GIM-283-2-audit-coverage-gaps`

**Files owned:**
- `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- `services/palace-mcp/src/palace_mcp/extractors/foundation/profiles.py` (adds `testability_di`, `reactive_dependency_tracer` to `swift_kit` once they're audit-ready)
- `services/palace-mcp/src/palace_mcp/extractors/reactive_dependency_tracer/extractor.py` (audit_contract override)
- `paperclips/scripts/ingest_swift_kit.sh` (DEFAULT_EXTRACTORS)
- `docs/runbooks/ingest-swift-kit.md`
- `docs/roadmap.md` (correct GIM-242 row ✅ → 📋 then back to ✅ at chain close)

### Task 1.1 — GIM-242 chain resumption (sub-issue + blocker)

**Addresses Gate Call P9 — GIM-283-2 Phase 4.2 merge MUST block until GIM-242 chain merges to develop.**

This is a chain-resumption, not a code task. Spawn a separate paperclip issue:
- **Title:** "GIM-283-2.1: resume GIM-242 testability_di chain to merge"
- **Initial assignee:** CTO Phase 1.1
- **Branch:** `feature/GIM-242-testability-di-pattern-extractor` (already exists, stale)
- **First action:** forward-merge `origin/develop` into the branch, resolve conflicts (39 commits ahead).
- **Then:** Phase 3.2 (Opus) → Phase 4.1 (QA, including a real-tron-kit smoke) → Phase 4.2 (CTO merge).
- **Roadmap update:** in PR description, include `docs(roadmap):` change ✅ → 📋 first, then ✅ at merge.

**Blocker invariant:** GIM-283-2 Phase 4.2 (CTO merge of slice 1) MUST verify GIM-242 is merged-to-develop via `git ls-tree origin/develop -- services/palace-mcp/src/palace_mcp/extractors/testability_di/` returning non-empty before approving its own merge. Documented in `§Phase chain reminder` below.

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

## GIM-283-3 — Slice 4: Data quality (deps + arch_layer)

**Goal:** Close Opus N1 + N2 small-template-side fixes.

**Branch:** `feature/GIM-283-3-audit-data-quality`

**Rev3 design note — `summary_stats` plumbing (addresses C1):**

`ExtractorStats` (base.py:68–72) has only `nodes_written` and `edges_written` — no `summary_stats` field.
The `summary_stats` dict consumed by Jinja templates is built inside `fetcher.py` by `_build_summary_stats()`,
which is a pure function over the findings list (no driver access, no filesystem access). This is the
correct plumbing path for any stat derivable from audit query results. For stats that require a separate
Cypher query (e.g. arch_layer `module_count` when `findings=[]`), a new async helper in `fetcher.py`
runs the supplemental query and merges results into `summary_stats` before handing off to the renderer.

**Files owned:**
- `services/palace-mcp/src/palace_mcp/extractors/dependency_surface/extractor.py`
- `services/palace-mcp/src/palace_mcp/extractors/dependency_surface/parsers/spm.py`
- `services/palace-mcp/src/palace_mcp/extractors/arch_layer/extractor.py`
- `services/palace-mcp/src/palace_mcp/audit/templates/dependency_surface.md`
- `services/palace-mcp/src/palace_mcp/audit/templates/arch_layer.md`
- `services/palace-mcp/src/palace_mcp/audit/fetcher.py`
- `tests/extractors/dependency_surface/test_lockfile_warning.py` (NEW)
- `tests/extractors/dependency_surface/test_spm_constraint_parsing.py` (NEW)
- `tests/audit/test_dependency_surface_template.py` (NEW)
- `tests/extractors/arch_layer/test_summary_stats_always_populated.py` (NEW)
- `tests/audit/test_arch_layer_template.py` (NEW)

### Task 4.1 — dependency_surface: extend audit query + lockfile detection in fetcher

**Problem (C1):** The current dep_surface audit query (`extractor.py:72–79`) returns only 4 columns:
`purl`, `scope`, `declared_in`, `declared_version_constraint`. It does NOT return `resolved_version`.
Without `resolved_version` in the findings, `_build_summary_stats` cannot determine whether a lockfile
was present (all-unresolved = no lockfile). The old plan said "set summary_stats in the extractor" —
this is wrong because `ExtractorStats` has no `summary_stats` field.

**Correct path:**

1. Extend the `audit_contract().query` in `extractors/dependency_surface/extractor.py` to also return
   `r.resolved_version AS resolved_version` (5th column).
2. Add an `arch_layer`-independent lockfile detection branch to `_build_summary_stats` in `fetcher.py`:

```python
elif extractor_name == "dependency_surface":
    scopes = list({f.get("scope") for f in findings if f.get("scope")})
    stats["scopes"] = scopes
    # Lockfile detection: if ALL findings have resolved_version == "unresolved",
    # no lockfile was available for this ecosystem.
    if findings:
        all_unresolved = all(
            f.get("resolved_version") == "unresolved" for f in findings
        )
        stats["missing_lockfile"] = all_unresolved
    else:
        stats["missing_lockfile"] = False
```

**RED:** `tests/extractors/dependency_surface/test_lockfile_warning.py`:
- `test_missing_lockfile_detected_when_all_unresolved` — findings with all `resolved_version="unresolved"` → `summary_stats["missing_lockfile"] == True`
- `test_lockfile_present_when_some_resolved` — findings with mixed resolved/unresolved → `summary_stats["missing_lockfile"] == False`
- `test_empty_findings_no_lockfile_false` — `findings=[]` → `summary_stats["missing_lockfile"] == False`

**GREEN:** Changes in `extractor.py` (query extension) + `fetcher.py` (`_build_summary_stats` dep_surface branch).

**Commit:** `feat(audit/dep_surface): extend audit query with resolved_version + lockfile detection in fetcher`

### Task 4.1b — SPM parser: populate declared_version_constraint (addresses C3)

**Problem (C3):** `parsers/spm.py:85` hard-codes `declared_version_constraint=""` for all SPM deps.
The regex `_PKG_PATTERN` (line 20–24) already captures the `ver` group from `from:`, `exact:`,
`branch:`, `revision:` constraints, but line 46 extracts only `url` — `ver` is discarded.
B9 acceptance requires "shows declared constraints, not `@unresolved`" — unsatisfiable without
this fix.

**Correct path:**

1. In `parse_spm()`, change line 46 to also capture the constraint type + value:
```python
for m in _PKG_PATTERN.finditer(text):
    url = m.group("url")
    ver = m.group("ver") or ""
    # ... use ver below
```

2. Populate `declared_version_constraint` with the captured value instead of `""`:
```python
declared_version_constraint=ver,  # was: ""
```

3. Optionally prefix with constraint type (e.g. `from: 5.0.0`, `exact: 1.2.3`) for clarity.
   This requires extending the regex to also capture the constraint keyword. If this adds
   complexity, plain version string (e.g. `5.0.0`) is acceptable for rev3.

**RED:** `tests/extractors/dependency_surface/test_spm_constraint_parsing.py`:
- `test_from_constraint_captured` — `Package.swift` with `.package(url: "...", from: "5.0.0")` → `declared_version_constraint == "5.0.0"` (or `"from: 5.0.0"`)
- `test_exact_constraint_captured` — `exact: "1.2.3"` → captured
- `test_branch_constraint_captured` — `branch: "main"` → captured
- `test_no_constraint_stays_empty` — `.package(url: "...")` with no version clause → `declared_version_constraint == ""`

**GREEN:** Fix `parsers/spm.py` lines 46 + 85.

**Commit:** `fix(parsers/spm): populate declared_version_constraint from captured regex group`

### Task 4.2 — dependency_surface template Data Quality block

**RED:** `tests/audit/test_dependency_surface_template.py::test_missing_lockfile_renders_warning` — fixture with `summary_stats.missing_lockfile=True`; assert rendered markdown has "No Package.resolved found" warning text.

**Additional RED:** `test_declared_constraint_shown_when_lockfile_missing` — fixture with
`summary_stats.missing_lockfile=True` + findings with `declared_version_constraint="5.0.0"` +
`resolved_version="unresolved"` → deps table shows `5.0.0` (not `@unresolved`).

**GREEN:** Update `audit/templates/dependency_surface.md`:
```jinja
{% if summary_stats.get("missing_lockfile") %}
### ⚠ Data Quality

No `Package.resolved` (or `uv.lock` / `gradle.lockfile`) found in `{{ project }}/`; declared constraints only. CVE / version-freshness checks unavailable.

{% endif %}
```

In the deps table: when `missing_lockfile`, show `declared_version_constraint` column instead of
`resolved_version`. When lockfile present, show `resolved_version` as before. Jinja conditional:
```jinja
{% if summary_stats.get("missing_lockfile") %}
| {{ f.declared_version_constraint or '—' }} |
{% else %}
| {{ f.resolved_version or '—' }} |
{% endif %}
```

**Commit:** `feat(audit/templates/dependency_surface): data-quality warning + declared-constraint fallback`

### Task 4.3 — arch_layer module_count via supplemental query in fetcher (addresses C1)

**Problem (C1):** `_build_summary_stats` has no `arch_layer` branch. When `findings=[]` (no violations),
`summary_stats = {"total": 0}` — no `module_count`. The arch_layer audit query (`_QUERY`) returns only
`:ArchViolation` rows, so module_count cannot be derived from findings. The extractor's `run()` knows
`len(all_modules)` (line 220) but `ExtractorStats` cannot carry this.

**Correct path:** Add a supplemental async query in `fetcher.py`. Specifically:

1. Add `_ARCH_LAYER_SUPPLEMENT` Cypher constant:
```python
_ARCH_LAYER_SUPPLEMENT = """
MATCH (m:Module {project_id: $project_id})
OPTIONAL MATCH (m)-[e:IMPORTS]->(m2:Module {project_id: $project_id})
WITH count(DISTINCT m) AS module_count, count(e) AS edge_count
OPTIONAL MATCH (r:ArchRule {project_id: $project_id})
RETURN module_count, edge_count,
       count(r) > 0 AS rules_declared,
       r.source AS rule_source
LIMIT 1
"""
```

2. In `fetch_audit_data`, after `_build_summary_stats` for `arch_layer`, run the supplement:
```python
if extractor_name == "arch_layer":
    supplement = await _fetch_arch_layer_supplement(driver, run_info)
    results[extractor_name].summary_stats.update(supplement)
```

3. `_fetch_arch_layer_supplement(driver, run_info) -> dict` is a new async helper that
   runs the Cypher and returns `{"module_count": N, "edge_count": M, "rules_declared": bool, "rule_source": str|None}`.

**RED:** `tests/extractors/arch_layer/test_summary_stats_always_populated.py`:
- `test_no_rules_path_includes_module_count` — mock driver returns 12 modules, 0 rules → `summary_stats["module_count"] == 12`, `summary_stats["rules_declared"] == False`
- `test_with_rules_path_includes_module_count` — mock driver returns 8 modules, 3 rules → `summary_stats["module_count"] == 8`, `summary_stats["rules_declared"] == True`
- `test_empty_project_zero_modules` — mock driver returns 0 → `summary_stats["module_count"] == 0`

**GREEN:** New helper + integration in `fetcher.py`.

**Commit:** `feat(audit/fetcher): add arch_layer supplemental query for module_count + rules_declared`

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
- §Dependency Surface shows declared constraints (e.g. `5.0.0`) + "No Package.resolved found" warning. NOT `@unresolved`.
- §Architecture rendering shows `No architecture rules declared — N modules indexed in Neo4j` with concrete N.
- Regression: a fixture project WITH Package.resolved still shows resolved versions correctly.

---

## GIM-283-4 — Slice 3: Source-context annotation (B7 + B8)

**Goal:** Add `source_context: library | example | test | other` to findings; render it; tune `error_handling_policy` `try?` severity. Biggest scope; ~2 weeks.

**Branch:** `feature/GIM-283-4-audit-source-context`

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

## GIM-283-5 — Slice 5: Pinned-then-severity ordering

**Goal:** Replace renderer's global severity sort with pinned-then-severity strategy.

**Branch:** `feature/GIM-283-5-audit-pinned-ordering`

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
  - GIM-283-4 Task 3.3 requires committed `docs/research/2026-05-NN-try-optional-critical-path-keywords.md` BEFORE CR Phase 3.1 APPROVE. CR Phase 3.1 paste includes the artifact SHA.
  - GIM-283-5 Task 5.3 requires committed `docs/research/2026-05-NN-tron-kit-ac5-manual-review.md` BEFORE CTO Phase 4.2 merge. QA Phase 4.1 paste includes the artifact SHA.
- [ ] **C1 backfill landed**: GIM-283-1 Task 2.0 includes the language_profile backfill Cypher for all 6 currently-mounted projects (uw-android-mini excluded — test fixture only, not mounted). Verify the migration script is in `services/palace-mcp/scripts/` and idempotent.
- [ ] **C2 bundle-mode**: Task 2.3b implements bundle-mode per-member discovery in `run.py`. `discover_extractor_statuses` called per `(:Bundle)-[:HAS_MEMBER]->(:Project)` member, each with its own profile. RED tests cover per-member aggregation + single-project backward compat.
- [ ] **C5 coverage appendix**: Task 2.4 §Profile Coverage appendix has a render-time `R == N+M+K+F+L` assertion (raises `coverage_count_mismatch` error on drift).
- [ ] **C4 source_context**: Task 3.5 (renderer) emits `library=X example=Y test=Z other=W` summary, supports `.gimle/source-context-overrides.yaml`, and emits `library_findings_empty` warning when applicable.
- [ ] B6 investigation (Task 2.5) explicitly precedes Task 2.6 fix — root cause must be in committed `docs/postmortems/2026-05-13-hotspot-zero-scan-investigation.md` artifact.
- [ ] Final verification (Slice 5 / Task 5.3) wipes the right node labels and re-ingests via `ingest_swift_kit.sh`, NOT `palace.audit.run` alone.
- [ ] Each slice ships its own PR; serial merge order = 1 → 2 → 3 → 4 → 5 (numbered as in this plan, which is reordered from the spec's slice numbering for clarity: spec Slice 2 = plan GIM-283-1, spec Slice 1 = plan GIM-283-2, spec Slice 4 = plan GIM-283-3, spec Slice 3 = plan GIM-283-4, spec Slice 5 = plan GIM-283-5).
- [ ] **GIM-283-2 Phase 4.2 blocker** (Gate Call P9): CTO verifies `testability_di/` is in `origin/develop` before Phase 4.2 merge of slice 1.

## Phase chain reminder (per slice)

Standard Gimle 7-phase. Special notes per this plan:

- **Phase 1.2 of GIM-283-4 (Slice 3)**: CR MUST dispatch BlockchainEngineer subagent for B8 regex completeness review before approving.
- **Phase 2.5 of GIM-283-1 (Slice 2)**: Investigation task — PE produces a write-up before Task 2.6 coding starts.
- **Phase 4.1 of every slice**: QA performs the slice-specific Verification step from the relevant Slice §Verification subsection. Real `:IngestRun` against tron-kit, real audit report artifact, real diff vs prior. No mocks.
- **Phase 4.2 of every slice**: CTO merges only after the slice's verification artifact exists in `docs/audit-reports/` on the FB.
- **After GIM-283-5 merge**: operator + BlockchainEngineer perform AC5 manual review (per spec §Acceptance criteria item 10).