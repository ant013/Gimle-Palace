# GIM-197 — SecurityAuditor survey response

> Saved locally because CTO holds execution lock on GIM-197; fallback if API comment fails.

---

## A. Tool inventory

### A1. Subagents available (verbatim from available-subagents list)

Full list from Agent tool (subagent_type parameter options observed in session):

- `accessibility-tester`, `ad-security-reviewer`, `agent-installer`, `agent-organizer`, `ai-engineer`, `ai-writing-auditor`, `angular-architect`, `api-designer`, `api-documenter`, `architect-reviewer`, `backend-architect`, `backend-developer`, `blockchain-developer`, `build-engineer`, `business-analyst`, `business-panel-experts`, `chaos-engineer`, `cloud-architect`, `code-reviewer`, `competitive-analyst`, `compliance-auditor`, `content-marketer`, `context-manager`, `cpp-pro`, `customer-success-manager`, `data-analyst`, `data-engineer`, `data-researcher`, `data-scientist`, `database-administrator`, `database-optimizer`, `debugger`, `deep-research-agent`, `dependency-manager`, `deployment-engineer`, `design-bridge`, `devops-architect`, `devops-engineer`, `docker-expert`, `electron-pro`, `embedded-systems`, `error-coordinator`, `error-detective`, `Explore`, `fastapi-developer`, `fintech-engineer`, `flutter-expert`, `frontend-architect`, `frontend-developer`, `fullstack-developer`, `game-developer`, `general-purpose`, `golang-pro`, `graphql-architect`, `iot-engineer`, `it-ops-orchestrator`, `java-architect`, `javascript-pro`, `knowledge-synthesizer`, `kotlin-specialist`, `kubernetes-specialist`, `learning-guide`, `legal-advisor`, `license-engineer`, `llm-architect`, `m365-admin`, `machine-learning-engineer`, `market-researcher`, `mcp-developer`, `microservices-architect`, `ml-engineer`, `mlops-engineer`, `mobile-app-developer`, `mobile-developer`, `multi-agent-coordinator`, `network-engineer`, `nextjs-developer`, `nlp-engineer`, `payment-integration`, `penetration-tester`, `performance-engineer`, `performance-monitor`, `Plan`, `platform-engineer`, `pm-agent`, `postgres-pro`, `powershell-5.1-expert`, `powershell-7-expert`, `powershell-security-hardening`, `powershell-ui-architect`, `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:code-simplifier`, `pr-review-toolkit:comment-analyzer`, `pr-review-toolkit:pr-test-analyzer`, `pr-review-toolkit:silent-failure-hunter`, `pr-review-toolkit:type-design-analyzer`, `product-manager`, `project-idea-validator`, `project-manager`, `prompt-engineer`, `python-expert`, `python-pro`, `qa-expert`, `quality-engineer`, `quant-analyst`, `react-specialist`, `readme-generator`, `refactoring-expert`, `reinforcement-learning-engineer`, `requirements-analyst`, `research-analyst`, `risk-manager`, `root-cause-analyst`, `rust-engineer`, `sales-engineer`, `scientific-literature-researcher`, `scrum-master`, `search-specialist`, `security-auditor`, `security-engineer`, `seo-specialist`, `socratic-mentor`, `sql-pro`, `statusline-setup`, `swift-expert`, `system-architect`, `task-distributor`, `technical-writer`, `test-automator`, `trend-analyst`, `typescript-pro`, `ui-designer`, `ux-researcher`, `vue-expert`, `websocket-engineer`, `wordpress-master`, `workflow-orchestrator`, plus full `voltagent-*` namespaced variants.

**Audit finding F1 — FAIL:** `kotlin-specialist` (bare) and `voltagent-lang:kotlin-specialist` appear in the available-subagents list. Post-Phase-2 disable has NOT taken effect in my loaded bundle.

Per my AGENTS.md `## Subagents / Skills`, my intended subagents are:
- `Explore`
- `voltagent-qa-sec:code-reviewer` (security-focused PR review)
- `voltagent-research:search-specialist` (CVE landscape lookup)

### A2. Skills loaded (verbatim from available-skills list)

- `update-config` — configure Claude Code harness via settings.json
- `keybindings-help` — customize keyboard shortcuts
- `simplify` — review changed code for quality and efficiency
- `fewer-permission-prompts` — scan transcripts, add allowlist to reduce prompts
- `loop` — run prompt on recurring interval
- `schedule` — create/manage scheduled remote agents
- `claude-api` — build/debug/optimize Claude API / Anthropic SDK apps
- `paperclip` — interact with Paperclip control plane API
- `paperclip-create-plugin` — create new Paperclip plugins
- `paperclip-converting-plans-to-tasks` — convert plans into executable tasks
- `para-memory-files` — file-based memory system using PARA method
- `paperclip-create-agent` — create new agents in Paperclip
- `paperclip-dev` — develop and operate local Paperclip instance
- `sc:document`, `sc:spawn`, `sc:estimate`, `sc:spec-panel`, `sc:implement`, `sc:troubleshoot`, `sc:business-panel`, `sc:improve`, `sc:explain`, `sc:reflect`, `sc:analyze`, `sc:workflow`, `sc:select-tool`, `sc:help`, `sc:load`, `sc:research`, `sc:index`, `sc:build`, `sc:save`, `sc:git`, `sc:task`, `sc:design`, `sc:pm`, `sc:cleanup`, `sc:test`, `sc:brainstorm`
- `prime` — assemble role-scoped context snapshot for current slice
- `pr-review-toolkit:review-pr` — comprehensive PR review
- `code-review:code-review` — code review a pull request
- `superpowers:*` (full set: using-git-worktrees, test-driven-development, subagent-driven-development, verification-before-completion, writing-skills, receiving-code-review, requesting-code-review, writing-plans, brainstorming, finishing-a-development-branch, executing-plans, dispatching-parallel-agents, using-superpowers, systematic-debugging)
- `init` — initialize a new CLAUDE.md file
- `review` — review a pull request
- `security-review` — complete a security review of pending changes

### A3. MCP servers connected

| Server | Tools exposed |
|---|---|
| **context7** | `query-docs`, `resolve-library-id` |
| **serena** | `check_onboarding_performed`, `delete_memory`, `edit_memory`, `find_referencing_symbols`, `find_symbol`, `get_symbols_overview`, `initial_instructions`, `insert_after_symbol`, `insert_before_symbol`, `list_memories`, `onboarding`, `read_memory`, `rename_memory`, `rename_symbol`, `replace_symbol_body`, `safe_delete_symbol`, `write_memory` |
| **supabase** | `apply_migration`, `confirm_cost`, `create_branch`, `create_project`, `delete_branch`, `deploy_edge_function`, `execute_sql`, `generate_typescript_types`, `get_advisors`, `get_cost`, `get_edge_function`, `get_logs`, `get_organization`, `get_project`, `get_project_url`, `get_publishable_keys`, `list_branches`, `list_edge_functions`, `list_extensions`, `list_migrations`, `list_organizations`, `list_projects`, `list_tables`, `merge_branch`, `pause_project`, `rebase_branch`, `reset_branch`, `restore_project`, `search_docs` |
| **playwright** | `browser_click`, `browser_close`, `browser_console_messages`, `browser_drag`, `browser_drop`, `browser_evaluate`, `browser_file_upload`, `browser_fill_form`, `browser_handle_dialog`, `browser_hover`, `browser_navigate`, `browser_navigate_back`, `browser_network_request`, `browser_network_requests`, `browser_press_key`, `browser_resize`, `browser_run_code_unsafe`, `browser_select_option`, `browser_snapshot`, `browser_tabs`, `browser_take_screenshot`, `browser_type`, `browser_wait_for` |
| **sequential-thinking** | `sequentialthinking` |
| **filesystem** | `create_directory`, `directory_tree`, `edit_file`, `get_file_info`, `list_allowed_directories`, `list_directory`, `list_directory_with_sizes`, `move_file`, `read_file`, `read_media_file`, `read_multiple_files`, `read_text_file`, `search_files`, `write_file` |
| **github** | `add_issue_comment`, `create_branch`, `create_issue`, `create_or_update_file`, `create_pull_request`, `create_pull_request_review`, `create_repository`, `fork_repository`, `get_file_contents`, `get_issue`, `get_pull_request`, `get_pull_request_comments`, `get_pull_request_files`, `get_pull_request_reviews`, `get_pull_request_status`, `list_commits`, `list_issues`, `list_pull_requests`, `merge_pull_request`, `push_files`, `search_code`, `search_issues`, `search_repositories`, `search_users`, `update_issue`, `update_pull_request_branch` |
| **magic** | `21st_magic_component_builder`, `21st_magic_component_inspiration`, `21st_magic_component_refiner`, `logo_search` |
| **tavily** | `tavily-extract`, `tavily-search` |
| **Gmail** | `authenticate`, `complete_authentication` |
| **Google Calendar** | `authenticate`, `complete_authentication` |
| **Google Drive** | `authenticate`, `complete_authentication` |

---

## B. Handoff & assign rules

### B1. Exact API call sequence for phase handoff

```
PATCH /api/issues/{id}
{
  "status": "<next-status>",
  "assigneeAgentId": "<next-agent-uuid>",
  "comment": "## Phase N.M complete\n\n[evidence]\n\n[@NextAgent](agent://<uuid>?i=<icon>) your turn — Phase N.M+1"
}
```
Then immediately: `GET /api/issues/{id}` to verify `assigneeAgentId` equals expected. If mismatch → retry once with same payload. If still mismatch → `PATCH status=blocked` + escalate to Board with `assigneeAgentId.actual != expected`.

### B2. Comment ≠ handoff iron rule

Writing "Reassigning to…" or "handing off to…" in a comment body **does not execute a handoff**. Only `PATCH /api/issues/{id}` with `assigneeAgentId` triggers the next agent's wake. Without PATCH, the issue stalls with the previous assignee indefinitely. Precedents: GIM-126 (QA→CTO stall, 2026-05-01), GIM-195 (CR→PE stall, 2026-05-05).

### B3. Formal mention vs plain @Role

**Phase handoffs REQUIRE formal form:** `[@Role](agent://<uuid>?i=<icon>)` — formal form is the recovery wake when assignee PATCH flakes.  
**Plain `@Role`** is acceptable for regular comments and @-mentions (wakes ordinary comments).  
**Rule:** "End of phase → always formal-mention next agent in the comment, even if already assignee."

### B4. Wake mechanism

**Event-driven** (mention-wake / comment-wake). This heartbeat was triggered by `issue_comment_mentioned` — CTO posted a comment with `[@SecurityAuditor](agent://a56f9e4a...)`.

### B5. HTTP 409 lock conflict resolution

1. `GET /api/issues/{id}` → read `executionAgentNameKey` (lock holder).
2. Comment to holder: "release execution lock on [GIM-X], I'm ready to close."
3. Alternative: `PATCH assigneeAgentId=<original-assignee>` → originator closes.
4. Observed workaround (GIM-52/53): `PATCH assignee=me` → `POST /release` → `PATCH assignee=<next>`.
5. **Never retry** the conflicting close call with the same JWT — without release, 409 keeps coming.

---

## C. Phase awareness

### C1. Canonical phase order (1.1 → 4.2)

| Phase | Role | Action |
|---|---|---|
| 1.1 | CTO | Formalize — verify spec/plan paths, swap GIM-NN placeholder |
| 1.2 | CodeReviewer | Plan-first review — validate every task has test+impl+commit |
| 2 | MCPEngineer / PythonEngineer / … | TDD implementation on feature branch |
| 3.1 | CodeReviewer | Mechanical review — paste ruff/mypy/pytest output, APPROVE |
| 3.2 | OpusArchitectReviewer | Adversarial review — poke holes |
| 4.1 | QAEngineer | Live smoke on iMac — real MCP call + CLI + Cypher invariant |
| 4.2 | CTO | Squash-merge to develop after CI green |

### C2. My specific role

**SecurityAuditor** is an **optional hire** (per spec §6.2). I am NOT in the standard phase sequence. I am invoked only when serious security work is required:
- MCP threat model (palace-mcp exposure changes, new tools)
- Wallet attack surface (Unstoppable integration)
- Docker Compose security (CIS Docker Benchmark)
- Secrets/sops audit (quarterly, major rotation)
- Cloudflared scope audit (tunnel exposure changes)
- Compliance mapping (GDPR/PCI/SOC2 — currently out-of-scope per project purpose)

### C3. Evidence required before `status=done`

- Phase 4.1 evidence-comment authored by **QAEngineer** (not implementer/CR), containing:
  1. Commit SHA tested
  2. `docker compose ps` — containers healthy
  3. `/healthz` check
  4. Real MCP tool call (not just healthz)
  5. Runtime smoke command output
  6. Direct Cypher invariant check (plan-specific)
- CI green on merge commit
- Production deploy completed post-merge
- `/healthz`-only evidence is **insufficient** — must show real functionality.

---

## D. Discipline rules

### D1. Pre-work discovery

Before writing code or decomposing, verify the feature/fix doesn't already exist:

```bash
git fetch --all && git log --all --grep="<keyword>" --oneline
gh pr list --state all --search "<keyword>"          # open and merged
serena find_symbol / get_symbols_overview            # existing implementations
# check docs/ — spec may already be written
# check Paperclip issues — is someone already working on it?
```

If it exists → close as `duplicate` with a link, or reframe ("integrate X from feature/Y").

### D2. "Don't mock substrate" rule for happy-path tests

Integration tests (happy-path) **must hit a real database/substrate**, not mocks. Mocked tests can pass while prod migrations fail — prior incident confirmed mock/prod divergence masked a broken migration. `MCP server absent at runtime → escalate to Board; do NOT proceed with LLM-reasoning fabrication` (per my AGENTS.md: "If MCP server absent at runtime — escalate to Board, do NOT proceed with LLM-reasoning fabrication").

### D3. "Silent scope reduction" antipattern

Silently dropping scope or closing an issue as "not actionable" without informing Board. Per AGENTS.md escalation rules: "DON'T silently close an issue as 'not actionable' — Board must see the blocker." The antipattern is: blocker exists → agent quietly abandons scope → no Board notification → lost work.

---

## E. Self-verification

### E1. No work assigned at idle wake

Exit immediately with `"No assignments, idle exit"`. Check only three things:
1. `PAPERCLIP_TASK_ID` non-empty + assigned to me → work
2. `GET /api/agents/me` → any issue with `assigneeAgentId=me` and `in_progress` → continue
3. Comments/@mentions with `createdAt > last_heartbeat_at` → reply

None of three → **exit immediately**. Each idle heartbeat must cost **<500 tokens**.

### E2. When to escalate to Board

- Unclear / contradictory spec — no single interpretation
- Missing dependency / tool / access
- Dependent agent unavailable or unresponsive
- Technical obstacle outside area of responsibility
- HTTP 409 execution lock conflict and lock-holder doesn't respond
- Success criteria fuzzy — unclear what "done" means

Protocol: mark issue `blocked` → comment with `@Board blocked:` format (what's needed / blocker / tried / need from Board).

### E3. Self-initiate?

**NO.** Work starts ONLY from:
- (a) Board/CEO/manager created/assigned an issue this session
- (b) Someone @mentioned me with a concrete task
- (c) `PAPERCLIP_TASK_ID` was passed at wake

"Unassigned ≠ 'I'll find work.'" Taking `todo` issues nobody assigned → **forbidden**.

---

## F. Phase 2 plugin sanity

### F1. Is `voltagent-lang:kotlin-specialist` invocable?

**YES — AUDIT FINDING FAIL.** `kotlin-specialist` appears in my available-subagents list (both bare and voltagent-namespaced form). Post-Phase-2 disable has NOT taken effect in my loaded bundle. Expected: NO.

### F2. Fallback for Kotlin code review

`voltagent-qa-sec:code-reviewer` for security-focused PR review. For general code quality, `code-reviewer`.

### F3. 4 disabled `voltagent-*` plugins (per Phase 2 settings.json)

1. `voltagent-lang`
2. `voltagent-infra`
3. `voltagent-meta`
4. `voltagent-core-dev`

---

## G. Phase 4.5 wake terminology

### G1. "Heartbeat" vs "wake-execution-window"

**Cannot fully answer from current bundle — see G3.** Per pre-slim understanding: "heartbeat" = periodic scheduled check-in (timer-based); "wake-execution-window" = the bounded execution window when an agent wakes (event-driven or scheduled). Post-slim rename aligns terminology: wake = the triggering event; execution-window = bounded run time within that wake.

### G2. Is `runtimeConfig.heartbeat.enabled` true or false?

**Cannot directly verify from my loaded context.** Per issue description, post-slim should be `false`. Cannot quote a value from my bundle.

### G3. Reconciliation note from wake-discipline section

**AUDIT FINDING FAIL — G3:** My loaded bundle has section heading `## Heartbeat discipline`, NOT `## Wake discipline`. The reconciliation note does not exist in my bundle. My bundle is **pre-slim**.

For reference, the section that exists in my bundle:
> "On every wake (heartbeat or event) check only three things: 1. PAPERCLIP_TASK_ID... 2. GET /api/agents/me... 3. Comments/@mentions... None of three → exit immediately..."

The new reconciliation note (expected but absent) would distinguish "heartbeat" from "wake-execution-window" and note the rename. **Cannot quote it because it was not loaded.**

---

## Summary of audit findings

| Check | Status | Finding |
|---|---|---|
| G3 — Wake discipline heading | **FAIL** | Bundle has `## Heartbeat discipline`, not `## Wake discipline`. Pre-slim bundle. |
| F1 — voltagent-lang:kotlin-specialist disabled | **FAIL** | Appears invocable in my subagents list. Disable did not take effect. |
| G2 — runtimeConfig.heartbeat.enabled | **⚠️ UNVERIFIABLE** | Cannot confirm from loaded context. |
| G3 — Reconciliation note | **FAIL** | Section does not exist in bundle (pre-slim). |
| All other sections (A–E, F2–F3, B–D) | **PASS** | Rules correctly loaded and can be cited. |
