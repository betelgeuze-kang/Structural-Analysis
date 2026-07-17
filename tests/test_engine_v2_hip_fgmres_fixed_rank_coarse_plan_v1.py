from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib.resources
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_plan_v1 import (  # noqa: E402
    HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE,
    HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_SCHEMA_VERSION,
    HipFgmresFixedRankCoarsePlanV1Error,
    compile_hip_fgmres_fixed_rank_coarse_plan_v1,
    hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1,
    validate_hip_fgmres_fixed_rank_coarse_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (  # noqa: E402
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (  # noqa: E402
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.operators.sparse_linear_static import (  # noqa: E402
    solve_sparse_execution_plan_v2,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (  # noqa: E402
    _compile_fixed_source,
    _load_hiprtc_api,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (  # noqa: E402
    compile_fgmres_policy_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (  # noqa: E402
    build_cpu_fgmres_fixed_rank_coarse_space_v1,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
MODULE = (
    SRC_ROOT
    / "structural_analysis/engine_v2/assembly_backend/fgmres_fixed_rank_coarse_plan_v1.py"
)
KERNEL = (
    SRC_ROOT
    / "structural_analysis/engine_v2/assembly_backend/kernels"
    / "engine_v2_fgmres_fixed_rank_coarse_v1.hip.cpp"
)
SCHEMA = (
    SRC_ROOT
    / "structural_analysis/schemas/hip_fgmres_fixed_rank_coarse_plan_v1.schema.json"
)


def _execution(load_pattern_id: str = "LC_WEAK"):
    model = load_model_ir_v2(FIXTURE)
    buffers = pack_solver_model_buffers(model, load_pattern_id=load_pattern_id)
    return compile_execution_plan_v2(buffers)


def _direct_mode(execution) -> np.ndarray:
    result = solve_sparse_execution_plan_v2(execution)
    free = execution.array("free_dofs")
    return immutable_array(
        result.displacements_si.reshape(-1)[free],
        dtype="<f8",
    )


def _sources(*, retained_rank: int = 1, load_pattern_id: str = "LC_WEAK"):
    execution = _execution(load_pattern_id)
    direct = _direct_mode(execution)
    if retained_rank == 1:
        candidates = direct.reshape(-1, 1)
    else:
        axis = np.zeros_like(direct)
        axis[0] = 1.0
        candidates = np.column_stack((direct, axis))
    coarse = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        execution,
        candidates,
        rank_cap=retained_rank,
    )
    free_space = compile_hip_free_space_operator_plan_v1(execution)
    policy = compile_fgmres_policy_v1(
        restart_dimension=4,
        max_iterations=16,
        absolute_tolerance=0.0,
        relative_tolerance=1.0e-10,
    )
    fgmres = compile_hip_fgmres_plan_v1(execution, free_space, policy)
    return execution, fgmres, coarse


def _plan(*, retained_rank: int = 1):
    _, fgmres, coarse = _sources(retained_rank=retained_rank)
    return compile_hip_fgmres_fixed_rank_coarse_plan_v1(fgmres, coarse)


def test_plan_replays_exact_sources_schema_and_claim_boundary() -> None:
    _, fgmres, coarse = _sources(retained_rank=2)
    plan = compile_hip_fgmres_fixed_rank_coarse_plan_v1(fgmres, coarse)
    payload = plan.to_dict()

    assert plan.schema_version == HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_SCHEMA_VERSION
    assert (
        plan.capability_profile
        == HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE
    )
    assert (
        plan.application_abi_version
        == HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1
    )
    assert plan.source_fgmres_plan_hash == fgmres.plan_hash
    assert plan.source_coarse_space_hash == coarse.coarse_space_hash
    assert plan.retained_rank == 2
    assert payload["claim_boundary"] == {
        "compile_time_plan_only": True,
        "fixed_source_present": True,
        "static_upload_planned": True,
        "application_iteration_h2d_zero_planned": True,
        "application_iteration_d2h_zero_planned": True,
        "application_additional_csr_zero_planned": True,
        "kernel_compiled": False,
        "device_allocation_performed": False,
        "device_upload_performed": False,
        "execution_performed": False,
        "numerical_parity_proven": False,
        "iteration_host_copy_zero_proven": False,
        "amg_or_dd_proven": False,
        "mesh_independent_iterations_proven": False,
        "end_to_end_O_N_proven": False,
        "speedup_proven": False,
        "promotion_eligible": False,
        "commercial_ready": False,
        "python_semantic_replay_required": True,
    }
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    validate_hip_fgmres_fixed_rank_coarse_plan_v1(
        plan,
        expected_fgmres_plan=fgmres,
        expected_coarse_space=coarse,
    )


def test_exact_parent_borrows_owned_extents_and_four_launch_schedule() -> None:
    plan = _plan(retained_rank=2)
    f = plan.free_dof_count
    k = plan.retained_rank
    m = plan.restart_dimension

    assert tuple(row.name for row in plan.buffers) == (
        "jacobi_inverse",
        "basis_v",
        "preconditioned_basis_z",
        "coarse_physical_basis_z",
        "coarse_operator_basis_az",
        "coarse_cholesky_l",
        "coarse_rhs",
        "coarse_coefficients",
        "coarse_status",
    )
    assert tuple(row.ownership for row in plan.buffers[:3]) == ("borrowed",) * 3
    assert tuple(row.ownership for row in plan.buffers[3:]) == ("owned",) * 6
    assert plan.borrowed_device_byte_span == 8 * (f + (m + 1) * f + m * f)
    assert plan.static_upload_copy_count == 3
    assert plan.static_upload_byte_count == 8 * (2 * f * k + k * k)
    assert plan.owned_device_byte_length == 8 * (2 * f * k + k * k + 2 * k) + 4
    assert tuple(row.symbol for row in plan.launches) == (
        HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1
    )
    assert tuple((row.grid_x, row.block_x) for row in plan.launches) == (
        (1, 1),
        (k, 256),
        (1, 1),
        ((f + 255) // 256, 256),
    )
    assert plan.application_kernel_launch_count == 4
    assert plan.application_h2d_copy_count == 0
    assert plan.application_d2h_copy_count == 0
    assert plan.application_csr_apply_count == 0
    assert plan.application_allocation_count == 0
    assert plan.application_synchronization_count == 0
    assert plan.dense_projector_element_count == 0


def test_compilation_is_deterministic_and_binds_source_array_hashes() -> None:
    _, fgmres, coarse = _sources(retained_rank=2)
    first = compile_hip_fgmres_fixed_rank_coarse_plan_v1(fgmres, coarse)
    second = compile_hip_fgmres_fixed_rank_coarse_plan_v1(fgmres, coarse)

    assert first.to_dict() == second.to_dict()
    assert first.plan_hash == second.plan_hash
    assert first.memory_layout_hash == second.memory_layout_hash
    assert first.physical_basis_data_hash == coarse.descriptors[3].data_hash
    assert first.operator_basis_data_hash == coarse.descriptors[4].data_hash
    assert first.cholesky_data_hash == coarse.descriptors[6].data_hash


def test_cross_plan_or_operator_source_pair_is_rejected() -> None:
    weak_execution, _, weak_coarse = _sources(load_pattern_id="LC_WEAK")
    strong_execution = _execution("LC_STRONG")
    assert weak_execution.plan_hash != strong_execution.plan_hash
    strong_free_space = compile_hip_free_space_operator_plan_v1(strong_execution)
    strong_fgmres = compile_hip_fgmres_plan_v1(
        strong_execution,
        strong_free_space,
        compile_fgmres_policy_v1(restart_dimension=4, max_iterations=16),
    )

    with pytest.raises(HipFgmresFixedRankCoarsePlanV1Error) as exc_info:
        compile_hip_fgmres_fixed_rank_coarse_plan_v1(strong_fgmres, weak_coarse)
    assert exc_info.value.code == "hip_fgmres_coarse_source_binding_mismatch"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_coarse_space_hash", "sha256:" + "1" * 64),
        ("static_upload_copy_count", 4),
        ("application_d2h_copy_count", 1),
        ("dense_projector_element_count", 1),
        ("kernel_source_hash", "sha256:" + "2" * 64),
    ),
)
def test_tampered_binding_work_or_source_identity_fails_closed(
    field: str,
    value: object,
) -> None:
    plan = _plan()
    forged = replace(plan, **{field: value})
    with pytest.raises(HipFgmresFixedRankCoarsePlanV1Error):
        validate_hip_fgmres_fixed_rank_coarse_plan_v1(forged)


def test_expected_source_identity_and_boolean_integer_alias_fail_closed() -> None:
    _, fgmres, coarse = _sources()
    plan = compile_hip_fgmres_fixed_rank_coarse_plan_v1(fgmres, coarse)
    with pytest.raises(HipFgmresFixedRankCoarsePlanV1Error) as exc_info:
        validate_hip_fgmres_fixed_rank_coarse_plan_v1(
            plan,
            expected_fgmres_plan=replace(fgmres),
            expected_coarse_space=coarse,
        )
    assert exc_info.value.code == "hip_fgmres_coarse_expected_fgmres_plan_mismatch"

    forged = replace(plan, retained_rank=True)
    with pytest.raises(HipFgmresFixedRankCoarsePlanV1Error) as exc_info:
        validate_hip_fgmres_fixed_rank_coarse_plan_v1(forged)
    assert exc_info.value.code == "hip_fgmres_coarse_plan_scalar_type_invalid"


def test_schema_rejects_extra_fields_and_coherent_promotion_claims() -> None:
    payload = _plan().to_dict()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    extra = deepcopy(payload)
    extra["runtime_receipt"] = {"ready": True}
    assert list(validator.iter_errors(extra))
    promoted = deepcopy(payload)
    promoted["claim_boundary"]["promotion_eligible"] = True
    assert list(validator.iter_errors(promoted))
    executed = deepcopy(payload)
    executed["claim_boundary"]["execution_performed"] = True
    assert list(validator.iter_errors(executed))


def test_kernel_abi_payload_is_fresh_and_hash_stable() -> None:
    first = hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1()
    second = hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1()
    assert first == second
    assert first is not second
    assert canonical_hash(first) == canonical_hash(second)
    first["status_bits"]["invalid_geometry"] = 99
    assert second["status_bits"]["invalid_geometry"] == 0
    assert second["integration_seam"]["replaces"] == (
        "recurrence_v2_vector_mode_APPLY_JACOBI_INDEXED"
    )
    assert second["pointer_contract"] == {
        "fp64_alignment_bytes": 8,
        "status_alignment_bytes": 4,
        "all_buffer_ranges_disjoint": True,
        "uintptr_range_checked": True,
    }


def test_fixed_source_has_exact_symbols_and_no_runtime_or_csr_calls() -> None:
    source = KERNEL.read_text(encoding="utf-8")
    for symbol in HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1:
        assert source.count(symbol) == 1
    for forbidden in (
        "hipMalloc",
        "hipFree",
        "hipMemcpy",
        "hipStreamSynchronize",
        "row_ptr",
        "column_indices",
    ):
        assert forbidden not in source
    assert "coarse_physical_basis_z" in source
    assert "coarse_operator_basis_az" in source
    assert "coarse_cholesky_l" in source
    assert "__shared__ double shared_sum[kCoarseBlockSize]" in source
    assert "__shared__ unsigned int shared_gate" in source
    assert "if (shared_gate != 0u)" in source
    assert "static_cast<unsigned int>(free_dof_count)" in source


@pytest.mark.parametrize("architecture", ("gfx1030", "gfx1100"))
def test_fixed_source_compiles_with_available_hiprtc(architecture: str) -> None:
    if not Path("/opt/rocm/lib/libhiprtc.so").exists():
        pytest.skip("libhiprtc is not installed")
    rtc = _load_hiprtc_api(None)
    status, major, _minor = rtc.version()
    assert status == 0 and major >= 0
    code_object, compile_log = _compile_fixed_source(
        rtc,
        KERNEL.read_bytes(),
        (
            f"--offload-arch={architecture}",
            "-O3",
            "-std=c++17",
            "-ffp-contract=off",
        ),
        program_name=KERNEL.name,
    )
    assert code_object
    assert compile_log == ""


def test_package_resources_and_python_module_contain_no_runtime_execution() -> None:
    schemas = importlib.resources.files("structural_analysis.schemas")
    packaged_schema = schemas.joinpath(SCHEMA.name)
    assert packaged_schema.read_bytes() == SCHEMA.read_bytes()
    kernels = importlib.resources.files(
        "structural_analysis.engine_v2.assembly_backend.kernels"
    )
    packaged_kernel = kernels.joinpath(KERNEL.name)
    assert packaged_kernel.read_bytes() == KERNEL.read_bytes()

    source = MODULE.read_text(encoding="utf-8")
    for forbidden in (
        "hipMalloc",
        "hipMemcpy",
        "hipModuleLaunchKernel",
        "compile_hip_rtc_fgmres_v2_kernel(",
    ):
        assert forbidden not in source
