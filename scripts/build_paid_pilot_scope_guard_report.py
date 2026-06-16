#!/usr/bin/env python3
"""Validate constrained paid-pilot scope language and evidence-package references."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "paid-pilot-scope-guard-report.v1"
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/paid_pilot_scope_guard_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_SCOPE_SOURCE = Path("docs/pm-release-gate-milestones.md")
DEFAULT_PM_RELEASE_GATE_REPORT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_SUPPORT_BUNDLE = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_PM_BLOCKER_REGISTER = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
)
DEFAULT_CI_STREAK_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json"
)
DEFAULT_LICENSE_STATUS_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/license_status_intake_packet.json"
)
DEFAULT_GA_ENTERPRISE_READINESS_REPORT = Path(
    "implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.json"
)


REQUIRED_SCOPE_TERMS = {
    "review_assist_boundary": ["검토 보조", "review-assist", "review assist", "engineer-in-loop"],
    "specified_structure_families": ["지정된 구조군", "specified structure families", "specified-structure-families"],
    "specified_workflow": ["지정된 workflow", "specified workflow", "specified-workflows"],
    "engine_reviewer_evidence_package": [
        "engine/reviewer evidence package",
        "engine-and-reviewer-evidence-package",
    ],
    "unsupported_or_missing_evidence_blocker": [
        "unsupported 또는 missing evidence 항목은 pass가 아니라 blocker",
        "unsupported or missing evidence",
    ],
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _contains_any(text: str, phrases: list[str]) -> bool:
    lowered = text.lower()
    return any(phrase.lower() in lowered for phrase in phrases)


def _artifact_row(label: str, path: Path, *, required_pass: bool = False) -> dict[str, Any]:
    payload = _load_json(path)
    return {
        "label": label,
        "path": str(path),
        "present": path.exists(),
        "required_pass": required_pass,
        "contract_pass": _reason_pass(payload) if path.exists() else False,
    }


def build_report(
    *,
    scope_source: Path = DEFAULT_SCOPE_SOURCE,
    pm_release_gate_report: Path = DEFAULT_PM_RELEASE_GATE_REPORT,
    support_bundle: Path = DEFAULT_SUPPORT_BUNDLE,
    pm_blocker_register: Path = DEFAULT_PM_BLOCKER_REGISTER,
    ci_streak_intake_packet: Path = DEFAULT_CI_STREAK_INTAKE_PACKET,
    license_status_intake_packet: Path = DEFAULT_LICENSE_STATUS_INTAKE_PACKET,
    ga_enterprise_readiness_report: Path = DEFAULT_GA_ENTERPRISE_READINESS_REPORT,
) -> dict[str, Any]:
    scope_text = _read_text(scope_source)
    term_rows = [
        {
            "check": check,
            "pass": _contains_any(scope_text, phrases),
            "accepted_phrases": phrases,
        }
        for check, phrases in REQUIRED_SCOPE_TERMS.items()
    ]
    artifact_rows = [
        _artifact_row("pm_release_gate_report", pm_release_gate_report),
        _artifact_row("support_bundle_manifest", support_bundle, required_pass=True),
        _artifact_row("pm_release_blocker_action_register", pm_blocker_register),
        _artifact_row("ci_streak_intake_packet", ci_streak_intake_packet),
        _artifact_row("license_status_intake_packet", license_status_intake_packet),
        _artifact_row("ga_enterprise_readiness_report", ga_enterprise_readiness_report),
    ]
    missing_terms = [row["check"] for row in term_rows if not row["pass"]]
    missing_artifacts = [row["label"] for row in artifact_rows if not row["present"]]
    failed_required_artifacts = [
        row["label"]
        for row in artifact_rows
        if row["required_pass"] and not row["contract_pass"]
    ]
    blockers = [
        *(f"scope_term_missing:{label}" for label in missing_terms),
        *(f"evidence_artifact_missing:{label}" for label in missing_artifacts),
        *(f"required_evidence_artifact_not_green:{label}" for label in failed_required_artifacts),
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PAID_PILOT_SCOPE_GUARD_BLOCKED",
        "summary_line": (
            f"Paid pilot scope guard: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"scope_terms={len(term_rows) - len(missing_terms)}/{len(term_rows)} | "
            f"artifacts={len(artifact_rows) - len(missing_artifacts)}/{len(artifact_rows)}"
        ),
        "checks": {
            "scope_source_present": scope_source.exists(),
            "all_required_scope_terms_present": not missing_terms,
            "evidence_package_artifacts_present": not missing_artifacts,
            "required_evidence_package_artifacts_green": not failed_required_artifacts,
        },
        "summary": {
            "scope_source": str(scope_source),
            "required_scope_term_count": len(term_rows),
            "required_scope_term_pass_count": len(term_rows) - len(missing_terms),
            "evidence_artifact_count": len(artifact_rows),
            "evidence_artifact_present_count": len(artifact_rows) - len(missing_artifacts),
            "owner_action": (
                "Keep paid-pilot product/contract language constrained to review assist, specified "
                "structure families/workflows, and attached engine/reviewer evidence package."
            ),
        },
        "scope_term_rows": term_rows,
        "artifact_rows": artifact_rows,
        "blockers": blockers,
        "claim_boundary": (
            "This guard validates scoped paid-pilot language and evidence-package references. It does not "
            "create legal approval, customer acceptance, or GA/Enterprise readiness."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Paid Pilot Scope Guard Report",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        "",
        "| Scope Check | Pass |",
        "|---|---|",
    ]
    for row in payload["scope_term_rows"]:
        lines.append(f"| `{row['check']}` | `{row['pass']}` |")
    lines.extend(["", "| Evidence Artifact | Present | Required Pass | Contract Pass |", "|---|---|---|---|"])
    for row in payload["artifact_rows"]:
        lines.append(
            f"| `{row['label']}` | `{row['present']}` | `{row['required_pass']}` | `{row['contract_pass']}` |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-source", type=Path, default=DEFAULT_SCOPE_SOURCE)
    parser.add_argument("--pm-release-gate-report", type=Path, default=DEFAULT_PM_RELEASE_GATE_REPORT)
    parser.add_argument("--support-bundle", type=Path, default=DEFAULT_SUPPORT_BUNDLE)
    parser.add_argument("--pm-blocker-register", type=Path, default=DEFAULT_PM_BLOCKER_REGISTER)
    parser.add_argument("--ci-streak-intake-packet", type=Path, default=DEFAULT_CI_STREAK_INTAKE_PACKET)
    parser.add_argument("--license-status-intake-packet", type=Path, default=DEFAULT_LICENSE_STATUS_INTAKE_PACKET)
    parser.add_argument("--ga-enterprise-readiness-report", type=Path, default=DEFAULT_GA_ENTERPRISE_READINESS_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        scope_source=args.scope_source,
        pm_release_gate_report=args.pm_release_gate_report,
        support_bundle=args.support_bundle,
        pm_blocker_register=args.pm_blocker_register,
        ci_streak_intake_packet=args.ci_streak_intake_packet,
        license_status_intake_packet=args.license_status_intake_packet,
        ga_enterprise_readiness_report=args.ga_enterprise_readiness_report,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
