#!/usr/bin/env python3
"""Build a Vina/GNINA execution plan from materialized public benchmark rows."""

from __future__ import annotations

import argparse
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
SCHEMA_VERSION = "public-benchmark-vina-gnina-execution-plan.v1"
DEFAULT_BOX_MARGIN_ANGSTROM = 8.0
DEFAULT_MIN_BOX_SIZE_ANGSTROM = 15.0
DOCKER_BIN_ENV = "PUBLIC_BENCHMARK_DOCKER_BIN"


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
) -> dict[str, Any]:
    run_root = f"operator_attached/vina_gnina/{case_id}/{engine_id}"
    return {
        "engine_id": engine_id,
        "docking_run_id": f"{case_id}_{engine_id}_run",
        "docking_box": docking_box,
        "expected_predicted_ligand_path_or_pose_ref": f"{run_root}_pose.sdf",
        "expected_engine_config_ref": f"{run_root}_config.json",
        "expected_engine_run_provenance_ref": f"{run_root}_run_receipt.json",
        "expected_adapter_engine_run_fields": list(REQUIRED_ENGINE_RUN_FIELDS),
        "command_template": (
            f"<{engine_id}> --receptor <prepared/{complex_id}_receptor> "
            f"--ligand <prepared/{complex_id}_ligand> "
            "--center_x {center[x]} --center_y {center[y]} --center_z {center[z]} "
            "--size_x {size[x]} --size_y {size[y]} --size_z {size[z]} "
            f"--out {run_root}_pose.sdf"
        ),
        "container_command_template": (
            f"docker run --rm -v $PWD:/work -w /work "
            f"<PUBLIC_BENCHMARK_{engine_id.upper()}_CONTAINER_IMAGE> "
            f"{engine_id} --receptor <prepared/{complex_id}_receptor> "
            f"--ligand <prepared/{complex_id}_ligand> "
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
    subset_row: dict[str, Any],
    pose_row: dict[str, Any] | None,
) -> dict[str, Any]:
    case_id = str(subset_row.get("case_id") or "")
    complex_id = str(subset_row.get("complex_id") or "")
    blockers: list[str] = []
    if pose_row is None:
        blockers.append("pose_row_missing_for_case")
    docking_box = _docking_box((pose_row or {}).get("reference_atoms"))
    blockers.extend(str(row) for row in docking_box.get("blockers", []) if str(row))
    engine_runs = [
        _run_spec(
            case_id=case_id,
            complex_id=complex_id,
            engine_id=engine_id,
            docking_box=docking_box,
        )
        for engine_id in SUPPORTED_ENGINES
    ]
    return {
        "case_id": case_id,
        "complex_id": complex_id,
        "benchmark_split": str(subset_row.get("benchmark_split") or ""),
        "source_family": "CASF/PDBBind + Vina/GNINA",
        "reference_pose_id": f"{case_id}_reference",
        "protein_structure_path": str(subset_row.get("protein_structure_path") or ""),
        "reference_ligand_path": str(subset_row.get("reference_ligand_path") or ""),
        "subset_source_checksum": str(subset_row.get("source_checksum") or ""),
        "source_license_or_accession": str(
            subset_row.get("source_license_or_accession") or ""
        ),
        "provenance_ref": str(subset_row.get("provenance_ref") or ""),
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
    vina_gnina_rows_out: Path = DEFAULT_VINA_GNINA_ROWS_OUT,
) -> dict[str, Any]:
    subset_payload = _load_json(repo_root, subset_rows_path)
    pose_payload = _load_json(repo_root, pose_rows_path)
    subset_rows = _rows(subset_payload)
    pose_by_id = _case_rows_by_id(_rows(pose_payload))
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
        _case_plan(subset_row=row, pose_row=pose_by_id.get(str(row.get("case_id") or "")))
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
    blockers.extend(case_blockers)
    blockers.extend(engine_blockers)
    execution_plan_ready = bool(case_plans and not case_blockers)
    operator_execution_ready = execution_plan_ready and not engine_blockers
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_vina_gnina_execution_plan.py"),
                subset_rows_path,
                pose_rows_path,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_execution_plan_from_materialized_rows",
            repo_root=repo_root,
        ),
        "status": (
            "ready_for_engine_execution"
            if operator_execution_ready
            else "engine_execution_required"
        ),
        "contract_pass": True,
        "execution_plan_ready": execution_plan_ready,
        "operator_execution_ready": operator_execution_ready,
        "adapter_rows_ready": False,
        "case_count": len(case_plans),
        "required_engine_run_count": len(case_plans) * len(SUPPORTED_ENGINES),
        "supported_engines": list(SUPPORTED_ENGINES),
        "container_runtime_status": docker_cli_status,
        "engine_binary_statuses": engine_statuses,
        "engine_container_statuses": engine_container_statuses,
        "engine_execution_statuses": engine_execution_statuses,
        "missing_engine_ids": [
            row["engine_id"]
            for row in engine_execution_statuses
            if not row["available"]
        ],
        "case_execution_plans": case_plans,
        "expected_vina_gnina_rows_artifact": str(vina_gnina_rows_out),
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
            "execution_plan_ready": execution_plan_ready,
            "operator_execution_ready": operator_execution_ready,
            "adapter_rows_ready": False,
        },
        "claim_boundary": (
            "This artifact is an execution plan derived from materialized CASF/PDBBind "
            "subset and pose rows. It does not run Vina or GNINA, does not create "
            "engine comparison rows, and does not close Public Benchmark Phase 2 until "
            "real engine outputs and receipts pass the comparison adapter."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--subset-rows", type=Path, default=DEFAULT_SUBSET_ROWS)
    parser.add_argument("--pose-rows", type=Path, default=DEFAULT_POSE_ROWS)
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
