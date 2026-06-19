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
DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET = Path(
    "implementation/phase1/release_evidence/productization/pm_owner_evidence_request_packet.json"
)
DEFAULT_PM_RELEASE_GATE_REVIEWER_HANDOFF = Path(
    "implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.json"
)
DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/pm_release_reproduction_command_audit.json"
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

COMMERCIAL_V1_SUPPORTED_SCOPE_TERMS = {
    "frame_families": [
        "frame structures",
        "frame families",
        "frame 구조",
        "골조 구조",
        "frame family",
    ],
    "wall_frame_families": [
        "wall-frame",
        "wall frame",
        "wall-frame structures",
        "벽-골조",
        "벽식 골조",
    ],
    "outrigger_families": [
        "outrigger",
        "outrigger systems",
        "outrigger structures",
        "아웃리거",
    ],
    "truss_families": [
        "truss",
        "truss systems",
        "truss structures",
        "트러스",
    ],
    "midas_interop": [
        "MIDAS interop",
        "MIDAS interoperability",
        "midas interop",
    ],
    "opensees_interop": [
        "OpenSees interop",
        "OpenSees interoperability",
        "opensees interop",
    ],
    "kds_interop": [
        "KDS interop",
        "KDS interoperability",
        "kds interop",
    ],
    "nonlinear_static": [
        "nonlinear static",
        "비선형 정적",
        "비선형정적",
        "nonlinear static analysis",
    ],
    "bounded_ndtha": [
        "bounded NDTHA",
        "Bounded NDTHA",
        "경계 NDTHA",
        "bounded non-linear time history",
    ],
    "residual_audit": [
        "residual audit",
        "residual auditing",
        "잔차 감사",
        "잔차 검증",
    ],
    "reference_comparison": [
        "reference comparison",
        "reference-comparison",
        "기준 비교",
        "reference benchmarking",
    ],
    "reviewer_package": [
        "reviewer package",
        "reviewer-package",
        "검토자 패키지",
        "reviewer handoff package",
    ],
}

COMMERCIAL_V1_SEPARATE_VALIDATION_EXCLUSIONS = {
    "rail_tunnel": [
        "rail/tunnel",
        "rail-tunnel",
        "rail tunnel",
        "철도/터널",
    ],
    "special_ssi": [
        "special SSI",
        "special-ssi",
        "special soil-structure interaction",
        "특수 SSI",
    ],
    "nonstandard_contact": [
        "nonstandard contact",
        "non-standard contact",
        "비표준 접촉",
    ],
    "legal_authority_approval_automation": [
        "legal/authority approval automation",
        "legal approval automation",
        "authority approval automation",
        "인허가 자동화",
    ],
    "special_construction_stages": [
        "special construction stages",
        "special-construction-stages",
        "special construction stage",
        "특수 시공 단계",
    ],
}

PROHIBITED_SCOPE_CLAIMS = {
    "limited_commercial_ready_true": [
        "limited_commercial_ready=true",
        "`limited_commercial_ready`: `true`",
        '"limited_commercial_ready": true',
    ],
    "limited_commercial_release_ready_true": [
        "limited_commercial_release_ready=true",
        "`limited_commercial_release_ready`: `true`",
        '"limited_commercial_release_ready": true',
    ],
    "ga_enterprise_ready_true": [
        "ga_enterprise_ready=true",
        "`ga_enterprise_ready`: `true`",
        '"ga_enterprise_ready": true',
    ],
    "full_commercial_replacement_ready_true": [
        "full_commercial_replacement_ready=true",
        "`full_commercial_replacement_ready`: `true`",
        '"full_commercial_replacement_ready": true',
    ],
    "engineer_of_record_replacement": [
        "engineer-of-record replacement ready",
        "structural engineer replacement ready",
        "구조기술사 검토 대체",
        "기술사 검토 대체",
    ],
    "autonomous_approval": [
        "autonomous approval",
        "automatic permit approval",
        "인허가 자동 승인",
        "자동 승인",
    ],
}

REQUIRED_SUPPORT_BUNDLE_SECTIONS = (
    "pm_owner_evidence_request_packet",
    "pm_release_gate_reviewer_handoff",
    "pm_release_reproduction_command_audit",
)


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


def _support_bundle_section_rows(support_bundle: Path) -> list[dict[str, Any]]:
    payload = _load_json(support_bundle)
    optional_sections = payload.get("optional_sections")
    optional_sections = optional_sections if isinstance(optional_sections, dict) else {}
    return [
        {
            "label": label,
            "present": bool(str(optional_sections.get(label, "") or "")),
            "redacted_bundle_path": str(optional_sections.get(label, "") or ""),
        }
        for label in REQUIRED_SUPPORT_BUNDLE_SECTIONS
    ]


def build_report(
    *,
    scope_source: Path = DEFAULT_SCOPE_SOURCE,
    pm_release_gate_report: Path = DEFAULT_PM_RELEASE_GATE_REPORT,
    support_bundle: Path = DEFAULT_SUPPORT_BUNDLE,
    pm_blocker_register: Path = DEFAULT_PM_BLOCKER_REGISTER,
    pm_owner_evidence_request_packet: Path = DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET,
    pm_release_gate_reviewer_handoff: Path = DEFAULT_PM_RELEASE_GATE_REVIEWER_HANDOFF,
    pm_release_reproduction_command_audit: Path = DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT,
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
    supported_scope_rows = [
        {
            "check": check,
            "pass": _contains_any(scope_text, phrases),
            "accepted_phrases": phrases,
        }
        for check, phrases in COMMERCIAL_V1_SUPPORTED_SCOPE_TERMS.items()
    ]
    separate_validation_exclusion_rows = [
        {
            "check": check,
            "pass": _contains_any(scope_text, phrases),
            "accepted_phrases": phrases,
        }
        for check, phrases in COMMERCIAL_V1_SEPARATE_VALIDATION_EXCLUSIONS.items()
    ]
    forbidden_claim_rows = [
        {
            "check": check,
            "pass": not _contains_any(scope_text, phrases),
            "prohibited_phrases": phrases,
        }
        for check, phrases in PROHIBITED_SCOPE_CLAIMS.items()
    ]
    artifact_rows = [
        _artifact_row("pm_release_gate_report", pm_release_gate_report),
        _artifact_row("support_bundle_manifest", support_bundle, required_pass=True),
        _artifact_row("pm_owner_evidence_request_packet", pm_owner_evidence_request_packet, required_pass=True),
        _artifact_row("pm_release_gate_reviewer_handoff", pm_release_gate_reviewer_handoff, required_pass=True),
        _artifact_row(
            "pm_release_reproduction_command_audit",
            pm_release_reproduction_command_audit,
            required_pass=True,
        ),
        _artifact_row("pm_release_blocker_action_register", pm_blocker_register),
        _artifact_row("ci_streak_intake_packet", ci_streak_intake_packet),
        _artifact_row("license_status_intake_packet", license_status_intake_packet),
        _artifact_row("ga_enterprise_readiness_report", ga_enterprise_readiness_report),
    ]
    support_bundle_section_rows = _support_bundle_section_rows(support_bundle)
    missing_terms = [row["check"] for row in term_rows if not row["pass"]]
    missing_supported_scope = [row["check"] for row in supported_scope_rows if not row["pass"]]
    missing_separate_validation_exclusions = [
        row["check"]
        for row in separate_validation_exclusion_rows
        if not row["pass"]
    ]
    present_forbidden_claims = [row["check"] for row in forbidden_claim_rows if not row["pass"]]
    missing_artifacts = [row["label"] for row in artifact_rows if not row["present"]]
    missing_support_sections = [
        row["label"] for row in support_bundle_section_rows if not row["present"]
    ]
    failed_required_artifacts = [
        row["label"]
        for row in artifact_rows
        if row["required_pass"] and not row["contract_pass"]
    ]
    blockers = [
        *(f"scope_term_missing:{label}" for label in missing_terms),
        *(f"commercial_v1_supported_scope_missing:{label}" for label in missing_supported_scope),
        *(
            f"commercial_v1_separate_validation_exclusion_missing:{label}"
            for label in missing_separate_validation_exclusions
        ),
        *(f"forbidden_scope_claim_present:{label}" for label in present_forbidden_claims),
        *(f"evidence_artifact_missing:{label}" for label in missing_artifacts),
        *(f"support_bundle_section_missing:{label}" for label in missing_support_sections),
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
            f"commercial_v1_supported_scope="
            f"{len(supported_scope_rows) - len(missing_supported_scope)}/{len(supported_scope_rows)} | "
            f"commercial_v1_separate_validation_exclusions="
            f"{len(separate_validation_exclusion_rows) - len(missing_separate_validation_exclusions)}"
            f"/{len(separate_validation_exclusion_rows)} | "
            f"artifacts={len(artifact_rows) - len(missing_artifacts)}/{len(artifact_rows)}"
        ),
        "checks": {
            "scope_source_present": scope_source.exists(),
            "all_required_scope_terms_present": not missing_terms,
            "commercial_v1_supported_scope_present": not missing_supported_scope,
            "commercial_v1_separate_validation_exclusions_present": (
                not missing_separate_validation_exclusions
            ),
            "no_prohibited_scope_claims_present": not present_forbidden_claims,
            "evidence_package_artifacts_present": not missing_artifacts,
            "support_bundle_required_sections_present": not missing_support_sections,
            "required_evidence_package_artifacts_green": not failed_required_artifacts,
        },
        "summary": {
            "scope_source": str(scope_source),
            "required_scope_term_count": len(term_rows),
            "required_scope_term_pass_count": len(term_rows) - len(missing_terms),
            "commercial_v1_supported_scope_count": len(supported_scope_rows),
            "commercial_v1_supported_scope_pass_count": (
                len(supported_scope_rows) - len(missing_supported_scope)
            ),
            "commercial_v1_separate_validation_exclusion_count": (
                len(separate_validation_exclusion_rows)
            ),
            "commercial_v1_separate_validation_exclusion_pass_count": (
                len(separate_validation_exclusion_rows)
                - len(missing_separate_validation_exclusions)
            ),
            "prohibited_scope_claim_count": len(forbidden_claim_rows),
            "prohibited_scope_claim_present_count": len(present_forbidden_claims),
            "evidence_artifact_count": len(artifact_rows),
            "evidence_artifact_present_count": len(artifact_rows) - len(missing_artifacts),
            "support_bundle_required_section_count": len(support_bundle_section_rows),
            "support_bundle_required_section_present_count": (
                len(support_bundle_section_rows) - len(missing_support_sections)
            ),
            "owner_action": (
                "Keep paid-pilot product/contract language constrained to review assist, specified "
                "structure families/workflows, and attached engine/reviewer evidence package. "
                "Commercial v1 supported scope and separate-validation exclusions must stay visible."
            ),
        },
        "scope_term_rows": term_rows,
        "commercial_v1_supported_scope_rows": supported_scope_rows,
        "commercial_v1_separate_validation_exclusion_rows": separate_validation_exclusion_rows,
        "forbidden_claim_rows": forbidden_claim_rows,
        "artifact_rows": artifact_rows,
        "support_bundle_section_rows": support_bundle_section_rows,
        "blockers": blockers,
        "claim_boundary": (
            "This guard validates scoped paid-pilot language and evidence-package references. It does not "
            "create legal approval, customer acceptance, or GA/Enterprise readiness. Commercial v1 supported "
            "scope and separate-validation exclusions describe the productization surface, not external V&V, "
            "authority approval, or signoff evidence."
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
    lines.extend(
        [
            "",
            "| Commercial v1 Supported Scope | Pass |",
            "|---|---|",
        ]
    )
    for row in payload["commercial_v1_supported_scope_rows"]:
        lines.append(f"| `{row['check']}` | `{row['pass']}` |")
    lines.extend(
        [
            "",
            "| Commercial v1 Separate-Validation Exclusion | Pass |",
            "|---|---|",
        ]
    )
    for row in payload["commercial_v1_separate_validation_exclusion_rows"]:
        lines.append(f"| `{row['check']}` | `{row['pass']}` |")
    lines.extend(["", "| Forbidden Claim Check | Pass |", "|---|---|"])
    for row in payload["forbidden_claim_rows"]:
        lines.append(f"| `{row['check']}` | `{row['pass']}` |")
    lines.extend(["", "| Evidence Artifact | Present | Required Pass | Contract Pass |", "|---|---|---|---|"])
    for row in payload["artifact_rows"]:
        lines.append(
            f"| `{row['label']}` | `{row['present']}` | `{row['required_pass']}` | `{row['contract_pass']}` |"
        )
    lines.extend(["", "| Support Bundle Section | Present | Redacted Bundle Path |", "|---|---|---|"])
    for row in payload["support_bundle_section_rows"]:
        lines.append(
            f"| `{row['label']}` | `{row['present']}` | `{row['redacted_bundle_path']}` |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-source", type=Path, default=DEFAULT_SCOPE_SOURCE)
    parser.add_argument("--pm-release-gate-report", type=Path, default=DEFAULT_PM_RELEASE_GATE_REPORT)
    parser.add_argument("--support-bundle", type=Path, default=DEFAULT_SUPPORT_BUNDLE)
    parser.add_argument("--pm-blocker-register", type=Path, default=DEFAULT_PM_BLOCKER_REGISTER)
    parser.add_argument("--pm-owner-evidence-request-packet", type=Path, default=DEFAULT_PM_OWNER_EVIDENCE_REQUEST_PACKET)
    parser.add_argument("--pm-release-gate-reviewer-handoff", type=Path, default=DEFAULT_PM_RELEASE_GATE_REVIEWER_HANDOFF)
    parser.add_argument(
        "--pm-release-reproduction-command-audit",
        type=Path,
        default=DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT,
    )
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
        pm_owner_evidence_request_packet=args.pm_owner_evidence_request_packet,
        pm_release_gate_reviewer_handoff=args.pm_release_gate_reviewer_handoff,
        pm_release_reproduction_command_audit=args.pm_release_reproduction_command_audit,
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
