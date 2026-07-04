#!/usr/bin/env python3
"""Build a Vina/GNINA execution plan from materialized public benchmark rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    REQUIRED_CASE_FIELDS,
    REQUIRED_ENGINE_RUN_FIELDS,
    SUPPORTED_ENGINES,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SUBSET_ROWS = PRODUCTIZATION / "public_benchmark_subset_rows.json"
DEFAULT_POSE_ROWS = PRODUCTIZATION / "public_benchmark_pose_rows.json"
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_vina_gnina_execution_plan.json"
DEFAULT_VINA_GNINA_ROWS_OUT = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
DEFAULT_INPUT_MANIFEST = PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest.json"
DEFAULT_ENGINE_RUN_BUNDLE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_bundle.json"
)
DEFAULT_ENGINE_RUN_COMMANDS = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_engine_run_commands.sh"
)
DEFAULT_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT = (
    PRODUCTIZATION
    / "public_benchmark_vina_gnina_rows_from_engine_run_bundle_report.json"
)
SCHEMA_VERSION = "public-benchmark-vina-gnina-execution-plan.v1"
DEFAULT_BOX_MARGIN_ANGSTROM = 8.0
DEFAULT_MIN_BOX_SIZE_ANGSTROM = 15.0
DOCKER_BIN_ENV = "PUBLIC_BENCHMARK_DOCKER_BIN"
LOCAL_SOURCE_FILE_FIELDS = ("protein_structure_path", "reference_ligand_path")
INPUT_MANIFEST_FORMATS = ("json", "jsonl", "ndjson", "csv", "tsv")
INPUT_MANIFEST_CASE_FIELDS = (
    "complex_id",
    "benchmark_split",
    "source_family",
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
    "protein_structure_path",
    "protein_structure_checksum",
    "reference_ligand_path",
    "reference_ligand_checksum",
    "prepared_receptor_path",
    "prepared_receptor_checksum",
    "prepared_ligand_path",
    "prepared_ligand_checksum",
    "docking_box_center_x",
    "docking_box_center_y",
    "docking_box_center_z",
    "docking_box_size_x",
    "docking_box_size_y",
    "docking_box_size_z",
    "vina_config_ref",
    "gnina_config_ref",
    "vina_run_receipt_ref",
    "gnina_run_receipt_ref",
    "input_preparation_provenance_ref",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("rows", "case_rows", "cases"):
        values = payload.get(key)
        if isinstance(values, list):
            return [row for row in values if isinstance(row, dict)]
    return []


def _case_rows_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("case_id") or ""): row
        for row in rows
        if str(row.get("case_id") or "")
    }


def _input_manifest_candidate_paths(input_manifest_path: Path) -> list[Path]:
    default_candidates = [
        PRODUCTIZATION / f"public_benchmark_vina_gnina_input_manifest.{suffix}"
        for suffix in INPUT_MANIFEST_FORMATS
    ]
    candidates = list(default_candidates)
    if input_manifest_path not in candidates:
        candidates.insert(0, input_manifest_path)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _normalized_manifest_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        str(key).strip(): str(value).strip() if value is not None else ""
        for key, value in row.items()
    }


def _rows_from_manifest_json(payload: Any) -> list[dict[str, str]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = []
        for key in ("rows", "case_rows", "cases", "input_manifest_rows"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        if not rows and payload.get("case_id"):
            rows = [payload]
    else:
        rows = []
    return [_normalized_manifest_row(row) for row in rows if isinstance(row, dict)]


def _load_manifest_rows_from_path(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _rows_from_manifest_json(json.loads(path.read_text(encoding="utf-8")))
    if suffix in {".jsonl", ".ndjson"}:
        rows: list[dict[str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if isinstance(value, dict):
                rows.append(_normalized_manifest_row(value))
        return rows
    delimiter = "\t" if suffix == ".tsv" else ","
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            _normalized_manifest_row(row)
            for row in csv.DictReader(handle, delimiter=delimiter)
            if isinstance(row, dict)
        ]


def _input_manifest_status(
    repo_root: Path,
    input_manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    candidate_rows: list[dict[str, Any]] = []
    selected_path = ""
    selected_format = ""
    selected_rows: list[dict[str, str]] = []
    detected_artifact_count = 0
    invalid_artifact_count = 0
    empty_artifact_count = 0
    for path in _input_manifest_candidate_paths(input_manifest_path):
        resolved = path if path.is_absolute() else repo_root / path
        row_status: dict[str, Any] = {
            "path": str(path),
            "format": path.suffix.lower().lstrip("."),
            "exists": resolved.exists(),
            "is_file": resolved.is_file(),
            "row_count": 0,
            "load_error": "",
        }
        if resolved.is_file():
            detected_artifact_count += 1
            try:
                rows = _load_manifest_rows_from_path(resolved)
            except Exception as exc:
                rows = []
                invalid_artifact_count += 1
                row_status["load_error"] = exc.__class__.__name__
            row_status["row_count"] = len(rows)
            if not rows and not row_status["load_error"]:
                empty_artifact_count += 1
            if rows and not selected_rows:
                selected_rows = rows
                selected_path = str(path)
                selected_format = str(row_status["format"])
        candidate_rows.append(row_status)

    case_ids = [str(row.get("case_id") or "") for row in selected_rows]
    duplicate_case_ids = sorted(
        {
            case_id
            for case_id in case_ids
            if case_id and case_ids.count(case_id) > 1
        }
    )
    blockers: list[str] = []
    if detected_artifact_count == 0:
        blockers.append("public_benchmark_vina_gnina_input_manifest_not_detected")
    elif not selected_rows:
        if invalid_artifact_count:
            blockers.append("public_benchmark_vina_gnina_input_manifest_invalid")
        if empty_artifact_count:
            blockers.append("public_benchmark_vina_gnina_input_manifest_rows_missing")
    if duplicate_case_ids:
        blockers.append("public_benchmark_vina_gnina_input_manifest_duplicate_case_ids")
    rows_by_case_id = {
        str(row.get("case_id") or ""): row
        for row in selected_rows
        if str(row.get("case_id") or "")
    }
    if selected_rows and len(rows_by_case_id) < len(selected_rows):
        blockers.append("public_benchmark_vina_gnina_input_manifest_case_id_missing")
    if selected_rows and not blockers:
        status = "ready"
    elif detected_artifact_count == 0:
        status = "not_detected"
    else:
        status = "blocked"
    return (
        {
            "status": status,
            "default_manifest_path": str(input_manifest_path),
            "accepted_formats": list(INPUT_MANIFEST_FORMATS),
            "candidate_paths": candidate_rows,
            "detected_manifest_artifact_count": detected_artifact_count,
            "selected_manifest_path": selected_path,
            "selected_manifest_format": selected_format,
            "row_count": len(selected_rows),
            "case_count": len(rows_by_case_id),
            "duplicate_case_ids": duplicate_case_ids,
            "blockers": blockers,
        },
        rows_by_case_id,
    )


def _merge_input_manifest_row(
    subset_row: dict[str, Any],
    manifest_row: dict[str, str] | None,
) -> dict[str, Any]:
    merged = dict(subset_row)
    if not manifest_row:
        return merged
    for field in INPUT_MANIFEST_CASE_FIELDS:
        value = str(manifest_row.get(field) or "").strip()
        if value:
            merged[field] = value
    return merged


def _source_file_checksum(
    case_row: dict[str, Any],
    *,
    path_field: str,
    checksum_field: str,
) -> str:
    explicit_checksum = str(case_row.get(checksum_field) or "").strip()
    if explicit_checksum:
        return explicit_checksum
    source_file_checksums = case_row.get("source_file_checksums")
    if not isinstance(source_file_checksums, dict):
        return ""
    path_value = str(case_row.get(path_field) or "").strip()
    if not path_value:
        return ""
    return str(source_file_checksums.get(path_value) or "").strip()


def _coordinates(atoms: Any) -> list[tuple[float, float, float]]:
    coords: list[tuple[float, float, float]] = []
    if not isinstance(atoms, list):
        return coords
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        try:
            coords.append((float(atom["x"]), float(atom["y"]), float(atom["z"])))
        except (KeyError, TypeError, ValueError):
            continue
    return coords


def _docking_box(
    reference_atoms: Any,
    *,
    margin_angstrom: float = DEFAULT_BOX_MARGIN_ANGSTROM,
    minimum_size_angstrom: float = DEFAULT_MIN_BOX_SIZE_ANGSTROM,
) -> dict[str, Any]:
    coords = _coordinates(reference_atoms)
    if not coords:
        return {
            "status": "blocked",
            "blockers": ["reference_atoms_missing_for_docking_box"],
        }
    xs = [row[0] for row in coords]
    ys = [row[1] for row in coords]
    zs = [row[2] for row in coords]
    spans = {
        "x": max(xs) - min(xs),
        "y": max(ys) - min(ys),
        "z": max(zs) - min(zs),
    }
    sizes = {
        axis: max(round(span + 2.0 * margin_angstrom, 6), minimum_size_angstrom)
        for axis, span in spans.items()
    }
    return {
        "status": "ready",
        "center": {
            "x": round((max(xs) + min(xs)) / 2.0, 6),
            "y": round((max(ys) + min(ys)) / 2.0, 6),
            "z": round((max(zs) + min(zs)) / 2.0, 6),
        },
        "size": sizes,
        "margin_angstrom": margin_angstrom,
        "minimum_size_angstrom": minimum_size_angstrom,
        "basis": "axis-aligned box around materialized reference ligand atoms",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _checksum_blocker(
    expected_checksum: str,
    actual_checksum: str,
    *,
    blocker_prefix: str,
    require_checksum: bool,
) -> str:
    if not expected_checksum:
        return f"{blocker_prefix}_checksum_missing" if require_checksum else ""
    if not expected_checksum.lower().startswith("sha256:"):
        return f"{blocker_prefix}_checksum_invalid"
    if expected_checksum.lower() != actual_checksum.lower():
        return f"{blocker_prefix}_checksum_mismatch"
    return ""


def _file_status(
    repo_root: Path,
    path_value: Any,
    *,
    blocker_prefix: str,
    expected_checksum: Any = "",
    require_checksum: bool = False,
) -> dict[str, Any]:
    path_text = str(path_value or "").strip()
    expected_checksum_text = str(expected_checksum or "").strip()
    if not path_text:
        return {
            "path": "",
            "exists": False,
            "is_file": False,
            "expected_checksum": expected_checksum_text,
            "actual_checksum": "",
            "checksum_verified": False,
            "status": "blocked",
            "blocker": f"{blocker_prefix}_missing",
        }
    path = Path(path_text)
    resolved = path if path.is_absolute() else repo_root / path
    exists = resolved.exists()
    is_file = resolved.is_file()
    blocker = ""
    if not exists:
        blocker = f"{blocker_prefix}_missing"
    elif not is_file:
        blocker = f"{blocker_prefix}_not_file"
    actual_checksum = ""
    checksum_verified = False
    if is_file:
        try:
            actual_checksum = _sha256_file(resolved)
        except OSError:
            blocker = f"{blocker_prefix}_checksum_read_error"
        else:
            checksum_blocker = _checksum_blocker(
                expected_checksum_text,
                actual_checksum,
                blocker_prefix=blocker_prefix,
                require_checksum=require_checksum,
            )
            if checksum_blocker:
                blocker = checksum_blocker
            checksum_verified = bool(expected_checksum_text) and not checksum_blocker
    return {
        "path": path_text,
        "exists": exists,
        "is_file": is_file,
        "expected_checksum": expected_checksum_text,
        "actual_checksum": actual_checksum,
        "checksum_verified": checksum_verified,
        "status": "ready" if is_file and not blocker else "blocked",
        "blocker": blocker,
    }


def _source_file_status(repo_root: Path, subset_row: dict[str, Any]) -> dict[str, Any]:
    checksum_fields = {
        "protein_structure_path": "protein_structure_checksum",
        "reference_ligand_path": "reference_ligand_checksum",
    }
    fields = {}
    for field in LOCAL_SOURCE_FILE_FIELDS:
        checksum_field = checksum_fields[field]
        fields[field] = _file_status(
            repo_root=repo_root,
            path_value=subset_row.get(field),
            blocker_prefix=field,
            expected_checksum=_source_file_checksum(
                subset_row,
                path_field=field,
                checksum_field=checksum_field,
            ),
            require_checksum=True,
        )
    blockers = [
        str(row["blocker"])
        for row in fields.values()
        if str(row.get("blocker") or "")
    ]
    return {
        "status": "ready" if not blockers else "blocked",
        "required_fields": list(LOCAL_SOURCE_FILE_FIELDS),
        "files": fields,
        "blockers": blockers,
    }


def _prepared_input_status(
    repo_root: Path,
    complex_id: str,
    case_row: dict[str, Any],
) -> dict[str, Any]:
    expected_paths = {
        "receptor": str(
            case_row.get("prepared_receptor_path") or f"prepared/{complex_id}_receptor"
        ),
        "ligand": str(
            case_row.get("prepared_ligand_path") or f"prepared/{complex_id}_ligand"
        ),
    }
    files = {
        role: _file_status(
            repo_root,
            path,
            blocker_prefix=f"prepared_{role}_path",
            expected_checksum=case_row.get(f"prepared_{role}_checksum"),
            require_checksum=True,
        )
        for role, path in expected_paths.items()
    }
    blockers = [
        str(row["blocker"])
        for row in files.values()
        if str(row.get("blocker") or "")
    ]
    return {
        "status": "ready" if not blockers else "blocked",
        "preparation_required": bool(blockers),
        "expected_paths": expected_paths,
        "files": files,
        "blockers": blockers,
    }


def _engine_binary_status(engine_id: str) -> dict[str, Any]:
    env_var = f"PUBLIC_BENCHMARK_{engine_id.upper()}_BIN"
    env_executable = os.environ.get(env_var, "").strip()
    executable = env_executable or shutil.which(engine_id)
    if not executable:
        return {
            "engine_id": engine_id,
            "available": False,
            "executable": "",
            "binary_source": "",
            "env_var": env_var,
            "version": "",
            "blocker": f"{engine_id}_binary_missing",
        }
    executable_path = Path(executable)
    if env_executable and not executable_path.is_file():
        return {
            "engine_id": engine_id,
            "available": False,
            "executable": executable,
            "binary_source": f"env:{env_var}",
            "env_var": env_var,
            "version": "",
            "blocker": f"{engine_id}_binary_not_found",
        }
    if env_executable and not os.access(executable_path, os.X_OK):
        return {
            "engine_id": engine_id,
            "available": False,
            "executable": executable,
            "binary_source": f"env:{env_var}",
            "env_var": env_var,
            "version": "",
            "blocker": f"{engine_id}_binary_not_executable",
        }
    try:
        version_output = subprocess.check_output(
            [executable, "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        ).strip()
    except Exception:
        version_output = ""
    return {
        "engine_id": engine_id,
        "available": True,
        "executable": executable,
        "binary_source": f"env:{env_var}" if env_executable else "PATH",
        "env_var": env_var,
        "version": version_output.splitlines()[0] if version_output else "",
        "blocker": "",
    }


def _docker_cli_status() -> dict[str, Any]:
    env_executable = os.environ.get(DOCKER_BIN_ENV, "").strip()
    executable = env_executable or shutil.which("docker")
    if not executable:
        return {
            "available": False,
            "executable": "",
            "binary_source": "",
            "env_var": DOCKER_BIN_ENV,
            "blocker": "docker_binary_missing",
        }
    executable_path = Path(executable)
    if env_executable and not executable_path.is_file():
        return {
            "available": False,
            "executable": executable,
            "binary_source": f"env:{DOCKER_BIN_ENV}",
            "env_var": DOCKER_BIN_ENV,
            "blocker": "docker_binary_not_found",
        }
    if env_executable and not os.access(executable_path, os.X_OK):
        return {
            "available": False,
            "executable": executable,
            "binary_source": f"env:{DOCKER_BIN_ENV}",
            "env_var": DOCKER_BIN_ENV,
            "blocker": "docker_binary_not_executable",
        }
    return {
        "available": True,
        "executable": executable,
        "binary_source": f"env:{DOCKER_BIN_ENV}" if env_executable else "PATH",
        "env_var": DOCKER_BIN_ENV,
        "blocker": "",
    }


def _docker_daemon_version(executable: str) -> tuple[bool, str]:
    try:
        output = subprocess.check_output(
            [executable, "version", "--format", "{{.Server.Version}}"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        ).strip()
    except Exception:
        return False, ""
    return bool(output), output.splitlines()[0] if output else ""


def _container_image_present(executable: str, image: str) -> bool:
    try:
        subprocess.check_output(
            [executable, "image", "inspect", image, "--format", "{{.Id}}"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
    except Exception:
        return False
    return True


def _engine_container_status(
    engine_id: str,
    *,
    docker_cli_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    image_env_var = f"PUBLIC_BENCHMARK_{engine_id.upper()}_CONTAINER_IMAGE"
    image = os.environ.get(image_env_var, "").strip()
    docker_status = docker_cli_status or _docker_cli_status()
    docker_daemon_available = False
    docker_version = ""
    if docker_status.get("available"):
        executable = str(docker_status.get("executable") or "docker")
        docker_daemon_available, docker_version = _docker_daemon_version(executable)
    base = {
        "engine_id": engine_id,
        "available": False,
        "image": image,
        "image_env_var": image_env_var,
        "docker_executable": str(docker_status.get("executable") or ""),
        "docker_binary_available": bool(docker_status.get("available")),
        "docker_daemon_available": docker_daemon_available,
        "docker_server_version": docker_version,
        "image_present": False,
        "command_prefix": "",
        "blocker": "",
    }
    if not image:
        return {**base, "status": "container_image_not_configured"}
    if not docker_status.get("available"):
        return {
            **base,
            "status": "blocked",
            "blocker": str(docker_status.get("blocker") or "docker_binary_missing"),
        }
    executable = str(docker_status.get("executable") or "docker")
    if not docker_daemon_available:
        return {
            **base,
            "status": "blocked",
            "docker_daemon_available": False,
            "blocker": "docker_daemon_unavailable",
        }
    image_present = _container_image_present(executable, image)
    if not image_present:
        return {
            **base,
            "status": "blocked",
            "docker_daemon_available": True,
            "blocker": f"{engine_id}_container_image_not_present",
        }
    command_prefix = f"{executable} run --rm -v $PWD:/work -w /work {image} {engine_id}"
    return {
        **base,
        "status": "ready",
        "available": True,
        "docker_daemon_available": True,
        "docker_server_version": docker_version,
        "image_present": True,
        "command_prefix": command_prefix,
    }


def _engine_execution_status(
    engine_id: str,
    binary_status: dict[str, Any],
    container_status: dict[str, Any],
) -> dict[str, Any]:
    if binary_status.get("available"):
        return {
            "engine_id": engine_id,
            "available": True,
            "execution_source": "binary",
            "executable": str(binary_status.get("executable") or ""),
            "command_prefix": str(binary_status.get("executable") or engine_id),
            "version": str(binary_status.get("version") or ""),
            "blocker": "",
        }
    if container_status.get("available"):
        return {
            "engine_id": engine_id,
            "available": True,
            "execution_source": "container",
            "executable": str(container_status.get("docker_executable") or ""),
            "command_prefix": str(container_status.get("command_prefix") or ""),
            "version": str(container_status.get("docker_server_version") or ""),
            "container_image": str(container_status.get("image") or ""),
            "blocker": "",
        }
    return {
        "engine_id": engine_id,
        "available": False,
        "execution_source": "",
        "executable": "",
        "command_prefix": "",
        "version": "",
        "container_image": str(container_status.get("image") or ""),
        "blocker": str(binary_status.get("blocker") or f"{engine_id}_runtime_missing"),
    }


def _run_spec(
    *,
    case_id: str,
    complex_id: str,
    engine_id: str,
    docking_box: dict[str, Any],
    case_row: dict[str, Any],
) -> dict[str, Any]:
    run_root = f"operator_attached/vina_gnina/{case_id}/{engine_id}"
    prepared_receptor_path = str(
        case_row.get("prepared_receptor_path") or f"prepared/{complex_id}_receptor"
    )
    prepared_ligand_path = str(
        case_row.get("prepared_ligand_path") or f"prepared/{complex_id}_ligand"
    )
    config_ref = str(
        case_row.get(f"{engine_id}_config_ref") or f"{run_root}_config.json"
    )
    run_receipt_ref = str(
        case_row.get(f"{engine_id}_run_receipt_ref") or f"{run_root}_run_receipt.json"
    )
    return {
        "engine_id": engine_id,
        "docking_run_id": f"{case_id}_{engine_id}_run",
        "docking_box": docking_box,
        "prepared_receptor_path": prepared_receptor_path,
        "prepared_ligand_path": prepared_ligand_path,
        "expected_predicted_ligand_path_or_pose_ref": f"{run_root}_pose.sdf",
        "expected_engine_config_ref": config_ref,
        "expected_engine_run_provenance_ref": run_receipt_ref,
        "expected_adapter_engine_run_fields": list(REQUIRED_ENGINE_RUN_FIELDS),
        "command_template": (
            f"<{engine_id}> --receptor <{prepared_receptor_path}> "
            f"--ligand <{prepared_ligand_path}> "
            "--center_x {center[x]} --center_y {center[y]} --center_z {center[z]} "
            "--size_x {size[x]} --size_y {size[y]} --size_z {size[z]} "
            f"--out {run_root}_pose.sdf"
        ),
        "container_command_template": (
            f"docker run --rm -v $PWD:/work -w /work "
            f"<PUBLIC_BENCHMARK_{engine_id.upper()}_CONTAINER_IMAGE> "
            f"{engine_id} --receptor <{prepared_receptor_path}> "
            f"--ligand <{prepared_ligand_path}> "
            "--center_x {center[x]} --center_y {center[y]} --center_z {center[z]} "
            "--size_x {size[x]} --size_y {size[y]} --size_z {size[z]} "
            f"--out {run_root}_pose.sdf"
        ),
        "container_image_env_var": (
            f"PUBLIC_BENCHMARK_{engine_id.upper()}_CONTAINER_IMAGE"
        ),
        "receipt_required": True,
    }


def _case_plan(
    *,
    repo_root: Path,
    subset_row: dict[str, Any],
    pose_row: dict[str, Any] | None,
    manifest_row: dict[str, str] | None = None,
    manifest_selected: bool = False,
) -> dict[str, Any]:
    case_id = str(subset_row.get("case_id") or "")
    case_row = _merge_input_manifest_row(subset_row, manifest_row)
    complex_id = str(case_row.get("complex_id") or "")
    blockers: list[str] = []
    if pose_row is None:
        blockers.append("pose_row_missing_for_case")
    if manifest_selected and manifest_row is None:
        blockers.append("input_manifest_row_missing_for_case")
    docking_box = _docking_box((pose_row or {}).get("reference_atoms"))
    blockers.extend(str(row) for row in docking_box.get("blockers", []) if str(row))
    source_file_status = _source_file_status(repo_root, case_row)
    prepared_input_status = _prepared_input_status(repo_root, complex_id, case_row)
    blockers.extend(str(row) for row in source_file_status["blockers"])
    blockers.extend(str(row) for row in prepared_input_status["blockers"])
    engine_runs = [
        _run_spec(
            case_id=case_id,
            complex_id=complex_id,
            engine_id=engine_id,
            docking_box=docking_box,
            case_row=case_row,
        )
        for engine_id in SUPPORTED_ENGINES
    ]
    return {
        "case_id": case_id,
        "complex_id": complex_id,
        "benchmark_split": str(case_row.get("benchmark_split") or ""),
        "source_family": str(
            case_row.get("source_family") or "CASF/PDBBind + Vina/GNINA"
        ),
        "reference_pose_id": f"{case_id}_reference",
        "protein_structure_path": str(case_row.get("protein_structure_path") or ""),
        "protein_structure_checksum": _source_file_checksum(
            case_row,
            path_field="protein_structure_path",
            checksum_field="protein_structure_checksum",
        ),
        "reference_ligand_path": str(case_row.get("reference_ligand_path") or ""),
        "reference_ligand_checksum": _source_file_checksum(
            case_row,
            path_field="reference_ligand_path",
            checksum_field="reference_ligand_checksum",
        ),
        "prepared_receptor_path": str(case_row.get("prepared_receptor_path") or ""),
        "prepared_receptor_checksum": str(
            case_row.get("prepared_receptor_checksum") or ""
        ),
        "prepared_ligand_path": str(case_row.get("prepared_ligand_path") or ""),
        "prepared_ligand_checksum": str(
            case_row.get("prepared_ligand_checksum") or ""
        ),
        "input_preparation_provenance_ref": str(
            case_row.get("input_preparation_provenance_ref") or ""
        ),
        "input_manifest_case_status": {
            "manifest_selected": manifest_selected,
            "manifest_row_present": manifest_row is not None,
            "provided_fields": sorted(
                field
                for field in INPUT_MANIFEST_CASE_FIELDS
                if manifest_row is not None and str(manifest_row.get(field) or "")
            ),
            "blocker": (
                "input_manifest_row_missing_for_case"
                if manifest_selected and manifest_row is None
                else ""
            ),
        },
        "source_file_status": source_file_status,
        "prepared_input_status": prepared_input_status,
        "subset_source_checksum": str(case_row.get("source_checksum") or ""),
        "source_license_or_accession": str(
            case_row.get("source_license_or_accession") or ""
        ),
        "provenance_ref": str(case_row.get("provenance_ref") or ""),
        "docking_box": docking_box,
        "engine_runs": engine_runs,
        "required_adapter_case_fields": list(REQUIRED_CASE_FIELDS),
        "status": "ready_for_engine_execution" if not blockers else "blocked",
        "blockers": blockers,
    }


def build_vina_gnina_execution_plan(
    *,
    repo_root: Path = ROOT,
    subset_rows_path: Path = DEFAULT_SUBSET_ROWS,
    pose_rows_path: Path = DEFAULT_POSE_ROWS,
    input_manifest_path: Path = DEFAULT_INPUT_MANIFEST,
    vina_gnina_rows_out: Path = DEFAULT_VINA_GNINA_ROWS_OUT,
) -> dict[str, Any]:
    subset_payload = _load_json(repo_root, subset_rows_path)
    pose_payload = _load_json(repo_root, pose_rows_path)
    subset_rows = _rows(subset_payload)
    pose_by_id = _case_rows_by_id(_rows(pose_payload))
    input_manifest_status, manifest_by_case_id = _input_manifest_status(
        repo_root,
        input_manifest_path,
    )
    manifest_selected = bool(input_manifest_status["selected_manifest_path"])
    docker_cli_status = _docker_cli_status()
    engine_statuses = [_engine_binary_status(engine) for engine in SUPPORTED_ENGINES]
    engine_container_statuses = [
        _engine_container_status(engine, docker_cli_status=docker_cli_status)
        for engine in SUPPORTED_ENGINES
    ]
    container_status_by_id = {
        str(row.get("engine_id") or ""): row for row in engine_container_statuses
    }
    engine_execution_statuses = [
        _engine_execution_status(
            str(row.get("engine_id") or ""),
            row,
            container_status_by_id.get(str(row.get("engine_id") or ""), {}),
        )
        for row in engine_statuses
    ]
    execution_status_by_id = {
        str(row.get("engine_id") or ""): row for row in engine_execution_statuses
    }
    engine_blockers = [
        str(row.get("blocker"))
        for row in engine_statuses
        if str(row.get("blocker") or "")
        and not execution_status_by_id.get(str(row.get("engine_id") or ""), {}).get(
            "available"
        )
    ]
    engine_blockers.extend(
        str(row.get("blocker"))
        for row in engine_container_statuses
        if str(row.get("blocker") or "")
        and str(row.get("image") or "")
        and not execution_status_by_id.get(str(row.get("engine_id") or ""), {}).get(
            "available"
        )
    )
    case_plans = [
        _case_plan(
            repo_root=repo_root,
            subset_row=row,
            pose_row=pose_by_id.get(str(row.get("case_id") or "")),
            manifest_row=manifest_by_case_id.get(str(row.get("case_id") or "")),
            manifest_selected=manifest_selected,
        )
        for row in subset_rows
    ]
    case_blockers = [
        f"{row['case_id']}::{blocker}"
        for row in case_plans
        for blocker in row["blockers"]
    ]
    blockers: list[str] = []
    if not subset_rows:
        blockers.append("subset_rows_missing")
    if not pose_by_id:
        blockers.append("pose_rows_missing")
    blockers.extend(
        blocker
        for blocker in input_manifest_status["blockers"]
        if blocker != "public_benchmark_vina_gnina_input_manifest_not_detected"
    )
    blockers.extend(case_blockers)
    blockers.extend(engine_blockers)
    execution_plan_ready = bool(case_plans and not case_blockers)
    operator_execution_ready = execution_plan_ready and not engine_blockers
    if operator_execution_ready:
        status = "ready_for_engine_execution"
    elif not execution_plan_ready:
        status = "engine_input_blocked"
    else:
        status = "engine_execution_required"
    local_source_ready_case_count = sum(
        1
        for row in case_plans
        if row.get("source_file_status", {}).get("status") == "ready"
    )
    prepared_input_ready_case_count = sum(
        1
        for row in case_plans
        if row.get("prepared_input_status", {}).get("status") == "ready"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_vina_gnina_execution_plan.py"),
                subset_rows_path,
                pose_rows_path,
                input_manifest_path,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_execution_plan_from_materialized_rows",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": True,
        "execution_plan_ready": execution_plan_ready,
        "operator_execution_ready": operator_execution_ready,
        "adapter_rows_ready": False,
        "case_count": len(case_plans),
        "required_engine_run_count": len(case_plans) * len(SUPPORTED_ENGINES),
        "supported_engines": list(SUPPORTED_ENGINES),
        "input_manifest_status": input_manifest_status,
        "container_runtime_status": docker_cli_status,
        "engine_binary_statuses": engine_statuses,
        "engine_container_statuses": engine_container_statuses,
        "engine_execution_statuses": engine_execution_statuses,
        "missing_engine_ids": [
            row["engine_id"]
            for row in engine_execution_statuses
            if not row["available"]
        ],
        "local_source_ready_case_count": local_source_ready_case_count,
        "prepared_input_ready_case_count": prepared_input_ready_case_count,
        "case_execution_plans": case_plans,
        "expected_vina_gnina_rows_artifact": str(vina_gnina_rows_out),
        "engine_run_bundle_materialization_command": (
            "python3 scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py "
            f"--execution-plan {DEFAULT_OUT} --out {DEFAULT_ENGINE_RUN_BUNDLE} "
            f"--commands-out {DEFAULT_ENGINE_RUN_COMMANDS}"
        ),
        "rows_from_engine_run_bundle_materialization_command": (
            "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py "
            f"--engine-run-bundle {DEFAULT_ENGINE_RUN_BUNDLE} "
            f"--out-rows {vina_gnina_rows_out} "
            f"--out-report {DEFAULT_ROWS_FROM_ENGINE_RUN_BUNDLE_REPORT} "
            "--fail-blocked"
        ),
        "adapter_materialization_command": (
            "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
            f"--intake {vina_gnina_rows_out} "
            "--out-adapter "
            f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
            "--out-report "
            f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
            "--fail-blocked"
        ),
        "engine_receipts_required": [
            "engine_version",
            "engine_config_checksum",
            "engine_run_provenance_ref",
            "predicted_ligand_checksum",
            "symmetry_aware_rmsd_angstrom",
            "pose_success",
            "score",
            "score_direction",
        ],
        "blockers": blockers,
        "summary": {
            "case_count": len(case_plans),
            "required_engine_run_count": len(case_plans) * len(SUPPORTED_ENGINES),
            "available_engine_count": sum(
                1 for row in engine_execution_statuses if row["available"]
            ),
            "missing_engine_count": sum(
                1 for row in engine_execution_statuses if not row["available"]
            ),
            "case_blocker_count": len(case_blockers),
            "local_source_ready_case_count": local_source_ready_case_count,
            "prepared_input_ready_case_count": prepared_input_ready_case_count,
            "input_manifest_status": input_manifest_status["status"],
            "input_manifest_detected": (
                input_manifest_status["detected_manifest_artifact_count"] > 0
            ),
            "input_manifest_row_count": input_manifest_status["row_count"],
            "execution_plan_ready": execution_plan_ready,
            "operator_execution_ready": operator_execution_ready,
            "adapter_rows_ready": False,
        },
        "claim_boundary": (
            "This artifact is an execution plan derived from materialized CASF/PDBBind "
            "subset and pose rows plus local source/prepared input file checks. It "
            "does not run Vina or GNINA, does not create engine comparison rows, and "
            "does not close Public Benchmark Phase 2 until real engine outputs and "
            "receipts pass the comparison adapter."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--subset-rows", type=Path, default=DEFAULT_SUBSET_ROWS)
    parser.add_argument("--pose-rows", type=Path, default=DEFAULT_POSE_ROWS)
    parser.add_argument("--input-manifest", type=Path, default=DEFAULT_INPUT_MANIFEST)
    parser.add_argument("--vina-gnina-rows-out", type=Path, default=DEFAULT_VINA_GNINA_ROWS_OUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_vina_gnina_execution_plan(
        repo_root=args.repo_root,
        subset_rows_path=args.subset_rows,
        pose_rows_path=args.pose_rows,
        input_manifest_path=args.input_manifest,
        vina_gnina_rows_out=args.vina_gnina_rows_out,
    )
    resolved_out = args.out if args.out.is_absolute() else args.repo_root / args.out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-execution-plan: "
            f"{payload['status']} | cases={payload['case_count']} | "
            f"required_engine_runs={payload['required_engine_run_count']} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
