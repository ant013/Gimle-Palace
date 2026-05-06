"""Unit tests for cross_repo_version_skew Pydantic models and enums."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.cross_repo_version_skew.models import (
    EcosystemEnum,
    SeverityEnum,
    SkewEntry,
    SkewGroup,
    RunSummary,
    WarningCodeEnum,
    WarningEntry,
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
