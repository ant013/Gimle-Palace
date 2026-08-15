# UAudit: authoritative Android ref and iOS partial-recovery readiness

## Grounding

This specification is grounded in `origin/develop` at
`4aa305fab6c7241cb2da1bedca26d29cdb533813` (2026-08-06).

On 2026-08-05 the Android daily issue compared its cursor and local branch at
`91ab6f60c74507b98cc5ee17787ae5ec10f13306`, while the authoritative upstream
`version/0.50` had advanced.  The current role source does not require a fetch
from the routine's declared `repo_url`; it can therefore accept a stale local
mirror as the branch head.  The iOS issue `UNS-535` already has a valid delivery
receipt but remains partial because deployment did not provision
`state/partial-approvers.json`.  Receipt-led reconciliation deliberately
requires a digest-bound comment by a verified human in that allowlist.

## Goal and success criteria

Make daily UAudit resolve `version/0.50` from the authoritative configured
upstream on both platforms, and make the iOS partial-recovery procedure
operationally complete without weakening receipt or human-approval safeguards.

Success means:

1. Android and iOS daily dispatchers fetch only their routine's declared
   `repo_url` and resolve `TO` from that fetch before cursor/no-op/delta checks.
2. A stale checkout ref cannot produce a `No new commits` result when the
   declared upstream has new commits.
3. The existing staged v1 chain, daily limits, locks, cursor CAS, Russian
   rendering, and receipt-led delivery remain unchanged.
4. A delivered partial iOS run can resume reconciliation without a second
   Telegram send, but only after an allowlisted human posts the exact
   digest-bound approval.
5. Deployment fails early with an explicit diagnosis when no valid iOS
   partial-approver configuration is present; it must never silently create an
   empty list or auto-approve a partial report.

## Scope

In scope:

- `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`
- the UAudit deployment/bootstrap path that validates and installs the
  host-local partial-approver configuration;
- generated UAudit Codex bundles and their source/renderer checks;
- targeted dispatcher, delivery-contract, and deployment tests;
- after deployment, operational recovery: refresh the Android mirror and
  launch a receipt-led forced-full Android audit from
  `e80ac5bbe5922be83840b6b26d7a515456947113` to the verified fetched
  `version/0.50` tip; resume `UNS-535` only after valid human approval.

Out of scope:

- changing the 30/300/3000 daily limits or daily cursor semantics;
- advancing either cursor manually;
- treating an agent/service comment as a human approval;
- resending the existing iOS Telegram report;
- changing report language/format or Telegram routing.

## Assumptions and open question

- The configured `repo_url` remains the canonical GitHub repository for each
  routine and is reachable from the audit host.
- The requested Android SHA is an ancestor of the fetched Android tip; otherwise
  the forced audit must block before issue creation.
- **Open operational input:** the verified Paperclip actor id(s) of the human
  allowed to accept partial audits must be supplied in the host-local allowlist.
  This is not inferred from an agent token or this source repository.  The
  recovery of `UNS-535` additionally requires the exact Board comment
  `partial audit approved <current-summary-sha256>` by one of those humans.

## Analog family and delta matrix

| Slice | Primary analog and supporting evidence | Preserved invariant | Required delta | Rejected alternative | Failure guard / verification |
| --- | --- | --- | --- | --- | --- |
| Android authoritative ref | Current Android dispatcher; routine config provides `repo_url`/branch; dispatcher tests; legacy fixture is counterexample | Cursor is the only daily FROM; staged v1 delivery owns cursor mutation | Fetch declared upstream ref and bind TO to fetched result before any equality/range decision | Restore legacy monolithic Infra flow or trust `origin/version/0.50` | Test source and rendered bundle require direct configured fetch; exercise a stale local ref versus newer fetched ref |
| iOS partial recovery | Current iOS Infra overlay; `reconcile-daily`; partial-approval tests | Matching receipt forbids a resend; partial needs exact human digest approval and cursor CAS | Validate/install non-empty host-local allowlist and document receipt-led resume | Auto-create an empty/default allowlist, bypass approval, or write cursor directly | Deployment validation rejects absent/invalid config; contract test proves no approval/no cursor mutation and matching receipt resume sends nothing |

The legacy v0.49 fixture demonstrates direct fetch but is rejected as a primary
because it combines that operation with obsolete monolithic routing, cursor
initialization, and delivery behavior.

## Design

1. Add a concise daily-intake step in both platform dispatcher role sources:
   use the routine's declared repository URL and branch to fetch a dedicated
   audit tracking ref, then resolve `TO` from that fetched commit.  Perform the
   ancestor, limit, and no-op checks only against that `TO`; retain the existing
   lock/bind-context/handoff workflow.
2. Add a deployment configuration validator for the JSON shape already enforced
   by `reconcile-daily`: schema version `1` and a sorted, non-empty set of
   approved human actor IDs.  The host-local file remains outside Git and is
   installed/validated explicitly; no user identity or credential is copied to
   the repository.
3. Extend tests to cover both role sources and generated bundles, direct-fetch
   behavior, invalid/missing partial-approver configuration, and idempotent
   receipt-led reconciliation.
4. Regenerate committed UAudit Codex bundles from role sources rather than
   editing generated files by hand.
5. Deploy only the reviewed bundle.  Refresh the Android checkout from the
   official URL, verify the requested SHA relationship, create the forced-full
   issue with unbounded confirmation, and verify its receipt/Telegram result.
   For iOS, configure only verified human actors, collect the exact approval,
   then resume `UNS-535`; verify cursor/workflow markers and absence of a new
   Telegram send.

## Affected areas

- UAudit dispatcher prompt sources and rendered Codex bundles.
- UAudit bootstrap/deploy validation for host-local partial approvers.
- UAudit dispatcher and delivery-contract test suites.
- iMac host-local Android mirror, Paperclip issue state, and iOS allowlist only
  during the explicitly verified operational recovery.

## Test plan and verification

Before code, add/adjust tests that fail if:

- either daily dispatcher lacks the direct configured fetch and fetched-TO
  requirement;
- generated `UWACTO`/`UWICTO` bundles omit that requirement;
- a partial approver file is absent, empty, unsorted, invalid, or not host-local;
- a matching receipt causes a second send or a cursor mutation without valid
  human approval.

After implementation:

```bash
python3 -m pytest paperclips/tests/test_uaudit_dispatcher_bundles.py
python3 -m pytest paperclips/tests/test_uaudit_delivery_contract.py
python3 paperclips/scripts/build_project_compat.py --project uaudit --target codex --inventory check
python3 paperclips/scripts/validate_uaudit_docs.py
```

Then deploy from the merged commit using the documented UAudit deployment path,
verify the fetched Android ref equals the public upstream tip, inspect the
forced-full issue's receipt, and perform iOS receipt-led reconciliation only
with the verified human approval artifact.

## Adversarial review

- **Stale-source risk:** a configured local checkout can be stale even though
  its ref name is `origin/version/0.50`.  Resolving TO exclusively from a direct
  fetch closes this gap.
- **Security risk:** auto-approving a partial audit would suppress real findings.
  The design provisions the allowlist but preserves the human/digest gate.
- **Duplicate-delivery risk:** only reconciliation after a matching receipt is
  permitted for `UNS-535`; Telegram send is not retried.
- **Scope risk:** forced full range is used only for the explicitly requested
  Android replay and does not mutate the daily cursor or alter the daily limits.

All challenges are accepted with the stated guards; no source change is
authorized until this exact specification revision is approved.
