"""Pydantic models for arch_layer extractor (GIM-243)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class Module(BaseModel):
    """A build-system module (SwiftPM target or Gradle subproject)."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    slug: str  # unique within project: e.g. "Core" or ":core"
    name: str
    kind: str  # "swift_target" | "gradle_module"
    manifest_path: str  # repo-relative path to the manifest that declares this
    source_root: str  # repo-relative source root, or "" when not declared
    run_id: str


class Layer(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    name: str
    rule_source: str  # path to rule file that declared this layer
    run_id: str


class ArchRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    rule_id: str
    kind: str
    severity: str
    rule_source: str
    run_id: str

    @field_validator("severity")
    @classmethod
    def _valid_severity(cls, v: str) -> str:
        valid = {"critical", "high", "medium", "low", "informational"}
        return v if v in valid else "informational"


class ArchViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    kind: str
    severity: str
    src_module: str
    dst_module: str
    rule_id: str
    message: str
    evidence: str  # short description of the evidence (import text, cycle path…)
    file: str  # source file path, or "" if not applicable
    start_line: int  # 0 when not applicable
    run_id: str
    source_context: str = "other"

    @field_validator("severity")
    @classmethod
    def _valid_severity(cls, v: str) -> str:
        valid = {"critical", "high", "medium", "low", "informational"}
        return v if v in valid else "informational"


class ModuleEdge(BaseModel):
    """A directed dependency edge between two modules."""

    model_config = ConfigDict(frozen=True)

    src_slug: str
    dst_slug: str
    scope: str  # "implementation" | "api" | "compileOnly" | "testImplementation" | "target_dep"
    declared_in: str  # manifest path where the edge was declared
    evidence_kind: str  # "manifest" | "import"
    run_id: str


class ParserWarning(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str


class ParseResult(BaseModel):
    """Output of a single manifest parser."""

    model_config = ConfigDict(frozen=True)

    modules: tuple[Module, ...]
    edges: tuple[ModuleEdge, ...]
    warnings: tuple[ParserWarning, ...]
