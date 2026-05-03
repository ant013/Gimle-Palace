## Git workflow (iron rule)

- Work **only** in a feature branch. Create from `develop`: `git checkout -b feature/X origin/develop`.
- Open PR **into `develop`**, not `main`. `main` updates only via release flow (develop → main).
- Before PR: `git fetch origin && git rebase origin/develop`.
- Force push on `main` / `develop` — **forbidden**. On a feature branch — only `--force-with-lease`.
- Direct commits to `main` / `develop` — **forbidden**.
- Branches diverged (develop diverged from main) — escalate to Board, don't act yourself.

### Fresh-fetch on wake

Before any `git log` / `git show` / `git checkout` in a new run:

```bash
git fetch origin --prune
```

Parent clone is shared across worktrees; a stale parent means stale `origin/*` refs for every worktree on the host. A single `fetch` updates all. Skip this and you will chase artifacts "not found on main" when they are pushed but uncached locally.

This is a **compensation control** (agent remembers). An environment-level hook (paperclip worktree pre-wake fetch or a `deploy-agents.sh` wrapper) is a followup — until it lands, this rule is load-bearing.

### Force-push discipline on feature branches

- `--force-with-lease` allowed on **feature branches only**.
- Use it ONLY when:
  1. You have fetched immediately prior (`git fetch origin`).
  2. You are the **sole writer** of the current phase (no parallel QA evidence, no parallel CR-rev from another agent).
- Multi-writer phases (e.g., QA adding evidence-docs alongside MCPEngineer's impl commits): regular `git push` only, and rebase-then-push instead of force.
- Force-push on `develop` / `main` — forbidden, always. Protection will reject; don't retry with `--force`.

### What applies to Board, too

This fragment binds **all writers** — agents, Board session, human operator. When Board writes a spec or plan, it goes on a feature branch. Board checkout location: a separate clone per `AGENTS.md § New Task Branch And Spec Gate`. When Board pushes, it's to `feature/...` then PR — never `main` or `develop` directly.

### Phase 4.2 — Merge-readiness reality-check

Before escalating **any** merge blocker, run these commands and paste their output in the same comment. An escalation without this evidence is a protocol violation — symmetric to the anti-rubber-stamp rule for code review.

#### Mandatory pre-escalation commands

```bash
# 1. PR merge state + CI status
gh pr view <N> --json mergeStateStatus,mergeable,statusCheckRollup,reviewDecision,headRefOid

# 2. Individual check-runs (when statusCheckRollup is empty or unclear)
gh api repos/<owner>/<repo>/commits/<head>/check-runs

# 3. Branch protection rules (when claiming review or check requirements block merge)
gh api repos/<owner>/<repo>/branches/develop/protection \
  | jq '.required_status_checks.contexts, (.required_pull_request_reviews // "NONE")'
```

#### `mergeStateStatus` decoder table

| Value | Meaning | Fix |
|---|---|---|
| `CLEAN` | Ready to merge | `gh pr merge --squash --auto` |
| `BEHIND` | Branch base has advanced (sibling PR merged) | `gh pr update-branch <N>` → wait CI → merge |
| `DIRTY` | Merge conflict against base | Forward-merge: `git merge origin/develop` on feature branch, push |
| `BLOCKED` | Failing checks OR missing reviews | Inspect `statusCheckRollup` first; if reviews issue + agent is PR author, see `feedback_single_token_review_gate` (do NOT relax protection) |
| `UNSTABLE` | Non-required checks failing | Usually mergeable — inspect rollup, proceed if required checks pass |
| `UNKNOWN` | GitHub still computing | Wait 5–10s, re-query |
| `DRAFT` | PR is a draft (deprecated — GitHub recommends `PullRequest.isDraft` instead, but `gh pr view --json mergeStateStatus` still returns this value) | Convert to ready-for-review: `gh pr ready <N>` |
| `HAS_HOOKS` | GitHub Enterprise pre-receive hooks exist | Mergeable — pre-receive hooks execute server-side on merge. Proceed normally |

#### Forbidden response patterns

These claims are **banned** without the corresponding evidence output pasted in the same comment:

- «GitHub Actions returned 0 checks» — without `total_count` from `gh api .../check-runs` output.
- «Branch protection requires N checks but received 0» — without `gh pr view --json statusCheckRollup` output.
- «Required reviews blocking merge» — without `gh api .../protection` output showing `required_pull_request_reviews` is present (not `"NONE"`).
- «GitHub broken» / «CI not running» — without `gh run list --branch <name>` output.

#### Self-approval clarification

GitHub's global rule «PR author cannot approve their own PR» applies **always** — this is a platform constraint, NOT branch-protection. If `required_pull_request_reviews` is absent in the protection JSON (shows `"NONE"`), then approval is **not required** for merge. The author-cannot-self-approve rejection is harmless in this case — it does not block merge.

See `feedback_single_token_review_gate` in operator memory for the full context on this distinction.
