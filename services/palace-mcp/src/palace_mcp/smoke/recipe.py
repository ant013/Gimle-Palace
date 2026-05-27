"""Versioned recipe schema — no machine-local absolute paths.

GIM-839 D0 contract: recipes are committed and portable. Machine-local
checkout paths live exclusively in RuntimeBinding (see runtime_binding.py).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Prepare-step discriminated union
# ---------------------------------------------------------------------------


class EnsureConfigFromTemplate(BaseModel, frozen=True):
    type: Literal["ensure_config_from_template"] = "ensure_config_from_template"
    template: str
    destination: str


PrepareStep = Annotated[
    Union[EnsureConfigFromTemplate],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Build configuration
# ---------------------------------------------------------------------------


class BuildConfig(BaseModel, frozen=True):
    workspace: str | None = None
    project: str | None = None
    scheme: str
    destination: str = "generic/platform=iOS Simulator"
    simulator_arch: Literal["auto", "arm64", "x86_64"] = "auto"
    derived_data_path: str = ".palace-scip-derived-data"
    code_signing_allowed: bool = False
    package_resolution: Literal["locked", "automatic"] = "locked"
    skip_build_reason: str | None = None


# ---------------------------------------------------------------------------
# Path safety checks
# ---------------------------------------------------------------------------

_TRAVERSAL_RE = re.compile(r"(^|/)\.\.(/|$)")


def _looks_absolute(value: str) -> bool:
    return value.startswith(("/", "absolute:"))


def _has_traversal(value: str) -> bool:
    return bool(_TRAVERSAL_RE.search(value))


def _check_path_safety(values: Mapping[str, object]) -> None:
    """Raise ValueError for absolute paths or path traversal."""
    for field_name, value in values.items():
        if field_name in ("type",):
            continue
        if isinstance(value, str):
            if _looks_absolute(value):
                raise ValueError(
                    f"absolute path in versioned recipe field '{field_name}': "
                    f"'{value}' — use RuntimeBinding for machine-local paths"
                )
            if _has_traversal(value):
                raise ValueError(
                    f"path traversal in versioned recipe field '{field_name}': "
                    f"'{value}'"
                )
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    if _looks_absolute(item):
                        raise ValueError(
                            f"absolute path in versioned recipe field "
                            f"'{field_name}[{i}]': '{item}'"
                        )
                    if _has_traversal(item):
                        raise ValueError(
                            f"path traversal in versioned recipe field "
                            f"'{field_name}[{i}]': '{item}'"
                        )


# ---------------------------------------------------------------------------
# Recipe (versioned, portable)
# ---------------------------------------------------------------------------


class Recipe(BaseModel, frozen=True, extra="forbid"):
    """Versioned project recipe — committed to the repo, no absolute paths."""

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str
    language: Literal["swift"]
    build_system: Literal["xcode_workspace", "xcode_project", "swift_package"]

    source_roots: list[str] = Field(min_length=1)
    workspace_package_roots: list[str] = []
    dependency_roots: list[str] = []
    generated_roots: list[str] = []
    derived_roots: list[str] = []

    scip_path: str
    prepare_steps: list[PrepareStep] = []
    build: BuildConfig
    extractors: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_recipe(self) -> Recipe:
        self._reject_unsafe_paths()
        self._validate_build_target()
        return self

    def _reject_unsafe_paths(self) -> None:
        path_fields = {
            "scip_path": self.scip_path,
            "source_roots": self.source_roots,
            "workspace_package_roots": self.workspace_package_roots,
            "dependency_roots": self.dependency_roots,
            "generated_roots": self.generated_roots,
            "derived_roots": self.derived_roots,
        }
        _check_path_safety(path_fields)

        if self.build.workspace:
            if _looks_absolute(self.build.workspace):
                raise ValueError(
                    f"absolute path in build.workspace: '{self.build.workspace}'"
                )
            if _has_traversal(self.build.workspace):
                raise ValueError(
                    f"path traversal in build.workspace: '{self.build.workspace}'"
                )
        if self.build.project:
            if _looks_absolute(self.build.project):
                raise ValueError(
                    f"absolute path in build.project: '{self.build.project}'"
                )
            if _has_traversal(self.build.project):
                raise ValueError(
                    f"path traversal in build.project: '{self.build.project}'"
                )
        if _looks_absolute(self.build.derived_data_path):
            raise ValueError(
                f"absolute path in build.derived_data_path: "
                f"'{self.build.derived_data_path}'"
            )
        if _has_traversal(self.build.derived_data_path):
            raise ValueError(
                f"path traversal in build.derived_data_path: "
                f"'{self.build.derived_data_path}'"
            )

        for step in self.prepare_steps:
            if isinstance(step, EnsureConfigFromTemplate):
                step_fields = {
                    "prepare_steps.template": step.template,
                    "prepare_steps.destination": step.destination,
                }
                _check_path_safety(step_fields)

    def _validate_build_target(self) -> None:
        if self.build_system == "xcode_workspace" and not self.build.workspace:
            raise ValueError("build_system 'xcode_workspace' requires build.workspace")
        if self.build_system == "xcode_project" and not self.build.project:
            raise ValueError("build_system 'xcode_project' requires build.project")


def load_recipe_yaml(path: Path) -> Recipe:
    """Load a Recipe from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return Recipe.model_validate(data)
