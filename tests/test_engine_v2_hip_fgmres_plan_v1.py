from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (  # noqa: E402
    HIP_FGMRES_PLAN_V1_CAPABILITY_PROFILE,
    HIP_FGMRES_PLAN_V1_SCHEMA_VERSION,
    HipFgmresPlanV1Error,
    _BUFFER_NAMES,
    _memory_layout_hash,
    _plan_hash,
    _plan_id,
    compile_hip_fgmres_plan_v1,
    hip_fgmres_solve_record_abi_payload_v1,
    validate_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (  # noqa: E402
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (  # noqa: E402
    compile_fgmres_policy_v1,
)
from structural_analysis.model_ir import load_model_ir_v2, parse_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/hip_fgmres_plan_v1.schema.json"


def _source(load_pattern_id: str = "LC_AXIAL") -> tuple[Any, Any]:
    model = load_model_ir_v2(FIXTURE)
    buffers = pack_solver_model_buffers(model, load_pattern_id=load_pattern_id)
    execution = compile_execution_plan_v2(buffers)
    overlay = compile_hip_free_space_operator_plan_v1(execution)
    return execution, overlay


def _artifact(
    load_pattern_id: str = "LC_AXIAL",
    *,
    restart_dimension: int = 16,
    max_iterations: int = 64,
):
    execution, overlay = _source(load_pattern_id)
    policy = compile_fgmres_policy_v1(
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
    )
    return (
        execution,
        overlay,
        compile_hip_fgmres_plan_v1(execution, overlay, policy),
    )


def _rehash(artifact: Any) -> Any:
    forged = replace(artifact, memory_layout_hash=_memory_layout_hash(artifact))
    forged = replace(forged, plan_id=_plan_id(forged))
    forged = replace(forged, plan_hash="sha256:" + "0" * 64)
    return replace(forged, plan_hash=_plan_hash(forged))


def test_schema_is_strict_and_plan_claims_no_runtime_or_promotion() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    _, _, artifact = _artifact()
    payload = artifact.to_dict()

    assert not list(validator.iter_errors(payload))
    assert artifact.schema_version == HIP_FGMRES_PLAN_V1_SCHEMA_VERSION
    assert artifact.capability_profile == HIP_FGMRES_PLAN_V1_CAPABILITY_PROFILE
    assert payload["claim_boundary"] == {
        "compile_time_plan_only": True,
        "hip_specific_layout": True,
        "device_buffer_layout_planned": True,
        "positive_jacobi_source_preflight_passed": True,
        "execution_performed": False,
        "device_allocation_performed": False,
        "runtime_receipt_lineage_bound": False,
        "fgmres_runtime_ready": False,
        "iteration_host_copy_zero_proven": False,
        "spd_proven": False,
        "pcg_ready": False,
        "fallback_used": False,
        "end_to_end_O_N_proven": False,
        "speedup_proven": False,
        "promotion_eligible": False,
        "commercial_ready": False,
        "schema_only_validation_authoritative": False,
        "python_semantic_replay_required": True,
    }
    extra = deepcopy(payload)
    extra["runtime_lineage_requirements"]["source_apply_receipt_hash"] = (
        "sha256:" + "1" * 64
    )
    assert list(validator.iter_errors(extra))
    promoted = deepcopy(payload)
    promoted["claim_boundary"]["promotion_eligible"] = True
    assert list(validator.iter_errors(promoted))


def test_compiler_is_deterministic_and_binds_exact_sources_and_policy() -> None:
    execution, overlay = _source()
    policy = compile_fgmres_policy_v1()
    first = compile_hip_fgmres_plan_v1(execution, overlay, policy)
    second = compile_hip_fgmres_plan_v1(execution, overlay, policy)

    assert first.to_dict() == second.to_dict()
    assert first.plan_hash == second.plan_hash
    assert first.source_execution_plan_hash == execution.plan_hash
    assert first.source_operator_hash == execution.operator_hash
    assert first.source_numeric_snapshot_hash == execution.numeric_snapshot_hash
    assert first.source_partition_hash == execution.partition_hash
    assert first.source_free_space_plan_hash == overlay.plan_hash
    assert first.source_free_space_view_hash == overlay.free_space_view_hash
    assert first.jacobi_inverse_data_hash.startswith("sha256:")
    assert first.source_residual_tolerance == execution.residual_tolerance
    assert first.policy == policy
    assert first.policy is not policy
    validate_hip_fgmres_plan_v1(
        first,
        expected_execution_plan=execution,
        expected_free_space_plan=overlay,
    )


def test_exact_seven_borrows_and_nine_owned_workspace_extents() -> None:
    _, _, artifact = _artifact(restart_dimension=16, max_iterations=64)
    f = artifact.free_dof_count
    z = artifact.reduced_csr_nnz
    m = artifact.restart_dimension
    p = (f + 511) // 512
    restarts = (artifact.max_iterations + m - 1) // m

    assert tuple(row.name for row in artifact.buffers) == _BUFFER_NAMES
    assert sum(row.ownership == "borrowed" for row in artifact.buffers) == 7
    assert sum(row.ownership == "owned" for row in artifact.buffers) == 9
    assert artifact.buffer("reduced_csr_row_ptr").shape == (f + 1,)
    assert artifact.buffer("reduced_csr_column_indices").shape == (z,)
    assert artifact.buffer("reduced_csr_values").shape == (z,)
    assert artifact.buffer("basis_v").shape == (m + 1, f)
    assert artifact.buffer("preconditioned_basis_z").shape == (m, f)
    assert artifact.buffer("reduction_ping").shape == (2 * p,)
    assert artifact.buffer("reduction_pong").shape == (2 * p,)
    assert artifact.buffer("packed_dense_state").shape == (m * m + 5 * m + 1,)
    assert artifact.buffer("solve_record").shape == (192 + 72 * restarts,)
    assert artifact.buffer("solve_record").dtype == "|u1"

    expected_owned = (
        8 * ((2 * m + 4) * f + 4 * p + m * m + 5 * m + 1) + 192 + 72 * restarts
    )
    expected_borrowed = 4 * (f + 1) + 4 * z + 8 * z + 8 * 4 * f
    assert artifact.owned_device_byte_length == expected_owned
    assert artifact.borrowed_device_byte_span == expected_borrowed
    assert (
        artifact.to_dict()["memory_plan"]["additional_peak_device_bytes_planned"]
        == expected_owned
    )


def test_recurrence_policy_is_explicit_fp64_dgks_and_no_fallback() -> None:
    _, _, artifact = _artifact()
    payload = artifact.to_dict()
    algorithm = payload["algorithm_contract"]

    assert algorithm["recurrence_abi_version"] == 1
    assert algorithm["dgks_reorthogonalization_eta"] == 0.717
    assert algorithm["arnoldi_breakdown_epsilon_multiplier"] == 64.0
    assert algorithm["hessenberg_layout"] == "column_major_(M+1)_by_M"
    assert algorithm["preconditioner"] == "positive_unshifted_jacobi_right"
    assert algorithm["convergence_requires_both_true_residual_gates"] is True
    assert algorithm["estimated_residual_authoritative"] is False
    assert algorithm["authoritative_load_scale"] == "max_1_rhs_linf"
    assert algorithm["candidate_true_residual_trigger"] == (
        "estimated_l2_pass_or_suspected_arnoldi_breakdown"
    )
    assert algorithm["dense_lstsq_or_pinv_fallback_allowed"] is False
    assert algorithm["diagonal_shift_or_clamp_allowed"] is False
    assert payload["policy"]["policy_hash"] == artifact.policy.policy_hash


@pytest.mark.parametrize(
    ("restart_dimension", "max_iterations", "expected_restarts", "record_bytes"),
    ((1, 0, 0, 192), (2, 5, 3, 408), (16, 4096, 256, 18624)),
)
def test_global_iteration_cap_and_history_extent_cross_restart_boundaries(
    restart_dimension: int,
    max_iterations: int,
    expected_restarts: int,
    record_bytes: int,
) -> None:
    _, _, artifact = _artifact(
        restart_dimension=restart_dimension,
        max_iterations=max_iterations,
    )

    assert artifact.maximum_restart_count == expected_restarts
    assert artifact.buffer("solve_record").byte_length == record_bytes
    assert artifact.packed_dense_scalar_count == (
        restart_dimension * restart_dimension + 5 * restart_dimension + 1
    )


def test_same_symbolic_topology_still_binds_each_numeric_and_load_source() -> None:
    axial_execution, axial_overlay, axial = _artifact("LC_AXIAL")
    weak_execution, weak_overlay, weak = _artifact("LC_WEAK")

    assert axial_execution.symbolic_reuse_hash == weak_execution.symbolic_reuse_hash
    assert axial.memory_layout_hash == weak.memory_layout_hash
    assert axial.source_numeric_snapshot_hash != weak.source_numeric_snapshot_hash
    assert axial.source_free_space_plan_hash != weak.source_free_space_plan_hash
    assert axial.plan_hash != weak.plan_hash

    with pytest.raises(HipFgmresPlanV1Error) as error:
        compile_hip_fgmres_plan_v1(axial_execution, weak_overlay)
    assert error.value.code == "hip_fgmres_source_free_space_plan_invalid"
    validate_hip_fgmres_plan_v1(
        weak,
        expected_execution_plan=weak_execution,
        expected_free_space_plan=weak_overlay,
    )
    assert axial_overlay.plan_hash != weak_overlay.plan_hash


def test_fully_rehashed_buffer_semantic_forgery_is_rejected() -> None:
    _, _, artifact = _artifact()
    rows = list(artifact.buffers)
    rows[0] = replace(rows[0], source="free_space_numeric")
    forged = _rehash(replace(artifact, buffers=tuple(rows)))

    with pytest.raises(HipFgmresPlanV1Error) as error:
        validate_hip_fgmres_plan_v1(forged)
    assert error.value.code == "hip_fgmres_plan_schema_invalid"

    rows = list(artifact.buffers)
    rows[0] = replace(
        rows[0],
        element_count=rows[0].element_count + 1,
        byte_length=rows[0].byte_length + 4,
    )
    extent_forgery = _rehash(replace(artifact, buffers=tuple(rows)))
    payload = extent_forgery.to_dict()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    assert payload["claim_boundary"]["schema_only_validation_authoritative"] is False
    with pytest.raises(HipFgmresPlanV1Error) as extent_error:
        validate_hip_fgmres_plan_v1(extent_forgery)
    assert extent_error.value.code == "hip_fgmres_buffer_plan_mismatch"


def test_fully_rehashed_execution_binding_forgery_is_rejected() -> None:
    _, _, artifact = _artifact()
    forged = _rehash(replace(artifact, source_operator_hash="sha256:" + "f" * 64))

    with pytest.raises(HipFgmresPlanV1Error) as error:
        validate_hip_fgmres_plan_v1(forged)
    assert error.value.code == "hip_fgmres_source_binding_mismatch"
    assert error.value.path == "/source_contract/operator_hash"


def test_policy_hash_forgery_and_wrong_expected_types_fail_closed() -> None:
    execution, overlay, artifact = _artifact()
    forged_policy = replace(artifact.policy, policy_hash="sha256:" + "0" * 64)
    forged = replace(artifact, policy=forged_policy)

    with pytest.raises(HipFgmresPlanV1Error) as policy_error:
        validate_hip_fgmres_plan_v1(forged)
    assert policy_error.value.code == "hip_fgmres_policy_invalid"

    with pytest.raises(HipFgmresPlanV1Error) as execution_error:
        validate_hip_fgmres_plan_v1(
            artifact,
            expected_execution_plan=object(),  # type: ignore[arg-type]
        )
    assert execution_error.value.code == "hip_fgmres_expected_execution_plan_invalid"

    with pytest.raises(HipFgmresPlanV1Error) as overlay_error:
        validate_hip_fgmres_plan_v1(
            artifact,
            expected_execution_plan=execution,
            expected_free_space_plan=object(),  # type: ignore[arg-type]
        )
    assert overlay_error.value.code == "hip_fgmres_expected_free_space_plan_invalid"
    assert overlay.plan_hash == artifact.source_free_space_plan_hash


def test_compile_time_manifest_has_no_live_runtime_identity_or_dynamic_hashes() -> None:
    _, _, artifact = _artifact()
    payload = artifact.to_dict()
    serialized = json.dumps(payload, sort_keys=True)

    for forbidden in (
        "source_apply_id",
        "source_apply_receipt_hash",
        "primitive_context_id",
        "primitive_receipt_hash",
        "lease_epoch",
        "stream_handle",
        "device_address",
        "kernel_identity_hash",
    ):
        assert forbidden not in serialized
    for name in (
        "reduced_state",
        "reduced_direction",
        "jacobi_inverse",
    ):
        descriptor = next(
            row for row in payload["memory_plan"]["buffers"] if row["name"] == name
        )
        assert "data_hash" not in descriptor


def test_solve_record_abi_has_exact_little_endian_fields_and_codes() -> None:
    _, _, artifact = _artifact(restart_dimension=2, max_iterations=5)
    memory = artifact.to_dict()["memory_plan"]

    assert memory["scalar_byte_order"] == "little_endian"
    assert memory["solve_record_header_fields"][0] == {
        "name": "recurrence_abi_version",
        "dtype": "i32",
        "offset_bytes": 0,
    }
    assert memory["solve_record_header_fields"][-1] == {
        "name": "reserved_f64_0",
        "dtype": "f64",
        "offset_bytes": 184,
    }
    assert memory["solve_record_header_fields"][15] == {
        "name": "restart_dimension",
        "dtype": "i32",
        "offset_bytes": 60,
    }
    assert memory["solve_record_restart_fields"][-1]["offset_bytes"] == 64
    assert memory["terminal_status_codes"]["converged"] == 1
    assert memory["termination_codes"]["arnoldi_invariant_subspace_breakdown"] == 31
    assert memory["restart_flag_bits"]["true_residual_replayed"] == 0

    shared = hip_fgmres_solve_record_abi_payload_v1()
    assert memory["scalar_byte_order"] == shared["byte_order"]
    assert memory["solve_record_header_bytes"] == shared["header_bytes"]
    assert memory["solve_record_restart_bytes"] == shared["restart_bytes"]
    assert memory["solve_record_header_layout"] == shared["header_layout"]
    assert memory["solve_record_restart_layout"] == shared["restart_layout"]
    assert memory["solve_record_header_fields"] == shared["header_fields"]
    assert memory["solve_record_restart_fields"] == shared["restart_fields"]
    for key in (
        "terminal_status_codes",
        "termination_codes",
        "restart_hint_codes",
        "restart_flag_bits",
    ):
        assert memory[key] == shared[key]


def test_positive_diagonal_with_nonfinite_reciprocal_is_rejected_at_compile() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["materials"][0]["parameters"]["elastic_modulus_pa"] = 1.0e-305
    model = parse_model_ir_v2(payload)
    buffers = pack_solver_model_buffers(model, load_pattern_id="LC_AXIAL")
    execution = compile_execution_plan_v2(buffers)
    diagonal = []
    row_ptr = execution.array("reduced_csr_row_ptr")
    columns = execution.array("reduced_csr_column_indices")
    values = execution.array("reduced_stiffness_csr_values")
    for row in range(execution.array("free_dofs").size):
        begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
        position = np.flatnonzero(columns[begin:end] == row)
        diagonal.append(float(values[begin + int(position[0])]))
    assert min(diagonal) > 0.0
    assert not np.isfinite(1.0 / min(diagonal))
    overlay = compile_hip_free_space_operator_plan_v1(execution)

    with pytest.raises(HipFgmresPlanV1Error) as error:
        compile_hip_fgmres_plan_v1(execution, overlay)
    assert error.value.code == "hip_fgmres_positive_jacobi_inverse_unavailable"


def test_public_api_exports_canonical_fgmres_plan_objects() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.assembly_backend as assembly_backend

    assert engine_v2.HipFgmresPlanV1 is assembly_backend.HipFgmresPlanV1
    assert engine_v2.HipFgmresBufferPlanV1 is assembly_backend.HipFgmresBufferPlanV1
    assert (
        engine_v2.compile_hip_fgmres_plan_v1
        is assembly_backend.compile_hip_fgmres_plan_v1
    )
    assert (
        engine_v2.validate_hip_fgmres_plan_v1
        is assembly_backend.validate_hip_fgmres_plan_v1
    )
