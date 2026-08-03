#!/usr/bin/env python3
"""Deterministic UAudit delivery contract (stdlib only).

The helper owns validation, aggregation, rendering, delivery receipts, and the
daily cursor compare-and-set.  It intentionally performs no network calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}-[1-9][0-9]*$")
ROUTINE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
SEVERITIES = ("Critical", "Block", "Important", "Observation")
SEVERITY_KEYS = {
    "Critical": "critical",
    "Block": "block",
    "Important": "important",
    "Observation": "observation",
}
SEVERITY_RANK = {severity: index for index, severity in enumerate(SEVERITIES)}
SEVERITY_RU = {
    "Critical": "Критическое",
    "Block": "Блокирующее",
    "Important": "Важное",
    "Observation": "Наблюдение",
}
INPUT_NAMES = {
    "pr": ("pr.json", "pr.diff"),
    "daily_delta": ("profile.json", "commits.tsv", "files.tsv", "diff.patch"),
}
BASE_STAGES = {
    ("pr", "ios"): (
        ("code", "uaudit-swift-audit-specialist", "code.findings.json"),
        ("bug", "uaudit-bug-hunter", "bug.findings.json"),
        ("security", "uaudit-security-auditor", "security.findings.json"),
        ("crypto", "uaudit-blockchain-auditor", "crypto.findings.json"),
    ),
    ("pr", "android"): (
        ("code", "uaudit-kotlin-audit-specialist", "code.findings.json"),
        ("bug", "uaudit-bug-hunter", "bug.findings.json"),
        ("security", "uaudit-security-auditor", "security.findings.json"),
        ("crypto", "uaudit-blockchain-auditor", "crypto.findings.json"),
    ),
    ("daily_delta", "ios"): (
        ("code", "UWISwiftAuditor", "code.findings.json"),
        ("security", "UWISecurityAuditor", "security.findings.json"),
        ("crypto", "UWICryptoAuditor", "crypto.findings.json"),
        ("infra", "UWIInfraEngineer", "infra.findings.json"),
        ("qa_verify", "UWIQAEngineer", "qa-verify.findings.json"),
    ),
    ("daily_delta", "android"): (
        ("code", "UWAKotlinAuditor", "code.findings.json"),
        ("security", "UWASecurityAuditor", "security.findings.json"),
        ("crypto", "UWACryptoAuditor", "crypto.findings.json"),
        ("infra", "UWAInfraEngineer", "infra.findings.json"),
        ("qa_verify", "UWAQAEngineer", "qa-verify.findings.json"),
    ),
}
RESEARCH_STAGE = {
    "ios": ("research_context", "UWIResearchAgent", "research-context.findings.json"),
    "android": ("research_context", "UWAResearchAgent", "research-context.findings.json"),
}
PAYLOAD_ARTIFACTS = (
    "canonical-findings.json",
    "telegram-summary.txt",
    "audit.md",
    "audit-final.md",
    "delivery-summary.json",
)
TERMINAL_MARKERS = (
    "status/telegram.done",
    "status/cursor.done",
    "status/workflow.done",
)
INSTALL_SCHEMA = "uaudit-helper-install/v1"
INSTALL_MANIFEST = "uaudit_delivery_contract.manifest.json"


class ContractError(RuntimeError):
    """Fail-closed contract violation."""


def _fail(message: str) -> None:
    raise ContractError(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _expect_object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{where} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    required: Iterable[str],
    optional: Iterable[str] = (),
    *,
    where: str,
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    keys = set(value)
    missing = sorted(required_set - keys)
    unknown = sorted(keys - allowed)
    if missing:
        _fail(f"{where} missing fields: {', '.join(missing)}")
    if unknown:
        _fail(f"{where} has unknown fields: {', '.join(unknown)}")


def _bounded_string(
    value: Any,
    where: str,
    *,
    minimum: int = 1,
    maximum: int = 4096,
    controls: bool = False,
) -> str:
    if not isinstance(value, str):
        _fail(f"{where} must be a string")
    if len(value) < minimum or len(value) > maximum:
        _fail(f"{where} length is outside {minimum}..{maximum}")
    if not controls and CONTROL_RE.search(value):
        _fail(f"{where} contains control characters")
    return value


def _iso_utc(value: Any, where: str) -> str:
    text = _bounded_string(value, where, maximum=64)
    if not text.endswith("Z"):
        _fail(f"{where} must be UTC with a Z suffix")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{where} is not valid ISO-8601") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail(f"{where} must be UTC")
    return text


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(value: Any, where: str, *, git: bool = False) -> str:
    text = _bounded_string(value, where, maximum=64)
    pattern = GIT_SHA_RE if git else SHA256_RE
    if not pattern.fullmatch(text):
        _fail(f"{where} must be lowercase {'40' if git else '64'}-hex")
    return text


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


def _normalize_key(value: str) -> str:
    return _normalize_space(unicodedata.normalize("NFC", value)).casefold()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_symlink():
        _fail(f"symbolic links are forbidden for contract files: {path.name}")
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ContractError(f"cannot read required file {path.name}") from exc
    return digest.hexdigest()


def _read_bytes(path: Path, *, maximum: int = 16 * 1024 * 1024) -> bytes:
    if path.is_symlink():
        _fail(f"symbolic links are forbidden for contract files: {path.name}")
    try:
        stat = path.stat()
    except OSError as exc:
        raise ContractError(f"missing file: {path}") from exc
    if not path.is_file() or stat.st_size > maximum:
        _fail(f"invalid or oversized file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read file: {path}") from exc


def _load_json(path: Path, *, maximum: int = 2 * 1024 * 1024) -> Any:
    raw = _read_bytes(path, maximum=maximum)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"malformed JSON: {path}") from exc


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, value: Any) -> bytes:
    raw = _canonical_bytes(value)
    _atomic_write(path, raw)
    return raw


def _create_or_match(path: Path, value: Any, where: str) -> None:
    raw = _canonical_bytes(value)
    if path.exists():
        if _read_bytes(path) != raw:
            _fail(f"conflicting immutable {where}")
        return
    _atomic_write(path, raw)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ContractError(f"cannot remove stale artifact {path}") from exc


def _validate_issue(value: Any, where: str = "issue_identifier") -> str:
    text = _bounded_string(value, where, maximum=64)
    if not ISSUE_RE.fullmatch(text):
        _fail(f"{where} has invalid format")
    return text


def _validate_platform(value: Any) -> str:
    if value not in ("ios", "android"):
        _fail("platform must be ios or android")
    return value


def _validate_kind(value: Any) -> str:
    if value not in ("pr", "daily_delta"):
        _fail("audit_kind must be pr or daily_delta")
    return value


def _validate_source_ref(value: Any, audit_kind: str, where: str = "source_ref") -> dict[str, Any]:
    ref = _expect_object(value, where)
    if audit_kind == "pr":
        _exact_keys(ref, ("repo", "pr_url", "base_sha", "head_sha"), where=where)
        repo = _bounded_string(ref["repo"], f"{where}.repo", maximum=200)
        if repo.strip() != repo:
            _fail(f"{where}.repo must be trimmed")
        pr_url = _bounded_string(ref["pr_url"], f"{where}.pr_url", maximum=500)
        parsed = urlparse(pr_url)
        if parsed.scheme != "https" or not parsed.netloc or not re.search(r"/pull/[1-9][0-9]*/?$", parsed.path):
            _fail(f"{where}.pr_url must be a validated HTTPS pull request URL")
        base_sha = _sha(ref["base_sha"], f"{where}.base_sha", git=True)
        head_sha = _sha(ref["head_sha"], f"{where}.head_sha", git=True)
        return {"repo": repo, "pr_url": pr_url, "base_sha": base_sha, "head_sha": head_sha}
    _exact_keys(ref, ("routine_id", "branch", "from_sha", "to_sha"), where=where)
    routine = _bounded_string(ref["routine_id"], f"{where}.routine_id", maximum=128)
    if not ROUTINE_RE.fullmatch(routine):
        _fail(f"{where}.routine_id has invalid format")
    branch = _bounded_string(ref["branch"], f"{where}.branch", maximum=200)
    if branch.strip() != branch or branch.startswith("-") or ".." in branch:
        _fail(f"{where}.branch is not safe")
    from_sha = _sha(ref["from_sha"], f"{where}.from_sha", git=True)
    to_sha = _sha(ref["to_sha"], f"{where}.to_sha", git=True)
    if from_sha == to_sha:
        _fail(f"{where} daily range must be non-empty")
    return {"routine_id": routine, "branch": branch, "from_sha": from_sha, "to_sha": to_sha}


def _validate_run_binding(value: Any, where: str = "run_binding") -> dict[str, Any]:
    binding = _expect_object(value, where)
    _exact_keys(
        binding,
        ("issue_identifier", "platform", "audit_kind", "generation_created_at", "source_ref", "input_digests"),
        where=where,
    )
    issue = _validate_issue(binding["issue_identifier"], f"{where}.issue_identifier")
    platform = _validate_platform(binding["platform"])
    kind = _validate_kind(binding["audit_kind"])
    created_at = _iso_utc(binding["generation_created_at"], f"{where}.generation_created_at")
    source_ref = _validate_source_ref(binding["source_ref"], kind, f"{where}.source_ref")
    digests = _expect_object(binding["input_digests"], f"{where}.input_digests")
    names = INPUT_NAMES[kind]
    _exact_keys(digests, names, where=f"{where}.input_digests")
    normalized_digests = {name: _sha(digests[name], f"{where}.input_digests.{name}") for name in names}
    return {
        "issue_identifier": issue,
        "platform": platform,
        "audit_kind": kind,
        "generation_created_at": created_at,
        "source_ref": source_ref,
        "input_digests": normalized_digests,
    }


def _load_context(run_dir: Path) -> tuple[dict[str, Any], bytes, str]:
    path = run_dir / "run-context.json"
    value = _validate_run_binding(_load_json(path), "run-context.json")
    raw = _canonical_bytes(value)
    if _read_bytes(path) != raw:
        _fail("run-context.json is not canonical")
    for name, expected in value["input_digests"].items():
        if _sha256_path(run_dir / name) != expected:
            _fail(f"run input digest mismatch: {name}")
    return value, raw, _sha256_bytes(raw)


def _validate_intake(value: Any) -> dict[str, Any]:
    intake = _expect_object(value, "intake")
    _exact_keys(
        intake,
        ("schema_version", "issue_identifier", "platform", "audit_kind", "source_ref"),
        ("generation_created_at",),
        where="intake",
    )
    if intake["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported intake schema_version")
    issue = _validate_issue(intake["issue_identifier"])
    platform = _validate_platform(intake["platform"])
    kind = _validate_kind(intake["audit_kind"])
    created_at = None
    if "generation_created_at" in intake:
        created_at = _iso_utc(intake["generation_created_at"], "intake.generation_created_at")
    return {
        "schema_version": SCHEMA_VERSION,
        "issue_identifier": issue,
        "platform": platform,
        "audit_kind": kind,
        "source_ref": _validate_source_ref(intake["source_ref"], kind),
        "generation_created_at": created_at,
    }


def _lock_metadata(
    value: Any,
    *,
    binding: Mapping[str, Any],
    binding_sha: str | None,
    allow_null_digest: bool,
) -> dict[str, Any]:
    metadata = _expect_object(value, "lock metadata")
    _exact_keys(
        metadata,
        ("schema_version", "issue_identifier", "routine_id", "from_sha", "to_sha", "run_binding_sha256"),
        where="lock metadata",
    )
    if metadata["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported lock metadata schema_version")
    ref = binding["source_ref"]
    expected = {
        "schema_version": SCHEMA_VERSION,
        "issue_identifier": binding["issue_identifier"],
        "routine_id": ref["routine_id"],
        "from_sha": ref["from_sha"],
        "to_sha": ref["to_sha"],
    }
    for field, expected_value in expected.items():
        if metadata[field] != expected_value:
            _fail(f"lock metadata mismatch: {field}")
    digest = metadata["run_binding_sha256"]
    if digest is None and allow_null_digest:
        pass
    elif not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        _fail("lock metadata has invalid run_binding_sha256")
    if binding_sha is not None and digest not in (None, binding_sha):
        _fail("lock metadata belongs to a different generation")
    return {**expected, "run_binding_sha256": digest}


def bind_context(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    intake_path = args.intake.resolve()
    if intake_path.parent != run_dir:
        _fail("intake must be inside run directory")
    intake = _validate_intake(_load_json(intake_path))
    if intake["audit_kind"] == "daily_delta" and args.lock_dir is None:
        _fail("daily bind-context requires --lock-dir")
    if intake["audit_kind"] == "pr" and args.lock_dir is not None:
        _fail("PR bind-context forbids --lock-dir")
    digests = {name: _sha256_path(run_dir / name) for name in INPUT_NAMES[intake["audit_kind"]]}
    context_path = run_dir / "run-context.json"
    pending_lock_metadata: tuple[Path, dict[str, Any]] | None = None
    if context_path.exists():
        existing, raw, binding_sha = _load_context(run_dir)
        created_at = intake["generation_created_at"] or existing["generation_created_at"]
        expected = {
            "issue_identifier": intake["issue_identifier"],
            "platform": intake["platform"],
            "audit_kind": intake["audit_kind"],
            "generation_created_at": created_at,
            "source_ref": intake["source_ref"],
            "input_digests": digests,
        }
        if existing != expected:
            _fail("immutable run-context.json conflicts with authoritative intake")
    else:
        for relative in ("delivery-summary.json", "delivery-result.json", "status/handoff.done"):
            if (run_dir / relative).exists():
                _fail(f"cannot bind context after {relative}")
        context = {
            "issue_identifier": intake["issue_identifier"],
            "platform": intake["platform"],
            "audit_kind": intake["audit_kind"],
            "generation_created_at": intake["generation_created_at"] or _now_utc(),
            "source_ref": intake["source_ref"],
            "input_digests": digests,
        }
        raw = _canonical_bytes(context)
        existing = context
        binding_sha = _sha256_bytes(raw)
        if existing["audit_kind"] == "daily_delta":
            lock_dir = args.lock_dir.resolve()
            if not lock_dir.is_dir():
                _fail("daily routine lock is not held")
            metadata_path = lock_dir / "metadata.json"
            metadata = _lock_metadata(
                _load_json(metadata_path),
                binding=existing,
                binding_sha=binding_sha,
                allow_null_digest=True,
            )
            pending_lock_metadata = (metadata_path, metadata)
        _atomic_write(context_path, raw)
    if existing["audit_kind"] == "daily_delta":
        lock_dir = args.lock_dir.resolve()
        if not lock_dir.is_dir():
            _fail("daily routine lock is not held")
        metadata_path = lock_dir / "metadata.json"
        if pending_lock_metadata is not None:
            metadata_path, metadata = pending_lock_metadata
        else:
            metadata = _lock_metadata(
                _load_json(metadata_path),
                binding=existing,
                binding_sha=binding_sha,
                allow_null_digest=True,
            )
        if metadata["run_binding_sha256"] is None:
            metadata["run_binding_sha256"] = binding_sha
            _atomic_json(metadata_path, metadata)
    return {"status": "bound", "run_binding_sha256": binding_sha}


def _validate_relative_file(value: Any, where: str) -> str:
    text = _bounded_string(value, where, maximum=500)
    if "\\" in text or text != text.strip() or "//" in text:
        _fail(f"{where} must be a normalized POSIX relative path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        _fail(f"{where} must be a normalized POSIX relative path")
    if str(path) != text:
        _fail(f"{where} must be a normalized POSIX relative path")
    return text


def _russian_prose(value: Any, where: str, maximum: int) -> str:
    text = _bounded_string(value, where, maximum=maximum)
    if text != text.strip():
        _fail(f"{where} must be trimmed")
    if not CYRILLIC_RE.search(text):
        _fail(f"{where} must contain Russian report-facing prose")
    return text


def _validate_finding(value: Any, where: str) -> dict[str, Any]:
    finding = _expect_object(value, where)
    _exact_keys(
        finding,
        (
            "severity",
            "file",
            "line",
            "area",
            "title",
            "evidence",
            "impact",
            "recommendation",
            "needs_runtime_verification",
        ),
        where=where,
    )
    severity = finding["severity"]
    if severity not in SEVERITIES:
        _fail(f"{where}.severity is unsupported")
    file_value = finding["file"]
    line_value = finding["line"]
    area_value = finding["area"]
    has_file = file_value is not None or line_value is not None
    has_area = area_value is not None
    if has_file == has_area:
        _fail(f"{where} must use exactly one location form")
    if has_file:
        file_text = _validate_relative_file(file_value, f"{where}.file")
        if not _is_int(line_value) or line_value <= 0:
            _fail(f"{where}.line must be a positive integer")
        area_text = None
    else:
        if file_value is not None or line_value is not None:
            _fail(f"{where} area location requires null file and line")
        file_text = None
        line_value = None
        area_text = _bounded_string(area_value, f"{where}.area", maximum=300)
        if area_text != area_text.strip():
            _fail(f"{where}.area must be trimmed")
    title = _russian_prose(finding["title"], f"{where}.title", 1000)
    if len(_normalize_space(title)) > 160:
        _fail(f"{where}.title exceeds 160 Unicode code points after normalization")
    evidence = _russian_prose(finding["evidence"], f"{where}.evidence", 3000)
    impact = _russian_prose(finding["impact"], f"{where}.impact", 3000)
    recommendation = _russian_prose(finding["recommendation"], f"{where}.recommendation", 3000)
    if len(_normalize_space(f"{evidence} {impact} {recommendation}").split()) > 120:
        _fail(f"{where} evidence/impact/recommendation exceeds 120 words")
    runtime = finding["needs_runtime_verification"]
    if not isinstance(runtime, bool):
        _fail(f"{where}.needs_runtime_verification must be boolean")
    return {
        "severity": severity,
        "file": file_text,
        "line": line_value,
        "area": area_text,
        "title": title,
        "evidence": evidence,
        "impact": impact,
        "recommendation": recommendation,
        "needs_runtime_verification": runtime,
    }


def _validate_limitation(value: Any, where: str) -> dict[str, Any]:
    limitation = _expect_object(value, where)
    _exact_keys(limitation, ("text", "material"), where=where)
    text = _russian_prose(limitation["text"], f"{where}.text", 240)
    if not isinstance(limitation["material"], bool):
        _fail(f"{where}.material must be boolean")
    return {"text": text, "material": limitation["material"]}


def _stage_definitions(binding: Mapping[str, Any], research_required: bool = False) -> tuple[tuple[str, str, str], ...]:
    definitions = list(BASE_STAGES[(binding["audit_kind"], binding["platform"])])
    if binding["audit_kind"] == "daily_delta" and research_required:
        definitions.append(RESEARCH_STAGE[binding["platform"]])
    return tuple(definitions)


def _stage_definition(binding: Mapping[str, Any], stage: str) -> tuple[str, str, str] | None:
    definitions = list(_stage_definitions(binding, True))
    return next((item for item in definitions if item[0] == stage), None)


def _validate_sidecar(value: Any, binding: Mapping[str, Any], where: str) -> dict[str, Any]:
    sidecar = _expect_object(value, where)
    _exact_keys(
        sidecar,
        ("schema_version", "run_binding", "stage", "source_agent", "audit_status", "findings", "limitations", "block_reason"),
        where=where,
    )
    if sidecar["schema_version"] != SCHEMA_VERSION:
        _fail(f"{where} has unsupported schema_version")
    bound = _validate_run_binding(sidecar["run_binding"], f"{where}.run_binding")
    if bound != binding:
        _fail(f"{where} run_binding mismatch")
    stage = _bounded_string(sidecar["stage"], f"{where}.stage", maximum=64)
    definition = _stage_definition(binding, stage)
    if definition is None:
        _fail(f"{where} has unauthorized stage")
    source = _bounded_string(sidecar["source_agent"], f"{where}.source_agent", maximum=128)
    if source != definition[1]:
        _fail(f"{where} stage/source_agent pair is unauthorized")
    status = sidecar["audit_status"]
    if status not in ("complete", "partial", "blocked"):
        _fail(f"{where}.audit_status is unsupported")
    if not isinstance(sidecar["findings"], list):
        _fail(f"{where}.findings must be an array")
    findings = [_validate_finding(item, f"{where}.findings[{index}]") for index, item in enumerate(sidecar["findings"])]
    if not isinstance(sidecar["limitations"], list):
        _fail(f"{where}.limitations must be an array")
    limitations = [
        _validate_limitation(item, f"{where}.limitations[{index}]")
        for index, item in enumerate(sidecar["limitations"])
    ]
    material = any(item["material"] for item in limitations)
    block_reason = sidecar["block_reason"]
    if status == "complete":
        if material or block_reason is not None:
            _fail(f"{where} complete stage cannot have material limitation or block_reason")
    elif status == "partial":
        if not material or block_reason is not None:
            _fail(f"{where} partial stage requires material limitation and null block_reason")
    else:
        block_reason = _russian_prose(block_reason, f"{where}.block_reason", 500)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_binding": bound,
        "stage": stage,
        "source_agent": source,
        "audit_status": status,
        "findings": findings,
        "limitations": limitations,
        "block_reason": block_reason,
    }


def _marker_for_stage(sidecar: Mapping[str, Any], sidecar_path: Path, raw: bytes, binding_sha: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": sidecar["stage"],
        "source_agent": sidecar["source_agent"],
        "sidecar_file": sidecar_path.name,
        "sidecar_sha256": _sha256_bytes(raw),
        "run_binding_sha256": binding_sha,
    }


def _validate_stage_marker(value: Any, expected: Mapping[str, Any], where: str) -> None:
    marker = _expect_object(value, where)
    _exact_keys(marker, expected.keys(), where=where)
    if marker != expected:
        _fail(f"{where} does not match sidecar generation")


def validate_stage(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    binding, _, binding_sha = _load_context(run_dir)
    sidecar_path = args.sidecar.resolve()
    if sidecar_path.parent != run_dir:
        _fail("sidecar must be directly inside run directory")
    sidecar = _validate_sidecar(_load_json(sidecar_path), binding, sidecar_path.name)
    definition = _stage_definition(binding, sidecar["stage"])
    assert definition is not None
    if sidecar_path.name != definition[2]:
        _fail("sidecar filename does not match its authorized stage")
    raw = _canonical_bytes(sidecar)
    if _read_bytes(sidecar_path) != raw:
        _atomic_write(sidecar_path, raw)
    marker = _marker_for_stage(sidecar, sidecar_path, raw, binding_sha)
    marker_path = run_dir / "status" / f"{sidecar['stage']}.done.json"
    _create_or_match(marker_path, marker, "stage marker")
    return {"status": "validated", "stage": sidecar["stage"], "sidecar_sha256": marker["sidecar_sha256"]}


def _load_validated_stage(
    run_dir: Path,
    binding: Mapping[str, Any],
    binding_sha: str,
    definition: tuple[str, str, str],
) -> dict[str, Any]:
    stage, _, filename = definition
    path = run_dir / filename
    sidecar = _validate_sidecar(_load_json(path), binding, filename)
    raw = _canonical_bytes(sidecar)
    if _read_bytes(path) != raw:
        _fail(f"{filename} is not canonical")
    expected = _marker_for_stage(sidecar, path, raw, binding_sha)
    marker_path = run_dir / "status" / f"{stage}.done.json"
    _validate_stage_marker(_load_json(marker_path), expected, marker_path.name)
    return sidecar


def _finding_location(finding: Mapping[str, Any]) -> tuple[str, str]:
    if finding["file"] is not None:
        display = f"{finding['file']}:{finding['line']}"
        return display, display
    display = finding["area"]
    return display, f"area:{_normalize_key(display)}"


def _canonicalize(
    binding: Mapping[str, Any],
    sidecars: Sequence[Mapping[str, Any]],
    definitions: Sequence[tuple[str, str, str]],
) -> tuple[dict[str, Any], str]:
    stage_rank = {definition[0]: index for index, definition in enumerate(definitions)}
    finding_groups: dict[tuple[str, str], list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
    limitation_groups: dict[tuple[str, bool], list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
    for sidecar in sidecars:
        for finding in sidecar["findings"]:
            _, location_key = _finding_location(finding)
            key = (location_key, _normalize_key(finding["title"]))
            finding_groups.setdefault(key, []).append((sidecar, finding))
        for limitation in sidecar["limitations"]:
            key = (_normalize_key(limitation["text"]), limitation["material"])
            limitation_groups.setdefault(key, []).append((sidecar, limitation))

    canonical_findings: list[dict[str, Any]] = []
    for (location_key, normalized_title), candidates in finding_groups.items():
        candidates.sort(
            key=lambda item: (
                SEVERITY_RANK[item[1]["severity"]],
                stage_rank[item[0]["stage"]],
                item[0]["source_agent"],
                _canonical_bytes(item[1]),
            )
        )
        representative = candidates[0][1]
        canonical_findings.append(
            {
                "dedup_key": {"location": location_key, "title": normalized_title},
                "severity": representative["severity"],
                "file": representative["file"],
                "line": representative["line"],
                "area": representative["area"],
                "title": representative["title"],
                "evidence": representative["evidence"],
                "impact": representative["impact"],
                "recommendation": representative["recommendation"],
                "source_agents": sorted({candidate[0]["source_agent"] for candidate in candidates}),
                "stages": sorted({candidate[0]["stage"] for candidate in candidates}),
                "needs_runtime_verification": any(candidate[1]["needs_runtime_verification"] for candidate in candidates),
            }
        )
    canonical_findings.sort(
        key=lambda item: (
            SEVERITY_RANK[item["severity"]],
            item["dedup_key"]["location"],
            item["dedup_key"]["title"],
        )
    )

    canonical_limitations: list[dict[str, Any]] = []
    for _, candidates in sorted(limitation_groups.items(), key=lambda item: item[0]):
        candidates.sort(
            key=lambda item: (
                stage_rank[item[0]["stage"]],
                item[0]["source_agent"],
                _canonical_bytes(item[1]),
            )
        )
        representative = candidates[0][1]
        canonical_limitations.append(
            {
                "text": representative["text"],
                "material": representative["material"],
                "source_agents": sorted({candidate[0]["source_agent"] for candidate in candidates}),
                "stages": sorted({candidate[0]["stage"] for candidate in candidates}),
            }
        )
    status = "partial" if any(
        sidecar["audit_status"] == "partial" or any(item["material"] for item in sidecar["limitations"])
        for sidecar in sidecars
    ) else "complete"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_binding": dict(binding),
        "audit_status": status,
        "findings": canonical_findings,
        "limitations": canonical_limitations,
    }, status


def _counts(findings: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    result = {key: 0 for key in ("critical", "block", "important", "observation")}
    for finding in findings:
        result[SEVERITY_KEYS[finding["severity"]]] += 1
    return result


def _verdict(status: str, counts: Mapping[str, int]) -> str:
    if counts["critical"] or counts["block"]:
        return "block"
    if counts["important"]:
        return "request_changes"
    if status == "partial":
        return "inconclusive"
    return "approve"


def _verdict_ru(verdict: str) -> str:
    return {
        "block": "блокирует принятие",
        "request_changes": "требуются изменения",
        "inconclusive": "вердикт не вынесен: проверка неполная",
        "approve": "можно принимать",
    }[verdict]


def _platform_ru(platform: str) -> str:
    return "iOS" if platform == "ios" else "Android"


def _pr_number(source_ref: Mapping[str, Any]) -> str:
    match = re.search(r"/pull/([1-9][0-9]*)/?$", source_ref["pr_url"])
    if not match:
        _fail("validated PR URL no longer contains a PR number")
    return match.group(1)


def _render_telegram(binding: Mapping[str, Any], status: str, counts: Mapping[str, int], verdict: str) -> bytes:
    platform = _platform_ru(binding["platform"])
    ref = binding["source_ref"]
    state = "завершён" if status == "complete" else "выполнен частично"
    if binding["audit_kind"] == "pr":
        first = f"Аудит {platform} PR #{_pr_number(ref)} {state}"
    else:
        first = f"Аудит {platform} {ref['branch']} {ref['from_sha'][:7]}..{ref['to_sha'][:7]} {state}"
    total = sum(counts.values())
    lines = [
        first,
        f"Найдено замечаний: {total}",
        (
            f"Критические: {counts['critical']} · Блокирующие: {counts['block']} · "
            f"Важные: {counts['important']} · Наблюдения: {counts['observation']}"
        ),
    ]
    if verdict == "inconclusive":
        lines.append("Вердикт не вынесен: проверка неполная")
    else:
        lines.append(f"Вердикт: {_verdict_ru(verdict)}")
    if status == "partial":
        lines.append("Покрытие неполное — ограничения указаны в отчёте")
    elif total == 0:
        lines.append("Итоговый отчёт не формировался")
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    if len(raw) >= 900:
        _fail("telegram summary must be shorter than 900 UTF-8 bytes")
    return raw


def _diff_counts(path: Path) -> tuple[int, int, int]:
    if path.is_symlink() or not path.is_file():
        _fail(f"invalid diff file: {path}")
    files = additions = deletions = 0
    try:
        with path.open("rb") as stream:
            for line in stream:
                if line.startswith(b"diff --git "):
                    files += 1
                elif line.startswith(b"+") and not line.startswith(b"+++"):
                    additions += 1
                elif line.startswith(b"-") and not line.startswith(b"---"):
                    deletions += 1
    except OSError as exc:
        raise ContractError(f"cannot read diff file: {path}") from exc
    return files, additions, deletions


def _render_report(
    run_dir: Path,
    canonical: Mapping[str, Any],
    counts: Mapping[str, int],
    verdict: str,
    sidecars: Sequence[Mapping[str, Any]],
) -> bytes:
    binding = canonical["run_binding"]
    ref = binding["source_ref"]
    platform = _platform_ru(binding["platform"])
    total = len(canonical["findings"])
    if binding["audit_kind"] == "pr":
        lines = [
            f"# Аудит {platform} PR #{_pr_number(ref)}",
            "",
            f"- Найдено замечаний: {total}",
            f"- Вердикт: {_verdict_ru(verdict)}",
        ]
    else:
        lines = [
            f"# Аудит изменений {platform} {ref['branch']}",
            "",
            f"- Диапазон: `{ref['from_sha'][:7]}..{ref['to_sha'][:7]}`",
            f"- Найдено замечаний: {total}",
            f"- Вердикт: {_verdict_ru(verdict)}",
        ]
    if canonical["audit_status"] == "partial":
        lines.extend(["", "> Проверка выполнена частично"])
    lines.extend(["", "## Замечания", ""])
    if canonical["findings"]:
        for index, finding in enumerate(canonical["findings"], start=1):
            location, _ = _finding_location(finding)
            lines.extend(
                [
                    f"### {index}. {SEVERITY_RU[finding['severity']]} — {finding['title']}",
                    "",
                    f"`{location}`" if finding["file"] is not None else f"Область: {location}",
                    "",
                    f"{finding['evidence']} {finding['impact']}",
                    "",
                    f"**Что сделать:** {finding['recommendation']}",
                ]
            )
            if finding["needs_runtime_verification"]:
                lines.extend(["", "Требуется проверка во время выполнения."])
            lines.append("")
    else:
        lines.extend(["В проверенной части замечаний не найдено.", ""])
    material = [item for item in canonical["limitations"] if item["material"]]
    if material:
        lines.extend(["## Ограничения", ""])
        lines.extend(f"- {item['text']}" for item in material)
        lines.append("")
    diff_name = "pr.diff" if binding["audit_kind"] == "pr" else "diff.patch"
    files, additions, deletions = _diff_counts(run_dir / diff_name)
    source_trace = ", ".join(f"{item['stage']} ({item['source_agent']})" for item in sidecars)
    lines.extend(["## Техническая информация", "", f"- Issue: `{binding['issue_identifier']}`", f"- Платформа: `{binding['platform']}`"])
    if binding["audit_kind"] == "pr":
        lines.extend(
            [
                f"- Репозиторий: `{ref['repo']}`",
                f"- PR: {ref['pr_url']}",
                f"- Base SHA: `{ref['base_sha']}`",
                f"- Head SHA: `{ref['head_sha']}`",
            ]
        )
    else:
        lines.extend(
            [
                f"- Routine: `{ref['routine_id']}`",
                f"- Ветка: `{ref['branch']}`",
                f"- FROM SHA: `{ref['from_sha']}`",
                f"- TO SHA: `{ref['to_sha']}`",
            ]
        )
    lines.extend(
        [
            f"- Время формирования: `{binding['generation_created_at']}`",
            f"- Объём diff: файлов — {files}, добавлений — {additions}, удалений — {deletions}",
            f"- Источники проверки: {source_trace}",
            "- Методика: structured stage outputs, строгая привязка к diff и каноническая дедупликация.",
        ]
    )
    if binding["platform"] == "android":
        lines.append("- Варианты Android: влияние оценено в доступном diff scope.")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _validate_canonical(value: Any, binding: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _expect_object(value, "canonical-findings.json")
    _exact_keys(canonical, ("schema_version", "run_binding", "audit_status", "findings", "limitations"), where="canonical-findings.json")
    if canonical["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported canonical schema_version")
    if _validate_run_binding(canonical["run_binding"], "canonical.run_binding") != binding:
        _fail("canonical run binding mismatch")
    if canonical["audit_status"] not in ("complete", "partial"):
        _fail("canonical audit_status is invalid")
    if not isinstance(canonical["findings"], list) or not isinstance(canonical["limitations"], list):
        _fail("canonical findings and limitations must be arrays")
    # Re-aggregation validation is intentionally structural and exact: the
    # generation path is the only producer of these additional canonical fields.
    expected_finding_keys = {
        "dedup_key", "severity", "file", "line", "area", "title", "evidence", "impact",
        "recommendation", "source_agents", "stages", "needs_runtime_verification",
    }
    for index, finding in enumerate(canonical["findings"]):
        item = _expect_object(finding, f"canonical.findings[{index}]")
        _exact_keys(item, expected_finding_keys, where=f"canonical.findings[{index}]")
        base = {key: item[key] for key in ("severity", "file", "line", "area", "title", "evidence", "impact", "recommendation", "needs_runtime_verification")}
        validated = _validate_finding(base, f"canonical.findings[{index}]")
        dedup = _expect_object(item["dedup_key"], f"canonical.findings[{index}].dedup_key")
        _exact_keys(dedup, ("location", "title"), where=f"canonical.findings[{index}].dedup_key")
        _, expected_location = _finding_location(validated)
        if dedup != {"location": expected_location, "title": _normalize_key(validated["title"])}:
            _fail("canonical dedup key mismatch")
        for array_name in ("source_agents", "stages"):
            values = item[array_name]
            if not isinstance(values, list) or not values or values != sorted(set(values)) or not all(isinstance(entry, str) for entry in values):
                _fail(f"canonical {array_name} must be a sorted unique non-empty string array")
    expected_limitation_keys = {"text", "material", "source_agents", "stages"}
    for index, limitation in enumerate(canonical["limitations"]):
        item = _expect_object(limitation, f"canonical.limitations[{index}]")
        _exact_keys(item, expected_limitation_keys, where=f"canonical.limitations[{index}]")
        _validate_limitation({"text": item["text"], "material": item["material"]}, f"canonical.limitations[{index}]")
        for array_name in ("source_agents", "stages"):
            values = item[array_name]
            if not isinstance(values, list) or not values or values != sorted(set(values)) or not all(isinstance(entry, str) for entry in values):
                _fail(f"canonical limitation {array_name} is invalid")
    return canonical


def _validate_summary(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    binding, _, binding_sha = _load_context(run_dir)
    summary_path = run_dir / "delivery-summary.json"
    summary = _expect_object(_load_json(summary_path), "delivery-summary.json")
    _exact_keys(
        summary,
        (
            "schema_version", "issue_identifier", "platform", "audit_kind", "audit_status",
            "run_binding_sha256", "source_ref", "finding_count", "severity_counts", "verdict",
            "material_limitations", "telegram_text", "findings", "report", "created_at",
        ),
        where="delivery-summary.json",
    )
    if summary["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported summary schema_version")
    for field in ("issue_identifier", "platform", "audit_kind", "source_ref"):
        binding_field = "source_ref" if field == "source_ref" else field
        if summary[field] != binding[binding_field]:
            _fail(f"summary binding mismatch: {field}")
    if summary["audit_status"] not in ("complete", "partial"):
        _fail("summary audit_status is invalid")
    if summary["run_binding_sha256"] != binding_sha:
        _fail("summary run_binding_sha256 mismatch")
    if summary["created_at"] != binding["generation_created_at"]:
        _fail("summary created_at mismatch")
    canonical_ref = _expect_object(summary["findings"], "summary.findings")
    _exact_keys(canonical_ref, ("file", "sha256"), where="summary.findings")
    if canonical_ref["file"] != "canonical-findings.json":
        _fail("summary findings filename is fixed")
    canonical_path = run_dir / canonical_ref["file"]
    _sha(canonical_ref["sha256"], "summary.findings.sha256")
    if _sha256_path(canonical_path) != canonical_ref["sha256"]:
        _fail("canonical findings digest mismatch")
    canonical = _validate_canonical(_load_json(canonical_path), binding)
    research_filename = RESEARCH_STAGE[binding["platform"]][2]
    research_marker = run_dir / "status" / "research_context.done.json"
    research_required = binding["audit_kind"] == "daily_delta" and (
        (run_dir / research_filename).exists() or research_marker.exists()
    )
    definitions = list(_stage_definitions(binding, research_required))
    sidecars = [_load_validated_stage(run_dir, binding, binding_sha, definition) for definition in definitions]
    if any(sidecar["audit_status"] == "blocked" for sidecar in sidecars):
        _fail("delivered generation contains a blocked required stage")
    expected_canonical, expected_status = _canonicalize(binding, sidecars, definitions)
    if canonical != expected_canonical:
        _fail("canonical findings do not reproduce from validated stage inputs")
    if canonical["audit_status"] != summary["audit_status"]:
        _fail("canonical/summary audit_status mismatch")
    if expected_status != summary["audit_status"]:
        _fail("summary status does not reproduce from validated stage inputs")
    counts = _expect_object(summary["severity_counts"], "summary.severity_counts")
    _exact_keys(counts, ("critical", "block", "important", "observation"), where="summary.severity_counts")
    if any(not _is_int(value) or value < 0 for value in counts.values()):
        _fail("summary severity counts must be non-negative integers")
    calculated = _counts(canonical["findings"])
    if counts != calculated:
        _fail("summary severity counts mismatch canonical findings")
    if not _is_int(summary["finding_count"]) or summary["finding_count"] < 0:
        _fail("summary finding_count must be a non-negative integer")
    if summary["finding_count"] != len(canonical["findings"]) or summary["finding_count"] != sum(counts.values()):
        _fail("summary finding_count mismatch")
    expected_verdict = _verdict(summary["audit_status"], counts)
    if summary["verdict"] != expected_verdict:
        _fail("summary verdict mismatch")
    expected_material = [item["text"] for item in canonical["limitations"] if item["material"]]
    if summary["material_limitations"] != expected_material:
        _fail("summary material limitations mismatch")
    text_ref = _expect_object(summary["telegram_text"], "summary.telegram_text")
    _exact_keys(text_ref, ("file", "sha256"), where="summary.telegram_text")
    if text_ref["file"] != "telegram-summary.txt":
        _fail("summary telegram text filename is fixed")
    _sha(text_ref["sha256"], "summary.telegram_text.sha256")
    text_path = run_dir / text_ref["file"]
    text_raw = _read_bytes(text_path, maximum=899)
    if len(text_raw) >= 900 or not text_raw.endswith(b"\n") or text_raw.endswith(b"\n\n"):
        _fail("telegram text bytes are not canonical or bounded")
    if _sha256_bytes(text_raw) != text_ref["sha256"]:
        _fail("telegram text digest mismatch")
    expected_text = _render_telegram(binding, summary["audit_status"], counts, summary["verdict"])
    if text_raw != expected_text:
        _fail("telegram text does not match deterministic rendering")
    report_ref = summary["report"]
    needs_report = summary["audit_status"] == "partial" or summary["finding_count"] > 0
    if needs_report:
        report = _expect_object(report_ref, "summary.report")
        _exact_keys(report, ("file", "sha256"), where="summary.report")
        expected_name = "audit.md" if binding["audit_kind"] == "pr" else "audit-final.md"
        if report["file"] != expected_name:
            _fail("summary report filename mismatch")
        _sha(report["sha256"], "summary.report.sha256")
        report_path = run_dir / report["file"]
        report_raw = _read_bytes(report_path)
        if _sha256_bytes(report_raw) != report["sha256"]:
            _fail("summary report digest mismatch")
        expected_report = _render_report(run_dir, canonical, counts, summary["verdict"], sidecars)
        if report_raw != expected_report:
            _fail("report does not match deterministic rendering")
    else:
        if report_ref is not None:
            _fail("complete-zero summary must have null report")
        if (run_dir / "audit.md").exists() or (run_dir / "audit-final.md").exists():
            _fail("complete-zero run must not have a report")
    raw = _canonical_bytes(summary)
    if _read_bytes(summary_path) != raw:
        _fail("delivery-summary.json is not canonical")
    return summary, canonical, _sha256_bytes(raw)


def _validate_receipt(run_dir: Path, summary: Mapping[str, Any], summary_sha: str) -> dict[str, Any]:
    receipt = _expect_object(_load_json(run_dir / "delivery-result.json"), "delivery-result.json")
    _exact_keys(
        receipt,
        (
            "schema_version", "summary_sha256", "run_binding_sha256", "mode", "route_source",
            "route_name", "message_id", "telegram_text_sha256", "report_sha256", "delivered_at",
        ),
        where="delivery-result.json",
    )
    if receipt["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported receipt schema_version")
    expected_mode = "message" if summary["report"] is None else "document"
    expected_report_sha = None if summary["report"] is None else summary["report"]["sha256"]
    expected = {
        "summary_sha256": summary_sha,
        "run_binding_sha256": summary["run_binding_sha256"],
        "mode": expected_mode,
        "route_source": "file_route",
        "route_name": "UAudit",
        "telegram_text_sha256": summary["telegram_text"]["sha256"],
        "report_sha256": expected_report_sha,
    }
    for field, expected_value in expected.items():
        if receipt[field] != expected_value:
            _fail(f"receipt mismatch: {field}")
    if not _is_int(receipt["message_id"]) or receipt["message_id"] <= 0:
        _fail("receipt message_id must be a positive integer")
    _iso_utc(receipt["delivered_at"], "receipt.delivered_at")
    return receipt


def _validate_telegram_marker(run_dir: Path, receipt: Mapping[str, Any]) -> None:
    marker_path = run_dir / "status" / "telegram.done"
    marker = _expect_object(_load_json(marker_path), "status/telegram.done")
    _exact_keys(marker, ("schema_version", "delivery_result_sha256", "summary_sha256"), where="status/telegram.done")
    if marker["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported telegram marker schema_version")
    if marker["delivery_result_sha256"] != _sha256_path(run_dir / "delivery-result.json"):
        _fail("telegram marker receipt digest mismatch")
    if marker["summary_sha256"] != receipt["summary_sha256"]:
        _fail("telegram marker summary digest mismatch")


def _existing_generation_preflight(run_dir: Path) -> dict[str, Any] | None:
    summary_path = run_dir / "delivery-summary.json"
    receipt_path = run_dir / "delivery-result.json"
    handoff_path = run_dir / "status" / "handoff.done"
    if receipt_path.exists() and not summary_path.exists():
        _fail("receipt exists without delivery summary")
    if handoff_path.exists() and not summary_path.exists():
        _fail("handoff marker exists without delivery summary")
    for relative in TERMINAL_MARKERS:
        if (run_dir / relative).exists() and not receipt_path.exists():
            _fail(f"{relative} exists without receipt")
    if not summary_path.exists():
        return None
    summary, _, summary_sha = _validate_summary(run_dir)
    if receipt_path.exists():
        receipt = _validate_receipt(run_dir, summary, summary_sha)
        return {"status": "already_delivered", "message_id": receipt["message_id"], "summary_sha256": summary_sha}
    return {"status": "ready", "summary_sha256": summary_sha, "handoff_done": handoff_path.exists()}


def aggregate(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    binding, _, binding_sha = _load_context(run_dir)
    if args.research_required and binding["audit_kind"] != "daily_delta":
        _fail("--research-required is valid only for daily audits")
    preflight = _existing_generation_preflight(run_dir)
    if preflight is not None:
        return preflight
    definitions = list(_stage_definitions(binding, args.research_required))
    research_filename = RESEARCH_STAGE[binding["platform"]][2]
    research_marker = run_dir / "status" / "research_context.done.json"
    if binding["audit_kind"] == "daily_delta" and not args.research_required and (
        (run_dir / research_filename).exists() or research_marker.exists()
    ):
        _fail("research artifacts exist but --research-required was not declared")
    _safe_unlink(run_dir / "status" / "aggregate.done")
    for name in PAYLOAD_ARTIFACTS:
        _safe_unlink(run_dir / name)
    sidecars = [_load_validated_stage(run_dir, binding, binding_sha, definition) for definition in definitions]
    blocked = [sidecar["stage"] for sidecar in sidecars if sidecar["audit_status"] == "blocked"]
    if blocked:
        _fail(f"blocked required stages: {', '.join(blocked)}")
    canonical, status = _canonicalize(binding, sidecars, definitions)
    canonical_raw = _canonical_bytes(canonical)
    _atomic_write(run_dir / "canonical-findings.json", canonical_raw)
    counts = _counts(canonical["findings"])
    finding_count = len(canonical["findings"])
    if finding_count != sum(counts.values()):
        _fail("internal finding count mismatch")
    verdict = _verdict(status, counts)
    telegram_raw = _render_telegram(binding, status, counts, verdict)
    _atomic_write(run_dir / "telegram-summary.txt", telegram_raw)
    report_ref: dict[str, str] | None
    if status == "partial" or finding_count > 0:
        report_name = "audit.md" if binding["audit_kind"] == "pr" else "audit-final.md"
        report_raw = _render_report(run_dir, canonical, counts, verdict, sidecars)
        _atomic_write(run_dir / report_name, report_raw)
        report_ref = {"file": report_name, "sha256": _sha256_bytes(report_raw)}
    else:
        _safe_unlink(run_dir / "audit.md")
        _safe_unlink(run_dir / "audit-final.md")
        if (run_dir / "audit.md").exists() or (run_dir / "audit-final.md").exists():
            _fail("complete-zero stale report removal failed")
        report_ref = None
    summary = {
        "schema_version": SCHEMA_VERSION,
        "issue_identifier": binding["issue_identifier"],
        "platform": binding["platform"],
        "audit_kind": binding["audit_kind"],
        "audit_status": status,
        "run_binding_sha256": binding_sha,
        "source_ref": binding["source_ref"],
        "finding_count": finding_count,
        "severity_counts": counts,
        "verdict": verdict,
        "material_limitations": [item["text"] for item in canonical["limitations"] if item["material"]],
        "telegram_text": {"file": "telegram-summary.txt", "sha256": _sha256_bytes(telegram_raw)},
        "findings": {"file": "canonical-findings.json", "sha256": _sha256_bytes(canonical_raw)},
        "report": report_ref,
        "created_at": binding["generation_created_at"],
    }
    summary_raw = _canonical_bytes(summary)
    _atomic_write(run_dir / "delivery-summary.json", summary_raw)
    # Re-read the just-published commit record before advertising readiness.
    _validate_summary(run_dir)
    marker = {
        "schema_version": SCHEMA_VERSION,
        "summary_sha256": _sha256_bytes(summary_raw),
        "run_binding_sha256": binding_sha,
    }
    _atomic_json(run_dir / "status" / "aggregate.done", marker)
    return {
        "status": "ready",
        "audit_status": status,
        "finding_count": finding_count,
        "mode": "message" if report_ref is None else "document",
        "summary_sha256": marker["summary_sha256"],
    }


def _validate_handoff(value: Any, run_dir: Path, summary: Mapping[str, Any]) -> None:
    handoff = _expect_object(value, "handoff")
    _exact_keys(
        handoff,
        (
            "schema_version", "delivery_contract", "run_dir", "delivery_summary",
            "issue_identifier", "platform", "audit_kind", "source_ref",
        ),
        where="handoff",
    )
    if handoff["schema_version"] != SCHEMA_VERSION or handoff["delivery_contract"] != "uaudit-delivery/v1":
        _fail("handoff does not declare uaudit-delivery/v1")
    if not isinstance(handoff["run_dir"], str) or Path(handoff["run_dir"]).resolve() != run_dir:
        _fail("handoff run_dir mismatch")
    if not isinstance(handoff["delivery_summary"], str) or Path(handoff["delivery_summary"]).resolve() != run_dir / "delivery-summary.json":
        _fail("handoff delivery_summary path mismatch")
    for field in ("issue_identifier", "platform", "audit_kind", "source_ref"):
        if handoff[field] != summary[field]:
            _fail(f"handoff binding mismatch: {field}")


def verify_payload(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    summary, _, summary_sha = _validate_summary(run_dir)
    handoff_path = args.handoff.resolve()
    if handoff_path != run_dir / "delivery-handoff.json":
        _fail("handoff must be $RUN/delivery-handoff.json")
    _validate_handoff(_load_json(handoff_path), run_dir, summary)
    expected_mode = "message" if summary["report"] is None else "document"
    if args.expected_mode != expected_mode:
        _fail("expected delivery mode does not match summary")
    aggregate_marker = _expect_object(_load_json(run_dir / "status" / "aggregate.done"), "status/aggregate.done")
    _exact_keys(aggregate_marker, ("schema_version", "summary_sha256", "run_binding_sha256"), where="status/aggregate.done")
    if aggregate_marker != {
        "schema_version": SCHEMA_VERSION,
        "summary_sha256": summary_sha,
        "run_binding_sha256": summary["run_binding_sha256"],
    }:
        _fail("aggregate marker mismatch")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": expected_mode,
        "route_name": "UAudit",
        "issue_identifier": summary["issue_identifier"],
        "telegram_text": _read_bytes(run_dir / "telegram-summary.txt", maximum=899).decode("utf-8").removesuffix("\n"),
        "telegram_text_sha256": summary["telegram_text"]["sha256"],
        "summary_sha256": summary_sha,
        "run_binding_sha256": summary["run_binding_sha256"],
        "report_file": None,
        "report_sha256": None,
    }
    if summary["report"] is not None:
        result["report_file"] = str((run_dir / summary["report"]["file"]).resolve())
        result["report_sha256"] = summary["report"]["sha256"]
    return result


def _plugin_data(value: Any) -> dict[str, Any]:
    response = _expect_object(value, "plugin response")
    if "ok" in response:
        return response
    if "data" not in response:
        return response
    action_response = _expect_object(response["data"], "plugin response.data")
    if "ok" in action_response:
        return action_response
    if "data" not in action_response:
        return action_response
    # Paperclip's raw HTTP action envelope is {content,data:{content,data:<result>}}.
    # Accept exactly that second wrapper, while leaving deeper/unknown shapes to
    # the field-level receipt validation below instead of unwrapping recursively.
    return _expect_object(action_response["data"], "plugin response.data.data")


def record_delivery(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    summary, _, summary_sha = _validate_summary(run_dir)
    receipt_path = run_dir / "delivery-result.json"
    if receipt_path.exists():
        receipt = _validate_receipt(run_dir, summary, summary_sha)
        marker_path = run_dir / "status" / "telegram.done"
        if marker_path.exists():
            _validate_telegram_marker(run_dir, receipt)
        else:
            _atomic_json(
                marker_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "delivery_result_sha256": _sha256_path(receipt_path),
                    "summary_sha256": summary_sha,
                },
            )
        return {"status": "already_recorded", "message_id": receipt["message_id"]}
    if (run_dir / "status" / "telegram.done").exists():
        _fail("telegram marker exists without receipt")
    handoff_path = run_dir / "delivery-handoff.json"
    _validate_handoff(_load_json(handoff_path), run_dir, summary)
    aggregate_marker = _expect_object(_load_json(run_dir / "status" / "aggregate.done"), "status/aggregate.done")
    _exact_keys(aggregate_marker, ("schema_version", "summary_sha256", "run_binding_sha256"), where="status/aggregate.done")
    if aggregate_marker != {
        "schema_version": SCHEMA_VERSION,
        "summary_sha256": summary_sha,
        "run_binding_sha256": summary["run_binding_sha256"],
    }:
        _fail("aggregate marker mismatch")
    response_path = args.response.resolve()
    if response_path != run_dir / "delivery-plugin-response.json":
        _fail("plugin response must be $RUN/delivery-plugin-response.json")
    data = _plugin_data(_load_json(response_path))
    expected_mode = "message" if summary["report"] is None else "document"
    required = {
        "ok": True,
        "mode": expected_mode,
        "routeSource": "file_route",
        "routeName": "UAudit",
        "issueIdentifier": summary["issue_identifier"],
        "projectKey": summary["issue_identifier"].split("-", 1)[0],
    }
    for field, expected in required.items():
        if data.get(field) != expected:
            _fail(f"plugin response mismatch: {field}")
    message_id = data.get("messageId")
    if not _is_int(message_id) or message_id <= 0:
        _fail("plugin response messageId must be a positive integer")
    delivered_at = _iso_utc(args.delivered_at, "delivered_at")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "summary_sha256": summary_sha,
        "run_binding_sha256": summary["run_binding_sha256"],
        "mode": expected_mode,
        "route_source": "file_route",
        "route_name": "UAudit",
        "message_id": message_id,
        "telegram_text_sha256": summary["telegram_text"]["sha256"],
        "report_sha256": None if summary["report"] is None else summary["report"]["sha256"],
        "delivered_at": delivered_at,
    }
    receipt_raw = _canonical_bytes(receipt)
    _atomic_write(receipt_path, receipt_raw)
    marker = {
        "schema_version": SCHEMA_VERSION,
        "delivery_result_sha256": _sha256_bytes(receipt_raw),
        "summary_sha256": summary_sha,
    }
    _atomic_json(run_dir / "status" / "telegram.done", marker)
    return {"status": "recorded", "message_id": message_id, "summary_sha256": summary_sha}


def _validate_approval(comments_path: Path, approvers_path: Path, summary_sha: str) -> str:
    comments_raw = _read_bytes(comments_path, maximum=256 * 1024)
    try:
        comments_value = json.loads(comments_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("malformed approval-comments.json") from exc
    export = _expect_object(comments_value, "approval comments")
    _exact_keys(export, ("schema_version", "comments"), where="approval comments")
    if export["schema_version"] != SCHEMA_VERSION or not isinstance(export["comments"], list):
        _fail("invalid approval comments schema")
    if len(export["comments"]) > 100:
        _fail("approval comments export is oversized")
    allowlist = _expect_object(_load_json(approvers_path, maximum=64 * 1024), "partial approvers")
    _exact_keys(allowlist, ("schema_version", "approver_actor_ids"), where="partial approvers")
    if allowlist["schema_version"] != SCHEMA_VERSION:
        _fail("unsupported partial approvers schema_version")
    actor_ids = allowlist["approver_actor_ids"]
    if not isinstance(actor_ids, list) or not actor_ids or len(actor_ids) > 100 or actor_ids != sorted(set(actor_ids)):
        _fail("approver_actor_ids must be a sorted unique non-empty array")
    if not all(isinstance(actor_id, str) and 1 <= len(actor_id) <= 128 and not CONTROL_RE.search(actor_id) for actor_id in actor_ids):
        _fail("invalid approver actor id")
    expected_text = f"partial audit approved {summary_sha}"
    approved: list[str] = []
    seen_ids: set[str] = set()
    for index, value in enumerate(export["comments"]):
        comment = _expect_object(value, f"comments[{index}]")
        _exact_keys(comment, ("id", "text", "actor"), where=f"comments[{index}]")
        comment_id = _bounded_string(comment["id"], f"comments[{index}].id", maximum=128)
        if comment_id in seen_ids:
            _fail("duplicate approval comment id")
        seen_ids.add(comment_id)
        text = _bounded_string(comment["text"], f"comments[{index}].text", maximum=512)
        actor = _expect_object(comment["actor"], f"comments[{index}].actor")
        _exact_keys(actor, ("id", "kind"), where=f"comments[{index}].actor")
        actor_id = _bounded_string(actor["id"], f"comments[{index}].actor.id", maximum=128)
        if actor["kind"] not in ("human", "agent", "service"):
            _fail("approval actor kind is invalid")
        if text == expected_text and actor["kind"] == "human" and actor_id in actor_ids:
            approved.append(comment_id)
    if not approved:
        _fail("no digest-bound approval from an allowlisted human")
    return sorted(approved)[0]


def _load_cursor(path: Path) -> dict[str, Any]:
    cursor = _expect_object(_load_json(path, maximum=64 * 1024), "daily cursor")
    _exact_keys(
        cursor,
        ("last_successfully_audited_sha",),
        (
            "last_successful_issue", "last_successful_at", "last_delivery_summary_sha256",
            "last_telegram_message_id",
        ),
        where="daily cursor",
    )
    _sha(cursor["last_successfully_audited_sha"], "cursor.last_successfully_audited_sha", git=True)
    if "last_successful_issue" in cursor and cursor["last_successful_issue"] is not None:
        _validate_issue(cursor["last_successful_issue"], "cursor.last_successful_issue")
    if "last_successful_at" in cursor and cursor["last_successful_at"] is not None:
        _iso_utc(cursor["last_successful_at"], "cursor.last_successful_at")
    if "last_delivery_summary_sha256" in cursor and cursor["last_delivery_summary_sha256"] is not None:
        _sha(cursor["last_delivery_summary_sha256"], "cursor.last_delivery_summary_sha256")
    if "last_telegram_message_id" in cursor and cursor["last_telegram_message_id"] is not None:
        if not _is_int(cursor["last_telegram_message_id"]) or cursor["last_telegram_message_id"] <= 0:
            _fail("cursor last_telegram_message_id is invalid")
    return cursor


def _cursor_matches(cursor: Mapping[str, Any], binding: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    return (
        cursor.get("last_successfully_audited_sha") == binding["source_ref"]["to_sha"]
        and cursor.get("last_successful_issue") == binding["issue_identifier"]
        and cursor.get("last_delivery_summary_sha256") == receipt["summary_sha256"]
        and cursor.get("last_telegram_message_id") == receipt["message_id"]
        and isinstance(cursor.get("last_successful_at"), str)
    )


def _cursor_marker_value(receipt: Mapping[str, Any], cursor_path: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "summary_sha256": receipt["summary_sha256"],
        "message_id": receipt["message_id"],
        "cursor_sha256": _sha256_path(cursor_path),
    }


def reconcile_daily(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    summary, _, summary_sha = _validate_summary(run_dir)
    if summary["audit_kind"] != "daily_delta":
        _fail("reconcile-daily requires a daily summary")
    receipt = _validate_receipt(run_dir, summary, summary_sha)
    _validate_telegram_marker(run_dir, receipt)
    binding, _, binding_sha = _load_context(run_dir)
    cursor_path = args.cursor.resolve()
    expected_cursor_name = f"{binding['platform']}-version-audit.json"
    if cursor_path.name != expected_cursor_name:
        _fail(f"daily cursor must be state/{expected_cursor_name}")
    expected_lock_dir = cursor_path.parent / "locks" / f"{binding['source_ref']['routine_id']}.lock"
    lock_dir = args.lock_dir.resolve()
    if lock_dir != expected_lock_dir:
        _fail("routine lock path does not match cursor state root and routine")
    if not lock_dir.is_dir():
        _fail("matching routine lock is not held")
    _lock_metadata(
        _load_json(lock_dir / "metadata.json"),
        binding=binding,
        binding_sha=binding_sha,
        allow_null_digest=False,
    )
    if (run_dir / "status" / "workflow.done").exists() and not (run_dir / "status" / "cursor.done").exists():
        _fail("workflow marker exists without cursor marker")
    approval_comment_id = None
    if summary["audit_status"] == "partial":
        if args.approval_comments is None or args.approvers is None:
            _fail("partial cursor reconciliation requires comments and approver allowlist")
        comments_path = args.approval_comments.resolve()
        if comments_path != run_dir / "approval-comments.json":
            _fail("partial approval export must be $RUN/approval-comments.json")
        approvers_path = args.approvers.resolve()
        if approvers_path != cursor_path.parent / "partial-approvers.json":
            _fail("partial approvers must be state/partial-approvers.json beside the cursor")
        approval_comment_id = _validate_approval(comments_path, approvers_path, summary_sha)
    elif args.approval_comments is not None or args.approvers is not None:
        _fail("approval arguments are allowed only for partial audits")
    cursor = _load_cursor(cursor_path)
    cursor_marker_path = run_dir / "status" / "cursor.done"
    if cursor_marker_path.exists():
        if not _cursor_matches(cursor, binding, receipt):
            _fail("cursor marker exists but cursor metadata does not match receipt")
        expected_marker = _cursor_marker_value(receipt, cursor_path)
        marker = _expect_object(_load_json(cursor_marker_path), "status/cursor.done")
        _exact_keys(marker, expected_marker.keys(), where="status/cursor.done")
        if marker != expected_marker:
            _fail("cursor marker is stale")
        return {"status": "already_applied", "to_sha": binding["source_ref"]["to_sha"]}
    reconciled_at = _iso_utc(args.reconciled_at, "reconciled_at")
    from_sha = binding["source_ref"]["from_sha"]
    to_sha = binding["source_ref"]["to_sha"]
    current = cursor["last_successfully_audited_sha"]
    if current == from_sha:
        updated = {
            "last_successfully_audited_sha": to_sha,
            "last_successful_issue": binding["issue_identifier"],
            "last_successful_at": reconciled_at,
            "last_delivery_summary_sha256": summary_sha,
            "last_telegram_message_id": receipt["message_id"],
        }
        _atomic_json(cursor_path, updated)
        status = "applied"
    elif current == to_sha:
        if not _cursor_matches(cursor, binding, receipt):
            _fail("cursor TO metadata belongs to a different generation")
        status = "confirmed"
    else:
        _fail("cursor compare-and-set failed; cursor is neither FROM nor matching TO")
    marker = _cursor_marker_value(receipt, cursor_path)
    _atomic_json(cursor_marker_path, marker)
    result = {"status": status, "to_sha": to_sha, "summary_sha256": summary_sha}
    if approval_comment_id is not None:
        result["approval_comment_id"] = approval_comment_id
    return result


def _verify_own_install(manifest_path: Path | None = None) -> str:
    helper_path = Path(__file__).resolve()
    manifest_path = (manifest_path or (helper_path.parent / INSTALL_MANIFEST)).resolve()
    if manifest_path != helper_path.parent / INSTALL_MANIFEST:
        _fail("install manifest must be adjacent to the deployed helper")
    manifest = _expect_object(_load_json(manifest_path, maximum=16 * 1024), "install manifest")
    _exact_keys(manifest, ("schema_version", "file", "sha256"), where="install manifest")
    if manifest["schema_version"] != INSTALL_SCHEMA:
        _fail("unsupported helper install manifest schema_version")
    if manifest["file"] != helper_path.name or manifest["file"] != "uaudit_delivery_contract.py":
        _fail("install manifest filename mismatch")
    try:
        mode = helper_path.stat().st_mode
    except OSError as exc:
        raise ContractError("cannot stat deployed helper") from exc
    if mode & 0o222:
        _fail("deployed helper must be read-only")
    expected_sha = _sha(manifest["sha256"], "install manifest sha256")
    actual_sha = _sha256_path(helper_path)
    if actual_sha != expected_sha:
        _fail("deployed helper digest mismatch")
    return actual_sha


def verify_install(args: argparse.Namespace) -> dict[str, Any]:
    actual_sha = _verify_own_install(args.manifest)
    return {"status": "installed", "sha256": actual_sha}


def _path(value: str) -> Path:
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bind = subparsers.add_parser("bind-context", help="create or validate immutable run binding")
    bind.add_argument("--run-dir", type=_path, required=True)
    bind.add_argument("--intake", type=_path, required=True)
    bind.add_argument("--lock-dir", type=_path)
    bind.set_defaults(func=bind_context)

    stage = subparsers.add_parser("validate-stage", help="validate a structured stage sidecar")
    stage.add_argument("--run-dir", type=_path, required=True)
    stage.add_argument("--sidecar", type=_path, required=True)
    stage.set_defaults(func=validate_stage)

    aggregate_parser = subparsers.add_parser("aggregate", help="publish deterministic delivery artifacts")
    aggregate_parser.add_argument("--run-dir", type=_path, required=True)
    aggregate_parser.add_argument("--research-required", action="store_true")
    aggregate_parser.set_defaults(func=aggregate)

    verify = subparsers.add_parser("verify-payload", help="verify immutable payload immediately before send")
    verify.add_argument("--run-dir", type=_path, required=True)
    verify.add_argument("--handoff", type=_path, required=True)
    verify.add_argument("--expected-mode", choices=("message", "document"), required=True)
    verify.set_defaults(func=verify_payload)

    record = subparsers.add_parser("record-delivery", help="validate plugin response and record receipt")
    record.add_argument("--run-dir", type=_path, required=True)
    record.add_argument("--response", type=_path, required=True)
    record.add_argument("--delivered-at", required=True)
    record.set_defaults(func=record_delivery)

    reconcile = subparsers.add_parser("reconcile-daily", help="apply or confirm daily cursor compare-and-set")
    reconcile.add_argument("--run-dir", type=_path, required=True)
    reconcile.add_argument("--cursor", type=_path, required=True)
    reconcile.add_argument("--lock-dir", type=_path, required=True)
    reconcile.add_argument("--reconciled-at", required=True)
    reconcile.add_argument("--approval-comments", type=_path)
    reconcile.add_argument("--approvers", type=_path)
    reconcile.set_defaults(func=reconcile_daily)

    install = subparsers.add_parser("verify-install", help="verify deployed helper against adjacent install manifest")
    install.add_argument("--manifest", type=_path, required=True)
    install.set_defaults(func=verify_install)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Every production action is gated by the immutable deployed-bytes
        # manifest. Tests exercise a copied deployment with its own manifest;
        # there is intentionally no environment-variable bypass.
        if args.command != "verify-install":
            _verify_own_install()
        result = args.func(args)
    except ContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
