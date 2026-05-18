#!/usr/bin/env bash
# UAA Phase C1 — host-wide setup for paperclip + telegram plugin + MCP servers + watchdog code.
# Per UAA spec §9.1. Idempotent. Run once per machine.
#
# Watchdog launchd service install is DEFERRED to bootstrap-watchdog.sh (Phase C2)
# because gimle_watchdog install requires non-empty companies in config — only
# possible after first project bootstrap.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=lib/_common.sh
source "${SCRIPT_DIR}/lib/_common.sh"
# shellcheck source=lib/_prompts.sh
source "${SCRIPT_DIR}/lib/_prompts.sh"

# Load pinned versions
# shellcheck source=versions.env
source "${SCRIPT_DIR}/versions.env"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--skip-step N]...

UAA host-wide setup. Installs:
- paperclipai pinned ($PAPERCLIPAI_VERSION)
- paperclip-plugin-telegram (fork pinned by SHA)
- 4 MCP servers (codebase-memory, serena, context7, sequential-thinking)
- Watchdog code prep (uv sync only; service install deferred to bootstrap-watchdog.sh)

Steps (all idempotent):
  0. Pre-flight (node 20+, gh, python3, uv, git, corepack/pnpm)
  1. Auth checks (gh, codex, claude, ssh) — interactive prompts if missing
  2. Install paperclipai pinned
  3. paperclip login (interactive, first-run only)
  4. Disable heartbeat in paperclip-server config
  5. Telegram plugin (clone fork → checkout SHA → pnpm build → POST /api/plugins/install)
  6. Core MCP servers (npm install -g at pinned versions)
  7. Register MCP servers in claude/codex configs
  8. Watchdog code prep (uv sync; service install deferred)
  9. Verification curl

Skip flag: --skip-step N (can be repeated). Useful for partial re-runs.
EOF
}

declare -A SKIP_STEPS

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --skip-step)
      SKIP_STEPS[$2]=1; shift 2 ;;
    *)
      die "unknown arg: $1 (try --help)" ;;
  esac
done

_skip() {
  [ -n "${SKIP_STEPS[$1]:-}" ]
}

step_0_preflight() {
  _skip 0 && { log info "[0/9] SKIPPED"; return 0; }
  log info "[0/9] Pre-flight"
  require_command node
  node_major=$(node -v | sed 's/v//' | cut -d. -f1)
  [ "$node_major" -ge 20 ] || die "node 20+ required, found $(node -v)"
  require_command gh
  require_command python3
  require_command uv
  require_command git
  require_command jq
  # corepack + pnpm setup (Node 20+ built-in)
  corepack enable >/dev/null 2>&1 || die "corepack enable failed"
  corepack prepare "pnpm@${PNPM_VERSION}" --activate >/dev/null 2>&1 || die "corepack pnpm prepare failed"
  pnpm --version >/dev/null || die "pnpm not available after corepack"
  log ok "[0/9] pre-flight green"
}

step_1_auth() {
  _skip 1 && { log info "[1/9] SKIPPED"; return 0; }
  log info "[1/9] Auth checks"
  if ! gh auth status >/dev/null 2>&1; then
    log warn "gh not authenticated"
    if prompt_yes_no "Run 'gh auth login' now?"; then
      gh auth login
    else
      die "gh auth required"
    fi
  fi
  [ -f "${HOME}/.codex/auth.json" ] || \
    log warn "~/.codex/auth.json missing — run 'codex auth' if you use codex agents"
  if [ ! -f "${HOME}/.claude/auth.json" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    log warn "neither ~/.claude/auth.json nor ANTHROPIC_API_KEY set — claude agents won't run"
  fi
  log ok "[1/9] auth checks done"
}

step_2_paperclipai() {
  _skip 2 && { log info "[2/9] SKIPPED"; return 0; }
  log info "[2/9] Install paperclipai@${PAPERCLIPAI_VERSION}"
  current=$(npm ls -g paperclipai 2>/dev/null | grep paperclipai | sed -E 's/.*paperclipai@([^ ]+).*/\1/' || true)
  if [ "$current" = "$PAPERCLIPAI_VERSION" ]; then
    log ok "already at $PAPERCLIPAI_VERSION"
    return 0
  fi
  npm install -g "paperclipai@${PAPERCLIPAI_VERSION}"
  installed=$(paperclip --version 2>/dev/null || npm ls -g paperclipai | grep paperclipai || echo "?")
  log ok "[2/9] installed: $installed"
}

step_3_paperclip_login() {
  _skip 3 && { log info "[3/9] SKIPPED"; return 0; }
  log info "[3/9] paperclip login"
  if [ -f "${HOME}/.paperclip/auth.json" ]; then
    log ok "already logged in"
    return 0
  fi
  paperclip login
  [ -f "${HOME}/.paperclip/auth.json" ] || die "auth.json not created after login"
  log ok "[3/9] logged in"
}

step_4_disable_heartbeat() {
  _skip 4 && { log info "[4/9] SKIPPED"; return 0; }
  log info "[4/9] Disable heartbeat in paperclip-server config"
  cfg="${HOME}/.paperclip/instances/default/config.json"
  if [ ! -f "$cfg" ]; then
    log warn "paperclip-server config not yet created — run paperclip once, then re-run install"
    return 0
  fi
  current=$(jq -r '.heartbeat.enabled // "missing"' "$cfg")
  if [ "$current" = "false" ]; then
    log ok "heartbeat already disabled"
    return 0
  fi
  tmp="${cfg}.tmp"
  jq '.heartbeat.enabled = false' "$cfg" > "$tmp" && mv "$tmp" "$cfg"
  log ok "[4/9] heartbeat disabled (was: $current)"
}

step_5_telegram_plugin() {
  _skip 5 && { log info "[5/9] SKIPPED"; return 0; }
  log info "[5/9] Install telegram plugin (fork: ${TELEGRAM_PLUGIN_REPO} @ ${TELEGRAM_PLUGIN_REF})"
  src="${HOME}/.paperclip/plugins-src/paperclip-plugin-telegram"
  if [ ! -d "${src}/.git" ]; then
    git clone "$TELEGRAM_PLUGIN_REPO" "$src"
  fi
  cd "$src"
  git fetch --all --tags
  git checkout "$TELEGRAM_PLUGIN_REF"

  log info "building plugin (--ignore-scripts for supply-chain safety)"
  pnpm install --frozen-lockfile --ignore-scripts
  pnpm build
  cd - >/dev/null

  # Idempotent register: query existing plugins first
  jwt=$(jq -r '.credentials.token' "${HOME}/.paperclip/auth.json")
  api_url="${PAPERCLIP_API_URL:-http://localhost:3100}"
  existing=$(curl -fsS "${api_url}/api/plugins" -H "Authorization: Bearer ${jwt}" 2>/dev/null \
    | jq -r '.[] | select(.name == "paperclip-plugin-telegram") | .id' | head -1)
  if [ -n "$existing" ]; then
    plugin_id="$existing"
    log ok "telegram plugin already installed: $plugin_id"
  else
    log info "registering plugin in paperclip instance"
    plugin_id=$(curl -fsS -X POST "${api_url}/api/plugins/install" \
      -H "Authorization: Bearer ${jwt}" -H "Content-Type: application/json" \
      -d "{\"path\":\"${src}\"}" | jq -r .id)
    [ -n "$plugin_id" ] && [ "$plugin_id" != "null" ] || die "plugin install returned no id"
    log ok "registered: $plugin_id"
  fi

  # Save host-wide registry
  hp="${HOME}/.paperclip/host-plugins.yaml"
  mkdir -p "$(dirname "$hp")"
  if [ ! -f "$hp" ]; then echo "schemaVersion: 2" > "$hp"; fi
  if command -v yq >/dev/null 2>&1; then
    yq -i ".telegram.plugin_id = \"${plugin_id}\" | .telegram.repo = \"${TELEGRAM_PLUGIN_REPO}\" | .telegram.ref = \"${TELEGRAM_PLUGIN_REF}\"" "$hp"
  else
    # yq missing — append crude block (operator should install yq for proper merge)
    log warn "yq not installed; appending crude block to host-plugins.yaml (re-run after yq install for proper merge)"
    {
      echo "telegram:"
      echo "  plugin_id: \"${plugin_id}\""
      echo "  repo: \"${TELEGRAM_PLUGIN_REPO}\""
      echo "  ref: \"${TELEGRAM_PLUGIN_REF}\""
    } >> "$hp"
  fi
  log ok "[5/9] telegram plugin ready (id $plugin_id)"
}

step_6_mcp_servers() {
  _skip 6 && { log info "[6/9] SKIPPED"; return 0; }
  log info "[6/9] Install core MCP servers at pinned versions"
  npm install -g \
    "codebase-memory-mcp@${CODEBASE_MEMORY_MCP_VERSION}" \
    "serena@${SERENA_VERSION}" \
    "context7@${CONTEXT7_MCP_VERSION}" \
    "sequential-thinking@${SEQUENTIAL_THINKING_MCP_VERSION}"
  log ok "[6/9] MCP servers pinned"
}

step_7_register_mcp() {
  _skip 7 && { log info "[7/9] SKIPPED"; return 0; }
  log info "[7/9] Register MCP servers in claude/codex configs"

  # Codex config: ~/.codex/config.toml under [mcp_servers.<name>]
  codex_config="${HOME}/.codex/config.toml"
  if [ -f "$codex_config" ]; then
    for srv in codebase-memory serena context7 sequential-thinking; do
      if ! grep -q "^\[mcp_servers\.${srv}\]" "$codex_config"; then
        cat >> "$codex_config" <<EOF

[mcp_servers.${srv}]
command = "${srv}"
args = []
EOF
        log ok "  appended [mcp_servers.${srv}] to $codex_config"
      else
        log info "  [mcp_servers.${srv}] already present"
      fi
    done
  else
    log warn "  $codex_config missing — operator must run codex auth first"
  fi

  # Claude config: ~/.claude/settings.json under "mcpServers": {<name>: {...}}
  claude_settings="${HOME}/.claude/settings.json"
  if [ -f "$claude_settings" ]; then
    for srv in codebase-memory serena context7 sequential-thinking; do
      tmp="${claude_settings}.tmp"
      jq --arg name "$srv" '.mcpServers[$name] //= {command: $name, args: []}' \
        "$claude_settings" > "$tmp" && mv "$tmp" "$claude_settings"
    done
    log ok "  merged 4 MCP servers into $claude_settings"
  else
    log warn "  $claude_settings missing — operator must run claude auth first"
  fi
  log ok "[7/9] MCP registration done"
}

step_8_watchdog_prep() {
  _skip 8 && { log info "[8/9] SKIPPED"; return 0; }
  log info "[8/9] Watchdog code prep (service install deferred to bootstrap-watchdog.sh)"
  cd "${REPO_ROOT}/${WATCHDOG_PATH}"
  uv sync --all-extras
  uv run python -m gimle_watchdog --help >/dev/null
  cd - >/dev/null
  log ok "[8/9] watchdog code ready"
}

step_9_verify() {
  _skip 9 && { log info "[9/9] SKIPPED"; return 0; }
  log info "[9/9] Verification"
  jwt=$(jq -r '.credentials.token' "${HOME}/.paperclip/auth.json")
  api_url="${PAPERCLIP_API_URL:-http://localhost:3100}"
  email=$(curl -fsS "${api_url}/api/agents/me" -H "Authorization: Bearer ${jwt}" \
    | jq -r '.email // .user.email // ""')
  [ -n "$email" ] || die "verification curl returned no email"
  log ok "[9/9] verified: logged in as $email"
}

main() {
  step_0_preflight
  step_1_auth
  step_2_paperclipai
  step_3_paperclip_login
  step_4_disable_heartbeat
  step_5_telegram_plugin
  step_6_mcp_servers
  step_7_register_mcp
  step_8_watchdog_prep
  step_9_verify
  log ok "READY. Run 'bootstrap-project.sh <project-key>' to set up your first project."
}

main "$@"
