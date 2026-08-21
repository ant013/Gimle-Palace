# UAudit: reconcile versioned routine locks with stable routine identities

Status: review-ready

Grounded repository state: `origin/develop` at
`14c52e1110cbe9cfe59f20ac09010b646ac9dd04`.

## Goal

Unblock receipt-led reconciliation of the already delivered Android daily
audit without weakening the cursor, lock, immutable run-binding, or partial
approval safeguards.

The live Android generation has a stable routine ID in its bound source
reference, while its valid, held lock directory uses the deployed versioned
name `daily-android-version-0.50.lock`. The helper currently rejects it before
it reads the lock metadata solely because the basename differs.

## Assumptions

- A daily lock remains valid only when it is an immediate child of the same
  `state/locks` directory as the canonical platform cursor.
- `metadata.json` remains the authority for ownership: it must match the
  issue, routine ID, SHA range, and immutable run-binding digest.
- Recovery will use the normal helper after deployment. It will not write a
  cursor, remove a lock, replay Telegram, or create terminal markers manually.

## Scope

1. Replace the basename equality check in `reconcile_daily` with a check that
   the resolved lock is an immediate `*.lock` child of the cursor's
   `state/locks` directory.
2. Preserve the existing `_lock_metadata` validation unchanged, including its
   run-binding digest check.
3. Add a focused regression fixture/test proving that a stable routine ID may
   reconcile through a matching, metadata-bound versioned lock basename.
4. Retain the existing copied-lock rejection test.

## Non-scope

- No change to the routine configuration, schedules, state files, generated
  agent bundles, delivery receipt, approval rules, or cursor CAS semantics.
- No manual repair of live cursor/lock state and no duplicate Telegram send.
- No attempt to resolve the stale iMac Paperclip worker through this source
  patch; deployment/recovery follows the existing operator flow.

## Affected areas

- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py`
- `paperclips/tests/test_uaudit_delivery_contract.py`

## Design delta matrix

| Slice | Verified analog | Change | Preserved contract | Verification |
| --- | --- | --- | --- | --- |
| Daily lock reconciliation | `reconcile_daily` plus `_lock_metadata` | Check `lock_dir.parent == cursor_path.parent / "locks"` and `lock_dir.suffix == ".lock"`; do not derive the basename from `source_ref.routine_id` | Canonical cursor location, lock existence, metadata fields, binding digest, cursor CAS, receipt and approval validation | New stable-ID/versioned-lock success case; existing copied-lock and conflicting-cursor cases |

## Acceptance criteria

1. A daily run with source-ref routine ID `uaudit-daily-android` and held
   `state/locks/daily-android-version-0.50.lock` reconciles successfully only
   when the lock metadata matches the immutable run binding.
2. A copied lock outside the cursor's `state/locks` directory remains rejected
   with no cursor change.
3. Metadata with a mismatched routine ID, issue, SHA range, or binding digest
   remains rejected.
4. Existing delivery-contract tests remain green.

## Verification plan

1. Run the focused daily reconciliation tests in
   `paperclips/tests/test_uaudit_delivery_contract.py`.
2. Run the full `test_uaudit_delivery_contract.py` module.
3. Inspect the final diff to ensure only the helper and its test are changed.
4. After merge/deploy, invoke only the documented helper reconciliation for
   the existing Android receipt and inspect its terminal marker/cursor result;
   do not resend Telegram.

## Open questions

None. The lock metadata contract supplies the missing identity proof; the
pathname correction is deliberately bounded to the canonical lock directory.
