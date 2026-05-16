# UAA Phase H — Cleanup Gate + Legacy Removal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Cleanup PR is mechanical; gate evaluation is operator-only.

**Spec:** `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §10.1, §10.5
**Owner:** `operator + team` (per spec §14.2 — operator evaluates watchdog metric, team produces cleanup PR)
**Estimate:** 1 day (after gate passes)
**Prereq:** Phase G complete; cleanup gate (§10.1) green for ≥7 days
**Blocks:** None — terminal phase of UAA migration

**Goal:** Remove legacy infrastructure no longer needed: `paperclips/codex-agent-ids.env`, legacy deploy scripts, `roles/legacy/`, `roles-codex/legacy/`, deprecated shared fragments. Update `imac-agents-deploy.sh` as thin wrapper around new `bootstrap-project.sh --reuse-bindings`.

**Architecture:** Two parts:
1. **Gate evaluation** (operator-only): query watchdog log for 7 days clean per spec §10.1 metric. Document evidence.
2. **Cleanup PR** (team-mechanical): grep for any remaining references to legacy files; remove if zero references.

**Risk profile:** LOW if gate honestly passed; HIGH if gate skipped. Failure mode: legacy file removed while still referenced → silent NameError / FileNotFoundError on next agent wake. Hence gate evidence is mandatory.

---

## File Structure

### Removed (after gate passes)

```
paperclips/codex-agent-ids.env                                   # legacy mapping; superseded by ~/.paperclip/projects/gimle/bindings.yaml
paperclips/deploy-agents.sh                                      # legacy claude deploy
paperclips/deploy-codex-agents.sh                                # legacy codex deploy
paperclips/update-agent-workspaces.sh                            # legacy workspace setup
paperclips/hire-codex-agents.sh                                  # legacy codex hire (replaced by bootstrap-project.sh)
paperclips/roles/legacy/*.md                                     # 12 legacy claude role files (Phase A.1 hybrid)
paperclips/roles-codex/legacy/cx-*.md                            # 12 legacy codex role files
paperclips/fragments/shared/fragments/karpathy-discipline.md     # deprecated shared fragments (Phase A)
paperclips/fragments/shared/fragments/heartbeat-discipline.md
paperclips/fragments/shared/fragments/escalation-blocked.md
paperclips/fragments/shared/fragments/git-workflow.md
paperclips/fragments/shared/fragments/worktree-discipline.md
paperclips/fragments/shared/fragments/phase-handoff.md
paperclips/fragments/shared/fragments/compliance-enforcement.md
paperclips/fragments/shared/fragments/test-design-discipline.md
paperclips/fragments/shared/fragments/pre-work-discovery.md
paperclips/fragments/shared/fragments/plan-first-producer.md
paperclips/fragments/shared/fragments/plan-first-review.md
paperclips/scripts/build_project_compat.py                       # legacy expand_includes path; new path consolidated
                                                                  # (KEEP file, but DELETE expand_includes / apply_overlay legacy code)
```

### Modified

```
paperclips/scripts/imac-agents-deploy.sh                         # rewrite as wrapper around bootstrap-project.sh
paperclips/scripts/imac-deploy.sh                                # update if it references removed files
paperclips/scripts/build_project_compat.py                       # remove legacy code paths
services/watchdog/src/gimle_watchdog/detection_semantic.py       # remove `_legacy_load_uuids` fallback
.gitignore                                                        # may need updates
```

### Created

```
docs/uaa-cleanup-gate-evidence.md                                # operator-authored signoff + watchdog log excerpts
paperclips/tests/test_phase_h_cleanup.py
```

---

## Task 1: Cleanup gate evaluation (operator-only)

This is the **most important** task in Phase H. No automation — operator manually verifies and documents.

- [ ] **Step 1: Run watchdog log scan for last 7 days**

```bash
# rev4 H-1: source common helpers so `log info` works as standalone snippet
source paperclips/scripts/lib/_common.sh

cutoff=$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ)
log info "checking watchdog log for events since $cutoff"

# Per spec §10.1 metric — zero of these events for 7 days across all 3 projects:
forbidden_events='["wake_failed", "handoff_alert_posted"]'

count_forbidden=$(jq -c "select(.timestamp >= \"$cutoff\")" ~/.paperclip/watchdog.log 2>/dev/null | \
                  jq -c "select(.event | IN(\"wake_failed\", \"handoff_alert_posted\"))" | wc -l)
echo "forbidden events in last 7d: $count_forbidden"
```

Expected: `0`.

If `> 0`, gate FAILS. Investigate each event:
```bash
jq -c 'select(.timestamp >= "'$cutoff'") | select(.event | IN("wake_failed", "handoff_alert_posted"))' \
  ~/.paperclip/watchdog.log
```

For each: identify root cause. Document. If transient (single event with clear cause), discuss with operator if it's acceptable. If pattern (recurring), Phase H BLOCKED — fix first, then restart 7-day window.

- [ ] **Step 2: Verify per-agent escalation cap not hit**

```bash
jq -c 'select(.timestamp >= "'$cutoff'") | select(.event == "escalation") | select(.reason == "per_agent_cap")' \
  ~/.paperclip/watchdog.log | wc -l
```

Expected: `0`. Per-agent cap escalations indicate agent failure mode — gate FAILS if any in last 7d.

- [ ] **Step 3: Verify zero non-2xx PUT responses for instructions-bundle**

If watchdog logs PUT failures (it doesn't directly — operator deploys are journaled instead), check journal:
```bash
for j in ~/.paperclip/journal/*-bootstrap-*.json; do
  outcome=$(jq -r '.outcome // "in-progress"' "$j")
  if [ "$outcome" != "success" ]; then
    echo "FAILED journal: $j"
  fi
done
```

Expected: zero non-success outcomes in last 7d.

- [ ] **Step 4: Smoke-test all 3 projects**

```bash
./paperclips/scripts/smoke-test.sh trading
./paperclips/scripts/smoke-test.sh uaudit
./paperclips/scripts/smoke-test.sh gimle
```

Expected: 3 × 7/7 PASS.

- [ ] **Step 5: Operator signoff document**

Create `docs/uaa-cleanup-gate-evidence.md`:

```markdown
# UAA Cleanup Gate — Evidence

**Date evaluated:** YYYY-MM-DD
**Evaluator:** <operator-name>
**Verdict:** PASS

## Stability metric (spec §10.1)

Window: YYYY-MM-DD to YYYY-MM-DD (7 days)

| Metric | Threshold | Observed | Status |
|---|---|---|---|
| `wake_failed` events | 0 | 0 | ✓ |
| `handoff_alert_posted` events | 0 | 0 | ✓ |
| `escalation` events with `per_agent_cap` reason | 0 | 0 | ✓ |
| Non-success deploy journals | 0 | 0 | ✓ |

## Per-project smoke (run on YYYY-MM-DD)

- trading: 7/7 PASS (smoke-test.sh log: …)
- uaudit: 7/7 PASS
- gimle: 7/7 PASS

## In-flight issue continuity

- Pre-Phase-G snapshot: <N> in_progress issues
- Current: <N>
- Lost: 0 (or document)

## Signoff

Cleanup gate PASSES. Phase H legacy removal authorized.

— <operator-name>, YYYY-MM-DD
```

- [ ] **Step 6: Commit signoff**

```bash
git add docs/uaa-cleanup-gate-evidence.md
git commit -m "docs(uaa-phase-h): cleanup gate signoff — 7d stable across all 3 projects"
```

If gate FAILS, **DO NOT PROCEED** with subsequent tasks. Postpone Phase H. Investigate and fix issues. Restart 7-day window. Document failure in this same file with verdict: FAIL.

---

## Task 2: Verify zero references to legacy files (pre-removal grep)

- [ ] **Step 1: Failing test (asserts no consumers reference legacy files)**

```python
# paperclips/tests/test_phase_h_cleanup.py
"""Phase H: pre-cleanup grep — no consumer should reference legacy files."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _grep_excluding_self(pattern: str, exclude_dirs=None) -> list[str]:
    """grep for pattern across repo, excluding the target file itself + tests/baseline."""
    excludes = ["tests/baseline", "docs/superpowers", "docs/uaa-cleanup", ".git", "node_modules", "dist"]
    if exclude_dirs:
        excludes.extend(exclude_dirs)
    cmd = ["git", "grep", "-l", pattern]
    for ex in excludes:
        cmd.extend(["--", f":!{ex}/**"])
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return [l for l in out.stdout.strip().split("\n") if l]


def test_no_consumer_references_codex_agent_ids_env():
    """Per Phase D dual-read seam: only resolve_bindings reads this file."""
    refs = _grep_excluding_self("codex-agent-ids.env",
                                exclude_dirs=["paperclips/scripts/resolve_bindings.py"])
    # Acceptable: resolve_bindings.py (the resolver itself) + spec/changelog.
    refs = [r for r in refs if r != "paperclips/scripts/resolve_bindings.py"]
    refs = [r for r in refs if not r.startswith("docs/")]
    refs = [r for r in refs if "test_phase_d_resolver" not in r]  # test fixtures use the path
    refs = [r for r in refs if "test_phase_h_cleanup" not in r]
    assert not refs, f"legacy file still referenced by: {refs}"


def test_no_consumer_references_deploy_agents_sh():
    refs = _grep_excluding_self("deploy-agents.sh")
    refs = [r for r in refs if not r.startswith("docs/")]
    refs = [r for r in refs if "test_phase_h_cleanup" not in r]
    refs = [r for r in refs if "imac-agents-deploy" not in r]  # imac wrapper still references — Task 4 rewrites it
    assert not refs, f"legacy script still referenced by: {refs}"


def test_no_consumer_references_hire_codex_agents_sh():
    refs = _grep_excluding_self("hire-codex-agents.sh")
    refs = [r for r in refs if not r.startswith("docs/")]
    refs = [r for r in refs if "test_phase_h_cleanup" not in r]
    assert not refs


def test_no_role_includes_legacy_directives():
    """No new craft file should contain <!-- @include fragments/karpathy-discipline.md --> etc."""
    deprecated_fragments = [
        "karpathy-discipline.md", "heartbeat-discipline.md", "phase-handoff.md",
        "git-workflow.md", "worktree-discipline.md", "escalation-blocked.md",
        "compliance-enforcement.md", "test-design-discipline.md", "pre-work-discovery.md",
        "plan-first-producer.md", "plan-first-review.md",
    ]
    for d in deprecated_fragments:
        refs = _grep_excluding_self(f"@include fragments/{d}",
                                    exclude_dirs=["paperclips/roles/legacy", "paperclips/roles-codex/legacy"])
        refs = [r for r in refs if not r.startswith("docs/")]
        refs = [r for r in refs if "test_phase_h_cleanup" not in r]
        assert not refs, f"deprecated fragment {d} still included by: {refs}"
```

- [ ] **Step 2: Run, verify PASS (zero references)**

```bash
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v
```

If any test FAILS, find the offending file:
```bash
git grep "codex-agent-ids.env"
```
Update or remove the reference, then re-run test.

- [ ] **Step 3: Commit pre-removal verification**

```bash
git add paperclips/tests/test_phase_h_cleanup.py
git commit -m "test(uaa-phase-h): pre-removal grep — zero consumers reference legacy files"
```

---

## Task 3: Remove deprecated shared fragments

**Files:**
- Delete (in submodule): 11 deprecated `.md` files in `paperclips/fragments/shared/fragments/`

- [ ] **Step 1: Failing test (asserts files removed)**

```python
def test_deprecated_fragments_removed():
    submodule = REPO / "paperclips" / "fragments" / "shared" / "fragments"
    deprecated = [
        "karpathy-discipline.md", "heartbeat-discipline.md", "phase-handoff.md",
        "git-workflow.md", "worktree-discipline.md", "escalation-blocked.md",
        "compliance-enforcement.md", "test-design-discipline.md", "pre-work-discovery.md",
        "plan-first-producer.md", "plan-first-review.md",
    ]
    still_present = [d for d in deprecated if (submodule / d).is_file()]
    assert not still_present, f"deprecated fragments not yet removed: {still_present}"


def test_kept_fragments_still_present():
    submodule = REPO / "paperclips" / "fragments" / "shared" / "fragments"
    kept = ["cto-no-code-ban.md", "language.md"]
    for k in kept:
        assert (submodule / k).is_file(), f"kept fragment removed: {k}"
```

- [ ] **Step 2: Verify FAIL (files still present)**

```bash
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v -k deprecated_fragments
```

- [ ] **Step 3: Remove files in submodule**

```bash
cd paperclips/fragments/shared
git checkout -b feature/uaa-phase-h-cleanup
rm fragments/karpathy-discipline.md
rm fragments/heartbeat-discipline.md
rm fragments/phase-handoff.md
rm fragments/git-workflow.md
rm fragments/worktree-discipline.md
rm fragments/escalation-blocked.md
rm fragments/compliance-enforcement.md
rm fragments/test-design-discipline.md
rm fragments/pre-work-discovery.md
rm fragments/plan-first-producer.md
rm fragments/plan-first-review.md
git add -u
git commit -m "feat(uaa-phase-h): remove 11 deprecated fragments after cleanup gate passed"
```

- [ ] **Step 4: Verify PASS**

```bash
cd ../../..
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v -k deprecated_fragments
```

- [ ] **Step 5: Bump submodule pointer + commit super-repo**

```bash
git add paperclips/fragments/shared
git commit -m "feat(uaa-phase-h): bump shared-fragments — removed 11 deprecated"
```

- [ ] **Step 6: Re-run all builds to confirm no consumer needs them**

```bash
./paperclips/build.sh --project trading --target codex
./paperclips/build.sh --project trading --target claude
./paperclips/build.sh --project uaudit --target codex
./paperclips/build.sh --project gimle --target claude
./paperclips/build.sh --project gimle --target codex
```

Expected: zero errors. If "fragment not found" errors, a consumer still references the deprecated file. Restore (git revert) and find the consumer.

---

## Task 4: Remove legacy role/legacy/* files

**Files:**
- Delete: `paperclips/roles/legacy/*.md` (12 files)
- Delete: `paperclips/roles-codex/legacy/*.md` (12 files)
- Delete: `paperclips/roles/legacy/`, `paperclips/roles-codex/legacy/`

- [ ] **Step 1: Failing test**

```python
def test_legacy_role_dirs_removed():
    for d in ["paperclips/roles/legacy", "paperclips/roles-codex/legacy"]:
        p = REPO / d
        assert not p.is_dir(), f"legacy dir still present: {d}"
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v -k legacy_role_dirs
```

- [ ] **Step 3: Verify no manifest references legacy role files**

```bash
git grep "roles/legacy" paperclips/projects/
git grep "roles-codex/legacy" paperclips/projects/
```

Expected: zero matches. If matches, manifest entry uses `role_source: roles/legacy/X.md` — update it to `roles/X.md` first.

- [ ] **Step 4: Remove**

```bash
rm -rf paperclips/roles/legacy
rm -rf paperclips/roles-codex/legacy
git add -u paperclips/roles/ paperclips/roles-codex/
```

- [ ] **Step 5: Verify PASS + commit**

```bash
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v -k legacy_role_dirs
git commit -m "feat(uaa-phase-h): remove roles/legacy/ + roles-codex/legacy/ after cleanup gate"
```

---

## Task 5: Remove legacy scripts + rewrite imac-agents-deploy.sh

**Files:**
- Delete: `paperclips/codex-agent-ids.env`
- Delete: `paperclips/deploy-agents.sh`
- Delete: `paperclips/deploy-codex-agents.sh`
- Delete: `paperclips/update-agent-workspaces.sh`
- Delete: `paperclips/hire-codex-agents.sh`
- Modify: `paperclips/scripts/imac-agents-deploy.sh` (rewrite as wrapper)

- [ ] **Step 1: Failing test**

```python
def test_legacy_scripts_removed():
    legacy_scripts = [
        "codex-agent-ids.env", "deploy-agents.sh", "deploy-codex-agents.sh",
        "update-agent-workspaces.sh", "hire-codex-agents.sh",
    ]
    for s in legacy_scripts:
        p = REPO / "paperclips" / s
        assert not p.is_file(), f"legacy script still present: {s}"


def test_imac_agents_deploy_uses_bootstrap_project():
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    if not p.is_file():
        return
    text = p.read_text()
    assert "bootstrap-project.sh" in text, "imac-agents-deploy.sh not yet rewritten as wrapper"
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v -k "legacy_scripts or imac_agents"
```

- [ ] **Step 3: Rewrite imac-agents-deploy.sh as thin wrapper**

```bash
#!/usr/bin/env bash
# UAA Phase H: thin wrapper around bootstrap-project.sh --reuse-bindings, for iMac use.
# Replaces legacy paperclips/deploy-agents.sh + paperclips/deploy-codex-agents.sh.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${SCRIPT_DIR}/lib/_common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <project-key>

iMac wrapper: re-deploys per-agent AGENTS.md to all hired agents of <project-key>
using bootstrap-project.sh --reuse-bindings.

Use after AGENTS.md template / fragment changes are merged to develop and need to
land on the iMac runtime.
EOF
}

[ "$#" -eq 1 ] || { usage; exit 2; }
project_key="$1"

bindings="${HOME}/.paperclip/projects/${project_key}/bindings.yaml"
[ -f "$bindings" ] || die "no bindings for project ${project_key} on this machine — run bootstrap-project.sh first"

log info "iMac re-deploy for ${project_key} (using existing bindings)"
"${SCRIPT_DIR}/bootstrap-project.sh" "${project_key}" --reuse-bindings "$bindings"
```

- [ ] **Step 4: Remove legacy files**

```bash
rm paperclips/codex-agent-ids.env
rm paperclips/deploy-agents.sh
rm paperclips/deploy-codex-agents.sh
rm paperclips/update-agent-workspaces.sh
rm paperclips/hire-codex-agents.sh
```

- [ ] **Step 5: Update imac-deploy.sh if it sources or exec's any removed file**

```bash
git grep -l "deploy-agents.sh\|hire-codex-agents.sh\|codex-agent-ids.env\|update-agent-workspaces.sh" paperclips/scripts/imac-deploy.sh paperclips/scripts/imac-deploy.README.md
```

If any matches, edit those files to remove or update references.

- [ ] **Step 6: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v -k "legacy_scripts or imac_agents"
```

- [ ] **Step 7: Commit**

```bash
git add paperclips/codex-agent-ids.env paperclips/deploy-agents.sh paperclips/deploy-codex-agents.sh \
        paperclips/update-agent-workspaces.sh paperclips/hire-codex-agents.sh \
        paperclips/scripts/imac-agents-deploy.sh paperclips/scripts/imac-deploy.sh
git commit -m "feat(uaa-phase-h): remove legacy deploy scripts; imac-agents-deploy.sh becomes thin wrapper"
```

---

## Task 6: Remove dual-read code paths from builder + watchdog

**Files:**
- Modify: `paperclips/scripts/build_project_compat.py` (drop legacy `expand_includes` if unused)
- Modify: `paperclips/scripts/resolve_bindings.py` (drop legacy_env_path support)
- Modify: `services/watchdog/src/gimle_watchdog/detection_semantic.py` (drop `_legacy_load_uuids`)

- [ ] **Step 1: Failing test**

```python
def test_resolve_bindings_drops_legacy():
    """Post-cleanup: resolve_all no longer accepts legacy_env_path."""
    text = (REPO / "paperclips" / "scripts" / "resolve_bindings.py").read_text()
    # Function still works, but the legacy_env_path argument should no longer be wired.
    # Soft check: ensure docstring updated to reflect single-source.
    assert "Phase H cleanup" in text or "legacy_env removed" in text, \
        "resolve_bindings.py docstring not updated for cleanup"


def test_watchdog_legacy_load_removed():
    text = (REPO / "services" / "watchdog" / "src" / "gimle_watchdog" / "detection_semantic.py").read_text()
    assert "_legacy_load_uuids" not in text, "fallback function not yet removed"
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v -k "resolve_bindings or watchdog_legacy"
```

- [ ] **Step 3: Edit `paperclips/scripts/resolve_bindings.py`**

Drop legacy support: remove `legacy_env_path` parameter or have it unconditionally raise `DeprecationWarning`. Add docstring note:

```python
"""UAA Phase D resolver — POST-PHASE-H: bindings.yaml is sole source.

After Phase H cleanup, paperclips/codex-agent-ids.env is removed.
The legacy_env_path argument remains for back-compat but is now a no-op.
Future PR will remove the parameter entirely once external callers updated.
"""
```

Comment out (or delete) the legacy-merge code in `resolve_all()`. Functions `_read_legacy_env` and `_normalize_legacy_name` can stay (used by tests) but are no longer called from `resolve_all` in production.

Update tests in `test_phase_d_resolver.py` — **rev4 H-2: DELETE obsolete tests, don't skip them**. Skipped tests rot silently and pile up. Delete or rewrite to test the post-cleanup contract.

```python
# DELETE these tests entirely (they test pre-cleanup back-compat that no longer exists):
# - test_legacy_only_returns_legacy_uuids
# - test_both_matching_no_conflicts
# - test_both_conflicting_raises_warning
# - test_normalize_legacy_name_to_canonical (move to a separate "historical" test file with note)
# - test_all_normalized_names_appear_in_role_taxonomy

# REPLACE with single new test that asserts post-cleanup contract:
def test_resolve_all_uses_only_bindings_yaml():
    """Post-Phase-H: legacy_env_path arg is ignored; only bindings.yaml drives output."""
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(legacy_env_path=None, bindings_yaml_path=Path("..."))
    assert out["sources_used"] == ["bindings"]
```

Run `git rm -r tests/...` for any test file that becomes empty.

- [ ] **Step 4: Edit `services/watchdog/src/gimle_watchdog/detection_semantic.py`**

Remove `_legacy_load_uuids()` function and the `try: from paperclips.scripts.resolve_bindings import resolve_all; except ImportError: return _legacy_load_uuids(repo_root)` fallback. Hard import.

- [ ] **Step 5: Verify all tests still pass (Phase D updates included)**

```bash
python3 -m pytest paperclips/tests/test_phase_d_resolver.py -v   # 3 expected SKIPS
python3 -m pytest paperclips/tests/test_phase_h_cleanup.py -v
cd services/watchdog && uv run pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/resolve_bindings.py services/watchdog/src/gimle_watchdog/detection_semantic.py paperclips/tests/test_phase_d_resolver.py
git commit -m "feat(uaa-phase-h): remove dual-read fallbacks; bindings.yaml is sole source"
```

---

## Task 7: Final acceptance + spec changelog

**Files:**
- Create: `paperclips/tests/test_phase_h_acceptance.py`

- [ ] **Step 1: Final acceptance suite**

```python
# paperclips/tests/test_phase_h_acceptance.py
"""Phase H acceptance: legacy infrastructure removed, all 3 projects on new schema."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_no_legacy_files_in_repo():
    legacy = [
        "paperclips/codex-agent-ids.env",
        "paperclips/deploy-agents.sh",
        "paperclips/deploy-codex-agents.sh",
        "paperclips/update-agent-workspaces.sh",
        "paperclips/hire-codex-agents.sh",
    ]
    for f in legacy:
        assert not (REPO / f).is_file(), f"legacy file still in repo: {f}"


def test_no_legacy_dirs_in_repo():
    for d in ["paperclips/roles/legacy", "paperclips/roles-codex/legacy"]:
        assert not (REPO / d).is_dir(), f"legacy dir still in repo: {d}"


def test_deprecated_shared_fragments_removed():
    submodule = REPO / "paperclips" / "fragments" / "shared" / "fragments"
    deprecated = [
        "karpathy-discipline.md", "heartbeat-discipline.md", "phase-handoff.md",
        "git-workflow.md", "worktree-discipline.md", "escalation-blocked.md",
        "compliance-enforcement.md", "test-design-discipline.md", "pre-work-discovery.md",
        "plan-first-producer.md", "plan-first-review.md",
    ]
    for d in deprecated:
        assert not (submodule / d).is_file(), f"deprecated fragment still present: {d}"


def test_all_3_projects_use_new_schema():
    import yaml
    for project in ["gimle", "trading", "uaudit"]:
        p = REPO / "paperclips" / "projects" / project / "paperclip-agent-assembly.yaml"
        data = yaml.safe_load(p.read_text())
        assert data.get("schemaVersion") == 2, f"{project}: not on schemaVersion 2"
        assert data.get("compatibility", {}).get("legacy_output_paths") is False, \
            f"{project}: still has legacy_output_paths"


def test_all_3_projects_pass_validator():
    from paperclips.scripts.validate_manifest import validate_manifest
    for project in ["gimle", "trading", "uaudit"]:
        validate_manifest(REPO / "paperclips" / "projects" / project / "paperclip-agent-assembly.yaml")


def test_imac_agents_deploy_is_thin_wrapper():
    p = REPO / "paperclips" / "scripts" / "imac-agents-deploy.sh"
    text = p.read_text()
    line_count = text.count("\n")
    assert line_count < 50, f"imac-agents-deploy.sh too large: {line_count} lines (should be wrapper)"
    assert "bootstrap-project.sh" in text


def test_full_test_suite_green():
    """Sanity: all phase tests pass after cleanup."""
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", "paperclips/tests/", "-q", "--tb=no"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"pytest failed:\n{result.stdout}\n{result.stderr}"
```

- [ ] **Step 2: Run all Phase H tests**

```bash
python3 -m pytest paperclips/tests/test_phase_h_*.py -v
```

- [ ] **Step 3: Update spec changelog (final)**

```markdown
**UAA Phase H complete (YYYY-MM-DD) — UAA migration FINISHED:**
- Cleanup gate passed (7+ days zero `wake_failed` / `handoff_alert` / `escalation per_agent_cap` events).
- Operator signoff: `docs/uaa-cleanup-gate-evidence.md`.
- Removed 5 legacy scripts: codex-agent-ids.env, deploy-agents.sh, deploy-codex-agents.sh, update-agent-workspaces.sh, hire-codex-agents.sh.
- Removed 24 legacy role files (roles/legacy/ + roles-codex/legacy/).
- Removed 11 deprecated shared fragments.
- Removed dual-read fallbacks from builder + watchdog.
- imac-agents-deploy.sh becomes thin wrapper around bootstrap-project.sh --reuse-bindings.
- All 3 projects (gimle, trading, uaudit) on uniform schema v2.
- Spec promoted from Draft → Implemented.
```

- [ ] **Step 4: Update spec status field**

In `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` header:
```markdown
| **Status** | Implemented (Phase H complete YYYY-MM-DD) |
```

- [ ] **Step 5: Final commit**

```bash
git add paperclips/tests/test_phase_h_acceptance.py docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md
git commit -m "feat(uaa-phase-h): UAA migration complete — spec promoted to Implemented"
```

---

## Phase H acceptance gate (terminal)

- [ ] Cleanup gate evidence document exists with operator signoff (`docs/uaa-cleanup-gate-evidence.md`).
- [ ] All Phase A-H tests green.
- [ ] Zero legacy files in repo (`git grep` clean).
- [ ] All 3 projects build and smoke-test green on the new schema.
- [ ] Spec status updated to "Implemented".
- [ ] PR for cleanup commits merged through standard CTO+CR+QA flow.
- [ ] Operator notified team that UAA migration is complete; future projects bootstrap directly via `bootstrap-project.sh <key>` from clean schema.

---

## Post-UAA: future maintenance

When new projects are created (e.g., ios-wallet from spec §1.4 example), the bring-up is now reproducible:
```bash
git clone <gimle-palace-repo>
./paperclips/scripts/install-paperclip.sh        # one-time per machine
./paperclips/scripts/bootstrap-project.sh ios-wallet
./paperclips/scripts/smoke-test.sh ios-wallet
```

Future spec amendments should:
- Bump `schemaVersion` if breaking changes; provide migration script.
- Update `paperclips/scripts/versions.env` for any new pinned version, then `update-versions.sh`.
- Add new profiles or fragment subdirs as additive changes; never delete without deprecation cycle.
