#!/usr/bin/env python3
"""Build an actionable register for open PM release blockers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pm-release-blocker-action-register.v1"
DEFAULT_PM_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json")
DEFAULT_OUT_MD = Path("implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md")
DEFAULT_PM_REPORT_MD = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.md")
DEFAULT_CI_STREAK_MANIFEST = Path(
    "implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json"
)
DEFAULT_GITHUB_ACTIONS_CI_STREAK_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json"
)
DEFAULT_LICENSE_STATUS_CLOSURE = Path(
    "implementation/phase1/release_evidence/productization/license_status_closure_report.json"
)
DEFAULT_LICENSE_STATUS_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/license_status_intake_packet.json"
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _split_blocker(blocker_id: str) -> tuple[str, str]:
    if "::" not in blocker_id:
        return "", blocker_id
    namespace, code = blocker_id.split("::", 1)
    return namespace, code


def _indexed_rows(rows: list[Any], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get(key, "") or "")
        if row_key:
            indexed[row_key] = row
    return indexed


def _owner_action(*, namespace: str, code: str, row: dict[str, Any]) -> str:
    summary = _as_dict(row.get("summary"))
    if namespace == "basic_ci":
        if code.startswith("pr_ci"):
            return str(summary.get("pr_owner_action", "") or "")
        if code.startswith("nightly_ci"):
            return str(summary.get("nightly_owner_action", "") or "")
    if namespace == "security" and "license" in code:
        return str(summary.get("license_status_owner_action", "") or "")
    direct = str(summary.get("owner_action", "") or row.get("owner_action", "") or "")
    if direct:
        return direct
    title = str(row.get("title", namespace or "PM release gate") or namespace or "PM release gate")
    return f"Resolve `{code}` in {title} evidence, regenerate PM release reports, and attach the updated evidence."


def _claim_boundary(*, namespace: str, code: str, row: dict[str, Any]) -> str:
    summary = _as_dict(row.get("summary"))
    if namespace == "basic_ci":
        if code.startswith("pr_ci"):
            direct = str(summary.get("pr_claim_boundary", "") or "")
            if direct:
                return direct
        if code.startswith("nightly_ci"):
            direct = str(summary.get("nightly_claim_boundary", "") or "")
            if direct:
                return direct
    direct = str(row.get("claim_boundary", "") or summary.get("claim_boundary", "") or "")
    if direct:
        return direct
    return "This register is a blocker handoff artifact; it does not convert missing evidence into a release pass."


def _acceptance_criteria(*, namespace: str, code: str, row: dict[str, Any]) -> list[str]:
    summary = _as_dict(row.get("summary"))
    if namespace == "basic_ci" and code.startswith("pr_ci"):
        required = int(summary.get("required_consecutive_pass_count", 30) or 30)
        return [
            f"`pr_pass_streak_count >= {required}` in `pm_release_gate_report.json`",
            "`basic_ci::pr_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`",
            "`github_actions_ci_streak_evidence.json` refreshed for the release signoff window",
        ]
    if namespace == "basic_ci" and code.startswith("nightly_ci"):
        required = int(summary.get("required_consecutive_pass_count", 30) or 30)
        return [
            f"`nightly_pass_streak_count >= {required}` in `pm_release_gate_report.json`",
            "`basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`",
            "`github_actions_ci_streak_evidence.json` refreshed for the release signoff window",
        ]
    if namespace == "security" and "license" in code:
        return [
            "`license_status_closure_report.json.contract_pass == true`",
            "`license_status` is active and populated from approved product/legal evidence",
            "`security::license_status_not_configured` absent from `release_area_blockers`",
        ]
    return [
        f"`{namespace}::{code}` absent from `full_release_blockers`",
        "`full_release_gate_ready == true` after PM report regeneration",
    ]


def _reproduction_commands(*, namespace: str, code: str) -> list[str]:
    pm_report_command = (
        "python3 scripts/report_pm_release_gate.py "
        f"--out {DEFAULT_PM_REPORT} --out-md {DEFAULT_PM_REPORT_MD}"
    )
    if namespace == "basic_ci":
        return [
            f"python3 scripts/build_github_actions_ci_streak_evidence.py --out {DEFAULT_GITHUB_ACTIONS_CI_STREAK_EVIDENCE}",
            f"python3 scripts/build_ci_consecutive_pass_manifest.py --out {DEFAULT_CI_STREAK_MANIFEST}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    if namespace == "security" and "license" in code:
        return [
            f"python3 scripts/build_license_status_intake_packet.py --out {DEFAULT_LICENSE_STATUS_INTAKE_PACKET}",
            f"python3 scripts/build_license_status_closure_report.py --out {DEFAULT_LICENSE_STATUS_CLOSURE}",
            pm_report_command,
            f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
        ]
    return [
        pm_report_command,
        f"python3 scripts/build_pm_release_blocker_action_register.py --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD}",
    ]


def _owner_input_required(*, namespace: str, code: str) -> bool:
    return bool(
        (namespace == "basic_ci" and "consecutive_pass" in code)
        or (namespace == "security" and "license" in code)
    )


def _evidence_artifacts(row: dict[str, Any]) -> dict[str, str]:
    artifacts = {
        str(key): str(value)
        for key, value in _as_dict(row.get("artifacts")).items()
        if str(value)
    }
    artifacts["pm_release_gate_report"] = str(DEFAULT_PM_REPORT)
    return artifacts


def _augment_evidence_artifacts(*, namespace: str, code: str, artifacts: dict[str, str]) -> dict[str, str]:
    augmented = dict(artifacts)
    if namespace == "security" and "license" in code:
        augmented["license_status_intake_packet"] = str(DEFAULT_LICENSE_STATUS_INTAKE_PACKET)
    return augmented


def build_register(pm_report: Path = DEFAULT_PM_REPORT) -> dict[str, Any]:
    report = _load_json(pm_report)
    release_area_rows = _indexed_rows(_as_list(report.get("release_area_matrix")), "area")
    milestone_rows = _indexed_rows(_as_list(report.get("milestones")), "milestone")
    full_blockers = [str(row) for row in _as_list(report.get("full_release_blockers"))]
    if not full_blockers:
        full_blockers = [
            *[str(row) for row in _as_list(report.get("blockers"))],
            *[str(row) for row in _as_list(report.get("release_area_blockers"))],
        ]

    rows: list[dict[str, Any]] = []
    for blocker_id in full_blockers:
        namespace, code = _split_blocker(blocker_id)
        if namespace in release_area_rows:
            scope = "release_area"
            source_row = release_area_rows[namespace]
        elif namespace in milestone_rows:
            scope = "milestone"
            source_row = milestone_rows[namespace]
        else:
            scope = "unknown"
            source_row = {}
        title = str(source_row.get("title", namespace) or namespace)
        row = {
            "blocker_id": blocker_id,
            "blocker_code": code,
            "namespace": namespace,
            "scope": scope,
            "title": title,
            "status": "open",
            "owner_input_required": _owner_input_required(namespace=namespace, code=code),
            "owner_action": _owner_action(namespace=namespace, code=code, row=source_row),
            "claim_boundary": _claim_boundary(namespace=namespace, code=code, row=source_row),
            "acceptance_criteria": _acceptance_criteria(namespace=namespace, code=code, row=source_row),
            "reproduction_commands": _reproduction_commands(namespace=namespace, code=code),
            "evidence_artifacts": _augment_evidence_artifacts(
                namespace=namespace,
                code=code,
                artifacts=_evidence_artifacts(source_row),
            ),
            "evidence_snapshot": _as_dict(source_row.get("summary")),
        }
        rows.append(row)

    release_area_blockers = [str(row) for row in _as_list(report.get("release_area_blockers"))]
    milestone_blockers = [str(row) for row in _as_list(report.get("blockers"))]
    contract_pass = not rows
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "pm_release_gate_report": str(pm_report),
        "pm_summary_line": str(report.get("summary_line", "")),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PM_RELEASE_BLOCKERS_OPEN",
        "summary": {
            "open_blocker_count": len(rows),
            "release_area_blocker_count": len(release_area_blockers),
            "milestone_blocker_count": len(milestone_blockers),
            "owner_input_required_count": sum(1 for row in rows if row["owner_input_required"]),
            "full_release_gate_ready": bool(report.get("full_release_gate_ready", False)),
            "release_area_gate_ready": bool(report.get("release_area_gate_ready", False)),
            "limited_commercial_ready": bool(report.get("limited_commercial_ready", False)),
            "paid_pilot_candidate": bool(report.get("paid_pilot_candidate", False)),
        },
        "rows": rows,
        "next_actions": [row["owner_action"] for row in rows],
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Blocker Action Register",
        "",
        f"- `pm_summary_line`: `{payload['pm_summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `open_blocker_count`: `{payload['summary']['open_blocker_count']}`",
        "",
        "| Blocker | Scope | Owner Action | Acceptance |",
        "|---|---|---|---|",
    ]
    for row in payload["rows"]:
        acceptance = "<br>".join(str(item) for item in row.get("acceptance_criteria", []))
        lines.append(
            f"| `{row['blocker_id']}` | {row['scope']} | {row['owner_action']} | {acceptance} |"
        )
    if not payload["rows"]:
        lines.append("| none | release | No open PM release blockers. | PM release gate is ready. |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pm-report", type=Path, default=DEFAULT_PM_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_register(pm_report=args.pm_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
