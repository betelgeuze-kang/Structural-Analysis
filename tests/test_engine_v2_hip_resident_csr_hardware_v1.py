from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.context import (
    HipAssemblyContextError,
    open_hip_assembly_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.plan import (
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.resident import (
    HipResidentCsrContextError,
    open_hip_resident_csr_execution_context,
    validate_hip_resident_csr_evaluation,
)
from structural_analysis.engine_v2.backends.hip.native import probe_hip_capability
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.state_ir import create_initial_state
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


def test_native_assembly_to_same_stream_resident_residual_jvp_contract() -> None:
    required = os.environ.get("ENGINE_V2_REQUIRE_HIP_HARDWARE") == "1"
    architectures = _local_architectures()
    if not architectures:
        if required:
            pytest.fail("Required HIP hardware lane detected no real gfx agent.")
        pytest.skip("No real gfx agent was detected; no fallback was used.")
    capability = probe_hip_capability(device_ordinal=0)
    if capability.status != "ready":
        assert not capability.fallback_used
        if required:
            pytest.fail(
                "Required HIP hardware capability is unavailable: "
                f"{capability.status_code}"
            )
        pytest.skip(
            "Native HIP capability unavailable without fallback: "
            f"{capability.status_code}"
        )

    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_AXIAL"
    )
    plan = compile_execution_plan_v2(buffers)
    assembly_plan = compile_hip_assembly_plan_v1(buffers, plan)
    try:
        assembly_open = open_hip_assembly_execution_context(
            buffers,
            plan,
            assembly_plan,
            verify_cpu_parity=True,
            device_ordinal=0,
            architecture=architectures[0],
        )
    except HipAssemblyContextError as exc:
        if required:
            pytest.fail(f"Required native device assembly failed: {exc.code}")
        pytest.skip(f"Native device assembly failed without fallback: {exc.code}")
    if not assembly_open.ready or assembly_open.context is None:
        assert assembly_open.receipt.telemetry.fallback_count == 0
        if assembly_open.context is not None:
            try:
                assembly_open.context.close()
            except HipAssemblyContextError:
                pass
        if required:
            pytest.fail(
                "Required native device assembly was unavailable: "
                f"{assembly_open.receipt.status}"
            )
        pytest.skip(
            "Native device assembly unavailable without fallback: "
            f"{assembly_open.receipt.status}"
        )

    parent = assembly_open.context
    resident = None
    try:
        try:
            resident_open = open_hip_resident_csr_execution_context(
                parent,
                create_initial_state(plan),
                architecture=architectures[0],
            )
        except HipResidentCsrContextError as exc:
            if required:
                pytest.fail(f"Required native resident consumer failed: {exc.code}")
            pytest.skip(f"Native resident consumer failed without fallback: {exc.code}")
        if not resident_open.ready or resident_open.context is None:
            assert resident_open.receipt.telemetry.fallback_count == 0
            if resident_open.context is not None:
                try:
                    resident_open.context.close()
                except HipResidentCsrContextError:
                    pass
            if required:
                pytest.fail(
                    "Required native resident consumer was unavailable: "
                    f"{resident_open.receipt.status}"
                )
            pytest.skip(
                "Native resident consumer unavailable without fallback: "
                f"{resident_open.receipt.status}"
            )
        resident = resident_open.context
        opening = resident_open.receipt
        assert opening.actual_backend == "hip"
        assert opening.evidence_scope == "native_hiprtc_composite"
        assert opening.bindings.residual_kernel_origin == "internally_compiled"
        assert opening.promotion_eligible is False
        assert opening.telemetry.new_stream_create_count == 0
        assert opening.telemetry.consumer_csr_symbolic_h2d_bytes == 0
        assert opening.telemetry.consumer_csr_numeric_h2d_bytes == 0
        assert opening.telemetry.consumer_load_h2d_bytes == 0
        assert opening.telemetry.owned_allocation_success_count == 4
        assert opening.telemetry.h2d_operation_success_count == 1
        assert opening.telemetry.fallback_count == 0

        indices = np.arange(1, plan.dof_count + 1, dtype="<f8")
        direction = np.where(indices.astype(np.int64) % 2, -indices, indices) * 1e-7
        evaluation = resident.evaluate_for_verification(direction)
        assert evaluation.receipt.status == "verified"
        assert evaluation.receipt.parity is not None
        assert evaluation.receipt.parity.passed
        assert evaluation.receipt.claims.assembled_device_csr_consumed
        assert evaluation.receipt.claims.cpu_reference_parity_verified
        assert not evaluation.receipt.claims.iteration_host_copy_zero
        assert evaluation.receipt.telemetry_delta.fallback_count == 0
        validate_hip_resident_csr_evaluation(evaluation, expected_context=resident)
    finally:
        if resident is not None:
            resident.close()
        parent.close()
    assert parent.receipt().telemetry.current_device_payload_bytes == 0
