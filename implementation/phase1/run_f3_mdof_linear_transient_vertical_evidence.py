#!/usr/bin/env python3
"""Build the linear MDOF transient nine-surface evidence receipt."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"{name}_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SDOF = _load_module(
    "f3_sdof_authenticated_transient_runner",
    ROOT / "implementation/phase1/run_f3_sdof_authenticated_transient_vertical_evidence.py",
)
LINEAR = SDOF.LINEAR
EXPLORER = SDOF.EXPLORER

from structural_analysis.engine_v2.contracts.mdof_transient_result import (  # noqa: E402
    create_mdof_transient_result_ir,
    validate_mdof_transient_result_ir_manifest,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.solvers.linear.transient import (  # noqa: E402
    LinearMDOFSystem,
    LinearMDOFTransientConfig,
    resume_linear_mdof_transient,
    solve_linear_mdof_transient,
    validate_linear_mdof_checkpoint_authority,
)
from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    ExternalVVSignatureVerification,
    F3Evidence,
    F3StageGateReceipt,
    evaluate_f3_stage_gate,
)


MODEL_PATH = Path("tests/fixtures/model_ir_v2/mdof_linear_transient.json")
FORCE_PATH = Path("tests/fixtures/dynamics/mdof_linear_force_history.csv")
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_mdof_linear_transient_vertical_evidence.json"
)
PREDECESSOR_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_sdof_authenticated_transient_vertical_evidence.json"
)
SCHEMA_VERSION = "f3-mdof-linear-transient-vertical-evidence.v1"
SOLVER_ID = "newmark.average-acceleration.linear-mdof.v1"
SOURCE_PATHS = (
    MODEL_PATH,
    FORCE_PATH,
    Path("src/structural_analysis/schemas/model_ir_v2.schema.json"),
    Path("src/structural_analysis/solvers/linear/transient.py"),
    Path("src/structural_analysis/engine_v2/contracts/mdof_transient_result.py"),
    Path("src/structural_analysis/schemas/mdof_transient_result_ir_v1.schema.json"),
    Path("implementation/phase1/results_explorer.py"),
    Path("implementation/phase1/run_f3_sdof_authenticated_transient_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_mdof_linear_transient_vertical_evidence.py"),
    Path("tests/test_linear_mdof_transient.py"),
    Path("tests/test_mdof_transient_result_ir.py"),
    Path("tests/test_f3_mdof_linear_transient_vertical_evidence.py"),
)


def _inputs() -> tuple[Any, LinearMDOFSystem, LinearMDOFTransientConfig, np.ndarray]:
    document = load_model_ir_v2(ROOT / MODEL_PATH)
    dynamics = document.to_dict()["dynamics"]
    if LINEAR._file_sha(FORCE_PATH) != dynamics["force_history_sha256"]:
        raise RuntimeError("mdof_force_history_sha256_mismatch")
    with (ROOT / FORCE_PATH).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    dt = float(dynamics["time_step_s"])
    times = np.asarray([float(row["time_s"]) for row in rows], dtype=np.float64)
    if not np.allclose(times, np.arange(len(rows)) * dt, rtol=0.0, atol=1.0e-12):
        raise RuntimeError("mdof_force_history_time_axis_mismatch")
    dof_ids = tuple(dynamics["dof_ids"])
    force_columns = ("floor_1_ux_n", "floor_2_ux_n")
    if len(force_columns) != len(dof_ids):
        raise RuntimeError("mdof_force_column_count_mismatch")
    forces = np.asarray([[float(row[column]) for column in force_columns] for row in rows])
    system = LinearMDOFSystem(
        dynamics["mass_matrix_kg"], dynamics["damping_matrix_n_s_per_m"],
        dynamics["stiffness_matrix_n_per_m"], dof_ids, model_id=document.model_id,
    )
    return document, system, LinearMDOFTransientConfig(time_step_s=dt), forces


def _result_ir(
    *, document: Any, system: LinearMDOFSystem, config: LinearMDOFTransientConfig,
    forces: np.ndarray, solution: Any, authority: Any,
) -> dict[str, Any]:
    result = create_mdof_transient_result_ir(
        result_id="f3.mdof.linear-transient",
        model_ir_content_hash=document.content_hash,
        force_history_hash=LINEAR._sha_payload(forces.tolist()),
        solver_id=SOLVER_ID,
        solver_result_hash=solution.result_hash,
        integration_contract_hash=config.contract_hash,
        terminal_checkpoint_hash=solution.checkpoints[-1].checkpoint_hash,
        checkpoint_authority_receipt_hash=authority.receipt_hash,
        dof_ids=system.dof_ids,
        time_step_s=config.time_step_s,
        residual_relative_tolerance=config.residual_relative_tolerance,
        samples=[step.to_dict() for step in solution.steps],
    )
    manifest = result.to_manifest()
    validate_mdof_transient_result_ir_manifest(manifest)
    return manifest


def _predecessor(source_commit: str) -> tuple[F3StageGateReceipt, str, dict[str, Any]]:
    current = SDOF.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_sdof_transient_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt.from_dict(stage)
    persisted = json.loads((ROOT / PREDECESSOR_RECEIPT).read_text(encoding="utf-8"))
    replay = {
        "source_receipt_path": PREDECESSOR_RECEIPT.as_posix(),
        "source_receipt_sha256": LINEAR._file_sha(PREDECESSOR_RECEIPT),
        "persisted_source_commit_sha": persisted["source_commit_sha"],
        "current_source_replay_executed": True,
        "replayed_source_commit_sha": source_commit,
        "vertical_stage_contract_passed": receipt.vertical_stage_contract_passed,
        "public_product_promotion_passed": receipt.public_product_promotion_passed,
    }
    return receipt, LINEAR._sha_payload(current["stage_gate"]), replay


def _modal_benchmark() -> dict[str, Any]:
    system = LinearMDOFSystem(
        [[2.0, 0.0], [0.0, 1.0]], [[0.0, 0.0], [0.0, 0.0]],
        [[600.0, -200.0], [-200.0, 200.0]], ("Floor1_UX", "Floor2_UX"),
        model_id="mdof-modal-vv",
    )
    mass, _, stiffness = system.arrays()
    eigenvalues, eigenvectors = np.linalg.eig(np.linalg.solve(mass, stiffness))
    mode_index = int(np.argmin(eigenvalues))
    omega = math.sqrt(float(eigenvalues[mode_index]))
    mode = np.asarray(eigenvectors[:, mode_index], dtype=np.float64)
    mode /= np.max(np.abs(mode))
    config = LinearMDOFTransientConfig(time_step_s=0.0005)
    sample_count = 1001
    solution = solve_linear_mdof_transient(
        system, np.zeros((sample_count, 2)), config=config,
        initial_displacement_m=0.01 * mode,
    )
    terminal_time = config.time_step_s * (sample_count - 1)
    exact = 0.01 * mode * math.cos(omega * terminal_time)
    observed = np.asarray(solution.steps[-1].displacement_m)
    return {
        "benchmark_id": "two-dof-first-mode-undamped-closed-form.v1",
        "first_mode_omega_rad_per_s": omega,
        "terminal_time_s": terminal_time,
        "exact_terminal_displacement_m": exact.tolist(),
        "observed_terminal_displacement_m": observed.tolist(),
        "maximum_absolute_error_m": float(np.max(np.abs(observed - exact))),
        "maximum_absolute_energy_balance_error_j": solution.maximum_absolute_energy_balance_error_j,
        "tolerance_m": 2.0e-7,
    }


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    document, system, config, forces = _inputs()
    solution = solve_linear_mdof_transient(system, forces, config=config)
    split = 11
    prefix = solve_linear_mdof_transient(system, forces[:split], config=config)
    resumed = resume_linear_mdof_transient(
        system, prefix.checkpoints[-1], forces[split:], config=config,
        checkpoint_chain=prefix.checkpoints, force_history_prefix_n=forces[:split],
    )
    joined = (*prefix.checkpoints, *resumed.checkpoints[1:])
    exact_restart = joined == solution.checkpoints
    authority = validate_linear_mdof_checkpoint_authority(
        solution.checkpoints[-1], system=system, config=config,
        checkpoint_chain=solution.checkpoints, force_history_prefix_n=forces,
    )
    repeated = solve_linear_mdof_transient(system, forces, config=config)
    deterministic = repeated.result_hash == solution.result_hash
    result_manifest = _result_ir(
        document=document, system=system, config=config, forces=forces,
        solution=solution, authority=authority,
    )
    benchmark = _modal_benchmark()
    displacements = np.asarray([step.displacement_m for step in solution.steps])
    velocities = np.asarray([step.velocity_m_per_s for step in solution.steps])
    accelerations = np.asarray([step.acceleration_m_per_s2 for step in solution.steps])
    residuals = np.asarray([step.equilibrium_residual_n for step in solution.steps])
    histories = []
    for index, dof_id in enumerate(system.dof_ids):
        history = EXPLORER.evaluate_time_history(
            result_type=f"mdof_displacement_m:{dof_id}",
            time_steps=tuple(step.time_s for step in solution.steps),
            values=tuple(float(value) for value in displacements[:, index]),
        )
        histories.append(history)
    workbench = {
        "schema_version": "f3-mdof-linear-transient-workbench-payload.v1",
        "model_ir_content_hash": document.content_hash,
        "dof_ids": list(system.dof_ids),
        "time_history_cards": [history.__dict__ for history in histories],
        "summary": EXPLORER.build_results_summary(time_histories=tuple(histories)),
    }
    all_pass = bool(
        document.analysis_ready and solution.contract_pass and exact_restart
        and deterministic and authority.source_authenticated_checkpoint
        and authority.parent_chain_complete and authority.dynamic_equilibrium_replay_pass
        and authority.newmark_kinematic_replay_pass and authority.energy_replay_pass
        and authority.deterministic_checkpoint_replay_pass
        and not solution.fallback_used and not solution.regularization_used
        and solution.maximum_relative_residual <= config.residual_relative_tolerance
        and benchmark["maximum_absolute_error_m"] <= benchmark["tolerance_m"]
        and benchmark["maximum_absolute_energy_balance_error_j"] <= 1.0e-12
    )
    surface_artifacts: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash, "model_id": document.model_id,
            "capability_profile": document.capability_profile,
            "analysis_ready": document.analysis_ready,
            "force_history_source_sha256": document.to_dict()["dynamics"]["force_history_sha256"],
            "matrix_dimension": system.dimension,
        },
        "solver": {
            "schema_version": solution.schema_version, "profile": solution.profile,
            "solver_id": SOLVER_ID, "step_count": len(solution.steps),
            "linear_solve_count": solution.linear_solve_count,
            "maximum_relative_residual": solution.maximum_relative_residual,
            "maximum_absolute_energy_balance_error_j": solution.maximum_absolute_energy_balance_error_j,
            "fallback_used": solution.fallback_used,
            "regularization_used": solution.regularization_used,
        },
        "result_ir": {"schema_version": result_manifest["schema_version"], "manifest": result_manifest, "manifest_valid": True},
        "recovery": {
            "maximum_absolute_displacement_by_dof_m": dict(zip(system.dof_ids, np.max(np.abs(displacements), axis=0).tolist(), strict=True)),
            "maximum_absolute_velocity_by_dof_m_per_s": dict(zip(system.dof_ids, np.max(np.abs(velocities), axis=0).tolist(), strict=True)),
            "maximum_absolute_acceleration_by_dof_m_per_s2": dict(zip(system.dof_ids, np.max(np.abs(accelerations), axis=0).tolist(), strict=True)),
            "maximum_absolute_equilibrium_residual_n": float(np.max(np.abs(residuals))),
        },
        "checkpoint": {
            "terminal_checkpoint": solution.checkpoints[-1].to_dict(),
            "source_authority_receipt": authority.to_dict(),
            "prefix_terminal_checkpoint_hash": prefix.checkpoints[-1].checkpoint_hash,
            "resumed_terminal_checkpoint_hash": resumed.checkpoints[-1].checkpoint_hash,
            "exact_restart": exact_restart,
        },
        "workbench": workbench,
        "benchmark": {**benchmark, "deterministic_repeat": deterministic},
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(), "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "independent_generalized_eigen_first_mode_cosine.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "maximum_absolute_error_m": benchmark["maximum_absolute_error_m"],
            "source_authenticated_checkpoint_pass": authority.source_authenticated_checkpoint,
            "signature_verifier_waived": True,
        },
    }
    evidence = [
        F3Evidence(surface=surface, status="verified" if all_pass else "blocked", artifact_sha256=LINEAR._sha_payload(artifact))
        for surface, artifact in surface_artifacts.items()
    ]
    predecessor, predecessor_hash, predecessor_replay = _predecessor(source_commit)
    gate = evaluate_f3_stage_gate(
        stage="mdof_linear_transient", source_commit_sha=source_commit,
        evidence=evidence,
        external_vv_signature=ExternalVVSignatureVerification(
            status="waived", authority="user_authorized_signature_verifier_waiver",
            waiver_reason="User authorized signature-verifier omission for F3 self-verification.",
        ),
        predecessor_receipt=predecessor, predecessor_receipt_sha256=predecessor_hash,
    )
    return {
        "schema_version": SCHEMA_VERSION, "source_commit_sha": source_commit,
        "source_input_checksums": {path.as_posix(): LINEAR._file_sha(path) for path in SOURCE_PATHS},
        "status": gate.status,
        "contract_pass": gate.vertical_stage_contract_passed,
        "predecessor_replay": predecessor_replay,
        "stage_gate": gate.to_dict(),
        "surface_artifacts": surface_artifacts,
        "claim_boundary": (
            "Closes a bounded force-driven two-DOF linear matrix Newmark stage with "
            "ModelIR matrix/source hash binding, authoritative vector SI ResultIR, "
            "complete source-authenticated checkpoint replay, Workbench histories, "
            "and an independent generalized-eigen first-mode closed-form check. "
            "Nonlinear MDOF, support excitation, shell, and contact remain outside."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if args.check:
        if not out.is_file():
            print("f3_mdof_linear_transient_vertical_evidence_mismatch")
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=str(recorded["source_commit_sha"]))
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if recorded.get("source_input_checksums") != payload["source_input_checksums"] or out.read_text(encoding="utf-8") != text:
            print("f3_mdof_linear_transient_vertical_evidence_mismatch")
            return 1
        print("f3_mdof_linear_transient_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    solver = payload["surface_artifacts"]["solver"]
    print(f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | dofs=2 | steps={solver['step_count']}")
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
