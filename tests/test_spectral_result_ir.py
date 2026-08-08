from __future__ import annotations

from dataclasses import replace
import math

import pytest

from structural_analysis.engine_v2.contracts.spectral_result import (
    SpectralResultIRError,
    create_spectral_result_ir,
    validate_spectral_result_ir,
    validate_spectral_result_ir_manifest,
)


HASH = "sha256:" + "1" * 64
NODES = ("N1", "N2")


def _mode(*, analysis_type: str) -> dict[str, object]:
    frequency = 10.0 if analysis_type == "modal" else None
    load_factor = 3.0 if analysis_type == "linear_buckling" else None
    return {
        "mode_number": 1,
        "eigenvalue": (2.0 * math.pi * 10.0) ** 2 if frequency else 3.0,
        "frequency_hz": frequency,
        "load_factor": load_factor,
        "residual_relative_inf": 1.0e-12,
        "node_shapes": [[0.0] * 6, [0.0, 1.0, 0.0, 0.0, 0.5, 0.0]],
    }


@pytest.mark.parametrize("analysis_type", ["modal", "linear_buckling"])
def test_spectral_result_ir_is_authoritative_hash_bound_and_replayable(
    analysis_type: str,
) -> None:
    result = create_spectral_result_ir(
        result_id=f"f3.{analysis_type}",
        analysis_type=analysis_type,
        model_ir_content_hash=HASH,
        solver_id=f"cpu.{analysis_type}.v1",
        solver_receipt_hash=HASH,
        stiffness_matrix_hash=HASH,
        secondary_matrix_hash=HASH,
        free_dof_map_hash=HASH,
        node_ids=NODES,
        tolerance=1.0e-8,
        modes=[_mode(analysis_type=analysis_type)],
    )

    assert validate_spectral_result_ir(result) is result
    assert validate_spectral_result_ir_manifest(result.to_manifest())
    assert result.to_manifest()["authority"]["mode_shapes"] == "authoritative"
    assert result.to_manifest()["checkpoint"]["mode_count"] == 1


def test_spectral_result_ir_rejects_mutated_checkpoint_and_mode_shape() -> None:
    result = create_spectral_result_ir(
        result_id="f3.modal",
        analysis_type="modal",
        model_ir_content_hash=HASH,
        solver_id="cpu.modal.v1",
        solver_receipt_hash=HASH,
        stiffness_matrix_hash=HASH,
        secondary_matrix_hash=HASH,
        free_dof_map_hash=HASH,
        node_ids=NODES,
        tolerance=1.0e-8,
        modes=[_mode(analysis_type="modal")],
    )

    with pytest.raises(SpectralResultIRError, match="checkpoint_hash_mismatch"):
        validate_spectral_result_ir(replace(result, checkpoint_hash="sha256:" + "2" * 64))
    mutated_mode = replace(result.modes[0], node_shapes=((0.0,) * 6, (1.0,) * 6))
    with pytest.raises(SpectralResultIRError, match="mode_shape_hash_mismatch"):
        validate_spectral_result_ir(replace(result, modes=(mutated_mode,)))


def test_spectral_result_ir_fails_closed_on_wrong_modal_quantity() -> None:
    row = _mode(analysis_type="modal")
    row["load_factor"] = 2.0

    with pytest.raises(SpectralResultIRError, match="modal_quantity_invalid"):
        create_spectral_result_ir(
            result_id="f3.modal",
            analysis_type="modal",
            model_ir_content_hash=HASH,
            solver_id="cpu.modal.v1",
            solver_receipt_hash=HASH,
            stiffness_matrix_hash=HASH,
            secondary_matrix_hash=HASH,
            free_dof_map_hash=HASH,
            node_ids=NODES,
            tolerance=1.0e-8,
            modes=[row],
        )
