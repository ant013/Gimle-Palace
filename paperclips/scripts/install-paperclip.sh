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
  5. Telegram plugin (backup → checkout SHA → build → forced reinstall/reload → loaded proof)
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
  require_command tar
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
  # shellcheck source=lib/_paperclip_api.sh
  source "${SCRIPT_DIR}/lib/_paperclip_api.sh"
  require_command git
  require_command pnpm
  require_command python3
  require_command tar
  log info "[5/9] Install and reload telegram plugin (fork: ${TELEGRAM_PLUGIN_REPO} @ ${TELEGRAM_PLUGIN_REF})"
  [[ "$TELEGRAM_PLUGIN_REF" =~ ^[0-9a-f]{40}$ ]] || \
    die "TELEGRAM_PLUGIN_REF must be an exact full 40-hex commit SHA"

  api_url="${PAPERCLIP_API_URL:-http://localhost:3100}"
  normalized_api_url=$(printf '%s' "$api_url" | sed -E \
    's/^[[:space:]]+//; s/[[:space:]]+$//; s:/+$::')
  [ -n "$normalized_api_url" ] || die "PAPERCLIP_API_URL normalizes to an empty value"
  api_url="$normalized_api_url"
  jwt=$(jq -r --arg api "$normalized_api_url" '.credentials[$api].token // empty' \
    "${HOME}/.paperclip/auth.json")
  [ -n "$jwt" ] && [ "$jwt" != "null" ] || die "paperclip auth token missing"
  export PAPERCLIP_API_URL="$api_url"
  export PAPERCLIP_API_KEY="$jwt"

  proof_dir="${HOME}/.paperclip/plugin-proofs"
  proof_file="${proof_dir}/telegram-loaded.json"
  pending_file="${proof_dir}/telegram-pending-reinstall.json"
  awaiting_file="${proof_dir}/telegram-awaiting-attestation.json"
  mkdir -p "$proof_dir"
  chmod 700 "$proof_dir"
  [ ! -e "$pending_file" ] || \
    die "unfinished telegram plugin transaction; preserve it and follow the rollback runbook before retry"

  # This read endpoint is instance-admin-only in the pinned Paperclip release.
  # Fail before preparing or unloading anything when that authority is absent.
  if ! paperclip_get "/api/instance/scheduler-heartbeats" >/dev/null; then
    die "telegram plugin reinstall requires an instance-admin Paperclip credential"
  fi
  plugins_json=$(paperclip_get "/api/plugins") || die "cannot list installed Paperclip plugins"
  existing_record=$(printf '%s' "$plugins_json" | jq -c '
    [.[] | select(
      .pluginKey == "paperclip-plugin-telegram" or
      .manifestJson.id == "paperclip-plugin-telegram"
    )] |
    if length > 1 then error("multiple telegram plugin records")
    elif length == 1 then .[0]
    else empty
    end')
  existing_id=$(printf '%s' "$existing_record" | jq -r '.id // ""')

  rollback_manifest=""
  rollback_source=""
  previous_ref=""
  existing_config=""
  existing_config_sha=""
  if [ -n "$existing_id" ]; then
    existing_package_path=$(printf '%s' "$existing_record" | jq -r '.packagePath // ""')
    [ -n "$existing_package_path" ] && [ -d "$existing_package_path" ] && \
      [ ! -L "$existing_package_path" ] || \
      die "installed telegram plugin packagePath is missing, non-directory, or a symlink"
    canonical_existing_path=$(python3 - "$existing_package_path" <<'PY'
import pathlib
import sys

print(pathlib.Path(sys.argv[1]).resolve(strict=True))
PY
)
    [ "$existing_package_path" = "$canonical_existing_path" ] || \
      die "installed telegram plugin packagePath must be canonical"
    [ -f "${existing_package_path}/dist/worker.js" ] || \
      die "installed telegram plugin worker is missing; refusing unload without rollback bytes"
    existing_config=$(paperclip_get "/api/plugins/${existing_id}/config" | jq -cS '.') || \
      die "cannot snapshot telegram plugin configuration before reinstall"
    existing_config_sha=$(printf '%s' "$existing_config" | python3 -c \
      'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')
    previous_ref=$(git -C "$existing_package_path" rev-parse HEAD 2>/dev/null || true)
    [[ "$previous_ref" =~ ^[0-9a-f]{40}$ ]] || previous_ref=""

    rollback_root="${HOME}/.paperclip/plugin-rollbacks/telegram/$(date -u +%Y%m%dT%H%M%SZ)-${existing_id}"
    rollback_source="${rollback_root}/source"
    rollback_manifest="${rollback_root}/rollback.json"
    mkdir -p "$rollback_source"
    chmod 700 "${HOME}/.paperclip/plugin-rollbacks" \
      "${HOME}/.paperclip/plugin-rollbacks/telegram" "$rollback_root"
    tar -C "$existing_package_path" -cf - . | tar -C "$rollback_source" -xf -
    [ -f "${rollback_source}/dist/worker.js" ] || die "rollback worker build missing"
    [ ! -L "${rollback_source}/dist/worker.js" ] || die "rollback worker must not be a symlink"
    chmod -R a-w "$rollback_source"
    rollback_worker_sha=$(python3 - "${rollback_source}/dist/worker.js" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)
    rollback_tree_sha=$(python3 - "$rollback_source" <<'PY'
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root).as_posix().encode()
    if path.is_symlink():
        digest.update(b"L\0" + relative + b"\0" + path.readlink().as_posix().encode() + b"\0")
    elif path.is_file():
        data = path.read_bytes()
        digest.update(b"F\0" + relative + b"\0" + str(len(data)).encode() + b"\0" + data)
    elif path.is_dir():
        digest.update(b"D\0" + relative + b"\0")
print(digest.hexdigest())
PY
)
    jq -n \
      --arg schema_version "telegram-plugin-rollback/v1" \
      --arg plugin_id "$existing_id" \
      --arg source_ref "$previous_ref" \
      --arg package_path "$rollback_source" \
      --arg worker_sha256 "$rollback_worker_sha" \
      --arg package_tree_sha256 "$rollback_tree_sha" \
      --arg config_sha256 "$existing_config_sha" \
      '{
        schema_version: $schema_version,
        plugin_id: $plugin_id,
        source_ref: (if $source_ref == "" then null else $source_ref end),
        package_path: $package_path,
        worker_sha256: $worker_sha256,
        package_tree_sha256: $package_tree_sha256,
        config_sha256: $config_sha256
      }' > "${rollback_manifest}.tmp"
    chmod 400 "${rollback_manifest}.tmp"
    mv -f "${rollback_manifest}.tmp" "$rollback_manifest"
    log ok "rollback generation prepared: $rollback_manifest"
  fi

  # Build the target in a new generation. The active packagePath is never
  # fetched, checked out, built, or otherwise modified before unload.
  generation_root="${HOME}/.paperclip/plugin-generations/telegram"
  mkdir -p "$generation_root"
  chmod 700 "${HOME}/.paperclip/plugin-generations" "$generation_root"
  staging_root=$(mktemp -d "${generation_root}/.staging-${TELEGRAM_PLUGIN_REF}.XXXXXX")
  staging_source="${staging_root}/source"
  git clone "$TELEGRAM_PLUGIN_REPO" "$staging_source"
  git -C "$staging_source" cat-file -e "${TELEGRAM_PLUGIN_REF}^{commit}" || \
    die "telegram plugin pin is not available from configured repository"
  git -C "$staging_source" checkout --detach "$TELEGRAM_PLUGIN_REF"
  loaded_head=$(git -C "$staging_source" rev-parse HEAD)
  [ "$loaded_head" = "$TELEGRAM_PLUGIN_REF" ] || die "telegram plugin checkout does not match pin"

  log info "building pinned plugin (--ignore-scripts for supply-chain safety)"
  (
    cd "$staging_source"
    pnpm install --frozen-lockfile --ignore-scripts
    pnpm build
  )
  worker_path="${staging_source}/dist/worker.js"
  [ -f "$worker_path" ] || die "telegram plugin worker build missing: $worker_path"
  worker_sha=$(python3 - "$worker_path" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)
  target_generation="${generation_root}/${TELEGRAM_PLUGIN_REF}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  mv "$staging_source" "$target_generation"
  rmdir "$staging_root"
  chmod -R a-w "$target_generation"
  worker_path="${target_generation}/dist/worker.js"

  jq -n \
    --arg schema_version "telegram-plugin-pending-reinstall/v1" \
    --arg plugin_id "$existing_id" \
    --arg target_ref "$TELEGRAM_PLUGIN_REF" \
    --arg target_package_path "$target_generation" \
    --arg target_worker_sha256 "$worker_sha" \
    --arg rollback_manifest "$rollback_manifest" \
    --arg prepared_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      schema_version: $schema_version,
      plugin_id: (if $plugin_id == "" then null else $plugin_id end),
      target_ref: $target_ref,
      target_package_path: $target_package_path,
      target_worker_sha256: $target_worker_sha256,
      rollback_manifest: (if $rollback_manifest == "" then null else $rollback_manifest end),
      prepared_at: $prepared_at
    }' > "${pending_file}.tmp"
  chmod 600 "${pending_file}.tmp"
  mv -f "${pending_file}.tmp" "$pending_file"
  # A proof is usable only when no pending transaction exists. Invalidate the
  # previous proof before unload so a crash cannot leave a stale green gate.
  rm -f "$proof_file"

  restore_previous_generation() {
    [ -n "$rollback_manifest" ] && [ -n "$existing_id" ] || return 1
    [ -f "$rollback_manifest" ] && [ ! -L "$rollback_manifest" ] || return 1
    [ -d "$rollback_source" ] && [ ! -L "$rollback_source" ] || return 1
    [ -f "${rollback_source}/dist/worker.js" ] && [ ! -L "${rollback_source}/dist/worker.js" ] || return 1
    python3 - "$rollback_manifest" "$rollback_source" "${rollback_source}/dist/worker.js" <<'PY' || return 1
import pathlib
import sys

raise SystemExit(1 if any(pathlib.Path(value).stat().st_mode & 0o222 for value in sys.argv[1:]) else 0)
PY
    local rollback_meta expected_worker expected_tree expected_config expected_source actual_worker actual_tree
    rollback_meta=$(jq -c '
      if type == "object" and
         keys == ["config_sha256","package_path","package_tree_sha256","plugin_id","schema_version","source_ref","worker_sha256"] and
         .schema_version == "telegram-plugin-rollback/v1"
      then . else error("invalid rollback manifest") end
    ' "$rollback_manifest") || return 1
    [ "$(printf '%s' "$rollback_meta" | jq -r '.plugin_id')" = "$existing_id" ] || return 1
    [ "$(printf '%s' "$rollback_meta" | jq -r '.package_path')" = "$rollback_source" ] || return 1
    expected_worker=$(printf '%s' "$rollback_meta" | jq -r '.worker_sha256')
    expected_tree=$(printf '%s' "$rollback_meta" | jq -r '.package_tree_sha256')
    expected_config=$(printf '%s' "$rollback_meta" | jq -r '.config_sha256')
    expected_source=$(printf '%s' "$rollback_meta" | jq -r '.source_ref // ""')
    [[ "$expected_worker" =~ ^[0-9a-f]{64}$ ]] && [[ "$expected_tree" =~ ^[0-9a-f]{64}$ ]] || return 1
    [ "$expected_config" = "$existing_config_sha" ] || return 1
    actual_worker=$(python3 - "${rollback_source}/dist/worker.js" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
) || return 1
    [ "$actual_worker" = "$expected_worker" ] || return 1
    actual_tree=$(python3 - "$rollback_source" <<'PY'
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root).as_posix().encode()
    if path.is_symlink():
        digest.update(b"L\0" + relative + b"\0" + path.readlink().as_posix().encode() + b"\0")
    elif path.is_file():
        data = path.read_bytes()
        digest.update(b"F\0" + relative + b"\0" + str(len(data)).encode() + b"\0" + data)
    elif path.is_dir():
        digest.update(b"D\0" + relative + b"\0")
print(digest.hexdigest())
PY
) || return 1
    [ "$actual_tree" = "$expected_tree" ] || return 1
    if [ -n "$expected_source" ]; then
      [ "$(git -C "$rollback_source" rev-parse HEAD 2>/dev/null)" = "$expected_source" ] || return 1
    fi
    curl -fsS --max-time 30 --connect-timeout 10 \
      -X DELETE "${api_url%/}/api/plugins/${existing_id}" \
      -H "Authorization: Bearer ${jwt}" \
      -H "User-Agent: uaa-bootstrap/1.0" >/dev/null 2>&1 || true
    local rollback_payload rollback_response rollback_id rollback_record rollback_health rollback_config rollback_attestation
    rollback_payload=$(jq -n --arg package_name "$rollback_source" \
      '{packageName: $package_name, isLocalPath: true}')
    rollback_response=$(paperclip_post "/api/plugins/install" "$rollback_payload") || return 1
    rollback_id=$(printf '%s' "$rollback_response" | jq -r '.id // ""')
    [ "$rollback_id" = "$existing_id" ] || return 1
    rollback_record=$(paperclip_get "/api/plugins/${rollback_id}") || return 1
    rollback_health=$(paperclip_get "/api/plugins/${rollback_id}/health") || return 1
    rollback_config=$(paperclip_get "/api/plugins/${rollback_id}/config" | jq -cS '.') || return 1
    [ "$(printf '%s' "$rollback_record" | jq -r '.status // ""')" = "ready" ] || return 1
    [ "$(printf '%s' "$rollback_record" | jq -r '.pluginKey // ""')" = "paperclip-plugin-telegram" ] || return 1
    [ "$(printf '%s' "$rollback_record" | jq -r '.packagePath // ""')" = "$rollback_source" ] || return 1
    [ "$(printf '%s' "$rollback_health" | jq -r '.healthy // false')" = "true" ] || return 1
    [ "$rollback_config" = "$existing_config" ] || return 1
    rollback_attestation=$(paperclip_post "/api/plugins/${rollback_id}/actions/send_to_telegram" \
      '{"params":{"companyId":"uaudit-install-attestation","agentId":"installer"}}') || return 1
    printf '%s' "$rollback_attestation" | jq -e \
      '.data.data.ok == false and .data.data.code == "missing_content"' >/dev/null || return 1
    return 0
  }

  # Paperclip 2026.508.0 has no in-place reinstall for an installed plugin.
  # A soft uninstall stops/unloads the current worker while preserving config
  # and plugin-scoped data; installing the same manifest ID reuses the DB row
  # and starts a fresh worker from the pinned local package path.
  if [ -n "$existing_id" ]; then
    uninstall_response=$(curl -fsS --max-time 30 --connect-timeout 10 \
      -X DELETE "${api_url%/}/api/plugins/${existing_id}" \
      -H "Authorization: Bearer ${jwt}" \
      -H "User-Agent: uaa-bootstrap/1.0")
    [ "$(printf '%s' "$uninstall_response" | jq -r '.status // ""')" = "uninstalled" ] || \
      die "telegram plugin soft uninstall did not stop the previous worker"
  fi

  install_payload=$(jq -n --arg package_name "$target_generation" \
    '{packageName: $package_name, isLocalPath: true}')
  if ! install_response=$(paperclip_post "/api/plugins/install" "$install_payload"); then
    if [ -n "$rollback_manifest" ]; then
      log err "pinned plugin install failed; attempting prepared rollback"
      if restore_previous_generation; then
        log warn "previous telegram worker restored and runtime-attested; target proof remains invalid"
      else
        log err "automatic telegram plugin rollback failed; use $rollback_manifest"
      fi
    fi
    die "telegram plugin forced reinstall failed"
  fi

  plugin_id=$(printf '%s' "$install_response" | jq -r '.id // ""')
  [ -n "$plugin_id" ] && [ "$plugin_id" != "null" ] || die "plugin install returned no id"
  if [ -n "$existing_id" ]; then
    if [ "$plugin_id" != "$existing_id" ]; then
      curl -fsS --max-time 30 --connect-timeout 10 \
        -X DELETE "${api_url%/}/api/plugins/${plugin_id}" \
        -H "Authorization: Bearer ${jwt}" \
        -H "User-Agent: uaa-bootstrap/1.0" >/dev/null 2>&1 || true
      restore_previous_generation || log err "automatic rollback failed after stable ID mismatch"
      die "telegram plugin reinstall changed stable plugin id"
    fi
  fi

  write_telegram_host_registry() {
    local loaded_proof="$1"
    local hp="${HOME}/.paperclip/host-plugins.yaml"
    mkdir -p "$(dirname "$hp")"
    if [ ! -f "$hp" ]; then echo "schemaVersion: 2" > "$hp"; fi
    if command -v yq >/dev/null 2>&1; then
      yq -i ".telegram.plugin_id = \"${plugin_id}\" | .telegram.repo = \"${TELEGRAM_PLUGIN_REPO}\" | .telegram.ref = \"${TELEGRAM_PLUGIN_REF}\" | .telegram.loaded_proof = \"${loaded_proof}\" | .telegram.rollback_manifest = \"${rollback_manifest}\"" "$hp"
    else
      log warn "yq not installed; appending crude block to host-plugins.yaml (re-run after yq install for proper merge)"
      {
        echo "telegram:"
        echo "  plugin_id: \"${plugin_id}\""
        echo "  repo: \"${TELEGRAM_PLUGIN_REPO}\""
        echo "  ref: \"${TELEGRAM_PLUGIN_REF}\""
        echo "  loaded_proof: \"${loaded_proof}\""
        echo "  rollback_manifest: \"${rollback_manifest}\""
      } >> "$hp"
    fi
  }

  target_identity_ok=true
  loaded_record=$(paperclip_get "/api/plugins/${plugin_id}") || target_identity_ok=false
  loaded_health=$(paperclip_get "/api/plugins/${plugin_id}/health") || target_identity_ok=false
  loaded_config=$(paperclip_get "/api/plugins/${plugin_id}/config" | jq -cS '.') || target_identity_ok=false
  [ "$(printf '%s' "$loaded_record" | jq -r '.status // ""')" = "ready" ] || target_identity_ok=false
  [ "$(printf '%s' "$loaded_record" | jq -r '.pluginKey // ""')" = "paperclip-plugin-telegram" ] || target_identity_ok=false
  [ "$(printf '%s' "$loaded_record" | jq -r '.packagePath // ""')" = "$target_generation" ] || target_identity_ok=false
  [ "$(printf '%s' "$loaded_health" | jq -r '.healthy // false')" = "true" ] || target_identity_ok=false
  if [ -n "$existing_id" ]; then
    [ "$loaded_config" = "$existing_config" ] || target_identity_ok=false
  fi
  runtime_attestation_ok=false
  attestation_payload='{"params":{"companyId":"uaudit-install-attestation","agentId":"installer","text":"runtime attestation","issueIdentifier":"INVALID"}}'
  if [ "$target_identity_ok" = true ]; then
    runtime_attestation=$(paperclip_post "/api/plugins/${plugin_id}/actions/send_to_telegram" \
      "$attestation_payload") || true
    if printf '%s' "$runtime_attestation" | jq -e \
      '.data.data.ok == false and .data.data.code == "invalid_route_context" and .data.data.invalidField == "issueIdentifier"' \
      >/dev/null; then
      runtime_attestation_ok=true
    fi
  fi
  if [ "$target_identity_ok" = true ] && [ "$runtime_attestation_ok" != true ] && \
    [ -z "$existing_id" ] && [ "$loaded_config" = "null" ]; then
    jq -n \
      --arg schema_version "telegram-plugin-awaiting-attestation/v1" \
      --arg plugin_id "$plugin_id" \
      --arg target_ref "$TELEGRAM_PLUGIN_REF" \
      --arg package_path "$target_generation" \
      --arg worker_sha256 "$worker_sha" \
      '{schema_version:$schema_version,plugin_id:$plugin_id,target_ref:$target_ref,package_path:$package_path,worker_sha256:$worker_sha256}' \
      > "${awaiting_file}.tmp"
    chmod 600 "${awaiting_file}.tmp"
    mv -f "${awaiting_file}.tmp" "$awaiting_file"
    rm -f "$pending_file"
    write_telegram_host_registry ""
    log warn "telegram plugin installed but unconfigured; configure it, then re-run step 5 for runtime attestation"
    return 0
  fi
  if [ "$target_identity_ok" != true ] || [ "$runtime_attestation_ok" != true ]; then
    if [ -n "$rollback_manifest" ]; then
      restore_previous_generation || log err "automatic rollback failed after target attestation failure"
    else
      curl -fsS --max-time 30 --connect-timeout 10 \
        -X DELETE "${api_url%/}/api/plugins/${plugin_id}" \
        -H "Authorization: Bearer ${jwt}" \
        -H "User-Agent: uaa-bootstrap/1.0" >/dev/null 2>&1 || true
    fi
    die "telegram plugin target generation failed identity/config/runtime attestation"
  fi

  if ! { jq -n \
    --arg schema_version "telegram-plugin-loaded-proof/v2" \
    --arg plugin_id "$plugin_id" \
    --arg plugin_key "paperclip-plugin-telegram" \
    --arg source_ref "$TELEGRAM_PLUGIN_REF" \
    --arg source_head "$loaded_head" \
    --arg package_path "$target_generation" \
    --arg worker_sha256 "$worker_sha" \
    --arg installed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg rollback_manifest "$rollback_manifest" \
    '{
      schema_version: $schema_version,
      plugin_id: $plugin_id,
      plugin_key: $plugin_key,
      source_ref: $source_ref,
      source_head: $source_head,
      package_path: $package_path,
      worker_sha256: $worker_sha256,
      status: "ready",
      registry_healthy: true,
      runtime_attestation: {
        action: "send_to_telegram",
        code: "invalid_route_context",
        invalid_field: "issueIdentifier"
      },
      installed_at: $installed_at,
      rollback_manifest: (if $rollback_manifest == "" then null else $rollback_manifest end)
    }' > "${proof_file}.tmp" && \
    chmod 600 "${proof_file}.tmp" && \
    mv -f "${proof_file}.tmp" "$proof_file"; }; then
    if [ -n "$rollback_manifest" ]; then
      restore_previous_generation || log err "automatic rollback failed after proof publication failure"
    fi
    die "failed to publish telegram plugin loaded proof"
  fi
  rm -f "$pending_file"
  rm -f "$awaiting_file"
  log ok "telegram plugin reloaded and runtime-attested from exact SHA $loaded_head (proof: $proof_file)"

  write_telegram_host_registry "$proof_file"
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
  api_url="${PAPERCLIP_API_URL:-http://localhost:3100}"
  normalized_api_url=$(printf '%s' "$api_url" | sed -E \
    's/^[[:space:]]+//; s/[[:space:]]+$//; s:/+$::')
  [ -n "$normalized_api_url" ] || die "PAPERCLIP_API_URL normalizes to an empty value"
  api_url="$normalized_api_url"
  jwt=$(jq -r --arg api "$normalized_api_url" '.credentials[$api].token // empty' \
    "${HOME}/.paperclip/auth.json")
  [ -n "$jwt" ] || die "paperclip auth token missing for $normalized_api_url"
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
