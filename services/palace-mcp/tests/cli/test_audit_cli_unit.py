"""Unit tests for palace_mcp.cli audit subcommands (S1.9).

CI-compatible: no live palace-mcp or Paperclip API required.
Tests cover:
- Argument-parse semantics
- Request payload construction
- Error envelope on missing/invalid args
- Slug regex validation
- dry-run output
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import pytest

from palace_mcp.cli import (
    _DEFAULT_COMPANY_ID,
    _DOMAIN_AGENTS,
    build_child_payload,
    build_dry_run_payloads,
    build_mcp_run_args,
    build_parent_payload,
    build_parser,
    validate_slug,
    _cmd_audit_run,
    _cmd_audit_launch,
)


# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------


class TestSlugValidation:
    def test_valid_slug(self) -> None:
        validate_slug("gimle")
        validate_slug("my-project")
        validate_slug("a")

    def test_invalid_uppercase(self) -> None:
        with pytest.raises(ValueError, match="invalid slug"):
            validate_slug("GIMLE")

    def test_invalid_space(self) -> None:
        with pytest.raises(ValueError, match="invalid slug"):
            validate_slug("my project")

    def test_invalid_special_chars(self) -> None:
        with pytest.raises(ValueError, match="invalid slug"):
            validate_slug("my.project!")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestArgParsing:
    def test_audit_run_project_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["audit", "run", "--project=gimle"])
        assert args.project == "gimle"
        assert args.bundle is None
        assert args.depth == "full"

    def test_audit_run_bundle_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["audit", "run", "--bundle=uw-ios"])
        assert args.bundle == "uw-ios"
        assert args.project is None

    def test_audit_run_depth_quick(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["audit", "run", "--project=gimle", "--depth=quick"])
        assert args.depth == "quick"

    def test_audit_run_missing_target_exits(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["audit", "run"])
        assert exc_info.value.code != 0

    def test_audit_run_both_project_and_bundle_exits(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["audit", "run", "--project=a", "--bundle=b"])
        assert exc_info.value.code != 0

    def test_audit_launch_dry_run_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "audit",
                "launch",
                "--project=gimle",
                "--auditor-id=test-uuid",
                "--dry-run",
            ]
        )
        assert args.dry_run is True
        assert args.auditor_id == "test-uuid"

    def test_audit_launch_auditor_id_required(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["audit", "launch", "--project=gimle"])
        assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


class TestBuildMcpRunArgs:
    def test_project_arg(self) -> None:
        args = build_mcp_run_args(project="gimle", bundle=None, depth="full")
        assert args == {"depth": "full", "project": "gimle"}

    def test_bundle_arg(self) -> None:
        args = build_mcp_run_args(project=None, bundle="uw-ios", depth="quick")
        assert args == {"depth": "quick", "bundle": "uw-ios"}

    def test_no_extra_keys(self) -> None:
        args = build_mcp_run_args(project="gimle", bundle=None, depth="full")
        assert "bundle" not in args


class TestBuildParentPayload:
    def test_title(self) -> None:
        p = build_parent_payload("gimle", "auditor-uuid", "company-id")
        assert p["title"] == "audit: gimle"

    def test_assignee(self) -> None:
        p = build_parent_payload("gimle", "auditor-uuid", "company-id")
        assert p["assigneeAgentId"] == "auditor-uuid"

    def test_company_id(self) -> None:
        p = build_parent_payload("gimle", "auditor-uuid", "my-company")
        assert p["companyId"] == "my-company"

    def test_required_fields_present(self) -> None:
        p = build_parent_payload("gimle", "auditor-uuid", "company-id")
        for field in ("title", "body", "assigneeAgentId", "companyId"):
            assert field in p


class TestBuildChildPayload:
    def test_title_format(self) -> None:
        c = build_child_payload(
            "gimle", "audit-arch", "agent-uuid", "parent-id", "co-id"
        )
        assert c["title"] == "audit-domain: gimle/audit-arch"

    def test_parent_id_wired(self) -> None:
        c = build_child_payload(
            "gimle", "audit-arch", "agent-uuid", "parent-123", "co-id"
        )
        assert c["parentIssueId"] == "parent-123"

    def test_agent_id_wired(self) -> None:
        c = build_child_payload("gimle", "audit-arch", "my-agent", "parent-id", "co-id")
        assert c["assigneeAgentId"] == "my-agent"


class TestBuildDryRunPayloads:
    def test_returns_4_payloads(self) -> None:
        payloads = build_dry_run_payloads("gimle", "auditor-id", "co-id")
        assert len(payloads) == 4  # 1 parent + 3 children

    def test_first_is_parent(self) -> None:
        payloads = build_dry_run_payloads("gimle", "auditor-id", "co-id")
        assert payloads[0]["title"] == "audit: gimle"

    def test_all_domains_present(self) -> None:
        payloads = build_dry_run_payloads("gimle", "auditor-id", "co-id")
        child_titles = [p["title"] for p in payloads[1:]]
        for da in _DOMAIN_AGENTS:
            assert f"audit-domain: gimle/{da['domain']}" in child_titles

    def test_valid_json_serializable(self) -> None:
        payloads = build_dry_run_payloads("gimle", "auditor-id", "co-id")
        dumped = json.dumps(payloads)
        reloaded: list[Any] = json.loads(dumped)
        assert len(reloaded) == 4


# ---------------------------------------------------------------------------
# Command handlers (error paths — no live network)
# ---------------------------------------------------------------------------


class TestCmdAuditRunErrors:
    def test_invalid_slug_returns_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = argparse.Namespace(
            project="INVALID SLUG!",
            bundle=None,
            url="http://localhost:8000/mcp",
            depth="full",
        )
        rc = _cmd_audit_run(args)
        assert rc == 2
        captured = capsys.readouterr()
        assert "error" in captured.err


class TestCmdAuditLaunchDryRun:
    def test_dry_run_prints_4_payloads(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = argparse.Namespace(
            project="gimle",
            bundle=None,
            auditor_id="test-auditor-uuid",
            company_id=_DEFAULT_COMPANY_ID,
            dry_run=True,
        )
        rc = _cmd_audit_launch(args)
        assert rc == 0
        captured = capsys.readouterr()
        payloads: list[Any] = json.loads(captured.out)
        assert len(payloads) == 4

    def test_dry_run_invalid_slug_returns_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = argparse.Namespace(
            project="INVALID SLUG!",
            bundle=None,
            auditor_id="test-uuid",
            company_id=_DEFAULT_COMPANY_ID,
            dry_run=True,
        )
        rc = _cmd_audit_launch(args)
        assert rc == 2

    def test_dry_run_payloads_well_formed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = argparse.Namespace(
            project="my-project",
            bundle=None,
            auditor_id="auditor-uuid",
            company_id="company-id",
            dry_run=True,
        )
        _cmd_audit_launch(args)
        captured = capsys.readouterr()
        payloads: list[Any] = json.loads(captured.out)
        parent = payloads[0]
        assert parent["title"] == "audit: my-project"
        assert parent["assigneeAgentId"] == "auditor-uuid"
        assert parent["companyId"] == "company-id"
        for child in payloads[1:]:
            assert "parentIssueId" in child
            assert "assigneeAgentId" in child
