"""Pydantic v2 models for the dependency_surface extractor (spec §3.3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParsedDep(BaseModel):
    """A single declared dependency parsed from a manifest file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    purl: str = Field(..., description="Package URL per purl-spec")
    ecosystem: str
    declared_version_constraint: str
    resolved_version: str = Field(
        ...,
        description="Pinned version or 'unresolved' sentinel (never empty).",
    )
    scope: str = Field(
        ...,
        description="compile | test | build | runtime",
    )
    declared_in: str = Field(..., description="Relative path of the declaring manifest file")

    @model_validator(mode="after")
    def _validate_purl_prefix(self) -> "ParsedDep":
        if not self.purl.startswith("pkg:"):
            raise ValueError(f"purl must start with 'pkg:' — got {self.purl!r}")
        return self

    @model_validator(mode="after")
    def _validate_resolved_version_nonempty(self) -> "ParsedDep":
        if not self.resolved_version:
            raise ValueError(
                "resolved_version must be non-empty (use 'unresolved' sentinel if resolution failed)"
            )
        return self


class ManifestParseResult(BaseModel):
    """Result of parsing one ecosystem's manifest files."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ecosystem: str
    deps: tuple[ParsedDep, ...] = ()
    parser_warnings: tuple[str, ...] = ()
