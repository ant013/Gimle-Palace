# Glitcherry autonomous correction policy

Date: 2026-09-05  
Status: APPROVED
Branch: `feature/glitcherry-autonomous-corrections`  
Baseline: `da3e67763b026198f14b1d62cc301651e0607102` (`origin/develop`)

## Goal

Make routine correction work inside an approved Glitcherry Android slice
autonomous by default. A failed assertion, implementation defect, test-harness
race, fixture defect, diagnostic defect, or verification-tool defect must not
create a Human Engineering Lead / Board decision unless resolving it would
change the approved product contract.

The policy is durable company configuration. It is assembled into every
Glitcherry role's generated `AGENTS.md`, tested from source and rendered output,
and deployed to the live Paperclip company. It is not a one-off comment or an
exception tied to GLA-41, TP1, or a particular plan revision.

## Assumptions and authority

- The Human Engineering Lead grants the Glitcherry CTO and the independently
  reviewing Code Reviewer standing authority for bounded corrections described
  below.
- The Human Engineering Lead continues to own roadmap content/order, future
  slices, `DRAFT -> READY`, product behavior, acceptance meaning, stage gates,
  release/signing/publication, and the other explicit reserved decisions.
- Existing single-issue, single-worktree, exact-HEAD, exclusive-lease, review,
  merge, and cleanup invariants remain unchanged.
- The maximum of three complete Code Review rejection/fix/re-review cycles
  remains unchanged.
- Full sprint smoke remains after the final slice only. This change must not add
  per-slice QA or full device matrices.
- GLA-41 keeps its current issue, branch, worktree, controller state, and PR.
  Deployment changes instructions loaded by later agent wakes; it does not edit
  GLA-41 product files or controller storage.

## Decision model

### Autonomous correction envelope

The current primary implementer may diagnose, edit, commit, push, run bounded
checks, and return to Code Review on the existing issue/worktree/branch/PR when
the approved intent and contract remain unchanged. Correcting actual buggy
behavior so it conforms to the already approved behavior is explicitly inside
this envelope. All of the following contract dimensions must remain unchanged:

- user-visible behavior and approved acceptance criteria;
- acceptance threshold and the meaning of pass/fail;
- roadmap, sprint, slice scope, order, and READY state;
- production dependencies, toolchain versions, `minSdk`, `targetSdk`, and API
  floor;
- accepted ADRs, explicitly named cross-slice or cross-module architecture
  boundaries, security policy, and ownership of the single primary writer;
- credentials, signing, publishing, and destructive external actions.

This envelope includes:

- product-code fixes needed to satisfy already approved behavior;
- unit, instrumentation, and UI test corrections that preserve what the test is
  proving;
- fixture generation, seeding, cleanup, timing, synchronization, parsing, and
  evidence-capture repairs;
- diagnostic and verification-tool repairs;
- deterministic replacement of a brittle exact implementation assertion with
  an equivalent behavioral assertion, provided the acceptance threshold and
  pass/fail meaning do not change;
- local build/configuration repairs that do not change a pinned toolchain or
  production dependency.

These corrections are implementation detail. They need a clean committed HEAD,
focused evidence, and independent Code Review, but do not require a CTO plan
revision, Paperclip plan-mirror revision, Board interaction, or exact-revision
human confirmation.

### Autonomous classification

When a bounded check fails, the implementer records the failure and classifies
it before acting:

1. Approved product behavior is wrong: fix the product within the current
   slice, run the focused check, and return the same PR to review.
2. Test, fixture, harness, diagnostic, or verification tooling is wrong or
   brittle: fix that support code without weakening acceptance, run the focused
   check, and return the same PR to review.
3. Host/emulator/tool transport failed before producing application evidence:
   perform the already allowed bounded cleanup/retry. If a repository-owned
   harness or diagnostic defect caused it, fix that defect autonomously. If an
   external operator action is genuinely required, report that concrete action
   as an operational blocker rather than asking the Board to choose a technical
   implementation.
4. Evidence is initially ambiguous: the CTO makes the technical classification
   from the pinned contract and routes the same issue to the correct existing
   owner. Ambiguity alone is not a reason to ask the Board. Reversible internal
   implementation choices inside accepted boundaries belong to CTO plus the
   primary implementer and independent Code Reviewer.

`ROADMAP_BLOCKED` or a structured Board interaction is allowed only when the
correction cannot be made without changing one of the reserved dimensions
listed above, the authoritative contracts actually conflict, or the required
action needs human-only credentials, signing, publication, a stage-gate ruling,
or unsafe/destructive external authority. "Architecture" alone is not a reason:
the proposed correction must change a cited accepted ADR or an explicitly named
architecture boundary before it becomes a Board decision.

### Executable controller routes

The instruction implementation must name these exact supported routes. It must
not leave phase names to individual agents:

| Starting situation | Required controller route |
| --- | --- |
| Implementer finds an envelope-safe defect before review | Keep the current `implementation` or `implementation_fix` lease, correct it, commit, run focused checks, then hand off the clean HEAD to `GlitcherryCodeReviewer / code_review`. |
| Code Reviewer finds a product or support-code defect | Use controller `reject` to the recorded primary implementer. The controller sets `implementation_fix`; the implementer corrects the same PR and returns the new HEAD to `code_review`. |
| Implementer cannot initially classify evidence | Commit any legitimate dirty slice work, then `handoff` the clean HEAD to `GlitcherryCTO / technical_triage`. CTO claims it and, without editing the plan, hands the unchanged HEAD to the recorded primary implementer in `implementation`. |
| A clean correction-only incident was already controller-blocked | CTO uses supported `resume-blocked` to `GlitcherryCTO / plan_revision` with the accepted autonomy-policy merge SHA as decision evidence, claims it, makes no synthetic plan edit, and hands the unchanged HEAD to the recorded primary implementer in `implementation`. |
| A dirty correction-only incident was already controller-blocked | CTO uses supported `resume-blocked` to the recorded primary implementer in `implementation_recovery`; that implementer preserves legitimate work in one commit and hands it to `GlitcherryCTO / plan_revision`; CTO makes no synthetic plan edit and routes the clean HEAD to that implementer in `implementation`. |
| A correction is discovered after exact-head Code Review approval but before merge | Do not merge the stale approval. CTO hands the clean approved HEAD to the primary implementer in `implementation`; the new correction HEAD must return through `code_review`. |

No direct controller JSON/database edit, replacement issue/worktree/branch, or
review-counter reset is allowed. A local implementer attempt before the first
Code Review does not consume a rejection cycle. Each controller `reject` from
`code_review` consumes exactly one cycle whether it identifies product code or
support code. CTO routing must never be used to bypass that counter.

### Focused replacement runs

A harness, fixture, emulator-startup, adb-transport, or evidence-capture attempt
that fails before producing valid application evidence does not consume a
product verification attempt. After an envelope-safe fix is committed, each new
clean correction HEAD receives the one focused rerun needed to verify that
correction and the affected acceptance criterion. This does not authorize a
second emulator, a full matrix, per-slice QA, repeated unchanged-HEAD retries,
or any threshold/pass-fail relaxation.

### Plans describe intent, not incidental mechanics

A plan must map acceptance criteria to implementation ownership and
verification. Acceptance criteria, explicit contract invariants, security
constraints, accepted ADRs, named architecture boundaries, and a file allowlist
explicitly marked `strict` remain mandatory. An implementation sketch, helper
names, ordinary file estimates, assertion mechanics, fixture seeding mechanics,
synchronization details, parser implementation, and other incidental details
are not frozen requirements unless the approved acceptance contract explicitly
makes them observable. Moving into a new module or across a named layer requires
CTO disposition and independent review, but not Board confirmation when every
reserved contract dimension remains unchanged.

An assertion that proves an explicit acceptance criterion, numeric threshold,
or the only remaining evidence for an acceptance criterion cannot be removed or
weakened autonomously. An assertion about an unstated internal detail may be
repaired or replaced when an equally strong or stronger stable proof of the
approved behavior remains. Implementer/reviewer disagreement is classified by
CTO against the pinned contract; Board is required only when that contract is
insufficient or must change.

If a bounded correction stays inside the autonomous envelope, the implementer
records it in commit and issue evidence. The CTO does not revise the tracked
plan merely to make the plan narrate the discovered implementation detail. If a
real plan revision is useful but stays entirely inside the standing delegation,
CTO plus independent exact-revision Code Review may complete it without another
human confirmation.

### Tool fallback

Failure or unavailability of Serena, codebase-memory, Context7, or another
advisory MCP is not a product blocker. The role records the unavailable tool and
continues with the remaining indexed tool plus targeted `rg`, local file reads,
compiler/test output, and official Android documentation. It stops only if the
missing tool was explicitly required by the active acceptance contract and no
equivalent evidence path exists.

## Scope

### In scope

- Replace the narrow issue-specific delegation language with the permanent
  autonomous correction envelope in the lifecycle authority.
- Give CTO a deterministic classifier and direct rerouting responsibility.
- Give both implementer roles explicit authority to correct product/test/
  harness/fixture/diagnostic defects inside the envelope.
- Require Code Reviewer to distinguish real acceptance weakening from valid
  implementation/test repair and to avoid a duplicate Board gate.
- Put the shared policy marker in the common Codex overlay so every generated
  role sees the standing delegation and its human-only boundaries.
- Add regression tests over source roles, workflow, and every rendered
  Glitcherry `AGENTS.md`.
- Rebuild the Glitcherry assembly and deploy the exact merged `develop` result
  to the iMac Paperclip company.

### Out of scope

- Changing the Android product, GLA-41 plan/code/tests, roadmap, or acceptance
  criteria.
- Removing exact worktree/HEAD/lease checks or permitting concurrent writers.
- Allowing agents to author/promote future slices or make stage-gate decisions.
- Changing the three-cycle Code Review ceiling.
- Waiving failing tests, relaxing thresholds, or turning sprint smoke into a
  non-blocking check.
- Editing Paperclip storage directly or changing the generic Paperclip server.
- Broad watchdog process matching or automatic termination without exact
  company/agent/issue/run/PID attribution.

## Affected files and areas

- `paperclips/projects/glitcherry-android/WORKFLOW.md`
  - define the standing delegation, failure classifier, direct correction loop,
    plan-detail rule, human-only boundary, and MCP fallback;
  - update phase 3/4/5 routing and stop conditions consistently.
- `paperclips/projects/glitcherry-android/roles-codex/glitcherry-cto.md`
  - make CTO the autonomous classifier/router and remove duplicate human gates
    for envelope-safe corrections.
- `paperclips/projects/glitcherry-android/roles-codex/android-engineer.md`
  - authorize bounded product/support-code corrections on the same PR.
- `paperclips/projects/glitcherry-android/roles-codex/media-pipeline-engineer.md`
  - authorize the same correction loop for media implementation and harnesses.
- `paperclips/projects/glitcherry-android/roles-codex/code-reviewer.md`
  - review behavioral equivalence and route valid corrections without Board.
- `paperclips/projects/glitcherry-android/overlays/codex/_common.md`
  - carry the permanent standing-delegation summary and MCP fallback to all six
    generated roles.
- `paperclips/tests/test_glitcherry_android_assembly.py`
  - scenario-style assertions over workflow/source roles and all rendered roles,
    including removal of conflicting legacy language and preservation of
    human-only and role-write boundaries.
- `paperclips/tests/test_glitcherry_slice_worktree.py`
  - exercise the supported implementer/reviewer/CTO routes, legacy clean/dirty
    correction-only recovery, stale approval invalidation, and unchanged review
    rejection counter semantics.
- Generated `paperclips/dist/glitcherry-android*` assembly artifacts
  - rebuild from source; never hand-edit.

No watchdog source change is planned. Existing exact-run hang/death recovery is
orthogonal: this task removes unnecessary decision waits after a healthy agent
has produced a correctable finding. If implementation discovery proves that a
runtime wake bug prevents the documented direct handoff, that is a separate
reproduced infrastructure defect and must not be silently folded into this
instruction-only change.

## Acceptance criteria

1. Workflow defines one project-wide autonomous correction envelope without a
   GLA/TP/slice-specific condition.
2. A product defect within approved behavior routes directly to the recorded
   primary implementer and then independent Code Review on the same PR.
3. A test/harness/fixture/diagnostic/verification defect routes through the same
   direct correction loop without plan revision or Board confirmation when
   acceptance meaning is unchanged.
4. CTO, Android Engineer, Media Pipeline Engineer, and Code Reviewer source
   roles all state the same classifier and boundaries without contradictory
   stop language.
5. All six rendered Glitcherry roles receive the standing-delegation marker via
   the common instruction layer.
6. Board interaction remains mandatory for product/roadmap/scope/order,
   dependency/toolchain/API floor, acceptance meaning/threshold, ADR/
   architecture, human credentials, signing/publication, destructive external
   action, and stage-gate decisions.
7. Exact issue/workspace/worktree/branch/HEAD/lease, one-writer, review, merge,
   cleanup, and three-review-cycle safeguards remain intact.
8. Advisory MCP failure has an explicit local-tool fallback and is not listed as
   an unconditional blocker.
9. A failed support/infrastructure attempt without application evidence does not
   consume the product attempt; one focused rerun is allowed for each new clean
   correction HEAD without relaxing acceptance.
10. Scenario tests prove the exact supported controller routes for findings
    before review, reviewer rejection, CTO technical triage, correction-only
    blocked recovery, and a correction after stale approval.
11. Common instructions do not expand write authority: CEO remains outside the
    normal slice chain, QA remains sprint-smoke-only, Code Reviewer remains
    read-only, and only the primary implementer writes corrections.
12. No full sprint smoke or per-slice QA is introduced; TP1 still stops only
   after its final slice at `SPRINT_SMOKE_REQUIRED`.
13. The project assembly builds, instruction validation passes, Glitcherry
    assembly regression tests pass, and `git diff --check` is clean.
14. The implementation branch is merged to `develop`, the Glitcherry bundle is
    deployed from that merged result, and live read-back proves every Paperclip
    role's generated instructions contain the durable policy marker.
15. Live read-back also proves byte-for-byte SHA-256 equality between each of the
    six rendered files and its deployed instruction bundle, with agent IDs,
    models, reasoning effort, reports-to bindings, and workspaces unchanged.
16. The active GLA-41 task branch/worktree/controller/PR and Android/control
    repository contents are not modified by this change.

## Verification plan

1. Run scenario-style source assertions covering the workflow, four
   participating role files, all generated roles, forbidden legacy language,
   and unchanged CEO/QA/reviewer write boundaries.
2. Run focused controller tests for every row in the executable route table and
   prove only real `CodeReviewer reject` transitions increment the durable
   rejection counter.
3. Build the Glitcherry project assembly with the repository's compatibility
   builder.
4. Run `paperclips/scripts/validate_instructions.py`.
5. Run
   `python3 -m pytest paperclips/tests/test_glitcherry_android_assembly.py -q`.
6. Run the focused Glitcherry controller test file.
7. Run `git diff --check` and inspect the changed-file allowlist.
8. Push the implementation head, review the exact diff, merge to `develop`, and
   verify the merge SHA is reachable from `origin/develop`.
9. The Human Engineering Lead explicitly authorizes immediate Glitcherry
   instruction deployment from the exact merged `develop` SHA. On the iMac run:

   ```bash
   bash paperclips/scripts/imac-agents-deploy.sh \
     glitcherry-android \
     --target-sha <exact-develop-merge-sha>
   ```

10. Read back all six live instruction files/API bindings. Prove SHA-256 equality
    with the corresponding rendered files and prove the permanent marker is
    present without changing agent IDs, models, reasoning effort, reports-to
    bindings, Project/execution workspaces, or the active GLA-41 controller
    tuple.

## Rollback

Revert the single merged instruction-policy change on `develop`, rebuild the
Glitcherry assembly, and redeploy that exact revert result. The change has no
Android data/schema migration and does not modify active slice controller state.

## Open questions

None. The Human Engineering Lead's request is treated as explicit standing
delegation within the boundaries above.
