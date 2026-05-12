"""Parser entrypoints for hot_path_profiler."""

from palace_mcp.extractors.hot_path_profiler.parsers.instruments import (
    parse_instruments_trace,
)
from palace_mcp.extractors.hot_path_profiler.parsers.perfetto import (
    parse_perfetto_trace,
)

__all__ = ["parse_instruments_trace", "parse_perfetto_trace"]
