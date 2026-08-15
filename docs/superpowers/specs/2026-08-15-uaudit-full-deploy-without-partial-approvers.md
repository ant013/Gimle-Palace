# UAudit: permit full-audit deployment without partial approver configuration

## Grounding and problem

Grounded in `origin/develop` at `b4c6bac9998f6dafa5cc6b4c6f084b6beaa7dde8`
(2026-08-15). A production deploy from the release commit reaches
`bootstrap-project.sh` and stops before prompt deployment because
`/Users/Shared/UnstoppableAudit/state/partial-approvers.json` is absent.

The file is only consumed by `uaudit_delivery_contract.reconcile_daily` when a
daily summary has `audit_status == "partial"`. Complete daily and forced-full
runs do not use it. An absent partial approver allowlist must continue to make
partial reconciliation fail closed, but it must not prevent deployment or an
explicit forced-full audit.

## Goal and observable success

Deploying UAudit from a valid release checkout succeeds without
`state/partial-approvers.json`; its helper, role bundles, agent instructions,
and routine configuration are installed normally. A partial daily reconciliation
with no valid allowlist still fails before cursor mutation or Telegram resend.

## Assumptions and open questions

- The existing host-local bindings, paths, and project state are valid.
- No verified human actor IDs are currently available. This change must not
  invent them, create an empty allowlist, or approve a partial result.
- The production source checkout remains user-dirty and is out of scope for
  branch switching; prompt deployment must use the documented clean release
  worktree.
- Open question: none for the source behavior. A later partial reconciliation
  still needs operator-supplied, verified actor IDs.

## Scope

In scope:

- Move the host-local partial-approver validation out of the unconditional
  UAudit bootstrap/deploy path.
- Preserve the deployed-helper validation/installation and all normal prompt,
  routine, and agent deployment work.
- Add behavioural coverage proving deploy prerequisites do not require an
  allowlist while `reconcile-daily` still does for partial summaries.
- Update the existing bootstrap source-contract assertion to express the
  narrower invariant.

Out of scope:

- Adding, changing, or guessing any human actor ID.
- Altering partial receipt, approval, cursor-CAS, lock, or Telegram semantics.
- Bypassing daily limits. Forced-full remains the explicitly authorised
  unlimited path and must keep its cursor prohibition.
- Switching, cleaning, or committing the current production checkout.

## Affected areas

- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`
- New/extended bootstrap integration coverage only if the existing test seams
  cannot exercise a no-allowlist host layout.

## Analog family and delta matrix

| Slice | Primary analog | Supporting / counterexample | Invariant | Required delta | Rejected alternative | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| Bootstrap optionality | Existing plugin configuration branch: absent or placeholder routing config is logged and skipped while the rest of bootstrap proceeds | `reconcile_daily` is the security counterexample: partial status requires both comments and an allowlist | Bootstrap still validates requirements needed to deploy; helper install remains fail-closed | Do not validate `partial-approvers.json` during bootstrap | Auto-create an empty list; suppress validation everywhere; make a partial audit complete | A no-allowlist UAudit bootstrap reaches deploy; helper contract test still rejects partial reconciliation without both arguments |
| Partial reconciliation | `reconcile_daily` branch on `audit_status == "partial"` | Existing partial approval/cursor test | No valid allowlist means no partial cursor update | Keep the exact runtime validation and path binding untouched | Accept a generic file, agent ID, or incomplete approval | Existing partial test remains green; add an explicit absence case if coverage is not already direct |
| Release operation | `imac-agents-deploy.sh` release worktree handoff | Current hard-stop is the rejected counterexample because it couples deploy to a condition not required by full audits | Release content, helper manifest and prompt bundles come from the same pinned `origin/main` SHA | Bootstrap no longer blocks a release merely because a partial-only state file is absent | Bypass the deploy wrapper by using dirty production source | Clean-worktree deploy log and routine dry-run evidence |

## Design

1. Keep `validate_uaudit_partial_approvers` as the validator for any explicit
   partial-recovery operator action, but remove its unconditional invocation
   from `bootstrap-project.sh`.
2. Retain the `project_root` resolution only where it is still required, and
   retain unconditional `team_workspace_root` validation plus immutable helper
   installation for UAudit bootstrap.
3. Keep `reconcile_daily` unchanged: it requires comments and the exact
   state-adjacent allowlist only when the summary is partial; complete runs
   reject approval arguments.
4. Replace the current text-presence test with behavioural assertions that
   distinguish deployment prerequisites from partial reconciliation safeguards.
5. Deploy the merged release from a clean worktree, run routine reconciliation
   dry-run then `--apply`, and launch the authorised forced-full range. Do not
   resume partial iOS recovery unless a verified operator allowlist is later
   supplied.

## Acceptance criteria

1. An absent `state/partial-approvers.json` no longer prevents UAudit bootstrap
   from building/deploying prompts and installing/verifying the helper.
2. Missing, empty, malformed, non-human, or unapproved partial evidence still
   prevents `reconcile-daily` from advancing a cursor.
3. No production checkout with user changes is reset, switched, stashed, or
   committed.
4. Existing forced-full Russian delivery, daily cursor, receipt, and lock
   guarantees remain unchanged.
5. The change is merged through `develop` and included in a release to `main`
   before runtime deployment.

## Test and verification plan

Before implementation, add a failing test that models the absent allowlist at
bootstrap level; it must reach the bootstrap/deploy path rather than fail on
the missing file. Keep or add a delivery-contract case in which a partial run
without approval arguments fails and leaves the cursor bytes unchanged.

Run:

```bash
uv run --with pytest --with PyYAML python -m pytest \
  paperclips/tests/test_uaudit_dispatcher_bundles.py \
  paperclips/tests/test_uaudit_delivery_contract.py -q
python3 paperclips/scripts/build_project_compat.py --project uaudit --target codex --inventory check
```

After merge and release, run the documented clean-worktree deploy and capture:

- deployed helper manifest verification;
- generated `UWACTO` and `UWICTO` bundle checks;
- reconciler dry-run and successful `--apply` output for Android/iOS;
- forced-full issue/receipt evidence; and
- confirmation that no partial iOS cursor reconciliation occurred without a
  verified allowlist.

## Adversarial review

- **Security:** removing bootstrap validation must not relax runtime partial
  validation. The implementation deliberately keeps the helper branch and
  approval path unchanged.
- **Operational:** deploying prompts from an arbitrary dirty checkout is not a
  fix; only a pinned clean release worktree is acceptable.
- **Scope:** changing daily limits, cursor semantics, Telegram routing, or the
  partial approval protocol is excluded.
- **Regression:** a source-string-only test could pass while bootstrap still
  fails for another accidental allowlist access. The new test must execute the
  relevant bootstrap prerequisite path or a bounded extracted seam.
