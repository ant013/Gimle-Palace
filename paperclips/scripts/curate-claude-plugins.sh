#!/usr/bin/env bash
# curate-claude-plugins.sh — idempotently remove unused plugin/agent/skill artefacts
# from ~/.claude/ that get re-installed by `/plugins update` or paperclip refreshes.
#
# Run on iMac after any `/plugins update`, `npm install paperclipai`, or fresh setup.
# Safe to run repeatedly — checks before each delete.
#
# What it removes:
#   - ~/.claude/agents/<unused>.md            (kept: 10 listed below)
#   - ~/.claude/plugins/cache/voltagent-subagents/voltagent-{biz,data-ai,dev-exp,meta,core-dev,infra}
#   - ~/.claude/plugins/marketplaces/voltagent-subagents/categories/{01,03,05,06,08,09}-*
#   - ~/.claude/CLAUDE.md if it contains SuperClaude entry-point markers
#   - ~/.claude/{BUSINESS_*,FLAGS,MCP_*,MODE_*,PRINCIPLES,RESEARCH_CONFIG,RULES}.md
#   - ~/.claude/commands/sc/
#   - ~/.local/pipx/venvs/superclaude
#   - ~/.local/bin/SuperClaude
#
# What it keeps (matches Gimle production agent needs):
#   - 10 user-level agents: code-reviewer, deep-research-agent, search-specialist,
#     penetration-tester, security-auditor, compliance-auditor, blockchain-developer,
#     kotlin-specialist, swift-expert, cpp-pro
#   - 4 voltagent plugins: lang (cache only — kept for blockchain plain agents),
#     domains, qa-sec, research
#   - 3 claude-plugins-official: superpowers, pr-review-toolkit, code-review
#   - paperclip user-level skill at ~/.claude/skills/paperclip/

set -euo pipefail

DRY_RUN=0
BACKUP_DIR="${HOME}/slim-backups/$(date +%Y%m%d-%H%M%S)-curate"

usage() {
  cat <<EOF
Usage: $0 [--dry-run]

  --dry-run    Print what would be removed without changing anything
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; usage >&2; exit 1 ;;
  esac
done

log() { echo "[$(date -u +%FT%TZ)] $*"; }

remove_path() {
  local path="$1"
  local label="$2"
  if [ ! -e "$path" ]; then
    return 0
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    log "WOULD remove: $path ($label)"
    return 0
  fi
  mkdir -p "$BACKUP_DIR"
  local rel
  rel="$(echo "$path" | sed "s|${HOME}/||")"
  local dest="$BACKUP_DIR/$(dirname "$rel")"
  mkdir -p "$dest"
  mv "$path" "$dest/"
  log "moved → $dest/$(basename "$path") ($label)"
}

KEEP_AGENTS=(
  code-reviewer
  deep-research-agent
  search-specialist
  penetration-tester
  security-auditor
  compliance-auditor
  blockchain-developer
  kotlin-specialist
  swift-expert
  cpp-pro
)

is_kept() {
  local name="$1"
  for k in "${KEEP_AGENTS[@]}"; do
    [ "$name" = "$k" ] && return 0
  done
  return 1
}

log "=== curate-claude-plugins.sh start (DRY_RUN=$DRY_RUN) ==="

# 1. ~/.claude/agents/ — keep only KEEP_AGENTS
if [ -d "${HOME}/.claude/agents" ]; then
  for f in "${HOME}/.claude/agents"/*.md; do
    [ -f "$f" ] || continue
    name="$(basename "$f" .md)"
    if ! is_kept "$name"; then
      remove_path "$f" "agent: $name"
    fi
  done
fi

# 2. voltagent plugin cache — keep only enabled+lang
for vp in biz data-ai dev-exp meta core-dev infra; do
  remove_path "${HOME}/.claude/plugins/cache/voltagent-subagents/voltagent-$vp" "plugin-cache: voltagent-$vp"
done

# 3. voltagent marketplace categories — keep 02 (lang), 04 (qa-sec), 07 (domains), 10 (research)
CATS_DIR="${HOME}/.claude/plugins/marketplaces/voltagent-subagents/categories"
if [ -d "$CATS_DIR" ]; then
  for cat in 01-core-development 03-infrastructure 05-data-ai 06-developer-experience 08-business-product 09-meta-orchestration; do
    remove_path "$CATS_DIR/$cat" "marketplace-category: $cat"
  done
fi

# 4. SuperClaude framework files in ~/.claude/
for fname in BUSINESS_PANEL_EXAMPLES BUSINESS_SYMBOLS FLAGS PRINCIPLES RULES RESEARCH_CONFIG; do
  remove_path "${HOME}/.claude/${fname}.md" "superclaude: $fname"
done
for f in "${HOME}/.claude"/MCP_*.md "${HOME}/.claude"/MODE_*.md; do
  [ -f "$f" ] || continue
  remove_path "$f" "superclaude: $(basename "$f")"
done

# 5. ~/.claude/CLAUDE.md — replace if SuperClaude entry-point present
if [ -f "${HOME}/.claude/CLAUDE.md" ]; then
  if grep -q "SuperClaude" "${HOME}/.claude/CLAUDE.md" 2>/dev/null; then
    if [ "$DRY_RUN" -eq 1 ]; then
      log "WOULD replace ~/.claude/CLAUDE.md (contains SuperClaude entry-point)"
    else
      mkdir -p "$BACKUP_DIR"
      mv "${HOME}/.claude/CLAUDE.md" "$BACKUP_DIR/CLAUDE.md.superclaude"
      cat > "${HOME}/.claude/CLAUDE.md" <<'STUB_EOF'
# User-level Claude Code rules

(Empty stub — SuperClaude framework removed by curate-claude-plugins.sh.)
STUB_EOF
      log "replaced ~/.claude/CLAUDE.md with stub (backup: $BACKUP_DIR/CLAUDE.md.superclaude)"
    fi
  fi
fi

# 6. ~/.claude/commands/sc/
remove_path "${HOME}/.claude/commands/sc" "superclaude: sc/ commands"

# 7. ~/.local/pipx/venvs/superclaude
remove_path "${HOME}/.local/pipx/venvs/superclaude" "superclaude: pipx venv"

# 8. ~/.local/bin/SuperClaude
remove_path "${HOME}/.local/bin/SuperClaude" "superclaude: binary symlink"

# 9. ~/.claude/.superclaude-metadata.json
remove_path "${HOME}/.claude/.superclaude-metadata.json" "superclaude: metadata"

# 10. SuperClaude logs + backup tar
for f in "${HOME}/.claude/logs"/superclaude_*.log; do
  [ -f "$f" ] || continue
  remove_path "$f" "superclaude: log"
done
for f in "${HOME}/.claude/backups"/superclaude_backup_*.tar.gz; do
  [ -f "$f" ] || continue
  remove_path "$f" "superclaude: install backup"
done

# 11. plugins/cache/temp_git_* (stale clones from past `/plugins update`)
for d in "${HOME}/.claude/plugins/cache"/temp_git_*; do
  [ -d "$d" ] || continue
  remove_path "$d" "stale-temp-clone"
done

# 12. Clean dead entries from installed_plugins.json + settings.json
if [ "$DRY_RUN" -eq 0 ]; then
  python3 - <<'PY_EOF'
import json
import os

home = os.environ["HOME"]
ip = f"{home}/.claude/plugins/installed_plugins.json"
ss = f"{home}/.claude/settings.json"
to_remove = [
    "voltagent-biz@voltagent-subagents",
    "voltagent-data-ai@voltagent-subagents",
    "voltagent-dev-exp@voltagent-subagents",
    "voltagent-meta@voltagent-subagents",
    "voltagent-core-dev@voltagent-subagents",
    "voltagent-infra@voltagent-subagents",
]

if os.path.exists(ip):
    with open(ip) as f:
        d = json.load(f)
    changed = False
    for k in to_remove:
        if k in d.get("plugins", {}):
            del d["plugins"][k]
            changed = True
            print(f"  installed_plugins.json: removed {k}")
    if changed:
        with open(ip, "w") as f:
            json.dump(d, f, indent=2)
            f.write("\n")

if os.path.exists(ss):
    with open(ss) as f:
        cfg = json.load(f)
    changed = False
    for k in to_remove:
        if k in cfg.get("enabledPlugins", {}):
            del cfg["enabledPlugins"][k]
            changed = True
            print(f"  settings.json: removed {k}")
    if changed:
        with open(ss, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
PY_EOF
fi

log "=== curate complete ==="
if [ "$DRY_RUN" -eq 0 ] && [ -d "$BACKUP_DIR" ]; then
  log "backup: $BACKUP_DIR ($(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}'))"
fi
