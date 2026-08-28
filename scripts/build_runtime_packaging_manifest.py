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
DEFAULT_RUNTIME_PROBE = Path(
    "implementation/phase1/release_evidence/productization/"
    "mgt_rust_hip_full_residual_ffi_followup376_probe.json"
)
DEFAULT_RUNTIME_WRAPPER = Path("implementation/phase1/run_mgt_rust_hip_full_residual_ffi_probe.py")
DEFAULT_CRATE_DIR = Path("implementation/phase1/mgt_hip_full_residual_ffi")
DEFAULT_NATIVE_HIP_FFI_SOURCE = Path("implementation/phase1/hip_full_residual_ffi.cpp")
DEFAULT_PYPROJECT = Path("pyproject.toml")
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_PACKAGE_LOCK = Path("package-lock.json")
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


def _node_lock_components(
    package_json: Path, package_lock: Path
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    manifest = _load_json(package_json)
    lock = _load_json(package_lock)
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    graph_rows: list[dict[str, Any]] = []
    if isinstance(packages, dict):
        for path, row in sorted(packages.items()):
            if path == "" or not isinstance(path, str) or not isinstance(row, dict):
                continue
            name = path.rsplit("node_modules/", maxsplit=1)[-1]
            graph_rows.append(
                {
                    "ecosystem": "node",
                    "kind": "package-lock-v3-package",
                    "name": name,
                    "version": str(row.get("version", "")),
                    "lock_path": path,
                    "development": row.get("dev") is True
                    or row.get("devOptional") is True,
                    "optional": row.get("optional") is True,
                    "peer": row.get("peer") is True,
                    "integrity": str(row.get("integrity", "")),
                }
            )
    ajv = packages.get("node_modules/ajv") if isinstance(packages, dict) else None
    postcss = (
        packages.get("node_modules/postcss") if isinstance(packages, dict) else None
    )
    graph = {
        "lockfile_version": lock.get("lockfileVersion"),
        "requires": lock.get("requires"),
        "package_count": len(graph_rows),
        "ajv_version": ajv.get("version") if isinstance(ajv, dict) else "",
        "postcss_version": (
            postcss.get("version") if isinstance(postcss, dict) else ""
        ),
        "package_json_sha256": (
            _sha256_path(package_json) if package_json.is_file() else ""
        ),
        "package_lock_sha256": (
            _sha256_path(package_lock) if package_lock.is_file() else ""
        ),
    }
    direct_fields = ("dependencies", "devDependencies", "optionalDependencies")
    contract_pass = bool(
        manifest.get("packageManager") == "npm@11.19.0"
        and manifest.get("engines") == {"node": "24.20.0", "npm": "11.19.0"}
        and isinstance(root, dict)
        and lock.get("name") == manifest.get("name") == root.get("name")
        and lock.get("version") == manifest.get("version") == root.get("version")
        and type(lock.get("lockfileVersion")) is int
        and lock.get("lockfileVersion") == 3
        and lock.get("requires") is True
        and root.get("engines") == manifest.get("engines")
        and all(root.get(field, {}) == manifest.get(field, {}) for field in direct_fields)
        and graph["package_count"] == len(packages) - 1
        and graph["ajv_version"] == "8.20.0"
        and graph["postcss_version"] == "8.5.26"
        and all(row["name"] and row["version"] for row in graph_rows)
    )
    project = {
        "ecosystem": "node",
        "name": str(manifest.get("name", "")),
        "version": str(manifest.get("version", "")),
        "kind": "project",
        "requires": manifest.get("engines", {}),
        "package_manager": manifest.get("packageManager", ""),
        "lockfile_version": lock.get("lockfileVersion"),
    }
    return [project, *graph_rows], contract_pass, graph


def _runtime_probe_pass(probe: dict[str, Any]) -> bool:
    if bool(probe.get("strict_rust_hip_pass")):
        return True
    return bool(
        probe.get("status") == "pass"
        and probe.get("rust_ffi_residual_gate_ready")
        and probe.get("native_hip_c_abi")
        and probe.get("operator_buffers_device_resident")
    )


def _runtime_probe_requirement(probe: dict[str, Any]) -> dict[str, Any]:
    probe_detail = probe.get("probe", {}) if isinstance(probe.get("probe"), dict) else {}
    return {
        "runtime_kind": probe.get("runtime_kind", "mgt_rust_hip_full_residual_ffi"),
        "runtime_backend": probe.get("runtime_backend", "native_hip_c_abi"),
        "device": probe_detail.get("device", probe.get("device_name", "")),
        "cpu_fallback_used": bool(probe.get("cpu_fallback_used", False)),
        "native_hip_c_abi": bool(probe.get("native_hip_c_abi")),
        "operator_buffers_device_resident": bool(
            probe.get("operator_buffers_device_resident")
        ),
        "rust_ffi_residual_gate_ready": bool(probe.get("rust_ffi_residual_gate_ready")),
    }


def _component_rows(
    *,
    pyproject: Path,
    package_json: Path,
    package_lock: Path,
    cargo_toml: Path,
    cargo_lock: Path,
) -> list[dict[str, Any]]:
    python_project = _parse_pyproject(pyproject)
    node_components, _, _ = _node_lock_components(package_json, package_lock)
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

    rows.extend(node_components)

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
    package_lock: Path,
    cargo_toml: Path,
    cargo_lock: Path,
) -> dict[str, Any]:
    rows = _component_rows(
        pyproject=pyproject,
        package_json=package_json,
        package_lock=package_lock,
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
            "package_lock": str(package_lock),
            "cargo_toml": str(cargo_toml),
            "cargo_lock": str(cargo_lock),
        },
        "source_hashes": {
            "package_json": _sha256_path(package_json),
            "package_lock": _sha256_path(package_lock),
        },
        "claim_boundary": {
            "allowed": ["package-lock-v3 transitive component inventory"],
            "not_granted": [
                "license or redistribution clearance",
                "product signing authority",
                "release authority",
            ],
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
    native_hip_ffi_source: Path,
) -> dict[str, Any]:
    rows = [
        _artifact_row(runtime_wrapper, label="runtime_wrapper"),
        _artifact_row(crate_dir / "Cargo.toml", label="cargo_toml"),
        _artifact_row(crate_dir / "Cargo.lock", label="cargo_lock"),
        _artifact_row(crate_dir / "src" / "lib.rs", label="rust_lib"),
        _artifact_row(native_hip_ffi_source, label="native_hip_c_abi_source"),
        _artifact_row(
            crate_dir
            / "target"
            / "release"
            / "libmgt_hip_full_residual_rust_ffi.so",
            label="release_cdylib",
            required=False,
        ),
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
    package_lock: Path,
    cargo_toml: Path,
    runtime_probe: Path,
) -> dict[str, Any]:
    python_project = _parse_pyproject(pyproject)
    node_project = _load_json(package_json)
    _, node_graph_pass, node_graph = _node_lock_components(
        package_json, package_lock
    )
    cargo_project = _parse_cargo_toml(cargo_toml)
    probe = _load_json(runtime_probe)
    rows = [
        {
            "target": "python_runtime",
            "requirement": python_project.get("requires_python", ""),
            "status": "declared",
        },
        {
            "target": "node_viewer_shell",
            "requirement": {
                "engines": node_project.get("engines", {}),
                "package_manager": node_project.get("packageManager", ""),
                "lock_graph": node_graph,
            },
            "status": "verified" if node_graph_pass else "blocked",
        },
        {
            "target": "mgt_rust_hip_full_residual_ffi",
            "requirement": {
                "crate": cargo_project.get("name", ""),
                "version": cargo_project.get("version", ""),
                "edition": cargo_project.get("edition", ""),
            },
            "status": "declared",
        },
        {
            "target": "strict_rust_hip_probe",
            "requirement": _runtime_probe_requirement(probe),
            "status": "verified" if _runtime_probe_pass(probe) else "blocked",
        },
    ]
    payload = {
        "schema_version": COMPATIBILITY_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": _runtime_probe_pass(probe) and node_graph_pass,
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
    native_hip_ffi_source: Path = DEFAULT_NATIVE_HIP_FFI_SOURCE,
    pyproject: Path = DEFAULT_PYPROJECT,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
    rollback_runbook: Path = DEFAULT_ROLLBACK_RUNBOOK,
) -> dict[str, Any]:
    cargo_toml = crate_dir / "Cargo.toml"
    cargo_lock = crate_dir / "Cargo.lock"
    sbom = _build_sbom(
        out=sbom_out,
        pyproject=pyproject,
        package_json=package_json,
        package_lock=package_lock,
        cargo_toml=cargo_toml,
        cargo_lock=cargo_lock,
    )
    native_manifest = _build_native_artifact_manifest(
        out=native_artifact_manifest_out,
        runtime_wrapper=runtime_wrapper,
        crate_dir=crate_dir,
        native_hip_ffi_source=native_hip_ffi_source,
    )
    compatibility = _build_compatibility_matrix(
        out=compatibility_matrix_out,
        pyproject=pyproject,
        package_json=package_json,
        package_lock=package_lock,
        cargo_toml=cargo_toml,
        runtime_probe=runtime_probe,
    )
    probe = _load_json(runtime_probe)
    pyproject_payload = _parse_pyproject(pyproject)
    cargo_payload = _parse_cargo_toml(cargo_toml)
    runtime_version = cargo_payload.get("version") or pyproject_payload.get("version") or ""
    runtime_probe_pass = _runtime_probe_pass(probe)
    _, node_graph_pass, node_graph = _node_lock_components(
        package_json, package_lock
    )
    blockers = [
        *(["runtime_version_missing"] if not runtime_version else []),
        *(["strict_runtime_probe_missing"] if not runtime_probe.exists() else []),
        *(["strict_runtime_probe_not_green"] if not runtime_probe_pass else []),
        *(["node_lock_graph_not_green"] if not node_graph_pass else []),
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
            "supported_backends": ["cpu", "mgt_rust_hip_full_residual_ffi"],
            "cpu_fallback_policy": "explicit_only_no_silent_fallback",
        },
        "required_evidence": {
            "strict_runtime_probe": str(runtime_probe),
            "sbom": str(sbom_out),
            "native_artifact_manifest": str(native_artifact_manifest_out),
            "version_compatibility_matrix": str(compatibility_matrix_out),
            "package_lock": str(package_lock),
            "rollback_runbook": str(rollback_runbook),
        },
        "checks": {
            "strict_runtime_probe_pass": runtime_probe_pass,
            "sbom_present": sbom_out.exists(),
            "native_artifact_manifest_pass": bool(native_manifest.get("contract_pass")),
            "version_compatibility_matrix_pass": bool(compatibility.get("contract_pass")),
            "node_lock_graph_pass": node_graph_pass,
            "node_lock_graph": node_graph,
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
    parser.add_argument("--native-hip-ffi-source", type=Path, default=DEFAULT_NATIVE_HIP_FFI_SOURCE)
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--package-lock", type=Path, default=DEFAULT_PACKAGE_LOCK)
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
        native_hip_ffi_source=args.native_hip_ffi_source,
        pyproject=args.pyproject,
        package_json=args.package_json,
        package_lock=args.package_lock,
        rollback_runbook=args.rollback_runbook,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
