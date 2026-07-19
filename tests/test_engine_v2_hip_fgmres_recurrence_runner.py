from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (
    HIP_FGMRES_OUTPUT_VERSION,
    build_cpu_hip_fgmres_recurrence_reference,
    fgmres_recurrence_receipt_hash,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_engine_v2_hip_fgmres_recurrence.py"
SPEC = importlib.util.spec_from_file_location(
    "run_engine_v2_hip_fgmres_recurrence",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _compile_receipt() -> dict:
    return module.build_compile_receipt(
        repo_root=ROOT,
        architecture="gfx1030",
        compiler_path="/opt/rocm/bin/hipcc",
        compiler_version_output="HIP version: 6.0.32831\nclang 17.0.0\n",
        binary_sha256="sha256:" + "a" * 64,
    )


def _runtime_output() -> dict:
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
    return {
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


def test_receipt_records_local_recurrence_without_production_promotion() -> None:
    receipt = module.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm-6.0.2/bin/hipcc",
        compiler_version_output="HIP version: 6.0.32831\nclang 17.0.0\n",
        binary_sha256="sha256:" + "f" * 64,
    )

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["receipt_hash"] == fgmres_recurrence_receipt_hash(receipt)
    assert receipt["hardware_execution"]["actual_hardware"] is True
    assert receipt["hardware_execution"]["gcn_arch_name"] == "gfx1030"
    assert receipt["recurrence_comparison"]["contract_pass"] is True
    assert receipt["claims"][
        "gfx1030_local_device_resident_recurrence_parity"
    ] is True
    assert receipt["claims"][
        "gfx1030_local_parallel_reduction_recurrence_parity"
    ] is True
    assert receipt["claims"][
        "gfx1030_local_global_krylov_workspace_parity"
    ] is True
    assert receipt["claims"][
        "gfx1030_local_multi_block_recurrence_parity"
    ] is True
    assert receipt["claims"][
        "gfx1030_local_operator_derived_scaled_jacobi_recurrence_parity"
    ] is True
    assert receipt["claims"]["restart_terminal_history_parity"] is True
    assert receipt["claims"]["checkpoint_restart_artifact_parity"] is True
    assert receipt["claims"]["production_scalable_parallel_recurrence"] is False
    assert receipt["claims"]["production_preconditioner_parity"] is False
    assert receipt["claims"]["independent_gfx1100_parity"] is False
    assert receipt["claims"]["signed_receipt"] is False
    assert receipt["claims"]["performance"] is False
    assert "checkpoint_restart_binary_artifact_not_verified" not in (
        receipt["blockers_remaining"]
    )
    assert "scalable_parallel_reduction_recurrence_not_implemented" not in (
        receipt["blockers_remaining"]
    )
    assert "production_dimension_global_workspace_not_implemented" not in (
        receipt["blockers_remaining"]
    )
    assert "multi_block_production_spmv_reduction_not_implemented" not in (
        receipt["blockers_remaining"]
    )
    assert "production_scale_multi_block_operator_not_verified" in (
        receipt["blockers_remaining"]
    )
    assert "production_preconditioner_apply_not_verified" not in (
        receipt["blockers_remaining"]
    )
    assert "production_scale_preconditioner_effectiveness_not_verified" in (
        receipt["blockers_remaining"]
    )
    assert receipt["checkpoint"]["checkpoint_hash"] == (
        receipt["recurrence_comparison"]["checkpoint_resume"][
            "checkpoint_hash"
        ]
    )


def test_compile_receipt_is_source_bound_and_compile_only() -> None:
    receipt = _compile_receipt()

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["contract_scope"] == "target_compile_only"
    assert receipt["receipt_hash"] == fgmres_recurrence_receipt_hash(receipt)
    assert receipt["target_compile"]["compile_succeeded"] is True
    assert receipt["target_compile"]["architecture"] == "gfx1030"
    assert receipt["target_compile"]["operator_blocks_per_case"] == 4
    assert receipt["claims"]["declared_target_compile"] is True
    assert receipt["claims"]["gfx1030_target_compile"] is True
    assert receipt["claims"]["actual_hardware_execution"] is False
    assert receipt["claims"]["numerical_parity"] is False
    assert receipt["claims"]["checkpoint_resume_parity"] is False
    assert receipt["claims"]["production_recurrence"] is False
    assert receipt["claims"]["performance"] is False
    assert "actual_hardware_execution_not_performed" in (
        receipt["blockers_remaining"]
    )


def test_compile_receipt_validation_rejects_stale_hash() -> None:
    receipt = _compile_receipt()
    tampered = deepcopy(receipt)
    tampered["target_compile"]["binary_sha256"] = "sha256:" + "b" * 64

    with pytest.raises(ValueError, match="compile_receipt_hash_mismatch"):
        module.validate_compile_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_receipt_validation_rejects_stale_hash() -> None:
    receipt = module.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm-6.0.2/bin/hipcc",
        compiler_version_output="HIP version: 6.0.32831\n",
        binary_sha256="sha256:" + "f" * 64,
    )
    tampered = deepcopy(receipt)
    tampered["hardware_execution"]["runtime_output"]["cases"][0][
        "solution"
    ][0] += 1.0e-6

    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        module.validate_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_compile_receipt_validation_rejects_stale_sources() -> None:
    receipt = _compile_receipt()
    tampered = deepcopy(receipt)
    tampered["source"]["input_checksums"][module.MODULE_PATH.as_posix()] = (
        "sha256:" + "0" * 64
    )
    tampered["receipt_hash"] = fgmres_recurrence_receipt_hash(tampered)

    with pytest.raises(ValueError, match="compile_receipt_sources_stale"):
        module.validate_compile_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=True,
        )


def test_check_reports_missing_receipt(tmp_path: Path) -> None:
    ok, message = module.check_committed_receipt(
        repo_root=ROOT,
        out=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("engine_v2_cpu_hip_fgmres_receipt_missing:")


def test_compile_check_reports_missing_receipt(tmp_path: Path) -> None:
    ok, message = module.check_committed_compile_receipt(
        repo_root=ROOT,
        out=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("engine_v2_multiblock_compile_receipt_missing:")


def test_compile_only_cli_writes_separate_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _compile_receipt()
    out = tmp_path / "compile-receipt.json"

    def fake_run_compile_only(**kwargs: object) -> dict:
        assert kwargs["architecture"] == "gfx1030"
        return receipt

    monkeypatch.setattr(module, "run_compile_only", fake_run_compile_only)

    assert module.main(["--compile-only", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == receipt
    assert "compile_only=True | actual_hardware=False" in capsys.readouterr().out


def test_compile_only_cli_check_uses_compile_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "compile-receipt.json"
    out.write_text(module._json_text(_compile_receipt()), encoding="utf-8")

    assert module.main(["--compile-only", "--check", "--out", str(out)]) == 0
    assert "engine_v2_multiblock_compile_receipt_consistent" in (
        capsys.readouterr().out
    )


def test_committed_cpu_hip_fgmres_receipt_is_current() -> None:
    ok, message = module.check_committed_receipt(repo_root=ROOT)

    assert ok is True
    assert message == "engine_v2_cpu_hip_fgmres_receipt_consistent"


def test_committed_hip_fgmres_compile_receipt_is_current() -> None:
    ok, message = module.check_committed_compile_receipt(repo_root=ROOT)

    assert ok is True
    assert message == "engine_v2_multiblock_compile_receipt_consistent"
