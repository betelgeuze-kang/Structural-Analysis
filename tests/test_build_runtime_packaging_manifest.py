from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_runtime_packaging_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_runtime_packaging_manifest", SCRIPT_PATH)
assert SPEC is not None
build_runtime_packaging_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_runtime_packaging_manifest)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _runtime_fixture(tmp_path: Path) -> dict[str, Path]:
    _write_text(
        tmp_path / "LICENSE",
        """Copyright (c) 2026 Test owner.
All rights reserved.
No permission is granted except under a separate written agreement.
It is not evidence of product-license approval.
""",
    )
    crate_dir = tmp_path / "crate"
    _write_text(
        crate_dir / "Cargo.toml",
        '[package]\nname = "runtime-hook"\nversion = "0.2.0"\nedition = "2021"\n'
        'license-file = "../LICENSE"\npublish = false\n',
    )
    _write_text(
        crate_dir / "Cargo.lock",
        '[[package]]\nname = "runtime-hook"\nversion = "0.2.0"\n'
        '[[package]]\nname = "serde"\nversion = "1.0.0"\nchecksum = "abc"\n',
    )
    _write_text(crate_dir / "src" / "main.rs", "fn main() {}\n")
    _write_text(crate_dir / "src" / "lib.rs", "pub fn run() {}\n")
    _write_text(
        crate_dir / "target" / "release" / "libmgt_hip_full_residual_rust_ffi.so",
        "so\n",
    )

    return {
        "runtime_probe": _write_json(
            tmp_path / "probe.json",
            {
                "status": "pass",
                "rust_ffi_residual_gate_ready": True,
                "native_hip_c_abi": True,
                "operator_buffers_device_resident": True,
                "device_name": "AMD Radeon RX 6900 XT",
            },
        ),
        "runtime_wrapper": _write_text(tmp_path / "runtime-wrapper.py", "print('runtime')\n"),
        "crate_dir": crate_dir,
        "native_hip_ffi_source": _write_text(tmp_path / "hip_full_residual_ffi.cpp", "// hip\n"),
        "pyproject": _write_text(
            tmp_path / "pyproject.toml",
            '[project]\nname = "runtime-product"\nversion = "0.1.0"\n'
            'license = "LicenseRef-Repository-Default-No-License"\n'
            'license-files = ["LICENSE"]\n'
            'requires-python = ">=3.10"\ndependencies = ["numpy>=1.23"]\n',
        ),
        "package_json": _write_json(
            tmp_path / "package.json",
            {
                "name": "runtime-viewer",
                "version": "1.0.0",
                "private": True,
                "license": "SEE LICENSE IN LICENSE",
                "packageManager": "npm@11.19.0",
                "engines": {"node": "24.20.0", "npm": "11.19.0"},
                "dependencies": {"ajv": "8.20.0", "react": "18.2.0"},
                "devDependencies": {"postcss": "8.5.26"},
            },
        ),
        "package_lock": _write_json(
            tmp_path / "package-lock.json",
            {
                "name": "runtime-viewer",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "license": "SEE LICENSE IN LICENSE",
                "packages": {
                    "": {
                        "name": "runtime-viewer",
                        "version": "1.0.0",
                        "license": "SEE LICENSE IN LICENSE",
                        "engines": {"node": "24.20.0", "npm": "11.19.0"},
                        "dependencies": {"ajv": "8.20.0", "react": "18.2.0"},
                        "devDependencies": {"postcss": "8.5.26"},
                    },
                    "node_modules/ajv": {
                        "version": "8.20.0",
                        "license": "MIT",
                        "integrity": "sha512-ajv",
                    },
                    "node_modules/react": {
                        "version": "18.2.0",
                        "license": "MIT",
                        "integrity": "sha512-react",
                    },
                    "node_modules/postcss": {
                        "version": "8.5.26",
                        "dev": True,
                        "license": "MIT",
                        "integrity": "sha512-postcss",
                    },
                },
            },
        ),
        "rollback_runbook": _write_text(tmp_path / "runtime-runbook.md", "rollback\n"),
    }


def test_runtime_packaging_manifest_generates_sbom_native_and_compatibility(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)

    payload = build_runtime_packaging_manifest.build_runtime_packaging_manifest(
        manifest_out=tmp_path / "manifest.json",
        sbom_out=tmp_path / "sbom.json",
        native_artifact_manifest_out=tmp_path / "native.json",
        compatibility_matrix_out=tmp_path / "compat.json",
        **fixture,
    )

    assert payload["contract_pass"] is True
    assert payload["runtime_package"]["version"] == "0.2.0"
    assert payload["checks"]["strict_runtime_probe_pass"] is True
    assert payload["checks"]["native_artifact_manifest_pass"] is True
    assert payload["checks"]["version_compatibility_matrix_pass"] is True
    assert payload["checks"]["node_lock_graph_pass"] is True
    assert payload["checks"]["first_party_license_metadata_pass"] is True
    assert payload["checks"]["node_lock_graph"]["package_count"] == 3
    assert payload["authority"] == {
        "product_license_approval": False,
        "commercial_use_authority": False,
        "redistribution_authority": False,
        "third_party_redistribution_clearance": "not_established",
        "release_authority": False,
    }
    sbom = json.loads(Path(payload["required_evidence"]["sbom"]).read_text())
    assert any(
        row.get("name") == "ajv" and row.get("version") == "8.20.0"
        for row in sbom["components"]
    )
    assert any(
        row.get("name") == "postcss" and row.get("version") == "8.5.26"
        for row in sbom["components"]
    )
    assert sbom["first_party_license"]["contract_pass"] is True
    assert sbom["first_party_license"]["product_license_approval"] is False
    assert sbom["first_party_license"]["commercial_redistribution_approved"] is False
    assert sbom["first_party_license"]["third_party_redistribution_clearance"] == (
        "not_established"
    )
    assert sbom["authority"] == payload["authority"]
    assert set(sbom["source_hashes"]) == {
        "repository_license",
        "pyproject",
        "package_json",
        "package_lock",
        "cargo_toml",
        "cargo_lock",
    }
    assert payload["blockers"] == []
    assert Path(payload["required_evidence"]["sbom"]).exists()
    assert Path(payload["required_evidence"]["native_artifact_manifest"]).exists()
    assert Path(payload["required_evidence"]["version_compatibility_matrix"]).exists()
    native = json.loads(
        Path(payload["required_evidence"]["native_artifact_manifest"]).read_text()
    )
    compatibility = json.loads(
        Path(payload["required_evidence"]["version_compatibility_matrix"]).read_text()
    )
    assert native["authority"] == payload["authority"]
    assert compatibility["authority"] == payload["authority"]


def test_runtime_packaging_manifest_blocks_missing_native_artifact(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    (fixture["crate_dir"] / "src" / "lib.rs").unlink()

    payload = build_runtime_packaging_manifest.build_runtime_packaging_manifest(
        manifest_out=tmp_path / "manifest.json",
        sbom_out=tmp_path / "sbom.json",
        native_artifact_manifest_out=tmp_path / "native.json",
        compatibility_matrix_out=tmp_path / "compat.json",
        **fixture,
    )

    assert payload["contract_pass"] is False
    assert "native_artifact_manifest_not_green" in payload["blockers"]


def test_runtime_packaging_manifest_rejects_stale_ajv_or_lock_sbom(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    lock = json.loads(fixture["package_lock"].read_text(encoding="utf-8"))
    lock["packages"]["node_modules/ajv"]["version"] = "8.17.1"
    fixture["package_lock"].write_text(json.dumps(lock), encoding="utf-8")

    payload = build_runtime_packaging_manifest.build_runtime_packaging_manifest(
        manifest_out=tmp_path / "manifest.json",
        sbom_out=tmp_path / "sbom.json",
        native_artifact_manifest_out=tmp_path / "native.json",
        compatibility_matrix_out=tmp_path / "compat.json",
        **fixture,
    )

    assert payload["contract_pass"] is False
    assert "node_lock_graph_not_green" in payload["blockers"]
    assert payload["checks"]["version_compatibility_matrix_pass"] is False


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("first_party_license", "first_party_license_metadata_pass"),
        ("dependency_license", "node_lock_graph_pass"),
    ],
)
def test_runtime_packaging_manifest_rejects_license_metadata_drift(
    tmp_path: Path,
    mutation: str,
    expected_check: str,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    if mutation == "first_party_license":
        package = json.loads(fixture["package_json"].read_text(encoding="utf-8"))
        package["license"] = "MIT"
        fixture["package_json"].write_text(json.dumps(package), encoding="utf-8")
    else:
        lock = json.loads(fixture["package_lock"].read_text(encoding="utf-8"))
        del lock["packages"]["node_modules/react"]["license"]
        fixture["package_lock"].write_text(json.dumps(lock), encoding="utf-8")

    payload = build_runtime_packaging_manifest.build_runtime_packaging_manifest(
        manifest_out=tmp_path / "manifest.json",
        sbom_out=tmp_path / "sbom.json",
        native_artifact_manifest_out=tmp_path / "native.json",
        compatibility_matrix_out=tmp_path / "compat.json",
        **fixture,
    )

    assert payload["contract_pass"] is False
    assert payload["checks"][expected_check] is False


def _materialize_canonical_runtime_fixture(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path / "fixture")
    copies = {
        fixture["runtime_probe"]: build_runtime_packaging_manifest.DEFAULT_RUNTIME_PROBE,
        fixture["runtime_wrapper"]: build_runtime_packaging_manifest.DEFAULT_RUNTIME_WRAPPER,
        fixture["native_hip_ffi_source"]: (
            build_runtime_packaging_manifest.DEFAULT_NATIVE_HIP_FFI_SOURCE
        ),
        fixture["pyproject"]: build_runtime_packaging_manifest.DEFAULT_PYPROJECT,
        fixture["package_json"]: build_runtime_packaging_manifest.DEFAULT_PACKAGE_JSON,
        fixture["package_lock"]: build_runtime_packaging_manifest.DEFAULT_PACKAGE_LOCK,
        fixture["rollback_runbook"]: (
            build_runtime_packaging_manifest.DEFAULT_ROLLBACK_RUNBOOK
        ),
    }
    for source, relative in copies.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(fixture["pyproject"].parent / "LICENSE", tmp_path / "LICENSE")
    shutil.copytree(
        fixture["crate_dir"],
        tmp_path / build_runtime_packaging_manifest.DEFAULT_CRATE_DIR,
    )


def test_runtime_packaging_validator_rebuilds_all_canonical_leaves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _materialize_canonical_runtime_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    build_runtime_packaging_manifest.build_runtime_packaging_manifest()

    assert (
        build_runtime_packaging_manifest.validate_runtime_packaging_artifacts(
            tmp_path
        )
        == []
    )


def test_runtime_packaging_validator_rejects_stale_sbom_even_with_parent_rehash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _materialize_canonical_runtime_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    build_runtime_packaging_manifest.build_runtime_packaging_manifest()
    sbom_path = tmp_path / build_runtime_packaging_manifest.DEFAULT_SBOM_OUT
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    sbom["components"][0]["version"] = "forged"
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
    manifest_path = tmp_path / build_runtime_packaging_manifest.DEFAULT_MANIFEST_OUT
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["sbom"]["sha256"] = (
        build_runtime_packaging_manifest._sha256_path(sbom_path)
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    violations = (
        build_runtime_packaging_manifest.validate_runtime_packaging_artifacts(
            tmp_path
        )
    )

    assert (
        "runtime_artifact_exact_rebuild_mismatch:"
        "implementation/phase1/runtime_sbom.json"
    ) in violations
