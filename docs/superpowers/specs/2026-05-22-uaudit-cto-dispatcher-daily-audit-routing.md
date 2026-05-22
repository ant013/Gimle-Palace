# UAudit CTO Dispatcher And Daily Audit Routing

## Goal

Reduce `UWACTO` and `UWICTO` from full CTO/merge agents into lightweight audit
dispatchers, and move "do we audit?" decisions for UAudit scheduled/manual
audit issues to the platform CTO dispatcher before any infra or auditor work
starts.

The target model is:

- platform CTO decides and routes;
- infra executes prepared runtime/delivery work;
- auditors review only non-empty, explicitly approved audit scopes.

This fixes the failure mode where a runtime executor can incorrectly treat stale
local repository state as an authoritative audit signal and run or deliver an
audit that should have been a no-op.

## Background

`UWACTO` and `UWICTO` currently compile from `role_source:
paperclips/roles-codex/cx-cto.md` with `profile: cto`. The deployed bundles
therefore include generic CTO/reviewer rules such as merge readiness, GitHub
approval, release-cut, phase orchestration, and plan-first workflow. For UAudit
platform CTO agents, most of that is not relevant to the active job.

The source overlays for `UWACTO` and `UWICTO` are much smaller: they mainly
route PR-audit issues to the platform audit coordinator. The deployed bundles
are therefore heavier and more ambiguous than the actual UAudit platform CTO
responsibility.

The Android daily delta incident in `UNS-102` exposed a second responsibility
problem. The daily version-branch routine is currently owned end-to-end by
`UWAInfraEngineer`, including the no-op/rollback decision. The design should
separate the decision gate from the runtime execution path.

## Assumptions

- `AUCEO` remains the high-level UAudit project owner and can keep a full CTO
  profile if needed.
- `UWACTO` and `UWICTO` are platform dispatchers, not merge/release owners for
  Gimle-Palace code changes.
- `UWAInfraEngineer` and `UWIInfraEngineer` remain the owners for Telegram
  delivery, cursor writes, runtime paths, repository checkout, and
  codebase-memory refresh.
- Daily version-branch audit issues are visible Paperclip issues and can be
  assigned to `UWACTO` or `UWICTO` before infra execution.
- GitHub upstream branch heads are authoritative for daily delta intake. Local
  mirrors and working copies are cache/execution state, not proof of current
  branch position.

## Scope

### Role And Manifest Updates

- Change `UWACTO` and `UWICTO` away from the full `cto` profile.
- Use `profile: custom` for `UWACTO` and `UWICTO` so the generated dispatcher bundles do not inherit the universal CTO/reviewer/release fragments. The role craft must carry the necessary routing safety text explicitly.
- Do not keep `role_source: paperclips/roles-codex/cx-cto.md` for `UWACTO`
  or `UWICTO`. `profile: custom` alone is insufficient because the role craft
  still says the agent owns plan-first review, merge gates, and release-cut.
- Add slim UAudit platform-dispatcher role craft in the UAudit project layer,
  for example:
  - `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`
  - `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`
- These slim role sources must describe platform audit dispatch only. They must
  not mention merge gates, release-cut, GitHub PR approval, plan-first review,
  or generic implementation ownership.
- Keep dispatcher logic in the UAudit project-layer overlays, not in a new
  global profile:
  - `paperclips/projects/uaudit/overlays/codex/UWACTO.md`
  - `paperclips/projects/uaudit/overlays/codex/UWICTO.md`
- Do not introduce a global dispatcher/router profile in this slice. If multiple
  projects later need the same pattern, extract a shared profile in a separate
  reviewed change.
- Keep only the rules needed for routing and issue hygiene:
  - wake/stale issue guard;
  - exact handoff rule: comment + PATCH + stop;
  - platform ownership and roster;
  - source-of-truth rules for GitHub branch head and audit cursor;
  - PR audit routing;
  - daily delta decision routing;
  - malformed/unknown/anomalous issue handling.
- Remove platform CTO exposure to unrelated merge/release/GitHub approval
  rules.

### Daily Delta Ownership Split

- Add a repo-owned daily audit routine/scope config as the single source of
  truth for scheduled routine reconciliation and valid scopes, for example:
  `paperclips/projects/uaudit/daily-version-branch-routines.yaml`.
- The config must include, per platform:
  - platform;
  - branch;
  - GitHub repo URL;
  - cursor path;
  - expected routine title/body marker;
  - schedule;
  - expected platform CTO agent name;
  - expected infra executor agent name;
  - required audit subagent roster by agent name;
  - delta size limits, at minimum `max_commits` and one of `max_files` or
    `max_diff_lines`;
  - allowed initialization mode.
- Default Android/iOS daily delta size limits are `max_commits: 30`,
  `max_files: 300`, and `max_diff_lines: 3000` unless a platform config
  explicitly tightens them.
- Routine reconciliation scripts and docs must read this config, not hard-code
  agent UUIDs or infer ownership from prose.
- Routine/scope config must refer to agents by name only. Reconciliation must
  resolve name to UUID through the existing UAA bindings/deploy resolver used by
  the deploy tooling. The config must not duplicate UUIDs.
- Assign daily version-branch issues first to the platform CTO dispatcher:
  - Android: `UWACTO`;
  - iOS: `UWICTO`.
- Platform CTO performs only the decision gate:
  1. fetch authoritative upstream branch head from GitHub;
  2. read the platform cursor;
  3. compare `FROM` and `TO`;
  4. decide `no-op`, `forward delta`, `blocked/anomaly`, or `initialization`.
- If `FROM == TO`, platform CTO comments `No new commits` and closes the issue
  without assigning infra or auditors.
- No-op daily issues must not create run directories, status files, audit
  artifacts, Telegram deliveries, subagent work, or cursor writes.
- If the delta is forward and within config policy, platform CTO assigns the
  platform infra engineer with exact immutable inputs: `FROM`, `TO`, branch,
  repo, cursor path, run path, delta size counts, and required subagent roster.
- The required subagent roster lives in the routine/scope config. CTO restates
  it verbatim in the infra handoff for audit trail. Infra verifies that the
  handoff roster equals the config roster; mismatch blocks the run.
- If the forward delta exceeds configured size limits, platform CTO blocks and
  assigns `AUCEO` using the anomaly handoff mechanics below. Infra must not be
  assigned for oversized deltas.
- If the branch appears to move backward, the cursor object is missing, the
  local mirror disagrees with GitHub, or the delta shape is ambiguous, platform
  CTO blocks/escalates. It must not run the audit.
- If the cursor is missing for a valid first-run or new-scope initialization,
  platform CTO classifies the issue as initialization and assigns infra with the
  exact authoritative upstream head SHA and evidence source. Infra writes that
  SHA verbatim as the baseline cursor, comments that no audit was run, closes
  the issue, and stops. Infra must not recompute branch state for initialization.
- If the cursor is missing for an already-active known scope, platform CTO
  treats it as lost audit state and blocks/escalates instead of initializing
  silently.
- Initialization is valid only for a new scope when explicitly allowed by the
  routine/scope config or by a one-off initialization issue body field such as
  `initialization_allowed: true`. A normal scheduled daily issue with a missing
  cursor is treated as lost audit state.
- Repeated initialization is forbidden. If a cursor already exists, any
  initialization request blocks. If initialization succeeds, the next config
  change must set the scope's bootstrap/init allowance to false, or the
  reconciliation/validation script must refuse repeated initialization for that
  scope.

### Anomaly Matrix

Platform CTO dispatchers must use this matrix before assigning infra:

| Case | CTO action | Owner after action |
|---|---|---|
| `FROM == TO` | Comment no-op with `FROM`, `TO`, GitHub source, and cursor unchanged; close issue | Closed by platform CTO |
| `FROM` ancestor of `TO`, within size limits | Assign infra with exact `FROM`, `TO`, repo URL, branch, cursor path, required subagents | Platform infra |
| Valid first-run/new-scope initialization | Assign infra with exact upstream head SHA and initialization evidence | Platform infra |
| Delta exceeds configured limits | PATCH `status=blocked`, assign `AUCEO`, comment exact counts and limits | `AUCEO` decision |
| Cursor missing for known scheduled scope | PATCH `status=blocked`, assign `AUCEO`, comment lost audit state | `AUCEO` decision |
| GitHub upstream and local mirror disagree | Use GitHub as authoritative; if local mirror state is needed for execution, PATCH `status=blocked`, assign `AUCEO`, comment mirror drift | `AUCEO` decision |
| Branch appears to move backward from cursor | PATCH `status=blocked`, assign `AUCEO`, comment rollback/divergence evidence | `AUCEO` decision |
| Cursor SHA missing from fetched upstream object graph | Treat as history rewrite / missing cursor object; PATCH `status=blocked`, assign `AUCEO`, comment missing-object evidence | `AUCEO` decision |
| Issue body malformed or unsupported scope | PATCH `status=blocked`, assign `AUCEO`, comment required fields | `AUCEO` decision |

For AUCEO escalation, do not rely on a decorative text mention. The platform CTO
must change ownership through Paperclip state: `PATCH status=blocked` and
`assigneeAgentId=<AUCEO UUID resolved by existing bindings/deploy resolver>`,
with a comment containing the evidence and requested decision. Use `blockedBy`
only if the current Paperclip API supports it and the implementation tests that
it wakes the target owner. Do not assign `runtime/harness operator` for
policy/data anomalies; reserve operator routing for API, sandbox, permission, or
tooling gaps that no UAudit agent can resolve.

### Infra Execution Path

- Keep `UWAInfraEngineer` and `UWIInfraEngineer` as runtime executors for
  approved non-empty daily deltas.
- Infra must not independently decide whether an audit is necessary when a
  platform CTO handoff is required.
- Remove these decision-gate branches from
  `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md` and
  `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`:
  - silent cursor bootstrap: `If the cursor file is missing, create it with ...`;
  - no-op decision and no-op marker creation;
  - initialization decision;
  - rollback/backward/divergence decision;
  - oversized-delta policy decision.
- Infra keeps only executor-side validation: it verifies that CTO-provided
  immutable inputs match the config and runtime state needed to execute.
- Infra still verifies its inputs before execution and blocks on mismatch, but
  it does not reinterpret stale local refs as authoritative branch state.
- Infra execution inputs are immutable. If infra observes that its local repo,
  cursor, or generated artifacts do not match the CTO handoff values, it blocks
  and returns to the platform CTO or `AUCEO`; it does not "fix up" the scope.
- Infra remains responsible for:
  - artifact generation;
  - checkout at `TO`;
  - codebase-memory refresh;
  - required subagent fanout;
  - aggregation;
  - Telegram delivery;
  - cursor update only after successful delivery.

### Documentation Updates

- Update `docs/superpowers/specs/2026-05-12-uaudit-infra-incremental-orchestrator.md`
  or add a successor note that supersedes the end-to-end infra ownership model.
- Update or explicitly mark stale sections as superseded in:
  - `docs/superpowers/specs/2026-05-12-uaudit-infra-incremental-orchestrator.md`
  - `docs/superpowers/specs/2026-05-11-uaudit-report-delivery-owner.md`
  - `docs/superpowers/plans/2026-05-15-uaa-phase-F-uaudit-migration.md`
  - `docs/runbooks/uaa-live-deploy.md`
  - `paperclips/scripts/imac-agents-deploy.README.md`
  - `services/palace-mcp/README.md` if it references UAudit role ownership or
    deploy responsibilities
- Update UAudit role documentation so the decision/execution boundary is clear.
- Update deploy/runbook documentation for UAudit prompt deploys, including:
  - which generated bundles should shrink;
  - how to verify live `UWACTO`/`UWICTO` instructions;
  - how to deploy the new UAudit bundles;
  - rollback path if routing fails after deploy.
- Update any routine creation/reconciliation docs so daily issues are assigned
  to platform CTO dispatchers rather than infra executors.
- Documentation changes must be validated as part of the implementation. Broken
  links, stale role names, stale agent IDs, or contradictory daily-audit
  ownership language block the change.
- Add `paperclips/scripts/validate_uaudit_docs.py` or equivalent automated
  validation. It must assert:
  - internal Markdown links touched by this slice resolve;
  - stale references to infra-owned daily audit are removed or marked
    `SUPERSEDED`;
  - docs refer to UAudit agents by valid names;
  - any UUIDs still present in docs match values resolved by the existing
    bindings/deploy resolver;
  - daily routine ownership docs point to platform CTO dispatchers.

### Deploy Updates

- Rebuild UAudit Codex bundles.
- Deploy updated UAudit agents to the iMac/Paperclip live environment using the
  prompt-only deploy path.
- Before release-cut, deploy for live smoke with:
  `paperclips/scripts/imac-agents-deploy.sh uaudit --from-develop`.
- After release-cut, deploy from the default `origin/main` path with:
  `paperclips/scripts/imac-agents-deploy.sh uaudit`.
- Do not use full `bootstrap-project.sh uaudit --canary` for this prompt-only
  update unless a fresh bootstrap/migration is explicitly required.
- Rollback for this deploy path is previous-SHA redeploy through
  `imac-agents-deploy.sh --target-sha <previous-good-sha>`; document the exact
  previous SHA used before live deploy.
- Verify authoritative Paperclip-managed deployed instructions, not only
  workspace copies. Use the repository's compare/deploy tooling, such as
  `paperclips/scripts/compare_deployed_agents.py`, or an equivalent hash check
  against the Paperclip-managed instructions.
- Verify deployed `AGENTS.md` for `UWACTO` and `UWICTO` no longer contain
  generic merge/release/code-review sections.
- Verify live `UWAInfraEngineer` and `UWIInfraEngineer` contain executor-only
  daily delta instructions.
- Deploy order is mandatory:
  1. prompt-only deploy;
  2. synthetic no-op smoke assigned manually to the platform CTO dispatcher;
  3. routine reconciliation only after smoke passes.
- If smoke fails, roll back the prompt deploy before touching routines.
- Reconcile Paperclip routines only after smoke passes so scheduled daily issues
  target the platform CTO dispatcher.
- Add or update a routine reconciliation check/script. It must support a dry-run
  mode that reports current daily routine assignees and the expected platform
  CTO assignees. Live mode may update the routines after operator approval.
- Before live deploy, record the previous good SHA in the issue or PR deploy
  notes. The rollback command must reference that exact SHA.

## Out Of Scope

- Changing Telegram plugin behavior.
- Changing the required audit subagent set.
- Changing UAudit issue prefixes, company IDs, or agent UUIDs except where
  routine assignment is updated.
- Implementing a new scheduler outside Paperclip routines.
- Rewriting PR-audit coordinator behavior beyond making CTO routing clearer.
- Changing `AUCEO` unless review finds project-level ambiguity that blocks the
  platform dispatcher split.
- Reviewing or shrinking `AUCEO`'s full CTO profile. `AUCEO` profile review is
  deferred to a follow-up so this slice stays focused on platform dispatchers.

## Affected Files And Areas

Expected files or areas:

- `paperclips/projects/uaudit/paperclip-agent-assembly.yaml`
- `paperclips/projects/uaudit/roles-codex/*.md` for slim platform dispatcher
  role craft
- `paperclips/projects/uaudit/overlays/codex/UWACTO.md`
- `paperclips/projects/uaudit/overlays/codex/UWICTO.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/daily-version-branch-routines.yaml` or equivalent
  repo-owned routine/scope config
- generated `paperclips/dist/uaudit/codex/*.md`
- generated `paperclips/dist/uaudit.resolved-assembly.json`; if it cannot show
  the effective manifest profile/role source, update the generator so it does.
  Rendered bundle content remains the final prompt-behavior authority.
- UAudit deploy/runbook docs
- daily routine reconciliation docs or scripts, if present

## Acceptance Criteria

- `UWACTO` and `UWICTO` generated bundles are bounded dispatcher bundles. The
  pre-commit ceiling is 100 lines and 4 KiB per generated bundle. If the first
  build proves this impossible because of mandatory universal content, the PR
  must pin a reviewed higher ceiling in tests with an explanation.
- `UWACTO` and `UWICTO` generated bundles do not include:
  - Git merge readiness;
  - merge state decoder;
  - GitHub approval checklist;
  - CTO merge authority;
  - release-cut procedure;
  - generic plan-first phase orchestration.
- `UWACTO` and `UWICTO` explicitly own daily audit intake decisions for their
  platform.
- `UWACTO` and `UWICTO` use slim UAudit dispatcher role sources, not
  `paperclips/roles-codex/cx-cto.md`.
- A daily no-op (`FROM == TO`) closes at the platform CTO dispatcher without
  assigning infra, spawning auditors, delivering Telegram, writing run
  artifacts, or updating the cursor.
- First-run/new-scope initialization is routed by platform CTO to infra; infra
  writes the current upstream head as the baseline cursor and stops without an
  audit.
- Forward deltas are handed to infra with exact `FROM` and `TO` values.
- Rollback/divergence/stale mirror cases block or escalate before audit fanout.
- History rewrite / missing cursor object cases block or escalate before audit
  fanout.
- Oversized deltas are blocked by platform CTO using routine-config size limits.
- Required audit subagent roster is sourced from routine/scope config; CTO
  restates it and infra verifies it.
- Infra daily delta instructions describe executor responsibilities only and
  preserve cursor-after-delivery safety.
- Infra overlays no longer contain silent cursor bootstrap, no-op decision,
  initialization decision, rollback/divergence decision, or oversized-delta
  decision branches.
- UAudit docs explain the decision/execution boundary and the deploy procedure.
- `paperclips/scripts/validate_uaudit_docs.py` or equivalent automated docs
  validation passes.
- Routine reconciliation has both documentation and a dry-run/live check/script
  backed by the repo-owned routine/scope config and resolving UUIDs from
  existing bindings/deploy resolver.
- Live deploy verification proves `UWACTO`/`UWICTO` are updated in authoritative
  Paperclip-managed instructions, not only in workspace copies.
- Existing PR-audit routing still routes Android PRs to `UWAKotlinAuditor` and
  iOS PRs to `UWISwiftAuditor`.
- Cross-platform PRs still route to the peer platform CTO before reaching the
  peer platform audit coordinator.
- Existing PR-audit branches in the slim dispatcher role/overlay preserve both
  current PR routing cases and daily-audit intake cases.

## Verification Plan

- Build UAudit Codex bundles:
  `./paperclips/build.sh --project uaudit --target codex`
- Validate instructions:
  `python3 paperclips/scripts/validate_instructions.py --repo-root .`
- Run relevant Paperclip tests:
  `python3 -m pytest paperclips/tests/test_handoff_strict_rules.py -v`
- Run Codex target validation:
  `./paperclips/validate-codex-target.sh`
- Run documentation validation/checks added or available in the repository. If
  a dedicated Markdown link validator is not added, the implementation is not
  complete.
- Run UAudit docs validation:
  `python3 paperclips/scripts/validate_uaudit_docs.py`
- Add or update tests that assert:
  - `UWACTO`/`UWICTO` generated bundles exclude merge/release/review sections;
  - `UWACTO`/`UWICTO` generated bundles include required dispatcher markers;
  - `UWACTO`/`UWICTO` generated bundles stay under numeric line/byte limits;
  - daily no-op routing text exists in platform CTO bundles;
  - infra bundles still include executor/delivery/cursor safety text;
  - infra bundles no longer include cursor-bootstrap/no-op/init/anomaly
    decision branches.
- Add or update deterministic tests for:
  - no-op: no infra assignment, no `$RUN`, no Telegram, no cursor mutation;
  - valid initialization: CTO hands exact head SHA to infra;
  - missing cursor on known scheduled scope: blocked/escalated;
  - backward/diverged branch: blocked/escalated;
  - missing cursor object/history rewrite: blocked/escalated;
  - oversized delta: blocked/escalated using config limits;
  - forward delta: infra handoff includes exact `FROM` and `TO`;
  - infra verifies handoff roster equals config roster;
  - Android PR routing to `UWAKotlinAuditor`;
  - iOS PR routing to `UWISwiftAuditor`;
  - cross-platform PR routing to the peer CTO.
- Add or update tests/checks for routine reconciliation dry-run output from the
  repo-owned routine/scope config.
- Update any existing UAudit profile snapshot tests that still hard-code
  `UWACTO`/`UWICTO` as `cto`.
- Dry-run UAudit deploy for changed agents.
- Live deploy changed UAudit agents through the pinned prompt-only deploy path.
- Execute deploy sequence in the pinned order: deploy, synthetic no-op smoke,
  then routine reconciliation.
- On iMac, verify:
  - authoritative Paperclip-managed `UWACTO` and `UWICTO` instructions match
    generated bundles;
  - authoritative Paperclip-managed `UWACTO` and `UWICTO` instructions do not
    contain merge/release/review sections;
  - live infra bundles contain the executor path;
  - routine assignment targets platform CTO dispatchers.
- Manual smoke with a synthetic no-op daily issue:
  - cursor equals GitHub upstream head;
  - platform CTO closes no-op;
  - infra is not assigned;
  - no run directory is created;
  - cursor remains unchanged.
- Verify stuck-dispatcher visibility: if platform CTO fails before creating
  artifacts, existing watchdog/stale-issue recovery surfaces the assigned issue
  to `AUCEO` or the operator path documented for Paperclip runtime failures.

## Decisions

- Use `profile: custom` for `UWACTO` and `UWICTO`; keep dispatcher behavior in
  UAudit project-layer role craft and overlays.
- Do not reuse `cx-cto.md` for platform dispatcher role sources.
- Daily no-op issues create no files and no artifacts. Paperclip comment plus
  closure is the record.
- Valid first-run/new-scope cursor initialization is routed by platform CTO and
  executed by infra. CTO supplies the exact upstream head SHA; infra writes that
  SHA as the baseline and stops.
- Routine reconciliation requires both documentation and a dry-run/live capable
  check/script backed by a repo-owned routine/scope config. Config uses agent
  names only; UUIDs resolve from existing bindings/deploy resolver.
- Documentation validity is part of acceptance; stale or contradictory docs
  block the implementation.
- Prompt-only live deploy uses `imac-agents-deploy.sh`; rollback uses previous
  SHA redeploy for that same mechanism.
- Platform infra overlays must literally remove old decision-gate branches so
  live bundles have only one daily-audit decision owner.
