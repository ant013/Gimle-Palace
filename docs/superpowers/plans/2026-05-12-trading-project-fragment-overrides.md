# Plan — Trading Project-Layer Fragment Overrides

**Spec**: `docs/superpowers/specs/2026-05-12-trading-project-fragment-overrides.md` (rev2).
**Branch**: `feature/GIM-NN-project-override-resolver` (cut from `origin/develop`).
**Ownership**: Board (operator session); no paperclip team handoff. Direct PR.
**Target**: `origin/develop`.
**Squash-merge** on CR APPROVE + AC1 baseline-diff green + AC2 grep green + AC3 deferred to post-merge smoke.

## Phase 0 — Prereqs (Board)

### 0.1 Clean working tree

- `git status` shows currently:
  - `M paperclips/fragments/shared` (submodule pointer drift, unrelated to this slice; **do NOT commit**)
  - `?? .claude/scheduled_tasks.lock`, `?? services/watchdog/.coverage` (runtime artefacts; ignore)
- Verify branch tip is `origin/develop` (`git log --oneline -1` should match `2baa4b5`).
- Action: keep working tree as-is; ensure no `git add` of the submodule
  pointer change. Selective `git add` of only this slice's files.

### 0.2 Verify resolver mechanism with a smoke test

Confirm `include_fragment_path` actually fires on project override before
writing files. Create a throwaway test:

```bash
mkdir -p paperclips/projects/trading/fragments/shared/fragments
echo "OVERRIDE PROBE" > paperclips/projects/trading/fragments/shared/fragments/heartbeat-discipline.md
python3 paperclips/scripts/build_project_compat.py --project trading --inventory skip 2>&1 | head -20
grep -c "OVERRIDE PROBE" paperclips/dist/cto.md  # if Trading build context is fed; otherwise verify on whatever agent claude target builds
# Then: remove probe
rm paperclips/projects/trading/fragments/shared/fragments/heartbeat-discipline.md
```

**Gotcha**: Trading project does not exist on develop (only on
`feature/TRD-paperclip-team-bootstrap`). The probe may need to run from a
worktree built off `origin/feature/TRD-paperclip-team-bootstrap` merged
with this slice's branch. If unfeasible, exercise the override on UAudit
instead (UAudit already uses the resolver — `paperclips/projects/uaudit/fragments/targets/codex/local/agent-roster.md`).

Acceptance for 0.2: probe content appears in rendered bundle, OR
documented why probe was infeasible.

### 0.3 Capture baseline

```bash
mkdir -p docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides
python3 paperclips/scripts/build_project_compat.py --project gimle --inventory skip 2>&1 \
  | tee docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/gimle-build.log
python3 paperclips/scripts/build_project_compat.py --project uaudit --inventory skip 2>&1 \
  | tee docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/uaudit-build.log
( cd paperclips/dist && find . -name '*.md' -print0 | sort -z | xargs -0 sha256sum ) \
  > docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/dist-sha256.txt
git rev-parse HEAD > docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/HEAD.txt
git submodule status paperclips/fragments/shared \
  > docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/submodule.txt
```

Commit baseline as Phase 0.3 atomic commit:
`baseline(trading-overrides): capture pre-implementation Gimle + UAudit dist sha256`

## Phase 1 — Build-tool log enhancement (5 LOC)

### 1.1 Test-first

Add unit test at `paperclips/scripts/tests/test_build_project_compat_override_log.py`
(or extend existing test if present):

```python
def test_project_override_emits_log(tmp_path, capsys):
    """When a project override file exists, build emits 'override applied: …' to stderr."""
    # Set up fake repo with project override structure
    # ...
    capsys.readouterr()
    # Run include_fragment_path on a fragment that has a project override
    # ...
    captured = capsys.readouterr()
    assert "override applied:" in captured.err
    assert "projects/<projkey>/fragments/" in captured.err
```

Run: `uv run pytest paperclips/scripts/tests/test_build_project_compat_override_log.py -q`.
Expect RED (no implementation yet).

### 1.2 Implementation

`paperclips/scripts/build_project_compat.py:80-84`:

```python
project_shared_fragment = project_fragments_root / fragment_rel
if project_shared_fragment.is_file():
    print(
        f"  override applied: {project_shared_fragment.relative_to(repo_root)} "
        f"(was: paperclips/fragments/{fragment_rel})",
        file=sys.stderr,
    )
    return project_shared_fragment
```

Same shape for the `targets/<target>/...` branch above. Total: 2 × ~4-line
block.

Run test: GREEN.

### 1.3 Atomic commit

`feat(build): log project-layer fragment overrides to stderr`

## Phase 2 — Override files (4 files)

### 2.1 `phase-handoff.md` override

Source: `paperclips/fragments/shared/fragments/phase-handoff.md` (114 lines,
claude/default — NOT the codex variant; CTO target=claude).

Path: `paperclips/projects/trading/fragments/shared/fragments/phase-handoff.md`.

Header:

```markdown
<!-- derived-from: paperclips/fragments/shared/fragments/phase-handoff.md @ shared-submodule 285bf36 -->
<!-- on shared advance, manually diff and re-derive -->
```

Edits to copied content:

| Where | Edit |
|---|---|
| Line 5–6 (naming notice) | Mention `TRDCodeReviewer / TRDPythonEngineer / TRDQAEngineer` are not used; Trading uses base family names `CR / PE / QA` per `paperclips/projects/trading/overlays/_common.md`. Adjust example list. |
| Lines 15–22 (6-row matrix table) | Replace with Trading 7-step matrix, exactly: <br>`| Phase done | Next | Required handoff |`<br>`|---|---|---|`<br>`| 1 Spec (CTO) | 2 Spec review (CR) | push spec branch + assignee=CR + formal mention |`<br>`| 2 Spec review (CR) | 3 Plan (CTO) | comment with severity tally + assignee=CTO + formal mention |`<br>`| 3 Plan (CTO) | 4 Impl (PE) | comment plan-ready + assignee=PE + formal mention |`<br>`| 4 Impl (PE) | 5 Code review (CR) | **MUST run all four**: `git push origin <branch>` + `gh pr create --base main` + atomic PATCH `status + assigneeAgentId=<CR-UUID> + comment="impl ready, PR #N"` + formal mention `[@CodeReviewer](agent://<CR-UUID>?i=eye)` |`<br>`| 5 Code review (CR) | 6 Smoke (QA) | paste `uv run ruff/mypy/pytest/coverage` output + assignee=QA + formal mention |`<br>`| 6 Smoke (QA) | 7 Merge (CTO) | paste smoke evidence (must contain command output, not just PASS) + assignee=CTO + formal mention |` |
| Line 24 "Sub-issues for Phase 1.1" | Delete (Trading does not split formalize) |
| Line 31 "Phase 4.1 evidence comment authored by QAEngineer" | Replace 4.1 → 6 |
| Lines 65–73 pre-close checklist | Phase 4.2 → 7; Phase 4.1 → 6; drop "Phase 3.2 Opus APPROVE present" |
| Lines 80–95 QA-evidence template | `## Phase 4.1 — QA PASS ✅` → `## Phase 6 — QA PASS ✅`; `Phase 4.2 squash-merge` → `Phase 7 squash-merge` |
| Line 101 release-reset workaround | Keep verbatim (project-agnostic mechanism) |
| Line 114 GIM-126/GIM-195 precedent | Keep verbatim; these are evidence references (no Trading equivalents yet) |

### 2.2 `compliance-enforcement.md` override

Source: `paperclips/fragments/shared/fragments/compliance-enforcement.md`
(102 lines, no codex variant).

Path: `paperclips/projects/trading/fragments/shared/fragments/compliance-enforcement.md`.

Header: same shape as 2.1.

Edits:

| Where | Edit |
|---|---|
| Line 14 "CR Phase 3.1 re-run → REQUEST CHANGES" | 3.1 → 5 |
| Line 77 "CR Phase 3.1: new/modified `@mcp.tool`" | 3.1 → 5. Also: `@mcp.tool` is Gimle/palace-mcp-specific; Trading has no MCP tools. Decision: keep section verbatim — it does no harm if absent (workers won't see new MCP tools to flag), AND it documents the principle (test wire-contracts). |
| Line 79 `## Phase 4.2 Merge` | `## Phase 7 Merge` |
| Line 81 "Phase 4.1 PASS" | 4.1 → 6 |

### 2.3 `phase-review-discipline.md` override

Source: **`paperclips/fragments/targets/codex/shared/fragments/phase-review-discipline.md`**
(30 lines, codex variant — workers are codex). Note `{{evidence.X}}`
placeholders; Trading `paperclip-agent-assembly.yaml` already defines
`evidence.review_scope_drift_issue` etc.

Path: `paperclips/projects/trading/fragments/shared/fragments/phase-review-discipline.md`.

Header: same shape.

Edits:

| Where | Edit |
|---|---|
| Line 3 `## Phase 3.1 — Plan vs Implementation file-structure check` | `## Phase 5 — Plan vs Implementation file-structure check` |
| Line 16 `## Phase 3.2 — Adversarial coverage matrix audit` and entire section through line 30 | **DELETE entire section** — Trading has no Opus / Architect role |
| Line 18 (if remains in retained body) `Architect Phase 3.2 must include` | Already deleted with section |

### 2.4 `worktree-discipline.md` override

Source: `paperclips/fragments/shared/fragments/worktree-discipline.md`
(36 lines, no codex variant).

Path: `paperclips/projects/trading/fragments/shared/fragments/worktree-discipline.md`.

Header: same shape.

Edits:

| Where | Edit |
|---|---|
| All `develop` references | Replace with `main` — but **review per-line**: if a line says `origin/develop` as a Git remote ref (e.g., "`git fetch origin develop`"), replace with `origin/main`. If a line uses "develop" as the integration-branch concept (e.g., "after merging to develop"), replace with "main". |
| Line 28 `## QA: restore checkout to develop after Phase 4.1` | `## QA: restore checkout to main after Phase 6` |
| Any other `Phase X.Y` literal | 4.1 → 6 (only one occurrence expected based on grep) |

### 2.5 Build verification

```bash
# Trading project root is on PR #144 branch, not develop. Verify locally:
git merge --no-commit origin/feature/TRD-paperclip-team-bootstrap
# Build trading
python3 paperclips/scripts/build_project_compat.py --project trading --inventory skip 2>&1 \
  | tee /tmp/trading-build.log
# Expect 4 "override applied" lines
grep -c "override applied:" /tmp/trading-build.log  # expect >=4 (one per override × usage)
# AC2 grep checks (per spec)
# ... (paste all greps from spec AC2 here)
git merge --abort  # don't commit the temp merge
```

If verification passes, atomic commit:
`feat(trading): project-layer fragment overrides for routing + main branch`

If any check fails, fix override file then re-run.

## Phase 3 — Push + PR

### 3.1 Push

```bash
git push -u origin feature/GIM-NN-project-override-resolver
```

### 3.2 Open PR

```
gh pr create --base develop --title "feat(trading): project-layer fragment overrides for phase chain + main branch" \
  --body "$(cat <<'EOF'
## Summary

Trading paperclip team uses a 7-step phase chain (1→2→3→4→5→6→7) and `main`
as integration branch, distinct from Gimle's 7-phase chain (1.1/1.2/2/3.1/3.2/4.1/4.2)
and `develop`. Currently the Trading CTO bundle inherits Gimle-flavored
`phase-handoff.md` from the shared submodule, causing CTO to improvise
routing prose (observed on TRD-2 2026-05-12).

This slice adds 4 project-layer override fragments under
`paperclips/projects/trading/fragments/shared/fragments/` — no submodule
edit, no shared fragment edit, no role-file edit. Uses the resolver
mechanism already present in `build_project_compat.py:62-88` (UAudit
precedent).

Plus a 5-LOC build-tool enhancement to log every applied override (drift
detection).

**Defect 2 (PE silent `task_complete`)** is partially addressed via
strengthened command-list in the Trading `phase-handoff.md` matrix row
"Phase 4 → 5". Structural fix is a separate followup.

## Spec + plan

- spec: `docs/superpowers/specs/2026-05-12-trading-project-fragment-overrides.md` (rev2)
- plan: `docs/superpowers/plans/2026-05-12-trading-project-fragment-overrides.md`

## Acceptance

AC1 (Gimle + UAudit byte-identical): see baseline at
`docs/superpowers/plans/baselines/2026-05-12-pre-trading-overrides/`.
AC2 (Trading bundle contains override content): commands in spec.
AC3 (iMac smoke): post-merge, requires PR #144 also on develop.

## Dependencies

- PR #144 (`feature/TRD-paperclip-team-bootstrap`) — has merge conflicts;
  separate operator task. This PR's overrides activate when both this AND
  #144 are on develop.
- Shared submodule pinned at `285bf36` (develop pin); override files derived
  from that revision and carry a `<!-- derived-from -->` header.

## QA Evidence

(post-merge — TBD)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### 3.3 CR review (Board does code review on own PR? — needs decision)

Two options for self-review:
- (a) Board approves own PR (per `feedback_anti_rubber_stamp` — full
  checklist + evidence in approve comment). Acceptable for Board work but
  doubles as self-review.
- (b) Tag Daisy (operator) for review.

Default: (a) — Board posts full APPROVE comment with AC1+AC2 evidence.
Operator may override via Daisy review request.

### 3.4 Merge

After CI green + APPROVE:

```bash
gh pr merge --squash --delete-branch
```

## Phase 4 — Post-merge deploy

### 4.1 Verify deploy script handles Trading company

```bash
ssh imac-ssh.ant013.work 'grep -E "company.*id|trading" /Users/Shared/Ios/Gimle-Palace/paperclips/scripts/imac-agents-deploy.sh | head -20'
```

If Trading company (`09edf17a-...`) is NOT referenced, patch deploy script
in a followup tiny PR before running. Plan task only — actual patch is a
separate slice.

### 4.2 Run deploy

```bash
ssh imac-ssh.ant013.work
cd /Users/Shared/Ios/Gimle-Palace
bash paperclips/scripts/imac-agents-deploy.sh
```

Verify rendered Trading bundles include override content:
```bash
grep -c 'override applied' /Users/anton/.paperclip/.../agents/4289e2d6-.../instructions/AGENTS.md \
  || ls -la /Users/anton/.paperclip/.../agents/4289e2d6-.../instructions/AGENTS.md
```

### 4.3 Smoke test

```bash
# Create test issue via Board API
TOKEN=pcp_board_3d52ef80...
TRD=09edf17a-31d5-46cb-9812-6f07623b1c45
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "http://localhost:3100/api/companies/$TRD/issues" \
  -d '{
    "title": "smoke: phase-handoff override v1",
    "description": "Trivial smoke. Implement: add a single comment to docs/SMOKE.md saying \"override active\". Then close.\n\n## Routing\n\nPhase 1 → 7 per ROADMAP.md. After impl, push + open PR + atomic PATCH assignee=CR.",
    "priority": "low",
    "assigneeAgentId": "4289e2d6-990b-4c53-b879-2a1dc90fe72b"
  }'
```

Watch CTO + PE turn outputs. Verify per AC3:
- CTO comments contain `## Phase N complete — …` template, formal mention,
  no `Next:` / `Then` / `After this` improvisation prose.
- After PE turn: `GET /api/issues/<id>` shows `assigneeAgentId == <CR-UUID>`.
- PR exists on `trading-agents` for the smoke branch.
- PE comment contains PR link.

If pass: close smoke issue + close this PR's followup task list.
If defect-1 still occurs: open issue "expand override to role-prime/*.md".
If defect-2 still occurs: open issue "PE bundle composition: add phase-handoff.md include".

## Phase 5 — Documentation hygiene

If smoke passes:

- Update `paperclips/projects/trading/overlays/{claude,codex}/_common.md` to
  remove the substitution-table-lie line "`paperclips/fragments/shared/...`
  Gimle submodule | Not used by Trading v1" — submodule IS used, with
  project overrides. **(Tiny followup PR; not in this slice.)**

## Out-of-scope (explicit deferrals)

- Expand override to 5 more shared fragments (`cto-no-code-ban.md`,
  `pre-work-discovery.md`, `test-design-discipline.md`, `fragment-density.md`,
  `role-prime/*.md`) — if smoke shows residual improvisation, do it then.
- PE bundle composition fix (add `phase-handoff.md` to
  `cx-python-engineer.md` `@include` list) — cross-team change affecting
  UAudit/Medic CX agents; separate decision.
- Templating refactor (`{{handoff_matrix}}` placeholder + per-project
  YAML chain config) — rejected per operator direction, may revisit if
  ≥3 paperclip teams join.
- `imac-agents-deploy.sh` Trading-company patch — separate tiny PR after
  4.1 confirms it's needed.

## Time estimate

- Phase 0: 15 min (probe + baseline capture)
- Phase 1: 20 min (test + impl + commit)
- Phase 2: 60-90 min (4 override files; careful per-line editing)
- Phase 3: 30 min (push, PR, self-review with evidence)
- Phase 4: 30 min (deploy + smoke creation)
- Phase 5 (followups): tracked but out of this slice

**Total active**: ~2.5h Board work. Plus AC3 smoke run time (~30 min for
agents to cycle through).

## Open questions for re-review before Phase 2 start

1. Probe smoke test in 0.2 — UAudit-based or fail-and-document? Operator
   call if Trading-build infeasible without TRD-bootstrap branch merge.
2. Self-review at 3.3 — Board APPROVE on own PR acceptable, or get Daisy
   review?
