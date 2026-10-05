# UAudit Daily Intake Freshness and No-Change Handoff

**Date:** 2026-10-05

**Status:** Proposed

**Incident:** UNS-688, with related failures in UNS-684 and UNS-686

**Scope:** UAudit daily Android and iOS version-branch routines in Gimle Palace

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

UNS-684, UNS-686, and UNS-688 also exposed a second contract gap: the dispatcher assigned delivery after a `no_change` decision without first creating the manifest-bound descriptor and scheduled-slot proof required by the delivery contract. Delivery correctly failed closed, but left the issue assigned to delivery while requesting platform recovery. The recovery agent then could not check out the issue because ownership had not been transferred, producing a 409 loop.

All recorded agent runs completed technically successfully. The failure is therefore a missing deterministic runtime contract, not an API/model crash. The current critical fetch and handoff requirements exist primarily as prompt prose and are not machine-enforced.

## Assumptions

1. `daily-version-branch-routines.yaml` remains the authority for routine identity, platform, repository URL, current release branch, and strict-next branch policy.
2. The release branch is an exact branch name such as `version/0.52`; branch discovery must not silently replace the configured current branch.
3. A missing strict-next branch is a valid, explicitly recorded state. It is not an error and must not invent `version/0.53`.
4. The audit cursor remains receipt-led. This work must not advance it directly.
5. Paperclip issue origin data provides a stable routine execution identity through `originKind`, `originId`, `originRunId`, and an authenticated creation/scheduled timestamp.
6. Android and iOS must share one intake contract even though UNS-688 occurred on Android.
7. Existing resolver and delivery manifests/digests remain authoritative and will be extended or composed rather than bypassed.

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

1. load and validate the selected routine from `daily-version-branch-routines.yaml`;
2. require the exact configured `repo_url` and exact configured release branch;
3. query `git ls-remote --heads <repo_url>` for the current branch and strict-next branch;
4. fetch explicit refspecs into dedicated tracking refs, for example:
   `+refs/heads/<branch>:refs/remotes/uaudit-upstream/<branch>`;
5. fetch the default/base ref required by the resolver using an equally explicit refspec;
6. fetch strict-next only when `ls-remote` proves it exists;
7. re-read the fetched ref and require exact equality with the authoritative `ls-remote` SHA;
8. retry the query/fetch/verify sequence once if the remote moves during acquisition, then fail closed with structured evidence;
9. reject missing, stale, mismatched, or unverifiable current-branch evidence;
10. invoke the existing release resolver with the verified SHAs and cursor;
11. persist the canonical input, output, and provenance before returning a decision.

No resolver decision may be emitted if authoritative current-branch verification did not succeed.

### 2. Persist a canonical issue-scoped intake bundle

Each issue gets a dedicated bundle under the installed UAudit tool state, for example:

`/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/intake-UNS-<number>/`

The exact installed path may follow the existing runtime layout, but must be deterministic and issue-scoped. The bundle contains at least:

- `git-evidence.json` — repository URL, exact refs, `ls-remote` SHAs, fetched SHAs, timestamps, command/result metadata, and strict-next presence;
- `resolver-input.json` — cursor, verified current head, verified base/default head, optional verified strict-next head, routine identity, and evidence digest;
- `resolver-output.json` — resolver decision and its manifest/digest provenance;
- `daily-status-descriptor.json` — required only for `no_change`;
- `daily-status-slot-proof.json` — required only for `no_change`;
- `daily-status-handoff.json` — validated paths and digests supplied to delivery.

Artifacts must be written atomically. A partial bundle is invalid and must not authorize delivery assignment.

### 3. Bind scheduled-slot proof to Paperclip origin data

The slot proof must identify the actual routine execution, not merely the routine name.

It must validate and record:

- `originKind == routine_execution`;
- the expected routine `originId`;
- the concrete `originRunId`;
- the authenticated UTC scheduled/creation timestamp;
- issue identifier and routine manifest digest.

Values such as `daily-android-version-0.52` are routine identities, not timestamps, and are invalid as scheduled-slot proof.

The preferred interface is for the dispatcher to capture the Paperclip issue/origin envelope and pass its path or explicit fields to the helper. The persisted evidence must exclude credentials and unrelated issue data.

### 4. Make `no_change` a complete producer transaction

When the resolver returns `no_change`, the intake helper must prepare and validate all inputs required by `uaudit_delivery_contract.py prepare-daily-status` before the dispatcher transfers ownership.

The sequence is:

1. authoritative refs verified;
2. resolver output persisted;
3. descriptor generated and bound to the active manifests;
4. scheduled-slot proof generated from validated origin data;
5. descriptor/proof compatibility validated with the installed delivery contract;
6. handoff artifact written atomically;
7. only then assign the issue to the platform delivery operator with the explicit handoff path.

The delivery agent consumes the handoff artifact instead of reconstructing producer evidence from comments or workspace state.

### 5. Define deterministic missing-input recovery

Delivery remains fail-closed for missing, corrupt, digest-mismatched, or slot-mismatched inputs. On failure it must not keep ownership while merely mentioning the platform CTO.

The recovery transition must atomically:

1. attach the structured validation failure and evidence paths;
2. assign the issue back to the correct platform CTO;
3. select an explicit daily-intake recovery mode;
4. preserve the original routine/run identity and prohibit cursor mutation;
5. allow the CTO to check out the issue without a 409 ownership conflict.

Repeated recovery for the same issue, run, and artifact digest must be idempotent.

### 6. Preserve platform parity

The Android and iOS dispatchers and delivery operators must use the same installed helper and the same schema. Platform-specific values must come from the routine manifest, not duplicated prompt logic.

Generated files under `paperclips/dist/uaudit/codex/` must be produced through the existing bundle generation process and must not be hand-edited.

### 7. Install the helper as one compatible runtime bundle

Bootstrap/install logic must deploy the intake helper alongside immutable manifests needed by the resolver and delivery contract. Startup compatibility checks must reject mixed helper/manifest versions.

A deployment must install compatible runtime files and rendered agent bundles together so an updated dispatcher cannot call an older helper contract, and an updated delivery operator cannot receive an older handoff schema.

## Affected Files and Areas

Expected areas; exact filenames may be adjusted after implementation-oriented symbol inspection:

- `paperclips/projects/uaudit/runtime/uaudit_daily_intake.py` — new deterministic intake coordinator;
- `paperclips/projects/uaudit/runtime/uaudit_release_resolver.py` — only if a narrow evidence precondition or schema extension is required;
- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py` — slot/origin validation and handoff consumption;
- `paperclips/projects/uaudit/daily-version-branch-routines.yaml` — schema/version metadata only if required;
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
3. Current-branch `ls-remote`, explicit fetch, and fetched-ref verification must agree; otherwise the run fails closed with evidence.
4. The helper never uses an implicit branch, `FETCH_HEAD`, a local mirror, or another repository remote as authoritative fallback.
5. A missing strict-next branch is recorded as absent and does not block the current release audit.
6. A `no_change` result always has a manifest-bound descriptor, valid scheduled-slot proof, and validated handoff before delivery ownership changes.
7. The scheduled slot is bound to `originId`, `originRunId`, and a real UTC timestamp; a routine-name placeholder is rejected.
8. Delivery can complete a valid `no_change` status in one normal handoff without a recovery cycle.
9. Missing or invalid delivery inputs transfer ownership to the correct platform CTO and do not produce a 409 checkout loop.
10. Android and iOS pass the same contract and parity tests.
11. The UNS-688 regression fixture resolves a delta from `fcb4266ff13743e728acc5722fb49cad9f5804d1` to an advanced authoritative head, never `no_change`.
12. Cursor advancement remains receipt-led and cannot occur during intake or failed recovery.
13. Generated bundles match their sources and runtime inventory/manifest validation passes.

## Verification Plan

### Unit and fixture tests

Use local bare Git repositories so tests do not depend on GitHub availability:

- seed a stale tracking ref, advance the bare remote, and prove intake selects the new remote head and delta;
- prove an absent strict-next branch is accepted and recorded;
- simulate the remote moving between `ls-remote` and fetched-ref verification, then prove one bounded retry and fail-closed behavior;
- prove local `origin`, mirrors, and `FETCH_HEAD` cannot influence the selected SHA;
- prove missing or mismatched current-branch evidence prevents resolver execution;
- prove canonical evidence files are atomic, complete, and digest-bound;
- prove origin metadata produces a valid scheduled-slot proof;
- reject a routine identifier used as a slot timestamp;
- reject descriptor/proof manifest or issue mismatches.

### Contract and orchestration tests

- assert dispatcher bundles require the structured intake helper result rather than prompt-only ref selection;
- assert `no_change` handoff paths exist and validate before delivery assignment;
- run Android and iOS parity cases from the same contract fixture;
- corrupt or remove a descriptor and prove ownership transfers to the platform CTO in recovery mode;
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

1. Should the helper receive a captured Paperclip issue/origin JSON envelope, or should it query Paperclip directly? Recommendation: pass a captured authenticated envelope or explicit validated fields so the helper does not need API credentials and the exact input is auditable.
2. If the remote changes during acquisition, is one retry sufficient? Recommendation: retry the complete query/fetch/verify sequence once, then fail closed; never resolve against mismatched observations.
3. For UNS-684 and UNS-686, should delayed `no_change` messages be sent or should those slots be marked superseded by the recovered delta audit? This is an operational/product decision and must not be inferred by the implementation.
4. Should the new intake helper wrap the existing resolver as a subprocess or expose a shared Python API? Recommendation: prefer the smallest change that preserves the resolver's installed immutable boundary and existing command contract.

## Approval Gate

No implementation changes should begin until this design is reviewed and approved. After approval, implementation will use a fresh code change on this branch, reproduce the stale-ref failure first, and keep every change traceable to the acceptance criteria above.
