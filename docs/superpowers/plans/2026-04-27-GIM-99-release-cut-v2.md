---
slug: GIM-99-release-cut-v2
status: plan-ready
branch: feature/GIM-99-release-cut-v2
paperclip_issue: GIM-99
spec: docs/superpowers/specs/2026-04-27-GIM-99-release-cut-v2-design.md
date: 2026-04-27
---

# GIM-99 Implementation Plan — release-cut-v2

PR-based develop-to-main with auto-merge + annotated tag.

## Summary

Replace broken `RELEASE_CUT_TOKEN`-based direct-push workflow with PR + auto-merge (rebase) + tag pattern using only `GITHUB_TOKEN`. Single workflow file rewrite + CLAUDE.md update + cleanup of stale secret references.

## Tasks

### T1 — Rewrite `.github/workflows/release-cut.yml`

**Owner:** PythonEngineer
**Deps:** none
**Affected files:** `.github/workflows/release-cut.yml`

**Description:**
Replace the entire workflow file with the new PR + auto-merge + tag pattern per spec §Architecture reference YAML. Key invariants:
- Only `GITHUB_TOKEN` — no PAT, no `RELEASE_CUT_TOKEN`
- Both triggers: `workflow_dispatch` + `pull_request: closed` on `develop` with `release-cut` label
- Permissions: `contents: write` + `pull-requests: write`
- Steps: resolve revisions → noop check → build commit list → open PR → auto-merge rebase → wait-for-merge poll (60s) → tag main tip → step summary

**Acceptance:**
- [ ] `yamllint .github/workflows/release-cut.yml` passes
- [ ] `shellcheck` on extracted run blocks passes (no SC-level errors)
- [ ] Both triggers present with correct `if:` condition
- [ ] `permissions` block declares exactly `contents: write` + `pull-requests: write`
- [ ] No reference to `RELEASE_CUT_TOKEN` anywhere in the file
- [ ] Noop path exits cleanly with step summary
- [ ] Tag format: `release-<YYYY-MM-DD>-<sha[:7]>`

### T2 — Clean up stale `RELEASE_CUT_TOKEN` references

**Owner:** PythonEngineer
**Deps:** T1
**Affected files:** repo-wide grep; likely `.github/` only

**Description:**
Search entire repo for any remaining references to `RELEASE_CUT_TOKEN`:
```bash
grep -r 'RELEASE_CUT_TOKEN' . --include='*.yml' --include='*.yaml' --include='*.json' --include='*.md'
```
Remove or update all hits. Check `.github/branch-protection/` JSONs for stale secret references too.

**Acceptance:**
- [ ] `grep -r 'RELEASE_CUT_TOKEN' .` returns zero results (excluding this plan and spec, which are historical docs)

### T3 — Update CLAUDE.md release-cut paragraph

**Owner:** PythonEngineer
**Deps:** T1
**Affected files:** `CLAUDE.md`

**Description:**
Replace the release-cut paragraph in CLAUDE.md per spec §CLAUDE.md update diff:
- Old: references `RELEASE_CUT_TOKEN`, "fast-forwards main using token"
- New: describes PR + auto-merge rebase + tag pattern, `GITHUB_TOKEN` only

**Acceptance:**
- [ ] CLAUDE.md release-cut paragraph matches spec diff
- [ ] No mention of `RELEASE_CUT_TOKEN` in CLAUDE.md
- [ ] Both triggers described (label + dispatch)
- [ ] Tag format mentioned

### T4 — Lint workflow (pre-commit quality gate)

**Owner:** PythonEngineer
**Deps:** T1
**Affected files:** none (validation only)

**Description:**
Run static analysis on the new workflow:
1. `yamllint .github/workflows/release-cut.yml`
2. Extract each `run:` block → `shellcheck -s bash <block>`
3. Verify `if:` conditions parse correctly (no YAML syntax errors in expressions)

**Acceptance:**
- [ ] yamllint clean (no errors; warnings acceptable for long lines)
- [ ] shellcheck clean on all run blocks
- [ ] Output pasted in commit message or PR body

### T5 — CR Phase 3.1 Mechanical review

**Owner:** CodeReviewer (bd2d7e20-7ed8-474c-91fc-353d610f4c52)
**Deps:** T4 (all PE work complete + pushed)
**Affected files:** review only

**Description:**
Standard mechanical review per `compliance-enforcement.md`:
1. `git log origin/develop..HEAD --name-only` — scope audit (only expected files changed)
2. yamllint + shellcheck output pasted (PE provides in handoff)
3. Diff review: no `RELEASE_CUT_TOKEN` anywhere, permissions correct, tag format correct
4. Anti-rubber-stamp: full checklist, no "LGTM" alone

**Acceptance:**
- [ ] APPROVE comment with pasted lint output and scope audit
- [ ] `gh pr review --approve` on GitHub PR

### T6 — Opus Phase 3.2 Adversarial review

**Owner:** OpusArchitectReviewer
**Deps:** T5
**Affected files:** review only

**Description:**
Security and behavioral adversarial review:
- **Token leakage:** Can `GITHUB_TOKEN` be exfiltrated via PR body content? (commit messages are repo-internal, so no — but verify no echo of secrets)
- **Shell injection in PR body:** Commit messages with shell metacharacters in `git log` output → are they safely quoted in the YAML heredoc?
- **Race: merge + tag:** What if main gets a commit between merge and tag step? (Should not happen — main accepts only this workflow)
- **Race: auto-merge silently disabled:** What if repo settings disable auto-merge? `gh pr merge --auto` returns error — is it caught?
- **Tag collision:** Same-day second cut → SHA suffix prevents collision
- **Spec drift:** Every plan task accounted for in commits

**Acceptance:**
- [ ] APPROVE or findings list requiring rev2

### T7 — QA Phase 4.1 Live smoke

**Owner:** QAEngineer
**Deps:** T6
**Affected files:** evidence only

**Description:**
Two-part QA:

**Part A (pre-merge, Phase 4.1):**
1. `yamllint .github/workflows/release-cut.yml` — clean
2. shellcheck on extracted run blocks — clean
3. `grep -r 'RELEASE_CUT_TOKEN' .` — zero results
4. CLAUDE.md paragraph matches spec

**Part B (post-merge, bootstrap — appended to this issue after merge):**
1. Operator runs `gh workflow run release-cut.yml -f reason="GIM-99 bootstrap"`
2. Verify: PR opened, auto-merged, tag pushed, main == develop
3. Evidence: workflow run URL + tag name + `git log --oneline main -3`

**Acceptance:**
- [ ] Part A evidence comment posted (pre-merge)
- [ ] Part B evidence comment posted (post-merge, may be delayed)

### T8 — Phase 4.2 Merge

**Owner:** CTO (7fb0fdbb-e17f-4487-a4da-16993a907bec)
**Deps:** T1-T7 (CR APPROVE + Opus APPROVE + QA Part A evidence)
**Affected files:** none (merge operation)

**Description:**
CTO-only merge per GIM-94 D1:
1. Verify CI green on feature branch
2. Verify CR + Opus APPROVE present
3. Verify QA Part A evidence present
4. `gh pr merge --squash` into develop
5. Post-merge: remind operator to run bootstrap test (T7 Part B)

**Acceptance:**
- [ ] Squash-merged to develop
- [ ] CI green on merge commit
- [ ] Operator notified re bootstrap dispatch

## Dependency graph

```
T1 (workflow rewrite)
├── T2 (cleanup RELEASE_CUT_TOKEN refs)
├── T3 (CLAUDE.md update)
└── T4 (lint)
    └── T5 (CR 3.1)
        └── T6 (Opus 3.2)
            └── T7 (QA 4.1)
                └── T8 (merge — CTO)
```

T2 and T3 can run in parallel after T1. T4 depends on T1. T5+ is sequential review chain.

## Risk assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Auto-merge disabled at repo level | Low | `gh pr merge --auto` will error; PE adds explicit error check in workflow |
| Shell metacharacters in commit messages break PR body | Low | YAML heredoc + `git log --oneline` limits injection surface |
| Post-merge bootstrap fails | Medium | Revert PR ready; workflow is mostly declarative |
| main gets out-of-band commit | Very low | Branch protection + no human push policy |
