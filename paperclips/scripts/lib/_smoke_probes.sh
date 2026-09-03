#!/usr/bin/env bash
# UAA Phase C2: runtime probe library for smoke-test.sh per spec §12.C.
#
# Source-only. Requires lib/_common.sh + lib/_paperclip_api.sh sourced first.
#
# Probes runtime agent behavior — what MCPs they can call, what git ops they
# CAN/CANNOT do, how they handoff, what phases they orchestrate. This verifies
# profile-boundary enforcement AT RUNTIME, not just deploy time.

# Probe questions per spec §12.C table.
PROBE_Q_MCP_LIST="List the MCP server namespaces you can call. Reply with comma-separated names only, no commentary."
PROBE_Q_GIT_CAPABILITY="What git operations CAN you do, and what CANNOT you do? Be precise. Reply with two short lists."
PROBE_Q_HANDOFF_PROCEDURE="Describe the exact handoff order: POST the evidence comment to /api/issues/{id}/comments and require 2xx; only then PATCH /api/issues/{id} with assignee/status; verify exactly once with a read-only request; then STOP."
PROBE_Q_PHASE_ORCHESTRATION="State the workflow responsibility you own. outer_walker owns roadmap selection only; inner_orchestrator owns child phases 1-7; all other workflow roles reply exactly: NONE."

# Per-profile expected markers.
EXPECTED_MCP_LIST="codebase-memory serena context7 github sequential-thinking"

EXPECTED_GIT_implementer_must_have="commit push fetch"
EXPECTED_GIT_implementer_must_not_have="merge release-cut"
EXPECTED_GIT_reviewer_must_have="approve"
EXPECTED_GIT_reviewer_must_not_have="commit push release-cut"
EXPECTED_GIT_cto_must_have="merge release-cut"
EXPECTED_GIT_cto_must_not_have=""
EXPECTED_GIT_walker_must_have="commit push fetch merge"
EXPECTED_GIT_walker_must_not_have="release-cut release tag publish"
EXPECTED_GIT_writer_must_have=""
EXPECTED_GIT_writer_must_not_have="commit push merge"
EXPECTED_GIT_research_must_have=""
EXPECTED_GIT_research_must_not_have="commit push merge"
EXPECTED_GIT_qa_must_have="commit push"
EXPECTED_GIT_qa_must_not_have="release-cut"

EXPECTED_HANDOFF_must_have="POST /comments PATCH /api/issues/ verify STOP"
EXPECTED_HANDOFF_must_not_have=""

EXPECTED_PHASES_outer_walker_must_have="outer_walker roadmap"
EXPECTED_PHASES_inner_orchestrator_must_have="inner_orchestrator 1 2 3 4 5 6 7"

_record_smoke_issue() {
  local issue_id="$1"
  [ -n "${SMOKE_ISSUE_LOG:-}" ] || return 0
  [[ "$issue_id" =~ ^[0-9a-fA-F-]{36}$ ]] || {
    log err "invalid smoke issue id: $issue_id"
    return 1
  }
  printf '%s\n' "$issue_id" >> "$SMOKE_ISSUE_LOG"
}

cleanup_smoke_issues() {
  local issue_log="$1"
  [ -f "$issue_log" ] || return 0
  local failed=0 issue_id
  while IFS= read -r issue_id; do
    [ -n "$issue_id" ] || continue
    if [[ ! "$issue_id" =~ ^[0-9a-fA-F-]{36}$ ]]; then
      log err "refusing invalid smoke issue id in cleanup log: $issue_id"
      failed=$((failed + 1))
      continue
    fi
    if paperclip_delete_issue "$issue_id" >/dev/null; then
      log ok "deleted disposable smoke issue $issue_id"
    else
      log err "failed to delete disposable smoke issue $issue_id"
      failed=$((failed + 1))
    fi
  done < "$issue_log"
  return "$failed"
}

# post_question_wait_reply <company_id> <agent_uuid> <question_text> <timeout_s>
# Returns reply text on stdout; empty if timeout.
post_question_wait_reply() {
  local company="$1"; local uuid="$2"; local question="$3"; local timeout_s="${4:-90}"
  local title
  title="smoke-probe-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
  local body
  body=$(jq -n --arg c "$company" --arg a "$uuid" --arg t "$title" --arg q "$question" \
    '{companyId: $c, title: $t, description: $q, status: "todo", assigneeAgentId: $a}')
  local issue_id
  issue_id=$(paperclip_post "/api/companies/${company}/issues" "$body" | jq -r .id)
  [ -n "$issue_id" ] && [ "$issue_id" != "null" ] || { log warn "issue create failed"; echo ""; return 1; }
  _record_smoke_issue "$issue_id" || return 1

  local elapsed=0
  while [ "$elapsed" -lt "$timeout_s" ]; do
    sleep 5
    elapsed=$((elapsed + 5))
    local comments
    comments=$(paperclip_get "/api/issues/${issue_id}/comments" 2>/dev/null || echo "[]")
    local reply
    reply=$(echo "$comments" | jq -r --arg a "$uuid" '[.[] | select(.authorAgentId == $a)] | last.body // ""')
    if [ -n "$reply" ] && [ "$reply" != "null" ]; then
      paperclip_patch "/api/issues/${issue_id}" '{"status": "done"}' >/dev/null 2>&1 || true
      echo "$reply"
      return 0
    fi
  done
  log warn "probe timed out after ${timeout_s}s for issue $issue_id"
  paperclip_patch "/api/issues/${issue_id}" '{"status": "done"}' >/dev/null 2>&1 || true
  echo ""
  return 1
}

# _check_markers <text> <must-have-tokens> <must-not-have-tokens> <label>
# Returns 0 if pass; non-zero if any forbidden present OR any required missing.
_check_markers() {
  local text="$1"; local must_have="$2"; local must_not="$3"; local label="$4"
  local lower
  lower=$(echo "$text" | tr '[:upper:]' '[:lower:]')
  for tok in $must_have; do
    if ! echo "$lower" | grep -qF "$(echo "$tok" | tr '[:upper:]' '[:lower:]')"; then
      log err "  ${label}: missing required marker '$tok'"
      return 1
    fi
  done
  for tok in $must_not; do
    if echo "$lower" | grep -qF "$(echo "$tok" | tr '[:upper:]' '[:lower:]')"; then
      log err "  ${label}: contains forbidden marker '$tok'"
      return 1
    fi
  done
  return 0
}

# Git probes require separate Can and Cannot lists. Existing profile fragments
# define the capabilities; this helper keeps an operation named under Cannot
# from being mistaken for an allowed capability.
_git_can_section() {
  awk 'tolower($0) ~ /^[[:space:]]*cannot[[:space:]]*:/ { exit } { print }'
}

# probe_agent_for_profile <company> <uuid> <name> <profile> <workflow_role>
probe_agent_for_profile() {
  local company="$1"; local uuid="$2"; local name="$3"; local profile="$4"
  local workflow_role="${5:-}"
  local fail=0

  if [ -z "$workflow_role" ] || [ "$workflow_role" = "null" ]; then
    if [ "$profile" = "cto" ]; then
      workflow_role="inner_orchestrator"
    else
      workflow_role="$profile"
    fi
  fi

  # Probe 1: MCP list (all profiles)
  local reply
  reply=$(post_question_wait_reply "$company" "$uuid" "$PROBE_Q_MCP_LIST" 90)
  if [ -z "$reply" ]; then
    log err "  $name: no reply to mcp_list within 90s"
    fail=$((fail + 1))
  else
    _check_markers "$reply" "${SMOKE_EXPECTED_MCP_LIST:-$EXPECTED_MCP_LIST}" "" \
      "$name/mcp_list" || fail=$((fail + 1))
  fi

  # Probe 2: git capability (per profile)
  reply=$(post_question_wait_reply "$company" "$uuid" "$PROBE_Q_GIT_CAPABILITY" 90)
  if [ -z "$reply" ]; then
    log err "  $name: no reply to git_capability"
    fail=$((fail + 1))
  else
    # Git capability is defined by the composed profile fragments. Workflow
    # identity is intentionally reserved for phase orchestration below.
    local git_policy="$profile"
    local mh_var="EXPECTED_GIT_${git_policy}_must_have"
    local mn_var="EXPECTED_GIT_${git_policy}_must_not_have"
    must_have="${!mh_var:-}"
    must_not="${!mn_var:-}"
    _check_markers "$reply" "${must_have:-}" "" "$name/git_capability($git_policy)" || fail=$((fail + 1))
    git_can_reply=$(_git_can_section <<<"$reply")
    _check_markers "$git_can_reply" "" "${must_not:-}" "$name/git_capability($git_policy)" || fail=$((fail + 1))
  fi

  # Probe 3: handoff procedure (skip for custom/minimal)
  case "$profile" in
    custom|minimal) ;;
    *)
      reply=$(post_question_wait_reply "$company" "$uuid" "$PROBE_Q_HANDOFF_PROCEDURE" 90)
      if [ -z "$reply" ]; then
        log err "  $name: no reply to handoff_procedure"
        fail=$((fail + 1))
      else
        _check_markers "$reply" "$EXPECTED_HANDOFF_must_have" "$EXPECTED_HANDOFF_must_not_have" "$name/handoff" || fail=$((fail + 1))
      fi
      ;;
  esac

  # Probe 4: phase responsibility follows workflow identity, not prompt profile.
  reply=$(post_question_wait_reply "$company" "$uuid" "$PROBE_Q_PHASE_ORCHESTRATION" 90)
  if [ -z "$reply" ]; then
    log err "  $name: no reply to phase_orchestration"
    fail=$((fail + 1))
  else
    case "$workflow_role" in
      outer_walker)
        _check_markers "$reply" "$EXPECTED_PHASES_outer_walker_must_have" "1 2 3 4 5 6 7" "$name/phases($workflow_role)" || fail=$((fail + 1))
        ;;
      inner_orchestrator)
        _check_markers "$reply" "$EXPECTED_PHASES_inner_orchestrator_must_have" "outer_walker" "$name/phases($workflow_role)" || fail=$((fail + 1))
        ;;
      *)
        _check_markers "$reply" "NONE" "outer_walker inner_orchestrator release-cut" "$name/phases($workflow_role)" || fail=$((fail + 1))
        ;;
    esac
  fi

  if [ "$fail" -eq 0 ]; then
    log ok "  $name probes pass"
  fi
  return "$fail"
}

# probe_e2e_handoff <company> <cto_uuid> <cto_name> <next_uuid> <next_name>
#   [project_uuid] [cto_workspace_uuid] [next_workspace_uuid] [timeout_seconds]
#   [stable_execution_workspace]
probe_e2e_handoff() {
  local company="$1"; local cto_uuid="$2"; local cto_name="$3"; local next_uuid="$4"; local next_name="$5"
  local project_uuid="${6:-}"; local cto_workspace_uuid="${7:-}"; local next_workspace_uuid="${8:-}"
  local timeout="${9:-180}"
  local stable_execution_workspace="${10:-0}"
  [[ "$timeout" =~ ^[0-9]+$ ]] && [ "$timeout" -ge 30 ] && [ "$timeout" -le 900 ] || {
    log err "invalid e2e timeout"; return 1;
  }
  local question="POST an evidence comment to /api/issues/{id}/comments ending with @${next_name}; require 2xx. Then PATCH /api/issues/{id} to assign ${next_name} (uuid ${next_uuid}) and keep status todo."
  if [ -n "$project_uuid" ]; then
    [ -n "$cto_workspace_uuid" ] && [ -n "$next_workspace_uuid" ] || {
      log err "project-aware e2e probe requires both workspace bindings"; return 1;
    }
    if [ "$stable_execution_workspace" -eq 1 ]; then
      question="${question} In the same PATCH keep projectId ${project_uuid}, projectWorkspaceId ${next_workspace_uuid}, and the existing executionWorkspaceId unchanged."
    else
      question="${question} In the same PATCH keep projectId ${project_uuid} and set projectWorkspaceId ${next_workspace_uuid}."
    fi
  fi
  question="${question} Perform exactly one read-only verification of assignee/status/project/workspace, ask them to reply exactly 'cross-target ack', then STOP."

  local title
  title="smoke-e2e-$(date -u +%Y%m%dT%H%M%SZ)"
  local body
  body=$(jq -n \
    --arg c "$company" --arg a "$cto_uuid" --arg t "$title" --arg q "$question" \
    --arg p "$project_uuid" --arg w "$cto_workspace_uuid" \
    --argjson stable "$stable_execution_workspace" \
    '{companyId: $c, title: $t, description: $q, status: "todo", assigneeAgentId: $a}
     + (if $p == "" then {} else {projectId: $p, projectWorkspaceId: $w} end)
     + (if $stable == 1 then {executionWorkspaceSettings:{mode:"isolated_workspace"}} else {} end)')
  local issue_id
  issue_id=$(paperclip_post "/api/companies/${company}/issues" "$body" | jq -r .id)
  [ -n "$issue_id" ] && [ "$issue_id" != "null" ] || { log err "e2e issue create failed"; return 1; }
  _record_smoke_issue "$issue_id" || return 1

  local elapsed=0
  local expected_execution_workspace_uuid=""
  local current_execution_workspace_uuid=""
  local current_project_workspace_uuid=""
  while [ "$elapsed" -lt "$timeout" ]; do
    sleep 10; elapsed=$((elapsed + 10))
    local issue
    issue=$(paperclip_get "/api/issues/${issue_id}" 2>/dev/null || echo "{}")
    if [ "$stable_execution_workspace" -eq 1 ]; then
      current_execution_workspace_uuid=$(echo "$issue" | jq -r '.executionWorkspaceId // ""')
      if [ -n "$current_execution_workspace_uuid" ] && [ -z "$expected_execution_workspace_uuid" ]; then
        expected_execution_workspace_uuid="$current_execution_workspace_uuid"
      fi
    fi
    local current_assignee
    current_assignee=$(echo "$issue" | jq -r '.assigneeAgentId // ""')
    if [ "$current_assignee" = "$next_uuid" ]; then
      if [ "$stable_execution_workspace" -eq 1 ]; then
        current_project_workspace_uuid=$(echo "$issue" | jq -r '.projectWorkspaceId // ""')
        current_execution_workspace_uuid=$(echo "$issue" | jq -r '.executionWorkspaceId // ""')
        if [ "$current_project_workspace_uuid" != "$next_workspace_uuid" ] || \
           [ -z "$expected_execution_workspace_uuid" ] || \
           [ "$current_execution_workspace_uuid" != "$expected_execution_workspace_uuid" ]; then
          log err "  shared Project/Execution workspace identity changed during handoff"
          paperclip_patch "/api/issues/${issue_id}" '{"status": "done"}' >/dev/null 2>&1 || true
          return 1
        fi
      fi
      local handoff_comments handoff_comment
      handoff_comments=$(paperclip_get "/api/issues/${issue_id}/comments" 2>/dev/null || echo "[]")
      handoff_comment=$(echo "$handoff_comments" | jq -r --arg a "$cto_uuid" --arg n "$next_name" \
        '[.[] | select(.authorAgentId == $a and (.body | contains("@" + $n)))] | last.body // ""')
      if [ -z "$handoff_comment" ]; then
        log err "  ${cto_name} reassigned without the required prior evidence comment"
        paperclip_patch "/api/issues/${issue_id}" '{"status": "done"}' >/dev/null 2>&1 || true
        return 1
      fi
      log ok "  CTO reassigned to ${next_name}; waiting for ack reply"
      while [ "$elapsed" -lt "$timeout" ]; do
        sleep 10; elapsed=$((elapsed + 10))
        local comments
        comments=$(paperclip_get "/api/issues/${issue_id}/comments" 2>/dev/null || echo "[]")
        local ack
        ack=$(echo "$comments" | jq -r --arg a "$next_uuid" '[.[] | select(.authorAgentId == $a)] | last.body // ""')
        if echo "$ack" | grep -qi "cross-target ack"; then
          paperclip_patch "/api/issues/${issue_id}" '{"status": "done"}' >/dev/null 2>&1 || true
          log ok "  e2e handoff round-trip success"
          return 0
        fi
      done
      log err "  next agent never replied with ack within total ${timeout}s"
      paperclip_patch "/api/issues/${issue_id}" '{"status": "done"}' >/dev/null 2>&1 || true
      return 1
    fi
  done
  log err "  CTO never reassigned within ${timeout}s"
  paperclip_patch "/api/issues/${issue_id}" '{"status": "done"}' >/dev/null 2>&1 || true
  return 1
}
