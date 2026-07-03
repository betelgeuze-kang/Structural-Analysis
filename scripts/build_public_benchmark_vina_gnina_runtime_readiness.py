#!/usr/bin/env python3
"""Build a runtime readiness receipt for Public Benchmark Vina/GNINA runs."""

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
DEFAULT_EXECUTION_PLAN = PRODUCTIZATION / "public_benchmark_vina_gnina_execution_plan.json"
DEFAULT_VINA_GNINA_ROWS = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_vina_gnina_runtime_readiness.json"
SCHEMA_VERSION = "public-benchmark-vina-gnina-runtime-readiness.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _row_candidate_status(repo_root: Path, rows_path: Path) -> dict[str, Any]:
    candidates = [
        PRODUCTIZATION / f"public_benchmark_vina_gnina_rows.{suffix}"
        for suffix in ("json", "jsonl", "ndjson", "csv")
    ]
    if rows_path not in candidates:
        candidates.insert(0, rows_path)
    rows = []
    for path in candidates:
        resolved = path if path.is_absolute() else repo_root / path
        rows.append(
            {
                "path": str(path),
                "exists": resolved.exists(),
                "is_file": resolved.is_file(),
            }
        )
    return {
        "default_rows_path": str(rows_path),
        "candidate_paths": rows,
        "detected_row_artifact_count": sum(1 for row in rows if row["is_file"]),
    }


def _engine_run_slots(
    execution_plan: dict[str, Any],
    engine_status_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    case_plans = execution_plan.get("case_execution_plans")
    if not isinstance(case_plans, list):
        return slots
    for case_plan in case_plans:
        if not isinstance(case_plan, dict):
            continue
        case_id = str(case_plan.get("case_id") or "")
        complex_id = str(case_plan.get("complex_id") or "")
        engine_runs = case_plan.get("engine_runs")
        if not isinstance(engine_runs, list):
            continue
        for run in engine_runs:
            if not isinstance(run, dict):
                continue
            engine_id = str(run.get("engine_id") or "")
            engine_status = engine_status_by_id.get(engine_id, {})
            docking_box = run.get("docking_box")
            docking_box_ready = (
                isinstance(docking_box, dict)
                and docking_box.get("status") == "ready"
            )
            engine_available = bool(engine_status.get("available"))
            slot_blockers: list[str] = []
            if not docking_box_ready:
                slot_blockers.append("docking_box_not_ready")
            if not engine_available:
                slot_blockers.append(f"{engine_id}_binary_missing")
            slots.append(
                {
                    "case_id": case_id,
                    "complex_id": complex_id,
                    "engine_id": engine_id,
                    "docking_run_id": str(run.get("docking_run_id") or ""),
                    "docking_box_ready": docking_box_ready,
                    "engine_available": engine_available,
                    "engine_executable": str(engine_status.get("executable") or ""),
                    "command_template": str(run.get("command_template") or ""),
                    "expected_predicted_ligand_path_or_pose_ref": str(
                        run.get("expected_predicted_ligand_path_or_pose_ref") or ""
                    ),
                    "expected_engine_config_ref": str(
                        run.get("expected_engine_config_ref") or ""
                    ),
                    "expected_engine_run_provenance_ref": str(
                        run.get("expected_engine_run_provenance_ref") or ""
                    ),
                    "required_adapter_case_fields": list(REQUIRED_CASE_FIELDS),
                    "required_adapter_engine_run_fields": list(
                        REQUIRED_ENGINE_RUN_FIELDS
                    ),
                    "status": (
                        "ready_for_engine_execution"
                        if docking_box_ready and engine_available
                        else "blocked"
                    ),
                    "blockers": slot_blockers,
                }
            )
    return slots


def build_vina_gnina_runtime_readiness(
    *,
    repo_root: Path = ROOT,
    execution_plan_path: Path = DEFAULT_EXECUTION_PLAN,
    vina_gnina_rows_path: Path = DEFAULT_VINA_GNINA_ROWS,
) -> dict[str, Any]:
    execution_plan = _load_json(repo_root, execution_plan_path)
    current_engine_statuses = [
        _engine_binary_status(engine_id) for engine_id in SUPPORTED_ENGINES
    ]
    engine_status_by_id = {
        str(row.get("engine_id") or ""): row for row in current_engine_statuses
    }
    row_status = _row_candidate_status(repo_root, vina_gnina_rows_path)
    engine_run_slots = _engine_run_slots(execution_plan, engine_status_by_id)
    execution_plan_ready = bool(execution_plan.get("execution_plan_ready"))
    all_engines_available = all(
        bool(row.get("available")) for row in current_engine_statuses
    )
    row_artifacts_ready = row_status["detected_row_artifact_count"] > 0
    slot_blockers = [
        f"{row['case_id']}::{row['engine_id']}::{blocker}"
        for row in engine_run_slots
        for blocker in row["blockers"]
    ]
    blockers: list[str] = []
    if not execution_plan_ready:
        blockers.append("vina_gnina_execution_plan_not_ready")
    blockers.extend(
        str(row.get("blocker"))
        for row in current_engine_statuses
        if str(row.get("blocker") or "")
    )
    if not row_artifacts_ready:
        blockers.append("public_benchmark_vina_gnina_rows_not_detected")
    blockers.extend(slot_blockers)
    blockers = list(dict.fromkeys(blockers))
    runtime_ready = execution_plan_ready and all_engines_available
    if not execution_plan_ready:
        status = "execution_plan_blocked"
    elif not all_engines_available:
        status = "engine_runtime_blocked"
    elif not row_artifacts_ready:
        status = "ready_for_engine_execution"
    else:
        status = "adapter_materialization_ready"
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_vina_gnina_runtime_readiness.py"),
                execution_plan_path,
                Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_runtime_readiness_from_current_environment",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": True,
        "execution_plan_ready": execution_plan_ready,
        "runtime_ready_for_engine_execution": runtime_ready,
        "operator_execution_ready": runtime_ready and row_artifacts_ready,
        "adapter_rows_ready": row_artifacts_ready,
        "phase2_closure_ready": False,
        "supported_engines": list(SUPPORTED_ENGINES),
        "current_engine_binary_statuses": current_engine_statuses,
        "missing_engine_ids": [
            str(row.get("engine_id") or "")
            for row in current_engine_statuses
            if not row.get("available")
        ],
        "row_candidate_status": row_status,
        "engine_run_slots": engine_run_slots,
        "required_engine_run_count": int(
            execution_plan.get("required_engine_run_count") or len(engine_run_slots)
        ),
        "ready_engine_run_slot_count": sum(
            1 for row in engine_run_slots if row["status"] == "ready_for_engine_execution"
        ),
        "operator_commands": {
            "build_execution_plan": (
                "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
                f"--out {DEFAULT_EXECUTION_PLAN}"
            ),
            "materialize_adapter_from_rows": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
                f"--intake {vina_gnina_rows_path} "
                "--out-adapter "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
                "--out-report "
                f"{PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
                "--fail-blocked"
            ),
            "run_phase2_row_audit": (
                "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
                "--fail-blocked"
            ),
        },
        "blockers": blockers,
        "summary": {
            "execution_plan_ready": execution_plan_ready,
            "runtime_ready_for_engine_execution": runtime_ready,
            "operator_execution_ready": runtime_ready and row_artifacts_ready,
            "adapter_rows_ready": row_artifacts_ready,
            "case_count": int(execution_plan.get("case_count") or 0),
            "required_engine_run_count": int(
                execution_plan.get("required_engine_run_count")
                or len(engine_run_slots)
            ),
            "ready_engine_run_slot_count": sum(
                1
                for row in engine_run_slots
                if row["status"] == "ready_for_engine_execution"
            ),
            "available_engine_count": sum(
                1 for row in current_engine_statuses if row.get("available")
            ),
            "missing_engine_count": sum(
                1 for row in current_engine_statuses if not row.get("available")
            ),
            "detected_row_artifact_count": row_status[
                "detected_row_artifact_count"
            ],
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This receipt reflects current runtime readiness for Vina/GNINA engine "
            "execution and adapter materialization. It does not run docking engines, "
            "create comparison rows, synthesize receipts, or close Public Benchmark "
            "Phase 2 without real engine outputs passing the comparison adapter."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--execution-plan", type=Path, default=DEFAULT_EXECUTION_PLAN)
    parser.add_argument("--vina-gnina-rows", type=Path, default=DEFAULT_VINA_GNINA_ROWS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_vina_gnina_runtime_readiness(
        repo_root=args.repo_root,
        execution_plan_path=args.execution_plan,
        vina_gnina_rows_path=args.vina_gnina_rows,
    )
    resolved_out = args.out if args.out.is_absolute() else args.repo_root / args.out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-runtime-readiness: "
            f"{payload['status']} | "
            f"ready_slots={payload['ready_engine_run_slot_count']} | "
            f"blockers={len(payload['blockers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
