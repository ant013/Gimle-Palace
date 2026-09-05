# Glitcherry lock-free sequential handoffs

Date: 2026-09-05  
Status: PROPOSED  
Branch: `feature/glitcherry-lock-free-handoffs`  
Baseline: `32f7f317afb8692cd6f673aa1e7b5bc94746cc15` (`origin/develop`)

## Goal

Remove the persistent Glitcherry slice lease and every human-visible wait caused
by cross-agent execution ownership. Preserve the intended sequential workflow:
one issue, one execution workspace, one task worktree, committed checkpoints,
and one active phase owner at a time.

Every normal handoff must terminate the previous Paperclip run and immediately
wake the newly assigned role. No agent may stop for an expired/conflicting
controller lease, wait for a stale execution lock, or request Board recovery for
either condition.

## Assumptions and evidence

- Glitcherry roles work sequentially. Removing waits does not authorize two
  roles to edit the task worktree concurrently.
- Paperclip already implements the required primitive: issue reassignment with
  `interrupt: true` cancels the active run and wakes the new assignee with
  handoff context. Its server regression tests cover this behavior.
- The Glitcherry controller's persisted lease duplicates Paperclip ownership and
  caused the observed blocked/resume/adopt recovery loops. Exact branch, path,
  clean/dirty state, HEAD, phase, primary implementer, review count, merge, and
  cleanup records remain useful and are not locks.
- The controller's short `fcntl.flock` around one state-file read/write remains.
  It is not a workflow lease and cannot survive a command or cause a human wait;
  removing it would only permit partial/corrupt JSON writes.
- Existing schema-v1 controller records, including records with a legacy
  `lease`, must migrate without manually editing state or replacing the issue.
- The standing autonomous-correction policy and the three Code Review rejection
  ceiling remain in force.

## Design

### 1. Stateless controller ownership validation

The controller keeps `expected_owner`, `phase`, `head_sha`, branch/worktree IDs,
and audit history. It no longer grants, renews, expires, or requires a persistent
lease.

- `claim` remains as a compatibility/readiness command for deployed role
  instructions and old issue comments. It validates live expected owner, phase,
  branch/worktree, and exact HEAD, then returns success without writing a lease.
- `renew` becomes a compatibility no-op that validates owner/phase/HEAD and
  returns success. New instructions never call it.
- `handoff`, `reject`, `approve`, `block`, merge, and cleanup commands validate
  the controller's expected owner and repository facts directly. They do not
  require `run_id` ownership or an unexpired lease.
- A successful command removes any legacy `lease` field/value from the state.
  Reading a legacy lease never blocks a command.
- `recover` and checkpoint-adoption routes become unnecessary for lease loss.
  They remain temporarily readable/compatible for historical records but may
  not be required by new instructions or normal recovery.
- Exact clean committed HEAD remains mandatory at cross-role handoff. Dirty work
  stays with the current implementer until it is committed; this is a checkpoint
  rule, not a lock.

### 2. Immediate Paperclip transfer

Every cross-agent handoff uses this order:

1. Commit and push the exact checkpoint when the current role is a writer.
2. Record the controller transition and POST the evidence comment.
3. PATCH the same issue to the next assignee/status with `interrupt: true`.
4. Stop immediately; no post-PATCH read-back is required from the process being
   interrupted.

The interrupt PATCH is the final mutation by the old role. Paperclip cancels its
active run and queues the new assignee. There is no release/poll/reassign loop
and no `executionRunId` wait. A failed HTTP request may be retried once with the
same idempotent target; after that the watchdog repairs the exact handoff.

### 3. Watchdog repair without waiting tiers

For the Glitcherry company only, an issue whose live assignee differs from the
active execution owner is immediately actionable. The watchdog uses the
supported issue PATCH with `interrupt: true` for the already recorded target,
instead of alerting, waiting 60/90 minutes, or asking Board. Exact company,
issue, current run, next assignee, controller owner/phase, and workspace IDs are
checked before the mutation.

The watchdog must not infer a next role. It only finishes a controller-recorded
handoff. If no deterministic target exists, it wakes CTO for technical triage;
it does not create a new issue/worktree or edit storage directly.

### 4. Generated instructions

All six Glitcherry role bundles describe the same model:

- one sequential phase owner, not an exclusive lease holder;
- controller validation before repository access;
- clean commit at each writer boundary;
- `interrupt: true` on every cross-agent handoff;
- no Board escalation for stale run/lease, assignment lag, or recoverable
  controller bookkeeping;
- only real contract conflicts, unsafe human-only actions, credentials,
  publication, or stage-gate decisions may stop the roadmap.

## Scope

### In scope

- Remove persistent lease enforcement and expiry from the Glitcherry slice
  controller while preserving exact state/HEAD validation and atomic JSON writes.
- Migrate legacy live state on the next supported controller command.
- Replace lease language and recovery choreography in Glitcherry workflow,
  common overlay, CTO, implementer, reviewer, and QA roles.
- Make every Glitcherry cross-agent assignment interrupt the old run.
- Add immediate watchdog repair for a deterministic Glitcherry handoff stranded
  behind an old execution run.
- Rebuild generated agents, merge, deploy the exact merge to iMac, and verify
  all live bundles plus controller help/runtime behavior.

### Out of scope

- Allowing concurrent writers or two simultaneous phase owners.
- Removing Paperclip's global database consistency fields for other companies.
- Editing Paperclip database/controller JSON by hand.
- Changing roadmap order, Android product behavior, acceptance thresholds,
  review depth, merge authority, sprint smoke, signing, or publication.
- Retrying unchanged Android test heads.

## Affected files and areas

- `paperclips/projects/glitcherry-android/scripts/slice-worktree.py`
  - remove persistent lease creation/expiry/ownership gates;
  - retain short state-file write serialization and exact owner/HEAD checks;
  - support legacy records without manual recovery.
- `paperclips/projects/glitcherry-android/WORKFLOW.md`
  - replace lease/recover flows with sequential checkpoints and interrupting
    handoffs.
- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`
  - carry the durable lock-free handoff rule into all generated roles.
- `paperclips/projects/glitcherry-android/roles-codex/*.md`
  - remove claim/renew/conflicting-lease stops and require final
    `interrupt: true` reassignment.
- `services/watchdog/src/gimle_watchdog/{models,paperclip,detection_semantic,actions,daemon}.py`
  - expose active execution owner and immediately repair deterministic
    Glitcherry cross-agent handoffs.
- Focused controller, assembly, and watchdog tests under `paperclips/tests/` and
  `services/watchdog/tests/`.
- Generated `paperclips/dist/glitcherry-android*` artifacts, rebuilt from source.

## Acceptance criteria

1. No generated Glitcherry role requires, renews, waits for, recovers, or blocks
   on a persistent controller lease.
2. `claim` and `renew` are safe compatibility validation commands and never
   create or extend ownership state.
3. All controller transitions reject wrong expected owner, phase, branch/path,
   stale HEAD, dirty cross-role handoff, stale review approval, partial merge, or
   unsafe cleanup without using a lease.
4. A legacy state containing an active or expired lease proceeds through the
   correct current owner transition and removes the legacy lease automatically.
5. Every generated cross-agent handoff PATCH contains `interrupt: true`, is the
   old run's final action, and does not wait for `executionRunId` to clear.
6. Paperclip's existing interrupt contract is verified by targeted server tests;
   no generic server lock removal is necessary.
7. Watchdog repairs a deterministic Glitcherry assignee/execution-owner mismatch
   on its first eligible scan, with no 60/90-minute tier and no Board comment.
8. Watchdog does not kill or reassign when controller target, issue, workspace,
   or exact execution identity is ambiguous.
9. The same issue, execution workspace, task worktree, branch, PR, review counter,
   and primary implementer persist through every role handoff.
10. Full project controller, assembly, and focused watchdog tests pass; generated
    bundles contain a versioned marker `GLITCHERRY_INTERRUPT_HANDOFF_V1` and no
    contradictory exclusive-lease instructions.
11. Deployment is from the exact merged `origin/develop` SHA; live API bundles
    and iMac `workspace/AGENTS.md` hashes match the built artifacts.

## Verification plan

- Controller unit scenarios: normal handoff, legacy active/expired lease,
  wrong-owner, stale/dirty HEAD, reject counter, review approval, merge, cleanup.
- Assembly tests over all six source and rendered roles, including forbidden
  lease phrases and required interrupt marker/payload.
- Watchdog tests: first-scan deterministic repair, idempotent replay, already
  healthy owner, ambiguous target, wrong company, changed run, and API failure.
- Paperclip targeted tests proving `interrupt: true` cancels a running old agent
  and wakes the new assignee.
- Live canary on a disposable Glitcherry diagnostic issue: writer handoff to
  reviewer while the writer run is active; assert old run cancelled and reviewer
  queued/running without a deferred wake or Board action.
- Re-read live GLA-41/controller state after deployment; do not alter its Android
  HEAD or start an extra AVD run as part of this infrastructure verification.

## Risks and rollback

- Risk: the old process issues a late write after reassignment. Mitigation: the
  interrupting PATCH is its final action and Paperclip terminates that run before
  starting the next; the controller expected-owner/HEAD checks reject late
  transitions.
- Risk: removing leases exposes a genuinely concurrent external process.
  Mitigation: Paperclip remains the single active run coordinator; controller
  state writes remain atomic; exact owner/HEAD checks fail a stale command.
- Risk: watchdog interrupts the wrong run. Mitigation: company, issue, exact run,
  assignee, controller target, and workspace identity must all match.
- Rollback: revert the Gimle Palace merge, rebuild/redeploy prior role bundles,
  and keep existing controller states readable. No Android or Paperclip database
  migration is involved.

## Open questions

None. The Human Engineering Lead has selected lock-free sequential handoffs,
automatic interruption of the previous run, and deterministic media-test repair.
