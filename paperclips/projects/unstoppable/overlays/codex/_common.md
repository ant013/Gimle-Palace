## Unstoppable Runtime Scope

This bundle inherits the shared Gimle/CX role text above. The base text was
authored for Gimle-Palace; for **Unstoppable** the substitutions below take
precedence over any conflicting reference up there.

- **Paperclip company**: Unstoppable (`UNS`).
- **Runtime agent**: `{{agent.agent_name}}`.
- **Team model**: ONE codex team works across a **family of three iOS apps** that
  all share a single `WalletCore` Swift package. Do not stand up per-app agents.
- **Workspace cwd**: `{{paths.team_workspace_root}}` — the parent that holds all
  app repos as siblings plus the shared `WalletCore`.
- **Primary codebase-memory project**: `{{agent.primary_codebase_memory_project}}`.
- **Required base MCP set**: `codebase-memory`, `context7`, `serena`, `github`,
  `sequential-thinking`. No Unstoppable-specific MCP in v1.
- **Instruction entry file**: each Unstoppable Codex role uses its own managed
  bundle file (`UnstoppableCEO.md`, `UnstoppableCTO.md`, …) because the default
  `AGENTS.md` path is shared across this all-Codex team.

### App family + repositories

| Paperclip project | Repo | Branch | Notes |
|---|---|---|---|
| `ios-app`    | `horizontalsystems/unstoppable-wallet-ios` (public)  | `version/0.49` | base app; **owns** `packages/WalletCore` |
| `stable-app` | `horizontalsystems/stable-wallet-ios` (**private**)  | `version/1.0`  | stablecoin variant |
| `swap-app`   | `ant013/multi-swap-ios` (private)                    | `main`         | swap-only variant |

- **Sibling layout (required):** all three repos live as siblings under the
  workspace root, e.g. `{{paths.team_workspace_root}}/{unstoppable-wallet-ios,
  stable-wallet-ios, multi-swap-ios}`.
- **Shared WalletCore (hard rule):** there is exactly ONE WalletCore at
  `unstoppable-wallet-ios/packages/WalletCore`. `stable-app` and `swap-app`
  reference it via their `Wallet.xcworkspace` (`group:../unstoppable-wallet-ios/packages/WalletCore`)
  and must NOT carry a local copy. A change to WalletCore affects all three apps —
  route any core change through the CTO; never fork the core to satisfy one app.
- **Per-issue repo selection:** each Paperclip issue belongs to one app project.
  Work in that app's repo; open its `Wallet.xcworkspace`; build its scheme.
- **Never push to upstream `horizontalsystems`** unless the issue explicitly
  authorizes it. `swap-app` pushes to `ant013/multi-swap-ios`.

### Substitution table

| Base text reference (Gimle/UW) | Unstoppable equivalent |
|---|---|
| `services/palace-mcp/` or `palace.*` MCP namespace | No MCP service in Unstoppable v1. Use base MCPs. |
| Graphiti / Neo4j extractor work | Not applicable — skip. |
| `/Users/Shared/Ios/Gimle-Palace` production checkout | `{{paths.primary_repo_root}}` (active app repo). |
| `docs/superpowers/specs` / `docs/superpowers/plans` | `docs/specs` + `docs/plans` IN the active app repo. |
| `develop` integration branch | each app's own mainline (`version/0.49` / `version/1.0` / `main`). No `develop`. |
| `feature/GIM-N-<slug>` branch convention | `feature/<phase-id>-<slug>` (operator's phase scheme, not the paperclip number). |
| Python / `uv` / `ruff`/`mypy`/`pytest` | Swift / Xcode: `xcodebuild`, Swift Package Manager, `swiftlint`, `swiftformat`, XCTest / Swift Testing. |
| Gimle/CX or Trading agent names | Unstoppable roster below only. |

### Code discovery, memory & implementation — Gimle palace + analog-driven-development

**Discovery & memory run on the Gimle code-memory palace** (MCP `palace-memory` → `http://127.0.0.1:8765/mcp`). Use it BEFORE grep/rg:
- code discovery: `palace.code.semantic_search` → `palace.code.search_graph` (pattern) → `palace.code.find_references` / `find_idiom` / `get_code_snippet`. Tier-fallback to serena (LSP) then guarded `rg` ONLY when palace underfills.
- cross-session memory: `palace.memory.lookup` (read Decisions at task start) / `palace.memory.decide` (write back at task end).

**Project slugs — mind the read/write split:**
- `code_project_slug = uw-ios-app` for ALL `palace.code.*` analogs and `palace.memory.*`. This is the indexed codebase (WalletCore + shells) where analogs live.
- **git/PR target = the active issue's app repo** (App-family table): swap-app → `multi-swap-ios`, ios-app → `unstoppable-wallet-ios`, stable-app → `stable-wallet-ios`. `palace.git.*` takes that repo's `git_repo_slug`, NOT `uw-ios-app`. Write code, branch and open the PR in that app repo.

**WalletCore reuse rule (hard):** reuse WalletCore to the MAX (its ViewModels, address-input + validation, ScanQr, QR render, theme, formatters). If a fitting module/class is `internal`, widen it to `public` — **visibility-only, NO behavioral/logic change**. Never fork or behaviorally edit WalletCore.

### Finding your assigned work (this paperclip instance)

Your assigned issues live on the company board. Query them **company-scoped**:
`GET $PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues?assigneeAgentId=$PAPERCLIP_AGENT_ID` (Bearer `$PAPERCLIP_API_KEY`).
⚠️ The flat `/api/issues` endpoint returns EMPTY on this instance — never rely on it. If `PAPERCLIP_TASK_ID` is empty on wake, you MUST check the company-scoped board for issues assigned to you in ANY active status (todo / in_progress / **in_review** / blocked) before idle-exiting. An `in_review` issue assigned to you is YOUR review to perform now — do not idle-exit past it.

### Gimle Skills — analog-driven-development is MANDATORY

**HARD RULE (non-negotiable):** EVERY implement / add / modify / extend / fix / refactor task on the indexed codebase MUST be executed through the **analog-driven-development** skill. No spec, no plan, no code, and no PR may bypass it. Implementing without first running the skill's protocol (analog-discovery via palace → delta-matrix → adversarial-verify → design-first) is a process violation — surface it and STOP, do not freelance.

- Skill at `/Users/ant013/Data/AI/gimle-skills/analog-driven-development/SKILL.md`. On the FIRST matching trigger, immediately read its SKILL.md + the files it references under `references/`/`agents/` BEFORE any other action, and follow its protocol EXACTLY. Skill instructions override default behavior where they conflict.
- **Design-approval gate in the autonomous walker:** the skill's "no code until the design is approved" gate is satisfied by the **CodeReviewer's spec review (phase 2)** plus the CTO's plan (phase 3) — that IS the approving authority inside the loop. Do NOT pause for a human; the CR + CTO review is the gate.
- Skip only if the operator explicitly disabled the skill for the session.

### Workflow chain (proven Trading two-loop pattern)

Unstoppable runs **two loops** per app:

- **Outer loop** — one parent `roadmap walker` issue per app project, assigned to
  UnstoppableCTO. CTO reads that app's `ROADMAP.md`, finds the next `### X.Y <Name>`
  heading NOT followed by a `**Status:** ✅` line within 3 lines, spawns ONE child,
  waits for it to close, then advances. At phase 7 the CTO adds the
  `**Status:** ✅ Implemented — PR #<N>` line on the feature branch (lands on the
  app mainline via the squashed PR — no direct push to mainline).
- **Inner loop** (per child) — 7 transitions:
  1. **CTO** cuts `feature/<phase-id>-<slug>` from the app mainline + drafts spec →
  2. **CodeReviewer** reviews the spec (adversarial subagents: arch / security / UX) →
  3. **CTO** writes the plan addressing CR blockers →
  4. **SwiftEngineer** implements (TDD) + opens PR to the app mainline →
  5. **CodeReviewer** reviews code (mechanical: build + `swiftlint`/`swiftformat` + XCTest, paste output) →
  6. **QAEngineer** smoke (build the scheme, run tests, evidence) →
  7. **CTO** squash-merges PR + closes child + advances parent.

CR sees the **spec first** (phase 2); the plan is written by CTO post-review. QA
routing is non-judgmental (pass/fail on pinned criteria).

### Agent roster

Use these formal mentions in handoffs. Never copy UUIDs from another Paperclip company.

| Role | Formal mention |
|---|---|
| CEO | `[@UnstoppableCEO](agent://{{bindings.agents.UnstoppableCEO}}?i=crown)` |
| CTO | `[@UnstoppableCTO](agent://{{bindings.agents.UnstoppableCTO}}?i=shield)` |
| CodeReviewer | `[@UnstoppableCodeReviewer](agent://{{bindings.agents.UnstoppableCodeReviewer}}?i=eye)` |
| SwiftEngineer | `[@UnstoppableSwiftEngineer](agent://{{bindings.agents.UnstoppableSwiftEngineer}}?i=code)` |
| QAEngineer | `[@UnstoppableQAEngineer](agent://{{bindings.agents.UnstoppableQAEngineer}}?i=bug)` |

### Telegram routing

Lifecycle events are auto-routed by `paperclip-plugin-telegram` once the operator
configures the per-company bot token + chats. Agents do NOT call Telegram actions
manually for lifecycle events.

### Report delivery

Final markdown reports go to `{{paths.project_root}}/artifacts/{{agent.agent_name}}/`.
Operator handles delivery until a delivery owner is designated.

### Operator memory location

Unstoppable auto-memory: `~/.claude/projects/-Users-ant013-Ios-HorizontalSystems/memory/`.
Do not write Gimle/Trading/UAudit memory paths.
