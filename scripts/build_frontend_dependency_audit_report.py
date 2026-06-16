#!/usr/bin/env python3
"""Build frontend dependency vulnerability audit evidence for the PM security gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = "frontend-dependency-audit-report.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json")
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_PACKAGE_LOCK = Path("package-lock.json")
VULNERABILITY_LEVELS = ("info", "low", "moderate", "high", "critical")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _npm() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _load_json_text(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _vulnerability_counts(payload: dict[str, Any]) -> dict[str, int]:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("vulnerabilities"), dict):
        counts = metadata["vulnerabilities"]
        return {level: _as_int(counts.get(level), 0) for level in VULNERABILITY_LEVELS}

    counts = {level: 0 for level in VULNERABILITY_LEVELS}
    vulnerabilities = payload.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        for row in vulnerabilities.values():
            if not isinstance(row, dict):
                continue
            severity = str(row.get("severity", "")).lower()
            if severity in counts:
                counts[severity] += 1
    return counts


def _vulnerability_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    rows: list[dict[str, Any]] = []
    for name, row in sorted(vulnerabilities.items()):
        if not isinstance(row, dict):
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
                    via_rows.append({"title": item, "severity": "", "url": "", "range": ""})
        rows.append(
            {
                "name": str(row.get("name", name)),
                "severity": str(row.get("severity", "")),
                "range": str(row.get("range", "")),
                "is_direct": bool(row.get("isDirect", False)),
                "fix_available": row.get("fixAvailable", False),
                "via": via_rows,
            }
        )
    return rows


def build_report(
    *,
    audit_payload: dict[str, Any],
    audit_exit_code: int,
    audit_stdout: str,
    audit_stderr: str,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
) -> dict[str, Any]:
    counts = _vulnerability_counts(audit_payload)
    total = sum(counts.values())
    high_critical = counts["high"] + counts["critical"]
    parsed_audit_json = bool(audit_payload)
    package_json_present = package_json.exists()
    package_lock_present = package_lock.exists()
    blockers = [
        *(["package_json_missing"] if not package_json_present else []),
        *(["package_lock_missing"] if not package_lock_present else []),
        *(["npm_audit_json_unavailable"] if not parsed_audit_json else []),
        *(["frontend_dependency_high_or_critical_vulnerabilities_present"] if high_critical else []),
        *(["frontend_dependency_vulnerabilities_present"] if total else []),
        *(["npm_audit_exit_code_nonzero"] if audit_exit_code != 0 and total == 0 else []),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_FRONTEND_DEPENDENCY_AUDIT_BLOCKED",
        "blockers": blockers,
        "checks": {
            "package_json_present": package_json_present,
            "package_lock_present": package_lock_present,
            "npm_audit_json_parse_pass": parsed_audit_json,
            "dependency_vulnerability_total_zero_pass": total == 0,
            "dependency_high_or_critical_zero_pass": high_critical == 0,
            "npm_audit_exit_code_zero_pass": audit_exit_code == 0,
        },
        "summary": {
            "package_json": str(package_json),
            "package_lock": str(package_lock),
            "npm_audit_exit_code": audit_exit_code,
            "vulnerability_total": total,
            "high_or_critical_vulnerability_count": high_critical,
            **{f"{level}_vulnerability_count": counts[level] for level in VULNERABILITY_LEVELS},
        },
        "vulnerabilities": _vulnerability_rows(audit_payload),
        "diagnostics": {
            "npm_audit_stdout_bytes": len(audit_stdout.encode("utf-8")),
            "npm_audit_stderr_tail": audit_stderr[-2000:],
        },
        "claim_boundary": (
            "This report records npm audit release evidence for the frontend dependency graph. It does not "
            "replace secrets, license, SBOM, or reproducible-build checks in the PM security gate."
        ),
    }


def run_audit(*, cwd: Path) -> tuple[dict[str, Any], int, str, str]:
    result = subprocess.run(
        [_npm(), "audit", "--json"],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    return _load_json_text(result.stdout), int(result.returncode), result.stdout, result.stderr


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
    audit_payload, audit_exit_code, audit_stdout, audit_stderr = run_audit(cwd=REPO_ROOT)
    payload = build_report(
        audit_payload=audit_payload,
        audit_exit_code=audit_exit_code,
        audit_stdout=audit_stdout,
        audit_stderr=audit_stderr,
        package_json=args.package_json,
        package_lock=args.package_lock,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
