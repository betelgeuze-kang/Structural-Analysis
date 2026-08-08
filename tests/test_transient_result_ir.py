from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.engine_v2.contracts.transient_result import (
    TransientResultIRError,
    create_transient_result_ir,
    validate_transient_result_ir,
    validate_transient_result_ir_manifest,
)


HASH = "sha256:" + "1" * 64


def _sample(index: int) -> dict[str, object]:
    return {
        "step_index": index,
        "time_s": 0.01 * index,
        "applied_force_n": 100.0 * index,
        "displacement_m": 0.001 * index,
        "velocity_m_per_s": 0.01 * index,
        "acceleration_m_per_s2": 0.1 * index,
        "restoring_force_n": 100.0 * index,
        "equilibrium_residual_n": 0.0,
        "relative_residual": 0.0,
        "kinetic_energy_j": float(index),
        "stored_energy_j": float(index),
        "external_work_j": float(index),
        "damping_dissipation_j": float(index),
        "plastic_dissipation_j": float(index),
        "yielded": index > 0,
        "newton_iterations": index,
    }


def _result():
    return create_transient_result_ir(
        result_id="f3.sdof.transient",
        model_ir_content_hash=HASH,
        force_history_hash=HASH,
        solver_id="newmark.sdof.v1",
        solver_result_hash=HASH,
        integration_contract_hash=HASH,
        terminal_checkpoint_hash=HASH,
        checkpoint_authority_receipt_hash=HASH,
        time_step_s=0.01,
        residual_relative_tolerance=1.0e-8,
        samples=[_sample(0), _sample(1)],
        terminal_material_state={
            "plastic_displacement_m": 0.001,
            "backstress_n": 2.0,
            "cumulative_plastic_displacement_m": 0.001,
            "plastic_dissipation_j": 1.0,
        },
    )


def test_transient_result_ir_is_authoritative_and_source_authenticated() -> None:
    result = _result()
    manifest = result.to_manifest()

    assert validate_transient_result_ir(result) is result
    assert validate_transient_result_ir_manifest(manifest)
    assert manifest["authority"]["response_history"] == "authoritative"
    assert manifest["checkpoint"]["authority"] == "source_authenticated_checkpoint"


def test_transient_result_ir_rejects_hash_and_time_mutations() -> None:
    result = _result()
    with pytest.raises(TransientResultIRError, match="result_hash_mismatch"):
        validate_transient_result_ir(replace(result, result_hash="sha256:" + "2" * 64))
    bad_sample = replace(result.samples[1], time_s=0.02)
    with pytest.raises(TransientResultIRError, match="time_index_mismatch"):
        validate_transient_result_ir(replace(result, samples=(result.samples[0], bad_sample)))
