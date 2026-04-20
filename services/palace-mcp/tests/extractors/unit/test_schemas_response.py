"""Unit tests for extractor Pydantic response models (spec §4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.schemas import (
    ExtractorDescriptor,
    ExtractorErrorResponse,
    ExtractorListResponse,
    ExtractorRunResponse,
)


def test_run_response_success() -> None:
    r = ExtractorRunResponse(
        run_id="abc-123",
        extractor="heartbeat",
        project="gimle",
        started_at="2026-04-20T10:00:00+00:00",
        finished_at="2026-04-20T10:00:01+00:00",
        duration_ms=1000,
        nodes_written=1,
        edges_written=0,
        success=True,
    )
    assert r.ok is True


def test_run_response_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ExtractorRunResponse(
            run_id="abc",
            extractor="heartbeat",
            project="gimle",
            started_at="2026-04-20T10:00:00+00:00",
            finished_at="2026-04-20T10:00:01+00:00",
            duration_ms=1,
            nodes_written=0,
            edges_written=0,
            success=True,
            unknown_field="x",  # type: ignore[call-arg]
        )


def test_error_response_minimal() -> None:
    r = ExtractorErrorResponse(
        error_code="invalid_slug",
        message="invalid slug: '../etc'",
    )
    assert r.ok is False
    assert r.extractor is None
    assert r.project is None
    assert r.run_id is None


def test_error_response_full() -> None:
    r = ExtractorErrorResponse(
        error_code="extractor_runtime_error",
        message="timeout",
        extractor="heartbeat",
        project="gimle",
        run_id="abc-123",
    )
    assert r.ok is False
    assert r.extractor == "heartbeat"


def test_error_response_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ExtractorErrorResponse(
            error_code="x",
            message="y",
            bogus="z",  # type: ignore[call-arg]
        )


def test_descriptor_and_list() -> None:
    d = ExtractorDescriptor(name="heartbeat", description="diagnostic probe")
    lst = ExtractorListResponse(extractors=[d])
    assert lst.ok is True
    assert lst.extractors[0].name == "heartbeat"
