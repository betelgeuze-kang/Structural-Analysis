#!/usr/bin/env python3
"""Build the nonlinear MDOF transient nine-surface evidence receipt."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"{name}_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MDOF = _load(
    "f3_mdof_linear_runner",
    ROOT / "implementation/phase1/run_f3_mdof_linear_transient_vertical_evidence.py",
)
LINEAR, EXPLORER = MDOF.LINEAR, MDOF.EXPLORER

from structural_analysis.engine_v2.contracts.nonlinear_mdof_transient_result import (  # noqa: E402
    create_nonlinear_mdof_result_ir,
    validate_nonlinear_mdof_result_ir_manifest,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.solvers.linear.transient import (  # noqa: E402
    LinearMDOFSystem,
    LinearMDOFTransientConfig,
    solve_linear_mdof_transient,
)
from structural_analysis.solvers.nonlinear.mdof_transient import (  # noqa: E402
    BilinearStory,
    NonlinearMDOFTransientConfig,
    NonlinearMDOFTransientError,
    NonlinearShearBuilding,
    resume_nonlinear_mdof_transient,
    solve_nonlinear_mdof_transient,
    validate_nonlinear_mdof_checkpoint_authority,
)
from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    ExternalVVSignatureVerification,
    F3Evidence,
    F3StageGateReceipt,
    evaluate_f3_stage_gate,
)

MODEL_PATH = Path("tests/fixtures/model_ir_v2/nonlinear_mdof_transient.json")
FORCE_PATH = Path("tests/fixtures/dynamics/nonlinear_mdof_force_history.csv")
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/f3_nonlinear_mdof_vertical_evidence.json"
)
PREDECESSOR_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/f3_mdof_linear_transient_vertical_evidence.json"
)
SOLVER_ID = "newmark.consistent-newton.bilinear-shear-mdof.v1"
SOURCE_PATHS = (
    MODEL_PATH,
    FORCE_PATH,
    Path("src/structural_analysis/schemas/model_ir_v2.schema.json"),
    Path("src/structural_analysis/solvers/nonlinear/mdof_transient.py"),
    Path(
        "src/structural_analysis/engine_v2/contracts/nonlinear_mdof_transient_result.py"
    ),
    Path(
        "src/structural_analysis/schemas/nonlinear_mdof_transient_result_ir_v1.schema.json"
    ),
    Path("implementation/phase1/results_explorer.py"),
    Path("implementation/phase1/run_f3_mdof_linear_transient_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_nonlinear_mdof_vertical_evidence.py"),
    Path("tests/test_nonlinear_mdof_transient.py"),
    Path("tests/test_nonlinear_mdof_transient_result_ir.py"),
    Path("tests/test_f3_nonlinear_mdof_vertical_evidence.py"),
)


def _inputs() -> tuple[
    Any, NonlinearShearBuilding, NonlinearMDOFTransientConfig, np.ndarray
]:
    document = load_model_ir_v2(ROOT / MODEL_PATH)
    dynamics = document.to_dict()["dynamics"]
    if LINEAR._file_sha(FORCE_PATH) != dynamics["force_history_sha256"]:
        raise RuntimeError("nonlinear_mdof_force_history_sha256_mismatch")
    with (ROOT / FORCE_PATH).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    dt = float(dynamics["time_step_s"])
    times = np.asarray([float(row["time_s"]) for row in rows])
    if not np.allclose(times, np.arange(len(rows)) * dt, rtol=0.0, atol=1e-12):
        raise RuntimeError("nonlinear_mdof_force_time_axis_mismatch")
    forces_kn = (
        np.asarray(
            [[float(row["floor_1_ux_n"]), float(row["floor_2_ux_n"])] for row in rows]
        )
        / 1000.0
    )
    stories = tuple(
        BilinearStory(
            row["story_id"],
            float(row["elastic_stiffness_n_per_m"]) / 1000.0,
            float(row["yield_force_n"]) / 1000.0,
            float(row["post_yield_stiffness_ratio"]),
        )
        for row in dynamics["stories"]
    )
    system = NonlinearShearBuilding(
        np.asarray(dynamics["mass_matrix_kg"]) / 1000.0,
        np.asarray(dynamics["damping_matrix_n_s_per_m"]) / 1000.0,
        stories,
        dynamics["dof_ids"],
        model_id=document.model_id,
    )
    return document, system, NonlinearMDOFTransientConfig(dt), forces_kn


def _result(
    document: Any,
    system: Any,
    config: Any,
    forces: np.ndarray,
    solution: Any,
    authority: Any,
) -> dict[str, Any]:
    samples = []
    for step in solution.steps:
        row = step.to_dict()
        for key in ("applied_force_kn", "story_force_kn", "equilibrium_residual_kn"):
            row[key.removesuffix("_kn") + "_n"] = [
                value * 1000.0 for value in row.pop(key)
            ]
        row["kinetic_energy_j"] = row.pop("kinetic_energy_kn_m") * 1000.0
        row["stored_energy_j"] = row.pop("stored_energy_kn_m") * 1000.0
        row["external_work_j"] = row.pop("external_work_kn_m") * 1000.0
        row["damping_dissipation_j"] = row.pop("damping_dissipation_kn_m") * 1000.0
        row["plastic_dissipation_j"] = row.pop("plastic_dissipation_kn_m") * 1000.0
        row["energy_balance_error_j"] = row.pop("energy_balance_error_kn_m") * 1000.0
        row.pop("checkpoint_hash")
        samples.append(row)
    terminal_states = [
        {
            "story_id": system.stories[index].story_id,
            "plastic_displacement_m": state.plastic_displacement_m,
            "backstress_n": state.backstress_kn * 1000.0,
            "cumulative_plastic_displacement_m": state.cumulative_plastic_displacement_m,
            "plastic_dissipation_j": state.plastic_dissipation_kn_m * 1000.0,
        }
        for index, state in enumerate(solution.checkpoints[-1].material_states)
    ]
    result = create_nonlinear_mdof_result_ir(
        result_id="f3.nonlinear-mdof",
        model_ir_content_hash=document.content_hash,
        force_history_hash=LINEAR._sha_payload(forces.tolist()),
        solver_id=SOLVER_ID,
        solver_result_hash=solution.result_hash,
        integration_contract_hash=config.contract_hash,
        terminal_checkpoint_hash=solution.checkpoints[-1].checkpoint_hash,
        checkpoint_authority_receipt_hash=authority.receipt_hash,
        dof_ids=system.dof_ids,
        story_ids=tuple(row.story_id for row in system.stories),
        time_step_s=config.time_step_s,
        residual_relative_tolerance=config.residual_relative_tolerance,
        samples=samples,
        terminal_story_material_states=terminal_states,
    )
    manifest = result.to_manifest()
    validate_nonlinear_mdof_result_ir_manifest(manifest)
    return manifest


def _predecessor(source_commit: str) -> tuple[F3StageGateReceipt, str, dict[str, Any]]:
    current = MDOF.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_mdof_linear_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt.from_dict(stage)
    persisted = json.loads((ROOT / PREDECESSOR_RECEIPT).read_text(encoding="utf-8"))
    return (
        receipt,
        LINEAR._sha_payload(current["stage_gate"]),
        {
            "source_receipt_path": PREDECESSOR_RECEIPT.as_posix(),
            "source_receipt_sha256": LINEAR._file_sha(PREDECESSOR_RECEIPT),
            "persisted_source_commit_sha": persisted["source_commit_sha"],
            "current_source_replay_executed": True,
            "replayed_source_commit_sha": source_commit,
            "vertical_stage_contract_passed": receipt.vertical_stage_contract_passed,
            "public_product_promotion_passed": receipt.public_product_promotion_passed,
        },
    )


def _elastic_parity(
    system: NonlinearShearBuilding, config: Any, forces: np.ndarray
) -> dict[str, Any]:
    elastic_stories = tuple(
        BilinearStory(
            row.story_id,
            row.elastic_stiffness_kn_per_m,
            1.0e12,
            row.post_yield_stiffness_ratio,
        )
        for row in system.stories
    )
    nonlinear_elastic = NonlinearShearBuilding(
        system.mass_matrix_kn_s2_per_m,
        system.damping_matrix_kn_s_per_m,
        elastic_stories,
        system.dof_ids,
        "elastic-limit-nonlinear",
    )
    nonlinear_solution = solve_nonlinear_mdof_transient(
        nonlinear_elastic, forces, config=config
    )
    stiffness = (
        system.drift_matrix.T
        @ np.diag([row.elastic_stiffness_kn_per_m for row in system.stories])
        @ system.drift_matrix
    )
    linear = LinearMDOFSystem(
        np.asarray(system.mass_matrix_kn_s2_per_m) * 1000.0,
        np.asarray(system.damping_matrix_kn_s_per_m) * 1000.0,
        stiffness * 1000.0,
        system.dof_ids,
        "elastic-limit-linear",
    )
    linear_solution = solve_linear_mdof_transient(
        linear, forces * 1000.0, config=LinearMDOFTransientConfig(config.time_step_s)
    )
    nonlinear_u = np.asarray([row.displacement_m for row in nonlinear_solution.steps])
    linear_u = np.asarray([row.displacement_m for row in linear_solution.steps])
    return {
        "benchmark_id": "nonlinear-mdof-elastic-limit-linear-matrix-parity.v1",
        "maximum_absolute_displacement_difference_m": float(
            np.max(np.abs(nonlinear_u - linear_u))
        ),
        "tolerance_m": 2.0e-14,
        "yielded_step_count": nonlinear_solution.yielded_step_count,
    }


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    document, system, config, forces = _inputs()
    solution = solve_nonlinear_mdof_transient(system, forces, config=config)
    split = 6
    prefix = solve_nonlinear_mdof_transient(system, forces[:split], config=config)
    resumed = resume_nonlinear_mdof_transient(
        system,
        prefix.checkpoints[-1],
        forces[split:],
        config=config,
        checkpoint_chain=prefix.checkpoints,
        force_history_prefix_kn=forces[:split],
    )
    exact_restart = (
        *prefix.checkpoints,
        *resumed.checkpoints[1:],
    ) == solution.checkpoints
    authority = validate_nonlinear_mdof_checkpoint_authority(
        solution.checkpoints[-1],
        system=system,
        config=config,
        checkpoint_chain=solution.checkpoints,
        force_history_prefix_kn=forces,
    )
    repeated = solve_nonlinear_mdof_transient(system, forces, config=config)
    deterministic = repeated.result_hash == solution.result_hash
    manifest = _result(document, system, config, forces, solution, authority)
    parity = _elastic_parity(system, config, forces)
    accepted = prefix.checkpoints[-1]
    rollback_exact = False
    trial_failure_observed = False
    try:
        import structural_analysis.solvers.nonlinear.mdof_transient as solver_module

        failing = NonlinearMDOFTransientConfig(0.01, 1e-14, 1e-14, 1)
        solver_module._advance(system, failing, accepted, np.asarray([[200.0, -150.0]]))
    except NonlinearMDOFTransientError:
        trial_failure_observed = True
        rollback_exact = accepted == prefix.checkpoints[-1]
    displacement = np.asarray([row.displacement_m for row in solution.steps])
    histories = [
        EXPLORER.evaluate_time_history(
            result_type=f"nonlinear_mdof_displacement_m:{dof}",
            time_steps=tuple(row.time_s for row in solution.steps),
            values=tuple(float(value) for value in displacement[:, index]),
        )
        for index, dof in enumerate(system.dof_ids)
    ]
    terminal_states = solution.checkpoints[-1].material_states
    all_pass = bool(
        document.analysis_ready
        and solution.contract_pass
        and solution.yielded_step_count > 0
        and sum(row.plastic_dissipation_kn_m for row in terminal_states) > 0.0
        and exact_restart
        and deterministic
        and authority.source_authenticated_checkpoint
        and authority.material_state_replay_pass
        and trial_failure_observed
        and rollback_exact
        and solution.material_trial_commit_rollback
        and not solution.fallback_used
        and not solution.regularization_used
        and solution.maximum_relative_residual <= config.residual_relative_tolerance
        and parity["maximum_absolute_displacement_difference_m"]
        <= parity["tolerance_m"]
        and parity["yielded_step_count"] == 0
    )
    surfaces: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash,
            "model_id": document.model_id,
            "capability_profile": document.capability_profile,
            "analysis_ready": document.analysis_ready,
            "story_count": len(system.stories),
            "force_history_source_sha256": document.to_dict()["dynamics"][
                "force_history_sha256"
            ],
        },
        "solver": {
            "schema_version": solution.schema_version,
            "profile": solution.profile,
            "solver_id": SOLVER_ID,
            "step_count": len(solution.steps),
            "total_newton_iterations": solution.total_newton_iterations,
            "yielded_step_count": solution.yielded_step_count,
            "maximum_relative_residual": solution.maximum_relative_residual,
            "material_trial_commit_rollback": solution.material_trial_commit_rollback,
            "fallback_used": solution.fallback_used,
            "regularization_used": solution.regularization_used,
        },
        "result_ir": {
            "schema_version": manifest["schema_version"],
            "manifest": manifest,
            "manifest_valid": True,
        },
        "recovery": {
            "maximum_absolute_displacement_by_dof_m": dict(
                zip(
                    system.dof_ids,
                    np.max(np.abs(displacement), axis=0).tolist(),
                    strict=True,
                )
            ),
            "terminal_story_material_states": manifest[
                "terminal_story_material_states"
            ],
            "plastic_dissipation_j": sum(
                row.plastic_dissipation_kn_m for row in terminal_states
            )
            * 1000.0,
        },
        "checkpoint": {
            "terminal_checkpoint": solution.checkpoints[-1].to_dict(),
            "source_authority_receipt": authority.to_dict(),
            "exact_restart": exact_restart,
            "forced_failure_trial_observed": trial_failure_observed,
            "forced_failure_rollback_exact": rollback_exact,
        },
        "workbench": {
            "schema_version": "f3-nonlinear-mdof-workbench-payload.v1",
            "time_history_cards": [row.__dict__ for row in histories],
            "summary": EXPLORER.build_results_summary(time_histories=tuple(histories)),
        },
        "benchmark": {**parity, "deterministic_repeat": deterministic},
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "independent-linear-matrix-elastic-limit-parity.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "maximum_absolute_displacement_difference_m": parity[
                "maximum_absolute_displacement_difference_m"
            ],
            "signature_verifier_waived": True,
        },
    }
    evidence = [
        F3Evidence(
            surface=name,
            status="verified" if all_pass else "blocked",
            artifact_sha256=LINEAR._sha_payload(value),
        )
        for name, value in surfaces.items()
    ]
    predecessor, predecessor_hash, replay = _predecessor(source_commit)
    gate = evaluate_f3_stage_gate(
        stage="nonlinear_mdof",
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
        "schema_version": "f3-nonlinear-mdof-vertical-evidence.v1",
        "source_commit_sha": source_commit,
        "source_input_checksums": {
            path.as_posix(): LINEAR._file_sha(path) for path in SOURCE_PATHS
        },
        "status": gate.status,
        "contract_pass": gate.vertical_stage_contract_passed,
        "predecessor_replay": replay,
        "stage_gate": gate.to_dict(),
        "surface_artifacts": surfaces,
        "claim_boundary": "Closes a bounded force-driven two-story nonlinear MDOF Newmark/Newton stage with immutable bilinear trial/commit/rollback, authoritative response and material-state ResultIR, source-authenticated exact restart, Workbench histories, and elastic-limit matrix parity. Shell and contact remain outside.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if args.check:
        if not out.is_file():
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=recorded["source_commit_sha"])
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if (
            recorded.get("source_input_checksums") != payload["source_input_checksums"]
            or out.read_text(encoding="utf-8") != text
        ):
            print("f3_nonlinear_mdof_vertical_evidence_mismatch")
            return 1
        print("f3_nonlinear_mdof_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    solver = payload["surface_artifacts"]["solver"]
    print(
        f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | yielded_steps={solver['yielded_step_count']}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
