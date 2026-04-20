"""Extractor protocol — BaseExtractor ABC + ExtractionContext + errors.

Contract for all palace-mcp extractors (spec §3.2). Extractors implement
extract() and declare their Cypher constraints + indexes as class attributes.
Framework (runner.py) handles :IngestRun lifecycle; extractor only writes
its domain nodes/edges via ctx.driver.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from neo4j import AsyncDriver


class BaseExtractor(ABC):
    """Contract for an extractor. Subclass + implement extract()."""

    # Required class attributes
    name: ClassVar[str]
    description: ClassVar[str]

    # Schema declaration — aggregated by ensure_extractors_schema
    constraints: ClassVar[list[str]] = []
    indexes: ClassVar[list[str]] = []

    @abstractmethod
    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        """Run the extractor. Write nodes/edges via ctx.driver.

        Returns ExtractorStats with counts (for :IngestRun finalize).
        Raise ExtractorError subclass or any Exception on failure —
        runner catches + finalizes :IngestRun as errored.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class ExtractionContext:
    """Per-run context passed by runner into extractor.extract()."""

    driver: AsyncDriver
    project_slug: str
    group_id: str
    repo_path: Path
    run_id: str
    logger: logging.Logger


@dataclass(frozen=True)
class ExtractorStats:
    """What extract() returns. Merged into :IngestRun for observability."""

    nodes_written: int = 0
    edges_written: int = 0


class ExtractorError(Exception):
    """Base class for extractor-originating errors the runner should surface."""

    error_code: ClassVar[str] = "extractor_error"


class ExtractorConfigError(ExtractorError):
    """Extractor misconfigured (missing tool, bad params). Non-retryable."""

    error_code: ClassVar[str] = "extractor_config_error"


class ExtractorRuntimeError(ExtractorError):
    """Extractor ran but data was invalid / partial. Retryable."""

    error_code: ClassVar[str] = "extractor_runtime_error"
