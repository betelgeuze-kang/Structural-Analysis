#!/usr/bin/env python3
"""Fill license_status.json from explicit product/legal approval metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_license_status_closure_report as closure_report  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "license-status-approval-fill.v1"
DEFAULT_OUT = Path("implementation/phase1/release/support_bundle/license_status.json")
DEFAULT_REPORT_OUT = Path(
    "implementation/phase1/release_evidence/productization/license_status.fill_report.json"
)
DEFAULT_PRODUCT_SCOPE = (
    "review-assist",
    "specified-structure-families",
    "specified-workflows",
    "engine-and-reviewer-evidence-package",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _deduped(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _license_status_payload(
    *,
    status: str,
    tier: str,
    license_id: str,
    issuer: str,
    approver_role: str,
    approval_ref: str,
    approved_at_utc: str,
    evidence_ref: str,
    product_scope: list[str],
    expires_at_utc: str,
    perpetual: bool,
    note: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "tier": tier,
        "license_id": license_id,
        "issuer": issuer,
        "approver_role": approver_role,
        "approval_ref": approval_ref,
        "approved_at_utc": approved_at_utc,
        "evidence_ref": evidence_ref,
        "product_scope": _deduped(product_scope or list(DEFAULT_PRODUCT_SCOPE)),
        "template_only": False,
        "note": note,
    }
    if perpetual:
        payload["perpetual"] = True
    else:
        payload["expires_at_utc"] = expires_at_utc
    return payload


def _blocked_license_status(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "status": "not_configured",
        "requested_status": payload["status"],
        "note": (
            "Fail-closed: the requested status was not activated because the "
            "cryptographic rights-holder decision contract did not pass."
        ),
    }


def _stage_payload(*, target: Path, payload: dict[str, Any]) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        staged = Path(handle.name)
        handle.write(_json_text(payload))
        handle.flush()
        os.fsync(handle.fileno())
    return staged


def _atomic_write_payload(*, target: Path, payload: dict[str, Any]) -> None:
    staged = _stage_payload(target=target, payload=payload)
    try:
        os.replace(staged, target)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass


def fill_license_status(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    template_path: Path = closure_report.DEFAULT_TEMPLATE,
    status: str,
    tier: str,
    license_id: str,
    issuer: str,
    approver_role: str,
    approval_ref: str,
    approved_at_utc: str,
    evidence_ref: str,
    product_scope: list[str] | None = None,
    expires_at_utc: str = "",
    perpetual: bool = False,
    note: str = "Populated from explicit product/legal approval metadata.",
    rights_holder_trust_root_path: Path = (
        closure_report.DEFAULT_RIGHTS_HOLDER_TRUST_ROOT
    ),
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_out = _resolve(repo_root, out)
    canonical_out = repo_root / closure_report.CANONICAL_LICENSE_STATUS
    output_path_canonical = bool(
        Path(os.path.abspath(resolved_out)) == canonical_out
    )
    license_status = _license_status_payload(
        status=status,
        tier=tier,
        license_id=license_id,
        issuer=issuer,
        approver_role=approver_role,
        approval_ref=approval_ref,
        approved_at_utc=approved_at_utc,
        evidence_ref=evidence_ref,
        product_scope=product_scope or list(DEFAULT_PRODUCT_SCOPE),
        expires_at_utc=expires_at_utc,
        perpetual=perpetual,
        note=note,
    )
    written_license_status = _blocked_license_status(license_status)
    validation: dict[str, Any]
    temporary_path: Path | None = None
    if not output_path_canonical:
        validation = {
            "status": "blocked",
            "reason_code": "ERR_LICENSE_STATUS_OUTPUT_NOT_CANONICAL",
            "contract_pass": False,
            "blockers": ["license_status_output_path_not_canonical"],
            "summary_line": (
                "License status: BLOCKED | output path is not the canonical "
                "repository status path"
            ),
        }
    else:
        try:
            resolved_out.parent.mkdir(parents=True, exist_ok=True)
            if resolved_out.parent.resolve() != canonical_out.parent:
                raise OSError("canonical license status parent traverses a symlink")
            temporary_path = _stage_payload(
                target=resolved_out,
                payload=license_status,
            )
            staged_validation = closure_report.build_report(
                license_status_path=temporary_path,
                template_path=template_path,
                repo_root=repo_root,
                rights_holder_trust_root_path=rights_holder_trust_root_path,
                allow_staged_canonical_status=True,
            )
            staged_validation_pass = bool(
                staged_validation.get("checks", {}).get(
                    "license_status_staged_validation_pass"
                )
                is True
            )
            if staged_validation_pass:
                os.replace(temporary_path, resolved_out)
                temporary_path = None
                validation = closure_report.build_report(
                    license_status_path=closure_report.CANONICAL_LICENSE_STATUS,
                    template_path=template_path,
                    repo_root=repo_root,
                    rights_holder_trust_root_path=rights_holder_trust_root_path,
                )
                if validation.get("contract_pass") is True:
                    written_license_status = license_status
                else:
                    _atomic_write_payload(
                        target=resolved_out,
                        payload=written_license_status,
                    )
            else:
                validation = staged_validation
                _atomic_write_payload(
                    target=resolved_out,
                    payload=written_license_status,
                )
        except Exception as error:
            validation = {
                "status": "blocked",
                "reason_code": "ERR_LICENSE_STATUS_VALIDATION_EXCEPTION",
                "contract_pass": False,
                "blockers": [
                    "license_status_validation_exception:"
                    f"{type(error).__name__}"
                ],
                "summary_line": (
                    "License status: BLOCKED | validation exception converted "
                    "to a fail-closed record"
                ),
            }
            try:
                _atomic_write_payload(
                    target=resolved_out,
                    payload=written_license_status,
                )
            except Exception as write_error:
                validation["blockers"].append(
                    "license_status_fail_closed_write_exception:"
                    f"{type(write_error).__name__}"
                )
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/fill_license_status_from_approval.py"),
                Path("scripts/build_license_status_closure_report.py"),
                Path("scripts/verify_rights_holder_license_decision.py"),
                Path("canonical/rights-holder-license-decision.v1.schema.json"),
                Path("canonical/rights-holder-license-trust-root.v1.schema.json"),
                Path("LICENSE"),
                template_path,
                rights_holder_trust_root_path,
                out if output_path_canonical else closure_report.CANONICAL_LICENSE_STATUS,
            ],
            reused_evidence=False,
            reuse_policy="license_status_filled_from_explicit_product_legal_approval_metadata",
            repo_root=repo_root,
        ),
        "status": "filled" if validation.get("contract_pass") is True else "blocked",
        "contract_pass": validation.get("contract_pass") is True,
        "license_status_path": out.as_posix(),
        "template_path": template_path.as_posix(),
        "license_status": written_license_status,
        "requested_license_status": license_status,
        "validation_status": validation.get("status", ""),
        "validation_reason_code": validation.get("reason_code", ""),
        "validation_blockers": validation.get("blockers", []),
        "validation_summary_line": validation.get("summary_line", ""),
        "validation_commands": closure_report._validation_commands(),
        "claim_boundary": (
            "This helper materializes a license_status.json record and immediately "
            "requires a cryptographically verified, exact-subject rights-holder decision "
            "from the repository trust root. CLI fields alone cannot pass the gate. It "
            "does not create or approve the underlying legal/product decision evidence."
        ),
    }


def write_report(*, payload: dict[str, Any], repo_root: Path, out: Path | None) -> None:
    if out is None:
        return
    resolved = _resolve(repo_root, out)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--template", type=Path, default=closure_report.DEFAULT_TEMPLATE)
    parser.add_argument(
        "--rights-holder-trust-root",
        type=Path,
        default=closure_report.DEFAULT_RIGHTS_HOLDER_TRUST_ROOT,
    )
    parser.add_argument(
        "--status",
        choices=sorted(closure_report.PASS_STATUSES),
        default="active",
    )
    parser.add_argument(
        "--tier",
        choices=sorted(closure_report.ALLOWED_TIERS),
        default="limited-commercial",
    )
    parser.add_argument("--license-id", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument(
        "--approver-role",
        choices=sorted(closure_report.ALLOWED_APPROVER_ROLES),
        required=True,
    )
    parser.add_argument("--approval-ref", required=True)
    parser.add_argument("--approved-at-utc", required=True)
    parser.add_argument("--evidence-ref", required=True)
    parser.add_argument(
        "--product-scope",
        action="append",
        default=[],
        help=(
            "Approved product scope value. Repeatable. Defaults to the required "
            "restricted release scope when omitted."
        ),
    )
    parser.add_argument("--expires-at-utc", default="")
    parser.add_argument("--perpetual", action="store_true")
    parser.add_argument(
        "--note",
        default="Populated from explicit product/legal approval metadata.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if not (sys.flags.isolated and sys.flags.dont_write_bytecode):
        print(
            "license-status approval fill: BLOCKED | invoke with "
            "/usr/bin/python3 -I -B",
            file=sys.stderr,
        )
        return 2
    args = build_parser().parse_args(argv)
    payload = fill_license_status(
        repo_root=ROOT,
        out=args.out,
        template_path=args.template,
        status=args.status,
        tier=args.tier,
        license_id=args.license_id,
        issuer=args.issuer,
        approver_role=args.approver_role,
        approval_ref=args.approval_ref,
        approved_at_utc=args.approved_at_utc,
        evidence_ref=args.evidence_ref,
        product_scope=args.product_scope or list(DEFAULT_PRODUCT_SCOPE),
        expires_at_utc=args.expires_at_utc,
        perpetual=args.perpetual,
        note=args.note,
        rights_holder_trust_root_path=args.rights_holder_trust_root,
    )
    write_report(payload=payload, repo_root=ROOT, out=args.report_out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "license-status approval fill: "
            f"{payload['status'].upper()} | "
            f"contract_pass={payload['contract_pass']} | "
            f"blockers={len(payload['validation_blockers'])}"
        )
    return 1 if not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
