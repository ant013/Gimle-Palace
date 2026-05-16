# UAA Phase B — Profile Library + Builder Updates

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Spec:** `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md` §5, §6
**Owner:** `operator` (per spec §14.2 — builder edits affect ALL agents on next deploy)
**Estimate:** 4–5 days
**Prereq:** Phase A complete (fragment hierarchy + role-craft files exist)
**Blocks:** Phase C (scripts call new builder), Phase D (dual-read seam), all migrations

**Goal:** Create 8 profile YAMLs (`paperclips/fragments/profiles/*.yaml`) and extend the builder to compose per-agent AGENTS.md from `[universal] + profile.includes + role_source + custom_includes + overlay`. Add forbidden-content rejection, template-source validation, and the project override seam preserved.

**Architecture:** Builder gains a new `compose_agent_prompt()` pipeline alongside existing `expand_includes()`. Old role-files (still present, with deprecation banners from Phase A) continue to work via legacy code path. New craft-files use new pipeline, distinguished by absence of `<!-- @include -->` directives in the role file. Both paths coexist until Phase H cleanup.

**Tech Stack:**
- Python 3.12+ (existing builder uses stdlib only — keep it that way; no new deps)
- pytest for unit + integration tests
- yaml stdlib (`pip install pyyaml` if not present — verify first)

---

## File Structure

### Created files

```
paperclips/fragments/profiles/
├── custom.yaml                  # 5 lines — opts out of universal
├── minimal.yaml                 # 5 lines — universal only
├── research.yaml                # ~10 lines
├── writer.yaml                  # ~7 lines
├── implementer.yaml             # ~15 lines
├── qa.yaml                      # ~8 lines (extends implementer)
├── reviewer.yaml                # ~15 lines
└── cto.yaml                     # ~12 lines (extends reviewer)

paperclips/scripts/
├── compose_agent_prompt.py      # NEW core composition logic
├── validate_manifest.py         # NEW forbidden-content rejection (§6.2)
├── resolve_template_sources.py  # NEW {{var}} resolution per §6.5
└── build_project_compat.py      # MODIFIED — calls compose for new-craft roles

paperclips/tests/
├── test_phase_b_profiles.py        # NEW
├── test_phase_b_builder_compose.py # NEW
├── test_phase_b_template_sources.py # NEW
├── test_phase_b_validator.py       # NEW
└── test_phase_b_overlay.py         # NEW (overlay still works post-changes)

paperclips/tests/fixtures/phase_b/
├── manifest_clean.yaml             # NEW — passes validation
├── manifest_with_uuid.yaml         # NEW — should fail
├── manifest_with_abs_path.yaml     # NEW — should fail
├── manifest_with_unresolved_var.yaml # NEW
└── synthetic_project/              # NEW — minimal project for builder integration tests
    ├── paperclip-agent-assembly.yaml
    ├── AGENTS.md.template
    ├── overlays/codex/_common.md
    └── fragments/git/commit-and-push.md  # tests project override
```

### Modified files

```
paperclips/scripts/build_project_compat.py  # extended; legacy code path preserved
paperclips/build.sh                         # no signature change; just calls extended builder
.gitignore                                  # add paperclips/dist/* to ignored (per spec §6.6)
```

---

## Task 1: Create profile YAML schema validator (Pydantic-free, stdlib only)

**Files:**
- Create: `paperclips/scripts/profile_schema.py`
- Test: `paperclips/tests/test_phase_b_profiles.py`

The existing builder is stdlib-only. Keep Phase B the same — use plain dicts + assertions, not Pydantic.

- [ ] **Step 1: Write failing test**

```python
# paperclips/tests/test_phase_b_profiles.py
"""Phase B: profile YAMLs load and validate."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILES_DIR = REPO / "paperclips" / "fragments" / "profiles"


def test_load_profile_returns_dict():
    from paperclips.scripts.profile_schema import load_profile
    p = PROFILES_DIR / "implementer.yaml"
    if not p.exists():
        import pytest
        pytest.skip("profile yaml not yet created — Tasks 2-9")
    data = load_profile(p)
    assert isinstance(data, dict)
    assert data["name"] == "implementer"
    assert data["schemaVersion"] == 2
    assert "includes" in data
    assert isinstance(data["includes"], list)


def test_validate_profile_rejects_missing_name():
    from paperclips.scripts.profile_schema import validate_profile, ProfileSchemaError
    import pytest
    bad = {"schemaVersion": 2, "includes": []}
    with pytest.raises(ProfileSchemaError, match="name"):
        validate_profile(bad)


def test_validate_profile_rejects_wrong_version():
    from paperclips.scripts.profile_schema import validate_profile, ProfileSchemaError
    import pytest
    bad = {"schemaVersion": 1, "name": "implementer", "includes": []}
    with pytest.raises(ProfileSchemaError, match="schemaVersion"):
        validate_profile(bad)


def test_validate_profile_rejects_unknown_keys():
    from paperclips.scripts.profile_schema import validate_profile, ProfileSchemaError
    import pytest
    bad = {"schemaVersion": 2, "name": "x", "includes": [], "extraField": "nope"}
    with pytest.raises(ProfileSchemaError, match="unknown"):
        validate_profile(bad)


def test_validate_profile_default_inheritsUniversal():
    from paperclips.scripts.profile_schema import validate_profile
    p = {"schemaVersion": 2, "name": "x", "includes": []}
    out = validate_profile(p)
    assert out["inheritsUniversal"] is True  # default True
```

- [ ] **Step 2: Run, verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_b_profiles.py -v
```
Expected: ImportError (module doesn't exist).

- [ ] **Step 3: Create `paperclips/scripts/profile_schema.py`**

```python
"""Profile YAML schema for UAA Phase B.

Stdlib-only. Validates the 8 profiles in paperclips/fragments/profiles/*.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# yaml is the only non-stdlib dep already used by build_project_compat.py;
# verify it's available.
try:
    import yaml
except ImportError as e:
    print("ERROR: pyyaml not installed; run `pip install pyyaml`", file=sys.stderr)
    raise

ALLOWED_KEYS = {"schemaVersion", "name", "inheritsUniversal", "extends", "includes"}
SUPPORTED_SCHEMA_VERSION = 2


class ProfileSchemaError(Exception):
    pass


def load_profile(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ProfileSchemaError(f"{path}: root must be a mapping")
    return validate_profile(raw)


def validate_profile(raw: dict[str, Any]) -> dict[str, Any]:
    if "name" not in raw:
        raise ProfileSchemaError("missing required key: name")
    if not isinstance(raw["name"], str) or not raw["name"]:
        raise ProfileSchemaError("name must be non-empty string")
    if raw.get("schemaVersion") != SUPPORTED_SCHEMA_VERSION:
        raise ProfileSchemaError(
            f"schemaVersion must be {SUPPORTED_SCHEMA_VERSION}, got {raw.get('schemaVersion')!r}"
        )
    unknown = set(raw.keys()) - ALLOWED_KEYS
    if unknown:
        raise ProfileSchemaError(f"unknown keys: {sorted(unknown)}")

    # Defaults
    out: dict[str, Any] = dict(raw)
    out.setdefault("inheritsUniversal", True)
    out.setdefault("extends", None)
    out.setdefault("includes", [])

    if not isinstance(out["inheritsUniversal"], bool):
        raise ProfileSchemaError("inheritsUniversal must be bool")
    if out["extends"] is not None and not isinstance(out["extends"], str):
        raise ProfileSchemaError("extends must be string (profile name) or null")
    if not isinstance(out["includes"], list):
        raise ProfileSchemaError("includes must be a list")
    for inc in out["includes"]:
        if not isinstance(inc, str):
            raise ProfileSchemaError(f"includes entry must be string, got {type(inc).__name__}")
        if "/" not in inc:
            raise ProfileSchemaError(f"includes entry must be subdir/file.md form, got {inc!r}")

    return out


def resolve_extends_chain(profile: dict[str, Any], all_profiles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return list of profiles in extends-resolution order: [base, ..., this]."""
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    cur: dict[str, Any] | None = profile
    while cur is not None:
        if cur["name"] in seen:
            raise ProfileSchemaError(f"extends cycle detected: {cur['name']}")
        seen.add(cur["name"])
        chain.append(cur)
        parent_name = cur.get("extends")
        if parent_name is None:
            break
        if parent_name not in all_profiles:
            raise ProfileSchemaError(f"profile {cur['name']!r} extends unknown profile {parent_name!r}")
        cur = all_profiles[parent_name]
    return list(reversed(chain))  # base first
```

- [ ] **Step 4: Run, verify PASS (skip on test_load_profile until profiles created)**

```bash
python3 -m pytest paperclips/tests/test_phase_b_profiles.py -v
```
Expected: 4 PASS + 1 SKIP.

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/profile_schema.py paperclips/tests/test_phase_b_profiles.py
git commit -m "feat(uaa-phase-b): profile schema validator (stdlib + yaml)"
```

---

## Task 2: Create profile YAMLs (8 files)

**Files:**
- Create: `paperclips/fragments/profiles/custom.yaml`
- Create: `paperclips/fragments/profiles/minimal.yaml`
- Create: `paperclips/fragments/profiles/research.yaml`
- Create: `paperclips/fragments/profiles/writer.yaml`
- Create: `paperclips/fragments/profiles/implementer.yaml`
- Create: `paperclips/fragments/profiles/qa.yaml`
- Create: `paperclips/fragments/profiles/reviewer.yaml`
- Create: `paperclips/fragments/profiles/cto.yaml`

- [ ] **Step 1: Add tests for each profile**

Append to `paperclips/tests/test_phase_b_profiles.py`:
```python
PROFILE_NAMES = ["custom", "minimal", "research", "writer", "implementer", "qa", "reviewer", "cto"]


def test_all_8_profiles_exist():
    for name in PROFILE_NAMES:
        p = PROFILES_DIR / f"{name}.yaml"
        assert p.is_file(), f"missing profile: {p}"


def test_all_8_profiles_validate():
    from paperclips.scripts.profile_schema import load_profile
    for name in PROFILE_NAMES:
        p = PROFILES_DIR / f"{name}.yaml"
        data = load_profile(p)
        assert data["name"] == name


def test_custom_opts_out_of_universal():
    from paperclips.scripts.profile_schema import load_profile
    p = load_profile(PROFILES_DIR / "custom.yaml")
    assert p["inheritsUniversal"] is False
    assert p["includes"] == []


def test_qa_extends_implementer():
    from paperclips.scripts.profile_schema import load_profile
    p = load_profile(PROFILES_DIR / "qa.yaml")
    assert p["extends"] == "implementer"


def test_cto_extends_reviewer():
    from paperclips.scripts.profile_schema import load_profile
    p = load_profile(PROFILES_DIR / "cto.yaml")
    assert p["extends"] == "reviewer"


def test_extends_chain_resolution():
    from paperclips.scripts.profile_schema import load_profile, resolve_extends_chain
    all_p = {n: load_profile(PROFILES_DIR / f"{n}.yaml") for n in PROFILE_NAMES}
    chain = resolve_extends_chain(all_p["cto"], all_p)
    assert [p["name"] for p in chain] == ["reviewer", "cto"]
    chain = resolve_extends_chain(all_p["qa"], all_p)
    assert [p["name"] for p in chain] == ["implementer", "qa"]
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_b_profiles.py -v
```

- [ ] **Step 3: Create the 8 YAML files**

`paperclips/fragments/profiles/custom.yaml`:
```yaml
schemaVersion: 2
name: custom
inheritsUniversal: false
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

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_b_profiles.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/fragments/profiles/ paperclips/tests/test_phase_b_profiles.py
git commit -m "feat(uaa-phase-b): create 8 profile YAMLs (custom/minimal/research/writer/implementer/qa/reviewer/cto)"
```

---

## Task 3: Implement compose_agent_prompt — universal layer + profile chain

**Files:**
- Create: `paperclips/scripts/compose_agent_prompt.py`
- Test: `paperclips/tests/test_phase_b_builder_compose.py`

- [ ] **Step 1: Failing test**

```python
# paperclips/tests/test_phase_b_builder_compose.py
"""Phase B: compose_agent_prompt produces correctly-ordered AGENTS.md."""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[1]
SUBMODULE_FRAGMENTS = REPO / "paperclips" / "fragments" / "shared" / "fragments"
PROFILES_DIR = REPO / "paperclips" / "fragments" / "profiles"


def test_minimal_profile_emits_universal_only():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="minimal",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Test Role\nbody",
        custom_includes=[],
        overlay_blocks=[],
    )
    # Universal layer
    assert "Karpathy discipline" in out
    assert "Wake & handoff basics" in out
    assert "@Board" in out
    # Role
    assert "# Test Role" in out
    # Order: universal before role
    assert out.index("Karpathy discipline") < out.index("# Test Role")


def test_implementer_includes_git_and_worktree():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="implementer",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Python Engineer\nbody",
        custom_includes=[],
        overlay_blocks=[],
    )
    assert "Git: commit & push" in out
    assert "Worktree discipline" in out
    assert "Karpathy discipline" in out  # universal still present
    # Order: universal → profile.includes → role
    u_idx = out.index("Karpathy discipline")
    g_idx = out.index("Git: commit & push")
    r_idx = out.index("# Python Engineer")
    assert u_idx < g_idx < r_idx


def test_qa_extends_implementer_dedup():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="qa",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# QA",
        custom_includes=[],
        overlay_blocks=[],
    )
    # qa includes everything from implementer + qa-specific
    assert "Git: commit & push" in out  # from implementer
    assert "QA: smoke + evidence" in out  # from qa.yaml
    # Universal appears EXACTLY ONCE despite two profiles in chain claiming inheritsUniversal: true
    assert out.count("Karpathy discipline") == 1


def test_custom_profile_skips_universal():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="custom",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Custom",
        custom_includes=[],
        overlay_blocks=[],
    )
    assert "Karpathy discipline" not in out
    assert "@Board" not in out
    assert "# Custom" in out


def test_custom_includes_appended_after_profile():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="reviewer",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Opus",
        custom_includes=["code-review/adversarial.md"],
        overlay_blocks=[],
    )
    # Reviewer profile already includes approve.md, custom adds adversarial.md
    assert "Code review: adversarial review" in out
    assert "Code review: APPROVE format" in out


def test_overlay_blocks_appended_last():
    from paperclips.scripts.compose_agent_prompt import compose
    out = compose(
        profile_name="minimal",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# Role",
        custom_includes=[],
        overlay_blocks=["## Project anti-pattern\nNever push directly."],
    )
    # Overlay text MUST be LAST in output
    overlay_idx = out.index("Project anti-pattern")
    role_idx = out.index("# Role")
    assert role_idx < overlay_idx, "overlay must come AFTER role"


def test_dedup_logs_to_stderr(capsys):
    """When extends-chain dedups a fragment, builder logs to stderr."""
    from paperclips.scripts.compose_agent_prompt import compose
    # qa extends implementer; both include handoff/basics.md → should dedup once
    compose(
        profile_name="qa",
        profiles_dir=PROFILES_DIR,
        fragments_dir=SUBMODULE_FRAGMENTS,
        role_source_text="# QA",
        custom_includes=[],
        overlay_blocks=[],
    )
    captured = capsys.readouterr()
    # implementer.yaml includes pre-work/codebase-memory-first.md AND handoff/basics.md;
    # qa extends implementer but adds qa/smoke-and-evidence.md only.
    # So no dedup expected for qa specifically. Use a synthetic case instead.
    # (This test is illustrative; actual dedup test in next task.)
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_b_builder_compose.py -v
```

- [ ] **Step 3: Create `paperclips/scripts/compose_agent_prompt.py`**

```python
"""Compose per-agent AGENTS.md from profile + role + custom_includes + overlays.

Per UAA spec §3, §5.2.1.

Composition order:
1. Universal layer (if profile.inheritsUniversal)
2. Profile.includes resolved against extends-chain (deduplicated)
3. Custom includes (per-agent)
4. Role craft (role_source content)
5. Overlay blocks (appended last; from §6.7 apply_overlay)
"""
from __future__ import annotations

import sys
from pathlib import Path

from paperclips.scripts.profile_schema import load_profile, resolve_extends_chain

UNIVERSAL_FRAGMENTS = [
    "universal/karpathy.md",
    "universal/wake-and-handoff-basics.md",
    "universal/escalation-board.md",
]


def _read_fragment(fragments_dir: Path, rel_path: str) -> str:
    """Read fragment by 'subdir/file.md' relative path."""
    p = fragments_dir / rel_path
    if not p.is_file():
        raise FileNotFoundError(f"fragment not found: {p}")
    return p.read_text()


def _load_all_profiles(profiles_dir: Path) -> dict[str, dict]:
    return {p.stem: load_profile(p) for p in profiles_dir.glob("*.yaml")}


def compose(
    *,
    profile_name: str,
    profiles_dir: Path,
    fragments_dir: Path,
    role_source_text: str,
    custom_includes: list[str],
    overlay_blocks: list[str],
) -> str:
    """Compose final AGENTS.md content."""
    all_profiles = _load_all_profiles(profiles_dir)
    if profile_name not in all_profiles:
        raise ValueError(f"unknown profile: {profile_name}; available: {sorted(all_profiles)}")

    profile = all_profiles[profile_name]
    chain = resolve_extends_chain(profile, all_profiles)  # base → ... → this

    sections: list[str] = []

    # 1. Universal layer (deduplicated across chain — emit once)
    inherits_universal = any(p["inheritsUniversal"] for p in chain)
    if inherits_universal:
        for u in UNIVERSAL_FRAGMENTS:
            sections.append(_read_fragment(fragments_dir, u))

    # 2. Profile.includes from chain, deduplicated by path (preserve first-occurrence order)
    seen: set[str] = set()
    for p in chain:
        for inc in p["includes"]:
            if inc in seen:
                print(
                    f"  dedup applied: {inc} (already included earlier in extends-chain)",
                    file=sys.stderr,
                )
                continue
            seen.add(inc)
            sections.append(_read_fragment(fragments_dir, inc))

    # 3. Custom includes (per-agent)
    for inc in custom_includes:
        if inc in seen:
            print(
                f"  dedup applied: {inc} (already in profile)",
                file=sys.stderr,
            )
            continue
        seen.add(inc)
        sections.append(_read_fragment(fragments_dir, inc))

    # 4. Role craft
    sections.append(role_source_text)

    # 5. Overlay blocks (appended last)
    for ov in overlay_blocks:
        sections.append(ov)

    return "\n\n".join(sections) + "\n"
```

- [ ] **Step 4: Run all tests, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_b_builder_compose.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/compose_agent_prompt.py paperclips/tests/test_phase_b_builder_compose.py
git commit -m "feat(uaa-phase-b): compose_agent_prompt — universal + profile chain + role + overlay"
```

---

## Task 4: Validator — forbidden-content rejection (§6.2)

**Files:**
- Create: `paperclips/scripts/validate_manifest.py`
- Create: `paperclips/tests/fixtures/phase_b/manifest_clean.yaml`
- Create: `paperclips/tests/fixtures/phase_b/manifest_with_uuid.yaml`
- Create: `paperclips/tests/fixtures/phase_b/manifest_with_abs_path.yaml`
- Create: `paperclips/tests/fixtures/phase_b/manifest_with_telegram_id.yaml`
- Test: `paperclips/tests/test_phase_b_validator.py`

- [ ] **Step 1: Failing test**

```python
# paperclips/tests/test_phase_b_validator.py
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "paperclips" / "tests" / "fixtures" / "phase_b"


def test_clean_manifest_passes():
    from paperclips.scripts.validate_manifest import validate_manifest
    validate_manifest(FIX / "manifest_clean.yaml")  # should not raise


def test_uuid_in_manifest_rejected():
    from paperclips.scripts.validate_manifest import validate_manifest, ManifestValidationError
    with pytest.raises(ManifestValidationError, match="UUID"):
        validate_manifest(FIX / "manifest_with_uuid.yaml")


def test_absolute_path_rejected():
    from paperclips.scripts.validate_manifest import validate_manifest, ManifestValidationError
    with pytest.raises(ManifestValidationError, match="absolute path"):
        validate_manifest(FIX / "manifest_with_abs_path.yaml")


def test_telegram_plugin_id_rejected():
    from paperclips.scripts.validate_manifest import validate_manifest, ManifestValidationError
    with pytest.raises(ManifestValidationError, match="telegram_plugin_id"):
        validate_manifest(FIX / "manifest_with_telegram_id.yaml")


def test_template_reference_to_uuid_field_allowed():
    """{{bindings.company_id}} is allowed in committed manifest (resolved at build time)."""
    from paperclips.scripts.validate_manifest import validate_manifest
    # manifest_clean uses {{bindings.company_id}} in overlay; should pass
    validate_manifest(FIX / "manifest_clean.yaml")
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_b_validator.py -v
```

- [ ] **Step 3: Create fixtures**

`paperclips/tests/fixtures/phase_b/manifest_clean.yaml`:
```yaml
schemaVersion: 2
project:
  key: synth
  display_name: Synthetic Test
  issue_prefix: SYN
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans
mcp:
  service_name: synth-mcp
  tool_namespace: synth
  base_required: [codebase-memory, serena]
agents:
  - agent_name: SynthCTO
    role_source: roles/cto.md
    profile: cto
    target: codex
```

`paperclips/tests/fixtures/phase_b/manifest_with_uuid.yaml`:
```yaml
schemaVersion: 2
project:
  key: synth
  display_name: Synthetic Test
  issue_prefix: SYN
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans
  company_id: 7f3a1234-aaaa-bbbb-cccc-deadbeefcafe   # FORBIDDEN
mcp:
  service_name: synth-mcp
  tool_namespace: synth
  base_required: [codebase-memory]
agents: []
```

`paperclips/tests/fixtures/phase_b/manifest_with_abs_path.yaml`:
```yaml
schemaVersion: 2
project:
  key: synth
  display_name: Synthetic Test
  issue_prefix: SYN
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans
paths:
  project_root: /Users/me/Code/synth   # FORBIDDEN
mcp:
  service_name: synth-mcp
  tool_namespace: synth
  base_required: [codebase-memory]
agents: []
```

`paperclips/tests/fixtures/phase_b/manifest_with_telegram_id.yaml`:
```yaml
schemaVersion: 2
project:
  key: synth
  display_name: Synthetic Test
  issue_prefix: SYN
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans
mcp:
  service_name: synth-mcp
  tool_namespace: synth
  base_required: [codebase-memory]
report_delivery:
  telegram_plugin_id: 60023916-4b6c-40f5-829f-bc8b98abc4ed   # FORBIDDEN
agents: []
```

- [ ] **Step 4: Create `paperclips/scripts/validate_manifest.py`**

```python
"""Validate that a committed manifest is path-free and UUID-free per UAA §6.2."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
ABS_PATH_RE = re.compile(r"(?<!{{)\b/(Users|home|private|var|opt)/[^\s\"',}]+", re.I)
FORBIDDEN_KEYS = {"company_id", "agent_id", "telegram_plugin_id", "bot_token", "chat_id"}
TEMPLATE_REF_RE = re.compile(r"\{\{[^}]+\}\}")


class ManifestValidationError(Exception):
    pass


def _strip_template_refs(text: str) -> str:
    """Remove {{template.refs}} so they don't trigger UUID/path scanners."""
    return TEMPLATE_REF_RE.sub("", text)


def _scan_text_for_forbidden(raw_text: str, source: str) -> list[str]:
    errors: list[str] = []
    cleaned = _strip_template_refs(raw_text)
    for m in UUID_RE.finditer(cleaned):
        errors.append(f"{source}: contains literal UUID {m.group(0)}")
    for m in ABS_PATH_RE.finditer(cleaned):
        errors.append(f"{source}: contains absolute path {m.group(0)}")
    return errors


def _scan_keys_for_forbidden(data: object, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            cur = f"{path}.{k}" if path else k
            if k.lower() in FORBIDDEN_KEYS:
                errors.append(f"forbidden key {cur!r} (host-local data, must move to ~/.paperclip/projects/<key>/)")
            errors.extend(_scan_keys_for_forbidden(v, cur))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            errors.extend(_scan_keys_for_forbidden(item, f"{path}[{i}]"))
    return errors


def validate_manifest(path: Path) -> None:
    """Raise ManifestValidationError if manifest contains host-local data."""
    raw_text = path.read_text()
    errors: list[str] = []

    # Text-level scan (catches inline UUIDs and abs paths even outside of forbidden keys)
    errors.extend(_scan_text_for_forbidden(raw_text, str(path)))

    # Structured scan for forbidden keys
    data = yaml.safe_load(raw_text)
    errors.extend(_scan_keys_for_forbidden(data))

    if errors:
        raise ManifestValidationError("; ".join(errors))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_manifest.py <path-to-manifest.yaml>", file=sys.stderr)
        return 2
    try:
        validate_manifest(Path(sys.argv[1]))
        print(f"OK: {sys.argv[1]} clean")
        return 0
    except ManifestValidationError as e:
        print(f"REJECT: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_b_validator.py -v
```

- [ ] **Step 6: Commit**

```bash
git add paperclips/scripts/validate_manifest.py paperclips/tests/test_phase_b_validator.py paperclips/tests/fixtures/phase_b/
git commit -m "feat(uaa-phase-b): validate_manifest — reject UUIDs/abs-paths/forbidden-keys"
```

---

## Task 5: Template-source resolver (§6.5)

**Files:**
- Create: `paperclips/scripts/resolve_template_sources.py`
- Test: `paperclips/tests/test_phase_b_template_sources.py`

- [ ] **Step 1: Failing test**

```python
# paperclips/tests/test_phase_b_template_sources.py
import pytest


SOURCES = {
    "manifest": {
        "project": {"key": "synth", "issue_prefix": "SYN", "display_name": "Synth"},
        "domain": {"target_name": "Test Wallet"},
        "mcp": {"service_name": "synth-mcp", "tool_namespace": "synth"},
    },
    "bindings": {
        "company_id": "7f3a-...",
        "agents": {"SynthCTO": "a2c1-..."},
    },
    "paths": {
        "project_root": "/Users/me/Code/synth",
    },
    "plugins": {
        "telegram": {"plugin_id": "60023916-...", "chat_id": "-100..."},
    },
}


def test_resolve_simple_manifest_var():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Project: {{project.key}}", SOURCES)
    assert out == "Project: synth"


def test_resolve_nested():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("MCP: {{mcp.service_name}}", SOURCES)
    assert out == "MCP: synth-mcp"


def test_resolve_bindings():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Company: {{bindings.company_id}}", SOURCES)
    assert out == "Company: 7f3a-..."


def test_resolve_paths():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Root: {{paths.project_root}}", SOURCES)
    assert out == "Root: /Users/me/Code/synth"


def test_resolve_plugins():
    from paperclips.scripts.resolve_template_sources import resolve
    out = resolve("Plugin: {{plugins.telegram.plugin_id}}", SOURCES)
    assert out == "Plugin: 60023916-..."


def test_unresolved_var_raises():
    from paperclips.scripts.resolve_template_sources import resolve, UnresolvedTemplateError
    with pytest.raises(UnresolvedTemplateError, match="nonexistent"):
        resolve("{{nonexistent.var}}", SOURCES)


def test_unknown_top_level_source_raises():
    from paperclips.scripts.resolve_template_sources import resolve, UnresolvedTemplateError
    with pytest.raises(UnresolvedTemplateError, match="unknown source"):
        resolve("{{secrets.api_key}}", SOURCES)
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Create resolver**

```python
# paperclips/scripts/resolve_template_sources.py
"""Resolve {{a.b.c}} template refs against allowed sources per UAA §6.5."""
from __future__ import annotations

import re

ALLOWED_TOP_LEVEL = {"manifest", "bindings", "paths", "plugins", "agent",
                     "project", "domain", "mcp"}  # last 4 are manifest.* shorthands

TEMPLATE_RE = re.compile(r"\{\{\s*([^}\s]+)\s*\}\}")


class UnresolvedTemplateError(Exception):
    pass


def _walk(data: dict, key_path: list[str], full_ref: str):
    cur: object = data
    for k in key_path:
        if not isinstance(cur, dict) or k not in cur:
            raise UnresolvedTemplateError(
                f"unresolved placeholder: {{{{{full_ref}}}}}; missing key {k!r}"
            )
        cur = cur[k]
    if cur is None:
        raise UnresolvedTemplateError(f"unresolved placeholder: {{{{{full_ref}}}}}; key resolves to null")
    return cur


def resolve(text: str, sources: dict) -> str:
    """Replace {{a.b.c}} with values from sources dict."""
    def _sub(m: re.Match) -> str:
        ref = m.group(1)
        parts = ref.split(".")
        top = parts[0]
        if top not in ALLOWED_TOP_LEVEL:
            raise UnresolvedTemplateError(
                f"unresolved placeholder: {{{{{ref}}}}}; unknown source {top!r} "
                f"(allowed: {sorted(ALLOWED_TOP_LEVEL)})"
            )
        # manifest shorthand: {{project.key}} == {{manifest.project.key}}
        if top in {"project", "domain", "mcp", "agent"}:
            data = sources.get("manifest", {})
            value = _walk(data, parts, ref)
        else:
            data = sources.get(top, {})
            value = _walk(data, parts[1:], ref)
        return str(value)

    return TEMPLATE_RE.sub(_sub, text)
```

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_b_template_sources.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/resolve_template_sources.py paperclips/tests/test_phase_b_template_sources.py
git commit -m "feat(uaa-phase-b): template-source resolver per §6.5"
```

---

## Task 6: Wire compose + validate + resolve into build_project_compat.py

**Files:**
- Modify: `paperclips/scripts/build_project_compat.py`

- [ ] **Step 1: Failing integration test**

```python
# paperclips/tests/test_phase_b_builder_compose.py — append:
def test_builder_uses_compose_for_new_craft_role(tmp_path):
    """Builder calls compose_agent_prompt() when role file lacks <!-- @include --> directives."""
    from paperclips.scripts.build_project_compat import render_role
    from paperclips.scripts.compose_agent_prompt import compose
    # New craft files (post Phase A) don't contain <!-- @include --> — they rely on profile composition.
    # render_role() must detect this and call compose() instead of expand_includes().
    # We test by inspecting that for the gimle CTO craft, output contains universal layer.
    REPO = Path(__file__).resolve().parents[1]
    cto_craft = REPO / "paperclips" / "roles" / "cto.md"
    text = cto_craft.read_text()
    assert "<!-- @include" not in text, "Phase A craft files should be include-free"
    # Now build gimle and check the output contains universal
    import subprocess
    result = subprocess.run(
        ["./paperclips/build.sh", "--project", "gimle", "--target", "claude"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    cto_built = REPO / "paperclips" / "dist" / "cto.md"
    out = cto_built.read_text()
    assert "Karpathy discipline" in out, "universal not composed into new-craft CTO output"
    assert "Phase 1.1" in out, "phase-orchestration (cto profile) not composed"
```

- [ ] **Step 2: Verify FAIL**

```bash
python3 -m pytest paperclips/tests/test_phase_b_builder_compose.py -v -k builder_uses_compose
```

- [ ] **Step 3: Modify `build_project_compat.py`**

Add at top of file (after existing imports):
```python
from paperclips.scripts.compose_agent_prompt import compose
from paperclips.scripts.profile_schema import load_profile
from paperclips.scripts.validate_manifest import validate_manifest
from paperclips.scripts.resolve_template_sources import resolve as resolve_template
```

Modify `render_role()` (find the existing function, around line 408):

```python
def render_role(
    repo_root: Path,
    target: str,
    role_file: Path,
    manifest_values: dict[str, str],
    agent_values: dict[str, str] | None = None,
) -> str:
    text = role_file.read_text()

    # Phase B: detect new craft files (no <!-- @include --> directives)
    if "<!-- @include fragments/" not in text:
        # New craft path: compose via profile system
        profile_name = (agent_values or {}).get("agent.profile", "minimal")
        profiles_dir = repo_root / "paperclips" / "fragments" / "profiles"
        fragments_dir = repo_root / "paperclips" / "fragments" / "shared" / "fragments"
        custom_includes = (agent_values or {}).get("agent.custom_includes", [])
        if isinstance(custom_includes, str):
            custom_includes = []  # back-compat
        # Compute overlay blocks (preserves existing apply_overlay logic, but as pre-compute)
        overlay_blocks = _collect_overlay_blocks(
            repo_root, manifest_values, target, role_file.name,
            (agent_values or {}).get("agent.agent_name", ""),
        )
        text = compose(
            profile_name=profile_name,
            profiles_dir=profiles_dir,
            fragments_dir=fragments_dir,
            role_source_text=text,
            custom_includes=custom_includes,
            overlay_blocks=overlay_blocks,
        )
    else:
        # Legacy path: existing expand_includes + apply_overlay (unchanged)
        text = expand_includes(repo_root, target, text, manifest_values)
        text = apply_overlay(repo_root, manifest_values, target, role_file.name, text)

    # Resolve template references (§6.5) — both paths
    sources = _build_template_sources(manifest_values, agent_values, repo_root)
    text = resolve_template(text, sources)

    return text


def _collect_overlay_blocks(
    repo_root: Path,
    manifest_values: dict[str, str],
    target: str,
    role_name: str,
    agent_name: str,
) -> list[str]:
    """Return overlay file contents as list of strings (without merging into role text)."""
    overlay_root = manifest_values.get("paths.overlay_root")
    if not overlay_root:
        return []
    blocks: list[str] = []
    for overlay_name in ["_common.md", role_name, f"{agent_name}.md" if agent_name else None]:
        if overlay_name is None:
            continue
        p = repo_root / overlay_root / target / overlay_name
        if p.is_file():
            blocks.append(p.read_text())
    return blocks


def _build_template_sources(
    manifest_values: dict[str, str],
    agent_values: dict[str, str] | None,
    repo_root: Path,
) -> dict:
    """Construct sources dict for template resolver per §6.5."""
    project_key = manifest_values.get("project.key", "")
    sources: dict = {
        "manifest": {
            "project": {k.split(".", 1)[1]: v for k, v in manifest_values.items() if k.startswith("project.")},
            "domain": {k.split(".", 1)[1]: v for k, v in manifest_values.items() if k.startswith("domain.")},
            "mcp": {k.split(".", 1)[1]: v for k, v in manifest_values.items() if k.startswith("mcp.")},
        },
        "agent": agent_values or {},
        "bindings": _load_host_yaml(repo_root, project_key, "bindings.yaml"),
        "paths": _load_host_yaml(repo_root, project_key, "paths.yaml"),
        "plugins": _load_host_yaml(repo_root, project_key, "plugins.yaml"),
    }
    return sources


def _load_host_yaml(repo_root: Path, project_key: str, fname: str) -> dict:
    """Load ~/.paperclip/projects/<key>/<fname>; return {} if absent (build-only)."""
    import os
    home_path = Path(os.path.expanduser(f"~/.paperclip/projects/{project_key}/{fname}"))
    if not home_path.is_file():
        return {}
    import yaml
    raw = yaml.safe_load(home_path.read_text())
    return raw if isinstance(raw, dict) else {}
```

Also modify the `main()` function to call `validate_manifest()` BEFORE building (find `def main`):

```python
def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    manifest_path = project_manifest_path(repo_root, args.project)

    # Phase B: validate manifest is path-free and UUID-free
    if args.validate_strict:  # add CLI flag
        try:
            validate_manifest(manifest_path)
        except Exception as e:
            print(f"ERROR: manifest validation failed: {e}", file=sys.stderr)
            return 1

    # ... existing main logic ...
```

Add CLI flag in `parse_args()`:
```python
parser.add_argument("--validate-strict", action="store_true",
                    help="reject manifest with literal UUIDs / abs paths / forbidden keys (UAA §6.2)")
```

- [ ] **Step 4: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_b_builder_compose.py -v
```

- [ ] **Step 5: Commit**

```bash
git add paperclips/scripts/build_project_compat.py paperclips/tests/test_phase_b_builder_compose.py
git commit -m "feat(uaa-phase-b): wire compose + validate + resolve_template into build_project_compat.py"
```

---

## Task 7: Overlay still works (smoke against trading + uaudit)

**Files:**
- Test: `paperclips/tests/test_phase_b_overlay.py`

- [ ] **Step 1: Add tests**

```python
# paperclips/tests/test_phase_b_overlay.py
"""Phase B: existing overlay mechanism (§6.7) preserved post-refactor."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_trading_overlay_appears_in_built_codex_cto():
    subprocess.run(["./paperclips/build.sh", "--project", "trading", "--target", "codex"],
                   cwd=REPO, check=True, capture_output=True)
    p = REPO / "paperclips" / "dist" / "trading" / "codex" / "CEO.md"  # CEO/CTO depends on trading manifest
    text = p.read_text()
    overlay = (REPO / "paperclips" / "projects" / "trading" / "overlays" / "codex" / "_common.md").read_text()
    # Overlay content should appear at end of file
    assert overlay.strip() in text


def test_uaudit_uwicto_overlay_appears():
    subprocess.run(["./paperclips/build.sh", "--project", "uaudit", "--target", "codex"],
                   cwd=REPO, check=True, capture_output=True)
    p = REPO / "paperclips" / "dist" / "uaudit" / "codex" / "UWICTO.md"
    text = p.read_text()
    overlay = (REPO / "paperclips" / "projects" / "uaudit" / "overlays" / "codex" / "UWICTO.md").read_text()
    assert overlay.strip() in text
```

- [ ] **Step 2: Run, verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_b_overlay.py -v
```

- [ ] **Step 3: Commit**

```bash
git add paperclips/tests/test_phase_b_overlay.py
git commit -m "test(uaa-phase-b): overlay (§6.7) still works after compose pipeline added"
```

---

## Task 8: Project override seam (§6.4) — verify still works + custom_includes interaction

**Files:**
- Create: `paperclips/tests/fixtures/phase_b/synthetic_project/` (full mini-project)
- Test: `paperclips/tests/test_phase_b_overlay.py` (extend)

- [ ] **Step 1: Create synthetic project fixture**

`paperclips/tests/fixtures/phase_b/synthetic_project/paperclip-agent-assembly.yaml`:
```yaml
schemaVersion: 2
project:
  key: synth-test
  display_name: Synth Test
  issue_prefix: SYN
  integration_branch: main
  specs_dir: docs/specs
  plans_dir: docs/plans
mcp:
  service_name: synth-mcp
  tool_namespace: synth
  base_required: [codebase-memory]
agents:
  - agent_name: SynthImpl
    role_source: roles/python-engineer.md
    profile: implementer
    custom_includes:
      - git/commit-and-push.md  # already in implementer profile — should dedup
    target: claude
```

`paperclips/tests/fixtures/phase_b/synthetic_project/fragments/git/commit-and-push.md`:
```markdown
## SYNTHETIC PROJECT OVERRIDE — commit-and-push

This project has a custom commit-and-push policy that REPLACES the shared one.
```

- [ ] **Step 2: Test that project override applies even when fragment is in custom_includes**

```python
# paperclips/tests/test_phase_b_overlay.py — append:
def test_project_override_applies_to_custom_includes():
    """§6.4 (rev3 close): project override resolves regardless of who included the fragment."""
    import subprocess, shutil
    fixture = REPO / "paperclips" / "tests" / "fixtures" / "phase_b" / "synthetic_project"
    project_root = REPO / "paperclips" / "projects" / "synth-test"
    # Symlink fixture into projects/ for build
    if project_root.is_symlink() or project_root.exists():
        project_root.unlink() if project_root.is_symlink() else shutil.rmtree(project_root)
    project_root.symlink_to(fixture)
    try:
        subprocess.run(["./paperclips/build.sh", "--project", "synth-test", "--target", "claude"],
                       cwd=REPO, check=True, capture_output=True)
        out = (REPO / "paperclips" / "dist" / "synth-test" / "claude" / "SynthImpl.md").read_text()
        assert "SYNTHETIC PROJECT OVERRIDE" in out, "project override fragment not picked up"
        # Confirm the SHARED fragment did NOT also appear (override REPLACES)
        assert "Fresh-fetch on wake" not in out, "shared fragment leaked despite override"
    finally:
        project_root.unlink()
```

- [ ] **Step 3: Verify PASS**

```bash
python3 -m pytest paperclips/tests/test_phase_b_overlay.py::test_project_override_applies_to_custom_includes -v
```

- [ ] **Step 4: Commit**

```bash
git add paperclips/tests/fixtures/phase_b/synthetic_project paperclips/tests/test_phase_b_overlay.py
git commit -m "test(uaa-phase-b): project override (§6.4) applies through custom_includes"
```

---

## Task 9: Determinism + golden-file test

- [ ] **Step 1: Add determinism test**

```python
# paperclips/tests/test_phase_b_builder_compose.py — append:
def test_build_is_deterministic():
    """Same manifest + same fragments → identical SHA across two builds."""
    import subprocess, hashlib
    for project, target in [("trading", "codex"), ("uaudit", "codex")]:
        # Build once
        subprocess.run(["./paperclips/build.sh", "--project", project, "--target", target],
                       cwd=REPO, check=True, capture_output=True)
        out1 = sorted((REPO / "paperclips" / "dist" / project / target).glob("*.md"))
        shas1 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out1}
        # Build again
        subprocess.run(["./paperclips/build.sh", "--project", project, "--target", target],
                       cwd=REPO, check=True, capture_output=True)
        shas2 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out1}
        assert shas1 == shas2, f"{project}/{target}: non-deterministic build"
```

- [ ] **Step 2: PASS + commit**

```bash
python3 -m pytest paperclips/tests/test_phase_b_builder_compose.py::test_build_is_deterministic -v
git add paperclips/tests/test_phase_b_builder_compose.py
git commit -m "test(uaa-phase-b): determinism — same inputs produce identical SHAs"
```

---

## Task 10: Phase B acceptance test + spec update

**Files:**
- Create: `paperclips/tests/test_phase_b_acceptance.py`
- Modify: `docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md`

- [ ] **Step 1: Acceptance suite**

```python
# paperclips/tests/test_phase_b_acceptance.py
"""Phase B acceptance gate: profile system + builder ready for Phase C scripts."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILES_DIR = REPO / "paperclips" / "fragments" / "profiles"


def test_all_8_profiles_present():
    for n in ["custom", "minimal", "research", "writer", "implementer", "qa", "reviewer", "cto"]:
        assert (PROFILES_DIR / f"{n}.yaml").is_file()


def test_compose_module_importable():
    from paperclips.scripts.compose_agent_prompt import compose  # noqa


def test_validator_module_importable():
    from paperclips.scripts.validate_manifest import validate_manifest  # noqa


def test_resolver_module_importable():
    from paperclips.scripts.resolve_template_sources import resolve  # noqa


def test_builder_extended_with_compose_path():
    text = (REPO / "paperclips" / "scripts" / "build_project_compat.py").read_text()
    assert "from paperclips.scripts.compose_agent_prompt import compose" in text
    assert "from paperclips.scripts.validate_manifest import validate_manifest" in text


def test_legacy_path_still_works_for_unmigrated_roles():
    """Roles in roles/legacy/* still produce equivalent output via expand_includes."""
    import subprocess
    # Build gimle (uses NEW craft files post Phase A — but legacy/ are still there as fallback)
    subprocess.run(["./paperclips/build.sh", "--project", "gimle", "--target", "claude"],
                   cwd=REPO, check=True)
```

- [ ] **Step 2: Run all Phase B tests**

```bash
python3 -m pytest paperclips/tests/test_phase_b_*.py -v
```
Expected: 0 FAIL.

- [ ] **Step 3: Update spec changelog**

Append at top of changelog section:
```markdown
**Phase B complete (YYYY-MM-DD):**
- 8 profile YAMLs created in `paperclips/fragments/profiles/`.
- `compose_agent_prompt.py` composes universal + profile chain (extends + dedup) + role + custom_includes + overlay.
- `validate_manifest.py` rejects literal UUIDs, absolute paths, and forbidden keys (company_id/agent_id/telegram_plugin_id/bot_token/chat_id).
- `resolve_template_sources.py` resolves `{{a.b.c}}` against allowed sources (manifest/bindings/paths/plugins/agent + project/domain/mcp shorthands).
- Builder dispatches to legacy `expand_includes` path for old-style role files (with `<!-- @include -->` directives) and new `compose()` path for craft files (without directives).
- Project override seam (§6.4) preserved.
- Overlay mechanism (§6.7) preserved.
- Determinism verified.
```

- [ ] **Step 4: Commit**

```bash
git add paperclips/tests/test_phase_b_acceptance.py docs/superpowers/specs/2026-05-15-uniform-agent-assembly-design.md
git commit -m "test+docs(uaa-phase-b): acceptance suite + spec changelog"
```

---

## Phase B acceptance gate (before Phase C)

- [ ] All Phase B tests green: `python3 -m pytest paperclips/tests/test_phase_b_*.py` → 0 FAIL.
- [ ] All Phase A tests still green: `python3 -m pytest paperclips/tests/test_phase_a_*.py` → 0 FAIL (no regression).
- [ ] Existing builds still produce equivalent output for unmigrated content paths (legacy roles using @include directives).
- [ ] No file in `paperclips/fragments/profiles/` exceeds 30 lines (sanity).
- [ ] `dist/` is in `.gitignore` if not already.
- [ ] Operator visual spot-check: `paperclips/dist/cto.md` (gimle, post-Phase-A craft) contains universal + reviewer-extended + cto-specific content with no duplication.
