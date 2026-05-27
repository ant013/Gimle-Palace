"""PR7 runtime smoke matrix artifact writer.

This command validates the committed runtime smoke matrix against fixture
evidence, then writes machine-readable JSON and a markdown QA summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_MATRIX = (
    _SERVICE_ROOT / "tests" / "runtime_smoke_matrix" / "runtime_smoke_matrix.yaml"
)
_DEFAULT_FIXTURES = (
    _SERVICE_ROOT / "tests" / "runtime_smoke_matrix" / "fixtures" / "responses.json"
)
_DEFAULT_JSON_OUT = _SERVICE_ROOT / "artifacts" / "runtime-smoke-matrix.json"
_DEFAULT_MARKDOWN_OUT = _SERVICE_ROOT / "artifacts" / "runtime-smoke-matrix.md"

sys.path.insert(0, str(_SERVICE_ROOT / "src"))
sys.path.insert(0, str(_SERVICE_ROOT))

from tests.runtime_smoke_matrix.evaluator import (  # noqa: E402
    build_json_summary,
    load_matrix,
    render_markdown_report,
    run_matrix,
)


def _git_head_sha(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=_DEFAULT_MATRIX)
    parser.add_argument("--fixture", type=Path, default=_DEFAULT_FIXTURES)
    parser.add_argument("--json-out", type=Path, default=_DEFAULT_JSON_OUT)
    parser.add_argument("--markdown-out", type=Path, default=_DEFAULT_MARKDOWN_OUT)
    args = parser.parse_args()

    schema_version, runner_version, rows = load_matrix(args.matrix)
    responses = json.loads(args.fixture.read_text(encoding="utf-8"))
    report = run_matrix(rows, responses)
    commit_sha = _git_head_sha(_SERVICE_ROOT.parent.parent)

    json_payload = build_json_summary(
        schema_version=schema_version,
        runner_version=runner_version,
        commit_sha=commit_sha,
        rows=rows,
        report=report,
    )
    markdown = render_markdown_report(
        schema_version=schema_version,
        runner_version=runner_version,
        commit_sha=commit_sha,
        rows=rows,
        report=report,
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(json_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_out.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(
        json.dumps(
            {
                "json_out": str(args.json_out),
                "markdown_out": str(args.markdown_out),
                "rows": len(rows),
                "passed": report.passed,
            },
            indent=2,
        )
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
