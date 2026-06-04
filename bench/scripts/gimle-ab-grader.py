#!/usr/bin/env python3
"""Mechanical grader for gimle-ab benchmark artifacts.

Reads a subagent's final response text + the gold checklist for a task,
computes pass_score (fraction of must_contain regex matched), and emits
a CSV row.

Usage:
    python3 gimle-ab-grader.py <task_id> <arm> <run_idx> <artifact_path> [--csv-append PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

GOLD_DIR = Path(__file__).parent.parent / "gold"


def grade(task_id: str, artifact_text: str) -> dict[str, object]:
    """Apply the gold checklist regexes against the artifact text.

    Returns a dict with grading details and an aggregate pass_score in [0, 1].
    """
    gold_path = GOLD_DIR / f"{task_id}.json"
    if not gold_path.exists():
        return {
            "pass_score": 0.0,
            "error": f"gold checklist not found: {gold_path}",
        }
    gold = json.loads(gold_path.read_text())

    must_results: list[tuple[str, bool]] = []
    for pat in gold.get("must_contain_regex", []):
        must_results.append((pat, bool(re.search(pat, artifact_text, re.IGNORECASE))))

    must_not_results: list[tuple[str, bool]] = []
    for pat in gold.get("must_not_contain_regex", []):
        must_not_results.append(
            (pat, not bool(re.search(pat, artifact_text, re.IGNORECASE)))
        )

    any_n = gold.get("any_n_of_regex")
    any_n_score = 0.0
    any_n_hits: list[str] = []
    if any_n:
        n = any_n.get("n", 1)
        items = any_n.get("items", [])
        for pat in items:
            if re.search(pat, artifact_text, re.IGNORECASE):
                any_n_hits.append(pat)
        any_n_score = min(1.0, len(any_n_hits) / max(1, n))

    must_score = (
        sum(1 for _, ok in must_results if ok) / max(1, len(must_results))
        if must_results
        else 1.0
    )
    must_not_score = (
        sum(1 for _, ok in must_not_results if ok) / max(1, len(must_not_results))
        if must_not_results
        else 1.0
    )

    # Aggregate: must+must_not weighted as hard gates, any_n as bonus
    if any_n:
        pass_score = (must_score + must_not_score + any_n_score) / 3.0
    else:
        pass_score = (must_score + must_not_score) / 2.0

    return {
        "pass_score": round(pass_score, 3),
        "must_score": round(must_score, 3),
        "must_not_score": round(must_not_score, 3),
        "any_n_score": round(any_n_score, 3),
        "any_n_hits_count": len(any_n_hits),
        "must_results": must_results,
        "must_not_results": must_not_results,
        "any_n_hits": any_n_hits,
        "qualitative": gold.get("qualitative", False),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("task")
    p.add_argument("arm")
    p.add_argument("run")
    p.add_argument("artifact_path")
    p.add_argument("--subagent-tokens", type=int, default=None)
    p.add_argument("--duration-ms", type=int, default=None)
    p.add_argument("--tool-uses", type=int, default=None)
    p.add_argument("--csv-append", default=None)
    args = p.parse_args()

    artifact_text = Path(args.artifact_path).read_text()
    g = grade(args.task, artifact_text)
    g.update(
        task=args.task,
        arm=args.arm,
        run=args.run,
        subagent_tokens=args.subagent_tokens,
        duration_ms=args.duration_ms,
        tool_uses=args.tool_uses,
    )

    print(json.dumps(g, indent=2))

    if args.csv_append:
        csv_path = Path(args.csv_append)
        write_header = not csv_path.exists()
        cols = [
            "task",
            "arm",
            "run",
            "pass_score",
            "must_score",
            "must_not_score",
            "any_n_score",
            "any_n_hits_count",
            "subagent_tokens",
            "duration_ms",
            "tool_uses",
            "qualitative",
        ]
        with csv_path.open("a") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            if write_header:
                w.writeheader()
            w.writerow({k: g.get(k) for k in cols})


if __name__ == "__main__":
    main()
