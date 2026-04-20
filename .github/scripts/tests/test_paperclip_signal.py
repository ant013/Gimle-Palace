"""Tests for paperclip_signal.py — added incrementally per plan tasks."""

from __future__ import annotations


def test_infrastructure_loads(load_fixture):
    """Smoke-test: fixtures load via conftest helper."""
    payload = load_fixture("workflow_run_success")
    assert payload["workflow_run"]["conclusion"] == "success"
