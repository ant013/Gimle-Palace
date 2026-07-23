# UAudit v0.50 Migration and Daily Delivery Recovery

Status: review-ready

Design revision: 2 — availability-first

Grounded repository state: `origin/develop` at
`0e9cf57c00ff970f584256126b500166580e7a72`

Live evidence captured: 2026-07-23 on `Antons-iMac.local`

## Goal

Restore dependable daily Android and iOS UAudit reports and complete the
migration of both platforms to `version/0.50`.

Availability is the primary criterion. Recovery uses at-least-once Telegram
delivery semantics: a one-time duplicate report during recovery is acceptable.
A stuck pipeline, skipped cursor range, or routine that does not run every day
is not acceptable.

Observable success means:

- repository source, generated bundles, deployed agents, and both live
  Paperclip routines use `version/0.50`;
- the receipt-led delivery helper and its prompts are durable in `main`, not
  only hot-patched on the iMac;
- Android and iOS each complete a fresh manual daily run and deliver a report
  or a validated no-change result;
- both schedules are active, have a next-run timestamp, and can execute without
  legacy cursor, lock, or issue blockers;
- the reconciler maps stable repository routine identities to live Paperclip
  UUID records and converges to a no-op.

## User Decision

The operator explicitly prioritized daily delivery over duplicate prevention:

- recovery may resend an already delivered Android report;
- retry after an indeterminate Telegram result may produce a duplicate;
- duplicate avoidance must not keep either daily routine disabled or blocked.

This does not permit silently skipping commits. Cursor movement must still be
bound to a verified audit range and a successful delivery attempt.

## Incident Evidence

The Paperclip server, scheduler, watchdog, and Telegram plugin are running. The
daily pipelines stopped because repository source, deployed prompts, routines,
and state files describe different contracts:

- `origin/develop` has Android on `version/0.50`, while iOS remains on
  `version/0.49`.
- Live routines describe `version/0.50`, but deployed agents contain a mixture
  of `version/0.49`, `version/0.50`, `state/` cursors, and legacy artifact
  cursors.
- Receipt-led helper source, installation logic, agent prompts, and tests exist
  only on unmerged `origin/feature/uaudit-russian-audit-delivery`
  (`cd919dd1..144169ab`). The deployed helper SHA matches that branch.
- Deploying current `origin/develop` would overwrite the live receipt-led
  prompts with the older direct Telegram/cursor flow.
- The current reconciler looks up logical IDs in a map keyed by live UUIDs and
  PATCHes an obsolete company-scoped endpoint.
- Android `UNS-478` has a successful Telegram receipt and complete audit
  payload, but the canonical state cursor is absent.
- iOS `UNS-481` has a complete payload and no receipt. Its legacy artifact
  cursor is the verified `version/0.50` FROM state.
- iOS `status/bind-context.json` contains a stale digest. The current
  `run-context.json`, delivery summary, and helper agree on
  `918307dea7d692758ca9c1c58062a9166fc9cea19f17e099edcf6e3ba8161c35`.

## Assumptions

- The existing receipt-led delivery contract remains the desired UAudit
  workflow and must be synchronized back into repository source.
- Telegram remains at-least-once. Exactly-once delivery is explicitly not a
  requirement for this repair.
- `state/<platform>-version-audit.json` is the only active cursor location.
- Legacy cursor files remain read-only evidence and are never copied verbatim
  into `state/`.
- Existing blocked issues are recovery inputs, not reasons to leave schedules
  disabled indefinitely.
- Audit limits remain `30` commits, `300` files, and `3000` diff lines.
- If the next delta exceeds those limits, a bounded catch-up generation is
  created instead of widening the daily limits.

## Scope

### In scope

1. Port the receipt-led UAudit delivery family from
   `origin/feature/uaudit-russian-audit-delivery` onto current `develop`.
2. Resolve that family and both daily platforms to `version/0.50`, canonical
   state cursors, and `version/0.50` lock names.
3. Complete the repository-owned iOS `version/0.50` migration.
4. Give each live routine a stable, version-independent repository identity.
5. Repair the reconciler for UUID records, rendered descriptions,
   revision-bound PATCHes, and partial-apply recovery.
6. Deploy source-backed bundles and helper installation through the supported
   release path.
7. Recover or replay the Android and iOS pending ranges with at-least-once
   delivery.
8. Quarantine superseded generations and prove fresh daily runs for both
   platforms before re-enabling schedules.

### Out of scope

- Telegram plugin exactly-once/idempotency implementation.
- Changing Telegram destinations or audit report content.
- Widening daily audit limits.
- Deleting historical run artifacts, receipts, or legacy cursor evidence.
- Broad Paperclip deployment refactors.
- Cleanup of unrelated UAudit PR-audit issues.

## Affected Areas

The exact diff is determined by porting the already implemented receipt-led
family and resolving it against current `develop`. Expected areas include:

- `paperclips/projects/uaudit/daily-version-branch-routines.yaml`
- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py`
- both platform dispatcher role sources
- both InfraEngineer overlays
- daily code, security, crypto, research, and QA producer overlays required by
  the v1 sidecar contract
- corresponding generated `paperclips/dist/uaudit/codex/*.md` bundles
- `paperclips/dist/uaudit.resolved-assembly.json`
- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/scripts/install-paperclip.sh`
- `paperclips/scripts/versions.env`
- `paperclips/scripts/reconcile_uaudit_routines.py`
- `paperclips/scripts/imac-agents-deploy.README.md`
- `docs/paperclip-operations/telegram-report-delivery.md`
- `paperclips/tests/test_uaudit_delivery_contract.py`
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`
- helper/bootstrap/plugin-install contract tests touched by the source branch

Expected live areas:

- deployed UAudit helper and manifest;
- all deployed UAudit agent bundles;
- two live routine records and revisions;
- Android and iOS canonical cursor files and lock directories;
- pending daily generations and their dynamically discovered superseded
  siblings.

## Design

### 1. Synchronize the live delivery contract into source

Port the validated delivery-contract changes from
`origin/feature/uaudit-russian-audit-delivery` rather than blindly merging the
old branch.

Conflict resolution must preserve current `develop` changes and apply these
requirements:

- Android and iOS routine IDs, branches, filenames, run bindings, and lock names
  use `version/0.50`.
- Both Infra roles use the deployed helper for `verify-install`,
  `verify-payload`, `record-delivery`, and `reconcile-daily`.
- All daily stages produce the structured sidecars expected by the helper.
- The helper is installed atomically by repository-owned bootstrap logic and
  verified through its adjacent manifest.
- Old direct-send/manual-cursor instructions are absent from active bundles.
- Generated bundles and tests are rebuilt from source.

No UAudit deploy is allowed until the source helper, rendered prompts, and tests
form one consistent `version/0.50` family.

### 2. Stable routine identity

Keep the versioned workflow ID for run context and locks:

```yaml
id: daily-ios-version-0.50
routine_key: uaudit-daily-ios
title: UAudit daily iOS version-branch audit
```

Android uses `routine_key: uaudit-daily-android`.

The desired live description is rendered deterministically:

```text
UAudit daily version-branch delta audit
routine_key: <uaudit-daily-android|uaudit-daily-ios>
platform: <android|ios>
branch: version/0.50
repo: <rendered repo path>
cursor: <rendered state cursor path>
```

Future matching uses the unique exact `routine_key`. Initial migration of a
record without a key uses exact title, marker, and platform. A missing,
duplicate, malformed, or conflicting key fails closed. A future migration to
`0.51` updates the versioned workflow ID and description while retaining the
same live UUID and `routine_key`.

Config validation requires unique, non-empty, single-line IDs, keys, titles,
platforms, branches, and templates.

### 3. Revision-safe routine reconciliation

The reconciler:

- loads host paths from `~/.paperclip/projects/uaudit/paths.yaml`, falling back
  to the committed example only for tests;
- uses the existing strict template resolver;
- separates logical workflow ID, stable routine key, and live UUID;
- builds and validates the complete two-routine plan before any write;
- fetches each routine again immediately before PATCH;
- PATCHes only changed assignee/description fields plus the fresh
  `baseRevisionId` to `/api/routines/<live UUID>`;
- verifies each write with a post-write GET;
- never creates routines or changes schedules;
- reports structured `updated`, `failed`, and `not_attempted` records and exits
  non-zero after a partial apply;
- converges safely when the operator reruns it after a conflict.

Tests cover UUID payloads, stable-key migration, ambiguous identity,
description drift, no-op behavior, stale revisions, first-PATCH-success plus
second-PATCH-409, and successful rerun.

### 4. Release and quiescence gates

Before state recovery:

1. Merge the implementation into `develop`.
2. Pause both routines and all UAudit agents, then wait for zero active
   heartbeat runs.
3. Capture a fresh dynamic snapshot of open routine-generated issues.
4. Deploy `--from-develop` for a paused smoke and verify source/rendered/helper
   hashes.
5. Complete the normal release cut to `main`.
6. Run the production UAudit deploy from `main`.
7. Verify the deployed helper manifest and active bundle hashes match `main`.
8. Run reconciler dry-run/apply/no-op while routines remain paused.

Failure before step 7 leaves the routines and agents paused and performs no
cursor or Telegram recovery.

### 5. Canonical cursor migration

Preserve the old iOS state file as a timestamped backup. Legacy artifact
cursors remain unchanged.

Create each canonical FROM cursor atomically with exactly:

```json
{"last_successfully_audited_sha":"<verified FROM SHA>"}
```

No `platform`, `branch`, operator note, legacy `sha`, or timestamp key is copied.
After rename, re-read the file, require the exact key set, and record its SHA-256
in a non-secret migration manifest.

Verified FROM values:

- Android: `4b32556a4196e1fde1c8de3d082922b1231a912a`
- iOS: `86451ae5a691aff73883232cda80b2a9f962d8d3`

Only the helper writes the expanded TO cursor metadata.

### 6. Availability-first recovery

Recover one platform at a time. Keep schedules paused and enable only the agents
needed for the current platform.

#### Android

Preferred path:

- validate the `UNS-478` payload, existing receipt, run context, and lock;
- post explicit resume approval;
- wake the corrected Android Infra role;
- let it reuse the receipt and reconcile the cursor to
  `f49bd4a78eea0f13eaa27d787977f66311afd46e`.

Availability fallback:

- if the receipt-led generation cannot be reconciled because its immutable
  artifacts are inconsistent, create a fresh bounded recovery generation for
  the same verified FROM..TO range;
- allow Telegram delivery again;
- require helper reconciliation to the same TO.

A duplicate Android report is acceptable. Direct cursor advancement without a
successful recovery generation is not.

#### iOS

- recompute the canonical `run-context.json` digest immediately before lock
  creation;
- require it to equal the delivery summary and `verify-payload` result;
- reject stale `status/bind-context.json` digest evidence;
- recreate the exact `daily-ios-version-0.50.lock` metadata for `UNS-481`;
- post explicit resume approval and wake the corrected iOS Infra role;
- retry the at-least-once Telegram step when necessary;
- require helper reconciliation to
  `8a63bfda028dd8543115b26dd777235a53304311`.

One or more duplicate iOS messages during an indeterminate recovery are
acceptable. The cursor must advance only after a successful receipt is
recorded.

### 7. Fresh daily proof and activation

After both recovery cursors reach their verified TO values:

1. Dynamically query open issues by `originKind=routine_execution` and each live
   routine UUID.
2. Cancel only no-receipt generations superseded by the recovered ranges.
3. Keep schedules paused and manually run iOS, then Android, with distinct
   idempotency keys.
4. Monitor each run to a valid terminal state. If the upstream head is
   unchanged, a validated no-change result is acceptable.
5. Confirm no active lock remains for either completed generation.
6. Activate both routines last with fresh revision IDs.
7. Verify next-run timestamps, Telegram plugin readiness, and reconciler no-op.

The issue numbers observed during diagnosis remain baseline evidence, not an
exhaustive cleanup list.

## Verification Plan

Repository checks:

```bash
python3 -m pytest paperclips/tests/test_uaudit_delivery_contract.py -q
python3 -m pytest paperclips/tests/test_uaudit_dispatcher_bundles.py -q
python3 -m pytest paperclips/tests/test_phase_c_bootstrap_project.py -q
python3 -m pytest paperclips/tests/test_phase_c_install_paperclip.py -q
python3 paperclips/scripts/validate_uaudit_docs.py
bash paperclips/build.sh --project uaudit --target codex
git diff --check
```

Targeted drift scan:

```bash
rg -n 'daily-(android|ios)-version-0\.49|version/0\.49|artifacts/.*/cursor\.json' \
  paperclips/projects/uaudit paperclips/dist/uaudit/codex
```

Remaining `0.49` text is allowed only in historical specs, baselines, or
migration evidence.

Live checks:

- zero active UAudit heartbeat runs before deploy and recovery;
- deployed helper/manifest and bundle hashes match released source;
- both routine GETs show stable keys, `version/0.50`, state cursors, fresh
  revisions, and paused status during recovery;
- helper `verify-install`, `verify-payload`, and `reconcile-daily` succeed;
- canonical cursor JSON passes exact-key validation;
- recovery delivery has at least one successful receipt; duplicate count is
  recorded but does not fail acceptance;
- fresh iOS and Android manual runs reach terminal state;
- no active completed-generation locks remain;
- routines are active only after manual proof and have next-run timestamps;
- Telegram plugin remains ready with no `lastError`.

## Acceptance Criteria

1. Receipt-led UAudit source, helper installation, prompts, generated bundles,
   and tests are present in released `main`.
2. Both active platform families use `version/0.50` and canonical state cursors.
3. Stable routine keys map to the existing live UUIDs and survive a simulated
   `0.50 -> 0.51` description migration.
4. Reconciler dry-run/apply/rerun is revision-safe and converges after partial
   failure.
5. Android recovery reaches its verified TO cursor and has at least one
   successful delivery receipt.
6. iOS recovery reaches its verified TO cursor and has at least one successful
   delivery receipt.
7. Duplicate recovery messages, if any, are documented and do not block
   completion.
8. Both platforms complete a fresh manual daily run under the released prompts.
9. Both schedules are active, have future next-run timestamps, and no stale
   generation can block the next run.
10. Legacy evidence remains recoverable and no secrets appear in source,
    manifests, logs, comments, or reports.

## Rollback and Failure Handling

- Before any recovery Telegram receipt, repository/deploy/routine changes may be
  rolled back while all UAudit execution remains paused.
- After a successful receipt or cursor CAS, do not revert that platform to
  `version/0.49`; continue forward from the recorded receipt and cursor.
- Success on one platform is retained if the other platform fails.
- A deployment, helper, or reconciler failure leaves schedules paused and
  produces an explicit operator-visible blocker.
- An indeterminate Telegram result may be retried because availability and
  eventual daily delivery take precedence over duplicate suppression.

## Open Questions

No product decision is blocking. The operator has accepted at-least-once
delivery and possible recovery duplicates.

Execution-time gates remain:

- the receipt-led source family must be reconciled with current `develop`;
- protected-branch review and release to `main` must complete before live state
  recovery;
- live SHAs, revisions, run digests, and issue states must be re-read before
  every mutation;
- an oversized post-recovery delta requires a bounded catch-up generation.

## Analog Delta Matrix

| Slice | Primary analog | Preserved invariants | Required delta | Rejected alternative | Verification |
|---|---|---|---|---|---|
| Source/live delivery convergence | Receipt-led family on `origin/feature/uaudit-russian-audit-delivery` and its deployed helper | Structured sidecars, helper validation, receipt before cursor, lock-bound run context | Port onto current `develop`; resolve both platforms and locks to `version/0.50`; preserve newer develop fixes | Deploy current develop and overwrite the live helper prompts | Helper, bootstrap, bundle, and generated-output tests; released/deployed hash comparison |
| Version migration | Current Android `version/0.50` family plus iOS migration commit `92738184` | Platform-specific agents, repos, filenames, limits, staged chain | Apply the same version/cursor/lock contract to iOS and all receipt-led consumers | Change only five visible iOS files while leaving v1 prompts on `0.49` | Build, targeted drift scan, symmetric bundle assertions |
| Routine reconciliation | Existing dry-run CLI plus Paperclip UUID/revision API | Default dry-run, no implicit creation, host bindings, fail closed | Stable version-independent key, rendered description, UUID PATCH, per-record CAS and partial-apply resume | Versioned key or fuzzy title-first matching | UUID, ambiguity, version-transition, 409, rerun, and no-op tests |
| Live recovery | Deployed helper FROM/TO CAS and existing complete runs | No skipped range, receipt before cursor, one active generation per platform | At-least-once retry and duplicate-tolerant recovery; exact cursor schema; corrected iOS digest | Exactly-once claim or direct unbound TO write | Helper verification, receipt/cursor/lock evidence, fresh manual runs |
