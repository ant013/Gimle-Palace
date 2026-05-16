# Uniform Agent Assembly — Design Spec

| | |
|---|---|
| **Date** | 2026-05-15 (rev4 — post third deep-review of plans + multi-target/runtime-probe additions) |
| **Status** | Draft (pending operator review) |
| **Author** | brainstorm with operator |
| **Scope** | Replace current per-project ad-hoc agent assembly (gimle legacy + trading + uaudit) with a uniform manifest+profile model; reduce per-agent prompt size by 60–80%; make paperclip+agents bring-up reproducible from a clean machine. |
| **Non-goals** | Rewriting paperclipai or telegram plugin; replacing watchdog; changing claude/codex CLI internals; adding new agent capabilities. |

Pinned grounding: this spec is grounded in the repo state at `main@568888a` (2026-05-14 docs/BUGS.md merge). All later commits should be cross-checked when implementing.

**Rev4 changelog (third deep-review of plans + 2 operator strategic questions applied):**
- §3.4 NEW — Target extensibility (`paperclips/roles-<target>/` convention; mixed-team support explicit; cross-target handoff first-class).
- §12.C extended — concrete runtime probe-questions per profile-family (mcp_list / git_capability / handoff_procedure / phase_orchestration) with expected/forbidden markers; replaces vague "operator-live" placeholder.
- Plan rev4 — 25 fixes (PR retarget to develop; CI failure mitigation; Phase B builder contract for output_path generation + agent.profile key fix; Phase C placeholder removal + per-agent role mapping + remove `\|\| true`; Phase D normalize fixed (CXCTO/CXMCPEngineer/CXQAEngineer per actual taxonomy) + heuristic replaced with manifest-target read; Phase F mandatory plugin GET-then-POST; Phase G watchdog-taxonomy gap as pre-flight blocker, 12 not 11; Phase H gate snippet sources _common.sh; smoke-test runtime probes per SM-1..5; multi-target docs per MA-1..3).

**Rev3 changelog (second deep-review feedback applied):**
- §14 added execution-ownership constraint: phases tagged `operator` / `team` / `operator + team` because Phases A–D are self-modifying (gimle team would edit its own runtime contract).
- §1.2 fixed role-file size range (67–167, was 76–114).
- §3.2 reworded to clarify v1 keeps EXISTING inlining cost (not new cost).
- §4.1 fixed library-size comparison (current 441 lines, redesigned ~530 = +20%; real saving is from per-agent selective composition, not library size).
- §5.2 added normative deduplication rule for `inheritsUniversal` + `extends:` chains.
- §6.4 closed open question on override + custom_includes interaction (override applies — they're orthogonal).
- §6.7 NEW — Overlays formalized as third composition mechanism (append-mode), not merged with fragment-override.
- §8.6 / §9.2 canary changed to 2-stage (canary-1 = read-only profile, canary-2 = cto, then fan-out).
- §9.2 added topological hire ordering by `reportsTo` dependency graph.
- §9.4 watchdog config template expanded (full schema, not just thresholds).
- §10 added explicit role-split phase (hybrid: new craft files alongside legacy, deprecation banner on legacy).
- §10.1 cleanup gate metric concretized (zero handoff_alert + zero recovery wake_failed for 7 days from watchdog log).
- §10.4 fixed gimle agent count (24 = 12 claude + 12 codex, not 12).
- §11 platform: clarified — passed to template_values, not consumed by current fragments; opaque-passthrough preserved.
- §13 rebalanced (open Q #5 closed; new open Q on role-split mechanics).
- §14 engineer-day estimates marked as ranges (19–25 days realistic, was 15 optimistic).

**Rev2 changelog (first deep-review feedback applied):**
- §3 Runtime instruction contract clarified — v1 = single AGENTS.md per agent (no split).
- §6.4 Project override seam formalized — keeps existing 4-level builder fallback as first-class.
- §6.5 Allowed template sources — explicit list of host-local sources for `{{vars}}`.
- §6.6 Committed vs generated AGENTS.md — committed is path-free template, generated is gitignored.
- §7 Versioning — all floating versions pinned (no `latest`, no `9.x`).
- §8 API contract section added — exact endpoints + payload shapes from existing scripts.
- §8.5 Mutation safety / rollback journal added.
- §9.4 New script: `bootstrap-watchdog.sh` (config-first install).
- §10 Migration: dual-read period + cleanup gate (no 24h timer).
- §12 Acceptance split into 12A offline-CI / 12B mock-integration / 12C operator-live-smoke.
- §13 Open questions: AGENTS.md split moved to v2 future direction.

---

## 1. Context

### 1.1 Current state — three projects, three layouts

The repo hosts assembly machinery for three sibling projects under one `paperclips/` infrastructure:

| | gimle | trading | uaudit |
|---|---|---|---|
| `agents:` in manifest | empty (legacy mapping) | 5 agents declared | 17 agents declared with `platform` tags |
| `legacy_output_paths` | `true` (flat `dist/<role>.md`) | `false` | `false` |
| dist layout | `dist/<role>.md` + `dist/codex/cx-<role>.md` | `dist/trading/{claude,codex}/<Agent>.md` | `dist/uaudit/codex/<Agent>.md` |
| Agent UUIDs | `paperclips/codex-agent-ids.env` (legacy) + paperclip company storage | inline in manifest YAML | inline in manifest YAML |
| Hardcoded paths | absolute `/Users/Shared/...` in manifest | absolute in manifest | absolute in manifest |
| Telegram plugin | not used | not used | `telegram_plugin_id` inline in manifest |
| Targets | claude + codex | claude + codex | codex-only |

### 1.2 Pain points (operator-confirmed)

1. **Assembled agents are huge.** Source role `.md` files are 67–167 lines (smallest `cx-auditor.md` 67; largest `code-reviewer.md` 167); assembled output is 463–867 lines (4–10× inflation from inlined fragments). Median ~600–700 lines per agent. Top end (`UWIInfraEngineer`) at 867 lines. Note: existing role files mix craft + capability + anti-patterns in one file — see §10 role-split migration step.
2. **Rigid workflow choreography baked into every agent.** Phase orchestration (`1.1 → 1.2 → 2 → 3.1 → 3.2 → 4.1 → 4.2`), formal `[@Role](agent://uuid)` mention rituals, APPROVE comment formats — inlined in every role even for agents that never orchestrate phases.
3. **Hardcoded paths and UUIDs in committed YAML.** Cannot reproduce on another machine without surgically editing manifests.
4. **Three different layouts.** No single way to add a new project; copy-paste leads to drift.

### 1.3 Adjacent reality (constraints)

- **Paperclip heartbeat is disabled** (operator policy). Agent wake is event-driven only (assignee PATCH, @mention, posted comment).
- **Watchdog (`services/watchdog/`, 3416 LOC)** is the safety net for missed wake events: kills idle hangs, respawns died-mid-work, alerts on handoff inconsistencies. Implements 6-class role taxonomy (`role_taxonomy.py`): `cto / reviewer / implementer / qa / research / writer`.
- **Watchdog config is non-empty mandatory.** `load_config` rejects empty `companies` list. Watchdog `install` cannot run before at least one project is bootstrapped (verified — see §9.4).
- **Fragment `heartbeat-discipline.md` is misnamed** — its content is wake-discipline + handoff-hygiene. Significant overlap with `phase-handoff.md`.
- **Telegram integration is via fork** `ant013/paperclip-plugin-telegram` (fork of `mvanhorn/paperclip-plugin-telegram`), not upstream npm. Pinned to `c0423e45` (2026-05-15 main HEAD).
- **Existing builder (`paperclips/scripts/build_project_compat.py`) implements 4-level fragment override fallback**: `projects/<key>/fragments/targets/<target>/X` → `projects/<key>/fragments/X` → `fragments/targets/<target>/X` → `fragments/X`. Trading and uaudit use this. Verified `build_project_compat.py:62-99`.
- **Existing deploy uses `PUT /api/agents/<id>/instructions-bundle/file`** with body `{path: "AGENTS.md", content: "<full markdown>"}` — single AGENTS.md artifact per agent. Verified `deploy_project_agents.py:208`.
- **Existing hire uses `POST /api/companies/<id>/agent-hires`** with full payload including `adapterType`, `adapterConfig{cwd, model, instructionsFilePath, instructionsBundleMode, maxTurnsPerRun, dangerouslyBypassApprovalsAndSandbox, env}`, `runtimeConfig{heartbeat: {enabled: false, ...}}`. Verified `hire-codex-agents.sh:31-90`.
- **paperclipai pinned to `2026.508.0-canary.0`** (2026-05-08T00:21Z, last canary before PR #5429 broke plugin secret-refs).

---

## 2. Design overview

### 2.1 Three perpendicular axes

```
ROLE-FILE     — what craft the agent knows (Swift / Python / MCP / Kotlin / generic)
PROFILE       — what capability-pack the agent gets (implementer / reviewer / qa / cto / ...)
PROJECT       — where the agent works (paths, UUIDs, MCP namespace, integrations)
```

Currently all three are smashed into one `.md` file per agent. The redesign splits them into independent layers, composed by the builder.

### 2.2 Architecture diagram

```
              ┌─────────────────────┐
              │  PROFILE LIBRARY    │   paperclips/fragments/profiles/*.yaml
              │  (capability-packs) │   { custom, minimal, research, writer,
              │                     │     implementer, qa, reviewer, cto }
              └──────────┬──────────┘
                         │ each profile composes:
                         ▼
              ┌─────────────────────┐
              │  FRAGMENT LIBRARY   │   paperclips/fragments/shared/fragments/*.md
              │  (sliced by         │   universal/  git/  worktree/  handoff/
              │   selectivity)      │   code-review/  qa/  pre-work/  plan/
              └──────────┬──────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
┌────────────┐   ┌────────────┐   ┌─────────────────────────┐
│ ROLE-FILES │   │ ASSEMBLY   │   │ PROJECT METADATA        │
│ (craft)    │   │ MANIFEST   │   │ (paths, MCP, branch...) │
│            │   │ per agent: │   │                         │
│ swift.md   │   │  agent_name│   │ paperclips/projects/    │
│ python.md  │   │  role_src  │   │   <key>/                │
│ kotlin.md  │   │  profile   │   │   paperclip-agent-      │
│ mcp.md ... │   │  cust._inc │   │   assembly.yaml         │
└─────┬──────┘   └────┬───────┘   └────────────┬────────────┘
      │               │                        │
      └───────────────┼────────────────────────┘
                      ▼
              ┌──────────────────┐
              │  build.sh        │
              │  --project <key> │
              │  --target ...    │
              └────────┬─────────┘
                       ▼
        ONE AGENTS.md per agent (universal + profile + role + custom_includes)
        — output is gitignored under paperclips/dist/
        — deployed via PUT /api/agents/<id>/instructions-bundle/file
```

### 2.3 Predicted size reduction

| profile | per-agent AGENTS.md | currently | reduction |
|---|---:|---:|---:|
| `writer` | 145 (universal) + 50 (D-role) = 195 | 481 | 2.5× |
| `research` | 145 + 65 = 210 | 479 | 2.3× |
| `implementer` | 145 + 230 = 375 | 757 | 2.0× |
| `qa` | 145 + 260 = 405 | 656 | 1.6× |
| `reviewer` | 145 + 200 = 345 | 682 | 2.0× |
| `cto` | 145 + 280 = 425 | 524 | 1.2× |

**Note:** Earlier rev1 estimates assumed universal layer was external (workspace AGENTS.md auto-loaded). Per §3 below, v1 keeps universal inlined per agent. Real reduction is from selective profile composition + fragment de-duplication, not from layer separation. Future v2 (§13) revisits the AGENTS.md split.

---

## 3. Runtime instruction contract (v1)

This section is normative. The v1 runtime contract follows what paperclip + the existing deploy tooling can do today, not aspirational architecture.

### 3.1 Single artifact per agent

For each hired agent, **exactly one** rendered AGENTS.md is deployed via `PUT /api/agents/<id>/instructions-bundle/file`. The content is the concatenation of:

```
[Universal layer]               # ~95 lines: karpathy, wake-and-handoff-basics, escalation-board
[Project metadata block]        # ~50 lines: paths, branch, MCP, evidence refs
[Profile composition]           # 0–280 lines: profile.includes resolved + concatenated
[Role craft]                    # 50–100 lines: role_source content
[Custom includes]               # any per-agent custom_includes
```

This is the only artifact paperclip stores. Workspace `AGENTS.md` and root `CLAUDE.md` are operator-convenience local files; they are NOT what claude/codex agents see at runtime — they see the API-deployed bundle.

### 3.2 Universal layer is inlined per agent (v1)

Universal-layer fragments (`karpathy.md`, `wake-and-handoff-basics.md`, `escalation-board.md`) are **inlined into every per-agent AGENTS.md**. They are not externalized to a workspace-loaded AGENTS.md in v1.

**Why v1 keeps it inlined:** paperclip serves one bundle to the agent. There is no native paperclip mechanism for "common project preamble + per-agent body". Splitting would require either (a) operator manually merging two files in workspace, or (b) duplicating universal content in per-workspace AGENTS.md outside paperclip's contract. Both options are fragile.

**Cost:** v1 keeps the EXISTING inlining cost — current `paperclips/fragments/shared/fragments/karpathy-discipline.md`, `heartbeat-discipline.md`, `phase-handoff.md` already inline into every agent today. The redesign does NOT introduce new duplication; it merely preserves what's there. v2 (§13) revisits if/when paperclip API supports multi-bundle delivery.

### 3.4 Multi-target teams + target extensibility (rev4)

Manifest declares `target: <string>` per agent. The string is **opaque** at the schema level; supported values come from filesystem convention: a value `<X>` requires `paperclips/roles-<X>/` to exist with target-appropriate craft files, and paperclip-server must support `<X>_local` adapter type.

| target | role-files dir | adapter type | currently supported |
|---|---|---|---|
| `claude` | `paperclips/roles/` | `claude_local` | yes (default) |
| `codex` | `paperclips/roles-codex/` | `codex_local` | yes |
| `<future>` | `paperclips/roles-<future>/` | `<future>_local` | requires (a) new craft files, (b) paperclip adapter, (c) bootstrap-script update if hire payload differs |

**Mixed teams within one project are explicitly supported.** trading uses `target: claude` for CTO + `target: codex` for the rest; gimle runs 12-claude + 12-codex teams in parallel under the same company; uaudit is codex-only. Future projects (e.g. ios-wallet) may declare `target: codex` for SwiftEngineer × N + `target: claude` for OpusReviewer.

**Cross-target handoff is a first-class scenario** — when CTO[claude] reassigns to PythonEngineer[codex], the hire payload differences (model id, sandbox flags) are configured at hire time, not at handoff time; paperclip routes events identically regardless of target. Phase C smoke-test §12.C explicitly validates one cross-target handoff per mixed-team project.

**What stays target-agnostic:**
- Profile library (`paperclips/fragments/profiles/*.yaml`).
- Fragment library (`paperclips/fragments/shared/fragments/`).
- Project manifests (only `target: <string>` field touches it).
- bootstrap-project.sh / smoke-test.sh / watchdog (read `target` from manifest, branch on it locally).

Adding a new target is **additive, not breaking** — existing projects unaffected.

### 3.3 Workspace and root AGENTS.md / CLAUDE.md (operator convenience only)

- `paperclips/projects/<key>/AGENTS.md.template` — committed, path-free template; rendered into a host-local `~/.paperclip/projects/<key>/AGENTS.md` for operator's own claude/codex sessions running in that workspace. **Not deployed to paperclip agents.**
- `paperclips/projects/<key>/CLAUDE.md` — symlink to template (or removed). Same scope: operator convenience.

These files exist to give the operator (running claude CLI manually in the project workspace) the same project context that paperclip-deployed agents have via API. They are NOT what the runtime agents read.

---

## 4. Fragment library (granularity = selectivity)

**Principle:** A fragment is a unit of inclusion. If two pieces are always loaded together OR never loaded apart, they're one fragment. Granularity follows selectivity boundaries, not arbitrary "smaller is better".

### 4.1 Layout

```
paperclips/fragments/shared/fragments/
├── universal/                                     # inlined into every agent AGENTS.md
│   ├── karpathy.md                       (~25)   # think/minimum/surgical/verify
│   ├── wake-and-handoff-basics.md        (~40)   # wake-check + cross-session-memory + @mention hygiene + 409
│   └── escalation-board.md               (~20)
├── git/                                            # selective by capability
│   ├── commit-and-push.md                (~50)   # implementer, qa
│   ├── merge-readiness.md                (~20)   # cto, reviewer
│   ├── merge-state-decoder.md            (~20)   # cto, reviewer
│   └── release-cut.md                    (~15)   # cto only
├── worktree/
│   └── active.md                         (~25)   # implementer, reviewer, qa
├── handoff/
│   ├── basics.md                         (~15)   # all profiles except minimal/custom
│   └── phase-orchestration.md            (~50)   # cto only
├── code-review/
│   ├── approve.md                        (~25)   # reviewer
│   └── adversarial.md                    (~30)   # OpusArchitectReviewer (custom_includes)
├── qa/
│   └── smoke-and-evidence.md             (~30)   # qa
├── pre-work/
│   ├── codebase-memory-first.md          (~15)   # all who read code
│   ├── sequential-thinking.md            (~10)   # implementer, reviewer, qa
│   └── existing-field-semantics.md       (~12)   # implementer
└── plan/
    ├── producer.md                       (~25)   # cto
    └── review.md                         (~20)   # reviewer
```

**Total: 18 files, ~530 lines.** (rev4 errata — previously said "16 files"; actual count is 3+4+1+2+2+1+3+2 = 18 per the enumerated tree above.) Current `paperclips/fragments/shared/fragments/` is **441 lines across 13 files** (verified `wc -l`). The redesign is **~20% larger** in absolute library size (530 vs 441) — but the win is per-agent: today every agent inlines essentially the entire library; in the redesign each agent inlines only its profile-selected subset. Net per-agent saving comes from selective composition, not from a smaller library.

### 4.2 Naming consolidation

- Current `heartbeat-discipline.md` is renamed and re-scoped → `universal/wake-and-handoff-basics.md`. Heartbeat content is removed (paperclip heartbeat is off).
- Current `phase-handoff.md` is split:
  - basics (PATCH+@mention+STOP, 409 procedure) → `universal/wake-and-handoff-basics.md`
  - explicit handoff comment template → `handoff/basics.md`
  - phase choreography → `handoff/phase-orchestration.md` (cto only)

---

## 5. Profile library

### 5.1 Eight profiles

```
custom         — empty; full freedom (only role_source + custom_includes)
minimal        — universal layer only (no capability fragments)
research       — read-only + research-first
writer         — read-only docs
implementer    — read + commit + push (NO merge)
qa             — implementer + smoke + evidence
reviewer       — read + approve + merge-readiness (NO commit, NO release-cut)
cto            — reviewer + phase orchestration + release-cut + plan-producer
```

### 5.2 Concrete profile YAMLs

Universal-layer fragments are NOT listed in profile YAMLs — they are unconditionally inlined by the builder (§3.2). The profile YAML lists capability-layer fragments only.

`paperclips/fragments/profiles/custom.yaml`:
```yaml
schemaVersion: 2
name: custom
inheritsUniversal: false   # ONLY profile that opts out — operator opts in by listing universal/* in custom_includes
includes: []
```

`paperclips/fragments/profiles/minimal.yaml`:
```yaml
schemaVersion: 2
name: minimal
inheritsUniversal: true
includes: []
```

`paperclips/fragments/profiles/research.yaml`:
```yaml
schemaVersion: 2
name: research
inheritsUniversal: true
includes:
  - pre-work/codebase-memory-first.md
  - handoff/basics.md
```

`paperclips/fragments/profiles/writer.yaml`:
```yaml
schemaVersion: 2
name: writer
inheritsUniversal: true
includes:
  - handoff/basics.md
```

`paperclips/fragments/profiles/implementer.yaml`:
```yaml
schemaVersion: 2
name: implementer
inheritsUniversal: true
includes:
  - git/commit-and-push.md
  - worktree/active.md
  - pre-work/codebase-memory-first.md
  - pre-work/sequential-thinking.md
  - pre-work/existing-field-semantics.md
  - handoff/basics.md
```

`paperclips/fragments/profiles/qa.yaml`:
```yaml
schemaVersion: 2
name: qa
inheritsUniversal: true
extends: implementer
includes:
  - qa/smoke-and-evidence.md
```

`paperclips/fragments/profiles/reviewer.yaml`:
```yaml
schemaVersion: 2
name: reviewer
inheritsUniversal: true
includes:
  - pre-work/codebase-memory-first.md
  - pre-work/sequential-thinking.md
  - git/merge-readiness.md
  - git/merge-state-decoder.md
  - code-review/approve.md
  - plan/review.md
  - handoff/basics.md
```

`paperclips/fragments/profiles/cto.yaml`:
```yaml
schemaVersion: 2
name: cto
inheritsUniversal: true
extends: reviewer
includes:
  - git/release-cut.md
  - handoff/phase-orchestration.md
  - plan/producer.md
```

### 5.2.1 Composition resolution (normative)

When the builder composes a per-agent AGENTS.md, it processes layers in this fixed order:

1. **Universal layer** — appended exactly once. Re-declarations of `inheritsUniversal: true` in `extends:` chain are deduplicated. If `extends: implementer` and both declare `inheritsUniversal: true`, the universal block is emitted ONCE at the start, not twice.
2. **`extends:` resolution** — recursive, breadth-first. `qa extends implementer extends none` → builder collects `implementer.includes ∪ qa.includes`, deduplicating by fragment path (preserves first occurrence order).
3. **Per-agent `custom_includes`** — appended after profile composition.
4. **Role craft** — `role_source` content appended.
5. **Project overlays** (per §6.7) — appended last.

A given fragment path appears at most once in the rendered output; duplicates from inheritance/custom_includes are silently deduplicated. The builder logs `dedup applied: <fragment> from <source-A> + <source-B>` to stderr when this happens — operator can then choose to remove the redundant declaration.

### 5.3 Escape hatch — `custom_includes`

Any profile can be augmented per-agent in the assembly YAML:

```yaml
agents:
  - agent_name: OpusArchitectReviewer
    role_source: roles/opus-architect.md
    profile: reviewer
    custom_includes:
      - code-review/adversarial.md   # added on top of reviewer profile
```

`profile: custom` with `custom_includes: [...]` gives total control. `profile: minimal` is the recommended floor — universal layer still loads.

### 5.4 Edge case demonstration

Same role-file (`roles/swift.md`), three capabilities, zero duplication:
- `iOSCTO` in ios-wallet project: `role_source: roles/swift.md, profile: cto`
- `SwiftEngineer` in ios-wallet project: `role_source: roles/swift.md, profile: implementer`
- `UWISwiftAuditor` in uaudit project: `role_source: roles/swift.md, profile: reviewer`

---

## 6. Assembly YAML schema (committed vs host-local split)

### 6.1 Committed manifest — only team description, no host-data

```yaml
# paperclips/projects/ios-wallet/paperclip-agent-assembly.yaml
schemaVersion: 2

project:
  key: ios-wallet
  display_name: iOS Wallet
  issue_prefix: IOS
  integration_branch: develop
  specs_dir: docs/specs
  plans_dir: docs/plans
  domain:
    target_name: Unstoppable iOS Wallet

mcp:
  service_name: ios-wallet-mcp
  tool_namespace: ios
  base_required:
    - codebase-memory
    - context7
    - serena
    - github
    - sequential-thinking

agents:
  - agent_name: iOSCTO
    role_source: roles/cto.md
    profile: cto
    target: codex
  - agent_name: SwiftEngineer1
    role_source: roles/swift.md
    profile: implementer
    target: codex
  - agent_name: SwiftEngineer2
    role_source: roles/swift.md
    profile: implementer
    target: codex
  - agent_name: iOSReviewer
    role_source: roles/code-reviewer.md
    profile: reviewer
    target: codex
  - agent_name: iOSQA
    role_source: roles/qa-engineer.md
    profile: qa
    target: codex
```

### 6.2 What is forbidden in committed manifest

- Literal UUIDs (regex: `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`)
- Absolute paths starting with `/Users/`, `/home/`, `/private/`, `/var/`, `/opt/`
- `company_id`, `agent_id` keys (any case)
- `telegram_plugin_id`, `bot_token`, `chat_id` keys

Enforced by `validate-manifest.sh` (acceptance test §12A).

**What IS allowed:** `{{template.references}}` to host-local sources (per §6.5). E.g. uaudit overlays may use `{{bindings.company_id}}` and `{{plugins.telegram.plugin_id}}` — at build time these resolve from host-local files.

### 6.3 Host-local files (gitignored)

```
~/.paperclip/
  auth.json                         # paperclip JWT (from `paperclip login`)
  config.yaml                       # API base + prefs (one per machine)
  watchdog-config.yaml              # generated by bootstrap-watchdog.sh
  host-plugins.yaml                 # plugin_id mapping (host-wide registry)
  instances/<name>/                 # paperclip-server data (untouched)
  projects/<key>/
    bindings.yaml                   # company_id + agents{name → uuid}
    paths.yaml                      # absolute local paths
    plugins.yaml                    # references to host-plugins.yaml entries
    watchdog-thresholds.yaml        # optional per-project threshold overrides
    AGENTS.md                       # rendered for operator's own CLI sessions (operator convenience)
```

Examples:

```yaml
# ~/.paperclip/projects/ios-wallet/bindings.yaml
# generated by bootstrap-project.sh, idempotent
schemaVersion: 2
company_id: 7f3a...
agents:
  iOSCTO: a2c1...
  SwiftEngineer1: b4d3...
  SwiftEngineer2: c8e2...
  iOSReviewer: d9f4...
  iOSQA: e0a1...
```

```yaml
# ~/.paperclip/projects/ios-wallet/paths.yaml
# bootstrap prompts initial values; editable
schemaVersion: 2
project_root: /Users/me/Code/ios-wallet
primary_repo_root: /Users/me/Code/ios-wallet
production_checkout: /Users/Shared/iOS/ios-wallet
team_workspace_root: /Users/Shared/iOS/runs
operator_memory_dir: ~/.claude/projects/-Users-me-Code-ios-wallet/memory
```

```yaml
# ~/.paperclip/projects/ios-wallet/plugins.yaml  (optional)
schemaVersion: 2
telegram:
  plugin_ref: telegram                # key in ~/.paperclip/host-plugins.yaml
  chat_id: -1001234567890
```

### 6.4 Project override seam (preserves existing builder behavior)

The existing builder (`build_project_compat.py:62-99`) implements 4-level fragment fallback. **This is preserved as a first-class v2 feature** — trading and uaudit use it, removing it would break working code.

**Fragment resolution order (highest priority first):**
1. `paperclips/projects/<key>/fragments/targets/<target>/<fragment>` — project + target-specific
2. `paperclips/projects/<key>/fragments/<fragment>` — project-level override
3. `paperclips/fragments/targets/<target>/<fragment>` — shared + target-specific
4. `paperclips/fragments/shared/fragments/<fragment>` — shared default

When an override applies, builder logs `override applied: <path> (was: <default>)` to stderr (existing behavior preserved).

**`custom_includes` is for per-agent additions; project overrides are for project-wide replacements.** Both coexist; they are not interchangeable.

**Interaction (closes rev2 open Q #5):** when an agent has `custom_includes: [git/commit-and-push.md]` AND the project has `paperclips/projects/<key>/fragments/git/commit-and-push.md` override — the override APPLIES. Reasoning: `custom_includes` declares WHAT to include (the path); fragment override resolves WHERE to read the content from (4-level fallback). They are orthogonal — inclusion list vs. resolution layer. This means project overrides reach per-agent custom includes too, which is the intuitive behavior (project owns its fragment content regardless of who includes it).

### 6.5 Allowed template sources for `{{vars}}` resolution

Builder resolves `{{a.b.c}}` placeholders against this fixed set of sources, in this priority order:

| source | scope | example |
|---|---|---|
| `manifest.project.*`, `manifest.domain.*`, `manifest.mcp.*` | committed manifest | `{{project.key}}`, `{{domain.target_name}}` |
| `bindings.company_id`, `bindings.agents.<name>` | host-local | `{{bindings.company_id}}` |
| `paths.*` | host-local | `{{paths.project_root}}` |
| `plugins.<service>.*` | host-local | `{{plugins.telegram.plugin_id}}` |

If a placeholder doesn't resolve to any source, build fails with `unresolved placeholder: {{...}} at <file>:<line>`. No silent fall-through.

This means uaudit's existing `{{project.company_id}}` and `{{report_delivery.telegram_plugin_id}}` references are renamed to `{{bindings.company_id}}` and `{{plugins.telegram.plugin_id}}` during migration. Mechanical rename + grep-verifiable.

### 6.6 Committed AGENTS.md → template; rendered output is gitignored



- `paperclips/projects/<key>/AGENTS.md.template` — **committed**, contains `{{template.references}}`, no literal paths or UUIDs.
- `paperclips/dist/<key>/<target>/<AgentName>.md` — **gitignored** (added to `.gitignore`), contains rendered output for the deploy step.
- `~/.paperclip/projects/<key>/AGENTS.md` — **gitignored**, rendered for operator's own CLI sessions in the project workspace.

`paperclips/projects/<key>/CLAUDE.md` symlink is to the template file (renderable for human reading) OR is removed entirely. Operator-convenience workspace AGENTS.md is generated by `bootstrap-project.sh` step.

### 6.7 Overlays — append-mode third composition mechanism

Verified existing builder behavior (`build_project_compat.py:382-401`, function `apply_overlay`): overlays are **appended to the end** of rendered content (after universal + profile + role + custom_includes), not substituted as fragments. They live at:

```
paperclips/projects/<key>/overlays/<target>/_common.md       # added to every agent of <target>
paperclips/projects/<key>/overlays/<target>/<role>.md        # added when role matches (e.g., cto.md)
paperclips/projects/<key>/overlays/<target>/<agent_name>.md  # added when agent name matches (e.g., UWICTO.md)
```

Currently used by trading (`overlays/{claude,codex}/_common.md`) and uaudit (`overlays/codex/_common.md` + 6 agent-name overlays for UWICTO/UWACTO/UWISwiftAuditor/UWAKotlinAuditor/UWIInfraEngineer/UWAInfraEngineer).

**Rev3 decision: keep overlays as a first-class mechanism, separate from fragment-override.** They are different operations:

| | Fragment override (§6.4) | Overlay (§6.7) |
|---|---|---|
| Operation | Replace | Append |
| Granularity | Single fragment file | Per-target / per-role / per-agent block |
| Use case | "We want our project's git-workflow rules instead of shared" | "Add this project-specific anti-pattern at the end of every CTO's bundle" |
| Resolution | At `<!-- @include -->` expansion time | After all includes resolved |

**`{{template.references}}` apply to overlays too** — `_common.md` etc. can use `{{paths.production_checkout}}`, `{{bindings.company_id}}` per §6.5.

**Migration impact:** trading/uaudit existing overlays are PRESERVED as-is during migration. Their existing `{{project.company_id}}` references rename to `{{bindings.company_id}}` (mechanical sed) per §10.

---

## 7. Versioning (`paperclips/scripts/versions.env`)

Single committed file pinning all toolchain versions. **No floating versions.**

```bash
# Paperclipai — last canary BEFORE PR #5429 (broke plugin secret-refs).
# 2026.508.0-canary.0 published 2026-05-08T00:21Z; includes PR #5428
# (Guard assigned backlog liveness); excludes PR #5429.
PAPERCLIPAI_VERSION="2026.508.0-canary.0"

# Telegram plugin — fork (not upstream npm), pinned by SHA.
TELEGRAM_PLUGIN_REPO="https://github.com/ant013/paperclip-plugin-telegram.git"
TELEGRAM_PLUGIN_REF="c0423e45"
TELEGRAM_PLUGIN_BUILD_CMD="pnpm install --frozen-lockfile --ignore-scripts && pnpm build"

# pnpm — managed via corepack (built into Node 20+). Pinned exact version.
PNPM_PROVIDER="corepack"
PNPM_VERSION="9.15.0"

# Watchdog — built locally from this repo; tracked by repo SHA.
WATCHDOG_PATH="services/watchdog"

# MCP servers — all pinned exact versions.
CODEBASE_MEMORY_MCP_VERSION="0.3.1"
SERENA_VERSION="0.2.5"
CONTEXT7_MCP_VERSION="0.4.2"               # was: latest
SEQUENTIAL_THINKING_MCP_VERSION="2026.04.0" # was: latest
```

**Bumping versions:** edit `versions.env` → run `./paperclips/scripts/update-versions.sh` → re-installs/rebuilds all components in-place. Snapshot of pre-update state goes to `~/.paperclip/journal/<timestamp>-version-bump.json` (per §8.5).

---

## 8. API contract (paperclip endpoints used by scripts)

This section pins exact endpoints and payload shapes against the existing working scripts. Implementation MUST use these; deviations require new spec amendment.

### 8.1 Hire an agent

`POST /api/companies/<company_id>/agent-hires`

Required body fields (verified against `hire-codex-agents.sh`):
```json
{
  "name": "<agent_name>",
  "role": "<role>",
  "title": "<title>",
  "icon": "<emoji or alias>",
  "reportsTo": "<uuid of supervisor>",
  "capabilities": "<comma-separated string>",
  "adapterType": "codex_local | claude_local",
  "adapterConfig": {
    "cwd": "<absolute path to workspace_cwd>",
    "model": "<model id>",
    "modelReasoningEffort": "<low|medium|high>",
    "instructionsFilePath": "AGENTS.md",
    "instructionsEntryFile": "AGENTS.md",
    "instructionsBundleMode": "managed",
    "maxTurnsPerRun": 200,
    "timeoutSec": 0,
    "graceSec": 15,
    "dangerouslyBypassApprovalsAndSandbox": true,
    "env": {
      "CODEX_HOME": "<codex_home_path>",
      "PATH": "<augmented PATH>"
    }
  },
  "runtimeConfig": {
    "heartbeat": {
      "enabled": false,
      "intervalSec": 14400,
      "wakeOnDemand": true,
      "maxConcurrentRuns": 1,
      "cooldownSec": 10
    }
  },
  "budgetMonthlyCents": 0,
  "sourceIssueId": "<bootstrap source issue uuid>"
}
```

Response: `{agent: {id, ...}}` — id saved to `~/.paperclip/projects/<key>/bindings.yaml`.

### 8.2 Deploy instruction bundle

`PUT /api/agents/<agent_id>/instructions-bundle/file`

Body:
```json
{
  "path": "AGENTS.md",
  "content": "<full markdown of rendered AGENTS.md>"
}
```

Headers:
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

Returns HTTP 200 on success. Verified against `deploy_project_agents.py:208-225`.

### 8.3 Probe agent configuration

`GET /api/agents/<agent_id>/configuration`

Used by `bootstrap-project.sh` to verify agent exists and read `adapterType` for routing decisions. Verified against `deploy_project_agents.py:195-208`.

### 8.4 Plugin configuration

`POST /api/plugins/<plugin_id>/config`

Body: full config object (replace mode — no PATCH semantics; reading current config first via `GET /api/plugins/<plugin_id>` is required to avoid clobbering).

Per memory `reference_paperclip_plugin_config_endpoint`: probe POST without prior GET wiped live config in 2026-05-12 incident.

Bootstrap implementation:
```
config = GET /api/plugins/<id>
config.merge_in(new_chat_id, new_routes)
POST /api/plugins/<id>/config with merged
```

### 8.5 Mutation safety / rollback journal

Before any operation that mutates paperclip state across multiple agents (deploy, plugin reconfig, version bump), the script:

1. Snapshots current state to `~/.paperclip/journal/<timestamp>-<op>.json`:
   - For deploy: `GET /api/agents/<id>/configuration` for each agent + current AGENTS.md content (via `GET /api/agents/<id>/instructions-bundle/file` if available, or local `paperclips/dist/<key>/<target>/<Agent>.md` if previously deployed)
   - For plugin reconfig: `GET /api/plugins/<id>`
   - For version bump: `paperclip --version`, plugin git SHA, `npm ls -g`
2. Performs mutation.
3. On any non-2xx or schema-validation failure, prints rollback hint: `rollback.sh <journal-id>`.

`rollback.sh <journal-id>` reads journal, replays inverse mutations:
- Re-PUTs old AGENTS.md content for each agent
- POSTs old plugin config
- For version bump: documents the steps but does NOT auto-rollback npm/git state (operator decision).

### 8.6 Canary deploy mode (optional, 2-stage)

`bootstrap-project.sh <key> --canary` deploys in two stages before fan-out, addressing the rev2 review concern that a CTO-only canary self-blocks (a broken CTO can't echo, can't handoff — false-negative or timeout-with-unclear-cause).

**Stage 1 — read-only canary** (proves: AGENTS.md loads, agent wakes, MCP servers visible):
- Deploy to first `writer` or `research` agent in manifest. If neither exists, deploy to first `qa` agent (still safer than CTO — qa is a leaf, can't break orchestration).
- Run `smoke-test.sh <key> --canary-stage=1`: posts a "list available tools" issue to that agent, expects MCP namespace list reply within 90s.
- On failure: stop, journal-rollback, surface error.

**Stage 2 — orchestration canary** (proves: handoff works):
- Deploy to first `cto` agent.
- Run `smoke-test.sh <key> --canary-stage=2`: end-to-end handoff test (CTO echoes + reassigns to first implementer; implementer echoes back).
- On failure: stop, journal-rollback (now 2 agents already deployed; journal restores both).

**Stage 3 — fan-out:** deploy remaining agents in topological order (per §9.2 step 4). Failure here doesn't auto-rollback (most agents already on new prompt); operator decides.

Default mode (no `--canary`) is fan-out only — CI/sandbox use, where rollback cost is low.

---

## 9. Operator scripts

### 9.1 `install-paperclip.sh` — host-wide setup, **once per machine**

Idempotent. Steps:

0. **Pre-flight:** Node 20+, gh CLI, python 3.12+, uv, git. `corepack enable && corepack prepare pnpm@$PNPM_VERSION --activate`.
1. **Auth checks:** `gh auth status` (prompt `gh auth login` if missing); `~/.codex/auth.json` (prompt `codex auth`); `~/.claude/auth.json` or `ANTHROPIC_API_KEY`; SSH key for palace.ops (optional).
2. **Install paperclipai pinned:** `npm install -g paperclipai@$PAPERCLIPAI_VERSION`. Skip if already at version.
3. **First-run paperclip:** `paperclip login` (interactive) → `~/.paperclip/auth.json`.
4. **Disable heartbeat:** patch `~/.paperclip/instances/default/config.json` → `heartbeat.enabled = false`. Verify by inspecting effective config.
5. **Telegram plugin (fork, pinned):**
   - `git clone $TELEGRAM_PLUGIN_REPO $HOME/.paperclip/plugins-src/paperclip-plugin-telegram` (skip if exists)
   - `git fetch && git checkout $TELEGRAM_PLUGIN_REF`
   - `pnpm install --frozen-lockfile --ignore-scripts && pnpm build`
   - Idempotent register: `GET /api/plugins` → if `paperclip-plugin-telegram` not present, `POST /api/plugins/install {path: "<plugin-src>"}` → save `plugin_id` to `~/.paperclip/host-plugins.yaml`
6. **Core MCP servers:** `npm install -g` for `codebase-memory-mcp@$CODEBASE_MEMORY_MCP_VERSION`, `serena@$SERENA_VERSION`, `context7@$CONTEXT7_MCP_VERSION`, `sequential-thinking@$SEQUENTIAL_THINKING_MCP_VERSION`.
7. **MCP registration in claude/codex configs:** merge minimal stanzas into `~/.codex/config.toml` and `~/.claude/settings.json` (jq/yq merge, no overwrite of operator's existing entries).
8. **Watchdog code preparation only (NO service install yet):**
   ```bash
   cd services/watchdog
   uv sync --all-extras
   # Verify CLI works
   uv run python -m gimle_watchdog --help
   ```
   **Service install (launchd plist) is deferred** — happens via `bootstrap-watchdog.sh` AFTER first project bootstrap, because `gimle_watchdog install` requires non-empty `companies` in config (verified — see §1.3 constraint).
9. **Verification:** `curl /api/agents/me` returns 200 with operator email.

Output: «Ready. Run `bootstrap-project.sh <project-key>`. Watchdog will be installed after first project bootstrap.»

**Security notes:**
- pnpm runs with `--ignore-scripts` to prevent install-script execution from telegram plugin dependencies. If the plugin needs native rebuilds (rare for pure-TS plugins), operator runs `pnpm rebuild <pkg>` explicitly.
- Trust boundary: operator owns the fork (`ant013/paperclip-plugin-telegram`); supply chain risk = operator merging malicious code into own fork. No additional sandboxing in v1; revisit if community-contributed plugins are added.

### 9.2 `bootstrap-project.sh <project-key>` — per-project, **interactive by default**

```bash
./paperclips/scripts/bootstrap-project.sh ios-wallet
./paperclips/scripts/bootstrap-project.sh ios-wallet --config bootstrap-input.yaml
./paperclips/scripts/bootstrap-project.sh gimle --reuse-bindings <existing-uuids.yaml>
./paperclips/scripts/bootstrap-project.sh ios-wallet --canary
```

**Interactive prompts** (with sensible defaults shown):
- Repo URL
- Local clone path (default: `/Users/Shared/iOS/<key>` on macOS)
- Team workspace root (default: `/Users/Shared/iOS/runs`)
- Integration branch (default from manifest)
- Telegram enabled? Y/N → if Y, chat_id
- Plugin to use (auto-detect if only one telegram-plugin instance)

**Steps (all idempotent, journal-snapshotted):**
1. Read committed manifest at `paperclips/projects/<key>/paperclip-agent-assembly.yaml`. Validate via `validate-manifest.sh`.
2. **Snapshot pre-state** to `~/.paperclip/journal/<timestamp>-bootstrap-<key>.json`.
3. If `~/.paperclip/projects/<key>/bindings.yaml` exists with company_id → reuse; else `POST /api/companies` → save company_id.
4. **Topological hire ordering.** Build a dependency graph from `reportsTo` (each agent's `reportsTo` field, if present, must reference another agent in the same manifest by `agent_name`). Hire in topological order: roots (no `reportsTo`, typically CTO/CEO) first; subordinates after their supervisors are hired and have UUIDs in bindings. Cycle detection: if cycle found, fail with `reportsTo cycle: a → b → ... → a`. For each agent in topological order:
   - if uuid already in bindings → reuse; verify via `GET /api/agents/<id>/configuration` (404 → re-hire)
   - else `POST /api/companies/<id>/agent-hires` with full payload (per §8.1):
     - `adapterConfig.cwd` = `<paths.team_workspace_root>/<agent_name>/workspace` (computed from paths.yaml)
     - `reportsTo` = uuid resolved from bindings (just-hired or pre-existing)
     - `runtimeConfig.heartbeat.enabled` = `false` (matches `install-paperclip.sh` step 4)
     - `sourceIssueId` from manifest or auto-generated bootstrap issue
   - save uuid to bindings.yaml IMMEDIATELY (so subordinates can resolve `reportsTo`)
   - removed agents (in bindings, not in manifest) trigger warning; operator runs `--prune` to delete.
5. Configure telegram plugin (if enabled): `GET /api/plugins/<id>` → merge new chat routes → `POST /api/plugins/<id>/config` (per §8.4).
6. Write/update `~/.paperclip/projects/<key>/{bindings,paths,plugins}.yaml`.
7. Build: `./paperclips/build.sh --project <key> --target <each>`.
8. Deploy per-agent AGENTS.md: `PUT /api/agents/<id>/instructions-bundle/file` per agent (per §8.2). If `--canary`, deploy first agent only, run `smoke-test.sh <key> --quick`, then proceed.
9. Set up workspaces: `mkdir -p $team_workspace_root/<AgentName>/workspace && cp <rendered AGENTS.md> → workspace/AGENTS.md`.
10. Render operator-convenience `~/.paperclip/projects/<key>/AGENTS.md` from template.
11. Trigger MCP indexing for project's `codebase_memory_projects.primary` (via `mcp__codebase-memory__index_repository`). Wait for completion (or timeout with warning).
12. Deploy codex subagents (if any in `paperclips/projects/<key>/codex-agents/*.toml`) → `~/.codex/projects/<key>/agents/`.
13. Call `bootstrap-watchdog.sh <key>` (per §9.4).

### 9.3 `smoke-test.sh <project-key>` — verify alive

7-stage check:
1. Paperclip API reachable + JWT valid.
2. Company exists; all manifest agents present in API; each agent's deployed AGENTS.md SHA matches local build SHA.
3. Workspaces exist + AGENTS.md deployed (SHA matches).
4. Watchdog sees this company (recent tick in `watchdog.log`).
5. **Per-agent MCP availability:** post test issue per agent ("list available tools"); verify reply within 90s; verify expected MCP namespaces present.
6. **Telegram plugin** (if enabled): `POST /api/plugins/<id>/action {action: "send_message", text: "smoke-test <key>"}` → verify delivery via Telegram API or message_id return.
7. **End-to-end handoff:** create test issue assigned to first CTO; expect echo response + handoff to first implementer; cleanup.

`--quick` flag skips heavy stages 5 + 7 (used by canary deploy in §8.6).

Failure mode: stops at first failure with diagnostic + suggestion.

### 9.4 `bootstrap-watchdog.sh <project-key>` — config-first watchdog install

**Why separate from `install-paperclip.sh`:** `gimle_watchdog install` calls `load_config(~/.paperclip/watchdog-config.yaml)` which requires non-empty `companies` list (verified `config.py:227` + tests). On a clean machine, watchdog cannot be installed before any project exists.

**Behavior (idempotent, called from `bootstrap-project.sh` step 13):**

```
bootstrap-watchdog.sh <project-key>
  │
  ├─ Read ~/.paperclip/projects/<key>/bindings.yaml → company_id
  ├─ Read paperclips/projects/<key>/paperclip-agent-assembly.yaml → project.display_name
  ├─ Read ~/.paperclip/config.yaml → paperclip base_url, api_key_source
  ├─ Read optional ~/.paperclip/projects/<key>/watchdog-thresholds.yaml for per-project tunables
  │
  ├─ IF ~/.paperclip/watchdog-config.yaml does NOT exist:
  │    Create from paperclips/templates/watchdog-config.yaml.template:
  │      - version: 1
  │      - paperclip block from ~/.paperclip/config.yaml
  │      - companies: [<this project as first entry>]
  │      - daemon, cooldowns, logging, escalation, handoff: defaults from template
  │
  ├─ IF file exists AND company_id NOT in companies[*].id:
  │    Append company block (with thresholds from watchdog-thresholds.yaml if present, else defaults)
  │
  ├─ IF file exists AND company_id IS in companies[*].id:
  │    No-op (idempotent reuse)
  │
  ├─ IF launchd plist (~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist) does NOT exist:
  │    cd services/watchdog
  │    uv run python -m gimle_watchdog install
  │    (load_config now passes — companies is non-empty)
  │
  └─ IF launchd already installed:
       launchctl kickstart gid/<uid>/work.ant013.gimle-watchdog
       (re-reads new config without restart loop)
```

**Templates committed in `paperclips/templates/`:**
- `watchdog-config.yaml.template` — full default config with `companies: []` placeholder
- `watchdog-company-block.yaml.template` — single company block with threshold defaults

**Full template structure** (matches `services/watchdog/src/gimle_watchdog/config.py` schema, verified via `load_config` + `tests/test_config.py`):

```yaml
version: 1
paperclip:
  base_url: "{{ host.paperclip.base_url }}"
  api_key_source: "{{ host.paperclip.api_key_source }}"   # e.g. "env:PAPERCLIP_API_KEY" or "inline:..."
companies: []   # populated by bootstrap-watchdog.sh; each entry = {id, name, thresholds}
daemon:
  poll_interval_seconds: 120
  recovery_enabled: true
  recovery_first_run_baseline_only: false   # set true on very first run to avoid waking long-stale issues
  max_actions_per_tick: 3
cooldowns:
  per_issue_seconds: 300
  per_agent_cap: 3
  per_agent_window_seconds: 900
logging:
  path: ~/.paperclip/watchdog.log
  level: INFO
  rotate_max_bytes: 10485760
  rotate_backup_count: 5
escalation:
  post_comment_on_issue: true
  comment_marker: "<!-- watchdog-escalation -->"
handoff:
  handoff_alert_enabled: true
  handoff_alert_cooldown_min: 30
  handoff_recent_window_min: 240
  handoff_alert_soft_budget_per_tick: 7
  handoff_alert_hard_budget_per_tick: 11
```

Per-company appended block:
```yaml
- id: "{{ bindings.company_id }}"
  name: "{{ project.display_name }}"
  thresholds:
    died_min: 3
    hang_etime_min: 60
    hang_cpu_max_s: null
    idle_cpu_ratio_max: 0.005
    hang_stream_idle_max_s: 300
    recover_max_age_min: 180
```

**Per-project threshold overrides (`~/.paperclip/projects/<key>/watchdog-thresholds.yaml`, optional):**
```yaml
schemaVersion: 2
died_min: 5
hang_etime_min: 90
idle_cpu_ratio_max: 0.005
hang_stream_idle_max_s: 300
recover_max_age_min: 180
```

**Removal:** `bootstrap-watchdog.sh <key> --remove` removes the project's company block. If `companies:` becomes empty, leaves config in invalid state (next watchdog tick will log error); operator decides whether to `gimle_watchdog uninstall` or add another project.

### 9.5 Other scripts

- `update-versions.sh` — re-runs install-paperclip.sh steps that depend on `versions.env`, journals pre/post state.
- `validate-manifest.sh <key>` — runs §6.2 forbidden-content checks + schema validation. CI gate (§12A).
- `rollback.sh <journal-id>` — replays inverse mutations from journal (§8.5).
- `migrate-bindings.sh <key>` — extracts UUIDs from legacy sources (`codex-agent-ids.env`, paperclip company storage) → writes new `bindings.yaml`. Used in §10 migration.

---

## 10. Migration plan (dual-read period, no timer)

### 10.1 Dual-read principle

For each migration phase, both legacy and new state sources are read simultaneously. Cleanup happens only when **all** of these conditions are met (the cleanup gate):

- All projects (gimle, trading, uaudit) successfully migrated to new schema.
- All deploy scripts updated to read from `~/.paperclip/projects/<key>/bindings.yaml` (not legacy `codex-agent-ids.env`).
- Watchdog detection confirmed reading from new bindings (verify via tick log).
- **Stability metric (concrete, watchdog-log-derivable):** for 7 consecutive days across all migrated companies:
  - Zero `handoff_alert_posted` events in `~/.paperclip/watchdog.log`
  - Zero `wake_failed` events in recovery pass
  - Zero `escalation` events of `reason=per_agent_cap`
  - Zero non-2xx responses logged from `PUT /api/agents/<id>/instructions-bundle/file` re-deploys
  Verifier: `gimle-watchdog tail -n 50000 | jq -c 'select(.event | IN(...))' | wc -l == 0` per day, 7 days running.
- Operator (QA) signoff documented in BUGS.md or migration log.

No 24h timer; gate is condition-based.

### 10.1.1 Role-split (Phase A.1 — hybrid hold-and-grow)

Existing `paperclips/roles/*.md` and `paperclips/roles-codex/cx-*.md` files mix three things in one file: craft (Python tooling, MCP knowledge, Swift conventions, ...), capability (phase-orchestration in cto.md, APPROVE-format in code-reviewer.md, ...), and project anti-patterns. They cannot be plugged into the new profile system as-is — including `roles/cto.md` already gives an agent phase-orchestration regardless of which profile is selected.

**Hybrid decomposition (rev3 chosen approach):**

1. **Create new craft files alongside existing ones:**
   - `paperclips/roles/cto.md` (174 lines, mixed) → `paperclips/roles/legacy/cto.md` (deprecated, kept temporarily) + new `paperclips/roles/cto.md` (slim ~50 lines, craft only — identity, area, MCP, anti-patterns)
   - Same pattern for `code-reviewer.md` (167 lines), `python-engineer.md`, etc.
   - Capability content moved into `paperclips/fragments/shared/fragments/<category>/*.md` per §4.1.
2. **Old role files get a deprecation banner:**
   ```
   > DEPRECATED — replaced by new craft `paperclips/roles/cto.md` + `profile: cto`.
   > Will be removed at cleanup gate (§10.5). Do not include in new manifests.
   ```
3. **Migration order is opt-in per project:**
   - New projects (e.g., ios-wallet) use new craft files from day 1.
   - trading + uaudit migrate to new craft files in their respective phases (§10.2, §10.3).
   - gimle migrates last (§10.4) — biggest blast radius.
4. **Validator gate:** during dual-read period, `validate-manifest.sh` warns (not errors) if `role_source: roles/legacy/...`. After cleanup gate, becomes error.

**Rationale:** Mechanical auto-split is risky (could split capability under wrong profile heading); per-project manual split spreads risk across phases; new projects pay zero migration cost.

### 10.2 trading migration (smallest, first)

1. `migrate-bindings.sh trading` — extracts 5 agent_ids from current manifest → `~/.paperclip/projects/trading/bindings.yaml`.
2. Move `/Users/Shared/Trading/...` paths from manifest → `~/.paperclip/projects/trading/paths.yaml`.
3. Strip UUIDs and absolute paths from manifest; replace with `{{template.references}}` per §6.5.
4. Re-render with new fragment slots: `./paperclips/build.sh --project trading --target claude --target codex`.
5. **Snapshot + canary deploy:** `bootstrap-project.sh trading --reuse-bindings ~/.paperclip/projects/trading/bindings.yaml --canary` — deploys CTO first, smoke-tests, then fans out.
6. Smoke: `smoke-test.sh trading`.
7. Document migration outcome.

### 10.3 uaudit migration (codex-only, plugins)

1. `migrate-bindings.sh uaudit` — 17 agent_ids + telegram_plugin_id from current manifest → `bindings.yaml` + `plugins.yaml`.
2. Move host paths → `paths.yaml`.
3. Rename overlay placeholders: `{{project.company_id}}` → `{{bindings.company_id}}`; `{{report_delivery.telegram_plugin_id}}` → `{{plugins.telegram.plugin_id}}` (mechanical sed).
4. Strip UUIDs/paths from manifest.
5. Codex subagents deploy step: copy `paperclips/projects/uaudit/codex-agents/*.toml` → `~/.codex/projects/uaudit/agents/`.
6. Re-render + canary deploy + smoke.

### 10.4 gimle migration (largest, soft-migrate)

Pre-flight: pause all 24 gimle agents (12 claude team + 12 codex team — both teams share company `9d8f432c-...`). Pause via paperclip UI or scripted PATCH each. 5–15 min downtime expected (longer than 12-agent estimate due to dual-team coordination).

1. `migrate-bindings.sh gimle` — reads `paperclips/codex-agent-ids.env` (12 codex UUIDs) + paperclip company storage (12 claude UUIDs via `GET /api/companies/9d8f432c-.../agents`) → `~/.paperclip/projects/gimle/bindings.yaml`. **No API recreate.** Source UUIDs preserved.
2. Move host paths from manifest → `~/.paperclip/projects/gimle/paths.yaml`.
3. Fill `agents:` list in manifest (24 entries: 12 claude + 12 codex) per new schema. Remove `legacy_output_paths: true`. Remove all hardcoded paths.
4. Decompose root `CLAUDE.md`:
   - Project rules (branch flow, deploy procedures) → `paperclips/projects/gimle/AGENTS.md.template`.
   - palace-mcp/extractor docs → `services/palace-mcp/README.md` + `docs/palace-mcp/extractors.md`.
   - Iron rules → standard fragments + `docs/contributing/branch-flow.md` for human readers.
5. Re-render: `./paperclips/build.sh --project gimle --target claude --target codex`.
6. **Canary deploy + smoke** per agent: `bootstrap-project.sh gimle --reuse-bindings ... --canary`.
7. Refresh workspace AGENTS.md: handled by bootstrap step 9.
8. Unpause + final smoke.
9. Wait for cleanup gate (§10.1).

### 10.5 Cleanup (gated)

Only after the cleanup gate passes:
- Remove `paperclips/codex-agent-ids.env`, `paperclips/deploy-agents.sh`, `paperclips/deploy-codex-agents.sh`, `paperclips/update-agent-workspaces.sh`, `paperclips/hire-codex-agents.sh`.
- Rewrite `paperclips/scripts/imac-agents-deploy.sh` as thin wrapper around new `bootstrap-project.sh ... --reuse-bindings`.
- Delete dual-read code paths from builder + scripts.

---

## 11. Out-of-scope (future work)

- **AGENTS.md split (v2):** universal layer externalized to workspace AGENTS.md auto-loaded by claude/codex; per-agent prompt deployed separately. Requires either paperclip API addition (multi-bundle) or workspace-merge mechanism. Promising direction but requires upstream cooperation.
- **Unifying `paperclips/roles/` and `paperclips/roles-codex/`** into one set with `target:` declared at composition time. Currently kept separate for safety; mechanical follow-up.
- **Per-platform agent variants** (uaudit's `platform: ios|android|all`) — verified existing builder behavior (`build_project_compat.py:512`): the `platform` field is passed into `template_values` as `agent.platform` and is available as `{{agent.platform}}` to fragments and overlays. No fragment in current shared library actually consumes it; uaudit overlays may. **v1 preserves this opaque-passthrough**: `platform` continues to flow into template_values, builder does not validate values, no profile-level semantics. Future v2 may introduce platform-conditional includes if a real consumer emerges.
- **Watchdog reading manifest directly** for role taxonomy (currently hardcoded in `role_taxonomy.py`). Cross-reference once both are stable.
- **GitHub MCP server** as a first-class MCP (currently agents use `gh CLI` keyring). Bootstrap handles registration when this lands.
- **Multi-instance paperclip on one machine** (operator runs separate instances per company). Out of scope; current design assumes one paperclip-instance per machine.
- **Community plugin sandboxing** — once plugins beyond own-fork are introduced, revisit pnpm sandbox / Docker-based plugin builds.
- **schemaVersion bump tooling** — automatic migrator from schema v1 to v2 manifests. Manual rename in v2 (small file count); automate when v3+ comes.

---

## 12. Acceptance criteria

Split by execution context.

### 12.A Offline CI (no external services)

Each is a CI-runnable check in this repo's test suite.

- [ ] `wc -l paperclips/dist/<key>/<target>/*.md` for all projects → median ≤ 350 lines, max ≤ 450 lines (revised from rev1 numbers per §3.2 inlining cost).
- [ ] `git grep -lE "/Users/Shared|/Users/ant013|/Users/anton|/home/|/private/|/var/|/opt/" paperclips/projects/` → empty.
- [ ] `git grep -lE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" paperclips/projects/` → empty.
- [ ] `git grep -lE "company_id|agent_id|telegram_plugin_id|bot_token|chat_id" paperclips/projects/` → only matches inside `{{template.references}}` (not as bare keys).
- [ ] `validate-manifest.sh <key>` passes for all projects.
- [ ] **Build determinism:** `build.sh --project trading --target codex` run twice with same inputs → byte-identical SHA for all rendered outputs.
- [ ] **Unresolved placeholders rejected:** synthetic broken manifest with `{{nonexistent.var}}` → builder exits non-zero with clear error.
- [ ] **Profile boundary tests:**
  - `assert "release-cut" not in built[implementer]` — implementer never sees release-cut content.
  - `assert "phase-orchestration" not in built[reviewer]` — reviewer doesn't see phase choreography.
  - `assert "git/commit-and-push" not in built[research]` — research never sees commit instructions.
  - `assert universal in built[all_profiles_except_custom]` — universal layer present per §3.2.
- [ ] **Override precedence test:** synthetic project with `paperclips/projects/test/fragments/git/commit-and-push.md` → builder uses project version, logs `override applied`.

### 12.B Mock integration (synthetic paperclip API)

Run against a stub paperclip server in CI (httpx mock or similar).

- [ ] `bootstrap-project.sh test-fixture` against mock API completes without error; produces expected bindings.yaml/paths.yaml.
- [ ] Idempotent re-run of `bootstrap-project.sh test-fixture` → no duplicate API calls; existing UUIDs reused.
- [ ] `--canary` path: deploys 1 agent, runs (mocked) smoke, then fans out.
- [ ] Mutation journal: every multi-agent operation produces journal file with snapshot.
- [ ] `rollback.sh <journal-id>` replays inverse mutations.

### 12.C Operator live smoke (requires real paperclip + macOS host)

**Runtime probe-questions per profile-family.** Smoke-test posts these questions as test issues to one agent per profile in each migrated project; agent reply must contain expected markers. This validates the profile boundaries actually work at runtime, not just at deploy time.

| Probe | Asked to | Expected markers in reply | Forbidden in reply |
|---|---|---|---|
| `mcp_list` — "List MCP namespaces you can call. Reply with comma-separated names." | every profile | `codebase-memory`, `serena`, `context7`, `github`, `sequential-thinking` (+ project-specific from manifest's `mcp.base_required` and `palace.*` for gimle) | (none) |
| `git_capability` — "What git operations CAN you do? CANNOT? Be precise." | implementer | CAN: `commit`, `push`, `fetch`, `--force-with-lease` | `merge`, `release-cut` |
| `git_capability` | reviewer | CAN: read, `gh pr review --approve`, mergeStateStatus decode | `commit`, `push`, `release-cut` |
| `git_capability` | cto | CAN: all reviewer + `release-cut`, merge to integration_branch | (none) |
| `git_capability` | writer / research | CANNOT: commit, push, merge | `commit`, `push`, `merge` |
| `handoff_procedure` — "Describe step-by-step your handoff to next agent." | every profile except custom | `PATCH /api/issues/<id>` with `assigneeAgentId`; `POST /api/issues/<id>/comments` with `@mention` (trailing space); STOP | (none) |
| `phase_orchestration` — "List phase numbers you orchestrate, comma-separated." | cto | `1.1`, `1.2`, `2`, `3.1`, `3.2`, `4.1`, `4.2` | (none) |
| `phase_orchestration` | every non-cto | "I do not orchestrate phases" or empty | any phase number |

**Cross-target handoff** (mixed-team projects only): smoke posts test issue to `target: claude` CTO with body "Reassign to first `target: codex` agent in your team and ask them to echo 'cross-target ack' back". Successful round-trip in <120s required.

Probe-question library + expected-marker matchers are committed in `paperclips/scripts/lib/_smoke_probes.sh`. Smoke-test invokes them via stage 5 (mcp/skills/git/handoff probes per profile) and stage 7 (e2e handoff incl. cross-target).

**Original §12.C deployment-side checks remain (below).**


Run by operator on real iMac/Mac with full toolchain.

- [ ] On a clean macOS (no paperclip, no `~/.paperclip/`), running `install-paperclip.sh` + `bootstrap-project.sh trading` produces a green smoke-test in <15 min.
- [ ] Adding a new project (`bootstrap-project.sh ios-wallet` from clean state) → green smoke in <5 min.
- [ ] **gimle migration safety:** `migrate-bindings.sh gimle` preserves all 24 UUIDs (verified by `diff before.json after.json` → no removed keys); all in-progress issues remain visible after migration.
- [ ] Watchdog tick in `~/.paperclip/watchdog.log` includes all migrated companies after `bootstrap-watchdog.sh` runs.
- [ ] Handoff alert detection (Phase 3) still fires on simulated `comment_only_handoff`.
- [ ] Telegram plugin: `smoke-test.sh <key>` step 6 delivers a real message to operator's Board chat.

---

## 13. Open questions

1. **AGENTS.md split (v2 direction):** when is the right time to revisit? Triggers: paperclip API gains multi-bundle support, OR universal layer grows to >150 lines (when inlining cost becomes painful).
2. **paperclipai version drift:** when paperclipai upstream fixes PAP-2394 (plugin secret-refs), do we bump `PAPERCLIPAI_VERSION` automatically or require explicit operator approval? Current design: explicit (versions.env edit + `update-versions.sh`).
3. **Watchdog role-taxonomy sync:** should `services/watchdog/src/gimle_watchdog/role_taxonomy.py` read from project manifests directly, or stay hardcoded with manual sync? Current design: stay hardcoded; agree boundaries via convention.
4. **Multi-machine team:** if two operators each run paperclip-instance for the same project, agents from machine A don't see agents from machine B. Out of scope; design optimizes for solo-operator-multi-project.
5. ~~Override scope expansion~~ — **closed in §6.4** (rev3): override applies on resolution layer, custom_includes operates on inclusion list; they're orthogonal and project overrides reach per-agent custom includes too.
6. **MCP indexing prereqs:** `bootstrap-project.sh` step 11 triggers indexing but doesn't fail bootstrap on indexing timeout. Should it block, or warn-and-continue? Current design: warn-and-continue with explicit operator notice; smoke test stage 5 will fail if indexing didn't complete.
7. **Role-split mechanics (rev3 new):** §10.1.1 chose hybrid approach (new craft files alongside legacy with deprecation banner). Open: does the operator want a *helper* for splitting (e.g., a script that scans `roles/cto.md`, finds phase-orchestration content via heuristics, suggests split lines) — or is fully manual rewrite preferred? Trade-off: helper saves time but may suggest wrong cut lines on subtle content. Current design: manual rewrite per role, one PR per role-family.

---

## 14. Implementation phasing (rough sketch — finalized in `writing-plans`)

**Note (rev3):** Day estimates are RANGES, not commitments. They illustrate relative phase weight, not project plan precision. Real timing is finalized in TDD task breakdown via `writing-plans`. Per rev2 deep-review feedback, prior 15-day total was optimistic.

### 14.1 Execution-ownership constraint (rev3)

This work is partially **self-modifying** — Phases A–D edit the prompts, builder, fragments, and runtime contract that the gimle paperclip team itself runs on. Self-execution by gimle agents creates structural problems:

- **Circularity**: a CodeReviewer reviewing the PR that splits its own role file uses pre-split instructions to evaluate post-split content; deployment lands between waves; same agent's reviews drift mid-PR.
- **Self-rescue impossibility**: §10.4 requires pausing all 24 gimle agents during the gimle migration — agents cannot pause themselves to migrate themselves.
- **Known team failure modes** (per operator memory): silent scope reduction in PE deliverables; evidence fabrication on self-modified tooling; subagent best-practice rules without product context. These risks compound when the tooling under change IS the team's own.
- **Watchdog dependency**: `services/watchdog/src/gimle_watchdog/role_taxonomy.py` hardcodes 22 agent names. Mid-flight role taxonomy drift can suppress recovery alerts on the very migration in progress.

Each phase below carries an **Owner** tag.

| Owner tag | Means |
|---|---|
| `operator` | Operator drives execution, possibly via a fresh Claude session. No gimle team runs work, no gimle team review. |
| `team` | gimle paperclip team executes via standard CTO → CR → PE → QA flow. |
| `operator + team` | Operator owns critical decisions and final review; team executes mechanical sub-tasks. |

### 14.2 Phases (with owners)

1. **Phase A: fragment library refactor + role-split (Phase A.1).** Rename heartbeat → wake-and-handoff-basics; split git-workflow into 4; split worktree; classify into universal/git/worktree/handoff/code-review/qa/pre-work/plan dirs. Hybrid role-split per §10.1.1. (**3–4 days**, owner: `operator`) — Self-touching: edits shared/fragments + role files that agents read on next wake.
2. **Phase B: profile library + builder updates.** 8 profile YAMLs; extend builder for `inheritsUniversal`, `extends:`, deduplication (§5.2.1), allowed template sources (§6.5), forbidden-content rejection; preserve existing override precedence (§6.4) and overlay mechanism (§6.7). (**4–5 days**, owner: `operator`) — Builder bug → wrong prompts deployed for ALL agents next deploy.
3. **Phase C: scripts.** install-paperclip.sh; bootstrap-project.sh (interactive + file-mode + reuse-bindings + 2-stage --canary + topological hire); smoke-test.sh (with `--canary-stage` flags); bootstrap-watchdog.sh; update-versions.sh; validate-manifest.sh; rollback.sh; migrate-bindings.sh. (**6–8 days**, owner: `operator + team`) — Tooling, not directly self-touching. Team may write scripts; operator reviews final cut. Scripts MUST be tested against trading/uaudit (not gimle) during this phase.
4. **Phase D: dual-read seam in builder + watchdog + scripts.** Read both legacy `codex-agent-ids.env` and new `bindings.yaml`; warn on conflict; preserve legacy `deploy-agents.sh` callsites until cleanup gate. (**2 days**, owner: `operator`) — Affects state resolution for ALL agents during transition.
5. **Phase E: trading migration** (smallest, fewest in-progress). 2-stage canary deploy. Smoke-test. Overlay placeholder rename. (**1 day**, owner: `team`) — Mechanical, low blast radius if it fails (trading breaks, gimle continues).
6. **Phase F: uaudit migration** (codex-only, plugins). Includes overlay placeholder rename + codex-agents .toml deploy. (**1–2 days**, owner: `team`) — Same risk profile as Phase E; comes after Phase E proves the mechanics work end-to-end.
7. **Phase G: gimle migration** (largest, soft-migrate). Pause/unpause window for both teams (24 agents). Decompose root CLAUDE.md. Per-role craft split where not yet done. (**2–3 days**, owner: `operator`, team paused) — Cannot be self-executed: spec requires pausing all 24 agents; only an external actor can drive without the team racing itself.
8. **Phase H: cleanup gate evaluation + legacy removal.** After cleanup gate (§10.1) — at minimum 7 days stable per metric + operator signoff. (**1 day**, owner: `operator + team`) — Watchdog log analysis (operator) + legacy file removal PR (team can produce, operator approves merge).

### 14.3 Effort distribution

**Total: 19–25 working days**, broken down by owner:
- `operator` solo: ~13–17 days (Phases A, B, D, G)
- `team` solo: ~3–5 days (Phases E, F)
- `operator + team` hybrid: ~6–9 days (Phases C, H)

Operator-only days dominate because the riskiest, most context-heavy work is exactly the self-modifying part. Future similar refactors (post v2) will have less self-modification load and can shift more to team execution.
