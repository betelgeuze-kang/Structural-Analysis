#!/usr/bin/env python3
"""Build the SDOF authenticated-transient nine-surface evidence receipt."""

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


MODAL = _load_module(
    "f3_modal_buckling_runner",
    ROOT / "implementation/phase1/run_f3_modal_buckling_vertical_evidence.py",
)
EXPLORER = MODAL.EXPLORER
LINEAR = MODAL.LINEAR

from structural_analysis.engine_v2.contracts.transient_result import (  # noqa: E402
    create_transient_result_ir,
    validate_transient_result_ir_manifest,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.solvers.nonlinear.transient import (  # noqa: E402
    BilinearOscillator,
    NonlinearTransientConfig,
    SOURCE_AUTHENTICATED_CHECKPOINT_AUTHORITY,
    resume_bilinear_transient,
    solve_bilinear_transient,
    validate_nonlinear_transient_checkpoint_chain,
)
from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    ExternalVVSignatureVerification,
    F3Evidence,
    F3StageGateReceipt,
    evaluate_f3_stage_gate,
)


MODEL_PATH = Path("tests/fixtures/model_ir_v2/sdof_authenticated_transient.json")
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_sdof_authenticated_transient_vertical_evidence.json"
)
MODAL_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_modal_buckling_vertical_evidence.json"
)
SCHEMA_VERSION = "f3-sdof-authenticated-transient-vertical-evidence.v1"
SOLVER_ID = "newmark.average-acceleration.bilinear-sdof.v1"
SOURCE_PATHS = (
    MODEL_PATH,
    Path("tests/fixtures/dynamics/sdof_authenticated_force_history.csv"),
    Path("src/structural_analysis/schemas/model_ir_v2.schema.json"),
    Path("src/structural_analysis/solvers/nonlinear/transient.py"),
    Path(
        "src/structural_analysis/schemas/nonlinear_transient_checkpoint_v1.schema.json"
    ),
    Path("src/structural_analysis/engine_v2/contracts/transient_result.py"),
    Path("src/structural_analysis/schemas/transient_result_ir_v1.schema.json"),
    Path("implementation/phase1/results_explorer.py"),
    Path("implementation/phase1/run_f3_modal_buckling_vertical_evidence.py"),
    Path(
        "implementation/phase1/run_f3_sdof_authenticated_transient_vertical_evidence.py"
    ),
    Path("tests/test_f3_sdof_authenticated_transient_vertical_evidence.py"),
)


def _inputs() -> tuple[
    Any, BilinearOscillator, NonlinearTransientConfig, tuple[float, ...]
]:
    document = load_model_ir_v2(ROOT / MODEL_PATH)
    payload = document.to_dict()
    dynamics = payload["dynamics"]
    source = ROOT / dynamics["force_history_source_path"]
    if (
        LINEAR._file_sha(Path(dynamics["force_history_source_path"]))
        != dynamics["force_history_sha256"]
    ):
        raise RuntimeError("sdof_force_history_sha256_mismatch")
    with source.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    csv_points = [(float(row["time_s"]), float(row["force_n"])) for row in rows]
    function = next(
        row
        for row in payload["time_functions"]
        if row["id"] == dynamics["force_time_function_id"]
    )
    model_points = [(float(row[0]), float(row[1])) for row in function["points"]]
    if csv_points != model_points:
        raise RuntimeError("sdof_force_history_model_ir_mismatch")
    dt = float(dynamics["time_step_s"])
    if any(
        not math.isclose(time_s, index * dt, rel_tol=0.0, abs_tol=1.0e-12)
        for index, (time_s, _) in enumerate(csv_points)
    ):
        raise RuntimeError("sdof_force_history_time_axis_mismatch")
    model = BilinearOscillator(
        mass_kn_s2_per_m=float(dynamics["mass_kg"]) / 1000.0,
        elastic_stiffness_kn_per_m=float(dynamics["elastic_stiffness_n_per_m"])
        / 1000.0,
        yield_force_kn=float(dynamics["yield_force_n"]) / 1000.0,
        post_yield_stiffness_ratio=float(dynamics["post_yield_stiffness_ratio"]),
        damping_kn_s_per_m=float(dynamics["damping_n_s_per_m"]) / 1000.0,
        model_id=document.model_id,
    )
    config = NonlinearTransientConfig(time_step_s=dt)
    return document, model, config, tuple(force_n / 1000.0 for _, force_n in csv_points)


def _result_ir(
    *,
    document: Any,
    config: Any,
    forces_kn: tuple[float, ...],
    solution: Any,
    authority: dict[str, Any],
) -> dict[str, Any]:
    samples = [
        {
            "step_index": step.step_index,
            "time_s": step.time_s,
            "applied_force_n": step.applied_force_kn * 1000.0,
            "displacement_m": step.displacement_m,
            "velocity_m_per_s": step.velocity_m_per_s,
            "acceleration_m_per_s2": step.acceleration_m_per_s2,
            "restoring_force_n": step.restoring_force_kn * 1000.0,
            "equilibrium_residual_n": step.equilibrium_residual_kn * 1000.0,
            "relative_residual": step.relative_residual,
            "kinetic_energy_j": step.kinetic_energy_kn_m * 1000.0,
            "stored_energy_j": step.stored_energy_kn_m * 1000.0,
            "external_work_j": step.external_work_kn_m * 1000.0,
            "damping_dissipation_j": step.damping_dissipation_kn_m * 1000.0,
            "plastic_dissipation_j": step.plastic_dissipation_kn_m * 1000.0,
            "yielded": step.yielded,
            "newton_iterations": step.newton_iterations,
        }
        for step in solution.steps
    ]
    state = solution.checkpoints[-1].material_state
    result = create_transient_result_ir(
        result_id="f3.sdof.authenticated-transient",
        model_ir_content_hash=document.content_hash,
        force_history_hash=LINEAR._sha_payload(list(forces_kn)),
        solver_id=SOLVER_ID,
        solver_result_hash=solution.result_hash,
        integration_contract_hash=config.contract_hash,
        terminal_checkpoint_hash=solution.checkpoints[-1].checkpoint_hash,
        checkpoint_authority_receipt_hash=authority["receipt_hash"],
        time_step_s=config.time_step_s,
        residual_relative_tolerance=config.residual_relative_tolerance,
        samples=samples,
        terminal_material_state={
            "plastic_displacement_m": state.plastic_displacement_m,
            "backstress_n": state.backstress_kn * 1000.0,
            "cumulative_plastic_displacement_m": state.cumulative_plastic_displacement_m,
            "plastic_dissipation_j": state.plastic_dissipation_kn_m * 1000.0,
        },
    )
    manifest = result.to_manifest()
    validate_transient_result_ir_manifest(manifest)
    return manifest


def _checkpoint_authority_receipt(chain: Any) -> dict[str, Any]:
    checkpoints = chain.checkpoints
    parent_chain_complete = bool(
        checkpoints
        and all(
            checkpoint.parent_checkpoint_hash
            == (None if index == 0 else checkpoints[index - 1].checkpoint_hash)
            for index, checkpoint in enumerate(checkpoints)
        )
    )
    source_authenticated = bool(
        chain.authority == SOURCE_AUTHENTICATED_CHECKPOINT_AUTHORITY
        and parent_chain_complete
    )
    return {
        "schema_version": "f3-sdof-checkpoint-authority-adapter.v1",
        "authority": chain.authority,
        "checkpoint_hash": checkpoints[-1].checkpoint_hash,
        "source_authenticated_checkpoint": source_authenticated,
        "parent_chain_complete": parent_chain_complete,
        "newmark_kinematic_replay_pass": source_authenticated,
        "dynamic_equilibrium_replay_pass": source_authenticated,
        "external_work_replay_pass": source_authenticated,
        "damping_dissipation_replay_pass": source_authenticated,
        "plastic_dissipation_replay_pass": source_authenticated,
        "deterministic_checkpoint_replay_pass": source_authenticated,
        "receipt_hash": chain.chain_hash,
    }


def _predecessor(source_commit: str) -> tuple[F3StageGateReceipt, str, dict[str, Any]]:
    current = MODAL.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_modal_buckling_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt(
        schema="f3-vertical-evidence-gate.v1",
        stage="modal_buckling",
        stage_index=4,
        source_commit_sha=source_commit,
        required_surfaces=tuple(stage["required_surfaces"]),
        verified_surfaces=tuple(stage["verified_surfaces"]),
        evidence_artifact_sha256=tuple(
            sorted(stage["evidence_artifact_sha256"].items())
        ),
        predecessor_stage="frame3d_stateful_material",
        predecessor_receipt_sha256=stage["predecessor_receipt_sha256"],
        external_vv_signature_status="waived",
        blockers=tuple(stage["blockers"]),
        public_product_promotion_passed=bool(stage["public_product_promotion_passed"]),
    )
    persisted = json.loads((ROOT / MODAL_RECEIPT).read_text(encoding="utf-8"))
    replay = {
        "source_receipt_path": MODAL_RECEIPT.as_posix(),
        "source_receipt_sha256": LINEAR._file_sha(MODAL_RECEIPT),
        "persisted_source_commit_sha": persisted["source_commit_sha"],
        "current_source_replay_executed": True,
        "replayed_source_commit_sha": source_commit,
        "public_product_promotion_passed": receipt.public_product_promotion_passed,
    }
    return receipt, LINEAR._sha_payload(current["stage_gate"]), replay


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    document, model, config, forces_kn = _inputs()
    solution = solve_bilinear_transient(model, forces_kn, config=config)
    split = 11
    prefix = solve_bilinear_transient(model, forces_kn[:split], config=config)
    resumed = resume_bilinear_transient(
        model,
        prefix.checkpoint_chain,
        forces_kn[split:],
        config=config,
    )
    joined = (*prefix.checkpoints, *resumed.checkpoints[1:])
    exact_restart = bool(
        joined == solution.checkpoints and resumed.steps[-1] == solution.steps[-1]
    )
    validate_nonlinear_transient_checkpoint_chain(
        solution.checkpoint_chain,
        model=model,
        config=config,
    )
    authority = _checkpoint_authority_receipt(solution.checkpoint_chain)
    repeated = solve_bilinear_transient(model, forces_kn, config=config)
    deterministic = repeated.result_hash == solution.result_hash
    result_manifest = _result_ir(
        document=document,
        config=config,
        forces_kn=forces_kn,
        solution=solution,
        authority=authority,
    )

    linear_model = BilinearOscillator(1.0, 4.0, 1000.0, 0.05, model_id="sdof-linear-vv")
    linear_config = NonlinearTransientConfig(time_step_s=0.005)
    linear_solution = solve_bilinear_transient(
        linear_model, [0.0] * 201, config=linear_config, initial_displacement_m=0.1
    )
    exact_linear_displacement = 0.1 * math.cos(2.0)
    linear_error_m = abs(
        linear_solution.steps[-1].displacement_m - exact_linear_displacement
    )
    max_displacement_m = max(abs(step.displacement_m) for step in solution.steps)
    max_velocity_m_per_s = max(abs(step.velocity_m_per_s) for step in solution.steps)
    max_acceleration_m_per_s2 = max(
        abs(step.acceleration_m_per_s2) for step in solution.steps
    )
    max_residual_n = max(
        abs(step.equilibrium_residual_kn) * 1000.0 for step in solution.steps
    )
    max_energy_error_j = solution.maximum_absolute_energy_balance_error_kn_m * 1000.0
    state = solution.checkpoints[-1].material_state
    displacement_history = EXPLORER.evaluate_time_history(
        result_type="sdof_displacement_m",
        time_steps=tuple(step.time_s for step in solution.steps),
        values=tuple(step.displacement_m for step in solution.steps),
    )
    force_history = EXPLORER.evaluate_time_history(
        result_type="sdof_applied_force_n",
        time_steps=tuple(step.time_s for step in solution.steps),
        values=tuple(step.applied_force_kn * 1000.0 for step in solution.steps),
    )
    workbench = {
        "schema_version": "f3-sdof-transient-workbench-payload.v1",
        "model_ir_content_hash": document.content_hash,
        "time_history_cards": [displacement_history.__dict__, force_history.__dict__],
        "summary": EXPLORER.build_results_summary(
            time_histories=(displacement_history, force_history)
        ),
    }
    all_pass = bool(
        document.analysis_ready
        and solution.contract_pass
        and exact_restart
        and deterministic
        and authority["source_authenticated_checkpoint"]
        and authority["parent_chain_complete"]
        and authority["newmark_kinematic_replay_pass"]
        and authority["dynamic_equilibrium_replay_pass"]
        and authority["external_work_replay_pass"]
        and authority["damping_dissipation_replay_pass"]
        and authority["plastic_dissipation_replay_pass"]
        and authority["deterministic_checkpoint_replay_pass"]
        and solution.yielded_step_count > 0
        and state.cumulative_plastic_displacement_m > 0.0
        and state.plastic_dissipation_kn_m > 0.0
        and not solution.fallback_used
        and not solution.regularization_used
        and solution.maximum_relative_residual <= config.residual_relative_tolerance
        and linear_error_m <= 2.0e-6
    )
    surface_artifacts: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash,
            "model_id": document.model_id,
            "capability_profile": document.capability_profile,
            "analysis_ready": document.analysis_ready,
            "force_history_source_sha256": document.to_dict()["dynamics"][
                "force_history_sha256"
            ],
        },
        "solver": {
            "schema_version": solution.schema_version,
            "profile": solution.profile,
            "solver_id": SOLVER_ID,
            "step_count": len(solution.steps),
            "yielded_step_count": solution.yielded_step_count,
            "maximum_relative_residual": solution.maximum_relative_residual,
            "maximum_absolute_energy_balance_error_j": max_energy_error_j,
            "fallback_used": solution.fallback_used,
            "regularization_used": solution.regularization_used,
        },
        "result_ir": {
            "schema_version": result_manifest["schema_version"],
            "manifest": result_manifest,
            "manifest_valid": True,
        },
        "recovery": {
            "maximum_absolute_displacement_m": max_displacement_m,
            "maximum_absolute_velocity_m_per_s": max_velocity_m_per_s,
            "maximum_absolute_acceleration_m_per_s2": max_acceleration_m_per_s2,
            "maximum_absolute_equilibrium_residual_n": max_residual_n,
            "terminal_material_state": result_manifest["terminal_material_state"],
        },
        "checkpoint": {
            "terminal_checkpoint": solution.checkpoints[-1].to_dict(),
            "source_authority_receipt": authority,
            "prefix_terminal_checkpoint_hash": prefix.checkpoints[-1].checkpoint_hash,
            "resumed_terminal_checkpoint_hash": resumed.checkpoints[-1].checkpoint_hash,
            "exact_restart": exact_restart,
            "source_authenticated_resume": (
                resumed.resume_checkpoint_authority
                == SOURCE_AUTHENTICATED_CHECKPOINT_AUTHORITY
            ),
        },
        "workbench": workbench,
        "benchmark": {
            "benchmark_id": "sdof-newmark-linear-closed-form-plus-bilinear-cyclic.v1",
            "linear_exact_terminal_displacement_m": exact_linear_displacement,
            "linear_observed_terminal_displacement_m": linear_solution.steps[
                -1
            ].displacement_m,
            "linear_absolute_error_m": linear_error_m,
            "linear_energy_error_kn_m": linear_solution.maximum_absolute_energy_balance_error_kn_m,
            "cyclic_plastic_history_nonzero": state.cumulative_plastic_displacement_m
            > 0.0,
            "cyclic_plastic_dissipation_nonzero": state.plastic_dissipation_kn_m > 0.0,
            "deterministic_repeat": deterministic,
        },
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "undamped_linear_sdof_cosine_solution.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "linear_absolute_error_m": linear_error_m,
            "source_authenticated_checkpoint_pass": authority[
                "source_authenticated_checkpoint"
            ],
            "signature_verifier_waived": True,
        },
    }
    evidence = [
        F3Evidence(
            surface=surface,
            status="verified" if all_pass else "blocked",
            artifact_sha256=LINEAR._sha_payload(artifact),
        )
        for surface, artifact in surface_artifacts.items()
    ]
    predecessor, predecessor_hash, predecessor_replay = _predecessor(source_commit)
    gate = evaluate_f3_stage_gate(
        stage="sdof_authenticated_transient",
        source_commit_sha=source_commit,
        evidence=evidence,
        external_vv_signature=ExternalVVSignatureVerification(
            status="waived",
            authority="user_authorized_signature_verifier_waiver",
            waiver_reason="User authorized signature-verifier omission for F3 self-verification.",
        ),
        predecessor_receipt=predecessor,
        predecessor_receipt_sha256=predecessor_hash,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit,
        "source_input_checksums": {
            path.as_posix(): LINEAR._file_sha(path) for path in SOURCE_PATHS
        },
        "status": "ready" if gate.public_product_promotion_passed else "blocked",
        "contract_pass": gate.public_product_promotion_passed,
        "predecessor_replay": predecessor_replay,
        "stage_gate": {
            "stage": gate.stage,
            "stage_index": gate.stage_index,
            "source_commit_sha": gate.source_commit_sha,
            "required_surfaces": list(gate.required_surfaces),
            "verified_surfaces": list(gate.verified_surfaces),
            "evidence_artifact_sha256": dict(gate.evidence_artifact_sha256),
            "predecessor_stage": gate.predecessor_stage,
            "predecessor_receipt_sha256": gate.predecessor_receipt_sha256,
            "external_vv_signature_status": gate.external_vv_signature_status,
            "blockers": list(gate.blockers),
            "public_product_promotion_passed": gate.public_product_promotion_passed,
        },
        "surface_artifacts": surface_artifacts,
        "claim_boundary": (
            "Closes a bounded force-driven bilinear SDOF Newmark transient stage "
            "with ModelIR and exact CSV hash binding, authoritative SI time-history "
            "ResultIR, complete source-authenticated checkpoint replay, Workbench "
            "history cards, and a closed-form linear oscillator check. Ground-motion "
            "support excitation and MDOF response remain outside this stage."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = ROOT / args.out
    if args.check:
        if not out.is_file():
            print("f3_sdof_authenticated_transient_vertical_evidence_mismatch")
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=str(recorded["source_commit_sha"]))
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if (
            recorded.get("source_input_checksums") != payload["source_input_checksums"]
            or out.read_text(encoding="utf-8") != text
        ):
            print("f3_sdof_authenticated_transient_vertical_evidence_mismatch")
            return 1
        print("f3_sdof_authenticated_transient_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    solver = payload["surface_artifacts"]["solver"]
    print(
        f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | "
        f"steps={solver['step_count']} | yielded={solver['yielded_step_count']}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
