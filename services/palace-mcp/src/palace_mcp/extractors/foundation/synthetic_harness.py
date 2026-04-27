"""Synthetic 70M-occurrence stress harness (GIM-101a, T12).

Generates a deterministic stream of SymbolOccurrence records without touching
the filesystem or Neo4j. Used to:
  - Stress-test BoundedInDegreeCounter eviction paths
  - Verify signed-i64 hash distribution (no overflow)
  - Benchmark TantivyBridge throughput under sustained load
  - Validate circuit breaker trips at configured caps

No I/O. All generation is in-process. The harness is a pure iterator;
callers decide how many records to consume and what to do with them.

Usage:
    from palace_mcp.extractors.foundation.synthetic_harness import SyntheticHarness

    harness = SyntheticHarness(total=70_000_000, symbols=100_000)
    for occ in harness.occurrences():
        ...  # process occurrence
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from dataclasses import dataclass, field

from palace_mcp.extractors.foundation.identifiers import symbol_id_for
from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
)

_LANGUAGES = [
    Language.PYTHON,
    Language.TYPESCRIPT,
    Language.RUST,
    Language.KOTLIN,
    Language.SWIFT,
]

_KINDS = [
    SymbolKind.USE,
    SymbolKind.DEF,
    SymbolKind.DECL,
    SymbolKind.IMPL,
    SymbolKind.ASSIGN,
]


@dataclass
class HarnessStats:
    total_generated: int = 0
    unique_symbols: int = 0
    negative_ids: int = 0
    positive_ids: int = 0
    hash_collisions: int = 0
    _seen_ids: set[int] = field(default_factory=set, repr=False)

    def record(self, symbol_id: int) -> None:
        self.total_generated += 1
        if symbol_id < 0:
            self.negative_ids += 1
        else:
            self.positive_ids += 1
        if symbol_id in self._seen_ids:
            self.hash_collisions += 1
        else:
            self._seen_ids.add(symbol_id)
            self.unique_symbols += 1


class SyntheticHarness:
    """Generate a deterministic stream of SymbolOccurrence records.

    Args:
        total: Total number of occurrences to generate.
        symbols: Number of distinct symbol qualified names in the pool.
        project: Project slug used in doc_key generation.
        file_count: Number of distinct file paths to cycle through.
    """

    def __init__(
        self,
        *,
        total: int = 70_000_000,
        symbols: int = 100_000,
        project: str = "stress_test",
        file_count: int = 10_000,
    ) -> None:
        self.total = total
        self.symbols = symbols
        self.project = project
        self.file_count = file_count

        self._symbol_names = [
            f"pkg.module_{i}.Class_{i}.method_{i % 100}" for i in range(symbols)
        ]
        self._symbol_ids = [symbol_id_for(name) for name in self._symbol_names]
        self._file_paths = [
            f"/repo/src/module_{i % file_count}/file.py" for i in range(file_count)
        ]

    def occurrences(self) -> Iterator[SymbolOccurrence]:
        """Yield SymbolOccurrence records up to self.total."""
        lang_cycle = itertools.cycle(_LANGUAGES)
        kind_cycle = itertools.cycle(_KINDS)
        importance_cycle = itertools.cycle([0.1, 0.3, 0.5, 0.7, 0.9])

        for i in range(self.total):
            sym_idx = i % self.symbols
            file_idx = i % self.file_count
            line = (i % 10_000) + 1
            lang = next(lang_cycle)
            kind = next(kind_cycle)
            importance = next(importance_cycle)
            sym_name = self._symbol_names[sym_idx]

            yield SymbolOccurrence(
                symbol_id=self._symbol_ids[sym_idx],
                symbol_qualified_name=sym_name,
                kind=kind,
                file_path=self._file_paths[file_idx],
                line=line,
                col_start=0,
                col_end=10,
                language=lang,
                importance=importance,
                commit_sha="synthetic_0000000",
                ingest_run_id=f"stress-{self.project}",
                doc_key=f"{self._symbol_ids[sym_idx]}:{self._file_paths[file_idx]}:{line}:0",
            )

    def sample(self, n: int = 1000) -> list[SymbolOccurrence]:
        """Return first n occurrences without consuming the full stream."""
        return list(itertools.islice(self.occurrences(), n))

    def stats(self, sample_size: int = 1_000_000) -> HarnessStats:
        """Compute statistics over a sample (not the full 70M, for CI speed)."""
        result = HarnessStats()
        for occ in itertools.islice(self.occurrences(), sample_size):
            result.record(occ.symbol_id)
        return result
