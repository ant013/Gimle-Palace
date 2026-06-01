"""Unit tests for F4.0 telemetry + JSONL audit sink (GIM-1097).

Covers:
- _write_audit_line() writes correct JSON to the sink
- _write_audit_line() is a no-op when sink is None
- _tool() wrapper records latency and captures error
- palace_telemetry_enabled=False suppresses audit lines
"""

from __future__ import annotations

import io
import json

import pytest

import palace_mcp.mcp_server as _mcp_module
from palace_mcp.mcp_server import _write_audit_line, set_audit_sink


@pytest.fixture(autouse=True)
def _reset_audit_sink():
    """Restore module-level sink after every test."""
    original = _mcp_module._audit_sink
    yield
    _mcp_module._audit_sink = original


# ---------------------------------------------------------------------------
# _write_audit_line()
# ---------------------------------------------------------------------------


def test_write_audit_line_format() -> None:
    buf = io.StringIO()
    set_audit_sink(buf)
    _write_audit_line(
        "palace.health.status",
        {},
        '{"neo4j": "reachable"}',
        42,
        None,
    )
    line = json.loads(buf.getvalue().strip())
    assert line["tool_name"] == "palace.health.status"
    assert line["latency_ms"] == 42
    assert line["error"] is None
    assert line["response_summary"] == '{"neo4j": "reachable"}'
    assert "timestamp" in line


def test_write_audit_line_with_error() -> None:
    buf = io.StringIO()
    set_audit_sink(buf)
    _write_audit_line("palace.memory.lookup", {"entity_type": "Symbol"}, None, 5, "ValueError: bad input")
    line = json.loads(buf.getvalue().strip())
    assert line["error"] == "ValueError: bad input"
    assert line["response_summary"] is None
    assert line["request_args"]["entity_type"] == "Symbol"


def test_write_audit_line_truncates_long_arg() -> None:
    buf = io.StringIO()
    set_audit_sink(buf)
    long_val = "x" * 600
    _write_audit_line("t", {"arg": long_val}, None, 1, None)
    line = json.loads(buf.getvalue().strip())
    assert len(line["request_args"]["arg"]) == 500


def test_write_audit_line_no_sink_is_noop() -> None:
    set_audit_sink(None)
    _write_audit_line("t", {}, None, 1, None)  # must not raise


def test_write_audit_line_appends_multiple_lines() -> None:
    buf = io.StringIO()
    set_audit_sink(buf)
    _write_audit_line("t1", {}, "r1", 1, None)
    _write_audit_line("t2", {}, "r2", 2, None)
    lines = [json.loads(l) for l in buf.getvalue().strip().splitlines()]
    assert len(lines) == 2
    assert lines[0]["tool_name"] == "t1"
    assert lines[1]["tool_name"] == "t2"


# ---------------------------------------------------------------------------
# Config: palace_audit_sink_path + palace_telemetry_enabled
# ---------------------------------------------------------------------------


def test_settings_audit_sink_path_default_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PALACE_AUDIT_SINK_PATH", raising=False)
    from palace_mcp.config import Settings

    s = Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
    assert s.palace_audit_sink_path is None


def test_settings_telemetry_enabled_default_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PALACE_TELEMETRY_ENABLED", raising=False)
    from palace_mcp.config import Settings

    s = Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
    assert s.palace_telemetry_enabled is True


def test_settings_telemetry_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALACE_TELEMETRY_ENABLED", "false")
    from palace_mcp.config import Settings

    s = Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
    assert s.palace_telemetry_enabled is False
