# UAA Phase G — Gimle Migration

> **For agentic workers:** REQUIRED SUB-SKILL: This phase is **operator-driven**. Subagent execution is forbidden — gimle team is paused for the duration. Operator runs each step manually with full context.

**Spec:** `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §10.4
**Owner:** `operator` solo, **all 24 gimle agents paused** (per spec §14.1 — cannot self-execute)
**Estimate:** 2–3 days (operator-driven; calendar can stretch)
**Prereq:** Phase E + F complete (trading + uaudit migrations green; mechanics proven on lower-risk targets)
**Blocks:** Phase H (cleanup gate evaluation)

**Goal:** Migrate gimle (24 agents = 12 claude + 12 codex on company `9d8f432c-…`) from legacy schema (`legacy_output_paths: true`, agents:[] empty, UUIDs in `paperclips/codex-agent-ids.env` + paperclip company storage, monolithic CLAUDE.md) to new schema. Decompose CLAUDE.md. Adopt new craft files (Phase A) for all gimle role usages.

**Architecture:** Largest migration. **Cannot be self-executed**: spec §10.4 requires pausing all 24 agents during the migration; agents cannot pause themselves to migrate themselves. Operator drives end-to-end with downtime window of 5–15 min.

**Risk profile:** HIGH. 24 agents with active in-progress issues. Failure modes:
- Lost UUIDs → agents hired with new UUIDs but in-progress issues still reference old UUIDs → orphan issues.
- Decomposed CLAUDE.md missing rules → agent loses critical context on next wake.
- Watchdog handoff_alert false-fire during migration window → spurious comments on production issues.

Mitigations:
- Snapshot ALL gimle state (manifest + dist + bindings + watchdog log) BEFORE starting.
- Reuse existing UUIDs (no API recreate) — `migrate-bindings.sh gimle` extracts UUIDs from both legacy env + paperclip API GET, writes new bindings.yaml. **Zero new POST /agent-hires** for existing agents.
- Pause window planned for low-activity time (operator picks).
- Rollback journal at every step.
- Phase H cleanup gate (7-day stability metric) before legacy file removal.

---

## File Structure

### Modified

```
paperclips/projects/gimle/paperclip-agent-assembly.yaml   # large rewrite: 24 agents declared, schemaVersion: 2, no UUIDs/paths
CLAUDE.md                                                  # decomposed: most content → other files; symlink → AGENTS.md
paperclips/projects/gimle/AGENTS.md.template               # NEW operator-convenience template
docs/contributing/branch-flow.md                           # NEW human-readable extracted from CLAUDE.md
services/palace-mcp/README.md                              # AUGMENTED with extractor/MCP docs from CLAUDE.md
docs/palace-mcp/extractors.md                              # NEW extracted from CLAUDE.md
```

### Created (host-local)

```
~/.paperclip/projects/gimle/bindings.yaml    # 24 UUIDs (no API recreate)
~/.paperclip/projects/gimle/paths.yaml       # gimle paths
~/.paperclip/projects/gimle/plugins.yaml     # telegram (gimle-palace-bot, chat -1003521772993)
```

### Tests

```
paperclips/tests/test_phase_g_gimle_migration.py
paperclips/tests/baseline/phase_g/                # snapshots: manifest, dist, watchdog log
```

---

## Task 1: Snapshot complete gimle pre-state

- [ ] **Step 1: Backup all relevant state**

```bash
mkdir -p paperclips/tests/baseline/phase_g

# Manifest + legacy UUIDs
cp paperclips/projects/gimle/paperclip-agent-assembly.yaml paperclips/tests/baseline/phase_g/gimle-manifest-pre.yaml
cp paperclips/codex-agent-ids.env paperclips/tests/baseline/phase_g/codex-agent-ids-pre.env

# Current dist
./paperclips/build.sh --project gimle --target claude
./paperclips/build.sh --project gimle --target codex
cp -r paperclips/dist/codex paperclips/tests/baseline/phase_g/dist-codex-pre
ls paperclips/dist/*.md | xargs -I {} cp {} paperclips/tests/baseline/phase_g/

# CLAUDE.md
cp CLAUDE.md paperclips/tests/baseline/phase_g/CLAUDE-pre.md

# Watchdog log snapshot (last 24h relevant for handoff baseline)
cp ~/.paperclip/watchdog.log paperclips/tests/baseline/phase_g/watchdog-pre.log 2>/dev/null || true

# Live API state — agent UUIDs from paperclip
PAPERCLIP_API_KEY=<...> curl -fsS \
  "${PAPERCLIP_API_URL}/api/companies/9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64/agents" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
  > paperclips/tests/baseline/phase_g/gimle-agents-api.json

# Issue snapshot — list of in-progress / in-review issues
PAPERCLIP_API_KEY=<...> curl -fsS \
  "${PAPERCLIP_API_URL}/api/companies/9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64/issues?status=in_progress" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
  > paperclips/tests/baseline/phase_g/gimle-issues-in-progress-pre.json
```

- [ ] **Step 2: Verify 24 agents in API**

```bash
jq 'length' paperclips/tests/baseline/phase_g/gimle-agents-api.json
```

Expected: 24 (12 claude + 12 codex).

- [ ] **Step 3: Open journal**

```bash
source paperclips/scripts/lib/_common.sh
source paperclips/scripts/lib/_journal.sh
journal=$(journal_open "gimle-migration")
echo "JOURNAL=$journal"
# Save journal path — every subsequent step records into it.
```

---

## Task 2: Pre-flight verification (no migration if any check fails)

- [ ] **Step 1: All Phase A-F tests green**

```bash
python3 -m pytest paperclips/tests/test_phase_a_*.py paperclips/tests/test_phase_b_*.py \
  paperclips/tests/test_phase_c_*.py paperclips/tests/test_phase_d_*.py \
  paperclips/tests/test_phase_e_*.py paperclips/tests/test_phase_f_*.py -v
```

Expected: 0 FAIL across ~80+ tests.

- [ ] **Step 2: Trading + uaudit still healthy**

```bash
./paperclips/scripts/smoke-test.sh trading --quick
./paperclips/scripts/smoke-test.sh uaudit --quick
```

Expected: green for both.

- [ ] **Step 3: Watchdog log shows 7 days clean for trading + uaudit**

```bash
# Per spec §10.1 cleanup gate metric
gimle-watchdog tail -n 50000 | jq -c 'select(.event | IN("wake_failed", "handoff_alert_posted"))' | wc -l
```

If > 0 over the last 7 days, investigate before starting Phase G. Migration of gimle on top of unhealthy E/F state magnifies risk.

- [ ] **Step 4: Operator confirmation**

Manually confirm in UI:
- All trading + uaudit agents alive (no `status=error`).
- No production iMac issues currently open.
- No release-cut PR pending merge.

If any blocker, postpone Phase G.

---

## Task 3: Pause all 24 gimle agents

- [ ] **Step 1: Pause via API loop**

```bash
COMPANY_ID="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"

agent_uuids=$(curl -fsS "${PAPERCLIP_API_URL}/api/companies/${COMPANY_ID}/agents" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" | jq -r '.[].id')

for uuid in $agent_uuids; do
  curl -fsS -X PATCH "${PAPERCLIP_API_URL}/api/agents/${uuid}" \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" -H "Content-Type: application/json" \
    -d '{"paused": true}' >/dev/null
  echo "paused $uuid"
done
```

Verify count:
```bash
echo "$agent_uuids" | wc -l
```
Expected: 24.

- [ ] **Step 2: Wait for in-flight runs to drain (5 min)**

```bash
sleep 300
running=$(curl -fsS "${PAPERCLIP_API_URL}/api/companies/${COMPANY_ID}/runs?status=running" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" | jq length)
echo "still running: $running"
```

If `running > 0`, wait or manually abort runs.

- [ ] **Step 3: Snapshot post-pause state**

```bash
journal_record "$journal" "$(jq -n --arg ts "$(date -u +%Y%m%dT%H%M%SZ)" --argjson n 24 \
  '{kind:"agents_paused",timestamp:$ts,count:$n}')"
```

---

## Task 4: Extract bindings + paths (no API recreate)

- [ ] **Step 1: Run migrate-bindings (reads both legacy env + API)**

```bash
./paperclips/scripts/migrate-bindings.sh gimle --dry-run
```

Inspect output. Expected: 24 agents listed (11 from codex-agent-ids.env + 13 from API; some overlap if both sources have same agent — bindings precedence per Phase D).

- [ ] **Step 2: Run for real**

```bash
./paperclips/scripts/migrate-bindings.sh gimle
cat ~/.paperclip/projects/gimle/bindings.yaml
```

Verify count:
```bash
yq '.agents | length' ~/.paperclip/projects/gimle/bindings.yaml
```
Expected: 24.

- [ ] **Step 3: Conflict check**

```bash
./paperclips/scripts/migrate-bindings.sh gimle --check-conflicts
```

Expected: "no conflicts". If conflicts, inspect — likely an agent renamed at some point. Resolve manually (operator picks correct UUID, edits bindings.yaml).

- [ ] **Step 4: Create paths.yaml**

```bash
cat > ~/.paperclip/projects/gimle/paths.yaml <<EOF
schemaVersion: 2
project_root: /Users/ant013/Android/Gimle-Palace
primary_repo_root: /Users/ant013/Android/Gimle-Palace
production_checkout: /Users/Shared/Ios/Gimle-Palace
team_workspace_root_claude: /Users/Shared/Ios/worktrees/claude
team_workspace_root_codex: /Users/Shared/Ios/worktrees/cx/Gimle-Palace
operator_memory_dir: ~/.claude/projects/-Users-ant013-Android-Gimle-Palace/memory
overlay_root: paperclips/projects/gimle/overlays
EOF
```

- [ ] **Step 5: Create plugins.yaml (telegram)**

```bash
plugin_id=$(yq -r '.telegram.plugin_id' ~/.paperclip/host-plugins.yaml)
cat > ~/.paperclip/projects/gimle/plugins.yaml <<EOF
schemaVersion: 2
telegram:
  plugin_id: "${plugin_id}"
  chat_id: "-1003521772993"   # gimle palace group
EOF
```

- [ ] **Step 6: Failing test → PASS**

```python
# paperclips/tests/test_phase_g_gimle_migration.py
import os, yaml
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[1]
HOST = Path(os.path.expanduser("~/.paperclip/projects/gimle"))


def test_bindings_yaml_has_24_agents():
    p = HOST / "bindings.yaml"
    if not p.is_file():
        pytest.skip("not yet migrated")
    data = yaml.safe_load(p.read_text())
    assert len(data["agents"]) == 24


def test_paths_yaml_has_dual_team_roots():
    p = HOST / "paths.yaml"
    if not p.is_file():
        pytest.skip("not yet migrated")
    data = yaml.safe_load(p.read_text())
    assert "team_workspace_root_claude" in data
    assert "team_workspace_root_codex" in data


def test_no_uuid_conflicts_between_legacy_and_new():
    """resolve_bindings reports no conflicts for gimle."""
    pytest.importorskip("yaml")
    from paperclips.scripts.resolve_bindings import resolve_all
    legacy = REPO / "paperclips" / "codex-agent-ids.env"
    bindings = HOST / "bindings.yaml"
    if not bindings.is_file():
        pytest.skip("not yet migrated")
    out = resolve_all(legacy_env_path=legacy, bindings_yaml_path=bindings)
    assert out["conflicts"] == [], f"unexpected conflicts: {out['conflicts']}"
```

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v
```

- [ ] **Step 7: Commit (test only)**

```bash
git add paperclips/tests/test_phase_g_gimle_migration.py
git commit -m "test(uaa-phase-g): gimle host-local files (bindings/paths/plugins) verified"
```

---

## Task 5: Decompose CLAUDE.md

CLAUDE.md is ~250+ lines mixing:
- Project rules (branch flow, deploy)
- palace-mcp + extractor docs
- Iron rules (codified incidents)

Extract into multiple files; CLAUDE.md becomes a thin pointer + symlink.

- [ ] **Step 1: Failing test**

```python
def test_root_claude_md_points_to_agents_md():
    """Per spec §3.3 + §10.4: root CLAUDE.md is symlink/thin pointer to AGENTS.md."""
    p = REPO / "CLAUDE.md"
    if not p.exists():
        pytest.skip("CLAUDE.md may have been removed")
    if p.is_symlink():
        # Verify symlink target
        target = p.resolve()
        assert target.name == "AGENTS.md"
        return
    # Or thin pointer:
    text = p.read_text()
    assert len(text.split("\n")) <= 30, f"CLAUDE.md not slim: {len(text.split(chr(10)))} lines"


def test_extractor_docs_in_palace_readme():
    p = REPO / "services" / "palace-mcp" / "README.md"
    text = p.read_text()
    assert "extractor" in text.lower()


def test_branch_flow_doc_exists():
    p = REPO / "docs" / "contributing" / "branch-flow.md"
    assert p.is_file()


def test_extractors_doc_exists():
    p = REPO / "docs" / "palace-mcp" / "extractors.md"
    assert p.is_file()
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v -k "claude_md or extractor or branch_flow"
```

- [ ] **Step 3: Read current CLAUDE.md and split content**

```bash
wc -l CLAUDE.md
cat CLAUDE.md | head -100
```

Identify sections (typical markdown headers). Split per the following table:

| Current CLAUDE.md section | Goes to |
|---|---|
| `## Branch Flow`, iron rules, force-push policy | `docs/contributing/branch-flow.md` |
| `## Production deploy on iMac`, palace-mcp deploy | `services/palace-mcp/README.md` |
| `## AGENTS.md deploy on iMac` | `services/palace-mcp/README.md` |
| `## Docker Compose Profiles`, env, mounts | `services/palace-mcp/README.md` |
| `## Extractors` (large block) + per-extractor sections | `docs/palace-mcp/extractors.md` |
| `## Bundles (GIM-182)` | `docs/palace-mcp/extractors.md` |
| `## Mounting project repos for palace.git.*` | `services/palace-mcp/README.md` |
| `## Pinning` (spec authoring rule) | `paperclips/projects/gimle/AGENTS.md.template` |
| `## Operator auto-memory` | `paperclips/projects/gimle/AGENTS.md.template` |
| `## Paperclip team workflow` (phase choreography) | `fragments/handoff/phase-orchestration.md` (already there post-Phase A) — DELETE from CLAUDE.md |

- [ ] **Step 4: Create destination files**

```bash
mkdir -p docs/contributing docs/palace-mcp

# Extract sections to new files (operator does this manually with sed/awk OR via dedicated text editor — content too project-specific to script)
```

For each new file, create with first-line title and migrated content. Example skeleton:

`docs/contributing/branch-flow.md`:
```markdown
# Gimle-Palace Branch Flow

(Content extracted from former CLAUDE.md "Branch Flow" section.)

## Single mainline: `develop`
...
```

`services/palace-mcp/README.md` — append (do not overwrite existing content if any):
```markdown
## Production deploy on iMac

(Content from former CLAUDE.md "Production deploy on iMac" section.)
...
```

`docs/palace-mcp/extractors.md`:
```markdown
# palace-mcp Extractors

(Content from former CLAUDE.md "Extractors" section.)
...
```

- [ ] **Step 5: Slim CLAUDE.md to thin pointer (or symlink)**

Choose one:

**Option A — symlink (recommended per spec §3.3):**
```bash
mv CLAUDE.md CLAUDE.md.removed-uaa-phase-g.bak
ln -s paperclips/projects/gimle/AGENTS.md CLAUDE.md
```

**Option B — thin pointer (if symlink causes tooling issues):**
```bash
cat > CLAUDE.md <<EOF
# Gimle-Palace — Project Reference

This file is intentionally slim. Authoritative references live elsewhere:

- **Per-agent runtime instructions**: composed by builder, deployed via paperclip API. See \`paperclips/projects/gimle/paperclip-agent-assembly.yaml\` + \`paperclips/fragments/profiles/\`.
- **Branch flow + git rules**: \`docs/contributing/branch-flow.md\`
- **palace-mcp ops + deploy**: \`services/palace-mcp/README.md\`
- **palace-mcp extractor catalog**: \`docs/palace-mcp/extractors.md\`
- **AGENTS.md template (operator-convenience)**: \`paperclips/projects/gimle/AGENTS.md.template\`

For UAA migration history, see \`docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md\`.
EOF
```

- [ ] **Step 6: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v -k "claude_md or extractor or branch_flow"
```

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md docs/contributing/branch-flow.md docs/palace-mcp/extractors.md services/palace-mcp/README.md
git commit -m "feat(uaa-phase-g): decompose CLAUDE.md into branch-flow + palace-mcp docs + AGENTS template"
```

---

## Task 6: Create gimle AGENTS.md.template (operator-convenience)

**Files:**
- Create: `paperclips/projects/gimle/AGENTS.md.template`

- [ ] **Step 1: Failing test**

```python
def test_gimle_agents_template_path_free():
    """AGENTS.md.template must NOT contain absolute paths or UUIDs."""
    p = REPO / "paperclips" / "projects" / "gimle" / "AGENTS.md.template"
    if not p.is_file():
        pytest.skip("not yet created")
    text = p.read_text()
    import re
    assert "/Users/Shared" not in text
    assert "/Users/ant013" not in text
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.I)


def test_gimle_agents_template_uses_template_refs():
    p = REPO / "paperclips" / "projects" / "gimle" / "AGENTS.md.template"
    if not p.is_file():
        pytest.skip("not yet created")
    text = p.read_text()
    # Must use {{paths.X}} for any host paths it references
    assert "{{" in text
```

- [ ] **Step 2: Create template**

```markdown
# Gimle-Palace — Project AGENTS.md (operator session)

> This file is rendered into operator's local CLI workspace at `{{paths.project_root}}/AGENTS.md` via `bootstrap-project.sh gimle`. Per-agent paperclip-deployed AGENTS.md is composed separately by the builder per UAA spec §3.

## Project facts

- **Issue prefix**: `{{project.issue_prefix}}`
- **Integration branch**: `{{project.integration_branch}}`
- **Paperclip company id**: `{{bindings.company_id}}` (host-local; never commit)
- **Production checkout**: `{{paths.production_checkout}}`
- **Team workspaces**: `{{paths.team_workspace_root_claude}}`, `{{paths.team_workspace_root_codex}}`

## MCP

Service: `{{mcp.service_name}}`
Tool namespace: `{{mcp.tool_namespace}}`
Required: codebase-memory, context7, serena, github, sequential-thinking.

## References

- Branch flow + iron rules: `docs/contributing/branch-flow.md`
- palace-mcp ops: `services/palace-mcp/README.md`
- palace-mcp extractors: `docs/palace-mcp/extractors.md`
- UAA spec: `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md`

## Pinning notes

When editing specs/plans, cite SHA. Don't assume "current develop" still means what it meant when a future reader lands here.
```

- [ ] **Step 3: PASS + commit**

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v -k template
git add paperclips/projects/gimle/AGENTS.md.template paperclips/tests/test_phase_g_gimle_migration.py
git commit -m "feat(uaa-phase-g): gimle AGENTS.md.template (operator-convenience, path-free)"
```

---

## Task 7: Rewrite gimle manifest (24 agents, profiles, no UUIDs/paths)

**Files:**
- Modify: `paperclips/projects/gimle/paperclip-agent-assembly.yaml`

- [ ] **Step 1: Failing test**

```python
def test_gimle_manifest_passes_validator():
    from paperclips.scripts.validate_manifest import validate_manifest
    validate_manifest(REPO / "paperclips" / "projects" / "gimle" / "paperclip-agent-assembly.yaml")


def test_gimle_manifest_has_24_agents():
    import yaml
    data = yaml.safe_load((REPO / "paperclips" / "projects" / "gimle" / "paperclip-agent-assembly.yaml").read_text())
    assert len(data["agents"]) == 24
    targets = [a["target"] for a in data["agents"]]
    assert targets.count("claude") == 12
    assert targets.count("codex") == 12


def test_gimle_no_legacy_output_paths():
    import yaml
    data = yaml.safe_load((REPO / "paperclips" / "projects" / "gimle" / "paperclip-agent-assembly.yaml").read_text())
    assert data.get("compatibility", {}).get("legacy_output_paths") is False
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v -k "manifest_passes or 24_agents or legacy_output"
```

- [ ] **Step 3: Rewrite manifest**

Replace `paperclips/projects/gimle/paperclip-agent-assembly.yaml` with new schema. The 24 agents (12 claude + 12 codex) declared explicitly. UUIDs come from `~/.paperclip/projects/gimle/bindings.yaml` (resolved at build time by Phase D resolver).

```yaml
schemaVersion: 2

project:
  key: gimle
  display_name: Gimle
  system_name: Gimle-Palace
  issue_prefix: GIM
  integration_branch: develop
  specs_dir: docs/superpowers/specs
  plans_dir: docs/superpowers/plans

domain:
  wallet_target_short: Unstoppable
  wallet_target_name: Unstoppable Wallet
  wallet_target_slug: Unstoppable-wallet

mcp:
  service_name: palace-mcp
  package_name: palace_mcp
  tool_namespace: palace
  base_required:
    - codebase-memory
    - context7
    - serena
    - github
    - sequential-thinking
  codebase_memory_projects:
    primary: repos-gimle

skills:
  additions:
    project: []
    by_role: {}

subagents:
  additions:
    project: []
    by_role: {}

targets:
  claude:
    instruction_entry_file: AGENTS.md
    adapter_type: claude_local
    deploy_mode: api
    instructions_bundle_mode: managed
  codex:
    instruction_entry_file: AGENTS.md
    adapter_type: codex_local
    deploy_mode: api
    instructions_bundle_mode: managed

compatibility:
  legacy_output_paths: false

agents:
  # === Claude team (12) ===
  - { agent_name: CTO,                       role_source: roles/cto.md,                      profile: cto,         target: claude }
  - { agent_name: CodeReviewer,              role_source: roles/code-reviewer.md,            profile: reviewer,    target: claude, reportsTo: CTO }
  - { agent_name: OpusArchitectReviewer,     role_source: roles/opus-architect-reviewer.md,  profile: reviewer,    target: claude, reportsTo: CTO,
      custom_includes: [code-review/adversarial.md] }
  - { agent_name: PythonEngineer,            role_source: roles/python-engineer.md,          profile: implementer, target: claude, reportsTo: CTO }
  - { agent_name: MCPEngineer,               role_source: roles/mcp-engineer.md,             profile: implementer, target: claude, reportsTo: CTO }
  - { agent_name: InfraEngineer,             role_source: roles/infra-engineer.md,           profile: implementer, target: claude, reportsTo: CTO }
  - { agent_name: BlockchainEngineer,        role_source: roles/blockchain-engineer.md,      profile: implementer, target: claude, reportsTo: CTO }
  - { agent_name: SecurityAuditor,           role_source: roles/security-auditor.md,         profile: reviewer,    target: claude, reportsTo: CTO }
  - { agent_name: QAEngineer,                role_source: roles/qa-engineer.md,              profile: qa,          target: claude, reportsTo: CTO }
  - { agent_name: ResearchAgent,             role_source: roles/research-agent.md,           profile: research,    target: claude, reportsTo: CTO }
  - { agent_name: TechnicalWriter,           role_source: roles/technical-writer.md,         profile: writer,      target: claude, reportsTo: CTO }
  - { agent_name: Auditor,                   role_source: roles/auditor.md,                  profile: reviewer,    target: claude, reportsTo: CTO }

  # === Codex team (12) ===
  - { agent_name: CXCto,                     role_source: roles-codex/cx-cto.md,             profile: cto,         target: codex }
  - { agent_name: CXCodeReviewer,            role_source: roles-codex/cx-code-reviewer.md,   profile: reviewer,    target: codex, reportsTo: CXCto }
  - { agent_name: CodexArchitectReviewer,    role_source: roles-codex/codex-architect-reviewer.md, profile: reviewer, target: codex, reportsTo: CXCto,
      custom_includes: [code-review/adversarial.md] }
  - { agent_name: CXPythonEngineer,          role_source: roles-codex/cx-python-engineer.md, profile: implementer, target: codex, reportsTo: CXCto }
  - { agent_name: CXMcpEngineer,             role_source: roles-codex/cx-mcp-engineer.md,    profile: implementer, target: codex, reportsTo: CXCto }
  - { agent_name: CXInfraEngineer,           role_source: roles-codex/cx-infra-engineer.md,  profile: implementer, target: codex, reportsTo: CXCto }
  - { agent_name: CXBlockchainEngineer,      role_source: roles-codex/cx-blockchain-engineer.md, profile: implementer, target: codex, reportsTo: CXCto }
  - { agent_name: CXSecurityAuditor,         role_source: roles-codex/cx-security-auditor.md, profile: reviewer,   target: codex, reportsTo: CXCto }
  - { agent_name: CXQaEngineer,              role_source: roles-codex/cx-qa-engineer.md,     profile: qa,          target: codex, reportsTo: CXCto }
  - { agent_name: CXResearchAgent,           role_source: roles-codex/cx-research-agent.md,  profile: research,    target: codex, reportsTo: CXCto }
  - { agent_name: CXTechnicalWriter,         role_source: roles-codex/cx-technical-writer.md, profile: writer,     target: codex, reportsTo: CXCto }
  - { agent_name: CXAuditor,                 role_source: roles-codex/cx-auditor.md,         profile: reviewer,    target: codex, reportsTo: CXCto }
```

**Naming alignment with bindings.yaml**: ensure `agent_name` matches the canonical name in bindings.yaml (resolved by `_normalize_legacy_name` in Phase D). Verify:
```bash
diff <(yq -r '.agents[].agent_name' paperclips/projects/gimle/paperclip-agent-assembly.yaml | sort) \
     <(yq -r '.agents | keys | .[]' ~/.paperclip/projects/gimle/bindings.yaml | sort)
```
Expected: zero diff. If diff exists, fix one side or the other to match.

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/projects/gimle/paperclip-agent-assembly.yaml
git commit -m "feat(uaa-phase-g): rewrite gimle manifest — 24 agents declared, schemaVersion 2, profiles, reportsTo"
```

---

## Task 8: Re-render gimle + verify

- [ ] **Step 1: Build both targets**

```bash
./paperclips/build.sh --project gimle --target claude
./paperclips/build.sh --project gimle --target codex
```

Expected: zero errors. Note any "dedup applied" messages.

- [ ] **Step 2: Compare line counts vs baseline**

```bash
echo "=== claude ==="
for f in paperclips/dist/gimle/claude/*.md; do
  name=$(basename "$f")
  pre=$(wc -l < "paperclips/tests/baseline/phase_g/${name}" 2>/dev/null || echo "?")
  post=$(wc -l < "$f")
  printf "%-30s pre=%-4s post=%-4s reduction=%s\n" "$name" "$pre" "$post" "$((pre - post))"
done
echo "=== codex ==="
for f in paperclips/dist/gimle/codex/*.md; do
  name=$(basename "$f")
  pre=$(wc -l < "paperclips/tests/baseline/phase_g/dist-codex-pre/$(basename "$name" .md | sed 's/^/cx-/').md" 2>/dev/null || echo "?")
  post=$(wc -l < "$f")
  printf "%-30s pre=%-4s post=%-4s\n" "$name" "$pre" "$post"
done
```

Expected: every agent shrinks 30-50%.

- [ ] **Step 3: Profile boundary tests**

```python
def test_gimle_implementer_no_phase_orchestration():
    p = REPO / "paperclips" / "dist" / "gimle" / "claude" / "PythonEngineer.md"
    if not p.is_file(): return
    text = p.read_text()
    assert "Phase 1.1" not in text
    assert "Phase 4.2" not in text
    assert "release-cut" not in text


def test_gimle_writer_minimal_size():
    p = REPO / "paperclips" / "dist" / "gimle" / "claude" / "TechnicalWriter.md"
    if not p.is_file(): return
    lines = p.read_text().count("\n")
    assert lines < 250, f"writer too large: {lines}"


def test_gimle_cto_has_all_cto_capabilities():
    p = REPO / "paperclips" / "dist" / "gimle" / "claude" / "CTO.md"
    if not p.is_file(): return
    text = p.read_text()
    assert "Phase 1.1" in text
    assert "release-cut" in text
    assert "Karpathy discipline" in text
```

- [ ] **Step 4: PASS + commit (test only)**

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v
git add paperclips/tests/test_phase_g_gimle_migration.py
git commit -m "test(uaa-phase-g): gimle profile boundaries + size reductions verified"
```

---

## Task 9: Deploy (canary 2-stage + fan-out)

- [ ] **Step 1: Run bootstrap with canary**

```bash
./paperclips/scripts/bootstrap-project.sh gimle \
  --reuse-bindings ~/.paperclip/projects/gimle/bindings.yaml \
  --canary
```

Stage 1: TechnicalWriter (writer profile) → smoke stage 1.
Stage 2: CTO (cto profile) → smoke stage 2.
Stage 3: fan-out remaining 22.

If failure at any stage:
```bash
./paperclips/scripts/rollback.sh <journal-id>
```

- [ ] **Step 2: Verify all 24 deployed**

```bash
for name in $(yq -r '.agents | keys | .[]' ~/.paperclip/projects/gimle/bindings.yaml); do
  uuid=$(yq -r ".agents.${name}" ~/.paperclip/projects/gimle/bindings.yaml)
  config=$(curl -fsS "${PAPERCLIP_API_URL}/api/agents/${uuid}/configuration" \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" 2>/dev/null)
  hb=$(echo "$config" | jq -r '.runtimeConfig.heartbeat.enabled')
  printf "%-30s heartbeat=%s\n" "$name" "$hb"
done
```

Expected: 24 entries, all `heartbeat=false`.

- [ ] **Step 3: Set up workspaces (handled by bootstrap step 9)**

Verify:
```bash
ls /Users/Shared/Ios/worktrees/claude/CTO/workspace/AGENTS.md
ls /Users/Shared/Ios/worktrees/cx/Gimle-Palace/CXCto/workspace/AGENTS.md
```

---

## Task 10: Unpause + smoke + observation

- [ ] **Step 1: Unpause all 24 agents**

```bash
for name in $(yq -r '.agents | keys | .[]' ~/.paperclip/projects/gimle/bindings.yaml); do
  uuid=$(yq -r ".agents.${name}" ~/.paperclip/projects/gimle/bindings.yaml)
  curl -fsS -X PATCH "${PAPERCLIP_API_URL}/api/agents/${uuid}" \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" -H "Content-Type: application/json" \
    -d '{"paused": false}' >/dev/null
  echo "unpaused $name"
done
```

- [ ] **Step 2: Full 7-stage smoke**

```bash
./paperclips/scripts/smoke-test.sh gimle
```

Expected: 7/7 PASS.

- [ ] **Step 3: 2h watchdog observation**

```bash
tail -f ~/.paperclip/watchdog.log | jq -c 'select(.event | IN("wake_failed", "handoff_alert_posted", "escalation"))'
```

Expected: zero events for gimle company in 2h.

If `handoff_alert_posted` for gimle: investigate immediately. Likely cause:
- Agent name mismatch between bindings and watchdog role-taxonomy (Phase A.1 role-split renamed agents).
- New canonical name (e.g., `CXCto`) not in `services/watchdog/src/gimle_watchdog/role_taxonomy.py` — mark as TODO, see open Q in spec §13.

- [ ] **Step 4: Verify in-progress issues survived**

```bash
running_now=$(curl -fsS "${PAPERCLIP_API_URL}/api/companies/${COMPANY_ID}/issues?status=in_progress" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" | jq length)
running_pre=$(jq length paperclips/tests/baseline/phase_g/gimle-issues-in-progress-pre.json)
echo "in_progress: pre=$running_pre, now=$running_now"
```

Expected: `running_now >= running_pre - 2` (allow for 1-2 issues that completed organically during migration window).

If `running_now < running_pre - 5`, suspect lost issues — check journal + investigate.

---

## Task 11: Phase G acceptance + spec changelog

- [ ] **Step 1: All Phase G tests**

```bash
python3 -m pytest paperclips/tests/test_phase_g_gimle_migration.py -v
```

- [ ] **Step 2: Spec changelog**

```markdown
**Phase G complete (YYYY-MM-DD):**
- gimle migration end-to-end on operator's machine.
- 24 agents (12 claude + 12 codex) reused existing UUIDs (zero API recreate).
- Manifest rewritten: schemaVersion 2, agents declared, no UUIDs/paths, profiles + reportsTo.
- CLAUDE.md decomposed into branch-flow.md + palace-mcp/README.md + extractors.md + AGENTS.md.template.
- 2-stage canary deploy + 7-stage smoke green.
- 2h post-migration observation: zero wake_failed / handoff_alert events.
- All in-progress issues preserved (snapshot diff: 0 lost).
- Operator manual signoff documented.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md
git commit -m "docs(uaa-phase-g): mark gimle migration complete in spec changelog"
```

---

## Phase G acceptance gate (before Phase H)

- [ ] All 24 gimle agents deployed with new AGENTS.md.
- [ ] All Phase A-G tests green.
- [ ] `validate-manifest.sh gimle` passes.
- [ ] `~/.paperclip/projects/gimle/bindings.yaml` has 24 UUIDs (no conflicts vs legacy).
- [ ] CLAUDE.md is symlink or thin pointer; original content lives in branch-flow.md / palace-mcp/README.md / extractors.md.
- [ ] Smoke test full pass.
- [ ] 2h watchdog observation: zero wake_failed / handoff_alert for gimle.
- [ ] In-progress issue count preserved (no orphan issues).
- [ ] At least one in-progress issue progressed normally (CTO → CR handoff observed).
- [ ] Operator signoff in journal + commit message.
