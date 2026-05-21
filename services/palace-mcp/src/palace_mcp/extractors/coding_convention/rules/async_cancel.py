from __future__ import annotations

import re

from palace_mcp.extractors.coding_convention.models import ConventionSignal
from palace_mcp.extractors.coding_convention.rules._base import (
    ConventionRule,
    build_signal,
)

_STRUCTURED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bwithTaskCancellationHandler\s*\("),
        "withTaskCancellationHandler",
    ),
    (re.compile(r"\bTask\.checkCancellation\(\)"), "Task.checkCancellation()"),
    (re.compile(r"\btry(?:\s+await)?\s+Task\.sleep\b"), "Task.sleep"),
)
_ASYNC_SAMPLE_RE = re.compile(
    r"\basync\b|\bawait\b|\bTask(?:\s*[\{<(]|\.|<)|\bwithTaskCancellationHandler\b"
)
_POLLING_RE = re.compile(r"\bTask\.(?:isCancelled|currentPriority)\b")
_CONTROL_FLOW_RE = re.compile(r"\b(if|guard|while|for)\b")
_EARLY_EXIT_RE = re.compile(r"\b(return|throw|break|continue)\b")
_TASK_PROPERTY_RE = re.compile(
    r"\b(?:let|var)\s+(?P<name>\w+)\s*:\s*Task<[^>\n]+>\??", re.MULTILINE
)
_TASK_ASSIGN_RE = re.compile(
    r"\b(?P<name>\w+)\s*=\s*Task(?:\s*\.detached)?\s*[\{<(]", re.MULTILINE
)
_CANCEL_CALL_RE = re.compile(r"\b(?P<name>\w+)\??\.cancel\(\)")


class AsyncCancelRule(ConventionRule):
    kind = "async_cancel"

    def collect(
        self, *, module: str, rel_path: str, text: str
    ) -> list[ConventionSignal]:
        if not rel_path.endswith(".swift"):
            return []

        structured = self._structured_signal(
            module=module, rel_path=rel_path, text=text
        )
        if structured is not None:
            return [structured]

        manual = self._manual_task_handle_signal(
            module=module, rel_path=rel_path, text=text
        )
        if manual is not None:
            return [manual]

        cooperative = self._cooperative_polling_signal(
            module=module, rel_path=rel_path, text=text
        )
        if cooperative is not None:
            return [cooperative]

        sample = _ASYNC_SAMPLE_RE.search(text)
        if sample is None:
            return []

        return [
            build_signal(
                module=module,
                rel_path=rel_path,
                text=text,
                offset=sample.start(),
                kind=self.kind,
                choice="missing_or_unclear",
                evidence=sample.group(0).strip(),
                message=(
                    "async_cancel prefers missing_or_unclear; found async/task "
                    f"usage without cancellation evidence in {rel_path}"
                ),
            )
        ]

    def _structured_signal(
        self, *, module: str, rel_path: str, text: str
    ) -> ConventionSignal | None:
        for pattern, evidence in _STRUCTURED_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            return build_signal(
                module=module,
                rel_path=rel_path,
                text=text,
                offset=match.start(),
                kind=self.kind,
                choice="structured_propagation",
                evidence=evidence,
            )
        return None

    def _manual_task_handle_signal(
        self, *, module: str, rel_path: str, text: str
    ) -> ConventionSignal | None:
        task_names = {
            match.group("name")
            for pattern in (_TASK_PROPERTY_RE, _TASK_ASSIGN_RE)
            for match in pattern.finditer(text)
        }
        if not task_names:
            return None

        for match in _CANCEL_CALL_RE.finditer(text):
            name = match.group("name")
            if name not in task_names:
                continue
            return build_signal(
                module=module,
                rel_path=rel_path,
                text=text,
                offset=match.start(),
                kind=self.kind,
                choice="manual_task_handle",
                evidence=f"{name}.cancel()",
                message=(
                    "async_cancel prefers manual_task_handle; found stored task "
                    f"handle cleanup via {name}.cancel() in {rel_path}"
                ),
            )
        return None

    def _cooperative_polling_signal(
        self, *, module: str, rel_path: str, text: str
    ) -> ConventionSignal | None:
        for match in _POLLING_RE.finditer(text):
            window_start = max(0, match.start() - 80)
            window_end = min(len(text), match.end() + 240)
            window = text[window_start:window_end]
            if _CONTROL_FLOW_RE.search(window) is None:
                continue
            if _EARLY_EXIT_RE.search(window) is None:
                continue
            evidence = match.group(0)
            return build_signal(
                module=module,
                rel_path=rel_path,
                text=text,
                offset=match.start(),
                kind=self.kind,
                choice="cooperative_polling",
                evidence=evidence,
                message=(
                    "async_cancel prefers cooperative_polling; found "
                    f"{evidence} paired with early exit in {rel_path}"
                ),
            )
        return None


RULES = (AsyncCancelRule(),)
