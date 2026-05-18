# UAA Phase E — Trading Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Spec:** `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §10.2
**Owner:** `team` (per spec §14.2 — mechanical, low blast radius; trading break ≠ gimle break)
**Estimate:** 1 day
**Prereq:** Phases A + B + C + D complete
**Blocks:** Phase F (uaudit migration uses same pattern after E proves it)

**Goal:** Migrate the trading project (5 agents: 1 claude CTO + 4 codex {CEO, CR, PE, QA}) from inline UUIDs/paths in manifest to the new schema (host-local bindings + path-free committed manifest). 2-stage canary deploy. Smoke-test green.

**Architecture:** trading is the simplest project (already partly on new schema — `legacy_output_paths: false`, agents declared inline). Migration steps: extract UUIDs/paths from current manifest → host-local files → strip from manifest → re-render via new builder pipeline → canary deploy → smoke. Overlay placeholder rename mechanical (sed).

**Tech Stack:**
- All Phase A-D infrastructure (builder, scripts, profile system, dual-read).
- Real paperclip API on operator's machine.

**Risk profile:** LOW. Trading is a 5-agent project with no deeply-running session state at the moment of migration (per operator memory: TRD bootstrap was 2026-05-12, still early). If migration fails, trading agents pause; gimle/uaudit unaffected.

---

## File Structure

### Modified

```
paperclips/projects/trading/paperclip-agent-assembly.yaml   # strip UUIDs + abs paths; add schemaVersion: 2
paperclips/projects/trading/overlays/{claude,codex}/_common.md  # rename {{project.X}} → {{bindings.X}} where X is host-local
```

### Created (host-local, gitignored)

```
~/.paperclip/projects/trading/bindings.yaml   # 5 agent UUIDs extracted from manifest
~/.paperclip/projects/trading/paths.yaml      # /Users/Shared/Trading/* paths
```

### Created in repo (test artifacts)

```
paperclips/tests/test_phase_e_trading_migration.py
paperclips/tests/fixtures/phase_e/expected_trading_bindings.yaml  # snapshot
```

---

## Task 1: Backup current trading state + journal pre-migration

**Files:**
- (operations only, no committed files)

- [ ] **Step 1: Verify Phase D acceptance complete**

```bash
python3 -m pytest paperclips/tests/test_phase_d_acceptance.py -v
```
Expected: 0 FAIL.

- [ ] **Step 2: Snapshot current manifest + UUID list**

```bash
mkdir -p paperclips/tests/baseline/phase_e
cp paperclips/projects/trading/paperclip-agent-assembly.yaml \
   paperclips/tests/baseline/phase_e/trading-manifest-pre.yaml

# Capture current dist outputs for trading
./paperclips/build.sh --project trading --target claude
./paperclips/build.sh --project trading --target codex
cp -r paperclips/dist/trading paperclips/tests/baseline/phase_e/trading-dist-pre
```

- [ ] **Step 3: Open journal entry**

```bash
source paperclips/scripts/lib/_common.sh
source paperclips/scripts/lib/_journal.sh
journal=$(journal_open "trading-migration")
echo "journal: $journal"
# (manual; later steps will record snapshots into it)
```

- [ ] **Step 4: Inspect current trading manifest**

```bash
cat paperclips/projects/trading/paperclip-agent-assembly.yaml | head -50
```

Confirm 5 agents (CEO, CTO, CodeReviewer, PythonEngineer, QAEngineer); 1 claude (CTO), 4 codex.

- [ ] **Step 5: No commit yet — pre-migration snapshot only**

---

## Task 2: Extract UUIDs + paths into host-local files

**Files:**
- Create: `~/.paperclip/projects/trading/bindings.yaml` (host-local)
- Create: `~/.paperclip/projects/trading/paths.yaml` (host-local)

- [ ] **Step 1: Failing test (verifies bindings.yaml shape)**

```python
# paperclips/tests/test_phase_e_trading_migration.py
"""Phase E: trading migration."""
import os
from pathlib import Path
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HOST = Path(os.path.expanduser("~/.paperclip/projects/trading"))


def test_trading_bindings_yaml_exists():
    p = HOST / "bindings.yaml"
    if not p.is_file():
        pytest.skip("Host-local trading bindings not yet migrated; this test runs post-Task 2.")
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2
    assert data["company_id"]
    assert "CEO" in data["agents"]
    assert "CTO" in data["agents"]
    assert "CodeReviewer" in data["agents"]
    assert "PythonEngineer" in data["agents"]
    assert "QAEngineer" in data["agents"]
    # All UUIDs must be valid hex format
    import re
    UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    for name, uuid in data["agents"].items():
        assert UUID_RE.match(uuid), f"{name}: invalid UUID format: {uuid!r}"


def test_trading_paths_yaml_exists():
    p = HOST / "paths.yaml"
    if not p.is_file():
        pytest.skip("Host-local trading paths not yet migrated; this test runs post-Task 2.")
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2
    for k in ["project_root", "team_workspace_root", "operator_memory_dir"]:
        assert k in data, f"missing key: {k}"
```

- [ ] **Step 2: Verify SKIP (host files don't exist yet)**

```bash
python3 -m pytest paperclips/tests/test_phase_e_trading_migration.py -v
```

- [ ] **Step 3: Run migrate-bindings.sh in dry-run first**

```bash
./paperclips/scripts/migrate-bindings.sh trading --dry-run
```

Inspect output. If looks correct (5 agent UUIDs from inline manifest), proceed.

- [ ] **Step 4: Run for real**

```bash
./paperclips/scripts/migrate-bindings.sh trading
cat ~/.paperclip/projects/trading/bindings.yaml
```

- [ ] **Step 5: Create paths.yaml from current manifest values**

Read current manifest:
```bash
yq '.paths' paperclips/projects/trading/paperclip-agent-assembly.yaml
```

Write `~/.paperclip/projects/trading/paths.yaml`:
```bash
cat > ~/.paperclip/projects/trading/paths.yaml <<EOF
schemaVersion: 2
project_root: /Users/Shared/Trading
primary_repo_root: /Users/Shared/Trading/repo
production_checkout: /Users/Shared/Trading
team_workspace_root: /Users/Shared/Trading/runs
operator_memory_dir: ~/.claude/projects/-Users-Shared-Trading/memory
overlay_root: paperclips/projects/trading/overlays
EOF
```

- [ ] **Step 6: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_e_trading_migration.py -v
```

Expected: 2 PASS.

- [ ] **Step 7: Commit (test file only — host configs are gitignored)**

```bash
git add paperclips/tests/test_phase_e_trading_migration.py
git commit -m "test(uaa-phase-e): bindings.yaml + paths.yaml shape verified for trading host-local"
```

---

## Task 3: Strip UUIDs + abs paths from committed manifest

**Files:**
- Modify: `paperclips/projects/trading/paperclip-agent-assembly.yaml`

- [ ] **Step 1: Failing test**

Append to `paperclips/tests/test_phase_e_trading_migration.py`:
```python
def test_trading_manifest_passes_validator():
    """Post-migration, manifest must pass validate-manifest.sh."""
    from paperclips.scripts.validate_manifest import validate_manifest
    p = REPO / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml"
    validate_manifest(p)


def test_trading_manifest_has_schemaVersion_2():
    import yaml
    p = REPO / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml"
    data = yaml.safe_load(p.read_text())
    assert data["schemaVersion"] == 2


def test_trading_manifest_no_inline_uuids():
    p = REPO / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml"
    text = p.read_text()
    import re
    matches = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text, re.I)
    # Allow {{template.references}} but no literal UUIDs
    assert not matches, f"inline UUIDs in manifest: {matches}"


def test_trading_manifest_no_abs_paths():
    p = REPO / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml"
    text = p.read_text()
    import re
    matches = re.findall(r"/Users/Shared|/home/|/Users/me", text)
    assert not matches, f"abs paths in manifest: {matches}"


def test_trading_manifest_has_5_agents():
    import yaml
    p = REPO / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml"
    data = yaml.safe_load(p.read_text())
    assert len(data["agents"]) == 5
    names = {a["agent_name"] for a in data["agents"]}
    assert names == {"CEO", "CTO", "CodeReviewer", "PythonEngineer", "QAEngineer"}


def test_trading_manifest_uses_profile_field():
    """Each agent must declare profile (per UAA §6.1)."""
    import yaml
    p = REPO / "paperclips" / "projects" / "trading" / "paperclip-agent-assembly.yaml"
    data = yaml.safe_load(p.read_text())
    for a in data["agents"]:
        assert "profile" in a, f"agent {a['agent_name']} missing profile"
        assert a["profile"] in {"custom", "minimal", "research", "writer", "implementer", "qa", "reviewer", "cto"}
```

- [ ] **Step 2: Verify FAIL (manifest still has UUIDs/paths/no schemaVersion)**

```bash
python3 -m pytest paperclips/tests/test_phase_e_trading_migration.py -v
```

- [ ] **Step 3: Rewrite trading manifest**

Read current `paperclips/projects/trading/paperclip-agent-assembly.yaml`, then replace with:

```yaml
schemaVersion: 2

project:
  key: trading
  display_name: Trading
  system_name: Trading
  issue_prefix: TRD
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans

domain:
  wallet_target_short: Trading
  wallet_target_name: Trading Platform
  wallet_target_slug: trading-agents

mcp:
  service_name: trading
  package_name: trading_agents
  tool_namespace: trading
  base_required:
    - codebase-memory
    - context7
    - serena
    - github
    - sequential-thinking
  codebase_memory_projects:
    primary: trading-agents

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
  - agent_name: CEO
    role_source: roles-codex/cx-cto.md
    profile: cto
    target: codex
  - agent_name: CTO
    role_source: roles/cto.md
    profile: cto
    target: claude
    reportsTo: CEO
  - agent_name: CodeReviewer
    role_source: roles-codex/cx-code-reviewer.md
    profile: reviewer
    target: codex
    reportsTo: CTO
  - agent_name: PythonEngineer
    role_source: roles-codex/cx-python-engineer.md
    profile: implementer
    target: codex
    reportsTo: CTO
  - agent_name: QAEngineer
    role_source: roles-codex/cx-qa-engineer.md
    profile: qa
    target: codex
    reportsTo: CTO
```

- [ ] **Step 4: Verify PASS (5 new tests + 2 from Task 2)**

```bash
python3 -m pytest paperclips/tests/test_phase_e_trading_migration.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/projects/trading/paperclip-agent-assembly.yaml paperclips/tests/test_phase_e_trading_migration.py
git commit -m "feat(uaa-phase-e): rewrite trading manifest — strip UUIDs/paths, add schemaVersion+profiles+reportsTo"
```

---

## Task 4: Rename overlay placeholders

**Files:**
- Modify: `paperclips/projects/trading/overlays/claude/_common.md`
- Modify: `paperclips/projects/trading/overlays/codex/_common.md`

- [ ] **Step 1: Inspect current overlay placeholders**

```bash
grep -E "\{\{[^}]+\}\}" paperclips/projects/trading/overlays/claude/_common.md
grep -E "\{\{[^}]+\}\}" paperclips/projects/trading/overlays/codex/_common.md
```

Expected: references to `{{project.company_id}}` (host-local in new schema), `{{paths.production_checkout}}` (also host-local), etc.

- [ ] **Step 2: Failing test**

```python
def test_trading_overlays_no_forbidden_placeholders():
    """Overlays must reference {{bindings.X}} or {{paths.X}}, not old {{project.company_id}}."""
    for p in [
        REPO / "paperclips" / "projects" / "trading" / "overlays" / "claude" / "_common.md",
        REPO / "paperclips" / "projects" / "trading" / "overlays" / "codex" / "_common.md",
    ]:
        text = p.read_text()
        assert "{{project.company_id}}" not in text, f"{p}: still uses {{{{project.company_id}}}} (move to {{{{bindings.company_id}}}})"
        assert "{{report_delivery.telegram_plugin_id}}" not in text


def test_trading_overlays_render_via_template_resolver():
    """Build trading and verify overlay placeholders resolved."""
    import subprocess
    subprocess.run(["./paperclips/build.sh", "--project", "trading", "--target", "codex"],
                   cwd=REPO, check=True, capture_output=True)
    rendered = (REPO / "paperclips" / "dist" / "trading" / "codex" / "CTO.md").read_text()
    # No unresolved {{...}} should remain
    import re
    unresolved = re.findall(r"\{\{[^}]+\}\}", rendered)
    assert not unresolved, f"unresolved placeholders in trading codex CTO: {unresolved}"
```

- [ ] **Step 3: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_e_trading_migration.py -v -k overlay
```

- [ ] **Step 4: Mechanical sed rename**

```bash
for f in paperclips/projects/trading/overlays/{claude,codex}/_common.md; do
  sed -i.bak \
    -e 's|{{project.company_id}}|{{bindings.company_id}}|g' \
    -e 's|{{report_delivery.telegram_plugin_id}}|{{plugins.telegram.plugin_id}}|g' \
    "$f"
  rm "${f}.bak"
done
```

- [ ] **Step 5: Inspect diffs**

```bash
git diff paperclips/projects/trading/overlays/
```

- [ ] **Step 6: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_e_trading_migration.py -v -k overlay
```

- [ ] **Step 7: Commit**

```bash
git add paperclips/projects/trading/overlays/
git commit -m "feat(uaa-phase-e): rename trading overlay placeholders → {{bindings.X}} / {{plugins.X}}"
```

---

## Task 5: Re-render trading

- [ ] **Step 1: Build both targets**

```bash
./paperclips/build.sh --project trading --target claude
./paperclips/build.sh --project trading --target codex
```

Expected: zero errors. Build emits dedup-applied messages from compose pipeline.

- [ ] **Step 2: Verify rendered output sanity**

```bash
wc -l paperclips/dist/trading/{claude,codex}/*.md
```

Expected line counts (per spec §3.1, with universal-inlined v1):
- CEO.md: ~425 (cto profile + craft)
- CTO.md (claude): ~425
- CodeReviewer.md: ~345
- PythonEngineer.md: ~375
- QAEngineer.md: ~405

If significantly larger or smaller, investigate (likely unresolved placeholder or wrong profile).

- [ ] **Step 3: Compare with pre-migration baseline**

```bash
diff -r paperclips/tests/baseline/phase_e/trading-dist-pre paperclips/dist/trading/ | head -50
```

Expected differences:
- Sizes shrink ~30-50% (per spec §2.3 predictions).
- Universal block now appears in each agent (was previously inlined via legacy fragments — same content, different source).
- Phase-orchestration content present only in CEO/CTO files (not in PE/QA — correct cto-profile-only).

- [ ] **Step 4: Failing assertion → PASS**

Append to `paperclips/tests/test_phase_e_trading_migration.py`:
```python
def test_trading_rebuilt_files_size_in_range():
    """Per spec §2.3: implementer ~375 lines; cto ~425; reviewer ~345; qa ~405."""
    sizes = {p.name: p.read_text().count("\n") for p in (REPO / "paperclips" / "dist" / "trading" / "codex").glob("*.md")}
    # Allow ±50 lines tolerance
    expected = {
        "CEO.md": (375, 475),
        "PythonEngineer.md": (325, 425),
        "QAEngineer.md": (355, 455),
        "CodeReviewer.md": (295, 395),
    }
    for name, (lo, hi) in expected.items():
        if name not in sizes:
            continue  # build hasn't run yet
        assert lo <= sizes[name] <= hi, f"{name}: {sizes[name]} not in [{lo},{hi}]"


def test_trading_pe_does_not_have_phase_orchestration():
    """PE is implementer; should NOT have CTO phase-orchestration content."""
    p = REPO / "paperclips" / "dist" / "trading" / "codex" / "PythonEngineer.md"
    if not p.is_file():
        return
    text = p.read_text()
    assert "Phase 1.1" not in text, "PE has phase-orchestration leak"
    assert "Phase 4.2" not in text


def test_trading_cto_has_phase_orchestration():
    p = REPO / "paperclips" / "dist" / "trading" / "codex" / "CEO.md"  # CEO uses cto profile
    if not p.is_file():
        return
    text = p.read_text()
    assert "Phase 1.1" in text, "CEO/CTO missing phase-orchestration"
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest paperclips/tests/test_phase_e_trading_migration.py -v
```

- [ ] **Step 6: Commit (only test additions; dist is gitignored per Phase B)**

```bash
git add paperclips/tests/test_phase_e_trading_migration.py
git commit -m "test(uaa-phase-e): trading rebuild profile boundaries verified"
```

---

## Task 6: Pause trading agents (manual)

This step is operator action — no scripting.

- [ ] **Step 1: Open paperclip UI for trading company**

In paperclip UI, navigate to Trading company → Agents.

- [ ] **Step 2: Pause each of the 5 agents**

For each: CEO, CTO, CodeReviewer, PythonEngineer, QAEngineer → click "Pause" or PATCH `agent.paused=true` via API.

- [ ] **Step 3: Verify no in-flight runs**

```bash
PAPERCLIP_API_KEY=<...> curl -fsS \
  "${PAPERCLIP_API_URL}/api/companies/${TRADING_COMPANY_ID}/runs?status=running" \
  -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" | jq length
```

Expected: `0`. If non-zero, wait for runs to finish or abort manually.

- [ ] **Step 4: Brief stand-by (5 min)**

To allow any in-flight wake events to drain.

---

## Task 7: Canary deploy (2-stage)

- [ ] **Step 1: Run bootstrap with --reuse-bindings + --canary**

```bash
./paperclips/scripts/bootstrap-project.sh trading \
  --reuse-bindings ~/.paperclip/projects/trading/bindings.yaml \
  --canary
```

Expected sequence (per spec §8.6):
1. Stage 1 canary: deploy to QAEngineer (first non-cto in topo order). Run `smoke-test.sh trading --canary-stage=1`. Stage 1 must pass before continuing.
2. Stage 2 canary: deploy to CEO (first cto). Run `smoke-test.sh trading --canary-stage=2`.
3. Fan-out: deploy CTO, CodeReviewer, PythonEngineer.

- [ ] **Step 2: If any stage fails, rollback**

```bash
journal_id=$(ls -t ~/.paperclip/journal/*-bootstrap-trading.json | head -1)
./paperclips/scripts/rollback.sh "$(basename "${journal_id%.json}")"
```

Investigate failure, fix, retry from Step 1.

- [ ] **Step 3: After successful deploy, verify all 5 deployed**

```bash
for agent in CEO CTO CodeReviewer PythonEngineer QAEngineer; do
  uuid=$(yq -r ".agents.${agent}" ~/.paperclip/projects/trading/bindings.yaml)
  echo "=== $agent ($uuid) ==="
  curl -fsS "${PAPERCLIP_API_URL}/api/agents/${uuid}/configuration" \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" | jq '.adapterConfig.instructionsFilePath, .runtimeConfig.heartbeat.enabled'
done
```

Expected per agent: `"AGENTS.md"` and `false`.

---

## Task 8: Run full smoke test

- [ ] **Step 1: Full 7-stage smoke**

```bash
./paperclips/scripts/smoke-test.sh trading
```

Expected: all 7 stages pass.

- [ ] **Step 2: Unpause agents**

In paperclip UI: unpause each of CEO/CTO/CR/PE/QA. OR via API:
```bash
for agent in CEO CTO CodeReviewer PythonEngineer QAEngineer; do
  uuid=$(yq -r ".agents.${agent}" ~/.paperclip/projects/trading/bindings.yaml)
  curl -fsS -X PATCH "${PAPERCLIP_API_URL}/api/agents/${uuid}" \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"paused": false}'
done
```

- [ ] **Step 3: Watch watchdog log for 1h**

```bash
tail -f ~/.paperclip/watchdog.log | jq -c 'select(.event | IN("wake_failed", "handoff_alert_posted"))'
```

Expected: zero events for trading company in this hour.

---

## Task 9: Phase E acceptance + commit migration outcome

- [ ] **Step 1: Final acceptance**

```python
# Append to paperclips/tests/test_phase_e_trading_migration.py:
def test_trading_journal_exists():
    """A journal entry must exist documenting the migration."""
    import os
    journal_dir = Path(os.path.expanduser("~/.paperclip/journal"))
    if not journal_dir.is_dir():
        return
    journals = sorted(journal_dir.glob("*-bootstrap-trading.json"))
    assert journals, "no trading bootstrap journal found"
```

- [ ] **Step 2: Run all Phase E tests**

```bash
python3 -m pytest paperclips/tests/test_phase_e_*.py -v
```

- [ ] **Step 3: Update spec changelog**

```markdown
**Phase E complete (YYYY-MM-DD):**
- trading manifest stripped of UUIDs/paths; schemaVersion: 2; profile + reportsTo per agent.
- bindings.yaml + paths.yaml in ~/.paperclip/projects/trading/ (host-local).
- Overlay placeholders renamed (sed): {{project.company_id}} → {{bindings.company_id}}.
- 2-stage canary deploy + 7-stage smoke green.
- 5 agents (CEO, CTO, CR, PE, QA) on new schema; legacy paperclips/codex-agent-ids.env still in repo (gimle still uses it; cleanup gated).
- Watchdog observation: 1h post-deploy zero wake_failed / handoff_alert events for trading.
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md \
        paperclips/tests/test_phase_e_trading_migration.py
git commit -m "docs+test(uaa-phase-e): trading migration complete; spec changelog updated"
```

---

## Phase E acceptance gate (before Phase F)

- [ ] All 5 trading agents deployed with new AGENTS.md (verified via `GET /api/agents/<uuid>/configuration`).
- [ ] All Phase A/B/C/D/E tests green.
- [ ] `validate-manifest.sh trading` passes (no UUIDs, no abs paths).
- [ ] `~/.paperclip/projects/trading/bindings.yaml` + `paths.yaml` exist with valid content.
- [ ] Smoke test full pass: `./paperclips/scripts/smoke-test.sh trading`.
- [ ] Watchdog log shows zero wake_failed for trading in 1h post-deploy observation window.
- [ ] At least one trading issue successfully completed end-to-end after migration (proves agents alive).
- [ ] Operator signoff documented (in commit message or BUGS.md).
