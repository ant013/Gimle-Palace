---
slug: GIM-94-ops-quality-round-2
status: rev3 (CR round 1 findings addressed)
branch: feature/GIM-94-ops-quality-round-2
paperclip_issue: 94
predecessor: 6fc1d1a (develop tip after GIM-81 merge)
date: 2026-04-26
---

# GIM-94 — Ops-quality round 2 (fragment compression + Phase 4.2 + .env.example)

## Goal

Fix three operational defects discovered in the 2026-04-25/26 N+1 + autonomous-chain session, while **net-reducing** the byte size of `paperclip-shared-fragments`. Today's GIM-82/90/91 added +184 lines (~5.5 KB ≈ 1500 tokens) of mostly postmortem narrative — that loads into every agent run. Compression must dominate the 3 new rules being added.

## Baseline

```
paperclip-shared-fragments @ 3d63d3f  (post-GIM-91 main, 2026-04-26)
```

File sizes at that commit (authoritative — all compression targets and bytewise checks reference these):

| File | Bytes at 3d63d3f |
|---|---|
| `fragments/worktree-discipline.md` | 3455 |
| `fragments/compliance-enforcement.md` | 3979 |
| `fragments/pre-work-discovery.md` | 2307 |

Verify any value with:

```bash
git -C paperclip-shared-fragments show 3d63d3f:fragments/<name>.md | wc -c
```

## Defects to fix

### D1 — Phase 4.2 role boundary not codified

GIM-81 (2026-04-25 19:09): CTO posted "I'll squash-merge once lint is green". PE pushed lint fix and immediately ran `gh pr merge --squash` themselves. Workflow violation, but `mergedBy: ant013` on GitHub gave no signal — all agents share the same token. GitHub-side enforcement cannot work (memory `feedback_single_token_review_gate.md`); discipline must live in fragments + role files.

### D2 — `PAPERCLIP_API_KEY` missing from `.env.example`

Live smoke 2026-04-26 03:55 UTC: `palace.ops.unstick_issue` returned 401 Unauthorized. Container env had `PAPERCLIP_API_KEY=""` because compose wires `${PAPERCLIP_API_KEY:-}` (empty default) and `.env` had no entry. QA Phase 4.1 PASS evidence falsely claimed "Blocker 1 401 FIXED" (tested with manual override or mock). Production deploys would hit the same 401 on first restart.

### D3 — Fragments edits bypass PR review

Audit 2026-04-26 04:00 UTC of `ant013/paperclip-shared-fragments`:
- GIM-82 → PR #7 ✅ (proper)
- GIM-90 commit `3d63d3f` — direct push to main, no PR
- GIM-91 commits `88a6803`, `14ce7d9` — direct push, no PR

Branch protection on fragments `main` is currently disabled. Risk: any agent run with operator's GH token can push broken rules with zero review trail.

### D4 — Fragment density bloat

Today's +184 lines breakdown:
- `worktree-discipline.md` +86 lines (mostly narrative GIM-75/76 incident text)
- `compliance-enforcement.md` +56 lines (verbose evidence-rigor + "how CR enforces" prose)
- `pre-work-discovery.md` +42 lines (long examples + practical-guidance sections)

Same rules can be expressed in ~30 lines total without semantic loss.

## Compression principle (applied to existing + future)

**One imperative line per rule + optional one-line "why" + optional one shell command.**

Forbidden in fragments:
- Multi-paragraph postmortem narratives → move to `docs/postmortems/`
- "How CR enforces" sections with bash → role-specific, move to `paperclips/roles/code-reviewer.md`
- "Practical guidance" with examples → cut; agents will reason

Soft cap per fragment file: **2 KB**. If exceeded, refactor or split.

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Compress `fragments/worktree-discipline.md` (3455 B → ≤ 2000 B) | PE | — |
| 2 | Compress `fragments/compliance-enforcement.md` (3979 B → ≤ 2000 B) + add D1 rule + D3 rule | PE | — |
| 3 | Compress `fragments/pre-work-discovery.md` (2307 B → ≤ 1500 B) | PE | — |
| 4 | Create `docs/runbooks/deploy-checklist.md` with auth-path probe (`.env.example` already has `PAPERCLIP_API_KEY` via GIM-81 merge `6fc1d1a`) | PE | — |
| 5 | New `fragments/fragment-density.md` (≤ 25 lines) — codify compression principle | PE | — |
| 6 | New `docs/postmortems/2026-04-26-fragment-extraction-postmortems.md` — narrative content moved here | PE | T1, T2, T3 |
| 7 | Setup branch protection on `paperclip-shared-fragments/main` via `gh api PUT` (blocks direct push) | **Operator (Board)** — NOT PE, requires admin perms; run parallel to Phase 2 or between 4.1→4.2 | — |
| 8 | Net-byte verification: per-file and aggregate `wc -c` vs pinned baseline | PE (CR verifies) | T1-T6 |

### Task 1 — worktree-discipline.md compression

**Baseline: 3455 B. Target: ≤ 2000 B.**

Current additions to trim (86 lines):

- "Cross-branch carry-over forbidden" — 4-section rule with full GIM-75/76 narrative.
  Compress to:
  ```
  ## Cross-branch carry-over forbidden

  Never carry commits between parallel slice branches via cherry-pick or
  copy-paste. If Slice B's tests need Slice A, declare `depends_on: A`
  in spec and rebase on develop after A merges.

  Why: GIM-75/76 incident (2026-04-24) — see postmortem 2026-04-26.

  CR enforcement: every changed file must be in slice's declared scope.
  ```

- "QA returns production checkout" — 4-section rule with GIM-48 narrative.
  Compress to:
  ```
  ## QA returns checkout to develop after Phase 4.1

  Before run exit, QA on iMac:
      cd /Users/Shared/Ios/Gimle-Palace && git checkout develop && git pull --ff-only

  Verify: `git branch --show-current` outputs `develop`.

  Why: production checkout drives deploys/observability. Incident GIM-48 (2026-04-18).
  ```

Delete: detailed dirty-worktree handling examples, "Practical guidance" subsections. PE/QA agents are intelligent — minimum directive is enough.

### Task 2 — compliance-enforcement.md compression + 2 new rules

**Baseline: 3979 B. Target: ≤ 2000 B.**

**Compress added today** (56 lines → ≤ 20 lines):

- Evidence rigor — keep the imperative + 1-line why. Drop the "Pattern" code blocks, drop "How CR enforces" subsection.
- Scope audit — keep imperative + bash command. Drop the wrap-around explanation.
- MCP wire-contract test rule (GIM-91) — keep imperative + reference test pattern path. Drop the "tests must do X, Y, Z" elaboration; the reference file shows it.

**Add D1 rule** (≤ 6 lines):

```
## Phase 4.2 squash-merge — CTO-only

Only CTO calls `gh pr merge`. Other roles stop after Phase 4.1 PASS:
they may comment, push final fixes, never merge.

Why: shared `ant013` GH token; branch protection cannot enforce actor.
See memory `feedback_single_token_review_gate`.
```

**Add D3 rule** (≤ 4 lines):

```
## Fragment edits go through PR

Never direct-push to `paperclip-shared-fragments/main`. Cut FB, open PR,
get CR APPROVE, squash-merge. Same flow as gimle-palace develop.
```

### Task 3 — pre-work-discovery.md compression

**Baseline: 2307 B. Target: ≤ 1500 B.**

Same shape as T1: keep imperative + one-line why + optional command. Drop multi-paragraph examples and "How to verify" subsections.

### Task 4 — deploy-checklist runbook (`.env.example` already done)

**`.env.example` already has `PAPERCLIP_API_KEY=` on develop** (landed via GIM-81 merge `6fc1d1a`, line 37). No `.env.example` edit needed — PE skips that part.

Create `docs/runbooks/deploy-checklist.md` (new file) with steps:

1. Pull latest develop.
2. `grep -E "^(NEO4J_PASSWORD|OPENAI_API_KEY|PAPERCLIP_API_KEY)=." .env` returns 3 lines (non-empty values).
3. `docker compose --profile review up -d --build --wait`
4. `curl -fsS http://localhost:8080/healthz` returns `{"status":"ok"}`.
5. **Auth-path probe** — run this immediately after step 4:
   ```bash
   docker compose exec -T palace-mcp python3 -c '
   import os, urllib.request, json
   url = os.environ["PAPERCLIP_API_URL"] + "/api/health"
   key = os.environ["PAPERCLIP_API_KEY"]
   req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
   with urllib.request.urlopen(req, timeout=5) as r:
       assert r.status == 200, f"paperclip auth failed: {r.status}"
   print("OK")'
   ```
   Expected output: `OK`. Any non-200 or exception = deploy blocked; re-check `PAPERCLIP_API_KEY` in `.env`.

   Alternative if the `/api/health` endpoint does not accept Authorization header: call `palace.ops.unstick_issue` via MCP with a known-done issue UUID and `dry_run=True`, assert response contains `"action": "noop"` (not an error or 401).

### Task 5 — `fragments/fragment-density.md` (NEW, ≤ 25 lines)

```
# Fragment density rule

Each fragment rule = imperative one-liner + (optional) one-line "why" +
(optional) one shell command if needed by an agent role.

Forbidden in fragments:
- Multi-paragraph postmortem narratives → `docs/postmortems/<date>-<slug>.md`
- Role-specific bash → `paperclips/roles/<role>.md`
- "Practical guidance" with examples → trust agent reasoning

Soft cap per file: 2 KB. If exceeded, refactor or split.

CR enforces: at Phase 1.2 plan-first review and Phase 3.1 mechanical review,
reject fragment-edit PRs that violate density rule.
```

Reference from `compliance-enforcement.md` (1 line link).

### Task 6 — `docs/postmortems/2026-04-26-fragment-extraction-postmortems.md` (NEW)

Move all narrative content extracted from fragments here. Format:

```
# 2026-04-26 — Fragment narratives extracted (GIM-94)

Postmortems for incidents that previously lived in fragments and bloated
agent prompts. Moved here per GIM-94 fragment-density rule. Fragments
now reference these by date+slug.

## GIM-75/76 carry-over commit incident (2026-04-24)
[narrative from worktree-discipline.md]

## GIM-48 production checkout drift (2026-04-18)
[narrative from worktree-discipline.md]

## GIM-89 palace.code.* arg-forwarding regression (2026-04-25)
[narrative — pertains to GIM-91 fragment]

## GIM-81 Phase 4.2 boundary violation (2026-04-25)
[narrative — pertains to D1 above]
```

### Task 7 — Branch protection on fragments main

The protection payload must set `required_pull_request_reviews` to a non-null object so that a PR is required before any commit lands on `main`. `required_approving_review_count: 0` means the PR author does not need a separate approver — this works under single-token reality (per memory `feedback_single_token_review_gate`) while still blocking direct push entirely.

```bash
gh api -X PUT /repos/ant013/paperclip-shared-fragments/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

After running, verify the protection is active:

```bash
gh api /repos/ant013/paperclip-shared-fragments/branches/main/protection \
  --jq '.required_pull_request_reviews.required_approving_review_count'
# expected output: 0
```

Then confirm direct push is rejected:

```bash
# From a local clone of paperclip-shared-fragments on a non-PR branch
echo "test" >> fragments/worktree-discipline.md
git add -A && git commit -m "test direct push protection"
git push origin main
# Expected: remote: error: GH006: Protected branch update failed ...
git reset --hard HEAD~1  # revert the test commit locally
```

### Task 8 — Net-byte verification (wc -c against pinned baseline)

PE runs this after T1–T6 are complete; CR re-runs independently at Phase 3.1.

**Baseline commit:** `3d63d3f` (post-GIM-91 `paperclip-shared-fragments` main — see Baseline section above).

```bash
BASELINE=3d63d3f
FRAGS="paperclips/fragments/shared"

# Per-file check for the three files this slice touches
for FILE in fragments/worktree-discipline.md fragments/compliance-enforcement.md fragments/pre-work-discovery.md; do
  PRE=$(git -C "$FRAGS" show "${BASELINE}:${FILE}" | wc -c)
  NEW=$(wc -c < "${FRAGS}/${FILE}")
  if [ "$NEW" -ge "$PRE" ]; then
    echo "BYTE BUDGET VIOLATED: $FILE  baseline=${PRE}B  now=${NEW}B"
    exit 1
  else
    echo "OK: $FILE  ${PRE}B -> ${NEW}B  (delta=$(( NEW - PRE ))B)"
  fi
done

# Aggregate check across all fragment files
PRE_TOTAL=$(git -C "$FRAGS" ls-tree -r "${BASELINE}" --name-only fragments/ | \
  xargs -I{} sh -c "git -C ${FRAGS} show ${BASELINE}:{} | wc -c" | \
  awk '{s+=$1} END {print s}')
NEW_TOTAL=$(find "${FRAGS}/fragments" -type f | xargs wc -c | tail -1 | awk '{print $1}')
echo "Aggregate: baseline=${PRE_TOTAL}B  now=${NEW_TOTAL}B  delta=$(( NEW_TOTAL - PRE_TOTAL ))B"
if [ "$NEW_TOTAL" -ge "$PRE_TOTAL" ]; then
  echo "AGGREGATE BYTE BUDGET VIOLATED"
  exit 1
fi
echo "Net-byte check PASSED"
```

If any check fails, fail Phase 3.1 review and iterate compression.

## Phase sequence (standard)

| Phase | Agent | Notes |
|---|---|---|
| 1.1 Formalize | CTO | This plan exists; CTO verifies baseline SHA + pushes branch |
| 1.2 Plan-first review | CR | Review this plan for completeness and scope |
| 2 Implement | PE | Tasks 1–6 + 8 only. T7 is Board/operator — runs in parallel or between 4.1→4.2 |
| 3.1 Mechanical | CR | Verify fragment sizes with `wc -c`; re-run T8 script independently |
| 3.2 Adversarial | Opus | Verify no semantic loss in compression; check D3 fix is real |
| 4.1 QA | QA | Full QA checklist below |
| 4.2 Merge | **CTO ONLY** | Per the new D1 rule landing in this PR |

No chain trigger to next slice — this is end of ops-quality cleanup queue.

## Phase 4.1 QA acceptance (detailed)

QA must verify each item and include evidence in the PR body under `## QA Evidence`.

### Bundle size: per-bundle delta, not absolute

Each of the 11 dist bundles in `paperclips/dist/*.md` must SHRINK in bytes vs the pre-GIM-94 baseline. Use the develop tip SHA immediately before this branch's submodule bump as `$BASELINE_GIMLE`.

```bash
BASELINE_GIMLE=$(git merge-base HEAD origin/develop)

for F in paperclips/dist/*.md; do
  PRE=$(git show "${BASELINE_GIMLE}:${F}" 2>/dev/null | wc -c)
  CUR=$(wc -c < "$F")
  if [ "$CUR" -gt "$PRE" ]; then
    echo "REGRESS: $F  ${PRE}B -> ${CUR}B  (+$(( CUR - PRE ))B)"
  else
    echo "OK: $F  ${PRE}B -> ${CUR}B  ($(( CUR - PRE ))B)"
  fi
done
```

Expected: zero `REGRESS` lines. Any regression = block on QA.

### Auth-path probe (must pass end-to-end)

After `docker compose --profile review up -d --wait`, run the auth probe from the deploy-checklist:

```bash
docker compose exec -T palace-mcp python3 -c '
import os, urllib.request, json
url = os.environ["PAPERCLIP_API_URL"] + "/api/health"
key = os.environ["PAPERCLIP_API_KEY"]
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
with urllib.request.urlopen(req, timeout=5) as r:
    assert r.status == 200, f"paperclip auth failed: {r.status}"
print("OK")'
```

Expected output: `OK`. Paste the terminal output as QA evidence. If response is non-200 or raises, QA is blocked — do not claim D2 fixed.

### Branch protection verification

Confirm T7 was executed and the protection is live:

```bash
gh api /repos/ant013/paperclip-shared-fragments/branches/main/protection \
  --jq '.required_pull_request_reviews.required_approving_review_count'
```

Expected output: `0`. Paste output as QA evidence.

### Fragment compression check

Re-run T8 script (net-byte verification). All per-file checks and aggregate must show `OK`. Paste full output as QA evidence.

### D1 rule readable in dist bundle

```bash
grep -c "Phase 4.2 squash-merge" paperclips/dist/python-engineer.md
```

Expected: `1`. Paste output.

## Acceptance summary

1. All 4 defects (D1-D4) addressed with concrete, enforceable artifacts
2. Net byte delta on `fragments/` is **negative** vs. `paperclip-shared-fragments@3d63d3f` baseline (verified per-file and aggregate with `wc -c`)
3. All previously-codified rules from GIM-82/90/91 still expressible (semantic preservation verified by Opus at 3.2)
4. Postmortem doc exists with extracted narratives; fragments reference it by date
5. `PAPERCLIP_API_KEY` documented in `.env.example` + deploy-checklist auth-path probe passes end-to-end in QA
6. Branch protection on fragments main has `required_pull_request_reviews.required_approving_review_count=0` (direct push blocked; verified via `gh api` + attempted push test)
7. New `fragment-density.md` enforced by CR going forward
8. Each of the 11 `paperclips/dist/*.md` bundles shrinks in bytes vs pre-GIM-94 baseline (zero `REGRESS` lines)

## Out of scope (defer to N+2 candidates)

- Per-role fragment loading (PE.md ingests only PE-relevant rules; CR.md only CR-relevant) — large architectural refactor, file as N+2
- Automated token-budget alarm in `paperclips/build.sh` — defer until compression discipline holds over multiple slices
- Migrating other historical narratives from fragments to memory/postmortems — this slice covers what GIM-82/90/91 added; older narratives left for a later cleanup pass

## Open questions for operator review

1. **Net-byte target tightness:** "≤ pre-GIM-94 baseline (`3d63d3f`)" or "≤ pre-GIM-82 baseline (more aggressive)"?
2. **Postmortem doc structure:** one file with 4 sections (current plan) or 4 separate files?
3. **D1 rule placement:** only in `compliance-enforcement.md`, or duplicated in `paperclips/roles/python-engineer.md` so PE sees it without cross-fragment lookup?
4. **`required_approving_review_count: 0` permanence:** keep at 0 until a separate bot identity is provisioned (separate slice), or revisit sooner?
