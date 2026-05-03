#!/usr/bin/env bash
# Sync the Paperclip-managed company Codex home with the shared Codex runtime.
# Run on the iMac host. This creates no secrets; it links shared agents/skills
# into the company managed CODEX_HOME while preserving Paperclip-required skills.
set -euo pipefail

COMPANY_ID="${PAPERCLIP_COMPANY_ID:-9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64}"
SHARED_CODEX_HOME="${SHARED_CODEX_HOME:-$HOME/.codex}"
MANAGED_CODEX_HOME="${MANAGED_CODEX_HOME:-$HOME/.paperclip/instances/default/companies/$COMPANY_ID/codex-home}"

if [ ! -d "$SHARED_CODEX_HOME" ]; then
  echo "ERROR: shared Codex home not found: $SHARED_CODEX_HOME" >&2
  exit 1
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

echo "Managed Codex home: $MANAGED_CODEX_HOME"
printf "Agents: "
find -L "$MANAGED_CODEX_HOME/agents" -maxdepth 1 -type f -name "*.toml" 2>/dev/null | wc -l | tr -d ' '
echo
printf "Skills: "
find -L "$MANAGED_CODEX_HOME/skills" -name SKILL.md 2>/dev/null | wc -l | tr -d ' '
echo

for agent in code-reviewer architect-reviewer security-auditor debugger error-detective mcp-developer frontend-design swift-pro; do
  if [ ! -f "$MANAGED_CODEX_HOME/agents/$agent.toml" ]; then
    echo "WARNING: expected Codex agent missing: $agent" >&2
  fi
done
