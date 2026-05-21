from __future__ import annotations

from abc import ABC, abstractmethod

from palace_mcp.extractors.coding_convention.models import ConventionSignal


class ConventionRule(ABC):
    kind: str

    @abstractmethod
    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        raise NotImplementedError


def build_signal(
    *,
    module: str,
    rel_path: str,
    text: str,
    offset: int,
    kind: str,
    choice: str,
    evidence: str,
    message: str | None = None,
) -> ConventionSignal:
    line = text.count("\n", 0, offset) + 1
    return ConventionSignal(
        module=module,
        kind=kind,
        choice=choice,
        file=rel_path,
        start_line=line,
        end_line=line,
        message=message or f"{kind} prefers {choice}; found {evidence} in {rel_path}",
    )
