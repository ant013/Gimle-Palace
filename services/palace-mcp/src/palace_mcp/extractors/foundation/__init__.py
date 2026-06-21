"""Foundation substrate for all palace-mcp extractors (GIM-101a).

Import the public surface from submodules as needed.
"""

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode
from palace_mcp.extractors.foundation.delta_resolution import (
    DeltaResolutionBaseline,
    EdgeDelta,
    EdgeSnapshot,
    PublicApiDelta,
    PublicApiSnapshot,
    ResolvedDelta,
    SeedDelta,
    SymbolDelta,
    SymbolSnapshot,
    capture_delta_resolution_baseline,
    diff_delta_snapshots,
    resolve_delta_resolution,
)
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
from palace_mcp.extractors.foundation.semgrep_runner import (
    SemgrepConfigInvalidError,
    SemgrepInternalError,
    SemgrepTargetError,
    run_semgrep,
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
    "DeltaResolutionBaseline",
    "Ecosystem",
    "EdgeDelta",
    "EdgeSnapshot",
    "EvictionRecord",
    "ExtractorError",
    "ExtractorErrorCode",
    "ExternalDependency",
    "IngestCheckpoint",
    "Language",
    "PublicApiDelta",
    "PublicApiArtifactKind",
    "PublicApiSnapshot",
    "PublicApiSurface",
    "PublicApiSymbol",
    "PublicApiSymbolKind",
    "PublicApiVisibility",
    "ResolvedDelta",
    "run_semgrep",
    "SemgrepConfigInvalidError",
    "SemgrepInternalError",
    "SemgrepTargetError",
    "SeedDelta",
    "should_skip_path",
    "SourceType",
    "SymbolDelta",
    "SymbolKind",
    "SymbolOccurrence",
    "SymbolOccurrenceShadow",
    "SymbolSnapshot",
    "capture_delta_resolution_baseline",
    "diff_delta_snapshots",
    "resolve_delta_resolution",
    "walk_repo",
]
