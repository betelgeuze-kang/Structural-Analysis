"""Material-scope orchestration with producer stubs; no physical analyses."""

from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_constitutive_history as material
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json


CONFIG = public_api.PublicRCFiberFrameConfig(load_steps=2)
HISTORY = design.FiberFrameHistoryLimits(1.0, 1.0)
LIMITS = design.FiberFrameMaterialHistoryLimits(0.0, 0.0, 0.0)
TERMINAL = design.FiberFrameTerminalLimits(1.0, 1.0)
PRICES = design.FiberFrameMaterialPrices(100.0, 1.0, "KRW", "2026-09-09", "test only")


def _model():
    return load_neutral_json(
        Path(__file__).parents[1] / "examples/public_rc_fiber_frame_cantilever.json"
    )


def _seal(payload):
    payload["report_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )
    return material.FiberFrameConstitutiveHistory(
        "ready", True, payload["report_hash"], json.dumps(payload, allow_nan=False)
    )


@pytest.fixture
def producer(monkeypatch):
    """Stubs physical authority, retaining real consumer and quantity arithmetic."""
    model = _model()
    checkpoint = b"synthetic checkpoint bytes, not a solver artifact"
    calls = []
    clock = [0]
    result = SimpleNamespace(
        status="ready",
        result_hash=canonical_hash("synthetic result"),
        canonical_model_checksum=model.canonical_model_checksum,
        input_checksum=model.input_checksum,
        metrics={"solver_executed": True},
        contract_bindings={"problem_contract_hash": canonical_hash("problem")},
        checkpoint={
            "chain_hash": canonical_hash("chain"),
            "artifact_hash": canonical_hash("artifact"),
        },
        unsupported_features=[],
        node_displacements=[{"UX_m": 0.001, "UY_m": 0.0, "UZ_m": 0.0}],
        fiber_results=[{"strain": 0.001}],
        checkpoint_artifact=lambda: checkpoint,
    )
    result.to_dict = lambda: {
        "result_hash": result.result_hash,
        "metrics": deepcopy(result.metrics),
        "checkpoint": deepcopy(result.checkpoint),
        "unsupported_features": [],
    }
    validation = SimpleNamespace(
        contract_pass=True,
        exact_engineering_recovery=True,
        terminal_epoch=2,
        terminal_load_factor=1.0,
        fallback_count=0,
        regularization_count=0,
        to_dict=lambda: {"contract_pass": True},
    )
    response = {
        "source_result_hash": result.result_hash,
        "report_hash": canonical_hash("response"),
        "history": {
            "history_hash": canonical_hash("history"),
            "envelope": {
                "maximum_translation_m": 0.001,
                "maximum_absolute_fiber_strain": 0.001,
            },
            "steps": [
                {
                    "epoch": i,
                    "step_index": i,
                    "target_load_factor": i / 2,
                    "bindings": {
                        "checkpoint_state_hash": canonical_hash(i),
                        "parent_checkpoint_state_hash": canonical_hash(i - 1),
                    },
                    "recovery_hash": canonical_hash(("recovery", i)),
                    "metrics": {"total_dissipated_energy_mj": 0.0},
                }
                for i in (1, 2)
            ],
        },
    }
    payload = {
        "schema_version": material.SCHEMA_VERSION,
        "status": "ready",
        "contract_pass": True,
        "claim_boundary": deepcopy(material._CLAIMS),
        "bindings": {
            "source_result_hash": result.result_hash,
            "canonical_model_checksum": model.canonical_model_checksum,
            "input_checksum": model.input_checksum,
            "problem_contract_hash": result.contract_bindings["problem_contract_hash"],
            "checkpoint_chain_hash": result.checkpoint["chain_hash"],
            "checkpoint_artifact_hash": result.checkpoint["artifact_hash"],
            "checkpoint_artifact_byte_length": len(checkpoint),
            "response_history_report_hash": response["report_hash"],
            "engineering_history_hash": response["history"]["history_hash"],
        },
        "accepted_epoch_count": 2,
        "states": [],
    }
    for epoch in range(3):
        state = {"epoch": epoch, "materials": {}}
        for _, kind, field in design.MATERIAL_HISTORY_METRICS.values():
            state["materials"].setdefault(kind, {"fields": {}})["fields"][field] = {
                "maximum": 0.0
            }
        if epoch:
            row = response["history"]["steps"][epoch - 1]
            state.update(
                step_index=epoch,
                load_factor=row["target_load_factor"],
                checkpoint_state_hash=row["bindings"]["checkpoint_state_hash"],
                parent_checkpoint_state_hash=row["bindings"][
                    "parent_checkpoint_state_hash"
                ],
                engineering_recovery_hash=row["recovery_hash"],
                total_dissipated_energy_mj=0.0,
            )
        payload["states"].append(state)

    def analyze(*_):
        calls.append("public_analysis_stub")
        clock[0] += 10
        return result

    def recover(_):
        calls.append("response_history_stub")
        clock[0] += 20
        return SimpleNamespace(
            status="ready", contract_pass=True, to_dict=lambda: deepcopy(response)
        )

    def inspect(_):
        calls.append("constitutive_source_recovery_stub")
        clock[0] += 70
        return _seal(deepcopy(payload))

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", analyze)
    monkeypatch.setattr(
        public_api, "validate_public_rc_fiber_frame_result", lambda _: validation
    )
    monkeypatch.setattr(
        public_api, "recover_public_rc_fiber_frame_response_history", recover
    )
    monkeypatch.setattr(
        material, "inspect_public_rc_fiber_frame_constitutive_history", inspect
    )
    monkeypatch.setattr(design, "perf_counter_ns", lambda: clock[0])
    return SimpleNamespace(
        model=model, result=result, response=response, payload=payload, calls=calls
    )


def _evaluate(producer, *, limits=LIMITS):
    return design._evaluate_design(
        "baseline",
        producer.model,
        CONFIG,
        PRICES,
        TERMINAL,
        7850.0,
        history_limits=HISTORY,
        material_history_limits=limits,
    )


def test_material_inspection_is_source_bound_and_charged_without_extra_analysis(
    producer,
):
    row = _evaluate(producer)
    assert producer.calls == [
        "public_analysis_stub",
        "response_history_stub",
        "constitutive_source_recovery_stub",
    ]
    assert row["reference_and_quantity_wall_ns"] == 100
    assert row["full_material_history_verification_pass"] is True
    assert row["material_history_limit_status"] == "pass"
    assert row["violated_material_history_limits"] == []
    assert row["constitutive_history"]["bindings"] == producer.payload["bindings"]
    assert design._verified_for_requested_scopes(row)
    assert design._requested_limits_pass(row)


@pytest.mark.parametrize("metric", list(design.MATERIAL_HISTORY_METRICS))
def test_all_accepted_memory_states_are_screened_separately_from_strain(
    producer, metric
):
    _, kind, field = design.MATERIAL_HISTORY_METRICS[metric]
    # Deliberate producer-boundary envelope case; not a constitutive observation.
    producer.payload["states"][1]["materials"][kind]["fields"][field]["maximum"] = 0.2
    row = _evaluate(producer)
    assert row["terminal_limit_status"] == row["history_limit_status"] == "pass"
    assert row["full_material_history_verification_pass"] is True
    assert row["material_history_limit_status"] == "fail"
    assert row["violated_material_history_limits"] == [metric]
    assert row["performance"][metric] == 0.2
    assert not design._requested_limits_pass(row)


@pytest.mark.parametrize(
    "mutation",
    ["source", "chain", "history", "epoch", "parent", "energy", "boolean_count"],
)
def test_resealed_detached_material_source_is_unavailable_and_preserves_quantities(
    producer, mutation
):
    payload = producer.payload
    if mutation in ("source", "chain", "history"):
        key = {
            "source": "source_result_hash",
            "chain": "checkpoint_chain_hash",
            "history": "response_history_report_hash",
        }[mutation]
        payload["bindings"][key] = canonical_hash("wrong source")
    elif mutation == "epoch":
        payload["states"][1]["epoch"] = True
    elif mutation == "parent":
        payload["states"][1]["parent_checkpoint_state_hash"] = canonical_hash(
            "wrong parent"
        )
    elif mutation == "energy":
        payload["states"][1]["total_dissipated_energy_mj"] = 0.1
    else:
        payload["accepted_epoch_count"] = True
    row = _evaluate(producer)
    assert row["full_reference_verification_pass"] is True
    assert row["full_history_verification_pass"] is True
    assert row["result"] == producer.result.to_dict()
    assert row["quantities"] and row["material_estimate"]
    assert row["constitutive_history"] is None
    assert row["material_history_limit_status"] == "unavailable"
    assert row["material_history_failure"]["kind"] == "material_history_recovery_failed"
    assert not set(design.MATERIAL_HISTORY_METRICS).intersection(row["performance"])
    assert not design._verified_for_requested_scopes(row)


def test_missing_response_history_never_calls_material_producer(producer, monkeypatch):
    def fail(_):
        raise ValueError("unavailable response history")

    monkeypatch.setattr(
        public_api, "recover_public_rc_fiber_frame_response_history", fail
    )
    row = _evaluate(producer)
    assert producer.calls == ["public_analysis_stub"]
    assert row["quantities"] is not None
    assert row["material_history_failure"] == {
        "kind": "response_history_verification_unavailable"
    }


def test_opt_out_preserves_old_row_and_avoids_companion(producer):
    row = _evaluate(producer, limits=None)
    assert producer.calls == ["public_analysis_stub", "response_history_stub"]
    assert row["reference_and_quantity_wall_ns"] == 30
    for key in (
        "constitutive_history",
        "full_material_history_verification_pass",
        "material_history_limit_status",
        "violated_material_history_limits",
        "material_history_failure",
    ):
        assert key not in row


def test_material_requires_history_before_any_public_request(producer):
    with pytest.raises(ValueError, match="requires history_limits"):
        design._evaluate_design(
            "baseline",
            producer.model,
            CONFIG,
            PRICES,
            TERMINAL,
            7850.0,
            material_history_limits=LIMITS,
        )
    assert producer.calls == []


@pytest.mark.parametrize("baseline_unavailable", [False, True])
def test_m2_and_m4_choice_requires_material_verification_and_limits(
    producer, monkeypatch, baseline_unavailable
):
    base = _evaluate(producer)

    def evaluate(candidate_id, model, *_args, **options):
        assert options["material_history_limits"] == LIMITS
        row = deepcopy(base)
        row.update(
            candidate_id=candidate_id, model_checksum=model.canonical_model_checksum
        )
        row["material_estimate"]["total"] = 5.0 if candidate_id == "baseline" else 1.0
        if candidate_id == "baseline" and baseline_unavailable:
            row["full_material_history_verification_pass"] = False
            row["material_history_limit_status"] = "unavailable"
        elif candidate_id != "baseline":
            row["material_history_limit_status"] = "fail"
        return row

    monkeypatch.setattr(design, "_evaluate_design", evaluate)
    candidate = design.FiberFrameDesignCandidate(
        "narrow", (design.FiberFrameSectionChange("RC1", width_m=0.39),)
    )
    report = design.compare_public_rc_fiber_frame_designs(
        producer.model,
        (candidate,),
        CONFIG,
        prices=PRICES,
        terminal_limits=TERMINAL,
        history_limits=HISTORY,
        material_history_limits=LIMITS,
        source_revision="a" * 40,
    ).to_dict()
    assert report["schema_version"] == design.DESIGN_MATERIAL_HISTORY_COMPARISON_SCHEMA
    assert report["identity"]["material_history_limits"] == asdict(LIMITS)
    assert report["selection"]["candidate_id"] == (
        None if baseline_unavailable else "baseline"
    )
    selected = search._winner(report["rows"])
    assert (
        selected is None
        if baseline_unavailable
        else selected["candidate_id"] == "baseline"
    )
    assert report["runtime"]["reference_analysis_request_count"] == 2


def test_oracle_material_failure_is_not_false_terminal_safety():
    states = [
        ("unknown", False, "unavailable"),
        ("over-limit", True, "fail"),
        ("feasible", True, "pass"),
    ]
    pool = [
        {"candidate_id": key, "predicted_terminal_safe": True} for key, _, _ in states
    ]
    rows = [
        {
            "candidate_id": key,
            "full_reference_verification_pass": True,
            "terminal_limit_status": "pass",
            "full_history_verification_pass": True,
            "history_limit_status": "pass",
            "full_material_history_verification_pass": verified,
            "material_history_limit_status": status,
        }
        for key, verified, status in states
    ]
    audit = search._audit_outcomes(pool, [], rows, True, True)
    assert audit["false_safe_count"] == 0
    assert audit["missed_feasible_candidate_ids"] == ["feasible"]
    assert audit["oracle_combined_verified_candidate_count"] == 2
    assert audit["oracle_combined_unverifiable_candidate_count"] == 1
    assert audit["predicted_material_history_safety_available"] is False
    unavailable = search._audit_outcomes(pool, [], None, True, True)
    assert unavailable["missed_feasible_count"] is None


def test_material_limits_overflow_and_exact_type_are_rejected():
    with pytest.raises(ValueError, match="finite"):
        design.FiberFrameMaterialHistoryLimits(10**400, 0.0, 0.0)
    with pytest.raises(ValueError, match="typed"):
        design._validate_material_history_limits(HISTORY, asdict(LIMITS))
    assert (
        replace(
            LIMITS, maximum_steel_accumulated_plastic_strain=2.0
        ).maximum_steel_accumulated_plastic_strain
        == 2.0
    )
