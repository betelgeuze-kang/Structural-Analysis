from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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
    crate_dir = tmp_path / "crate"
    _write_text(
        crate_dir / "Cargo.toml",
        '[package]\nname = "runtime-hook"\nversion = "0.2.0"\nedition = "2021"\n',
    )
    _write_text(
        crate_dir / "Cargo.lock",
        '[[package]]\nname = "runtime-hook"\nversion = "0.2.0"\n'
        '[[package]]\nname = "serde"\nversion = "1.0.0"\nchecksum = "abc"\n',
    )
    _write_text(crate_dir / "src" / "main.rs", "fn main() {}\n")
    _write_text(crate_dir / "src" / "lib.rs", "pub fn run() {}\n")
    _write_text(crate_dir / "target" / "release" / "rust_hip_md3bead_hook", "binary\n")
    _write_text(crate_dir / "target" / "release" / "librust_hip_md3bead_hook.so", "so\n")
    _write_text(crate_dir / "target" / "release" / "librust_hip_md3bead_hook.rlib", "rlib\n")

    return {
        "runtime_probe": _write_json(
            tmp_path / "probe.json",
            {
                "strict_rust_hip_pass": True,
                "runtime_kind": "rust_hip",
                "runtime_backend": "rocm_torch",
                "cpu_fallback_used": False,
                "host_copy_share": 0.0,
                "probe": {"device": "cuda:0"},
            },
        ),
        "runtime_wrapper": _write_text(tmp_path / "runtime-wrapper.py", "print('runtime')\n"),
        "crate_dir": crate_dir,
        "pyproject": _write_text(
            tmp_path / "pyproject.toml",
            '[project]\nname = "runtime-product"\nversion = "0.1.0"\n'
            'requires-python = ">=3.10"\ndependencies = ["numpy>=1.23"]\n',
        ),
        "package_json": _write_json(
            tmp_path / "package.json",
            {
                "name": "runtime-viewer",
                "version": "1.0.0",
                "engines": {"node": ">=20"},
                "dependencies": {"react": "18.2.0"},
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
    assert payload["blockers"] == []
    assert Path(payload["required_evidence"]["sbom"]).exists()
    assert Path(payload["required_evidence"]["native_artifact_manifest"]).exists()
    assert Path(payload["required_evidence"]["version_compatibility_matrix"]).exists()


def test_runtime_packaging_manifest_blocks_missing_native_artifact(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    (fixture["crate_dir"] / "target" / "release" / "rust_hip_md3bead_hook").unlink()

    payload = build_runtime_packaging_manifest.build_runtime_packaging_manifest(
        manifest_out=tmp_path / "manifest.json",
        sbom_out=tmp_path / "sbom.json",
        native_artifact_manifest_out=tmp_path / "native.json",
        compatibility_matrix_out=tmp_path / "compat.json",
        **fixture,
    )

    assert payload["contract_pass"] is False
    assert "native_artifact_manifest_not_green" in payload["blockers"]
