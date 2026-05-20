#!/usr/bin/env python3
"""Build on-prem and air-gapped packaging skeleton evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "onprem-deployment-packaging-manifest.v1"
DEFAULT_MANIFEST_OUT = Path("implementation/phase1/onprem_deployment_packaging_manifest.json")
DEFAULT_PACKAGING_DIR = Path("deployment/onprem")
DEFAULT_CONTAINERFILE = DEFAULT_PACKAGING_DIR / "Containerfile"
DEFAULT_COMPOSE = DEFAULT_PACKAGING_DIR / "compose.example.yml"
DEFAULT_OFFLINE_LICENSE = DEFAULT_PACKAGING_DIR / "offline-license.example.json"
DEFAULT_SIGNED_UPDATE_PACKAGE = DEFAULT_PACKAGING_DIR / "signed-update-package.example.json"
DEFAULT_PACKAGING_README = DEFAULT_PACKAGING_DIR / "README.md"
DEFAULT_RUNTIME_PACKAGING_MANIFEST = Path("implementation/phase1/production_runtime_packaging_manifest.json")
DEFAULT_SUPPORT_BUNDLE_MANIFEST = Path("implementation/phase1/support_bundle_manifest.json")


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


def _check_row(
    check_id: str,
    *,
    title: str,
    checks: dict[str, bool],
    evidence: list[str],
    residual_live_work: str,
) -> dict[str, Any]:
    blockers = [key for key, ok in checks.items() if not ok]
    return {
        "check_id": check_id,
        "title": title,
        "status": "pass" if not blockers else "blocked",
        "checks": checks,
        "blockers": blockers,
        "evidence": evidence,
        "residual_live_work": residual_live_work,
    }


def _attestation(source_rows: list[dict[str, Any]], check_rows: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = {
        "source_rows": [
            {"label": row["label"], "path": row["path"], "sha256": row["sha256"]}
            for row in source_rows
        ],
        "check_rows": [
            {
                "check_id": row["check_id"],
                "status": row["status"],
                "checks": row["checks"],
                "blockers": row["blockers"],
            }
            for row in check_rows
        ],
    }
    canonical_bytes = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "schema_version": "onprem-deployment-packaging-attestation.v1",
        "generated_at": _now_utc_iso(),
        "signature_mode": "sha256_attestation_envelope_not_cryptographic_signature",
        "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
        "canonical_payload_bytes": len(canonical_bytes),
    }


def build_onprem_deployment_packaging_manifest(
    *,
    containerfile: Path = DEFAULT_CONTAINERFILE,
    compose_file: Path = DEFAULT_COMPOSE,
    offline_license: Path = DEFAULT_OFFLINE_LICENSE,
    signed_update_package: Path = DEFAULT_SIGNED_UPDATE_PACKAGE,
    packaging_readme: Path = DEFAULT_PACKAGING_README,
    runtime_packaging_manifest: Path = DEFAULT_RUNTIME_PACKAGING_MANIFEST,
    support_bundle_manifest: Path = DEFAULT_SUPPORT_BUNDLE_MANIFEST,
) -> dict[str, Any]:
    container_text = _read_text(containerfile)
    compose_text = _read_text(compose_file)
    readme_text = _read_text(packaging_readme)
    license_payload = _load_json(offline_license)
    update_payload = _load_json(signed_update_package)
    runtime_payload = _load_json(runtime_packaging_manifest)
    support_payload = _load_json(support_bundle_manifest)

    source_rows = [
        _source_row(packaging_readme, label="packaging_readme"),
        _source_row(containerfile, label="containerfile"),
        _source_row(compose_file, label="compose_example"),
        _source_row(offline_license, label="offline_license_example"),
        _source_row(signed_update_package, label="signed_update_package_example"),
        _source_row(runtime_packaging_manifest, label="runtime_packaging_manifest"),
        _source_row(support_bundle_manifest, label="support_bundle_manifest"),
    ]

    license_features = set(license_payload.get("features", [])) if isinstance(license_payload.get("features"), list) else set()
    update_artifacts = update_payload.get("artifacts", []) if isinstance(update_payload.get("artifacts"), list) else []
    runtime_modes = (
        runtime_payload.get("runtime_package", {}).get("supported_modes", [])
        if isinstance(runtime_payload.get("runtime_package"), dict)
        else []
    )

    check_rows = [
        _check_row(
            "container_runtime_contract",
            title="Container skeleton runs the auth-required project ops service without embedding secrets",
            checks={
                "containerfile_present": containerfile.exists(),
                "auth_required_cmd": "--auth-required" in container_text,
                "service_entrypoint_present": "project_ops_api_service.py" in container_text,
                "secret_not_baked_into_image": "PROJECT_OPS_JWT_HMAC_SECRET=" not in container_text,
                "telemetry_default_off": "PROJECT_OPS_TELEMETRY_ENABLED" in compose_text
                and "false" in compose_text.lower(),
            },
            evidence=[str(containerfile), str(compose_file)],
            residual_live_work="Build and scan the image in the customer-approved container environment.",
        ),
        _check_row(
            "compose_secret_and_volume_contract",
            title="Compose example uses secret injection, loopback binding, read-only root, and support volumes",
            checks={
                "compose_present": compose_file.exists(),
                "secret_store_reference": "PROJECT_OPS_JWT_HMAC_SECRET" in compose_text,
                "loopback_port_binding": "127.0.0.1:8080:8080" in compose_text,
                "read_only_root": "read_only: true" in compose_text,
                "support_bundle_volume": "support_bundle" in compose_text,
            },
            evidence=[str(compose_file)],
            residual_live_work="Bind the compose profile to the site gateway/TLS/WAF and backup storage.",
        ),
        _check_row(
            "offline_license_contract",
            title="Offline license example has tenant, expiry, features, public key id, and signature placeholder",
            checks={
                "license_present": offline_license.exists(),
                "license_schema_declared": license_payload.get("schema_version") == "offline-license-file.example.v1",
                "tenant_bound": bool(license_payload.get("tenant_id")),
                "expiry_declared": bool(license_payload.get("expires_at_utc")),
                "required_features_present": {"project_ops_api", "support_bundle"}.issubset(license_features),
                "signature_placeholder_present": "signature" in license_payload
                and "public_key_id" in license_payload,
            },
            evidence=[str(offline_license)],
            residual_live_work="Replace placeholder signature fields with production license signing output.",
        ),
        _check_row(
            "signed_update_contract",
            title="Signed update package example has offline transfer policy, artifact hashes, signature, and rollback",
            checks={
                "update_manifest_present": signed_update_package.exists(),
                "update_schema_declared": update_payload.get("schema_version") == "signed-update-package.example.v1",
                "offline_transfer_policy": update_payload.get("network_policy") == "offline_transfer_only",
                "artifact_rows_present": len(update_artifacts) >= 2,
                "artifact_hashes_declared": all(bool(row.get("sha256")) for row in update_artifacts if isinstance(row, dict)),
                "rollback_policy_present": isinstance(update_payload.get("rollback"), dict),
                "signature_placeholder_present": "signature" in update_payload,
            },
            evidence=[str(signed_update_package)],
            residual_live_work="Replace placeholder hashes/signatures with the generated release asset digests and signing key output.",
        ),
        _check_row(
            "runtime_support_bundle_link",
            title="On-prem packaging is linked to runtime and support bundle evidence",
            checks={
                "runtime_manifest_pass": bool(runtime_payload.get("contract_pass")),
                "runtime_modes_include_onprem_airgap": {"on_prem", "air_gapped"}.issubset(set(runtime_modes)),
                "support_bundle_pass": bool(support_payload.get("contract_pass")),
                "support_bundle_roundtrip_pass": bool(
                    support_payload.get("checks", {}).get("bundle_roundtrip_test_pass")
                    if isinstance(support_payload.get("checks"), dict)
                    else False
                ),
            },
            evidence=[str(runtime_packaging_manifest), str(support_bundle_manifest)],
            residual_live_work="Run a restore/support-bundle roundtrip from the actual installed package.",
        ),
        _check_row(
            "airgap_operator_runbook",
            title="Operator runbook states offline transfer, no implicit network dependency, signed update, and support bundle handoff",
            checks={
                "readme_present": packaging_readme.exists(),
                "offline_transfer_declared": "offline" in readme_text.lower(),
                "no_implicit_network_dependency": "network isolated" in readme_text.lower()
                or "no external network" in readme_text.lower(),
                "signed_update_declared": "signed update" in readme_text.lower(),
                "support_bundle_handoff_declared": "support bundle" in readme_text.lower(),
            },
            evidence=[str(packaging_readme)],
            residual_live_work="Capture the customer site import/export checklist and operator sign-off.",
        ),
    ]

    missing_sources = [row["label"] for row in source_rows if not row["available"]]
    check_blockers = [
        f"{row['check_id']}:{blocker}"
        for row in check_rows
        for blocker in row["blockers"]
    ]
    blockers = [*(f"source_missing:{label}" for label in missing_sources), *check_blockers]
    contract_pass = not blockers
    attestation = _attestation(source_rows, check_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_ONPREM_DEPLOYMENT_PACKAGING_PENDING",
        "summary_line": (
            f"On-prem deployment packaging: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"checks={sum(1 for row in check_rows if row['status'] == 'pass')}/{len(check_rows)} | "
            "mode=skeleton_contract"
        ),
        "package_mode": "skeleton_contract",
        "live_deployment_claim": False,
        "supported_deployment_modes": ["on_prem", "air_gapped"],
        "source_rows": source_rows,
        "check_rows": check_rows,
        "attestation_envelope": attestation,
        "residual_live_work": [
            "Build and scan the container image in the deployment environment.",
            "Replace example license/update signatures with production signing keys.",
            "Run offline artifact import, restore, and support bundle roundtrip from the installed package.",
            "Attach customer/site gateway, backup, and incident response drill evidence.",
        ],
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--containerfile", type=Path, default=DEFAULT_CONTAINERFILE)
    parser.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--offline-license", type=Path, default=DEFAULT_OFFLINE_LICENSE)
    parser.add_argument("--signed-update-package", type=Path, default=DEFAULT_SIGNED_UPDATE_PACKAGE)
    parser.add_argument("--packaging-readme", type=Path, default=DEFAULT_PACKAGING_README)
    parser.add_argument("--runtime-packaging-manifest", type=Path, default=DEFAULT_RUNTIME_PACKAGING_MANIFEST)
    parser.add_argument("--support-bundle-manifest", type=Path, default=DEFAULT_SUPPORT_BUNDLE_MANIFEST)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_onprem_deployment_packaging_manifest(
        containerfile=args.containerfile,
        compose_file=args.compose_file,
        offline_license=args.offline_license,
        signed_update_package=args.signed_update_package,
        packaging_readme=args.packaging_readme,
        runtime_packaging_manifest=args.runtime_packaging_manifest,
        support_bundle_manifest=args.support_bundle_manifest,
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
