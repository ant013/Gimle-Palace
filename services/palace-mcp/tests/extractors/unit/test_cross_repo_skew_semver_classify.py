"""Unit tests for semver_classify — pairwise version comparison."""

from __future__ import annotations

import pytest

from palace_mcp.extractors.cross_repo_version_skew.semver_classify import (
    classify,
    max_pairwise_severity,
    severity_rank,
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
    with pytest.raises(ValueError):
        max_pairwise_severity(["1.5.0"])
