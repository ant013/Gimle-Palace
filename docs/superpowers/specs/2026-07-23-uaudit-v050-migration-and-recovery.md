# UAudit v0.50 Migration Completion and Live Recovery

Status: review-ready

Design revision: 1

Grounded repository state: `origin/develop` at `0e9cf57c00ff970f584256126b500166580e7a72`

Live evidence captured: 2026-07-23 on `Antons-iMac.local`

## Goal

Restore daily Android and iOS UAudit delivery and complete the migration of both
platforms to `version/0.50` without duplicating an already delivered Telegram
report or corrupting the audit cursor.

Observable success means:

- both repository-owned daily routines, roles, rendered bundles, and live
  Paperclip routine descriptions use `version/0.50`;
- both platforms use
  `/Users/Shared/UnstoppableAudit/state/<platform>-version-audit.json` as the
  only active cursor contract;
- the live routine reconciler can map repository logical routine IDs to
  Paperclip UUID routine records and reports a no-op after reconciliation;
- Android `UNS-478` is reconciled without a second Telegram send;
- iOS `UNS-481` is delivered exactly once and reconciled;
- both routine locks are released, obsolete blocked generations are closed,
  both schedules are active, and a fresh manual run reaches a valid terminal
  state.

## Incident Evidence

The server, scheduler, watchdog, and Telegram plugin are healthy. The failures
are contract drift:

- Repository `develop` already has Android on `version/0.50`, but iOS remains
  on `version/0.49`.
- Repository config and the deployed delivery helper define canonical cursors
  under `state/`, while live routine descriptions and hot-patched Android role
  instructions refer to `artifacts/<InfraAgent>/cursor.json`.
- The current reconciler keys API records by `id` and then looks them up using
  logical config IDs such as `daily-android-version-0.50`. Live Paperclip IDs
  are UUIDs, so the current dry-run fails with:

  ```text
  ERROR: routine 'daily-android-version-0.50' not found; creation is not implicit
  ```

- Android `UNS-478` has an immutable successful Telegram receipt
  (`message_id=335`) and a matching held lock. Its state cursor is absent, so
  helper reconciliation stopped after delivery.
- iOS `UNS-481` has a complete validated delivery payload but no Telegram
  receipt and no matching lock. Its `state/` cursor is stale `version/0.49`,
  while the legacy artifact cursor is the verified `version/0.50` FROM SHA.

## Assumptions

- `state/<platform>-version-audit.json` remains the authoritative cursor
  boundary; the helper will not be weakened to accept arbitrary artifact
  paths.
- Existing legacy artifact cursor files remain available as read-only migration
  evidence but are no longer referenced by active routines or roles.
- The `UAudit` Telegram file route remains the approved destination.
- Live routine titles remain unique within the UAudit company. Matching still
  fails closed if the title/marker/platform fallback is ambiguous.
- Before live recovery, both FROM SHAs and all run/receipt digests will be
  revalidated. Any mismatch stops the operation.
- If the post-recovery Android delta exceeds configured limits at execution
  time, normal daily intake will not be widened; a separate bounded catch-up
  path will be created.

## Scope

### In scope

1. Complete repository-owned iOS migration from `version/0.49` to
   `version/0.50`.
2. Keep Android and iOS routine definitions symmetric while preserving their
   platform-specific agents, repository paths, and report filenames.
3. Repair `reconcile_uaudit_routines.py` so it:
   - resolves logical routine definitions to live UUID routines;
   - renders canonical descriptions from config plus operator `paths.yaml`;
   - patches assignee and description drift through
     `PATCH /api/routines/<uuid>`;
   - uses `baseRevisionId` for optimistic concurrency;
   - fails on missing or ambiguous matches and never creates routines.
4. Add tests for the current UUID API shape, description drift, no-op behavior,
   ambiguous matches, and revision-bound apply requests.
5. Document the state-cursor migration and receipt-safe recovery invariant.
6. Deploy the approved bundles and repair the two existing live generations.
7. Close only the obsolete UAudit daily issues superseded by the repaired
   generations, then execute and monitor fresh routine runs.

### Out of scope

- Changing audit limits (`30` commits, `300` files, `3000` diff lines).
- Changing schedules, Telegram destinations, audit findings, or product source.
- Modifying the deployed delivery helper to accept legacy artifact cursors.
- Deleting legacy cursor files or historical `phase_f` baselines.
- Re-sending the Android `UNS-478` report.
- Broad refactors of the Paperclip build/deploy system.

## Affected Areas

Expected repository files:

- `paperclips/projects/uaudit/daily-version-branch-routines.yaml`
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/dist/uaudit/codex/UWICTO.md` (generated)
- `paperclips/dist/uaudit/codex/UWIInfraEngineer.md` (generated)
- `paperclips/scripts/reconcile_uaudit_routines.py`
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`
- `paperclips/scripts/imac-agents-deploy.README.md`
- `docs/paperclip-operations/telegram-report-delivery.md`

Expected live areas:

- two Paperclip routine records and their revisions;
- deployed UAudit agent `AGENTS.md` bundles;
- `state/android-version-audit.json`;
- `state/ios-version-audit.json` plus a preserved v0.49 backup;
- the Android and iOS `version/0.50` lock directories;
- issues `UNS-478` and `UNS-481`;
- superseded daily issues explicitly listed in the live recovery section.

## Design

### 1. Canonical routine identity and description

Add an exact `title` to each configured routine. The desired description is
rendered deterministically as:

```text
UAudit daily version-branch delta audit
routine_id: <logical config id>
platform: <android|ios>
branch: version/0.50
repo: <rendered repo path>
cursor: <rendered state cursor path>
```

The new `routine_id:` line becomes the stable future match key. For the first
migration of existing records that lack it, use an exact fallback over:

- routine title;
- the configured marker line;
- exact `platform:` line;
- absence of a conflicting `routine_id:`.

Zero or multiple candidates are errors. Logical ID and live UUID stay separate
in the plan output.

Host paths are loaded with the existing precedence:

1. `~/.paperclip/projects/<project>/paths.yaml`;
2. committed `paths.local-example.yaml` for tests/CI.

Template resolution uses the existing strict
`resolve_template_sources.resolve` contract. Unresolved placeholders fail the
plan.

### 2. Revision-safe reconciliation

The dry-run plan reports, per routine:

- logical routine ID;
- live UUID;
- live revision ID;
- current and desired assignee;
- current and desired description;
- a bounded patch object;
- whether an update is needed.

Apply mode sends only changed mutable fields plus:

```json
{"baseRevisionId": "<latestRevisionId>"}
```

to `PATCH /api/routines/<live UUID>`. A revision conflict is surfaced and not
blindly retried. Routine creation remains unsupported. Schedule triggers,
catch-up policy, priority, and status are not changed by the reconciler.

### 3. Live recovery ordering

All mutable steps use a fresh read immediately before the write.

1. Revalidate the two routine records, relevant issue states, helper install,
   run payloads, cursor SHAs, lock metadata, and delivery receipt.
2. Pause both live routines with revision-bound routine PATCHes so no new
   generation can overlap recovery.
3. Deploy the approved UAudit bundles from merged `develop` using the supported
   `--from-develop` smoke path. Verify both platform roles say
   `version/0.50` and use `state/` cursors.
4. Run the repaired reconciler in dry-run and apply modes. Verify a second
   dry-run is a no-op while routines remain paused.
5. Preserve the old iOS state cursor as a timestamped v0.49 backup. Do not
   delete either legacy artifact cursor.
6. Atomically seed canonical FROM cursors:
   - Android from verified `UNS-473` /
     `4b32556a4196e1fde1c8de3d082922b1231a912a`;
   - iOS from verified `UNS-459` /
     `86451ae5a691aff73883232cda80b2a9f962d8d3`.
7. Write a non-secret migration manifest containing source/destination paths,
   before/after hashes, issue IDs, and timestamps.
8. Android recovery:
   - post explicit Board resume approval on `UNS-478`;
   - wake `UWAInfraEngineer` under corrected instructions;
   - require it to reuse the existing receipt and execute helper
     `reconcile-daily`;
   - verify cursor advances to
     `f49bd4a78eea0f13eaa27d787977f66311afd46e`, `cursor.done` and
     `workflow.done` exist, the lock is released, and no second Telegram
     delivery occurred.
9. iOS recovery:
   - recreate only the exact
     `state/locks/daily-ios-version-0.50.lock` metadata bound to `UNS-481`
     and its existing run-context digest;
   - post explicit Board resume approval;
   - wake `UWIInfraEngineer` under corrected instructions;
   - require one Telegram receipt followed by helper `reconcile-daily`;
   - verify cursor advances to
     `8a63bfda028dd8543115b26dd777235a53304311`, terminal markers exist,
     and the lock is released.
10. Close superseded generations with an explanatory Board comment:
    - Android: cancel `UNS-476`, `UNS-482`, `UNS-485`, `UNS-487`, and
      `UNS-490` after `UNS-478` is terminal.
    - iOS: mark `UNS-480` done after its catch-up `UNS-481` is terminal;
      cancel `UNS-483`, `UNS-486`, `UNS-488`, `UNS-489`, and `UNS-491`.
11. Re-enable both routines with fresh `baseRevisionId` values.
12. Trigger each routine once manually with distinct idempotency keys and
    monitor it to terminal state:
    - iOS should be a no-op unless upstream changed;
    - Android audits the remaining verified delta if it is within limits.
13. Verify live reconciler dry-run is a no-op, routines are active, locks are
    absent, cursors are current, Telegram plugin remains ready, and the next
    scheduled run timestamps are populated.
14. After the validated change is included in the normal release cut to
    `main`, run the production UAudit agent deploy without `--from-develop`.
    Verify the deployed bundle hashes and reconciler no-op are unchanged. This
    prevents a later main-based deploy from reverting the live migration.

At no point is a cursor advanced by an operator directly to a TO SHA. The
operator may only seed the verified FROM state needed to restore the helper's
compare-and-set contract; the deployed helper performs every TO advancement.

## Analog Delta Matrix

| Slice | Analog family | Coverage | Invariants to preserve | Required differences | Rejected differences | Failure modes | Tests before code | Verification |
|---|---|---|---|---|---|---|---|---|
| Canonical v0.50 config | Primary: current Android v0.50 config/role/overlay/dist family. Supporting: symmetric generated-bundle tests. Counterexample: hard-coded v0.49 reconcile fixture. | Contract, implementation, composition, consumers, lifecycle language, generated output, and tests are present. | Platform-specific repo paths and agents; state cursor root; staged daily chain; delivery-after-audit rule. | Apply the Android v0.50 shape to iOS and add stable routine titles/IDs for reconciliation. | Editing historical baselines, widening limits, or copying Android agent names into iOS. | Mixed branch text; stale rendered dist; wrong filename; artifact cursor reintroduced. | Assert both active routines are v0.50/state and generated bundles contain no active v0.49 path. | Build uaudit codex bundles, targeted pytest, exact `rg` drift scan, diff review. |
| Live routine reconciliation | Primary: current dry-run/apply reconciler skeleton. Supporting: host-local template resolver, Paperclip update schema, reconcile tests. Counterexample: UUID-keyed normalization plus logical-ID lookup and obsolete endpoint. | CLI lifecycle, auth boundary, path dependency, API revision contract, failure path, and test seam are covered. | Default dry-run; no implicit creation; names resolved through bindings; fail closed on missing data. | Stable description identity, UUID matching, canonical rendered description, `/api/routines/<uuid>`, and `baseRevisionId`. | Persisting environment UUIDs in committed config; fuzzy first-match behavior; blind retry on conflict. | Missing/duplicate routine; unresolved paths; stale revision; partial multi-routine apply. | Reproduce current “routine not found”; add UUID, ambiguity, no-op, description drift, and apply-request tests. | Targeted pytest, fixture dry-run, authenticated live dry-run/apply/no-op. |
| Cursor and lock recovery | Primary: deployed receipt-bound `reconcile_daily` CAS. Supporting: repository state contract and the two immutable run states. Counterexample: manual TO overwrite or duplicate send. | Receipt, lock, cursor lifecycle, trust boundary, idempotent markers, consumers, and live verification commands are covered. | Immutable run context; exact lock binding; delivery before cursor; FROM/TO CAS; no overlapping generation. | Seed canonical FROM state, restore only the missing iOS lock, resume Android without send and iOS with one send. | Changing helper path checks, deleting evidence, resending Android, or force-clearing locks. | Wrong SHA/digest; duplicate Telegram send; stale cursor overwrite; schedule race; oversized new delta. | Existing helper verification commands and pre-mutation hash/API snapshot; no direct code-unit seam exists for host state. | Helper verify/reconcile output, marker/hash checks, issue/routine API states, manual end-to-end routine runs. |

## Verification Plan

### Repository checks

```bash
python3 -m pytest paperclips/tests/test_uaudit_dispatcher_bundles.py -q
python3 paperclips/scripts/validate_uaudit_docs.py
bash paperclips/build.sh --project uaudit --target codex
git diff --check
```

Then verify generated output is stable and scoped:

```bash
git status --short
rg -n 'daily-(android|ios)-version-0\\.49|version/0\\.49|UWAInfraEngineer/cursor|UWIInfraEngineer/cursor' \
  paperclips/projects/uaudit paperclips/dist/uaudit/codex \
  paperclips/scripts/reconcile_uaudit_routines.py \
  paperclips/tests/test_uaudit_dispatcher_bundles.py
```

Any remaining `0.49` match must be intentionally historical and outside the
active paths above.

### Live checks

- Paperclip routine GET before/after with UUID, description, status,
  `latestRevisionId`, trigger enabled state, and next run timestamp.
- Reconciler dry-run before apply, apply output, and no-op dry-run after apply.
- Deployed role-file exact checks for branch and cursor constants.
- SHA-256 and JSON-schema checks for both canonical cursor files, both run
  contexts, receipts, and lock metadata.
- `verify-install`, `verify-payload`, and `reconcile-daily` helper commands.
- Android proof that `message_id=335` remains the only `UNS-478` receipt.
- iOS proof of exactly one new `UNS-481` receipt.
- Issue terminal states and absence of both routine lock directories.
- Manual routine runs monitored to terminal state.
- Telegram plugin `ready` with no `lastError`.

## Acceptance Criteria

1. Active repository paths contain no iOS `version/0.49` routine, role, bundle,
   filename, or no-op message.
2. Both config routines use canonical state cursor templates and stable titles.
3. Current live UUID routine payloads can be reconciled without storing UUIDs
   in committed config.
4. Reconciler dry-run is deterministic; apply is revision-bound; a second
   dry-run reports no changes.
5. Tests fail against the old logical-ID/UUID behavior and pass after the fix.
6. Android `UNS-478` is terminal, its canonical cursor is TO, its lock is gone,
   and no duplicate Telegram send exists.
7. iOS `UNS-481` is terminal, its canonical cursor is TO, its lock is gone, and
   exactly one delivery receipt exists.
8. Legacy cursor evidence and the old iOS v0.49 state are preserved
   recoverably.
9. Superseded blocked daily issues are terminal with explicit provenance.
10. Both routines are active with canonical descriptions and successful fresh
    manual-run evidence.
11. No secrets are written to source, logs, migration manifests, issue
    comments, or reports.
12. The release-cut `main` contains the migration and the final production
    agent deploy preserves the verified `develop` smoke state.

## Rollback

- Repository rollback uses the previous known-good commit and the documented
  agent deploy `--target-sha` path.
- Live routine rollback uses Paperclip routine revisions, not hand-reconstructed
  payloads.
- Cursor rollback is allowed only before a new successful generation consumes
  the migrated cursor. Restore the preserved pre-migration file and routine
  revision together while routines are paused.
- A Telegram receipt is never rolled back or resent. If a post-send
  reconciliation fails, recovery resumes from that immutable receipt.

## Open Questions

No design choice is currently blocking.

Execution-time gates remain:

- protected-branch review and merge must complete before `--from-develop`
  deployment;
- the normal release cut to `main` and production agent deploy must complete
  before the migration is considered durable;
- all live SHAs, revisions, and issue states must still match the evidence
  recorded here;
- an oversized post-recovery upstream delta requires a separate catch-up
  decision rather than an implicit limit change.
