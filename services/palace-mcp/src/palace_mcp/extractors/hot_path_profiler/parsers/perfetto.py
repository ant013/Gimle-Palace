"""Perfetto trace parser for hot_path_profiler."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Protocol

from palace_mcp.extractors.base import ExtractorConfigError, ExtractorRuntimeError
from palace_mcp.extractors.hot_path_profiler.models import HotPathSample, HotPathSummary

DEFAULT_THRESHOLD = 0.05
PERFETTO_HOT_PATH_SQL = """
SELECT
  COALESCE(slice.name, thread.name, 'unknown') AS symbol_name,
  COUNT(*) AS cpu_samples,
  CAST(COALESCE(SUM(slice.dur) / 1000000, 0) AS INT) AS wall_ms,
  thread.name AS thread_name
FROM slice
LEFT JOIN thread_track ON slice.track_id = thread_track.id
LEFT JOIN thread USING (utid)
WHERE slice.name IS NOT NULL
GROUP BY symbol_name, thread_name
ORDER BY cpu_samples DESC, wall_ms DESC, symbol_name ASC
""".strip()


class TraceProcessorFactory(Protocol):
    """Structural protocol for the Perfetto TraceProcessor constructor."""

    def __call__(self, *, trace: str) -> Any: ...


def parse_perfetto_trace(
    trace_path: Path,
    *,
    trace_processor_factory: TraceProcessorFactory | None = None,
) -> tuple[HotPathSummary, list[HotPathSample]]:
    """Parse one `.pftrace` file into aggregated hot-path samples."""

    factory = trace_processor_factory or _load_trace_processor
    processor = factory(trace=str(trace_path))
    context = processor if hasattr(processor, "__enter__") else nullcontext(processor)

    with context as trace_processor:
        rows = list(trace_processor.query(PERFETTO_HOT_PATH_SQL))

    if not rows:
        raise ExtractorRuntimeError(f"no hot-path rows returned for {trace_path}")

    total_cpu_samples = 0
    total_wall_ms = 0
    samples: list[HotPathSample] = []
    trace_id = trace_path.stem

    for row in rows:
        symbol_name = _row_value(row, "symbol_name", default="unknown")
        cpu_samples = max(int(_row_value(row, "cpu_samples", default=0)), 0)
        wall_ms = max(int(_row_value(row, "wall_ms", default=0)), 0)
        total_cpu_samples += cpu_samples
        total_wall_ms += wall_ms
        samples.append(
            HotPathSample(
                trace_id=trace_id,
                source_format="perfetto",
                symbol_name=str(symbol_name),
                cpu_samples=cpu_samples,
                wall_ms=wall_ms,
                total_samples_in_trace=1,
                total_wall_ms_in_trace=0,
                thread_name=_coerce_optional_str(_row_value(row, "thread_name")),
            )
        )

    if total_cpu_samples <= 0:
        raise ExtractorRuntimeError(f"Perfetto trace {trace_path} produced zero samples")

    normalised = [
        sample.model_copy(
            update={
                "total_samples_in_trace": total_cpu_samples,
                "total_wall_ms_in_trace": total_wall_ms,
            }
        )
        for sample in samples
    ]

    summary = HotPathSummary(
        trace_id=trace_id,
        source_format="perfetto",
        total_cpu_samples=total_cpu_samples,
        total_wall_ms=total_wall_ms,
        hot_function_count=sum(
            1 for sample in normalised if sample.cpu_share >= DEFAULT_THRESHOLD
        ),
        threshold_cpu_share=DEFAULT_THRESHOLD,
    )
    return summary, normalised


def _load_trace_processor(*, trace: str) -> Any:
    try:
        from perfetto.trace_processor import TraceProcessor
    except ImportError as exc:
        raise ExtractorConfigError(
            "perfetto dependency is not installed; add it to palace-mcp before running hot_path_profiler"
        ) from exc
    return TraceProcessor(trace=trace)


def _row_value(row: Any, key: str, *, default: Any = None) -> Any:
    if hasattr(row, key):
        return getattr(row, key)
    if hasattr(row, "__getitem__"):
        try:
            return row[key]
        except Exception:  # noqa: BLE001 - foreign row object
            return default
    if hasattr(row, "get"):
        return row.get(key, default)
    return default


def _coerce_optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
