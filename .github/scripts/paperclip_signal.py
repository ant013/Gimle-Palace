"""paperclip-signal dispatcher.

Reads a GitHub event + .github/paperclip-signals.yml config, resolves a
wake target (currently only `issue_assignee`), and triggers a paperclip
reassign-refresh to wake the current assignee of the linked paperclip
issue. Designed to run as a GitHub Action on workflow_run /
pull_request_review / pull_request_review_comment / repository_dispatch.

Spec: docs/superpowers/specs/2026-04-20-async-signal-integration-design.md
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml


ALLOWED_TRIGGERS = frozenset({"ci.success", "pr.review", "qa.smoke_complete"})
ROLE_TARGET_RE = re.compile(r"^role\(([A-Za-z][A-Za-z0-9_-]*)\)$")
SUPPORTED_VERSION = 1
BRANCH_RE = re.compile(r"^feature/GIM-(\d+)-")
GITHUB_API_BASE = "https://api.github.com"
ACTIVE_RUN_RECHECK_DELAY_SECONDS = 30
RETRY_DELAYS_SECONDS = (10, 30)
RETRY_STATUS_CODES = {409, 500, 502, 503, 504}

log = logging.getLogger("paperclip-signal")


class ConfigError(Exception):
    """Raised when the signals config is malformed or contains unsupported values."""


class PaperclipError(Exception):
    """Raised for paperclip API failures (network, 4xx, 5xx after retries)."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    trigger: str
    target: str
    note: str = ""


@dataclass(frozen=True)
class Config:
    version: int
    company_id: str
    rules: list[Rule] = field(default_factory=list)
    bot_authors: list[str] = field(default_factory=list)


def _validate_target(target: str) -> None:
    if target == "issue_assignee":
        return
    if ROLE_TARGET_RE.match(target):
        return
    raise ConfigError(
        f"Unknown target {target!r}. Supported: 'issue_assignee' or 'role(<Name>)'."
    )


def _validate_trigger(trigger: str) -> None:
    if trigger == "pr.review_comment":
        raise ConfigError(
            "trigger 'pr.review_comment' is not a valid config key. "
            "The GitHub event pull_request_review_comment is normalized to "
            "'pr.review' in parse_event; use 'pr.review' instead."
        )
    if trigger not in ALLOWED_TRIGGERS:
        raise ConfigError(
            f"Unknown trigger {trigger!r}. Supported: {sorted(ALLOWED_TRIGGERS)}."
        )


def load_config(path: Path) -> Config:
    """Parse and validate the signals config from disk."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping, got {type(raw).__name__}.")

    version = raw.get("version")
    if version != SUPPORTED_VERSION:
        raise ConfigError(
            f"Unsupported config version {version!r}. Expected {SUPPORTED_VERSION}."
        )

    company_id = raw.get("company_id")
    if not isinstance(company_id, str) or not company_id:
        raise ConfigError("company_id must be a non-empty string.")

    rules_raw = raw.get("rules") or []
    if not isinstance(rules_raw, list):
        raise ConfigError("rules must be a list.")

    rules: list[Rule] = []
    for i, entry in enumerate(rules_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"rules[{i}] must be a mapping.")
        trigger = entry.get("trigger")
        target = entry.get("target")
        note = entry.get("note", "")
        if not isinstance(trigger, str):
            raise ConfigError(f"rules[{i}].trigger must be a string.")
        if not isinstance(target, str):
            raise ConfigError(f"rules[{i}].target must be a string.")
        _validate_trigger(trigger)
        _validate_target(target)
        rules.append(Rule(trigger=trigger, target=target, note=note))

    bot_authors = raw.get("bot_authors") or []
    if not isinstance(bot_authors, list) or not all(isinstance(x, str) for x in bot_authors):
        raise ConfigError("bot_authors must be a list of strings.")

    return Config(
        version=version,
        company_id=company_id,
        rules=rules,
        bot_authors=list(bot_authors),
    )


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """Normalized GitHub webhook event."""

    trigger: str
    sha: str
    pr_number: int
    branch: str
    author: str


def _parse_workflow_run(payload: dict) -> Event | None:
    run = payload.get("workflow_run") or {}
    conclusion = run.get("conclusion")
    if conclusion != "success":
        return None
    prs = run.get("pull_requests") or []
    if not prs:
        return None
    pr = prs[0]
    return Event(
        trigger="ci.success",
        sha=run.get("head_sha") or "",
        pr_number=pr.get("number") or 0,
        branch=run.get("head_branch") or pr.get("head", {}).get("ref") or "",
        author=(payload.get("sender") or {}).get("login") or "",
    )


def _parse_pull_request_review(payload: dict) -> Event | None:
    pr = payload.get("pull_request") or {}
    return Event(
        trigger="pr.review",
        sha=(payload.get("review") or {}).get("commit_id") or pr.get("head", {}).get("sha", ""),
        pr_number=pr.get("number") or 0,
        branch=pr.get("head", {}).get("ref") or "",
        author=(payload.get("sender") or {}).get("login") or "",
    )


def _parse_pull_request_review_comment(payload: dict) -> Event | None:
    pr = payload.get("pull_request") or {}
    return Event(
        trigger="pr.review",
        sha=(payload.get("comment") or {}).get("commit_id") or pr.get("head", {}).get("sha", ""),
        pr_number=pr.get("number") or 0,
        branch=pr.get("head", {}).get("ref") or "",
        author=(payload.get("sender") or {}).get("login") or "",
    )


def _parse_repository_dispatch(payload: dict) -> Event | None:
    action = payload.get("action") or ""
    if action != "qa-smoke-complete":
        return None
    cp = payload.get("client_payload") or {}
    branch = cp.get("branch")
    pr_number = cp.get("pr_number")
    sha = cp.get("sha")
    if not branch:
        raise ConfigError(
            "repository_dispatch qa-smoke-complete payload missing required "
            "field 'branch' in client_payload."
        )
    return Event(
        trigger="qa.smoke_complete",
        sha=sha or "",
        pr_number=pr_number or 0,
        branch=branch,
        author=(payload.get("sender") or {}).get("login") or "",
    )


_EVENT_PARSERS = {
    "workflow_run": _parse_workflow_run,
    "pull_request_review": _parse_pull_request_review,
    "pull_request_review_comment": _parse_pull_request_review_comment,
    "repository_dispatch": _parse_repository_dispatch,
}


def parse_event(event_name: str, payload: dict) -> Event | None:
    """Normalize a GitHub webhook into an internal Event, or None if non-actionable."""
    parser = _EVENT_PARSERS.get(event_name)
    if parser is None:
        return None
    return parser(payload)


# ---------------------------------------------------------------------------
# Branch extraction
# ---------------------------------------------------------------------------


def extract_issue_number(branch: str) -> int | None:
    """Parse the paperclip issueNumber from a feature-branch name.

    Convention: feature/GIM-<N>-<slug>. Non-matching branches return None.
    """
    if not branch:
        return None
    match = BRANCH_RE.match(branch)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Bot filter
# ---------------------------------------------------------------------------


def is_bot_author(author: str, bot_authors: list[str]) -> bool:
    """Return True if the sender login should be filtered out.

    Complements the workflow-level `if:` which filters Bot-type senders.
    This Python-level check covers shared-token accounts like `ant013`
    where sender.type is User.
    """
    return author in bot_authors


# ---------------------------------------------------------------------------
# Paperclip API client
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    """Subset of paperclip issue fields this script needs."""

    id: str
    issue_number: int
    assignee_id: str | None
    assignee_name: str | None
    execution_run_id: str | None


class PaperclipClient:
    """Thin httpx wrapper over paperclip REST API."""

    def __init__(self, base_url: str, api_key: str, company_id: str, timeout: float = 30.0):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=timeout),
        )
        self._company_id = company_id

    def get_issue_by_number(self, issue_number: int) -> Issue:
        resp = self._client.get(
            "/api/issues",
            params={"issueNumber": issue_number, "companyId": self._company_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            raise PaperclipError(
                f"Issue with issueNumber={issue_number} not found in company {self._company_id}."
            )
        entry = data[0]
        return Issue(
            id=entry["id"],
            issue_number=entry["issueNumber"],
            assignee_id=entry.get("assigneeId"),
            assignee_name=entry.get("assigneeName"),
            execution_run_id=entry.get("executionRunId"),
        )

    def release_and_reassign(self, issue_id: str, assignee_id: str) -> None:
        """Wake an assignee via release + re-patch (GIM-52/53 proven workaround)."""
        release = self._client.post(f"/api/issues/{issue_id}/release")
        release.raise_for_status()
        patch = self._client.patch(f"/api/issues/{issue_id}", json={"assigneeId": assignee_id})
        patch.raise_for_status()

    def post_comment(self, issue_id: str, body: str) -> None:
        resp = self._client.post(f"/api/issues/{issue_id}/comments", json={"body": body})
        resp.raise_for_status()

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


def _sleep(seconds: float) -> None:
    """Indirection point for patching in tests."""
    time.sleep(seconds)


def release_and_reassign_with_retry(
    client: PaperclipClient,
    issue_id: str,
    assignee_id: str,
) -> None:
    """Call release + reassign with retry on transient failures.

    Retries on HTTP 409 (stale execution lock) and 5xx. Does NOT retry on
    other 4xx — those are deterministic errors. After exhausting retries,
    raises PaperclipError.
    """
    last_exc: Exception | None = None
    for delay in [0, *RETRY_DELAYS_SECONDS]:
        if delay:
            _sleep(delay)
        try:
            client.release_and_reassign(issue_id=issue_id, assignee_id=assignee_id)
            return
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status not in RETRY_STATUS_CODES:
                raise PaperclipError(
                    f"release_and_reassign failed with non-retryable status {status}: {exc.response.text}"
                ) from exc
            last_exc = exc
        except httpx.RequestError as exc:
            last_exc = exc
    raise PaperclipError(
        f"release_and_reassign failed after {len(RETRY_DELAYS_SECONDS) + 1} attempts: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Resolve target
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolveResult:
    """Outcome of resolving a target for a given event.

    status ∈ {"proceed", "deferred", "no_assignee"}.
    """

    status: str
    issue: Issue


def resolve_target_issue_assignee(
    client: PaperclipClient,
    issue_number: int,
) -> ResolveResult:
    """Resolve the target issue's assignee, with active-session pre-check."""
    issue = client.get_issue_by_number(issue_number)
    if issue.assignee_id is None:
        return ResolveResult(status="no_assignee", issue=issue)
    if issue.execution_run_id is not None:
        _sleep(ACTIVE_RUN_RECHECK_DELAY_SECONDS)
        issue = client.get_issue_by_number(issue_number)
        if issue.execution_run_id is not None:
            return ResolveResult(status="deferred", issue=issue)
    return ResolveResult(status="proceed", issue=issue)


# ---------------------------------------------------------------------------
# Dedup marker
# ---------------------------------------------------------------------------


def pr_has_signal_marker(comments: list[dict], trigger: str, sha: str) -> bool:
    """Check if a success marker for this (trigger, sha) already exists.

    Only success markers count — failed and deferred markers intentionally
    don't dedupe so a future retry can succeed.
    """
    success_pattern = f"<!-- paperclip-signal: {trigger} {sha}"
    for c in comments:
        body = c.get("body", "")
        if success_pattern in body:
            return True
    return False


# ---------------------------------------------------------------------------
# Comment builders + GitHub helpers
# ---------------------------------------------------------------------------


def build_success_comment(trigger: str, sha: str, agent_name: str) -> str:
    return (
        f"<!-- paperclip-signal: {trigger} {sha} assignee={agent_name} -->\n"
        f"Woke {agent_name} on {trigger} at {sha}."
    )


def build_deferred_comment(trigger: str, sha: str, execution_run_id: str) -> str:
    return (
        f"<!-- paperclip-signal-deferred: {trigger} {sha} -->\n"
        f"Signal {trigger} received at {sha}, but agent session is actively running "
        f"(executionRunId={execution_run_id}); deferred. Next matching event will retry."
    )


def build_failed_comment(trigger: str, sha: str, error_message: str) -> str:
    return (
        f"<!-- paperclip-signal-failed: {trigger} {sha} -->\n"
        f"⚠ Failed to wake agent on {trigger} at {sha}: {error_message}. "
        f"Operator intervention may be needed."
    )


def build_no_assignee_comment(trigger: str, sha: str) -> str:
    return (
        f"<!-- paperclip-signal-no-assignee: {trigger} {sha} -->\n"
        f"⚠ Signal {trigger} received at {sha} but the linked paperclip issue "
        f"has no assignee. Operator must assign someone manually."
    )


def github_post_pr_comment(repo: str, pr_number: int, body: str, github_token: str) -> None:
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    resp = httpx.post(
        url,
        json={"body": body},
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()


def github_get_pr_comments(repo: str, pr_number: int, github_token: str) -> list[dict]:
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    resp = httpx.get(
        url,
        params={"per_page": 100},
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise PaperclipError(f"Unexpected GitHub API response shape: {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# main() orchestration
# ---------------------------------------------------------------------------


def _resolve_target(rule: Rule, client: PaperclipClient, issue_number: int) -> ResolveResult:
    """Dispatch target to the correct resolver."""
    if rule.target == "issue_assignee":
        return resolve_target_issue_assignee(client, issue_number)
    if ROLE_TARGET_RE.match(rule.target):
        raise NotImplementedError(
            f"Target {rule.target!r} is an extension-point placeholder; "
            f"implementation is scheduled for a followup slice."
        )
    raise ConfigError(f"Unknown target {rule.target!r}.")


def main(
    *,
    event_name: str,
    event_payload: dict,
    config_path: Path,
    paperclip_base_url: str,
    paperclip_api_key: str,
    github_token: str,
    repo: str,
) -> int:
    """Entry point. Returns process exit code."""
    config = load_config(config_path)
    event = parse_event(event_name, event_payload)
    if event is None:
        log.info("Event %s non-actionable; exiting 0.", event_name)
        return 0

    if is_bot_author(event.author, config.bot_authors):
        log.info("Event author %s is in bot_authors; exiting 0.", event.author)
        return 0

    matching_rules = [r for r in config.rules if r.trigger == event.trigger]
    if not matching_rules:
        log.info("No config rule matches trigger %s; exiting 0.", event.trigger)
        return 0

    issue_number = extract_issue_number(event.branch)
    if issue_number is None:
        log.warning("Branch %s does not match feature/GIM-N pattern; exiting 0.", event.branch)
        return 0

    client = PaperclipClient(
        base_url=paperclip_base_url,
        api_key=paperclip_api_key,
        company_id=config.company_id,
    )
    try:
        for rule in matching_rules:
            result = _resolve_target(rule, client, issue_number)

            if result.status == "no_assignee":
                body = build_no_assignee_comment(trigger=event.trigger, sha=event.sha)
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.warning("Issue %s has no assignee; posted warning.", result.issue.id)
                continue

            if result.status == "deferred":
                body = build_deferred_comment(
                    trigger=event.trigger,
                    sha=event.sha,
                    execution_run_id=result.issue.execution_run_id or "",
                )
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.info(
                    "Signal deferred for issue %s (executionRunId=%s).",
                    result.issue.id,
                    result.issue.execution_run_id,
                )
                continue

            # result.status == "proceed"
            existing = github_get_pr_comments(repo, event.pr_number, github_token)
            if pr_has_signal_marker(existing, event.trigger, event.sha):
                log.info("Signal %s at %s already posted; dedup skip.", event.trigger, event.sha)
                continue

            try:
                release_and_reassign_with_retry(
                    client=client,
                    issue_id=result.issue.id,
                    assignee_id=result.issue.assignee_id or "",
                )
                body = build_success_comment(
                    trigger=event.trigger,
                    sha=event.sha,
                    agent_name=result.issue.assignee_name or "unknown",
                )
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.info(
                    "Woke %s on %s at %s.",
                    result.issue.assignee_name,
                    event.trigger,
                    event.sha,
                )
            except PaperclipError as exc:
                body = build_failed_comment(
                    trigger=event.trigger,
                    sha=event.sha,
                    error_message=str(exc),
                )
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.error("Paperclip signal failed: %s", exc)
                return 1
    finally:
        client.close()

    return 0


def _cli() -> int:
    """CLI entry used by the GitHub Action step."""
    import json as _json
    import os as _os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    event_name = _os.environ["EVENT_NAME"]
    event_payload = _json.loads(_os.environ["EVENT_JSON"])
    config_path = Path(_os.environ.get("CONFIG_PATH", ".github/paperclip-signals.yml"))
    return main(
        event_name=event_name,
        event_payload=event_payload,
        config_path=config_path,
        paperclip_base_url=_os.environ["PAPERCLIP_BASE_URL"],
        paperclip_api_key=_os.environ["PAPERCLIP_API_KEY"],
        github_token=_os.environ["GITHUB_TOKEN"],
        repo=_os.environ["REPO"],
    )


if __name__ == "__main__":
    raise SystemExit(_cli())
