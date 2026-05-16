# UAA Phase F — UAudit Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Spec:** `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §10.3
**Owner:** `team` (per spec §14.2 — same risk profile as Phase E; codex-only project)
**Estimate:** 1–2 days
**Prereq:** Phase E complete (trading migration green; validates approach)
**Blocks:** Phase G (gimle migration uses same pattern + role-craft adoption)

**Goal:** Migrate uaudit (17 codex-only agents across ios/android platforms) to new schema. Preserve telegram plugin integration, codex subagents, platform: opaque-passthrough.

**Architecture:** Same as Phase E with extras:
1. 17 agents (vs 5 trading) → larger topo graph, longer canary fan-out.
2. Telegram plugin in use → `~/.paperclip/projects/uaudit/plugins.yaml` + overlay placeholders rename.
3. Codex subagents (5 .toml files in `paperclips/projects/uaudit/codex-agents/`) → deploy to `~/.codex/projects/uaudit/agents/`.
4. Per-agent `platform: ios|android|all` opaque-passthrough preserved.
5. Per-agent `primary_codebase_memory_project` retained (read by `_build_template_sources`).

**Risk profile:** MEDIUM. Larger blast radius than trading; if migration fails, 17 agents stuck. But uaudit is read-only (audit work, no code changes) → at-worst delays audits, doesn't lose data.

---

## File Structure

### Modified

```
paperclips/projects/uaudit/paperclip-agent-assembly.yaml         # strip UUIDs/paths/telegram_plugin_id; schemaVersion: 2
paperclips/projects/uaudit/overlays/codex/_common.md             # placeholder rename
paperclips/projects/uaudit/overlays/codex/{UWICTO,UWACTO,...}.md # 6 per-agent overlays — placeholder rename if any
```

### Created (host-local)

```
~/.paperclip/projects/uaudit/bindings.yaml         # 17 UUIDs
~/.paperclip/projects/uaudit/paths.yaml            # uaudit absolute paths
~/.paperclip/projects/uaudit/plugins.yaml          # telegram plugin_id reference
```

### Deployed to host

```
~/.codex/projects/uaudit/agents/uaudit-bug-hunter.toml
~/.codex/projects/uaudit/agents/uaudit-security-auditor.toml
~/.codex/projects/uaudit/agents/uaudit-blockchain-auditor.toml
~/.codex/projects/uaudit/agents/uaudit-swift-audit-specialist.toml
~/.codex/projects/uaudit/agents/uaudit-kotlin-audit-specialist.toml
```

### Tests

```
paperclips/tests/test_phase_f_uaudit_migration.py
```

---

## Task 1: Pre-migration backup + journal

- [ ] **Step 1: Verify Phase E acceptance**

```bash
python3 -m pytest paperclips/tests/test_phase_e_*.py -v
```

- [ ] **Step 2: Snapshot current uaudit state**

```bash
mkdir -p paperclips/tests/baseline/phase_f
cp paperclips/projects/uaudit/paperclip-agent-assembly.yaml paperclips/tests/baseline/phase_f/uaudit-manifest-pre.yaml
./paperclips/build.sh --project uaudit --target codex
cp -r paperclips/dist/uaudit paperclips/tests/baseline/phase_f/uaudit-dist-pre
```

- [ ] **Step 3: Open journal**

```bash
source paperclips/scripts/lib/_common.sh
source paperclips/scripts/lib/_journal.sh
journal=$(journal_open "uaudit-migration")
echo "journal: $journal"
```

---

## Task 2: Extract bindings + paths + plugins to host-local

**Files:**
- Create: `~/.paperclip/projects/uaudit/bindings.yaml`
- Create: `~/.paperclip/projects/uaudit/paths.yaml`
- Create: `~/.paperclip/projects/uaudit/plugins.yaml`

- [ ] **Step 1: Failing test**

```python
# paperclips/tests/test_phase_f_uaudit_migration.py
import os
from pathlib import Path
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HOST = Path(os.path.expanduser("~/.paperclip/projects/uaudit"))


def test_bindings_yaml_has_17_agents():
    p = HOST / "bindings.yaml"
    if not p.is_file():
        pytest.skip("not yet migrated")
    data = yaml.safe_load(p.read_text())
    assert len(data["agents"]) == 17
    expected = {
        "AUCEO", "UWICTO", "UWACTO",
        "UWISwiftAuditor", "UWAKotlinAuditor",
        "UWICryptoAuditor", "UWACryptoAuditor",
        "UWISecurityAuditor", "UWASecurityAuditor",
        "UWIQAEngineer", "UWAQAEngineer",
        "UWIInfraEngineer", "UWAInfraEngineer",
        "UWIResearchAgent", "UWAResearchAgent",
        "UWITechnicalWriter", "UWATechnicalWriter",
    }
    assert set(data["agents"].keys()) == expected


def test_paths_yaml_exists():
    p = HOST / "paths.yaml"
    if not p.is_file():
        pytest.skip("not yet migrated")
    data = yaml.safe_load(p.read_text())
    for k in ["project_root", "primary_repo_root", "team_workspace_root"]:
        assert k in data


def test_plugins_yaml_has_telegram():
    p = HOST / "plugins.yaml"
    if not p.is_file():
        pytest.skip("not yet migrated")
    data = yaml.safe_load(p.read_text())
    assert "telegram" in data
    assert data["telegram"]["plugin_id"]
```

- [ ] **Step 2: Verify SKIP (3 tests)**

```bash
python3 -m pytest paperclips/tests/test_phase_f_uaudit_migration.py -v
```

- [ ] **Step 3: Run migrate-bindings.sh**

```bash
./paperclips/scripts/migrate-bindings.sh uaudit --dry-run
# Inspect output. If 17 UUIDs present, run for real:
./paperclips/scripts/migrate-bindings.sh uaudit
cat ~/.paperclip/projects/uaudit/bindings.yaml
```

- [ ] **Step 4: Create paths.yaml**

```bash
cat > ~/.paperclip/projects/uaudit/paths.yaml <<EOF
schemaVersion: 2
project_root: /Users/Shared/UnstoppableAudit
primary_repo_root: /Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios
production_checkout: /Users/Shared/UnstoppableAudit
team_workspace_root: /Users/Shared/UnstoppableAudit/runs
operator_memory_dir: /Users/Shared/UnstoppableAudit
overlay_root: paperclips/projects/uaudit/overlays
EOF
```

- [ ] **Step 5: Extract telegram plugin_id from current manifest**

```bash
plugin_id=$(yq -r '.report_delivery.telegram_plugin_id' paperclips/projects/uaudit/paperclip-agent-assembly.yaml)
chat_id="<operator-fills-from-current-paperclip-instance>"

cat > ~/.paperclip/projects/uaudit/plugins.yaml <<EOF
schemaVersion: 2
telegram:
  plugin_id: "${plugin_id}"
  chat_id: "${chat_id}"
EOF
```

If `chat_id` unknown, `paperclip plugin show ${plugin_id}` (or `GET /api/plugins/${plugin_id}`) to retrieve current routes.

- [ ] **Step 6: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_f_uaudit_migration.py -v -k "bindings_yaml_has_17 or paths_yaml or plugins_yaml"
```

- [ ] **Step 7: Commit (test file only)**

```bash
git add paperclips/tests/test_phase_f_uaudit_migration.py
git commit -m "test(uaa-phase-f): host-local files for uaudit (bindings/paths/plugins) verified"
```

---

## Task 3: Strip UUIDs + paths + telegram_plugin_id from manifest

**Files:**
- Modify: `paperclips/projects/uaudit/paperclip-agent-assembly.yaml`

- [ ] **Step 1: Failing test**

```python
def test_uaudit_manifest_passes_validator():
    from paperclips.scripts.validate_manifest import validate_manifest
    validate_manifest(REPO / "paperclips" / "projects" / "uaudit" / "paperclip-agent-assembly.yaml")


def test_uaudit_manifest_no_uuids_or_paths():
    p = REPO / "paperclips" / "projects" / "uaudit" / "paperclip-agent-assembly.yaml"
    text = p.read_text()
    import re
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.I), \
        "inline UUIDs found"
    assert "/Users/Shared" not in text, "abs paths found"


def test_uaudit_manifest_no_telegram_plugin_id_inline():
    p = REPO / "paperclips" / "projects" / "uaudit" / "paperclip-agent-assembly.yaml"
    text = p.read_text()
    # report_delivery.telegram_plugin_id is host-local now
    assert "telegram_plugin_id" not in text


def test_uaudit_manifest_has_17_agents_with_profiles():
    import yaml
    data = yaml.safe_load((REPO / "paperclips" / "projects" / "uaudit" / "paperclip-agent-assembly.yaml").read_text())
    assert len(data["agents"]) == 17
    for a in data["agents"]:
        assert "profile" in a
        assert "platform" in a  # uaudit-specific opaque-passthrough


def test_uaudit_manifest_subagents_preserved():
    import yaml
    data = yaml.safe_load((REPO / "paperclips" / "projects" / "uaudit" / "paperclip-agent-assembly.yaml").read_text())
    sub = data.get("subagents", {}).get("additions", {}).get("project", [])
    assert "uaudit-bug-hunter" in sub
    assert "uaudit-security-auditor" in sub
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_f_uaudit_migration.py -v -k manifest
```

- [ ] **Step 3: Rewrite uaudit manifest**

Read current `paperclips/projects/uaudit/paperclip-agent-assembly.yaml` and produce:

```yaml
schemaVersion: 2

project:
  key: uaudit
  display_name: UnstoppableAudit
  system_name: UnstoppableAudit
  issue_prefix: UNS
  integration_branch: develop
  specs_dir: docs/superpowers/specs
  plans_dir: docs/superpowers/plans

domain:
  wallet_target_short: Unstoppable
  wallet_target_name: Unstoppable Wallet
  wallet_target_slug: unstoppable-wallet

mcp:
  service_name: uaudit
  package_name: uaudit
  tool_namespace: uaudit
  base_required:
    - codebase-memory
    - context7
    - serena
    - github
    - sequential-thinking
  codebase_memory_projects:
    primary: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    ios: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    android: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
  additions:
    project:
      - neo4j
    by_role: {}

skills:
  additions:
    project: []
    by_role: {}

subagents:
  additions:
    project:
      - uaudit-swift-audit-specialist
      - uaudit-kotlin-audit-specialist
      - uaudit-bug-hunter
      - uaudit-security-auditor
      - uaudit-blockchain-auditor
    by_role: {}

# report_delivery section removed — telegram_plugin_id moved to ~/.paperclip/projects/uaudit/plugins.yaml
# operator can still set defaults below for reporting metadata that's safe in repo:
report_delivery:
  default_owner: UWAInfraEngineer
  android_owner: UWAInfraEngineer
  ios_owner: UWIInfraEngineer

targets:
  codex:
    instruction_entry_file: AGENTS.md
    adapter_type: codex_local
    deploy_mode: api
    instructions_bundle_mode: managed

compatibility:
  legacy_output_paths: false

agents:
  - agent_name: AUCEO
    role_source: roles-codex/cx-cto.md
    profile: cto
    target: codex
    platform: all
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios

  - agent_name: UWICTO
    role_source: roles-codex/cx-cto.md
    profile: cto
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: AUCEO
  - agent_name: UWISwiftAuditor
    role_source: roles-codex/cx-code-reviewer.md
    profile: reviewer
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: UWICTO
  - agent_name: UWICryptoAuditor
    role_source: roles-codex/cx-blockchain-engineer.md
    profile: reviewer
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: UWICTO
  - agent_name: UWISecurityAuditor
    role_source: roles-codex/cx-security-auditor.md
    profile: reviewer
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: UWICTO
  - agent_name: UWIQAEngineer
    role_source: roles-codex/cx-qa-engineer.md
    profile: qa
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: UWICTO
  - agent_name: UWIInfraEngineer
    role_source: roles-codex/cx-infra-engineer.md
    profile: implementer
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: UWICTO
  - agent_name: UWIResearchAgent
    role_source: roles-codex/cx-research-agent.md
    profile: research
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: UWICTO
  - agent_name: UWITechnicalWriter
    role_source: roles-codex/cx-technical-writer.md
    profile: writer
    target: codex
    platform: ios
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios
    reportsTo: UWICTO

  - agent_name: UWACTO
    role_source: roles-codex/cx-cto.md
    profile: cto
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: AUCEO
  - agent_name: UWAKotlinAuditor
    role_source: roles-codex/cx-code-reviewer.md
    profile: reviewer
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: UWACTO
  - agent_name: UWACryptoAuditor
    role_source: roles-codex/cx-blockchain-engineer.md
    profile: reviewer
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: UWACTO
  - agent_name: UWASecurityAuditor
    role_source: roles-codex/cx-security-auditor.md
    profile: reviewer
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: UWACTO
  - agent_name: UWAQAEngineer
    role_source: roles-codex/cx-qa-engineer.md
    profile: qa
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: UWACTO
  - agent_name: UWAInfraEngineer
    role_source: roles-codex/cx-infra-engineer.md
    profile: implementer
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: UWACTO
  - agent_name: UWAResearchAgent
    role_source: roles-codex/cx-research-agent.md
    profile: research
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: UWACTO
  - agent_name: UWATechnicalWriter
    role_source: roles-codex/cx-technical-writer.md
    profile: writer
    target: codex
    platform: android
    primary_codebase_memory_project: Users-Shared-UnstoppableAudit-repos-android-unstoppable-wallet-android
    reportsTo: UWACTO
```

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_f_uaudit_migration.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/projects/uaudit/paperclip-agent-assembly.yaml paperclips/tests/test_phase_f_uaudit_migration.py
git commit -m "feat(uaa-phase-f): rewrite uaudit manifest — strip UUIDs/paths/plugin_id, add schemaVersion+profiles+reportsTo"
```

---

## Task 4: Rename overlay placeholders (per-agent overlays + _common.md)

**Files:**
- Modify: 7 files in `paperclips/projects/uaudit/overlays/codex/`

- [ ] **Step 1: Inspect placeholders**

```bash
grep -E "\{\{[^}]+\}\}" paperclips/projects/uaudit/overlays/codex/*.md
```

- [ ] **Step 2: Mechanical rename**

```bash
for f in paperclips/projects/uaudit/overlays/codex/*.md; do
  sed -i.bak \
    -e 's|{{project.company_id}}|{{bindings.company_id}}|g' \
    -e 's|{{report_delivery.telegram_plugin_id}}|{{plugins.telegram.plugin_id}}|g' \
    -e 's|{{paths.production_checkout}}|{{paths.production_checkout}}|g' \
    "$f"
  rm "${f}.bak"
done
```

- [ ] **Step 3: Verify build doesn't error on unresolved placeholders**

```bash
./paperclips/build.sh --project uaudit --target codex
# Builder will fail with "unresolved placeholder" if any rename was missed.
```

- [ ] **Step 4: Test verification**

```python
def test_uaudit_overlays_render_without_unresolved():
    import re, subprocess
    subprocess.run(["./paperclips/build.sh", "--project", "uaudit", "--target", "codex"],
                   cwd=REPO, check=True, capture_output=True)
    for p in (REPO / "paperclips" / "dist" / "uaudit" / "codex").glob("*.md"):
        text = p.read_text()
        unresolved = re.findall(r"\{\{[^}]+\}\}", text)
        assert not unresolved, f"{p.name}: unresolved {unresolved}"
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/projects/uaudit/overlays/
git commit -m "feat(uaa-phase-f): rename uaudit overlay placeholders → {{bindings.X}}/{{plugins.X}}"
```

---

## Task 5: Re-render + verify size + profile boundaries

- [ ] **Step 1: Build**

```bash
./paperclips/build.sh --project uaudit --target codex
wc -l paperclips/dist/uaudit/codex/*.md
```

Expected (per spec §2.3, with universal-inlined v1 + craft files post Phase A):
- AUCEO.md (cto): ~425
- UWICTO/UWACTO.md (cto): ~425
- UWISwiftAuditor/UWAKotlinAuditor.md (reviewer): ~345
- UWICryptoAuditor/UWACryptoAuditor.md (reviewer): ~345
- UWISecurityAuditor/UWASecurityAuditor.md (reviewer): ~345
- UWIQAEngineer/UWAQAEngineer.md (qa): ~405
- UWIInfraEngineer/UWAInfraEngineer.md (implementer): ~375
- UWIResearchAgent/UWAResearchAgent.md (research): ~210
- UWITechnicalWriter/UWATechnicalWriter.md (writer): ~195

Compare with pre-migration baseline (`paperclips/tests/baseline/phase_f/uaudit-dist-pre`):

```bash
for f in paperclips/dist/uaudit/codex/*.md; do
  name=$(basename "$f")
  pre=$(wc -l < "paperclips/tests/baseline/phase_f/uaudit-dist-pre/codex/$name" 2>/dev/null || echo "?")
  post=$(wc -l < "$f")
  printf "%-25s pre=%-4s post=%-4s\n" "$name" "$pre" "$post"
done
```

Expected: post < pre by 30-50%.

- [ ] **Step 2: Profile boundary tests**

```python
def test_uaudit_profile_boundaries():
    """Per spec §3.2: each profile only includes its capability fragments."""
    cases = [
        ("UWITechnicalWriter.md", "writer", ["Phase 1.1", "release-cut", "merge-readiness", "git/commit-and-push"]),
        ("UWIResearchAgent.md", "research", ["Phase 1.1", "release-cut", "git/commit-and-push"]),
        ("UWIInfraEngineer.md", "implementer", ["Phase 1.1", "release-cut"]),  # implementer doesn't have these
        ("UWISwiftAuditor.md", "reviewer", ["Phase 1.1", "release-cut", "git/commit-and-push"]),  # reviewer doesn't have phase or push
        ("UWICTO.md", "cto", []),  # cto has all
    ]
    for name, profile, forbidden in cases:
        p = REPO / "paperclips" / "dist" / "uaudit" / "codex" / name
        if not p.is_file():
            continue
        text = p.read_text()
        for forbidden_str in forbidden:
            assert forbidden_str not in text, f"{name} ({profile}) leaked: {forbidden_str}"
```

- [ ] **Step 3: PASS + commit**

```bash
python3 -m pytest paperclips/tests/test_phase_f_uaudit_migration.py -v
git add paperclips/tests/test_phase_f_uaudit_migration.py
git commit -m "test(uaa-phase-f): uaudit profile boundaries verified per spec §3.2"
```

---

## Task 6: Pause uaudit agents → canary deploy → smoke

- [ ] **Step 1: Pause all 17 agents in paperclip UI**

OR via API loop:
```bash
for name in $(yq -r '.agents | keys | .[]' ~/.paperclip/projects/uaudit/bindings.yaml); do
  uuid=$(yq -r ".agents.${name}" ~/.paperclip/projects/uaudit/bindings.yaml)
  curl -fsS -X PATCH "${PAPERCLIP_API_URL}/api/agents/${uuid}" \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"paused": true}' >/dev/null
  echo "paused $name"
done
```

- [ ] **Step 2: Verify no runs in flight**

```bash
PAPERCLIP_API_KEY=<...> curl -fsS "${PAPERCLIP_API_URL}/api/companies/${UAUDIT_COMPANY_ID}/runs?status=running" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" | jq length
```

Expected: `0`.

- [ ] **Step 3: Reconfigure telegram plugin via bootstrap**

The new `bootstrap-project.sh` will call `paperclip_plugin_set_config` (per spec §8.4) with merged config. Snapshot current first:

```bash
plugin_id=$(yq -r '.telegram.plugin_id' ~/.paperclip/projects/uaudit/plugins.yaml)
curl -fsS "${PAPERCLIP_API_URL}/api/plugins/${plugin_id}" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
  > paperclips/tests/baseline/phase_f/telegram-plugin-config-pre.json
```

- [ ] **Step 4: Bootstrap with reuse-bindings + canary**

```bash
./paperclips/scripts/bootstrap-project.sh uaudit \
  --reuse-bindings ~/.paperclip/projects/uaudit/bindings.yaml \
  --canary
```

Stage 1 canary (per Phase C §8.6): writer (UWITechnicalWriter) gets first deploy + smoke.
Stage 2 canary: AUCEO (cto) deploy + smoke.
Stage 3 fan-out: remaining 15 agents.

If any stage fails: `./paperclips/scripts/rollback.sh <journal-id>`.

- [ ] **Step 5: Deploy codex subagents .toml files**

```bash
mkdir -p ~/.codex/projects/uaudit/agents
cp paperclips/projects/uaudit/codex-agents/*.toml ~/.codex/projects/uaudit/agents/
ls ~/.codex/projects/uaudit/agents/
```

Expected: 5 .toml files.

- [ ] **Step 6: Run full smoke**

```bash
./paperclips/scripts/smoke-test.sh uaudit
```

Expected: 7/7 PASS including stage 6 (telegram delivery).

- [ ] **Step 7: Unpause agents**

```bash
for name in $(yq -r '.agents | keys | .[]' ~/.paperclip/projects/uaudit/bindings.yaml); do
  uuid=$(yq -r ".agents.${name}" ~/.paperclip/projects/uaudit/bindings.yaml)
  curl -fsS -X PATCH "${PAPERCLIP_API_URL}/api/agents/${uuid}" \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" -H "Content-Type: application/json" \
    -d '{"paused": false}' >/dev/null
done
```

- [ ] **Step 8: 1h watchdog observation**

```bash
tail -f ~/.paperclip/watchdog.log | jq -c 'select(.event | IN("wake_failed","handoff_alert_posted")) | select(.company == "<UAUDIT_COMPANY_ID>")'
```

Expected: zero events.

---

## Task 7: Phase F acceptance + spec changelog

- [ ] **Step 1: Acceptance test additions**

```python
def test_codex_subagents_deployed():
    import os
    p = Path(os.path.expanduser("~/.codex/projects/uaudit/agents"))
    if not p.is_dir():
        pytest.skip("not yet deployed")
    tomls = sorted(f.name for f in p.glob("*.toml"))
    assert "uaudit-bug-hunter.toml" in tomls
    assert "uaudit-security-auditor.toml" in tomls
    assert "uaudit-blockchain-auditor.toml" in tomls
    assert "uaudit-swift-audit-specialist.toml" in tomls
    assert "uaudit-kotlin-audit-specialist.toml" in tomls
```

- [ ] **Step 2: Run all Phase F tests**

```bash
python3 -m pytest paperclips/tests/test_phase_f_*.py -v
```

- [ ] **Step 3: Update spec changelog**

```markdown
**Phase F complete (YYYY-MM-DD):**
- uaudit manifest stripped (17 agents, schemaVersion 2, profiles + reportsTo + platform opaque-passthrough).
- Host-local: bindings.yaml (17 UUIDs), paths.yaml, plugins.yaml (telegram).
- Overlay placeholders renamed (7 files).
- 5 codex subagent .toml files deployed to ~/.codex/projects/uaudit/agents/.
- 2-stage canary deploy + 7-stage smoke green.
- Watchdog: 1h post-deploy zero wake_failed for uaudit company.
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md paperclips/tests/test_phase_f_uaudit_migration.py
git commit -m "docs+test(uaa-phase-f): uaudit migration complete"
```

---

## Phase F acceptance gate (before Phase G)

- [ ] All 17 uaudit agents deployed with new AGENTS.md.
- [ ] All Phase A-F tests green.
- [ ] `validate-manifest.sh uaudit` passes.
- [ ] 5 codex subagent .toml deployed in `~/.codex/projects/uaudit/agents/`.
- [ ] Telegram plugin still delivers (smoke test stage 6).
- [ ] No wake_failed for uaudit in 1h post-deploy.
- [ ] At least one uaudit issue completed end-to-end after migration.
- [ ] `legacy_output_paths: false` confirmed in manifest.
