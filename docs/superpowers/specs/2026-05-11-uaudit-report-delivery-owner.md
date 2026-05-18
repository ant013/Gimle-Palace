# UAudit Report Delivery Owner

## Assumptions

- UAudit uses the layered Paperclip project assembly under `paperclips/projects/uaudit/`.
- Telegram report delivery is a transport/runtime concern and should be owned by
  infra delivery roles, not every audit role.
- The Telegram plugin routes UAudit report files through `fileRoutes` when the
  caller sends the current `UNS-*` `issueIdentifier`.
- Agent-scoped tokens may still return `Board access required`; that is a
  permission outcome, not a reason to retry through raw Telegram APIs.

## Scope

- UAudit Codex bundles only.
- Add a short non-owner report-delivery ownership rule to the UAudit project
  overlay.
- Add the Telegram send contract only to UAudit infra delivery owners.
- Record project report-delivery params in the UAudit manifest.

## Out Of Scope

- No Gimle, Medic, or TEL instruction changes.
- No Telegram plugin code/config changes.
- No raw chat IDs in role text beyond what is already owned by plugin config.
- No broad shared fragment rendered unconditionally into all projects.

## Affected Areas

- `paperclips/projects/uaudit/paperclip-agent-assembly.yaml`
- `paperclips/projects/uaudit/overlays/codex/_common.md`
- UAudit infra-specific overlays under `paperclips/projects/uaudit/overlays/codex/`
- Generated `paperclips/dist/uaudit/codex/*.md`
- Generated `paperclips/dist/uaudit.resolved-assembly.json`

## Acceptance Criteria

- Non-infra UAudit bundles tell roles to save a final/user-requested Markdown
  report artifact, comment its absolute path, and formally hand off delivery to
  the correct infra owner.
- `UWAInfraEngineer` and `UWIInfraEngineer` bundles contain the endpoint/body
  wrapper contract for `send_to_telegram`.
- Non-owner bundles do not contain `send_to_telegram`.
- Gimle/Medic/TEL bundles do not receive the new UAudit text.
- Bundle size delta is reported and kept small.

## Verification Plan

- Run `python3 paperclips/scripts/build_project_compat.py --project uaudit --target codex --inventory check`.
- Grep generated bundles for non-owner and owner text.
- Run `python3 paperclips/scripts/validate_instructions.py --repo-root .`.
- Run `./paperclips/validate-codex-target.sh`.
- Run UAudit deploy dry-run before live-local deploy.
- Smoke with one non-infra handoff and one infra delivery attempt.
