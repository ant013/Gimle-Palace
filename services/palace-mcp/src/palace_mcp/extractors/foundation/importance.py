"""BoundedInDegreeCounter and importance_score formula (GIM-101a, T2 + T4).

Fixes applied in rev3a:
- F-C: eviction removes EXACTLY evict_n entries via most_common[-N:] slice.
- F-D: JSON persistence (not pickle); RCE-safe.
- F-E: run_id validation on load; mismatch → discard, not silent stale load.
- GIM-349: stale/corrupt persisted counter state self-heals on load.
"""

from __future__ import annotations

import errno
import fcntl
import json
import logging
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import Language, SymbolKind

# ---------------------------------------------------------------------------
# Kind weights — keep in sync with SymbolKind enum
# ---------------------------------------------------------------------------

KIND_WEIGHT: dict[SymbolKind, float] = {
    SymbolKind.DEF: 1.0,
    SymbolKind.DECL: 0.8,
    SymbolKind.IMPL: 0.7,
    SymbolKind.MODIFIER: 0.6,  # Solidity modifier (Architect F23)
    SymbolKind.EVENT: 0.55,  # Solidity event (Architect F23)
    SymbolKind.ASSIGN: 0.5,
    SymbolKind.USE: 0.3,
}

# Vendor/third-party tier patterns — lower tier_weight = more eviction-eligible.
# Order matters: first match wins.
_VENDOR_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"node_modules/"), 0.1),
    (re.compile(r"vendor/"), 0.1),
    (re.compile(r"\.venv/"), 0.1),
    (re.compile(r"site-packages/"), 0.1),
    (re.compile(r"__pycache__/"), 0.05),
    (re.compile(r"dist/"), 0.15),
    (re.compile(r"build/"), 0.15),
    (re.compile(r"target/"), 0.15),
    (re.compile(r"\.gradle/"), 0.1),
]

_FIRST_PARTY_WEIGHT: float = 1.0
_THIRD_PARTY_DEFAULT_WEIGHT: float = 0.2
_TANTIVY_WRITER_LOCK_NAME = ".tantivy-writer.lock"


def tier_weight(file_path: str) -> float:
    """Classify a file path into a tier weight ∈ (0, 1].

    Vendor/generated paths → low weight (eviction-eligible).
    First-party paths → 1.0.
    """
    for pattern, weight in _VENDOR_PATTERNS:
        if pattern.search(file_path):
            return weight
    return _FIRST_PARTY_WEIGHT


def language_weight(language: Language, primary_lang: Language | None) -> float:
    """Language relevance ∈ [0, 1].

    Primary project language → 1.0, others → 0.5, UNKNOWN → 0.1.
    """
    if language == Language.UNKNOWN:
        return 0.1
    if primary_lang is not None and language == primary_lang:
        return 1.0
    return 0.5


def recency_decay(days_since_seen: float, half_life_days: float = 30.0) -> float:
    """Exponential recency decay ∈ (0, 1].

    decay(0) = 1.0, decay(half_life) ≈ 0.5.
    """
    return math.exp(-math.log(2) * days_since_seen / half_life_days)


def importance_score(
    *,
    cms_in_degree: int,
    file_path: str,
    kind: SymbolKind,
    last_seen_at: datetime,
    language: Language,
    primary_lang: Language | None,
    half_life_days: float = 30.0,
) -> float:
    """Compute importance ∈ [0, 1].

    5-component formula with documented weights:
      centrality:  0.35 × log1p(in_degree) / log1p(100)  [unbounded above 100; clamped]
      tier:        0.30 × tier_weight(file_path)
      kind:        0.20 × KIND_WEIGHT[kind]
      recency:     0.10 × recency_decay(days_since_seen)
      language:    0.05 × language_weight(language, primary_lang)
    """
    centrality = math.log1p(cms_in_degree) / math.log1p(100)
    tier = tier_weight(file_path)
    kind_w = KIND_WEIGHT[kind]

    now = datetime.now(tz=timezone.utc)
    if last_seen_at.tzinfo is None:
        # Treat naive datetimes as UTC
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - last_seen_at).total_seconds() / 86400)
    recency = recency_decay(days, half_life_days)

    lang_w = language_weight(language, primary_lang)

    raw = (
        0.35 * centrality + 0.30 * tier + 0.20 * kind_w + 0.10 * recency + 0.05 * lang_w
    )
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# BoundedInDegreeCounter
# ---------------------------------------------------------------------------


class BoundedInDegreeCounter:
    """Exact in-degree counter with bounded memory and JSON persistence.

    Fixes applied:
    - F-C: _evict_lowest_n removes EXACTLY n entries via most_common[-N:] slice,
      regardless of ties. Under uniform load the old threshold-share approach
      wiped the entire counter.
    - F-D: JSON persistence (not pickle).
    - F-E: run_id validation; stale or corrupt state → return False.
    """

    def __init__(self, max_entries: int = 1_000_000) -> None:
        self._counter: Counter[str] = Counter()
        self._max = max_entries
        # Batched eviction trigger: fire after max + 10% overflow
        self._next_evict_at = max_entries + max_entries // 10

    def increment(self, qualified_name: str) -> None:
        self._counter[qualified_name] += 1
        if len(self._counter) > self._next_evict_at:
            self._evict_lowest_n(self._max // 10)
            self._next_evict_at = len(self._counter) + self._max // 10

    def estimate(self, qualified_name: str) -> int:
        return self._counter.get(qualified_name, 0)

    def __len__(self) -> int:
        return len(self._counter)

    def _evict_lowest_n(self, n: int) -> None:
        """Remove EXACTLY n lowest-count entries, regardless of ties (F-C fix)."""
        if n <= 0 or n >= len(self._counter):
            return
        # most_common() returns sorted desc; reverse-slice gives lowest-count keys.
        # Ties broken by insertion order (Counter inherits dict ordering).
        lowest_keys = [k for k, _ in self._counter.most_common()[-(n):]]
        for k in lowest_keys:
            del self._counter[k]

    def to_disk(self, path: Path, run_id: str) -> None:
        """Write counter to JSON with run_id for validation on load (F-D + F-E fix)."""
        payload = {
            "version": 1,
            "run_id": run_id,
            "counts": dict(self._counter),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def from_disk(self, path: Path, expected_run_id: str) -> bool:
        """Load counter from JSON if run_id matches.

        Returns False if:
        - file does not exist
        - JSON is corrupt or unexpected shape
        - run_id does not match expected_run_id

        Callers decide whether False should hard-fail or trigger a reset.
        """
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False

        if not isinstance(payload, dict):
            return False
        if payload.get("version") != 1:
            return False
        if payload.get("run_id") != expected_run_id:
            return False
        counts = payload.get("counts")
        if not isinstance(counts, dict):
            return False

        try:
            self._counter = Counter({k: int(v) for k, v in counts.items()})
        except (ValueError, TypeError):
            return False

        return True


def load_or_reset_in_degree_counter(
    tantivy_path: Path,
    run_id: str,
    *,
    logger: logging.Logger,
) -> BoundedInDegreeCounter:
    """Load the persisted counter, recovering stale/corrupt state when needed."""
    counter = BoundedInDegreeCounter()
    counter_path = tantivy_path / "in_degree_counter.json"
    reset_requested = os.environ.get("PALACE_COUNTER_RESET") == "1"

    if reset_requested:
        if counter_path.exists():
            _delete_counter_file(
                counter_path,
                reason="PALACE_COUNTER_RESET=1 requested a fresh counter",
            )
            logger.warning(
                "Reset persisted in-degree counter at %s because PALACE_COUNTER_RESET=1",
                counter_path,
            )
        stale_lock = _delete_stale_tantivy_writer_lock(
            tantivy_path,
            reason="PALACE_COUNTER_RESET=1 requested a fresh counter",
        )
        if stale_lock is not None:
            logger.warning(
                "Removed stale Tantivy writer lock at %s during PALACE_COUNTER_RESET=1 recovery",
                stale_lock,
            )
        return counter

    if not counter_path.exists():
        return counter

    if counter.from_disk(counter_path, expected_run_id=run_id):
        return counter

    _delete_counter_file(
        counter_path,
        reason="stale or corrupt counter state was detected",
    )
    stale_lock = _delete_stale_tantivy_writer_lock(
        tantivy_path,
        reason="stale or corrupt counter state was detected",
    )
    logger.warning(
        "Recovered stale or corrupt in-degree counter at %s; starting fresh",
        counter_path,
    )
    if stale_lock is not None:
        logger.warning(
            "Removed stale Tantivy writer lock at %s during counter recovery",
            stale_lock,
        )
    return BoundedInDegreeCounter()


def _delete_counter_file(counter_path: Path, *, reason: str) -> None:
    try:
        counter_path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ExtractorError(
            error_code=ExtractorErrorCode.COUNTER_STATE_CORRUPT,
            message=f"Failed to remove counter state at {counter_path}: {reason}.",
            recoverable=False,
            action="manual_cleanup",
            context={"path": str(counter_path), "reason": reason, "error": str(exc)},
        ) from exc


def _delete_stale_tantivy_writer_lock(tantivy_path: Path, *, reason: str) -> Path | None:
    lock_path = tantivy_path / _TANTIVY_WRITER_LOCK_NAME
    if not lock_path.exists():
        return None

    try:
        with lock_path.open("a+b") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EAGAIN):
                    raise ExtractorError(
                        error_code=ExtractorErrorCode.TANTIVY_LOCK_HELD,
                        message=(
                            f"Tantivy writer lock is still held at {lock_path}; "
                            f"refusing to delete a live lock during {reason}."
                        ),
                        recoverable=True,
                        action="retry",
                        context={"path": str(lock_path), "reason": reason},
                    ) from exc
                raise
            try:
                lock_path.unlink()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except FileNotFoundError:
        return None
    except ExtractorError:
        raise
    except OSError as exc:
        raise ExtractorError(
            error_code=ExtractorErrorCode.TANTIVY_DELETE_FAILED,
            message=f"Failed to remove Tantivy writer lock at {lock_path}: {reason}.",
            recoverable=False,
            action="manual_cleanup",
            context={"path": str(lock_path), "reason": reason, "error": str(exc)},
        ) from exc

    return lock_path
