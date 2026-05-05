from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ParsedFunction(_Frozen):
    name: str = Field(min_length=1, max_length=512)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    ccn: int = Field(ge=0)
    parameter_count: int = Field(ge=0)
    nloc: int = Field(ge=0)

    @model_validator(mode="after")
    def _line_range(self) -> "ParsedFunction":
        if self.end_line < self.start_line:
            raise ValueError(
                f"end_line ({self.end_line}) must be >= start_line ({self.start_line})"
            )
        return self


class ParsedFile(_Frozen):
    path: str = Field(min_length=1, max_length=4096)
    language: str = Field(min_length=1, max_length=64)
    functions: tuple[ParsedFunction, ...]

    @field_validator("path", mode="after")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError(f"path must be repo-relative, got absolute: {v!r}")
        if "\\" in v:
            raise ValueError(f"path must use POSIX separators, got: {v!r}")
        return v

    @property
    def ccn_total(self) -> int:
        return sum(fn.ccn for fn in self.functions)
