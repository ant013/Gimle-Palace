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
