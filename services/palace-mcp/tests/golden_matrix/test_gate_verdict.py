"""Unit tests for Gate 1 / Gate 2 verdict logic — GIM-1108, GIM-1170.

Tests the build_verdict() function in isolation using mock RowResults.
No MCP server or Neo4j required.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from run_gate_verdict import (  # noqa: E402
    _Q1_THRESHOLD,
    _Q2_GROUND_TRUTH,
    _Q2_THRESHOLD,
    _Q3_ROW_ID,
    _Q3_THRESHOLD,
    _SLO_THRESHOLD_MS,
    build_verdict,
)
from tests.golden_matrix.evaluator import HitEvidence, RowResult  # noqa: E402

_MANIFEST = {"palace_mcp_sha": "abc123"}
_Q2_ID = "gate-q2-balance-data-refs"
_Q1_ID = "gate-q1-evm-chain-adapters"
_Q3_ID = _Q3_ROW_ID


def _make_hit(qualified_name: str) -> HitEvidence:
    return HitEvidence(
        project="uw-ios-app",
        qualified_name=qualified_name,
        file_path=None,
        source_scope="project",
        score=0.9,
        context_status="absent",
        embedding_input_hash=None,
    )


def _make_result(row_id: str, hits: list[HitEvidence], returned: int) -> RowResult:
    return RowResult(
        row_id=row_id,
        split="gate",
        class_="mandatory",
        query="test",
        passed=True,
        failure_reasons=[],
        hits=hits,
        returned_count=returned,
        precision_at_k=0.0,
        recall_at_k=0.0,
        mrr=0.0,
        ndcg=0.0,
        scope_leak_count=0,
        context_present_count=0,
        determinism_hash_count=0,
    )


def _q2_row(balance_hits: int, total_returned: int = 40) -> RowResult:
    hits = [_make_hit(f"Wallet/BalanceData_{i}") for i in range(balance_hits)]
    hits += [
        _make_hit(f"Other/Symbol_{i}") for i in range(total_returned - balance_hits)
    ]
    return _make_result(_Q2_ID, hits, total_returned)


def _q1_row(evm_hits: int, total_returned: int = 20) -> RowResult:
    hits = [_make_hit(f"Chain/EvmAdapter_{i}") for i in range(evm_hits)]
    hits += [_make_hit(f"Other/Symbol_{i}") for i in range(total_returned - evm_hits)]
    return _make_result(_Q1_ID, hits, total_returned)


def _q3_row(caller_count: int) -> RowResult:
    hits = [_make_hit(f"BalanceData_caller_{i}") for i in range(caller_count)]
    return _make_result(_Q3_ID, hits, caller_count)


_DEFAULT_LATENCIES = [3000.0, 3200.0, 2900.0]


# ── Q2 threshold tests ────────────────────────────────────────────────────────


def test_q2_pass_at_30_of_31() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q2"]["status"] == "PASS"
    assert v["overall"] == "PASS"
    assert v["q2"]["detail"] == "30/31 refs found"


def test_q2_pass_at_31_of_31() -> None:
    row_data = {
        _Q2_ID: (_q2_row(31), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q2"]["status"] == "PASS"
    assert v["q2"]["recall"] == round(31 / 31, 4)


def test_q2_fail_at_29_of_31() -> None:
    row_data = {
        _Q2_ID: (_q2_row(29), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q2"]["status"] == "FAIL"
    assert v["overall"] == "FAIL"


def test_q2_recall_computed_against_ground_truth_31() -> None:
    row_data = {
        _Q2_ID: (_q2_row(15), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q2"]["recall"] == round(15 / _Q2_GROUND_TRUTH, 4)


def test_q2_threshold_value() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q2"]["threshold"] == round(_Q2_THRESHOLD, 4)


# ── Q1 informational tests ────────────────────────────────────────────────────


def test_q1_informational_does_not_gate() -> None:
    """Q1 failing must not fail overall — it's informational."""
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q1_ID: (
            _q1_row(5, total_returned=20),
            _DEFAULT_LATENCIES,
        ),  # 5/20 = 0.25 < 0.80
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q1"]["status"] == "FAIL"
    assert v["overall"] == "PASS"


def test_q1_pass_at_threshold() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(16, total_returned=20), _DEFAULT_LATENCIES),  # 16/20 = 0.80
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q1"]["status"] == "PASS"
    assert v["q1"]["recall"] == round(16 / 20, 4)


def test_q1_threshold_value() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q1"]["threshold"] == _Q1_THRESHOLD


# ── Warm SLO tests ────────────────────────────────────────────────────────────


def test_slo_fail_does_not_gate() -> None:
    """SLO failing must not fail overall — only Q2 determines gate outcome."""
    slow = [9000.0, 9500.0, 8500.0]
    row_data = {
        _Q2_ID: (_q2_row(30), slow),
        _Q1_ID: (_q1_row(17), slow),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["warm_slo"]["status"] == "FAIL"
    assert v["overall"] == "PASS"


def test_slo_p50_is_median_of_all_latencies() -> None:
    q2_lat = [1000.0, 3000.0, 5000.0]
    q1_lat = [2000.0, 4000.0, 6000.0]
    row_data = {
        _Q2_ID: (_q2_row(30), q2_lat),
        _Q1_ID: (_q1_row(17), q1_lat),
    }
    v = build_verdict(_MANIFEST, row_data)
    # median of [1000, 3000, 5000, 2000, 4000, 6000] = (3000+4000)/2 = 3500
    assert v["warm_slo"]["p50_ms"] == 3500.0
    assert v["warm_slo"]["status"] == "PASS"


def test_slo_pass_below_threshold() -> None:
    fast = [2000.0, 2500.0, 3000.0]
    row_data = {
        _Q2_ID: (_q2_row(30), fast),
        _Q1_ID: (_q1_row(17), fast),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["warm_slo"]["status"] == "PASS"
    assert v["warm_slo"]["p50_ms"] < _SLO_THRESHOLD_MS


def test_slo_threshold_value() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["warm_slo"]["threshold_ms"] == _SLO_THRESHOLD_MS


# ── Output structure tests ────────────────────────────────────────────────────


def test_verdict_has_required_keys() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q1_ID: (_q1_row(17), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    for key in (
        "gate",
        "timestamp",
        "manifest_sha",
        "q2",
        "q1",
        "warm_slo",
        "overall",
        "gate_adjustment_applied",
    ):
        assert key in v, f"Missing key: {key}"


def test_manifest_sha_in_verdict() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
    }
    v = build_verdict({"palace_mcp_sha": "deadbeef"}, row_data)
    assert v["manifest_sha"] == "deadbeef"


def test_gate_adjustment_applied_is_false() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["gate_adjustment_applied"] is False


def test_gate_label() -> None:
    row_data = {_Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES)}
    v = build_verdict(_MANIFEST, row_data)
    assert v["gate"] == "gate-1"


# ── Pattern matching tests ────────────────────────────────────────────────────


def test_balance_data_snake_case_matches() -> None:
    """balanceData (camelCase) should also be counted for Q2."""
    hits = [_make_hit("Wallet/balanceData")]
    result = _make_result(_Q2_ID, hits, 1)
    row_data = {_Q2_ID: (result, _DEFAULT_LATENCIES)}
    v = build_verdict(_MANIFEST, row_data)
    assert v["q2"]["detail"] == "1/31 refs found"


def test_file_path_pattern_matching() -> None:
    """BalanceData in file_path should count for Q2."""
    hit = HitEvidence(
        project="uw-ios-app",
        qualified_name="SomeClass/method",
        file_path="Sources/Models/BalanceData.swift",
        source_scope="project",
        score=0.9,
        context_status="absent",
        embedding_input_hash=None,
    )
    result = _make_result(_Q2_ID, [hit], 1)
    row_data = {_Q2_ID: (result, _DEFAULT_LATENCIES)}
    v = build_verdict(_MANIFEST, row_data)
    assert v["q2"]["detail"] == "1/31 refs found"


# ── Q3 (Gate 2) tests ─────────────────────────────────────────────────────────


def test_q3_present_in_verdict() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q3_ID: (_q3_row(35), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert "q3" in v


def test_q3_pass_at_threshold() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q3_ID: (_q3_row(30), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q3"]["status"] == "PASS"
    assert v["q3"]["caller_count"] == 30


def test_q3_fail_below_threshold() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q3_ID: (_q3_row(29), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q3"]["status"] == "FAIL"


def test_q3_informational_does_not_gate() -> None:
    """Q3 failing must not fail overall — it's informational."""
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q3_ID: (_q3_row(0), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q3"]["status"] == "FAIL"
    assert v["overall"] == "PASS"


def test_q3_absent_verdict_has_zero_callers() -> None:
    """When Q3 row is not in row_data, caller_count should be 0."""
    row_data = {_Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES)}
    v = build_verdict(_MANIFEST, row_data)
    assert v["q3"]["caller_count"] == 0
    assert v["q3"]["status"] == "FAIL"


def test_q3_threshold_value_in_verdict() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q3_ID: (_q3_row(35), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert v["q3"]["threshold"] == _Q3_THRESHOLD


def test_q3_detail_message_includes_symbol() -> None:
    row_data = {
        _Q2_ID: (_q2_row(30), _DEFAULT_LATENCIES),
        _Q3_ID: (_q3_row(42), _DEFAULT_LATENCIES),
    }
    v = build_verdict(_MANIFEST, row_data)
    assert "42" in v["q3"]["detail"]
    assert "BalanceData" in v["q3"]["detail"]
