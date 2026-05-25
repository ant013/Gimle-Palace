"""Versioned recipe schema — no machine-local absolute paths.

GIM-839 D0 contract: recipes are committed and portable. Machine-local
checkout paths live exclusively in RuntimeBinding (see runtime_binding.py).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Literal, Union

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


# ---------------------------------------------------------------------------
# Absolute-path detector
# ---------------------------------------------------------------------------

_ABS_PATH_RE = re.compile(r"(?:^|/)(?:/[A-Za-z]|/Users|/home|/tmp|/var|/opt|/ABS)")


def _looks_absolute(value: str) -> bool:
    return value.startswith("/")


def _check_no_absolute_paths(values: Mapping[str, object]) -> None:
    """Raise ValueError if any string field contains an absolute path."""
    for field_name, value in values.items():
        if field_name in ("type",):
            continue
        if isinstance(value, str) and _looks_absolute(value):
            raise ValueError(
                f"absolute path in versioned recipe field '{field_name}': "
                f"'{value}' — use RuntimeBinding for machine-local paths"
            )
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str) and _looks_absolute(item):
                    raise ValueError(
                        f"absolute path in versioned recipe field "
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

    source_roots: list[str]
    workspace_package_roots: list[str] = []
    dependency_roots: list[str] = []
    generated_roots: list[str] = []
    derived_roots: list[str] = []

    scip_path: str
    prepare_steps: list[PrepareStep] = []
    build: BuildConfig
    extractors: list[str]

    @model_validator(mode="after")
    def _reject_absolute_paths(self) -> Recipe:
        path_fields = {
            "scip_path": self.scip_path,
            "source_roots": self.source_roots,
            "workspace_package_roots": self.workspace_package_roots,
            "dependency_roots": self.dependency_roots,
            "generated_roots": self.generated_roots,
            "derived_roots": self.derived_roots,
        }
        _check_no_absolute_paths(path_fields)

        if self.build.workspace and _looks_absolute(self.build.workspace):
            raise ValueError(
                f"absolute path in build.workspace: '{self.build.workspace}'"
            )
        if self.build.project and _looks_absolute(self.build.project):
            raise ValueError(
                f"absolute path in build.project: '{self.build.project}'"
            )
        if _looks_absolute(self.build.derived_data_path):
            raise ValueError(
                f"absolute path in build.derived_data_path: "
                f"'{self.build.derived_data_path}'"
            )

        for step in self.prepare_steps:
            if isinstance(step, EnsureConfigFromTemplate):
                step_fields = {
                    "prepare_steps.template": step.template,
                    "prepare_steps.destination": step.destination,
                }
                _check_no_absolute_paths(step_fields)

        return self
