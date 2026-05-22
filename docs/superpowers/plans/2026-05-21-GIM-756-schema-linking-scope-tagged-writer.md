# GIM-756 - Schema Linking ScopeTaggedWriter

Plan for [GIM-756](/GIM/issues/GIM-756). Source of truth is the issue thread and approved implementation scope cited by [GIM-758](/GIM/issues/GIM-758).

## Scope

- In: add `ScopeTaggedWriter`, refactor the named extractor write paths to use it or declare an explicit exemption, add migration compatibility for `path`/`file_path`, backport dual-read queries needed by Audit V1, and ship the operator migration script.
- Out: broad graph identity changes for labels still keyed by `path`, unrelated extractor refactors, and cleanup outside the named write paths.

## Phase Steps

### Step 1 - Add `ScopeTaggedWriter`

**Description:** Introduce a shared helper that stamps `group_id`, dual-writes `path`/`file_path`, and supports opt-in legacy-path removal for new writes.
**Acceptance criteria:** helper rejects missing `group_id`; helper rejects non-allowlisted labels; helper dual-writes `file_path` from `path`; helper can omit legacy `path` when requested.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/src/palace_mcp/extractors/foundation/scope_tagging.py`, `services/palace-mcp/tests/extractors/unit/test_scope_tagging.py`.

### Step 2 - Refactor the approved extractor write paths

**Description:** Route the planned extractor node writes through `ScopeTaggedWriter`, preserving identity semantics for exempt MERGE paths.
**Acceptance criteria:** touched extractors either call `ScopeTaggedWriter` or carry an inline `scope-tagging-exempt` note explaining why identity must stay on the existing MERGE key.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** shared SCIP/symbol index write path plus `git_history`, `code_ownership`, `coding_convention`, `error_handling_policy`, `testability_di`, `arch_layer`, `crypto_domain_model`, `hotspot`, `localization_accessibility`, `dependency_surface`.

### Step 3 - Add migration compatibility

**Description:** Keep reads compatible during the `path` → `file_path` migration window and ship the operator script for staged rollout.
**Acceptance criteria:** production reads use `coalesce(n.file_path, n.path)` where this slice touches them; migration script supports `--dry-run`, `--apply-step-1`, `--apply-step-3`, and `--rollback-snapshot`; step 3 only removes `path` where this slice has made the read path safe.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `paperclips/scripts/migrate_path_to_file_path.sh`, `services/palace-mcp/src/palace_mcp/code_composite.py`, audit-query backports, and any touched extractor/read paths.

### Step 4 - Guard coverage and verification

**Description:** Add narrow regression coverage for the helper and migration-sensitive queries.
**Acceptance criteria:** tests cover missing-group rejection, label rejection, path alias dual-write, legacy path removal, and dual-read query behavior for the touched call sites; targeted pytest and formatting checks pass.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** `services/palace-mcp/tests/extractors/unit/test_scope_tagging.py`, `services/palace-mcp/tests/code/test_path_dual_read_queries.py`, related extractor tests.

### Step 5 - PR readiness

**Description:** Land the slice on `feature/GIM-756-schema-linking-scope-tagged-writer` targeting `develop`.
**Acceptance criteria:** PR references this plan and includes a `## QA Evidence` section with the verified head SHA before final review.
**Suggested owner:** CXPythonEngineer.
**Affected paths:** PR body, branch `feature/GIM-756-schema-linking-scope-tagged-writer`.

## Acceptance Mapping

- All touched extractor node writes carry `group_id` or an explicit exemption: Steps 1 and 2.
- Existing node identity and relationship semantics are preserved: Steps 2 and 3.
- Migration script supports the required flags: Step 3.
- Audit-V1 dual-read compatibility exists for touched queries: Steps 3 and 4.
- PR references the plan and carries QA Evidence: Step 5.
