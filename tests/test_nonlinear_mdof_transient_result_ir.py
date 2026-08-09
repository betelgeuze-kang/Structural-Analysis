from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.engine_v2.contracts.nonlinear_mdof_transient_result import (
    NonlinearMDOFResultIRError,
    create_nonlinear_mdof_result_ir,
    validate_nonlinear_mdof_result_ir,
)


HASH = "sha256:" + "1" * 64


def _sample(index: int) -> dict[str, object]:
    vector = [float(index), -float(index)]
    return {
        "step_index": index,
        "time_s": 0.01 * index,
        "applied_force_n": vector,
        "displacement_m": vector,
        "velocity_m_per_s": vector,
        "acceleration_m_per_s2": vector,
        "story_drift_m": vector,
        "story_force_n": vector,
        "equilibrium_residual_n": [0.0, 0.0],
        "relative_residual": 0.0,
        "newton_iterations": index,
        "yielded_story_count": index,
        "kinetic_energy_j": float(index),
        "stored_energy_j": float(index),
        "external_work_j": float(index),
        "damping_dissipation_j": 0.0,
        "plastic_dissipation_j": float(index),
        "energy_balance_error_j": 0.0,
    }


def _result():
    states = [
        {
            "story_id": story,
            "plastic_displacement_m": 0.001,
            "backstress_n": 1.0,
            "cumulative_plastic_displacement_m": 0.001,
            "plastic_dissipation_j": 1.0,
        }
        for story in ("Story1", "Story2")
    ]
    return create_nonlinear_mdof_result_ir(
        result_id="f3.nonlinear-mdof",
        model_ir_content_hash=HASH,
        force_history_hash=HASH,
        solver_id="newmark.nonlinear-mdof.v1",
        solver_result_hash=HASH,
        integration_contract_hash=HASH,
        terminal_checkpoint_hash=HASH,
        checkpoint_authority_receipt_hash=HASH,
        dof_ids=("Floor1_UX", "Floor2_UX"),
        story_ids=("Story1", "Story2"),
        time_step_s=0.01,
        residual_relative_tolerance=1.0e-8,
        samples=(_sample(0), _sample(1)),
        terminal_story_material_states=states,
    )


def test_nonlinear_mdof_result_ir_is_response_and_material_authoritative() -> None:
    result = _result()
    manifest = result.to_manifest()
    assert validate_nonlinear_mdof_result_ir(result) is result
    assert manifest["authority"]["response_history"] == "authoritative"
    assert manifest["authority"]["material_state"] == "authoritative"
    assert len(manifest["terminal_story_material_states"]) == 2


def test_nonlinear_mdof_result_ir_rejects_mutation() -> None:
    result = _result()
    bad = dict(result.samples[1])
    bad["displacement_m"] = [1.0]
    with pytest.raises(NonlinearMDOFResultIRError, match="history_vector_invalid"):
        validate_nonlinear_mdof_result_ir(
            replace(result, samples=(result.samples[0], bad))
        )
    with pytest.raises(NonlinearMDOFResultIRError, match="result_hash_mismatch"):
        validate_nonlinear_mdof_result_ir(
            replace(result, result_hash="sha256:" + "2" * 64)
        )
