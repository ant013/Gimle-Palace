from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction


def test_parsed_function_minimal():
    fn = ParsedFunction(
        name="parse_x",
        start_line=10,
        end_line=25,
        ccn=4,
        parameter_count=2,
        nloc=12,
    )
    assert fn.name == "parse_x"
    assert fn.ccn == 4


def test_parsed_function_rejects_negative_ccn():
    with pytest.raises(ValidationError):
        ParsedFunction(
            name="bad",
            start_line=1,
            end_line=2,
            ccn=-1,
            parameter_count=0,
            nloc=1,
        )


def test_parsed_function_rejects_end_before_start():
    with pytest.raises(ValidationError):
        ParsedFunction(
            name="bad",
            start_line=10,
            end_line=5,
            ccn=1,
            parameter_count=0,
            nloc=1,
        )


def test_parsed_file_ccn_total_sums_functions():
    f1 = ParsedFunction(
        name="a", start_line=1, end_line=5, ccn=3, parameter_count=0, nloc=4
    )
    f2 = ParsedFunction(
        name="b", start_line=10, end_line=20, ccn=7, parameter_count=1, nloc=10
    )
    pf = ParsedFile(path="src/foo.py", language="python", functions=(f1, f2))
    assert pf.ccn_total == 10


def test_parsed_file_empty_functions_ccn_zero():
    pf = ParsedFile(path="src/foo.py", language="python", functions=())
    assert pf.ccn_total == 0


def test_parsed_file_path_must_be_relative_posix():
    with pytest.raises(ValidationError):
        ParsedFile(path="/abs/path.py", language="python", functions=())
    with pytest.raises(ValidationError):
        ParsedFile(path="windows\\style.py", language="python", functions=())


def test_parsed_models_are_frozen():
    fn = ParsedFunction(
        name="x", start_line=1, end_line=2, ccn=1, parameter_count=0, nloc=1
    )
    with pytest.raises(ValidationError):
        fn.ccn = 99  # type: ignore[misc]
