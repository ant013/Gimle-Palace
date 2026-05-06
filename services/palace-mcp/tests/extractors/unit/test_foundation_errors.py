"""Unit tests for cross_repo_version_skew error codes in ExtractorErrorCode."""

from __future__ import annotations

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
