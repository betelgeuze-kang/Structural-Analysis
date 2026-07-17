from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend import (  # noqa: E402
    fgmres_fixed_rank_coarse_slot_plan_v1 as slot_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_context_v2 import (  # noqa: E402
    HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
    HIP_FGMRES_RTC_SOURCE_SHA256_V2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixed_rank_coarse_slot_plan_v1 import (  # noqa: E402
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1,
    HipFgmresFixedRankCoarseSlotPlanV1Error,
    hip_fgmres_fixed_rank_coarse_slot_kernel_abi_hash_v1,
    hip_fgmres_fixed_rank_coarse_slot_kernel_abi_payload_v1,
    hip_fgmres_fixed_rank_coarse_slot_source_components_v1,
    hip_fgmres_fixed_rank_coarse_slot_source_v1,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.rtc_backend.rtc import (  # noqa: E402
    _compile_fixed_source,
    _load_hiprtc_api,
)


KERNEL_DIRECTORY = SRC_ROOT / "structural_analysis/engine_v2/assembly_backend/kernels"
RECURRENCE = KERNEL_DIRECTORY / "engine_v2_fgmres_v2.hip.cpp"
COARSE = KERNEL_DIRECTORY / "engine_v2_fgmres_fixed_rank_coarse_v1.hip.cpp"
SLOT = KERNEL_DIRECTORY / "engine_v2_fgmres_fixed_rank_coarse_slot_v1.hip.cpp"


def test_combined_source_preserves_frozen_component_bytes_and_order() -> None:
    recurrence = RECURRENCE.read_bytes()
    coarse = COARSE.read_bytes()
    slot = SLOT.read_bytes()
    source = hip_fgmres_fixed_rank_coarse_slot_source_v1()
    components = hip_fgmres_fixed_rank_coarse_slot_source_components_v1()

    assert components["recurrence"]["sha256"] == HIP_FGMRES_RTC_SOURCE_SHA256_V2
    assert components["recurrence"]["byte_length"] == len(recurrence)
    assert components["coarse"]["byte_length"] == len(coarse)
    assert components["slot"]["byte_length"] == len(slot)
    assert components["combined"]["byte_length"] == len(source)
    assert source.startswith(recurrence + b"\nnamespace engine_v2_coarse_v1 {\n")
    assert coarse in source
    assert source.endswith(slot)
    assert source.index(recurrence) < source.index(coarse) < source.index(slot)


def test_typed_slot_abi_has_one_logical_operation_and_four_physical_launches() -> None:
    first = hip_fgmres_fixed_rank_coarse_slot_kernel_abi_payload_v1()
    second = hip_fgmres_fixed_rank_coarse_slot_kernel_abi_payload_v1()

    assert first == second
    assert first is not second
    assert first["frozen_recurrence_abi_hash"] == (
        HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2
    )
    assert first["logical_operation"] == {
        "schedule_row": "APPLY_JACOBI_INDEXED",
        "selected_kind": "fixed_rank_coarse",
        "logical_operation_count": 1,
        "jacobi_kernel_launch_count": 0,
        "recurrence_schedule_epoch_claim_count": 1,
        "recurrence_pending_reservation_count": 1,
    }
    assert first["physical_launches"]["count"] == 4
    assert tuple(first["physical_launches"]["symbols"]) == (
        HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1
    )
    assert first["inactive_padding"] == {
        "device_status_bit": 31,
        "host_branch_required": False,
        "schedule_epoch_claimed": False,
        "numeric_inputs_read": False,
        "preconditioned_basis_z_written": False,
    }
    assert first["claim_boundary"]["logical_jacobi_row_replaced_in_source_contract"]
    assert not first["claim_boundary"]["live_runtime_integration_performed"]
    assert not first["claim_boundary"]["coarse_device_status_directly_terminal_bound"]
    assert (
        canonical_hash(first) == hip_fgmres_fixed_rank_coarse_slot_kernel_abi_hash_v1()
    )


def test_slot_supplement_claims_epoch_and_makes_inactive_apply_byte_preserving() -> (
    None
):
    source = SLOT.read_text(encoding="utf-8")
    assert source.count("engine_v2_fgmres_fixed_rank_coarse_slot_gate_v1") == 1
    assert source.count("engine_v2_fgmres_fixed_rank_coarse_slot_apply_v1") == 1
    assert "engine_v2_claim_schedule_or_fail(" in source
    assert "engine_v2_common_state_valid(" in source
    assert "kCoarseSlotInactive = 1u << 31" in source
    inactive = source.index("if ((status & kCoarseSlotInactive) != 0u)")
    first_slot_write = source.index("preconditioned_basis_z[vector_offset + row]")
    assert inactive < first_slot_write
    for forbidden in (
        "hipMalloc",
        "hipFree",
        "hipMemcpy",
        "hipStreamSynchronize",
        "row_ptr",
        "column_indices",
    ):
        assert forbidden not in source


def test_frozen_recurrence_source_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    changed = tmp_path / RECURRENCE.name
    changed.write_bytes(RECURRENCE.read_bytes() + b"\n// drift\n")
    monkeypatch.setattr(slot_module, "_RECURRENCE_PATH", changed)

    with pytest.raises(HipFgmresFixedRankCoarseSlotPlanV1Error) as exc_info:
        hip_fgmres_fixed_rank_coarse_slot_source_v1()
    assert exc_info.value.code == "hip_fgmres_coarse_slot_recurrence_source_changed"


@pytest.mark.parametrize("architecture", ("gfx1030", "gfx1100"))
def test_combined_typed_slot_source_compiles_with_available_hiprtc(
    architecture: str,
) -> None:
    if not Path("/opt/rocm/lib/libhiprtc.so").exists():
        pytest.skip("libhiprtc is not installed")
    rtc = _load_hiprtc_api(None)
    code_object, compile_log = _compile_fixed_source(
        rtc,
        hip_fgmres_fixed_rank_coarse_slot_source_v1(),
        (
            f"--offload-arch={architecture}",
            "-O3",
            "-std=c++17",
            "-ffp-contract=off",
        ),
        program_name=SLOT.name,
    )
    assert code_object
    assert compile_log == ""


def test_combined_source_contains_exact_selected_symbols() -> None:
    source = hip_fgmres_fixed_rank_coarse_slot_source_v1()
    for symbol in HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1:
        assert source.count(symbol.encode()) == 1
