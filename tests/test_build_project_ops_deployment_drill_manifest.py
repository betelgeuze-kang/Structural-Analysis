from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_project_ops_deployment_drill_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_project_ops_deployment_drill_manifest", SCRIPT_PATH)
assert SPEC is not None
build_project_ops_deployment_drill_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_project_ops_deployment_drill_manifest)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_project_ops_deployment_drill_manifest_passes_dry_run_contract(tmp_path: Path) -> None:
    api = _write_text(
        tmp_path / "project_ops_api_service.py",
        "\n".join(
            [
                "PROJECT_OPS_JWT_HMAC_SECRET = 'PROJECT_OPS_JWT_HMAC_SECRET'",
                "raise ValueError('jwt_hmac_secret is required when auth_required=True')",
                "allowed_tenants = ()",
                "rate_limit_window_seconds = 60",
                "rate_limited = True",
                "request_metadata_byte_limit = 8192",
                "backup_policy = 'operator_managed_snapshot_required'",
                "restore_policy = 'operator_verified_restore_required'",
                "tenant_delete_policy = 'manual_approval_required'",
                "def _filter_snapshot_for_tenant(): pass",
                "route = '/audit/digest'",
                "audit_log_sha256 = 'abc'",
            ]
        ),
    )
    doc = _write_text(
        tmp_path / "production-ops-security.md",
        "Secret rotation, gateway/WAF/TLS, backup/restore, tenant delete, signed WORM audit, incident response.",
    )
    support = _write_json(
        tmp_path / "support.json",
        {
            "contract_pass": True,
            "bundle_policy": {"tenant_scoped": True},
            "checks": {
                "bundle_roundtrip_test_pass": True,
                "audit_event_digest_pass": True,
                "redaction_self_test_pass": True,
            },
            "audit_digest": {"sha256": "abc"},
        },
    )
    runtime = _write_json(
        tmp_path / "runtime.json",
        {
            "contract_pass": True,
            "runtime_package": {"supported_modes": ["saas", "on_prem", "air_gapped"]},
        },
    )

    payload = build_project_ops_deployment_drill_manifest.build_project_ops_deployment_drill_manifest(
        project_ops_api=api,
        production_security_doc=doc,
        support_bundle_manifest=support,
        runtime_packaging_manifest=runtime,
    )

    assert payload["contract_pass"] is True
    assert payload["drill_mode"] == "dry_run_contract"
    assert payload["live_deployment_claim"] is False
    assert payload["checks"]["attestation_sha256_present"] is True
    assert {row["status"] for row in payload["drill_rows"]} == {"pass"}


def test_project_ops_deployment_drill_manifest_blocks_missing_policy(tmp_path: Path) -> None:
    api = _write_text(tmp_path / "project_ops_api_service.py", "PROJECT_OPS_JWT_HMAC_SECRET = 'x'\n")
    doc = _write_text(tmp_path / "production-ops-security.md", "incident response")
    support = _write_json(tmp_path / "support.json", {"contract_pass": False, "checks": {}})
    runtime = _write_json(tmp_path / "runtime.json", {"contract_pass": False})

    payload = build_project_ops_deployment_drill_manifest.build_project_ops_deployment_drill_manifest(
        project_ops_api=api,
        production_security_doc=doc,
        support_bundle_manifest=support,
        runtime_packaging_manifest=runtime,
    )

    assert payload["contract_pass"] is False
    assert any("secret_rotation_negative_start" in blocker for blocker in payload["blockers"])
    assert any("backup_restore_policy_roundtrip" in blocker for blocker in payload["blockers"])
