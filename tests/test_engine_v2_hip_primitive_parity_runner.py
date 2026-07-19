from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from structural_analysis.engine_v2_backends.hip_primitive_parity import (
    HIP_PRIMITIVE_OUTPUT_VERSION,
    build_engine_v2_cpu_hip_parity_reference,
    cpu_hip_primitive_reference,
    parity_receipt_hash,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_engine_v2_hip_primitive_parity.py"
SPEC = importlib.util.spec_from_file_location(
    "run_engine_v2_hip_primitive_parity",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _runtime_output() -> dict:
    reference = build_engine_v2_cpu_hip_parity_reference()
    return {
        "schema_version": HIP_PRIMITIVE_OUTPUT_VERSION,
        "runtime_status": "success",
        "runtime_status_code": 0,
        "backend": "amd_rocm_hip",
        "cpu_backend": False,
        "same_stream_ordering": True,
        "blocking_d2h_synchronization_count": 1,
        "kernel_invocation_count": 6,
        "production_full_recurrence_claim": False,
        "preconditioner_profile": (
            "operator_derived_left_scaled_jacobi_right.v1"
        ),
        "reduction_profile": "single_thread_ascending_index_fp64_probe.v1",
        "device_index": 0,
        "device_name": "AMD Radeon RX 6900 XT",
        "gcn_arch_name": "gfx1030",
        "fixture_dimension": reference.fixture.dimension,
        "fixture_nnz": reference.fixture.nnz,
        "operations": cpu_hip_primitive_reference(reference.fixture),
    }


def test_receipt_records_actual_primitive_scope_without_recurrence_promotion() -> None:
    receipt = module.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm-6.0.2/bin/hipcc",
        compiler_version_output="HIP version: 6.0.32831\nclang 17.0.0\n",
        binary_sha256="sha256:" + "f" * 64,
    )

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["receipt_hash"] == parity_receipt_hash(receipt)
    assert receipt["cpu_reference"]["converged"] is True
    assert receipt["hardware_execution"]["actual_hardware"] is True
    assert receipt["hardware_execution"]["gcn_arch_name"] == "gfx1030"
    assert receipt["primitive_comparison"]["contract_pass"] is True
    assert receipt["claims"]["gfx1030_local_primitive_parity"] is True
    assert receipt["claims"][
        "gfx1030_local_operator_derived_scaled_jacobi_apply_parity"
    ] is True
    assert receipt["claims"]["full_fgmres_recurrence_parity"] is False
    assert receipt["claims"]["device_resident_restart_checkpoint"] is False
    assert receipt["claims"]["independent_gfx1100_parity"] is False
    assert receipt["claims"]["signed_receipt"] is False
    assert receipt["claims"]["performance"] is False
    assert "full_fgmres_recurrence_not_covered_by_this_primitive_receipt" in (
        receipt["blockers_remaining"]
    )
    assert (
        "device_resident_restart_checkpoint_not_covered_by_this_primitive_receipt"
        in receipt["blockers_remaining"]
    )
    assert "production_preconditioner_apply_not_verified" not in (
        receipt["blockers_remaining"]
    )
    assert "production_scale_preconditioner_effectiveness_not_verified" in (
        receipt["blockers_remaining"]
    )


def test_receipt_validation_rejects_stale_hash() -> None:
    receipt = module.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm-6.0.2/bin/hipcc",
        compiler_version_output="HIP version: 6.0.32831\n",
        binary_sha256="sha256:" + "f" * 64,
    )
    tampered = deepcopy(receipt)
    tampered["hardware_execution"]["runtime_output"]["operations"]["dot"] += 1.0

    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        module.validate_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_check_reports_missing_receipt(tmp_path: Path) -> None:
    ok, message = module.check_committed_receipt(
        repo_root=ROOT,
        out=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("engine_v2_cpu_hip_primitive_receipt_missing:")


def test_committed_cpu_hip_primitive_receipt_is_current() -> None:
    ok, message = module.check_committed_receipt(repo_root=ROOT)

    assert ok is True
    assert message == "engine_v2_cpu_hip_primitive_receipt_consistent"
