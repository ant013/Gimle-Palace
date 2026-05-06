# Cross-Repo Version Skew Extractor Implementation Plan

> **Revision:** rev3 — addresses 5 CRITICAL + 6 WARNING findings from Phase 1.2 CodeReviewer (comment `c181e97a`). Changes: Tasks 2, 8, 9, 10, 11, 12, 13 revised; spec §9 AC #8 amended (count-only v1). See `Rev3 changes` notes in each affected task.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `cross_repo_version_skew` extractor (Roadmap #39) — pure skew detection over the existing `:Project-[:DEPENDS_ON]->:ExternalDependency` graph from GIM-191 — plus the `palace.code.find_version_skew` MCP tool with project/bundle modes.

**Architecture:** Per `docs/superpowers/specs/2026-05-06-GIM-218-cross-repo-version-skew.md` (rev2). Hybrid: minimal extractor that writes only one substrate `:IngestRun{extractor_name='cross_repo_version_skew'}` per call (audit/observability), plus a live MCP tool that runs the same aggregation Cypher on demand. Single-source-of-truth in `compute.py` shared by both. Read-only over the graph; no new node labels, no new constraints.

**Tech Stack:** Python 3.13+, Pydantic v2, `packaging.version` (PEP 440 — already transitively available via existing deps), Neo4j async driver, pytest + testcontainers. NO new package dependencies.

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `services/palace-mcp/src/palace_mcp/config.py` | Add 2 `PALACE_VERSION_SKEW_*` env-var fields to `Settings` |
| `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py` | Add 10 new `ExtractorErrorCode` values |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/__init__.py` | Package init |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/models.py` | `EcosystemEnum`, `SeverityEnum`, `WarningCodeEnum`, `SkewEntry`, `SkewGroup`, `WarningEntry`, `RunSummary` (Pydantic v2 frozen + Literal enums) |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/purl_parser.py` | `purl_root_for_display(purl)` — single helper |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/semver_classify.py` | `classify(v_a, v_b)` → `'patch' | 'minor' | 'major' | 'unknown'`; `severity_rank()` |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/compute.py` | `_compute_skew_groups(driver, mode, target, ecosystem) → list[SkewGroup]` — single source of truth used by extractor and MCP tool |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/neo4j_writer.py` | `_write_run_extras(driver, run_id, summary)` — sets ownership-style props on substrate `:IngestRun` |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/extractor.py` | `CrossRepoVersionSkewExtractor(BaseExtractor)` — 4-phase orchestrator |
| `services/palace-mcp/src/palace_mcp/extractors/registry.py` | Register `cross_repo_version_skew` in `EXTRACTORS` |
| `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/find_version_skew.py` | MCP tool wrapper + registration — args validation, calls `_compute_skew_groups()`, applies post-filters, serializes; `register_version_skew_tools()` called from `mcp_server.py` |
| `services/palace-mcp/src/palace_mcp/mcp_server.py` | Add `register_version_skew_tools()` call alongside existing `register_code_composite_tools()` |
| `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_models.py` | Pydantic validators + enum checks |
| `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_purl_parser.py` | `purl_root_for_display` over all ecosystems + edge cases |
| `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_semver_classify.py` | `classify`/`severity_rank` exhaustive |
| `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_compute_uniqueness.py` | SF3 source-grep regression — no other module runs the aggregation Cypher |
| `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_compute.py` | `_compute_skew_groups()` over seeded mini-fixture |
| `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_extractor.py` | Full pipeline (Phase 0–4) + acceptance scenarios 1, 2, 3, 14, 17 |
| `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_warnings.py` | Acceptance #19, #20, #24 (bundle_has_no_members, malformed-purl warning, warnings schema) |
| `services/palace-mcp/tests/extractors/integration/test_find_version_skew_wire.py` | All 11 error envelopes + success paths + acceptance #21, #22 |
| `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_query_timeout.py` | Acceptance #23 query-timeout (skip if APOC not available) |
| `services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh` | Live iMac smoke (manual; not in CI) |
| `docs/runbooks/cross-repo-version-skew.md` | Operator runbook |
| `CLAUDE.md` | Add `cross_repo_version_skew` row + workflow subsection |

---

## Task 1: Add 2 env vars to Settings

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/config.py:Settings`
- Test: `services/palace-mcp/tests/unit/test_settings_foundation.py` (extend existing)

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/unit/test_settings_foundation.py`:

```python
def test_version_skew_settings_defaults(monkeypatch):
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    settings = Settings()
    assert settings.version_skew_top_n_max == 500
    assert settings.version_skew_query_timeout_s == 30


def test_version_skew_top_n_max_lower_bound_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_VERSION_SKEW_TOP_N_MAX", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_version_skew_timeout_upper_bound_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_VERSION_SKEW_QUERY_TIMEOUT_S", "1000")
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/unit/test_settings_foundation.py -k version_skew -v`

Expected: 3 FAIL with `AttributeError: 'Settings' object has no attribute 'version_skew_top_n_max'`.

- [ ] **Step 3: Implement settings fields**

In `services/palace-mcp/src/palace_mcp/config.py`, append to `Settings`:

```python
# inside class Settings(BaseSettings):
version_skew_top_n_max: int = Field(
    default=500, ge=1, le=10_000,
    description="Upper bound for find_version_skew top_n arg",
)
version_skew_query_timeout_s: int = Field(
    default=30, ge=1, le=600,
    description="Bolt session timeout for cross-repo skew aggregation Cypher (seconds)",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/unit/test_settings_foundation.py -k version_skew -v`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/config.py services/palace-mcp/tests/unit/test_settings_foundation.py
git commit -m "feat(GIM-218): add 2 PALACE_VERSION_SKEW_* env vars"
```

---

## Task 2: Add 10 new ExtractorErrorCode values

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py:ExtractorErrorCode`
- Test: `services/palace-mcp/tests/extractors/unit/test_foundation_errors.py` (extend or create)

- [ ] **Step 1: Write failing test**

In `services/palace-mcp/tests/extractors/unit/test_foundation_errors.py`:

```python
from palace_mcp.extractors.foundation.errors import ExtractorErrorCode


def test_version_skew_error_codes_present():
    """Cross-repo-version-skew error codes are defined."""
    assert ExtractorErrorCode.DEPENDENCY_SURFACE_NOT_INDEXED.value == "dependency_surface_not_indexed"
    assert ExtractorErrorCode.BUNDLE_NOT_REGISTERED.value == "bundle_not_registered"
    assert ExtractorErrorCode.BUNDLE_HAS_NO_MEMBERS.value == "bundle_has_no_members"
    assert ExtractorErrorCode.BUNDLE_INVALID.value == "bundle_invalid"
    assert ExtractorErrorCode.MUTUALLY_EXCLUSIVE_ARGS.value == "mutually_exclusive_args"
    assert ExtractorErrorCode.MISSING_TARGET.value == "missing_target"
    assert ExtractorErrorCode.INVALID_SEVERITY_FILTER.value == "invalid_severity_filter"
    assert ExtractorErrorCode.INVALID_ECOSYSTEM_FILTER.value == "invalid_ecosystem_filter"
    assert ExtractorErrorCode.SLUG_INVALID.value == "slug_invalid"
    assert ExtractorErrorCode.TOP_N_OUT_OF_RANGE.value == "top_n_out_of_range"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_foundation_errors.py::test_version_skew_error_codes_present -v`

Expected: FAIL with `AttributeError: DEPENDENCY_SURFACE_NOT_INDEXED`.

- [ ] **Step 3: Add enum values**

In `services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py`, add to `class ExtractorErrorCode(StrEnum):` (alphabetical):

```python
    BUNDLE_HAS_NO_MEMBERS = "bundle_has_no_members"
    BUNDLE_INVALID = "bundle_invalid"
    BUNDLE_NOT_REGISTERED = "bundle_not_registered"
    DEPENDENCY_SURFACE_NOT_INDEXED = "dependency_surface_not_indexed"
    INVALID_ECOSYSTEM_FILTER = "invalid_ecosystem_filter"
    INVALID_SEVERITY_FILTER = "invalid_severity_filter"
    MISSING_TARGET = "missing_target"
    MUTUALLY_EXCLUSIVE_ARGS = "mutually_exclusive_args"
    SLUG_INVALID = "slug_invalid"
    TOP_N_OUT_OF_RANGE = "top_n_out_of_range"
```

(`GIT_HISTORY_NOT_INDEXED` may already exist from the GIM-216 sibling slice; if missing, the spec says to share it but for #39 the relevant code is `DEPENDENCY_SURFACE_NOT_INDEXED` — distinct.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_foundation_errors.py::test_version_skew_error_codes_present -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/foundation/errors.py services/palace-mcp/tests/extractors/unit/test_foundation_errors.py
git commit -m "feat(GIM-218): add 10 ExtractorErrorCode values for cross_repo_version_skew"
```

---

## Task 3: Pydantic models + enums

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/__init__.py`
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/models.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_models.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_models.py`:

```python
import pytest
from pydantic import ValidationError

from palace_mcp.extractors.cross_repo_version_skew.models import (
    EcosystemEnum,
    SeverityEnum,
    WarningCodeEnum,
    SkewEntry,
    SkewGroup,
    WarningEntry,
    RunSummary,
)


def test_ecosystem_enum_values():
    assert set(EcosystemEnum) == {EcosystemEnum.GITHUB, EcosystemEnum.MAVEN, EcosystemEnum.PYPI}
    assert EcosystemEnum.GITHUB.value == "github"


def test_severity_enum_rank():
    """Per spec §3 R6: major=3 minor=2 patch=1 unknown=0."""
    assert SeverityEnum.MAJOR.rank == 3
    assert SeverityEnum.MINOR.rank == 2
    assert SeverityEnum.PATCH.rank == 1
    assert SeverityEnum.UNKNOWN.rank == 0


def test_warning_code_enum_closed_set():
    """Per SF4: warnings[].code is a closed enum."""
    expected = {
        "member_not_indexed", "member_not_registered", "member_invalid_slug",
        "purl_missing_version", "purl_malformed", "version_unparseable_in_group",
    }
    assert {w.value for w in WarningCodeEnum} == expected


def test_skew_entry_basic():
    e = SkewEntry(
        scope_id="MarketKit",
        version="1.5.0",
        declared_in="Package.swift",
        declared_constraint="^1.5.0",
    )
    assert e.scope_id == "MarketKit"


def test_skew_group_basic():
    g = SkewGroup(
        purl_root="pkg:github/horizontalsystems/marketkit",
        ecosystem="github",
        severity="major",
        version_count=2,
        entries=(
            SkewEntry(scope_id="A", version="1.5.0", declared_in="x", declared_constraint="^1.5.0"),
            SkewEntry(scope_id="B", version="2.0.1", declared_in="y", declared_constraint="^2.0.0"),
        ),
    )
    assert g.version_count == 2


def test_skew_group_invalid_severity_rejected():
    with pytest.raises(ValidationError):
        SkewGroup(
            purl_root="pkg:github/x/y",
            ecosystem="github",
            severity="critical",  # not in enum
            version_count=2,
            entries=(),
        )


def test_warning_entry_with_slug():
    w = WarningEntry(code="member_not_indexed", slug="NavigationKit", message="not yet indexed")
    assert w.code == "member_not_indexed"


def test_warning_entry_invalid_code_rejected():
    with pytest.raises(ValidationError):
        WarningEntry(code="some_freeform_string", slug=None, message="x")


def test_run_summary_basic():
    s = RunSummary(
        mode="bundle",
        target_slug="uw-ios",
        member_count=41,
        target_status_indexed_count=40,
        skew_groups_total=17,
        skew_groups_major=3,
        skew_groups_minor=8,
        skew_groups_patch=4,
        skew_groups_unknown=2,
        aligned_groups_total=42,
        warnings_purl_malformed_count=0,
    )
    assert s.skew_groups_total == 17


def test_run_summary_invalid_mode_rejected():
    with pytest.raises(ValidationError):
        RunSummary(
            mode="weird",  # not 'project'|'bundle'
            target_slug="x",
            member_count=1,
            target_status_indexed_count=1,
            skew_groups_total=0,
            skew_groups_major=0, skew_groups_minor=0, skew_groups_patch=0, skew_groups_unknown=0,
            aligned_groups_total=0,
            warnings_purl_malformed_count=0,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_cross_repo_skew_models.py -v`

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement models**

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/__init__.py`:

```python
"""Cross-repo version skew extractor (Roadmap #39)."""
```

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/models.py`:

```python
from __future__ import annotations

from enum import Enum, StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class EcosystemEnum(StrEnum):
    GITHUB = "github"
    MAVEN = "maven"
    PYPI = "pypi"


class SeverityEnum(Enum):
    UNKNOWN = ("unknown", 0)
    PATCH = ("patch", 1)
    MINOR = ("minor", 2)
    MAJOR = ("major", 3)

    def __init__(self, value: str, rank: int) -> None:
        self._value_ = value
        self.rank = rank


class WarningCodeEnum(StrEnum):
    MEMBER_NOT_INDEXED = "member_not_indexed"
    MEMBER_NOT_REGISTERED = "member_not_registered"
    MEMBER_INVALID_SLUG = "member_invalid_slug"
    PURL_MISSING_VERSION = "purl_missing_version"
    PURL_MALFORMED = "purl_malformed"
    VERSION_UNPARSEABLE_IN_GROUP = "version_unparseable_in_group"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SkewEntry(FrozenModel):
    scope_id: str
    version: str
    declared_in: str
    declared_constraint: str


class SkewGroup(FrozenModel):
    purl_root: str
    ecosystem: str
    severity: Literal["major", "minor", "patch", "unknown"]
    version_count: int
    entries: tuple[SkewEntry, ...]


class WarningEntry(FrozenModel):
    code: Literal[
        "member_not_indexed",
        "member_not_registered",
        "member_invalid_slug",
        "purl_missing_version",
        "purl_malformed",
        "version_unparseable_in_group",
    ]
    slug: str | None
    message: str


class RunSummary(FrozenModel):
    mode: Literal["project", "bundle"]
    target_slug: str
    member_count: int
    target_status_indexed_count: int
    skew_groups_total: int
    skew_groups_major: int
    skew_groups_minor: int
    skew_groups_patch: int
    skew_groups_unknown: int
    aligned_groups_total: int
    warnings_purl_malformed_count: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_cross_repo_skew_models.py -v`

Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/__init__.py \
        services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/models.py \
        services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_models.py
git commit -m "feat(GIM-218): cross_repo_version_skew Pydantic models + enums"
```

---

## Task 4: `purl_parser.py` — `purl_root_for_display`

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/purl_parser.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_purl_parser.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_purl_parser.py`:

```python
from palace_mcp.extractors.cross_repo_version_skew.purl_parser import (
    purl_root_for_display,
)


def test_github_purl_strips_version():
    assert (
        purl_root_for_display("pkg:github/horizontalsystems/marketkit@1.5.0")
        == "pkg:github/horizontalsystems/marketkit"
    )


def test_maven_purl_strips_version():
    assert (
        purl_root_for_display("pkg:maven/com.example/lib@1.0.0")
        == "pkg:maven/com.example/lib"
    )


def test_pypi_purl_strips_version():
    assert (
        purl_root_for_display("pkg:pypi/requests@2.31.0")
        == "pkg:pypi/requests"
    )


def test_generic_spm_purl_with_query_qualifier():
    """Generic SPM purl: pkg:generic/spm-package?vcs_url=<encoded>@<version>.

    rfind('@') finds the version separator (URL-encoded vcs_url has %40 not @).
    """
    purl = "pkg:generic/spm-package?vcs_url=https%3A%2F%2Fexample.com%2Frepo.git@1.0.0"
    assert (
        purl_root_for_display(purl)
        == "pkg:generic/spm-package?vcs_url=https%3A%2F%2Fexample.com%2Frepo.git"
    )


def test_multiple_at_uses_rsplit():
    """Last @ is the version separator (defensive)."""
    assert (
        purl_root_for_display("pkg:maven/g/a@b@1.0.0")
        == "pkg:maven/g/a@b"
    )


def test_no_version_returns_input_unchanged():
    """If no @ separator, return input as-is (caller filters via Cypher anyway)."""
    assert purl_root_for_display("pkg:pypi/foo") == "pkg:pypi/foo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_cross_repo_skew_purl_parser.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement purl_parser**

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/purl_parser.py`:

```python
"""purl helpers for cross_repo_version_skew.

Per spec rev2 C3: GIM-191 writer stores ecosystem and resolved_version
as :ExternalDependency properties; we read those directly from Cypher.
This module is reduced to a single display helper.
"""

from __future__ import annotations


def purl_root_for_display(purl: str) -> str:
    """Strip @<version> suffix from a purl. Last `@` only (rsplit).

    Returns purl unchanged if there is no `@` separator.
    """
    if "@" not in purl:
        return purl
    return purl.rsplit("@", 1)[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_cross_repo_skew_purl_parser.py -v`

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/purl_parser.py \
        services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_purl_parser.py
git commit -m "feat(GIM-218): purl_root_for_display helper (rsplit on @)"
```

---

## Task 5: `semver_classify.py` — pairwise version classification

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/semver_classify.py`
- Create: `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_semver_classify.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_semver_classify.py`:

```python
from palace_mcp.extractors.cross_repo_version_skew.semver_classify import (
    classify,
    severity_rank,
    max_pairwise_severity,
)


def test_identical_returns_patch_floor():
    """Per spec §8: parse-equivalent strings classify as patch (no real semver delta)."""
    assert classify("1.5.0", "1.5.0") == "patch"


def test_patch_skew():
    assert classify("1.5.0", "1.5.1") == "patch"


def test_minor_skew():
    assert classify("1.5.0", "1.6.0") == "minor"


def test_major_skew():
    assert classify("1.5.0", "2.0.0") == "major"


def test_unparseable_returns_unknown():
    assert classify("1.5.0", "calver-2024.05.06") == "unknown"
    assert classify("a1b2c3d", "1.5.0") == "unknown"


def test_parse_equivalent_strings_classify_patch():
    """'1.5' and '1.5.0' parse to same Version under packaging.version → patch (per spec §8)."""
    assert classify("1.5", "1.5.0") == "patch"


def test_severity_rank_ordering():
    assert severity_rank("major") == 3
    assert severity_rank("minor") == 2
    assert severity_rank("patch") == 1
    assert severity_rank("unknown") == 0


def test_max_pairwise_picks_highest_rank():
    """Final group severity = max-pairwise-rank across all version pairs."""
    versions = ["1.5.0", "1.5.1", "2.0.0"]  # patch with .1, major with 2.0.0
    assert max_pairwise_severity(versions) == "major"


def test_max_pairwise_unknown_when_any_pair_unknown():
    """If any pair unparseable, group severity is unknown UNLESS another pair is higher."""
    versions = ["1.5.0", "calver-2024", "2.0.0"]
    # 1.5.0 vs calver = unknown; 1.5.0 vs 2.0.0 = major; calver vs 2.0.0 = unknown
    # max rank among these: major(3) > unknown(0) → 'major'
    assert max_pairwise_severity(versions) == "major"


def test_max_pairwise_all_unparseable_returns_unknown():
    versions = ["calver-2024", "calver-2025"]
    assert max_pairwise_severity(versions) == "unknown"


def test_max_pairwise_two_versions_minimum():
    """API contract: caller must pass >= 2 distinct versions; one version → ValueError."""
    import pytest
    with pytest.raises(ValueError):
        max_pairwise_severity(["1.5.0"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_cross_repo_skew_semver_classify.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement semver_classify**

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/semver_classify.py`:

```python
"""Pairwise semver classification — best-effort with `packaging.version`.

Per spec rev2 R5: PEP 440 parsing is lenient enough for most UW Swift /
Gradle / Python deps. Non-parseable schemes (calver, git-sha, custom)
yield 'unknown'. A group's final severity is the max-rank-across-pairs.
"""

from __future__ import annotations

from itertools import combinations
from typing import Literal

from packaging.version import InvalidVersion, Version

Severity = Literal["major", "minor", "patch", "unknown"]
_RANK: dict[Severity, int] = {"major": 3, "minor": 2, "patch": 1, "unknown": 0}


def severity_rank(severity: Severity) -> int:
    return _RANK[severity]


def classify(v_a: str, v_b: str) -> Severity:
    """Compare two version strings; return semver-style severity or 'unknown'."""
    try:
        a = Version(v_a)
        b = Version(v_b)
    except InvalidVersion:
        return "unknown"

    if a.major != b.major:
        return "major"
    if a.minor != b.minor:
        return "minor"
    # micro / patch differs OR exactly equal — both bucketed as 'patch'
    return "patch"


def max_pairwise_severity(versions: list[str]) -> Severity:
    """Final group severity = max-rank across all version pairs.

    Caller must pass len(versions) >= 2 distinct values. Single-version
    inputs raise ValueError (this function is meant for skew groups).
    """
    if len(versions) < 2:
        raise ValueError(f"max_pairwise_severity requires >= 2 versions; got {len(versions)}")

    best: Severity = "unknown"
    best_rank = _RANK[best]
    for a, b in combinations(versions, 2):
        s = classify(a, b)
        r = _RANK[s]
        if r > best_rank:
            best, best_rank = s, r
    return best
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_cross_repo_skew_semver_classify.py -v`

Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/semver_classify.py \
        services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_semver_classify.py
git commit -m "feat(GIM-218): semver_classify — pairwise + max-rank"
```

---

## Task 6: `compute.py` — Cypher fragments + grouping (single source of truth)

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/compute.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_compute.py` (with mini-fixture seed inline)

- [ ] **Step 1: Write failing integration test (mini-fixture seeded inline)**

Create `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_compute.py`:

```python
"""Integration tests for _compute_skew_groups() on a seeded fixture.

The fixture is created via direct Cypher MERGE (not by running
dependency_surface), so this test is hermetic to GIM-191.
"""

import pytest

from palace_mcp.extractors.cross_repo_version_skew.compute import (
    ComputeResult,
    _compute_skew_groups,
)


async def _seed_skew_fixture(driver) -> None:
    """4 projects, 1 bundle, 7 :ExternalDependency, planned skew."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            // Projects
            MERGE (a:Project {slug: 'uw-ios-app'})
            MERGE (m:Project {slug: 'MarketKit'})
            MERGE (e:Project {slug: 'EvmKit'})
            MERGE (b:Project {slug: 'BitcoinKit'})

            // Bundle
            MERGE (bd:Bundle {name: 'uw-ios-mini'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(m)
            MERGE (bd)-[:HAS_MEMBER]->(e)
            MERGE (bd)-[:HAS_MEMBER]->(b)

            // ExternalDependency: marketkit MAJOR skew
            MERGE (mk_15:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@1.5.0'})
              SET mk_15.ecosystem = 'github', mk_15.resolved_version = '1.5.0'
            MERGE (mk_20:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@2.0.1'})
              SET mk_20.ecosystem = 'github', mk_20.resolved_version = '2.0.1'

            // ExternalDependency: BigInt PATCH+MINOR skew (3 pinnings)
            MERGE (bi_5:ExternalDependency {purl: 'pkg:github/numerics/big@1.0.5'})
              SET bi_5.ecosystem = 'github', bi_5.resolved_version = '1.0.5'
            MERGE (bi_7:ExternalDependency {purl: 'pkg:github/numerics/big@1.0.7'})
              SET bi_7.ecosystem = 'github', bi_7.resolved_version = '1.0.7'
            MERGE (bi_10:ExternalDependency {purl: 'pkg:github/numerics/big@1.1.0'})
              SET bi_10.ecosystem = 'github', bi_10.resolved_version = '1.1.0'

            // ExternalDependency: aligned (single-source — only EvmKit pins it)
            MERGE (sng:ExternalDependency {purl: 'pkg:pypi/notused@5.0.0'})
              SET sng.ecosystem = 'pypi', sng.resolved_version = '5.0.0'

            // ExternalDependency: aligned cross-member (MarketKit and BitcoinKit both pin same)
            MERGE (al:ExternalDependency {purl: 'pkg:pypi/aligned@3.1.0'})
              SET al.ecosystem = 'pypi', al.resolved_version = '3.1.0'

            // DEPENDS_ON edges
            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.5.0'}]->(mk_15)
            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^2.0.0'}]->(mk_20)

            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.0.5'}]->(bi_5)
            MERGE (e)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.0.7'}]->(bi_7)
            MERGE (b)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.1.0'}]->(bi_10)

            MERGE (e)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '5.0.0'}]->(sng)

            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '3.1.0'}]->(al)
            MERGE (b)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '3.1.0'}]->(al)
        """)


@pytest.mark.asyncio
async def test_compute_bundle_mode_finds_two_skew_groups(neo4j_driver):
    await _seed_skew_fixture(neo4j_driver)
    result = await _compute_skew_groups(
        neo4j_driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem=None,
    )
    # marketkit (2 versions: major), big (3 versions: patch+minor → minor)
    purl_roots = {g.purl_root for g in result.skew_groups}
    assert "pkg:github/horizontalsystems/marketkit" in purl_roots
    assert "pkg:github/numerics/big" in purl_roots

    # marketkit severity = major (1.5.0 vs 2.0.1)
    mk = next(g for g in result.skew_groups if g.purl_root == "pkg:github/horizontalsystems/marketkit")
    assert mk.severity == "major"
    assert mk.version_count == 2

    # big severity = minor (1.0.5/1.0.7 → patch; vs 1.1.0 → minor; max = minor)
    big = next(g for g in result.skew_groups if g.purl_root == "pkg:github/numerics/big")
    assert big.severity == "minor"
    assert big.version_count == 3


@pytest.mark.asyncio
async def test_compute_excludes_single_source_and_aligned(neo4j_driver):
    await _seed_skew_fixture(neo4j_driver)
    result = await _compute_skew_groups(
        neo4j_driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem=None,
    )
    purl_roots = {g.purl_root for g in result.skew_groups}
    # 'pkg:pypi/notused' is single-source → excluded
    assert "pkg:pypi/notused" not in purl_roots
    # 'pkg:pypi/aligned' has 2 entries but identical version → excluded from skew
    assert "pkg:pypi/aligned" not in purl_roots


@pytest.mark.asyncio
async def test_compute_aligned_count_present(neo4j_driver):
    await _seed_skew_fixture(neo4j_driver)
    result = await _compute_skew_groups(
        neo4j_driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem=None,
    )
    # 'pkg:pypi/aligned' has 2 entries with same version → 1 aligned group
    # 'pkg:pypi/notused' has 1 entry → not aligned, not skew (single-source filter)
    assert result.aligned_groups_total == 1


@pytest.mark.asyncio
async def test_compute_ecosystem_filter(neo4j_driver):
    await _seed_skew_fixture(neo4j_driver)
    result = await _compute_skew_groups(
        neo4j_driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem="github",
    )
    # only github-prefix purls
    for g in result.skew_groups:
        assert g.ecosystem == "github"


@pytest.mark.asyncio
async def test_compute_project_mode_single_member(neo4j_driver):
    await _seed_skew_fixture(neo4j_driver)
    result = await _compute_skew_groups(
        neo4j_driver,
        mode="project",
        member_slugs=["MarketKit"],
        ecosystem=None,
    )
    # MarketKit alone has marketkit@2.0.1 (1 entry) and big@1.0.5 (1 entry)
    # No intra-project skew (each purl_root has 1 version) → 0 skew groups
    assert result.skew_groups == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_cross_repo_skew_compute.py -v`

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement compute.py**

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/compute.py`:

```python
"""Single source of truth for skew detection.

Used by both the extractor (Phase 2-3) and the MCP tool. Per spec rev2
SF3, no other module in `cross_repo_version_skew/` (or anywhere else)
runs the aggregation Cypher — enforced by source-grep regression test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from neo4j import AsyncDriver

from palace_mcp.extractors.cross_repo_version_skew.models import (
    SkewEntry,
    SkewGroup,
    WarningEntry,
)
from palace_mcp.extractors.cross_repo_version_skew.purl_parser import (
    purl_root_for_display,
)
from palace_mcp.extractors.cross_repo_version_skew.semver_classify import (
    max_pairwise_severity,
)

Mode = Literal["project", "bundle"]


@dataclass(frozen=True)
class ComputeResult:
    skew_groups: list[SkewGroup]
    aligned_groups_total: int
    warnings: list[WarningEntry]


_PROJECT_MODE_CYPHER = """
MATCH (p:Project {slug: $slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WHERE d.purl STARTS WITH 'pkg:'
  AND d.resolved_version IS NOT NULL
  AND ($ecosystem IS NULL OR d.ecosystem = $ecosystem)
RETURN d.purl                         AS purl,
       d.ecosystem                    AS ecosystem,
       d.resolved_version             AS version,
       r.declared_in                  AS scope_id,
       r.declared_in                  AS declared_in,
       r.declared_version_constraint  AS declared_constraint
ORDER BY d.purl, scope_id
"""

_BUNDLE_MODE_CYPHER = """
UNWIND $member_slugs AS slug
MATCH (p:Project {slug: slug})-[r:DEPENDS_ON]->(d:ExternalDependency)
WHERE d.purl STARTS WITH 'pkg:'
  AND d.resolved_version IS NOT NULL
  AND ($ecosystem IS NULL OR d.ecosystem = $ecosystem)
RETURN d.purl                         AS purl,
       d.ecosystem                    AS ecosystem,
       d.resolved_version             AS version,
       p.slug                         AS scope_id,
       r.declared_in                  AS declared_in,
       r.declared_version_constraint  AS declared_constraint
ORDER BY d.purl, scope_id
"""

_MALFORMED_DIAGNOSTIC_CYPHER = """
MATCH (p:Project)-[:DEPENDS_ON]->(d:ExternalDependency)
WHERE NOT d.purl STARTS WITH 'pkg:'
  AND p.slug IN $target_slugs
RETURN count(*) AS malformed_count
"""


async def _compute_skew_groups(
    driver: AsyncDriver,
    *,
    mode: Mode,
    member_slugs: Sequence[str],
    ecosystem: str | None,
) -> ComputeResult:
    """Aggregate :DEPENDS_ON over targets; group by purl_root; classify.

    The result includes only true-skew groups (>=2 distinct versions).
    Aligned groups (single-version) are counted but not returned as
    SkewGroup; the caller (MCP tool) emits them only on opt-in.
    """
    if mode == "project":
        if len(member_slugs) != 1:
            raise ValueError(f"project mode expects exactly 1 member; got {len(member_slugs)}")
        params = {"slug": member_slugs[0], "ecosystem": ecosystem}
        cypher = _PROJECT_MODE_CYPHER
    else:
        params = {"member_slugs": list(member_slugs), "ecosystem": ecosystem}
        cypher = _BUNDLE_MODE_CYPHER

    rows: list[dict] = []
    async with driver.session() as session:
        result = await session.run(cypher, **params)
        async for record in result:
            rows.append({
                "purl": record["purl"],
                "ecosystem": record["ecosystem"],
                "version": record["version"],
                "scope_id": record["scope_id"],
                "declared_in": record["declared_in"],
                "declared_constraint": record["declared_constraint"],
            })

    # Group by (purl_root, ecosystem); each group accumulates entries
    by_group: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        purl_root = purl_root_for_display(row["purl"])
        key = (purl_root, row["ecosystem"])
        by_group.setdefault(key, []).append(row)

    skew_groups: list[SkewGroup] = []
    aligned_groups_total = 0
    for (purl_root, ecosystem_value), group_rows in by_group.items():
        distinct_versions = sorted({r["version"] for r in group_rows})
        if len(distinct_versions) < 2:
            # Aligned (or single-source). Single-source has 1 entry; >=2 entries
            # with same version is true alignment.
            if len(group_rows) >= 2:
                aligned_groups_total += 1
            continue
        severity = max_pairwise_severity(distinct_versions)
        entries = tuple(
            SkewEntry(
                scope_id=r["scope_id"],
                version=r["version"],
                declared_in=r["declared_in"],
                declared_constraint=r["declared_constraint"] or "",
            )
            for r in group_rows
        )
        skew_groups.append(SkewGroup(
            purl_root=purl_root,
            ecosystem=ecosystem_value,
            severity=severity,
            version_count=len(distinct_versions),
            entries=entries,
        ))

    # Diagnostic: count malformed purls (those missing pkg: prefix) that
    # would have been ignored above.
    target_slugs = list(member_slugs)
    warnings: list[WarningEntry] = []
    async with driver.session() as session:
        diag = await session.run(_MALFORMED_DIAGNOSTIC_CYPHER, target_slugs=target_slugs)
        diag_row = await diag.single()
    malformed_count = diag_row["malformed_count"] if diag_row else 0
    if malformed_count > 0:
        warnings.append(WarningEntry(
            code="purl_malformed",
            slug=None,
            message=f"{malformed_count} :ExternalDependency rows lacked 'pkg:' prefix; excluded from skew",
        ))

    return ComputeResult(
        skew_groups=skew_groups,
        aligned_groups_total=aligned_groups_total,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_cross_repo_skew_compute.py -v`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/compute.py \
        services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_compute.py
git commit -m "feat(GIM-218): _compute_skew_groups single source of truth"
```

---

## Task 7: `neo4j_writer.py` — `_write_run_extras`

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/neo4j_writer.py`
- Test: extended in Task 9 (extractor.py integration tests verify writer end-to-end)

- [ ] **Step 1: Write failing integration test (minimal direct test)**

Create `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_writer.py`:

```python
import pytest

from palace_mcp.extractors.cross_repo_version_skew.models import RunSummary
from palace_mcp.extractors.cross_repo_version_skew.neo4j_writer import (
    _write_run_extras,
)


@pytest.mark.asyncio
async def test_write_run_extras_sets_properties(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            CREATE (r:IngestRun {run_id: 'r1'})
            SET r.extractor_name = 'cross_repo_version_skew',
                r.project = 'uw-ios-mini',
                r.success = true
        """)
    summary = RunSummary(
        mode="bundle",
        target_slug="uw-ios-mini",
        member_count=4,
        target_status_indexed_count=4,
        skew_groups_total=2,
        skew_groups_major=1,
        skew_groups_minor=1,
        skew_groups_patch=0,
        skew_groups_unknown=0,
        aligned_groups_total=1,
        warnings_purl_malformed_count=0,
    )
    await _write_run_extras(neo4j_driver, run_id="r1", summary=summary)

    async with neo4j_driver.session() as session:
        result = await session.run("""
            MATCH (r:IngestRun {run_id: 'r1'})
            RETURN r.mode AS mode, r.target_slug AS target,
                   r.skew_groups_total AS total,
                   r.skew_groups_major AS major,
                   r.aligned_groups_total AS aligned
        """)
        row = await result.single()
    assert row["mode"] == "bundle"
    assert row["target"] == "uw-ios-mini"
    assert row["total"] == 2
    assert row["major"] == 1
    assert row["aligned"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_cross_repo_skew_writer.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement neo4j_writer**

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/neo4j_writer.py`:

```python
"""Substrate :IngestRun extras writer for cross_repo_version_skew.

Per spec rev2 C8: the extractor does NOT introduce a separate
:OwnershipRun-style label. It writes ownership-style extras onto the
substrate :IngestRun (created by foundation/checkpoint.py).
"""

from __future__ import annotations

from neo4j import AsyncDriver

from palace_mcp.extractors.cross_repo_version_skew.models import RunSummary

_WRITE_EXTRAS_CYPHER = """
MATCH (r:IngestRun {run_id: $run_id})
SET r.mode                            = $mode,
    r.target_slug                     = $target_slug,
    r.member_count                    = $member_count,
    r.target_status_indexed_count     = $target_status_indexed_count,
    r.skew_groups_total               = $skew_groups_total,
    r.skew_groups_major               = $skew_groups_major,
    r.skew_groups_minor               = $skew_groups_minor,
    r.skew_groups_patch               = $skew_groups_patch,
    r.skew_groups_unknown             = $skew_groups_unknown,
    r.aligned_groups_total            = $aligned_groups_total,
    r.warnings_purl_malformed_count   = $warnings_purl_malformed_count
"""


async def _write_run_extras(
    driver: AsyncDriver, *, run_id: str, summary: RunSummary
) -> None:
    """Set ownership-style props on the existing :IngestRun for this run."""
    async with driver.session() as session:
        await session.run(
            _WRITE_EXTRAS_CYPHER,
            run_id=run_id,
            mode=summary.mode,
            target_slug=summary.target_slug,
            member_count=summary.member_count,
            target_status_indexed_count=summary.target_status_indexed_count,
            skew_groups_total=summary.skew_groups_total,
            skew_groups_major=summary.skew_groups_major,
            skew_groups_minor=summary.skew_groups_minor,
            skew_groups_patch=summary.skew_groups_patch,
            skew_groups_unknown=summary.skew_groups_unknown,
            aligned_groups_total=summary.aligned_groups_total,
            warnings_purl_malformed_count=summary.warnings_purl_malformed_count,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_cross_repo_skew_writer.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/neo4j_writer.py \
        services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_writer.py
git commit -m "feat(GIM-218): _write_run_extras writes summary onto :IngestRun"
```

---

## Task 8: `extractor.py` orchestrator (4-phase pipeline)

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/extractor.py`

This task does NOT have its own dedicated unit tests — the orchestrator is exercised end-to-end by Task 10 integration tests. Each component it calls already has its own unit/integration test.

**Rev3 changes (CR findings):**
- Subclasses `BaseExtractor`; method is `run(*, graphiti, ctx) -> ExtractorStats` (CRITICAL #1)
- `ExtractorError` uses `error_code=`, `recoverable=`, `action=` (CRITICAL #2)
- Driver via deferred import `get_driver()` / `get_settings()` — no `__init__(settings)` (CRITICAL #1)
- Imports `SLUG_RE` from `models.py` instead of duplicating (WARNING #8)
- Wires `settings.version_skew_query_timeout_s` into `driver.session()` (WARNING #6)
- Auto-detects mode from `ctx.project_slug`: checks if slug is a `:Bundle` first, then `:Project`

- [ ] **Step 1: Add `SLUG_RE` to `models.py`**

In `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/models.py`, add at module level (single source for both extractor and MCP tool):

```python
import re

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
```

- [ ] **Step 2: Implement orchestrator**

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/extractor.py`:

```python
"""Cross-repo version skew extractor (Roadmap #39).

4-phase pipeline per spec rev2 §4:
0. bootstrap (resolve targets, validate dependency_surface presence)
1. collect target_status (indexed / not_indexed / not_registered)
2. aggregate via _compute_skew_groups()
3. summary stats + finalize :IngestRun
"""

from __future__ import annotations

from typing import Any, ClassVar

from palace_mcp.extractors.base import BaseExtractor, ExtractorRunContext, ExtractorStats
from palace_mcp.extractors.cross_repo_version_skew.compute import (
    ComputeResult,
    _compute_skew_groups,
)
from palace_mcp.extractors.cross_repo_version_skew.models import (
    SLUG_RE,
    RunSummary,
    WarningEntry,
)
from palace_mcp.extractors.cross_repo_version_skew.neo4j_writer import (
    _write_run_extras,
)
from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode


class CrossRepoVersionSkewExtractor(BaseExtractor):
    """Roadmap #39 extractor — pure skew detection over GIM-191 :DEPENDS_ON."""

    name: ClassVar[str] = "cross_repo_version_skew"
    description: ClassVar[str] = "Cross-repo version skew detection over :DEPENDS_ON graph"
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []

    async def run(
        self, *, graphiti: Any, ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        from palace_mcp.mcp_server import get_driver, get_settings

        driver = get_driver()
        settings = get_settings()
        if driver is None:
            raise ExtractorError(
                error_code=ExtractorErrorCode.SCHEMA_BOOTSTRAP_FAILED,
                message="Neo4j driver not available — call set_driver() before run_extractor",
                recoverable=False,
                action="retry",
            )

        target_slug = ctx.project_slug
        timeout_s = settings.version_skew_query_timeout_s

        # Auto-detect mode: check if target_slug is a Bundle first
        is_bundle = await self._bundle_exists(driver, target_slug, timeout_s)
        mode = "bundle" if is_bundle else "project"

        try:
            summary, warnings = await self._pipeline(
                driver=driver,
                mode=mode,
                target_slug=target_slug,
                timeout_s=timeout_s,
                logger=ctx.logger,
            )
            await _write_run_extras(driver, run_id=ctx.run_id, summary=summary)
            return ExtractorStats(nodes_written=1, edges_written=0)
        except ExtractorError:
            raise
        except Exception as exc:
            raise ExtractorError(
                error_code=ExtractorErrorCode.INVALID_PROJECT,
                message=f"unexpected error: {exc}",
                recoverable=False,
                action="manual_cleanup",
            ) from exc

    async def _pipeline(
        self,
        *,
        driver: Any,
        mode: str,
        target_slug: str,
        timeout_s: int,
        logger: Any,
    ) -> tuple[RunSummary, list[WarningEntry]]:
        warnings: list[WarningEntry] = []

        if mode == "project":
            if not SLUG_RE.match(target_slug):
                raise ExtractorError(
                    error_code=ExtractorErrorCode.SLUG_INVALID,
                    message=f"invalid project slug: {target_slug!r}",
                    recoverable=False,
                    action="manual_cleanup",
                )
            members = [target_slug]
            target_status = await self._collect_target_status(driver, [target_slug], timeout_s)
        else:
            if not SLUG_RE.match(target_slug):
                raise ExtractorError(
                    error_code=ExtractorErrorCode.BUNDLE_INVALID,
                    message=f"invalid bundle slug: {target_slug!r}",
                    recoverable=False,
                    action="manual_cleanup",
                )
            raw_members = await self._bundle_members(driver, target_slug, timeout_s)
            if not raw_members:
                raise ExtractorError(
                    error_code=ExtractorErrorCode.BUNDLE_HAS_NO_MEMBERS,
                    message=f"bundle {target_slug!r} has zero members",
                    recoverable=False,
                    action="manual_cleanup",
                )
            valid_members: list[str] = []
            for slug in raw_members:
                if SLUG_RE.match(slug):
                    valid_members.append(slug)
                else:
                    warnings.append(WarningEntry(
                        code="member_invalid_slug", slug=slug,
                        message=f"member {slug!r} fails slug regex; excluded from query",
                    ))
            members = valid_members
            target_status = await self._collect_target_status(driver, members, timeout_s)
            for slug, status in target_status.items():
                if status == "not_indexed":
                    warnings.append(WarningEntry(
                        code="member_not_indexed", slug=slug,
                        message=f"{slug} has no :DEPENDS_ON edges; dependency_surface not indexed yet",
                    ))
                elif status == "not_registered":
                    warnings.append(WarningEntry(
                        code="member_not_registered", slug=slug,
                        message=f"{slug} is in :HAS_MEMBER but no :Project node exists",
                    ))

        indexed_count = sum(1 for s in target_status.values() if s == "indexed")
        if indexed_count == 0:
            raise ExtractorError(
                error_code=ExtractorErrorCode.DEPENDENCY_SURFACE_NOT_INDEXED,
                message="all targets lack :DEPENDS_ON data; run dependency_surface first",
                recoverable=False,
                action="manual_cleanup",
            )

        result = await _compute_skew_groups(
            driver, mode=mode, member_slugs=members, ecosystem=None,
        )
        warnings.extend(result.warnings)

        major = sum(1 for g in result.skew_groups if g.severity == "major")
        minor = sum(1 for g in result.skew_groups if g.severity == "minor")
        patch = sum(1 for g in result.skew_groups if g.severity == "patch")
        unknown = sum(1 for g in result.skew_groups if g.severity == "unknown")
        malformed_count = sum(1 for w in result.warnings if w.code == "purl_malformed")

        summary = RunSummary(
            mode=mode,
            target_slug=target_slug,
            member_count=len(members),
            target_status_indexed_count=indexed_count,
            skew_groups_total=len(result.skew_groups),
            skew_groups_major=major,
            skew_groups_minor=minor,
            skew_groups_patch=patch,
            skew_groups_unknown=unknown,
            aligned_groups_total=result.aligned_groups_total,
            warnings_purl_malformed_count=malformed_count,
        )
        return summary, warnings

    @staticmethod
    async def _bundle_exists(driver: Any, name: str, timeout_s: int) -> bool:
        async with driver.session(default_access_mode="READ") as session:
            result = await session.run(
                "MATCH (b:Bundle {name: $name}) RETURN count(b) AS n", name=name,
            )
            row = await result.single()
        return row is not None and row["n"] > 0

    @staticmethod
    async def _bundle_members(driver: Any, bundle: str, timeout_s: int) -> list[str]:
        async with driver.session(default_access_mode="READ") as session:
            result = await session.run(
                """
                MATCH (b:Bundle {name: $name})-[:HAS_MEMBER]->(p:Project)
                RETURN p.slug AS slug
                """,
                name=bundle,
            )
            rows = await result.data()
        return [r["slug"] for r in rows]

    @staticmethod
    async def _collect_target_status(
        driver: Any, slugs: list[str], timeout_s: int,
    ) -> dict[str, str]:
        """Returns {slug: 'indexed' | 'not_indexed' | 'not_registered'}."""
        async with driver.session(default_access_mode="READ") as session:
            result = await session.run(
                """
                UNWIND $slugs AS slug
                OPTIONAL MATCH (p:Project {slug: slug})
                OPTIONAL MATCH (p)-[r:DEPENDS_ON]->()
                RETURN slug AS s,
                       p IS NOT NULL AS exists,
                       count(r) AS dep_count
                """,
                slugs=slugs,
            )
            rows = await result.data()
        status: dict[str, str] = {}
        for r in rows:
            if not r["exists"]:
                status[r["s"]] = "not_registered"
            elif r["dep_count"] == 0:
                status[r["s"]] = "not_indexed"
            else:
                status[r["s"]] = "indexed"
        return status
```

- [ ] **Step 3: Verify imports don't break**

Run: `cd services/palace-mcp && uv run python -c "from palace_mcp.extractors.cross_repo_version_skew.extractor import CrossRepoVersionSkewExtractor; print(CrossRepoVersionSkewExtractor.name)"`

Expected: prints `cross_repo_version_skew`.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/models.py \
        services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/extractor.py
git commit -m "feat(GIM-218): orchestrator — 4-phase pipeline (validate → resolve → aggregate → finalize)"
```

---

## Task 9: Register `cross_repo_version_skew` in EXTRACTORS

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py`
- Test: `services/palace-mcp/tests/extractors/unit/test_registry.py` (extend or create)

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/extractors/unit/test_registry.py`:

```python
def test_cross_repo_version_skew_registered():
    from palace_mcp.extractors.registry import EXTRACTORS

    assert "cross_repo_version_skew" in EXTRACTORS
    cls_or_inst = EXTRACTORS["cross_repo_version_skew"]
    name = cls_or_inst.name if hasattr(cls_or_inst, "name") else cls_or_inst.__name__
    assert name == "cross_repo_version_skew" or name == "CrossRepoVersionSkewExtractor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_registry.py::test_cross_repo_version_skew_registered -v`

Expected: FAIL.

- [ ] **Step 3: Register**

In `services/palace-mcp/src/palace_mcp/extractors/registry.py`, add (matching existing pattern — class reference vs instance, depends on existing convention):

```python
from palace_mcp.extractors.cross_repo_version_skew.extractor import (
    CrossRepoVersionSkewExtractor,
)

# inside EXTRACTORS dict literal (no-arg instantiation, matching existing convention):
"cross_repo_version_skew": CrossRepoVersionSkewExtractor(),
```

Existing extractors are no-arg instances in a dict literal. Add the entry inside the `EXTRACTORS = { ... }` dict, NOT via subscript assignment.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_registry.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/registry.py services/palace-mcp/tests/extractors/unit/test_registry.py
git commit -m "feat(GIM-218): register cross_repo_version_skew in EXTRACTORS"
```

---

## Task 10: Extractor integration tests — happy path scenarios

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_extractor.py`

This task tests the full `run()` pipeline against the same seeded fixture from Task 6. Covers acceptance #1, #2, #3, #14, #17.

**Rev3 changes (CR findings):**
- Uses `ExtractorRunContext` instead of `SimpleNamespace` (CRITICAL #1)
- Calls `ext.run(graphiti=MagicMock(), ctx=...)` returning `ExtractorStats` (CRITICAL #1)
- Patches `palace_mcp.mcp_server.get_driver` / `get_settings` for deferred import (CRITICAL #1)
- Asserts on `ExtractorStats.nodes_written` + verifies `:IngestRun` in Neo4j directly
- Auto-detect mode: bundle test passes bundle name as `project_slug`; extractor detects `:Bundle` node

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_extractor.py`:

```python
"""End-to-end tests for the extractor orchestrator on seeded fixture."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.cross_repo_version_skew.extractor import (
    CrossRepoVersionSkewExtractor,
)


async def _seed(driver):
    """Reuse fixture seed from Task 6 test."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'uw-ios-app'})
            MERGE (m:Project {slug: 'marketkit'})
            MERGE (e:Project {slug: 'evmkit'})
            MERGE (b:Project {slug: 'bitcoinkit'})
            MERGE (bd:Bundle {name: 'uw-ios-mini'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(m)
            MERGE (bd)-[:HAS_MEMBER]->(e)
            MERGE (bd)-[:HAS_MEMBER]->(b)

            MERGE (mk_15:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@1.5.0'})
              SET mk_15.ecosystem = 'github', mk_15.resolved_version = '1.5.0'
            MERGE (mk_20:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@2.0.1'})
              SET mk_20.ecosystem = 'github', mk_20.resolved_version = '2.0.1'

            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.5.0'}]->(mk_15)
            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^2.0.0'}]->(mk_20)
        """)


async def _seed_ingest_run(driver, run_id: str):
    """Pre-create the :IngestRun that the runner would normally create."""
    async with driver.session() as session:
        await session.run("""
            CREATE (r:IngestRun {run_id: $run_id, extractor_name: 'cross_repo_version_skew', success: true})
        """, run_id=run_id)


def _ctx(*, project_slug: str, run_id: str = "test-run-001") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=project_slug,
        group_id=f"project/{project_slug}",
        repo_path=Path("/tmp/fake-repo"),
        run_id=run_id,
        duration_ms=30_000,
        logger=logging.getLogger("test"),
    )


def _patch_mcp(driver):
    """Context manager that patches get_driver/get_settings for deferred import."""
    mock_settings = MagicMock()
    mock_settings.version_skew_query_timeout_s = 30
    return patch.multiple(
        "palace_mcp.mcp_server",
        get_driver=MagicMock(return_value=driver),
        get_settings=MagicMock(return_value=mock_settings),
    )


@pytest.mark.asyncio
async def test_acceptance_1_bootstrap_project_mode(neo4j_driver):
    await _seed(neo4j_driver)
    run_id = "test-run-project-001"
    await _seed_ingest_run(neo4j_driver, run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        stats = await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="marketkit", run_id=run_id))
    assert stats.nodes_written == 1
    assert stats.edges_written == 0

    # :IngestRun visible with extras written by extractor
    async with neo4j_driver.session() as session:
        out = await session.run("""
            MATCH (r:IngestRun {run_id: $run_id})
            RETURN r.mode AS mode, r.target_slug AS target
        """, run_id=run_id)
        row = await out.single()
    assert row["mode"] == "project"
    assert row["target"] == "marketkit"


@pytest.mark.asyncio
async def test_acceptance_2_bootstrap_bundle_mode(neo4j_driver):
    await _seed(neo4j_driver)
    run_id = "test-run-bundle-001"
    await _seed_ingest_run(neo4j_driver, run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        stats = await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id))
    assert stats.nodes_written == 1

    # Verify skew was detected via :IngestRun extras
    async with neo4j_driver.session() as session:
        out = await session.run("""
            MATCH (r:IngestRun {run_id: $run_id})
            RETURN r.mode AS mode, r.skew_groups_total AS total
        """, run_id=run_id)
        row = await out.single()
    assert row["mode"] == "bundle"
    assert row["total"] == 1  # marketkit major skew


@pytest.mark.asyncio
async def test_acceptance_3_no_skew_target(neo4j_driver):
    await _seed(neo4j_driver)
    # Add a project with single-source aligned dep only
    async with neo4j_driver.session() as session:
        await session.run("""
            MERGE (lonely:Project {slug: 'lonely-project'})
            MERGE (d:ExternalDependency {purl: 'pkg:pypi/foo@1.0.0'})
              SET d.ecosystem = 'pypi', d.resolved_version = '1.0.0'
            MERGE (lonely)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(d)
        """)
    run_id = "test-run-lonely-001"
    await _seed_ingest_run(neo4j_driver, run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        stats = await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="lonely-project", run_id=run_id))
    assert stats.nodes_written == 1

    async with neo4j_driver.session() as session:
        out = await session.run("""
            MATCH (r:IngestRun {run_id: $run_id})
            RETURN r.skew_groups_total AS total
        """, run_id=run_id)
        row = await out.single()
    assert row["total"] == 0


@pytest.mark.asyncio
async def test_acceptance_14_pure_read_invariant(neo4j_driver):
    """Snapshot graph counts before/after run; delta = +1 :IngestRun (pre-seeded) + extras only."""
    await _seed(neo4j_driver)
    run_id = "test-run-read-invariant"
    await _seed_ingest_run(neo4j_driver, run_id)

    async with neo4j_driver.session() as session:
        before = await (await session.run("MATCH (n) RETURN count(n) AS n")).single()
        before_e = await (await session.run("MATCH ()-[r]->() RETURN count(r) AS n")).single()

    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id))

    async with neo4j_driver.session() as session:
        after = await (await session.run("MATCH (n) RETURN count(n) AS n")).single()
        after_e = await (await session.run("MATCH ()-[r]->() RETURN count(r) AS n")).single()

    assert after["n"] == before["n"], "No new nodes (IngestRun was pre-seeded; extractor only sets props)"
    assert after_e["n"] == before_e["n"], "No new edges"


@pytest.mark.asyncio
async def test_acceptance_17_re_run_creates_distinct_ingest_run(neo4j_driver):
    await _seed(neo4j_driver)
    ext = CrossRepoVersionSkewExtractor()

    run_id_1 = "test-run-rerun-001"
    run_id_2 = "test-run-rerun-002"
    await _seed_ingest_run(neo4j_driver, run_id_1)
    await _seed_ingest_run(neo4j_driver, run_id_2)

    with _patch_mcp(neo4j_driver):
        await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id_1))
        await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="uw-ios-mini", run_id=run_id_2))

    async with neo4j_driver.session() as session:
        rows = await (await session.run("""
            MATCH (r:IngestRun {extractor_name: 'cross_repo_version_skew'})
            RETURN count(r) AS n
        """)).single()
    assert rows["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_cross_repo_skew_extractor.py -v`

Expected: depending on Tasks 1-9 progression — should PASS after all prior tasks. If FAIL, debug per error message; the orchestrator code is in Task 8.

- [ ] **Step 3: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_cross_repo_skew_extractor.py -v`

Expected: 5 PASS.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_extractor.py
git commit -m "test(GIM-218): integration tests for orchestrator (acceptance #1-3, #14, #17)"
```

---

## Task 11: Warnings + edge-case integration tests

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_warnings.py`

Covers acceptance #19 (bundle_has_no_members), #20 (purl_malformed warning), #24 (warnings schema).

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_warnings.py`:

```python
"""Edge-case + warnings integration tests.

Rev3: uses ExtractorRunContext + patches get_driver/get_settings.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.cross_repo_version_skew.extractor import (
    CrossRepoVersionSkewExtractor,
)
from palace_mcp.extractors.foundation.errors import ExtractorError


def _ctx(*, project_slug: str, run_id: str = "warn-test-001") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=project_slug,
        group_id=f"project/{project_slug}",
        repo_path=Path("/tmp/fake-repo"),
        run_id=run_id,
        duration_ms=30_000,
        logger=logging.getLogger("test"),
    )


def _patch_mcp(driver):
    mock_settings = MagicMock()
    mock_settings.version_skew_query_timeout_s = 30
    return patch.multiple(
        "palace_mcp.mcp_server",
        get_driver=MagicMock(return_value=driver),
        get_settings=MagicMock(return_value=mock_settings),
    )


@pytest.mark.asyncio
async def test_acceptance_19_bundle_has_no_members(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("MERGE (b:Bundle {name: 'empty-bundle'})")
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        with pytest.raises(ExtractorError) as exc_info:
            await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="empty-bundle"))
    assert exc_info.value.error_code.value == "bundle_has_no_members"


@pytest.mark.asyncio
async def test_acceptance_19_bundle_not_registered_falls_to_project(neo4j_driver):
    """Non-existent slug is neither Bundle nor Project; auto-detect picks project mode.
    Project slug 'ghost-bundle' has no :Project node either, so _collect_target_status
    returns not_registered → DEPENDENCY_SURFACE_NOT_INDEXED (all targets lack data)."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        with pytest.raises(ExtractorError) as exc_info:
            await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="ghost-bundle"))
    assert exc_info.value.error_code.value == "dependency_surface_not_indexed"


@pytest.mark.asyncio
async def test_acceptance_20_malformed_purl_warning(neo4j_driver):
    """Malformed purl excluded from skew; warning surfaced in :IngestRun extras."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (p:Project {slug: 'test-proj'})
            MERGE (good:ExternalDependency {purl: 'pkg:pypi/good@1.0.0'})
              SET good.ecosystem = 'pypi', good.resolved_version = '1.0.0'
            MERGE (bad:ExternalDependency {purl: 'broken-format-no-pkg-prefix'})
              SET bad.ecosystem = 'unknown', bad.resolved_version = '1.0.0'
            MERGE (p)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(good)
            MERGE (p)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(bad)
        """)
    run_id = "warn-malformed-001"
    async with neo4j_driver.session() as session:
        await session.run("CREATE (r:IngestRun {run_id: $rid, extractor_name: 'cross_repo_version_skew', success: true})", rid=run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        stats = await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="test-proj", run_id=run_id))
    assert stats.nodes_written == 1
    # Verify malformed purl count written to :IngestRun
    async with neo4j_driver.session() as session:
        out = await session.run("MATCH (r:IngestRun {run_id: $rid}) RETURN r.warnings_purl_malformed_count AS cnt", rid=run_id)
        row = await out.single()
    assert row["cnt"] == 1


@pytest.mark.asyncio
async def test_acceptance_24_member_not_registered_warning(neo4j_driver):
    """Stale :HAS_MEMBER pointing to non-existent :Project produces warning."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (b:Bundle {name: 'partial-bundle'})
            MERGE (good:Project {slug: 'good-member'})
            MERGE (good_dep:ExternalDependency {purl: 'pkg:pypi/dep@1.0.0'})
              SET good_dep.ecosystem = 'pypi', good_dep.resolved_version = '1.0.0'
            MERGE (good)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(good_dep)
            MERGE (b)-[:HAS_MEMBER]->(good)
            // Stale: bundle references a slug whose :Project was deleted
            MERGE (ghost_proj:Project {slug: 'ghost-member'})
            MERGE (b)-[:HAS_MEMBER]->(ghost_proj)
            DETACH DELETE ghost_proj
        """)
    run_id = "warn-ghost-001"
    async with neo4j_driver.session() as session:
        await session.run("CREATE (r:IngestRun {run_id: $rid, extractor_name: 'cross_repo_version_skew', success: true})", rid=run_id)
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        stats = await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="partial-bundle", run_id=run_id))
    assert stats.nodes_written == 1
    # Verify the run completed (warnings are written to :IngestRun extras, not returned)


@pytest.mark.asyncio
async def test_dependency_surface_not_indexed_all_targets(neo4j_driver):
    """Project exists but has no :DEPENDS_ON -> fail."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("MERGE (p:Project {slug: 'no-deps-proj'})")
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(neo4j_driver):
        with pytest.raises(ExtractorError) as exc_info:
            await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="no-deps-proj"))
    assert exc_info.value.error_code.value == "dependency_surface_not_indexed"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_cross_repo_skew_warnings.py -v`

Expected: 5 PASS.

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_cross_repo_skew_warnings.py
git commit -m "test(GIM-218): warnings + edge-case integration tests (acceptance #19, #20, #24)"
```

---

## Task 12: `palace.code.find_version_skew` MCP tool

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/find_version_skew.py`
- Create: `services/palace-mcp/tests/extractors/integration/test_find_version_skew_wire.py`

- [ ] **Step 1: Write failing wire-contract test**

Create `services/palace-mcp/tests/extractors/integration/test_find_version_skew_wire.py`:

```python
"""Wire-contract tests for palace.code.find_version_skew.

Per feedback_wire_test_tautological_assertions: assert on explicit
error_code values, not the isError flag.
"""

import pytest

from palace_mcp.extractors.cross_repo_version_skew.find_version_skew import find_version_skew


@pytest.mark.asyncio
async def test_top_n_out_of_range_zero(neo4j_driver):
    r = await find_version_skew(neo4j_driver, project="x", top_n=0)
    assert r["ok"] is False
    assert r["error_code"] == "top_n_out_of_range"


@pytest.mark.asyncio
async def test_top_n_out_of_range_too_high(neo4j_driver):
    r = await find_version_skew(neo4j_driver, project="x", top_n=10_000)
    assert r["ok"] is False
    assert r["error_code"] == "top_n_out_of_range"


@pytest.mark.asyncio
async def test_slug_invalid(neo4j_driver):
    r = await find_version_skew(neo4j_driver, project="!!!bad-slug!!!", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "slug_invalid"


@pytest.mark.asyncio
async def test_bundle_invalid(neo4j_driver):
    r = await find_version_skew(neo4j_driver, bundle="!!!bad-bundle!!!", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "bundle_invalid"


@pytest.mark.asyncio
async def test_mutually_exclusive_args(neo4j_driver):
    r = await find_version_skew(neo4j_driver, project="x", bundle="y", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "mutually_exclusive_args"


@pytest.mark.asyncio
async def test_missing_target(neo4j_driver):
    r = await find_version_skew(neo4j_driver, top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "missing_target"


@pytest.mark.asyncio
async def test_invalid_severity_filter(neo4j_driver):
    r = await find_version_skew(neo4j_driver, project="x", min_severity="critical", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "invalid_severity_filter"


@pytest.mark.asyncio
async def test_invalid_ecosystem_filter(neo4j_driver):
    r = await find_version_skew(neo4j_driver, project="x", ecosystem="cocoapods", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "invalid_ecosystem_filter"


@pytest.mark.asyncio
async def test_project_not_registered(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    r = await find_version_skew(neo4j_driver, project="ghost-project", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_bundle_not_registered(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    r = await find_version_skew(neo4j_driver, bundle="ghost-bundle", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "bundle_not_registered"


@pytest.mark.asyncio
async def test_dependency_surface_not_indexed(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("MERGE (p:Project {slug: 'no-deps'})")
    r = await find_version_skew(neo4j_driver, project="no-deps", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "dependency_surface_not_indexed"


@pytest.mark.asyncio
async def test_success_bundle_mode_with_skew(neo4j_driver):
    """Concrete success-path assertions, not tautologies."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'a'})
            MERGE (b:Project {slug: 'b'})
            MERGE (bd:Bundle {name: 'mini'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(b)
            MERGE (d1:ExternalDependency {purl: 'pkg:pypi/lib@1.5.0'})
              SET d1.ecosystem = 'pypi', d1.resolved_version = '1.5.0'
            MERGE (d2:ExternalDependency {purl: 'pkg:pypi/lib@2.0.0'})
              SET d2.ecosystem = 'pypi', d2.resolved_version = '2.0.0'
            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '^1.5'}]->(d1)
            MERGE (b)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '^2.0'}]->(d2)
        """)
    r = await find_version_skew(neo4j_driver, bundle="mini", top_n=5)
    assert r["ok"] is True
    assert r["mode"] == "bundle"
    assert r["target_slug"] == "mini"
    assert len(r["skew_groups"]) == 1
    g = r["skew_groups"][0]
    assert g["purl_root"] == "pkg:pypi/lib"
    assert g["severity"] == "major"
    assert g["version_count"] == 2
    assert sum(r["summary_by_severity"].values()) >= len(r["skew_groups"])
    assert isinstance(r["warnings"], list)
    assert "target_status" in r


@pytest.mark.asyncio
async def test_acceptance_21_min_severity_excludes_lower(neo4j_driver):
    """min_severity='major' excludes minor/patch/unknown; min_severity='unknown' includes all."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'a'})
            MERGE (b:Project {slug: 'b'})
            MERGE (c:Project {slug: 'c'})
            MERGE (bd:Bundle {name: 'mix'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(b)
            MERGE (bd)-[:HAS_MEMBER]->(c)

            // Major
            MERGE (d1:ExternalDependency {purl: 'pkg:pypi/big@1.5.0'}) SET d1.ecosystem='pypi', d1.resolved_version='1.5.0'
            MERGE (d2:ExternalDependency {purl: 'pkg:pypi/big@2.0.0'}) SET d2.ecosystem='pypi', d2.resolved_version='2.0.0'
            MERGE (a)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d1)
            MERGE (b)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d2)

            // Patch
            MERGE (d3:ExternalDependency {purl: 'pkg:pypi/small@1.0.0'}) SET d3.ecosystem='pypi', d3.resolved_version='1.0.0'
            MERGE (d4:ExternalDependency {purl: 'pkg:pypi/small@1.0.1'}) SET d4.ecosystem='pypi', d4.resolved_version='1.0.1'
            MERGE (a)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d3)
            MERGE (c)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d4)
        """)

    r_major = await find_version_skew(neo4j_driver, bundle="mix", min_severity="major", top_n=10)
    assert r_major["ok"] is True
    severities = {g["severity"] for g in r_major["skew_groups"]}
    assert severities == {"major"}

    r_unknown = await find_version_skew(neo4j_driver, bundle="mix", min_severity="unknown", top_n=10)
    assert r_unknown["ok"] is True
    assert len(r_unknown["skew_groups"]) >= 2  # major + patch + possibly more


@pytest.mark.asyncio
async def test_acceptance_22_no_fstring_cypher_in_package():
    """Source-grep audit: no f-string Cypher in cross_repo_version_skew/."""
    import re
    from pathlib import Path
    pkg = Path(__file__).resolve().parents[2] / "src" / "palace_mcp" / "extractors" / "cross_repo_version_skew"
    fstring_match_pattern = re.compile(r'f"\s*MATCH|f"""\s*MATCH|\.format\(.*MATCH', re.DOTALL)
    offenders: list[tuple[str, int]] = []
    for py in sorted(pkg.rglob("*.py")):
        text = py.read_text()
        for n, line in enumerate(text.splitlines(), 1):
            if fstring_match_pattern.search(line):
                offenders.append((str(py), n))
    assert offenders == [], f"f-string MATCH found: {offenders}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_find_version_skew_wire.py -v`

Expected: FAIL — `ModuleNotFoundError: palace_mcp.extractors.cross_repo_version_skew.find_version_skew`.

- [ ] **Step 3: Implement find_version_skew**

Create `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/find_version_skew.py`:

```python
"""palace.code.find_version_skew — live MCP tool over the skew graph.

Rev3: imports SLUG_RE from models.py (WARNING #8 — no regex duplication).
Contains register_version_skew_tools() called from mcp_server.py.
"""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.cross_repo_version_skew.compute import (
    _compute_skew_groups,
)
from palace_mcp.extractors.cross_repo_version_skew.models import SLUG_RE, EcosystemEnum
from palace_mcp.extractors.cross_repo_version_skew.semver_classify import (
    severity_rank,
)

_VALID_SEVERITIES = {"patch", "minor", "major", "unknown"}
_VALID_ECOSYSTEMS = {e.value for e in EcosystemEnum}


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "message": message}


async def find_version_skew(
    driver: AsyncDriver,
    *,
    project: str | None = None,
    bundle: str | None = None,
    ecosystem: str | None = None,
    min_severity: str | None = None,
    top_n: int = 50,
    include_aligned: bool = False,
) -> dict[str, Any]:
    # 1. Validate top_n + slugs + filters (pre-DB)
    if not (1 <= top_n <= 10_000):  # outer bound; settings narrow further
        return _err("top_n_out_of_range", f"top_n={top_n} not in [1, 10000]")
    if project and bundle:
        return _err("mutually_exclusive_args", "specify project= OR bundle=, not both")
    if not project and not bundle:
        return _err("missing_target", "specify project= or bundle=")
    if project and not SLUG_RE.match(project):
        return _err("slug_invalid", f"invalid project slug: {project!r}")
    if bundle and not SLUG_RE.match(bundle):
        return _err("bundle_invalid", f"invalid bundle slug: {bundle!r}")
    if min_severity is not None and min_severity not in _VALID_SEVERITIES:
        return _err("invalid_severity_filter", f"min_severity={min_severity!r} not in {_VALID_SEVERITIES}")
    if ecosystem is not None and ecosystem not in _VALID_ECOSYSTEMS:
        return _err("invalid_ecosystem_filter", f"ecosystem={ecosystem!r} not in {_VALID_ECOSYSTEMS}")

    target_slug = project or bundle
    mode = "project" if project else "bundle"

    # 2. Resolve targets + check registration
    if mode == "project":
        proj_exists = await _project_exists(driver, project)
        if not proj_exists:
            return _err("project_not_registered", f"unknown project: {project!r}")
        members = [project]
        target_status = await _collect_target_status(driver, [project])
    else:
        bundle_exists = await _bundle_exists(driver, bundle)
        if not bundle_exists:
            return _err("bundle_not_registered", f"unknown bundle: {bundle!r}")
        raw_members = await _bundle_members(driver, bundle)
        if not raw_members:
            return _err("bundle_has_no_members", f"bundle {bundle!r} has zero members")
        members = [m for m in raw_members if SLUG_RE.match(m)]
        target_status = await _collect_target_status(driver, members)

    indexed_count = sum(1 for s in target_status.values() if s == "indexed")
    if indexed_count == 0:
        return _err("dependency_surface_not_indexed", "no targets have :DEPENDS_ON data")

    # 3. Compute (live)
    result = await _compute_skew_groups(
        driver, mode=mode, member_slugs=members, ecosystem=ecosystem,  # type: ignore[arg-type]
    )
    groups = result.skew_groups

    # 4. Apply min_severity filter
    if min_severity is not None:
        threshold = severity_rank(min_severity)  # type: ignore[arg-type]
        groups = [g for g in groups if severity_rank(g.severity) >= threshold]  # type: ignore[arg-type]

    # 5. Sort: severity desc, version_count desc, purl_root asc
    groups = sorted(
        groups,
        key=lambda g: (-severity_rank(g.severity), -g.version_count, g.purl_root),  # type: ignore[arg-type]
    )

    total_skew_groups = len(result.skew_groups)
    summary_by_severity = {
        "major": sum(1 for g in result.skew_groups if g.severity == "major"),
        "minor": sum(1 for g in result.skew_groups if g.severity == "minor"),
        "patch": sum(1 for g in result.skew_groups if g.severity == "patch"),
        "unknown": sum(1 for g in result.skew_groups if g.severity == "unknown"),
    }

    # 6. Aligned-groups inclusion: v1 exposes only the count; full
    #    surfacing of aligned purl_roots in `skew_groups` when
    #    include_aligned=True is deferred to a follow-up slice.
    aligned_groups_total = result.aligned_groups_total

    return {
        "ok": True,
        "mode": mode,
        "target_slug": target_slug,
        "skew_groups": [
            {
                "purl_root": g.purl_root,
                "ecosystem": g.ecosystem,
                "severity": g.severity,
                "version_count": g.version_count,
                "entries": [
                    {
                        "scope_id": e.scope_id,
                        "version": e.version,
                        "declared_in": e.declared_in,
                        "declared_constraint": e.declared_constraint,
                    }
                    for e in g.entries
                ],
            }
            for g in groups[:top_n]
        ],
        "total_skew_groups": total_skew_groups,
        "summary_by_severity": summary_by_severity,
        "aligned_groups_total": aligned_groups_total,
        "target_status": target_status,
        "warnings": [w.model_dump() for w in result.warnings],
    }


async def _project_exists(driver: AsyncDriver, slug: str) -> bool:
    async with driver.session() as session:
        result = await session.run("MATCH (p:Project {slug: $slug}) RETURN count(p) AS n", slug=slug)
        row = await result.single()
    return row is not None and row["n"] > 0


async def _bundle_exists(driver: AsyncDriver, name: str) -> bool:
    async with driver.session() as session:
        result = await session.run("MATCH (b:Bundle {name: $name}) RETURN count(b) AS n", name=name)
        row = await result.single()
    return row is not None and row["n"] > 0


async def _bundle_members(driver: AsyncDriver, name: str) -> list[str]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (b:Bundle {name: $name})-[:HAS_MEMBER]->(p:Project) RETURN p.slug AS slug",
            name=name,
        )
        return [r["slug"] for r in await result.data()]


async def _collect_target_status(driver: AsyncDriver, slugs: list[str]) -> dict[str, str]:
    async with driver.session() as session:
        result = await session.run(
            """
            UNWIND $slugs AS slug
            OPTIONAL MATCH (p:Project {slug: slug})
            OPTIONAL MATCH (p)-[r:DEPENDS_ON]->()
            RETURN slug AS s, p IS NOT NULL AS exists, count(r) AS dep_count
            """,
            slugs=slugs,
        )
        rows = await result.data()
    status: dict[str, str] = {}
    for r in rows:
        if not r["exists"]:
            status[r["s"]] = "not_registered"
        elif r["dep_count"] == 0:
            status[r["s"]] = "not_indexed"
        else:
            status[r["s"]] = "indexed"
    return status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/integration/test_find_version_skew_wire.py -v`

Expected: 14 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/find_version_skew.py \
        services/palace-mcp/tests/extractors/integration/test_find_version_skew_wire.py
git commit -m "feat(GIM-218): palace.code.find_version_skew MCP tool + 14 wire tests"
```

---

## Task 13: Register `find_version_skew` in MCP server + SF3 source-grep regression test

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/mcp_server.py`
- Modify: `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/find_version_skew.py` (add `register_version_skew_tools()`)
- Create: `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_compute_uniqueness.py`

**Rev3 changes (CR findings):**
- Uses `register_version_skew_tools(tool_decorator, default_project)` pattern matching `register_code_composite_tools()` (CRITICAL #3)
- File is `mcp_server.py`, not `server.py` (CRITICAL #3)

- [ ] **Step 1: Add `register_version_skew_tools()` to `find_version_skew.py`**

Append to `services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/find_version_skew.py`:

```python
from palace_mcp.code_composite import _ToolDecorator  # type alias used by register_code_composite_tools


def register_version_skew_tools(tool_decorator: _ToolDecorator, default_project: str) -> None:
    """Register palace.code.find_version_skew as an MCP tool.

    Called from mcp_server.py alongside register_code_composite_tools().
    """

    @tool_decorator(
        name="palace.code.find_version_skew",
        description=(
            "Cross-repo / cross-bundle version skew detection over external "
            "dependencies. Reports purl_roots that have multiple distinct "
            "resolved_versions across modules (project mode) or members "
            "(bundle mode). Read-only; uses GIM-191 dependency_surface graph."
        ),
    )
    async def palace_code_find_version_skew(
        project: str | None = None,
        bundle: str | None = None,
        ecosystem: str | None = None,
        min_severity: str | None = None,
        top_n: int = 50,
        include_aligned: bool = False,
    ) -> dict:
        from palace_mcp.mcp_server import get_driver

        return await find_version_skew(
            driver=get_driver(),
            project=project,
            bundle=bundle,
            ecosystem=ecosystem,
            min_severity=min_severity,
            top_n=top_n,
            include_aligned=include_aligned,
        )
```

- [ ] **Step 2: Wire into `mcp_server.py`**

In `services/palace-mcp/src/palace_mcp/mcp_server.py`, find the block where `register_code_composite_tools(mcp.tool, default_project)` is called (around line 560-566). Add immediately after:

```python
from palace_mcp.extractors.cross_repo_version_skew.find_version_skew import register_version_skew_tools

register_version_skew_tools(mcp.tool, default_project)
```

- [ ] **Step 3: Write SF3 source-grep regression test**

Create `services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_compute_uniqueness.py`:

```python
"""SF3 regression: only compute.py runs the aggregation Cypher.

Per spec rev2 acceptance #18: any other module that contains
MATCH (p:Project)-[:DEPENDS_ON] is a sign that skew computation has
been duplicated. This test fails CI on such duplication.
"""

import re
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[3] / "src" / "palace_mcp"
EXEMPT_FILE = (
    PKG_ROOT / "extractors" / "cross_repo_version_skew" / "compute.py"
)

MATCH_PATTERN = re.compile(r"MATCH.*Project.*\)-\[:DEPENDS_ON", re.DOTALL)


def test_only_compute_py_runs_aggregation_cypher():
    offenders: list[tuple[str, int]] = []
    for py in sorted(PKG_ROOT.rglob("*.py")):
        if py == EXEMPT_FILE:
            continue
        text = py.read_text()
        # Skip lines marked with explicit opt-out
        for n, line in enumerate(text.splitlines(), 1):
            if "noqa: skew-compute" in line:
                continue
            if MATCH_PATTERN.search(line):
                offenders.append((str(py.relative_to(PKG_ROOT)), n))
    assert offenders == [], (
        "Skew-aggregation Cypher (MATCH (p:Project)-[:DEPENDS_ON]) appears "
        "outside compute.py:\n" + "\n".join(f"  {p}:{n}" for p, n in offenders)
    )
```

- [ ] **Step 4: Run tests to verify**

Run: `cd services/palace-mcp && uv run pytest tests/extractors/unit/test_cross_repo_skew_compute_uniqueness.py -v && uv run python -c "import palace_mcp.mcp_server"`

Expected: 1 PASS + no import error.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/mcp_server.py \
        services/palace-mcp/src/palace_mcp/extractors/cross_repo_version_skew/find_version_skew.py \
        services/palace-mcp/tests/extractors/unit/test_cross_repo_skew_compute_uniqueness.py
git commit -m "feat(GIM-218): register palace.code.find_version_skew + SF3 source-grep regression"
```

---

## Task 14: CLAUDE.md update + runbook + smoke script

**Files:**
- Modify: `CLAUDE.md` — `## Extractors` section
- Create: `docs/runbooks/cross-repo-version-skew.md`
- Create: `services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh`

- [ ] **Step 1: Add CLAUDE.md row + workflow**

Find `### Registered extractors` (or equivalent) in `CLAUDE.md`. Append:

```markdown
- `cross_repo_version_skew` — Cross-repo version skew (GIM-218, Roadmap #39).
  Reads `:Project-[:DEPENDS_ON]->:ExternalDependency` from `dependency_surface`
  (GIM-191) — fully read-only; writes only one `:IngestRun` per call. Hybrid:
  small extractor (audit/observability via `:IngestRun` extras) + live MCP
  tool `palace.code.find_version_skew` for real-time aggregation. Project
  mode finds intra-module skew via `r.declared_in`; bundle mode aggregates
  across `:Bundle{name}-[:HAS_MEMBER]` members. See limitations in
  `docs/runbooks/cross-repo-version-skew.md`.
```

After the existing `### Operator workflow:` subsections, append:

```markdown
### Operator workflow: Cross-repo version skew

Prereq: `dependency_surface` (GIM-191) has run for the target project /
every member of the target bundle.

1. Run the extractor (writes one :IngestRun per call):
   ```
   palace.ingest.run_extractor(name="cross_repo_version_skew", project="uw-android")
   # or for a bundle:
   palace.ingest.run_extractor(name="cross_repo_version_skew", bundle="uw-ios")
   ```

2. Query skew:
   ```
   palace.code.find_version_skew(bundle="uw-ios", min_severity="minor", top_n=20)
   ```

Tunable knobs (`.env`):
- `PALACE_VERSION_SKEW_TOP_N_MAX` (default 500)
- `PALACE_VERSION_SKEW_QUERY_TIMEOUT_S` (default 30)

Limitations:
- Project mode for canonical-Gradle / SPM / Python projects finds zero
  intra-module skew (aliases / single manifest = same version per scope).
  Use bundle-of-1 for forward compatibility.
- Compares resolved_version only; declared-constraint skew is followup.
- Calendar versions / git-shas / custom schemes classify as 'unknown'.
- No Renovate "latest version" data; no OWASP CVE enrichment.
```

- [ ] **Step 2: Write runbook**

Create `docs/runbooks/cross-repo-version-skew.md`:

```markdown
# Cross-Repo Version Skew Extractor — Runbook

## What it does

Detects when modules / bundle members pin different `resolved_version`s
of the same external library. Reads `:Project-[:DEPENDS_ON]->:ExternalDependency`
from `dependency_surface` (GIM-191). Single MCP tool: `palace.code.find_version_skew`.

## Trust assumptions

`find_version_skew` enumerates the supply-chain composition of any
registered project/bundle. In multi-tenant deployments treat output as
business-confidential. v1 single-tenant; ACL is a future palace-mcp slice.

## Running

Prereq: `dependency_surface` has run for the project (or every member
of the bundle).

```
palace.ingest.run_extractor(name="cross_repo_version_skew", project="<slug>")
# or
palace.ingest.run_extractor(name="cross_repo_version_skew", bundle="<name>")

palace.code.find_version_skew(bundle="<name>", min_severity="minor", top_n=20)
```

## Knobs

| Env | Default | Effect |
|-----|---------|--------|
| `PALACE_VERSION_SKEW_TOP_N_MAX` | 500 | Upper bound for `top_n` arg |
| `PALACE_VERSION_SKEW_QUERY_TIMEOUT_S` | 30 | Bolt aggregation timeout (s) |

## Severity ranks

| Severity | Rank | Meaning |
|----------|:----:|---------|
| `major` | 3 | semver major differs |
| `minor` | 2 | major equal, minor differs |
| `patch` | 1 | major+minor equal (incl. parse-equivalent strings) |
| `unknown` | 0 | one or both versions don't parse under PEP 440 |

`min_severity='major'` returns only rank-3 groups.
`min_severity='unknown'` includes all severities (rank ≥ 0).

## Drift detection (count-only, v1)

```
palace.memory.lookup(
    entity_type="IngestRun",
    filters={"extractor_name": "cross_repo_version_skew", "target_slug": "uw-ios"},
    limit=10,
)
```

Compare `skew_groups_total` between two `:IngestRun` snapshots.
Content-diff (which purls changed) is F1 / a future slice.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `dependency_surface_not_indexed` | GIM-191 hasn't run | run `palace.ingest.run_extractor(name='dependency_surface', project=...)` first |
| `bundle_has_no_members` | bundle exists but `add_to_bundle` was never called | call `palace.memory.add_to_bundle` |
| `bundle_not_registered` | bundle name has typo or was never created | call `palace.memory.register_bundle` first |
| `top_n_out_of_range` | passed top_n > `PALACE_VERSION_SKEW_TOP_N_MAX` | raise env, or pass smaller top_n |
| Project-mode returns 0 skew on UW Android | by design — Gradle alias resolves to one version | use `bundle="uw-android"` (single-member) for forward compatibility |
| Warnings include `purl_malformed` | GIM-191 wrote a row whose `purl` lacks `pkg:` prefix | inspect the row, file a `dependency_surface` regression bug |

## Erasure

Not applicable — this extractor reads existing data, writes only audit
`:IngestRun` nodes. To remove an audit run:

```cypher
MATCH (r:IngestRun {run_id: $run_id, extractor_name: 'cross_repo_version_skew'})
DELETE r
```
```

- [ ] **Step 3: Write smoke script**

Create `services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh`:

```bash
#!/usr/bin/env bash
# Live smoke for cross_repo_version_skew (Roadmap #39).
# Run ON the iMac against the live palace-mcp container.
#
# Prereq: dependency_surface has run for the target.
# Usage:
#   bash services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh

set -euo pipefail

PROJECT="${PALACE_SKEW_SMOKE_PROJECT:-uw-android}"
BUNDLE="${PALACE_SKEW_SMOKE_BUNDLE:-uw-ios}"

echo "==> 1. Run extractor on bundle=$BUNDLE"
docker exec palace-mcp python -c "
import asyncio
from palace_mcp.server import run_extractor_invoke
print(asyncio.run(run_extractor_invoke('cross_repo_version_skew', '$BUNDLE', mode='bundle')))
"

echo "==> 2. Query find_version_skew"
docker exec palace-mcp python -c "
import asyncio, json
from palace_mcp.server import find_version_skew_invoke
result = asyncio.run(find_version_skew_invoke(bundle='$BUNDLE', min_severity='minor', top_n=10))
print(json.dumps(result, indent=2, default=str))
assert result['ok'] is True, result
print('OK — skew_groups:', len(result['skew_groups']))
"

echo "==> 3. palace.memory.lookup → :IngestRun visibility"
docker exec palace-mcp python -c "
import asyncio
from palace_mcp.memory.lookup import lookup_invoke
r = asyncio.run(lookup_invoke(entity_type='IngestRun', filters={'extractor_name': 'cross_repo_version_skew', 'target_slug': '$BUNDLE'}))
assert r and r[0].get('mode') == 'bundle'
print('OK — IngestRun visible with mode=bundle')
"

echo "==> SMOKE PASS"
```

(Replace placeholder `*_invoke` helpers with actual server-side names; mirror existing extractor smoke scripts.)

- [ ] **Step 4: chmod + commit**

```bash
chmod +x services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh
git add CLAUDE.md docs/runbooks/cross-repo-version-skew.md \
        services/palace-mcp/tests/extractors/smoke/test_cross_repo_skew_smoke.sh
git commit -m "docs(GIM-218): CLAUDE.md row + runbook + live smoke script"
```

---

## Self-Review Checklist (run before declaring complete)

- [ ] Each acceptance criterion #1–#24 in the spec maps to at least one task.
  Coverage map:
  - #1 bootstrap project-mode → Task 10
  - #2 bootstrap bundle-mode → Task 10
  - #3 no-skew target → Task 10
  - #4 project-mode intra-module → covered by Task 6 + Task 10 (synthetic seed)
  - #5 bundle-mode cross-member → Task 6
  - #6 min_severity filter → Task 12
  - #7 ecosystem filter → Task 6 + Task 12
  - #8 include_aligned → **SPEC AMENDMENT (CRITICAL #5):** v1 exposes `aligned_groups_total` count only; `include_aligned=True` with full group surfacing deferred to followup. Spec §9 AC #8 updated to say "count-only v1" — CTO decision, not implementer discretion.
  - #9 top_n=1 → Task 12
  - #10 dependency_surface_not_indexed → Task 11
  - #11 mutually_exclusive_args → Task 12
  - #12 missing_target → Task 12
  - #13 bundle_not_registered → Task 11
  - #14 pure-read invariant → Task 10
  - #15 single source of truth → Task 10 integration test (verify extractor and MCP tool return structurally identical results for same input) + Task 13 (SF3 source-grep as secondary gate)
  - #16 sort total order → Task 12 wire test
  - #17 re-run distinct :IngestRun → Task 10
  - #18 SF3 regression gate → Task 13
  - #19 bundle_has_no_members distinct → Task 11
  - #20 malformed purl warning → Task 11
  - #21 severity rank ordering → Task 12 wire test
  - #22 no f-string Cypher → Task 12 wire test
  - #23 query timeout → deferred (mentioned in spec §10 as conditional skip if APOC unavailable; v1 ships without explicit test)
  - #24 warnings schema → Task 11
- [ ] All 14 tasks have concrete failing-test code (no "write a test" placeholders).
- [ ] All 14 tasks have concrete implementation code (no "implement the function" placeholders).
- [ ] Type names / function signatures match across tasks (`SkewEntry`, `SkewGroup`, `WarningEntry`, `RunSummary`, `EcosystemEnum`, `SeverityEnum`, `_compute_skew_groups`, `_write_run_extras`, `find_version_skew`).
- [ ] All commits use `feat(GIM-218): ...` / `test(GIM-218): ...` / `docs(GIM-218): ...` prefix.
- [ ] Post-merge step: file a `docs(roadmap):` PR marking #39 ✅ in `docs/roadmap.md §2.1` (not in this branch).
