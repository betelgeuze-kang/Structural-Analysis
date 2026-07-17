from __future__ import annotations

import importlib.resources
import json
from types import SimpleNamespace

from jsonschema import Draft202012Validator

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend
import structural_analysis.engine_v2.solvers as solvers
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_checkpoint_history_context_v1 as history_context,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_checkpoint_history_plan_v1 as history_plan,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_checkpoint_history_rtc_v1 as history_rtc,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_completion_export_v2 as completion_v2,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_general_history_parity_v2 as parity_v2,
)


def test_general_history_public_api_is_additive_and_unique() -> None:
    expected = {
        "compile_hip_fgmres_checkpoint_history_plan_v1": (
            history_plan.compile_hip_fgmres_checkpoint_history_plan_v1
        ),
        "open_hip_fgmres_checkpoint_history_context_v1": (
            history_context.open_hip_fgmres_checkpoint_history_context_v1
        ),
        "open_hip_fgmres_completion_export_context_v2": (
            completion_v2.open_hip_fgmres_completion_export_context_v2
        ),
        "attest_hip_fgmres_general_history_parity_v2": (
            parity_v2.attest_hip_fgmres_general_history_parity_v2
        ),
    }
    for name, value in expected.items():
        assert getattr(engine_v2, name) is value
        assert getattr(assembly_backend, name) is value
        assert name in engine_v2.__all__
        assert name in assembly_backend.__all__
    assert (
        engine_v2.solve_cpu_fgmres_checkpoint_history_v2
        is solvers.solve_cpu_fgmres_checkpoint_history_v2
    )
    assert len(engine_v2.__all__) == 1103
    assert len(assembly_backend.__all__) == 930
    assert len(solvers.__all__) == 47
    assert len(engine_v2.__all__) == len(set(engine_v2.__all__))
    assert len(assembly_backend.__all__) == len(set(assembly_backend.__all__))
    assert len(solvers.__all__) == len(set(solvers.__all__))


def test_general_history_leaf_module_exports_are_exact() -> None:
    assert len(history_plan.__all__) == 19
    assert len(history_rtc.__all__) == 10
    assert len(history_context.__all__) == 18
    assert len(completion_v2.__all__) == 18
    assert len(parity_v2.__all__) == 18
    for module in (
        history_plan,
        history_rtc,
        history_context,
        completion_v2,
        parity_v2,
    ):
        assert len(module.__all__) == len(set(module.__all__))
        assert all(not name.startswith("_") for name in module.__all__)


def test_checkpoint_history_kernel_is_packaged() -> None:
    kernels = importlib.resources.files(
        "structural_analysis.engine_v2.assembly_backend.kernels"
    )
    source = kernels.joinpath(
        "engine_v2_fgmres_checkpoint_history_v1.hip.cpp"
    ).read_bytes()
    assert source == history_rtc._fixed_source()
    assert (
        source.count(
            history_rtc.HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1.encode()
        )
        == 1
    )
    assert (
        source.count(
            history_rtc.HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1.encode()
        )
        == 1
    )


def test_general_history_schemas_are_packaged_and_draft_2020_12_valid() -> None:
    schemas = importlib.resources.files("structural_analysis.schemas")
    for name in (
        "hip_fgmres_checkpoint_history_plan_v1.schema.json",
        "cpu_fgmres_checkpoint_history_v2.schema.json",
        "hip_fgmres_checkpoint_history_context_v1.schema.json",
        "hip_fgmres_completion_export_v2.schema.json",
        "hip_fgmres_general_history_parity_v2.schema.json",
    ):
        schema = json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_completion_v2_telemetry_preserves_nested_export_counts() -> None:
    base = SimpleNamespace(
        receipt=SimpleNamespace(
            telemetry=SimpleNamespace(
                d2h_operation_attempt_count=3,
                d2h_operation_success_count=3,
                d2h_bytes_succeeded=792,
            )
        )
    )
    history = SimpleNamespace(
        receipt=SimpleNamespace(
            telemetry=SimpleNamespace(
                d2h_operation_attempt_count=2,
                d2h_operation_success_count=2,
                d2h_bytes_succeeded=1472,
            )
        )
    )

    row = completion_v2._telemetry(base, history)

    assert row.base_blocking_d2h_attempt_count == 3
    assert row.history_blocking_d2h_attempt_count == 2
    assert row.total_blocking_d2h_attempt_count == 5
    assert row.total_blocking_d2h_success_count == 5
    assert row.base_d2h_byte_count == 792
    assert row.history_d2h_byte_count == 1472
    assert row.total_d2h_byte_count == 2264
