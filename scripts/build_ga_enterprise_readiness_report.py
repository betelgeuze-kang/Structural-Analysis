#!/usr/bin/env python3
"""Build GA/Enterprise readiness evidence without substituting for owner signoff."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ga-enterprise-readiness-report.v1"
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_MEASURED_BREADTH = Path(
    "implementation/phase1/release_evidence/productization/measured_benchmark_breadth_report.json"
)
DEFAULT_RELEASE_REGISTRY = Path("implementation/phase1/release/release_registry.json")
DEFAULT_SUPPORT_BUNDLE = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_VALIDATION_MANUAL = Path("docs/commercial-structural-solver-product-gap-ledger.md")
DEFAULT_INDEPENDENT_VV_ATTESTATION = Path(
    "implementation/phase1/release_evidence/productization/independent_vv_attestation.json"
)
DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF = Path(
    "implementation/phase1/release_evidence/productization/family_validation_manual_signoff.json"
)
DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA = Path(
    "implementation/phase1/release_evidence/productization/customer_audit_failure_bundle_sla.json"
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(payload.get("summary"))


def build_report(
    *,
    measured_benchmark_breadth: Path = DEFAULT_MEASURED_BREADTH,
    release_registry: Path = DEFAULT_RELEASE_REGISTRY,
    support_bundle: Path = DEFAULT_SUPPORT_BUNDLE,
    validation_manual: Path = DEFAULT_VALIDATION_MANUAL,
    independent_vv_attestation: Path = DEFAULT_INDEPENDENT_VV_ATTESTATION,
    family_validation_manual_signoff: Path = DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF,
    customer_audit_failure_bundle_sla: Path = DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA,
    ga_validation_cases: int = 300,
) -> dict[str, Any]:
    measured = _load_json(measured_benchmark_breadth)
    registry = _load_json(release_registry)
    support = _load_json(support_bundle)
    independent_vv = _load_json(independent_vv_attestation)
    family_signoff = _load_json(family_validation_manual_signoff)
    customer_sla = _load_json(customer_audit_failure_bundle_sla)

    measured_cases = _as_int(_summary(measured).get("measured_case_count"), 0)
    registry_summary = _summary(registry)
    support_checks = _as_dict(support.get("checks"))
    checks = {
        "ga_validation_case_threshold_pass": measured_cases >= ga_validation_cases,
        "signed_release_registry_pass": bool(
            _reason_pass(registry)
            and str(registry_summary.get("signing_algorithm", "")).lower() == "ed25519"
        ),
        "support_failure_bundle_export_pass": bool(
            _reason_pass(support)
            and support_checks.get("redaction_self_test_pass", False)
            and support_checks.get("bundle_roundtrip_test_pass", False)
        ),
        "validation_manual_present": validation_manual.exists(),
        "independent_vv_attestation_present": independent_vv_attestation.exists(),
        "independent_vv_attestation_pass": _reason_pass(independent_vv),
        "family_validation_manual_signoff_present": family_validation_manual_signoff.exists(),
        "family_validation_manual_signoff_pass": _reason_pass(family_signoff),
        "customer_audit_failure_bundle_sla_present": customer_audit_failure_bundle_sla.exists(),
        "customer_audit_failure_bundle_sla_pass": _reason_pass(customer_sla),
    }
    blockers = [
        *(["ga_validation_case_count_lt_300"] if not checks["ga_validation_case_threshold_pass"] else []),
        *(["signed_release_registry_missing_or_failed"] if not checks["signed_release_registry_pass"] else []),
        *(["support_failure_bundle_missing_or_failed"] if not checks["support_failure_bundle_export_pass"] else []),
        *(["family_validation_manual_missing"] if not checks["validation_manual_present"] else []),
        *(["independent_vv_missing"] if not checks["independent_vv_attestation_pass"] else []),
        *(
            ["family_validation_manual_signoff_missing"]
            if not checks["family_validation_manual_signoff_pass"]
            else []
        ),
        *(
            ["customer_audit_failure_bundle_sla_missing"]
            if not checks["customer_audit_failure_bundle_sla_pass"]
            else []
        ),
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_GA_ENTERPRISE_EVIDENCE_PENDING",
        "summary_line": (
            f"GA enterprise readiness: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"cases={measured_cases}/{ga_validation_cases} | "
            f"signed_registry={checks['signed_release_registry_pass']} | "
            f"support_bundle={checks['support_failure_bundle_export_pass']} | "
            f"independent_vv={checks['independent_vv_attestation_pass']} | "
            f"family_signoff={checks['family_validation_manual_signoff_pass']} | "
            f"customer_sla={checks['customer_audit_failure_bundle_sla_pass']}"
        ),
        "checks": checks,
        "blockers": blockers,
        "summary": {
            "measured_case_count": measured_cases,
            "ga_validation_case_threshold": ga_validation_cases,
            "release_registry_signing_algorithm": str(registry_summary.get("signing_algorithm", "")),
            "support_bundle_missing_required_count": _as_int(support_checks.get("missing_required_count"), -1),
            "owner_action": (
                "Attach independent V&V attestation, family validation-manual signoff, and customer "
                "audit/failure-bundle/SLA approval evidence before GA/Enterprise release."
            ),
        },
        "owner_handoff_rows": [
            {
                "blocker": "independent_vv_missing",
                "owner_action": "Attach third-party or independent V&V attestation with scope, case set, date, and approver.",
                "evidence_path": str(independent_vv_attestation),
                "acceptance": "`independent_vv_attestation.contract_pass == true`",
            },
            {
                "blocker": "family_validation_manual_signoff_missing",
                "owner_action": "Attach family-by-family validation manual signoff tied to the release registry.",
                "evidence_path": str(family_validation_manual_signoff),
                "acceptance": "`family_validation_manual_signoff.contract_pass == true`",
            },
            {
                "blocker": "customer_audit_failure_bundle_sla_missing",
                "owner_action": "Attach customer audit/failure-bundle export acceptance and support SLA evidence.",
                "evidence_path": str(customer_audit_failure_bundle_sla),
                "acceptance": "`customer_audit_failure_bundle_sla.contract_pass == true`",
            },
        ],
        "artifacts": {
            "measured_benchmark_breadth": str(measured_benchmark_breadth),
            "release_registry": str(release_registry),
            "support_bundle": str(support_bundle),
            "validation_manual": str(validation_manual),
            "independent_vv_attestation": str(independent_vv_attestation),
            "family_validation_manual_signoff": str(family_validation_manual_signoff),
            "customer_audit_failure_bundle_sla": str(customer_audit_failure_bundle_sla),
        },
        "validation_commands": [
            f"python3 scripts/build_ga_enterprise_readiness_report.py --out {DEFAULT_OUT}",
            "python3 scripts/report_pm_release_gate.py "
            " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
            " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        ],
        "claim_boundary": (
            "This report is a readiness/evidence gate. It does not create independent V&V, legal approval, "
            "customer acceptance, or support SLA commitments."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GA Enterprise Readiness Report",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        "",
        "| Blocker | Owner Action | Evidence | Acceptance |",
        "|---|---|---|---|",
    ]
    for row in payload["owner_handoff_rows"]:
        status = "closed" if row["blocker"] not in payload["blockers"] else "open"
        lines.append(
            f"| `{row['blocker']}` ({status}) | {row['owner_action']} | "
            f"`{row['evidence_path']}` | {row['acceptance']} |"
        )
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measured-benchmark-breadth", type=Path, default=DEFAULT_MEASURED_BREADTH)
    parser.add_argument("--release-registry", type=Path, default=DEFAULT_RELEASE_REGISTRY)
    parser.add_argument("--support-bundle", type=Path, default=DEFAULT_SUPPORT_BUNDLE)
    parser.add_argument("--validation-manual", type=Path, default=DEFAULT_VALIDATION_MANUAL)
    parser.add_argument("--independent-vv-attestation", type=Path, default=DEFAULT_INDEPENDENT_VV_ATTESTATION)
    parser.add_argument(
        "--family-validation-manual-signoff",
        type=Path,
        default=DEFAULT_FAMILY_VALIDATION_MANUAL_SIGNOFF,
    )
    parser.add_argument(
        "--customer-audit-failure-bundle-sla",
        type=Path,
        default=DEFAULT_CUSTOMER_AUDIT_FAILURE_BUNDLE_SLA,
    )
    parser.add_argument("--ga-validation-cases", type=int, default=300)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        measured_benchmark_breadth=args.measured_benchmark_breadth,
        release_registry=args.release_registry,
        support_bundle=args.support_bundle,
        validation_manual=args.validation_manual,
        independent_vv_attestation=args.independent_vv_attestation,
        family_validation_manual_signoff=args.family_validation_manual_signoff,
        customer_audit_failure_bundle_sla=args.customer_audit_failure_bundle_sla,
        ga_validation_cases=args.ga_validation_cases,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
