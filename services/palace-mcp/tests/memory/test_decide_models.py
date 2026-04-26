"""Unit tests for DecideRequest Pydantic model."""

import pytest
from pydantic import ValidationError

from palace_mcp.memory.decide_models import (
    VALID_DECISION_MAKERS,
    DecideRequest,
)

_MINIMAL = dict(
    title="x",
    body="y",
    slice_ref="GIM-1",
    decision_maker_claimed="cto",
)


def test_valid_minimal() -> None:
    req = DecideRequest(**_MINIMAL)
    assert req.title == "x"
    assert req.confidence == 1.0
    assert req.tags is None
    assert req.evidence_ref is None
    assert req.project is None


def test_valid_full() -> None:
    req = DecideRequest(
        title="A" * 200,
        body="B" * 2000,
        slice_ref="GIM-99",
        decision_maker_claimed="operator",
        project="gimle",
        decision_kind="design",
        tags=["a", "b"],
        evidence_ref=["sha1", "sha2"],
        confidence=0.7,
    )
    assert req.decision_kind == "design"
    assert req.tags == ["a", "b"]


def test_title_empty_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "title": ""})


def test_title_too_long_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "title": "x" * 201})


def test_body_empty_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "body": ""})


def test_body_too_long_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "body": "x" * 2001})


def test_slice_ref_bad_format_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "slice_ref": "bad-format"})


def test_slice_ref_gim_ok() -> None:
    req = DecideRequest(**{**_MINIMAL, "slice_ref": "GIM-123"})
    assert req.slice_ref == "GIM-123"


def test_slice_ref_n_plus_ok() -> None:
    req = DecideRequest(**{**_MINIMAL, "slice_ref": "N+2a"})
    assert req.slice_ref == "N+2a"


def test_slice_ref_n_plus_multipart_ok() -> None:
    req = DecideRequest(**{**_MINIMAL, "slice_ref": "N+1a.1"})
    assert req.slice_ref == "N+1a.1"


def test_slice_ref_operator_decision_ok() -> None:
    req = DecideRequest(**{**_MINIMAL, "slice_ref": "operator-decision-20260426"})
    assert req.slice_ref == "operator-decision-20260426"


def test_decision_maker_invalid_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "decision_maker_claimed": "hacker"})


@pytest.mark.parametrize("maker", sorted(VALID_DECISION_MAKERS))
def test_each_valid_maker(maker: str) -> None:
    req = DecideRequest(**{**_MINIMAL, "decision_maker_claimed": maker})
    assert req.decision_maker_claimed == maker


def test_confidence_too_high_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "confidence": 1.5})


def test_confidence_negative_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "confidence": -0.1})


def test_tags_too_many_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "tags": ["a"] * 17})


def test_tags_max_ok() -> None:
    req = DecideRequest(**{**_MINIMAL, "tags": ["a"] * 16})
    assert len(req.tags) == 16  # type: ignore[arg-type]


def test_evidence_ref_too_many_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "evidence_ref": ["x"] * 33})


def test_decision_kind_too_long_raises() -> None:
    with pytest.raises(ValidationError):
        DecideRequest(**{**_MINIMAL, "decision_kind": "x" * 81})
