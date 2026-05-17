# UAA Live Deploy — Operator Runbook

> **Audience:** operator running on iMac, after Phase E/F/G code-side merges land on `develop`. Each section is one project; run them sequentially (trading → uaudit → gimle) so you fail-fast cheap before touching the 24-agent gimle window.

**Status (2026-05-17):**
- Phase E (trading code-side): merged via PR #199. Live deploy = pending operator.
- Phase F (uaudit code-side): merged via PR #202. Live deploy = pending operator.
- Phase G (gimle code-side + followup): merged via PR #203 + PR #204 H1. Live deploy = pending operator (requires both-team pause).
- Phase H1 dead-only cleanup: merged via PR #204. H2 + H3 gated on stability metric (≥7d clean watchdog post-deploys).

---

## 0. Pre-flight (run once, before any deploy)

```bash
# 0.1 SSH to iMac
ssh -L 8080:localhost:8080 imac-ssh.ant013.work

# 0.2 Sync repo
cd /Users/Shared/Ios/Gimle-Palace
git fetch origin && git checkout develop && git pull --ff-only

# 0.3 Verify Phase H1 + Phase G commits on develop
git log --oneline -5 | grep -E "phase-h1|phase-g"
# Expected: feat(uaa-phase-h1)..., feat(uaa-phase-g)... lines

# 0.4 Verify scripts exist
ls paperclips/scripts/bootstrap-project.sh \
   paperclips/scripts/migrate-bindings.sh \
   paperclips/scripts/smoke-test.sh \
   paperclips/scripts/rollback.sh \
   paperclips/scripts/bootstrap-watchdog.sh

# 0.5 Sanity: paperclip token + companyId reachable
source ~/.paperclip/auth.json 2>/dev/null || cat ~/.paperclip/auth.json | jq .
# Should show token + companyId for gimle (9d8f432c-...)

# 0.6 Backup current bindings (if any pre-exist for ANY project)
mkdir -p ~/.paperclip/backups/$(date +%Y-%m-%d)/
cp -r ~/.paperclip/projects/* ~/.paperclip/backups/$(date +%Y-%m-%d)/ 2>/dev/null || echo "no pre-existing bindings"
```

If any step 0.1–0.6 fails, **STOP** and fix before touching live agents.

---

## 1. Trading deploy (5 agents — lowest risk, run first)

### 1.1 Pause trading agents in paperclip UI

Open https://app.paperclipai.com → Trading company (5 agents: CEO, CTO, CR, PE, QA) → for each agent: set status = `paused`. This prevents live-handoff during the migration window.

### 1.2 Migrate bindings from legacy → new host-local

```bash
# Trading has no legacy codex-agent-ids.env equivalent (only 5 agents, all
# tracked in paperclip API). migrate-bindings.sh pulls from GET /api/companies.
./paperclips/scripts/migrate-bindings.sh trading
```

Expected: `~/.paperclip/projects/trading/bindings.yaml` created with 5 entries + companyId.

If it errors with "no sources", check `paperclips/projects/trading/paperclip-agent-assembly.yaml` has `project.key: trading` and run with `--from-api` flag if available.

### 1.3 Provide host-local paths

```bash
mkdir -p ~/.paperclip/projects/trading
cat > ~/.paperclip/projects/trading/paths.yaml <<EOF
schemaVersion: 2
paths:
  project_root: /Users/Shared/Trading/trading-agents
  primary_repo_root: /Users/Shared/Trading/trading-agents
  production_checkout: /Users/Shared/Trading/trading-agents
EOF
```

Adjust paths to match your iMac layout.

### 1.4 Canary deploy (writer/research/qa first, then cto, then fan-out)

```bash
./paperclips/scripts/bootstrap-project.sh trading --canary
```

This runs the 13-step lifecycle. The `--canary` flag splits step 10 into 3 sub-stages with pause between each:
- Stage 1: writer/research/qa (low-blast agents)
- Stage 2: cto (orchestrator)
- Stage 3: implementers (PE etc.)

Watch the journal at `~/.paperclip/journal/trading-bootstrap-<timestamp>.json` for per-step outcome.

### 1.5 Smoke test

```bash
./paperclips/scripts/smoke-test.sh trading
```

Expected: `7/7 PASS`.

If any probe fails: capture the journal + the failing probe output, then:

```bash
./paperclips/scripts/rollback.sh trading
```

This replays inverse mutations from the journal (LIFO order).

### 1.6 Unpause + observe

Unpause all 5 trading agents in paperclip UI. Watch for 1 hour:
- Any `wake_failed` events in `~/.paperclip/watchdog.log`?
- Any agents stuck in `status=error`?
- Any `handoff_alert_posted`?

If clean for 1 hour → trading deploy DONE. Move to §2.

---

## 2. Uaudit deploy (17 agents — codex-only, includes telegram plugin)

### 2.1 Pause uaudit agents

Same as 1.1 but for Uaudit company. 17 agents including AUCEO + 3 regional CTOs (UWICTO, UWACTO, etc.).

### 2.2 Migrate bindings

```bash
./paperclips/scripts/migrate-bindings.sh uaudit
```

### 2.3 Provide host-local paths + plugins

```bash
mkdir -p ~/.paperclip/projects/uaudit
cat > ~/.paperclip/projects/uaudit/paths.yaml <<EOF
schemaVersion: 2
paths:
  project_root: /Users/Shared/UnstoppableAudit
  primary_repo_root: /Users/Shared/UnstoppableAudit/repos
EOF

cat > ~/.paperclip/projects/uaudit/plugins.yaml <<EOF
schemaVersion: 2
plugins:
  telegram:
    plugin_id: <real-telegram-plugin-id-from-paperclip>
EOF
```

Get the real `plugin_id` from paperclip UI → Plugins → Telegram → configuration page.

### 2.4 Canary deploy

```bash
./paperclips/scripts/bootstrap-project.sh uaudit --canary
```

### 2.5 Smoke test (includes telegram delivery probe — stage 6)

```bash
./paperclips/scripts/smoke-test.sh uaudit
```

Expected: `7/7 PASS`. Specifically verify stage 6 (telegram delivery) succeeds — this confirms the plugin migration.

### 2.6 Unpause + observe 1h

Same as 1.6. After clean hour → uaudit done.

---

## 3. Gimle deploy (24 agents — REQUIRES BOTH-TEAM PAUSE)

> **CRITICAL:** gimle has 12 claude + 12 codex agents on the same company. Both teams must be paused simultaneously. If either team races mid-migration, you'll get handoff conflicts that look like UUIDs out-of-sync.

### 3.1 Pre-pause comms

- Announce in TG channel: "Gimle deploy starting at HH:MM UTC, ETA 30 min."
- Verify no in-flight critical issue (operator judgment).

### 3.2 Pause both teams

Paperclip UI → Gimle company → set ALL 24 agents to `paused`. Wait 60s for in-flight runs to drain.

### 3.3 Migrate bindings

```bash
./paperclips/scripts/migrate-bindings.sh gimle
```

This reads BOTH legacy `paperclips/codex-agent-ids.env` (12 codex UUIDs) AND `GET /api/companies/9d8f432c-.../agents` (24 UUIDs total) → merges into `~/.paperclip/projects/gimle/bindings.yaml`.

Per Phase D dual-read, conflict warnings on cross-form keys (`cx-cto` vs `CXCTO`) are expected and benign post-Phase-G-followup (PR #203). If migrate-bindings reports `CONFLICT:` with DIFFERENT UUIDs (not just naming-form), STOP and investigate.

### 3.4 Provide host-local paths

```bash
mkdir -p ~/.paperclip/projects/gimle
cat > ~/.paperclip/projects/gimle/paths.yaml <<EOF
schemaVersion: 2
paths:
  project_root: /Users/Shared/Ios/Gimle-Palace
  primary_repo_root: /Users/Shared/Ios/Gimle-Palace
  production_checkout: /Users/Shared/Ios/Gimle-Palace
  codex_team_root: /Users/ant013/Android/Gimle-Palace
  operator_memory_dir: /Users/ant013/.claude/projects/-Users-ant013-Android-Gimle-Palace/memory
EOF
```

### 3.5 Canary deploy

```bash
./paperclips/scripts/bootstrap-project.sh gimle --canary
```

Watch journal closely. Stage 1 (writer/research/qa = 6 agents) is the smallest blast radius — if it fails, abort with rollback before proceeding to stages 2-3.

### 3.6 Smoke test

```bash
./paperclips/scripts/smoke-test.sh gimle
```

### 3.7 Unpause + observe 2h (longer window for 24-agent surface)

Unpause all 24 agents in paperclip UI. Watch watchdog log for 2 hours. Any escalation or wake_failed → revert via rollback.sh.

---

## 4. Post-deploy: 7-day stability gate (Phase H2/H3 prerequisite)

After all 3 projects deployed cleanly, the **cleanup gate** starts counting. Per spec §10.1:

```bash
# Run once per day for 7 days; gate passes if all checks return 0.
cutoff=$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ)
jq -c 'select(.timestamp >= "'$cutoff'") | select(.event | IN("wake_failed","handoff_alert_posted","escalation_per_agent_cap"))' \
  ~/.paperclip/watchdog.log | wc -l
# Expected: 0 every day for 7 consecutive days.
```

If any day returns >0:
1. Investigate the event(s) — root cause per spec §10.1.
2. Document in `docs/uaa-cleanup-gate-evidence.md`.
3. Restart 7-day window.

When 7 clean days pass:
- Create `docs/uaa-cleanup-gate-evidence.md` per Phase H plan Task 1 Step 5 template.
- Open Phase H2 PR (rewrite imac-agents-deploy.sh + remove 5 legacy scripts).
- Open Phase H3 PR (remove dual-read code paths from builder + watchdog).

---

## 5. Rollback (if anything goes wrong)

```bash
./paperclips/scripts/rollback.sh <project-key>
```

Reads the most recent journal under `~/.paperclip/journal/<key>-bootstrap-*.json` and replays inverse mutations LIFO:
- `agent_instructions_snapshot` → PUT old AGENTS.md back
- `plugin_config_snapshot` → POST old plugin config back
- `agent_hire` → DELETE the hired agent

Verify post-rollback: original UUIDs restored, smoke-test passes against pre-deploy state.

If rollback itself fails (rare): manually restore from `~/.paperclip/backups/<date>/`.

---

## 6. Common issues + fixes

| Symptom | Cause | Fix |
|---|---|---|
| `migrate-bindings.sh: no sources` | manifest has no `compatibility.codex_agent_ids_env` AND no agents in paperclip API yet | first-time bootstrap → skip migrate-bindings, go directly to bootstrap-project.sh |
| `CONFLICT: <agent> legacy=X bindings=Y` with DIFFERENT UUIDs | someone manually rotated UUIDs in one source but not the other | reconcile in paperclip UI first → re-run migrate-bindings.sh |
| `bootstrap-project.sh: {{paths.X}} unresolved` | paths.yaml missing required key | add the field to `~/.paperclip/projects/<key>/paths.yaml` |
| smoke-test stage 6 (telegram) FAIL | plugins.yaml has wrong plugin_id or telegram plugin disabled | check paperclip UI → plugins → telegram is "enabled" + plugin_id correct |
| Agent stuck `status=error` post-deploy | failed instruction PUT during canary stage | rollback that one agent + re-hire via bootstrap-project.sh with `--reuse-bindings` |

---

## 7. References

- Phase H plan: `docs/superpowers/plans/2026-05-15-uaa-phase-H-cleanup.md`
- UAA spec: `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §9–§14
- iMac SSH: `~/.claude/projects/-Users-ant013-Android-Gimle-Palace/memory/reference_imac_ssh_access.md`
- Paperclip API token: `~/.claude/projects/-Users-ant013-Android-Gimle-Palace/memory/reference_paperclip_token_locations.md`
- Watchdog service: `~/.claude/projects/-Users-ant013-Android-Gimle-Palace/memory/reference_watchdog_service.md`
