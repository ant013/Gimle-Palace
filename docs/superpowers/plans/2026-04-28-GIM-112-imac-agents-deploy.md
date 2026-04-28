# imac-agents-deploy.sh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `paperclips/scripts/imac-agents-deploy.sh` — an idempotent bash script that deploys updated AGENTS.md files to live paperclip agents on iMac via a worktree-from-`origin/main` pattern. Symmetric to `imac-deploy.sh` (GIM-106).

**Architecture:** The script runs locally on iMac. It creates a temporary git worktree from `origin/main` (detached HEAD), initialises submodules, runs `paperclips/build.sh` to render fragments into `paperclips/dist/`, then runs `paperclips/deploy-agents.sh --local` to copy dist files to the live agent instruction directories. Cleanup is guaranteed via `trap EXIT`. A `--target-sha` flag allows pinning to a specific main SHA for rollback.

**Tech Stack:** Pure bash (3.2+ compatible for macOS stock). Git worktree. Existing `paperclips/build.sh` + `paperclips/deploy-agents.sh --local`.

**Predecessor SHA:** `54691a7` (develop tip at spec time).

**Template:** `paperclips/scripts/imac-deploy.sh` (GIM-106) — reuse PATH augmentation, logging helpers, pre-flight pattern, exit code scheme.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `paperclips/scripts/imac-agents-deploy.sh` | Create | Main deploy script |
| `paperclips/scripts/imac-agents-deploy.README.md` | Create | Usage docs, prerequisites, rollback, gotchas |
| `CLAUDE.md` | Modify (lines ~49-65) | Add agents deploy section under existing palace-mcp deploy |

**Note:** `.gitignore` already has `*.log` — no update needed for `imac-agents-deploy.log`.

---

## Task 1: Script skeleton — constants, args, pre-flight

**Files:**
- Create: `paperclips/scripts/imac-agents-deploy.sh`

- [ ] **Step 1: Create executable script file with shebang, PATH augmentation, constants**

```bash
#!/usr/bin/env bash
# imac-agents-deploy.sh — idempotent AGENTS.md deploy on iMac production checkout
# Deploys from origin/main via temporary worktree (never mutates local main).
# See paperclips/scripts/imac-agents-deploy.README.md for prerequisites + rollback.

# Gotcha #1 (from GIM-106): PATH augmentation so bash -s over SSH finds git
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

set -eu

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_LOG="$SCRIPT_DIR/imac-agents-deploy.log"
RUN_LOG="/tmp/imac-agents-deploy-$(date -u +%Y%m%dT%H%M%SZ).log"

EXPECTED_CWD="/Users/Shared/Ios/Gimle-Palace"
EXPECTED_BRANCH="develop"
WORKTREE_PATH="/tmp/gimle-agents-deploy"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
TARGET_SHA=""
VERIFY_MARKER="Phase 4.2"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--target-sha <sha>] [--verify-marker <text>] [--help]

  --target-sha <sha>        Checkout specific main SHA instead of origin/main tip
  --verify-marker <text>    Grep deployed AGENTS.md for this marker (default: "Phase 4.2")
  --help                    Show this message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-sha)
            [[ $# -ge 2 ]] || { echo "ERROR: --target-sha requires an argument" >&2; exit 1; }
            TARGET_SHA="$2"; shift 2 ;;
        --verify-marker)
            [[ $# -ge 2 ]] || { echo "ERROR: --verify-marker requires an argument" >&2; exit 1; }
            VERIFY_MARKER="$2"; shift 2 ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Logging helpers — tee all output to per-run transient log
# ---------------------------------------------------------------------------
exec > >(tee -a "$RUN_LOG") 2>&1
log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die()  { log "ERROR: $*" >&2; exit "${2:-1}"; }

log "=== imac-agents-deploy.sh start (run log: $RUN_LOG) ==="

# ---------------------------------------------------------------------------
# Cleanup trap — ALWAYS remove worktree, even on ctrl-C or error
# ---------------------------------------------------------------------------
cleanup() {
    log "--- Cleanup ---"
    # cd back to repo root first (worktree dir may be cwd)
    cd "$REPO_ROOT" 2>/dev/null || cd / 2>/dev/null || true
    if [ -d "$WORKTREE_PATH" ]; then
        git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || {
            log "WARN: git worktree remove failed, removing directory manually"
            rm -rf "$WORKTREE_PATH" 2>/dev/null || true
            git worktree prune 2>/dev/null || true
        }
        log "Worktree cleaned: $WORKTREE_PATH"
    else
        log "Worktree already clean"
    fi
    # Verify production checkout is still on develop
    local current
    current="$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
    if [[ "$current" != "$EXPECTED_BRANCH" ]]; then
        log "WARNING: production checkout on '$current', expected '$EXPECTED_BRANCH'"
    else
        log "Production checkout: $current (OK)"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Pre-flight (exit code 1)
# ---------------------------------------------------------------------------
log "--- Pre-flight checks ---"

if [[ "$REPO_ROOT" != "$EXPECTED_CWD" ]]; then
    die "must run from $EXPECTED_CWD (got $REPO_ROOT)" 1
fi
cd "$REPO_ROOT"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]]; then
    die "branch must be '$EXPECTED_BRANCH' (got '$CURRENT_BRANCH')" 1
fi

log "Pre-flight OK (branch=$CURRENT_BRANCH)"
```

- [ ] **Step 2: Make the script executable**

```bash
chmod +x paperclips/scripts/imac-agents-deploy.sh
```

- [ ] **Step 3: Run shellcheck on the partial script**

Run: `shellcheck paperclips/scripts/imac-agents-deploy.sh`
Expected: no errors (warnings about `local` in non-function context are OK if present — they won't be since `local` is only in `cleanup()`)

- [ ] **Step 4: Commit skeleton**

```bash
git add paperclips/scripts/imac-agents-deploy.sh
git commit -m "feat(GIM-112): script skeleton — constants, args, pre-flight, cleanup trap"
```

---

## Task 2: Worktree creation, submodule init, build, deploy

**Files:**
- Modify: `paperclips/scripts/imac-agents-deploy.sh` (append after pre-flight section)

- [ ] **Step 1: Add git fetch + worktree creation section**

Append after the pre-flight section (before the final closing of the script):

```bash
# ---------------------------------------------------------------------------
# Git fetch (exit code 2 on failure)
# ---------------------------------------------------------------------------
log "--- Git fetch ---"
git fetch origin || die "git fetch failed" 2

# Resolve target ref
if [[ -n "$TARGET_SHA" ]]; then
    if ! git rev-parse --verify --quiet "${TARGET_SHA}^{commit}" >/dev/null 2>&1; then
        die "--target-sha $TARGET_SHA is not a valid commit" 1
    fi
    DEPLOY_REF="$TARGET_SHA"
    log "Target SHA: $DEPLOY_REF"
else
    DEPLOY_REF="origin/main"
    log "Deploying from: origin/main"
fi

# ---------------------------------------------------------------------------
# Worktree (exit code 2)
# ---------------------------------------------------------------------------
log "--- Creating worktree ---"

# Remove stale worktree if it exists (idempotency)
if [ -d "$WORKTREE_PATH" ]; then
    log "Stale worktree found, removing..."
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || {
        rm -rf "$WORKTREE_PATH" 2>/dev/null || true
        git worktree prune 2>/dev/null || true
    }
fi

if ! git worktree add --detach "$WORKTREE_PATH" "$DEPLOY_REF"; then
    die "git worktree add failed" 2
fi

MAIN_SHA="$(cd "$WORKTREE_PATH" && git rev-parse HEAD)"
log "Worktree created at $WORKTREE_PATH (SHA: $MAIN_SHA)"

# ---------------------------------------------------------------------------
# Submodule init (exit code 2)
# ---------------------------------------------------------------------------
log "--- Submodule init ---"
cd "$WORKTREE_PATH"

if ! git submodule update --init --recursive; then
    die "git submodule update failed" 2
fi
log "Submodules initialised"

# ---------------------------------------------------------------------------
# Build (exit code 3)
# ---------------------------------------------------------------------------
log "--- Build (paperclips/build.sh) ---"

if ! bash paperclips/build.sh; then
    die "paperclips/build.sh failed" 3
fi
log "Build complete"

# ---------------------------------------------------------------------------
# Deploy (exit code 3)
# ---------------------------------------------------------------------------
log "--- Deploy (paperclips/deploy-agents.sh --local) ---"

if ! bash paperclips/deploy-agents.sh --local; then
    die "paperclips/deploy-agents.sh --local failed" 3
fi
log "Deploy complete"

# Return to repo root before verify (cleanup trap also does this)
cd "$REPO_ROOT"
```

- [ ] **Step 2: Run shellcheck**

Run: `shellcheck paperclips/scripts/imac-agents-deploy.sh`
Expected: clean

- [ ] **Step 3: Commit**

```bash
git add paperclips/scripts/imac-agents-deploy.sh
git commit -m "feat(GIM-112): worktree creation, submodule init, build, deploy steps"
```

---

## Task 3: Verify + baseline log + success output

**Files:**
- Modify: `paperclips/scripts/imac-agents-deploy.sh` (append after deploy section, before trap fires)

- [ ] **Step 1: Add verify section**

Append after the deploy section:

```bash
# ---------------------------------------------------------------------------
# Verify (exit code 4)
# ---------------------------------------------------------------------------
log "--- Verify ---"

# Find CTO AGENTS.md as verification target (known to contain shared fragments)
COMPANY_ID="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
CTO_AGENT_ID="7fb0fdbb-e17f-4487-a4da-16993a907bec"
PAPERCLIP_DATA="${PAPERCLIP_DATA_DIR:-$HOME/.paperclip/instances/default}"
CTO_AGENTS_MD="$PAPERCLIP_DATA/companies/$COMPANY_ID/agents/$CTO_AGENT_ID/instructions/AGENTS.md"

if [ ! -f "$CTO_AGENTS_MD" ]; then
    die "CTO AGENTS.md not found at $CTO_AGENTS_MD — deploy may have failed" 4
fi

if ! grep -q "$VERIFY_MARKER" "$CTO_AGENTS_MD"; then
    die "marker '$VERIFY_MARKER' not found in deployed CTO AGENTS.md" 4
fi
log "Verify OK: marker '$VERIFY_MARKER' found in CTO AGENTS.md"

# Count deployed agents (grep dist files that were actually copied)
DEPLOYED_COUNT=0
DIST_DIR="$WORKTREE_PATH/paperclips/dist"
if [ -d "$DIST_DIR" ]; then
    DEPLOYED_COUNT="$(ls -1 "$DIST_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')"
fi
log "Deployed agents: $DEPLOYED_COUNT"

# ---------------------------------------------------------------------------
# Baseline log
# ---------------------------------------------------------------------------
UTC_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG_LINE="$UTC_NOW\tmain_sha=$MAIN_SHA\tdeployed_agents=$DEPLOYED_COUNT"
printf "%b\n" "$LOG_LINE" >> "$DEPLOY_LOG"
log "Baseline log: $LOG_LINE"

# ---------------------------------------------------------------------------
# Done (cleanup trap fires after this)
# ---------------------------------------------------------------------------
log "=== imac-agents-deploy.sh SUCCESS ==="
log "  Main SHA        : $MAIN_SHA"
log "  Deployed agents : $DEPLOYED_COUNT"
log "  Run log         : $RUN_LOG"
log "  Baseline        : $DEPLOY_LOG"
```

- [ ] **Step 2: Run shellcheck on complete script**

Run: `shellcheck paperclips/scripts/imac-agents-deploy.sh`
Expected: clean

- [ ] **Step 3: Commit**

```bash
git add paperclips/scripts/imac-agents-deploy.sh
git commit -m "feat(GIM-112): verify marker, baseline log, success output"
```

---

## Task 4: README

**Files:**
- Create: `paperclips/scripts/imac-agents-deploy.README.md`

- [ ] **Step 1: Write README**

```markdown
# imac-agents-deploy.sh — iMac AGENTS.md Deploy

Single idempotent script that deploys updated AGENTS.md role files to live
paperclip agents on iMac via a temporary git worktree from `origin/main`.
Symmetric to `imac-deploy.sh` (palace-mcp container deploy).

Paperclip reads AGENTS.md fresh on each agent run — no agent restart needed
after deploy.

**Must be run on the iMac directly** (or via SSH).

---

## Prerequisites

- Git available (no Docker needed — this is file-copy only)
- Repo checked out at `/Users/Shared/Ios/Gimle-Palace` on branch `develop`
- SSH key that can access `git@github.com:ant013/paperclip-shared-fragments.git`
  (submodule fetch during worktree init)
- Agent bundle directories exist at
  `~/.paperclip/instances/default/companies/<CID>/agents/<AID>/instructions/`

---

## Usage

```bash
# Deploy from origin/main tip
bash paperclips/scripts/imac-agents-deploy.sh

# Deploy specific main SHA (rollback or pinned deploy)
bash paperclips/scripts/imac-agents-deploy.sh --target-sha abc1234

# Custom verification marker
bash paperclips/scripts/imac-agents-deploy.sh --verify-marker "my custom text"
```

### Idempotency

Running the script twice when `origin/main` is unchanged is safe:
- Stale worktree is removed before creating a new one
- `build.sh` overwrites dist files (idempotent)
- `deploy-agents.sh --local` overwrites AGENTS.md files (idempotent)
- A new baseline log line is appended either way

---

## Gotchas

### Gotcha #1 — Submodule init required

`git worktree add` does not auto-init submodules. The script runs
`git submodule update --init --recursive` explicitly in the worktree.
If the submodule SSH key is not available, this step will fail (exit code 2).

### Gotcha #2 — Worktree cleanup on interrupt

The script uses `trap cleanup EXIT` to guarantee the temporary worktree
at `/tmp/gimle-agents-deploy` is removed even on ctrl-C or error.
If `git worktree remove` fails (e.g. locks), it falls back to `rm -rf`
plus `git worktree prune`.

### Gotcha #3 — Production checkout drift

The cleanup function verifies the production repo is still on `develop`
after worktree removal. If it somehow drifted (should not happen since
the worktree is detached), a WARNING is logged.

### Gotcha #4 — PATH augmentation

Same as `imac-deploy.sh` — `/usr/local/bin` and `/opt/homebrew/bin` are
prepended so that `git` is found when invoked via `bash -s` over SSH.
Docker paths are NOT added (this script does not use Docker).

### Gotcha #5 — dist/ directory lives in worktree

After worktree removal, the dist files only exist at the deploy target
(agent bundle dirs). The `DEPLOYED_COUNT` in the log is captured before
cleanup.

---

## Rollback

Re-run the script with the previous `main_sha` from the deploy log:

```bash
tail -2 paperclips/scripts/imac-agents-deploy.log
# Find the previous main_sha value
bash paperclips/scripts/imac-agents-deploy.sh --target-sha <previous-sha>
```

---

## Log files

### Baseline log — `paperclips/scripts/imac-agents-deploy.log`

Gitignored (`*.log` pattern). Appended on every successful deploy:

```
2026-04-28T10:15:00Z	main_sha=abc1234...	deployed_agents=11
```

### Transient run log — `/tmp/imac-agents-deploy-<utc>.log`

Full stdout+stderr for the run.

---

## Exit code reference

| Code | Meaning | When |
|------|---------|------|
| 0 | Success | All steps passed |
| 1 | Pre-flight failure | Wrong cwd/branch, bad --target-sha |
| 2 | Worktree failure | git fetch, worktree add, or submodule init failed |
| 3 | Build/deploy failure | build.sh or deploy-agents.sh failed |
| 4 | Verify failure | Marker not found in deployed AGENTS.md |
```

- [ ] **Step 2: Commit**

```bash
git add paperclips/scripts/imac-agents-deploy.README.md
git commit -m "docs(GIM-112): README — prerequisites, usage, gotchas, rollback"
```

---

## Task 5: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md` (around line 49-65, the "Production deploy on iMac" section)

- [ ] **Step 1: Extend the deploy section to cover both scripts**

After the existing `imac-deploy.sh` subsection (around line 65), add a new subsection:

```markdown
## AGENTS.md deploy on iMac

After a release-cut merges to `main`, update live agent role files with:

```bash
bash paperclips/scripts/imac-agents-deploy.sh
```

The script must run **on the iMac** (SSH in first, then invoke locally).

- Pinned deploy: `bash paperclips/scripts/imac-agents-deploy.sh --target-sha <sha>`
- Rollback: see `paperclips/scripts/imac-agents-deploy.README.md`
- Details: `paperclips/scripts/imac-agents-deploy.README.md`

No Docker needed — the script only copies files. Paperclip reads AGENTS.md
fresh on each agent run, so no restart is required after deploy.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-112): CLAUDE.md — add AGENTS.md deploy section"
```

---

## Phase chain

| Phase | Owner | What |
|-------|-------|------|
| 1.1 Formalize | CTO | This plan (done) |
| 1.2 Plan-first review | CodeReviewer | Validate plan completeness |
| 2 Implement | InfraEngineer | TDD through Tasks 1-5 on feature branch |
| 3.1 Mechanical review | CodeReviewer | shellcheck clean, gotchas, idempotency |
| 3.2 Adversarial review | OpusArchitectReviewer | Edge cases: submodule fail mid-flight, worktree remove during paperclip run, trap EXIT race |
| 4.1 Live smoke | QAEngineer | Run script on iMac end-to-end, post evidence |
| 4.2 Merge | CTO | GIM-108 merge-readiness discipline |
