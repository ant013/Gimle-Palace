"""Foundation substrate for all palace-mcp extractors (GIM-101a).

Import the public surface from submodules as needed.
"""

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.models import (
    Ecosystem,
    EvictionRecord,
    ExternalDependency,
    IngestCheckpoint,
    Language,
    SourceType,
    SymbolKind,
    SymbolOccurrence,
    SymbolOccurrenceShadow,
)

__all__ = [
    "Ecosystem",
    "EvictionRecord",
    "ExtractorError",
    "ExtractorErrorCode",
    "ExternalDependency",
    "IngestCheckpoint",
    "Language",
    "SourceType",
    "SymbolKind",
    "SymbolOccurrence",
    "SymbolOccurrenceShadow",
]
