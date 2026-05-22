# GIM-NN Plan: UAudit CTO dispatcher daily audit routing

## Goal

Implement the UAudit dispatcher split described in
`docs/superpowers/specs/2026-05-22-uaudit-cto-dispatcher-daily-audit-routing.md`.

Platform CTO agents (`UWACTO`, `UWICTO`) become lightweight decision/routing
agents. Platform infra agents (`UWAInfraEngineer`, `UWIInfraEngineer`) keep
runtime execution, delivery, and cursor mutation, but no longer make daily-audit
intake decisions.

## Pinned Context

- Spec branch: `feature/GIM-uaudit-cto-dispatcher-spec`
- Spec commit at plan creation: `317b2937`
- Integration branch base at spec creation: `origin/develop` `44782198`
- CX-team workspace root: `/Users/ant013/Android/Gimle-Palace`. Never remove
  this persistent workspace or its worktree.
- Pre-existing local dirt observed outside this plan scope:
  - `paperclips/fragments/shared`
  - `.serena/`
  - `1000`

## Assumptions

- Replace `GIM-NN` with the real issue number during Phase 1.1 formalization.
- `AUCEO` remains a full CTO profile in this slice; reviewing or shrinking
  `AUCEO` is a follow-up.
- UAudit deploy uses the current UAA prompt-only deploy path:
  `paperclips/scripts/imac-agents-deploy.sh`.
- Paperclip routine UUIDs and agent UUIDs are resolved through existing
  UAA bindings/deploy resolver logic. New routine config must use agent names,
  not UUID literals.
- Existing dirty files not listed in this plan are unrelated and must not be
  reverted or included.
- Do not use `git add .` in this slice. Stage only explicitly planned paths.
- This docs branch is the review gate. After approval, implementation may
  continue on this branch; alternatively, merge the docs-only branch first and
  start implementation from updated `develop`. The chosen path must be stated in
  the implementation PR body.

## Acceptance Criteria

- `UWACTO` and `UWICTO` use `profile: custom` and slim UAudit platform
  dispatcher role craft, not `paperclips/roles-codex/cx-cto.md`.
- Generated `UWACTO` and `UWICTO` bundles are each at or below 100 lines and
  4 KiB, unless the PR explicitly pins a reviewed higher ceiling caused by
  mandatory universal content.
- Generated `UWACTO` and `UWICTO` bundles do not contain merge/release/code
  review/plan-first CTO sections.
- Platform CTO dispatchers own daily audit intake: no-op, forward delta,
  valid initialization, and anomaly classification.
- Infra overlays no longer contain silent cursor bootstrap, no-op decision,
  initialization decision, rollback/divergence decision, or oversized-delta
  decision branches.
- Routine/scope config is repo-owned, uses agent names only, and contains
  branch/repo/cursor/schedule/owner/limits/subagent roster for iOS and Android.
- No-op daily issues create no run directory, no artifacts, no Telegram
  delivery, no subagent work, and no cursor mutation.
- Valid first-run/new-scope initialization is routed by platform CTO to infra;
  CTO supplies the exact upstream head SHA, and infra writes that SHA verbatim.
- Lost cursor, history rewrite/missing cursor object, stale mirror, rollback,
  malformed issue, and oversized delta all block/escalate to `AUCEO` through
  `PATCH status=blocked + assigneeAgentId=<AUCEO>`.
- Routine reconciliation has docs and a dry-run/live script backed by the
  routine/scope config.
- UAudit docs validation is automated by `paperclips/scripts/validate_uaudit_docs.py`.
- Prompt-only deploy order is deploy -> synthetic no-op smoke -> routine
  reconciliation.
- Existing PR-audit routing still works for Android, iOS, and cross-platform
  handoff cases.

## Steps

- [ ] Phase 1.1: Formalize issue and freeze scope
  - Owner: `CXCTO` or `AUCEO`
  - Affected paths:
    - This plan file
    - The linked spec file only if review requires a final wording correction
  - Details:
    - Replace `GIM-NN` in this file name/content with the real issue number.
    - Use `git mv` to rename this file from
      `2026-05-22-GIM-NN-uaudit-cto-dispatcher-daily-audit-routing.md` to
      `2026-05-22-GIM-<N>-uaudit-cto-dispatcher-daily-audit-routing.md`.
    - Confirm the implementation branch starts from current `origin/develop`.
    - Identify the existing untracked `1000` path: record whether it is user
      data, generated scratch, or accidental command output. Either clean it
      with operator approval or document it as unrelated local dirt. Never stage
      it.
    - Confirm no unrelated dirty files are in scope.
  - Check:
    - `git status --short`
    - `git status --porcelain | grep -v -e '^ M paperclips/fragments/shared' -e '^?? .serena/' -e '^?? 1000$'` returns no implementation files before coding starts.
    - `git merge-base --is-ancestor origin/develop HEAD` on the implementation branch

- [ ] Phase 1.2: Plan-first review
  - Owner: `CXCodeReviewer`
  - Depends on: Phase 1.1
  - Details:
    - Review this plan against the spec.
    - Confirm the task list covers must-fix gaps from the spec review:
      infra decision removal, AUCEO wake mechanics, UUID source-of-truth,
      bundle ceilings, docs validation, size limits, history rewrite,
      roster source, deploy order, and initialization lifecycle.
  - Check:
    - Paperclip review comment explicitly APPROVES or requests changes.

- [ ] Phase 2.1: Add UAudit routine/scope config
  - Owner: `CXPythonEngineer`
  - Depends on: Phase 1.2 approval
  - Affected paths:
    - `paperclips/projects/uaudit/daily-version-branch-routines.yaml`
    - tests under `paperclips/tests/`
  - Details:
    - Add repo-owned config for Android and iOS `version/0.49`.
    - Use agent names only, no UUID literals.
    - Include GitHub repo URL, branch, cursor path, schedule, expected CTO
      dispatcher, infra executor, required subagent roster, `max_commits: 30`,
      `max_files: 300`, `max_diff_lines: 3000`, and initialization policy.
    - Add tests that load the config and fail on UUID-looking values.
    - Add tests that every agent name in config resolves through the existing
      UAA bindings/deploy resolver. Typos such as `UWACTO_typo` must fail before
      runtime.
  - Check:
    - Targeted pytest for the new config parser/validator.

- [ ] Phase 2.2: Slim platform CTO role craft and manifest wiring
  - Owner: `CXPythonEngineer`
  - Depends on: Phase 2.1
  - Affected paths:
    - `paperclips/projects/uaudit/paperclip-agent-assembly.yaml`
    - `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`
    - `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`
    - `paperclips/projects/uaudit/overlays/codex/UWACTO.md`
    - `paperclips/projects/uaudit/overlays/codex/UWICTO.md`
  - Details:
    - Switch `UWACTO` and `UWICTO` to `profile: custom` because `minimal` still composes the universal layer and exceeds the bundle ceiling.
    - Point them at slim UAudit dispatcher role sources, not `cx-cto.md`.
    - Preserve PR-audit routing and add daily-audit intake routing.
    - Include anomaly matrix behavior and AUCEO blocked-assignment mechanics.
    - Inject AUCEO's `assigneeAgentId` into rendered dispatcher instructions at
      build time from the existing bindings/deploy resolver. The final bundle
      must contain a concrete AUCEO UUID for the PATCH action, not only the name
      `AUCEO`.
    - Keep routing text project-layer only; do not add a global dispatcher profile.
  - Check:
    - Build bundles.
    - Tests assert forbidden CTO markers are absent and required dispatcher markers are present.
    - Tests assert each platform CTO bundle stays within the pinned line/byte ceiling.

- [ ] Phase 2.3: Move daily decision gates out of infra overlays
  - Owner: `CXPythonEngineer`
  - Depends on: Phase 2.2
  - Affected paths:
    - `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
    - `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
  - Details:
    - Remove silent cursor bootstrap.
    - Remove no-op decision and marker creation.
    - Remove initialization decision.
    - Remove rollback/backward/divergence decision.
    - Remove oversized-delta policy decision.
    - Keep executor validation, artifact generation, checkout at `TO`,
      codebase-memory refresh, subagent fanout, aggregation, Telegram delivery,
      and cursor update after successful delivery.
    - For initialization handoff, require infra to write the exact SHA supplied
      by CTO without recomputing branch state.
    - Do not edit generated dist files manually in this phase. Generated dist is
      rebuilt and committed only in Phase 2.8.
  - Check:
    - Tests assert infra bundles no longer contain removed decision-gate text.
    - Tests assert infra bundles still contain delivery/cursor-after-delivery safety text.

- [ ] Phase 2.4: Add deterministic routing and anomaly tests
  - Owner: `CXPythonEngineer`
  - Depends on: Phase 2.2 and Phase 2.3
  - Affected paths:
    - tests under `paperclips/tests/`
  - Details:
    - These are deterministic text/config tests over generated dispatcher bundle
      text, infra bundle text, and routine/scope config. They are not live
      Paperclip behavioral tests.
    - Behavioural verification happens in Phase 4.1 with a synthetic no-op issue.
    - Add tests for:
      - no-op: no infra assignment, no `$RUN`, no Telegram, no cursor mutation;
      - valid initialization: CTO hands exact head SHA to infra;
      - missing cursor on known scheduled scope: blocked and assigned to `AUCEO`;
      - backward/diverged branch: blocked and assigned to `AUCEO`;
      - missing cursor object/history rewrite: blocked and assigned to `AUCEO`;
      - oversized delta: blocked using config limits;
      - forward delta: infra handoff includes exact `FROM`, `TO`, size counts,
        and subagent roster;
      - infra verifies handoff roster equals config roster;
      - Android PR routes to `UWAKotlinAuditor`;
      - iOS PR routes to `UWISwiftAuditor`;
      - cross-platform PR routes to the peer CTO.
  - Check:
    - Targeted pytest for new dispatcher/routing tests.

- [ ] Phase 2.5: Add routine reconciliation script
  - Owner: `CXPythonEngineer`
  - Depends on: Phase 2.1
  - Affected paths:
    - `paperclips/scripts/reconcile_uaudit_routines.py`
    - tests under `paperclips/tests/`
    - UAudit routine/reconcile docs
  - Details:
    - Add a dry-run/live script that reads the routine/scope config.
    - CLI contract:
      - default mode is dry-run;
      - `--apply` enables live mutation;
      - no interactive prompts, so CI and automation cannot hang;
      - `--company-id`, `--api-url`, and auth inputs follow existing Paperclip
        script conventions where possible.
    - Live auth on iMac uses the existing Paperclip auth resolution path,
      including `/Users/anton/.paperclip/auth.json` when run on that host.
      Tests must use mocks/fixtures and must not require a live token.
    - API contract:
      - read current routines through the Paperclip routines API;
      - update assignee only through explicit `--apply`;
      - missing routine is a failure by default, not an implicit create;
      - routine creation requires a future explicit `--create` mode or separate
        reviewed change.
    - Resolve agent names to UUIDs through the existing UAA bindings/deploy
      resolver; do not duplicate UUIDs in config.
    - Dry-run reports current routine assignees and expected platform CTO
      assignees.
    - Live mode updates routines only after operator approval.
  - Check:
    - Unit tests for dry-run output and UUID resolution.
    - Live mode remains opt-in and non-default.

- [ ] Phase 2.6: Add automated UAudit docs validator
  - Owner: `CXPythonEngineer`
  - Depends on: Phase 2.1
  - Affected paths:
    - `paperclips/scripts/validate_uaudit_docs.py`
    - tests under `paperclips/tests/`
    - existing validation entrypoint, preferably `paperclips/validate-codex-target.sh`
  - Details:
    - Validate internal Markdown links touched by this slice.
    - Fail on stale infra-owned daily-audit language unless marked `SUPERSEDED`.
    - Validate UAudit agent names in touched docs.
    - Validate any UUIDs in touched docs against existing bindings/deploy resolver.
    - Validate daily routine ownership docs point to platform CTO dispatchers.
    - Wire the validator into a CI-visible/repo validation path. Prefer adding
      it to `paperclips/validate-codex-target.sh` or the existing Paperclip
      validation lane. Do not rely on local-only git hooks.
  - Check:
    - `python3 paperclips/scripts/validate_uaudit_docs.py`
    - `./paperclips/validate-codex-target.sh`
    - Targeted pytest for validator fixtures.

- [ ] Phase 2.7: Update documentation and supersede stale ownership docs
  - Owner: `CXPythonEngineer` or `CXTechnicalWriter`
  - Depends on: Phase 2.2 through Phase 2.6
  - Affected paths:
    - `docs/superpowers/specs/2026-05-12-uaudit-infra-incremental-orchestrator.md`
    - `docs/superpowers/specs/2026-05-11-uaudit-report-delivery-owner.md`
    - `docs/superpowers/plans/2026-05-15-uaa-phase-F-uaudit-migration.md`
    - `docs/runbooks/uaa-live-deploy.md`
    - `paperclips/scripts/imac-agents-deploy.README.md`
    - `services/palace-mcp/README.md` if it references UAudit role ownership or deploy responsibilities
  - Details:
    - Mark stale end-to-end infra daily-audit ownership as `SUPERSEDED`.
    - Document decision/execution boundary.
    - Document prompt-only deploy, previous-good-SHA rollback, and deploy order:
      deploy -> synthetic no-op smoke -> routine reconciliation.
    - Document routine reconciliation dry-run/live usage.
    - Keep stale historical claims only when clearly marked `SUPERSEDED` with a
      pointer to the new dispatcher spec.
  - Check:
    - `python3 paperclips/scripts/validate_uaudit_docs.py`

- [ ] Phase 2.8: Build generated artifacts and update snapshot expectations
  - Owner: `CXPythonEngineer`
  - Depends on: Phase 2.2 through Phase 2.7
  - Affected paths:
    - `paperclips/dist/uaudit/codex/*.md`
    - `paperclips/dist/uaudit.resolved-assembly.json`
    - tests that snapshot UAudit profiles or output paths
  - Details:
    - Rebuild UAudit Codex bundles.
    - If `uaudit.resolved-assembly.json` does not expose effective manifest
      profile/role source, update the generator so it does.
    - Update tests that still hard-code `UWACTO`/`UWICTO` as `cto`.
    - Commit generated dist artifacts only from this rebuild phase; earlier
      source-edit phases must not hand-edit dist output.
  - Check:
    - `./paperclips/build.sh --project uaudit --target codex`
    - `python3 paperclips/scripts/validate_instructions.py --repo-root .`
    - `./paperclips/validate-codex-target.sh`
    - Targeted pytest for UAudit migration/profile tests.

- [ ] Phase 3.1: Code review
  - Owner: `CXCodeReviewer`
  - Depends on: Phase 2.8
  - Details:
    - Review prompt composition, docs, tests, and generated artifacts.
    - Confirm no unrelated files are included.
    - Confirm the decision owner is only platform CTO and executor owner is only infra.
    - Produce a compliance checklist that maps every acceptance criterion in
      this plan to file/test/command evidence.
    - Paste `gh pr checks <PR>` output.
    - Include explicit absence verification for forbidden phrases in generated
      dispatcher bundles, for example grep output showing no merge/release/PR
      approval markers.
  - Check:
    - Paperclip APPROVE comment with command evidence.

- [ ] Phase 4.1: QA and live deploy smoke
  - Owner: `CXQAEngineer` or operator with QA evidence
  - Depends on: Phase 3.1
  - Affected paths:
    - No code changes expected during QA unless docs evidence is updated.
  - Details:
    - Record previous good SHA before live prompt deploy.
    - Dry-run deploy changed UAudit agents.
    - Prompt-only deploy with:
      - pre-release: `paperclips/scripts/imac-agents-deploy.sh uaudit --from-develop`
      - post-release: `paperclips/scripts/imac-agents-deploy.sh uaudit`
    - Verify authoritative Paperclip-managed `UWACTO`/`UWICTO` instructions
      match generated bundles, using compare/hash tooling.
    - Run a synthetic no-op daily issue manually assigned to `UWACTO` or `UWICTO`.
      Use this literal body shape, replacing platform-specific fields:

      ```text
      UAudit daily version-branch delta audit
      platform: android
      branch: version/0.49
      repo: https://github.com/horizontalsystems/unstoppable-wallet-android
      cursor: /Users/Shared/UnstoppableAudit/state/android-version-audit.json
      routine_config: paperclips/projects/uaudit/daily-version-branch-routines.yaml
      expected_decision: no-op
      ```

      Before creating the issue, set or verify the cursor equals the current
      GitHub upstream `version/0.49` head so `FROM == TO` is guaranteed. For iOS,
      use the iOS repo URL and cursor path from the routine config.
    - Confirm no infra assignment, no run directory, no Telegram delivery, and
      cursor unchanged.
    - Only after smoke passes, run routine reconciliation dry-run and live mode
      if operator approval is present.
  - Check:
    - Evidence comment includes this exact field set:
      - `Deploy SHA: <sha>`
      - `Previous good SHA: <sha>`
      - `Compare hash/result: <output>`
      - `Synthetic issue: UNS-<N>`
      - `Cursor before: <sha>`
      - `Cursor after: <sha>`
      - `Infra assigned: yes/no`
      - `Run directory created: yes/no`
      - `Telegram sent: yes/no`
      - `Routine dry-run: <output/path>`
      - `Routines applied: yes/no`
      - `Rollback command if needed: <command>`
    - If smoke fails, rollback with:
      `paperclips/scripts/imac-agents-deploy.sh uaudit --target-sha <previous-good-sha>`
      and do not reconcile routines.

- [ ] Phase 4.2: Merge readiness
  - Owner: `CXCTO`
  - Depends on: Phase 4.1 PASS
  - Details:
    - Confirm plan acceptance criteria are covered.
    - Confirm CI/checks are green.
    - Confirm QA/live evidence includes prompt deploy, synthetic no-op smoke,
      and routine reconciliation evidence or explicit "not applied" reason.
    - Independently verify authoritative Paperclip-managed instructions for
      `UWACTO` and `UWICTO` match generated bundles using
      `compare_deployed_agents.py` or the approved hash-equivalent command.
      Do not rely only on QA's pasted evidence.
    - Merge per current Gimle-Palace branch-flow rules.
  - Check:
    - `gh pr checks <PR>`
    - No conflict markers.
    - PR body references this plan and includes QA evidence.

## Verification Commands

Expected implementation verification set:

```bash
./paperclips/build.sh --project uaudit --target codex
python3 paperclips/scripts/validate_instructions.py --repo-root .
./paperclips/validate-codex-target.sh
python3 paperclips/scripts/validate_uaudit_docs.py
python3 -m pytest paperclips/tests/test_handoff_strict_rules.py -v
python3 -m pytest paperclips/tests -k "uaudit and (dispatcher or routine or docs)" -v
```

Exact targeted pytest names may change during implementation, but the PR must
show the concrete commands that cover dispatcher bundle content, no-op,
initialization, anomaly handling, routine reconciliation, PR routing, and docs
validation.

## Rollback

If live prompt deploy fails before routine reconciliation:

```bash
paperclips/scripts/imac-agents-deploy.sh uaudit --target-sha <previous-good-sha>
```

If routine reconciliation was already applied and then a failure is found:

1. Revert routines to the previous assignees using the reconciliation script's
   live mode or the documented Paperclip API procedure.
2. Redeploy previous prompt SHA using the command above.
3. Post evidence to the issue with the previous-good SHA and routine rollback
   output.

## Branch and PR

- Implementation branch: `feature/GIM-NN-uaudit-cto-dispatcher-routing`
- PR target: `develop`
- PR body must reference:
  - this plan file;
  - the linked spec;
  - generated bundle size evidence;
  - docs validation evidence;
  - deploy/smoke/reconcile evidence if live deployment is performed in the PR.
