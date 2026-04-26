#!/usr/bin/env python3
"""Promote case-onepage attestation templates into real manifest inputs.

This helper is intentionally explicit: it turns case-level reviewer/authority
placeholders into concrete manifests that the external validation workflow can
load on the next bundle generation. The default mode is suitable for informal
friend/demo review so we can exercise the full workflow without pretending a
formal authority submission happened.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KICKOFF_DIR = REPO_ROOT / "implementation/phase1/release/external_benchmark_kickoff"
DEFAULT_TEMPLATE_DIRNAME = "case_onepage_attestation_templates"
DEFAULT_MANIFEST_DIRNAME = "case_onepage_attestation_manifests"
DEFAULT_REPORT_PATH = (
    REPO_ROOT / "implementation/phase1/release/external_benchmark_kickoff/case_onepage_attestation_manifest_generation_report.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} is not a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _preferred_template_paths(template_dir: Path) -> list[Path]:
    grouped: dict[str, list[Path]] = {}
    for path in sorted(template_dir.glob("*.template.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        case = payload.get("case") if isinstance(payload.get("case"), dict) else {}
        case_id = str(case.get("case_id", "") or "").strip()
        if not case_id or case_id == "sample_case":
            continue
        grouped.setdefault(case_id, []).append(path)

    selected: list[Path] = []
    for _, paths in sorted(grouped.items()):
        preferred = sorted(
            paths,
            key=lambda p: (
                p.name.startswith("00."),
                p.name,
            ),
        )[0]
        selected.append(preferred)
    return selected


def _build_manifest_payload(
    template_payload: dict[str, Any],
    *,
    session_id: str,
    reviewer_name: str,
    reviewer_role: str,
    reviewer_license_id: str,
    reviewer_signature_name: str,
    decision_basis: str,
    authority_name: str,
    authority_receipt_note: str,
    approval_signature_name: str,
    attested_at_utc: str,
    case_index: int,
) -> dict[str, Any]:
    case = template_payload.get("case") if isinstance(template_payload.get("case"), dict) else {}
    case_id = str(case.get("case_id", "") or "").strip() or f"case-{case_index:02d}"
    return {
        "schema_version": "1.0",
        "generated_at": attested_at_utc,
        "contract_pass": True,
        "reason_code": "PASS_CASE_ATTESTATION_MANIFEST_READY",
        "reason": "real values supplied for case-level reviewer/authority workflow input",
        "manifest_mode": "friend_demo_review",
        "case": case,
        "attestation": {
            "reviewer_name": reviewer_name,
            "reviewer_role": reviewer_role,
            "reviewer_license_id": reviewer_license_id,
            "reviewer_signature_name": reviewer_signature_name,
            "decision_basis": f"{decision_basis} | case_id={case_id}",
            "review_session_id": session_id,
            "attested_at_utc": attested_at_utc,
            "authority_name": authority_name,
            "authority_receipt_id": f"DEMO-RECEIPT-{case_index:02d}-{case_id.upper()}",
            "authority_receipt_issued_at_utc": attested_at_utc,
            "authority_receipt_note": f"{authority_receipt_note} | case_id={case_id}",
            "approval_signature_name": approval_signature_name,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kickoff-dir", default=str(DEFAULT_KICKOFF_DIR))
    parser.add_argument("--template-dirname", default=DEFAULT_TEMPLATE_DIRNAME)
    parser.add_argument("--manifest-dirname", default=DEFAULT_MANIFEST_DIRNAME)
    parser.add_argument("--reviewer-name", default="Informal Friend Reviewer")
    parser.add_argument("--reviewer-role", default="informal external reviewer")
    parser.add_argument("--reviewer-license-id", default="demo-review-no-license")
    parser.add_argument("--reviewer-signature-name", default="")
    parser.add_argument(
        "--decision-basis",
        default="informal friend walkthrough of signed external benchmark bundle for demo validation",
    )
    parser.add_argument("--authority-name", default="informal demo receipt authority")
    parser.add_argument(
        "--authority-receipt-note",
        default="non-regulatory demo receipt recorded for external walkthrough",
    )
    parser.add_argument("--approval-signature-name", default="")
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT_PATH))
    args = parser.parse_args()

    kickoff_dir = Path(args.kickoff_dir)
    template_dir = kickoff_dir / args.template_dirname
    manifest_dir = kickoff_dir / args.manifest_dirname
    manifest_dir.mkdir(parents=True, exist_ok=True)

    templates = _preferred_template_paths(template_dir)
    now = datetime.now(timezone.utc).isoformat()
    session_id = f"friend-demo-review-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    reviewer_signature_name = args.reviewer_signature_name or args.reviewer_name
    approval_signature_name = args.approval_signature_name or reviewer_signature_name

    rows: list[dict[str, Any]] = []
    for idx, template_path in enumerate(templates, start=1):
        template_payload = _load_json(template_path)
        manifest_path = manifest_dir / template_path.name.replace(".template.json", ".manifest.json")
        manifest_payload = _build_manifest_payload(
            template_payload,
            session_id=session_id,
            reviewer_name=args.reviewer_name,
            reviewer_role=args.reviewer_role,
            reviewer_license_id=args.reviewer_license_id,
            reviewer_signature_name=reviewer_signature_name,
            decision_basis=args.decision_basis,
            authority_name=args.authority_name,
            authority_receipt_note=args.authority_receipt_note,
            approval_signature_name=approval_signature_name,
            attested_at_utc=now,
            case_index=idx,
        )
        _write_json(manifest_path, manifest_payload)
        case = manifest_payload.get("case") if isinstance(manifest_payload.get("case"), dict) else {}
        rows.append(
            {
                "case_id": str(case.get("case_id", "") or ""),
                "case_label": str(case.get("case_label", "") or ""),
                "template_json": str(template_path),
                "manifest_json": str(manifest_path),
                "authority_receipt_id": str(
                    ((manifest_payload.get("attestation") or {}).get("authority_receipt_id", "")) or ""
                ),
            }
        )

    report = {
        "schema_version": "1.0",
        "generated_at": now,
        "contract_pass": bool(rows),
        "reason_code": "PASS" if rows else "ERR_NO_TEMPLATES",
        "summary": {
            "template_count": len(templates),
            "manifest_count": len(rows),
            "session_id": session_id,
            "reviewer_name": args.reviewer_name,
            "reviewer_role": args.reviewer_role,
            "reviewer_license_id": args.reviewer_license_id,
            "authority_name": args.authority_name,
        },
        "rows": rows,
    }
    _write_json(Path(args.report_out), report)


if __name__ == "__main__":
    main()
