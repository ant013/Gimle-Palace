"""Pydantic response models for palace.git.* tools. Spec §4.

Every tool returns either a tool-specific success model or a shared
ErrorResponse. MCP clients receive the discriminated union.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_CFG = ConfigDict(extra="forbid")


# --- Shared ---


class ErrorResponse(BaseModel):
    model_config = _CFG

    ok: Literal[False] = False
    error_code: str
    message: str
    project: str | None = None


# --- log ---


class LogEntry(BaseModel):
    model_config = _CFG

    sha: str
    short: str
    author_name: str
    author_email: str
    date: str  # ISO-8601 with TZ (%aI)
    subject: str


class LogResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    ref: str
    entries: list[LogEntry]
    truncated: bool


# --- show (two modes) ---


class FileStat(BaseModel):
    model_config = _CFG

    path: str
    added: int | None = None  # None → binary
    deleted: int | None = None  # None → binary
    status: str | None = None  # M/A/D etc., commit mode only


class ShowCommitResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    mode: Literal["commit"] = "commit"
    project: str
    sha: str
    author_name: str
    date: str
    subject: str
    body: str
    files_changed: list[FileStat]
    diff: str
    truncated: bool


class ShowFileResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    mode: Literal["file"] = "file"
    project: str
    ref: str
    path: str
    content: str
    lines: int
    truncated: bool


class BinaryFileResponse(BaseModel):
    model_config = _CFG

    ok: Literal[False] = False
    error_code: Literal["binary_file"] = "binary_file"
    project: str
    ref: str
    path: str
    size_bytes: int


# --- blame ---


class BlameLine(BaseModel):
    model_config = _CFG

    line_no: int
    sha: str
    short: str
    author_name: str
    date: str
    content: str


class BlameResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    path: str
    ref: str
    lines: list[BlameLine]
    truncated: bool


# --- diff ---


class DiffResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    ref_a: str
    ref_b: str
    path: str | None
    mode: Literal["full", "stat"]
    diff: str | None = None  # populated when mode="full"
    files_stat: list[FileStat] | None = None  # populated when mode="stat"
    truncated: bool


# --- ls_tree ---


class TreeEntry(BaseModel):
    model_config = _CFG

    path: str
    type: Literal["blob", "tree", "commit"]  # commit = submodule
    mode: str
    sha: str


class LsTreeResponse(BaseModel):
    model_config = _CFG

    ok: Literal[True] = True
    project: str
    ref: str
    path: str | None
    recursive: bool
    entries: list[TreeEntry]
    truncated: bool
