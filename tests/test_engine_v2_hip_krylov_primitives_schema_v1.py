from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator
import pytest

from tests.test_engine_v2_hip_krylov_primitives_context_v1 import (
    _close_all,
    _open_primitives,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "src/structural_analysis/schemas"
SCHEMA_FILES = {
    "context": "hip_krylov_primitives_context_v2.schema.json",
    "batch": "hip_krylov_primitives_batch_v1.schema.json",
    "evaluation": "hip_krylov_primitives_evaluation_v1.schema.json",
}
LEGACY_CONTEXT_SCHEMA = "hip_krylov_primitives_context_v1.schema.json"


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / SCHEMA_FILES[name]).read_text(encoding="utf-8"))


def _errors(name: str, payload: dict[str, Any]) -> list[Any]:
    return list(Draft202012Validator(_schema(name)).iter_errors(payload))


@pytest.fixture(scope="module")
def live_payloads() -> Iterator[dict[str, dict[str, Any]]]:
    *_, parent_open, resident_open, free_open, _, _, opened = _open_primitives()
    context = opened.context
    assert context is not None
    try:
        batch = context.enqueue_primitive_batch()
        evaluation = context.evaluate_for_verification()
        assert batch.status == "enqueued"
        assert evaluation.receipt.status == "verified"
        yield {
            "context": opened.receipt.to_dict(),
            "batch": batch.to_dict(),
            "evaluation": evaluation.receipt.to_dict(),
        }
    finally:
        _close_all(opened, free_open, resident_open, parent_open)


def test_draft_2020_12_schemas_self_check_and_accept_live_payloads(
    live_payloads: dict[str, dict[str, Any]],
) -> None:
    for name, payload in live_payloads.items():
        schema = _schema(name)
        Draft202012Validator.check_schema(schema)
        assert list(Draft202012Validator(schema).iter_errors(payload)) == []


def test_legacy_context_v1_schema_artifact_remains_well_formed() -> None:
    schema = json.loads((SCHEMAS / LEGACY_CONTEXT_SCHEMA).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_context_schema_rejects_extra_telemetry_and_claim_fields(
    live_payloads: dict[str, dict[str, Any]],
) -> None:
    telemetry = deepcopy(live_payloads["context"])
    telemetry["telemetry"]["forged_extra_count"] = 0
    assert _errors("context", telemetry)

    claims = deepcopy(live_payloads["context"])
    claims["claims"]["forged_extra_claim"] = False
    assert _errors("context", claims)

    missing_backend = deepcopy(live_payloads["context"])
    missing_backend["actual_backend"] = None
    assert _errors("context", missing_backend)

    false_ready_claim = deepcopy(live_payloads["context"])
    false_ready_claim["claims"]["dot_primitive_ready"] = False
    assert _errors("context", false_ready_claim)


def test_batch_schema_rejects_extras_and_binds_reason_to_status(
    live_payloads: dict[str, dict[str, Any]],
) -> None:
    payload = live_payloads["batch"]

    delta = deepcopy(payload)
    delta["telemetry_delta"]["forged_extra_count"] = 0
    assert _errors("batch", delta)

    claims = deepcopy(payload)
    claims["claims"]["forged_extra_claim"] = False
    assert _errors("batch", claims)

    enqueued_with_reason = deepcopy(payload)
    enqueued_with_reason["reason"] = {"code": "forged", "detail": "forged"}
    assert _errors("batch", enqueued_with_reason)

    unavailable = deepcopy(payload)
    unavailable["status"] = "unavailable"
    unavailable["reason"] = {"code": "unavailable", "detail": "unavailable"}
    unavailable["telemetry_delta"]["lassq_finalize_launch_success_count"] = 0
    unavailable["claims"]["stable_l2_reduction_enqueued"] = False
    assert _errors("batch", unavailable) == []

    unavailable_without_reason = deepcopy(unavailable)
    unavailable_without_reason["reason"] = None
    assert _errors("batch", unavailable_without_reason)


@pytest.mark.parametrize("field", ["batch", "parity", "arrays"])
def test_verified_evaluation_schema_rejects_empty_nested_objects(
    live_payloads: dict[str, dict[str, Any]],
    field: str,
) -> None:
    forged = deepcopy(live_payloads["evaluation"])
    forged[field] = {}
    assert _errors("evaluation", forged)


def test_evaluation_schema_rejects_all_nested_extra_fields(
    live_payloads: dict[str, dict[str, Any]],
) -> None:
    payload = live_payloads["evaluation"]

    cases = []
    evaluation_delta = deepcopy(payload)
    evaluation_delta["telemetry_delta"]["forged_extra_count"] = 0
    cases.append(evaluation_delta)

    nested_batch_delta = deepcopy(payload)
    nested_batch_delta["batch"]["telemetry_delta"]["forged_extra_count"] = 0
    cases.append(nested_batch_delta)

    nested_batch_claims = deepcopy(payload)
    nested_batch_claims["batch"]["claims"]["forged_extra_claim"] = False
    cases.append(nested_batch_claims)

    parity = deepcopy(payload)
    parity["parity"]["forged_extra_claim"] = False
    cases.append(parity)

    metric = deepcopy(payload)
    metric["parity"]["metrics"]["dot_result"]["forged_extra_metric"] = 0
    cases.append(metric)

    descriptor = deepcopy(payload)
    descriptor["arrays"]["work_x"]["forged_extra_descriptor"] = 0
    cases.append(descriptor)

    arrays = deepcopy(payload)
    arrays["arrays"]["forged_extra_array"] = deepcopy(arrays["arrays"]["work_x"])
    cases.append(arrays)

    for forged in cases:
        assert _errors("evaluation", forged)


def test_evaluation_schema_requires_exact_six_success_arrays(
    live_payloads: dict[str, dict[str, Any]],
) -> None:
    forged = deepcopy(live_payloads["evaluation"])
    forged["arrays"].pop("norm_result")
    assert _errors("evaluation", forged)


def test_evaluation_schema_binds_status_reason_arrays_and_parity(
    live_payloads: dict[str, dict[str, Any]],
) -> None:
    verified = live_payloads["evaluation"]

    missing_batch = deepcopy(verified)
    missing_batch["batch"] = None
    assert _errors("evaluation", missing_batch)

    verified_false = deepcopy(verified)
    verified_false["parity"]["passed"] = False
    assert _errors("evaluation", verified_false)

    verified_with_failed_metric = deepcopy(verified)
    verified_with_failed_metric["parity"]["metrics"]["dot_result"]["passed"] = False
    assert _errors("evaluation", verified_with_failed_metric)

    parity_failed = deepcopy(verified)
    parity_failed["status"] = "parity_failed"
    parity_failed["parity"]["passed"] = False
    parity_failed["parity"]["metrics"]["dot_result"]["passed"] = False
    parity_failed["parity"]["metrics"]["dot_result"]["max_scaled_error"] = 2.0
    assert _errors("evaluation", parity_failed) == []

    parity_failed_true = deepcopy(parity_failed)
    parity_failed_true["parity"]["passed"] = True
    assert _errors("evaluation", parity_failed_true)

    unavailable = deepcopy(verified)
    unavailable["status"] = "unavailable"
    unavailable["reason"] = {"code": "unavailable", "detail": "unavailable"}
    unavailable["arrays"] = {}
    unavailable["parity"] = None
    assert _errors("evaluation", unavailable) == []

    unavailable_without_reason = deepcopy(unavailable)
    unavailable_without_reason["reason"] = None
    assert _errors("evaluation", unavailable_without_reason)

    unavailable_with_arrays = deepcopy(unavailable)
    unavailable_with_arrays["arrays"] = deepcopy(verified["arrays"])
    assert _errors("evaluation", unavailable_with_arrays)

    unavailable_with_parity = deepcopy(unavailable)
    unavailable_with_parity["parity"] = deepcopy(verified["parity"])
    assert _errors("evaluation", unavailable_with_parity)
