# imac-deploy.sh — iMac Production Deploy for palace-mcp

Single idempotent script that pulls `develop` tip on iMac, rebuilds the
`palace-mcp` Docker image, brings containers up, and records a baseline log
line for rollback. Codifies the 5-gotcha pattern captured during GIM-102
deploy (2026-04-27).

**Must be run on the iMac directly** (or via SSH by a user who already has a
session on the iMac). It does not initiate any SSH connection itself.

---

## Prerequisites

- Docker Desktop running on iMac (`docker info` must succeed)
- Git repo checked out at `/Users/Shared/Ios/Gimle-Palace` on branch `develop`
- Tracked tree clean (`git status --porcelain --untracked-files=no` empty)
- Docker binary accessible at one of:
  - `/Applications/Docker.app/Contents/Resources/bin/docker`
  - `/usr/local/bin/docker`
  - `/opt/homebrew/bin/docker`
  - Override: `export DOCKER_BIN=/your/docker` before running (PATH is
    augmented at script top — see Gotcha #1)

---

## Usage

```bash
# Basic deploy — pull develop tip, rebuild, up, verify
bash paperclips/scripts/imac-deploy.sh

# Pinned deploy — assert HEAD == specific SHA after pull
bash paperclips/scripts/imac-deploy.sh --target 3c7ba7d

# Assert a specific extractor is registered after deploy
bash paperclips/scripts/imac-deploy.sh --expect-extractor symbol_index_python

# Combined
bash paperclips/scripts/imac-deploy.sh --target 3c7ba7d --expect-extractor symbol_index_typescript
```

### Idempotency

Running the script twice when `develop` is unchanged is safe:
- `git pull --ff-only` reports "already up to date" and continues
- Docker rebuild re-builds from cache (fast if no layers changed)
- Healthcheck polls succeed quickly (containers already running)
- A new baseline log line is appended either way

---

## Gotchas (all addressed in the script)

### Gotcha #1 — PATH augmentation

`bash -s` over SSH inherits a minimal PATH that may not include Docker or
Homebrew binaries. The script sets:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
```

This must be at the very top, before any `docker` or `git` calls.

### Gotcha #2 — No `set -o pipefail` + `head | grep`

`set -o pipefail` causes scripts to fail when any command in a pipeline
exits non-zero — including when `head` closes the pipe early, producing
SIGPIPE in upstream commands like `git log`.

**Solution:** script uses `set -eu` (no pipefail). To test whether a commit
SHA exists the script uses:
```bash
git rev-parse --verify --quiet "${sha}^{commit}"
```
…instead of `git log --oneline | grep <sha>` which would trigger SIGPIPE.

### Gotcha #3 — No multi-line `python -c` in `docker exec`

Shell quoting breaks when a multi-line Python one-liner is passed as a
`docker exec` argument over SSH.

**Solution:** all `docker exec python3 -c "..."` calls use a single line
with `;` separators:
```bash
docker exec palace-mcp python3 -c "import foo; print(foo.bar)"
```

### Gotcha #4 — Untracked files are OK

The production checkout may contain large untracked files (e.g. `scip/`
SCIP index, `*.log` files) that are intentionally gitignored. These are
**not** a blocker for deploy.

**Solution:** dirty-check uses `--untracked-files=no`:
```bash
git status --porcelain --untracked-files=no
```
Untracked files are listed in the log output for visibility but do not
abort the deploy.

### Gotcha #5 — No worktree for develop deploy

The production checkout is already on `develop`. Using `git worktree` or
checking out a different branch would leave the deploy on the wrong SHA.

**Solution:** the script asserts `branch == develop` in pre-flight, then
does a simple `git pull --ff-only origin develop`. Worktree-from-origin/main
is reserved for `deploy-agents.sh` (AGENTS.md update workflow only).

---

## Log files

### Baseline log — `paperclips/scripts/imac-deploy.log`

Gitignored. Appended on every successful deploy:

```
2026-04-27T17:10:05Z	source=3c7ba7d...	prev_image=sha256:7e5f45...	new_image=sha256:a1b2c3...	container=d4e5f6a7b8c9
```

Fields: `UTC timestamp`, `source SHA`, `prev image digest` (for rollback),
`new image digest`, `12-char container ID`.

### Transient run log — `/tmp/imac-deploy-<utc>.log`

Full stdout+stderr for the run. Survives reboots in `/tmp` until cleared.

---

## Rollback procedure

1. Find the `prev_image` SHA from `paperclips/scripts/imac-deploy.log`:
   ```bash
   tail -2 paperclips/scripts/imac-deploy.log
   ```

2. Tag that image with the compose-expected name. Compose uses `build:` for
   `palace-mcp`, so `--no-build` is required to prevent a rebuild:
   ```bash
   docker tag <prev_image_sha> gimle-palace-palace-mcp:latest
   docker compose --profile review up -d --no-build palace-mcp
   ```

3. Verify:
   ```bash
   docker compose --profile review ps
   docker inspect --format='{{.State.Health.Status}}' gimle-palace-palace-mcp-1
   ```

---

## Exit code reference

| Code | Meaning              | When                                           |
|------|----------------------|------------------------------------------------|
| 0    | Success              | All steps passed                               |
| 1    | Pre-flight failure   | Wrong cwd/branch, dirty tree, non-FF pull, bad SHA |
| 2    | Docker failure       | Build, up, or healthcheck timeout              |
| 3    | Verify failure       | Expected extractor missing from registry       |
| 4    | Argument error       | Unknown flag or missing value                  |
