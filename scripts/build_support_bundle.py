#!/usr/bin/env python3
"""Build a redacted support bundle manifest for product ops handoff."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "support-bundle-manifest.v1"
DEFAULT_BUNDLE_DIR = Path("implementation/phase1/release/support_bundle")
DEFAULT_MANIFEST_OUT = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_P0_STATUS = Path("implementation/phase1/release/publication_evidence/current/p0-status.json")
DEFAULT_P1_STATUS = Path("implementation/phase1/release/publication_evidence/current/p1-readiness-status.json")
DEFAULT_P1_STRICT_PREFLIGHT = Path("implementation/phase1/commercialization_status/p1_evidence_sidecar_preflight.json")
DEFAULT_PROJECT_OPS_SNAPSHOT = Path("implementation/phase1/release/project_ops_service_snapshot.json")
DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL = Path("implementation/phase1/project_ops_deployment_drill_manifest.json")
DEFAULT_RUNTIME_PROBE = Path("implementation/phase1/zero_copy_real_probe_report_strict.json")
DEFAULT_RUNTIME_PACKAGING_MANIFEST = Path("implementation/phase1/production_runtime_packaging_manifest.json")
DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST = Path(
    "implementation/phase1/structure_viewer_performance_budget_manifest.json"
)
DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE = Path(
    "implementation/phase1/structure_viewer_visual_regression_baseline.json"
)
DEFAULT_WORKSTATION_HARDWARE_PROFILE = Path("implementation/phase1/workstation_hardware_profile.json")
DEFAULT_WORKSTATION_SERVICE_BUDGET = Path("implementation/phase1/workstation_service_budget.json")
DEFAULT_WORKSTATION_DELIVERY_PACKAGE_MANIFEST = Path(
    "implementation/phase1/workstation_delivery_package_manifest.json"
)
DEFAULT_WORKSTATION_DELIVERY_READINESS = Path("implementation/phase1/workstation_delivery_readiness.json")
DEFAULT_WORKSTATION_DELIVERY_VIEWER_SMOKE = Path("implementation/phase1/workstation_delivery_viewer_smoke.json")
DEFAULT_CLIENT_INPUT_VALIDATION_REPORT = Path("implementation/phase1/client_input_validation_report.json")
DEFAULT_WORKSTATION_JOB_RECORD = Path("implementation/phase1/workstation_job_record.json")
DEFAULT_WORKSTATION_JOB_RETENTION_POLICY = Path("implementation/phase1/workstation_job_retention_policy.json")
DEFAULT_EXTERNAL_BENCHMARK_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json"
)
DEFAULT_RESIDUAL_HOLDOUT_UPDATES = Path(
    "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
)
DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
)
DEFAULT_LICENSE_STATUS_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/license_status_intake_packet.json"
)
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_PYPROJECT = Path("pyproject.toml")

SENSITIVE_KEY_MARKERS = (
    "authorization",
    "secret",
    "token",
    "password",
    "private_key",
    "apikey",
    "api_key",
    "credential",
)
TEXT_REDACTIONS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(secret|token|password|api[_-]?key)\s*[:=]\s*[^,\s\"']+"),
)
REDACTED = "[REDACTED]"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in TEXT_REDACTIONS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): REDACTED if _is_sensitive_key(str(key)) else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _safe_bundle_name(label: str, source: Path) -> str:
    suffix = source.suffix if source.suffix in {".json", ".md", ".txt", ".toml", ".jsonl"} else ".txt"
    return f"{label.replace('/', '_')}{suffix}"


def _write_redacted_copy(*, label: str, source: Path, bundle_dir: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "source_path": str(source),
        "available": source.exists(),
        "bytes": 0,
        "sha256": "",
        "redacted_bundle_path": "",
        "redacted_sha256": "",
    }
    if not source.exists():
        return row

    raw_bytes = source.read_bytes()
    row["bytes"] = len(raw_bytes)
    row["sha256"] = _sha256_bytes(raw_bytes)
    destination = bundle_dir / "redacted" / _safe_bundle_name(label, source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    json_payload = _load_json(source)
    if json_payload is not None:
        redacted_bytes = (
            json.dumps(redact_payload(json_payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    else:
        redacted_bytes = (_redact_text(source.read_text(encoding="utf-8", errors="replace")) + "\n").encode("utf-8")
    destination.write_bytes(redacted_bytes)
    row["redacted_bundle_path"] = str(destination)
    row["redacted_sha256"] = _sha256_bytes(redacted_bytes)
    return row


def _build_audit_digest(audit_log_path: Path | None, bundle_dir: Path) -> dict[str, Any]:
    lines: list[str] = []
    if audit_log_path and audit_log_path.exists():
        lines = audit_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    canonical = "\n".join(_redact_text(line) for line in lines).encode("utf-8")
    payload = {
        "schema_version": "support-bundle-audit-digest.v1",
        "generated_at": _now_utc_iso(),
        "audit_log_path": str(audit_log_path or ""),
        "audit_log_available": bool(audit_log_path and audit_log_path.exists()),
        "event_count": len([line for line in lines if line.strip()]),
        "sha256": _sha256_bytes(canonical),
    }
    destination = bundle_dir / "audit_digest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["bundle_path"] = str(destination)
    return payload


def _build_license_snapshot(license_status: Path | None, bundle_dir: Path) -> dict[str, Any]:
    payload: dict[str, Any]
    loaded = _load_json(license_status) if license_status else None
    if isinstance(loaded, dict):
        payload = loaded
    else:
        payload = {
            "status": "not_configured",
            "tier": "",
            "expires_at": "",
            "note": "No license status file was provided for this support bundle.",
        }
    redacted = redact_payload(payload)
    destination = bundle_dir / "license_status.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "path": str(license_status or ""),
        "available": bool(license_status and license_status.exists()),
        "bundle_path": str(destination),
        "sha256": _sha256_path(destination),
    }


def _redaction_self_test() -> dict[str, Any]:
    fixture = {
        "Authorization": "Bearer eyJexample.secret.token",
        "nested": {"api_key": "sample-api-key", "safe": "kept"},
        "line": "token=sample-token",
    }
    redacted = json.dumps(redact_payload(fixture), ensure_ascii=False, sort_keys=True)
    forbidden = ("eyJexample", "sample-api-key", "sample-token")
    return {
        "pass": not any(token in redacted for token in forbidden),
        "redacted_fixture": redacted,
    }


def _build_index(*, bundle_dir: Path, artifact_rows: list[dict[str, Any]], audit_digest: dict[str, Any]) -> dict[str, Any]:
    index = {
        "schema_version": "support-bundle-index.v1",
        "generated_at": _now_utc_iso(),
        "artifact_count": len(artifact_rows),
        "available_artifact_count": sum(1 for row in artifact_rows if row.get("available")),
        "artifact_rows": artifact_rows,
        "audit_digest": audit_digest,
    }
    index_path = bundle_dir / "support_bundle_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index["bundle_index_path"] = str(index_path)
    index["bundle_index_sha256"] = _sha256_path(index_path)
    return index


def _roundtrip_self_test(index: dict[str, Any]) -> dict[str, Any]:
    index_path = Path(str(index.get("bundle_index_path", "")))
    if not index_path.exists():
        return {"pass": False, "reason": "bundle_index_missing"}
    loaded = json.loads(index_path.read_text(encoding="utf-8"))
    expected_count = int(index.get("artifact_count", 0))
    actual_count = len(loaded.get("artifact_rows", [])) if isinstance(loaded.get("artifact_rows"), list) else -1
    return {
        "pass": actual_count == expected_count,
        "reason": "PASS" if actual_count == expected_count else "artifact_count_mismatch",
        "expected_artifact_count": expected_count,
        "actual_artifact_count": actual_count,
    }


def build_support_bundle(
    *,
    bundle_dir: Path = DEFAULT_BUNDLE_DIR,
    audit_log_path: Path | None = None,
    license_status: Path | None = None,
    p0_status: Path = DEFAULT_P0_STATUS,
    p1_status: Path = DEFAULT_P1_STATUS,
    p1_strict_evidence_preflight: Path = DEFAULT_P1_STRICT_PREFLIGHT,
    project_ops_snapshot: Path = DEFAULT_PROJECT_OPS_SNAPSHOT,
    project_ops_deployment_drill: Path = DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL,
    runtime_probe: Path = DEFAULT_RUNTIME_PROBE,
    runtime_packaging_manifest: Path = DEFAULT_RUNTIME_PACKAGING_MANIFEST,
    viewer_performance_budget_manifest: Path = DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST,
    viewer_browser_performance_probe: Path = DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    viewer_visual_regression_baseline: Path = DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    workstation_hardware_profile: Path = DEFAULT_WORKSTATION_HARDWARE_PROFILE,
    workstation_service_budget: Path = DEFAULT_WORKSTATION_SERVICE_BUDGET,
    workstation_delivery_package_manifest: Path = DEFAULT_WORKSTATION_DELIVERY_PACKAGE_MANIFEST,
    workstation_delivery_readiness: Path = DEFAULT_WORKSTATION_DELIVERY_READINESS,
    workstation_delivery_viewer_smoke: Path = DEFAULT_WORKSTATION_DELIVERY_VIEWER_SMOKE,
    client_input_validation_report: Path = DEFAULT_CLIENT_INPUT_VALIDATION_REPORT,
    workstation_job_record: Path = DEFAULT_WORKSTATION_JOB_RECORD,
    workstation_job_retention_policy: Path = DEFAULT_WORKSTATION_JOB_RETENTION_POLICY,
    external_benchmark_updates: Path = DEFAULT_EXTERNAL_BENCHMARK_UPDATES,
    residual_holdout_updates: Path = DEFAULT_RESIDUAL_HOLDOUT_UPDATES,
    pm_release_blocker_action_register: Path | None = DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER,
    license_status_intake_packet: Path | None = DEFAULT_LICENSE_STATUS_INTAKE_PACKET,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    pyproject: Path = DEFAULT_PYPROJECT,
    viewer_report: Path | None = None,
) -> dict[str, Any]:
    required_specs = [
        ("p0_status", p0_status),
        ("p1_status", p1_status),
        ("p1_strict_evidence_preflight", p1_strict_evidence_preflight),
        ("project_ops_snapshot", project_ops_snapshot),
        ("project_ops_deployment_drill", project_ops_deployment_drill),
        ("runtime_probe", runtime_probe),
        ("runtime_packaging_manifest", runtime_packaging_manifest),
        ("viewer_performance_budget_manifest", viewer_performance_budget_manifest),
        ("viewer_browser_performance_probe", viewer_browser_performance_probe),
        ("viewer_visual_regression_baseline", viewer_visual_regression_baseline),
        ("workstation_hardware_profile", workstation_hardware_profile),
        ("workstation_service_budget", workstation_service_budget),
        ("workstation_delivery_package_manifest", workstation_delivery_package_manifest),
        ("workstation_delivery_readiness", workstation_delivery_readiness),
        ("workstation_delivery_viewer_smoke", workstation_delivery_viewer_smoke),
        ("client_input_validation_report", client_input_validation_report),
        ("workstation_job_record", workstation_job_record),
        ("workstation_job_retention_policy", workstation_job_retention_policy),
        ("external_benchmark_updates", external_benchmark_updates),
        ("residual_holdout_updates", residual_holdout_updates),
        ("package_json", package_json),
        ("pyproject", pyproject),
    ]
    optional_specs = [
        ("pm_release_blocker_action_register", pm_release_blocker_action_register),
        ("license_status_intake_packet", license_status_intake_packet),
        ("viewer_report", viewer_report),
    ]
    artifact_rows = [_write_redacted_copy(label=label, source=path, bundle_dir=bundle_dir) for label, path in required_specs]
    for label, path in optional_specs:
        if path is not None:
            artifact_rows.append(_write_redacted_copy(label=label, source=path, bundle_dir=bundle_dir))

    audit_digest = _build_audit_digest(audit_log_path, bundle_dir)
    license_snapshot = _build_license_snapshot(license_status, bundle_dir)
    redaction = _redaction_self_test()
    index = _build_index(bundle_dir=bundle_dir, artifact_rows=artifact_rows, audit_digest=audit_digest)
    roundtrip = _roundtrip_self_test(index)

    missing_required = [row["label"] for row in artifact_rows[: len(required_specs)] if not row.get("available")]
    blockers = [
        *(f"required_artifact_missing:{label}" for label in missing_required),
        *(["redaction_self_test_failed"] if not redaction["pass"] else []),
        *(["audit_event_digest_missing"] if not audit_digest.get("sha256") else []),
        *(["bundle_roundtrip_test_failed"] if not roundtrip["pass"] else []),
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_SUPPORT_BUNDLE_EVIDENCE_PENDING",
        "summary_line": (
            f"Support bundle: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"artifacts={index['available_artifact_count']}/{index['artifact_count']} | "
            f"redaction={redaction['pass']} | roundtrip={roundtrip['pass']}"
        ),
        "bundle_policy": {
            "redact_secrets": True,
            "include_private_keys": False,
            "include_tokens": False,
            "tenant_scoped": True,
            "copy_mode": "redacted_evidence_plus_digest",
        },
        "required_sections": {
            row["label"]: row["redacted_bundle_path"] if row.get("available") else "missing"
            for row in artifact_rows[: len(required_specs)]
        },
        "optional_sections": {
            row["label"]: row["redacted_bundle_path"] if row.get("available") else "missing"
            for row in artifact_rows[len(required_specs) :]
        },
        "checks": {
            "redaction_self_test_pass": redaction["pass"],
            "audit_event_digest_pass": bool(audit_digest.get("sha256")),
            "bundle_roundtrip_test_pass": roundtrip["pass"],
            "missing_required_count": len(missing_required),
        },
        "audit_digest": audit_digest,
        "license_status": license_snapshot,
        "bundle_index": {
            "path": index["bundle_index_path"],
            "sha256": index["bundle_index_sha256"],
            "artifact_count": index["artifact_count"],
            "available_artifact_count": index["available_artifact_count"],
        },
        "artifact_rows": artifact_rows,
        "blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--audit-log-path", type=Path)
    parser.add_argument("--license-status-json", type=Path)
    parser.add_argument("--p0-status", type=Path, default=DEFAULT_P0_STATUS)
    parser.add_argument("--p1-status", type=Path, default=DEFAULT_P1_STATUS)
    parser.add_argument("--p1-strict-evidence-preflight", type=Path, default=DEFAULT_P1_STRICT_PREFLIGHT)
    parser.add_argument("--project-ops-snapshot", type=Path, default=DEFAULT_PROJECT_OPS_SNAPSHOT)
    parser.add_argument("--project-ops-deployment-drill", type=Path, default=DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL)
    parser.add_argument("--runtime-probe", type=Path, default=DEFAULT_RUNTIME_PROBE)
    parser.add_argument("--runtime-packaging-manifest", type=Path, default=DEFAULT_RUNTIME_PACKAGING_MANIFEST)
    parser.add_argument(
        "--viewer-performance-budget-manifest",
        type=Path,
        default=DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST,
    )
    parser.add_argument(
        "--viewer-browser-performance-probe",
        type=Path,
        default=DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    )
    parser.add_argument(
        "--viewer-visual-regression-baseline",
        type=Path,
        default=DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    )
    parser.add_argument("--workstation-hardware-profile", type=Path, default=DEFAULT_WORKSTATION_HARDWARE_PROFILE)
    parser.add_argument("--workstation-service-budget", type=Path, default=DEFAULT_WORKSTATION_SERVICE_BUDGET)
    parser.add_argument(
        "--workstation-delivery-package-manifest",
        type=Path,
        default=DEFAULT_WORKSTATION_DELIVERY_PACKAGE_MANIFEST,
    )
    parser.add_argument("--workstation-delivery-readiness", type=Path, default=DEFAULT_WORKSTATION_DELIVERY_READINESS)
    parser.add_argument(
        "--workstation-delivery-viewer-smoke",
        type=Path,
        default=DEFAULT_WORKSTATION_DELIVERY_VIEWER_SMOKE,
    )
    parser.add_argument("--client-input-validation-report", type=Path, default=DEFAULT_CLIENT_INPUT_VALIDATION_REPORT)
    parser.add_argument("--workstation-job-record", type=Path, default=DEFAULT_WORKSTATION_JOB_RECORD)
    parser.add_argument(
        "--workstation-job-retention-policy",
        type=Path,
        default=DEFAULT_WORKSTATION_JOB_RETENTION_POLICY,
    )
    parser.add_argument("--external-benchmark-updates", type=Path, default=DEFAULT_EXTERNAL_BENCHMARK_UPDATES)
    parser.add_argument("--residual-holdout-updates", type=Path, default=DEFAULT_RESIDUAL_HOLDOUT_UPDATES)
    parser.add_argument(
        "--pm-release-blocker-action-register",
        type=Path,
        default=DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER,
    )
    parser.add_argument(
        "--license-status-intake-packet",
        type=Path,
        default=DEFAULT_LICENSE_STATUS_INTAKE_PACKET,
    )
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--viewer-report", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_support_bundle(
        bundle_dir=args.bundle_dir,
        audit_log_path=args.audit_log_path,
        license_status=args.license_status_json,
        p0_status=args.p0_status,
        p1_status=args.p1_status,
        p1_strict_evidence_preflight=args.p1_strict_evidence_preflight,
        project_ops_snapshot=args.project_ops_snapshot,
        project_ops_deployment_drill=args.project_ops_deployment_drill,
        runtime_probe=args.runtime_probe,
        runtime_packaging_manifest=args.runtime_packaging_manifest,
        viewer_performance_budget_manifest=args.viewer_performance_budget_manifest,
        viewer_browser_performance_probe=args.viewer_browser_performance_probe,
        viewer_visual_regression_baseline=args.viewer_visual_regression_baseline,
        workstation_hardware_profile=args.workstation_hardware_profile,
        workstation_service_budget=args.workstation_service_budget,
        workstation_delivery_package_manifest=args.workstation_delivery_package_manifest,
        workstation_delivery_readiness=args.workstation_delivery_readiness,
        workstation_delivery_viewer_smoke=args.workstation_delivery_viewer_smoke,
        client_input_validation_report=args.client_input_validation_report,
        workstation_job_record=args.workstation_job_record,
        workstation_job_retention_policy=args.workstation_job_retention_policy,
        external_benchmark_updates=args.external_benchmark_updates,
        residual_holdout_updates=args.residual_holdout_updates,
        pm_release_blocker_action_register=args.pm_release_blocker_action_register,
        license_status_intake_packet=args.license_status_intake_packet,
        package_json=args.package_json,
        pyproject=args.pyproject,
        viewer_report=args.viewer_report,
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
