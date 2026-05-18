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
    PublicApiArtifactKind,
    PublicApiSurface,
    PublicApiSymbol,
    PublicApiSymbolKind,
    PublicApiVisibility,
    SourceType,
    SymbolKind,
    SymbolOccurrence,
    SymbolOccurrenceShadow,
)
from palace_mcp.extractors.foundation.walk import (
    DEFAULT_STOP_DIRS,
    DEFAULT_STOP_PREFIXES,
    should_skip_path,
    walk_repo,
)

__all__ = [
    "DEFAULT_STOP_DIRS",
    "DEFAULT_STOP_PREFIXES",
    "Ecosystem",
    "EvictionRecord",
    "ExtractorError",
    "ExtractorErrorCode",
    "ExternalDependency",
    "IngestCheckpoint",
    "Language",
    "PublicApiArtifactKind",
    "PublicApiSurface",
    "PublicApiSymbol",
    "PublicApiSymbolKind",
    "PublicApiVisibility",
    "should_skip_path",
    "SourceType",
    "SymbolKind",
    "SymbolOccurrence",
    "SymbolOccurrenceShadow",
    "walk_repo",
]
