"""Actual-gfx1030 observation for the allocation-lineage coarse context."""

from __future__ import annotations

import os

import numpy as np

from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_context_v1 import (
    open_hip_fgmres_fixed_rank_coarse_context_v1,
    validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1,
    validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_plan_v1 import (
    compile_hip_fgmres_fixed_rank_coarse_plan_v1,
)
from structural_analysis.engine_v2.backends.hip.transfer_audit_v1 import (
    _capture_bound_copy_audit_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (
    apply_cpu_fgmres_fixed_rank_coarse_v1,
    build_cpu_fgmres_fixed_rank_coarse_space_v1,
)

from tests.test_engine_v2_hip_fgmres_global_recurrence_context_hardware_v1 import (
    _three_node_serial_cantilever_model,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
    _open_canonical_chain,
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            "ENGINE_V2_REQUIRE_HIP_FGMRES_FIXED_RANK_COARSE_CONTEXT_HARDWARE",
        )
    )


def test_native_gfx1030_live_coarse_context_matches_cpu_exactly() -> None:
    architecture = _native_gfx1030(_hardware_required())
    policy = compile_fgmres_policy_v1(
        restart_dimension=2,
        max_iterations=2,
        relative_tolerance=1.0e-15,
    )
    chain, _ = _open_canonical_chain(
        model=_three_node_serial_cantilever_model(),
        architecture=architecture,
        required=_hardware_required(),
        policy=policy,
    )
    coarse_open = None
    try:
        source_plan = chain.live._source_plan
        execution = source_plan._source_execution_plan
        basis = np.eye(
            source_plan.free_dof_count,
            min(2, source_plan.free_dof_count),
            dtype="<f8",
        )
        coarse = build_cpu_fgmres_fixed_rank_coarse_space_v1(
            execution,
            basis,
            rank_cap=2,
        )
        plan = compile_hip_fgmres_fixed_rank_coarse_plan_v1(source_plan, coarse)
        runtime = chain.live._runtime
        setup_before = _capture_bound_copy_audit_v1(runtime).snapshot
        coarse_open = open_hip_fgmres_fixed_rank_coarse_context_v1(
            chain.live,
            plan,
            architecture=architecture,
        )
        context = coarse_open.context
        assert coarse_open.ready and context is not None
        assert coarse_open.receipt is not None
        opening = validate_hip_fgmres_fixed_rank_coarse_context_receipt_v1(
            coarse_open.receipt,
            expected_context=context,
        )
        setup_after = _capture_bound_copy_audit_v1(runtime).snapshot
        assert opening.actual_backend == "hip"
        assert opening.kernel.kernel_origin == "internally_compiled"
        assert opening.kernel.architecture == "gfx1030"
        assert opening.kernel.source_sha256 == plan.kernel_source_hash
        assert opening.kernel.kernel_abi_hash == plan.kernel_abi_hash
        assert opening.dimensions.free_dof_count == 12
        assert opening.dimensions.retained_rank == 2
        assert opening.allocation_lineage.managed_device_bytes == 452
        assert opening.telemetry.h2d_operation_success_count == 3
        assert opening.telemetry.h2d_bytes_succeeded == 416
        assert opening.telemetry.fence_attempt_count == 1
        assert opening.telemetry.fence_success_count == 1
        assert (
            setup_after.h2d_async.attempt_count - setup_before.h2d_async.attempt_count
            == 3
        )

        before_application = _capture_bound_copy_audit_v1(runtime).snapshot
        application = context.enqueue_application(0)
        validate_hip_fgmres_fixed_rank_coarse_application_receipt_v1(
            application,
            expected_context=context,
        )
        after_application = _capture_bound_copy_audit_v1(runtime).snapshot
        for before, after in (
            (before_application.h2d_async, after_application.h2d_async),
            (before_application.d2h_async, after_application.d2h_async),
            (before_application.d2h_blocking, after_application.d2h_blocking),
        ):
            assert after.attempt_count - before.attempt_count == 0
        assert application.accepted_launch_count == 4
        assert context.fence() == 4

        free_dof_count = source_plan.free_dof_count
        restart_dimension = source_plan.restart_dimension
        basis_v = np.empty(
            (restart_dimension + 1, free_dof_count),
            dtype="<f8",
        )
        basis_z = np.empty(
            (restart_dimension, free_dof_count),
            dtype="<f8",
        )
        status = np.empty(1, dtype="<u4")
        runtime.copy_d2h(
            basis_v,
            chain.live._owned_capabilities["basis_v"].base,
        )
        runtime.copy_d2h(
            basis_z,
            chain.live._owned_capabilities["preconditioned_basis_z"].base,
        )
        runtime.copy_d2h(
            status,
            context._owned_capabilities["coarse_status"].base,
        )
        expected = apply_cpu_fgmres_fixed_rank_coarse_v1(coarse, basis_v[0])
        assert int(status[0]) == 0
        np.testing.assert_array_equal(basis_z[0], expected)
        assert float(np.max(np.abs(basis_z[0] - expected))) == 0.0

        product_receipt = context.receipt()
        assert product_receipt.telemetry.application_success_count == 1
        assert product_receipt.telemetry.kernel_launch_success_count == 4
        assert product_receipt.telemetry.fence_attempt_count == 2
        assert product_receipt.telemetry.fence_success_count == 2
        assert product_receipt.telemetry.fence_acknowledged_launch_count == 4
        assert product_receipt.telemetry.d2h_operation_count == 0
        assert not product_receipt.claims.actual_device_application_observed
        assert not product_receipt.claims.recurrence_state_machine_integrated
        assert not product_receipt.claims.device_status_terminal_bound
        assert not product_receipt.claims.promotion_eligible
    finally:
        if (
            coarse_open is not None
            and coarse_open.context is not None
            and not coarse_open.context.closed
        ):
            coarse_open.context.close()
        chain.close()
