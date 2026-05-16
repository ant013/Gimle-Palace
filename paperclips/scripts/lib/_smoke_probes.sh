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
PROBE_Q_HANDOFF_PROCEDURE="Describe step-by-step how you handoff a task to another agent in this team. Include the exact API endpoints you call."
PROBE_Q_PHASE_ORCHESTRATION="List the phase numbers you orchestrate (e.g. 1.1, 1.2, ...), comma-separated. If you do not orchestrate phases, reply: NONE."

# Per-profile expected markers.
EXPECTED_MCP_LIST="codebase-memory serena context7 github sequential-thinking"

EXPECTED_GIT_implementer_must_have="commit push fetch"
EXPECTED_GIT_implementer_must_not_have="merge release-cut"
EXPECTED_GIT_reviewer_must_have="approve"
EXPECTED_GIT_reviewer_must_not_have="commit push release-cut"
EXPECTED_GIT_cto_must_have="merge release-cut"
EXPECTED_GIT_cto_must_not_have=""
EXPECTED_GIT_writer_must_have=""
EXPECTED_GIT_writer_must_not_have="commit push merge"
EXPECTED_GIT_research_must_have=""
EXPECTED_GIT_research_must_not_have="commit push merge"
EXPECTED_GIT_qa_must_have="commit push"
EXPECTED_GIT_qa_must_not_have="release-cut"

EXPECTED_HANDOFF_must_have="PATCH @"
EXPECTED_HANDOFF_must_not_have=""

EXPECTED_PHASES_cto_must_have="1.1 1.2 2 3.1 3.2 4.1 4.2"

# post_question_wait_reply <company_id> <agent_uuid> <question_text> <timeout_s>
# Returns reply text on stdout; empty if timeout.
post_question_wait_reply() {
  local company="$1"; local uuid="$2"; local question="$3"; local timeout_s="${4:-90}"
  local title="smoke-probe-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
  local body
  body=$(jq -n --arg c "$company" --arg a "$uuid" --arg t "$title" --arg q "$question" \
    '{companyId: $c, title: $t, body: $q, status: "todo", assigneeAgentId: $a}')
  local issue_id
  issue_id=$(paperclip_post "/api/companies/${company}/issues" "$body" | jq -r .id)
  [ -n "$issue_id" ] && [ "$issue_id" != "null" ] || { log warn "issue create failed"; echo ""; return 1; }

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

# probe_agent_for_profile <company> <uuid> <name> <profile>
probe_agent_for_profile() {
  local company="$1"; local uuid="$2"; local name="$3"; local profile="$4"
  local fail=0

  # Probe 1: MCP list (all profiles)
  local reply
  reply=$(post_question_wait_reply "$company" "$uuid" "$PROBE_Q_MCP_LIST" 90)
  if [ -z "$reply" ]; then
    log err "  $name: no reply to mcp_list within 90s"
    fail=$((fail + 1))
  else
    _check_markers "$reply" "$EXPECTED_MCP_LIST" "" "$name/mcp_list" || fail=$((fail + 1))
  fi

  # Probe 2: git capability (per profile)
  reply=$(post_question_wait_reply "$company" "$uuid" "$PROBE_Q_GIT_CAPABILITY" 90)
  if [ -z "$reply" ]; then
    log err "  $name: no reply to git_capability"
    fail=$((fail + 1))
  else
    eval "must_have=\$EXPECTED_GIT_${profile}_must_have"
    eval "must_not=\$EXPECTED_GIT_${profile}_must_not_have"
    _check_markers "$reply" "${must_have:-}" "${must_not:-}" "$name/git_capability($profile)" || fail=$((fail + 1))
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

  # Probe 4: phase orchestration (cto vs others)
  reply=$(post_question_wait_reply "$company" "$uuid" "$PROBE_Q_PHASE_ORCHESTRATION" 90)
  if [ -z "$reply" ]; then
    log err "  $name: no reply to phase_orchestration"
    fail=$((fail + 1))
  else
    if [ "$profile" = "cto" ]; then
      _check_markers "$reply" "$EXPECTED_PHASES_cto_must_have" "" "$name/phases(cto)" || fail=$((fail + 1))
    else
      _check_markers "$reply" "" "1.1 4.2 release-cut" "$name/phases(non-cto)" || fail=$((fail + 1))
    fi
  fi

  if [ "$fail" -eq 0 ]; then
    log ok "  $name probes pass"
  fi
  return "$fail"
}

# probe_e2e_handoff <company> <cto_uuid> <cto_name> <next_uuid> <next_name>
probe_e2e_handoff() {
  local company="$1"; local cto_uuid="$2"; local cto_name="$3"; local next_uuid="$4"; local next_name="$5"
  local question="Reassign this issue to agent ${next_name} (uuid ${next_uuid}) and ask them to reply with exactly: 'cross-target ack'. Then STOP."

  local title="smoke-e2e-$(date -u +%Y%m%dT%H%M%SZ)"
  local body
  body=$(jq -n --arg c "$company" --arg a "$cto_uuid" --arg t "$title" --arg q "$question" \
    '{companyId: $c, title: $t, body: $q, status: "todo", assigneeAgentId: $a}')
  local issue_id
  issue_id=$(paperclip_post "/api/companies/${company}/issues" "$body" | jq -r .id)

  local timeout=180; local elapsed=0
  while [ "$elapsed" -lt "$timeout" ]; do
    sleep 10; elapsed=$((elapsed + 10))
    local issue
    issue=$(paperclip_get "/api/issues/${issue_id}" 2>/dev/null || echo "{}")
    local current_assignee
    current_assignee=$(echo "$issue" | jq -r '.assigneeAgentId // ""')
    if [ "$current_assignee" = "$next_uuid" ]; then
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
