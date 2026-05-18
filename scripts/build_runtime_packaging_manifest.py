#!/usr/bin/env python3
"""Build production runtime packaging evidence for the independent product gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "production-runtime-packaging-manifest.v1"
SBOM_SCHEMA_VERSION = "runtime-sbom.v1"
NATIVE_ARTIFACT_SCHEMA_VERSION = "native-runtime-artifact-manifest.v1"
COMPATIBILITY_SCHEMA_VERSION = "runtime-version-compatibility-matrix.v1"

DEFAULT_MANIFEST_OUT = Path("implementation/phase1/production_runtime_packaging_manifest.json")
DEFAULT_SBOM_OUT = Path("implementation/phase1/runtime_sbom.json")
DEFAULT_NATIVE_ARTIFACT_MANIFEST_OUT = Path("implementation/phase1/native_runtime_artifact_manifest.json")
DEFAULT_COMPATIBILITY_MATRIX_OUT = Path("implementation/phase1/runtime_version_compatibility_matrix.json")
DEFAULT_RUNTIME_PROBE = Path("implementation/phase1/zero_copy_real_probe_report_strict.json")
DEFAULT_RUNTIME_WRAPPER = Path("implementation/phase1/rust_hip_md3bead_hook.py")
DEFAULT_CRATE_DIR = Path("implementation/phase1/rust_hip_md3bead_hook")
DEFAULT_PYPROJECT = Path("pyproject.toml")
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_ROLLBACK_RUNBOOK = Path("docs/runtime-production-packaging.md")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_row(path: Path, *, label: str, required: bool = True) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "required": required,
        "available": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": _sha256_path(path) if path.exists() else "",
    }


def _toml_string(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    return match.group(1) if match else ""


def _toml_list(text: str, key: str) -> list[str]:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r"[\"']([^\"']+)[\"']", match.group(1))


def _parse_pyproject(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    return {
        "name": _toml_string(text, "name"),
        "version": _toml_string(text, "version"),
        "requires_python": _toml_string(text, "requires-python"),
        "dependencies": _toml_list(text, "dependencies"),
    }


def _parse_cargo_toml(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    return {
        "name": _toml_string(text, "name"),
        "version": _toml_string(text, "version"),
        "edition": _toml_string(text, "edition"),
    }


def _parse_cargo_lock(path: Path) -> list[dict[str, Any]]:
    text = _read_text(path)
    packages: list[dict[str, Any]] = []
    for block in text.split("[[package]]"):
        name = _toml_string(block, "name")
        if not name:
            continue
        packages.append(
            {
                "name": name,
                "version": _toml_string(block, "version"),
                "source": _toml_string(block, "source"),
                "checksum": _toml_string(block, "checksum"),
            }
        )
    return packages


def _component_rows(
    *,
    pyproject: Path,
    package_json: Path,
    cargo_toml: Path,
    cargo_lock: Path,
) -> list[dict[str, Any]]:
    python_project = _parse_pyproject(pyproject)
    node_project = _load_json(package_json)
    cargo_project = _parse_cargo_toml(cargo_toml)
    cargo_packages = _parse_cargo_lock(cargo_lock)

    rows: list[dict[str, Any]] = []
    if python_project.get("name"):
        rows.append(
            {
                "ecosystem": "python",
                "name": python_project["name"],
                "version": python_project.get("version", ""),
                "kind": "project",
                "requires": python_project.get("requires_python", ""),
            }
        )
    for dependency in python_project.get("dependencies", []):
        rows.append({"ecosystem": "python", "name": dependency, "version": "", "kind": "dependency"})

    if node_project:
        rows.append(
            {
                "ecosystem": "node",
                "name": str(node_project.get("name", "")),
                "version": str(node_project.get("version", "")),
                "kind": "project",
                "requires": node_project.get("engines", {}),
            }
        )
        for section in ("dependencies", "devDependencies"):
            deps = node_project.get(section, {})
            if isinstance(deps, dict):
                for name, version in sorted(deps.items()):
                    rows.append({"ecosystem": "node", "name": name, "version": str(version), "kind": section})

    if cargo_project.get("name"):
        rows.append(
            {
                "ecosystem": "rust",
                "name": cargo_project["name"],
                "version": cargo_project.get("version", ""),
                "kind": "crate",
                "requires": {"edition": cargo_project.get("edition", "")},
            }
        )
    for package in cargo_packages:
        rows.append({"ecosystem": "rust", **package, "kind": "cargo-lock-package"})
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_sbom(
    *,
    out: Path,
    pyproject: Path,
    package_json: Path,
    cargo_toml: Path,
    cargo_lock: Path,
) -> dict[str, Any]:
    rows = _component_rows(
        pyproject=pyproject,
        package_json=package_json,
        cargo_toml=cargo_toml,
        cargo_lock=cargo_lock,
    )
    payload = {
        "schema_version": SBOM_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "component_count": len(rows),
        "components": rows,
        "source_files": {
            "pyproject": str(pyproject),
            "package_json": str(package_json),
            "cargo_toml": str(cargo_toml),
            "cargo_lock": str(cargo_lock),
        },
    }
    _write_json(out, payload)
    payload["path"] = str(out)
    payload["sha256"] = _sha256_path(out)
    return payload


def _build_native_artifact_manifest(
    *,
    out: Path,
    runtime_wrapper: Path,
    crate_dir: Path,
) -> dict[str, Any]:
    rows = [
        _artifact_row(runtime_wrapper, label="runtime_wrapper"),
        _artifact_row(crate_dir / "Cargo.toml", label="cargo_toml"),
        _artifact_row(crate_dir / "Cargo.lock", label="cargo_lock"),
        _artifact_row(crate_dir / "src" / "main.rs", label="rust_main"),
        _artifact_row(crate_dir / "src" / "lib.rs", label="rust_lib"),
        _artifact_row(crate_dir / "target" / "release" / "rust_hip_md3bead_hook", label="release_binary"),
        _artifact_row(crate_dir / "target" / "release" / "librust_hip_md3bead_hook.so", label="release_cdylib"),
        _artifact_row(crate_dir / "target" / "release" / "librust_hip_md3bead_hook.rlib", label="release_rlib"),
    ]
    missing = [row["label"] for row in rows if row["required"] and not row["available"]]
    payload = {
        "schema_version": NATIVE_ARTIFACT_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": not missing,
        "artifact_count": len(rows),
        "available_artifact_count": sum(1 for row in rows if row["available"]),
        "artifact_rows": rows,
        "missing_required": missing,
    }
    _write_json(out, payload)
    payload["path"] = str(out)
    payload["sha256"] = _sha256_path(out)
    return payload


def _build_compatibility_matrix(
    *,
    out: Path,
    pyproject: Path,
    package_json: Path,
    cargo_toml: Path,
    runtime_probe: Path,
) -> dict[str, Any]:
    python_project = _parse_pyproject(pyproject)
    node_project = _load_json(package_json)
    cargo_project = _parse_cargo_toml(cargo_toml)
    probe = _load_json(runtime_probe)
    probe_detail = probe.get("probe", {}) if isinstance(probe.get("probe"), dict) else {}
    rows = [
        {
            "target": "python_runtime",
            "requirement": python_project.get("requires_python", ""),
            "status": "declared",
        },
        {
            "target": "node_viewer_shell",
            "requirement": node_project.get("engines", {}),
            "status": "declared",
        },
        {
            "target": "rust_native_hook",
            "requirement": {
                "crate": cargo_project.get("name", ""),
                "version": cargo_project.get("version", ""),
                "edition": cargo_project.get("edition", ""),
            },
            "status": "declared",
        },
        {
            "target": "strict_rust_hip_probe",
            "requirement": {
                "runtime_kind": probe.get("runtime_kind", ""),
                "runtime_backend": probe.get("runtime_backend", ""),
                "device": probe_detail.get("device", ""),
                "cpu_fallback_used": bool(probe.get("cpu_fallback_used", True)),
                "host_copy_share": probe.get("host_copy_share", 1.0),
            },
            "status": "verified" if bool(probe.get("strict_rust_hip_pass")) else "blocked",
        },
    ]
    payload = {
        "schema_version": COMPATIBILITY_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": bool(probe.get("strict_rust_hip_pass")),
        "compatibility_rows": rows,
        "deployment_modes": [
            {"mode": "saas", "status": "manifest_ready", "requires": "production ops gateway secret injection"},
            {"mode": "on_prem", "status": "manifest_ready", "requires": "offline artifact cache and license file"},
            {"mode": "air_gapped", "status": "manifest_ready", "requires": "signed artifact transfer package"},
        ],
    }
    _write_json(out, payload)
    payload["path"] = str(out)
    payload["sha256"] = _sha256_path(out)
    return payload


def build_runtime_packaging_manifest(
    *,
    manifest_out: Path = DEFAULT_MANIFEST_OUT,
    sbom_out: Path = DEFAULT_SBOM_OUT,
    native_artifact_manifest_out: Path = DEFAULT_NATIVE_ARTIFACT_MANIFEST_OUT,
    compatibility_matrix_out: Path = DEFAULT_COMPATIBILITY_MATRIX_OUT,
    runtime_probe: Path = DEFAULT_RUNTIME_PROBE,
    runtime_wrapper: Path = DEFAULT_RUNTIME_WRAPPER,
    crate_dir: Path = DEFAULT_CRATE_DIR,
    pyproject: Path = DEFAULT_PYPROJECT,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    rollback_runbook: Path = DEFAULT_ROLLBACK_RUNBOOK,
) -> dict[str, Any]:
    cargo_toml = crate_dir / "Cargo.toml"
    cargo_lock = crate_dir / "Cargo.lock"
    sbom = _build_sbom(
        out=sbom_out,
        pyproject=pyproject,
        package_json=package_json,
        cargo_toml=cargo_toml,
        cargo_lock=cargo_lock,
    )
    native_manifest = _build_native_artifact_manifest(
        out=native_artifact_manifest_out,
        runtime_wrapper=runtime_wrapper,
        crate_dir=crate_dir,
    )
    compatibility = _build_compatibility_matrix(
        out=compatibility_matrix_out,
        pyproject=pyproject,
        package_json=package_json,
        cargo_toml=cargo_toml,
        runtime_probe=runtime_probe,
    )
    probe = _load_json(runtime_probe)
    pyproject_payload = _parse_pyproject(pyproject)
    cargo_payload = _parse_cargo_toml(cargo_toml)
    runtime_version = cargo_payload.get("version") or pyproject_payload.get("version") or ""
    blockers = [
        *(["runtime_version_missing"] if not runtime_version else []),
        *(["strict_runtime_probe_missing"] if not runtime_probe.exists() else []),
        *(["strict_runtime_probe_not_green"] if not bool(probe.get("strict_rust_hip_pass")) else []),
        *(["sbom_missing"] if not sbom_out.exists() else []),
        *(["native_artifact_manifest_not_green"] if not native_manifest.get("contract_pass") else []),
        *(["version_compatibility_matrix_not_green"] if not compatibility.get("contract_pass") else []),
        *(["rollback_runbook_missing"] if not rollback_runbook.exists() else []),
    ]
    contract_pass = not blockers
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_RUNTIME_PACKAGING_EVIDENCE_PENDING",
        "summary_line": (
            f"Runtime production packaging: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"version={runtime_version or 'missing'} | "
            f"sbom_components={sbom['component_count']} | "
            f"native_artifacts={native_manifest['available_artifact_count']}/{native_manifest['artifact_count']}"
        ),
        "runtime_package": {
            "package_id": "structural-analysis-runtime-production-candidate",
            "version": runtime_version,
            "supported_modes": ["saas", "on_prem", "air_gapped"],
            "supported_backends": ["cpu", "rust_hip"],
            "cpu_fallback_policy": "explicit_only_no_silent_fallback",
        },
        "required_evidence": {
            "strict_runtime_probe": str(runtime_probe),
            "sbom": str(sbom_out),
            "native_artifact_manifest": str(native_artifact_manifest_out),
            "version_compatibility_matrix": str(compatibility_matrix_out),
            "rollback_runbook": str(rollback_runbook),
        },
        "checks": {
            "strict_runtime_probe_pass": bool(probe.get("strict_rust_hip_pass")),
            "sbom_present": sbom_out.exists(),
            "native_artifact_manifest_pass": bool(native_manifest.get("contract_pass")),
            "version_compatibility_matrix_pass": bool(compatibility.get("contract_pass")),
            "rollback_runbook_present": rollback_runbook.exists(),
        },
        "artifacts": {
            "sbom": {"path": str(sbom_out), "sha256": sbom["sha256"]},
            "native_artifact_manifest": {
                "path": str(native_artifact_manifest_out),
                "sha256": native_manifest["sha256"],
            },
            "version_compatibility_matrix": {
                "path": str(compatibility_matrix_out),
                "sha256": compatibility["sha256"],
            },
        },
        "blockers": blockers,
    }
    _write_json(manifest_out, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--sbom-out", type=Path, default=DEFAULT_SBOM_OUT)
    parser.add_argument("--native-artifact-manifest-out", type=Path, default=DEFAULT_NATIVE_ARTIFACT_MANIFEST_OUT)
    parser.add_argument("--compatibility-matrix-out", type=Path, default=DEFAULT_COMPATIBILITY_MATRIX_OUT)
    parser.add_argument("--runtime-probe", type=Path, default=DEFAULT_RUNTIME_PROBE)
    parser.add_argument("--runtime-wrapper", type=Path, default=DEFAULT_RUNTIME_WRAPPER)
    parser.add_argument("--crate-dir", type=Path, default=DEFAULT_CRATE_DIR)
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--rollback-runbook", type=Path, default=DEFAULT_ROLLBACK_RUNBOOK)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_runtime_packaging_manifest(
        manifest_out=args.manifest_out,
        sbom_out=args.sbom_out,
        native_artifact_manifest_out=args.native_artifact_manifest_out,
        compatibility_matrix_out=args.compatibility_matrix_out,
        runtime_probe=args.runtime_probe,
        runtime_wrapper=args.runtime_wrapper,
        crate_dir=args.crate_dir,
        pyproject=args.pyproject,
        package_json=args.package_json,
        rollback_runbook=args.rollback_runbook,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
