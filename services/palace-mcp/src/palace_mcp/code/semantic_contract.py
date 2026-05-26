"""Semantic search API contract types.

GIM-839 D0 contract: defines the request/response shapes and scope-resolution
logic for ``palace.code.semantic_search``.

Migration note (GIM-837 → GIM-839):
  The function signature is compatible. Existing callers that pass ``project``
  and ``query`` will continue to work. However, the default behavior changes:
  GIM-837 returned all embedded symbols in scope. GIM-839 defaults to
  first-party symbols only (``project`` + ``workspace_package``). Callers that
  need dependency or SDK symbols must now pass ``include_dependencies=True``,
  ``include_sdk=True``, or explicit ``source_scopes``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from palace_mcp.code.source_scope import SourceScope


_DEFAULT_SCOPES = frozenset({SourceScope.PROJECT, SourceScope.WORKSPACE_PACKAGE})

_MAX_SCOPE_PROJECTS = 10


class SemanticSearchRequest(BaseModel, frozen=True):
    """Validated request for palace.code.semantic_search."""

    query: str = Field(min_length=1)

    project: str | None = None
    projects: list[str] | None = None

    source_scopes: list[SourceScope] | None = None
    include_dependencies: bool = False
    include_generated: bool = False
    include_sdk: bool = False

    limit: int = Field(default=10, ge=1, le=50)
    include_context: bool = True
    context_limit: int = Field(default=3, ge=0, le=10)
    backend: str | None = None

    @model_validator(mode="after")
    def _validate_scope(self) -> SemanticSearchRequest:
        if (self.project is None) == (self.projects is None):
            raise ValueError("specify exactly one of 'project' or 'projects'")

        if self.projects is not None:
            if len(self.projects) == 0:
                raise ValueError("'projects' must not be empty")
            if len(self.projects) > _MAX_SCOPE_PROJECTS:
                raise ValueError(
                    f"'projects' must contain at most {_MAX_SCOPE_PROJECTS} entries"
                )

        if self.source_scopes is not None and len(self.source_scopes) == 0:
            raise ValueError("'source_scopes' must not be empty when provided")

        return self

    def resolved_projects(self) -> list[str]:
        """Return the canonical project list (order preserved for tie-break)."""
        if self.project is not None:
            return [self.project]
        assert self.projects is not None
        return list(self.projects)

    def effective_scopes(self) -> frozenset[SourceScope]:
        """Resolve the effective source scope filter.

        Precedence (spec §7.5):
        - ``source_scopes`` when provided is authoritative (overrides flags).
        - Otherwise: start with [project, workspace_package], add per flags.
        """
        if self.source_scopes is not None:
            return frozenset(self.source_scopes)

        scopes = set(_DEFAULT_SCOPES)

        if self.include_dependencies:
            scopes.add(SourceScope.DEPENDENCY)

        if self.include_generated:
            scopes.add(SourceScope.GENERATED)
            scopes.add(SourceScope.DERIVED)

        if self.include_sdk:
            scopes.add(SourceScope.SDK)

        return frozenset(scopes)


class ScoreComponents(BaseModel, frozen=True):
    """Breakdown of the hybrid ranking score."""

    vector_score_normalized: float = 0.0
    lexical_match: float = 0.0
    source_scope_score: float = 0.0
    symbol_kind_boost: float = 0.0
    module_path_boost: float = 0.0
    penalty: float = 0.0


class SemanticSearchHit(BaseModel, frozen=True):
    """A single semantic search result — always includes source_scope."""

    project: str
    group_id: str
    qualified_name: str
    file_path: str | None = None
    source_scope: SourceScope
    score: float
    score_components: ScoreComponents = Field(default_factory=ScoreComponents)


class EmbeddingCoverage(BaseModel, frozen=True):
    """Embedding index coverage metadata (spec §7.6)."""

    bounded: bool
    max_symbols: int | None = None
    embedded_symbols: int
    eligible_symbols: int
    source_scope_counts: dict[str, int] = Field(default_factory=dict)


class SymbolSourceMetadata(BaseModel, frozen=True):
    """Contract for source metadata persisted on :Symbol nodes.

    This defines the fields that must be present on newly extracted symbols
    so that search, snippet hydration, and scope classification work correctly.
    """

    source_scope: SourceScope
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    commit_sha: str | None = None
    project_root: str
