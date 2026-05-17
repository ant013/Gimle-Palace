#!/usr/bin/env bash
# Shared helpers for UAA Phase C scripts. Source-only; do not run directly.

# Logging — to stderr so stdout stays clean for piping.
log() {
  local level="${1:-info}"; shift
  local color=""
  case "$level" in
    info)  color="\033[0;36m" ;;     # cyan
    warn)  color="\033[0;33m" ;;     # yellow
    err)   color="\033[0;31m" ;;     # red
    ok)    color="\033[0;32m" ;;     # green
  esac
  printf "%b[%s]%b %s\n" "$color" "$level" "\033[0m" "$*" >&2
}

die() {
  log err "$*"
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

require_env() {
  [ -n "${!1:-}" ] || die "required env var not set: $1"
}

# Atomic file write — write to .tmp, then mv (avoids partial writes on crash).
atomic_write() {
  local target="$1"; shift
  local tmp="${target}.tmp.$$"
  printf '%s' "$*" > "$tmp"
  mv "$tmp" "$target"
}

# JSON pretty-print to file.
write_json_pretty() {
  local target="$1"
  local content="$2"
  printf '%s' "$content" | jq . > "$target"
}

# CRIT-5 fix: input validation for path-bearing arguments.
# project_key gates ~/.paperclip/projects/<key>/, paperclips/projects/<key>/,
# yq selectors, file paths — must be canonical alphanumeric.
validate_project_key() {
  local key="$1"
  if [[ ! "$key" =~ ^[a-z0-9][a-z0-9_-]{0,39}$ ]]; then
    die "invalid project key: '$key' (must match [a-z0-9][a-z0-9_-]{0,39})"
  fi
}

# IMP-E fix: agent_name reaches yq path expressions; restrict to safe charset.
# Phase H2-followup: kebab `-` added — gimle Phase G manifest uses kebab agent_names
# (e.g., `cto`, `cx-cto`). Bracket-syntax in yq paths (`.agents["${name}"]`) makes
# `-` safe (yq would otherwise treat it as subtraction in dot-path).
validate_agent_name() {
  local name="$1"
  if [[ ! "$name" =~ ^[A-Za-z][A-Za-z0-9_-]*$ ]]; then
    die "invalid agent_name: '$name' (must match [A-Za-z][A-Za-z0-9_-]*)"
  fi
}

# Phase H2-followup CRIT-2: guard against path-traversal / absolute paths in
# manifest-supplied `output_path` fields (or similar repo-relative paths).
# A malicious manifest with `output_path: /etc/passwd` or `../../../etc/shadow`
# would otherwise let `cp ${REPO_ROOT}/${output_path}` resolve outside the repo.
validate_safe_repo_path() {
  local p="$1"
  # Reject empty.
  [ -n "$p" ] || die "invalid path: empty"
  # Reject absolute paths.
  case "$p" in
    /*) die "invalid path: must be repo-relative, got absolute: '$p'" ;;
  esac
  # Reject any `..` segment.
  case "$p" in
    *..*) die "invalid path: contains '..' (traversal): '$p'" ;;
  esac
  # Reject shell-special chars that could break later interpolation.
  if [[ "$p" =~ [\$\`\"\'\\] ]]; then
    die "invalid path: contains shell-special chars: '$p'"
  fi
}

# journal_id is a filename basename — no path separators, no .., no absolute.
validate_journal_id() {
  local jid="$1"
  case "$jid" in
    */*|*..*|/*)
      die "invalid journal id: '$jid' (no path separators, no .., no absolute path)"
      ;;
  esac
  if [[ ! "$jid" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    die "invalid journal id: '$jid' (must match [A-Za-z0-9][A-Za-z0-9._-]*)"
  fi
}
