"""Small synthetic contracts; no historical data, structural solve or campaign."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import importlib
import json
from pathlib import Path

import pytest

from structural_analysis.ai.fiber_frame_warm_start_features import (
    FiberFrameWarmStartModelFeatures,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import RCControlSeedPolicy
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext


def _hash(index):
    return f"sha256:{index:064x}"


@pytest.fixture
def gate_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("rc_prior_work_cost_margin_gate")


def _model():
    return FiberFrameWarmStartModelFeatures(_hash(1), _hash(2), ("width",), (0.4,))


def _context():
    return RCControlSeedContext(
        _hash(1), 7, 0, 0.003, (0.001, 0.002), ((0.001, 1.0), (0.002, 2.0))
    )


def _seed_policy():
    """Declared tiny zero-correction policy; no fit or numerical replay."""
    payload = dict(
        schema_version="experimental-rc-control-secant-correction-policy.v1",
        model_context_hash=_hash(2),
        model_feature_names=["width"],
        free_global_dofs=[7],
        control_free_index=0,
        solver_config_hash=_hash(6),
        feature_mean=[0.0] * 9,
        feature_scale=[1.0] * 9,
        feature_min=[-10.0] * 9,
        feature_max=[10.0] * 9,
        target_scale=[1.0, 1.0],
        weights=[[0.0, 0.0] for _ in range(10)],
        training_sample_hashes=[_hash(30), _hash(31)],
        ridge=10000.0,
        ood_margin=0.1,
    )
    payload["policy_hash"] = _sha(_bytes(payload))
    return RCControlSeedPolicy(_bytes(payload).decode())


def _gate(gate_module):
    """Synthetic constant cost score with the exact new profile layout."""
    prefix = importlib.import_module("rc_switch_prefix_features")
    features = prefix.prefix_features(_context(), _model())
    names = features["feature_names"] + [
        "prior_work." + name for name in prefix.PRIOR_WORK_COUNTERS
    ]
    values = features["values"] + [1.0, 4.0, 4.0, 9.0, 2.0, 0.0]
    payload = dict(
        schema_version=gate_module.SCHEMA,
        feature_profile=prefix.PRIOR_WORK_PROFILE,
        feature_names=names,
        mean=values,
        scale=[1.0] * len(values),
        minimum=values,
        maximum=values,
        weights=[0.0] * len(values) + [0.02],
        ridge=1.0,
        threshold=0.01,
        outer_group_index=0,
        excluded_case_ids=["outer", "validation"],
        training_sample_hashes=[_hash(11)],
        positive_count=1,
        negative_count=0,
        training_rows_hash=_hash(12),
        seed_policy_hash=_seed_policy().policy_hash,
    )
    payload["policy_hash"] = _sha(_bytes(payload))
    return gate_module.PriorWorkCostMarginGate(_bytes(payload).decode())


def test_legacy_prefix_function_has_exact_original_values_and_profile(gate_module):
    prefix = importlib.import_module("rc_switch_prefix_features")
    expected = dict(
        profile="rc-switch-accepted-prefix-features.v1",
        feature_names=[
            "model.width",
            "target_m",
            "target_increment_m",
            "previous_target_increment_m",
            "last_coordinate_0",
            "last_coordinate_1",
            "coordinate_increment_0",
            "coordinate_increment_1",
        ],
        values=[0.4, 0.003, 0.001, 0.001, 0.002, 2.0, 0.001, 1.0],
    )
    assert _bytes(prefix.prefix_features(_context(), _model())) == _bytes(expected)
    material = replace(
        _context(), committed_material_state_json="ignored material payload"
    )
    assert _bytes(prefix.prefix_features(material, _model())) == _bytes(expected)


def test_bound_policy_retains_fixed_cost_profile_and_immutable_actual_bindings(
    gate_module,
):
    gate = _gate(gate_module)
    assert gate._payload["ridge"] == 1.0
    assert gate._payload["threshold"] == 0.01
    assert gate.seed_policy_hash == _seed_policy().policy_hash
    assert gate.excluded_case_ids == ("outer", "validation")
    assert (
        gate.decision(
            dict(
                profile=gate._feature_profile,
                feature_names=list(gate._payload["feature_names"]),
                values=list(gate._payload["mean"]),
            )
        )
        is True
    )
    with pytest.raises(TypeError):
        gate._payload["seed_policy_hash"] = _hash(99)
    with pytest.raises(TypeError):
        gate._payload["weights"][-1] = 0.0
    with pytest.raises(FrozenInstanceError):
        gate._json = "{}"
    with pytest.raises(ValueError):
        importlib.import_module("rc_cost_margin_gate").CostMarginGate(gate._json)


@pytest.mark.parametrize(
    "mutation",
    [
        "seed",
        "weights",
        "unknown_field",
        "missing_field",
        "duplicate",
        "counter_layout",
        "identity_feature",
        "threshold",
        "ridge",
        "boolean",
    ],
)
def test_bound_policy_rejects_hash_tampering_ambiguous_or_foreign_contract(
    gate_module, mutation
):
    gate = _gate(gate_module)
    payload = json.loads(gate._json)
    if mutation == "seed":
        payload["seed_policy_hash"] = _hash(99)
    elif mutation == "weights":
        payload["weights"][-1] += 1
    elif mutation == "unknown_field":
        payload["target_outcome"] = "future"
    elif mutation == "missing_field":
        payload.pop("seed_policy_hash")
    elif mutation == "duplicate":
        with pytest.raises(ValueError):
            gate_module.PriorWorkCostMarginGate(
                '{"seed_policy_hash":"foreign",' + gate._json[1:]
            )
        return
    elif mutation == "counter_layout":
        payload["feature_names"][-1] = "prior_work.wall_ns"
    elif mutation == "identity_feature":
        payload["feature_names"][1] = "arm_identity"
    elif mutation == "threshold":
        payload["threshold"] = 0.001
    elif mutation == "ridge":
        payload["ridge"] = 0.1
    else:
        payload["mean"][0] = True
    if mutation not in ("seed", "weights"):
        payload.pop("policy_hash")
        payload["policy_hash"] = _sha(_bytes(payload))
    with pytest.raises(ValueError):
        gate_module.PriorWorkCostMarginGate(_bytes(payload).decode())


def test_guard_missing_checked_predecessor_abstains_exactly(gate_module):
    gate = _gate(gate_module)
    assert gate.guard(_model())(_context()) is False
    assert gate.guard(_model())(None) is False


def test_factory_returns_only_exact_seed_and_exclusion_bound_guard(gate_module):
    gate = _gate(gate_module)
    result = gate_module.prior_work_guard_binding(
        gate,
        policy=_seed_policy(),
        model_features=_model(),
        excluded_case_ids=("outer", "validation"),
    )
    assert set(result) == {
        "guard",
        "guard_identity",
        "seed_policy_hash",
        "excluded_case_ids",
    }
    assert result["guard_identity"] == gate.policy_hash
    assert result["seed_policy_hash"] == gate.seed_policy_hash
    assert type(result["excluded_case_ids"]) is tuple
    assert callable(result["guard"])
    assert result["guard"](_context()) is False


@pytest.mark.parametrize(
    "mutation",
    ["seed", "exclusions", "order", "tuple", "model", "names", "opaque_policy"],
)
def test_factory_rejects_foreign_fold_or_mutable_exclusion_claim(gate_module, mutation):
    gate, policy, model, excluded = (
        _gate(gate_module),
        _seed_policy(),
        _model(),
        ("outer", "validation"),
    )
    if mutation == "seed":
        payload = policy.to_dict()
        payload["weights"][0][0] = 1.0
        payload.pop("policy_hash")
        payload["policy_hash"] = _sha(_bytes(payload))
        policy = RCControlSeedPolicy(_bytes(payload).decode())
    elif mutation == "exclusions":
        excluded = ("outer",)
    elif mutation == "order":
        excluded = ("validation", "outer")
    elif mutation == "tuple":
        excluded = ["outer", "validation"]
    elif mutation == "model":
        model = replace(model, context_hash=_hash(99))
    elif mutation == "names":
        model = replace(model, feature_names=("height",))
    else:
        from types import SimpleNamespace

        policy = SimpleNamespace(policy_hash=gate.seed_policy_hash)
    with pytest.raises(ValueError):
        gate_module.prior_work_guard_binding(
            gate, policy=policy, model_features=model, excluded_case_ids=excluded
        )


def test_online_individual_bounds_decline_without_threshold_changes(gate_module):
    gate = _gate(gate_module)
    feature = dict(
        profile=gate._feature_profile,
        feature_names=list(gate._payload["feature_names"]),
        values=list(gate._payload["mean"]),
    )
    feature["values"][-6] += 1.0
    assert gate.decision(feature) is False


@pytest.mark.parametrize(
    "value", [True, "1", None, -1, 1.5, float("nan"), float("inf"), 2**53]
)
def test_direct_decision_requires_known_exact_counter_values(gate_module, value):
    gate = _gate(gate_module)
    feature = dict(
        profile=gate._feature_profile,
        feature_names=list(gate._payload["feature_names"]),
        values=list(gate._payload["mean"]),
    )
    feature["values"][-6] = value
    with pytest.raises(ValueError):
        gate.decision(feature)


def test_direct_decision_rejects_identity_or_outcome_as_an_extra_feature_field(
    gate_module,
):
    gate = _gate(gate_module)
    feature = dict(
        profile=gate._feature_profile,
        feature_names=list(gate._payload["feature_names"]),
        values=list(gate._payload["mean"]),
        arm_identity=_hash(90),
    )
    with pytest.raises(ValueError):
        gate.decision(feature)


def _codec_context(**kwargs):
    from tests.test_rc_control_prior_work import synthetic_prior_context

    return synthetic_prior_context(**kwargs)


def _codec_model(context, width=0.4):
    return replace(
        _model(), problem_contract_hash=context.problem_contract_hash, values=(width,)
    )


def _change_original(context, name, mutation):
    from tests.test_rc_control_prior_work import _change_original as change

    return change(context, name, mutation)


def _tables_and_inputs(gate_module, *, ratios=(0.98, 0.98), widths=(0.4, 0.4)):
    """Only tiny schema-shaped codec records; never observed solver work."""
    prefix = importlib.import_module("rc_switch_prefix_features")
    labels = importlib.import_module("audit_rc_nested_switch_labels")
    cost = importlib.import_module("rc_cost_margin_gate")
    context = _codec_context()
    cases = ("train-a", "train-b", "validation")
    rows, sources, names = [], [], None
    for index, case in enumerate(cases):
        model = _codec_model(context, widths[index] if index < 2 else 0.4)
        feature = prefix.prefix_features(context, model)
        names = feature["feature_names"]
        ratio = ratios[index] if index < 2 else 0.98
        repetitions = [
            dict(
                repetition=i,
                comparison_pass=True,
                decision="proposed",
                path_time_ratio=ratio,
                report_hash=_hash(40 + index * 3 + i),
            )
            for i in range(3)
        ]
        row = dict(
            case_id=case,
            source_sample_hash=_hash(11 + index),
            parent_hash=context.prior_work_binding["current_parent_hash"],
            seed_fit_index=index,
            policy_hash=_hash(21 + index),
            values=feature["values"],
            label=labels.label_from_repetitions(repetitions)["label"],
            cost_repetitions=repetitions,
            cost_target=cost.cost_target(repetitions),
        )
        rows.append(row)
        sources.append(
            {
                **{
                    key: row[key]
                    for key in (
                        "case_id",
                        "source_sample_hash",
                        "parent_hash",
                        "seed_fit_index",
                        "policy_hash",
                    )
                },
                "prior_work_context": json.loads(_bytes(context.to_dict())),
                "model_features": model.to_dict(),
            }
        )
    training = dict(
        outer_group_index=0,
        validation_group_index=1,
        excluded_case_ids=["outer", "validation"],
        feature_profile=prefix.PROFILE,
        feature_names=list(names),
        cost_target_profile=cost.TARGET_PROFILE,
        training_rows=rows[:2],
        unverified_rows=[],
        verified_positive_count=sum(row["label"] is True for row in rows[:2]),
        verified_negative_count=sum(row["label"] is False for row in rows[:2]),
        normalization_scope="verified training rows only; no validation statistics",
        gate_fitted=False,
        independent_evaluation=False,
    )
    validation = dict(
        outer_group_index=0,
        validation_group_index=1,
        feature_profile=prefix.PROFILE,
        feature_names=list(names),
        rows=rows[2:],
        unverified_count=0,
        declared_row_count=1,
        independent_evaluation=False,
    )
    return dict(training=training, validation=validation), dict(
        schema_version=gate_module.JOIN_PROFILE, rows=sources
    )


def _fitted_codec_gate(gate_module):
    tables, inputs = _tables_and_inputs(gate_module)
    joined = gate_module.append_prior_work_inputs(
        tables, inputs, seed_policy_hash=_seed_policy().policy_hash
    )
    gate, receipt = gate_module.fit_prior_work_cost_gate(joined["training"])
    return gate, receipt, joined


def test_new_feature_profile_uses_all_retried_previous_work_and_no_identity_scalars(
    gate_module,
):
    prefix = importlib.import_module("rc_switch_prefix_features")
    context = _codec_context(retries=2)
    model = _codec_model(context)
    legacy = prefix.prefix_features(context, model)
    features = prefix.prefix_prior_work_features(context, model)
    assert features["profile"] == prefix.PRIOR_WORK_PROFILE
    assert features["feature_names"] == legacy["feature_names"] + [
        "prior_work." + name for name in prefix.PRIOR_WORK_COUNTERS
    ]
    assert features["values"] == legacy["values"] + [3.0, 9.0, 6.0, 9.0, 3.0, 3.0]
    assert all(type(value) is float for value in features["values"])
    assert not any(
        "identity" in name
        or "hash" in name
        or "epoch" in name
        or "wall" in name
        or "outcome" in name
        for name in features["feature_names"]
    )


def test_consistent_identity_changes_do_not_change_numeric_features_or_authenticate_data(
    gate_module,
):
    prefix = importlib.import_module("rc_switch_prefix_features")
    context = _codec_context()
    model = _codec_model(context)
    expected = prefix.prefix_prior_work_features(context, model)
    binding = dict(context.prior_work_binding)
    for index, key in enumerate(
        ("arm_identity", "request_hash", "source_binding_hash")
    ):
        binding[key] = _hash(80 + index)
    record = deepcopy(context.prior_accepted_transition_work)
    record["binding"] = binding
    consistent = replace(
        context, prior_work_binding=binding, prior_accepted_transition_work=record
    )
    # Internal consistency permits this authored transport change. This is why
    # an external source auditor, not this feature vector, authenticates inputs.
    assert prefix.prefix_prior_work_features(consistent, model) == expected


def test_valid_online_callback_uses_new_profile_while_unrecorded_dispatches_abstain(
    gate_module,
):
    gate, receipt, _ = _fitted_codec_gate(gate_module)
    context = _codec_context()
    guard = gate.guard(_codec_model(context))
    assert guard(context) is True
    assert guard(_codec_context(assembly=False)) is False
    assert receipt["predecessor_counter_authenticity_established"] is False
    assert receipt["historical_training_admitted"] is False
    assert receipt["online_extraction_cost_in_target"] is False
    assert receipt["independent_evaluation"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "first",
        "foreign",
        "future",
        "unknown",
        "missing_metric",
        "inexact_counter",
        "counter_mismatch",
        "partial_dispatch",
        "current_outcome",
        "bool_target",
        "string_target",
    ],
)
def test_new_callback_strictly_abstains_on_unchecked_foreign_future_unknown_or_inexact_work(
    gate_module, mutation
):
    gate, _, _ = _fitted_codec_gate(gate_module)
    context = _codec_context()
    model = _codec_model(context)
    if mutation == "missing":
        context = replace(context, prior_accepted_transition_work=None)
    elif mutation == "first":
        context = replace(
            context,
            accepted_targets_m=(0.0,),
            accepted_augmented_coordinates_m=((0.0, 0.0),),
        )
    elif mutation == "foreign":
        record = deepcopy(context.prior_accepted_transition_work)
        record["binding"]["arm_identity"] = _hash(99)
        context = replace(context, prior_accepted_transition_work=record)
    elif mutation == "future":
        binding = dict(context.prior_work_binding, current_parent_epoch=2)
        record = deepcopy(context.prior_accepted_transition_work)
        record["binding"] = binding
        context = replace(
            context, prior_work_binding=binding, prior_accepted_transition_work=record
        )
    elif mutation == "unknown":
        context = _change_original(
            context, "outcome", lambda v: v.update(unknown_work=True)
        )
    elif mutation == "missing_metric":
        context = _change_original(
            context,
            "step",
            lambda v: v["trial_solution"]["metrics"].pop("linear_solve_count"),
        )
    elif mutation == "inexact_counter":
        context = _change_original(
            context, "outcome", lambda v: v["work"].update(core_calls=True)
        )
    elif mutation == "counter_mismatch":
        context = _change_original(
            context, "outcome", lambda v: v["work"].update(newton_iterations=99)
        )
    elif mutation == "partial_dispatch":
        context = _change_original(
            context,
            "outcome",
            lambda v: v["newton_assembly_work"]["calls"][0].update(status="started"),
        )
    elif mutation == "current_outcome":
        record = deepcopy(context.prior_accepted_transition_work)
        record["current_target_outcome"] = {"newton_iterations": 1}
        context = replace(context, prior_accepted_transition_work=record)
    elif mutation == "bool_target":
        context = replace(context, target_m=True)
    else:
        context = replace(context, target_m="0.2")
    assert gate.guard(model)(context) is False


def test_pure_fit_keeps_known_ridge_solution_and_train_only_normalization(gate_module):
    tables, inputs = _tables_and_inputs(
        gate_module, ratios=(1.25, 0.5), widths=(0.2, 0.6)
    )
    joined = gate_module.append_prior_work_inputs(
        tables, inputs, seed_policy_hash=_seed_policy().policy_hash
    )
    gate, receipt = gate_module.fit_prior_work_cost_gate(joined["training"])
    assert gate._payload["mean"][0] == pytest.approx(0.4)
    assert gate._payload["scale"][0] == pytest.approx(0.2)
    assert gate._payload["weights"][0] == pytest.approx(0.25)
    assert gate._payload["weights"][-1] == pytest.approx(0.125)
    assert gate._payload["weights"][1:-1] == pytest.approx(
        [0.0] * (len(gate._payload["feature_names"]) - 1), abs=1e-14
    )
    assert gate._payload["excluded_case_ids"] == ("outer", "validation")
    assert gate._payload["training_sample_hashes"] == (_hash(11), _hash(12))
    assert receipt["target_profile"] == "minimum-three-repeat-relative-time-margin.v1"
    assert receipt["gate_cost_in_training_target"] is False


def test_excluded_validation_perturbation_cannot_change_training_bytes_stats_weights_or_policy_hash(
    gate_module,
):
    tables, inputs = _tables_and_inputs(gate_module)
    joined = gate_module.append_prior_work_inputs(
        tables, inputs, seed_policy_hash=_seed_policy().policy_hash
    )
    gate, _ = gate_module.fit_prior_work_cost_gate(joined["training"])
    changed_tables, changed_inputs = deepcopy(tables), deepcopy(inputs)
    context = replace(_codec_context(), target_m=0.8)
    model = _codec_model(context, 100.0)
    feature = importlib.import_module("rc_switch_prefix_features").prefix_features(
        context, model
    )
    changed_tables["validation"]["rows"][0]["values"] = feature["values"]
    changed_tables["validation"]["rows"][0]["label"] = False
    changed_tables["validation"]["rows"][0]["cost_target"] = -1.0
    for repeat in changed_tables["validation"]["rows"][0]["cost_repetitions"]:
        repeat["path_time_ratio"] = 2.0
    changed_inputs["rows"][-1]["prior_work_context"] = json.loads(
        _bytes(context.to_dict())
    )
    changed_inputs["rows"][-1]["model_features"] = model.to_dict()
    changed = gate_module.append_prior_work_inputs(
        changed_tables, changed_inputs, seed_policy_hash=_seed_policy().policy_hash
    )
    changed_gate, _ = gate_module.fit_prior_work_cost_gate(changed["training"])
    assert changed["validation"] != joined["validation"]
    assert _bytes(changed["training"]) == _bytes(joined["training"])
    assert changed_gate._json == gate._json
    assert changed_gate.policy_hash == gate.policy_hash


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign_sample",
        "foreign_policy",
        "foreign_seed",
        "case",
        "parent",
        "prefix",
        "context_hash",
        "unrecorded",
        "future_field",
    ],
)
def test_complete_pure_join_rejects_missing_foreign_parent_or_unchecked_inputs(
    gate_module, mutation
):
    tables, inputs = _tables_and_inputs(gate_module)
    row = inputs["rows"][0]
    if mutation == "missing":
        inputs["rows"].pop()
    elif mutation == "duplicate":
        inputs["rows"][-1] = deepcopy(row)
    elif mutation == "foreign_sample":
        row["source_sample_hash"] = _hash(99)
    elif mutation == "foreign_policy":
        row["policy_hash"] = _hash(99)
    elif mutation == "foreign_seed":
        row["seed_fit_index"] = True
    elif mutation == "case":
        row["case_id"] = "foreign"
    elif mutation == "parent":
        row["parent_hash"] = tables["training"]["training_rows"][0]["parent_hash"] = (
            _hash(99)
        )
    elif mutation == "prefix":
        tables["training"]["training_rows"][0]["values"][1] += 1
    elif mutation == "context_hash":
        row["model_features"]["feature_hash"] = _hash(99)
    elif mutation == "unrecorded":
        row["prior_work_context"] = json.loads(
            _bytes(_codec_context(assembly=False).to_dict())
        )
    else:
        row["current_target_work"] = {"linear_solves": 1}
    with pytest.raises(ValueError):
        gate_module.append_prior_work_inputs(
            tables, inputs, seed_policy_hash=_seed_policy().policy_hash
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "excluded",
        "values",
        "boolean",
        "target",
        "label",
        "profile",
        "future_row_field",
        "whole_packet_field",
        "seed_hash",
        "counts",
        "promoted",
    ],
)
def test_pure_fit_rechecks_causal_inputs_exclusions_original_targets_and_no_global_packet(
    gate_module, mutation
):
    _, _, tables = _fitted_codec_gate(gate_module)
    training = deepcopy(tables["training"])
    row = training["training_rows"][0]
    if mutation == "excluded":
        row["case_id"] = "validation"
    elif mutation == "values":
        row["values"][-6] += 1.0
    elif mutation == "boolean":
        row["values"][-6] = True
    elif mutation == "target":
        row["cost_target"] = 0.5
    elif mutation == "label":
        row["label"] = False
    elif mutation == "profile":
        training["cost_target_profile"] = "tuned"
    elif mutation == "future_row_field":
        row["current_target_work"] = {"newton_iterations": 1}
    elif mutation == "whole_packet_field":
        training["source_packet_with_validation"] = {"values": [999.0]}
    elif mutation == "seed_hash":
        training["seed_policy_hash"] = "foreign"
    elif mutation == "counts":
        training["verified_positive_count"] = True
    else:
        training["gate_fitted"] = True
    with pytest.raises(ValueError):
        gate_module.fit_prior_work_cost_gate(training)


def test_unknown_current_target_label_stays_in_denominator_and_out_of_normalization(
    gate_module,
):
    tables, inputs = _tables_and_inputs(gate_module)
    row = tables["training"]["training_rows"].pop()
    row["label"], row["cost_target"] = None, None
    row["cost_repetitions"][0].update(comparison_pass=False, path_time_ratio=None)
    model = _codec_model(_codec_context(), 100.0)
    row["values"] = importlib.import_module(
        "rc_switch_prefix_features"
    ).prefix_features(_codec_context(), model)["values"]
    inputs["rows"][1]["model_features"] = model.to_dict()
    tables["training"]["unverified_rows"] = [row]
    tables["training"]["verified_positive_count"] = 1
    joined = gate_module.append_prior_work_inputs(
        tables, inputs, seed_policy_hash=_seed_policy().policy_hash
    )
    gate, receipt = gate_module.fit_prior_work_cost_gate(joined["training"])
    assert receipt["verified_rows"] == 1
    assert receipt["unverified_rows_excluded"] == 1
    assert len(joined["training"]["unverified_rows"]) == 1
    assert gate._payload["mean"][0] == 0.4
    assert gate._payload["minimum"][0] == gate._payload["maximum"][0] == 0.4
    assert gate._payload["training_sample_hashes"] == (_hash(11),)
    joined["training"]["unverified_rows"][0]["cost_target"] = 0.0
    with pytest.raises(ValueError, match="unknown cost denominator"):
        gate_module.fit_prior_work_cost_gate(joined["training"])


def _full_training(
    gate_module, *, unknown=False, ratios=(1.25, 0.5), widths=(0.2, 0.6)
):
    """Authored codec rows only; no structural work or original data admission."""
    tables, inputs = _tables_and_inputs(gate_module, ratios=ratios, widths=widths)
    joined = gate_module.append_prior_work_inputs(
        tables, inputs, seed_policy_hash=_seed_policy().policy_hash
    )
    training = joined["training"]
    training.pop("outer_group_index")
    training.pop("validation_group_index")
    training.update(
        schema_version=gate_module.FULL_TRAINING_PROFILE,
        training_scope="declared_training_only",
        excluded_case_ids=[],
        teacher_roster_hash=_hash(90),
        declared_training_sample_hashes=[_hash(11), _hash(12)],
    )
    if unknown:
        row = training["training_rows"].pop()
        row["label"], row["cost_target"] = None, None
        row["cost_repetitions"][0].update(comparison_pass=False, path_time_ratio=None)
        training["unverified_rows"] = [row]
        training["verified_positive_count"] = sum(
            r["label"] is True for r in training["training_rows"]
        )
        training["verified_negative_count"] = sum(
            r["label"] is False for r in training["training_rows"]
        )
    seed_payload = _seed_policy().to_dict()
    seed_payload["training_sample_hashes"] = list(
        training["declared_training_sample_hashes"]
    )
    seed_payload.pop("policy_hash")
    seed_payload["policy_hash"] = _sha(_bytes(seed_payload))
    seed = RCControlSeedPolicy(_bytes(seed_payload).decode())
    training["seed_policy_hash"] = seed.policy_hash
    return training, seed


def test_full_training_fit_is_explicit_fixed_scope_without_fold_impersonation(
    gate_module,
):
    training, seed = _full_training(gate_module)
    gate, receipt = gate_module.fit_full_training_prior_work_cost_gate(training)
    assert type(gate) is gate_module.FullTrainingPriorWorkCostMarginGate
    payload = gate.to_dict()
    assert payload["schema_version"] == gate_module.FULL_TRAINING_GATE_SCHEMA
    assert payload["training_scope"] == "declared_training_only"
    assert payload["excluded_case_ids"] == []
    assert (
        "outer_group_index" not in payload and "validation_group_index" not in payload
    )
    assert payload["ridge"] == 1.0 and payload["threshold"] == 0.01
    assert (
        payload["cost_target_profile"] == "minimum-three-repeat-relative-time-margin.v1"
    )
    assert payload["mean"][0] == pytest.approx(0.4)
    assert payload["scale"][0] == pytest.approx(0.2)
    assert payload["weights"][0] == pytest.approx(0.25)
    assert payload["weights"][-1] == pytest.approx(0.125)
    assert payload["seed_policy_hash"] == seed.policy_hash
    assert payload["teacher_roster_hash"] == training["teacher_roster_hash"]
    assert payload["training_rows_hash"] == _sha(_bytes(training))
    assert receipt["declared_rows"] == receipt["verified_rows"] == 2
    assert receipt["unverified_rows_excluded"] == 0
    assert receipt["fit_completed"] is True and receipt["unknown_work"] is False
    for key in (
        "historical_training_admitted",
        "predecessor_counter_authenticity_established",
        "independent_evaluation",
        "gate_cost_in_training_target",
    ):
        assert receipt[key] is False
    with pytest.raises(ValueError):
        gate_module.PriorWorkCostMarginGate(gate._json)
    with pytest.raises(ValueError):
        gate_module.fit_prior_work_cost_gate(training)
    with pytest.raises(FrozenInstanceError):
        gate._json = "{}"
    with pytest.raises(TypeError):
        gate._payload["training_scope"] = "outer"
    payload["weights"][-1] = 99.0
    assert gate.to_dict()["weights"][-1] == pytest.approx(0.125)


def test_full_known_numerics_match_legacy_fold_without_repurposing_fold_identity(
    gate_module,
):
    training, _ = _full_training(gate_module)
    tables, inputs = _tables_and_inputs(
        gate_module, ratios=(1.25, 0.5), widths=(0.2, 0.6)
    )
    fold = gate_module.append_prior_work_inputs(
        tables, inputs, seed_policy_hash=_seed_policy().policy_hash
    )
    old, _ = gate_module.fit_prior_work_cost_gate(fold["training"])
    full, _ = gate_module.fit_full_training_prior_work_cost_gate(training)
    for key in (
        "mean",
        "scale",
        "minimum",
        "maximum",
        "weights",
        "feature_names",
        "ridge",
        "threshold",
    ):
        assert _bytes(full.to_dict()[key]) == _bytes(old._payload[key])
    assert old._payload["outer_group_index"] == 0
    assert old.excluded_case_ids == ("outer", "validation")
    assert full.excluded_case_ids == ()


def test_full_unknown_denominator_is_hashed_and_excluded_from_numeric_statistics(
    gate_module,
):
    training, _ = _full_training(
        gate_module, unknown=True, ratios=(0.98, 0.98), widths=(0.4, 100.0)
    )
    gate, receipt = gate_module.fit_full_training_prior_work_cost_gate(training)
    assert gate._payload["mean"][0] == 0.4
    assert gate._payload["minimum"][0] == gate._payload["maximum"][0] == 0.4
    assert gate._payload["declared_training_sample_hashes"] == (_hash(11), _hash(12))
    assert gate._payload["training_sample_hashes"] == (_hash(11),)
    assert gate._payload["unverified_sample_hashes"] == (_hash(12),)
    assert gate._payload["unverified_count"] == 1
    assert receipt["declared_rows"] == 2
    assert receipt["verified_rows"] == receipt["unverified_rows_excluded"] == 1
    altered = deepcopy(training)
    context = _codec_context()
    model = _codec_model(context, 900.0)
    row = altered["unverified_rows"][0]
    row["model_features"] = model.to_dict()
    row["values"] = importlib.import_module(
        "rc_switch_prefix_features"
    ).prefix_prior_work_features(context, model)["values"]
    changed, _ = gate_module.fit_full_training_prior_work_cost_gate(altered)
    for key in ("mean", "scale", "minimum", "maximum", "weights"):
        assert gate._payload[key] == changed._payload[key]
    assert gate.policy_hash != changed.policy_hash


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "scope",
        "outer",
        "validation",
        "exclusions",
        "duplicate_declared",
        "foreign_declared",
        "missing_row",
        "duplicate_unknown",
        "roster_order",
        "bool_fit",
        "future_feature",
        "unknown_zero",
        "unknown_known_cost",
        "counts",
        "seed",
        "teacher",
        "destination_teacher",
        "row_extra",
        "values",
        "bool_value",
        "target",
        "label",
        "promoted",
        "independent",
        "empty_scope",
        "tuple_roster",
    ],
)
def test_full_fitter_rejects_incomplete_foreign_or_ambiguous_scope(
    gate_module, mutation
):
    training, _ = _full_training(gate_module, unknown=True, ratios=(0.98, 0.98))
    row = training["training_rows"][0]
    if mutation == "schema":
        training["schema_version"] = gate_module.JOIN_PROFILE
    elif mutation == "scope":
        training["training_scope"] = "outer"
    elif mutation in ("outer", "validation"):
        training[mutation + "_group_index"] = 0
    elif mutation == "exclusions":
        training["excluded_case_ids"] = ["fake"]
    elif mutation == "duplicate_declared":
        training["declared_training_sample_hashes"] += [_hash(11)]
    elif mutation == "foreign_declared":
        training["declared_training_sample_hashes"][1] = _hash(99)
    elif mutation == "missing_row":
        training["unverified_rows"] = []
    elif mutation == "duplicate_unknown":
        training["unverified_rows"] += [deepcopy(training["unverified_rows"][0])]
    elif mutation == "roster_order":
        # Two known rows make the subsequence ordering check observable.
        training, _ = _full_training(gate_module)
        training["declared_training_sample_hashes"].reverse()
    elif mutation == "bool_fit":
        row["seed_fit_index"] = True
    elif mutation == "future_feature":
        row["prior_work_context"]["current_target_work"] = {"core_calls": 0}
    elif mutation == "unknown_zero":
        training["unverified_rows"][0]["cost_target"] = 0.0
    elif mutation == "unknown_known_cost":
        training["unverified_rows"][0]["cost_repetitions"][0].update(
            comparison_pass=True, path_time_ratio=0.98
        )
    elif mutation == "counts":
        training["verified_positive_count"] = True
    elif mutation == "seed":
        training["seed_policy_hash"] = "unbound"
    elif mutation == "teacher":
        training["teacher_roster_hash"] = "unbound"
    elif mutation == "destination_teacher":
        row["policy_hash"] = training["seed_policy_hash"]
    elif mutation == "row_extra":
        row["outer_group_index"] = 0
    elif mutation == "values":
        row["values"][-1] += 1.0
    elif mutation == "bool_value":
        row["values"][-1] = False
    elif mutation == "target":
        row["cost_target"] = 0.9
    elif mutation == "label":
        row["label"] = False
    elif mutation == "promoted":
        training["gate_fitted"] = True
    elif mutation == "independent":
        training["independent_evaluation"] = True
    elif mutation == "empty_scope":
        training["normalization_scope"] = ""
    else:
        training["declared_training_sample_hashes"] = tuple(
            training["declared_training_sample_hashes"]
        )
    with pytest.raises(ValueError):
        gate_module.fit_full_training_prior_work_cost_gate(training)


def test_full_all_unknown_fit_stays_hold_without_zero_statistics(gate_module):
    training, _ = _full_training(gate_module, unknown=True)
    row = training["training_rows"].pop()
    row["label"], row["cost_target"] = None, None
    row["cost_repetitions"][0].update(comparison_pass=False, path_time_ratio=None)
    training["unverified_rows"].insert(0, row)
    training["verified_positive_count"] = training["verified_negative_count"] = 0
    with pytest.raises(ValueError, match="nonempty"):
        gate_module.fit_full_training_prior_work_cost_gate(training)


@pytest.mark.parametrize(
    "mutation",
    [
        "two",
        "duplicate_index",
        "boolean_index",
        "boolean_pass",
        "boolean_ratio",
        "string_ratio",
        "foreign_report",
        "extra_field",
        "tuple_rows",
    ],
)
def test_full_fit_rechecks_three_typed_original_repetition_records(
    gate_module, mutation
):
    training, _ = _full_training(gate_module)
    row = training["training_rows"][0]
    repetition = row["cost_repetitions"][0]
    if mutation == "two":
        row["cost_repetitions"].pop()
    elif mutation == "duplicate_index":
        repetition["repetition"] = 1
    elif mutation == "boolean_index":
        repetition["repetition"] = False
    elif mutation == "boolean_pass":
        repetition["comparison_pass"] = 1
    elif mutation == "boolean_ratio":
        repetition["path_time_ratio"] = True
    elif mutation == "string_ratio":
        repetition["path_time_ratio"] = "0.98"
    elif mutation == "foreign_report":
        repetition["report_hash"] = "unsigned"
    elif mutation == "extra_field":
        repetition["current_target_core_calls"] = 0
    else:
        row["cost_repetitions"] = tuple(row["cost_repetitions"])
    with pytest.raises(ValueError):
        gate_module.fit_full_training_prior_work_cost_gate(training)


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "seed_hash",
        "teacher_hash",
        "bad_hash",
        "duplicate_json",
        "extra_outer",
        "scope",
        "exclusions",
        "counts_bool",
        "count_mismatch",
        "declared_missing",
        "duplicate_hash",
        "known_unknown_overlap",
        "unknown_count_bool",
        "unknown_count",
        "known_order",
        "threshold",
        "ridge",
        "target_profile",
        "boolean_array",
        "scale",
        "feature_layout",
        "weight_width",
        "hash_changed",
    ],
)
def test_full_decoder_is_strict_even_for_self_consistently_rehashed_mutations(
    gate_module, mutation
):
    training, _ = _full_training(gate_module, unknown=True)
    gate, _ = gate_module.fit_full_training_prior_work_cost_gate(training)
    payload = gate.to_dict()
    if mutation == "duplicate_json":
        with pytest.raises(ValueError):
            gate_module.FullTrainingPriorWorkCostMarginGate(
                '{"seed_policy_hash":"foreign",' + gate._json[1:]
            )
        return
    if mutation == "schema":
        payload["schema_version"] = gate_module.SCHEMA
    elif mutation == "seed_hash":
        payload["seed_policy_hash"] = "foreign"
    elif mutation == "teacher_hash":
        payload["teacher_roster_hash"] = True
    elif mutation == "bad_hash":
        payload["training_rows_hash"] = None
    elif mutation == "extra_outer":
        payload["outer_group_index"] = 0
    elif mutation == "scope":
        payload["training_scope"] = "fold"
    elif mutation == "exclusions":
        payload["excluded_case_ids"] = ["outer"]
    elif mutation == "counts_bool":
        payload["positive_count"] = True
    elif mutation == "count_mismatch":
        payload["positive_count"] += 1
    elif mutation == "declared_missing":
        payload["declared_training_sample_hashes"].pop()
    elif mutation == "duplicate_hash":
        payload["declared_training_sample_hashes"] += [
            payload["declared_training_sample_hashes"][0]
        ]
    elif mutation == "known_unknown_overlap":
        payload["unverified_sample_hashes"] = payload["training_sample_hashes"][:]
    elif mutation == "unknown_count_bool":
        payload["unverified_count"] = True
    elif mutation == "unknown_count":
        payload["unverified_count"] = 0
    elif mutation == "known_order":
        training, _ = _full_training(gate_module)
        gate, _ = gate_module.fit_full_training_prior_work_cost_gate(training)
        payload = gate.to_dict()
        payload["training_sample_hashes"].reverse()
    elif mutation == "threshold":
        payload["threshold"] = 0.001
    elif mutation == "ridge":
        payload["ridge"] = 0.1
    elif mutation == "target_profile":
        payload["cost_target_profile"] = "tuned"
    elif mutation == "boolean_array":
        payload["mean"][0] = True
    elif mutation == "scale":
        payload["scale"][0] = 0.0
    elif mutation == "feature_layout":
        payload["feature_names"][-1] = "target_work"
    elif mutation == "weight_width":
        payload["weights"].pop()
    else:
        payload["weights"][-1] += 1.0
    if mutation != "hash_changed":
        payload.pop("policy_hash")
        payload["policy_hash"] = _sha(_bytes(payload))
    with pytest.raises(ValueError):
        gate_module.FullTrainingPriorWorkCostMarginGate(_bytes(payload).decode())


def test_full_binding_checks_actual_seed_roster_model_and_causal_context(gate_module):
    training, seed = _full_training(gate_module, ratios=(0.98, 0.98), widths=(0.4, 0.4))
    gate, _ = gate_module.fit_full_training_prior_work_cost_gate(training)
    context = _codec_context()
    model = _codec_model(context)
    binding = gate_module.full_training_prior_work_guard_binding(
        gate, policy=seed, model_features=model
    )
    assert set(binding) == {
        "guard",
        "guard_identity",
        "seed_policy_hash",
        "excluded_case_ids",
    }
    assert binding["guard_identity"] == gate.policy_hash
    assert binding["seed_policy_hash"] == seed.policy_hash
    assert binding["excluded_case_ids"] == ()
    assert binding["guard"](context) is True
    assert binding["guard"](_codec_context(assembly=False)) is False
    assert binding["guard"](_context()) is False
    assert binding["guard"](None) is False


@pytest.mark.parametrize(
    "mutation", ["seed", "seed_roster", "model", "names", "fold_gate", "opaque_seed"]
)
def test_full_binding_rejects_fold_or_foreign_destination(gate_module, mutation):
    training, seed = _full_training(gate_module)
    gate, _ = gate_module.fit_full_training_prior_work_cost_gate(training)
    model = _codec_model(_codec_context())
    if mutation in ("seed", "seed_roster"):
        p = seed.to_dict()
        if mutation == "seed":
            p["weights"][0][0] = 1.0
        else:
            p["training_sample_hashes"].reverse()
        p.pop("policy_hash")
        p["policy_hash"] = _sha(_bytes(p))
        seed = RCControlSeedPolicy(_bytes(p).decode())
        if mutation == "seed_roster":
            # Even a gate re-bound to this hash must reject reordered actual seed samples.
            p = gate.to_dict()
            p["seed_policy_hash"] = seed.policy_hash
            p.pop("policy_hash")
            p["policy_hash"] = _sha(_bytes(p))
            gate = gate_module.FullTrainingPriorWorkCostMarginGate(_bytes(p).decode())
    elif mutation == "model":
        model = replace(model, context_hash=_hash(99))
    elif mutation == "names":
        model = replace(model, feature_names=("height",))
    elif mutation == "fold_gate":
        gate = _gate(gate_module)
    else:
        from types import SimpleNamespace

        seed = SimpleNamespace(policy_hash=gate.seed_policy_hash)
    with pytest.raises(ValueError):
        gate_module.full_training_prior_work_guard_binding(
            gate, policy=seed, model_features=model
        )
