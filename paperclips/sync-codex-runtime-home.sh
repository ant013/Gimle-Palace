#!/usr/bin/env bash
# Sync the Paperclip-managed company Codex home with the shared Codex runtime.
# Run on the iMac host. This creates no secrets; it links shared agents/skills
# into the company managed CODEX_HOME while preserving Paperclip-required skills.
set -euo pipefail

COMPANY_ID="${PAPERCLIP_COMPANY_ID:-9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64}"
SHARED_CODEX_HOME="${SHARED_CODEX_HOME:-$HOME/.codex}"
MANAGED_CODEX_HOME="${MANAGED_CODEX_HOME:-$HOME/.paperclip/instances/default/companies/$COMPANY_ID/codex-home}"
TRUST_WORKSPACE_ROOTS="${PAPERCLIP_TRUST_WORKSPACE_ROOTS:-}"
UAUDIT_COMPANY_ID="8f55e80b-0264-4ab6-9d56-8b2652f18005"
UAUDIT_REQUIRED_CODEX_AGENTS="uaudit-swift-audit-specialist uaudit-kotlin-audit-specialist uaudit-bug-hunter uaudit-security-auditor uaudit-blockchain-auditor"
DEFAULT_EXPECTED_CODEX_AGENTS="code-reviewer architect-reviewer security-auditor debugger error-detective mcp-developer frontend-design swift-pro"

if [ ! -d "$SHARED_CODEX_HOME" ]; then
  echo "ERROR: shared Codex home not found: $SHARED_CODEX_HOME" >&2
  exit 1
fi

if [ "$COMPANY_ID" = "$UAUDIT_COMPANY_ID" ]; then
  case "$MANAGED_CODEX_HOME" in
    *"/companies/$UAUDIT_COMPANY_ID/codex-home") ;;
    *)
      echo "ERROR: UAudit managed Codex home does not match company $UAUDIT_COMPANY_ID: $MANAGED_CODEX_HOME" >&2
      exit 1
      ;;
  esac
fi

mkdir -p "$MANAGED_CODEX_HOME"

if [ ! -e "$MANAGED_CODEX_HOME/agents" ]; then
  ln -s "$SHARED_CODEX_HOME/agents" "$MANAGED_CODEX_HOME/agents"
elif [ ! -d "$MANAGED_CODEX_HOME/agents" ]; then
  echo "ERROR: managed agents path exists but is not a directory: $MANAGED_CODEX_HOME/agents" >&2
  exit 1
fi

mkdir -p "$MANAGED_CODEX_HOME/skills"
for skill_dir in "$SHARED_CODEX_HOME"/skills/*; do
  [ -d "$skill_dir" ] || continue
  skill_name="$(basename "$skill_dir")"
  if [ ! -e "$MANAGED_CODEX_HOME/skills/$skill_name" ]; then
    ln -s "$skill_dir" "$MANAGED_CODEX_HOME/skills/$skill_name"
  fi
done

mkdir -p "$HOME/.local/bin"

NVM_NODE_HOME="${NVM_NODE_HOME:-$HOME/.nvm/versions/node/v20.20.2/bin}"
if [ -x "$NVM_NODE_HOME/node" ]; then
  ln -sf "$NVM_NODE_HOME/node" "$HOME/.local/bin/node"
fi
if [ -x "$NVM_NODE_HOME/npm" ]; then
  ln -sf "$NVM_NODE_HOME/npm" "$HOME/.local/bin/npm"
fi
if [ -x "$NVM_NODE_HOME/npx" ]; then
  ln -sf "$NVM_NODE_HOME/npx" "$HOME/.local/bin/npx"
fi

for tool in rg jq node npm; do
  if ! PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" command -v "$tool" >/dev/null 2>&1; then
    echo "WARNING: expected runtime tool missing from stable PATH: $tool" >&2
  fi
done

if [ -n "$TRUST_WORKSPACE_ROOTS" ]; then
  CONFIG_FILE="$MANAGED_CODEX_HOME/config.toml"
  touch "$CONFIG_FILE"
  IFS=":" read -r -a trust_roots <<< "$TRUST_WORKSPACE_ROOTS"
  for trust_root in "${trust_roots[@]}"; do
    [ -d "$trust_root" ] || continue
    while IFS= read -r workspace; do
      project_header="[projects.\"$workspace\"]"
      if ! grep -Fqx "$project_header" "$CONFIG_FILE"; then
        {
          echo
          echo "$project_header"
          echo 'trust_level = "trusted"'
        } >> "$CONFIG_FILE"
      fi
    done < <(find "$trust_root" -mindepth 3 -maxdepth 3 -type f -name AGENTS.md -path "*/workspace/AGENTS.md" -exec dirname {} \; | sort)
  done
fi

echo "Managed Codex home: $MANAGED_CODEX_HOME"
echo "Company ID: $COMPANY_ID"
printf "Agents: "
find -L "$MANAGED_CODEX_HOME/agents" -maxdepth 1 -type f -name "*.toml" 2>/dev/null | wc -l | tr -d ' '
echo
printf "Skills: "
find -L "$MANAGED_CODEX_HOME/skills" -name SKILL.md 2>/dev/null | wc -l | tr -d ' '
echo

if [ "$COMPANY_ID" = "$UAUDIT_COMPANY_ID" ]; then
  required_agents="${PAPERCLIP_REQUIRED_CODEX_AGENTS:-$UAUDIT_REQUIRED_CODEX_AGENTS}"
  expected_agents="${PAPERCLIP_EXPECTED_CODEX_AGENTS:-}"
else
  required_agents="${PAPERCLIP_REQUIRED_CODEX_AGENTS:-}"
  expected_agents="${PAPERCLIP_EXPECTED_CODEX_AGENTS:-$DEFAULT_EXPECTED_CODEX_AGENTS}"
fi

missing_required=0
for agent in $required_agents; do
  if [ ! -f "$MANAGED_CODEX_HOME/agents/$agent.toml" ]; then
    echo "ERROR: required Codex agent missing: $agent" >&2
    missing_required=$((missing_required + 1))
  else
    if ! grep -q '^sandbox_mode = "read-only"$' "$MANAGED_CODEX_HOME/agents/$agent.toml"; then
      echo "ERROR: required Codex agent is not read-only: $agent" >&2
      missing_required=$((missing_required + 1))
    fi
  fi
done
if [ "$missing_required" -ne 0 ]; then
  exit 1
fi

for agent in $expected_agents; do
  if [ ! -f "$MANAGED_CODEX_HOME/agents/$agent.toml" ]; then
    echo "WARNING: expected Codex agent missing: $agent" >&2
  fi
done
