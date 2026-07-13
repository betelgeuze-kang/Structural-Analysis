from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    pack_solver_model_buffers,
    run_linear_static_v1,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    probe_hip_capability,
)
from structural_analysis.engine_v2.rtc_backend import (  # noqa: E402
    HipRtcCsrContextError,
    open_hip_rtc_csr_execution_context,
    validate_hip_rtc_csr_context_receipt,
    validate_hip_rtc_residual_jvp_evaluation,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
_ARCH_PATTERN = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")


def _local_gpu_architectures() -> tuple[str, ...]:
    """Detect real GPU targets outside the Engine v2 runtime contract."""

    executable = shutil.which("rocm_agent_enumerator")
    if executable is None:
        for candidate in (
            Path("/opt/rocm/bin/rocm_agent_enumerator"),
            Path("/opt/rocm-6.0.2/bin/rocm_agent_enumerator"),
        ):
            if candidate.is_file() and candidate.stat().st_mode & 0o111:
                executable = str(candidate)
                break
    if executable is None:
        return ()
    try:
        completed = subprocess.run(
            [executable],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if completed.returncode != 0:
        return ()
    return tuple(
        target
        for target in (
            token.strip().lower() for token in completed.stdout.split()
        )
        if target != "gfx000" and _ARCH_PATTERN.fullmatch(target)
    )


def _deterministic_direction(dof_count: int) -> np.ndarray:
    indices = np.arange(1, dof_count + 1, dtype=np.float64)
    signs = np.where(indices.astype(np.int64) % 2 == 0, 1.0, -1.0)
    return np.ascontiguousarray(signs * indices * 1.0e-7, dtype="<f8")


def _assert_partition_parity(
    actual: np.ndarray,
    expected: np.ndarray,
    free: np.ndarray,
    constrained: np.ndarray,
) -> None:
    np.testing.assert_allclose(actual, expected, rtol=1.0e-8, atol=1.0e-8)
    np.testing.assert_allclose(
        actual[free], expected[free], rtol=1.0e-8, atol=1.0e-8
    )
    np.testing.assert_allclose(
        actual[constrained],
        expected[constrained],
        rtol=1.0e-8,
        atol=1.0e-8,
    )


def test_native_hiprtc_fused_residual_jvp_hardware_contract() -> None:
    architectures = _local_gpu_architectures()
    if not architectures:
        pytest.skip(
            "rocm_agent_enumerator reported no real gfx* agent; no CPU "
            "fallback was used in place of the missing hardware run."
        )
    architecture = architectures[0]
    capability = probe_hip_capability(device_ordinal=0)
    if capability.status != "ready":
        assert capability.fallback_used is False
        assert capability.operator_execution_proven is False
        pytest.skip(
            "Native HIP capability explicitly unavailable without fallback: "
            f"{capability.status_code}"
        )
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_STRONG"
    )
    authoritative = run_linear_static_v1(buffers, matrix_backend="dense")
    plan = authoritative.execution_plan
    committed = authoritative.committed_state
    assert committed.role == "committed"

    try:
        opened = open_hip_rtc_csr_execution_context(
            buffers,
            plan,
            committed,
            device_ordinal=0,
            architecture=architecture,
        )
    except HipRtcCsrContextError as exc:
        pytest.skip(
            "Native HIPRTC context explicitly failed without CPU fallback: "
            f"{exc.code}"
        )
    if not opened.ready or opened.context is None:
        assert opened.receipt.status in ("unavailable", "cleanup_failed")
        assert opened.receipt.telemetry.fallback_count == 0
        assert opened.receipt.reason is not None
        if opened.context is not None:
            try:
                opened.context.close()
            except HipRtcCsrContextError:
                pass
        pytest.skip(
            "Native HIPRTC context explicitly unavailable without fallback: "
            f"{opened.receipt.reason.code}"
        )

    context = opened.context
    opening = opened.receipt
    try:
        assert opening.status == "context_ready"
        assert opening.actual_backend == "hip"
        assert opening.evidence_scope == "native_hiprtc"
        assert opening.promotion_eligible is False
        assert opening.kernel is not None
        assert opening.kernel.architecture == architecture
        assert opening.kernel.kernel_symbol == "engine_v2_csr_residual_jvp_v1"
        assert opening.bindings.state_hash == committed.state_hash
        assert opening.bindings.state_epoch == committed.epoch
        assert opening.claims.native_hiprtc_kernel_loaded
        assert opening.claims.canonical_csr_operator_bound
        assert opening.claims.committed_state_bound
        assert opening.claims.residual_jvp_ready
        assert opening.telemetry.child_allocation_attempt_count == 8
        assert opening.telemetry.child_allocation_success_count == 8
        assert opening.telemetry.child_initial_h2d_attempt_count == 5
        assert opening.telemetry.child_initial_h2d_success_count == 5
        assert opening.telemetry.kernel_launch_count == 0
        assert opening.telemetry.d2h_bytes == 0
        assert opening.telemetry.fallback_count == 0
        validate_hip_rtc_csr_context_receipt(
            opening,
            expected_buffers=buffers,
            expected_plan=plan,
            expected_state=committed,
        )

        direction = _deterministic_direction(plan.dof_count)
        cpu_residual = plan.operator.residual(committed.displacement_si)
        cpu_jvp = plan.operator.jvp(direction)
        free = plan.array("free_dofs").astype(np.int64, copy=False)
        constrained = plan.array("constrained_dofs").astype(
            np.int64, copy=False
        )

        first = context.evaluate_residual_jvp(direction)
        assert first.residual is not None and first.jvp is not None
        assert first.receipt.status == "verified"
        assert first.receipt.actual_backend == "hip"
        assert first.receipt.evidence_scope == "native_hiprtc"
        # Unsigned v1 evidence is observable and live-revalidated, but cannot
        # authorize promotion because an offline rehasher can forge a receipt.
        assert first.receipt.promotion_eligible is False
        assert first.receipt.claims.residual_jvp_executed
        assert first.receipt.claims.cpu_reference_parity_verified
        parity = first.receipt.parity
        assert parity is not None and parity.passed
        assert parity.residual_full.passed
        assert parity.residual_free.passed
        assert parity.residual_constrained.passed
        assert parity.jvp_full.passed
        assert parity.jvp_free.passed
        assert parity.jvp_constrained.passed
        _assert_partition_parity(
            first.residual, cpu_residual, free, constrained
        )
        _assert_partition_parity(first.jvp, cpu_jvp, free, constrained)
        validate_hip_rtc_residual_jvp_evaluation(
            first, expected_context=context
        )

        vector_bytes = plan.dof_count * np.dtype("<f8").itemsize
        delta = first.receipt.telemetry_delta
        assert delta.h2d_bytes == vector_bytes
        assert delta.d2h_bytes == 2 * vector_bytes
        assert delta.h2d_operation_count == 1
        assert delta.d2h_operation_count == 2
        assert delta.explicit_sync_count == 1
        assert delta.kernel_launch_attempt_count == 1
        assert delta.kernel_launch_count == 1
        assert delta.allocation_count == 0
        assert delta.blocking_copy_count == 0
        assert delta.fallback_count == 0
        work = first.receipt.work.to_dict()
        assert work["csr_pass_count"] == 1
        assert work["physical_dram_bytes"] == "not_instrumented"
        assert work["end_to_end_o_n_claim"] is False

        second = context.evaluate_residual_jvp(direction)
        assert second.residual is not None and second.jvp is not None
        assert second.receipt.status == "verified"
        np.testing.assert_array_equal(second.residual, first.residual)
        np.testing.assert_array_equal(second.jvp, first.jvp)
        assert second.receipt.residual == first.receipt.residual
        assert second.receipt.jvp == first.receipt.jvp
        assert second.receipt.receipt_hash == first.receipt.receipt_hash

        zero = context.evaluate_residual_jvp(
            np.zeros(plan.dof_count, dtype="<f8")
        )
        assert zero.residual is not None and zero.jvp is not None
        assert zero.receipt.status == "verified"
        assert zero.receipt.parity is not None
        assert zero.receipt.parity.zero_direction_exact is True
        np.testing.assert_array_equal(
            zero.jvp, np.zeros(plan.dof_count, dtype="<f8")
        )
        np.testing.assert_array_equal(zero.residual, first.residual)

        cumulative = context.receipt().telemetry
        assert cumulative.kernel_launch_attempt_count == 3
        assert cumulative.kernel_launch_count == 3
        assert (
            cumulative.h2d_operation_count - opening.telemetry.h2d_operation_count
            == 3
        )
        assert (
            cumulative.d2h_operation_count - opening.telemetry.d2h_operation_count
            == 6
        )
        assert cumulative.fallback_count == 0
    finally:
        context.close()

    closed = context.receipt()
    assert closed.status == "context_closed"
    assert closed.telemetry.child_deallocation_attempt_count == 8
    assert closed.telemetry.child_deallocation_success_count == 8
    assert closed.telemetry.current_device_payload_bytes == 0
    assert closed.telemetry.fallback_count == 0
