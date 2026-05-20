#!/usr/bin/env python3
"""Build dry-run deployment drill evidence for the project ops control plane."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "project-ops-deployment-drill-manifest.v1"
DEFAULT_MANIFEST_OUT = Path("implementation/phase1/project_ops_deployment_drill_manifest.json")
DEFAULT_PROJECT_OPS_API = Path("implementation/phase1/project_ops_api_service.py")
DEFAULT_PRODUCTION_SECURITY_DOC = Path("docs/production-ops-security.md")
DEFAULT_SUPPORT_BUNDLE_MANIFEST = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_RUNTIME_PACKAGING_MANIFEST = Path("implementation/phase1/production_runtime_packaging_manifest.json")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_path(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_row(path: Path, *, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "available": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": _sha256_path(path),
    }


def _has_all(text: str, tokens: tuple[str, ...]) -> bool:
    return all(token in text for token in tokens)


def _drill(
    drill_id: str,
    *,
    title: str,
    checks: dict[str, bool],
    evidence: list[str],
    residual_live_work: str,
) -> dict[str, Any]:
    blockers = [key for key, ok in checks.items() if not ok]
    return {
        "drill_id": drill_id,
        "title": title,
        "mode": "dry_run_contract",
        "status": "pass" if not blockers else "blocked",
        "checks": checks,
        "blockers": blockers,
        "evidence": evidence,
        "residual_live_work": residual_live_work,
    }


def _attestation_envelope(drills: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = {
        "drills": [
            {
                "drill_id": row["drill_id"],
                "status": row["status"],
                "checks": row["checks"],
                "blockers": row["blockers"],
            }
            for row in drills
        ],
        "sources": [
            {
                "label": row["label"],
                "path": row["path"],
                "sha256": row["sha256"],
            }
            for row in sources
        ],
    }
    canonical_bytes = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "schema_version": "project-ops-drill-attestation-envelope.v1",
        "generated_at": _now_utc_iso(),
        "signature_mode": "sha256_attestation_envelope_not_cryptographic_signature",
        "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
        "canonical_payload_bytes": len(canonical_bytes),
    }


def build_project_ops_deployment_drill_manifest(
    *,
    project_ops_api: Path = DEFAULT_PROJECT_OPS_API,
    production_security_doc: Path = DEFAULT_PRODUCTION_SECURITY_DOC,
    support_bundle_manifest: Path = DEFAULT_SUPPORT_BUNDLE_MANIFEST,
    runtime_packaging_manifest: Path = DEFAULT_RUNTIME_PACKAGING_MANIFEST,
) -> dict[str, Any]:
    api_text = _read_text(project_ops_api)
    doc_text = _read_text(production_security_doc)
    support_bundle = _load_json(support_bundle_manifest)
    runtime_packaging = _load_json(runtime_packaging_manifest)

    support_checks = support_bundle.get("checks", {}) if isinstance(support_bundle.get("checks"), dict) else {}
    support_policy = (
        support_bundle.get("bundle_policy", {}) if isinstance(support_bundle.get("bundle_policy"), dict) else {}
    )
    audit_digest = support_bundle.get("audit_digest", {}) if isinstance(support_bundle.get("audit_digest"), dict) else {}
    runtime_package = (
        runtime_packaging.get("runtime_package", {})
        if isinstance(runtime_packaging.get("runtime_package"), dict)
        else {}
    )

    sources = [
        _source_row(project_ops_api, label="project_ops_api"),
        _source_row(production_security_doc, label="production_security_doc"),
        _source_row(runtime_packaging_manifest, label="runtime_packaging_manifest"),
    ]

    drills = [
        _drill(
            "secret_rotation_negative_start",
            title="Auth-enabled service requires injected secret and has a documented rotation path",
            checks={
                "env_secret_contract_present": "PROJECT_OPS_JWT_HMAC_SECRET" in api_text,
                "auth_start_without_secret_rejected": "jwt_hmac_secret is required when auth_required=True" in api_text,
                "dev_secret_removed": "project-ops-dev-secret" not in api_text,
                "rotation_runbook_declared": "secret rotation" in doc_text.lower(),
            },
            evidence=[str(project_ops_api), str(production_security_doc)],
            residual_live_work="Run the same negative-start and rotation drill against the selected production secret store.",
        ),
        _drill(
            "gateway_boundary_and_rate_policy",
            title="Gateway boundary, tenant allow-list, request limit, and rate policy are declared",
            checks={
                "gateway_boundary_declared": any(token in doc_text.lower() for token in ("gateway", "waf", "tls")),
                "tenant_allowlist_present": "allowed_tenants" in api_text,
                "rate_limit_present": "rate_limit_window_seconds" in api_text and "rate_limited" in api_text,
                "request_limit_present": "request_metadata_byte_limit" in api_text,
            },
            evidence=[str(project_ops_api), str(production_security_doc)],
            residual_live_work="Bind these parameters to the real gateway/WAF profile and capture a live throttle proof.",
        ),
        _drill(
            "backup_restore_policy_roundtrip",
            title="Backup/restore policy is surfaced and support bundle roundtrip is green",
            checks={
                "backup_policy_surface_present": "backup_policy" in api_text,
                "restore_policy_surface_present": "restore_policy" in api_text,
                "backup_restore_runbook_declared": "backup/restore" in doc_text.lower(),
                "support_bundle_roundtrip_pass": bool(support_checks.get("bundle_roundtrip_test_pass")),
            },
            evidence=[str(project_ops_api), str(production_security_doc), str(support_bundle_manifest)],
            residual_live_work="Execute backup and clean restore with tenant-scoped evidence against the deployment store.",
        ),
        _drill(
            "tenant_delete_policy_roundtrip",
            title="Tenant delete policy and tenant-scoped redacted support handoff are present",
            checks={
                "tenant_delete_policy_surface_present": "tenant_delete_policy" in api_text,
                "tenant_filtering_present": "_filter_snapshot_for_tenant" in api_text,
                "tenant_delete_runbook_declared": "tenant" in doc_text.lower() and "delete" in doc_text.lower(),
                "support_bundle_tenant_scoped": bool(support_policy.get("tenant_scoped")),
            },
            evidence=[str(project_ops_api), str(production_security_doc), str(support_bundle_manifest)],
            residual_live_work="Run a tenant-delete drill and verify export/restore denies deleted tenant state.",
        ),
        _drill(
            "audit_tamper_evidence_roundtrip",
            title="Audit digest and redacted audit support handoff are reproducible",
            checks={
                "api_audit_digest_present": "/audit/digest" in api_text and "audit_log_sha256" in api_text,
                "support_audit_digest_pass": bool(support_checks.get("audit_event_digest_pass")),
                "support_audit_digest_sha_present": bool(audit_digest.get("sha256")),
                "worm_or_signature_boundary_declared": any(
                    token in doc_text.lower() for token in ("worm", "signed", "signature")
                ),
            },
            evidence=[str(project_ops_api), str(production_security_doc), str(support_bundle_manifest)],
            residual_live_work="Replace the local SHA-256 envelope with WORM storage or a production signing key.",
        ),
        _drill(
            "incident_response_support_bundle_roundtrip",
            title="Incident response handoff can be assembled from support/runtime evidence",
            checks={
                "incident_runbook_declared": "incident response" in doc_text.lower(),
                "support_bundle_contract_pass": bool(support_bundle.get("contract_pass")),
                "redaction_self_test_pass": bool(support_checks.get("redaction_self_test_pass")),
                "runtime_package_contract_pass": bool(runtime_packaging.get("contract_pass")),
                "runtime_modes_declared": {"saas", "on_prem", "air_gapped"}.issubset(
                    set(runtime_package.get("supported_modes", []))
                ),
            },
            evidence=[str(production_security_doc), str(support_bundle_manifest), str(runtime_packaging_manifest)],
            residual_live_work="Run a timed incident drill with token disable, route rollback, and support upload receipt.",
        ),
    ]

    drill_blockers = [
        f"{row['drill_id']}:{blocker}"
        for row in drills
        for blocker in row["blockers"]
    ]
    missing_sources = [row["label"] for row in sources if not row["available"]]
    blockers = [*(f"source_missing:{label}" for label in missing_sources), *drill_blockers]
    contract_pass = not blockers
    attestation = _attestation_envelope(drills, sources)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_PROJECT_OPS_DEPLOYMENT_DRILL_PENDING",
        "summary_line": (
            f"Project ops deployment drill: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"drills={sum(1 for row in drills if row['status'] == 'pass')}/{len(drills)} | "
            "mode=dry_run_contract"
        ),
        "drill_mode": "dry_run_contract",
        "live_deployment_claim": False,
        "drill_rows": drills,
        "source_rows": sources,
        "support_bundle_evidence": {
            "path": str(support_bundle_manifest),
            "available": support_bundle_manifest.exists(),
            "contract_pass": bool(support_bundle.get("contract_pass")),
            "roundtrip_pass": bool(support_checks.get("bundle_roundtrip_test_pass")),
            "audit_digest_pass": bool(support_checks.get("audit_event_digest_pass")),
            "tenant_scoped": bool(support_policy.get("tenant_scoped")),
        },
        "attestation_envelope": attestation,
        "checks": {
            "all_sources_available": not missing_sources,
            "all_drills_pass": not drill_blockers,
            "attestation_sha256_present": bool(attestation.get("sha256")),
            "live_deployment_claim": False,
        },
        "residual_live_work": [
            "Capture gateway/WAF/TLS deployment parameter evidence.",
            "Run production secret rotation against the chosen secret store.",
            "Execute backup/restore and tenant-delete drills against the deployment data store.",
            "Attach WORM or production signing-key proof for audit digest storage.",
            "Run a timed incident response drill with support bundle upload receipt.",
        ],
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--project-ops-api", type=Path, default=DEFAULT_PROJECT_OPS_API)
    parser.add_argument("--production-security-doc", type=Path, default=DEFAULT_PRODUCTION_SECURITY_DOC)
    parser.add_argument("--support-bundle-manifest", type=Path, default=DEFAULT_SUPPORT_BUNDLE_MANIFEST)
    parser.add_argument("--runtime-packaging-manifest", type=Path, default=DEFAULT_RUNTIME_PACKAGING_MANIFEST)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_project_ops_deployment_drill_manifest(
        project_ops_api=args.project_ops_api,
        production_security_doc=args.production_security_doc,
        support_bundle_manifest=args.support_bundle_manifest,
        runtime_packaging_manifest=args.runtime_packaging_manifest,
    )
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
