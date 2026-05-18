# UAA Phase D — Dual-Read Seam

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Spec:** `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §10.1
**Owner:** `operator` (per spec §14.2 — affects state resolution for ALL agents during transition)
**Estimate:** 2 days
**Prereq:** Phase C complete (new bindings.yaml format exists; legacy `codex-agent-ids.env` still in repo)
**Blocks:** Phases E/F/G migrations (each project migrates to new bindings; dual-read keeps legacy working until cleanup gate)

**Goal:** Builder + watchdog + scripts read BOTH legacy `paperclips/codex-agent-ids.env` (and similar) AND new `~/.paperclip/projects/<key>/bindings.yaml`. Warn on conflict (different UUIDs for same agent name). Preserve legacy `paperclips/deploy-agents.sh` + `hire-codex-agents.sh` callsites until §10.5 cleanup gate.

**Architecture:** Single source-of-truth resolver (`paperclips/scripts/resolve_bindings.py`) that consults both sources in priority order: new bindings.yaml first; fall back to legacy env file; warn if both present and disagree. All consumers (builder, watchdog config generation, deploy scripts) call this resolver instead of reading sources directly.

**Tech Stack:**
- Python 3.12+ stdlib + pyyaml
- Existing watchdog Python (`services/watchdog/src/gimle_watchdog/`)
- Bash scripts call resolver via `python3 -m paperclips.scripts.resolve_bindings <project> <agent_name>`

---

## File Structure

### Created

```
paperclips/scripts/resolve_bindings.py        # NEW: single resolver, 3 sources
paperclips/tests/test_phase_d_resolver.py     # NEW: dual-read precedence + conflict warning
paperclips/tests/test_phase_d_integration.py  # NEW: builder + watchdog read via resolver
paperclips/tests/fixtures/phase_d/
├── codex-agent-ids.env                       # legacy fixture
├── bindings_matching.yaml                    # same UUIDs as legacy → no warning
├── bindings_conflicting.yaml                 # different UUID → warning
└── bindings_only_new.yaml                    # legacy missing the agent → use new only
```

### Modified

```
paperclips/scripts/build_project_compat.py        # consume resolver instead of direct file reads
services/watchdog/src/gimle_watchdog/config.py    # accept agent_uuids from resolver (currently doesn't read env files)
paperclips/scripts/migrate-bindings.sh            # cross-check legacy vs new (Phase C wrote it; Phase D uses resolver)
paperclips/scripts/bootstrap-project.sh           # call resolver during step 4 (hire/reuse)
```

---

## Task 1: Create `resolve_bindings.py` with precedence rules

**Files:**
- Create: `paperclips/scripts/resolve_bindings.py`
- Test: `paperclips/tests/test_phase_d_resolver.py`
- Create: `paperclips/tests/fixtures/phase_d/codex-agent-ids.env`
- Create: `paperclips/tests/fixtures/phase_d/bindings_matching.yaml`
- Create: `paperclips/tests/fixtures/phase_d/bindings_conflicting.yaml`
- Create: `paperclips/tests/fixtures/phase_d/bindings_only_new.yaml`

- [ ] **Step 1: Create fixtures**

`paperclips/tests/fixtures/phase_d/codex-agent-ids.env`:
```
CX_CTO_AGENT_ID=da97dbd9-6627-48d0-b421-66af0750eacf
CX_PYTHON_ENGINEER_AGENT_ID=e010d305-22f7-4f5c-9462-e6526b195b19
CX_QA_ENGINEER_AGENT_ID=99d5f8f8-822f-4ddb-baaa-0bdaec6f9399
```

`paperclips/tests/fixtures/phase_d/bindings_matching.yaml`:
```yaml
schemaVersion: 2
company_id: "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
agents:
  CXCTO: "da97dbd9-6627-48d0-b421-66af0750eacf"
  CXPythonEngineer: "e010d305-22f7-4f5c-9462-e6526b195b19"
  CXQAEngineer: "99d5f8f8-822f-4ddb-baaa-0bdaec6f9399"
```

`paperclips/tests/fixtures/phase_d/bindings_conflicting.yaml`:
```yaml
schemaVersion: 2
company_id: "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
agents:
  CXCTO: "DIFFERENT-uuid-from-legacy"
  CXPythonEngineer: "e010d305-22f7-4f5c-9462-e6526b195b19"
  CXQAEngineer: "99d5f8f8-822f-4ddb-baaa-0bdaec6f9399"
```

`paperclips/tests/fixtures/phase_d/bindings_only_new.yaml`:
```yaml
schemaVersion: 2
company_id: "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
agents:
  CXCTO: "da97dbd9-6627-48d0-b421-66af0750eacf"
  CXPythonEngineer: "e010d305-22f7-4f5c-9462-e6526b195b19"
  CXQAEngineer: "99d5f8f8-822f-4ddb-baaa-0bdaec6f9399"
  CXNewAgent: "fresh-uuid-only-in-bindings"
```

- [ ] **Step 2: Failing test**

```python
# paperclips/tests/test_phase_d_resolver.py
"""Phase D: dual-read precedence + conflict detection."""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "paperclips" / "tests" / "fixtures" / "phase_d"


def test_legacy_only_returns_legacy_uuids():
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=None,
    )
    assert out["agents"]["CXCTO"] == "da97dbd9-6627-48d0-b421-66af0750eacf"
    assert out["sources_used"] == ["legacy"]
    assert out["conflicts"] == []


def test_bindings_only_returns_new_uuids():
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(
        legacy_env_path=None,
        bindings_yaml_path=FIX / "bindings_only_new.yaml",
    )
    assert out["agents"]["CXCTO"] == "da97dbd9-6627-48d0-b421-66af0750eacf"
    assert out["sources_used"] == ["bindings"]
    assert "CXNewAgent" in out["agents"]


def test_both_matching_no_conflicts():
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=FIX / "bindings_matching.yaml",
    )
    assert set(out["sources_used"]) == {"legacy", "bindings"}
    assert out["conflicts"] == []


def test_both_conflicting_raises_warning():
    from paperclips.scripts.resolve_bindings import resolve_all, BindingsConflictWarning
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = resolve_all(
            legacy_env_path=FIX / "codex-agent-ids.env",
            bindings_yaml_path=FIX / "bindings_conflicting.yaml",
        )
    # Bindings wins (precedence: new > legacy)
    assert out["agents"]["CXCTO"] == "DIFFERENT-uuid-from-legacy"
    # Conflict captured
    assert len(out["conflicts"]) == 1
    assert out["conflicts"][0]["agent"] == "CXCTO"
    assert out["conflicts"][0]["legacy"] == "da97dbd9-6627-48d0-b421-66af0750eacf"
    assert out["conflicts"][0]["bindings"] == "DIFFERENT-uuid-from-legacy"
    # Warning emitted
    conflict_warnings = [w for w in caught if issubclass(w.category, BindingsConflictWarning)]
    assert len(conflict_warnings) == 1


def test_normalize_legacy_name_to_canonical():
    """env-var → canonical name MUST match watchdog/role_taxonomy.py exactly."""
    from paperclips.scripts.resolve_bindings import _normalize_legacy_name
    # Acronym preserved (per role_taxonomy.py entries):
    assert _normalize_legacy_name("CX_CTO_AGENT_ID") == "CXCTO"
    assert _normalize_legacy_name("CX_QA_ENGINEER_AGENT_ID") == "CXQAEngineer"
    assert _normalize_legacy_name("CX_MCP_ENGINEER_AGENT_ID") == "CXMCPEngineer"
    # PascalCase for non-acronym words:
    assert _normalize_legacy_name("CX_PYTHON_ENGINEER_AGENT_ID") == "CXPythonEngineer"
    assert _normalize_legacy_name("CX_CODE_REVIEWER_AGENT_ID") == "CXCodeReviewer"
    # CODEX_ prefix:
    assert _normalize_legacy_name("CODEX_ARCHITECT_REVIEWER_AGENT_ID") == "CodexArchitectReviewer"


def test_all_normalized_names_appear_in_role_taxonomy():
    """Smoke: every name produced by normalization is recognized by watchdog taxonomy."""
    import sys
    sys.path.insert(0, str(REPO / "services" / "watchdog" / "src"))
    from gimle_watchdog.role_taxonomy import _ROLE_CLASS_RAW
    from paperclips.scripts.resolve_bindings import _read_legacy_env

    legacy_path = REPO / "paperclips" / "codex-agent-ids.env"
    if not legacy_path.is_file():
        import pytest
        pytest.skip("legacy env file already removed (post Phase H)")
    extracted = _read_legacy_env(legacy_path)
    unknown = [n for n in extracted if n not in _ROLE_CLASS_RAW]
    assert not unknown, (
        f"normalization produces names unknown to watchdog taxonomy: {unknown}\n"
        f"Either fix _normalize_legacy_name() or add entries to "
        f"services/watchdog/src/gimle_watchdog/role_taxonomy.py"
    )


def test_resolve_one_agent_returns_uuid():
    from paperclips.scripts.resolve_bindings import resolve_one
    uuid = resolve_one(
        agent_name="CXCTO",
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=FIX / "bindings_matching.yaml",
    )
    assert uuid == "da97dbd9-6627-48d0-b421-66af0750eacf"


def test_resolve_one_missing_returns_none():
    from paperclips.scripts.resolve_bindings import resolve_one
    uuid = resolve_one(
        agent_name="NonexistentAgent",
        legacy_env_path=FIX / "codex-agent-ids.env",
        bindings_yaml_path=FIX / "bindings_matching.yaml",
    )
    assert uuid is None


def test_no_sources_raises():
    from paperclips.scripts.resolve_bindings import resolve_all
    import pytest
    with pytest.raises(FileNotFoundError):
        resolve_all(legacy_env_path=None, bindings_yaml_path=None)
```

- [ ] **Step 3: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_d_resolver.py -v
```

- [ ] **Step 4: Create `paperclips/scripts/resolve_bindings.py`**

```python
"""UAA Phase D: dual-read resolver — bindings.yaml (new) + codex-agent-ids.env (legacy).

Precedence: new (bindings.yaml) > legacy (env). Conflicts emit BindingsConflictWarning.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

import yaml


class BindingsConflictWarning(UserWarning):
    """Emitted when same agent has different UUID in legacy vs new source."""
    pass


def _normalize_legacy_name(env_var: str) -> str:
    """CX_PYTHON_ENGINEER_AGENT_ID → CXPythonEngineer.

    Output MUST match canonical names in services/watchdog/src/gimle_watchdog/role_taxonomy.py
    (verified against develop@c7b1310 — entries like CXCTO, CXMCPEngineer, CXQAEngineer
    preserve acronym case; entries like CXPythonEngineer, CXCodeReviewer use PascalCase).

    Algorithm:
    - Strip _AGENT_ID suffix.
    - Special case: CX_ prefix → "CX" prefix on the result.
    - Special case: CODEX_ prefix → preserve "Codex" prefix.
    - Snake_case → PascalCase, with PRESERVED ACRONYMS (CTO, QA, MCP, CR, CEO, API).
    """
    PRESERVED_ACRONYMS = {"CTO", "CEO", "QA", "MCP", "CR", "API", "URL", "UUID"}

    name = env_var
    if name.endswith("_AGENT_ID"):
        name = name[: -len("_AGENT_ID")]

    parts = name.split("_")
    if not parts:
        return name

    prefix = ""
    rest = parts
    if parts[0] == "CX":
        prefix = "CX"
        rest = parts[1:]
    elif parts[0] == "CODEX":
        prefix = "Codex"
        rest = parts[1:]

    out_parts: list[str] = []
    for p in rest:
        if p in PRESERVED_ACRONYMS:
            out_parts.append(p)
        else:
            out_parts.append(p.capitalize())
    return prefix + "".join(out_parts)


def _read_legacy_env(path: Path) -> dict[str, str]:
    """Parse legacy KEY=VALUE env file → {canonical_agent_name: uuid}."""
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if not key.endswith("_AGENT_ID"):
            continue
        if not value:
            continue
        canonical = _normalize_legacy_name(key)
        out[canonical] = value
    return out


def _read_bindings_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: root must be mapping")
    agents = raw.get("agents", {})
    if not isinstance(agents, dict):
        raise ValueError(f"{path}: agents must be mapping")
    return {
        "company_id": raw.get("company_id"),
        "agents": agents,
    }


def resolve_all(
    *,
    legacy_env_path: Path | None,
    bindings_yaml_path: Path | None,
) -> dict[str, Any]:
    """Merge sources. Bindings precedence > legacy. Conflicts warned but bindings wins.

    Returns:
        {
          "company_id": str | None,
          "agents": {agent_name: uuid, ...},  # merged
          "sources_used": ["legacy", "bindings"],  # subset
          "conflicts": [{"agent": ..., "legacy": ..., "bindings": ...}],
        }
    """
    sources_used: list[str] = []
    conflicts: list[dict[str, str]] = []

    legacy: dict[str, str] = {}
    if legacy_env_path is not None and legacy_env_path.is_file():
        legacy = _read_legacy_env(legacy_env_path)
        sources_used.append("legacy")

    bindings: dict[str, Any] = {"company_id": None, "agents": {}}
    if bindings_yaml_path is not None and bindings_yaml_path.is_file():
        bindings = _read_bindings_yaml(bindings_yaml_path)
        sources_used.append("bindings")

    if not sources_used:
        raise FileNotFoundError(
            f"no sources available (legacy={legacy_env_path}, bindings={bindings_yaml_path})"
        )

    # Merge: start from legacy, override with bindings; record conflicts
    merged: dict[str, str] = dict(legacy)
    for name, uuid in bindings["agents"].items():
        if name in merged and merged[name] != uuid:
            conflicts.append({
                "agent": name,
                "legacy": merged[name],
                "bindings": uuid,
            })
            warnings.warn(
                f"conflict for agent {name!r}: legacy={merged[name]!r}, bindings={uuid!r}; "
                f"using bindings value (resolve via cleanup gate per spec §10.5)",
                BindingsConflictWarning,
                stacklevel=2,
            )
        merged[name] = uuid

    return {
        "company_id": bindings.get("company_id"),
        "agents": merged,
        "sources_used": sources_used,
        "conflicts": conflicts,
    }


def resolve_one(
    *,
    agent_name: str,
    legacy_env_path: Path | None = None,
    bindings_yaml_path: Path | None = None,
) -> str | None:
    """Return UUID for agent_name, or None if not found in any source."""
    try:
        result = resolve_all(legacy_env_path=legacy_env_path, bindings_yaml_path=bindings_yaml_path)
    except FileNotFoundError:
        return None
    return result["agents"].get(agent_name)


def main() -> int:
    """CLI: print UUID for agent_name, or exit 1 if not found."""
    import argparse
    parser = argparse.ArgumentParser(description="UAA dual-read bindings resolver")
    parser.add_argument("project_key")
    parser.add_argument("--agent-name", required=False, help="single-agent lookup")
    parser.add_argument("--legacy-env", help="path to legacy codex-agent-ids.env")
    parser.add_argument("--bindings", help="path to ~/.paperclip/projects/<key>/bindings.yaml")
    args = parser.parse_args()

    repo_root = Path.cwd()
    home = Path.home()

    legacy = Path(args.legacy_env) if args.legacy_env else (
        repo_root / "paperclips" / "codex-agent-ids.env"
        if args.project_key == "gimle"
        else None
    )
    bindings = Path(args.bindings) if args.bindings else (
        home / ".paperclip" / "projects" / args.project_key / "bindings.yaml"
    )

    try:
        result = resolve_all(legacy_env_path=legacy, bindings_yaml_path=bindings)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.agent_name:
        uuid = result["agents"].get(args.agent_name)
        if uuid is None:
            print(f"ERROR: agent {args.agent_name!r} not found", file=sys.stderr)
            return 1
        print(uuid)
    else:
        import json
        print(json.dumps(result, indent=2, default=str))

    if result["conflicts"]:
        print(
            f"WARNING: {len(result['conflicts'])} bindings conflicts (see stderr)",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_d_resolver.py -v
```

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/resolve_bindings.py paperclips/tests/test_phase_d_resolver.py paperclips/tests/fixtures/phase_d/
git commit -m "feat(uaa-phase-d): resolve_bindings.py — dual-read with bindings>legacy precedence + conflict warning"
```

---

## Task 2: Wire builder to use resolver instead of direct file reads

**Files:**
- Modify: `paperclips/scripts/build_project_compat.py`
- Test: `paperclips/tests/test_phase_d_integration.py`

- [ ] **Step 1: Failing test**

```python
# paperclips/tests/test_phase_d_integration.py
"""Phase D: integration — builder reads via resolver, no direct file access."""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_builder_uses_resolver():
    """build_project_compat.py imports resolve_bindings."""
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    assert "from paperclips.scripts.resolve_bindings import" in text or \
           "import paperclips.scripts.resolve_bindings" in text


def test_builder_does_not_read_legacy_env_directly():
    """build_project_compat.py should NOT directly open codex-agent-ids.env."""
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    # Direct .env opens are forbidden in builder post-Phase D
    direct_reads = re.findall(r"(open|read_text|Path)\([^)]*codex-agent-ids\.env", text)
    assert not direct_reads, f"builder still reads legacy env directly: {direct_reads}"


def test_builder_template_value_resolution_via_resolver():
    """{{bindings.agents.<name>}} resolves through dual-read."""
    # Build trading and check that any agent UUID in rendered output came from resolver.
    # Trading currently has UUIDs inline in manifest — pre-Phase E migration.
    # After this task, builder still resolves from manifest fallback.
    subprocess.run(
        ["./paperclips/build.sh", "--project", "trading", "--target", "codex"],
        cwd=REPO, check=True, capture_output=True,
    )
    # Pass if build doesn't error.
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_d_integration.py -v
```

- [ ] **Step 3: Modify `build_project_compat.py`**

Add import at top:
```python
from paperclips.scripts.resolve_bindings import resolve_all
```

Modify `_build_template_sources()` (introduced in Phase B, Task 6) — replace `_load_host_yaml(...)` for bindings with resolver:

```python
def _build_template_sources(
    manifest_values: dict[str, str],
    agent_values: dict[str, str] | None,
    repo_root: Path,
) -> dict:
    """Construct sources dict for template resolver per §6.5, using dual-read for bindings."""
    project_key = manifest_values.get("project.key", "")
    home = Path.home()

    # Dual-read: bindings.yaml (new) + codex-agent-ids.env (legacy, gimle only)
    bindings_path = home / ".paperclip" / "projects" / project_key / "bindings.yaml"
    legacy_path = (
        repo_root / "paperclips" / "codex-agent-ids.env"
        if project_key == "gimle"
        else None
    )
    bindings_data: dict = {}
    try:
        merged = resolve_all(
            legacy_env_path=legacy_path,
            bindings_yaml_path=bindings_path,
        )
        bindings_data = {
            "company_id": merged.get("company_id"),
            "agents": merged.get("agents", {}),
        }
    except FileNotFoundError:
        # Build OK without bindings (early bootstrap, no project hired yet)
        pass

    sources: dict = {
        "manifest": {
            "project": {k.split(".", 1)[1]: v for k, v in manifest_values.items() if k.startswith("project.")},
            "domain": {k.split(".", 1)[1]: v for k, v in manifest_values.items() if k.startswith("domain.")},
            "mcp": {k.split(".", 1)[1]: v for k, v in manifest_values.items() if k.startswith("mcp.")},
        },
        "agent": agent_values or {},
        "bindings": bindings_data,
        "paths": _load_host_yaml(repo_root, project_key, "paths.yaml"),
        "plugins": _load_host_yaml(repo_root, project_key, "plugins.yaml"),
    }
    return sources
```

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_d_integration.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/build_project_compat.py paperclips/tests/test_phase_d_integration.py
git commit -m "feat(uaa-phase-d): builder reads bindings via dual-read resolver"
```

---

## Task 3: Wire watchdog to use resolver

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/config.py`
- Test: `services/watchdog/tests/test_phase_d_resolver_integration.py`

The watchdog currently doesn't read agent UUIDs at all (it queries paperclip API). But its handoff-detector (`detection_semantic.py:_detect_wrong_assignee`) cross-references against a hired-agents list loaded via `load_team_uuids_from_repo()`. That function currently reads `paperclips/codex-agent-ids.env` directly. Wire it through resolver.

- [ ] **Step 1: Inspect current implementation**

```bash
grep -n "load_team_uuids_from_repo\|codex-agent-ids" services/watchdog/src/gimle_watchdog/*.py
```

- [ ] **Step 2: Failing test**

```python
# services/watchdog/tests/test_phase_d_resolver_integration.py
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_load_team_uuids_uses_resolver():
    """load_team_uuids_from_repo must call resolve_all (dual-read)."""
    text = (REPO / "services" / "watchdog" / "src" / "gimle_watchdog" / "detection_semantic.py").read_text()
    assert "resolve_all" in text or "resolve_bindings" in text


def test_load_team_uuids_reads_both_sources(tmp_path, monkeypatch):
    """When both legacy + bindings exist, function returns merged set."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Set up fake bindings + legacy
    proj = tmp_path / ".paperclip" / "projects" / "gimle"
    proj.mkdir(parents=True)
    (proj / "bindings.yaml").write_text(
        'schemaVersion: 2\ncompany_id: "abc"\nagents:\n  NewAgent: "uuid-from-bindings"\n'
    )
    legacy = tmp_path / "fake-repo" / "paperclips" / "codex-agent-ids.env"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("CX_CTO_AGENT_ID=uuid-from-legacy\n")
    from paperclips.scripts.resolve_bindings import resolve_all
    out = resolve_all(legacy_env_path=legacy, bindings_yaml_path=proj / "bindings.yaml")
    assert "uuid-from-bindings" in out["agents"].values()
    assert "uuid-from-legacy" in out["agents"].values()
```

- [ ] **Step 3: Verify FAIL**

```bash
cd services/watchdog
uv run pytest tests/test_phase_d_resolver_integration.py -v
```

- [ ] **Step 4: Modify `detection_semantic.py`**

Find existing `load_team_uuids_from_repo()` (currently reads `codex-agent-ids.env` directly), replace with:

```python
def load_team_uuids_from_repo(repo_root: Path) -> dict[str, set[str]]:
    """Load known team UUIDs via dual-read (bindings.yaml + legacy codex-agent-ids.env).

    Returns {"claude": {uuid, ...}, "codex": {uuid, ...}}.
    """
    # Add to module-level imports:
    # import sys; sys.path.insert(0, str(repo_root))
    # from paperclips.scripts.resolve_bindings import resolve_all

    import sys
    sys.path.insert(0, str(repo_root))
    try:
        from paperclips.scripts.resolve_bindings import resolve_all
    except ImportError:
        log.warning("resolve_bindings not importable; falling back to legacy env-only read")
        return _legacy_load_uuids(repo_root)

    legacy = repo_root / "paperclips" / "codex-agent-ids.env"
    home = Path.home()
    out: dict[str, set[str]] = {"claude": set(), "codex": set()}

    # Iterate per-project bindings (gimle, trading, uaudit, plus any future)
    projects_dir = home / ".paperclip" / "projects"
    if not projects_dir.is_dir():
        # Pre-Phase-E: only legacy exists
        if legacy.is_file():
            data = resolve_all(legacy_env_path=legacy, bindings_yaml_path=None)
            # Legacy is codex-only
            for uuid in data["agents"].values():
                out["codex"].add(uuid)
        return out

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        bindings = project_dir / "bindings.yaml"
        try:
            data = resolve_all(
                legacy_env_path=legacy if project_dir.name == "gimle" else None,
                bindings_yaml_path=bindings if bindings.is_file() else None,
            )
        except FileNotFoundError:
            continue

        # Read manifest to get authoritative target per agent (NOT name-prefix heuristic).
        # uaudit has UWICTO/UWAKotlinAuditor — codex agents that don't start with CX.
        manifest_path = repo_root / "paperclips" / "projects" / project_dir.name / "paperclip-agent-assembly.yaml"
        target_by_name: dict[str, str] = {}
        if manifest_path.is_file():
            try:
                import yaml
                m = yaml.safe_load(manifest_path.read_text())
                for a in m.get("agents", []):
                    target_by_name[a["agent_name"]] = a.get("target", "claude")
            except Exception as e:
                log.warning("watchdog: could not read manifest for %s: %s", project_dir.name, e)

        for name, uuid in data["agents"].items():
            target = target_by_name.get(name)
            if target is None:
                # Pre-Phase-A: legacy gimle env has names not in manifest. Codex env file = codex agents.
                target = "codex" if project_dir.name == "gimle" and name.startswith("CX") else "claude"
            if target not in out:
                # Defensive: unknown target string treated as claude
                target = "claude"
            out[target].add(uuid)

        if data.get("conflicts"):
            log.warning(
                "watchdog: bindings conflicts for project %s — %d agents differ between legacy and new",
                project_dir.name, len(data["conflicts"]),
            )

    return out


def _legacy_load_uuids(repo_root: Path) -> dict[str, set[str]]:
    """Fallback when resolve_bindings unavailable."""
    out = {"claude": set(), "codex": set()}
    legacy = repo_root / "paperclips" / "codex-agent-ids.env"
    if legacy.is_file():
        for line in legacy.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                _, _, val = line.partition("=")
                out["codex"].add(val.strip().strip('"'))
    return out
```

- [ ] **Step 5: Verify PASS**

```bash
cd services/watchdog
uv run pytest tests/test_phase_d_resolver_integration.py -v
# Also re-run all watchdog tests to catch regressions
uv run pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/detection_semantic.py services/watchdog/tests/test_phase_d_resolver_integration.py
git commit -m "feat(uaa-phase-d): watchdog reads team UUIDs via dual-read resolver"
```

---

## Task 4: Migrate-bindings.sh adds conflict-detection mode

**Files:**
- Modify: `paperclips/scripts/migrate-bindings.sh`

- [ ] **Step 1: Failing test**

```python
# paperclips/tests/test_phase_d_migrate_conflict.py
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_migrate_warns_on_conflict(tmp_path, monkeypatch):
    """If a project has both legacy + bindings with different UUIDs, migrate warns."""
    # Setup: create a fake gimle setup with conflicting sources
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / ".paperclip" / "projects" / "gimle"
    proj.mkdir(parents=True)
    (proj / "bindings.yaml").write_text(
        'schemaVersion: 2\ncompany_id: "abc"\nagents:\n  CXCTO: "different-uuid"\n'
    )
    # Run with --check-conflicts mode
    out = subprocess.run(
        ["bash", str(REPO / "paperclips" / "scripts" / "migrate-bindings.sh"), "gimle", "--check-conflicts"],
        cwd=REPO, capture_output=True, text=True,
        env={**dict(__import__("os").environ), "HOME": str(tmp_path)},
    )
    assert "conflict" in out.stderr.lower() or "different" in out.stderr.lower() or out.returncode != 0
```

- [ ] **Step 2: Add `--check-conflicts` flag to `migrate-bindings.sh`**

In existing `paperclips/scripts/migrate-bindings.sh`, add at top of arg-parse loop:
```bash
CHECK_CONFLICTS=0
# ... in case statement ...
    --check-conflicts) CHECK_CONFLICTS=1; shift ;;
```

At end of script, before `log ok "wrote $target_file"`, add:
```bash
if [ "$CHECK_CONFLICTS" -eq 1 ]; then
  log info "running dual-read conflict check"
  PYTHONPATH="${REPO_ROOT}" python3 -c "
from pathlib import Path
import sys
from paperclips.scripts.resolve_bindings import resolve_all

legacy = Path('${legacy_env:-/dev/null}')
bindings = Path('${target_file}')

try:
    out = resolve_all(legacy_env_path=legacy if legacy.is_file() else None,
                      bindings_yaml_path=bindings if bindings.is_file() else None)
except FileNotFoundError as e:
    print(f'no sources: {e}', file=sys.stderr)
    sys.exit(2)

if out['conflicts']:
    for c in out['conflicts']:
        print(f'CONFLICT: {c[\"agent\"]} legacy={c[\"legacy\"]} bindings={c[\"bindings\"]}', file=sys.stderr)
    sys.exit(1)
print('no conflicts')
"
fi
```

- [ ] **Step 3: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_d_migrate_conflict.py -v
```

- [ ] **Step 4: Commit**

```bash
git add paperclips/scripts/migrate-bindings.sh paperclips/tests/test_phase_d_migrate_conflict.py
git commit -m "feat(uaa-phase-d): migrate-bindings.sh --check-conflicts mode"
```

---

## Task 5: Phase D acceptance suite

**Files:**
- Create: `paperclips/tests/test_phase_d_acceptance.py`

- [ ] **Step 1: Acceptance**

```python
# paperclips/tests/test_phase_d_acceptance.py
"""Phase D acceptance: dual-read seam ready for migrations (E/F/G)."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_resolver_module_exists():
    assert (REPO / "paperclips" / "scripts" / "resolve_bindings.py").is_file()


def test_resolver_exports_required_api():
    from paperclips.scripts.resolve_bindings import resolve_all, resolve_one, BindingsConflictWarning
    assert callable(resolve_all)
    assert callable(resolve_one)


def test_builder_calls_resolver():
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    assert "resolve_bindings" in text


def test_watchdog_calls_resolver():
    text = (REPO / "services" / "watchdog" / "src" / "gimle_watchdog" / "detection_semantic.py").read_text()
    assert "resolve_bindings" in text


def test_legacy_files_still_present():
    """Legacy sources MUST remain in repo until cleanup gate (§10.5)."""
    assert (REPO / "paperclips" / "codex-agent-ids.env").is_file(), \
        "legacy file removed prematurely; cleanup happens in Phase H"


def test_no_direct_legacy_reads_in_consumers():
    """Builder + watchdog + scripts MUST go through resolver."""
    builder = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    # Allow comments + strings; check there's no read_text/open on the file path
    import re
    bad = re.findall(r"(open|read_text|Path)\([^)]*codex-agent-ids\.env", builder)
    assert not bad


def test_existing_phase_a_b_c_tests_still_pass():
    """No regression."""
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", "paperclips/tests/test_phase_a_*.py",
         "paperclips/tests/test_phase_b_*.py", "paperclips/tests/test_phase_c_*.py",
         "-v", "--tb=short"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Run + commit**

```bash
python3 -m pytest paperclips/tests/test_phase_d_*.py -v
git add paperclips/tests/test_phase_d_acceptance.py
git commit -m "test(uaa-phase-d): acceptance suite — dual-read seam ready for migrations"
```

- [ ] **Step 3: Update spec changelog**

Append:
```markdown
**Phase D complete (YYYY-MM-DD):**
- `resolve_bindings.py` provides dual-read (bindings.yaml > legacy codex-agent-ids.env, with conflict warning).
- Builder reads bindings via resolver (no direct file access).
- Watchdog (`detection_semantic.load_team_uuids_from_repo`) reads via resolver.
- `migrate-bindings.sh --check-conflicts` flags any UUID divergence pre-cleanup.
- Legacy files remain in repo; cleanup gated to §10.5.
```

```bash
git add docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md
git commit -m "docs(uaa-phase-d): mark Phase D complete in spec changelog"
```

---

## Phase D acceptance gate (before Phase E)

- [ ] All Phase D tests green.
- [ ] Phase A + B + C tests still green (regression check).
- [ ] Watchdog tests still green: `cd services/watchdog && uv run pytest`.
- [ ] `resolve_bindings.py --project gimle` returns valid JSON with merged UUIDs from both sources.
- [ ] Builder produces identical output for unchanged inputs (determinism preserved).
- [ ] No direct legacy-file reads remain in builder/watchdog/scripts (grep verified).
- [ ] Operator manual check: run `python3 -m paperclips.scripts.resolve_bindings gimle` on real machine — confirm both sources are listed in `sources_used`.
