# Glitcherry DX-00 diagnostic runtime contract

Status: awaiting explicit implementation approval

Date: 2026-09-01

Design revision: 1

Target repository: `ant013/Gimle-Palace`

Integration branch: `develop`

Design branch: `core/glitcherry-diagnostic-runtime`

Baseline: `9fc45f3e9c50f94188b95149cad4621b24a6e5ea`

Control contract: `ant013/Glitcherry@6e76a73e894e69f4546e67c3498f7864c8d0cb99`

## 1. Outcome

Make the existing Glitcherry Android Paperclip bundle execute the one approved
diagnostic sprint `DX-00` exactly as written in the control repository, without
weakening the normal product-slice workflow.

The runtime must recognize only `DX-001`, `DX-002`, `DX-003`, and `DX-004` as a
project-scoped diagnostic execution class. It must serialize them through the
existing CTO parent/child Walker loop, retain all issue history, respect the
owner-approved unlimited budget mode, and fail closed when watchdog PID attribution
is not exact.

This change is successful when the rebuilt six-role bundle can be deployed to the
existing Glitcherry Android company and the CTO can activate `DX-00` without either:

- applying seven product phases and two repository merges to read-only diagnostics;
- stopping merely because `budgetMonthlyCents=0` means unlimited rather than zero;
- creating the next child before the current child is terminal and cleanup is proven;
- deleting an issue or using a broad process-kill operation.

It does not start `DX-00`; live deployment and root-issue activation happen only
after this design is approved, implemented, verified, merged, and reconciled on the
iMac.

## 2. Assumptions and resolved owner decisions

- The canonical diagnostic contract is
  `Glitcherry/docs/roadmap/diagnostic-sprint.md` at control commit `6e76a73e`.
- The root issue pins `DX-00`, ordered children `DX-001..DX-004`, and that exact
  control commit before work begins.
- The existing Paperclip company, Project, six agents, and six named Project
  workspaces remain the deployment target; no second company is created.
- `budgetMonthlyCents=0` is explicitly approved by the owner as unlimited for
  Glitcherry. It is not a stop condition. Each run still records cost evidence and
  escalates anomalous spend.
- Issues are historical records. Runtime may transition them to `done`, `cancelled`,
  or `blocked`, but never DELETE them.
- The watchdog is live and can perform bounded issue recovery, but its current
  Codex-specific process attribution is unproven. `DX-004` therefore returns a safe
  `NOT_READY` unless an exact `company -> agent -> run -> PID` chain is observed.
- Persistent role workspaces and their persistent clones are retained. Cleanup
  applies only to exact proven-merged task/status refs and explicitly recorded
  temporary worktrees.
- No release build, signing, tagging, publication, roadmap promotion, or product
  feature work is authorized by this change.

## 3. Current failure and concrete evidence

The control roadmap is ready, but the current generated CTO prompt cannot execute it
faithfully:

1. `overlays/codex/_common.md` describes the seven product phases as unconditional.
2. `roles-codex/glitcherry-cto.md` says to stop on `zero budget at activation`.
3. `WORKFLOW.md` has no separate execution rules for `DX-001..DX-004`.
4. The existing disposable smoke exception cannot be reused because it forbids every
   repository write while `DX-003` deliberately proves one bounded Git lifecycle.

These facts were verified in the exact target worktree with Serena and targeted
`rg`. The available codebase-memory project points to a different checkout and does
not expose an indexed commit, so indexed locations are not load-bearing for this
design. Gimle/Palace MCP tools are unavailable in this session; the durable evidence
run records that environment drift and the exact-tree fallback.

## 4. Scope

### Project workflow source

Update `paperclips/projects/glitcherry-android/WORKFLOW.md` to define a diagnostic
execution class before the normal seven-phase child contract:

- allowlist only an issue whose title begins with an exact ID followed by
  `diagnostic`: `DX-001 diagnostic`, `DX-002 diagnostic`, `DX-003 diagnostic`, or
  `DX-004 diagnostic`;
- require the root to pin `DX-00`, the ordered four IDs, and control commit
  `6e76a73e894e69f4546e67c3498f7864c8d0cb99`;
- require the child description to identify the immutable control contract, current
  bounded step, and expected next owner;
- preserve one root, at most one non-terminal direct child, dependency order, and
  cleanup-before-next selection;
- define the exact diagnostic route and terminal behavior for each child;
- retain every issue and prohibit issue DELETE;
- treat owner-approved `budgetMonthlyCents=0` as unlimited while requiring per-run
  cost evidence and escalation for anomalous growth;
- leave the normal `READY` product-slice seven-phase contract unchanged.

### Shared rendered-role overlay

Update `paperclips/projects/glitcherry-android/overlays/codex/_common.md` so all six
roles receive the same diagnostic classifier, bounded contribution rules, handoff
order, issue-retention rule, budget semantics, and stop conditions.

The common overlay must make precedence explicit:

1. exact disposable smoke titles keep the existing repository-write-free smoke
   exception;
2. exact `DX-001..DX-004 diagnostic` titles use the new diagnostic contract;
3. every other prepared slice uses the normal seven product phases.

No issue body, comment, approximate prefix, or unapproved `DX-*` title can grant the
exception.

### CTO role source

Update `paperclips/projects/glitcherry-android/roles-codex/glitcherry-cto.md` to:

- recognize the exact diagnostic class and follow the project workflow instead of
  unconditionally promising two merges;
- accept owner-approved unlimited budget mode and stop only when cost policy is
  missing, contradictory, or exceeded under a future nonzero cap;
- keep the normal product-slice seven-phase, two-merge, and cleanup responsibilities;
- require prior-child terminal state plus cleanup proof before creating the next
  child;
- preserve CEO exclusion from normal product work while allowing the exact DX-001
  handoff route required by the diagnostic contract.

The individual non-CTO role crafts do not need separate policy edits because the
project common overlay is rendered into all six bundles and is the shared runtime
contract.

### Tests and generated artifacts

Extend `paperclips/tests/test_glitcherry_android_assembly.py` before changing runtime
source. Tests must pin the new source contract and every rendered role, then rebuild
the committed distribution:

- `paperclips/dist/glitcherry-android/codex/GlitcherryCEO.md`;
- `paperclips/dist/glitcherry-android/codex/GlitcherryCTO.md`;
- `paperclips/dist/glitcherry-android/codex/GlitcherryAndroidEngineer.md`;
- `paperclips/dist/glitcherry-android/codex/GlitcherryMediaPipelineEngineer.md`;
- `paperclips/dist/glitcherry-android/codex/GlitcherryCodeReviewer.md`;
- `paperclips/dist/glitcherry-android/codex/GlitcherryQAEngineer.md`;
- the resolved assembly only if the deterministic build changes its recorded output
  or digest.

## 5. Non-scope

- Shared `walker`, `reviewer`, `implementer`, or other fragment/profile changes.
- Runtime behavior of fullAudit, Trading, ThorChain, or any other company.
- Changes to Paperclip server source, database schema, scheduler, or issue API.
- Watchdog implementation changes or broad process-kill support.
- Android application source, Gradle configuration, emulator setup, or media code.
- Editing the already-approved control roadmap in this change.
- Creating, deleting, or replacing the live Glitcherry company or its Project.
- Creating the live root issue before the new bundle is deployed.

## 6. Diagnostic lifecycle

### Parent serialization

The existing CTO Walker parent loop remains the owner of selection. For `DX-00` it
selects only the first pinned diagnostic child whose dependency is `DONE`. Before
creating that child it proves:

- no non-terminal direct child exists;
- no unresolved parent blocker exists;
- the prior diagnostic issue is terminal and retained;
- all persistent clones are clean/current;
- no approved-but-unmerged PR, exact task/status ref, or recorded temporary worktree
  remains;
- prior-child cleanup evidence is complete.

The CTO then creates exactly one child, verifies its parent/Project/CTO-workspace
bindings, and blocks the root through `blockedByIssueIds`. Recovery may wake that
same issue; it never creates a replacement child.

### DX-001 — role and handoff circuit

Route exactly:

`CTO -> Android Engineer -> Media Pipeline Engineer -> Code Reviewer -> QA -> CEO -> CTO`

Each wake posts only its six-field identity/boundary card, atomically hands off the
same issue, verifies once, and stops. There are no repository writes, branches,
spec/plan files, product phases, reviews, QA test execution, or merges. The issue
description is the bounded execution spec.

### DX-002 — capability inventory circuit

Use the same one-issue route. Each role performs only safe read-only probes and posts
declared-versus-observed skill/MCP evidence without secrets. Missing, broken,
not-applicable, nested-error, mapping, or freshness results stay visible and cannot be
converted into PASS. There are no repository writes, product phases, or merges.

### DX-003 — bounded Git lifecycle

This is the only diagnostic child that enters the existing seven phases. The normal
independence, immutable-head, one-writer, QA, merge-authority, and cleanup gates apply,
with these narrower outputs:

- the CTO creates the task branch and materializes the diagnostic spec and plan;
- the Android Engineer adds only
  `docs/diagnostics/DX-003-workflow-proof.md` plus the approved diagnostic spec/plan
  artifacts;
- Code Reviewer and QA remain non-writing and bind evidence to the same exact head;
- QA does not invent an emulator gate when no Android scaffold exists;
- CTO squash-merges only to Android `develop`;
- no control status branch/second merge is needed because Paperclip comments and the
  retained issue are the diagnostic status ledger;
- the exact remote/local task refs and any recorded temporary worktree are removed
  only after the merge is proven, and all six persistent clones return clean/current
  `develop`.

This is an explicit narrow exception to the normal product slice's two-merge control
status synchronization. It does not weaken product behavior.

### DX-004 — watchdog qualification

The child first collects read-only live posture, detector, test, run, and process-tree
evidence. Fault injection is permitted only when the current diagnostic run maps to
one exact Codex subprocess PID through an unambiguous company/agent/run chain.

If attribution is absent or ambiguous, the role must not kill anything. It records
the framework blocker, sets the diagnostic child to `blocked`, and leaves the root
`blocked` with `ROADMAP_BLOCKED` and a bounded human-authored remediation. No next
child is permitted. That is a correct `NOT_READY` result, not a failed attempt to
force PASS.

If attribution is exact, watchdog may exercise only the documented `SIGTERM`, bounded
`SIGKILL` fallback, and same-issue recovery path. Broad `pkill`, process-name/glob
kills, threshold weakening, server/watchdog termination, another company, or a new
child are forbidden.

## 7. Handoff, status, and authority invariants

Every diagnostic handoff uses the existing atomic order:

1. POST evidence and require a 2xx response;
2. PATCH assignee, status, and the next owner's exact Project workspace ID;
3. perform one read-only GET verifying assignee/status/Project/workspace;
4. STOP the current run.

Additional invariants:

- a mention is not a handoff;
- no role wakes or advances itself after a successful transfer;
- only CTO creates a child and merges;
- Code Reviewer and QA never implement or push fixes;
- CEO participates only in the exact DX-001 circuit and remains outside normal
  product execution;
- `LOCAL_BLOCKED` and `ROADMAP_BLOCKED` use API status `blocked`;
- diagnostic issues are never physically deleted;
- a terminal issue is never reopened merely to continue the sprint;
- no next child exists until the current child is terminal and cleanup is proven.

## 8. Analog delta matrix

| Dimension | Primary/current analog | Required DX delta | Deliberately preserved |
| --- | --- | --- | --- |
| Boundary | Glitcherry exact `smoke-probe-*` / `smoke-e2e-*` project exception | Add a separate exact four-title diagnostic class | Smoke titles and their no-write behavior remain unchanged |
| Responsibility | Project `WORKFLOW.md` owns lifecycle; shared `walker` delegates to it | Put all DX orchestration in the Glitcherry project layer | No shared profile or other-company change |
| Lifecycle | Smoke performs one bounded response and stops | DX-001/2 use multi-role atomic handoff; DX-003 uses narrowed seven phases; DX-004 is fail-closed | Normal product slices retain all seven phases and two merges |
| State/errors | Smoke verifies handoff once; normal workflow blocks on dirty or partial state | Retain issues, accept unlimited budget, require terminal+cleanup before next, block on ambiguous PID | Existing 409 reload ceiling, exact workspace binding, no duplicate child |
| Dependencies | All six rendered roles consume `_common.md` and `WORKFLOW.md` | Rebuild and test all six outputs | Existing assembly and bindings remain authoritative |
| Trust | Current-tree Serena/`rg` confirms source and rendered contracts | Pin exact control commit/title allowlist in source and tests | Indexed search remains non-load-bearing until mapping/freshness is fixed |
| Tests | Glitcherry assembly tests pin workflow/common/roles; fullAudit pins its smoke class | Add exact DX source/rendered assertions plus negative and preservation assertions | Existing profile and all current assembly tests stay green |

## 9. Acceptance criteria

1. Only exact `DX-001 diagnostic` through `DX-004 diagnostic` title prefixes activate
   the diagnostic execution class.
2. Approximate `DX-*`, body text, comments, and unrelated company issues do not.
3. DX-001 and DX-002 are repository-write-free and do not require fake product
   spec/plan/review/QA/merge phases.
4. DX-003 retains independent spec/plan review, one writer, exact-head code review,
   read-only QA, one Android `develop` merge, and proven cleanup.
5. DX-004 never performs fault injection without exact run-to-PID attribution and
   returns a safe `NOT_READY`/`ROADMAP_BLOCKED` result when attribution is absent.
6. The CTO cannot create a next child until the current child is terminal and cleanup
   is proven.
7. Every issue is retained; no runtime source or generated role authorizes DELETE.
8. Owner-approved `budgetMonthlyCents=0` does not stop activation; missing or
   contradictory cost policy still does.
9. CEO is reachable only for the exact DX-001 circuit and remains outside the normal
   product chain.
10. The existing disposable smoke exception and normal seven-phase product workflow
    retain their behavior.
11. All six rendered roles contain the same resolved diagnostic contract and no
    unresolved template markers.
12. No shared profile, other-company bundle, watchdog source, Android app source, or
    Paperclip server source changes.

## 10. Test-first and verification plan

### Red test

First add assertions to `test_glitcherry_android_assembly.py` that fail on the current
baseline and cover:

- exact four-ID/title allowlist and immutable control SHA;
- distinct read-only DX-001/2, narrowed DX-003, and fail-closed DX-004 behavior;
- terminal-and-clean-before-next serialization;
- issue retention/no DELETE;
- owner-approved unlimited budget semantics and absence of the old
  `zero budget at activation` stop;
- CEO diagnostic-only participation;
- preservation of smoke and normal product seven-phase markers;
- propagation into every rendered role.

Run:

```bash
pytest -q paperclips/tests/test_glitcherry_android_assembly.py
```

The new test must fail for the expected missing runtime contract before source edits.

### Implementation verification

After the minimum source change:

```bash
bash paperclips/build.sh --project glitcherry-android --target codex
pytest -q paperclips/tests/test_glitcherry_android_assembly.py
pytest -q paperclips/tests/test_glitcherry_android_assembly.py paperclips/tests/test_phase_b_profiles.py
git diff --check
```

Also inspect the diff to prove only scoped source, test, and deterministic generated
artifacts changed. Search source and all six rendered roles for:

- unresolved `{{...}}` markers;
- `zero budget at activation`;
- any issue DELETE authorization;
- broad `pkill` or non-exact kill guidance;
- accidental changes to smoke or release authority.

### Post-merge live verification

From a fresh deployment worktree at the implementation merge SHA:

1. build and validate the Glitcherry Codex bundle;
2. reconcile the existing company, agents, Project, and workspace bindings without
   recreating them;
3. verify generated live `workspace/AGENTS.md` digests and runtime cwd mappings;
4. confirm all six agents remain idle before activation;
5. create one retained DX-00 root issue pinned to the exact control SHA and four
   ordered IDs;
6. wake only the CTO and monitor the one-child invariant, cost, watchdog, handoffs,
   Git state, and terminal retention through the sprint.

Live evidence is operational qualification, not part of the implementation commit.

## 11. Deployment and rollback

After tests pass, merge the implementation branch to `develop`, then deploy from a
fresh clean worktree rather than the dirty shared Gimle-Palace checkout. Rebuild and
reconcile the existing project bundle; do not recreate IDs.

If bundle validation or pre-activation live inspection fails, do not create the root
issue. Restore the previous generated prompt bundle from its known merge SHA, reconcile
the same agents/workspaces, and record the failed deployment evidence.

Once DX-00 is activated, recovery operates on the same retained root/child issues. It
does not delete them or replace them with a new sprint.

## 12. Open questions

No product or authority question remains before implementation. The only intentionally
unresolved operational fact is whether the current watchdog can attribute a
`codex_local` subprocess exactly. `DX-004` exists to answer that safely; absence of
proof produces `NOT_READY` and never authorizes an inferred or broad kill.
