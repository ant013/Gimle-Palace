"""Tests for runtime smoke runner (GIM-839 A3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from palace_mcp.smoke.mcp_caller import ExtractorResult, McpCallError
from palace_mcp.smoke.preflight import PreflightCheck, PreflightReport
from palace_mcp.smoke.recipe import Recipe
from palace_mcp.smoke.runner import (
    SMOKE_STAGES,
    RunReport,
    SmokeRunner,
    StageResult,
    StageStatus,
    write_report_json,
)
from palace_mcp.smoke.runtime_binding import RuntimeBinding


def _passing_preflight_report() -> PreflightReport:
    return PreflightReport(
        checks=[PreflightCheck(name="stub", passed=True)],
        passed=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MCP_URL = "http://localhost:8000/mcp"


def _make_recipe(**overrides: Any) -> Recipe:
    defaults: dict[str, Any] = {
        "slug": "test-project",
        "name": "Test Project",
        "language": "swift",
        "build_system": "xcode_workspace",
        "source_roots": ["Sources"],
        "dependency_roots": [".build"],
        "scip_path": "scip/index.scip",
        "build": {
            "workspace": "Test.xcworkspace",
            "scheme": "TestScheme",
        },
        "extractors": ["symbol_index_swift", "dead_code"],
    }
    defaults.update(overrides)
    return Recipe.model_validate(defaults)


def _make_binding(tmp_path: Path) -> RuntimeBinding:
    repo = tmp_path / "repos" / "test-project"
    repo.mkdir(parents=True)
    return RuntimeBinding(
        repo_path=repo,
        parent_mount=tmp_path / "repos",
        mcp_url=_MCP_URL,
    )


def _ok_extractor(name: str) -> ExtractorResult:
    return ExtractorResult(
        ok=True,
        run_id="r1",
        extractor_name=name,
        project="test-project",
        duration_ms=100,
        nodes_written=10,
        edges_written=5,
    )


def _failed_extractor(name: str, message: str = "boom") -> ExtractorResult:
    return ExtractorResult(
        ok=False,
        extractor_name=name,
        project="test-project",
        error_code="extractor_error",
        message=message,
    )


# ---------------------------------------------------------------------------
# Stage order
# ---------------------------------------------------------------------------


@patch(
    "palace_mcp.smoke.runner.run_preflight", return_value=_passing_preflight_report()
)
class TestStageOrder:
    def test_smoke_stages_constant_is_deterministic(self, _pf: Any) -> None:
        assert SMOKE_STAGES == (
            "preflight",
            "prepare",
            "build_scip",
            "register_project",
            "run_extractors",
            "report",
        )

    async def test_stages_execute_in_order(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()

        stage_names = [s.stage for s in report.stages]
        assert stage_names == list(SMOKE_STAGES)

    async def test_mode_is_smoke(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()
        assert report.mode == "smoke"

    async def test_mode_is_semantic_probe(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_semantic_probe()
        assert report.mode == "semantic_probe"


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


@patch(
    "palace_mcp.smoke.runner.run_preflight", return_value=_passing_preflight_report()
)
class TestDryRun:
    async def test_skips_mutating_stages(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()

        mutating = {"build_scip", "register_project", "run_extractors"}
        for stage in report.stages:
            if stage.stage in mutating:
                assert stage.status == StageStatus.SKIPPED, (
                    f"{stage.stage} should be SKIPPED in dry-run"
                )

    async def test_preflight_still_runs(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()

        preflight = next(s for s in report.stages if s.stage == "preflight")
        assert preflight.status == StageStatus.PASSED

    async def test_prepare_still_runs(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()

        prepare = next(s for s in report.stages if s.stage == "prepare")
        assert prepare.status == StageStatus.PASSED

    async def test_dry_run_flag_in_report(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()
        assert report.dry_run is True

    async def test_dry_run_passes_overall(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()
        assert report.passed is True


# ---------------------------------------------------------------------------
# Failure propagation
# ---------------------------------------------------------------------------


def _failing_preflight_report() -> PreflightReport:
    return PreflightReport(
        checks=[
            PreflightCheck(name="repo_path", passed=False, message="repo not found")
        ],
        passed=False,
        actionable_failures=["repo not found"],
    )


@patch(
    "palace_mcp.smoke.runner.run_preflight", return_value=_failing_preflight_report()
)
class TestFailurePropagation:
    async def test_preflight_failure_skips_subsequent(
        self, _pf: Any, tmp_path: Path
    ) -> None:
        recipe = _make_recipe()
        binding = RuntimeBinding(
            repo_path=tmp_path / "repos" / "nonexistent",
            parent_mount=tmp_path / "repos",
            mcp_url=_MCP_URL,
        )
        (tmp_path / "repos").mkdir(parents=True, exist_ok=True)

        runner = SmokeRunner(recipe, binding)
        report = await runner.run_smoke()

        preflight = next(s for s in report.stages if s.stage == "preflight")
        assert preflight.status == StageStatus.FAILED

        for stage in report.stages:
            if stage.stage in (
                "prepare",
                "build_scip",
                "register_project",
                "run_extractors",
            ):
                assert stage.status == StageStatus.SKIPPED, (
                    f"{stage.stage} should be SKIPPED after preflight failure"
                )

    async def test_report_always_runs_after_failure(
        self, _pf: Any, tmp_path: Path
    ) -> None:
        recipe = _make_recipe()
        binding = RuntimeBinding(
            repo_path=tmp_path / "repos" / "nonexistent",
            parent_mount=tmp_path / "repos",
            mcp_url=_MCP_URL,
        )
        (tmp_path / "repos").mkdir(parents=True, exist_ok=True)

        runner = SmokeRunner(recipe, binding)
        report = await runner.run_smoke()

        report_stage = next(s for s in report.stages if s.stage == "report")
        assert report_stage.status == StageStatus.PASSED

    async def test_failed_run_is_not_passed(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = RuntimeBinding(
            repo_path=tmp_path / "repos" / "nonexistent",
            parent_mount=tmp_path / "repos",
            mcp_url=_MCP_URL,
        )
        (tmp_path / "repos").mkdir(parents=True, exist_ok=True)

        runner = SmokeRunner(recipe, binding)
        report = await runner.run_smoke()
        assert report.passed is False


# ---------------------------------------------------------------------------
# Extractor partial failure
# ---------------------------------------------------------------------------


@patch(
    "palace_mcp.smoke.runner.run_preflight", return_value=_passing_preflight_report()
)
class TestExtractorPartialFailure:
    @patch("palace_mcp.smoke.runner.mcp_caller")
    @patch("palace_mcp.smoke.runner.asyncio.create_subprocess_exec")
    async def test_partial_failure_continues(
        self, mock_subprocess: AsyncMock, mock_mcp: AsyncMock, _pf: Any, tmp_path: Path
    ) -> None:
        recipe = _make_recipe(
            extractors=["symbol_index_swift", "dead_code", "embedding_symbol"]
        )
        binding = _make_binding(tmp_path)

        mock_mcp.list_tools = AsyncMock(return_value=["palace.memory.register_project"])

        proc_mock = AsyncMock()
        proc_mock.communicate.return_value = (b"BUILD SUCCEEDED", None)
        proc_mock.returncode = 0
        mock_subprocess.return_value = proc_mock

        scip_file = binding.repo_path / recipe.scip_path
        scip_file.parent.mkdir(parents=True, exist_ok=True)
        scip_file.write_bytes(b"scip-data")

        mock_mcp.register_project = AsyncMock(
            return_value={"slug": "test-project", "name": "Test Project"}
        )
        mock_mcp.run_extractor = AsyncMock(
            side_effect=[
                _ok_extractor("symbol_index_swift"),
                _failed_extractor("dead_code", "timeout"),
                _ok_extractor("embedding_symbol"),
            ]
        )

        runner = SmokeRunner(recipe, binding)
        report = await runner.run_smoke()

        ext_stage = next(s for s in report.stages if s.stage == "run_extractors")
        assert ext_stage.status == StageStatus.FAILED

        extractors = ext_stage.details.get("extractors", [])
        assert len(extractors) == 3
        assert extractors[0]["ok"] is True
        assert extractors[1]["ok"] is False
        assert extractors[2]["ok"] is True

    @patch("palace_mcp.smoke.runner.mcp_caller")
    @patch("palace_mcp.smoke.runner.asyncio.create_subprocess_exec")
    async def test_extractor_call_error_captured(
        self, mock_subprocess: AsyncMock, mock_mcp: AsyncMock, _pf: Any, tmp_path: Path
    ) -> None:
        recipe = _make_recipe(extractors=["symbol_index_swift"])
        binding = _make_binding(tmp_path)

        mock_mcp.list_tools = AsyncMock(return_value=[])

        proc_mock = AsyncMock()
        proc_mock.communicate.return_value = (b"ok", None)
        proc_mock.returncode = 0
        mock_subprocess.return_value = proc_mock

        scip_file = binding.repo_path / recipe.scip_path
        scip_file.parent.mkdir(parents=True, exist_ok=True)
        scip_file.write_bytes(b"x")

        mock_mcp.register_project = AsyncMock(return_value={"slug": "s"})
        mock_mcp.run_extractor = AsyncMock(
            side_effect=McpCallError(
                "connection refused", tool_name="palace.ingest.run_extractor"
            )
        )

        runner = SmokeRunner(recipe, binding)
        report = await runner.run_smoke()

        ext_stage = next(s for s in report.stages if s.stage == "run_extractors")
        assert ext_stage.status == StageStatus.FAILED
        extractors = ext_stage.details.get("extractors", [])
        assert len(extractors) == 1
        assert extractors[0]["ok"] is False
        assert extractors[0]["error_code"] == "call_failed"


# ---------------------------------------------------------------------------
# Successful full run (mocked)
# ---------------------------------------------------------------------------


@patch(
    "palace_mcp.smoke.runner.run_preflight", return_value=_passing_preflight_report()
)
class TestSuccessfulRun:
    @patch("palace_mcp.smoke.runner.mcp_caller")
    @patch("palace_mcp.smoke.runner.asyncio.create_subprocess_exec")
    async def test_all_stages_pass(
        self, mock_subprocess: AsyncMock, mock_mcp: AsyncMock, _pf: Any, tmp_path: Path
    ) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)

        mock_mcp.list_tools = AsyncMock(return_value=["palace.memory.register_project"])

        proc_mock = AsyncMock()
        proc_mock.communicate.return_value = (b"BUILD SUCCEEDED", None)
        proc_mock.returncode = 0
        mock_subprocess.return_value = proc_mock

        scip_file = binding.repo_path / recipe.scip_path
        scip_file.parent.mkdir(parents=True, exist_ok=True)
        scip_file.write_bytes(b"scip-index-content")

        mock_mcp.register_project = AsyncMock(
            return_value={"slug": "test-project", "name": "Test Project"}
        )
        mock_mcp.run_extractor = AsyncMock(
            side_effect=[
                _ok_extractor("symbol_index_swift"),
                _ok_extractor("dead_code"),
            ]
        )

        runner = SmokeRunner(recipe, binding)
        report = await runner.run_smoke()

        assert report.passed is True
        assert report.recipe_slug == "test-project"
        assert report.dry_run is False

        for stage in report.stages:
            assert stage.status == StageStatus.PASSED, f"{stage.stage} should be PASSED"

    @patch("palace_mcp.smoke.runner.mcp_caller")
    @patch("palace_mcp.smoke.runner.asyncio.create_subprocess_exec")
    async def test_report_has_timing(
        self, mock_subprocess: AsyncMock, mock_mcp: AsyncMock, _pf: Any, tmp_path: Path
    ) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)

        mock_mcp.list_tools = AsyncMock(return_value=[])
        proc_mock = AsyncMock()
        proc_mock.communicate.return_value = (b"ok", None)
        proc_mock.returncode = 0
        mock_subprocess.return_value = proc_mock

        scip_file = binding.repo_path / recipe.scip_path
        scip_file.parent.mkdir(parents=True, exist_ok=True)
        scip_file.write_bytes(b"x")

        mock_mcp.register_project = AsyncMock(return_value={})
        mock_mcp.run_extractor = AsyncMock(
            side_effect=[
                _ok_extractor("symbol_index_swift"),
                _ok_extractor("dead_code"),
            ]
        )

        runner = SmokeRunner(recipe, binding)
        report = await runner.run_smoke()

        assert report.started_at < report.finished_at
        for stage in report.stages:
            assert stage.duration_ms >= 0


# ---------------------------------------------------------------------------
# JSON report writer
# ---------------------------------------------------------------------------


@patch(
    "palace_mcp.smoke.runner.run_preflight", return_value=_passing_preflight_report()
)
class TestReportWriter:
    async def test_write_report_json(self, _pf: Any, tmp_path: Path) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()

        out_path = tmp_path / "reports" / "smoke.json"
        write_report_json(report, out_path)

        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["recipe_slug"] == "test-project"
        assert data["dry_run"] is True
        assert isinstance(data["stages"], list)
        assert len(data["stages"]) == len(SMOKE_STAGES)


# ---------------------------------------------------------------------------
# Report stage details
# ---------------------------------------------------------------------------


@patch(
    "palace_mcp.smoke.runner.run_preflight", return_value=_passing_preflight_report()
)
class TestReportStageContent:
    async def test_report_stage_contains_stage_summaries(
        self, _pf: Any, tmp_path: Path
    ) -> None:
        recipe = _make_recipe()
        binding = _make_binding(tmp_path)
        runner = SmokeRunner(recipe, binding, dry_run=True)
        report = await runner.run_smoke()

        report_stage = next(s for s in report.stages if s.stage == "report")
        assert "stages" in report_stage.details
        assert "recipe_slug" in report_stage.details
        assert report_stage.details["recipe_slug"] == "test-project"


# ---------------------------------------------------------------------------
# StageResult / RunReport model checks
# ---------------------------------------------------------------------------


class TestModels:
    def test_stage_result_serializes(self) -> None:
        r = StageResult(
            stage="preflight",
            status=StageStatus.PASSED,
            duration_ms=42,
            details={"repo_path_exists": True},
        )
        d = r.model_dump()
        assert d["stage"] == "preflight"
        assert d["status"] == "passed"
        assert d["duration_ms"] == 42

    def test_run_report_serializes(self) -> None:
        r = RunReport(
            recipe_slug="test",
            mode="smoke",
            dry_run=False,
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:01:00Z",
            stages=[],
            passed=True,
        )
        d = r.model_dump()
        assert d["mode"] == "smoke"
        assert d["passed"] is True
