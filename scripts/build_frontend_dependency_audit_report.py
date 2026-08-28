#!/usr/bin/env python3
"""Build and verify exact-source npm vulnerability audit evidence.

The report is a point-in-time npm registry audit of the dependency graph
described by ``package.json`` and ``package-lock.json``. It intentionally does
not grant license, SBOM, signing, release, or commercial authority.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = "frontend-dependency-audit-report.v2"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "frontend_dependency_audit_report.json"
)
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_PACKAGE_LOCK = Path("package-lock.json")
VULNERABILITY_LEVELS = ("info", "low", "moderate", "high", "critical")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
AUDIT_COMMAND = ("audit", "--json", "--audit-level=info")
REQUIRED_AJV_VERSION = "8.20.0"
REQUIRED_NODE_VERSION = "v20.19.0"
REQUIRED_NPM_VERSION = "10.8.2"
CLAIM_BOUNDARY = {
    "allowed": [
        "point-in-time npm registry vulnerability audit",
        "exact source and package manifest byte binding",
        "zero reported vulnerabilities at audit execution time",
    ],
    "not_granted": [
        "future vulnerability absence",
        "license or third-party redistribution clearance",
        "complete SBOM authority",
        "product signing or provenance authority",
        "release or commercial authority",
    ],
}


class FrontendDependencyAuditError(RuntimeError):
    """Raised when audit evidence cannot be built or verified exactly."""


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _npm() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _node() -> str:
    return "node.exe" if sys.platform == "win32" else "node"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate_json_key:{key}")
        payload[key] = value
    return payload


def _load_json_text(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite:{token}")
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _git_text(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise FrontendDependencyAuditError(
            f"git_identity_unavailable:{args[0]}"
        ) from exc


def git_identity() -> dict[str, Any]:
    commit_sha = _git_text("rev-parse", "HEAD")
    tree_sha = _git_text("rev-parse", "HEAD^{tree}")
    if commit_sha == "0" * 40 or SHA_PATTERN.fullmatch(commit_sha) is None:
        raise FrontendDependencyAuditError("source_commit_sha_invalid")
    if tree_sha == "0" * 40 or SHA_PATTERN.fullmatch(tree_sha) is None:
        raise FrontendDependencyAuditError("source_tree_sha_invalid")
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise FrontendDependencyAuditError("source_status_unavailable") from exc
    return {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "worktree_clean": not bool(status),
    }


def _validate_identity(
    source_identity: dict[str, Any], expected_source_sha: str
) -> dict[str, Any]:
    commit_sha = source_identity.get("commit_sha")
    tree_sha = source_identity.get("tree_sha")
    expected = expected_source_sha or commit_sha
    if (
        not isinstance(commit_sha, str)
        or commit_sha == "0" * 40
        or SHA_PATTERN.fullmatch(commit_sha) is None
    ):
        raise FrontendDependencyAuditError("source_commit_sha_invalid")
    if (
        not isinstance(tree_sha, str)
        or tree_sha == "0" * 40
        or SHA_PATTERN.fullmatch(tree_sha) is None
    ):
        raise FrontendDependencyAuditError("source_tree_sha_invalid")
    if not isinstance(expected, str) or SHA_PATTERN.fullmatch(expected) is None:
        raise FrontendDependencyAuditError("expected_source_sha_invalid")
    return {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "expected_commit_sha": expected,
        "worktree_clean": source_identity.get("worktree_clean") is True,
    }


def _file_binding(path: Path) -> dict[str, Any]:
    regular_file = path.is_file() and not path.is_symlink()
    return {
        "path": _display_path(path),
        "regular_file": regular_file,
        "bytes": path.stat().st_size if regular_file else None,
        "sha256": _sha256_path(path) if regular_file else None,
    }


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = _load_json_text(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload


def _manifest_lock_match(package_json: Path, package_lock: Path) -> bool:
    manifest = _json_object(package_json)
    lock = _json_object(package_lock)
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    if not manifest or not isinstance(root, dict):
        return False
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        manifest_rows = manifest.get(key, {})
        lock_rows = root.get(key, {})
        if not isinstance(manifest_rows, dict) or not isinstance(lock_rows, dict):
            return False
        if manifest_rows != lock_rows:
            return False
    return True


def _ajv_exact_version_match(package_json: Path, package_lock: Path) -> bool:
    manifest = _json_object(package_json)
    lock = _json_object(package_lock)
    dependencies = manifest.get("dependencies")
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    ajv = packages.get("node_modules/ajv") if isinstance(packages, dict) else None
    return bool(
        isinstance(dependencies, dict)
        and dependencies.get("ajv") == REQUIRED_AJV_VERSION
        and isinstance(root, dict)
        and isinstance(root.get("dependencies"), dict)
        and root["dependencies"].get("ajv") == REQUIRED_AJV_VERSION
        and isinstance(ajv, dict)
        and ajv.get("version") == REQUIRED_AJV_VERSION
    )


def _strict_vulnerability_counts(
    payload: dict[str, Any],
) -> tuple[dict[str, int], bool]:
    metadata = payload.get("metadata")
    values = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(values, dict) or set(values) != {
        *VULNERABILITY_LEVELS,
        "total",
    }:
        return {level: 0 for level in VULNERABILITY_LEVELS}, False
    counts: dict[str, int] = {}
    for level in VULNERABILITY_LEVELS:
        value = values.get(level)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return {name: 0 for name in VULNERABILITY_LEVELS}, False
        counts[level] = value
    total = values.get("total")
    valid = (
        not isinstance(total, bool)
        and isinstance(total, int)
        and total >= 0
        and total == sum(counts.values())
    )
    return counts, valid


def _vulnerability_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    rows: list[dict[str, Any]] = []
    for name, row in sorted(vulnerabilities.items()):
        if not isinstance(name, str) or not isinstance(row, dict):
            continue
        via_rows: list[dict[str, Any]] = []
        via = row.get("via")
        if isinstance(via, list):
            for item in via:
                if isinstance(item, dict):
                    via_rows.append(
                        {
                            "title": str(item.get("title", "")),
                            "severity": str(item.get("severity", "")),
                            "url": str(item.get("url", "")),
                            "range": str(item.get("range", "")),
                        }
                    )
                elif isinstance(item, str):
                    via_rows.append(
                        {"title": item, "severity": "", "url": "", "range": ""}
                    )
        rows.append(
            {
                "name": str(row.get("name", name)),
                "severity": str(row.get("severity", "")),
                "range": str(row.get("range", "")),
                "is_direct": row.get("isDirect") is True,
                "fix_available": row.get("fixAvailable", False),
                "via": via_rows,
            }
        )
    return rows


def _audit_payload_contract(payload: dict[str, Any]) -> bool:
    vulnerabilities = payload.get("vulnerabilities")
    metadata = payload.get("metadata")
    dependencies = metadata.get("dependencies") if isinstance(metadata, dict) else None
    return bool(
        set(payload) == {"auditReportVersion", "vulnerabilities", "metadata"}
        and payload.get("auditReportVersion") == 2
        and isinstance(vulnerabilities, dict)
        and all(
            isinstance(name, str) and isinstance(row, dict)
            for name, row in vulnerabilities.items()
        )
        and isinstance(metadata, dict)
        and set(metadata) == {"vulnerabilities", "dependencies"}
        and isinstance(dependencies, dict)
        and set(dependencies)
        == {"prod", "dev", "optional", "peer", "peerOptional", "total"}
        and all(
            not isinstance(value, bool) and isinstance(value, int) and value >= 0
            for value in dependencies.values()
        )
    )


def _vulnerability_rows_match_metadata(payload: dict[str, Any]) -> bool:
    counts, metadata_valid = _strict_vulnerability_counts(payload)
    vulnerabilities = payload.get("vulnerabilities")
    if not metadata_valid or not isinstance(vulnerabilities, dict):
        return False
    actual = {level: 0 for level in VULNERABILITY_LEVELS}
    for row in vulnerabilities.values():
        if not isinstance(row, dict):
            return False
        severity = row.get("severity")
        if severity not in actual:
            return False
        actual[str(severity)] += 1
    return actual == counts


def _timestamp_is_utc(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() == timezone.utc.utcoffset(parsed)
    )


def _evaluation(
    *,
    source: dict[str, Any],
    package_json_binding: dict[str, Any],
    package_lock_binding: dict[str, Any],
    manifest_lock_match: bool,
    ajv_exact_version_match: bool,
    audit_payload: dict[str, Any],
    audit_exit_code: int,
    stdout_payload_match: bool,
    node_version: str,
    npm_version: str,
) -> tuple[dict[str, bool], list[str], dict[str, Any]]:
    counts, metadata_valid = _strict_vulnerability_counts(audit_payload)
    total = sum(counts.values())
    high_critical = counts["high"] + counts["critical"]
    checks = {
        "source_identity_valid": (
            isinstance(source.get("commit_sha"), str)
            and SHA_PATTERN.fullmatch(str(source.get("commit_sha"))) is not None
            and isinstance(source.get("tree_sha"), str)
            and SHA_PATTERN.fullmatch(str(source.get("tree_sha"))) is not None
        ),
        "source_commit_matches_expected": source.get("commit_sha")
        == source.get("expected_commit_sha"),
        "source_worktree_clean": source.get("worktree_clean") is True,
        "package_json_regular_file": package_json_binding.get("regular_file") is True,
        "package_lock_regular_file": package_lock_binding.get("regular_file") is True,
        "package_manifest_lock_root_match": manifest_lock_match,
        "ajv_direct_runtime_fixed_exact_version": ajv_exact_version_match,
        "node_version_exact": node_version.strip() == REQUIRED_NODE_VERSION,
        "npm_version_exact": npm_version.strip() == REQUIRED_NPM_VERSION,
        "npm_audit_payload_contract_pass": _audit_payload_contract(audit_payload),
        "npm_audit_stdout_payload_match": stdout_payload_match,
        "npm_audit_metadata_consistent": metadata_valid,
        "npm_audit_vulnerability_rows_match_metadata": (
            _vulnerability_rows_match_metadata(audit_payload)
        ),
        "dependency_vulnerability_total_zero_pass": metadata_valid and total == 0,
        "dependency_high_or_critical_zero_pass": metadata_valid
        and high_critical == 0,
        "npm_audit_exit_code_zero_pass": audit_exit_code == 0,
    }
    blockers = [label for label, passed in checks.items() if not passed]
    summary = {
        "npm_audit_exit_code": audit_exit_code,
        "vulnerability_total": total,
        "high_or_critical_vulnerability_count": high_critical,
        **{
            f"{level}_vulnerability_count": counts[level]
            for level in VULNERABILITY_LEVELS
        },
    }
    return checks, blockers, summary


def build_report(
    *,
    audit_payload: dict[str, Any],
    audit_exit_code: int,
    audit_stdout: str,
    source_identity: dict[str, Any],
    expected_source_sha: str,
    node_version: str,
    npm_version: str,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
) -> dict[str, Any]:
    source = _validate_identity(source_identity, expected_source_sha)
    package_json_binding = _file_binding(package_json)
    package_lock_binding = _file_binding(package_lock)
    manifest_lock_match = _manifest_lock_match(package_json, package_lock)
    stdout_payload_match = (
        bool(audit_payload) and _load_json_text(audit_stdout) == audit_payload
    )
    checks, blockers, summary = _evaluation(
        source=source,
        package_json_binding=package_json_binding,
        package_lock_binding=package_lock_binding,
        manifest_lock_match=manifest_lock_match,
        ajv_exact_version_match=_ajv_exact_version_match(
            package_json, package_lock
        ),
        audit_payload=audit_payload,
        audit_exit_code=audit_exit_code,
        stdout_payload_match=stdout_payload_match,
        node_version=node_version,
        npm_version=npm_version,
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source": source,
        "inputs": {
            "package_json": package_json_binding,
            "package_lock": package_lock_binding,
        },
        "audit": {
            "command": [_npm(), *AUDIT_COMMAND],
            "exit_code": audit_exit_code,
            "node_version": node_version.strip(),
            "npm_version": npm_version.strip(),
            "payload": audit_payload,
            "payload_sha256": _canonical_hash(audit_payload),
            "stdout": audit_stdout,
            "stdout_bytes": len(audit_stdout.encode("utf-8")),
            "stdout_sha256": _sha256_bytes(audit_stdout.encode("utf-8")),
        },
        "contract_pass": not blockers,
        "reason_code": (
            "PASS" if not blockers else "ERR_FRONTEND_DEPENDENCY_AUDIT_BLOCKED"
        ),
        "blockers": blockers,
        "checks": checks,
        "summary": {
            "package_json": package_json_binding["path"],
            "package_lock": package_lock_binding["path"],
            **summary,
        },
        "vulnerabilities": _vulnerability_rows(audit_payload),
        "claim_boundary": deepcopy(CLAIM_BOUNDARY),
    }
    payload["artifact_hash"] = _canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    return payload


def run_audit(*, cwd: Path) -> dict[str, Any]:
    try:
        node_version = subprocess.check_output(
            [_node(), "--version"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        npm_version = subprocess.check_output(
            [_npm(), "--version"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        result = subprocess.run(
            [_npm(), *AUDIT_COMMAND],
            cwd=cwd,
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FrontendDependencyAuditError("npm_audit_execution_failed") from exc
    return {
        "payload": _load_json_text(result.stdout),
        "exit_code": int(result.returncode),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "node_version": node_version,
        "npm_version": npm_version,
    }


def verify_report(
    payload: dict[str, Any],
    *,
    source_identity: dict[str, Any],
    expected_source_sha: str,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
) -> dict[str, Any]:
    if set(payload) != {
        "schema_version",
        "generated_at",
        "source",
        "inputs",
        "audit",
        "contract_pass",
        "reason_code",
        "blockers",
        "checks",
        "summary",
        "vulnerabilities",
        "claim_boundary",
        "artifact_hash",
    }:
        raise FrontendDependencyAuditError("report_fields_invalid")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise FrontendDependencyAuditError("report_schema_version_invalid")
    expected_artifact_hash = _canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    if payload.get("artifact_hash") != expected_artifact_hash:
        raise FrontendDependencyAuditError("report_artifact_hash_invalid")
    if not _timestamp_is_utc(payload.get("generated_at")):
        raise FrontendDependencyAuditError("report_generated_at_invalid")

    source = _validate_identity(source_identity, expected_source_sha)
    if payload.get("source") != source:
        raise FrontendDependencyAuditError("report_source_binding_invalid")
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        raise FrontendDependencyAuditError("report_input_bindings_invalid")
    package_json_binding = _file_binding(package_json)
    package_lock_binding = _file_binding(package_lock)
    if inputs != {
        "package_json": package_json_binding,
        "package_lock": package_lock_binding,
    }:
        raise FrontendDependencyAuditError("report_input_bindings_invalid")

    audit = payload.get("audit")
    if not isinstance(audit, dict) or audit.get("command") != [
        _npm(),
        *AUDIT_COMMAND,
    ]:
        raise FrontendDependencyAuditError("report_audit_contract_invalid")
    if set(audit) != {
        "command",
        "exit_code",
        "node_version",
        "npm_version",
        "payload",
        "payload_sha256",
        "stdout",
        "stdout_bytes",
        "stdout_sha256",
    }:
        raise FrontendDependencyAuditError("report_audit_contract_invalid")
    audit_payload = audit.get("payload")
    if not isinstance(audit_payload, dict):
        raise FrontendDependencyAuditError("report_audit_payload_invalid")
    if audit.get("payload_sha256") != _canonical_hash(audit_payload):
        raise FrontendDependencyAuditError("report_audit_payload_hash_invalid")
    audit_stdout = audit.get("stdout")
    if not isinstance(audit_stdout, str):
        raise FrontendDependencyAuditError("report_audit_stdout_invalid")
    stdout_bytes = audit_stdout.encode("utf-8")
    if (
        audit.get("stdout_bytes") != len(stdout_bytes)
        or audit.get("stdout_sha256") != _sha256_bytes(stdout_bytes)
        or _load_json_text(audit_stdout) != audit_payload
    ):
        raise FrontendDependencyAuditError("report_audit_stdout_binding_invalid")
    audit_exit_code = audit.get("exit_code")
    if isinstance(audit_exit_code, bool) or not isinstance(audit_exit_code, int):
        raise FrontendDependencyAuditError("report_audit_exit_code_invalid")
    node_version = audit.get("node_version")
    npm_version = audit.get("npm_version")
    if not isinstance(node_version, str) or not isinstance(npm_version, str):
        raise FrontendDependencyAuditError("report_toolchain_invalid")

    checks, blockers, summary = _evaluation(
        source=source,
        package_json_binding=package_json_binding,
        package_lock_binding=package_lock_binding,
        manifest_lock_match=_manifest_lock_match(package_json, package_lock),
        ajv_exact_version_match=_ajv_exact_version_match(
            package_json, package_lock
        ),
        audit_payload=audit_payload,
        audit_exit_code=audit_exit_code,
        stdout_payload_match=True,
        node_version=node_version,
        npm_version=npm_version,
    )
    expected_summary = {
        "package_json": package_json_binding["path"],
        "package_lock": package_lock_binding["path"],
        **summary,
    }
    if (
        payload.get("checks") != checks
        or payload.get("blockers") != blockers
        or payload.get("contract_pass") is not (not blockers)
        or payload.get("reason_code")
        != ("PASS" if not blockers else "ERR_FRONTEND_DEPENDENCY_AUDIT_BLOCKED")
        or payload.get("summary") != expected_summary
        or payload.get("vulnerabilities") != _vulnerability_rows(audit_payload)
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise FrontendDependencyAuditError("report_semantics_invalid")
    if blockers:
        raise FrontendDependencyAuditError("report_contract_blocked")
    return payload


def build_current_report(
    *,
    out: Path,
    expected_source_sha: str = "",
    source_identity: dict[str, Any] | None = None,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
) -> dict[str, Any]:
    caller_supplied_identity = source_identity is not None
    identity = source_identity if source_identity is not None else git_identity()
    run = run_audit(cwd=REPO_ROOT)
    if not caller_supplied_identity and git_identity() != identity:
        raise FrontendDependencyAuditError("source_changed_during_npm_audit")
    payload = build_report(
        audit_payload=run["payload"],
        audit_exit_code=run["exit_code"],
        audit_stdout=run["stdout"],
        source_identity=identity,
        expected_source_sha=expected_source_sha,
        node_version=run["node_version"],
        npm_version=run["npm_version"],
        package_json=package_json,
        package_lock=package_lock,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--package-lock", type=Path, default=DEFAULT_PACKAGE_LOCK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--expected-source-sha", default="")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        identity = git_identity()
        if args.verify:
            payload = _json_object(args.out)
            verify_report(
                payload,
                source_identity=identity,
                expected_source_sha=args.expected_source_sha,
                package_json=args.package_json,
                package_lock=args.package_lock,
            )
        else:
            payload = build_current_report(
                out=args.out,
                expected_source_sha=args.expected_source_sha,
                source_identity=identity,
                package_json=args.package_json,
                package_lock=args.package_lock,
            )
    except (FrontendDependencyAuditError, OSError, ValueError) as exc:
        print(f"frontend dependency audit failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else payload["summary"]
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
