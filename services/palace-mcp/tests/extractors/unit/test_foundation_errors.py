from palace_mcp.extractors.foundation.errors import ExtractorErrorCode


def test_ownership_error_codes_present():
    """Code-ownership-specific error codes are defined on the enum."""
    assert ExtractorErrorCode.OWNERSHIP_DIFF_FAILED.value == "ownership_diff_failed"
    assert ExtractorErrorCode.REPO_HEAD_INVALID.value == "repo_head_invalid"
    assert ExtractorErrorCode.OWNERSHIP_MAX_FILES_EXCEEDED.value == "ownership_max_files_exceeded"
    assert ExtractorErrorCode.GIT_HISTORY_NOT_INDEXED.value == "git_history_not_indexed"
