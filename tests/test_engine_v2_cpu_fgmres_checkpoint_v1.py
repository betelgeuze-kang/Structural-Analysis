from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.engine_v2.cpu_fgmres import (
    CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
    CPUFGMRESError,
)
from structural_analysis.engine_v2.cpu_fgmres_checkpoint import (
    CPU_FGMRES_CHECKPOINT_FILENAME,
    CPU_FGMRES_CHECKPOINT_MAGIC,
    CPU_FGMRES_CHECKPOINT_SCHEMA_VERSION,
    create_cpu_fgmres_checkpoint,
    load_cpu_fgmres_checkpoint,
    resume_cpu_fgmres_from_checkpoint,
    validate_cpu_fgmres_checkpoint_bytes,
    validate_cpu_fgmres_checkpoint_manifest,
    write_cpu_fgmres_checkpoint_artifact,
)
from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (
    build_cpu_hip_fgmres_recurrence_reference,
)


def _reference_checkpoint():
    reference = build_cpu_hip_fgmres_recurrence_reference()
    run = reference.cpu_runs[1]
    checkpoint = create_cpu_fgmres_checkpoint(
        run,
        restart_index=0,
        checkpoint_artifact_uri=(
            "artifact://engine-v2/checkpoints/fgmres_restart_checkpoint.bin"
        ),
    )
    return reference, run, checkpoint


def _load(
    reference,
    run,
    checkpoint,
    data: bytes | None = None,
    *,
    include_explicit_preconditioner: bool = True,
):
    return load_cpu_fgmres_checkpoint(
        checkpoint.to_manifest(),
        checkpoint.to_bytes() if data is None else data,
        execution_plan=run._execution_plan,
        scaling=run._scaling,
        reduced_csr=run._reduced_csr,
        node_coordinates_m=reference.primitive_reference.node_coordinates_m,
        reference_equation_load_si=(
            reference.primitive_reference.reference_equation_load_si
        ),
        global_csr_values_si=run._input_arrays["global_csr_values_si"],
        right_hand_side_si=run._input_arrays["right_hand_side_si"],
        initial_solution_free=run._input_arrays["initial_solution_free"],
        right_preconditioner_inverse_diagonal=(
            run._input_arrays["right_preconditioner_inverse_diagonal"]
            if include_explicit_preconditioner
            else None
        ),
    )


def test_checkpoint_binary_is_descriptor_only_and_restart_bound() -> None:
    _reference, run, checkpoint = _reference_checkpoint()
    manifest = checkpoint.to_manifest()
    raw = checkpoint.to_bytes()

    assert checkpoint.schema_version == CPU_FGMRES_CHECKPOINT_SCHEMA_VERSION
    assert raw.startswith(CPU_FGMRES_CHECKPOINT_MAGIC)
    assert checkpoint.iteration_count == 1
    assert checkpoint.matvec_count == 3
    assert checkpoint.next_restart_index == 1
    assert checkpoint.restart_history[0].disposition == "restarted"
    assert manifest["boundary"]["last_observation_hash"] == (
        run.observations[1].observation_hash
    )
    assert manifest["artifact"]["byte_length"] == 48 + 2 * 8 * run.free_count
    assert [row["name"] for row in manifest["artifact"]["vectors"]] == [
        "solution_free",
        "scaled_recurrence_residual_free",
    ]
    assert "values" not in manifest["artifact"]
    assert manifest["claim_boundary"][
        "resumable_without_completed_iteration_replay"
    ] is True
    assert manifest["claim_boundary"]["result_ir_authority"] is False
    assert not checkpoint.solution_free.flags.writeable
    assert not checkpoint.scaled_residual_free.flags.writeable
    validate_cpu_fgmres_checkpoint_manifest(manifest)
    validate_cpu_fgmres_checkpoint_bytes(checkpoint, raw)


def test_loaded_checkpoint_resumes_to_exact_one_shot_manifest() -> None:
    reference, one_shot, checkpoint = _reference_checkpoint()

    loaded = _load(reference, one_shot, checkpoint)
    resumed = resume_cpu_fgmres_from_checkpoint(
        loaded,
        solution_artifact_uri=str(one_shot.solution_descriptor.artifact_uri),
    )

    assert resumed.run_hash == one_shot.run_hash
    assert resumed.to_manifest() == one_shot.to_manifest()
    assert np.array_equal(resumed.solution_free, one_shot.solution_free)
    assert resumed.iteration_count == 2
    assert resumed.matvec_count == 5
    assert [row.disposition for row in resumed.restart_history] == [
        "restarted",
        "max_iterations",
    ]


def test_scaled_jacobi_checkpoint_rederives_exact_preconditioner() -> None:
    reference, one_shot, checkpoint = _reference_checkpoint()
    assert (
        one_shot.preconditioner_profile
        == CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
    )

    loaded = _load(
        reference,
        one_shot,
        checkpoint,
        include_explicit_preconditioner=False,
    )
    np.testing.assert_array_equal(
        loaded._input_arrays["right_preconditioner_inverse_diagonal"],
        one_shot._input_arrays["right_preconditioner_inverse_diagonal"],
    )


def test_checkpoint_bytes_and_source_inputs_fail_closed_on_tamper() -> None:
    reference, run, checkpoint = _reference_checkpoint()
    tampered = bytearray(checkpoint.to_bytes())
    tampered[-1] ^= 1

    with pytest.raises(CPUFGMRESError) as bytes_error:
        _load(reference, run, checkpoint, bytes(tampered))
    assert bytes_error.value.code == "fgmres_checkpoint_artifact_hash_mismatch"

    stale_rhs = np.asarray(run._input_arrays["right_hand_side_si"]).copy()
    stale_rhs[-1] += 1.0
    with pytest.raises(CPUFGMRESError) as source_error:
        load_cpu_fgmres_checkpoint(
            checkpoint.to_manifest(),
            checkpoint.to_bytes(),
            execution_plan=run._execution_plan,
            scaling=run._scaling,
            reduced_csr=run._reduced_csr,
            node_coordinates_m=reference.primitive_reference.node_coordinates_m,
            reference_equation_load_si=(
                reference.primitive_reference.reference_equation_load_si
            ),
            global_csr_values_si=run._input_arrays["global_csr_values_si"],
            right_hand_side_si=stale_rhs,
            initial_solution_free=run._input_arrays["initial_solution_free"],
            right_preconditioner_inverse_diagonal=run._input_arrays[
                "right_preconditioner_inverse_diagonal"
            ],
        )
    assert source_error.value.code == "fgmres_checkpoint_input_binding_mismatch"


def test_checkpoint_manifest_rejects_stale_hash_and_terminal_boundary() -> None:
    _reference, run, checkpoint = _reference_checkpoint()
    stale = deepcopy(checkpoint.to_manifest())
    stale["boundary"]["iteration_count"] = 2

    with pytest.raises(CPUFGMRESError) as stale_error:
        validate_cpu_fgmres_checkpoint_manifest(stale)
    assert stale_error.value.code == "fgmres_checkpoint_hash_mismatch"

    with pytest.raises(CPUFGMRESError) as terminal_error:
        create_cpu_fgmres_checkpoint(
            run,
            restart_index=1,
            checkpoint_artifact_uri=(
                "artifact://engine-v2/checkpoints/fgmres_restart_checkpoint.bin"
            ),
        )
    assert terminal_error.value.code == (
        "fgmres_checkpoint_restart_boundary_unavailable"
    )


def test_checkpoint_writer_is_exact_and_non_overwriting(tmp_path: Path) -> None:
    _reference, _run, checkpoint = _reference_checkpoint()
    target = tmp_path / CPU_FGMRES_CHECKPOINT_FILENAME

    written = write_cpu_fgmres_checkpoint_artifact(checkpoint, target)

    assert written.read_bytes() == checkpoint.to_bytes()
    with pytest.raises(CPUFGMRESError) as overwrite_error:
        write_cpu_fgmres_checkpoint_artifact(checkpoint, target)
    assert overwrite_error.value.code == "fgmres_checkpoint_target_exists"
    assert written.read_bytes() == checkpoint.to_bytes()
