#!/usr/bin/env bash
# Interactive prompt helpers for UAA Phase C scripts. Source-only.

# Prompt with default; usage: name=$(prompt_with_default "Local clone path" "/Users/me/Code/synth")
prompt_with_default() {
  local question="$1"
  local default="$2"
  local response
  printf "? %s\n  (default: %s)\n  > " "$question" "$default" >&2
  read -r response
  echo "${response:-$default}"
}

prompt_yes_no() {
  local question="$1"
  local default="${2:-n}"  # 'y' or 'n'
  local prompt_str="[y/N]"
  [ "$default" = "y" ] && prompt_str="[Y/n]"
  local response
  printf "? %s %s " "$question" "$prompt_str" >&2
  read -r response
  response="${response:-$default}"
  case "$response" in
    [Yy]|[Yy]es) return 0 ;;
    *) return 1 ;;
  esac
}

prompt_required() {
  local question="$1"
  local response=""
  while [ -z "$response" ]; do
    printf "? %s\n  > " "$question" >&2
    read -r response
  done
  echo "$response"
}
