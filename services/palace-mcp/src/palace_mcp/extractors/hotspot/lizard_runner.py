from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from palace_mcp.extractors.hotspot.models import ParsedFile, ParsedFunction

logger = logging.getLogger(__name__)

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".sol": "solidity",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".m": "objc",
    ".mm": "objc",
    ".rb": "ruby",
    ".php": "php",
    ".scala": "scala",
}

_ITEM_RE = re.compile(r"^(?P<name>[^(]+)\(.*\) at (?P<path>.+?):(?P<line>\d+)$")


class LizardBatchTimeout(Exception):
    pass


@dataclass(frozen=True)
class LizardRunResult:
    parsed: tuple[ParsedFile, ...]
    skipped_files: tuple[str, ...]


async def _invoke_lizard(files: list[Path], *, timeout_s: int) -> str:
    proc = await asyncio.create_subprocess_exec(
        "lizard",
        "--xml",
        "--working_threads=1",
        *map(str, files),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return stdout_b.decode("utf-8", errors="replace")


def parse_lizard_xml(xml_text: str, *, repo_root: Path) -> tuple[ParsedFile, ...]:
    if not xml_text.strip():
        return ()
    root = ET.fromstring(xml_text)
    fns_by_path: dict[str, list[ParsedFunction]] = {}
    for item in root.findall(".//measure[@type='Function']/item"):
        name_attr = item.attrib.get("name", "")
        m = _ITEM_RE.match(name_attr)
        if not m:
            continue
        try:
            abs_path = Path(m.group("path"))
            rel = abs_path.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        values = [
            int(v.text)
            for v in item.findall("value")
            if v.text and v.text.strip().lstrip("-").isdigit()
        ]
        if len(values) < 3:
            continue
        nloc, ccn = values[1], values[2]
        params = _count_params(name_attr)
        fns_by_path.setdefault(rel, []).append(
            ParsedFunction(
                name=m.group("name").strip(),
                start_line=int(m.group("line")),
                end_line=int(m.group("line")) + max(nloc - 1, 0),
                ccn=ccn,
                parameter_count=params,
                nloc=nloc,
            )
        )

    out: list[ParsedFile] = []
    for rel, fns in fns_by_path.items():
        ext = Path(rel).suffix
        lang = _EXT_TO_LANG.get(ext, "unknown")
        out.append(ParsedFile(path=rel, language=lang, functions=tuple(fns)))
    return tuple(out)


def _count_params(name_attr: str) -> int:
    try:
        inner = name_attr.split("(", 1)[1].rsplit(")", 1)[0].strip()
    except IndexError:
        return 0
    if not inner:
        return 0
    return len([p for p in inner.split(",") if p.strip()])


async def run_batch(
    files: list[Path],
    *,
    repo_root: Path,
    timeout_s: int,
    behavior: Literal["drop_batch", "fail_run"],
) -> LizardRunResult:
    if not files:
        return LizardRunResult(parsed=(), skipped_files=())
    try:
        xml_text = await _invoke_lizard(files, timeout_s=timeout_s)
    except TimeoutError:
        skipped = tuple(f.relative_to(repo_root).as_posix() for f in files)
        if behavior == "fail_run":
            raise LizardBatchTimeout(
                f"lizard batch timeout ({timeout_s}s) on {len(files)} files; "
                f"first: {skipped[0] if skipped else '<empty>'}"
            )
        logger.warning(
            "hotspot_lizard_batch_timeout",
            extra={
                "batch_size": len(files),
                "first_file": skipped[0] if skipped else None,
            },
        )
        return LizardRunResult(parsed=(), skipped_files=skipped)
    parsed = parse_lizard_xml(xml_text, repo_root=repo_root)
    return LizardRunResult(parsed=parsed, skipped_files=())
