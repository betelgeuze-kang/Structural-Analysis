from __future__ import annotations

from copy import deepcopy

import pytest

from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (
    HIP_FGMRES_CASE_IDS,
    HIP_FGMRES_OUTPUT_VERSION,
    HIPFGMRESParityError,
    build_cpu_hip_fgmres_recurrence_reference,
    compare_hip_fgmres_recurrence_output,
)


def _runtime_output() -> tuple[object, dict]:
    reference = build_cpu_hip_fgmres_recurrence_reference()
    cases = []
    for config, run in zip(
        reference.fixture.cases,
        reference.cpu_runs,
        strict=True,
    ):
        cases.append(
            {
                "case_id": config.case_id,
                "runtime_status_code": 0,
                "terminal_reason": run.terminal_reason,
                "converged": run.converged,
                "iteration_count": run.iteration_count,
                "matvec_count": run.matvec_count,
                "restart_count": len(run.restart_history),
                "convergence_threshold_scaled_l2": (
                    run.convergence_threshold_scaled_l2
                ),
                "solution": [float(value) for value in run.solution_free],
                "scaled_l2_history": [
                    row.scaled_l2 for row in run.observations
                ],
                "scaled_linf_history": [
                    row.scaled_linf for row in run.observations
                ],
                "restart_history": [
                    {
                        "start_iteration": row.start_iteration,
                        "end_iteration": row.end_iteration,
                        "iteration_count": row.iteration_count,
                        "disposition": row.disposition,
                    }
                    for row in run.restart_history
                ],
            }
        )
    payload = {
        "schema_version": HIP_FGMRES_OUTPUT_VERSION,
        "runtime_status": "success",
        "runtime_status_code": 0,
        "backend": "amd_rocm_hip",
        "cpu_backend": False,
        "same_stream_ordering": True,
        "mid_recurrence_host_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
        "checkpoint_h2d_transfer_count": 1,
        "checkpoint_completed_iteration_replay_count": 0,
        "threads_per_case": 64,
        "kernel_invocation_count": 3710,
        "multi_block_kernel_invocation_count": 3710,
        "operator_blocks_per_case": 4,
        "recurrence_execution_profile": (
            "same_stream_fixed_kernel_sequence_device_guarded.v1"
        ),
        "device_resident_full_recurrence_probe": True,
        "production_recurrence_claim": False,
        "preconditioner_profile": (
            "operator_derived_left_scaled_jacobi_right.v1"
        ),
        "reduction_profile": "fixed_block_binary_tree_fp64_probe.v1",
        "krylov_workspace_profile": "device_global_dynamic_dimension_fp64.v1",
        "workspace_dimension": reference.fixture.dimension,
        "workspace_doubles_per_case": 71 * reference.fixture.dimension,
        "cooperative_launch_supported": False,
        "device_status_to_terminal_state": True,
        "device_index": 0,
        "device_name": "AMD Radeon RX 6900 XT",
        "gcn_arch_name": "gfx1030",
        "cases": cases,
        "checkpoint_hash": reference.checkpoint.checkpoint_hash,
        "checkpoint_artifact_data_hash": (
            reference.checkpoint.artifact_descriptor.data_hash
        ),
        "checkpoint_recurrence_contract_hash": (
            reference.checkpoint.recurrence_contract_hash
        ),
        "checkpoint_resume": _checkpoint_resume_output(reference),
    }
    return reference, payload


def _checkpoint_resume_output(reference) -> dict:
    checkpoint = reference.checkpoint
    run = reference.cpu_runs[1]
    return {
        "case_id": "restart_max_iterations",
        "runtime_status_code": 0,
        "artifact_loaded": True,
        "device_resident_suffix_recurrence": True,
        "completed_iteration_replay_count": 0,
        "resumed_from_iteration": checkpoint.iteration_count,
        "restart_index_base": checkpoint.next_restart_index,
        "terminal_reason": run.terminal_reason,
        "converged": run.converged,
        "iteration_count": run.iteration_count,
        "matvec_count": run.matvec_count,
        "suffix_restart_count": len(run.restart_history)
        - checkpoint.next_restart_index,
        "convergence_threshold_scaled_l2": (
            run.convergence_threshold_scaled_l2
        ),
        "solution": [float(value) for value in run.solution_free],
        "scaled_l2_suffix_history": [
            row.scaled_l2
            for row in run.observations[checkpoint.iteration_count :]
        ],
        "scaled_linf_suffix_history": [
            row.scaled_linf
            for row in run.observations[checkpoint.iteration_count :]
        ],
        "restart_suffix_history": [
            {
                "start_iteration": row.start_iteration,
                "end_iteration": row.end_iteration,
                "iteration_count": row.iteration_count,
                "disposition": row.disposition,
            }
            for row in run.restart_history[checkpoint.next_restart_index :]
        ],
    }


def test_recurrence_fixture_binds_two_cpu_terminal_paths() -> None:
    first = build_cpu_hip_fgmres_recurrence_reference()
    second = build_cpu_hip_fgmres_recurrence_reference()
    fixture = first.fixture

    assert fixture.fixture_hash == second.fixture.fixture_hash
    assert fixture.to_bytes().startswith(b"EV2FGR01")
    assert fixture.dimension == 66
    assert fixture.nnz == 4356
    assert tuple(case.case_id for case in fixture.cases) == HIP_FGMRES_CASE_IDS
    assert [run.terminal_reason for run in first.cpu_runs] == [
        "converged_scaled_residual",
        "max_iterations",
    ]
    assert [row.disposition for row in first.cpu_runs[1].restart_history] == [
        "restarted",
        "max_iterations",
    ]
    assert fixture.execution_plan_hash == first.cpu_runs[0].execution_plan_hash
    assert fixture.reduced_csr_identity_hash == (
        first.cpu_runs[0].reduced_csr_identity_hash
    )
    assert fixture.to_manifest()["preconditioner_contract_hash"] == (
        fixture.preconditioner_contract_hash
    )


def test_recurrence_output_matches_terminal_and_restart_semantics() -> None:
    reference, payload = _runtime_output()

    comparison = compare_hip_fgmres_recurrence_output(reference, payload)

    assert comparison["contract_pass"] is True
    assert comparison["terminal_semantics_exact"] is True
    assert comparison["restart_checkpoint_semantics_exact"] is True
    assert comparison["persisted_checkpoint_resume_semantics_exact"] is True
    assert comparison["parallel_reduction_recurrence_probe_claim"] is True
    assert comparison["device_global_krylov_workspace_probe_claim"] is True
    assert comparison["cooperative_launch_supported"] is False
    assert comparison["multi_block_recurrence_probe_claim"] is True
    assert comparison[
        "operator_derived_scaled_jacobi_recurrence_probe_claim"
    ] is True
    assert comparison["checkpoint_resume"]["hash_binding_exact"] is True
    assert comparison["checkpoint_resume"]["completed_iteration_replay_count"] == 0
    assert comparison["maximum_solution_absolute_error"] == 0.0
    assert comparison["maximum_observation_absolute_error"] == 0.0
    assert comparison["device_resident_full_recurrence_probe_claim"] is True
    assert comparison["production_recurrence_claim"] is False
    assert comparison["performance_claim"] is False


def test_recurrence_output_exposes_numerical_drift_without_boolean_forgery() -> None:
    reference, payload = _runtime_output()
    payload["cases"][0]["solution"][2] += 1.0e-5

    comparison = compare_hip_fgmres_recurrence_output(reference, payload)

    assert comparison["contract_pass"] is False
    assert comparison["case_rows"][0]["contract_pass"] is False
    assert comparison["case_rows"][1]["contract_pass"] is True


def test_recurrence_output_requires_exact_restart_dispositions() -> None:
    reference, payload = _runtime_output()
    payload["cases"][1]["restart_history"][0]["disposition"] = "converged"

    comparison = compare_hip_fgmres_recurrence_output(reference, payload)

    assert comparison["contract_pass"] is False
    assert comparison["restart_checkpoint_semantics_exact"] is False


@pytest.mark.parametrize(
    ("key", "value", "code"),
    [
        ("runtime_status", "error", "hip_fgmres_output_runtime_contract_invalid"),
        ("cpu_backend", True, "hip_fgmres_output_runtime_contract_invalid"),
        (
            "mid_recurrence_host_transfer_count",
            1,
            "hip_fgmres_output_runtime_contract_invalid",
        ),
        (
            "kernel_invocation_count",
            2,
            "hip_fgmres_output_kernel_count_invalid",
        ),
        (
            "threads_per_case",
            1,
            "hip_fgmres_output_runtime_contract_invalid",
        ),
        (
            "reduction_profile",
            "single_thread_ascending_index_fp64_probe.v1",
            "hip_fgmres_output_runtime_contract_invalid",
        ),
        (
            "krylov_workspace_profile",
            "shared_fixed_dimension_fp64.v1",
            "hip_fgmres_output_runtime_contract_invalid",
        ),
        (
            "workspace_dimension",
            32,
            "hip_fgmres_output_runtime_contract_invalid",
        ),
        (
            "cooperative_launch_supported",
            "unknown",
            "hip_fgmres_output_runtime_contract_invalid",
        ),
        ("gcn_arch_name", "cpu", "hip_fgmres_output_arch_invalid"),
    ],
)
def test_recurrence_output_fails_closed_on_runtime_contract_drift(
    key: str,
    value: object,
    code: str,
) -> None:
    reference, original = _runtime_output()
    payload = deepcopy(original)
    payload[key] = value

    with pytest.raises(HIPFGMRESParityError) as caught:
        compare_hip_fgmres_recurrence_output(reference, payload)

    assert caught.value.code == code
