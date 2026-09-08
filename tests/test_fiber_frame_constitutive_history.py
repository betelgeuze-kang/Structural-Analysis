"""Pure state aggregation and a stubbed public-authority boundary; no solves."""

from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
    stateful_fiber_frame2d_checkpoint_chain_artifact_hash,
)
from structural_analysis.benchmark import fiber_frame_constitutive_history as module
from structural_analysis.benchmark.stateful_fiber_frame2d import (
    make_two_element_stateful_fiber_cantilever,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState


def _point(kind, index=0, **values):
    constructor = UniaxialPlasticityState if kind == "steel" else ConcreteDamageState
    state = constructor(**values)
    return ("member", 0, index, str(index), kind), {
        name: getattr(state, name) for name in module._FIELDS[kind]
    }


def test_signed_reversal_and_accumulated_memory_are_separate():
    before = (
        _point(
            "steel",
            accumulated_plastic_strain=0.2,
            plastic_strain=0.1,
            backstress_mpa=10.0,
        ),
    )
    current = (
        _point(
            "steel",
            accumulated_plastic_strain=0.2,
            plastic_strain=-0.1,
            backstress_mpa=-10.0,
        ),
    )
    fields = module._summarize_points(current, before)["materials"]["steel"]["fields"]
    assert fields["accumulated_plastic_strain"]["positive_value_point_count"] == 1
    assert (
        fields["accumulated_plastic_strain"]["increased_from_parent_point_count"] == 0
    )
    for name in ("plastic_strain", "backstress_mpa"):
        assert fields[name]["positive_value_point_count"] == 0
        assert fields[name]["changed_from_parent_point_count"] == 1
        assert fields[name]["decreased_from_parent_point_count"] == 1
        assert fields[name]["increased_from_parent_point_count"] == 0


def test_concrete_history_growth_is_not_damage_and_density_is_not_energy():
    before = (_point("concrete"), _point("concrete", 1))
    current = (
        _point(
            "concrete",
            tensile_history_strain=0.001,
            dissipated_energy_density_mj_per_m3=2.0,
        ),
        _point(
            "concrete",
            1,
            compressive_history_strain=0.002,
            compressive_damage=0.1,
            dissipated_energy_density_mj_per_m3=3.0,
        ),
    )
    summary = module._summarize_points(current, before)
    fields = summary["materials"]["concrete"]["fields"]
    assert fields["tensile_history_strain"]["increased_from_parent_point_count"] == 1
    assert fields["tensile_damage"]["positive_value_point_count"] == 0
    assert fields["compressive_damage"]["increased_from_parent_point_count"] == 1
    density = fields["dissipated_energy_density_mj_per_m3"]
    assert density["minimum"] == 2.0 and density["maximum"] == 3.0
    assert density["unit"] == "MJ/m^3"
    assert "sum" not in density and "total_dissipated_energy_mj" not in summary


def test_genesis_has_no_measured_parent_change():
    result = module._summarize_points((_point("steel"), _point("concrete", 1)))
    assert result["material_point_count"] == 2
    for material in result["materials"].values():
        for field in material["fields"].values():
            assert field["positive_value_point_count"] == 0
            assert field["changed_from_parent_point_count"] is None
            assert field["increased_from_parent_point_count"] is None
            assert field["decreased_from_parent_point_count"] is None
            assert field["parent_comparison_reason"] == "genesis_has_no_parent"


def test_point_order_membership_must_match():
    points = (_point("steel"), _point("concrete", 1))
    with pytest.raises(ValueError, match="identity/order"):
        module._summarize_points(points, points[::-1])


@pytest.fixture
def retained(monkeypatch):
    """Typed storage fixture with mocked physical authority, not accepted physics."""
    problem = make_two_element_stateful_fiber_cantilever()
    root = initial_stateful_fiber_frame2d_checkpoint(problem)
    checkpoints = [root]
    for epoch in (1, 2):
        elements = tuple(
            replace(
                element,
                step_index=epoch,
                integration_point_states=tuple(
                    replace(state, step_index=epoch)
                    for state in element.integration_point_states
                ),
            )
            for element in root.element_states
        )
        checkpoints.append(
            replace(
                root,
                epoch=epoch,
                step_index=epoch,
                load_factor=epoch / 2,
                parent_state_hash=checkpoints[-1].state_hash,
                element_states=elements,
                state_hash="",
            )
        )
    chain = make_stateful_fiber_frame2d_checkpoint_chain(problem, tuple(checkpoints))
    artifact = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(problem, chain)
    result = public_api.PublicRCFiberFrameResult(
        status="ready",
        contract_pass=True,
        result_hash=canonical_hash("synthetic-public"),
        canonical_model_checksum=canonical_hash("synthetic-model"),
        input_checksum=canonical_hash("synthetic-input"),
        solver_id="synthetic",
        compiler_profile="synthetic-wrapper-test",
        configuration={"load_steps": 2},
        contract_bindings={"problem_contract_hash": problem.contract_hash},
        checkpoint={
            "artifact_hash": stateful_fiber_frame2d_checkpoint_chain_artifact_hash(
                artifact
            )
        },
        authority={},
        node_displacements=(),
        support_reactions=(),
        member_end_forces=(),
        section_results=(),
        fiber_results=(),
        convergence_history=(),
        metrics={},
        unsupported_features=(),
        warnings=(),
        _problem=problem,
        _checkpoint_chain=chain,
    )
    history = {
        "bindings": {"checkpoint_chain_hash": chain.chain_hash},
        "history_hash": canonical_hash("synthetic-history"),
        "steps": [
            {
                "epoch": cp.epoch,
                "step_index": cp.step_index,
                "target_load_factor": cp.load_factor,
                "bindings": {
                    "checkpoint_state_hash": cp.state_hash,
                    "parent_checkpoint_state_hash": cp.parent_state_hash,
                },
                "metrics": {"total_dissipated_energy_mj": energy},
                "recovery_hash": canonical_hash({"synthetic_epoch": cp.epoch}),
            }
            for cp, energy in zip(checkpoints[1:], (0.125, 0.375), strict=True)
        ],
    }
    response = {
        "status": "ready",
        "contract_pass": True,
        "source_result_hash": result.result_hash,
        "history": history,
        "report_hash": canonical_hash("synthetic-response"),
    }
    calls = []

    def recover(value):
        assert value is result
        calls.append(value)
        return SimpleNamespace(to_dict=lambda: deepcopy(response))

    monkeypatch.setattr(
        public_api, "recover_public_rc_fiber_frame_response_history", recover
    )
    return result, response, calls


def test_wrapper_uses_one_authority_call_preserves_sources_and_original_energy(
    retained,
):
    result, response, calls = retained
    before = (result.to_dict(), result.checkpoint_artifact())
    report = module.inspect_public_rc_fiber_frame_constitutive_history(result)
    payload = report.to_dict()
    assert len(calls) == 1
    assert before == (result.to_dict(), result.checkpoint_artifact())
    assert payload["accepted_epoch_count"] == 2
    assert [s["epoch"] for s in payload["states"]] == [0, 1, 2]
    assert [s["total_dissipated_energy_mj"] for s in payload["states"]] == [
        None,
        0.125,
        0.375,
    ]
    assert payload["states"][0]["engineering_recovery_hash"] is None
    assert (
        payload["states"][0]["engineering_recovery_reason"]
        == "genesis_has_no_engineering_recovery"
    )
    for state in payload["states"]:
        assert state["material_point_count"] == 84
        assert state["materials"]["steel"]["point_count"] == 12
        assert state["materials"]["concrete"]["point_count"] == 72
    assert (
        payload["states"][-1]["engineering_recovery_hash"]
        == response["history"]["steps"][-1]["recovery_hash"]
    )
    assert payload["bindings"]["source_result_hash"] == result.result_hash
    assert (
        payload["bindings"]["checkpoint_artifact_hash"]
        == result.checkpoint["artifact_hash"]
    )
    assert payload["claim_boundary"] == module._CLAIMS
    assert report.report_hash == canonical_hash(
        {k: v for k, v in payload.items() if k != "report_hash"}
    )
    payload["states"].clear()
    assert len(report.to_dict()["states"]) == 3


@pytest.mark.parametrize(
    "field",
    [
        "epoch",
        "target_load_factor",
        "checkpoint_state_hash",
        "parent_checkpoint_state_hash",
    ],
)
def test_detached_recovery_step_is_rejected(retained, field):
    result, response, _ = retained
    row = response["history"]["steps"][0]
    if field in row:
        row[field] = 99
    else:
        row["bindings"][field] = canonical_hash("wrong-checkpoint")
    with pytest.raises(ValueError, match="epoch/recovery"):
        module.inspect_public_rc_fiber_frame_constitutive_history(result)


def test_public_authority_failure_propagates(retained, monkeypatch):
    result, _, _ = retained

    def reject(_):
        raise ValueError("full J1-J5 failed")

    monkeypatch.setattr(
        public_api, "recover_public_rc_fiber_frame_response_history", reject
    )
    with pytest.raises(ValueError, match="full J1-J5 failed"):
        module.inspect_public_rc_fiber_frame_constitutive_history(result)


def test_source_mutation_during_authority_call_is_rejected(retained, monkeypatch):
    result, response, _ = retained

    def mutate(_):
        result.metrics["changed"] = True
        return SimpleNamespace(to_dict=lambda: deepcopy(response))

    monkeypatch.setattr(
        public_api, "recover_public_rc_fiber_frame_response_history", mutate
    )
    with pytest.raises(ValueError, match="mutated retained source"):
        module.inspect_public_rc_fiber_frame_constitutive_history(result)


@pytest.mark.parametrize("value", [None, {}, SimpleNamespace()])
def test_exact_public_result_type_required(value):
    with pytest.raises(ValueError, match="exact PublicRCFiberFrameResult"):
        module.inspect_public_rc_fiber_frame_constitutive_history(value)


def test_changed_immutable_payload_is_not_exported(retained):
    result, _, _ = retained
    report = module.inspect_public_rc_fiber_frame_constitutive_history(result)
    payload = report.to_dict()
    payload["states"][1]["material_point_count"] = 0
    with pytest.raises(ValueError, match="integrity"):
        replace(report, _report_json=json.dumps(payload))


@pytest.mark.parametrize("value", [None, True, -1.0, float("nan"), float("inf")])
def test_accepted_energy_unavailable_or_invalid_does_not_receive_credit(
    retained, value
):
    result, response, _ = retained
    response["history"]["steps"][0]["metrics"]["total_dissipated_energy_mj"] = value
    with pytest.raises(ValueError, match="invalid source dissipated energy"):
        module.inspect_public_rc_fiber_frame_constitutive_history(result)


def test_source_mutation_during_aggregation_is_rejected(retained, monkeypatch):
    result, _, _ = retained
    summarize = module._summarize_points

    def mutate(*args):
        report = summarize(*args)
        result.metrics["changed_during_aggregation"] = True
        return report

    monkeypatch.setattr(module, "_summarize_points", mutate)
    with pytest.raises(ValueError, match="aggregation mutated retained source"):
        module.inspect_public_rc_fiber_frame_constitutive_history(result)


def _reseal(report, payload):
    payload["report_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )
    return replace(
        report, report_hash=payload["report_hash"], _report_json=json.dumps(payload)
    )


def test_explicit_validator_rebuilds_once_and_returns_original_report(retained):
    result, _, calls = retained
    report = module.inspect_public_rc_fiber_frame_constitutive_history(result)
    assert len(calls) == 1
    report.to_dict()
    assert len(calls) == 1
    assert (
        module.validate_public_rc_fiber_frame_constitutive_history(report, result)
        is report
    )
    assert len(calls) == 2


@pytest.mark.parametrize("mutation", ["statistics", "source", "numeric_type"])
def test_resealed_payload_requires_exact_original_source(retained, mutation):
    result, _, calls = retained
    report = module.inspect_public_rc_fiber_frame_constitutive_history(result)
    payload = report.to_dict()
    if mutation == "statistics":
        payload["states"][1]["materials"]["steel"]["fields"][
            "accumulated_plastic_strain"
        ]["positive_value_point_count"] = 1
    elif mutation == "source":
        payload["bindings"]["source_result_hash"] = canonical_hash("other-source")
    else:
        # Python dict equality would accept this integer/float substitution.
        payload["states"][0]["epoch"] = 0.0
    detached = _reseal(report, payload)
    assert detached.to_dict() == payload  # The seal alone is only local integrity.
    with pytest.raises(ValueError, match="exact retained public source"):
        module.validate_public_rc_fiber_frame_constitutive_history(detached, result)
    assert len(calls) == 2


@pytest.mark.parametrize("value", [True, 0, None])
def test_resealed_claim_promotion_or_type_alias_is_rejected(retained, value):
    result, _, calls = retained
    report = module.inspect_public_rc_fiber_frame_constitutive_history(result)
    payload = report.to_dict()
    payload["claim_boundary"]["independent_physical_validation"] = value
    with pytest.raises(ValueError, match="integrity"):
        _reseal(report, payload)
    # Even a deliberately mutated frozen object must fail before source replay.
    object.__setattr__(report, "report_hash", payload["report_hash"])
    object.__setattr__(report, "_report_json", json.dumps(payload))
    with pytest.raises(ValueError, match="integrity"):
        module.validate_public_rc_fiber_frame_constitutive_history(report, result)
    assert len(calls) == 1


@pytest.mark.parametrize("argument", ["report", "result"])
def test_validator_requires_exact_types_before_source_replay(retained, argument):
    result, _, calls = retained
    report = module.inspect_public_rc_fiber_frame_constitutive_history(result)
    with pytest.raises(ValueError, match="exact"):
        module.validate_public_rc_fiber_frame_constitutive_history(
            SimpleNamespace() if argument == "report" else report,
            SimpleNamespace() if argument == "result" else result,
        )
    assert len(calls) == 1
