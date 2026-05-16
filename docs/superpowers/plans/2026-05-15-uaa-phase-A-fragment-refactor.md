# UAA Phase A — Fragment Library Refactor + Role-Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §4, §10.1.1
**Owner:** `operator` (per spec §14.2 — self-modifying work, not for gimle team)
**Estimate:** 3–4 days
**Prereq:** None (this is the first phase)
**Blocks:** Phase B (profile library expects new fragment layout)

**Goal:** Reorganize `paperclips/fragments/shared/fragments/*.md` into a hierarchical layout (`universal/`, `git/`, `worktree/`, `handoff/`, `code-review/`, `qa/`, `pre-work/`, `plan/`) and split heavy mixed-content role files into legacy-deprecated + new craft-only files.

**Multi-target note (rev4 MA-2):** Phase A touches role-files in `paperclips/roles/` (claude) and `paperclips/roles-codex/` (codex). The directory naming is convention: a future target X (e.g. `gemini`) would have `paperclips/roles-gemini/` paralleling these. Phase A does NOT introduce new targets; it only reorganizes existing two. See spec §3.4 for target extensibility.

**Architecture:** Two parallel refactor tracks, both committed to the `paperclip-shared-fragments` submodule (`ant013/paperclip-shared-fragments.git`):
1. **Fragment hierarchy** — move/split 13 existing fragment files into 16 new files organized by selectivity (some fragments split, some renamed, none deleted in Phase A — preserves backward compat for existing builder until Phase B).
2. **Role-split (hybrid)** — copy each `paperclips/roles/*.md` and `paperclips/roles-codex/cx-*.md` to `paperclips/roles/legacy/` (and `roles-codex/legacy/`); rewrite originals as slim craft-only files that defer capability to profile composition.

**Tech Stack:**
- bash + git (submodule edits)
- pytest (test fragment integrity)
- existing `paperclips/scripts/build_project_compat.py` for build verification

**Critical constraint:** This phase touches what every running paperclip agent reads on next wake. **Pause all gimle agents before deploying any change** (operator-only, not via paperclip API hot-update). Builds must produce identical output to current state until Phase B activates new layout.

---

## File Structure

### Created files (in `paperclip-shared-fragments` submodule)

```
fragments/universal/
├── karpathy.md                       # was: karpathy-discipline.md (renamed)
├── wake-and-handoff-basics.md        # NEW: merged heartbeat-discipline + phase-handoff basics
└── escalation-board.md               # was: escalation-blocked.md (renamed)

fragments/git/
├── commit-and-push.md                # NEW: split from git-workflow.md (commit/branch/push parts)
├── merge-readiness.md                # NEW: split from git-workflow.md (merge-readiness check)
├── merge-state-decoder.md            # NEW: split from git-workflow.md (mergeStateStatus codes)
└── release-cut.md                    # NEW: split from git-workflow.md (release-cut procedure)

fragments/worktree/
└── active.md                         # was: worktree-discipline.md (renamed, content split)

fragments/handoff/
├── basics.md                         # NEW: PATCH+@mention+STOP rules (split from phase-handoff.md)
└── phase-orchestration.md            # NEW: cto-only phase choreography (split from phase-handoff.md)

fragments/code-review/
├── approve.md                        # NEW: split from compliance-enforcement.md
└── adversarial.md                    # NEW: split from compliance-enforcement.md (Opus-only content)

fragments/qa/
└── smoke-and-evidence.md             # NEW: split from compliance-enforcement.md (qa parts) + test-design-discipline.md

fragments/pre-work/
├── codebase-memory-first.md          # was: pre-work-discovery.md (split + renamed)
├── sequential-thinking.md            # NEW: split from pre-work-discovery.md
└── existing-field-semantics.md       # NEW: split from pre-work-discovery.md

fragments/plan/
├── producer.md                       # was: plan-first-producer.md (renamed)
└── review.md                         # was: plan-first-review.md (renamed)
```

### Deprecated files (kept temporarily for builder back-compat)

```
fragments/heartbeat-discipline.md     # KEEP, add deprecation banner
fragments/phase-handoff.md            # KEEP, add deprecation banner
fragments/git-workflow.md             # KEEP, add deprecation banner
fragments/karpathy-discipline.md      # KEEP, add deprecation banner
fragments/escalation-blocked.md       # KEEP, add deprecation banner
fragments/worktree-discipline.md      # KEEP, add deprecation banner
fragments/compliance-enforcement.md   # KEEP, add deprecation banner
fragments/test-design-discipline.md   # KEEP, add deprecation banner
fragments/pre-work-discovery.md       # KEEP, add deprecation banner
fragments/plan-first-producer.md      # KEEP, add deprecation banner
fragments/plan-first-review.md        # KEEP, add deprecation banner
fragments/cto-no-code-ban.md          # KEEP unchanged (it stays as-is, not refactored — used only by CTO craft)
fragments/language.md                 # KEEP unchanged (small, used by all)
```

### Role-split files (in main `Gimle-Palace` repo, not submodule)

```
# For each of 12 claude roles (in paperclips/roles/):
#   roles/legacy/<role>.md  # copy of current with deprecation banner
#   roles/<role>.md         # NEW slim craft-only file

# For each of 12 codex roles (in paperclips/roles-codex/):
#   roles-codex/legacy/cx-<role>.md  # copy with banner
#   roles-codex/cx-<role>.md         # NEW slim craft-only

# Total: 24 legacy/ files + 24 rewritten craft files
```

### Test files

```
paperclips/tests/test_phase_a_fragment_layout.py   # NEW
paperclips/tests/test_phase_a_role_craft.py        # NEW
paperclips/tests/test_phase_a_build_compat.py      # NEW (golden-file build comparison)
```

---

## Task 1: Snapshot baseline build output for golden-file tests

**Files:**
- Create: `paperclips/tests/baseline/dist-snapshot/` (gitignored — local reference)

- [ ] **Step 1: Verify clean working state**

```bash
git status --short paperclips/
```
Expected: only spec PR file in `docs/superpowers/specs/`. If other modified files exist, stash them.

- [ ] **Step 2: Capture current builder output for all 3 projects × all targets**

```bash
mkdir -p paperclips/tests/baseline/dist-snapshot
./paperclips/build.sh --project gimle --target claude
./paperclips/build.sh --project gimle --target codex
./paperclips/build.sh --project trading --target claude
./paperclips/build.sh --project trading --target codex
./paperclips/build.sh --project uaudit --target codex
cp -r paperclips/dist/ paperclips/tests/baseline/dist-snapshot/
```

- [ ] **Step 3: Compute SHA256 manifest of baseline**

```bash
cd paperclips/tests/baseline/dist-snapshot
find dist -type f -name "*.md" | sort | xargs shasum -a 256 > ../baseline-shas.txt
cd -
wc -l paperclips/tests/baseline/baseline-shas.txt
```
Expected: ~30+ lines (one per built agent .md).

- [ ] **Step 4: Add baseline to .gitignore**

Edit `.gitignore`:
```
+# Phase A baseline (local-only reference, not committed)
+paperclips/tests/baseline/dist-snapshot/
```

- [ ] **Step 5: Commit gitignore + baseline-shas.txt**

```bash
git add .gitignore paperclips/tests/baseline/baseline-shas.txt
git commit -m "test(uaa-phase-a): snapshot baseline build SHAs for compat tests"
```

---

## Task 2: Create universal/karpathy.md (rename + content polish)

**Files:**
- Create: `paperclips/fragments/shared/fragments/universal/karpathy.md`
- Modify: `paperclips/fragments/shared/fragments/karpathy-discipline.md` (add deprecation banner)
- Test: `paperclips/tests/test_phase_a_fragment_layout.py`

- [ ] **Step 1: Create test file with first failing test**

```python
# paperclips/tests/test_phase_a_fragment_layout.py
"""Phase A: verify new fragment hierarchy exists with expected content."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUBMODULE = REPO / "paperclips" / "fragments" / "shared" / "fragments"


def test_universal_karpathy_exists():
    p = SUBMODULE / "universal" / "karpathy.md"
    assert p.is_file(), f"missing {p}"
    text = p.read_text()
    assert "Think before" in text or "Think Before" in text
    assert "Minimum" in text or "minimum" in text
    assert "Surgical" in text or "surgical" in text
    assert "Goal" in text or "goal" in text
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd paperclips
python3 -m pytest tests/test_phase_a_fragment_layout.py::test_universal_karpathy_exists -v
```
Expected: FAIL with "missing .../universal/karpathy.md"

- [ ] **Step 3: Create the new file (cd into submodule)**

```bash
cd paperclips/fragments/shared
git checkout -b feature/uaa-phase-a-fragment-refactor
mkdir -p fragments/universal
cp fragments/karpathy-discipline.md fragments/universal/karpathy.md
```

- [ ] **Step 4: Polish content of the new file (no semantic change, just header)**

Edit `paperclips/fragments/shared/fragments/universal/karpathy.md` — replace H2 heading with the canonical name:
```diff
-## Karpathy discipline (think before / minimum / surgical / verify)
+## Karpathy discipline
+
+Think before coding • Minimum code • Surgical changes • Goal+criteria+verification.
```
(Keep all 4 sub-rules. The summary line above the sub-rules is the only addition.)

- [ ] **Step 5: Add deprecation banner to original**

Edit `paperclips/fragments/shared/fragments/karpathy-discipline.md` — prepend at top (before any existing content):
```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Replaced by `fragments/universal/karpathy.md`.
> This file is kept for builder back-compat with un-migrated role files.
> Will be removed at UAA cleanup gate (spec §10.5).
```

- [ ] **Step 6: Run test, verify it passes**

```bash
cd ../../../  # back to Gimle-Palace root
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_universal_karpathy_exists -v
```
Expected: PASS

- [ ] **Step 7: Commit (in submodule first, then super-repo)**

```bash
cd paperclips/fragments/shared
git add fragments/universal/karpathy.md fragments/karpathy-discipline.md
git commit -m "feat(uaa-phase-a): split karpathy → universal/karpathy.md (deprecation banner on original)"
cd -

git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments submodule (universal/karpathy.md) + test"
```

---

## Task 3: Create universal/wake-and-handoff-basics.md (merge heartbeat + handoff basics)

**Files:**
- Create: `paperclips/fragments/shared/fragments/universal/wake-and-handoff-basics.md`
- Modify: `paperclips/fragments/shared/fragments/heartbeat-discipline.md` (add deprecation banner)

- [ ] **Step 1: Add failing test**

Append to `paperclips/tests/test_phase_a_fragment_layout.py`:
```python
def test_universal_wake_and_handoff_exists():
    p = SUBMODULE / "universal" / "wake-and-handoff-basics.md"
    assert p.is_file()
    text = p.read_text()
    # Wake-discipline checks (was in heartbeat-discipline.md)
    assert "PAPERCLIP_TASK_ID" in text
    assert "/api/agents/me" in text
    assert "Cross-session memory" in text or "cross-session memory" in text
    # Handoff basics (was in phase-handoff.md)
    assert "@mention" in text or "@-mention" in text
    assert "trailing space" in text
    assert "409" in text  # HTTP 409 lock procedure
    # Heartbeat content removed (paperclip heartbeat is OFF — not relevant content here)
    assert "intervalSec" not in text  # heartbeat-config artifact, should be gone
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_universal_wake_and_handoff_exists -v
```
Expected: FAIL

- [ ] **Step 3: Create the new merged file**

In `paperclips/fragments/shared/fragments/universal/wake-and-handoff-basics.md`:

```markdown
## Wake & handoff basics

Paperclip heartbeat is **disabled** company-wide. Agent wake is event-driven only:
assignee PATCH, @mention, posted comment. Watchdog (`services/watchdog`) is the
safety net for missed wake events — it does not replace correct handoff
discipline.

### On every wake

1. **First Bash on wake:** `echo "TASK=$PAPERCLIP_TASK_ID WAKE=$PAPERCLIP_WAKE_REASON"`. If `TASK` non-empty → `GET /api/issues/$PAPERCLIP_TASK_ID` + work. **Do NOT exit** on `inbox-lite=[]` if `TASK` is set.
2. `GET /api/agents/me` → any issue with `assigneeAgentId=me` and `in_progress`? → continue.
3. Comments / @mentions newer than `last_heartbeat_at`? → reply.

None of three → **exit immediately** with `No assignments, idle exit`.

### Cross-session memory — FORBIDDEN

If you "remember" past work at session start (*"let me continue where I left off"*) — that's claude CLI cache, not reality. Source of truth is the Paperclip API:

- Issue exists, assigned to you now → work
- Issue deleted / cancelled / done → don't resurrect, don't reopen
- Don't remember the issue ID? It doesn't exist — query the API.

### @-mentions: trailing space after name

Paperclip's parser captures trailing punctuation into the name (e.g. `@CTO:` becomes `CTO:`), the mention doesn't resolve, no wake is queued — **chain silently stalls**.

**Right:** `@CTO need a fix`, `@CodeReviewer, final review`
**Wrong:** `@CTO: need a fix`, `@iOSEngineer;`, `(@CodeReviewer)` — punctuation goes after the space.

### Handoff: PATCH + comment with @mention + STOP

Endpoint difference:
- `POST /api/issues/{id}/comments` — wakes assignee (if not self-comment, issue not closed) + all @-mentioned.
- `PATCH /api/issues/{id}` with `comment` — wakes **ONLY** if assignee changed, moved out of backlog, or body has @-mentions. No-mention comment on PATCH **won't wake assignee** → silent stall.

**Rule:** handoff comment always includes `@NextAgent` (trailing space). Covers both paths.

### Self-checkout on explicit handoff

Got an @-mention with explicit handoff phrase (`"your turn"`, `"pick it up"`, `"handing over"`) and sender already pushed → `POST /api/issues/{id}/checkout` yourself, don't wait for formal reassign.

### HTTP 409 on close/update — execution lock conflict

`PATCH /api/issues/{id}` → **409** = another agent's execution lock. Holder is in `issues.execution_agent_name_key`. Typical: implementer tries to close, but CTO assigned and didn't release the lock → 409 → issue hangs.

**Do:**
1. `GET /api/issues/{id}` → read `executionAgentNameKey`.
2. Comment to holder: `"@CTO release execution lock on [GIM-5], I'm ready to close"`.
3. Alternative — if holder unavailable, `PATCH ... assigneeAgentId=<original-assignee>` → originator closes.
4. Don't retry close with the same JWT — without release, 409 keeps coming.

**Don't:** Direct SQL `UPDATE`, or create new issue copy.

Release (from holder): `POST /api/issues/{id}/release` → lock released, assignee can close via PATCH.
```

- [ ] **Step 4: Add deprecation banners to source files**

In `paperclips/fragments/shared/fragments/heartbeat-discipline.md` — prepend:
```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Content split into `fragments/universal/wake-and-handoff-basics.md` (wake-discipline + handoff basics) and `fragments/handoff/phase-orchestration.md` (cto-only choreography).
> Heartbeat-config content removed entirely (paperclip heartbeat is OFF).
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 5: Run test, verify it passes**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_universal_wake_and_handoff_exists -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/universal/wake-and-handoff-basics.md fragments/heartbeat-discipline.md
git commit -m "feat(uaa-phase-a): create universal/wake-and-handoff-basics.md (merged from heartbeat + phase-handoff)"
cd -

git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (wake-and-handoff-basics) + test"
```

---

## Task 4: Create universal/escalation-board.md (rename)

**Files:**
- Create: `paperclips/fragments/shared/fragments/universal/escalation-board.md`
- Modify: `paperclips/fragments/shared/fragments/escalation-blocked.md` (deprecation banner)

- [ ] **Step 1: Add failing test**

Append to `paperclips/tests/test_phase_a_fragment_layout.py`:
```python
def test_universal_escalation_exists():
    p = SUBMODULE / "universal" / "escalation-board.md"
    assert p.is_file()
    text = p.read_text()
    assert "@Board" in text
    assert "blocker" in text.lower()
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_universal_escalation_exists -v
```

- [ ] **Step 3: Copy + rename + banner**

```bash
cd paperclips/fragments/shared
cp fragments/escalation-blocked.md fragments/universal/escalation-board.md
# Edit fragments/escalation-blocked.md — prepend deprecation banner (same pattern as Tasks 2-3)
```

Banner content:
```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Replaced by `fragments/universal/escalation-board.md`.
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 4: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_universal_escalation_exists -v
```

- [ ] **Step 5: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/universal/escalation-board.md fragments/escalation-blocked.md
git commit -m "feat(uaa-phase-a): rename escalation-blocked → universal/escalation-board"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (universal/escalation-board) + test"
```

---

## Task 5: Split git-workflow.md → 4 files in git/

**Files:**
- Create: `paperclips/fragments/shared/fragments/git/commit-and-push.md`
- Create: `paperclips/fragments/shared/fragments/git/merge-readiness.md`
- Create: `paperclips/fragments/shared/fragments/git/merge-state-decoder.md`
- Create: `paperclips/fragments/shared/fragments/git/release-cut.md`
- Modify: `paperclips/fragments/shared/fragments/git-workflow.md` (deprecation banner)

- [ ] **Step 1: Add 4 failing tests**

Append to `paperclips/tests/test_phase_a_fragment_layout.py`:
```python
def test_git_commit_and_push_exists():
    p = SUBMODULE / "git" / "commit-and-push.md"
    assert p.is_file()
    text = p.read_text()
    assert "fresh-fetch" in text or "git fetch" in text
    assert "force-with-lease" in text
    # Should NOT contain merge-readiness or release-cut content
    assert "release-cut" not in text.lower()
    assert "mergeStateStatus" not in text


def test_git_merge_readiness_exists():
    p = SUBMODULE / "git" / "merge-readiness.md"
    assert p.is_file()
    text = p.read_text()
    assert "merge-readiness" in text.lower() or "merge readiness" in text.lower()
    assert "release-cut" not in text.lower()


def test_git_merge_state_decoder_exists():
    p = SUBMODULE / "git" / "merge-state-decoder.md"
    assert p.is_file()
    text = p.read_text()
    for code in ["CLEAN", "DIRTY", "BEHIND", "BLOCKED"]:
        assert code in text, f"missing mergeStateStatus code {code}"


def test_git_release_cut_exists():
    p = SUBMODULE / "git" / "release-cut.md"
    assert p.is_file()
    text = p.read_text()
    assert "release-cut" in text.lower()
    assert "release-cut.yml" in text or "develop → main" in text
```

- [ ] **Step 2: Run tests, verify all 4 FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k git_
```
Expected: 4 FAILs.

- [ ] **Step 3: Read source git-workflow.md and split content into 4 files**

```bash
cd paperclips/fragments/shared
mkdir -p fragments/git
wc -l fragments/git-workflow.md  # current ~33 lines (small)
cat fragments/git-workflow.md
```

Note: `git-workflow.md` is only 33 lines currently. Most of the git/worktree/handoff content actually lives in **per-role inlining** today, not in the shared fragment. Phase A creates the 4 split files with **canonical, comprehensive content** (drawing from spec §3 in scope and reflecting current `paperclips/projects/uaudit/overlays/codex/_common.md` and CLAUDE.md branch-flow rules).

Create `paperclips/fragments/shared/fragments/git/commit-and-push.md`:
```markdown
## Git: commit & push (implementer / qa)

### Fresh-fetch on wake

Every wake, before any git operation:
```
git fetch --all --prune
```
Stale local refs cause silent merge conflicts on push.

### Branch naming

Feature branches: `feature/{{project.issue_prefix}}-N-<slug>` (e.g. `feature/IOS-12-add-swift-engineer`). Branch from `{{project.integration_branch}}` (default `develop`).

### Commit format

- Conventional commits: `type(scope): subject`
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
- Subject ≤ 70 chars, imperative mood ("add X" not "added X")
- Body explains WHY, not WHAT (the diff shows what)

### Push (your own feature branch only)

```
git push -u origin feature/{{project.issue_prefix}}-N-<slug>
```

Force-push: ONLY `--force-with-lease`, ONLY when you are the sole writer of the current phase. Bare `--force` is forbidden on every branch including features (eats teammate's commits).

`develop` and `main` reject force-push at branch protection (no exceptions, no admin override).

### Post-commit verification

Before `git push`, run the project's verification commands. For Python services:
```
uv run ruff check && uv run mypy src/ && uv run pytest
```

For other targets, see project AGENTS.md. Don't push commits that fail local checks — CI will block, and you'll loop.
```

Create `paperclips/fragments/shared/fragments/git/merge-readiness.md`:
```markdown
## Git: merge-readiness check (cto / reviewer)

Before approving or merging a PR, verify:

1. **CI green:** `gh pr checks <PR>` — all required checks pass (`lint`, `typecheck`, `test`, `docker-build`, `qa-evidence-present` per project rules in AGENTS.md).
2. **PR approved by CR:** GitHub PR review state = `APPROVED`.
3. **Branch up-to-date with target:** `mergeStateStatus` = `CLEAN` (see `merge-state-decoder.md`).
4. **No conflict markers in diff:** `gh pr diff <PR> | grep -E '^(<<<<<<<|=======|>>>>>>>)'` → empty.
5. **Spec/plan references valid:** if PR references `docs/superpowers/plans/...`, that file exists on the branch.

Self-approval forbidden — you cannot approve your own PR even if you are the only reviewer hired.
```

Create `paperclips/fragments/shared/fragments/git/merge-state-decoder.md`:
```markdown
## Git: mergeStateStatus decoder (cto / reviewer)

`gh pr view <PR> --json mergeStateStatus` returns one of:

| Status | Meaning | Action |
|---|---|---|
| `CLEAN` | Up-to-date, all checks green, ready to merge | Proceed with merge |
| `BEHIND` | Branch lags target — needs rebase/merge from target | Rebase or `gh pr update-branch` |
| `DIRTY` | Merge conflicts exist | Resolve in feature branch |
| `BLOCKED` | Required checks failing OR review missing OR branch protection veto | `gh pr checks` to see which check; if review missing, request it |
| `UNSTABLE` | Non-required checks failing (informational only) | Usually safe to merge; document why |
| `HAS_HOOKS` | Pre-merge hooks pending | Wait, then re-check |
| `BEHIND` + `BLOCKED` simultaneously | Multi-cause | Address whichever is fixable; recheck |

Never merge while status is `DIRTY`, `BLOCKED`, or `BEHIND`. `UNSTABLE` is judgment call — document the override in PR comment.
```

Create `paperclips/fragments/shared/fragments/git/release-cut.md`:
```markdown
## Git: release-cut procedure (cto only)

`develop` → `main` happens via `.github/workflows/release-cut.yml`. Two trigger modes:

1. **Label trigger:** add label `release-cut` to a merged develop PR. Workflow auto-runs.
2. **Manual trigger:** `gh workflow run release-cut.yml` from CTO's CLI.

Workflow steps (you do NOT script these — they run in CI):
- Open PR `develop → main` titled `release: <date> — develop → main`.
- Enable auto-merge with rebase strategy.
- After merge, push annotated tag `release-<date>-<sha>` to main.

**Iron rule:** no human pushes `main` directly. Branch protection enforces this — only `github-actions[bot]` may push, only via this workflow.

**Rollback:** if a release-cut breaks production, see `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` for revert procedure.
```

- [ ] **Step 4: Add deprecation banner to git-workflow.md**

```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Content split into `fragments/git/{commit-and-push,merge-readiness,merge-state-decoder,release-cut}.md`. New role-craft files include the relevant subset per profile.
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 5: Run all 4 tests, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k git_
```
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/git/ fragments/git-workflow.md
git commit -m "feat(uaa-phase-a): split git-workflow → git/{commit-and-push,merge-readiness,merge-state-decoder,release-cut}"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (git/ split) + tests"
```

---

## Task 6: Create worktree/active.md (rename + minor split)

**Files:**
- Create: `paperclips/fragments/shared/fragments/worktree/active.md`
- Modify: `paperclips/fragments/shared/fragments/worktree-discipline.md` (deprecation banner)

- [ ] **Step 1: Add failing test**

Append to `paperclips/tests/test_phase_a_fragment_layout.py`:
```python
def test_worktree_active_exists():
    p = SUBMODULE / "worktree" / "active.md"
    assert p.is_file()
    text = p.read_text()
    assert "worktree" in text.lower()
    assert "team-isolated" in text or "team isolated" in text or "shared" in text.lower()
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_worktree_active_exists -v
```

- [ ] **Step 3: Create new file**

```bash
cd paperclips/fragments/shared
mkdir -p fragments/worktree
cp fragments/worktree-discipline.md fragments/worktree/active.md
```

The current `worktree-discipline.md` is only 9 lines. Expand `worktree/active.md` to be canonical for implementer/reviewer/qa profiles:

```markdown
## Worktree discipline (implementer / reviewer / qa)

### Per-team isolated worktree

Each agent runs in its own workspace under `<team_workspace_root>/<AgentName>/workspace/`. This directory is the agent's `cwd`. **Do not** `cd` outside it for git operations — every commit/push originates from this worktree.

### Never remove shared workspace dirs

Workspaces under `<team_workspace_root>/<AgentName>/workspace/` are persistent: branch rotates per slice, the directory does not. **Never** `git worktree remove <AgentName>/workspace` — you'll wipe in-progress state of another agent if you happen to share the team_workspace_root.

### Cross-branch carry-over forbidden

Switching branches inside an agent worktree drags uncommitted changes across branches and contaminates the next slice. Discipline:
- Before switching branch: commit or stash.
- Before starting a new feature branch: `git status --short` must be clean.

### Operator vs production checkout

The `production_checkout` path (e.g. `/Users/Shared/Ios/Gimle-Palace`) is the iMac deploy target. Stay on `{{project.integration_branch}}` (typically `develop`) there — never check out feature branches in production_checkout. Discovered in GIM-48: feature checkout in production_checkout caused QA to test stale code.
```

- [ ] **Step 4: Add deprecation banner to original**

```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Replaced by `fragments/worktree/active.md` (expanded canonical content for implementer/reviewer/qa profiles).
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 5: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_worktree_active_exists -v
```

- [ ] **Step 6: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/worktree/ fragments/worktree-discipline.md
git commit -m "feat(uaa-phase-a): create worktree/active.md (expanded from worktree-discipline)"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (worktree/active) + test"
```

---

## Task 7: Create handoff/basics.md + handoff/phase-orchestration.md (split phase-handoff.md)

**Files:**
- Create: `paperclips/fragments/shared/fragments/handoff/basics.md`
- Create: `paperclips/fragments/shared/fragments/handoff/phase-orchestration.md`
- Modify: `paperclips/fragments/shared/fragments/phase-handoff.md` (deprecation banner)

- [ ] **Step 1: Add failing tests**

Append to `paperclips/tests/test_phase_a_fragment_layout.py`:
```python
def test_handoff_basics_exists():
    p = SUBMODULE / "handoff" / "basics.md"
    assert p.is_file()
    text = p.read_text()
    assert "PATCH" in text
    assert "@" in text  # mention syntax
    # Phase choreography MUST NOT be in basics
    assert "Phase 1.1" not in text
    assert "phase-handoff" not in text.lower() or "deprecated" in text.lower()


def test_handoff_phase_orchestration_exists():
    p = SUBMODULE / "handoff" / "phase-orchestration.md"
    assert p.is_file()
    text = p.read_text()
    # Phase choreography for CTO
    for phase in ["1.1", "1.2", "2", "3.1", "3.2", "4.1", "4.2"]:
        assert phase in text, f"missing phase {phase} in choreography"
    assert "CodeReviewer" in text
    assert "QAEngineer" in text or "qa" in text.lower()
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k handoff_
```

- [ ] **Step 3: Create both files**

`paperclips/fragments/shared/fragments/handoff/basics.md`:
```markdown
## Handoff basics

To pass work to another agent:

1. **PATCH the issue** to set `assigneeAgentId` to the recipient's UUID:
   ```
   PATCH /api/issues/{id}
   { "assigneeAgentId": "<recipient-uuid>", "status": "<new-status>" }
   ```
2. **Post a comment** with explicit @-mention (with trailing space, see `universal/wake-and-handoff-basics.md`):
   ```
   POST /api/issues/{id}/comments
   { "body": "@Recipient explanation. Your turn." }
   ```
3. **STOP.** Do not loop. Do not check status. Do not pre-emptively pick up follow-up work.

The combined PATCH + comment is the only reliable wake mechanism for the recipient.

### Cross-team handoff

If the recipient is on a different team (claude → codex or vice versa), use the same procedure. Both teams share the same paperclip company; UUIDs resolve regardless.

### Self-checkout on explicit handoff

If the sender's comment includes explicit handoff phrases (`"your turn"`, `"pick it up"`, `"handing over"`) AND assignee is already you, take the lock yourself: `POST /api/issues/{id}/checkout`.

### Watchdog safety net

If your handoff PATCH was authored by a SIGTERM'd run, paperclip may suppress the wake event. Watchdog Phase 2 (`services/watchdog`) detects stuck `in_review` assigneeAgentId+null-execution_run state and fires recovery. Don't rely on it as primary mechanism — author handoffs correctly.
```

`paperclips/fragments/shared/fragments/handoff/phase-orchestration.md`:
```markdown
## Phase orchestration (cto only)

CTO sequences a slice through these phases. Every phase ends with explicit handoff (per `handoff/basics.md`).

### Phase 1.1 — Formalize (CTO)

CTO verifies Board's spec+plan paths exist; swaps `{{project.issue_prefix}}-NN` placeholder for the real issue number; reassigns to CodeReviewer.

Handoff: `@CodeReviewer plan-first review of [{{project.issue_prefix}}-N]`.

### Phase 1.2 — Plan-first review (CodeReviewer)

CR validates every task in plan has concrete test+impl+commit; flags gaps. APPROVE → reassign to implementer.

Handoff (CR → implementer): `@<Implementer> plan APPROVED, begin implementation`.

### Phase 2 — Implement (PythonEngineer / MCPEngineer / etc.)

TDD through plan tasks on `feature/{{project.issue_prefix}}-N-<slug>`. Push frequently. When done, PR to `{{project.integration_branch}}`.

Handoff (implementer → CR): `@CodeReviewer mechanical review, PR <link>`.

### Phase 3.1 — Mechanical review (CodeReviewer)

CR pastes `uv run ruff check && uv run mypy src/ && uv run pytest` output (or project equivalent) AND `gh pr checks <PR>` output. APPROVE only with green CI proof. No "LGTM" rubber-stamps.

Handoff (CR → architect reviewer): `@OpusArchitectReviewer adversarial review, PR <link>`.

### Phase 3.2 — Adversarial review (OpusArchitectReviewer)

Find architectural problems, attack surfaces, missed edge cases. Findings addressed before Phase 4.

Handoff (Opus → QA): `@QAEngineer live smoke, PR <link>`.

### Phase 4.1 — Live smoke (QAEngineer)

On iMac (or production target). Real MCP tool call + CLI + direct invariant. Evidence comment authored by QAEngineer with concrete output (not paraphrased).

Handoff (QA → CTO): `@CTO QA evidence posted, ready to merge`.

### Phase 4.2 — Merge (CTO)

CTO merges via squash on green CI + APPROVED CR review + QA evidence. No admin override.

Post-merge handoff: `@CTO release-cut planned for <date>` (CTO of self) or no handoff (slice complete).

### Forbidden between phases

- `status=todo` between phases is forbidden. Always reassign explicitly.
- Skipping a reviewer (going straight from implementer to merge) is forbidden.
- Self-approval is forbidden (CR cannot APPROVE own implementation PR).
```

- [ ] **Step 4: Deprecation banner on phase-handoff.md**

```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Content split into `fragments/handoff/basics.md` (universal handoff mechanics) and `fragments/handoff/phase-orchestration.md` (cto-only choreography).
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k handoff_
```

- [ ] **Step 6: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/handoff/ fragments/phase-handoff.md
git commit -m "feat(uaa-phase-a): split phase-handoff → handoff/{basics,phase-orchestration}"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (handoff/ split) + tests"
```

---

## Task 8: Create code-review/approve.md + code-review/adversarial.md

**Files:**
- Create: `paperclips/fragments/shared/fragments/code-review/approve.md`
- Create: `paperclips/fragments/shared/fragments/code-review/adversarial.md`
- Modify: `paperclips/fragments/shared/fragments/compliance-enforcement.md` (deprecation banner — partial; some content moves to qa/)

- [ ] **Step 1: Add failing tests**

Append to `paperclips/tests/test_phase_a_fragment_layout.py`:
```python
def test_code_review_approve_exists():
    p = SUBMODULE / "code-review" / "approve.md"
    assert p.is_file()
    text = p.read_text()
    assert "APPROVE" in text
    assert "gh pr checks" in text
    assert "compliance" in text.lower() or "checklist" in text.lower()


def test_code_review_adversarial_exists():
    p = SUBMODULE / "code-review" / "adversarial.md"
    assert p.is_file()
    text = p.read_text()
    assert "adversarial" in text.lower() or "attack" in text.lower() or "edge" in text.lower()
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k code_review
```

- [ ] **Step 3: Create both files**

`paperclips/fragments/shared/fragments/code-review/approve.md`:
```markdown
## Code review: APPROVE format (reviewer)

To approve a PR, post a paperclip comment AND a GitHub PR review (both required for branch protection):

```
gh pr review <PR> --approve
```

Plus paperclip comment with **full compliance checklist + evidence**. No "LGTM" rubber-stamps.

### Mandatory checklist in APPROVE comment

```markdown
## Compliance Review — {{project.issue_prefix}}-N

| Check | Status | Evidence |
|---|---|---|
| `uv run ruff check` | ✅ | <paste last 5 lines> |
| `uv run mypy src/` | ✅ | <paste output> |
| `uv run pytest` | ✅ | <paste tail incl. summary> |
| `gh pr checks <PR>` | ✅ | <paste table> |
| Plan acceptance criteria covered | ✅ | <map each criterion to a test/file> |
| No silent scope reduction vs plan | ✅ | `git diff --name-only <base>...<head>` matches plan files |
| QA evidence present in PR body | ✅ | <quote `## QA Evidence` block> |

APPROVED. Reassigning to <next agent>.
```

### Forbidden APPROVE patterns

- "LGTM" without checklist.
- "Tests pass" without pasted output.
- Approving with `gh pr checks` showing red checks.
- Approving own PR (self-approval blocked at branch protection level too).
- Approving without `git diff --stat` against plan file count (silent scope reduction risk — codified after GIM-114).
```

`paperclips/fragments/shared/fragments/code-review/adversarial.md`:
```markdown
## Code review: adversarial review (OpusArchitectReviewer only)

After mechanical review (Phase 3.1) approves, OpusArchitectReviewer runs adversarial pass. Goal: find what mechanical review couldn't see.

### Attack surface checklist

For every PR:
1. **Race conditions:** any new shared state? Any async without explicit ordering? Any DB migrations + concurrent writes?
2. **Error paths:** every `try` has a matching test? Every fallback documented (silent fallback = bug, see `silent-failure-hunter` agent)?
3. **Bypass paths:** any `--no-verify`, `--force`, `dangerouslyBypassApprovalsAndSandbox`? If yes — justified in PR description?
4. **Wire contracts:** if MCP tools touched, every error envelope has `error_code` + caller-side test that asserts on it (not just `if isError: pass`)?
5. **Idempotency:** if the change writes state (Neo4j, Tantivy, paperclip API), is the operation safe to re-run? Does the PR include an idempotency test?
6. **Resource bounds:** any unbounded loop? Any subprocess without `timeout=`? Any list comprehension over potentially-huge input?
7. **Trust boundaries:** any new input from untrusted source (HTTP body, env var, file path)? Validated?
8. **Time bombs:** any hardcoded date, version, or commit SHA that will break in N months?

### Output

Either:
- **APPROVED — adversarial pass clean.** (rare) Reassign to QAEngineer.
- **CHANGES REQUESTED — N findings.** Post each finding as a separate comment with: location (`file:line`), severity (Block / Important / Nit), reproduction, suggested fix.

Adversarial findings are NOT advisory — implementer addresses each before Phase 4.
```

- [ ] **Step 4: Deprecation banner on compliance-enforcement.md**

```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Content split:
> - reviewer-side APPROVE format → `fragments/code-review/approve.md`
> - opus-side adversarial review → `fragments/code-review/adversarial.md`
> - qa-side smoke + evidence → `fragments/qa/smoke-and-evidence.md` (Task 9)
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 5: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k code_review
```

- [ ] **Step 6: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/code-review/ fragments/compliance-enforcement.md
git commit -m "feat(uaa-phase-a): split compliance-enforcement → code-review/{approve,adversarial}"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (code-review/ split) + tests"
```

---

## Task 9: Create qa/smoke-and-evidence.md

**Files:**
- Create: `paperclips/fragments/shared/fragments/qa/smoke-and-evidence.md`
- Modify: `paperclips/fragments/shared/fragments/test-design-discipline.md` (deprecation banner)

- [ ] **Step 1: Add failing test**

```python
def test_qa_smoke_and_evidence_exists():
    p = SUBMODULE / "qa" / "smoke-and-evidence.md"
    assert p.is_file()
    text = p.read_text()
    assert "QA Evidence" in text or "qa evidence" in text.lower()
    assert "iMac" in text or "production" in text.lower()
    assert "smoke" in text.lower()
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_qa_smoke_and_evidence_exists -v
```

- [ ] **Step 3: Create the file**

```markdown
## QA: smoke + evidence (qa)

### Live smoke checklist (Phase 4.1)

On the production target (iMac for gimle, dev Mac for codex-only uaudit):

1. **Restore production checkout to `{{project.integration_branch}}`** before any test:
   ```
   cd {{paths.production_checkout}} && git fetch && git checkout {{project.integration_branch}} && git pull --ff-only
   ```
   Codified after GIM-48: feature-branch checkout in production_checkout caused stale-code QA pass.
2. **Run real MCP tool against real palace-mcp/{{mcp.service_name}}** (not testcontainers):
   - For new extractor: `palace.ingest.run_extractor(name="<new>", project="<test-project>")`
   - For new tool: invoke directly via paperclip MCP client
3. **Verify output via direct query** (Cypher for Neo4j, jq for JSON, sqlite3 for SQL):
   - Don't trust the tool's success envelope — query the actual side effect.
4. **CLI invariant:** if the change touches CLI, run real CLI command and capture full stdout/stderr.

### Evidence format (QA Evidence comment)

PR body must contain `## QA Evidence` section before merge. CI check `qa-evidence-present` enforces this (grep-only — content quality is YOUR responsibility, not CI's).

```markdown
## QA Evidence

**Smoke run on:** iMac, 2026-05-15T14:23Z, on commit <SHA>

**1. Extractor invocation:**
```
$ palace.ingest.run_extractor(name="my_extractor", project="gimle")
{"ok": true, "run_id": "abc-...", "duration_ms": 1247, "nodes_written": 42, ...}
```

**2. Direct Cypher verification:**
```
MATCH (n:NewNodeType) RETURN count(n)
→ 42
```

**3. CLI smoke:**
```
$ ./scripts/my-new-cli --target gimle
... actual output ...
```

**4. Negative test (handles error correctly):**
```
$ palace.ingest.run_extractor(name="my_extractor", project="nonexistent")
{"ok": false, "error_code": "project_not_registered", ...}
```
```

### Forbidden evidence patterns (codified after GIM-127)

- Numbers exactly matching dev-Mac fixture oracle while claiming iMac smoke.
- Paraphrasing tool output ("returned successfully") instead of pasting envelope.
- Skipping negative test ("happy path passes" only).
- Evidence authored on dev Mac when PR claims iMac smoke (verify host in evidence header).
- Reusing evidence from a different PR (always include current PR's commit SHA in evidence).

### Restore checkout post-smoke

After smoke completes, restore `{{paths.production_checkout}}` to `{{project.integration_branch}}` (not the feature branch you tested) before handoff to CTO. Otherwise next session starts on stale feature branch.
```

- [ ] **Step 4: Deprecation banner on test-design-discipline.md**

```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** QA-relevant test-design content moved to `fragments/qa/smoke-and-evidence.md` (smoke + evidence). General test-design principles will be embedded in role-craft files (`roles/qa-engineer.md` etc.) where applicable.
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 5: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py::test_qa_smoke_and_evidence_exists -v
```

- [ ] **Step 6: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/qa/ fragments/test-design-discipline.md
git commit -m "feat(uaa-phase-a): create qa/smoke-and-evidence.md"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (qa/) + test"
```

---

## Task 10: Create pre-work/ trio (codebase-memory-first / sequential-thinking / existing-field-semantics)

**Files:**
- Create: `paperclips/fragments/shared/fragments/pre-work/codebase-memory-first.md`
- Create: `paperclips/fragments/shared/fragments/pre-work/sequential-thinking.md`
- Create: `paperclips/fragments/shared/fragments/pre-work/existing-field-semantics.md`
- Modify: `paperclips/fragments/shared/fragments/pre-work-discovery.md` (deprecation banner)

- [ ] **Step 1: Add 3 failing tests**

```python
def test_prework_codebase_memory_first_exists():
    p = SUBMODULE / "pre-work" / "codebase-memory-first.md"
    assert p.is_file()
    text = p.read_text()
    assert "search_graph" in text or "codebase-memory" in text


def test_prework_sequential_thinking_exists():
    p = SUBMODULE / "pre-work" / "sequential-thinking.md"
    assert p.is_file()
    text = p.read_text()
    assert "sequential-thinking" in text or "sequential_thinking" in text


def test_prework_existing_field_semantics_exists():
    p = SUBMODULE / "pre-work" / "existing-field-semantics.md"
    assert p.is_file()
    text = p.read_text()
    assert "rename" in text.lower() or "field" in text.lower() or "schema" in text.lower()
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k prework
```

- [ ] **Step 3: Create files**

`pre-work/codebase-memory-first.md`:
```markdown
## Pre-work: codebase-memory first

Before reading any code file, query the codebase-memory MCP graph:

- `search_graph(name_pattern=...)` to find functions/classes/routes by symbol name
- `trace_path(function_name, mode=calls)` for call chains
- `get_code_snippet(qualified_name)` to read source (NOT `cat`)
- `query_graph(...)` for complex Cypher patterns

Fall back to `Grep`/`Read` only when the graph lacks the symbol (text-only content, config files, recent commits). If the project is unindexed, run `index_repository` first.

Reading files cold without graph context invites missing call sites and dead-code mistakes.
```

`pre-work/sequential-thinking.md`:
```markdown
## Pre-work: sequential-thinking

For tasks with 3+ logical steps, branching paths, or unclear dependencies, invoke `mcp__sequential-thinking__sequentialthinking` BEFORE writing code or tests:

- Decompose the task into ordered steps.
- Surface assumptions explicitly.
- Identify which steps can run in parallel vs. must serialize.

Skip for trivial mechanical edits (rename, format, single-line fix). Use for: new feature, refactor across files, anything touching async/state machines.
```

`pre-work/existing-field-semantics.md`:
```markdown
## Pre-work: existing field semantics

Before renaming, removing, or repurposing a field on an existing data structure (Pydantic model, Cypher node label, JSON schema, env var):

1. **Find all readers** via `search_graph` + `trace_path(... mode=data_flow)`.
2. **Find all writers** (often more than readers — backfill scripts, migrations, fixtures).
3. **Document the migration** in PR description: old → new mapping, deprecation window, rollback.
4. **Add backwards-compat shim** if external API surface (MCP tool args, REST endpoint params) — at least one release cycle.

Renaming a field that's referenced in saved Neo4j data without migration loses that data. Renaming an MCP tool arg without shim breaks every caller silently.
```

- [ ] **Step 4: Deprecation banner**

`pre-work-discovery.md`:
```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Content split into `fragments/pre-work/{codebase-memory-first,sequential-thinking,existing-field-semantics}.md`.
> Will be removed at UAA cleanup gate.
```

- [ ] **Step 5: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k prework
```

- [ ] **Step 6: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/pre-work/ fragments/pre-work-discovery.md
git commit -m "feat(uaa-phase-a): split pre-work-discovery → pre-work/{cm-first,sequential,field-semantics}"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (pre-work/ trio) + tests"
```

---

## Task 11: Create plan/producer.md + plan/review.md (rename)

**Files:**
- Create: `paperclips/fragments/shared/fragments/plan/producer.md`
- Create: `paperclips/fragments/shared/fragments/plan/review.md`
- Modify: `paperclips/fragments/shared/fragments/plan-first-producer.md` (banner)
- Modify: `paperclips/fragments/shared/fragments/plan-first-review.md` (banner)

- [ ] **Step 1: Add failing tests**

```python
def test_plan_producer_exists():
    p = SUBMODULE / "plan" / "producer.md"
    assert p.is_file()


def test_plan_review_exists():
    p = SUBMODULE / "plan" / "review.md"
    assert p.is_file()
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k plan_
```

- [ ] **Step 3: Copy + rename**

```bash
cd paperclips/fragments/shared
mkdir -p fragments/plan
cp fragments/plan-first-producer.md fragments/plan/producer.md
cp fragments/plan-first-review.md fragments/plan/review.md
```

Add deprecation banners to originals (same pattern as previous tasks).

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v -k plan_
```

- [ ] **Step 5: Commit**

```bash
cd paperclips/fragments/shared
git add fragments/plan/ fragments/plan-first-producer.md fragments/plan-first-review.md
git commit -m "feat(uaa-phase-a): rename plan-first-{producer,review} → plan/"
cd -
git add paperclips/fragments/shared paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "feat(uaa-phase-a): bump shared-fragments (plan/) + tests"
```

---

## Task 12: Hierarchy completeness sweep test

**Files:**
- Modify: `paperclips/tests/test_phase_a_fragment_layout.py` (add summary tests)

- [ ] **Step 1: Add comprehensive layout test**

Append to `paperclips/tests/test_phase_a_fragment_layout.py`:
```python
EXPECTED_HIERARCHY = {
    "universal": {"karpathy.md", "wake-and-handoff-basics.md", "escalation-board.md"},
    "git": {"commit-and-push.md", "merge-readiness.md", "merge-state-decoder.md", "release-cut.md"},
    "worktree": {"active.md"},
    "handoff": {"basics.md", "phase-orchestration.md"},
    "code-review": {"approve.md", "adversarial.md"},
    "qa": {"smoke-and-evidence.md"},
    "pre-work": {"codebase-memory-first.md", "sequential-thinking.md", "existing-field-semantics.md"},
    "plan": {"producer.md", "review.md"},
}


def test_hierarchy_complete():
    for subdir, expected_files in EXPECTED_HIERARCHY.items():
        actual = {p.name for p in (SUBMODULE / subdir).glob("*.md")}
        missing = expected_files - actual
        assert not missing, f"{subdir}/ missing: {missing}"


def test_no_orphan_files_in_subdirs():
    for subdir, expected_files in EXPECTED_HIERARCHY.items():
        actual = {p.name for p in (SUBMODULE / subdir).glob("*.md")}
        unexpected = actual - expected_files
        assert not unexpected, f"{subdir}/ has unexpected: {unexpected}"


def test_deprecated_files_have_banner():
    deprecated = [
        "karpathy-discipline.md", "heartbeat-discipline.md", "escalation-blocked.md",
        "git-workflow.md", "worktree-discipline.md", "phase-handoff.md",
        "compliance-enforcement.md", "test-design-discipline.md", "pre-work-discovery.md",
        "plan-first-producer.md", "plan-first-review.md",
    ]
    for fname in deprecated:
        p = SUBMODULE / fname
        text = p.read_text()
        assert "DEPRECATED" in text, f"{fname} missing deprecation banner"
        assert "UAA Phase A" in text, f"{fname} banner doesn't reference UAA Phase A"


def test_unchanged_files_preserved():
    """cto-no-code-ban.md and language.md stay as-is in Phase A."""
    for fname in ["cto-no-code-ban.md", "language.md"]:
        p = SUBMODULE / fname
        assert p.is_file()
        text = p.read_text()
        assert "DEPRECATED" not in text, f"{fname} should NOT be deprecated"
```

- [ ] **Step 2: Run all tests, verify all PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_fragment_layout.py -v
```
Expected: ~16 PASS, 0 FAIL.

- [ ] **Step 3: Commit**

```bash
git add paperclips/tests/test_phase_a_fragment_layout.py
git commit -m "test(uaa-phase-a): hierarchy completeness sweep"
```

---

## Task 13: Build-compat test — verify no behavior change for existing role files

**Files:**
- Create: `paperclips/tests/test_phase_a_build_compat.py`

The deprecated original files are still present, so existing role files (which reference `<!-- @include fragments/karpathy-discipline.md -->` etc.) MUST still build to byte-identical output as the baseline from Task 1.

- [ ] **Step 1: Create the compat test**

```python
# paperclips/tests/test_phase_a_build_compat.py
"""Phase A: verify no build-output drift since baseline.

Existing role files (paperclips/roles/*.md) still reference the OLD fragment
paths via <!-- @include fragments/<name>.md -->. Those old files are still
present (with deprecation banners) — banners are added BEFORE the original
content, so when builder includes them, output gains the banner block at the
top of each fragment. This shifts SHAs.

We assert that ALL OLD fragments still resolve and the only diff vs baseline
is the deprecation-banner addition at predictable line ranges.
"""
import hashlib
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _build(project, target):
    subprocess.run(
        ["./paperclips/build.sh", "--project", project, "--target", target],
        cwd=REPO, check=True, capture_output=True,
    )


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_all_projects_still_build():
    """Builder doesn't crash; all old fragment includes still resolve."""
    for project, target in [
        ("gimle", "claude"), ("gimle", "codex"),
        ("trading", "claude"), ("trading", "codex"),
        ("uaudit", "codex"),
    ]:
        _build(project, target)


def test_baseline_compat_drift_only_from_banners():
    """Diff vs baseline limited to deprecation-banner additions."""
    baseline = REPO / "paperclips" / "tests" / "baseline" / "baseline-shas.txt"
    if not baseline.exists():
        # baseline file is gitignored; only run when present locally
        import pytest
        pytest.skip("baseline-shas.txt missing — run Task 1 first")

    # Re-build all
    for project, target in [
        ("gimle", "claude"), ("gimle", "codex"),
        ("trading", "claude"), ("trading", "codex"),
        ("uaudit", "codex"),
    ]:
        _build(project, target)

    # For each baseline entry, compute current SHA. Drift expected = banner.
    drifts = []
    for line in baseline.read_text().strip().split("\n"):
        sha_old, path = line.split("  ", 1)
        path = REPO / path
        if not path.exists():
            drifts.append(f"missing: {path}")
            continue
        sha_new = _sha256(path)
        if sha_new == sha_old:
            continue  # unchanged
        # Drift exists. Verify it's banner-only by checking content includes both old-text body + banner.
        text = path.read_text()
        if "DEPRECATED (UAA Phase A" not in text:
            drifts.append(f"unexpected drift (no banner) in {path}")
    assert not drifts, "\n".join(drifts)
```

- [ ] **Step 2: Run, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_build_compat.py -v
```
Expected: 2 PASS (all_projects_still_build PASS; baseline_compat may SKIP if baseline file absent).

- [ ] **Step 3: If baseline present, manually inspect 3 sample diffs**

```bash
# Pick one agent from each project
diff paperclips/tests/baseline/dist-snapshot/dist/cto.md paperclips/dist/cto.md | head -30
diff paperclips/tests/baseline/dist-snapshot/dist/trading/codex/CTO.md paperclips/dist/trading/codex/CTO.md | head -30
diff paperclips/tests/baseline/dist-snapshot/dist/uaudit/codex/UWICTO.md paperclips/dist/uaudit/codex/UWICTO.md | head -30
```
Expected: each diff shows the deprecation banner block(s) as the only addition. If unrelated content shifted, investigate.

- [ ] **Step 4: Commit**

```bash
git add paperclips/tests/test_phase_a_build_compat.py
git commit -m "test(uaa-phase-a): build-compat drift check (banner-only allowed)"
```

---

## Task 14: Role-split scaffolding — create roles/legacy/ + roles-codex/legacy/ subdirs

**Files:**
- Create: `paperclips/roles/legacy/.gitkeep`
- Create: `paperclips/roles-codex/legacy/.gitkeep`

- [ ] **Step 1: Create directories**

```bash
mkdir -p paperclips/roles/legacy paperclips/roles-codex/legacy
touch paperclips/roles/legacy/.gitkeep paperclips/roles-codex/legacy/.gitkeep
```

- [ ] **Step 2: Commit empty dirs (gitkeep)**

```bash
git add paperclips/roles/legacy/.gitkeep paperclips/roles-codex/legacy/.gitkeep
git commit -m "chore(uaa-phase-a): scaffold roles/legacy/ + roles-codex/legacy/ subdirs"
```

---

## Task 15: Role-split — `roles/cto.md` (74 lines mixed → slim craft + legacy copy)

**Files:**
- Create: `paperclips/roles/legacy/cto.md` (copy of current with banner)
- Modify: `paperclips/roles/cto.md` (rewrite as slim craft)
- Test: `paperclips/tests/test_phase_a_role_craft.py`

- [ ] **Step 1: Create test file with first failing test**

```python
# paperclips/tests/test_phase_a_role_craft.py
"""Phase A.1: verify role-split produces slim craft files + legacy banners."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROLES = REPO / "paperclips" / "roles"
ROLES_CODEX = REPO / "paperclips" / "roles-codex"


def test_legacy_cto_exists_with_banner():
    p = ROLES / "legacy" / "cto.md"
    assert p.is_file()
    text = p.read_text()
    assert "DEPRECATED" in text
    assert "UAA Phase A" in text


def test_new_cto_is_slim_craft():
    p = ROLES / "cto.md"
    assert p.is_file()
    text = p.read_text()
    lines = text.count("\n")
    assert lines <= 100, f"new roles/cto.md too large ({lines} lines) — should be slim craft only"
    # Must NOT contain phase-orchestration content (that's in fragments/handoff/phase-orchestration.md)
    assert "Phase 1.1" not in text, "phase choreography should be in fragment, not role-craft"
    assert "Phase 4.2" not in text
    # Must contain craft markers
    assert "CTO" in text or "Chief" in text
```

- [ ] **Step 2: Verify FAIL (3 failures)**

```bash
python3 -m pytest paperclips/tests/test_phase_a_role_craft.py -v
```

- [ ] **Step 3: Copy current cto.md to legacy/, add banner**

```bash
cp paperclips/roles/cto.md paperclips/roles/legacy/cto.md
```

Edit `paperclips/roles/legacy/cto.md` — prepend at top:
```markdown
> **DEPRECATED (UAA Phase A, 2026-05).** Replaced by:
> - `paperclips/roles/cto.md` — slim craft-only file (identity, area, MCP, anti-patterns)
> - `profile: cto` — capability composition (phase-orchestration, merge-gate, plan-producer, etc.)
>
> This file kept until UAA cleanup gate. Do not include in new manifests; do not edit (changes will be lost).
```

- [ ] **Step 4: Rewrite paperclips/roles/cto.md as slim craft**

Replace entire content of `paperclips/roles/cto.md` with:

```markdown
---
target: claude
role_id: claude:cto
family: cto
---

# CTO — {{project.display_name}}

> Project tech rules in `AGENTS.md` (auto-loaded). Universal layer + capability profile composed by builder. Below: role-craft only.

## Role

You are CTO. You own technical strategy, architecture, decomposition.

**You do NOT write code.** No exceptions. Use `Edit`/`Write` only on `docs/superpowers/**` and `docs/runbooks/**` for Phase 1.1 mechanical work (plan renames, `{{project.issue_prefix}}-N` placeholder swaps).

If you catch yourself opening `Edit`/`Write` on files under `services/`, `tests/`, `src/`, or anywhere outside `docs/`, `paperclips/projects/<key>/`, `paperclips/roles/`: **stop**. Comment: *"Caught myself trying to write code outside allowed scope. Block me or give explicit permission."*

If a needed role isn't hired → `"Blocked until {role} is hired. Escalating to Board."` + @Board. Don't write code "while no one's around".

<!-- @include fragments/cto-no-code-ban.md -->

## Area of responsibility

- Architecture decisions, technology choices, decomposition into slices
- Plan-first review (Phase 1.2): validate every task has concrete test+impl+commit
- Merge gate (Phase 4.2): squash-merge to {{project.integration_branch}} on green CI + APPROVED CR + QA evidence
- Release-cut to main when slice complete
- Cross-team coordination (claude ↔ codex if both teams active)

## Delegation

| Task type | Owner |
|---|---|
| Python services (Graphiti, {{mcp.service_name}}, extractors, telemetry) | **PythonEngineer** |
| Docker Compose, Justfile, install scripts, networking, secrets, healthchecks | **InfraEngineer** |
| MCP protocol design, {{mcp.service_name}} API contracts, client distribution | **MCPEngineer** |
| Research: library updates, MCP spec, Neo4j patterns, {{domain.target_name}} planning | **ResearchAgent** |
| PR review (code + plans), architecture compliance | **CodeReviewer** |
| Integration tests via testcontainers + docker-compose smoke | **QAEngineer** |
| Technical writing: install guides, runbooks, README, man-pages | **TechnicalWriter** |

Run independent subtasks in parallel when possible; don't serialize.

## MCP / Tool scope

Required MCP servers (from project AGENTS.md): {{mcp.base_required | join(", ")}}.

Read-only tools allowed: `palace.git.*`, `palace.code.*`, `palace.memory.*`, codebase-memory, serena (read-only), GitHub (read-only).

Write-tools allowed: `gh pr comment`, `gh issue comment`, `paperclip` API for assignment changes. NOT `gh pr merge` (merge is Phase 4.2 — done after CI green + reviews + QA).

## Anti-patterns

- **Writing code "to unblock the team"** — blocked, ask Board.
- **Approving own plan** — Phase 1.2 is CR's gate, not yours.
- **Skipping Phase 3.2 adversarial review** when slice is "small" — small slices ship the worst bugs.
- **Merging without QA evidence** — `qa-evidence-present` CI check is grep-only; CONTENT quality is your responsibility.
- **Direct push to {{project.integration_branch}}** — branch protection blocks; trying = noise.
```

- [ ] **Step 5: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_role_craft.py -v
```

- [ ] **Step 6: Commit**

```bash
git add paperclips/roles/cto.md paperclips/roles/legacy/cto.md paperclips/tests/test_phase_a_role_craft.py
git commit -m "feat(uaa-phase-a): split roles/cto.md → slim craft + legacy/cto.md"
```

---

## Task 16: Role-split — `roles/code-reviewer.md` (167 lines, largest mixed file)

**Files:**
- Create: `paperclips/roles/legacy/code-reviewer.md`
- Modify: `paperclips/roles/code-reviewer.md` (rewrite as slim craft)

This is the heaviest role-split. Current `code-reviewer.md` is 167 lines — mixes craft + APPROVE-format + adversarial-review + ci-verification. Most of those move to fragments (already done in Tasks 8-9). Slim version keeps craft only.

- [ ] **Step 1: Add failing test**

Append to `paperclips/tests/test_phase_a_role_craft.py`:
```python
def test_legacy_code_reviewer_exists():
    p = ROLES / "legacy" / "code-reviewer.md"
    assert p.is_file()
    assert "DEPRECATED" in p.read_text()


def test_new_code_reviewer_is_slim():
    p = ROLES / "code-reviewer.md"
    assert p.is_file()
    text = p.read_text()
    lines = text.count("\n")
    assert lines <= 80, f"new roles/code-reviewer.md too large ({lines} lines)"
    # Approve format moved to fragments/code-review/approve.md
    assert "## Compliance Review" not in text
    assert "uv run ruff check" not in text  # that's in fragment now
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_a_role_craft.py -v -k code_reviewer
```

- [ ] **Step 3: Copy + banner + rewrite**

```bash
cp paperclips/roles/code-reviewer.md paperclips/roles/legacy/code-reviewer.md
```

Add banner to `paperclips/roles/legacy/code-reviewer.md` (same pattern as Task 15).

Replace `paperclips/roles/code-reviewer.md` with slim craft:

```markdown
---
target: claude
role_id: claude:code-reviewer
family: reviewer
---

# CodeReviewer — {{project.display_name}}

> Project tech rules in `AGENTS.md`. Universal + reviewer profile composed by builder. Below: craft only.

## Role

You are the project's code reviewer. You gate every PR before merge.

You do NOT write production code. You do write comments, suggested-edit blocks, and (rarely) test additions to prove a defect.

## Area of responsibility

- **Phase 1.2 — plan-first review:** validate every task has concrete test+impl+commit; flag gaps; APPROVE → reassign to implementer.
- **Phase 3.1 — mechanical review:** verify CI green (`gh pr checks`), local linters/tests pass, plan acceptance criteria covered, no silent scope reduction. APPROVE format from `fragments/code-review/approve.md`.
- **Re-review on changes:** every push to a PR you reviewed → re-check.

## MCP / Tool scope

Read tools: codebase-memory, serena (read-only), GitHub (read), `palace.code.*`, `palace.git.*`.

Write tools: `gh pr review`, `gh pr comment`, paperclip API (assignment changes only — never merge).

## Anti-patterns

- **"LGTM" without checklist** — APPROVE comment must paste linter/test/CI output. Codified after GIM-127 where CR claimed "17/17 tests pass" while CI was red.
- **Reviewing without `git diff --name-only` against plan** — silent scope reduction (PE quietly cuts files) is invisible without this. Codified in GIM-114.
- **Self-approving** — branch protection blocks technically; trying signals confusion.
- **Approving when adversarial review (Phase 3.2) is open** — wait for OpusReviewer's findings to be addressed.
- **Re-reviewing only the diff** — sometimes the bug is what was DELETED. Read full file context for any non-trivial change.
```

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_a_role_craft.py -v -k code_reviewer
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/roles/code-reviewer.md paperclips/roles/legacy/code-reviewer.md paperclips/tests/test_phase_a_role_craft.py
git commit -m "feat(uaa-phase-a): split roles/code-reviewer.md → slim craft + legacy/"
```

---

## Tasks 17–24: Repeat role-split for remaining 10 claude roles

Same pattern as Tasks 15–16 for each of:
- `python-engineer.md` (80 → ~60 slim)
- `mcp-engineer.md` (97 → ~65 slim)
- `infra-engineer.md` (98 → ~65 slim)
- `blockchain-engineer.md` (82 → ~60 slim)
- `qa-engineer.md` (105 → ~70 slim)
- `security-auditor.md` (111 → ~70 slim)
- `auditor.md` (81 → ~55 slim)
- `research-agent.md` (94 → ~60 slim)
- `technical-writer.md` (81 → ~55 slim)
- `opus-architect-reviewer.md` (128 → ~70 slim)

For EACH role:

- [ ] **Step 1**: Add `test_legacy_<role>_exists_with_banner` + `test_new_<role>_is_slim` to `test_phase_a_role_craft.py`. Verify FAIL.
- [ ] **Step 2**: `cp paperclips/roles/<role>.md paperclips/roles/legacy/<role>.md`; add banner.
- [ ] **Step 3**: Rewrite `paperclips/roles/<role>.md` as slim craft (drop all `<!-- @include -->` references — capability now comes from profile composition; keep only identity, area, MCP/tool scope, anti-patterns).
- [ ] **Step 4**: Verify PASS.
- [ ] **Step 5**: `git add` both files + test; commit `feat(uaa-phase-a): split roles/<role>.md → slim craft + legacy/`.

**Slim file size targets** (assert in test):
- `python-engineer.md`: ≤ 70 lines
- `mcp-engineer.md`: ≤ 75 lines
- `infra-engineer.md`: ≤ 75 lines
- `blockchain-engineer.md`: ≤ 70 lines
- `qa-engineer.md`: ≤ 80 lines
- `security-auditor.md`: ≤ 75 lines
- `auditor.md`: ≤ 65 lines
- `research-agent.md`: ≤ 70 lines
- `technical-writer.md`: ≤ 65 lines
- `opus-architect-reviewer.md`: ≤ 80 lines

---

## Tasks 25–36: Repeat for 12 codex roles in `roles-codex/`

Same pattern as Tasks 15–24, but for `paperclips/roles-codex/cx-*.md` files. Slim copies go to `paperclips/roles-codex/cx-<role>.md`; legacy copies to `paperclips/roles-codex/legacy/cx-<role>.md`.

12 codex roles to migrate:
- `cx-cto.md`, `cx-code-reviewer.md`, `cx-python-engineer.md`, `cx-mcp-engineer.md`, `cx-infra-engineer.md`, `cx-blockchain-engineer.md`, `cx-qa-engineer.md`, `cx-security-auditor.md`, `cx-auditor.md`, `cx-research-agent.md`, `cx-technical-writer.md`, `codex-architect-reviewer.md`

Per-role: failing test → copy + banner → slim rewrite → passing test → commit.

---

## Task 37: Final phase-A acceptance test

**Files:**
- Create: `paperclips/tests/test_phase_a_acceptance.py`

- [ ] **Step 1: Create acceptance suite**

```python
# paperclips/tests/test_phase_a_acceptance.py
"""Phase A acceptance: all targets met, ready for Phase B."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUBMODULE = REPO / "paperclips" / "fragments" / "shared" / "fragments"
ROLES = REPO / "paperclips" / "roles"
ROLES_CODEX = REPO / "paperclips" / "roles-codex"

CLAUDE_ROLES = [
    "cto.md", "code-reviewer.md", "python-engineer.md", "mcp-engineer.md",
    "infra-engineer.md", "blockchain-engineer.md", "qa-engineer.md",
    "security-auditor.md", "auditor.md", "research-agent.md",
    "technical-writer.md", "opus-architect-reviewer.md",
]
CODEX_ROLES = [
    "cx-cto.md", "cx-code-reviewer.md", "cx-python-engineer.md", "cx-mcp-engineer.md",
    "cx-infra-engineer.md", "cx-blockchain-engineer.md", "cx-qa-engineer.md",
    "cx-security-auditor.md", "cx-auditor.md", "cx-research-agent.md",
    "cx-technical-writer.md", "codex-architect-reviewer.md",
]

SIZE_LIMIT_PER_ROLE = 100  # lines


def test_all_24_roles_have_legacy_copies():
    for r in CLAUDE_ROLES:
        assert (ROLES / "legacy" / r).is_file(), f"missing legacy: {r}"
    for r in CODEX_ROLES:
        assert (ROLES_CODEX / "legacy" / r).is_file(), f"missing legacy: {r}"


def test_all_24_legacy_have_banners():
    for r in CLAUDE_ROLES + CODEX_ROLES:
        legacy = (ROLES if r in CLAUDE_ROLES else ROLES_CODEX) / "legacy" / r
        assert "UAA Phase A" in legacy.read_text(), f"banner missing: {legacy}"


def test_all_24_new_roles_are_slim():
    for r in CLAUDE_ROLES + CODEX_ROLES:
        new = (ROLES if r in CLAUDE_ROLES else ROLES_CODEX) / r
        lines = new.read_text().count("\n")
        assert lines <= SIZE_LIMIT_PER_ROLE, f"{new}: {lines} lines (limit {SIZE_LIMIT_PER_ROLE})"


def test_no_new_role_includes_phase_orchestration_directly():
    """Capability content must come from profile, not be inlined in new craft files."""
    for r in CLAUDE_ROLES + CODEX_ROLES:
        new = (ROLES if r in CLAUDE_ROLES else ROLES_CODEX) / r
        text = new.read_text()
        assert "Phase 1.1" not in text, f"phase choreography leaked into {new}"
        assert "Phase 4.2" not in text, f"phase choreography leaked into {new}"


def test_fragment_hierarchy_complete():
    expected_dirs = ["universal", "git", "worktree", "handoff", "code-review", "qa", "pre-work", "plan"]
    for d in expected_dirs:
        assert (SUBMODULE / d).is_dir(), f"missing fragment dir: {d}"
        assert any((SUBMODULE / d).glob("*.md")), f"empty fragment dir: {d}"


def test_total_new_fragment_count():
    new_files = []
    for d in ["universal", "git", "worktree", "handoff", "code-review", "qa", "pre-work", "plan"]:
        new_files.extend((SUBMODULE / d).glob("*.md"))
    # Per spec §4.1: 16 files total
    assert len(new_files) == 16, f"expected 16 new fragment files, got {len(new_files)}: {[f.name for f in new_files]}"
```

- [ ] **Step 2: Run, verify PASS (all 6 tests)**

```bash
python3 -m pytest paperclips/tests/test_phase_a_acceptance.py -v
```

- [ ] **Step 3: Run all Phase A tests together**

```bash
python3 -m pytest paperclips/tests/test_phase_a_*.py -v
```
Expected: ~25–30 PASS, 0 FAIL.

- [ ] **Step 4: Commit**

```bash
git add paperclips/tests/test_phase_a_acceptance.py
git commit -m "test(uaa-phase-a): acceptance suite (16 fragments + 24 role-splits + size limits)"
```

---

## Task 38: Update spec changelog + open Phase A PR

**Files:**
- Modify: `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` (add Phase A completion note)

- [ ] **Step 1: Append to spec changelog**

Edit the spec rev3 changelog section, add at top:

```markdown
**Phase A complete (YYYY-MM-DD):**
- Fragment hierarchy created (16 files in 8 subdirs).
- 24 role files split (12 claude + 12 codex) — slim craft files in original paths, legacy copies under `roles/legacy/` + `roles-codex/legacy/` with deprecation banners.
- All 11 deprecated shared fragments retain content with banners (builder back-compat preserved until Phase B).
- Build-compat tests pass: existing role files still produce equivalent output (banner-only drift).
- Acceptance suite (`test_phase_a_acceptance.py`) green.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md
git commit -m "docs(uaa-phase-a): mark Phase A complete in spec changelog"
```

- [ ] **Step 3: Push + open PR**

```bash
git push origin feature/spec-uniform-agent-assembly
gh pr view 184  # if extending the spec PR
# OR if Phase A is its own PR:
git checkout -b feature/uaa-phase-a-fragment-refactor
git push -u origin feature/uaa-phase-a-fragment-refactor
gh pr create --title "feat(uaa-phase-a): fragment library refactor + role-split (hybrid)" \
  --body-file docs/superpowers/plans/2026-05-15-uaa-phase-A-fragment-refactor.md
```

(Operator decides: extend spec PR or new PR. Recommend new PR — Phase A is its own implementation unit per §14.)

---

## Phase A acceptance gate (all checks before unblocking Phase B)

- [ ] All 38 tasks committed; clean working tree (`git status` empty under `paperclips/`).
- [ ] All Phase A tests pass: `python3 -m pytest paperclips/tests/test_phase_a_*.py` → 0 FAIL.
- [ ] Build-compat verified: 5 existing builds (gimle×2 + trading×2 + uaudit×1) succeed; output drift limited to deprecation banners.
- [ ] Submodule pointer in main repo updated to commit SHA on `paperclip-shared-fragments` `feature/uaa-phase-a-fragment-refactor` branch.
- [ ] Submodule branch is **merged** to its `main` and superrepo points to the merge SHA on `main` (so other consumers — Medic — pick up changes coherently). If Medic needs paired migration, coordinate with Medic operator BEFORE submodule merge.
- [ ] Operator visual review of 1 sample slim role file (`roles/cto.md`) and 1 fragment dir (`universal/`).
- [ ] Watchdog tick log shows no `wake_failed` or `handoff_alert_posted` since Phase A merge (1h post-merge observation).
- [ ] Phase B plan (`docs/superpowers/plans/2026-05-15-uaa-phase-B-profile-builder.md`) reviewed; explicit `@<next-operator-session>` handoff comment posted.

**No Phase B work begins until this gate is green.**
