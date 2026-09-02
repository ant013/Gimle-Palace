# UAudit iOS Non-Blocking Runtime Limitations

Status: design for review

Grounded in: `origin/develop` at `59c8eb1f8e4e96c3ed0854c5db73f9bf6c58af0f`

Branch: `fix/uaudit-ios-nonblocking-runtime-limitations`

## Goal

Keep daily UAudit delivery continuous on the old iMac. A known unavailable
runtime capability that does not prevent static audit conclusions must be a
non-material warning, not a reason to retain the daily lock. Complete and
partial audits that reached a valid receipt must reconcile the cursor without a
second human-approval dependency; only genuinely blocked or invalid audit state
must stop the workflow.

Observable success means:

1. iOS QA reports the old-iMac Xcode/device/runtime gap with `material:false`,
   keeps `audit_status=complete`, and uses
   `needs_runtime_verification:true` on affected findings.
2. A delivered daily result, including a genuine `partial`, follows the
   receipt-bound cursor compare-and-set and releases its retained lock without
   `partial-approvers.json` or an approval comment.
3. The retained iOS generation is reconciled without a duplicate Telegram
   send, the next non-overlapping range is delivered, and the following daily
   intake can start from the updated cursor without operator intervention.

## Reproduced Failure

- Live `UNS-590` produced a valid bilingual Telegram receipt, but iOS QA marked
  the permanent lack of full Xcode/device execution as a material limitation
  and selected `partial`.
- The live delivery role then required a human approval before cursor
  reconciliation, leaving the cursor at
  `ec6da4583e2128108413b5a50c55f5874bc4b433` and retaining
  `daily-ios-version-0.50.lock`.
- Later scheduled iOS intake, including `UNS-603`, could prove a valid range but
  could not create a run because the retained lock remained owned by `UNS-590`.
- On the clean repository base, the focused contract test reproduces a second
  inconsistency: `reconcile_daily` autonomously returns `status=applied` for a
  partial audit while the stale test and Infra instructions expect rejection
  until human approval.

## Assumptions

- The old iMac intentionally has Command Line Tools only. Full Xcode,
  simulator/device execution, and equivalent runtime smoke infrastructure will
  remain unavailable.
- Static review, dependency analysis, security analysis, repository evidence,
  and available command-line checks are sufficient to complete the audit when
  the unavailable runtime checks would only confirm already reported findings.
- `blocked` remains a fail-closed state for malformed/missing bound artifacts,
  invalid contracts, unproven ranges, receipt conflicts, lock conflicts, or
  cursor compare-and-set conflicts.
- `partial` remains a valid delivered audit status, but it is not a retained-lock
  state. The current helper implementation already follows this policy.
- The live recovery must use existing receipt, lock metadata, and cursor CAS;
  it must not delete or steal the lock manually.

## Scope

### In scope

- Make the iOS daily QA role explicitly classify known old-iMac runtime/device
  unavailability as non-material and `complete` when static audit conclusions
  are valid.
- Reserve `partial` for a material gap in the audit conclusion and `blocked`
  for a workflow/contract condition that truly prevents valid continuation.
- Align both iOS and Android Infra delivery instructions with the already
  deployed cross-platform helper contract: a receipt-bound `partial` reconciles
  without approval files or approval comments.
- Update regression tests to reflect autonomous partial reconciliation and to
  cover the exact non-material iOS QA case through delivery and cursor update.
- Regenerate committed UAudit Codex bundles from source.
- Deploy the approved UAudit bundles/helper through the documented path and
  perform receipt-led recovery of the retained iOS generation.

### Out of scope

- Installing or upgrading Xcode, simulators, devices, adb, emulators, or
  fault-injection infrastructure.
- Changing Unstoppable Wallet iOS application source.
- Weakening receipt validation, run binding, lock ownership, cursor CAS,
  Telegram-route validation, or malformed/blocked-stage checks.
- Treating a missing mandatory audit artifact or an unproven Git range as a
  warning.
- Editing or cleaning any Thorchain files or worktrees.
- Resending an already receipt-confirmed Telegram document.

## Affected Areas

- `paperclips/projects/uaudit/overlays/codex/UWIQAEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`
- `paperclips/tests/test_uaudit_delivery_contract.py`
- Generated files under `paperclips/dist/uaudit/codex/`
- `paperclips/dist/uaudit.resolved-assembly.json` if regeneration changes it
- Live UAudit role/helper projection and the retained iOS run/cursor/lock state

The helper implementation in
`paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py` is not expected
to change: its current receipt/lock/CAS behavior is the implementation spine.

## Design

### 1. iOS QA limitation classification

Add a concise mandatory rule to `UWIQAEngineer`:

- do not attempt full-Xcode compilation, simulator/device execution, RPC smoke,
  or equivalent unavailable runtime checks on this host;
- when static audit evidence remains sufficient, record the missing check as a
  warning/non-material limitation (`material:false`) and keep
  `audit_status=complete`;
- preserve `needs_runtime_verification:true` on findings whose final runtime
  confirmation is unavailable;
- select `partial` only when missing evidence materially prevents a defensible
  audit conclusion;
- never select `blocked` merely because the known host lacks those tools.

This copies the classification invariant from the same-stage Android QA analog
and the hardware vocabulary from the same-platform Swift auditor. Android-only
tool names and domain examples are not copied.

### 2. Autonomous delivered-partial reconciliation

Update both Infra overlays so daily delivery matches the current helper:

- after a matching receipt, run `reconcile-daily` for `complete` or `partial`
  without `--approval-comments` or `--approvers`;
- do not fetch approval comments and do not require
  `partial-approvers.json`;
- retain every existing prerequisite: exact summary, receipt, Telegram marker,
  run binding, owned lock metadata, cursor path, cursor CAS, terminal marker
  consistency, Board comment, final issue state, and lock release only after
  `status/cursor.done` and `status/workflow.done`;
- `blocked` stages still stop before aggregation/delivery.

No new bypass is added to the helper. The change removes stale callers and
tests that contradict the helper's existing behavior.

### 3. Regression coverage

Add or update tests before changing role sources:

1. Source/render contract: both the source overlay and generated
   `UWIQAEngineer` bundle contain the non-material/complete old-iMac rule and
   runtime-verification marker.
2. Stage-to-delivery contract: an iOS QA sidecar with a non-material runtime
   limitation validates, aggregates as `complete`, records delivery, advances
   the daily cursor through the receipt-bound CAS, and resumes idempotently.
3. Partial contract: a material `partial` still renders/delivers as partial,
   but reconciles without approval files and remains idempotent.
4. Infra bundles: source and generated iOS/Android Infra instructions contain
   autonomous partial reconciliation and do not contain approval-file/comment
   dependencies.
5. Existing malformed, blocked, receipt-conflict, lock-conflict, and cursor-CAS
   rejection tests remain unchanged and passing.

### 4. Deployment and live recovery

After implementation verification and merge/release through the repository's
normal path:

1. Deploy the generated UAudit Codex roles/helper using the documented iMac
   agent deployment path.
2. Read back live `UWIQAEngineer`, `UWIInfraEngineer`, and installed helper
   content/digests; require the approved policy and helper version to match.
3. Revalidate the retained generation's run binding, delivery summary,
   bilingual receipt, Telegram marker, lock metadata, and current cursor.
4. If they still match the reproduced `UNS-590` generation, invoke the helper's
   receipt-led `reconcile-daily` without resending Telegram. Require cursor CAS
   from the generation's exact FROM to exact TO and creation of
   `status/cursor.done`.
5. Complete/verify the Board comment and terminal issue state, write
   `status/workflow.done`, then release only the matching retained lock.
6. Re-resolve pending daily intake from the updated cursor. Permit exactly one
   non-overlapping current generation; older overlapping scheduled issues are
   marked superseded/no-run without cursor mutation so they cannot deliver
   duplicates.
7. Run the current generation through Telegram delivery, cursor reconciliation,
   workflow completion, and lock release. Confirm the next resolver invocation
   is `no_change` or selects only commits after the new cursor.

Any receipt, binding, cursor, or lock mismatch stops recovery. Manual lock
deletion, cursor editing, and duplicate Telegram delivery are forbidden.

## Analog Delta Matrix

### Slice S-001 — iOS QA non-material limitation classification

| Field | Decision |
|---|---|
| Analog family | Primary: Android `UWAQAEngineer` same-stage classification. Supporting: iOS `UWISwiftAuditor` old-iMac policy, UAudit manifest composition, delivery sidecar consumer, bundle test seam. Rejected counterexample: current ambiguous `UWIQAEngineer`. |
| Coverage | Responsibility/boundary/state error: QA and Swift overlays. Composition/dependencies: UAudit manifest and helper. Consumer/lifecycle: sidecar validation/canonicalization. Tests: generated bundle test. No role waiver. |
| Invariants to preserve | Strict v1 sidecar, Russian limitation prose, `complete` cannot carry material limitations, `partial` requires material limitations, QA never sends Telegram or mutates cursor. |
| Required differences | Use iOS host capabilities and explicitly bind non-impact runtime gaps to `material:false`, `complete`, and finding-level runtime verification. |
| Rejected differences | Do not copy Android adb/emulator examples; do not remove `partial`/`blocked`; do not infer that all unavailable evidence is non-material. |
| Failure modes | Ambiguous wording recreates `material:true`; overly broad wording hides a material gap; generated bundle omits the source policy. |
| Tests before code | Add failing source/render assertions and a failing non-material iOS QA delivery/CAS fixture. |
| Verification | Build UAudit Codex bundles; run focused dispatcher and delivery-contract tests; inspect source and rendered policy markers. |

### Slice S-002 — daily delivery and cursor continuity

| Field | Decision |
|---|---|
| Analog family | Primary: current `reconcile_daily` receipt/lock/CAS implementation. Supporting: bootstrap no-approver composition and complete delivery/receipt test. Rejected counterexamples: stale Infra approval requirement and failing approval-era test. |
| Coverage | Contract/implementation/consumer/lifecycle/trust: helper. Composition: bootstrap. Tests: delivery/CAS tests. Counterexamples: both stale caller and stale test. No role waiver. |
| Invariants to preserve | No cursor mutation before matching receipt; exact lock metadata; atomic CAS; idempotent matching TO; blocked/malformed/conflicting state fails closed; lock released only after terminal markers. |
| Required differences | Remove approval file/comment dependency from both Infra roles and update tests to the existing autonomous partial helper behavior. |
| Rejected differences | No manual cursor write, manual lock theft, receipt bypass, duplicate Telegram send, or auto-conversion of a truly blocked stage. |
| Failure modes | Cursor advances for wrong generation; lock releases before workflow completion; stale test masks prompt/helper drift; duplicate scheduled issue sends overlapping range. |
| Tests before code | Keep the reproduced approval-era test failure, then rewrite it to assert autonomous apply/idempotence; add non-material complete delivery/CAS coverage. |
| Verification | Focused pytest, full two affected UAudit suites, bundle build/validation, live receipt-led reconciliation and next-intake smoke. |

## Acceptance Criteria

- Source and rendered `UWIQAEngineer` explicitly classify known old-iMac
  runtime gaps as non-material warnings and require `complete` when the audit
  conclusion is valid.
- A finding may retain `needs_runtime_verification:true` without changing the
  stage or aggregate status to `partial`.
- Source and rendered iOS/Android Infra roles no longer require a partial
  approval file or comment.
- A receipt-confirmed `partial` advances the cursor through the same lock/CAS
  checks as `complete`, and a repeated reconciliation is idempotent.
- `blocked`, malformed, receipt-conflicting, lock-conflicting, and cursor-
  conflicting runs still cannot mutate cursor or release the lock.
- Generated UAudit bundles are produced from source and validation passes.
- The retained iOS lock is released only after the existing generation is
  receipt-reconciled; no existing Telegram receipt is resent.
- A new iOS audit covering the remaining range is delivered and reconciled, and
  a subsequent daily intake is not blocked by a retained prior-delivery lock.
- No Thorchain or Unstoppable Wallet application files are changed.

## Verification Plan

Run in this order:

```bash
cd paperclips
uv run pytest tests/test_uaudit_delivery_contract.py -q \
  -k 'non_material or partial or cursor_cas or complete_zero'
uv run pytest tests/test_uaudit_dispatcher_bundles.py -q \
  -k 'qa or infra or partial or bootstrap'
python3 scripts/build_project_compat.py \
  --project uaudit --target codex --inventory skip
uv run pytest tests/test_uaudit_delivery_contract.py \
  tests/test_uaudit_dispatcher_bundles.py -q
python3 scripts/validate_instructions.py --repo-root ..
python3 scripts/validate_uaudit_docs.py
```

Then inspect the task-only diff and confirm generated output contains no
unresolved variables or unrelated bundle churn. After merge/deploy, verify on
the iMac:

- live QA/Infra policy markers and installed helper digest;
- retained-run receipt, Telegram marker, cursor and lock binding;
- helper reconciliation result and cursor marker;
- workflow marker and exact lock removal;
- one subsequent delivered non-overlapping daily range;
- next resolver outcome from the updated cursor.

The old iMac's unavailable Xcode/device checks are intentionally not run; the
point of this change is to classify that permanent environment fact correctly.

## Rollback

- Repository rollback reverts the role/test/generated-bundle commit and
  redeploys the preceding released bundles.
- Live cursor reconciliation is not rolled back by rewriting the cursor. If a
  post-deploy role problem appears after a valid receipt-bound CAS, fix and
  audit only the subsequent range.
- If live recovery has not yet reconciled the retained generation, leave its
  lock and cursor untouched and stop.

## Open Questions

- No design-blocking question remains. At recovery time, the newest pending
  issue identifier may be later than `UNS-603`; resolve live state and select
  one non-overlapping generation rather than hard-coding an issue number.
