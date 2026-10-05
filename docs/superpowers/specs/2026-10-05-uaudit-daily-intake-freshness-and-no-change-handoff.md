# UAudit Daily Intake Freshness and No-Change Handoff

**Date:** 2026-10-05

**Status:** Approved for implementation after two independent adversarial reviews

**Incident:** UNS-688, with related failures in UNS-684 and UNS-686

**Scope:** UAudit daily Android and iOS version-branch routines in Gimle Palace

**Grounded at:** `origin/develop` / `cebad4067b2c05903802febc2573a5b85da46ede`

## Goal

Make every daily UAudit run resolve release state from a freshly verified authoritative remote ref and make the `no_change` path produce a complete, validated delivery handoff before ownership moves to a delivery agent.

The fix must make the UNS-688 failure mode impossible: an old local tracking ref must never be accepted as proof that the remote release branch has not changed.

## Incident Summary

UNS-688 was created at `2026-10-05T10:45:00Z` for the Android `version/0.52` routine. UWACTO selected `no_change` at cursor/head `fcb4266ff13743e728acc5722fb49cad9f5804d1` and passed the issue to delivery.

That result was false:

- the authoritative `version/0.52` ref had already advanced before the routine ran;
- GitHub PushEvent evidence records advances beginning at `2026-10-05T06:59:42Z`;
- the current authoritative head observed during diagnosis was `cc5a6b362e200ac0d2d6c01cabb7a21507823a2e`;
- `fcb4266..cc5a6b3` contains eight commits;
- the iMac tracking ref had not been refreshed since `2026-10-02T16:46:13+06:00` and updated only during diagnosis at `2026-10-05T18:05:40+06:00`;
- no `version/0.53` branch exists on the authoritative remote.

UNS-684, UNS-686, and UNS-688 also exposed a second contract gap: the dispatcher assigned delivery after a `no_change` decision without first creating the manifest-bound descriptor and scheduled-slot proof required by the delivery contract. Delivery correctly failed closed, but left the issue assigned to delivery while requesting platform recovery. UNS-686 then produced a confirmed 409 when the recovery agent tried to check out an issue still owned by delivery; UNS-684 and UNS-688 remained blocked and assigned to delivery, but no equivalent checkout attempt is recorded for them.

All recorded agent runs completed technically successfully. The failure is therefore a missing deterministic runtime contract, not an API/model crash. The current critical fetch and handoff requirements exist primarily as prompt prose and are not machine-enforced.

## Assumptions

1. `daily-version-branch-routines.yaml` remains the source authority for routine identity, platform, repository URL, base branch, current release branch, and strict-next branch policy. Bootstrap installs a canonical, immutable JSON projection because the runtime must not depend on PyYAML or repository-relative files. The live Paperclip routine UUID is resolved into a separate host-local binding and included in that projection; UUIDs do not enter the repository-owned routine document.
2. The release branch is an exact branch name such as `version/0.52`; branch discovery must not silently replace the configured current branch.
3. A missing strict-next branch is a valid, explicitly recorded state. It is not an error and must not invent `version/0.53`.
4. The audit cursor remains receipt-led. This work must not advance it directly.
5. Paperclip issue and routine-run data provide a stable execution identity through `originKind`, `originId`, `originRunId`, `linkedIssueId`, run `source`, and run `triggeredAt`. `issue.createdAt` is not the scheduled slot.
6. Android and iOS must share one intake contract even though UNS-688 occurred on Android.
7. The delivery helper manifest remains authoritative. The current resolver installer bypasses its manifest path and must be fixed before the intake helper may depend on it.

## Scope

### In scope

- deterministic acquisition and validation of authoritative release refs;
- persisted, issue-scoped git and resolver evidence;
- a single structured dispatcher intake result;
- complete `no_change` descriptor and scheduled-slot proof generation before delivery assignment;
- deterministic recovery ownership transfer when required artifacts are missing or invalid;
- equivalent Android and iOS behavior;
- installation, bundle rendering, compatibility checks, and automated tests;
- operational recovery guidance for affected issues.

### Out of scope

- changing audit thresholds, stages, finding severity, or report content;
- changing agent models or reasoning effort;
- changing routine schedules;
- creating `version/0.53`;
- manually advancing or rewriting audit cursors;
- redesigning Telegram delivery;
- changing application source in Unstoppable Wallet Android or iOS repositories.

## Proposed Design

### 1. Add a deterministic daily-intake runtime helper

Add an installed helper, provisionally:

`paperclips/projects/uaudit/runtime/uaudit_daily_intake.py`

The helper owns the complete pre-dispatch intake sequence. Dispatchers must call it once and act only on its validated structured result. They must not infer `no_change` from an ad hoc local ref, `FETCH_HEAD`, a workspace mirror, or prompt reasoning.

The helper must:

1. load and validate the selected routine from the immutable installed JSON projection of `daily-version-branch-routines.yaml`;
2. require the exact configured HTTPS `repo_url`, `base_branch`, and release branch;
3. acquire the routine lock before reading the cursor or any Git state;
4. capture and validate sanitized issue and routine-run envelopes without Paperclip credentials;
5. query only the exact base/current/strict-next refs from the configured URL (`remote observation A`);
6. fetch present refs with explicit refspecs into run-scoped refs such as `refs/uaudit-intake/<originRunId>/{base,current,next}`; shared tracking refs, local remotes, mirrors, and `FETCH_HEAD` are forbidden authorities;
7. query the same exact remote refs again (`remote observation B`) and require `A == fetched == B` for every present ref and `A == B == proven_absent` for every absent ref;
8. retry the complete query/fetch/query sequence once on any mismatch, then fail closed with structured evidence;
9. read the cursor while the routine lock is still held and compute strictly typed ancestry facts from only the run-scoped refs;
10. invoke the existing pure release resolver with its unchanged exact JSON payload;
11. persist provenance outside `resolver-input.json`, because the resolver rejects unknown fields;
12. for a delta/recovery result, retain the routine lock through receipt-led reconciliation; for `no_change`, release it only after a prepared status handoff has been committed.

The lock owner records the issue, routine execution, output bundle, host, process, and timestamp. A retry of the same execution resumes an orphaned intake; a later execution may recover a dead pre-commit owner but may never steal a lock carrying audit metadata. A committed `no_change` result safely releases its own orphaned lock.

No resolver decision may be emitted from an unverified observation. A release ref proven absent in both remote observations is valid evidence and may enter the resolver's existing strict-next/bridge paths; absence must not be confused with a failed or incomplete query.

### 2. Persist a canonical issue-scoped intake bundle

Each routine execution gets a dedicated mutable bundle under shared run/state storage, not under the immutable `.uaudit-tools` executable area, for example:

`/Users/Shared/UnstoppableAudit/runs/UNS-<number>-intake/<originRunId>/`

The exact installed path may follow the existing runtime layout, but must be deterministic and issue-scoped. The bundle contains at least:

- `git-evidence.json` — repository URL, exact refs, `ls-remote` SHAs, fetched SHAs, timestamps, command/result metadata, and strict-next presence;
- `resolver-input.json` — only the existing exact resolver payload: cursor, verified current head or proven absence, verified base/default head, optional verified strict-next head, and strictly typed ancestry facts;
- `resolver-output.json` — resolver decision and its manifest/digest provenance;
- `daily-status-descriptor.json` — required only for `no_change`;
- `daily-status-slot-proof.json` — required only for `no_change`;
- `daily-status-handoff.json` — validated paths and digests supplied to delivery.

Immutable artifacts use create-or-match semantics with symlink/path-escape rejection. `intake-result.json` is written last as the completion/commit marker; a directory without that marker is incomplete and cannot authorize assignment.

### 3. Bind scheduled-slot proof to Paperclip origin data

The slot proof must identify the actual routine execution, not merely the routine name.

Status proof schema v2 must validate and record:

- `originKind == routine_execution`;
- issue `originId` equal to the captured routine id;
- issue `originRunId` equal to the captured routine-run id;
- routine run `linkedIssueId` equal to the captured issue id;
- routine run `source == schedule`;
- the authenticated UTC slot from routine run `triggeredAt`;
- issue id/identifier and the canonical installed per-routine configuration digest.

Values such as `daily-android-version-0.52` are routine identities, not timestamps, and are invalid as scheduled-slot proof.

The dispatcher captures minimal authenticated issue and routine-run envelopes and passes them as files. The helper does not query Paperclip and persisted evidence excludes credentials and unrelated issue data. Existing v1 status directories and receipts remain readable/resumable; all new producer artifacts use v2 proof binding.

### 4. Make `no_change` a complete producer transaction

When the resolver returns `no_change`, the intake helper must prepare and validate all inputs required by `uaudit_delivery_contract.py prepare-daily-status` before the dispatcher transfers ownership.

The sequence is:

1. authoritative refs verified;
2. resolver output persisted;
3. descriptor generated and bound to the active manifests;
4. scheduled-slot proof generated from validated origin data;
5. `prepare-daily-status` invoked before reassignment, producing the receipt-bound status run;
6. prepared `status-summary.json` and Telegram text deeply validated and digest-bound;
7. handoff artifact written with the prepared run directory and summary digest;
8. intake completion marker committed and routine lock released;
9. only then assign the issue to the platform delivery operator with the explicit handoff path.

`prepare-daily-status` builds a complete staging directory and atomically publishes it. An older incomplete final directory is quarantined and rebuilt; incomplete staging directories never become authoritative.

The delivery agent consumes the handoff artifact instead of reconstructing producer evidence from comments or workspace state.

### 5. Define deterministic missing-input recovery

Delivery remains fail-closed for missing, corrupt, digest-mismatched, or slot-mismatched inputs. On failure it must not keep ownership while merely mentioning the platform CTO.

Paperclip does not provide one transaction spanning a comment and assignment. The authoritative recovery operation is therefore one issue PATCH which:

1. assigns the issue back to the correct platform CTO;
2. sets `status=in_progress` and an explicit daily-intake recovery mode/context;
3. preserves the original routine/run identity and prohibits cursor mutation.

The evidence comment is best-effort and nonblocking after the ownership PATCH. If the PATCH fails, delivery remains retryable/pending and must not mark the issue blocked. This prevents the persistent comment-only ownership state that caused the confirmed UNS-686 checkout 409.

Repeated recovery for the same issue, run, and artifact digest must be idempotent.

### 6. Preserve platform parity

The Android and iOS dispatchers and delivery operators must use the same installed helper and the same schema. Platform-specific values must come from the routine manifest, not duplicated prompt logic.

Generated files under `paperclips/dist/uaudit/codex/` must be produced through the existing bundle generation process and must not be hand-edited.

### 7. Install the helper as one compatible runtime bundle

Bootstrap compiles a canonical JSON routine projection containing resolved repo/cursor paths, exact `repo_url`, `base_branch`, branch, routine, platform, app, and source-config digest. It deploys that projection with the intake helper and a manifest-verified resolver. The current resolver direct-copy/early-return path must be removed. Startup compatibility checks reject mixed helper/resolver/config/delivery generations.

Resolver and intake pending transactions are resumable after interruption. Re-running bootstrap may complete only the same target generation recorded by the pending marker; a marker for another generation fails closed.

A deployment must install compatible runtime files and rendered agent bundles together so an updated dispatcher cannot call an older helper contract, and an updated delivery operator cannot receive an older handoff schema.

## Affected Files and Areas

Expected areas; exact filenames may be adjusted after implementation-oriented symbol inspection:

- `paperclips/projects/uaudit/runtime/uaudit_daily_intake.py` — new deterministic intake coordinator;
- canonical installed runtime projection for daily routines;
- `paperclips/projects/uaudit/runtime/uaudit_release_resolver.py` — only if a narrow evidence precondition or schema extension is required;
- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py` — slot/origin validation and handoff consumption;
- `paperclips/projects/uaudit/daily-version-branch-routines.yaml` and `reconcile_uaudit_routines.py` — validated `repo_url` and `base_branch`;
- UAudit runtime/bootstrap installer and immutable manifest inventory;
- `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`;
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`;
- Android and iOS delivery overlays;
- generated `paperclips/dist/uaudit/codex/` bundles via the generator;
- `paperclips/tests/test_uaudit_delivery_contract.py`;
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`;
- new focused daily-intake tests if that keeps responsibilities clearer.

Implementation must avoid unrelated prompt cleanup or runtime refactoring.

## Acceptance Criteria

1. Every Android and iOS daily intake persists fresh authoritative remote evidence before the resolver runs.
2. A stale local tracking ref cannot produce `no_change` when the configured remote branch has advanced.
3. Exact remote observation A, explicit run-scoped fetch, fetched ref, and exact remote observation B must agree; otherwise the complete snapshot retries once and then fails closed with evidence.
4. The helper never uses an implicit branch, `FETCH_HEAD`, a local mirror, or another repository remote as authoritative fallback.
5. A missing strict-next branch is recorded as proven absent and does not block the current release audit; a current release branch proven absent remains eligible for existing strict-next/bridge resolution.
6. A `no_change` result always has a manifest-bound descriptor, valid scheduled-slot proof, and validated handoff before delivery ownership changes.
7. The scheduled slot is bound to issue/routine/run identities and routine run `triggeredAt`; `issue.createdAt` and routine-name placeholders are rejected as slot substitutes.
8. Delivery can complete a valid `no_change` status in one normal handoff without a recovery cycle.
9. Missing or invalid delivery inputs PATCH ownership/status back to the correct platform CTO before best-effort commentary and do not leave a persistent delivery-owned 409 loop.
10. Android and iOS pass the same contract and parity tests.
11. The UNS-688 regression fixture resolves a delta from `fcb4266ff13743e728acc5722fb49cad9f5804d1` to an advanced authoritative head, never `no_change`.
12. Cursor advancement remains receipt-led and cannot occur during intake or failed recovery.
13. Generated bundles match their sources and runtime inventory/manifest validation passes.
14. The resolver rejects strings/integers in boolean and boolean-or-null evidence fields.
15. New run-scoped Git refs and lock-before-cursor ordering prevent cross-run ref races and cursor TOCTOU.
16. Existing v1 daily-status receipts remain resumable after v2 deployment.

## Verification Plan

### Unit and fixture tests

Use local bare Git repositories so tests do not depend on GitHub availability:

- seed a stale tracking ref, advance the bare remote, and prove intake selects the new remote head and delta;
- prove an absent strict-next branch is accepted and recorded;
- simulate the remote moving between observations A/fetch/B, then prove one complete bounded retry and fail-closed behavior;
- prove local `origin`, mirrors, and `FETCH_HEAD` cannot influence the selected SHA;
- prove two concurrent executions use distinct run-scoped refs;
- prove a release branch proven absent is distinct from failed/unverified evidence;
- prove the routine lock precedes cursor snapshot and remains held for a delta;
- prove canonical evidence files are atomic, complete, and digest-bound;
- prove routine run `triggeredAt`, not issue `createdAt`, produces the scheduled-slot proof;
- reject mismatched issue/origin/run/linked-issue identities;
- reject a routine identifier used as a slot timestamp;
- reject descriptor/proof manifest or issue mismatches.
- reject non-boolean resolver ancestry fields;
- resume a legacy v1 status receipt after the v2 change.

### Contract and orchestration tests

- assert dispatcher bundles require the structured intake helper result rather than prompt-only ref selection;
- assert `no_change` handoff paths exist and validate before delivery assignment;
- run Android and iOS parity cases from the same contract fixture;
- corrupt or remove a prepared handoff and assert delivery PATCHes ownership plus `in_progress` back to the platform CTO before stopping;
- repeat the recovery transition and prove idempotency without a 409 loop;
- reproduce UNS-688 with cursor `fcb4266...` and an authoritative remote advanced by eight commits.

### Repository validation

- run the focused runtime and bundle test suites;
- run bundle generation and verify a clean generated diff;
- run runtime inventory/manifest compatibility validation;
- run YAML/schema validation for daily routines;
- run `git diff --check`;
- run the broader Paperclip/UAudit test suite when practical and report any environment-limited validation.

### Deployment verification

After review and deployment:

1. confirm installed helper and manifest digests are compatible;
2. execute a dry-run fixture for both platforms without cursor mutation or external delivery;
3. recover UNS-688 as a real delta audit from its unchanged cursor to the freshly verified authoritative head;
4. reconcile UNS-684 and UNS-686 as historical slots using their original evidence, without falsely folding them into UNS-688;
5. verify any cursor change is caused only by a valid delivered audit receipt;
6. observe the next scheduled Android and iOS routines and retain their intake bundles as rollout evidence.

## Rollout and Recovery Notes

- Deploy helper, immutable manifests, and rendered agent bundles as one compatible change.
- Do not edit the Android cursor to compensate for UNS-688.
- Do not classify UNS-688 as `no_change`; it has a real version-branch delta.
- Do not create `version/0.53`; its absence is valid evidence under the current manifest.
- Historical `no_change` slots may be delivered late or marked superseded only through an explicit operational decision with preserved evidence.
- Rollback must restore the previous compatible helper/bundle set together. A mixed-version rollback is invalid.

## Open Questions for Implementation Review

1. The helper receives captured minimal issue and routine-run JSON envelopes; it does not query Paperclip.
2. If the remote changes during acquisition, is one retry sufficient? Recommendation: retry the complete query/fetch/verify sequence once, then fail closed; never resolve against mismatched observations.
3. For UNS-684 and UNS-686, should delayed `no_change` messages be sent or should those slots be marked superseded by the recovered delta audit? This is an operational/product decision and must not be inferred by the implementation.
4. The intake helper invokes the installed resolver through its manifest-verified command contract; resolver provenance stays outside its unchanged JSON input.

## Approval Gate

The user approved implementation after two independent read-only reviews. Implementation will reproduce the stale-ref failure first and keep every change traceable to the revised acceptance criteria above.
