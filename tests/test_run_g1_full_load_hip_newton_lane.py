from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "run_g1_full_load_hip_newton_lane.py"
)
SPEC = importlib.util.spec_from_file_location("run_g1_full_load_hip_newton_lane", SCRIPT_PATH)
assert SPEC is not None
run_g1_full_load_hip_newton_lane = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = run_g1_full_load_hip_newton_lane
SPEC.loader.exec_module(run_g1_full_load_hip_newton_lane)


def _hip_component(
    *,
    backend: str,
    attempted: bool = True,
    promoted_to_final_state: bool = True,
    require_hip_krylov_solver: bool = False,
    hip_krylov_solver_used: bool = False,
    accepted_state_refresh_hip_used: bool = True,
    accepted_state_refresh_cpu_used: bool = False,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "attempted": attempted,
        "promoted_to_final_state": promoted_to_final_state,
        "batch_replay_backend": backend,
        "require_hip_batch_replay": True,
        "require_hip_krylov_solver": require_hip_krylov_solver,
        "hip_krylov_solver_used": hip_krylov_solver_used,
        "accepted_state_refresh_backend": backend,
        "accepted_state_refresh_hip_used": accepted_state_refresh_hip_used,
        "accepted_state_refresh_cpu_used": accepted_state_refresh_cpu_used,
    }


def _checkpoint(
    path: Path,
    *,
    load_scale: float,
    frontier_load_scale: float | None = None,
    failed_bracket_load_scales: list[float] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "checkpoint_schema": np.asarray("mgt-direct-residual-newton-state.v1"),
        "load_scale": np.asarray(load_scale, dtype=np.float64),
        "displacement_u": np.zeros(12, dtype=np.float64),
    }
    if frontier_load_scale is not None:
        payload["frontier_load_scale"] = np.asarray(
            float(frontier_load_scale), dtype=np.float64
        )
    if failed_bracket_load_scales is not None:
        payload["failed_bracket_load_scales"] = np.asarray(
            [float(value) for value in failed_bracket_load_scales],
            dtype=np.float64,
        )
    np.savez_compressed(path, **payload)
    return path


def test_sub_full_load_checkpoint_blocks_before_execution(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.656)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["reused_evidence"] is False
    assert payload["checkpoint"]["load_scale"] == 0.656
    assert payload["full_load_input_pass"] is False
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]
    assert "checkpoint_resolution_no_full_load_candidate" in payload["blockers"]
    checkpoint_resolution_gate = payload["checkpoint_resolution_gate"]
    assert checkpoint_resolution_gate["mode"] == "explicit"
    assert checkpoint_resolution_gate["passed"] is False
    assert checkpoint_resolution_gate["full_load_candidate_count"] == 0
    assert checkpoint_resolution_gate["selected_checkpoint_load_scale"] == 0.656
    assert (
        checkpoint_resolution_gate["highest_observed_gap_to_required_load_scale"]
        == 1.0 - 0.656
    )
    partition = payload["blocker_partition"]
    assert partition["checkpoint_resolution"]["ready"] is False
    assert partition["checkpoint_resolution"]["highest_observed_load_scale"] == 0.656
    assert partition["checkpoint_resolution"]["full_load_candidate_count"] == 0
    assert (
        "checkpoint_resolution_no_full_load_candidate"
        in partition["checkpoint_resolution"]["blockers"]
    )
    next_actions = {row["id"]: row for row in payload["lane_next_actions"]}
    full_load_action_id = (
        "build_consistent_newton_full_load_checkpoint_candidate_runner"
    )
    assert full_load_action_id in next_actions
    assert (
        next_actions[full_load_action_id][
            "highest_observed_gap_to_required_load_scale"
        ]
        == 1.0 - 0.656
    )
    assert (
        next_actions[full_load_action_id]["rerun_command"]
        == "python3 scripts/run_g1_full_load_hip_newton_lane.py "
        "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
    )
    assert next_actions[full_load_action_id]["reason"] == (
        "row_only_largest_rows_operator_exhausted"
    )
    terminal = payload["terminal_requirement_breakdown"]
    assert (
        terminal["schema_version"]
        == "g1-full-load-hip-newton-terminal-requirement-breakdown.v1"
    )
    assert terminal["requirement_count"] == 4
    assert terminal["active_terminal_requirement_id"] == "full_load_checkpoint_1p0"
    requirements = {row["id"]: row for row in terminal["requirements"]}
    assert requirements["full_load_checkpoint_1p0"]["ready"] is False
    assert (
        "checkpoint_resolution_no_full_load_candidate"
        in requirements["full_load_checkpoint_1p0"]["blockers"]
    )
    child_requirement = requirements["full_load_child_direct_probe"]
    assert child_requirement["status"] == "deferred_upstream_blocked"
    assert (
        "full_load_checkpoint_1p0"
        in child_requirement["upstream_blocking_requirement_ids"]
    )
    assert payload["child_gate_evidence"]["ready"] is False
    assert payload["child_gate_evidence"]["material_newton_breadth_passed"] is False
    assert (
        "child_material_newton_breadth_not_proven"
        in payload["child_gate_evidence"]["blockers"]
    )
    assert payload["child_exit_code"] is None


def test_frontier_non_promoting_context_is_attached_without_promotion(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.656)
    frontier_status = tmp_path / "mgt_g1_frontier_status.json"
    frontier_status.write_text(
        json.dumps(
            {
                "schema_version": "mgt-g1-shell-material-budgeted-continuation-status.v1",
                "status": "partial",
                "contract_pass": False,
                "latest_frontier_receipt": "followup398.json",
                "latest_frontier_direct_residual_inf_n": 5.74426714604332,
                "direct_residual_gate_tolerance_n": 0.0005,
                "frontier_chain": [{"receipt": "followup398.json"}],
                "non_promoting_launch_receipts": [
                    {
                        "receipt": "followup390_launch.json",
                        "status": "in_progress",
                        "counted_in_frontier": False,
                        "non_count_reason": (
                            "completed child direct-residual receipt required"
                        ),
                    }
                ],
                "blockers": [
                    "full_mesh_nonlinear_equilibrium_not_closed",
                    "production_rocm_hip_residual_row_backend_not_closed",
                ],
                "claim_boundary": {
                    "launch_only_receipts_do_not_claim_descent": True,
                },
            }
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(frontier_status,),
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    context = payload["frontier_non_promoting_evidence"]
    assert context["present"] is True
    assert context["source_path"] == str(frontier_status)
    assert context["evidence_role"] == "non_promoting_partial_frontier_context"
    assert context["promotes_g1_closure"] is False
    assert context["promotes_lane_status"] is False
    assert context["frontier_chain_count"] == 1
    assert context["non_promoting_launch_receipt_count"] == 1
    assert context["latest_frontier_direct_residual_inf_n"] == 5.74426714604332
    assert context["direct_residual_gate_tolerance_n"] == 0.0005
    assert context["frontier_residual_above_tolerance"] is True
    assert context["non_promoting_launch_receipts"][0]["counted_in_frontier"] is False
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]


def test_row_only_frontier_exhaustion_routes_full_load_candidate_to_newton_runner(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.656)
    frontier_status = tmp_path / "mgt_g1_frontier_status.json"
    frontier_status.write_text(
        json.dumps(
            {
                "schema_version": (
                    "mgt-g1-shell-material-budgeted-continuation-status.v1"
                ),
                "status": "partial",
                "contract_pass": False,
                "latest_frontier_receipt": "followup431.json",
                "latest_frontier_compact_checkpoint": "followup431_checkpoint.npz",
                "latest_frontier_direct_residual_inf_n": 1.3092276661494922,
                "direct_residual_gate_tolerance_n": 0.0005,
                "frontier_chain": [{"receipt": "followup431.json"}],
                "non_promoting_launch_receipts": [],
                "same_operator_exhausted_at_latest_checkpoint": True,
                "latest_frontier_operator_stop_reason": "no_residual_descent",
                "latest_frontier_operator_target_row_count": 128,
                "latest_frontier_operator_support_column_count": 8,
                "next_actions": [
                    "do not spend another slice on largest-rows support/Jacobian retuning",
                    (
                        "replace row-only correction with a consistent residual/"
                        "Jacobian Newton path"
                    ),
                ],
                "blockers": ["full_mesh_nonlinear_equilibrium_not_closed"],
            }
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(frontier_status,),
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    context = payload["frontier_non_promoting_evidence"]
    assert context["same_operator_exhausted_at_latest_checkpoint"] is True
    assert context["latest_frontier_operator_stop_reason"] == "no_residual_descent"
    next_actions = {row["id"]: row for row in payload["lane_next_actions"]}
    assert "generate_full_load_1p0_checkpoint_candidate" not in next_actions
    routed = next_actions["build_consistent_newton_full_load_checkpoint_candidate_runner"]
    assert routed["reason"] == "row_only_largest_rows_operator_exhausted"
    assert (
        routed["preferred_candidate_generator"]
        == "consistent_residual_jacobian_newton_rocm_full_load_candidate"
    )
    assert routed["row_only_largest_rows_exhausted_at_latest_checkpoint"] is True
    assert routed["suppressed_retry_action_ids"] == [
        "repeat_largest_rows_target128_support8_row_only_retuning"
    ]
    requirements = {
        row["id"]: row
        for row in payload["terminal_requirement_breakdown"]["requirements"]
    }
    checkpoint_requirement = requirements["full_load_checkpoint_1p0"]
    assert checkpoint_requirement["next_action_ids"] == [
        "build_consistent_newton_full_load_checkpoint_candidate_runner"
    ]
    assert (
        checkpoint_requirement["observed"][
            "row_only_largest_rows_exhausted_at_latest_checkpoint"
        ]
        is True
    )


def test_full_load_dry_run_builds_hip_required_direct_probe_command(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
        hip_consistency_proof_json=proof,
    )

    command = payload["command"]
    assert exit_code == 0, payload["blockers"]
    assert payload["status"] == "ready_to_run"
    assert payload["contract_pass"] is False
    assert payload["full_load_input_pass"] is True
    checkpoint_resolution_gate = payload["checkpoint_resolution_gate"]
    assert checkpoint_resolution_gate["mode"] == "explicit"
    assert checkpoint_resolution_gate["passed"] is True
    assert checkpoint_resolution_gate["full_load_candidate_count"] == 1
    assert checkpoint_resolution_gate["selected_checkpoint_load_scale"] == 1.0
    assert "--matrix-free-global-krylov-require-hip-batch-replay" in command
    assert "--current-tangent-residual-row-require-hip-batch-replay" in command
    assert "--allow-state-dependent-shell-material-tangent-hip-replay" in command
    assert "hip_full_residual_resident" in command
    assert "hip_full_residual" in command
    assert "child_material_newton_breadth_passed" in payload["child_safety_requirements"]
    assert (
        "external_hip_consistency_proof_gate_passed"
        in payload["child_safety_requirements"]
    )
    assert (
        "child_hip_required_accepted_residual_refresh_proven"
        in payload["child_safety_requirements"]
    )
    next_action_ids = [row["id"] for row in payload["lane_next_actions"]]
    assert "run_full_load_child_direct_probe_with_hip_refresh" in next_action_ids
    assert (
        "generate_full_load_1p0_checkpoint_candidate"
        not in next_action_ids
    )
    assert "material Newton breadth" in payload["claim_boundary"]
    assert "separate HIP-required residual/Jacobian" in payload["claim_boundary"]


def test_child_probe_result_must_report_full_load_and_fallback_zero(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        lane_source_commit = run_g1_full_load_hip_newton_lane._git_head()
        child.write_text(
            json.dumps(
                {
                    "schema_version": "mgt-direct-residual-newton-probe.v1",
                    "source_commit_sha": lane_source_commit,
                    "reused_evidence": False,
                    "direct_residual_newton_ready": True,
                    "matrix_free_global_krylov": _hip_component(
                        backend="hip_full_residual_resident",
                        require_hip_krylov_solver=True,
                        hip_krylov_solver_used=True,
                    ),
                    "current_tangent_residual_row_correction": _hip_component(
                        backend="hip_full_residual",
                    ),
                    "residual_contract": {
                        "hip_residual_engine_contract_passed": True,
                        "consistent_residual_jacobian_newton_gate_passed": True,
                    },
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_passed": True,
                        "full_load_closure_passed": True,
                        "fallback_zero_passed": True,
                        "material_newton_breadth_passed": True,
                        "consistent_residual_jacobian_newton_passed": True,
                        "full_load_closure_gate": {
                            "observed_load_scale": 1.0,
                            "required_load_scale": 1.0,
                        },
                        "cpu_acceptance_refresh_closure_blocked": False,
                    },
                    "blockers": [],
                }
            ),
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 0, payload["blockers"]
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["child_exit_code"] == 0
    assert payload["child_gate_evidence"]["ready"] is True
    assert payload["child_gate_evidence"]["direct_residual_gate_passed"] is True
    assert payload["child_gate_evidence"]["relative_increment_gate_passed"] is True
    assert payload["child_gate_evidence"]["load_scale_passed"] is True
    assert payload["child_hip_residual_refresh_evidence"]["ready"] is True
    child_components = payload["child_hip_residual_refresh_evidence"]["components"]
    assert child_components["matrix_free_global_krylov"]["ready"] is True
    assert (
        child_components["current_tangent_residual_row_correction"]["ready"]
        is True
    )
    assert payload["hip_consistency_proof"]["cpu_diagnostic_assembler_used"] is False
    assert payload["hip_consistency_proof"]["production_hip_residual_jacobian_path"] is True
    assert payload["blockers"] == []
    terminal = payload["terminal_requirement_breakdown"]
    assert terminal["ready_requirement_count"] == 4
    assert terminal["blocked_requirement_ids"] == []
    assert terminal["active_terminal_requirement_id"] is None
    requirements = {row["id"]: row for row in terminal["requirements"]}
    assert requirements["full_load_checkpoint_1p0"]["ready"] is True
    assert (
        requirements["hip_consistent_residual_jacobian_newton_proof"]["ready"]
        is True
    )
    assert requirements["production_rocm_hip_residual_jvp_worker"]["ready"] is True
    assert requirements["full_load_child_direct_probe"]["ready"] is True


def test_missing_hip_consistency_proof_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        raise AssertionError("child probe must not run without HIP proof")

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=tmp_path / "missing-proof.json",
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "hip_consistency_proof_receipt_missing_or_unreadable" in payload["blockers"]
    assert payload["hip_consistency_proof"]["present"] is False
    assert payload["child_exit_code"] is None
    assert not child.exists()


def test_partial_hip_consistency_proof_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        raise AssertionError("child probe must not run while HIP proof is blocked")

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
        gate_passed=False,
        blockers=["rocm_hip_runtime_unavailable"],
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "hip_consistency_proof_gate_not_passed" in payload["blockers"]
    assert "hip_consistency_proof_has_blockers" in payload["blockers"]
    partition = payload["blocker_partition"]
    assert partition["checkpoint_resolution"]["ready"] is True
    assert partition["hip_consistency_proof"]["ready"] is False
    assert partition["production_rocm_hip_residual_jvp_worker"]["ready"] is False
    next_actions = {row["id"]: row for row in payload["lane_next_actions"]}
    assert "close_consistent_residual_jacobian_newton_gate" in next_actions
    assert (
        next_actions["close_consistent_residual_jacobian_newton_gate"][
            "worker_id"
        ]
        == "consistent_residual_jacobian_newton_rocm_worker"
    )
    assert payload["child_exit_code"] is None
    assert not child.exists()


def test_cause_narrowing_context_routes_consistent_newton_rocm_action(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    proof = tmp_path / "hip-proof.json"
    cause_status = tmp_path / "cause-narrowing.json"

    def fake_run(command: list[str], *, check: bool) -> Any:
        raise AssertionError("child probe must not run while HIP proof is blocked")

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
        gate_passed=False,
        blockers=["consistent_residual_jacobian_newton_not_proven"],
    )
    cause_status.write_text(
        json.dumps(
            {
                "schema_version": "g1-f2g-f2h-cause-narrowing-status.v1",
                "status": "ready",
                "source_commit_sha": run_g1_full_load_hip_newton_lane._git_head(),
                "summary_line": (
                    "G1 F2g/F2h cause narrowing: READY | next="
                    "consistent_residual_jacobian_newton_rocm_worker"
                ),
                "blockers": [],
                "evidence_signals": {
                    "support_or_link_row_gap_disfavored": True,
                    "row_only_correction_loop_stopped_by_global_connectivity": True,
                    "global_connectivity_primary_next_lane": (
                        "consistent_residual_jacobian_newton_rocm_worker"
                    ),
                    "global_connectivity_required_next_receipts": [
                        "implementation/phase1/release_evidence/productization/"
                        "mgt_residual_jacobian_consistency_hip_required_probe.json"
                    ],
                },
                "decision_record": {
                    "schema_version": "g1-f2g-f2h-next-lane-decision.v1",
                    "stop_row_only_support_or_elastic_link_correction_loop": True,
                    "primary_next_lane": (
                        "consistent_residual_jacobian_newton_rocm_worker"
                    ),
                    "required_next_receipts": [
                        "implementation/phase1/release_evidence/productization/"
                        "mgt_residual_jacobian_consistency_hip_required_probe.json"
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=False,
        hip_consistency_proof_json=proof,
        cause_narrowing_status_path=cause_status,
    )

    assert exit_code == 1
    context = payload["f2g_f2h_cause_narrowing_context"]
    assert context["present"] is True
    assert context["ready"] is True
    assert context["support_or_link_row_gap_disfavored"] is True
    assert context["row_only_correction_loop_stopped"] is True
    assert (
        context["primary_next_lane"]
        == "consistent_residual_jacobian_newton_rocm_worker"
    )
    assert context["consistent_newton_rocm_lane_prioritized"] is True
    next_actions = {row["id"]: row for row in payload["lane_next_actions"]}
    close_action = next_actions["close_consistent_residual_jacobian_newton_gate"]
    assert (
        close_action["cause_narrowing_primary_next_lane"]
        == "consistent_residual_jacobian_newton_rocm_worker"
    )
    assert close_action["cause_narrowing_support_or_link_row_gap_disfavored"] is True
    assert close_action["cause_narrowing_row_only_correction_loop_stopped"] is True


def test_cpu_diagnostic_hip_consistency_proof_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        raise AssertionError("child probe must not run with CPU diagnostic HIP proof")

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
        gate_passed=True,
        cpu_diagnostic_assembler_used=True,
        production_hip_residual_jacobian_path=False,
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "hip_consistency_proof_cpu_diagnostic_assembler_not_explicitly_false"
        in payload["blockers"]
    )
    assert (
        "hip_consistency_proof_production_hip_path_not_proven"
        in payload["blockers"]
    )
    assert payload["child_exit_code"] is None
    assert not child.exists()


def test_missing_hip_worker_contract_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        raise AssertionError("child probe must not run without worker contract")

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    proof.write_text(
        json.dumps(
            {
                "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
                "source_commit_sha": run_g1_full_load_hip_newton_lane._git_head(),
                "reused_evidence": False,
                "rocm_hip_required": True,
                "execution_mode": "hip_required_direct_probe_no_cpu_fallback",
                "cpu_diagnostic_assembler_used": False,
                "production_hip_residual_jacobian_path": True,
                "consistent_residual_jacobian_newton_gate_passed": True,
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "hip_consistency_proof_worker_contract_missing" in payload["blockers"]
    assert payload["hip_consistency_proof"]["production_rocm_hip_residual_jvp_worker"] == {
        "present": False,
        "ready": False,
        "status": None,
        "worker_id": None,
        "blockers": [],
        "residual_jvp_worker_path_ready": None,
        "residual_jvp_worker_path_blockers": [],
        "g1_closure_gate_ready": None,
        "g1_closure_gate_blockers": [],
    }
    assert payload["child_exit_code"] is None
    assert not child.exists()


def test_hip_runtime_blockers_propagate_to_lane_blockers_and_summary(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        raise AssertionError("child probe must not run with HIP runtime blockers")

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
        gate_passed=False,
        blockers=["rocm_hip_runtime_unavailable"],
        runtime_blockers=["dev_kfd_missing", "dev_dri_missing"],
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    proof_summary = payload["hip_consistency_proof"]
    assert proof_summary["runtime_blockers"] == ["dev_kfd_missing", "dev_dri_missing"]
    assert "hip_consistency_proof_runtime::dev_kfd_missing" in payload["blockers"]
    assert "hip_consistency_proof_runtime::dev_dri_missing" in payload["blockers"]
    assert "hip_consistency_proof_gate_not_passed" in payload["blockers"]
    assert "hip_consistency_proof_has_blockers" in payload["blockers"]
    assert payload["child_exit_code"] is None
    assert not child.exists()


def test_blocked_hip_proof_skips_subprocess_invocation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )
    _write_hip_consistency_proof(
        proof,
        source_commit_sha="stale-proof-commit",
    )

    def fail_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "subprocess.run must not be invoked while the HIP proof is blocked"
        )

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fail_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["child_exit_code"] is None
    assert "hip_consistency_proof_source_commit_sha_mismatch" in payload["blockers"]
    assert payload["hip_consistency_proof"]["present"] is True
    assert payload["hip_consistency_proof"]["source_commit_sha"] == "stale-proof-commit"
    assert payload["full_load_input_pass"] is True
    assert payload["load_path_provenance_pass"] is True
    assert not child.exists()


def test_blocked_hip_proof_dry_run_reports_blocked_not_ready_to_run(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
        gate_passed=False,
        blockers=["rocm_hip_runtime_unavailable"],
    )

    def fail_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "subprocess.run must not be invoked while the HIP proof is blocked"
        )

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fail_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["child_exit_code"] is None
    assert payload["status"] != "ready_to_run"
    assert "hip_consistency_proof_gate_not_passed" in payload["blockers"]
    assert "hip_consistency_proof_has_blockers" in payload["blockers"]
    assert payload["full_load_input_pass"] is True
    assert payload["load_path_provenance_pass"] is True


def test_blocked_hip_proof_runtime_blocker_blocks_before_dry_run_returns_ready(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
        gate_passed=False,
        blockers=["rocm_hip_runtime_unavailable"],
        runtime_blockers=["dev_kfd_missing"],
    )

    def fail_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "subprocess.run must not be invoked while HIP runtime blockers remain"
        )

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fail_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "hip_consistency_proof_runtime::dev_kfd_missing" in payload["blockers"]
    assert payload["hip_consistency_proof"]["runtime_blockers"] == ["dev_kfd_missing"]


def _write_acceptance_child(
    child: Path,
    *,
    source_commit_sha: str,
    reused_evidence: bool,
    hip_engine_passed: bool,
    observed_load_scale: float,
    fallback_zero_passed: bool = True,
    direct_residual_newton_ready: bool = True,
    direct_residual_gate_passed: bool = True,
    relative_increment_gate_passed: bool = True,
    full_load_closure_passed: bool = True,
    material_newton_breadth_passed: bool = True,
    consistent_residual_jacobian_newton_passed: bool = True,
    cpu_acceptance_refresh_closure_blocked: bool = False,
    include_hip_components: bool = True,
    global_refresh_backend: str = "hip_full_residual_resident",
    row_refresh_backend: str = "hip_full_residual",
    global_refresh_hip_used: bool = True,
    row_refresh_hip_used: bool = True,
    global_refresh_cpu_used: bool = False,
    row_refresh_cpu_used: bool = False,
    global_promoted: bool = True,
    row_promoted: bool = True,
    residual_contract_consistent_passed: bool | None = None,
    residual_contract_material_passed: bool | None = None,
    residual_contract_state_dependent_material_passed: bool | None = None,
) -> None:
    consistent_contract_passed = (
        consistent_residual_jacobian_newton_passed
        if residual_contract_consistent_passed is None
        else residual_contract_consistent_passed
    )
    payload: dict[str, Any] = {
        "schema_version": "mgt-direct-residual-newton-probe.v1",
        "source_commit_sha": source_commit_sha,
        "reused_evidence": reused_evidence,
        "direct_residual_newton_ready": direct_residual_newton_ready,
        "residual_contract": {
            "hip_residual_engine_contract_passed": hip_engine_passed,
            "consistent_residual_jacobian_newton_gate_passed": (
                consistent_contract_passed
            ),
        },
        "gate_assessment": {
            "direct_residual_gate_passed": direct_residual_gate_passed,
            "relative_increment_gate_passed": relative_increment_gate_passed,
            "full_load_closure_passed": full_load_closure_passed,
            "fallback_zero_passed": fallback_zero_passed,
            "material_newton_breadth_passed": material_newton_breadth_passed,
            "consistent_residual_jacobian_newton_passed": (
                consistent_residual_jacobian_newton_passed
            ),
            "full_load_closure_gate": {
                "observed_load_scale": observed_load_scale,
                "required_load_scale": 1.0,
            },
            "cpu_acceptance_refresh_closure_blocked": (
                cpu_acceptance_refresh_closure_blocked
            ),
        },
        "blockers": [],
    }
    if residual_contract_material_passed is not None:
        payload["residual_contract"]["material_newton_gate_passed"] = (
            residual_contract_material_passed
        )
    if residual_contract_state_dependent_material_passed is not None:
        payload["residual_contract"][
            "state_dependent_material_newton_closure_passed"
        ] = residual_contract_state_dependent_material_passed
    if include_hip_components:
        payload["matrix_free_global_krylov"] = _hip_component(
            backend=global_refresh_backend,
            promoted_to_final_state=global_promoted,
            require_hip_krylov_solver=True,
            hip_krylov_solver_used=True,
            accepted_state_refresh_hip_used=global_refresh_hip_used,
            accepted_state_refresh_cpu_used=global_refresh_cpu_used,
        )
        payload["current_tangent_residual_row_correction"] = _hip_component(
            backend=row_refresh_backend,
            promoted_to_final_state=row_promoted,
            accepted_state_refresh_hip_used=row_refresh_hip_used,
            accepted_state_refresh_cpu_used=row_refresh_cpu_used,
        )
    child.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _write_hip_consistency_proof(
    proof: Path,
    *,
    source_commit_sha: str,
    reused_evidence: bool = False,
    rocm_hip_required: bool = True,
    gate_passed: bool = True,
    cpu_diagnostic_assembler_used: bool = False,
    production_hip_residual_jacobian_path: bool = True,
    blockers: list[str] | None = None,
    runtime_blockers: list[str] | None = None,
    worker_contract: dict[str, Any] | None = None,
) -> None:
    worker_ready = bool(
        gate_passed
        and production_hip_residual_jacobian_path
        and not cpu_diagnostic_assembler_used
        and not blockers
        and not runtime_blockers
    )
    default_worker_contract = {
        "schema_version": "production-rocm-hip-residual-jvp-worker-contract.v1",
        "worker_id": "consistent_residual_jacobian_newton_rocm_worker",
        "ready": worker_ready,
        "status": "ready" if worker_ready else "blocked",
        "blockers": [] if worker_ready else ["fixture_worker_not_ready"],
        "residual_jvp_worker_path_ready": worker_ready,
        "residual_jvp_worker_path_blockers": (
            [] if worker_ready else ["fixture_worker_not_ready"]
        ),
        "g1_closure_gate_ready": worker_ready,
        "g1_closure_gate_blockers": (
            [] if worker_ready else ["fixture_worker_not_ready"]
        ),
        "required_for_g1_closure": True,
        "promotes_g1_closure": False,
        "cpu_fallback_allowed": False,
    }
    payload: dict[str, Any] = {
        "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
        "source_commit_sha": source_commit_sha,
        "reused_evidence": reused_evidence,
        "rocm_hip_required": rocm_hip_required,
        "execution_mode": (
            "hip_required_production_residual_jacobian"
            if production_hip_residual_jacobian_path
            else "hip_required_runtime_unavailable_no_cpu_fallback"
        ),
        "cpu_diagnostic_assembler_used": cpu_diagnostic_assembler_used,
        "production_hip_residual_jacobian_path": production_hip_residual_jacobian_path,
        "consistent_residual_jacobian_newton_gate_passed": gate_passed,
        "production_rocm_hip_residual_jvp_worker": (
            worker_contract if worker_contract is not None else default_worker_contract
        ),
        "blockers": blockers or [],
    }
    if runtime_blockers is not None:
        payload["rocm_hip_runtime_preflight"] = {
            "runtime_blockers": runtime_blockers,
        }
    proof.write_text(json.dumps(payload), encoding="utf-8")


def test_hip_proof_receipt_only_source_commit_is_fresh(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha="proof-commit",
        gate_passed=False,
        blockers=["consistent_residual_jacobian_newton_not_proven"],
    )
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_rev_parse",
        lambda ref: {"proof-commit": "proof-sha", "lane-commit": "lane-sha"}.get(ref, ""),
    )
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_diff_name_only",
        lambda base, head: [
            "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
            "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
        ],
    )

    summary, blockers = run_g1_full_load_hip_newton_lane._hip_consistency_proof_assessment(
        proof_json=proof,
        lane_source_commit_sha="lane-commit",
    )

    assert "hip_consistency_proof_source_commit_sha_mismatch" not in blockers
    assert "hip_consistency_proof_gate_not_passed" in blockers
    assert "hip_consistency_proof_has_blockers" in blockers
    assert summary["source_state_fresh"] is True
    assert summary["source_state_kind"] == "receipt_only_commit"
    assert summary["changed_paths_since_source_commit"] == [
        "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
        "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
    ]


def test_hip_proof_partitions_worker_path_from_g1_closure_gate(
    tmp_path: Path,
) -> None:
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
        gate_passed=False,
        blockers=["consistent_residual_jacobian_newton_not_proven"],
        worker_contract={
            "schema_version": "production-rocm-hip-residual-jvp-worker-contract.v1",
            "worker_id": "consistent_residual_jacobian_newton_rocm_worker",
            "ready": False,
            "status": "blocked",
            "blockers": ["consistent_residual_jacobian_newton_gate_not_passed"],
            "residual_jvp_worker_path_ready": True,
            "residual_jvp_worker_path_blockers": [],
            "g1_closure_gate_ready": False,
            "g1_closure_gate_blockers": [
                "consistent_residual_jacobian_newton_gate_not_passed"
            ],
            "required_for_g1_closure": True,
            "promotes_g1_closure": False,
            "cpu_fallback_allowed": False,
            "terminal_gate_partition": {
                "schema_version": (
                    "production-rocm-hip-worker-terminal-gate-partition.v1"
                ),
                "worker_path": {"ready": True, "blockers": []},
                "g1_closure_gate": {
                    "ready": False,
                    "blockers": [
                        "consistent_residual_jacobian_newton_gate_not_passed"
                    ],
                    "consistent_residual_jacobian_newton_gate_passed": False,
                },
                "checkpoint_gate": {
                    "full_load_required": True,
                    "load_scale": 0.656,
                    "full_load_candidate": False,
                    "gap_to_full_load": 0.344,
                    "full_load_closure_passed": False,
                },
                "direct_residual_gate": {
                    "passed": False,
                    "relative_increment_gate_passed": True,
                    "material_newton_breadth_passed": False,
                    "fallback_zero_passed": True,
                },
                "next_action": {
                    "id": "generate_full_load_1p0_checkpoint_candidate",
                    "blockers": [
                        "full_load_checkpoint_candidate_missing",
                        "full_load_closure_gate_not_passed",
                    ],
                },
            },
        },
    )

    summary, blockers = run_g1_full_load_hip_newton_lane._hip_consistency_proof_assessment(
        proof_json=proof,
        lane_source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    worker = summary["production_rocm_hip_residual_jvp_worker"]
    assert worker["residual_jvp_worker_path_ready"] is True
    assert worker["g1_closure_gate_ready"] is False
    assert (
        worker["terminal_gate_partition"]["next_action"]["id"]
        == "generate_full_load_1p0_checkpoint_candidate"
    )
    assert "hip_consistency_proof_worker_g1_closure_gate_not_ready" in blockers
    assert (
        "hip_consistency_proof_production_rocm_hip_residual_jvp_worker_not_ready"
        not in blockers
    )

    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.656)
    child = tmp_path / "child.json"
    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )
    assert exit_code == 1
    partition = payload["blocker_partition"][
        "production_rocm_hip_residual_jvp_worker"
    ]["terminal_gate_partition"]
    assert partition["checkpoint_gate"]["full_load_candidate"] is False
    requirements = {
        row["id"]: row
        for row in payload["terminal_requirement_breakdown"]["requirements"]
    }
    assert requirements["production_rocm_hip_residual_jvp_worker"][
        "next_action_ids"
    ] == ["build_consistent_newton_full_load_checkpoint_candidate_runner"]


def test_hip_proof_non_receipt_source_commit_still_blocks(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(proof, source_commit_sha="proof-commit")
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_rev_parse",
        lambda ref: {"proof-commit": "proof-sha", "lane-commit": "lane-sha"}.get(ref, ""),
    )
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_diff_name_only",
        lambda base, head: [
            "implementation/phase1/run_mgt_direct_residual_newton_probe.py",
        ],
    )

    summary, blockers = run_g1_full_load_hip_newton_lane._hip_consistency_proof_assessment(
        proof_json=proof,
        lane_source_commit_sha="lane-commit",
    )

    assert "hip_consistency_proof_source_commit_sha_mismatch" in blockers
    assert summary["source_state_fresh"] is False
    assert summary["source_state_kind"] == "g1_hip_paths_changed"
    assert summary["changed_paths_since_source_commit"] == [
        "implementation/phase1/run_mgt_direct_residual_newton_probe.py",
    ]


def test_hip_proof_unrelated_release_helpers_do_not_stale_g1_lane(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha="proof-commit",
        gate_passed=False,
        blockers=["consistent_residual_jacobian_newton_not_proven"],
    )
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_rev_parse",
        lambda ref: {"proof-commit": "proof-sha", "lane-commit": "lane-sha"}.get(ref, ""),
    )
    changed_paths = [
        "scripts/build_ux_new_user_observation_report.py",
        "scripts/build_license_status_intake_packet.py",
        "tests/test_build_phase6_ux_observation_status.py",
    ]
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_diff_name_only",
        lambda base, head: changed_paths,
    )

    summary, blockers = run_g1_full_load_hip_newton_lane._hip_consistency_proof_assessment(
        proof_json=proof,
        lane_source_commit_sha="lane-commit",
    )

    assert "hip_consistency_proof_source_commit_sha_mismatch" not in blockers
    assert "hip_consistency_proof_gate_not_passed" in blockers
    assert "hip_consistency_proof_has_blockers" in blockers
    assert summary["source_state_fresh"] is True
    assert summary["source_state_kind"] == "non_g1_hip_paths_changed"
    assert summary["changed_paths_since_source_commit"] == changed_paths


def test_hip_proof_g1_status_builders_do_not_stale_numeric_proof(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha="proof-commit",
        gate_passed=False,
        blockers=["consistent_residual_jacobian_newton_not_proven"],
    )
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_rev_parse",
        lambda ref: {"proof-commit": "proof-sha", "lane-commit": "lane-sha"}.get(ref, ""),
    )
    changed_paths = [
        "scripts/build_g1_f2g_f2h_cause_narrowing_status.py",
        "scripts/build_g1_global_connectivity_load_path_audit.py",
        "scripts/build_g1_support_elastic_link_reconciliation_audit.py",
    ]
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_diff_name_only",
        lambda base, head: changed_paths,
    )

    summary, blockers = run_g1_full_load_hip_newton_lane._hip_consistency_proof_assessment(
        proof_json=proof,
        lane_source_commit_sha="lane-commit",
    )

    assert "hip_consistency_proof_source_commit_sha_mismatch" not in blockers
    assert summary["source_state_fresh"] is True
    assert summary["source_state_kind"] == "non_g1_hip_paths_changed"
    assert summary["changed_paths_since_source_commit"] == changed_paths


def test_hip_proof_lane_wrapper_change_does_not_stale_proof_source(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(proof, source_commit_sha="proof-commit")
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_rev_parse",
        lambda ref: {"proof-commit": "proof-sha", "lane-commit": "lane-sha"}.get(ref, ""),
    )
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_diff_name_only",
        lambda base, head: [
            "scripts/run_g1_full_load_hip_newton_lane.py",
            "tests/test_run_g1_full_load_hip_newton_lane.py",
        ],
    )

    summary, blockers = run_g1_full_load_hip_newton_lane._hip_consistency_proof_assessment(
        proof_json=proof,
        lane_source_commit_sha="lane-commit",
    )

    assert "hip_consistency_proof_source_commit_sha_mismatch" not in blockers
    assert summary["source_state_fresh"] is True
    assert summary["source_state_kind"] == "non_g1_hip_paths_changed"
    assert summary["changed_paths_since_source_commit"] == [
        "scripts/run_g1_full_load_hip_newton_lane.py",
        "tests/test_run_g1_full_load_hip_newton_lane.py",
    ]


def test_hip_proof_benchmark_acquisition_change_does_not_stale_g1_lane(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(proof, source_commit_sha="proof-commit")
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_rev_parse",
        lambda ref: {"proof-commit": "proof-sha", "lane-commit": "lane-sha"}.get(ref, ""),
    )
    changed_paths = ["src/structural_analysis/benchmark/acquisition.py"]
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane,
        "_git_diff_name_only",
        lambda base, head: changed_paths,
    )

    summary, blockers = run_g1_full_load_hip_newton_lane._hip_consistency_proof_assessment(
        proof_json=proof,
        lane_source_commit_sha="lane-commit",
    )

    assert "hip_consistency_proof_source_commit_sha_mismatch" not in blockers
    assert summary["source_state_fresh"] is True
    assert summary["source_state_kind"] == "non_g1_hip_paths_changed"
    assert summary["changed_paths_since_source_commit"] == changed_paths


def test_child_reused_evidence_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=True,
            hip_engine_passed=True,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_reused_evidence_not_false" in payload["blockers"]


def test_child_source_commit_mismatch_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha="lane-head-commit",
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha="stale-child-commit",
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_source_commit_sha_mismatch" in payload["blockers"]


def test_child_missing_source_commit_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha="",
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_source_commit_sha_missing" in payload["blockers"]


def test_child_observed_load_scale_below_required_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=0.656,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_observed_load_scale_below_required_full_load" in payload["blockers"]


def test_child_invalid_observed_load_scale_blocks_without_crashing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale="not-a-number",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_observed_load_scale_below_required_full_load" in payload["blockers"]


def test_child_hip_residual_engine_contract_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=False,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_hip_residual_engine_contract_not_proven" in payload["blockers"]


def test_child_direct_residual_gate_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            direct_residual_gate_passed=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_direct_residual_gate_not_proven" in payload["blockers"]
    assert payload["child_gate_evidence"]["ready"] is False
    assert (
        "child_direct_residual_gate_not_proven"
        in payload["child_gate_evidence"]["blockers"]
    )


def test_child_relative_increment_gate_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            relative_increment_gate_passed=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_relative_increment_gate_not_proven" in payload["blockers"]
    assert payload["child_gate_evidence"]["ready"] is False
    assert (
        "child_relative_increment_gate_not_proven"
        in payload["child_gate_evidence"]["blockers"]
    )


def test_child_cpu_acceptance_refresh_blocked_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            cpu_acceptance_refresh_closure_blocked=True,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_cpu_acceptance_refresh_closure_blocked" in payload["blockers"]


def test_child_missing_hip_refresh_components_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            include_hip_components=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_global_krylov_component_missing" in payload["blockers"]
    )
    assert (
        "child_current_tangent_residual_row_component_missing"
        in payload["blockers"]
    )


def test_child_unpromoted_secondary_hip_component_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            row_promoted=False,
            row_refresh_backend="",
            row_refresh_hip_used=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_current_tangent_residual_row_not_promoted_to_final_state"
        in payload["blockers"]
    )
    assert (
        "child_current_tangent_residual_row_hip_residual_refresh_not_proven"
        in payload["blockers"]
    )
    evidence = payload["child_hip_residual_refresh_evidence"]
    assert evidence["ready"] is False
    assert (
        "child_current_tangent_residual_row_not_promoted_to_final_state"
        in evidence["blockers"]
    )
    assert (
        evidence["components"]["current_tangent_residual_row_correction"][
            "ready"
        ]
        is False
    )


def test_child_non_hip_residual_refresh_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            global_refresh_backend="cpu_full_assembly",
            global_refresh_hip_used=False,
            row_refresh_backend="cpu_full_assembly",
            row_refresh_hip_used=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_global_krylov_hip_residual_refresh_not_proven" in payload["blockers"]
    assert (
        "child_current_tangent_residual_row_hip_residual_refresh_not_proven"
        in payload["blockers"]
    )


def test_child_fallback_zero_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            fallback_zero_passed=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_fallback_zero_not_proven" in payload["blockers"]


def test_child_material_newton_breadth_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            material_newton_breadth_passed=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_material_newton_breadth_not_proven" in payload["blockers"]


def test_child_material_contract_cannot_override_gate_blocker(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            material_newton_breadth_passed=False,
            residual_contract_material_passed=True,
            residual_contract_state_dependent_material_passed=True,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_material_newton_breadth_not_proven" in payload["blockers"]
    assert "child_material_newton_contract_gate_conflict" in payload["blockers"]
    assert (
        "child_material_newton_contract_gate_conflict"
        in payload["child_gate_evidence"]["blockers"]
    )


def test_child_consistent_residual_jacobian_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            consistent_residual_jacobian_newton_passed=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_consistent_residual_jacobian_newton_not_proven"
        in payload["blockers"]
    )


def test_child_consistent_jacobian_contract_cannot_override_gate_blocker(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            consistent_residual_jacobian_newton_passed=False,
            residual_contract_consistent_passed=True,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_consistent_residual_jacobian_newton_not_proven"
        in payload["blockers"]
    )
    assert (
        "child_consistent_residual_jacobian_contract_gate_conflict"
        in payload["blockers"]
    )
    assert (
        "child_consistent_residual_jacobian_contract_gate_conflict"
        in payload["child_gate_evidence"]["blockers"]
    )


def test_child_diagnostic_jacobian_inclusion_does_not_prove_consistency(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            consistent_residual_jacobian_newton_passed=False,
        )
        payload = json.loads(child.read_text(encoding="utf-8"))
        payload["residual_contract"][
            "matrix_free_consistent_jacobian_subspace_included"
        ] = True
        payload["residual_contract"][
            "finite_difference_residual_row_jacobian_included"
        ] = True
        child.write_text(json.dumps(payload), encoding="utf-8")
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert (
        "child_consistent_residual_jacobian_newton_not_proven"
        in payload["blockers"]
    )


def test_child_residual_jacobian_ready_hint_does_not_prove_consistency(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            consistent_residual_jacobian_newton_passed=False,
        )
        payload = json.loads(child.read_text(encoding="utf-8"))
        payload["gate_assessment"]["residual_jacobian_consistency_ready"] = True
        child.write_text(json.dumps(payload), encoding="utf-8")
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_consistent_residual_jacobian_newton_not_proven"
        in payload["blockers"]
    )


def test_child_fallback_zero_boundaries_with_passed_flag_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        lane_source_commit = run_g1_full_load_hip_newton_lane._git_head()
        child.write_text(
            json.dumps(
                {
                    "schema_version": "mgt-direct-residual-newton-probe.v1",
                    "source_commit_sha": lane_source_commit,
                    "reused_evidence": False,
                    "direct_residual_newton_ready": True,
                    "residual_contract": {
                        "hip_residual_engine_contract_passed": True,
                        "consistent_residual_jacobian_newton_gate_passed": True,
                    },
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_passed": True,
                        "full_load_closure_passed": True,
                        "fallback_zero_passed": True,
                        "fallback_zero_audit": {
                            "fallback_zero_passed": False,
                            "fallback_zero_boundary_count": 1,
                            "fallback_zero_boundaries": [
                                {
                                    "boundary": (
                                        "global_krylov_host_gmres_used_with_hip_required"
                                    ),
                                    "path": "matrix_free_global_krylov",
                                }
                            ],
                        },
                        "material_newton_breadth_passed": True,
                        "consistent_residual_jacobian_newton_passed": True,
                        "full_load_closure_gate": {
                            "observed_load_scale": 1.0,
                            "required_load_scale": 1.0,
                        },
                        "cpu_acceptance_refresh_closure_blocked": False,
                    },
                    "blockers": [],
                }
            ),
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_fallback_zero_boundaries_present_with_passed_flag"
        in payload["blockers"]
    )
    assert "child_fallback_zero_gate_audit_mismatch" in payload["blockers"]


def test_child_fallback_zero_boundary_count_mismatch_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        lane_source_commit = run_g1_full_load_hip_newton_lane._git_head()
        child.write_text(
            json.dumps(
                {
                    "schema_version": "mgt-direct-residual-newton-probe.v1",
                    "source_commit_sha": lane_source_commit,
                    "reused_evidence": False,
                    "direct_residual_newton_ready": True,
                    "residual_contract": {
                        "hip_residual_engine_contract_passed": True,
                        "consistent_residual_jacobian_newton_gate_passed": True,
                    },
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_passed": True,
                        "full_load_closure_passed": True,
                        "fallback_zero_passed": True,
                        "fallback_zero_audit": {
                            "fallback_zero_passed": True,
                            "fallback_zero_boundary_count": 0,
                            "fallback_zero_boundaries": [
                                {
                                    "boundary": (
                                        "global_krylov_host_gmres_used_with_hip_required"
                                    ),
                                    "path": "matrix_free_global_krylov",
                                }
                            ],
                        },
                        "material_newton_breadth_passed": True,
                        "consistent_residual_jacobian_newton_passed": True,
                        "full_load_closure_gate": {
                            "observed_load_scale": 1.0,
                            "required_load_scale": 1.0,
                        },
                        "cpu_acceptance_refresh_closure_blocked": False,
                    },
                    "blockers": [],
                }
            ),
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_fallback_zero_boundary_count_mismatch" in payload["blockers"]
    )
    assert (
        "child_fallback_zero_boundaries_present_with_passed_flag"
        in payload["blockers"]
    )


def test_child_material_newton_breadth_blockers_with_passed_flag_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        lane_source_commit = run_g1_full_load_hip_newton_lane._git_head()
        child.write_text(
            json.dumps(
                {
                    "schema_version": "mgt-direct-residual-newton-probe.v1",
                    "source_commit_sha": lane_source_commit,
                    "reused_evidence": False,
                    "direct_residual_newton_ready": True,
                    "residual_contract": {
                        "hip_residual_engine_contract_passed": True,
                        "consistent_residual_jacobian_newton_gate_passed": True,
                    },
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_passed": True,
                        "full_load_closure_passed": True,
                        "fallback_zero_passed": True,
                        "fallback_zero_audit": {
                            "fallback_zero_passed": True,
                            "fallback_zero_boundary_count": 0,
                            "fallback_zero_boundaries": [],
                        },
                        "material_newton_breadth_passed": True,
                        "material_newton_breadth_blockers": [
                            "material_newton_breadth_not_proven",
                        ],
                        "consistent_residual_jacobian_newton_passed": True,
                        "full_load_closure_gate": {
                            "observed_load_scale": 1.0,
                            "required_load_scale": 1.0,
                        },
                        "cpu_acceptance_refresh_closure_blocked": False,
                    },
                    "blockers": [],
                }
            ),
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_material_newton_breadth_blockers_present_with_passed_flag"
        in payload["blockers"]
    )


def test_child_consistent_residual_jacobian_blockers_with_passed_flag_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"
    proof = tmp_path / "hip-proof.json"

    class Result:
        returncode = 0

    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        lane_source_commit = run_g1_full_load_hip_newton_lane._git_head()
        child.write_text(
            json.dumps(
                {
                    "schema_version": "mgt-direct-residual-newton-probe.v1",
                    "source_commit_sha": lane_source_commit,
                    "reused_evidence": False,
                    "direct_residual_newton_ready": True,
                    "residual_contract": {
                        "hip_residual_engine_contract_passed": True,
                        "consistent_residual_jacobian_newton_gate_passed": True,
                    },
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_passed": True,
                        "full_load_closure_passed": True,
                        "fallback_zero_passed": True,
                        "fallback_zero_audit": {
                            "fallback_zero_passed": True,
                            "fallback_zero_boundary_count": 0,
                            "fallback_zero_boundaries": [],
                        },
                        "material_newton_breadth_passed": True,
                        "consistent_residual_jacobian_newton_passed": True,
                        "consistent_residual_jacobian_newton_blockers": [
                            "residual_jacobian_consistency_not_executed",
                        ],
                        "full_load_closure_gate": {
                            "observed_load_scale": 1.0,
                            "required_load_scale": 1.0,
                        },
                        "cpu_acceptance_refresh_closure_blocked": False,
                    },
                    "blockers": [],
                }
            ),
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_consistent_residual_jacobian_newton_blockers_present_with_passed_flag"
        in payload["blockers"]
    )


def test_cli_writes_blocked_receipt_and_fails_when_requested(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.75)
    out = tmp_path / "lane.json"

    exit_code = run_g1_full_load_hip_newton_lane.main(
        [
            "--checkpoint-npz",
            str(checkpoint),
            "--out",
            str(out),
            "--skip-workspace-checkpoint-inventory",
            "--fail-blocked",
        ]
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]
    evidence = payload["child_hip_residual_refresh_evidence"]
    assert evidence["ready"] is False
    assert "child_global_krylov_component_missing" in evidence["blockers"]
    assert (
        "child_current_tangent_residual_row_component_missing"
        in evidence["blockers"]
    )
    assert evidence["components"]["matrix_free_global_krylov"]["present"] is False
    assert (
        evidence["components"]["current_tangent_residual_row_correction"][
            "present"
        ]
        is False
    )


def test_cli_dry_run_receipt_keeps_child_hip_evidence_contract(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    proof = tmp_path / "hip-proof.json"
    out = tmp_path / "lane.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    exit_code = run_g1_full_load_hip_newton_lane.main(
        [
            "--checkpoint-npz",
            str(checkpoint),
            "--hip-consistency-proof-json",
            str(proof),
            "--out",
            str(out),
            "--dry-run",
            "--skip-workspace-checkpoint-inventory",
        ]
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "ready_to_run"
    assert payload["contract_pass"] is False
    evidence = payload["child_hip_residual_refresh_evidence"]
    assert evidence["schema_version"] == "g1-child-hip-residual-refresh-evidence.v1"
    assert evidence["ready"] is False
    assert "child_global_krylov_component_missing" in evidence["blockers"]
    assert (
        "child_current_tangent_residual_row_component_missing"
        in evidence["blockers"]
    )


def test_cli_writes_workspace_checkpoint_inventory_by_default(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.75)
    workspace_root = tmp_path / "productization"
    _checkpoint(workspace_root / "frontier.npz", load_scale=0.656)
    _checkpoint(workspace_root / "higher_sub.npz", load_scale=0.82)
    out = tmp_path / "lane.json"

    exit_code = run_g1_full_load_hip_newton_lane.main(
        [
            "--checkpoint-npz",
            str(checkpoint),
            "--workspace-checkpoint-scan-root",
            str(workspace_root),
            "--out",
            str(out),
            "--fail-blocked",
        ]
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert exit_code == 1
    inventory = payload["workspace_checkpoint_inventory"]
    assert inventory["enabled"] is True
    assert inventory["candidate_count"] == 2
    assert inventory["loadable_count"] == 2
    assert inventory["full_load_candidate_count"] == 0
    assert inventory["highest_observed_load_scale"] == 0.82
    next_actions = {row["id"]: row for row in payload["lane_next_actions"]}
    assert (
        next_actions[
            "build_consistent_newton_full_load_checkpoint_candidate_runner"
        ][
            "workspace_highest_observed_load_scale"
        ]
        == 0.82
    )


def test_load_path_provenance_frontier_below_full_load_blocks_claimed_full_load(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(
        tmp_path / "state.npz",
        load_scale=1.0,
        frontier_load_scale=0.85,
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["full_load_input_pass"] is True
    assert payload["load_path_provenance_pass"] is False
    assert payload["checkpoint"]["frontier_load_scale"] == 0.85
    assert payload["checkpoint"]["load_path_provenance_present"] is True
    assert (
        "load_path_provenance_accepted_frontier_below_full_load"
        in payload["blockers"]
    )
    assert payload["child_exit_code"] is None


def test_load_path_provenance_failed_bracket_below_full_load_blocks_claimed_full_load(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(
        tmp_path / "state.npz",
        load_scale=1.0,
        failed_bracket_load_scales=[0.7, 0.92],
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["full_load_input_pass"] is True
    assert payload["load_path_provenance_pass"] is False
    assert payload["checkpoint"]["failed_bracket_load_scales"] == [0.7, 0.92]
    assert (
        "load_path_provenance_failed_bracket_below_full_load"
        in payload["blockers"]
    )
    assert payload["child_exit_code"] is None


def test_load_path_provenance_clean_history_passes_claimed_full_load(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(
        tmp_path / "state.npz",
        load_scale=1.0,
        frontier_load_scale=1.0,
        failed_bracket_load_scales=[],
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 0
    assert payload["status"] == "ready_to_run"
    assert payload["full_load_input_pass"] is True
    assert payload["load_path_provenance_pass"] is True
    assert payload["blockers"] == []


def test_load_path_provenance_absent_does_not_block_claimed_full_load(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 0
    assert payload["status"] == "ready_to_run"
    assert payload["full_load_input_pass"] is True
    assert payload["load_path_provenance_pass"] is True
    assert payload["checkpoint"]["load_path_provenance_present"] is False
    assert payload["blockers"] == []


def test_load_path_provenance_blocked_payload_omits_hip_consistency_when_unprovided(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(
        tmp_path / "state.npz",
        load_scale=1.0,
        frontier_load_scale=0.95,
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert (
        "load_path_provenance_accepted_frontier_below_full_load"
        in payload["blockers"]
    )
    assert "hip_consistency_proof_receipt_missing_or_unreadable" not in payload["blockers"]


def _write_evidence_source(
    source: Path,
    *,
    candidates: list[Path],
    prefix_keys: tuple[str, ...] = ("compact_checkpoint", "retained_checkpoint_npz"),
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "test-evidence-source.v1",
        "entries": [{key: str(path) for key in prefix_keys} for path in candidates],
    }
    flat: dict[str, Any] = {}
    for path in candidates:
        flat[f"entry_{path.stem}"] = {
            "compact_checkpoint": str(path),
            "retained_checkpoint_npz": {"path": str(path)},
        }
    payload.update(flat)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_auto_select_picks_full_load_candidate(tmp_path: Path) -> None:
    sub = _checkpoint(tmp_path / "sub.npz", load_scale=0.4)
    full = _checkpoint(tmp_path / "full.npz", load_scale=1.0)
    medium = _checkpoint(tmp_path / "medium.npz", load_scale=0.7)
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[sub, medium, full],
        prefix_keys=("compact_checkpoint",),
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=True,
        evidence_sources=(source,),
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 0
    assert payload["status"] == "ready_to_run"
    assert payload["full_load_input_pass"] is True
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "auto_select"
    assert resolution["selection"]["candidate_count"] == 3
    assert resolution["selection"]["loadable_count"] == 3
    assert resolution["selection"]["highest_observed_load_scale"] == 1.0
    assert resolution["selection"]["selected_checkpoint"]["path"] == str(full)
    assert resolution["selection"]["selection_reason"] == "full_load_candidate_selected"
    checkpoint_resolution_gate = payload["checkpoint_resolution_gate"]
    assert checkpoint_resolution_gate["mode"] == "auto_select"
    assert checkpoint_resolution_gate["passed"] is True
    assert checkpoint_resolution_gate["full_load_candidate_count"] == 1
    assert checkpoint_resolution_gate["highest_observed_load_scale"] == 1.0
    assert Path(payload["checkpoint"]["path"]) == full


def test_auto_select_blocks_full_load_checkpoint_with_sub_full_load_provenance(
    tmp_path: Path,
) -> None:
    full = _checkpoint(tmp_path / "full.npz", load_scale=1.0)
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "test-evidence-source.v1",
                "current_g1_frontier": {
                    "load_scale": 0.656,
                    "retained_checkpoint_npz": {"path": str(full)},
                },
            }
        ),
        encoding="utf-8",
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=True,
        evidence_sources=(source,),
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["full_load_input_pass"] is True
    assert payload["load_path_provenance_pass"] is False
    assert (
        "checkpoint_load_path_provenance_below_required_full_load"
        in payload["blockers"]
    )
    assert payload["load_path_provenance"]["context"]["load_scale"] == 0.656
    selected = payload["checkpoint_resolution"]["selection"]["selected_checkpoint"]
    assert selected["provenance_context"]["load_scale"] == 0.656


def test_auto_select_picks_highest_sub_full_load_candidate(tmp_path: Path) -> None:
    low = _checkpoint(tmp_path / "low.npz", load_scale=0.4)
    medium = _checkpoint(tmp_path / "medium.npz", load_scale=0.7)
    higher_sub = _checkpoint(tmp_path / "higher_sub.npz", load_scale=0.95)
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[low, medium, higher_sub],
        prefix_keys=("compact_checkpoint",),
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(source,),
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["full_load_input_pass"] is False
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]
    assert "checkpoint_resolution_no_full_load_candidate" in payload["blockers"]
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "auto_select"
    assert resolution["selection"]["highest_observed_load_scale"] == 0.95
    assert (
        resolution["selection"]["selected_checkpoint"]["path"] == str(higher_sub)
    )
    assert (
        resolution["selection"]["selection_reason"]
        == "highest_sub_full_load_candidate_selected"
    )
    assert payload["checkpoint"]["load_scale"] == 0.95
    checkpoint_resolution_gate = payload["checkpoint_resolution_gate"]
    assert checkpoint_resolution_gate["mode"] == "auto_select"
    assert checkpoint_resolution_gate["passed"] is False
    assert checkpoint_resolution_gate["full_load_candidate_count"] == 0
    assert checkpoint_resolution_gate["highest_observed_load_scale"] == 0.95
    assert (
        checkpoint_resolution_gate["highest_observed_gap_to_required_load_scale"]
        == 0.050000000000000044
    )


def test_workspace_checkpoint_inventory_reports_no_full_load_candidate(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "productization"
    frontier = _checkpoint(workspace_root / "frontier.npz", load_scale=0.656)
    higher_sub = _checkpoint(workspace_root / "higher_sub.npz", load_scale=0.8)
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=frontier,
        output_json=tmp_path / "child.json",
        dry_run=True,
        hip_consistency_proof_json=proof,
        workspace_checkpoint_scan_root=workspace_root,
    )

    assert exit_code == 1
    inventory = payload["workspace_checkpoint_inventory"]
    assert inventory["schema_version"] == "g1-workspace-checkpoint-inventory.v1"
    assert inventory["enabled"] is True
    assert inventory["scan_root"] == str(workspace_root)
    assert inventory["scan_root_exists"] is True
    assert inventory["candidate_count"] == 2
    assert inventory["loadable_count"] == 2
    assert inventory["full_load_candidate_count"] == 0
    assert inventory["highest_observed_load_scale"] == 0.8
    assert abs(inventory["highest_observed_gap_to_required_load_scale"] - 0.2) < 1e-12
    assert inventory["top_loadable_candidates"][0]["path"] == str(higher_sub)
    assert inventory["top_loadable_candidates"][0]["load_scale"] == 0.8
    next_actions = {row["id"]: row for row in payload["lane_next_actions"]}
    action = next_actions["build_consistent_newton_full_load_checkpoint_candidate_runner"]
    assert action["workspace_scan_root"] == str(workspace_root)
    assert action["workspace_candidate_count"] == 2
    assert action["workspace_full_load_candidate_count"] == 0
    assert action["workspace_highest_observed_load_scale"] == 0.8


def test_explicit_checkpoint_overrides_auto_selection(tmp_path: Path) -> None:
    explicit = _checkpoint(tmp_path / "explicit.npz", load_scale=0.656)
    full = _checkpoint(tmp_path / "full.npz", load_scale=1.0)
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[full],
        prefix_keys=("compact_checkpoint",),
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=explicit,
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(source,),
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "explicit"
    assert resolution["selection"] is None
    assert resolution["requested_path"] == str(explicit)
    assert Path(payload["checkpoint"]["path"]) == explicit
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]
    checkpoint_resolution_gate = payload["checkpoint_resolution_gate"]
    assert checkpoint_resolution_gate["mode"] == "explicit"
    assert checkpoint_resolution_gate["passed"] is False
    assert checkpoint_resolution_gate["full_load_candidate_count"] == 0


def test_auto_select_ignores_generic_npz_path_records(tmp_path: Path) -> None:
    generic = _checkpoint(tmp_path / "generic_deleted_candidate.npz", load_scale=1.0)
    frontier = _checkpoint(tmp_path / "frontier.npz", load_scale=0.8)
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "test-evidence-source.v1",
                "documented_deleted_checkpoint_candidates": [
                    {"path": str(generic)},
                ],
                "latest_frontier_compact_checkpoint": str(frontier),
            }
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(source,),
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    selection = payload["checkpoint_resolution"]["selection"]
    assert selection["candidate_count"] == 1
    assert selection["selected_checkpoint"]["path"] == str(frontier)
    assert selection["highest_observed_load_scale"] == 0.8
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]


def test_auto_select_with_no_loadable_candidates_blocks(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[],
        prefix_keys=("compact_checkpoint",),
    )
    proof = tmp_path / "hip-proof.json"
    _write_hip_consistency_proof(
        proof,
        source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=True,
        evidence_sources=(source,),
        hip_consistency_proof_json=proof,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert "auto_select_no_loadable_candidates" in payload["blockers"]
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "auto_select"
    assert resolution["selection"]["selection_reason"] == "no_loadable_candidates"
    assert resolution["selection"]["selected_checkpoint"] is None


def test_cli_auto_select_default_and_auto_arg_use_evidence_scan(tmp_path: Path) -> None:
    out = tmp_path / "lane.json"
    default_args = run_g1_full_load_hip_newton_lane.build_parser().parse_args(
        ["--dry-run", "--out", str(out)]
    )
    assert default_args.checkpoint_npz is None
    assert (
        default_args.workspace_checkpoint_scan_root
        == run_g1_full_load_hip_newton_lane.PRODUCTIZATION
    )
    assert default_args.skip_workspace_checkpoint_inventory is False

    args = run_g1_full_load_hip_newton_lane.build_parser().parse_args(
        [
            "--checkpoint-npz",
            "auto",
            "--dry-run",
            "--out",
            str(out),
            "--skip-workspace-checkpoint-inventory",
        ]
    )
    assert args.checkpoint_npz is None
    assert args.dry_run is True
    assert args.skip_workspace_checkpoint_inventory is True
