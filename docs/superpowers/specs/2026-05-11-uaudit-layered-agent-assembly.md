# UAudit Layered Agent Assembly Slice

## Goal

Add a reproducible Paperclip layered assembly path for the UnstoppableAudit
Codex-local team without changing Gimle legacy bundles or live-deploying UAudit
agents.

## Assumptions

- UAudit Paperclip company id is `8f55e80b-0264-4ab6-9d56-8b2652f18005`.
- UAudit live workspaces are under `/Users/Shared/UnstoppableAudit/runs/<agent>/workspace`.
- UAudit source repos are:
  - iOS: `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios`
  - Android: `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android`
- Indexed codebase-memory projects are:
  - `Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios`
  - `Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android`
- Existing UAudit live `AGENTS.md` files are operator-patched bootstrap files,
  not the final shared-fragment assembly output.

## Scope

- Add `paperclips/projects/uaudit/paperclip-agent-assembly.yaml`.
- Add compatibility metadata for UAudit agent ids and workspace paths.
- Extend the project compatibility builder to support explicit manifest agents
  with project-scoped output paths such as `paperclips/dist/uaudit/codex/AUCEO.md`.
- Extend validation/tests for explicit project agents and project-scoped outputs.
- Generate UAudit resolved assembly and codex bundles for compare/dry-run only.

## Out Of Scope

- No live UAudit deployment in this slice.
- No changes to Gimle generated bundles unless the test/build pipeline proves
  they are intentionally regenerated and byte-identical to the current state.
- No migration of Claude-local UAudit agents.
- No renaming of existing UAudit agents.
- No removal of legacy Gimle compatibility files.

## Affected Areas

- `paperclips/scripts/build_project_compat.py`
- `paperclips/scripts/validate_instructions.py`
- `paperclips/scripts/deploy_project_agents.py` only if dry-run selection needs a
  manifest-agent fix
- `paperclips/tests/test_validate_instructions.py`
- `paperclips/projects/uaudit/**`
- `paperclips/dist/uaudit/codex/**`
- `paperclips/dist/uaudit.resolved-assembly.json`

## Design

The manifest remains the project-specific source of truth for UAudit facts:
company id, issue prefix, source repos, codebase-memory projects, project MCP
additions, live workspace paths, and agent ids.

Shared role logic remains in the existing role fragments. UAudit-specific
runtime facts are provided through manifest variables and overlays. The builder
must support explicit agent entries so an agent can have a stable Paperclip name
like `UWICTO` while still rendering from a generic role source such as
`paperclips/roles-codex/cx-cto.md`.

Generated UAudit bundles must go under a project-scoped output root:
`paperclips/dist/uaudit/codex/`. This prevents accidental overwrite of Gimle
legacy `paperclips/dist/codex/*.md`.

## Acceptance Criteria

- `python3 paperclips/scripts/build_project_compat.py --project uaudit --target codex --inventory skip` builds UAudit codex bundles and resolved assembly.
- `python3 paperclips/scripts/deploy_project_agents.py --project uaudit --target codex --agent AUCEO --dry-run` resolves AUCEO from the UAudit manifest output.
- `python3 paperclips/scripts/validate_instructions.py --repo-root .` passes.
- `python -m pytest paperclips/tests/test_validate_instructions.py` passes.
- `./paperclips/build.sh` and `./paperclips/validate-codex-target.sh` pass.
- `git diff -- paperclips/dist paperclips/projects paperclips/scripts paperclips/tests` shows no unintended Gimle bundle changes.

## Verification Plan

1. Build Gimle to establish compatibility behavior.
2. Build UAudit codex target.
3. Validate all Paperclip manifests and generated bundles.
4. Run Paperclip pytest coverage.
5. Run project-aware dry-run for at least AUCEO and one platform CTO.
6. Compare generated UAudit output with live UAudit `AGENTS.md` by path and size;
   report drift instead of deploying.

## Open Questions

- Exact UAudit specialist role mapping can be refined after comparing generated
  output with live agent responsibilities. This slice keeps current agent names
  and records the source role used for each generated bundle.
- Live deploy remains a later step after review of generated-vs-live diffs.
