from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.engine_v2.contracts.mdof_transient_result import (
    MDOFTransientResultIRError,
    create_mdof_transient_result_ir,
    validate_mdof_transient_result_ir,
    validate_mdof_transient_result_ir_manifest,
)


HASH = "sha256:" + "1" * 64


def _sample(index: int) -> dict[str, object]:
    vector = [float(index), -float(index)]
    zero = [0.0, 0.0]
    return {
        "step_index": index, "time_s": 0.01 * index,
        "applied_force_n": vector, "displacement_m": vector,
        "velocity_m_per_s": vector, "acceleration_m_per_s2": vector,
        "restoring_force_n": vector, "damping_force_n": zero,
        "inertia_force_n": zero, "equilibrium_residual_n": zero,
        "relative_residual": 0.0, "kinetic_energy_j": float(index),
        "strain_energy_j": float(index), "external_work_j": float(index),
        "damping_dissipation_j": 0.0, "energy_balance_error_j": 0.0,
        "linear_solve_count": min(index, 1),
    }


def _result():
    return create_mdof_transient_result_ir(
        result_id="f3.mdof.linear-transient", model_ir_content_hash=HASH,
        force_history_hash=HASH, solver_id="newmark.mdof.v1",
        solver_result_hash=HASH, integration_contract_hash=HASH,
        terminal_checkpoint_hash=HASH, checkpoint_authority_receipt_hash=HASH,
        dof_ids=("Floor1_UX", "Floor2_UX"), time_step_s=0.01,
        residual_relative_tolerance=1.0e-8, samples=(_sample(0), _sample(1)),
    )


def test_mdof_transient_result_ir_is_vector_authoritative() -> None:
    result = _result()
    manifest = result.to_manifest()
    assert validate_mdof_transient_result_ir(result) is result
    assert validate_mdof_transient_result_ir_manifest(manifest)
    assert manifest["analysis_type"] == "mdof_linear_transient"
    assert manifest["authority"]["response_history"] == "authoritative"
    assert len(manifest["history"][0]["displacement_m"]) == 2


def test_mdof_transient_result_ir_rejects_vector_dimension_and_hash_mutation() -> None:
    result = _result()
    bad = replace(result.samples[1], displacement_m=(1.0,))
    with pytest.raises(MDOFTransientResultIRError, match="history_vector_invalid"):
        validate_mdof_transient_result_ir(replace(result, samples=(result.samples[0], bad)))
    with pytest.raises(MDOFTransientResultIRError, match="result_hash_mismatch"):
        validate_mdof_transient_result_ir(replace(result, result_hash="sha256:" + "2" * 64))
