# UAudit: continuous daily audit across release lines without intake caps

## Goal

Restore continuous daily Android and iOS UAudit runs. A daily audit must not
stop because a configured release line has been superseded or because the
delta is large. When the configured `version/X.Y` branch is gone, it must use
only the strictly next release line and audit the continuous history from the
last saved cursor through `master` to that release head.

For the currently observed upstream state this means Android may move from
`version/0.50` to `version/0.51`; iOS remains on `version/0.50` until its own
strict successor exists. This is per platform, never a global `0.51` switch.

## Assumptions

- `master` and release-line heads are fetched directly from the declared
  upstream remote into the dedicated `uaudit-upstream` namespace.
- The existing daily cursor remains the sole start point, and its current SHA
  is a real Git object in the declared checkout.
- `version/X.(Y+1)` is the only permissible automatic successor. A missing
  branch, a skipped version, ambiguous ancestry, or a rewritten/ref-invalid
  history cannot produce a no-op or advance a cursor.
- The existing UAudit receipt, delivery, partial-approval, lock, and
  compare-and-swap cursor contracts remain authoritative.

## Scope

### 1. Release-line continuity

- Extend the existing pure release resolver with a small command-line adapter
  that accepts only validated, direct-Git facts and emits a JSON `Resolution`.
  The adapter performs neither Git access nor state writes. Install and verify
  that resolver beside the delivery helper as a separately manifest-bound,
  read-only runtime tool; a dispatcher must never use an unverified repository
  checkout copy.
- Change both platform-dispatcher role sources to fetch the configured release
  branch and `master`; if the configured release ref is absent, probe only
  `version/<same-major>.<minor+1>`. They must collect and validate the
  ancestry facts required by `resolve_release_history`.
- For a proven successor transition, prove and record ordered segments
  `cursor -> master` followed by `master -> successor release` in the hashed
  daily input profile. The ordinary daily run then binds the single contiguous
  Git range `cursor -> successor release`, which is exactly that ordered union
  when both ancestry proofs hold. This preserves the existing one-range
  immutable run and cursor-CAS schema while making the master bridge
  inspectable. Reconciliation may advance only after normal receipt-led
  delivery of that run.
- Preserve the stable routine keys (`uaudit-daily-android` and
  `uaudit-daily-ios`) and their existing cursor paths and lock ownership.
  `branch` in routine configuration is the baseline release line, not a new
  daily-execution identity.
- A missing configured release with no proven successor yields the resolver's
  bounded recovery result and blocks/reports with Git evidence. It does not
  silently mark success.

### 2. Unbounded daily intake

- Remove `max_commits`, `max_files`, and `max_diff_lines` from
  `daily-version-branch-routines.yaml` and stop requiring them in
  `load_config`.
- Remove only the dispatcher decision that blocks a daily audit due to those
  three range sizes. The dispatcher must still bind exact SHAs, enumerate and
  record the actual range, and preserve all normal staged-review checks.
- Update routine-config validation, renderer/bundle assertions, and generated
  Codex bundles to assert the absence of these caps rather than a fixed
  30/300/3000 policy.

### 3. Safe live recovery after deployment

- Reconcile the two live routines on iMac from the merged deployment, then
  resolve Android's pending source selection through its proven `0.51`
  transition rather than a manual cursor edit.
- For iOS `UNS-538`, obtain the exact delivered summary digest and provide the
  required digest-bound partial-approval comment through the Paperclip API;
  then resume the existing receipt-led reconciliation. Do not send another
  Telegram delivery.
- For iOS `UNS-541`, request a bounded resume of the blocked crypto stage so
  it regenerates its malformed digest-bound artifact under the normal run
  contract. Do not hand-edit immutable run artifacts or release its lock by
  editing state.
- Use the normal reconciliation helper for all cursor/lock mutation. Do not
  write cursor JSON, remove locks, or mark workflows successful manually.

## Non-scope

- This does not make forced full-range audits mutate daily cursors or schedule
  state; that workflow stays distinct.
- This does not automatically skip a release series, select a non-version
  branch, infer ancestry from local stale refs, or change audit scope based on
  commit/file/diff size.
- This does not remove audit evidence, human partial-approval, delivery
  receipts, locks, immutable run bindings, or cursor CAS safeguards.
- It does not repair unrelated historical findings or change the upstream
  Unstoppable Wallet repositories.

## Affected areas

- `paperclips/projects/uaudit/runtime/uaudit_release_resolver.py`
- `paperclips/tests/test_uaudit_release_resolver.py`
- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/tests/test_phase_c_bootstrap_project.py`
- `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`
- `paperclips/projects/uaudit/daily-version-branch-routines.yaml`
- `paperclips/scripts/reconcile_uaudit_routines.py`
- `paperclips/scripts/validate_uaudit_docs.py`
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`
- regenerated `paperclips/dist/uaudit/codex/UWACTO.md`,
  `paperclips/dist/uaudit/codex/UWICTO.md`, and any assembly artifacts changed
  by the standard UAudit builder.

## Design delta matrix

| Slice | Existing verified analog | Delta | Preserved contract | Verification |
| --- | --- | --- | --- | --- |
| Successor selection | `resolve_release_history` returns a strict-next `transition` with ordered master/release segments | Deploy its verified CLI beside the helper; dispatchers provide direct-Git proof and use its JSON result instead of static `version/0.50` fetch-only logic | Resolver does not write; profile records two proven segments, while the existing one-range run binds their contiguous union; ambiguity is recovery, not no-op | Resolver and installer unit cases: 0.50→0.51, skipped 0.52 rejection, absent successor bridge, bad SHA/ref rejection; bundle assertions |
| Unbounded intake | Routine config/reconciler validates three positive integer caps | Omit caps and accept their absence; daily dispatchers no longer reject large deltas | Exact SHAs, immutable run context, staged chain, delivery receipt, partial approval, lock and cursor CAS | Config/reconciler tests; source/bundle checks that caps and size-block language are absent |
| Live recovery | Infra overlay and delivery helper reconcile daily runs only from receipt/approval evidence | Resume the existing blocked executions through their supported controls after deployment | No manual cursor/lock edits and no duplicate Telegram | Helper delivery-contract tests plus iMac API status, run markers, and routine health checks |

## Acceptance criteria

1. A daily dispatcher cannot contain a hard-coded `daily-*-version-0.50`
   execution identity, a static direct fetch limited to `version/0.50`, or a
   size-limit blocking rule.
2. Given cursor `C`, master `M`, and Android `version/0.51` `R`, with
   `C <= M <= R`, it records ordered proofs `C..M` and `M..R`, binds the
   contiguous `C..R` audit range, and targets `R`; it does not advance the
   cursor before all normal completion artifacts are present.
3. A candidate `version/0.52` for configured `version/0.50` is rejected; a
   missing or unprovable next branch cannot be interpreted as no changes.
4. Routine configuration loads without range caps, yet keeps stable routine
   keys, platform-specific baselines, paths, schedules, and agent chains.
5. The rendered UAudit Codex bundles match their sources, remain within their
   existing size limits, and contain the dynamic resolver procedure.
6. Existing delivery/partial-approval/cursor-CAS tests stay green.
7. On iMac, the deployed Android routine no longer waits for a branch-choice
   interaction when a proven `version/0.51` exists, and iOS is not blocked by
   the former 3,000-line intake cap. Existing executions are recovered only via
   documented Paperclip/helper flows.

## Verification plan

1. Run resolver and runtime-installer unit tests and add boundary cases for
   strict successor, master bridge, malformed proof, and skipped release
   rejection.
2. Run targeted routine/config/dispatcher-bundle/doc-validator tests.
3. Regenerate UAudit Codex compatibility output with
   `python3 paperclips/scripts/build_project_compat.py --project uaudit --target codex --inventory check --validate-strict`, then rerun generated-bundle tests.
4. Run the delivery-contract partial-approval/reconcile subset and the full
   relevant `paperclips/tests` UAudit suite when runtime permits.
5. After merge and iMac deployment, dry-run then apply routine reconciliation;
   inspect exact live routine definitions and execution status through the
   Paperclip API. Verify cursor and lock state only through the helper's
   terminal markers.

## Open questions

- None for implementation. The live recovery sequence is intentionally
  deferred until the reviewed source change is merged and deployed, so the
  running routines receive the same verified policy as the tests.
