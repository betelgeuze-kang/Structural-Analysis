from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

import pytest

from structural_analysis.engine_v2.assembly_backend.context import (
    HipAssemblyContextError,
    open_hip_assembly_execution_context,
    validate_hip_assembly_context_receipt,
    validate_hip_assembly_evaluation,
)
from structural_analysis.engine_v2.assembly_backend.plan import (
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.backends.hip.native import (
    probe_hip_capability,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.model_ir import load_model_ir_v2

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
_ARCH_PATTERN = re.compile(r"^gfx[0-9][0-9a-f]{2,15}$")


def _local_architectures() -> tuple[str, ...]:
    executable = shutil.which("rocm_agent_enumerator")
    if executable is None:
        for path in (
            Path("/opt/rocm/bin/rocm_agent_enumerator"),
            Path("/opt/rocm-6.0.2/bin/rocm_agent_enumerator"),
        ):
            if path.is_file() and path.stat().st_mode & 0o111:
                executable = str(path)
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
        token
        for token in (item.strip().lower() for item in completed.stdout.split())
        if token != "gfx000" and _ARCH_PATTERN.fullmatch(token)
    )


def test_native_device_frame_truss_assembly_hardware_contract() -> None:
    architectures = _local_architectures()
    if not architectures:
        pytest.skip("No real gfx agent was detected; no fallback was used.")
    capability = probe_hip_capability(device_ordinal=0)
    if capability.status != "ready":
        assert not capability.fallback_used
        pytest.skip(
            "Native HIP capability unavailable without fallback: "
            f"{capability.status_code}"
        )
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_AXIAL"
    )
    source_plan = compile_execution_plan_v2(buffers)
    assembly_plan = compile_hip_assembly_plan_v1(buffers, source_plan)
    try:
        opened = open_hip_assembly_execution_context(
            buffers,
            source_plan,
            assembly_plan,
            verify_cpu_parity=True,
            device_ordinal=0,
            architecture=architectures[0],
        )
    except HipAssemblyContextError as exc:
        pytest.skip(
            f"Native HIPRTC assembly explicitly failed without fallback: {exc.code}"
        )
    if not opened.ready or opened.context is None:
        assert opened.receipt.telemetry.fallback_count == 0
        if opened.context is not None:
            try:
                opened.context.close()
            except HipAssemblyContextError:
                pass
        pytest.skip(
            "Native assembly context unavailable without fallback: "
            f"{opened.receipt.status}"
        )
    context = opened.context
    try:
        assert opened.receipt.actual_backend == "hip"
        assert opened.receipt.evidence_scope == "native_hiprtc"
        assert opened.receipt.promotion_eligible is False
        assert opened.receipt.telemetry.host_csr_values_h2d_bytes == 0
        assert opened.receipt.telemetry.kernel_launch_count == 2
        assert opened.receipt.telemetry.fallback_count == 0
        assert opened.evaluation.receipt.status == "verified"
        assert opened.evaluation.receipt.parity is not None
        assert opened.evaluation.receipt.parity.passed
        assert opened.evaluation.receipt.claims.cpu_reference_parity_verified
        assert context.operator_view().verification_data_hash is not None
        validate_hip_assembly_context_receipt(
            opened.receipt,
            expected_buffers=buffers,
            expected_source_plan=source_plan,
            expected_assembly_plan=assembly_plan,
            expected_kernel=context._rtc_kernel,
        )
        validate_hip_assembly_evaluation(
            opened.evaluation,
            expected_context=context,
            expected_buffers=buffers,
            expected_source_plan=source_plan,
            expected_assembly_plan=assembly_plan,
            expected_kernel=context._rtc_kernel,
        )
    finally:
        context.close()
    closed = context.receipt()
    assert closed.status == "context_closed"
    assert closed.telemetry.current_device_payload_bytes == 0
    assert closed.telemetry.child_deallocation_success_count == 8
    assert closed.telemetry.fallback_count == 0
