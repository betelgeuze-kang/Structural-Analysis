from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_case_parity_v1 as parity_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1,
    HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1,
    HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1,
    HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1,
    HipFgmresModelCaseParityBindingsV1,
    HipFgmresModelCaseParityClaimsV1,
    HipFgmresModelCaseParityDimensionsV1,
    HipFgmresModelCaseParityDiscreteComparisonV1,
    HipFgmresModelCaseParityReceiptV1,
    HipFgmresModelCaseParityResultV1,
    HipFgmresModelCaseParityTelemetryV1,
    HipFgmresModelCaseParityToleranceV1,
    HipFgmresModelCaseParityV1Error,
    HipFgmresModelCaseParityVectorComparisonV1,
    validate_hip_fgmres_model_case_parity_receipt_v1,
    validate_hip_fgmres_model_case_parity_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeObservationResultV1,
)
from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    HipDeviceIdentityResultV1,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import ExecutionPlanV2
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresReferenceResultV1,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_case_parity_v1.schema.json"
)
_ZERO_HASH = "sha256:" + "0" * 64
_VECTOR_NAMES = ("solution_x", "true_residual", "true_residual_replay")


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _case_id(bindings: HipFgmresModelCaseParityBindingsV1) -> str:
    return canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
            "execution_plan_hash": bindings.execution_plan_hash,
            "policy_hash": bindings.policy_hash,
            "terminal_observation_receipt_hash": (
                bindings.terminal_observation_receipt_hash
            ),
            "device_identity_receipt_hash": bindings.device_identity_receipt_hash,
        }
    )


def _bindings() -> HipFgmresModelCaseParityBindingsV1:
    values = {
        name: _hash(name)
        for name in (
            "model_ir_content_hash",
            "execution_plan_hash",
            "operator_hash",
            "numeric_snapshot_hash",
            "symbolic_reuse_hash",
            "partition_hash",
            "fgmres_plan_hash",
            "recurrence_plan_hash",
            "policy_hash",
            "terminal_observation_id",
            "terminal_observation_receipt_hash",
            "terminal_outcome_hash",
            "completion_export_context_id",
            "completion_export_receipt_hash",
            "completion_export_payload_hash",
            "global_context_id",
            "global_receipt_hash",
            "kernel_identity_hash",
            "kernel_source_sha256",
            "device_identity_receipt_hash",
            "runtime_library_sha256",
            "cpu_result_hash",
        )
    }
    return HipFgmresModelCaseParityBindingsV1(
        **values,
        execution_plan_id="SparsePlan:000000000000000000000001",
        fgmres_plan_id="HipFgmresPlan:000000000000000000000002",
        recurrence_plan_id="HipFgmresRecurrencePlan:000000000000000000000003",
        load_pattern_id="LC_WEAK",
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=0,
        device_uuid_bytes_hex="0102030405060708090a0b0c0d0e0f10",
        device_pci_bdf="0000:0b:00.0",
    )


def _vector(name: str) -> HipFgmresModelCaseParityVectorComparisonV1:
    return HipFgmresModelCaseParityVectorComparisonV1(
        name=name,  # type: ignore[arg-type]
        element_count=6,
        cpu_or_reference_sha256=_hash(f"{name}:cpu"),
        hip_or_candidate_sha256=_hash(f"{name}:hip"),
        maximum_absolute_error=0.0,
        l2_absolute_error=0.0,
        reference_l2=1.0,
        relative_l2_error=0.0,
        maximum_tolerance_ratio=0.0,
        relative_l2_tolerance_passed=True,
        absolute_linf_tolerance_passed=True,
        componentwise_tolerance_passed=True,
    )


def _discrete() -> HipFgmresModelCaseParityDiscreteComparisonV1:
    return HipFgmresModelCaseParityDiscreteComparisonV1(
        terminal_status_match=True,
        termination_code_match=True,
        iteration_count_match=True,
        restart_count_match=True,
        operator_apply_count_match=True,
        preconditioner_apply_count_match=True,
        restart_history_shape_match=True,
        restart_history_discrete_fields_match=True,
        restart_history_metrics_within_tolerance=True,
        terminal_metrics_within_tolerance=True,
        numerical_failure_absent=True,
    )


def _receipt() -> HipFgmresModelCaseParityReceiptV1:
    bindings = _bindings()
    draft = HipFgmresModelCaseParityReceiptV1(
        schema_version=HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
        status="case_parity_verified",
        evidence_scope=HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        promotion_eligible=False,
        case_id=_case_id(bindings),
        bindings=bindings,
        dimensions=HipFgmresModelCaseParityDimensionsV1(
            global_dof_count=12,
            free_dof_count=6,
            reduced_csr_nnz=36,
            restart_dimension=2,
            max_iterations=4,
            maximum_restart_count=2,
            populated_restart_row_count=1,
        ),
        tolerance=HipFgmresModelCaseParityToleranceV1(),
        discrete=_discrete(),
        vectors=tuple(_vector(name) for name in _VECTOR_NAMES),
        telemetry=HipFgmresModelCaseParityTelemetryV1(),
        claims=HipFgmresModelCaseParityClaimsV1(),
        receipt_hash=_ZERO_HASH,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            parity_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _coherently_rehash(
    receipt: HipFgmresModelCaseParityReceiptV1,
    **changes: Any,
) -> HipFgmresModelCaseParityReceiptV1:
    draft = replace(receipt, **changes, receipt_hash=_ZERO_HASH)
    if "bindings" in changes:
        draft = replace(draft, case_id=_case_id(draft.bindings))
    return replace(
        draft,
        receipt_hash=canonical_hash(
            parity_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _uninitialized(exact_type: type[Any]) -> Any:
    return object.__new__(exact_type)


def _result_sources() -> tuple[Any, Any, Any, Any]:
    return (
        _uninitialized(CpuFgmresReferenceResultV1),
        _uninitialized(HipFgmresTerminalOutcomeObservationResultV1),
        _uninitialized(HipDeviceIdentityResultV1),
        _uninitialized(ExecutionPlanV2),
    )


def _result(
    receipt: HipFgmresModelCaseParityReceiptV1,
    sources: tuple[Any, Any, Any, Any],
) -> HipFgmresModelCaseParityResultV1:
    cpu, observation, device, plan = sources
    return HipFgmresModelCaseParityResultV1(
        receipt=receipt,
        _cpu_result=cpu,
        _observation_result=observation,
        _device_identity_result=device,
        _source_execution_plan=plan,
    )


def test_schema_and_canonical_receipt_are_strict_fixed_and_nonpromoting() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    receipt = _receipt()

    assert validate_hip_fgmres_model_case_parity_receipt_v1(receipt) is receipt
    assert not list(validator.iter_errors(receipt.to_dict()))
    assert receipt.tolerance.relative_tolerance == 1.0e-8
    assert receipt.tolerance.absolute_tolerance == 1.0e-12
    assert not receipt.tolerance.caller_relaxation_allowed
    assert receipt.claims.single_model_case_numerical_parity_verified
    assert not receipt.claims.full_model_family_parity_verified
    assert not receipt.claims.multi_architecture_parity_verified
    assert not receipt.claims.signed_evidence
    assert not receipt.claims.commercial_ready
    assert not receipt.promotion_eligible

    extra = receipt.to_dict()
    extra["untrusted"] = True
    assert list(validator.iter_errors(extra))


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    (
        (
            lambda receipt: replace(receipt, receipt_hash=_ZERO_HASH),
            "hip_fgmres_model_case_parity_receipt_hash_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                actual_backend="test_double",
            ),
            "hip_fgmres_model_case_parity_schema_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                tolerance=replace(receipt.tolerance, relative_tolerance=1.0e-7),
            ),
            "hip_fgmres_model_case_parity_schema_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                claims=replace(receipt.claims, signed_evidence=True),
            ),
            "hip_fgmres_model_case_parity_schema_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                dimensions=replace(receipt.dimensions, maximum_restart_count=3),
            ),
            "hip_fgmres_model_case_parity_dimension_invalid",
        ),
        (
            lambda receipt: _coherently_rehash(
                receipt,
                vectors=(
                    replace(receipt.vectors[0], element_count=5),
                    *receipt.vectors[1:],
                ),
            ),
            "hip_fgmres_model_case_parity_vector_dimension_mismatch",
        ),
    ),
)
def test_receipt_validator_rejects_stale_and_coherently_rehashed_claims(
    mutate: Callable[[HipFgmresModelCaseParityReceiptV1], Any],
    expected_code: str,
) -> None:
    with pytest.raises(HipFgmresModelCaseParityV1Error) as caught:
        validate_hip_fgmres_model_case_parity_receipt_v1(mutate(_receipt()))
    assert caught.value.code == expected_code


def test_result_validator_replays_exact_sources_and_rejects_plan_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt()
    sources = _result_sources()
    result = _result(receipt, sources)
    cpu, observation, device, plan = sources

    monkeypatch.setattr(
        parity_module,
        "_evaluate_sources",
        lambda actual_cpu, actual_observation, actual_device: (
            receipt,
            plan,
        ),
    )
    assert (
        validate_hip_fgmres_model_case_parity_result_v1(
            result,
            expected_cpu_result=cpu,
            expected_observation_result=observation,
            expected_device_identity_result=device,
        )
        is result
    )

    other_plan = _uninitialized(ExecutionPlanV2)
    monkeypatch.setattr(
        parity_module,
        "_evaluate_sources",
        lambda *_args: (receipt, other_plan),
    )
    with pytest.raises(HipFgmresModelCaseParityV1Error) as caught:
        validate_hip_fgmres_model_case_parity_result_v1(result)
    assert (
        caught.value.code
        == "hip_fgmres_model_case_parity_execution_plan_identity_changed"
    )


@pytest.mark.parametrize("source_name", ("cpu", "observation", "device"))
def test_result_validator_requires_exact_expected_source_identity(
    monkeypatch: pytest.MonkeyPatch,
    source_name: str,
) -> None:
    receipt = _receipt()
    sources = _result_sources()
    result = _result(receipt, sources)
    cpu, observation, device, _plan = sources
    unexpected = {
        "cpu": _uninitialized(CpuFgmresReferenceResultV1),
        "observation": _uninitialized(HipFgmresTerminalOutcomeObservationResultV1),
        "device": _uninitialized(HipDeviceIdentityResultV1),
    }
    called = False

    def forbidden_replay(*_args: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("source mismatch must fail before replay")

    monkeypatch.setattr(parity_module, "_evaluate_sources", forbidden_replay)
    expected = {
        "expected_cpu_result": unexpected["cpu"] if source_name == "cpu" else cpu,
        "expected_observation_result": (
            unexpected["observation"] if source_name == "observation" else observation
        ),
        "expected_device_identity_result": (
            unexpected["device"] if source_name == "device" else device
        ),
    }
    with pytest.raises(HipFgmresModelCaseParityV1Error) as caught:
        validate_hip_fgmres_model_case_parity_result_v1(result, **expected)
    assert (
        caught.value.code
        == {
            "cpu": "hip_fgmres_model_case_parity_cpu_source_mismatch",
            "observation": "hip_fgmres_model_case_parity_observation_source_mismatch",
            "device": "hip_fgmres_model_case_parity_device_source_mismatch",
        }[source_name]
    )
    assert not called


@pytest.mark.parametrize(
    "forge",
    (
        lambda receipt: _coherently_rehash(
            receipt,
            bindings=replace(
                receipt.bindings,
                compiled_architecture="gfx1100",
                runtime_architecture_base="gfx1100",
            ),
        ),
        lambda receipt: _coherently_rehash(
            receipt,
            bindings=replace(receipt.bindings, cpu_result_hash=_hash("other-cpu")),
        ),
        lambda receipt: _coherently_rehash(
            receipt,
            bindings=replace(
                receipt.bindings,
                device_identity_receipt_hash=_hash("other-device"),
            ),
        ),
        lambda receipt: _coherently_rehash(
            receipt,
            vectors=(
                replace(
                    receipt.vectors[0],
                    hip_or_candidate_sha256=_hash("other-solution"),
                ),
                *receipt.vectors[1:],
            ),
        ),
    ),
    ids=("architecture_relabel", "cpu_relabel", "device_relabel", "vector_relabel"),
)
def test_coherent_serialized_relabel_cannot_replace_process_local_result(
    monkeypatch: pytest.MonkeyPatch,
    forge: Callable[
        [HipFgmresModelCaseParityReceiptV1], HipFgmresModelCaseParityReceiptV1
    ],
) -> None:
    receipt = _receipt()
    forged = forge(receipt)
    assert validate_hip_fgmres_model_case_parity_receipt_v1(forged) is forged
    sources = _result_sources()
    result = _result(forged, sources)
    plan = sources[3]
    monkeypatch.setattr(
        parity_module,
        "_evaluate_sources",
        lambda *_args: (receipt, plan),
    )

    with pytest.raises(HipFgmresModelCaseParityV1Error) as caught:
        validate_hip_fgmres_model_case_parity_result_v1(result)
    assert caught.value.code == "hip_fgmres_model_case_parity_replay_mismatch"


def test_discrete_cpu_status_or_count_mismatch_fails_closed() -> None:
    cpu = SimpleNamespace(
        status="converged",
        termination_code="converged_happy_breakdown",
        iteration_count=2,
        restart_count=1,
        operator_apply_count=4,
        preconditioner_apply_count=2,
        history=(),
    )
    counters = SimpleNamespace(
        effective_iterations=2,
        effective_restarts=1,
        operator_apply_count=4,
        preconditioner_apply_count=2,
    )
    matching = SimpleNamespace(
        terminal_status="converged",
        termination_code="converged_happy_breakdown",
        counters=counters,
    )

    parity_module._validate_discrete_parity(cpu, matching, ())
    for mismatched in (
        SimpleNamespace(
            terminal_status="max_iterations",
            termination_code=matching.termination_code,
            counters=counters,
        ),
        SimpleNamespace(
            terminal_status=matching.terminal_status,
            termination_code=matching.termination_code,
            counters=SimpleNamespace(
                effective_iterations=1,
                effective_restarts=1,
                operator_apply_count=4,
                preconditioner_apply_count=2,
            ),
        ),
    ):
        with pytest.raises(HipFgmresModelCaseParityV1Error) as caught:
            parity_module._validate_discrete_parity(cpu, mismatched, ())
        assert caught.value.code == "hip_fgmres_model_case_parity_discrete_mismatch"


def test_fixed_componentwise_vector_tolerance_accepts_boundary_and_rejects_next() -> (
    None
):
    reference = np.array([0.0, 1.0, -2.0], dtype="<f8")
    tolerance = (
        HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
        + HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1 * np.abs(reference)
    )
    within = reference + 0.5 * tolerance

    row = parity_module._compare_vector("solution_x", reference, within)
    assert row.componentwise_tolerance_passed
    assert row.maximum_tolerance_ratio == pytest.approx(0.5, rel=1.0e-8)

    outside = reference.copy()
    outside[0] = np.nextafter(tolerance[0], np.inf)
    with pytest.raises(HipFgmresModelCaseParityV1Error) as caught:
        parity_module._compare_vector("solution_x", reference, outside)
    assert caught.value.code == "hip_fgmres_model_case_parity_vector_mismatch"


def test_signed_zero_is_rejected_in_source_vectors_policy_and_receipt_metrics() -> None:
    vector = np.array([-0.0], dtype="<f8")
    with pytest.raises(HipFgmresModelCaseParityV1Error) as vector_error:
        parity_module._exact_f64_vector(vector, 1)
    assert vector_error.value.code == "hip_fgmres_model_case_parity_vector_invalid"

    policy = SimpleNamespace(
        max_iterations=1,
        absolute_tolerance=-0.0,
        relative_tolerance=1.0e-8,
    )
    with pytest.raises(HipFgmresModelCaseParityV1Error) as policy_error:
        parity_module._validate_fixed_policy(policy)
    assert policy_error.value.code == (
        "hip_fgmres_model_case_parity_negative_zero_policy"
    )

    receipt = _receipt()
    signed_zero_row = replace(receipt.vectors[0], maximum_absolute_error=-0.0)
    forged = _coherently_rehash(
        receipt,
        vectors=(signed_zero_row, *receipt.vectors[1:]),
    )
    with pytest.raises(HipFgmresModelCaseParityV1Error) as receipt_error:
        validate_hip_fgmres_model_case_parity_receipt_v1(forged)
    assert receipt_error.value.code == (
        "hip_fgmres_model_case_parity_vector_metric_invalid"
    )


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    (
        (
            lambda receipt: {
                "claims": replace(
                    receipt.claims,
                    exact_retained_execution_plan_snapshot_bound=1,
                )
            },
            "hip_fgmres_model_case_parity_schema_invalid",
        ),
        (
            lambda receipt: {
                "discrete": replace(receipt.discrete, terminal_status_match=1)
            },
            "hip_fgmres_model_case_parity_schema_invalid",
        ),
        (
            lambda receipt: {
                "telemetry": replace(receipt.telemetry, cpu_reference_result_count=1.0)
            },
            "hip_fgmres_model_case_parity_telemetry_type_invalid",
        ),
    ),
    ids=("integer_bool_claim", "integer_bool_discrete", "float_integer_telemetry"),
)
def test_nested_scalar_type_confusion_fails_even_after_coherent_rehash(
    changes: Callable[[HipFgmresModelCaseParityReceiptV1], dict[str, Any]],
    expected_code: str,
) -> None:
    receipt = _receipt()
    forged = _coherently_rehash(receipt, **changes(receipt))

    with pytest.raises(HipFgmresModelCaseParityV1Error) as caught:
        validate_hip_fgmres_model_case_parity_receipt_v1(forged)
    assert caught.value.code == expected_code
