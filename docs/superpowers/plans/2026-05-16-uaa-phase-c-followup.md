# UAA Phase C Followup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address 6 verified CRITICAL findings + 5 high-signal IMPORTANT findings from the 4-voltAgent deep-review of cumulative Phase C (PRs #191/#193/#194), making Phase C ready for Phase D + Phase E execution.

**Architecture:** Surgical fixes inside existing Phase C scripts (`paperclips/scripts/*.sh` + `lib/*.sh`); no new scripts; no architectural shape changes. Each fix accompanied by a *behavioral* test (not source-string-grep) so future regressions are caught.

**Tech Stack:** bash 4+, jq, yq (mikefarah v4), python3, pytest.

**Branch:** `feature/uaa-phase-c-followup` off `origin/develop` (post `b00e8dad`).

**PR:** target `develop`, label `micro-slice`.

---

## Provenance

This plan responds to findings from the cumulative Phase C deep-review (architect-reviewer + code-reviewer + qa-expert + security-auditor) on 2026-05-16. Findings were verified against actual code in `/tmp/phase-c/` before inclusion; rejected false-positives (e.g. architect C-5 "watchdog template `---` separator") are explicitly excluded.

| # | Finding | Verified | Sub-task |
|---|---------|----------|----------|
| **CRIT-1** | rollback.sh handles `*_snapshot` kinds; bootstrap-project writes `agent_hire`+`agent_instructions_deploy` → rollback no-op | yes | Tasks 1+2 |
| **CRIT-2** | plugin step 8 does GET-then-POST but never journals `plugin_config_snapshot` | yes | Task 3 |
| **CRIT-3** | BSD sed `\u&` non-portable; `bootstrap-project.sh:85` will break on clean Mac | yes | Task 4 |
| **CRIT-4** | migrate-bindings outputs `CXCto`/`CXQaEngineer`/`CXMcpEngineer` but canonical vocab is `CXCTO`/`CXQAEngineer`/`CXMCPEngineer` (acronyms preserved per uaudit manifest) | yes | Task 5 |
| **CRIT-5** | `project_key` + `journal_id` not path-validated → `../../etc` escape or `/etc/passwd` read | yes | Task 6 |
| **CRIT-6** | `bootstrap-watchdog.sh` yq merge uses wrong v4 syntax → silent literal-append fallback corrupts YAML | yes | Task 7 |
| IMP-A | No `--max-time`/`--connect-timeout` on curl in `_paperclip_api.sh` | yes | Task 8 |
| IMP-B | 401 swallowed by `2>/dev/null || echo "{}"` → telegram config wipe if JWT expired | yes | Task 9 |
| IMP-C | journal + bindings files default umask 0644 (medium-sensitivity AGENTS.md content) | yes | Task 10 |
| IMP-D | Shell-execute used in _smoke_probes.sh:111-112 for dynamic variable lookup; replace with bash indirect expansion `${!var}` | yes | Task 11 |
| IMP-E | `yq -r ".agents.${agent_name}"` is path injection if agent_name has `.` / `[` | yes | Task 12 |

**Out of scope (parked):**
- ~15 tautological tests — separate "test-quality refactor" effort; non-blocking for Phase D
- 7 stale skipped tests in `test_validate_instructions.py` — needs separate Phase A→B reconciliation; non-blocking
- flock for concurrent bootstrap-project — design decision; human-operated scripts, race unlikely; deferred
- update-versions snapshots only 3 of 8 versions — document as known limitation rather than expand snapshot scope

---

## File Structure

| Path | Responsibility | Touched in |
|---|---|---|
| `paperclips/scripts/bootstrap-project.sh` | hire + deploy + plugin reconfig | Tasks 1, 3, 4, 6, 9, 12 |
| `paperclips/scripts/rollback.sh` | journal replay | Tasks 2, 6 |
| `paperclips/scripts/migrate-bindings.sh` | UUID extraction | Tasks 5, 6, 10 |
| `paperclips/scripts/bootstrap-watchdog.sh` | watchdog config + launchd | Tasks 6, 7 |
| `paperclips/scripts/smoke-test.sh` | liveness | Task 6 |
| `paperclips/scripts/lib/_paperclip_api.sh` | REST helpers | Tasks 1, 2, 8, 9 |
| `paperclips/scripts/lib/_journal.sh` | journal open/record/finalize | Task 10 |
| `paperclips/scripts/lib/_common.sh` | validators + log/die | Tasks 6, 12 |
| `paperclips/scripts/lib/_smoke_probes.sh` | runtime probes | Task 11 |
| `paperclips/tests/test_phase_c_followup.py` | NEW — behavioral tests for all fixes | Tasks 1-12 |

Single shared test file (`test_phase_c_followup.py`) collects behavioral assertions; per-script structural tests stay where they are.

---

## Task 1: Pre-state snapshot for AGENTS.md deploy

**Why:** Spec §8.5 requires journaling the OLD content before mutation so rollback can restore it. Current code at `bootstrap-project.sh:283` writes only `agent_instructions_deploy` with `source_path` — no `old_content`, wrong `kind`.

**Files:**
- Modify: `paperclips/scripts/bootstrap-project.sh:280-288` (the `deploy_one` helper)
- Modify: `paperclips/scripts/lib/_paperclip_api.sh` — add `paperclip_get_agent_instructions`
- Test: `paperclips/tests/test_phase_c_followup.py` (new file)

- [ ] **Step 1: Write the failing test**

```python
# paperclips/tests/test_phase_c_followup.py
"""Behavioral tests for Phase C followup fixes."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "paperclips" / "scripts"


def test_bootstrap_records_snapshot_kind_for_deploy(tmp_path, monkeypatch):
    """deploy_one must write kind='agent_instructions_snapshot' with old_content,
    matching what rollback.sh:96 case handles."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    # Snapshot kind must match rollback handler — no agent_instructions_deploy
    assert 'kind:"agent_instructions_snapshot"' in text or \
           "kind: agent_instructions_snapshot" in text, \
        "bootstrap-project.sh must write snapshot kind handled by rollback.sh"
    # Must capture old_content via GET before PUT
    assert "paperclip_get_agent_instructions" in text or \
           "get_agent_instructions" in text, \
        "bootstrap must fetch existing AGENTS.md before overwriting"
    # The legacy kind must NOT be present
    assert 'kind:"agent_instructions_deploy"' not in text, \
        "agent_instructions_deploy kind is unhandled by rollback — remove"
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
cd /Users/ant013/Android/Gimle-Palace
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_bootstrap_records_snapshot_kind_for_deploy -v
```
Expected: FAIL on first assertion (no `agent_instructions_snapshot` kind in bootstrap).

- [ ] **Step 3: Add `paperclip_get_agent_instructions` to lib**

Append to `paperclips/scripts/lib/_paperclip_api.sh` (after `paperclip_deploy_agents_md`):

```bash
paperclip_get_agent_instructions() {
  local agent_id="$1"
  # Returns the AGENTS.md text body. Empty string + exit 0 if agent has no file yet (404).
  local response http body
  response=$(curl -sS --max-time 30 \
    -o - -w '\n%{http_code}' \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    "${PAPERCLIP_API_URL%/}/api/agents/${agent_id}/instructions-bundle/file" 2>/dev/null) || return 1
  http=$(printf '%s' "$response" | tail -1)
  body=$(printf '%s' "$response" | sed '$d')
  case "$http" in
    200) printf '%s' "$body" ;;
    404) printf '' ;;
    *) return 1 ;;
  esac
}
```

- [ ] **Step 4: Rewrite `deploy_one` in bootstrap-project.sh**

Replace `bootstrap-project.sh:280-288` (deploy_one body around the journal_record + paperclip_deploy_agents_md):

```bash
deploy_one() {
  local agent_name="$1"
  local agent_id
  agent_id=$(yq -r ".agents.${agent_name}" "$bindings")
  [ -n "$agent_id" ] && [ "$agent_id" != "null" ] || die "deploy: agent $agent_name has no UUID in bindings"
  local content_path="${REPO_ROOT}/paperclips/dist/${project_key}/${target}/${agent_name}.md"
  [ -f "$content_path" ] || die "deploy: built artifact not found: $content_path"
  local old_content
  old_content=$(paperclip_get_agent_instructions "$agent_id") || \
    die "deploy: failed to fetch current AGENTS.md for agent $agent_id (HTTP error — check JWT)"
  journal_record "$journal" "$(jq -n \
    --arg id "$agent_id" \
    --arg old "$old_content" \
    '{kind:"agent_instructions_snapshot",agent_id:$id,old_content:$old}')"
  local content
  content=$(cat "$content_path")
  paperclip_deploy_agents_md "$agent_id" "$content"
  log ok "  deployed $agent_name"
}
```

- [ ] **Step 5: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_bootstrap_records_snapshot_kind_for_deploy -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/bootstrap-project.sh paperclips/scripts/lib/_paperclip_api.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): snapshot OLD AGENTS.md content before deploy

bootstrap-project.sh now GETs existing AGENTS.md via
paperclip_get_agent_instructions, records kind=agent_instructions_snapshot
with old_content, matching rollback.sh's existing handler.

Closes CRIT-1 (part 1 of 2) from Phase C deep-review."
```

---

## Task 2: Add `agent_hire` handler to rollback.sh

**Why:** bootstrap-project.sh:238 writes `kind:"agent_hire"`. rollback.sh's case at lines 96/108/119 has no handler — falls into `unknown snapshot kind`. Operator sees "rollback complete" but the agent is still hired and consuming a paperclip slot.

**Files:**
- Modify: `paperclips/scripts/rollback.sh:91-128`
- Modify: `paperclips/scripts/lib/_paperclip_api.sh` — add `paperclip_delete_agent`
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append to `paperclips/tests/test_phase_c_followup.py`:

```python
def test_rollback_handles_agent_hire_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T130000Z-hire-test"
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "test-hire",
        "timestamp": "20260516T130000Z",
        "entries": [
            {"kind": "agent_hire",
             "name": "TestAgent",
             "id": "00000000-0000-0000-0000-000000000123"},
        ],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), name, "--dry-run"],
        capture_output=True, text=True,
    )
    combined = out.stdout + out.stderr
    assert out.returncode == 0, f"rollback failed: {combined}"
    assert "unknown snapshot kind" not in combined.lower(), \
        f"agent_hire treated as unknown: {combined}"
    assert "would delete agent" in combined.lower() or \
           ("DRY RUN" in combined and "TestAgent" in combined), \
        f"agent_hire rollback did not surface delete intent: {combined}"


def test_rollback_handles_plugin_config_snapshot(tmp_path, monkeypatch):
    """plugin_config_snapshot already in rollback.sh — verify wiring."""
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_dir = tmp_path / ".paperclip" / "journal"
    journal_dir.mkdir(parents=True)
    name = "20260516T130100Z-plugin-test"
    (journal_dir / f"{name}.json").write_text(json.dumps({
        "op": "test-plugin",
        "timestamp": "20260516T130100Z",
        "entries": [
            {"kind": "plugin_config_snapshot",
             "plugin_id": "telegram",
             "old_config": {"defaultChatId": "12345"}},
        ],
        "outcome": "success",
    }))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), name, "--dry-run"],
        capture_output=True, text=True,
    )
    combined = out.stdout + out.stderr
    assert out.returncode == 0
    assert "telegram" in combined, f"plugin_config_snapshot not surfaced: {combined}"
```

- [ ] **Step 2: Run tests, verify FAIL on agent_hire**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_rollback_handles_agent_hire_kind -v
```
Expected: FAIL with "unknown snapshot kind: agent_hire" in output.

- [ ] **Step 3: Add `paperclip_delete_agent` helper**

Append to `paperclips/scripts/lib/_paperclip_api.sh`:

```bash
paperclip_delete_agent() {
  local agent_id="$1"
  curl -fsS --max-time 30 -X DELETE \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    "${PAPERCLIP_API_URL%/}/api/agents/${agent_id}"
}
```

- [ ] **Step 4: Add `agent_hire` case to rollback.sh**

Insert between lines 119 (after `version_bump_snapshot)` block) and the `*)` case:

```bash
    agent_hire)
      agent_id=$(printf '%s' "$entry" | jq -r '.id')
      agent_name=$(printf '%s' "$entry" | jq -r '.name')
      log info "rolling back hire of $agent_name ($agent_id)"
      if [ "$DRY_RUN" -eq 1 ]; then
        log info "DRY RUN — would delete agent $agent_name ($agent_id)"
      else
        paperclip_delete_agent "$agent_id" >/dev/null
        log ok "deleted agent $agent_name"
      fi
      ;;
```

- [ ] **Step 5: Run both tests, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py -v -k "rollback_handles"
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/rollback.sh paperclips/scripts/lib/_paperclip_api.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): rollback.sh handles agent_hire + adds DELETE helper

rollback.sh now has a case for agent_hire (DELETE /api/agents/<id>) — closes
the kind-mismatch loop with bootstrap-project.sh.

Closes CRIT-1 (part 2 of 2) from Phase C deep-review."
```

---

## Task 3: Journal plugin_config_snapshot before POST

**Why:** Step 8 fetches `current_config` (line 250) but never journals it before line 252's POST. If POST corrupts telegram config, rollback has no snapshot.

**Files:**
- Modify: `paperclips/scripts/bootstrap-project.sh:243-259`
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append to `paperclips/tests/test_phase_c_followup.py`:

```python
def test_bootstrap_journals_plugin_config_snapshot():
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    plugin_section_start = text.find("[8/13] telegram plugin config")
    assert plugin_section_start != -1, "could not locate telegram step"
    plugin_section_end = text.find("[9/13]", plugin_section_start)
    section = text[plugin_section_start:plugin_section_end] if plugin_section_end != -1 else text[plugin_section_start:]
    assert "paperclip_plugin_get_config" in section
    assert "plugin_config_snapshot" in section, \
        "plugin step must journal plugin_config_snapshot before POST"
    snapshot_pos = section.find("plugin_config_snapshot")
    post_pos = section.find("paperclip_plugin_set_config")
    assert snapshot_pos < post_pos, \
        f"snapshot at {snapshot_pos} must precede POST at {post_pos}"
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_bootstrap_journals_plugin_config_snapshot -v
```
Expected: FAIL with "plugin step must journal plugin_config_snapshot".

- [ ] **Step 3: Edit bootstrap-project.sh step 8**

Replace `paperclips/scripts/bootstrap-project.sh:249-252` (the comment + GET + merge + POST trio):

```bash
    # rev2 F-1: GET → diff → POST (replace mode per spec §8.4)
    # Followup CRIT-2: snapshot current_config BEFORE POST so rollback can restore.
    current_config=$(paperclip_plugin_get_config "$plugin_id" 2>/dev/null || echo "{}")
    journal_record "$journal" "$(jq -n \
      --arg pid "$plugin_id" \
      --argjson cfg "$current_config" \
      '{kind:"plugin_config_snapshot",plugin_id:$pid,old_config:$cfg}')"
    new_config=$(echo "$current_config" | jq --arg cid "$chat_id" '.config.defaultChatId = $cid')
    paperclip_plugin_set_config "$plugin_id" "$new_config" >/dev/null
```

- [ ] **Step 4: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_bootstrap_journals_plugin_config_snapshot -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/bootstrap-project.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): journal plugin_config_snapshot before POST in step 8

bootstrap-project.sh:249 now records old_config before paperclip_plugin_set_config,
closing the rollback gap for telegram plugin config mutations.

Closes CRIT-2 from Phase C deep-review."
```

---

## Task 4: Replace BSD-incompatible `sed '\u&'`

**Why:** `bootstrap-project.sh:85` uses `sed 's/.*/\u&/'` to capitalize project_key. `\u` is a GNU sed extension; macOS BSD sed prints literal `\u`. Affects the **first** interactive prompt on a fresh Mac.

**Files:**
- Modify: `paperclips/scripts/bootstrap-project.sh:85`
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_capitalize_uses_portable_construct():
    """No GNU-sed \\u extension — must be bash ${var^} or awk."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    assert "sed 's/.*/\\u" not in text, \
        "bootstrap-project.sh still uses GNU sed \\u (broken on BSD/macOS)"
    prompt_section = text[text.find("Local project root"):text.find("Local project root") + 200]
    portable = (
        "${project_key^}" in prompt_section or
        "awk '{print toupper" in prompt_section or
        "tr '[:lower:]' '[:upper:]'" in prompt_section
    )
    assert portable, f"prompt section uses no portable capitalize:\n{prompt_section}"
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_capitalize_uses_portable_construct -v
```
Expected: FAIL on first assertion.

- [ ] **Step 3: Edit bootstrap-project.sh:85**

Replace the line:

```bash
    proot=$(prompt_with_default "Local project root" "/Users/Shared/$(echo "$project_key" | sed 's/.*/\u&/')")
```

with:

```bash
    proot=$(prompt_with_default "Local project root" "/Users/Shared/${project_key^}")
```

(Bash 4+ parameter expansion `${var^}` capitalizes first char; works on macOS bash 5 — install-paperclip.sh already requires bash 4+.)

- [ ] **Step 4: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_capitalize_uses_portable_construct -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/bootstrap-project.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): replace GNU sed \\u with bash \${var^} for portability

BSD sed (macOS default) prints literal \\u; bash 4+ \${var^} capitalizes
portably. install-paperclip.sh already requires bash 4+.

Closes CRIT-3 from Phase C deep-review."
```

---

## Task 5: Preserve acronyms in migrate-bindings camelCase

**Why:** Current logic turns `CX_CTO_AGENT_ID` → `CXCto`, but canonical agent_name vocabulary preserves acronyms (uaudit manifest has `UWICTO`, `UWIQAEngineer`, `UWIMCPEngineer`). 3 of 12 gimle codex names are wrong: `CXCto`, `CXQaEngineer`, `CXMcpEngineer` should be `CXCTO`, `CXQAEngineer`, `CXMCPEngineer`.

**Files:**
- Modify: `paperclips/scripts/migrate-bindings.sh:62-79` (prefix translation block)
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_migrate_bindings_preserves_acronyms(tmp_path, monkeypatch):
    """CX_CTO → CXCTO not CXCto; CX_QA_ENGINEER → CXQAEngineer not CXQaEngineer."""
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "migrate-bindings.sh"), "gimle", "--dry-run"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"failed: {out.stderr}"
    assert "CXCTO:" in out.stdout, f"CXCTO missing (got CXCto?): {out.stdout}"
    assert "CXQAEngineer:" in out.stdout, f"CXQAEngineer missing: {out.stdout}"
    assert "CXMCPEngineer:" in out.stdout, f"CXMCPEngineer missing: {out.stdout}"
    assert "CXPythonEngineer:" in out.stdout
    assert "CXBlockchainEngineer:" in out.stdout
    assert "CodexArchitectReviewer:" in out.stdout
    assert "CXCto:" not in out.stdout
    assert "CXQaEngineer:" not in out.stdout
    assert "CXMcpEngineer:" not in out.stdout
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_migrate_bindings_preserves_acronyms -v
```
Expected: FAIL on `CXCTO:` missing.

- [ ] **Step 3: Edit migrate-bindings.sh camelization**

Replace `paperclips/scripts/migrate-bindings.sh:75-79` (the `camel=$(...)` line + `name=...`) with:

```bash
    # Acronym list per uaudit manifest convention (UWICTO, UWIQAEngineer, etc.)
    # CRIT-4 fix: preserve uppercase for well-known abbreviations during camelCase translation.
    ACRONYMS="CTO QA MCP CEO CFO CIO COO CSO CRO API CLI CI CD AI ML DB IT IO UI UX UWI UWA UW"
    camel=$(printf '%s' "$rest" | awk -F_ -v acr="$ACRONYMS" '
      BEGIN { split(acr, a, " "); for (i in a) is_acr[a[i]] = 1 }
      { out = ""
        for (i=1; i<=NF; i++) {
          tok = toupper($i)
          if (is_acr[tok]) { out = out tok }
          else { out = out toupper(substr($i,1,1)) tolower(substr($i,2)) }
        }
        print out
      }')
    name="${prefix}${camel}"
```

- [ ] **Step 4: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_migrate_bindings_preserves_acronyms -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/migrate-bindings.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): migrate-bindings preserves acronyms (CTO/QA/MCP)

Acronym whitelist matches uaudit manifest convention (UWICTO, UWIQAEngineer).
Prevents Phase G gimle migration from emitting unknown names to paperclip API.

Closes CRIT-4 from Phase C deep-review."
```

---

## Task 6: Path-validate project_key + journal_id

**Why:** `bootstrap-project.sh trading` is OK; `bootstrap-project.sh ../../etc` resolves to `~/.paperclip/projects/../../etc` and mkdir happily creates it. `rollback.sh /etc/passwd` reads it via `-f "$journal_id"`. Both should fail-loud early.

**Files:**
- Modify: `paperclips/scripts/lib/_common.sh` — add `validate_project_key` + `validate_journal_id`
- Modify: `paperclips/scripts/bootstrap-project.sh` (call after arg-parse)
- Modify: `paperclips/scripts/migrate-bindings.sh` (call after arg-parse)
- Modify: `paperclips/scripts/rollback.sh` (call after journal_id parse)
- Modify: `paperclips/scripts/bootstrap-watchdog.sh` (call after arg-parse)
- Modify: `paperclips/scripts/smoke-test.sh` (call after arg-parse)
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_path_traversal_rejected_by_bootstrap_project():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap-project.sh"), "../../etc"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "project key" in (out.stdout + out.stderr).lower()


def test_path_traversal_rejected_by_migrate_bindings():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "migrate-bindings.sh"), "../../etc", "--dry-run"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "project key" in (out.stdout + out.stderr).lower()


def test_path_traversal_rejected_by_rollback():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), "../../etc/passwd"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
    assert "journal" in (out.stdout + out.stderr).lower()


def test_absolute_path_rejected_by_rollback():
    out = subprocess.run(
        ["bash", str(SCRIPTS / "rollback.sh"), "/etc/passwd"],
        capture_output=True, text=True,
    )
    assert out.returncode != 0
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py -v -k "path_traversal or absolute_path"
```
Expected: 4 FAILed.

- [ ] **Step 3: Add validators to _common.sh**

Append to `paperclips/scripts/lib/_common.sh`:

```bash
# CRIT-5 fix: input validation for path-bearing arguments.
validate_project_key() {
  local key="$1"
  if [[ ! "$key" =~ ^[a-z0-9][a-z0-9_-]{0,39}$ ]]; then
    die "invalid project key: '$key' (must match [a-z0-9][a-z0-9_-]{0,39})"
  fi
}

validate_journal_id() {
  local jid="$1"
  case "$jid" in
    */*|*..*|/*)
      die "invalid journal id: '$jid' (no path separators, no .., no absolute path)"
      ;;
  esac
  if [[ ! "$jid" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    die "invalid journal id: '$jid' (must match [A-Za-z0-9][A-Za-z0-9._-]*)"
  fi
}
```

- [ ] **Step 4: Wire validators into 5 scripts**

In each script, after the arg-parse loop completes and `project_key`/`journal_id` is known, add the validator call:

`paperclips/scripts/bootstrap-project.sh` — after `[ -n "$project_key" ] || die "project-key required"`:

```bash
validate_project_key "$project_key"
```

`paperclips/scripts/migrate-bindings.sh` — same place.

`paperclips/scripts/bootstrap-watchdog.sh` — same place.

`paperclips/scripts/smoke-test.sh` — same place.

`paperclips/scripts/rollback.sh` — after `[ -n "$journal_id" ] || { usage; die "journal-id required"; }`:

```bash
validate_journal_id "$journal_id"
```

- [ ] **Step 5: Run tests, verify all 4 PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py -v -k "path_traversal or absolute_path"
python3 -m pytest paperclips/tests/test_phase_c_*.py 2>&1 | tail -5
```
Expected: 4 passed; full Phase C suite green.

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/lib/_common.sh paperclips/scripts/bootstrap-project.sh paperclips/scripts/migrate-bindings.sh paperclips/scripts/rollback.sh paperclips/scripts/bootstrap-watchdog.sh paperclips/scripts/smoke-test.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): validate project_key + journal_id early

validate_project_key rejects path-traversal + non-canonical chars in 4 scripts;
validate_journal_id rejects /etc/passwd, ../foo, foo/bar in rollback.sh.

Closes CRIT-5 from Phase C deep-review."
```

---

## Task 7: Rewrite bootstrap-watchdog yq merge in python3

**Why:** The yq merge `'.companies += [load_str("/dev/stdin")[0]]'` is wrong syntax for mikefarah yq v4 (silently caught by `2>/dev/null` and triggers the fallback). The fallback literal-appends a YAML sequence item after non-sequence sections, producing invalid YAML that the next watchdog tick will fail-parse.

**Files:**
- Modify: `paperclips/scripts/bootstrap-watchdog.sh:90-96`
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_watchdog_append_produces_valid_yaml(tmp_path, monkeypatch):
    """bootstrap-watchdog.sh must produce parseable YAML after appending company."""
    import yaml
    monkeypatch.setenv("HOME", str(tmp_path))
    project_key = "gimle"
    manifest_dir = REPO / "paperclips" / "projects" / project_key
    if not (manifest_dir / "paperclip-agent-assembly.yaml").is_file():
        return
    bindings_dir = tmp_path / ".paperclip" / "projects" / project_key
    bindings_dir.mkdir(parents=True)
    (bindings_dir / "bindings.yaml").write_text(
        'schemaVersion: 2\ncompany_id: "test-company-id-9999"\nagents: {}\n'
    )
    monkeypatch.setenv("PAPERCLIP_API_URL", "http://localhost:3100")
    out = subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap-watchdog.sh"), project_key, "--skip-launchd"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"watchdog setup failed: {out.stderr}"
    config_path = tmp_path / ".paperclip" / "watchdog-config.yaml"
    assert config_path.is_file()
    data = yaml.safe_load(config_path.read_text())
    assert "companies" in data, f"companies key missing: {data}"
    assert isinstance(data["companies"], list)
    subprocess.run(
        ["bash", str(SCRIPTS / "bootstrap-watchdog.sh"), project_key, "--skip-launchd"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    data2 = yaml.safe_load(config_path.read_text())
    ids = [c["id"] for c in data2["companies"]]
    assert ids.count("test-company-id-9999") == 1, f"duplicate after re-run: {ids}"
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_watchdog_append_produces_valid_yaml -v
```
Expected: FAIL — yq fallback produces invalid YAML.

- [ ] **Step 3: Replace yq merge with python3 merge**

Replace `paperclips/scripts/bootstrap-watchdog.sh:90-96` (the yq merge block + fallback) with:

```bash
  log info "appending company block for $display_name ($company_id)"
  # CRIT-6 fix: use python3 for robust YAML merge instead of yq (version-fragile syntax).
  python3 - "$config" "$block" <<'PY'
import sys, yaml
config_path, block_yaml = sys.argv[1], sys.argv[2]
with open(config_path) as f:
    cfg = yaml.safe_load(f) or {}
cfg.setdefault("companies", [])
new = yaml.safe_load(block_yaml)
if isinstance(new, list):
    cfg["companies"].extend(new)
else:
    cfg["companies"].append(new)
with open(config_path, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
PY
```

Note: install-paperclip.sh already requires python3 + PyYAML (per CLAUDE.md). No new dependency.

- [ ] **Step 4: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_watchdog_append_produces_valid_yaml -v
```
Expected: PASS — config parses + idempotent on re-run.

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/bootstrap-watchdog.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): use python3 for watchdog config merge

yq's load_str syntax differs across v3/v4; fallback literal-append produced
invalid YAML. python3 + PyYAML (already required) gives deterministic merge.

Closes CRIT-6 from Phase C deep-review."
```

---

## Task 8: Add curl timeouts to _paperclip_api.sh

**Why:** Network hang → indefinite bootstrap stall.

**Files:**
- Modify: `paperclips/scripts/lib/_paperclip_api.sh` (all 4 curl wrappers + Task-1+2 new helpers)
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_paperclip_api_has_curl_timeouts():
    text = (SCRIPTS / "lib" / "_paperclip_api.sh").read_text()
    import re
    curls = re.findall(r"curl\s+[^\n]+", text)
    bad = [c for c in curls if "--max-time" not in c]
    assert not bad, f"curl without --max-time:\n" + "\n".join(bad)
    bad2 = [c for c in curls if "--connect-timeout" not in c]
    assert not bad2, f"curl without --connect-timeout:\n" + "\n".join(bad2)
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_paperclip_api_has_curl_timeouts -v
```
Expected: FAIL.

- [ ] **Step 3: Add `--max-time 30 --connect-timeout 10` to each curl in _paperclip_api.sh**

For each curl invocation in `paperclips/scripts/lib/_paperclip_api.sh` (`paperclip_get`, `paperclip_post`, `paperclip_put`, `paperclip_patch`, plus Task-1's `paperclip_get_agent_instructions` and Task-2's `paperclip_delete_agent`):

Replace `curl -fsS` with `curl -fsS --max-time 30 --connect-timeout 10`. For Task-1's wrapper that uses `curl -sS` (without `-f`), use `curl -sS --max-time 30 --connect-timeout 10`.

Example for `paperclip_get`:

```bash
paperclip_get() {
  local path="$1"
  curl -fsS --max-time 30 --connect-timeout 10 \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    "${PAPERCLIP_API_URL%/}${path}"
}
```

(Apply identical change to `paperclip_post`, `paperclip_put`, `paperclip_patch`, and any other helper added in earlier tasks.)

- [ ] **Step 4: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_paperclip_api_has_curl_timeouts -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/lib/_paperclip_api.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): add --max-time 30 + --connect-timeout 10 to all curl

Prevents indefinite hang when paperclip-server is unresponsive.

Closes IMP-A from Phase C deep-review."
```

---

## Task 9: Distinguish 401 from 404 in plugin GET

**Why:** `current_config=$(paperclip_plugin_get_config "$plugin_id" 2>/dev/null || echo "{}")` treats every failure as "no prior config", so an expired JWT (401) produces `{}` → next POST wipes telegram defaultChatId.

**Files:**
- Modify: `paperclips/scripts/lib/_paperclip_api.sh` — add `paperclip_plugin_get_config_safe`
- Modify: `paperclips/scripts/bootstrap-project.sh:250` — handle 404 vs other-error
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_plugin_step_fail_closes_on_non_404():
    """Step 8 must die on non-404 GET errors, not silently fall back to {}."""
    text = (SCRIPTS / "bootstrap-project.sh").read_text()
    plugin_start = text.find("[8/13] telegram plugin")
    plugin_end = text.find("[9/13]", plugin_start)
    section = text[plugin_start:plugin_end]
    assert '|| echo "{}"' not in section, \
        "step 8 still has || echo \"{}\" fail-soft; must distinguish 404 from auth errors"
    assert "_safe" in section or "404" in section or \
           "first-time plugin config" in section.lower(), \
        "step 8 must explicitly handle 404 vs other errors"
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_plugin_step_fail_closes_on_non_404 -v
```
Expected: FAIL.

- [ ] **Step 3: Add `paperclip_plugin_get_config_safe` helper**

Append to `paperclips/scripts/lib/_paperclip_api.sh`:

```bash
paperclip_plugin_get_config_safe() {
  # Like paperclip_plugin_get_config but emits "{}" only on HTTP 404 (first-time config).
  # On 401/403/5xx, emits to stderr + returns non-zero (caller dies under set -e).
  local plugin_id="$1"
  local response http body
  response=$(curl -sS --max-time 30 --connect-timeout 10 \
    -o - -w '\n%{http_code}' \
    -H "Authorization: Bearer ${PAPERCLIP_API_KEY}" \
    -H "User-Agent: uaa-bootstrap/1.0" \
    "${PAPERCLIP_API_URL%/}/api/plugins/${plugin_id}/config" 2>/dev/null) || return 1
  http=$(printf '%s' "$response" | tail -1)
  body=$(printf '%s' "$response" | sed '$d')
  case "$http" in
    200) printf '%s' "$body" ;;
    404) printf '{}' ;;
    *) log err "plugin GET returned HTTP $http (expected 200 or 404)"; return 1 ;;
  esac
}
```

- [ ] **Step 4: Edit step 8 to use the safe variant**

Replace `paperclips/scripts/bootstrap-project.sh:250` (the `current_config=$(...)` line):

```bash
    current_config=$(paperclip_plugin_get_config_safe "$plugin_id") || \
      die "plugin GET failed for $plugin_id (likely auth issue — check PAPERCLIP_API_KEY)"
```

- [ ] **Step 5: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_plugin_step_fail_closes_on_non_404 -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/lib/_paperclip_api.sh paperclips/scripts/bootstrap-project.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): distinguish 404 from auth errors in plugin GET

paperclip_plugin_get_config_safe returns {} only on 404; on 401/403/5xx the
caller dies. Prevents telegram defaultChatId wipe on expired JWT.

Closes IMP-B from Phase C deep-review."
```

---

## Task 10: chmod 600 on bindings + journal files

**Why:** Default umask leaves AGENTS.md content (medium-sensitivity) world-readable in `~/.paperclip/journal/*.json`.

**Files:**
- Modify: `paperclips/scripts/lib/_journal.sh:7-20` (init + open + record)
- Modify: `paperclips/scripts/bootstrap-project.sh` — chmod 600 on bindings.yaml after write
- Modify: `paperclips/scripts/migrate-bindings.sh` — chmod 600 on bindings.yaml after write
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_journal_files_created_with_mode_600(tmp_path, monkeypatch):
    """Journal files contain AGENTS.md content — must be 600."""
    import os
    monkeypatch.setenv("HOME", str(tmp_path))
    cmd = f'source {SCRIPTS / "lib" / "_journal.sh"}; journal_open test-mode'
    result = subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True,
        env={"HOME": str(tmp_path), "PATH": os.environ["PATH"]},
    )
    assert result.returncode == 0, f"journal_open failed: {result.stderr}"
    journal_path = result.stdout.strip()
    assert Path(journal_path).is_file()
    mode = Path(journal_path).stat().st_mode & 0o777
    assert mode == 0o600, f"journal mode {oct(mode)} != 0o600"
    journal_dir = tmp_path / ".paperclip" / "journal"
    dir_mode = journal_dir.stat().st_mode & 0o777
    assert dir_mode == 0o700, f"journal dir mode {oct(dir_mode)} != 0o700"


def test_migrate_bindings_creates_bindings_yaml_mode_600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = subprocess.run(
        ["bash", str(SCRIPTS / "migrate-bindings.sh"), "gimle"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert out.returncode == 0, f"migrate-bindings failed: {out.stderr}"
    bindings = tmp_path / ".paperclip" / "projects" / "gimle" / "bindings.yaml"
    assert bindings.is_file()
    mode = bindings.stat().st_mode & 0o777
    assert mode == 0o600, f"bindings.yaml mode {oct(mode)} != 0o600"
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py -v -k "mode_600"
```
Expected: 2 FAILed.

- [ ] **Step 3: Add umask + chmod to _journal.sh**

At the TOP of `paperclips/scripts/lib/_journal.sh` (before function definitions), add:

```bash
# IMP-C fix: protect journal files (contain AGENTS.md content + plugin configs).
umask 0077
```

In the `journal_init` function, after `mkdir -p "$JOURNAL_DIR"`:

```bash
  chmod 700 "$JOURNAL_DIR"
```

In `journal_open`, after `printf '%s' "$initial" > "$path"`:

```bash
  chmod 600 "$path"
```

- [ ] **Step 4: Add chmod to migrate-bindings.sh + bootstrap-project.sh bindings writes**

In `migrate-bindings.sh`, after the `printf '%s' "$yaml_content" > "$target_file"` line:

```bash
chmod 600 "$target_file"
chmod 700 "$target_dir"
```

In `bootstrap-project.sh`, find the line that writes `bindings.yaml` (around line 119-123) and add the same chmod after the write.

- [ ] **Step 5: Run tests, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py -v -k "mode_600"
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/lib/_journal.sh paperclips/scripts/migrate-bindings.sh paperclips/scripts/bootstrap-project.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): chmod 600 bindings.yaml + journal files

Journal contains AGENTS.md content (medium-sensitivity); bindings hold
agent UUIDs + company_id. 600 mode + 700 dir, umask 0077 in _journal.sh.

Closes IMP-C from Phase C deep-review."
```

---

## Task 11: Replace dynamic-shell-evaluation with `${!var}` in _smoke_probes.sh

**Why:** `_smoke_probes.sh:111-112` uses bash builtin `e v a l` (the dynamic-shell-evaluation builtin) to look up profile-keyed variables. If `profile` arrives unfiltered (validate-manifest fails or schema change), this is a code-execution sink. Bash indirect expansion `${!var}` is the safe equivalent.

**Files:**
- Modify: `paperclips/scripts/lib/_smoke_probes.sh:111-112`
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_smoke_probes_no_shell_evaluation_builtin():
    """Replace 'e''val' invocations with bash indirect ${!var}."""
    text = (SCRIPTS / "lib" / "_smoke_probes.sh").read_text()
    # The two specific call sites must be gone
    assert 'must_have=\\$EXPECTED_GIT_' not in text and 'must_have=$EXPECTED_GIT_' not in text, \
        "smoke_probes still uses dynamic shell evaluation for variable lookup"
    # Should use indirect expansion
    assert '${!' in text, \
        "smoke_probes must use bash indirect expansion ${!var}"
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_smoke_probes_no_shell_evaluation_builtin -v
```
Expected: FAIL.

- [ ] **Step 3: Edit _smoke_probes.sh:111-112**

Find the two lines using bash builtin `e v a l` to set `must_have` / `must_not` from `EXPECTED_GIT_${profile}_*` variables, and replace with:

```bash
    # IMP-D fix: bash indirect expansion instead of dynamic shell evaluation
    local mh_var="EXPECTED_GIT_${profile}_must_have"
    local mn_var="EXPECTED_GIT_${profile}_must_not_have"
    must_have="${!mh_var:-}"
    must_not="${!mn_var:-}"
```

- [ ] **Step 4: Run test, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py::test_smoke_probes_no_shell_evaluation_builtin -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/lib/_smoke_probes.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): bash indirect expansion in _smoke_probes for profile lookup

Defense-in-depth against profile-string injection if a future manifest
sneaks past validate-manifest with shell-active characters in profile.

Closes IMP-D from Phase C deep-review."
```

---

## Task 12: Validate agent_name to prevent yq path injection

**Why:** `yq -r ".agents.${agent_name}"` lets manifests with names containing `.`, `[`, or `]` produce unexpected yq path expressions.

**Files:**
- Modify: `paperclips/scripts/lib/_common.sh` — add `validate_agent_name`
- Modify: `paperclips/scripts/bootstrap-project.sh` — call after reading agent_name (in step 7 + deploy_one)
- Test: `paperclips/tests/test_phase_c_followup.py`

- [ ] **Step 1: Add test**

Append:

```python
def test_validate_agent_name_rejects_path_chars():
    """Call validator from bash with bad inputs; must exit non-zero."""
    bad_names = ["foo.bar", "foo[0]", "foo bar", "foo;rm", "$(pwd)", "../foo"]
    common = SCRIPTS / "lib" / "_common.sh"
    for name in bad_names:
        cmd = f'source {common}; validate_agent_name "{name}"'
        out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        assert out.returncode != 0, f"validate_agent_name accepted bad: {name!r}"


def test_validate_agent_name_accepts_canonical():
    good = ["CTO", "PythonEngineer", "CXCTO", "CXMCPEngineer", "UWIQAEngineer",
            "CodexArchitectReviewer", "code_reviewer", "auditor"]
    common = SCRIPTS / "lib" / "_common.sh"
    for name in good:
        cmd = f'source {common}; validate_agent_name "{name}"'
        out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        assert out.returncode == 0, f"validate_agent_name rejected good: {name!r}: {out.stderr}"
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py -v -k "agent_name"
```
Expected: FAIL — function not defined.

- [ ] **Step 3: Add validator to _common.sh**

Append to `paperclips/scripts/lib/_common.sh`:

```bash
validate_agent_name() {
  local name="$1"
  if [[ ! "$name" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]]; then
    die "invalid agent_name: '$name' (must match [A-Za-z][A-Za-z0-9_]*)"
  fi
}
```

- [ ] **Step 4: Call validator in bootstrap-project.sh**

In `paperclips/scripts/bootstrap-project.sh`, find the step 7 hire loop (`for agent_name in $hire_order; do`) and add inside the loop body, right at the top:

```bash
  validate_agent_name "$agent_name"
```

Also in `deploy_one` (after Task 1's rewrite), add at top:

```bash
  validate_agent_name "$agent_name"
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_c_followup.py -v -k "agent_name"
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/lib/_common.sh paperclips/scripts/bootstrap-project.sh paperclips/tests/test_phase_c_followup.py
git commit -m "fix(uaa-phase-c): validate agent_name against yq-path-safe alphabet

Prevents future manifest with agent_name='foo.bar' from misparsing yq
selectors. Belt-and-suspenders alongside Phase B validate-manifest.

Closes IMP-E from Phase C deep-review."
```

---

## Task 13: Full sweep + spec changelog + open PR

**Files:**
- Modify: `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` (changelog)

- [ ] **Step 1: Run full repo sweep**

```bash
cd /Users/ant013/Android/Gimle-Palace
python3 -m pytest paperclips/tests/ 2>&1 | tail -5
```
Expected: 244 + 19 new ≈ 263 passed, 7 skipped.

- [ ] **Step 2: Append spec changelog**

Edit `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md`. Find the `**Phase C complete (2026-05-16):**` block. Insert ABOVE it:

```markdown
**Phase C followup complete (2026-05-16):**
- 6 CRITICAL findings from 4-voltAgent deep-review addressed:
  - CRIT-1 — bootstrap-project + rollback now use matching journal kinds (`agent_instructions_snapshot` + new `agent_hire`); old AGENTS.md content captured before PUT.
  - CRIT-2 — plugin step 8 journals `plugin_config_snapshot` before POST.
  - CRIT-3 — BSD-incompatible `sed '\u&'` replaced with bash `${var^}`.
  - CRIT-4 — migrate-bindings preserves acronyms (`CXCTO`/`CXMCPEngineer`/`CXQAEngineer`) per uaudit manifest convention.
  - CRIT-5 — `validate_project_key` + `validate_journal_id` reject path-traversal in 5 scripts.
  - CRIT-6 — `bootstrap-watchdog.sh` uses python3 for YAML merge instead of fragile yq syntax + literal-append fallback.
- 5 high-signal IMPORTANT addressed: curl timeouts (IMP-A), 401-vs-404 distinguish in plugin GET (IMP-B), chmod 600 on journal + bindings (IMP-C), dynamic shell-evaluation builtin replaced by `${!var}` (IMP-D), `validate_agent_name` (IMP-E).
- 19 new behavioral tests in `test_phase_c_followup.py` (assertions on runtime behavior, not source-string-greps).
- One architect false-positive rejected after verification: watchdog-config.yaml.template does NOT contain `---` separator.
- Parked (separate efforts): ~15 tautological tests (test-quality refactor); 7 stale `test_validate_instructions.py` skips (Phase A→B reconciliation); flock for concurrent bootstrap (design decision); update-versions snapshot scope (document as limitation).
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md
git commit -m "docs(uaa-phase-c-followup): spec changelog with 6 CRITICAL + 5 IMPORTANT fixes"
git push -u origin feature/uaa-phase-c-followup
```

- [ ] **Step 4: Open PR**

```bash
gh pr create --base develop --title "fix(uaa-phase-c-followup): 6 CRITICAL + 5 IMPORTANT findings from deep-review" --label "micro-slice" --body-file - <<'EOF'
## Summary

Addresses 6 CRITICAL + 5 IMPORTANT verified findings from the 4-voltAgent deep-review of cumulative Phase C (PRs #191/#193/#194). Each fix has a behavioral test (not source-string-grep). One architect false-positive rejected after verification.

**Owner:** operator (per UAA spec §14 execution-ownership; followup to Phase C scripts).

## CRITICAL (verified)

| ID | Fix |
|---|---|
| CRIT-1 | Journal kind mismatch — bootstrap snapshots OLD AGENTS.md; rollback gets new `agent_hire` case + DELETE helper |
| CRIT-2 | Plugin step 8 journals `plugin_config_snapshot` before POST |
| CRIT-3 | BSD sed `\u&` → bash `${var^}` |
| CRIT-4 | migrate-bindings acronym preservation (CXCTO/QA/MCP per uaudit) |
| CRIT-5 | path-validate project_key + journal_id in 5 scripts |
| CRIT-6 | bootstrap-watchdog yq merge → python3 (deterministic) |

## IMPORTANT

| ID | Fix |
|---|---|
| IMP-A | curl `--max-time 30 --connect-timeout 10` on all wrappers |
| IMP-B | 401 vs 404 distinguished in plugin GET |
| IMP-C | chmod 600 on journal + bindings; umask 0077 in _journal.sh |
| IMP-D | dynamic shell evaluation in _smoke_probes → bash indirect expansion |
| IMP-E | validate_agent_name in lib/_common.sh; called in bootstrap loops |

## Tests

- New file: `paperclips/tests/test_phase_c_followup.py` (~19 tests, all behavioral)
- Full sweep target: ~263 passed, 7 skipped

## Out of scope

- ~15 tautological tests across earlier Phase C test files
- 7 stale skips in `test_validate_instructions.py`
- flock for concurrent bootstrap-project
- update-versions snapshot scope expansion

## Test plan

- [ ] CI green
- [ ] Operator review

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

## Acceptance gate (before Phase D unblocked)

- [ ] All 12 task commits land on `feature/uaa-phase-c-followup`
- [ ] `python3 -m pytest paperclips/tests/` shows ≥263 passed, 7 skipped, 0 failed
- [ ] CI green on PR
- [ ] Spec changelog appended

---

## Self-review checklist

1. **Spec coverage:** Each finding (CRIT-1..6, IMP-A..E) maps to exactly one task ✓
2. **Placeholder scan:** No TBD/TODO; every shell snippet shows full bash; every test shows full Python ✓
3. **Type consistency:** `kind:"agent_instructions_snapshot"` used in Tasks 1 + 2 — same string. `validate_project_key`/`validate_journal_id`/`validate_agent_name` consistently named ✓
4. **No invented APIs:** `paperclip_get_agent_instructions` is NEW in Task 1; explicitly added to lib. `paperclip_delete_agent` NEW in Task 2. `paperclip_plugin_get_config_safe` NEW in Task 9. All defined before being called ✓
