---
slug: GIM-99-release-cut-v2
status: rev1 (operator-approved approach A — PR + auto-merge rebase, with tagging)
branch: feature/GIM-99-release-cut-v2
paperclip_issue: GIM-99
predecessor: f8ccb97 (develop tip after GIM-98 merge)
date: 2026-04-27
parent_initiative: ops-quality (release flow)
related: GIM-57 (broken release-cut.yml landed there), GIM-94 (Phase 4.2 CTO-only rule), GIM-98 (last develop merge)
---

# GIM-99 — release-cut-v2 — PR-based develop→main with auto-merge + tag

## Goal

Replace the broken `RELEASE_CUT_TOKEN`-based direct push in `.github/workflows/release-cut.yml` with a **PR + auto-merge (rebase) + annotated tag** pattern that uses only the auto-injected `GITHUB_TOKEN`. After this slice, every triggered cut produces a visible PR, fast-forwards `main` to `develop`'s tip, tags the new commit, and leaves an audit trail.

**Use case:** N+2 Cat 1 closed (GIM-95 → GIM-98); `main` is **10 commits behind develop**. There is no working path to update `main` short of operator manual push. This slice fixes that.

## Sequence

Standalone ops-quality slice. Not part of N+2 category sequencing. Carried over as a followup from GIM-57 closure (per `project_backlog.md`).

## Hard dependencies

- All N+2 Cat 1 slices merged to develop ✅ (GIM-95 → GIM-98)
- No code dependencies — workflow file change only

## Non-goals

- **Decommission `main`** — operator chose to keep `main` as stable release reference (option B in brainstorm rejected)
- **Bypass-actor branch protection** — personal-repo `restrictions.apps` limitation (option C rejected)
- **Multi-repo release coordination** — out of scope
- **Changelog generation** — could be a separate slice if needed; for v2 we just list commits in PR body
- **Pre-release validation** (e.g., re-running CI on the cut PR) — main has no required checks; auto-merge fires immediately
- **Rollback workflow** — separate slice if needed; for v2, manual `git reset` is acceptable for personal repo

## Current state of brokenness

Per investigation 2026-04-27:

```yaml
# .github/workflows/release-cut.yml (current, broken)
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
    token: ${{ secrets.RELEASE_CUT_TOKEN }}
- name: Fast-forward main to develop
  run: |
    git push origin main          # FAILS — RELEASE_CUT_TOKEN unset
```

Failure mode:
- `secrets.RELEASE_CUT_TOKEN` is empty → `git push origin main` runs with no auth → fails
- Even if token existed, `enforce_admins: true` on main + `GITHUB_TOKEN`-as-bot identity may still reject direct push to protected branch
- Last 5 workflow runs all "skipped" (correct — `release-cut` label was never applied to any merged PR)

Live `main` branch protection state (verified 2026-04-27):
- `enforce_admins: true`
- `required_linear_history: true`
- No required status checks, no required reviews, no force-push, no deletions

## Architecture

### Workflow design (rev2)

**Triggers — both kept:**
1. `workflow_dispatch` — manual operator trigger; default `reason="manual dispatch"`
2. `pull_request: closed` to `develop` with label `release-cut` — automation when operator wants a release cut after specific merge

**Steps (sequential):**
1. **Resolve revisions** — fetch main + develop, compute SHAs, exit `noop` if equal
2. **Open PR** — `gh pr create --base main --head develop --title "release: <YYYY-MM-DD>" --body <commit list since main tip>`
3. **Enable auto-merge** — `gh pr merge --auto --rebase <PR>` — merges immediately since main has no required checks
4. **Wait for merge confirmation** — poll `gh pr view --json state,mergedAt` up to 60s
5. **Tag** — `git tag -a release-<YYYY-MM-DD>-<sha[:7]> -m "Auto-cut from develop@<sha[:7]>"` + push tag
6. **Step summary** — log before/after SHAs, PR URL, tag name to `$GITHUB_STEP_SUMMARY`

### Permissions

```yaml
permissions:
  contents: write       # for tag push
  pull-requests: write  # for PR create + auto-merge
```

`GITHUB_TOKEN` auto-provided by Actions; **no `secrets.RELEASE_CUT_TOKEN` needed**. The reference + secret are deleted by this slice.

### Tagging strategy

- Format: `release-<YYYY-MM-DD>-<short-sha>` (e.g., `release-2026-04-27-a1b2c3d`)
- **Annotated tag** (`-a` flag) — message records auto-cut origin
- Pushed to `origin` immediately after merge
- One tag per release-cut event (collisions on same-day cut handled by SHA suffix)

### Reference YAML (for PE — not normative; PE adapts to repo conventions)

```yaml
name: release-cut
on:
  workflow_dispatch:
    inputs:
      reason:
        description: "Reason for release cut"
        required: false
        default: "manual dispatch"
  pull_request:
    types: [closed]
    branches: [develop]

jobs:
  cut:
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event.pull_request.merged == true &&
       contains(github.event.pull_request.labels.*.name, 'release-cut'))
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Compute revisions
        id: rev
        run: |
          git fetch origin develop main --tags
          DEVELOP_SHA=$(git rev-parse origin/develop)
          MAIN_SHA=$(git rev-parse origin/main)
          echo "develop=$DEVELOP_SHA" >> "$GITHUB_OUTPUT"
          echo "main=$MAIN_SHA" >> "$GITHUB_OUTPUT"
          if [[ "$DEVELOP_SHA" == "$MAIN_SHA" ]]; then
            echo "noop=true" >> "$GITHUB_OUTPUT"
          else
            echo "noop=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Exit if noop
        if: steps.rev.outputs.noop == 'true'
        run: |
          echo "main already at develop tip — nothing to cut" | tee -a "$GITHUB_STEP_SUMMARY"

      - name: Build commit list since main
        if: steps.rev.outputs.noop == 'false'
        id: commits
        run: |
          {
            echo 'body<<EOF'
            echo "## Release cut: ${{ steps.rev.outputs.develop }}"
            echo ""
            echo "Fast-forwards main to develop tip."
            echo ""
            echo "### Commits"
            git log --oneline ${{ steps.rev.outputs.main }}..${{ steps.rev.outputs.develop }}
            echo "EOF"
          } >> "$GITHUB_OUTPUT"

      - name: Open release PR + enable auto-merge
        if: steps.rev.outputs.noop == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          DATE=$(date -u +%Y-%m-%d)
          TITLE="release: $DATE"
          BODY=$(cat <<'EOF'
          ${{ steps.commits.outputs.body }}
          EOF
          )
          PR_URL=$(gh pr create --base main --head develop --title "$TITLE" --body "$BODY")
          PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')
          echo "PR_NUM=$PR_NUM" >> "$GITHUB_ENV"
          echo "PR_URL=$PR_URL" >> "$GITHUB_ENV"
          gh pr merge --auto --rebase "$PR_NUM"

      - name: Wait for merge
        if: steps.rev.outputs.noop == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          for i in $(seq 1 30); do
            STATE=$(gh pr view "$PR_NUM" --json state -q .state)
            if [[ "$STATE" == "MERGED" ]]; then
              echo "PR #$PR_NUM merged"
              break
            fi
            if [[ "$STATE" == "CLOSED" ]]; then
              echo "::error::PR #$PR_NUM closed without merge"
              exit 1
            fi
            sleep 2
          done
          if [[ "$STATE" != "MERGED" ]]; then
            echo "::error::PR #$PR_NUM not merged after 60s — auto-merge may be blocked"
            exit 1
          fi

      - name: Tag main tip
        if: steps.rev.outputs.noop == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          git fetch origin main
          git checkout main
          git pull --ff-only origin main
          NEW_SHA=$(git rev-parse HEAD)
          DATE=$(date -u +%Y-%m-%d)
          TAG="release-$DATE-${NEW_SHA:0:7}"
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git tag -a "$TAG" -m "Auto-cut from develop@${{ steps.rev.outputs.develop }} (PR $PR_URL)"
          git push origin "$TAG"
          {
            echo "## Release cut complete"
            echo ""
            echo "- before main: \`${{ steps.rev.outputs.main }}\`"
            echo "- after main:  \`$NEW_SHA\`"
            echo "- tag:        \`$TAG\`"
            echo "- PR:         $PR_URL"
            echo "- trigger:    \`${{ github.event_name }}\`"
          } >> "$GITHUB_STEP_SUMMARY"
```

### Bootstrap test plan

The new workflow can only be tested after merge (workflow_dispatch runs from default branch). Plan:

1. **Pre-merge** — Phase 4.1 QA Mechanical: lint YAML (`yamllint`), shellcheck the run blocks, verify `if:` condition syntax. No runtime test possible.
2. **Post-merge first run** — operator-driven on iMac: `gh workflow run release-cut.yml -f reason="GIM-99 first cut"` after this slice merges. Verifies whole pipeline end-to-end. Evidence comment to be appended to issue after success.
3. **If post-merge run fails** — file revert PR via `gh pr create --base develop --head <revert-branch>` and reland fix.

### CLAUDE.md update

Existing CLAUDE.md release-cut paragraph references `RELEASE_CUT_TOKEN`. Update to describe new flow:

```diff
- **Release-cut procedure:** to update `main`:
- 1. Add label `release-cut` to a merged develop PR, OR
- 2. Run `gh workflow run release-cut.yml`.
-
- The Action fast-forwards `main` to `origin/develop` using `RELEASE_CUT_TOKEN` (GitHub App or PAT with `contents: write`). No human pushes `main`, ever.
+ **Release-cut procedure:** to update `main`:
+ 1. Add label `release-cut` to a merged develop PR, OR
+ 2. Run `gh workflow run release-cut.yml`.
+
+ The Action opens a PR `develop → main`, enables auto-merge with rebase
+ strategy, and (after merge) pushes an annotated tag `release-<date>-<sha>`.
+ Uses only the workflow's `GITHUB_TOKEN` — no PAT or App needed. No human
+ pushes `main`, ever.
```

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Rewrite `.github/workflows/release-cut.yml` per reference YAML above (PE adapts to repo conventions; key invariants: GITHUB_TOKEN-only, PR + auto-merge --rebase, tag push) | PE | — |
| 2 | Search repo for any other refs to `RELEASE_CUT_TOKEN` (besides this workflow) and clean up; check `.github/branch-protection/` JSONs for stale references too | PE | T1 |
| 3 | Update CLAUDE.md release-cut paragraph per diff above | PE | T1 |
| 4 | Lint workflow — `yamllint .github/workflows/release-cut.yml`, `shellcheck` the run blocks (extracted) | PE | T1 |
| 5 | Mechanical review (CR Phase 3.1) — yaml lint output pasted, scope audit `git log origin/develop..HEAD --name-only`, anti-rubber-stamp full checklist | CR | T4 |
| 6 | Adversarial review (Opus Phase 3.2) — yaml security review (token leakage paths, shell injection in PR body, race between merge + tag), behavioral review (what happens if PR auto-merge silently disabled at repo level? what if main gets a commit between merge and tag? what if same-day cut creates tag collision?), spec drift check (every plan task in commits) | Opus | T5 |
| 7 | QA Phase 4.1 — pre-merge static checks (YAML/shellcheck output as evidence), full pipeline post-merge dispatch as **followup-acceptance comment** after merge | QA | T6 |
| 8 | Phase 4.2 merge — CTO only (per GIM-94 D1); after CI green | CTO | T1-T7 |

## Acceptance

1. `release-cut.yml` runs without `RELEASE_CUT_TOKEN` (uses only `GITHUB_TOKEN`)
2. Trigger condition logic preserved: workflow_dispatch OR `release-cut` labelled merged-to-develop PR
3. Workflow opens PR `develop→main` with title `release: <YYYY-MM-DD>` and commit list in body
4. Auto-merge with rebase strategy enabled on the PR
5. Annotated tag `release-<YYYY-MM-DD>-<short-sha>` created on main tip after merge, pushed to origin
6. Step summary records before/after SHAs, PR URL, tag name
7. No-op handling: if `develop == main`, workflow exits cleanly with summary "main already at develop tip"
8. Linear history maintained on main (rebase strategy)
9. CLAUDE.md release-cut paragraph reflects new flow
10. **Post-merge bootstrap test PASSES**: operator-driven dispatch reduces main lag from 11 commits → 0; tag visible on `main`

## Out of scope (defer)

- Multiple release tracks (e.g., `release/v1`, `release/v2`) — single linear release model
- Pre-release / RC tagging — only `release-<date>-<sha>` for now
- Slack/email notification on release cut — separate concern
- Auto-rollback workflow — manual `git reset` acceptable for personal repo
- Removing `main` entirely — operator decision; out of scope here
- Removing `enforce_admins: true` on main — current setting is correct

## Decisions recorded (rev1)

| # | Decision | Rationale |
|---|---|---|
| D1 | Approach A (PR + auto-merge rebase) over B (decommission) and C (bypass-actor) | Operator approved 2026-04-27. A keeps main functional, no PAT needed, audit trail via PR |
| D2 | Both triggers preserved (workflow_dispatch + label) | Operator approved. Label = automation hook, dispatch = manual escape hatch |
| D3 | Annotated tags on main tip after merge | Operator approved. Format `release-<YYYY-MM-DD>-<sha[:7]>`, tag push to origin |
| D4 | Rebase merge strategy (not squash, not merge-commit) | Linear history (`required_linear_history: true`); preserves develop's commits as ancestors of main |
| D5 | Wait-for-merge poll up to 60s | Auto-merge fires immediately when no required checks; 60s is generous safety margin |
| D6 | No required CI on the cut PR | main has no required checks (verified). Auto-merge unblocked. Adding required checks deferred unless need surfaces |
| D7 | Bootstrap test = post-merge operator dispatch (not pre-merge) | workflow_dispatch only runs from default branch; can't test before merging. Acceptable risk — workflow is mostly declarative |

## Open questions

None at design time. If Opus Phase 3.2 surfaces concerns (token scope, race conditions, tag collision strategy), apply rev2 before paperclip Phase 2 starts.

## References

- `.github/workflows/release-cut.yml` — current broken state
- `.github/branch-protection/main.json` — main protection JSON (verify no stale `RELEASE_CUT_TOKEN` reference)
- CLAUDE.md — release-cut paragraph (target of Task 3)
- `paperclip-shared-fragments@1c76fa9/fragments/compliance-enforcement.md` — Phase 4.2 CTO-only rule + anti-rubber-stamp
- `paperclip-shared-fragments@1c76fa9/fragments/phase-handoff.md` — handoff matrix
- GIM-57 — original release-cut.yml shipped here; broken since
- Memory `project_backlog.md` — release-cut-v2 tracked as followup since 2026-04-19
- Memory `feedback_single_token_review_gate.md` — single-token reality (informs why direct-push to main needs PR pattern)
