# GIM-844 A5 Xcode Workspace Adapter And UW Recipe Plan

## Goal

Implement the GIM-839 A5 slice only: an Xcode workspace build adapter for the
existing smoke recipe contract and the `unstoppable-wallet-ios` recipe behavior
needed to emit the app SCIP artifact without using the direct Xcode project.

## Assumptions

- D0 and A1 are already merged to `develop`:
  - D0: `afa3561`
  - A1: `4e64393`
- The baseline UW fixture already lives at
  `services/palace-mcp/tests/smoke/fixtures/uw_ios_recipe.yaml`.
- A5 should not implement the full runtime runner, Docker/Neo4j/Qodo preflight,
  or runbook; those belong to A3, A6, and A7.
- Unit tests must not run Xcode, resolve packages, access the network, or mutate
  a real checkout.

## Acceptance Criteria

- Generated Xcode command uses:
  - `-workspace Wallet.xcworkspace`
  - `-scheme Development`
  - `-destination generic/platform=iOS Simulator`
  - resolved simulator architecture from `auto|arm64|x86_64`
  - repo-local `-derivedDataPath .palace-scip-derived-data`
  - signing disabled
- Generated command never uses direct
  `-project Unstoppable/Unstoppable.xcodeproj` for the UW recipe.
- Default package mode is locked and includes no-download Xcode flags.
- Opt-in package resolution mode removes the locked/no-download flags only when
  the recipe or caller explicitly selects automatic resolution.
- `ensure_config_from_template` prepare step is idempotent:
  - copies `Config.template.xcconfig` to `Config.xcconfig` when missing;
  - does not overwrite an existing `Config.xcconfig`.
- Workspace `absolute:` references are detected and rejected unless an explicit
  mapping/sanitization path is implemented in this slice.

## Implementation Steps

1. Add failing tests for Xcode workspace command construction.
   - Owner: `CXPythonEngineer`
   - Suggested files:
     - `services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py`
     - `services/palace-mcp/tests/smoke/fixtures/uw_ios_recipe.yaml`
   - Check:
     `uv run pytest services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py`

2. Add failing tests for prepare-step idempotency and no-overwrite behavior.
   - Owner: `CXPythonEngineer`
   - Suggested file:
     - `services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py`
   - Check:
     `uv run pytest services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py -k config`

3. Add failing tests for package-resolution behavior and workspace absolute
   reference detection.
   - Owner: `CXPythonEngineer`
   - Suggested file:
     - `services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py`
   - Check:
     `uv run pytest services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py -k "package or absolute"`

4. Implement the smallest adapter surface that makes the tests pass.
   - Owner: `CXPythonEngineer`
   - Suggested files:
     - `services/palace-mcp/src/palace_mcp/smoke/xcode_workspace.py`
     - `services/palace-mcp/src/palace_mcp/smoke/__init__.py`
   - Constraints:
     - keep recipe schema changes out unless a test proves they are needed;
     - build command construction must be pure and testable;
     - filesystem mutation is limited to the prepare step.
   - Check:
     `uv run pytest services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py`

5. Run focused regression checks for the D0/A1 contract files.
   - Owner: `CXPythonEngineer`
   - Check:
     `uv run pytest services/palace-mcp/tests/smoke/test_recipe_contract.py services/palace-mcp/tests/smoke/test_recipe_fixtures.py services/palace-mcp/tests/smoke/test_runtime_binding_contract.py services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py`

6. Open a PR to `develop` from `feature/GIM-839-A5-xcode-uw-recipe`.
   - Owner: `CXPythonEngineer`
   - PR body must reference this plan and include QA evidence with the focused
     pytest output.

## Review And Handoff

- Plan-first review: `CXCodeReviewer`
- Implementation: `CXPythonEngineer`
- Mechanical review: `CXCodeReviewer`
- Adversarial review: `CodexArchitectReviewer`
- QA smoke/evidence for this unit-testable slice: `CXQAEngineer`
- Merge gate: `CXCTO`

## Verification

Primary verification for this slice:

```bash
uv run pytest services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py
uv run pytest services/palace-mcp/tests/smoke/test_recipe_contract.py services/palace-mcp/tests/smoke/test_recipe_fixtures.py services/palace-mcp/tests/smoke/test_runtime_binding_contract.py services/palace-mcp/tests/smoke/test_xcode_workspace_adapter.py
```

CI/PR verification should also run the project-required checks before review:

```bash
uv run ruff check services/palace-mcp/src services/palace-mcp/tests
uv run mypy services/palace-mcp/src
uv run pytest services/palace-mcp/tests/smoke
```

## Close Requirement

Close GIM-844 only after the PR is merged to `develop`. The close comment must
include:

- PR link
- merged-to-`develop` commit SHA
- focused pytest evidence
- any follow-up blockers for A7/C2
