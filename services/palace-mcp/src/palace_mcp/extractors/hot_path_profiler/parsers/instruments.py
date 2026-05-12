"""Parser for normalized Instruments/xctrace JSON fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from palace_mcp.extractors.base import ExtractorRuntimeError
from palace_mcp.extractors.hot_path_profiler.models import HotPathSample, HotPathSummary

DEFAULT_THRESHOLD = 0.05


def parse_instruments_trace(trace_path: Path) -> tuple[HotPathSummary, list[HotPathSample]]:
    """Parse one normalized Instruments JSON trace fixture."""

    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExtractorRuntimeError(f"trace file not found: {trace_path}") from exc
    except json.JSONDecodeError as exc:
        raise ExtractorRuntimeError(
            f"invalid Instruments JSON fixture at {trace_path}: {exc.msg}"
        ) from exc

    summary_block = _as_dict(payload.get("summary"))
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list):
        raise ExtractorRuntimeError(
            f"trace fixture at {trace_path} must contain a list under 'samples'"
        )

    trace_id = str(payload.get("trace_id") or trace_path.stem)
    total_cpu_samples = _as_int(
        payload.get("total_cpu_samples") or summary_block.get("total_cpu_samples")
    )
    if total_cpu_samples <= 0:
        total_cpu_samples = sum(max(_as_int(sample.get("cpu_samples")), 0) for sample in raw_samples)
    if total_cpu_samples <= 0:
        raise ExtractorRuntimeError(
            f"trace fixture at {trace_path} must contain positive cpu_samples totals"
        )

    total_wall_ms = _as_int(
        payload.get("total_wall_ms") or summary_block.get("total_wall_ms")
    )
    if total_wall_ms <= 0:
        total_wall_ms = sum(max(_as_int(sample.get("wall_ms")), 0) for sample in raw_samples)

    threshold = _as_float(
        payload.get("threshold_cpu_share")
        or summary_block.get("threshold_cpu_share")
        or DEFAULT_THRESHOLD
    )

    samples = [
        HotPathSample(
            trace_id=trace_id,
            source_format="instruments",
            symbol_name=_sample_symbol_name(sample),
            cpu_samples=max(_as_int(sample.get("cpu_samples")), 0),
            wall_ms=max(_as_int(sample.get("wall_ms")), 0),
            total_samples_in_trace=total_cpu_samples,
            total_wall_ms_in_trace=max(total_wall_ms, 0),
            qualified_name=_optional_str(sample.get("qualified_name")),
            thread_name=_optional_str(sample.get("thread_name")),
        )
        for sample in raw_samples
    ]
    samples.sort(
        key=lambda sample: (
            -sample.cpu_samples,
            -sample.wall_ms,
            sample.symbol_name,
        )
    )

    summary = HotPathSummary(
        trace_id=trace_id,
        source_format="instruments",
        total_cpu_samples=total_cpu_samples,
        total_wall_ms=max(total_wall_ms, 0),
        hot_function_count=sum(
            1 for sample in samples if sample.cpu_share >= threshold
        ),
        threshold_cpu_share=threshold,
    )
    return summary, samples


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(float(value))
    return 0


def _as_float(value: Any) -> float:
    if value is None:
        return DEFAULT_THRESHOLD
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return DEFAULT_THRESHOLD


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _sample_symbol_name(sample: Any) -> str:
    if not isinstance(sample, dict):
        raise ExtractorRuntimeError("trace sample must be a JSON object")
    value = (
        sample.get("symbol_name")
        or sample.get("symbol")
        or sample.get("name")
        or sample.get("qualified_name")
    )
    if not isinstance(value, str) or not value.strip():
        raise ExtractorRuntimeError("trace sample is missing symbol_name")
    return value.strip()
