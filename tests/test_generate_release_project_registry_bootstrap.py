from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import zipfile


SCRIPT = Path("implementation/phase1/generate_release_project_registry_bootstrap.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_release_project_registry_bootstrap_cli(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    release_signing_dir = release_dir / "signing"
    release_pub = release_signing_dir / "release_registry_ed25519.pub.pem"
    release_sig = release_signing_dir / "release_registry.signature.b64"
    release_pub.parent.mkdir(parents=True, exist_ok=True)
    release_pub.write_text("PUBLIC KEY PLACEHOLDER\n", encoding="utf-8")
    release_sig.write_text("U0lHTkFUVVJF\n", encoding="utf-8")

    repro = tmp_path / "reproducibility_version_lock_report.json"
    lock_manifest = release_dir / "version_lock_manifest.json"
    committee_package = release_dir / "committee_review" / "committee_review_package_report.json"
    _write_json(repro, {"contract_pass": True, "reason_code": "PASS"})
    _write_json(lock_manifest, {"schema_version": "1.0", "replay_digest": "a" * 64})
    _write_json(committee_package, {"contract_pass": True, "reason_code": "PASS"})

    release_registry = release_dir / "release_registry.json"
    _write_json(
        release_registry,
        {
            "generated_at": "2026-04-19T06:00:00+00:00",
            "contract_pass": True,
            "checks": {
                "signature_verified_pass": True,
            },
            "inputs": {
                "public_key_out": str(release_pub),
                "signature_out": str(release_sig),
            },
            "signature": {
                "public_key_path": str(release_pub),
                "signature_out": str(release_sig),
            },
            "registry_body": {
                "artifacts": [
                    {
                        "label": "repro_report",
                        "path": str(repro),
                    },
                    {
                        "label": "lock_manifest",
                        "path": str(lock_manifest),
                    },
                    {
                        "label": "committee_package",
                        "path": str(committee_package),
                    },
                ]
            },
        },
    )

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--release-dir", str(release_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    project_registry = release_dir / "project_registry.json"
    project_package = release_dir / "project_package.zip"
    project_signature = release_dir / "project_registry.signature.b64"
    project_public_key = release_signing_dir / "project_registry_ed25519.pub.pem"
    assert project_registry.exists()
    assert project_package.exists()
    assert project_signature.exists()
    assert project_public_key.exists()

    payload = json.loads(project_registry.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["generated_at"] == "2026-04-19T06:00:00+00:00"
    assert payload["summary"]["artifact_count"] == 5
    assert payload["summary"]["approval_count"] == 2
    assert payload["checks"]["audit_trail_complete_pass"] is True
    assert payload["checks"]["approval_complete_pass"] is True
    assert payload["checks"]["signature_verified_pass"] is True
    assert payload["artifacts"]["project_package_zip"] == str(project_package)
    assert payload["artifacts"]["project_registry_json"] == str(project_registry)
    assert payload["artifacts"]["project_signature_b64"] == str(project_signature)

    with zipfile.ZipFile(project_package) as zf:
        assert zf.namelist() == [
            "artifacts/committee_review_package_report.json",
            "artifacts/release_registry.signature.b64",
            "artifacts/release_registry_ed25519.pub.pem",
            "artifacts/reproducibility_version_lock_report.json",
            "artifacts/version_lock_manifest.json",
            "package_manifest.json",
        ]
        package_manifest = json.loads(zf.read("package_manifest.json").decode("utf-8"))

    assert package_manifest["generated_at"] == "2026-04-19T06:00:00+00:00"
    assert package_manifest["project_id"] == "phase1-release"
    assert len(package_manifest["artifact_rows"]) == 5
