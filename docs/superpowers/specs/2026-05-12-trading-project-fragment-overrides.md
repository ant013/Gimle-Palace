# Trading Project-Layer Fragment Overrides (rev2)

## Rev2 — post-audit corrections (2026-05-12)

VoltAgent 3-subagent spec audit (arch / code-review / qa) ran 2026-05-12.
Findings folded in:

- **B3 fixed**: acceptance grep patterns redefined to match override file
  shape (NOT WORKFLOW.md table shape — the override file defines its own
  matrix table, distinct from WORKFLOW.md's columnar table).
- **B4 fixed**: build output paths corrected
  (`paperclips/dist/<role>.md` for claude, `paperclips/dist/codex/cx-<role>.md`
  for codex; no `paperclips/dist/<project>/` directory).
- **M1 fixed**: resolver-gate wording corrected — override applies when
  `project.key` is truthy AND project override file exists at the resolved
  path; cross-project safety comes from "file absent = fallback to shared",
  not from project_key equality.
- **M2 added**: golden Gimle+UAudit baseline captured pre-implementation as
  a committed artefact under `docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/`.
- **M3 strengthened**: defect-2 smoke now checks (a) `issue.assigneeAgentId`
  changed from PE to CR after PE turn; (b) PR exists on `trading-agents`
  for the feature branch; not only "comment contains X".
- **M5 added**: each override file has `<!-- derived-from: shared@<SHA> -->`
  header for drift detection.
- **m3 added**: rollback path documented (revert + redeploy).
- **m2 promoted to in-scope**: build-tool log enhancement (~5 LOC) bundled
  with this slice (per arch MINOR-1, drift detection requires it).
- **Defect-2 scope honesty**: PE silent `task_complete` is **partially**
  addressed via stronger CTO-issued routing instructions in PE-handoff
  comments. Structural fix (PE bundle composition or codex exit-protocol)
  remains a separate followup.

Audit findings **not** absorbed (rejected per operator direction "stay on
initial idea"):

- arch BLOCKER-2 (switch to templating): rejected; override duplication
  accepted as pragmatic tradeoff for "Trading working NOW".
- arch BLOCKER-1 (expand override to 9+ files): rejected; remaining 5
  fragments with literal Gimle phase IDs (`cto-no-code-ban.md`,
  `pre-work-discovery.md`, `test-design-discipline.md`, `fragment-density.md`,
  `role-prime/*.md`) **may** trigger residual CTO improvisation; mitigation
  is monitor-and-iterate, not pre-emptive override.
- arch MAJOR-5 (root cause is `role-prime/cto.md` Phase 1.2 prose):
  acknowledged but deferred — `role-prime/cto.md` is unread by Trading CTO
  per `roles/cto.md` inclusions (verified by grep — `role-prime/*` is not
  `@include`d by `roles/cto.md`).

## Ownership

Board work — implemented directly in operator session, not handed to a
paperclip company. Trading paperclip company (`09edf17a-...`) consumes the
output (its agents read the overridden fragments after deploy), but does not
implement it. Gimle paperclip company is unrelated and is not involved.

## Context

Trading paperclip company `TRD` launched 2026-05-12 with 5 agents on the
`trading-agents` repo. PR #144 (`feat(trading): bootstrap Trading paperclip
company + 5-agent assembly`) created `paperclips/projects/trading/` with
assembly YAML, project-overlay `_common.md`, and a 7-step `WORKFLOW.md`.

On TRD-3 ingestion smoke (2026-05-12 ~12 UTC) two structural defects surfaced:

1. **CTO improvises routing prose** — TRD-2 comment from CTO included the line
   `Next: CR code-review (Phase 5) after PR is opened.` That phrasing is not
   from any fragment. The shared `phase-handoff.md` hardcodes Gimle's
   `1.1 / 1.2 / 2 / 3.1 / 3.2 / 4.1 / 4.2` chain; Trading's `WORKFLOW.md`
   defines a different `1 → 2 → 3 → 4 → 5 → 6 → 7` chain with no Opus phase.
   CTO sees both in its bundle and improvises free-form prose to bridge the
   mismatch.
2. **PE silently `task_complete`s without commit / push / handoff PATCH** —
   on TRD-3, codex PE wrote `real_baseline_replay_integrity.py` and tests
   locally, posted a Russian summary comment, then ended the turn. No
   `git add`, no `git commit`, no `gh pr create`, no atomic PATCH to reassign
   to CR. The worker bundle (`cx-python-engineer.md`) only includes
   `fragments/profiles/handoff.md` (no routing matrix), so PE has no per-phase
   next-hop in its bundle.

Both defects originate from the same root: `paperclips/fragments/shared/` is a
shared sub-repo owned by other teams; its `phase-handoff.md` is Gimle-flavored.
Trading must override the project-specific parts at the project layer.

## Problem

Trading needs to override 4 shared fragments without touching the sub-repo,
without touching shared role files, and without affecting any other project's
bundle.

## Approach

Use the existing project-layer override mechanism in
`paperclips/scripts/build_project_compat.py` (function `include_fragment_path`,
lines 70–83). The resolver already checks
`paperclips/projects/<project_key>/fragments/<fragment_rel>` before falling
back to `paperclips/fragments/<fragment_rel>`. Precedent:
`paperclips/projects/uaudit/fragments/targets/codex/local/agent-roster.md`.

**No code change** in `build_project_compat.py`. **No change** to shared
fragments or role files. Only new files under
`paperclips/projects/trading/fragments/shared/fragments/`.

## File-set

### Override files (`paperclips/projects/trading/fragments/shared/fragments/`)

Each override file starts with header:

```markdown
<!-- derived-from: paperclips/fragments/shared/fragments/<name>.md @ shared-submodule-pin 285bf36 -->
<!-- on shared submodule update, manual diff + re-derive may be required -->
```

| File | Source | Edits |
|---|---|---|
| `phase-handoff.md` | copy of `paperclips/fragments/shared/fragments/phase-handoff.md` (NOT the codex variant — `roles/cto.md` claude target falls back to non-target-prefixed shared) | (a) replace 6-row routing matrix (current lines 15–22) with Trading 7-step routing rows; (b) replace `Phase 1.1 / 1.2 / 2 / 3.1 / 3.2 / 4.1 / 4.2` → `Phase 1 / 2 / 3 / 4 / 5 / 6 / 7` in checklists, QA-evidence template, section headers; (c) drop `3.2 Opus APPROVE` row + pre-close-checklist line requiring Opus evidence; (d) keep all discipline text (atomic PATCH, GET-verify, exit protocol, formal mention format) byte-identical; (e) **strengthen Phase 4 → 5 row**: explicit command list ("push branch + `gh pr create` + atomic PATCH `assignee=CR`") embedded in matrix row, so CTO's PE-routing comment template inherits it |
| `compliance-enforcement.md` | copy of shared (no codex variant exists; both targets fall back to shared) | swap phase IDs (Phase 3.1→5, Phase 4.1→6, Phase 4.2→7); keep all discipline text intact |
| `phase-review-discipline.md` | copy of `paperclips/fragments/targets/codex/shared/fragments/phase-review-discipline.md` (codex variant — workers are codex; uses `{{evidence.review_scope_drift_issue}}` placeholders which Trading `paperclip-agent-assembly.yaml` already defines) | swap Phase 3.1→5; **remove entire `## Phase 3.2 — Adversarial coverage matrix audit` section** (Trading has no Opus role); replace literal `Architect` ref (codex variant) with `CR` (Trading uses base family names per overlay `_common.md`) |
| `worktree-discipline.md` | copy of shared (no codex variant) | replace `develop` → `main` everywhere (excluding line 19 `origin/develop` if it refers to a non-Git context — review per-line); Phase 4.1 → Phase 6 |

### Build-tool enhancement (in-scope, ~5 LOC)

`paperclips/scripts/build_project_compat.py:80-84` — when project override
applies (i.e. resolver returns project path rather than fragments root),
emit a single-line `print` to stderr:

```python
print(f"  override applied: {project_shared_fragment} (was: {fragments_root / fragment_rel})",
      file=sys.stderr)
```

Drift detection mechanism: build output captures every override application;
diff against baseline reveals when override surface changed unexpectedly.

Trading roster naming: notice in `phase-handoff.md` already references
"family names resolved via `agent-roster.md`" — no edit needed there;
concrete UUIDs come from `paperclips/projects/trading/overlays/codex/_common.md`
or a future Trading-specific `agent-roster.md`.

## Acceptance criteria

### AC1 — Gimle + UAudit bundles byte-identical to pre-baseline

Baseline captured pre-implementation, committed at
`docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/`
(zip of `paperclips/dist/`, plus `git rev-parse HEAD` + `git submodule status`
record). Verification:

```
python3 paperclips/scripts/build_project_compat.py --project gimle --inventory skip
python3 paperclips/scripts/build_project_compat.py --project uaudit --inventory skip
sha256sum paperclips/dist/cto.md paperclips/dist/codex/cx-*.md \
  paperclips/dist/uaudit/codex/cx-*.md > /tmp/after.sha
diff /tmp/after.sha docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/sha256.txt
```

No diff. Confirms no other project disturbed.

### AC2 — Trading bundle contains override content

After PR #144 also lands on `develop` (or built locally from this PR's branch
merged with TRD bootstrap branch tip):

```
python3 paperclips/scripts/build_project_compat.py --project trading --inventory skip 2>&1 \
  | tee /tmp/trading-build.log
# Verify override applied (build-tool emits log per applied override):
grep -c "override applied: paperclips/projects/trading/fragments/shared/fragments/phase-handoff.md" /tmp/trading-build.log  # expect >=1 (claude CTO)
grep -c "override applied: paperclips/projects/trading/fragments/shared/fragments/compliance-enforcement.md" /tmp/trading-build.log  # expect >=1 (workers)
# Verify content:
grep -cE '^\|\s*1\s*Spec\s*\(CTO\)\s*\|\s*2\s*Spec review' paperclips/dist/cto.md       # expect >=1
grep -cE '^\|\s*6\s*Smoke\s*\(QA\)\s*\|\s*7\s*Merge' paperclips/dist/cto.md             # expect >=1
grep -cE '1\.1 Formalization|3\.2 Opus|Phase 4\.1|Phase 4\.2' paperclips/dist/cto.md   # expect 0
grep -cE 'Adversarial coverage matrix audit' paperclips/dist/codex/cx-python-engineer.md # expect 0
grep -cE '\bdevelop\b' paperclips/dist/codex/cx-python-engineer.md                      # expect 0 within worktree-discipline section
```

Exact override-table-row shape is defined in the override file itself — the
acceptance grep matches what we write, not what WORKFLOW.md uses (which has
a different 5-column table for documentation).

### AC3 — iMac smoke

After deploy (`bash paperclips/scripts/imac-agents-deploy.sh`) and Trading
agents picking up fresh AGENTS.md on next run, create a test TRD issue
(spec for the test issue in `## Smoke procedure` below). Verify:

**Defect 1 (CTO improvisation)** — CTO handoff comments do not improvise
routing prose. Concrete check:
- Get all CTO authored comments on the smoke issue.
- For each: the body MUST start with `## Phase <N> complete —` matching the
  override's handoff template, AND contain exactly one formal mention block
  `[@<NextAgent>](agent://<UUID>?i=<icon>)`.
- Body MUST NOT contain any improvised prose like `Next:`, `Then `,
  `After this, `, `Coming up:`, `The next step`.

**Defect 2 (PE silent task_complete)** — PE phase 4 must terminate with
a successful handoff to CR. Concrete check (negative-space test):
- After PE turn completes, `GET /api/issues/<test-trd-N>` must show
  `assigneeAgentId == <CR-UUID>` (not still PE).
- PR exists on `trading-agents`: `gh pr list --head feature/phase-<id>-* --json url`
  returns non-empty.
- Latest comment authored by PE contains a PR link (`https://github.com/ant013/trading-agents/pull/...`).

If defect 2 still occurs (PE still silently `task_complete`s), this slice is
considered a **defect-1-only** fix; followup slice for PE bundle composition.

## Out of scope

- Refactor of shared `phase-handoff.md` matrix into a parameterized template
  via `{{handoff_matrix}}` placeholder — rejected upstream as over-engineering.
- Stage-name rename of `Phase X.Y` literals in other shared fragments
  (`git-workflow.md`, `cto-no-code-ban.md`, `pre-work-discovery.md`,
  `test-design-discipline.md`, `fragment-density.md`) — out of scope; only the
  4 fragments that actively block Trading routing.
- PE worker bundle composition fix (`cx-python-engineer.md` includes only
  `fragments/profiles/handoff.md` without matrix) — separate slice. CTO
  routing instruction in issue body remains the workaround for PE for now.
- Cleanup of the substitution-table lie in
  `paperclips/projects/trading/overlays/{claude,codex}/_common.md`
  ("`fragments/shared/...` Not used by Trading v1") — separate small cleanup.

## Dependencies

- **PR #144** (`feature/TRD-paperclip-team-bootstrap`) is the parent slice. The
  override files have **no effect** until `paperclips/projects/trading/` is
  present on `develop`. Override files can land on a separate PR in parallel;
  both must reach `develop` before Trading agents read overridden bundles.
- Shared submodule `paperclip-shared-fragments` is pinned at `285bf36`
  (current `develop` pin). Override files are derived from that revision.

## Risks

1. **Drift** — shared fragments may evolve; Trading copies do not auto-inherit
   improvements. Mitigation (rev2): each override has a `derived-from: …@<SHA>`
   header recording the submodule pin at copy time. Submodule update on
   `develop` becomes a CR-visible signal that overrides may need re-derive.
   No CI enforcement yet — acceptable for rev2.
2. **Silent override** — fixed in rev2: build-tool logs each applied override
   to stderr (~5 LOC enhancement, in-scope).
3. **Bundle size** — corrected from rev1: CTO (claude) bundle gains Trading
   `phase-handoff.md` + `worktree-discipline.md` (replacement, ~same size).
   Worker (codex) bundles gain Trading `worktree-discipline.md` +
   `compliance-enforcement.md` + `phase-review-discipline.md`. Net delta per
   worker: ~0 (replacement of shared/codex variant with Trading variant of
   similar length). Verified by AC2 grep counts.
4. **Cross-project safety** — corrected from rev1: resolver gate is
   "project.key set AND project override file exists at resolved path".
   Gimle / UAudit / Medic are safe **because** no override files exist
   under `paperclips/projects/{gimle,uaudit,medic}/fragments/shared/...` for
   the 4 override targets. Verified by AC1 byte-equality.
5. **Residual Gimle phase IDs in non-overridden fragments** (audit
   arch-BLOCKER-1): 5 shared fragments (`cto-no-code-ban.md`,
   `pre-work-discovery.md`, `test-design-discipline.md`, `fragment-density.md`,
   `role-prime/*.md`) contain literal Gimle `Phase X.Y` strings and flow
   into worker bundles. CTO (claude) does NOT include `role-prime/*` (per
   `roles/cto.md` grep), so the high-risk strings reach workers only. Workers'
   primary directive is via `compliance-enforcement.md` + `worktree-discipline.md`
   (both overridden); residual strings in other fragments are reference-only.
   Mitigation: monitor smoke output; iterate to expand override if PE still
   improvises.
6. **Defect 2 partial fix** — PE silent `task_complete` is structurally
   caused by codex-model exit pattern + PE bundle not including a routing
   matrix. This slice addresses it via *behavioral nudge* (stronger
   command-list in CTO's PE-handoff comment, embedded in Trading
   `phase-handoff.md` row "Phase 4 → 5"). May or may not be sufficient.
   AC3 explicitly tests for it; failure triggers followup slice for PE
   bundle composition.

## Deploy

After merge to `develop` (and PR #144 also on `develop`):

1. SSH iMac (`ssh imac-ssh.ant013.work`).
2. Inspect `paperclips/scripts/imac-agents-deploy.sh` — if it hardcodes Gimle
   company ID only (per audit qa-M3), patch deploy step to also re-render
   `Trading` company's 5 agent bundles. If `--company` flag exists, run
   twice; otherwise extend the script as part of this slice (added to plan).
3. Run `bash paperclips/scripts/imac-agents-deploy.sh` for both companies.
4. Trading agents read fresh AGENTS.md on next run.

(`palace-mcp` Docker rebuild NOT required — pure agent-bundle update.)

### Rollback

If overrides break a Trading agent run (malformed markdown / missing
placeholder / unexpected behavior):

1. Local: `git revert <merge-sha> && git push origin develop`.
2. iMac: re-run `bash paperclips/scripts/imac-agents-deploy.sh` to redeploy
   pre-override bundles.
3. Next agent run picks up reverted bundles. No state to migrate.

If the failure is content-only (e.g., a typo in matrix row), prefer a
forward-fix PR over revert.

## Verification commands

```bash
# Local — before merge
python3 paperclips/scripts/build_project_compat.py --project gimle --inventory skip
# capture baseline; diff after applying override files
python3 paperclips/scripts/build_project_compat.py --project trading --inventory skip
grep -c '| 1 Spec (CTO)' paperclips/dist/trading/cx-cto.md   # expect >=1
grep -c '3.2 Opus' paperclips/dist/trading/cx-cto.md          # expect 0
grep -c '| develop ' paperclips/dist/trading/cx-cto.md        # expect 0

# iMac — after merge + redeploy
ssh imac-ssh.ant013.work
bash paperclips/scripts/imac-agents-deploy.sh
# Create test TRD issue → audit CTO+PE comments
```

## Open questions — resolutions (rev2)

1. **PR strategy** — RESOLVED: separate PR from PR #144. Different concern,
   parallel landing, easier review. Overrides land on develop independently;
   activate when both are merged. (PR #144 has merge conflicts with develop
   per `gh pr view 144` — needs rebase before merge, separate operator task.)
2. **Log enhancement** — RESOLVED: in-scope, 5 LOC in
   `paperclips/scripts/build_project_compat.py` resolver. Required for drift
   detection (Risk 1) and AC2 verification.
3. **Trading agent reboot** — RESOLVED: no manual poke required; paperclip
   reads AGENTS.md fresh per run (per `reference_paperclip_imac_runtime`).
   However: AC3 smoke must create a fresh TRD issue (not retry TRD-3) so
   the agent's NEXT run picks up the bundle.
4. **Deploy script scope** — NEW: `imac-agents-deploy.sh` may hardcode Gimle
   company ID. Plan task verifies + patches if needed.
