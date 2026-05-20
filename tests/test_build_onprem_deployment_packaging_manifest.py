from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_onprem_deployment_packaging_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_onprem_deployment_packaging_manifest", SCRIPT_PATH)
assert SPEC is not None
build_onprem_deployment_packaging_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_onprem_deployment_packaging_manifest)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _packaging_fixture(tmp_path: Path) -> dict[str, Path]:
    return {
        "containerfile": _write_text(
            tmp_path / "Containerfile",
            "FROM python:3.10-slim\nCMD [\"python\", \"implementation/phase1/project_ops_api_service.py\", \"--auth-required\"]\n",
        ),
        "compose_file": _write_text(
            tmp_path / "compose.yml",
            "services:\n  app:\n    read_only: true\n    ports:\n      - \"127.0.0.1:8080:8080\"\n"
            "    environment:\n      PROJECT_OPS_JWT_HMAC_SECRET: ${PROJECT_OPS_JWT_HMAC_SECRET:?set}\n"
            "      PROJECT_OPS_TELEMETRY_ENABLED: \"false\"\n"
            "    volumes:\n      - support_bundle:/support_bundle\nvolumes:\n  support_bundle:\n",
        ),
        "offline_license": _write_json(
            tmp_path / "offline-license.json",
            {
                "schema_version": "offline-license-file.example.v1",
                "tenant_id": "tenant-a",
                "expires_at_utc": "2026-12-31T23:59:59Z",
                "features": ["project_ops_api", "support_bundle"],
                "public_key_id": "key",
                "signature": "sig",
            },
        ),
        "signed_update_package": _write_json(
            tmp_path / "update.json",
            {
                "schema_version": "signed-update-package.example.v1",
                "network_policy": "offline_transfer_only",
                "artifacts": [{"label": "a", "sha256": "abc"}, {"label": "b", "sha256": "def"}],
                "rollback": {"policy": "restore"},
                "signature": "sig",
            },
        ),
        "packaging_readme": _write_text(
            tmp_path / "README.md",
            "offline transfer, network isolated, signed update, support bundle handoff\n",
        ),
        "runtime_packaging_manifest": _write_json(
            tmp_path / "runtime.json",
            {
                "contract_pass": True,
                "runtime_package": {"supported_modes": ["saas", "on_prem", "air_gapped"]},
            },
        ),
        "support_bundle_manifest": _write_json(
            tmp_path / "support.json",
            {
                "contract_pass": True,
                "checks": {"bundle_roundtrip_test_pass": True},
            },
        ),
    }


def test_onprem_deployment_packaging_manifest_passes_skeleton_contract(tmp_path: Path) -> None:
    payload = build_onprem_deployment_packaging_manifest.build_onprem_deployment_packaging_manifest(
        **_packaging_fixture(tmp_path)
    )

    assert payload["contract_pass"] is True
    assert payload["package_mode"] == "skeleton_contract"
    assert payload["live_deployment_claim"] is False
    assert payload["supported_deployment_modes"] == ["on_prem", "air_gapped"]
    assert {row["status"] for row in payload["check_rows"]} == {"pass"}
    assert payload["attestation_envelope"]["sha256"]


def test_onprem_deployment_packaging_manifest_blocks_missing_license_signature(tmp_path: Path) -> None:
    fixture = _packaging_fixture(tmp_path)
    license_payload = json.loads(fixture["offline_license"].read_text(encoding="utf-8"))
    license_payload.pop("signature")
    fixture["offline_license"].write_text(json.dumps(license_payload), encoding="utf-8")

    payload = build_onprem_deployment_packaging_manifest.build_onprem_deployment_packaging_manifest(**fixture)

    assert payload["contract_pass"] is False
    assert any("offline_license_contract:signature_placeholder_present" in blocker for blocker in payload["blockers"])
