#!/usr/bin/env python3
"""Build production runtime packaging evidence for the independent product gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
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
REPOSITORY_LICENSE_PATH = "LICENSE"
REPOSITORY_LICENSE_REF = "LicenseRef-Repository-Default-No-License"
NPM_LICENSE_REF = "SEE LICENSE IN LICENSE"
NO_GRANT_LICENSE_FRAGMENTS = (
    "All rights reserved.",
    "No permission is granted",
    "except under a separate written agreement",
    "It is not evidence of product-license approval",
)


def _no_release_authority() -> dict[str, Any]:
    return {
        "product_license_approval": False,
        "commercial_use_authority": False,
        "redistribution_authority": False,
        "third_party_redistribution_clearance": "not_established",
        "release_authority": False,
    }


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


def _toml_bool(text: str, key: str) -> bool | None:
    match = re.search(
        rf"^\s*{re.escape(key)}\s*=\s*(true|false)\s*$",
        text,
        re.MULTILINE,
    )
    if match is None:
        return None
    return match.group(1) == "true"


def _parse_pyproject(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    return {
        "name": _toml_string(text, "name"),
        "version": _toml_string(text, "version"),
        "requires_python": _toml_string(text, "requires-python"),
        "license": _toml_string(text, "license"),
        "license_files": _toml_list(text, "license-files"),
        "dependencies": _toml_list(text, "dependencies"),
    }


def _parse_cargo_toml(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    return {
        "name": _toml_string(text, "name"),
        "version": _toml_string(text, "version"),
        "edition": _toml_string(text, "edition"),
        "license_file": _toml_string(text, "license-file"),
        "publish": _toml_bool(text, "publish"),
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
                    "license": str(row.get("license", "")),
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
        and manifest.get("private") is True
        and manifest.get("license") == NPM_LICENSE_REF
        and lock.get("license") == NPM_LICENSE_REF
        and root.get("license") == NPM_LICENSE_REF
        and root.get("engines") == manifest.get("engines")
        and all(root.get(field, {}) == manifest.get(field, {}) for field in direct_fields)
        and graph["package_count"] == len(packages) - 1
        and graph["ajv_version"] == "8.20.0"
        and graph["postcss_version"] == "8.5.26"
        and all(
            row["name"]
            and row["version"]
            and row["integrity"].startswith("sha512-")
            and row["license"]
            for row in graph_rows
        )
    )
    project = {
        "ecosystem": "node",
        "name": str(manifest.get("name", "")),
        "version": str(manifest.get("version", "")),
        "kind": "project",
        "requires": manifest.get("engines", {}),
        "package_manager": manifest.get("packageManager", ""),
        "lockfile_version": lock.get("lockfileVersion"),
        "private": manifest.get("private") is True,
        "license_ref": str(manifest.get("license", "")),
        "license_file": REPOSITORY_LICENSE_PATH,
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
                "license_ref": python_project.get("license", ""),
                "license_files": python_project.get("license_files", []),
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
                "license_file": cargo_project.get("license_file", ""),
                "publish": cargo_project.get("publish"),
            }
        )
    for package in cargo_packages:
        rows.append({"ecosystem": "rust", **package, "kind": "cargo-lock-package"})
    return rows


def _first_party_license_policy(
    *,
    pyproject: Path,
    package_json: Path,
    package_lock: Path,
    cargo_toml: Path,
) -> dict[str, Any]:
    python_project = _parse_pyproject(pyproject)
    node_manifest = _load_json(package_json)
    node_lock = _load_json(package_lock)
    node_packages = node_lock.get("packages")
    node_root = node_packages.get("") if isinstance(node_packages, dict) else None
    cargo_project = _parse_cargo_toml(cargo_toml)
    repository_license = pyproject.parent / REPOSITORY_LICENSE_PATH
    cargo_license_value = str(cargo_project.get("license_file", ""))
    cargo_license = (
        (cargo_toml.parent / cargo_license_value).resolve()
        if cargo_license_value
        else None
    )
    blockers: list[str] = []
    notice = ""
    if (
        repository_license.is_symlink()
        or not repository_license.is_file()
    ):
        blockers.append("repository_license_missing_or_unsafe")
    else:
        try:
            notice = " ".join(
                repository_license.read_text(encoding="utf-8").split()
            )
        except (OSError, UnicodeDecodeError):
            blockers.append("repository_license_unreadable")
        else:
            if not all(
                fragment in notice for fragment in NO_GRANT_LICENSE_FRAGMENTS
            ):
                blockers.append("repository_license_no_grant_boundary_missing")
    if (
        python_project.get("license") != REPOSITORY_LICENSE_REF
        or python_project.get("license_files") != [REPOSITORY_LICENSE_PATH]
    ):
        blockers.append("python_license_metadata_not_repository_authority")
    if (
        node_manifest.get("private") is not True
        or node_manifest.get("license") != NPM_LICENSE_REF
        or node_lock.get("license") != NPM_LICENSE_REF
        or not isinstance(node_root, dict)
        or node_root.get("license") != NPM_LICENSE_REF
    ):
        blockers.append("node_license_metadata_not_repository_authority")
    if (
        cargo_project.get("publish") is not False
        or cargo_license is None
        or cargo_license != repository_license.resolve()
    ):
        blockers.append("rust_license_metadata_not_repository_authority")
    blockers = sorted(set(blockers))
    return {
        "contract_pass": not blockers,
        "repository_posture": "all_rights_reserved_no_license_granted",
        "repository_license": {
            "path": REPOSITORY_LICENSE_PATH,
            "sha256": (
                _sha256_path(repository_license)
                if repository_license.is_file()
                and not repository_license.is_symlink()
                else ""
            ),
        },
        "python": {
            "license_ref": python_project.get("license", ""),
            "license_files": python_project.get("license_files", []),
        },
        "node": {
            "private": node_manifest.get("private") is True,
            "license_ref": str(node_manifest.get("license", "")),
            "license_file": REPOSITORY_LICENSE_PATH,
        },
        "rust": {
            "license_file": cargo_license_value,
            "publish": cargo_project.get("publish"),
        },
        "product_license_approval": False,
        "commercial_redistribution_approved": False,
        "third_party_redistribution_clearance": "not_established",
        "blockers": blockers,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalized_generated_payload(
    payload: dict[str, Any], *, path_substitutions: dict[str, str]
) -> dict[str, Any]:
    """Normalize generated timestamps and caller-specific absolute output paths."""

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: normalize(row)
                for key, row in value.items()
                if key != "generated_at"
            }
        if isinstance(value, list):
            return [normalize(row) for row in value]
        if isinstance(value, str):
            return path_substitutions.get(value, value)
        return value

    normalized = normalize(payload)
    if not isinstance(normalized, dict):  # pragma: no cover - input is typed
        raise ValueError("generated payload must remain an object")
    return normalized


def validate_runtime_packaging_artifacts(repo_root: Path) -> list[str]:
    """Rebuild the canonical runtime leaves and reject stale tracked evidence.

    Timestamps are observation metadata and are intentionally ignored. Every
    semantic field, source path, lock-graph row, and parent-to-child byte hash
    remains exact. This validator grants no license, signing, or release
    authority.
    """

    repo_root = repo_root.resolve()
    canonical_outputs = {
        "manifest": DEFAULT_MANIFEST_OUT,
        "sbom": DEFAULT_SBOM_OUT,
        "native": DEFAULT_NATIVE_ARTIFACT_MANIFEST_OUT,
        "compatibility": DEFAULT_COMPATIBILITY_MATRIX_OUT,
    }
    violations: list[str] = []
    actual_payloads: dict[str, dict[str, Any]] = {}
    for label, relative in canonical_outputs.items():
        path = repo_root / relative
        if not os.path.lexists(path) or not path.is_file() or path.is_symlink():
            violations.append(f"runtime_artifact_missing_or_unsafe:{relative.as_posix()}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            violations.append(f"runtime_artifact_json_invalid:{relative.as_posix()}")
            continue
        if not isinstance(payload, dict):
            violations.append(f"runtime_artifact_json_invalid:{relative.as_posix()}")
            continue
        actual_payloads[label] = payload
    if violations:
        return violations

    source_paths = {
        DEFAULT_RUNTIME_PROBE: repo_root / DEFAULT_RUNTIME_PROBE,
        DEFAULT_RUNTIME_WRAPPER: repo_root / DEFAULT_RUNTIME_WRAPPER,
        DEFAULT_CRATE_DIR: repo_root / DEFAULT_CRATE_DIR,
        DEFAULT_NATIVE_HIP_FFI_SOURCE: repo_root / DEFAULT_NATIVE_HIP_FFI_SOURCE,
        DEFAULT_PYPROJECT: repo_root / DEFAULT_PYPROJECT,
        DEFAULT_PACKAGE_JSON: repo_root / DEFAULT_PACKAGE_JSON,
        DEFAULT_PACKAGE_LOCK: repo_root / DEFAULT_PACKAGE_LOCK,
        DEFAULT_ROLLBACK_RUNBOOK: repo_root / DEFAULT_ROLLBACK_RUNBOOK,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="runtime-packaging-rebuild-") as raw_tmp:
            temp_root = Path(raw_tmp)
            temporary_outputs = {
                label: temp_root / relative.name
                for label, relative in canonical_outputs.items()
            }
            build_runtime_packaging_manifest(
                manifest_out=temporary_outputs["manifest"],
                sbom_out=temporary_outputs["sbom"],
                native_artifact_manifest_out=temporary_outputs["native"],
                compatibility_matrix_out=temporary_outputs["compatibility"],
                runtime_probe=source_paths[DEFAULT_RUNTIME_PROBE],
                runtime_wrapper=source_paths[DEFAULT_RUNTIME_WRAPPER],
                crate_dir=source_paths[DEFAULT_CRATE_DIR],
                native_hip_ffi_source=source_paths[DEFAULT_NATIVE_HIP_FFI_SOURCE],
                pyproject=source_paths[DEFAULT_PYPROJECT],
                package_json=source_paths[DEFAULT_PACKAGE_JSON],
                package_lock=source_paths[DEFAULT_PACKAGE_LOCK],
                rollback_runbook=source_paths[DEFAULT_ROLLBACK_RUNBOOK],
            )
            expected_payloads = {
                label: _load_json(path)
                for label, path in temporary_outputs.items()
            }
            substitutions = {
                str(absolute): relative.as_posix()
                for relative, absolute in source_paths.items()
            }
            for suffix in (
                Path("Cargo.toml"),
                Path("Cargo.lock"),
                Path("src/lib.rs"),
                Path("target/release/libmgt_hip_full_residual_rust_ffi.so"),
            ):
                substitutions[str(source_paths[DEFAULT_CRATE_DIR] / suffix)] = (
                    DEFAULT_CRATE_DIR / suffix
                ).as_posix()
            substitutions.update(
                {
                    str(temporary_outputs[label]): relative.as_posix()
                    for label, relative in canonical_outputs.items()
                }
            )

            for label in ("sbom", "native", "compatibility"):
                actual = _normalized_generated_payload(
                    actual_payloads[label], path_substitutions={}
                )
                expected = _normalized_generated_payload(
                    expected_payloads[label], path_substitutions=substitutions
                )
                if actual != expected:
                    violations.append(
                        "runtime_artifact_exact_rebuild_mismatch:"
                        + canonical_outputs[label].as_posix()
                    )

            expected_manifest = expected_payloads["manifest"]
            artifacts = expected_manifest.get("artifacts")
            if isinstance(artifacts, dict):
                for artifact_key, output_label in (
                    ("sbom", "sbom"),
                    ("native_artifact_manifest", "native"),
                    ("version_compatibility_matrix", "compatibility"),
                ):
                    row = artifacts.get(artifact_key)
                    if isinstance(row, dict):
                        row["sha256"] = _sha256_path(
                            repo_root / canonical_outputs[output_label]
                        )
            actual_manifest = _normalized_generated_payload(
                actual_payloads["manifest"], path_substitutions={}
            )
            normalized_expected_manifest = _normalized_generated_payload(
                expected_manifest, path_substitutions=substitutions
            )
            if actual_manifest != normalized_expected_manifest:
                violations.append(
                    "runtime_artifact_exact_rebuild_mismatch:"
                    + canonical_outputs["manifest"].as_posix()
                )
    except (OSError, ValueError, json.JSONDecodeError):
        return ["runtime_artifact_rebuild_error"]
    return violations


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
    first_party_license = _first_party_license_policy(
        pyproject=pyproject,
        package_json=package_json,
        package_lock=package_lock,
        cargo_toml=cargo_toml,
    )
    payload = {
        "schema_version": SBOM_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "component_count": len(rows),
        "components": rows,
        "first_party_license": first_party_license,
        "authority": _no_release_authority(),
        "source_files": {
            "pyproject": str(pyproject),
            "package_json": str(package_json),
            "package_lock": str(package_lock),
            "cargo_toml": str(cargo_toml),
            "cargo_lock": str(cargo_lock),
        },
        "source_hashes": {
            "repository_license": _sha256_path(
                pyproject.parent / REPOSITORY_LICENSE_PATH
            ),
            "pyproject": _sha256_path(pyproject),
            "package_json": _sha256_path(package_json),
            "package_lock": _sha256_path(package_lock),
            "cargo_toml": _sha256_path(cargo_toml),
            "cargo_lock": _sha256_path(cargo_lock),
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
        "authority": _no_release_authority(),
        "claim_boundary": (
            "This is a technical native-artifact inventory only. It grants no product "
            "license, commercial use, redistribution, third-party-material clearance, "
            "or release authority."
        ),
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
        "authority": _no_release_authority(),
        "claim_boundary": (
            "This matrix records declared or technically verified runtime compatibility "
            "only. It grants no product license, commercial use, redistribution, "
            "third-party-material clearance, or release authority."
        ),
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
    first_party_license = _first_party_license_policy(
        pyproject=pyproject,
        package_json=package_json,
        package_lock=package_lock,
        cargo_toml=cargo_toml,
    )
    blockers = [
        *(["runtime_version_missing"] if not runtime_version else []),
        *(["strict_runtime_probe_missing"] if not runtime_probe.exists() else []),
        *(["strict_runtime_probe_not_green"] if not runtime_probe_pass else []),
        *(["node_lock_graph_not_green"] if not node_graph_pass else []),
        *(
            ["first_party_license_metadata_not_green"]
            if not first_party_license["contract_pass"]
            else []
        ),
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
        "authority": _no_release_authority(),
        "claim_boundary": (
            "contract_pass covers the technical runtime packaging contract only. It "
            "grants no product license, commercial use, redistribution, third-party-"
            "material clearance, signing authority, or release authority."
        ),
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
            "first_party_license_metadata_pass": first_party_license[
                "contract_pass"
            ],
            "first_party_license_metadata_blockers": first_party_license["blockers"],
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
