# Meta-workflow migration — rollback runbook

**Date:** 2026-04-19
**Consumed by:** spec `docs/superpowers/specs/2026-04-19-meta-workflow-migration-design.md` §11.
**Trigger conditions:** any of
- Branch protection on main/develop blocks legitimate operations we need now.
- qa-evidence-present check false-positives blocking real merges repeatedly.
- CR GitHub-review bridge fails for technical reasons and blocks merges.
- Agent behavior regression after fragment deploy.

## Pre-rollback snapshot

Record before executing:

```bash
PRE_MAIN=$(git rev-parse origin/main)
PRE_DEV=$(git rev-parse origin/develop)
PRE_FRAG=$(cd paperclips/fragments/shared && git rev-parse HEAD)
echo "PRE_MAIN=$PRE_MAIN PRE_DEV=$PRE_DEV PRE_FRAG=$PRE_FRAG" | tee /tmp/migration-rollback-snapshot.env
```

## Steps

### 1. Remove branch protection (immediate unblock)

```bash
gh api -X DELETE /repos/ant013/Gimle-Palace/branches/main/protection
gh api -X DELETE /repos/ant013/Gimle-Palace/branches/develop/protection
```

### 2. Disable the new workflows

```bash
gh workflow disable qa-evidence-present
gh workflow disable release-cut
```

Or delete the files on a revert branch (step 4).

### 3. Restore pre-migration fragment bundle

Identify the migration-merge-sha on develop:

```bash
MERGE_SHA=$(git log origin/develop --oneline | grep 'meta-workflow migration' | head -1 | awk '{print $1}')
```

Revert it on a new branch:

```bash
git fetch origin
git switch -c rollback/meta-workflow-migration origin/develop
git revert -m 1 $MERGE_SHA
# Resolve any submodule conflict — restore to pre-migration fragments ref
cd paperclips/fragments/shared
git checkout <pre-migration-submodule-sha>    # from PRE_FRAG snapshot
cd ../../..
git add paperclips/fragments/shared
git commit -m "rollback: restore pre-migration shared fragments"
git push origin rollback/meta-workflow-migration
```

### 4. Merge the revert via PR (or direct-push, protection is off)

```bash
gh pr create --base develop --head rollback/meta-workflow-migration \
  --title "rollback: meta-workflow migration (GIM-57)" \
  --body "Emergency rollback per runbook. Reason: <describe>.

Pre-rollback state:
- develop: $PRE_DEV
- main: $PRE_MAIN
- submodule: $PRE_FRAG"
gh pr merge <PR#> --squash --delete-branch
```

### 5. Redeploy old fragment bundle to 11 agents

```bash
./paperclips/build.sh
./paperclips/deploy-agents.sh --local
```

### 6. If release-cut already moved main, rewind main via FF-back

Only works while main is still a direct ancestor-or-descendant of the rollback commit:

```bash
git switch main
git reset --hard $PRE_MAIN
git push origin main --force-with-lease    # emergency escape hatch ONLY during rollback
```

(Force-with-lease on main is forbidden during normal operation. During rollback, with branch protection already removed in Step 1, it is the restore path.)

### 7. Notify all 11 agents

Deploy step 5 + paperclip UI refresh. If some agent is mid-run, reassign or release its execution lock.

## Post-rollback

- Record in `project_backlog.md` memory: slice rolled back, with reason + pre/post SHAs.
- Open a new paperclip issue for followup (what went wrong + what to try next).
- Re-apply branch protection manually if you want to keep admin-bypass closure WITHOUT the other changes — create a minimal `branches/develop/protection` JSON with only admin-enforce + required checks (no qa-evidence, no CR-review requirement).

## Time budget

Steps 1-2: 2 min (immediate unblock).
Steps 3-5: 20-30 min (revert + rebuild + deploy).
Step 6-7: 10 min if needed.
Total: 30-45 min for a full rollback.
