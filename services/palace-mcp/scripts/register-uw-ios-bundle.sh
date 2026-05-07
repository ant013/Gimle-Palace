#!/usr/bin/env bash
# register-uw-ios-bundle.sh — idempotent uw-ios bundle registration (GIM-182 §7.2).
#
# Reads uw-ios-bundle-manifest.json and:
#   1. Registers each member project (register_project; idempotent: skip if exists).
#   2. Registers the bundle (register_bundle; idempotent).
#   3. Adds each member to the bundle (add_to_bundle; idempotent).
#
# Usage (from repo root or iMac):
#   bash services/palace-mcp/scripts/register-uw-ios-bundle.sh
#
# Environment variables:
#   PALACE_MCP_URL  — default http://localhost:18080/mcp
#   GIMLE_ROOT      — repo root; default $(git rev-parse --show-toplevel)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${SCRIPT_DIR}/uw-ios-bundle-manifest.json"
MCP_CLIENT="${SCRIPT_DIR}/_mcp_client.py"
PALACE_MCP_URL="${PALACE_MCP_URL:-http://localhost:18080/mcp}"
export PALACE_MCP_URL

if [ ! -f "$MANIFEST" ]; then
  echo "ERROR: manifest not found at $MANIFEST" >&2
  exit 1
fi

BUNDLE_NAME=$(python3 -c "import json,sys; print(json.load(open('$MANIFEST'))['bundle_name'])")
BUNDLE_DESC=$(python3 -c "import json,sys; print(json.load(open('$MANIFEST'))['bundle_description'])")
PARENT_MOUNT=$(python3 -c "import json,sys; print(json.load(open('$MANIFEST'))['parent_mount'])")

echo "==> Registering bundle '$BUNDLE_NAME' from $MANIFEST"

# 1. Register each member project (idempotent)
python3 - <<PYEOF
import json, subprocess, sys

manifest = json.load(open("$MANIFEST"))
parent_mount = manifest["parent_mount"]
ok_count = 0
skip_count = 0
fail_count = 0

for m in manifest["members"]:
    slug = m["slug"]
    rel_path = m["relative_path"]
    args = json.dumps({
        "slug": slug,
        "parent_mount": parent_mount,
        "relative_path": rel_path,
    })
    try:
        result = json.loads(subprocess.check_output(
            ["python3", "$MCP_CLIENT", "palace.memory.register_project", args],
            stderr=subprocess.PIPE,
        ))
        if result.get("ok") or result.get("slug"):
            print(f"  registered: {slug}")
            ok_count += 1
        elif "already" in str(result).lower() or result.get("error_code") == "already_registered":
            print(f"  skip (exists): {slug}")
            skip_count += 1
        else:
            print(f"  WARN: {slug} → {result}", file=sys.stderr)
            skip_count += 1
    except subprocess.CalledProcessError as e:
        print(f"  FAIL: {slug} — {e.stderr.decode()[:200]}", file=sys.stderr)
        fail_count += 1

print(f"  projects: {ok_count} registered, {skip_count} skipped, {fail_count} failed")
if fail_count > 0:
    sys.exit(1)
PYEOF

# 2. Register the bundle (idempotent)
echo "==> Registering bundle entity '$BUNDLE_NAME'"
python3 "$MCP_CLIENT" palace.memory.register_bundle \
  "{\"name\":\"$BUNDLE_NAME\",\"description\":\"$BUNDLE_DESC\"}" || true

# 3. Add each member to the bundle (idempotent)
echo "==> Adding members to bundle '$BUNDLE_NAME'"
python3 - <<PYEOF
import json, subprocess, sys

manifest = json.load(open("$MANIFEST"))
bundle_name = manifest["bundle_name"]
ok_count = 0
skip_count = 0
fail_count = 0

for m in manifest["members"]:
    slug = m["slug"]
    tier = m["tier"]
    args = json.dumps({"bundle": bundle_name, "project": slug, "tier": tier})
    try:
        result = json.loads(subprocess.check_output(
            ["python3", "$MCP_CLIENT", "palace.memory.add_to_bundle", args],
            stderr=subprocess.PIPE,
        ))
        if result.get("ok") or "added" in str(result).lower():
            print(f"  added: {slug} ({tier})")
            ok_count += 1
        else:
            print(f"  skip/warn: {slug} → {result}")
            skip_count += 1
    except subprocess.CalledProcessError as e:
        print(f"  FAIL: {slug} — {e.stderr.decode()[:200]}", file=sys.stderr)
        fail_count += 1

print(f"  members: {ok_count} added, {skip_count} skipped, {fail_count} failed")
if fail_count > 0:
    sys.exit(1)
PYEOF

echo "==> Done: bundle '$BUNDLE_NAME' registered."
