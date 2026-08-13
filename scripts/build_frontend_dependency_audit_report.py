#!/usr/bin/env python3
"""Launch the native frontend dependency-audit evidence command."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "frontend_dependency_audit_report.json"
)
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_PACKAGE_LOCK = Path("package-lock.json")
NATIVE_COMMAND = [
    "cargo",
    "run",
    "--quiet",
    "--locked",
    "--manifest-path",
    "native/Cargo.toml",
    "-p",
    "structural-frontend-contract",
    "--",
    "frontend-audit-report",
    "--root",
    ".",
]
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "action",
        "status",
        "source_map_sha256",
        "frontend_contract_receipt_hash",
        "logical_command",
        "process_launcher",
        "node_options_disposition",
        "direct_processes_spawned",
        "observed_exit_code",
        "report",
        "contract_pass",
        "reason_code",
        "blocker_count",
        "vulnerability_total",
        "high_or_critical_vulnerability_count",
        "network_access_accounting",
        "filesystem_mutation_accounting",
        "environment_accounting",
        "deterministic_receipt",
        "claim_boundary",
        "receipt_hash",
    }
)
REPORT_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "contract_pass",
        "reason_code",
        "blockers",
        "checks",
        "summary",
        "vulnerabilities",
        "diagnostics",
        "claim_boundary",
    }
)
SUMMARY_KEYS = frozenset(
    {
        "package_json",
        "package_lock",
        "npm_audit_exit_code",
        "vulnerability_total",
        "high_or_critical_vulnerability_count",
        "info_vulnerability_count",
        "low_vulnerability_count",
        "moderate_vulnerability_count",
        "high_vulnerability_count",
        "critical_vulnerability_count",
    }
)
CHECK_KEYS = frozenset(
    {
        "package_json_present",
        "package_lock_present",
        "npm_audit_json_parse_pass",
        "dependency_vulnerability_total_zero_pass",
        "dependency_high_or_critical_zero_pass",
        "npm_audit_exit_code_zero_pass",
    }
)
DIAGNOSTIC_KEYS = frozenset(
    {"npm_audit_stdout_bytes", "npm_audit_stderr_tail"}
)
VULNERABILITY_KEYS = frozenset(
    {"name", "severity", "range", "is_direct", "fix_available", "via"}
)
VIA_KEYS = frozenset({"title", "severity", "url", "range"})


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def _reject_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON number: {value}")


def _decode_object(text: str) -> dict[str, Any]:
    payload = json.loads(
        text,
        object_pairs_hook=_strict_object,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _sha256_identity(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256_identity(value: Any) -> bool:
    text = str(value or "")
    digest = text.removeprefix("sha256:")
    return bool(
        text.startswith("sha256:")
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def _receipt_from_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            payload = _decode_object(line)
        except (json.JSONDecodeError, ValueError):
            continue
        report = payload.get("report")
        if (
            set(payload) != RECEIPT_KEYS
            or payload.get("schema_version")
            != "structural-native-frontend-audit-report-receipt.v1"
            or payload.get("action") != "frontend_audit_report"
            or payload.get("status")
            not in {"published_pass", "published_blocked"}
            or payload.get("logical_command") != ["npm", "audit", "--json"]
            or payload.get("process_launcher") != "npm"
            or payload.get("node_options_disposition")
            != "removed_for_direct_child"
            or payload.get("direct_processes_spawned") != 1
            or not isinstance(payload.get("observed_exit_code"), int)
            or isinstance(payload.get("observed_exit_code"), bool)
            or not isinstance(report, dict)
            or set(report)
            != {"path", "byte_length", "sha256", "publication_strategy"}
            or not isinstance(report.get("path"), str)
            or not isinstance(report.get("byte_length"), int)
            or isinstance(report.get("byte_length"), bool)
            or int(report["byte_length"]) <= 0
            or not _is_sha256_identity(report.get("sha256"))
            or report.get("publication_strategy")
            != "bounded_staging_then_backup_rename_with_rollback"
            or not isinstance(payload.get("contract_pass"), bool)
            or payload.get("status")
            != (
                "published_pass"
                if payload.get("contract_pass")
                else "published_blocked"
            )
            or not isinstance(payload.get("reason_code"), str)
            or not isinstance(payload.get("blocker_count"), int)
            or isinstance(payload.get("blocker_count"), bool)
            or not isinstance(payload.get("vulnerability_total"), int)
            or isinstance(payload.get("vulnerability_total"), bool)
            or not isinstance(
                payload.get("high_or_critical_vulnerability_count"), int
            )
            or isinstance(
                payload.get("high_or_critical_vulnerability_count"), bool
            )
            or payload.get("deterministic_receipt") is not False
            or not _is_sha256_identity(payload.get("source_map_sha256"))
            or not _is_sha256_identity(
                payload.get("frontend_contract_receipt_hash")
            )
            or not _is_sha256_identity(payload.get("receipt_hash"))
            or any(
                not str(payload.get(key) or "").strip()
                for key in (
                    "network_access_accounting",
                    "filesystem_mutation_accounting",
                    "environment_accounting",
                    "claim_boundary",
                )
            )
        ):
            continue
        unsigned = dict(payload)
        expected = unsigned.pop("receipt_hash")
        canonical = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if _sha256_identity(canonical) == expected:
            return payload
    return {}


def _load_published_report(
    *, repo_root: Path, requested: Path, receipt: dict[str, Any]
) -> dict[str, Any]:
    report_receipt = receipt["report"]
    if report_receipt["path"] != str(requested):
        raise ValueError("native receipt report path does not match requested output")
    path = requested if requested.is_absolute() else repo_root / requested
    report_bytes = path.read_bytes()
    if (
        len(report_bytes) != report_receipt["byte_length"]
        or _sha256_identity(report_bytes) != report_receipt["sha256"]
        or not report_bytes.endswith(b"\n")
    ):
        raise ValueError("published report identity does not match native receipt")
    payload = _decode_object(report_bytes.decode("utf-8"))
    summary = payload.get("summary")
    blockers = payload.get("blockers")
    checks = payload.get("checks")
    vulnerabilities = payload.get("vulnerabilities")
    diagnostics = payload.get("diagnostics")
    if (
        set(payload) != REPORT_KEYS
        or payload.get("schema_version") != "frontend-dependency-audit-report.v1"
        or payload.get("contract_pass") is not receipt["contract_pass"]
        or payload.get("reason_code") != receipt["reason_code"]
        or not isinstance(blockers, list)
        or not all(isinstance(blocker, str) and blocker for blocker in blockers)
        or len(blockers) != receipt["blocker_count"]
        or not isinstance(summary, dict)
        or set(summary) != SUMMARY_KEYS
        or any(
            not isinstance(summary.get(key), int)
            or isinstance(summary.get(key), bool)
            or int(summary[key]) < 0
            for key in SUMMARY_KEYS
            if key not in {"package_json", "package_lock", "npm_audit_exit_code"}
        )
        or not isinstance(summary.get("npm_audit_exit_code"), int)
        or isinstance(summary.get("npm_audit_exit_code"), bool)
        or summary.get("npm_audit_exit_code")
        != receipt["observed_exit_code"]
        or not isinstance(summary.get("package_json"), str)
        or not isinstance(summary.get("package_lock"), str)
        or summary.get("vulnerability_total") != receipt["vulnerability_total"]
        or summary.get("high_or_critical_vulnerability_count")
        != receipt["high_or_critical_vulnerability_count"]
        or summary.get("vulnerability_total")
        != sum(
            int(summary[f"{level}_vulnerability_count"])
            for level in ("info", "low", "moderate", "high", "critical")
        )
        or summary.get("high_or_critical_vulnerability_count")
        != summary.get("high_vulnerability_count")
        + summary.get("critical_vulnerability_count")
        or not isinstance(checks, dict)
        or set(checks) != CHECK_KEYS
        or not all(isinstance(value, bool) for value in checks.values())
        or checks.get("dependency_vulnerability_total_zero_pass")
        is not (summary.get("vulnerability_total") == 0)
        or checks.get("dependency_high_or_critical_zero_pass")
        is not (summary.get("high_or_critical_vulnerability_count") == 0)
        or checks.get("npm_audit_exit_code_zero_pass")
        is not (summary.get("npm_audit_exit_code") == 0)
        or not isinstance(vulnerabilities, list)
        or not _valid_vulnerability_rows(vulnerabilities)
        or not isinstance(diagnostics, dict)
        or set(diagnostics) != DIAGNOSTIC_KEYS
        or not isinstance(diagnostics.get("npm_audit_stdout_bytes"), int)
        or isinstance(diagnostics.get("npm_audit_stdout_bytes"), bool)
        or int(diagnostics["npm_audit_stdout_bytes"]) < 0
        or not isinstance(diagnostics.get("npm_audit_stderr_tail"), str)
        or not str(payload.get("generated_at") or "").strip()
        or not str(payload.get("claim_boundary") or "").strip()
    ):
        raise ValueError("published report does not match the native report contract")
    return payload


def _valid_vulnerability_rows(rows: list[Any]) -> bool:
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != VULNERABILITY_KEYS
            or not all(
                isinstance(row.get(key), str)
                for key in ("name", "severity", "range")
            )
            or not isinstance(row.get("is_direct"), bool)
            or not isinstance(row.get("via"), list)
        ):
            return False
        for via in row["via"]:
            if (
                not isinstance(via, dict)
                or set(via) != VIA_KEYS
                or not all(isinstance(value, str) for value in via.values())
            ):
                return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--package-lock", type=Path, default=DEFAULT_PACKAGE_LOCK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        *NATIVE_COMMAND,
        "--package-json",
        str(args.package_json),
        "--package-lock",
        str(args.package_lock),
        "--out",
        str(args.out),
    ]
    if args.fail_blocked:
        command.append("--fail-blocked")
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"native frontend dependency audit launch failed: {error}")
        return 1
    receipt = _receipt_from_stdout(result.stdout)
    if not receipt:
        detail = (result.stdout + result.stderr).strip()
        print(detail or "native frontend dependency audit emitted no valid receipt")
        return result.returncode or 1
    try:
        payload = _load_published_report(
            repo_root=REPO_ROOT,
            requested=args.out,
            receipt=receipt,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"native frontend dependency audit report validation failed: {error}")
        return 1
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else payload["summary"]
    )
    expected_returncode = 1 if args.fail_blocked and not payload["contract_pass"] else 0
    if result.returncode != expected_returncode:
        print(
            "native frontend dependency audit exit did not match its published receipt: "
            f"expected {expected_returncode}, observed {result.returncode}"
        )
        return 1
    return expected_returncode


if __name__ == "__main__":
    raise SystemExit(main())
