"""Unit tests for extractors/foundation/source_context.py (Tasks 3.1 + 3.1b).

RED tests — fail until source_context.py is implemented.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Task 3.1: classify() table-driven tests (plan §GIM-283-4 Task 3.1 RED)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        # library paths
        ("Sources/TronKit/Foo.swift", "library"),
        ("src/lib/core.py", "library"),
        ("libs/utils/helper.ts", "library"),
        # example paths
        ("iOS Example/Sources/Manager.swift", "example"),
        ("ios-example/Sources/Manager.swift", "example"),  # C3: case-insensitive
        ("IOS_EXAMPLE/foo.swift", "example"),  # C3: uppercase + underscore
        ("Samples/Demo/App.swift", "example"),
        ("Demos/BasicApp/main.swift", "example"),
        # test paths
        ("Tests/FooTests.swift", "test"),
        ("tests/unit/test_foo.py", "test"),  # C3: lowercase variant
        ("spec/helpers/utils.rb", "test"),
        ("SomeModule/SomeTests.swift", "test"),  # Test*.swift suffix
        ("foo_test.py", "test"),  # _test.py suffix
        # other paths
        ("Scripts/build.sh", "other"),
        ("Makefile", "other"),
        ("docs/README.md", "other"),
    ],
)
def test_classifies_paths(path: str, expected: str) -> None:
    from palace_mcp.extractors.foundation.source_context import classify

    result = classify(path)
    assert result == expected, f"classify({path!r}) = {result!r}, want {expected!r}"


def test_classify_no_overrides_arg() -> None:
    from palace_mcp.extractors.foundation.source_context import classify

    # calling without overrides should work
    assert classify("Sources/Kit/Foo.swift") == "library"


def test_classify_with_none_overrides() -> None:
    from palace_mcp.extractors.foundation.source_context import classify

    assert classify("Sources/Kit/Foo.swift", overrides=None) == "library"


# ---------------------------------------------------------------------------
# Task 3.1b: overrides YAML tests (plan §GIM-283-4 Task 3.1b RED)
# ---------------------------------------------------------------------------


def test_overrides_yaml_applied(tmp_path: Path) -> None:
    """Overrides file takes priority over default classification."""
    from palace_mcp.extractors.foundation.source_context import classify, load_overrides

    # create .gimle/source-context-overrides.yaml
    gimle_dir = tmp_path / ".gimle"
    gimle_dir.mkdir()
    overrides_file = gimle_dir / "source-context-overrides.yaml"
    overrides_file.write_text(textwrap.dedent("""\
        "**/Vendor/**": "other"
    """))

    overrides = load_overrides(str(tmp_path))
    assert overrides is not None

    # normally "Sources/..." → library, but Vendor override wins
    assert classify("Sources/Vendor/ThirdParty.swift", overrides=overrides) == "other"
    # non-overridden path still classifies normally
    assert classify("Sources/TronKit/Foo.swift", overrides=overrides) == "library"


def test_overrides_missing_file_no_error(tmp_path: Path) -> None:
    """No .gimle/source-context-overrides.yaml → returns None, no exception."""
    from palace_mcp.extractors.foundation.source_context import load_overrides

    result = load_overrides(str(tmp_path))
    assert result is None


def test_overrides_invalid_value_ignored(tmp_path: Path) -> None:
    """YAML entries with invalid context values are filtered out."""
    from palace_mcp.extractors.foundation.source_context import classify, load_overrides

    gimle_dir = tmp_path / ".gimle"
    gimle_dir.mkdir()
    (gimle_dir / "source-context-overrides.yaml").write_text(textwrap.dedent("""\
        "**/Vendor/**": "invalid_context"
        "**/Shims/**": "other"
    """))

    overrides = load_overrides(str(tmp_path))
    assert overrides is not None
    # invalid_context is filtered; only Shims override remains
    assert "other" in overrides.values()
    result = classify("Sources/Vendor/Foo.swift", overrides=overrides)
    # invalid override was dropped → falls through to normal classification
    assert result == "library"
    # valid override still works
    assert classify("Sources/Shims/Bar.swift", overrides=overrides) == "other"


def test_overrides_empty_yaml_no_error(tmp_path: Path) -> None:
    """Empty YAML file is handled gracefully."""
    from palace_mcp.extractors.foundation.source_context import load_overrides

    gimle_dir = tmp_path / ".gimle"
    gimle_dir.mkdir()
    (gimle_dir / "source-context-overrides.yaml").write_text("")

    result = load_overrides(str(tmp_path))
    assert result is None


def test_classify_windows_backslash() -> None:
    """Backslashes normalised to forward slashes before matching."""
    from palace_mcp.extractors.foundation.source_context import classify

    assert classify("Sources\\TronKit\\Foo.swift") == "library"
    assert classify("Tests\\FooTests.swift") == "test"
