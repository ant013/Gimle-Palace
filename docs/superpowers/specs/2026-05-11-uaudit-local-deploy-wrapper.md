# UAudit Local Agent Deploy Wrapper

## Goal

Add a safe local deploy path for manifest-built UAudit Codex bundles so an
operator can update live `AGENTS.md` files from `paperclips/dist/uaudit/codex`
without hand-copying files.

## Assumptions

- UAudit generated bundles are already committed under
  `paperclips/dist/uaudit/codex/*.md`.
- UAudit live workspaces are recorded in
  `paperclips/dist/uaudit.resolved-assembly.json` as `workspaceCwd`.
- Live deploy means writing `<workspaceCwd>/AGENTS.md` on the local filesystem.
- Paperclip API upload remains out of scope for this slice.

## Scope

- Extend `paperclips/scripts/deploy_project_agents.py` with:
  - `--live-local` for local filesystem deploy.
  - `--backup-dir` for live `AGENTS.md` backups.
  - `--rollback <backup-file>` for restoring one backup.
  - path and content guards before writing.
- Add tests covering dry-run compatibility, live-local backup/write, rollback,
  and missing workspace protection.

## Out Of Scope

- No API deploy.
- No automatic issue creation or agent wake.
- No deploy of Gimle bundles.
- No change to generated UAudit bundle content.

## Safety Rules

- `--dry-run` remains non-writing and is the default safe path.
- `--live-local` must require a specific `--agent`; no all-agent live deploy in
  this slice.
- Source bundle must exist and match the resolved assembly `sha256`.
- Target `workspaceCwd` must exist and contain no shell expansion or relative
  path.
- Live target path is always `<workspaceCwd>/AGENTS.md`.
- Existing live file must be copied to the backup directory before replacement.
- Rollback restores one explicit backup file and refuses paths outside the
  backup directory unless `--backup-dir` is set to that parent.

## Acceptance Criteria

- `python3 paperclips/scripts/deploy_project_agents.py --project uaudit --target codex --agent AUCEO --dry-run` still reports the intended deploy.
- `python3 paperclips/scripts/deploy_project_agents.py --project uaudit --target codex --agent AUCEO --live-local --backup-dir /tmp/...` writes only AUCEO live `AGENTS.md` and creates a backup.
- `python3 paperclips/scripts/deploy_project_agents.py --rollback <backup> --backup-dir /tmp/...` restores the backup.
- `python -m pytest paperclips/tests/test_validate_instructions.py` passes.
- `python3 paperclips/scripts/validate_instructions.py --repo-root .` passes.
- `./paperclips/validate-codex-target.sh` passes.

## Verification Plan

1. Unit test live deploy against temp workspaces.
2. Run full Paperclip validation.
3. Run a real `--dry-run` for `uaudit/AUCEO`.
4. For real UAudit deploy, deploy only `AUCEO` first, verify backup exists,
   compare live size/hash, then rollback if anything is wrong.
