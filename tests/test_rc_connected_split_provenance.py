"""Actual typed-case shape grouping and pure complete complement contracts."""

from copy import deepcopy
from dataclasses import replace
import importlib
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
)
from tests.test_rc_control_learning_split import make


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    result = importlib.import_module("rc_connected_split_provenance")

    def forbidden(*args, **kwargs):
        pytest.fail(
            "pure grouping/complement contracts must not fit or run numerical studies"
        )

    monkeypatch.setattr(learning, "_fit", forbidden)
    monkeypatch.setattr(learning, "run_rc_control_learning_study", forbidden)
    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", forbidden)
    return result


def _case(
    tmp_path,
    name,
    ratio,
    *,
    project=None,
    family=None,
    history_id=None,
    targets=None,
    model=None,
):
    case = make(
        tmp_path,
        name,
        "train",
        lengths=(2.0, 2.0 * ratio),
        targets=targets or (1e-7, -(1.0 + ratio) * 1e-7, 0.4e-7),
    )
    return learning.RCControlLearningCase(
        name,
        project or name,
        family or name,
        history_id or name,
        "train",
        model or case.model,
        case.request,
    )


def _samples(cases):
    return [
        {
            "case_id": case.case_id,
            "split": "train",
            "target_index": index,
            "sample_hash": _sha(f"authored-{case.case_id}-{index}".encode()),
            "parent_hash": _sha(f"parent-{case.case_id}-{index}".encode()),
            "label": None if index == 2 else False,
            "correction": [0.0, 0.0],
            "cost_repetitions": [],
        }
        for case in cases
        for index in (1, 2)
    ]


def _independent(tmp_path):
    cases = [
        _case(tmp_path, name, ratio)
        for name, ratio in zip("ABCD", (0.2, 0.3, 0.4, 0.5))
    ]
    return cases, _samples(cases), [[case.case_id] for case in cases]


def _plans(module, cases, samples, groups):
    return dict(
        cases=cases,
        source_samples=samples,
        groups=groups,
        inner_plan=module.inner_validation_plan(groups, samples),
        retained_seed_plan=module.nested_plan(groups, samples),
    )


def _policy(hashes, *, ridge=10000.0):
    """Schema-valid authored policy, never fitted on observations."""
    payload = dict(
        schema_version="experimental-rc-control-secant-correction-policy.v1",
        model_context_hash=_sha(b"context"),
        model_feature_names=["width"],
        free_global_dofs=[7],
        control_free_index=0,
        solver_config_hash=_sha(b"solver"),
        feature_mean=[0.0] * 9,
        feature_scale=[1.0] * 9,
        feature_min=[-10.0] * 9,
        feature_max=[10.0] * 9,
        target_scale=[1.0, 1.0],
        weights=[[0.0, 0.0] for _ in range(10)],
        training_sample_hashes=list(hashes),
        ridge=ridge,
        ood_margin=0.1,
    )
    payload["policy_hash"] = _sha(_bytes(payload))
    return learning.RCControlSeedPolicy(_bytes(payload).decode())


def test_typed_cases_rebuild_exact_maximal_groups_and_keep_unknown_roster(
    tmp_path, module
):
    cases, samples, groups = _independent(tmp_path)
    before = deepcopy(samples)
    receipt = module.validate_connected_partition(
        cases=cases, source_samples=samples, groups=groups
    )
    assert receipt["groups"] == groups
    assert receipt["connections"] == []
    assert len(receipt["sample_roster"]) == 8
    assert {row["sample_hash"] for row in receipt["sample_roster"]} == {
        row["sample_hash"] for row in samples
    }
    assert b"label" not in _bytes(receipt) and b"cost_repetitions" not in _bytes(
        receipt
    )
    assert samples == before
    assert (
        receipt["numerical_solves"] == 0 and receipt["independent_provenance"] is False
    )
    assert receipt["provenance_hash"] == _sha(
        _bytes({k: v for k, v in receipt.items() if k != "provenance_hash"})
    )


@pytest.mark.parametrize("identity", ["project", "family", "history_id"])
def test_actual_shared_declaration_ids_connect_cases_without_trusting_nominal_groups(
    tmp_path, module, identity
):
    cases, _, _ = _independent(tmp_path)
    # Five distinct physical/history shapes become four components by one shared ID.
    cases.append(_case(tmp_path, "E", 0.6))
    first = cases[0]
    args = {
        identity: getattr(
            first,
            {
                "project": "project_id",
                "family": "geometry_family_id",
                "history_id": "load_history_id",
            }[identity],
        )
    }
    cases[1] = _case(tmp_path, "B", 0.3, **args)
    samples = _samples(cases)
    groups = [["A", "B"], ["C"], ["D"], ["E"]]
    receipt = module.validate_connected_partition(
        cases=cases, source_samples=samples, groups=groups
    )
    assert receipt["groups"] == groups and receipt["connections"][0]["reasons"]
    with pytest.raises(ValueError, match="maximal connected"):
        module.validate_connected_partition(
            cases=cases,
            source_samples=samples,
            groups=[[case.case_id] for case in cases],
        )


def test_transitive_A_B_C_closure_keeps_unconnected_endpoints_in_same_group(
    tmp_path, module
):
    cases = [
        _case(tmp_path, "A", 0.2, project="AB"),
        _case(tmp_path, "B", 0.3, project="AB", family="BC"),
        _case(tmp_path, "C", 0.4, family="BC"),
        *[_case(tmp_path, name, ratio) for name, ratio in zip("DEF", (0.5, 0.6, 0.7))],
    ]
    receipt = module.validate_connected_partition(
        cases=cases,
        source_samples=_samples(cases),
        groups=[["A", "B", "C"], ["D"], ["E"], ["F"]],
    )
    links = {tuple(row["case_ids"]) for row in receipt["connections"]}
    assert ("A", "B") in links and ("B", "C") in links and ("A", "C") not in links
    assert receipt["transitive_closure"] is True


@pytest.mark.parametrize(
    "mode", ["scaled_geometry", "resampled_history", "history_prefix"]
)
def test_renamed_physical_or_history_aliases_are_connected_using_current_authority(
    tmp_path, module, mode
):
    cases, _, _ = _independent(tmp_path)
    cases.append(_case(tmp_path, "E", 0.6))
    if mode == "scaled_geometry":
        alias = make(
            tmp_path,
            "alias",
            "train",
            lengths=(4.0, 0.8),
            targets=(1e-7, -1.7e-7, 0.4e-7),
            transform=lambda x: x + [4.0, -8.0, 0.0],
        )
    elif mode == "resampled_history":
        alias = make(
            tmp_path,
            "alias",
            "train",
            lengths=(2.0, 1.4),
            targets=(0.5e-7, 1e-7, -1.2e-7, 0.4e-7),
        )
    else:
        alias = make(
            tmp_path,
            "alias",
            "train",
            lengths=(2.0, 1.4),
            targets=(1e-7, -1.2e-7, 0.1e-7),
        )
    cases[1] = learning.RCControlLearningCase(
        "B", "B", "B", "B", "train", alias.model, alias.request
    )
    groups = [["A", "B"], ["C"], ["D"], ["E"]]
    receipt = module.validate_connected_partition(
        cases=cases, source_samples=_samples(cases), groups=groups
    )
    reasons = receipt["connections"][0]["reasons"]
    assert (
        "geometry_shape" if mode == "scaled_geometry" else "history_shape_or_prefix"
    ) in reasons


def test_less_than_four_genuine_components_is_hold_even_if_ids_claim_independence(
    tmp_path, module
):
    cases = [_case(tmp_path, name, 0.2) for name in "ABCD"]
    samples = _samples(cases)
    groups = control_training_exclusion_groups(cases)["groups"]
    assert groups == [["A", "B", "C", "D"]]
    with pytest.raises(ValueError, match="HOLD.*four connected"):
        module.validate_connected_partition(
            cases=cases, source_samples=samples, groups=groups
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "bool_target",
        "duplicate_hash",
        "duplicate_target",
        "foreign_case",
        "wrong_split",
        "missing_case",
        "malformed_parent",
        "group_omission",
        "group_foreign",
        "group_duplicate",
        "group_order",
        "group_tuple",
        "cases_duplicate",
        "untyped_case",
    ],
)
def test_malformed_or_incomplete_identity_rosters_reject(tmp_path, module, mutation):
    cases, samples, groups = _independent(tmp_path)
    if mutation == "bool_target":
        samples[0]["target_index"] = True
    elif mutation == "duplicate_hash":
        samples[1]["sample_hash"] = samples[0]["sample_hash"]
    elif mutation == "duplicate_target":
        samples[1]["target_index"] = samples[0]["target_index"]
    elif mutation == "foreign_case":
        samples[0]["case_id"] = "foreign"
    elif mutation == "wrong_split":
        samples[0]["split"] = "holdout"
    elif mutation == "missing_case":
        samples = [row for row in samples if row["case_id"] != "D"]
    elif mutation == "malformed_parent":
        samples[0]["parent_hash"] = "not-a-hash"
    elif mutation == "group_omission":
        groups.pop()
    elif mutation == "group_foreign":
        groups[-1] = ["foreign"]
    elif mutation == "group_duplicate":
        groups[1] = ["A"]
    elif mutation == "group_order":
        groups.reverse()
    elif mutation == "group_tuple":
        groups = tuple(groups)
    elif mutation == "cases_duplicate":
        cases.append(cases[0])
    else:
        cases[0] = cases[0].case_id
    with pytest.raises(ValueError):
        module.validate_connected_partition(
            cases=cases, source_samples=samples, groups=groups
        )


def test_current_unsupported_pinroller_and_zero_first_histories_remain_rejected(
    tmp_path, module
):
    cases, samples, groups = _independent(tmp_path)
    original = cases[0]
    pin = replace(original.request, experimental_pin_roller_beam=True)
    cases[0] = learning.RCControlLearningCase(
        "A", "A", "A", "A", "train", original.model, pin
    )
    with pytest.raises(ValueError, match="pin-roller"):
        module.validate_connected_partition(
            cases=cases, source_samples=samples, groups=groups
        )
    zero = BoundedRCFiberDirectControlRequest(7, (0.0, -1e-7, -2e-7))
    cases[0] = learning.RCControlLearningCase(
        "A", "A", "A", "A", "train", original.model, zero
    )
    with pytest.raises(ValueError, match="distinct control targets"):
        module.validate_connected_partition(
            cases=cases, source_samples=samples, groups=groups
        )


def test_exact_all_pair_and_triple_complements_and_outer_validation_exclusions(
    tmp_path, module
):
    cases, samples, groups = _independent(tmp_path)
    kwargs = _plans(module, cases, samples, groups)
    before = deepcopy({k: v for k, v in kwargs.items() if k != "cases"})
    receipt = module.validate_inner_validation_provenance(**kwargs)
    assert receipt["triple_seed_fit_count"] == 4
    assert receipt["pair_seed_fit_count"] == 6
    assert receipt["gate_fold_count"] == 12
    assert receipt["original_sample_count"] == 8
    assert receipt["exact_all_training_complements_checked"] is True
    assert receipt["outer_validation_label_exclusions_checked"] is True
    assert receipt["normalization_checked"] is False
    assert before == {k: v for k, v in kwargs.items() if k != "cases"}


@pytest.mark.parametrize(
    "mutation",
    [
        "bool_fit",
        "bool_exclusion",
        "bool_task",
        "missing_fit",
        "extra_fit",
        "incomplete_complement",
        "heldout_training_hash",
        "wrong_excluded_cases",
        "missing_task",
        "foreign_label",
        "missing_fold",
        "same_outer_validation",
        "wrong_fold_tasks",
        "retained_leak",
        "retained_index",
        "wrong_counts",
        "tuple_indices",
        "extra_claim",
        "foreign_retained_fit",
    ],
)
def test_complete_inner_and_retained_plans_reject_typed_tampering(
    tmp_path, module, mutation
):
    cases, samples, groups = _independent(tmp_path)
    kwargs = _plans(module, cases, samples, groups)
    plan, retained = kwargs["inner_plan"], kwargs["retained_seed_plan"]
    fit, task, fold = (
        plan["seed_fits"][0],
        plan["unique_new_label_tasks"][0],
        plan["gate_folds"][0],
    )
    if mutation == "bool_fit":
        fit["fit_index"] = False
    elif mutation == "bool_exclusion":
        fit["excluded_group_indices"][0] = False
    elif mutation == "bool_task":
        task["task_index"] = False
    elif mutation == "missing_fit":
        plan["seed_fits"].pop()
    elif mutation == "extra_fit":
        plan["seed_fits"].append(deepcopy(fit))
    elif mutation == "incomplete_complement":
        fit["training_sample_hashes"].pop()
    elif mutation == "heldout_training_hash":
        fit["training_sample_hashes"][0] = samples[0]["sample_hash"]
    elif mutation == "wrong_excluded_cases":
        fit["excluded_case_ids"].pop()
    elif mutation == "missing_task":
        plan["unique_new_label_tasks"].pop()
    elif mutation == "foreign_label":
        task["label_case_ids"] = ["A"]
    elif mutation == "missing_fold":
        plan["gate_folds"].pop()
    elif mutation == "same_outer_validation":
        fold["validation_group_index"] = fold["outer_group_index"]
    elif mutation == "wrong_fold_tasks":
        fold["training_label_task_indices"].reverse()
    elif mutation == "retained_leak":
        fold["validation_label_task"]["label_case_ids"] = ["A"]
    elif mutation == "retained_index":
        fold["validation_label_task"]["seed_fit_index"] = True
    elif mutation == "wrong_counts":
        plan["planned_new_comparisons"] = True
    elif mutation == "tuple_indices":
        fit["excluded_group_indices"] = tuple(fit["excluded_group_indices"])
    elif mutation == "extra_claim":
        plan["independent_validation"] = True
    else:
        retained["seed_fits"][0]["training_sample_hashes"].append(_sha(b"foreign"))
    with pytest.raises(ValueError):
        module.validate_inner_validation_provenance(**kwargs)


def test_excluded_numeric_perturbation_never_changes_groups_roster_or_plan_checks(
    tmp_path, module
):
    cases, samples, groups = _independent(tmp_path)
    original = module.validate_inner_validation_provenance(
        **_plans(module, cases, samples, groups)
    )
    changed = deepcopy(samples)
    for row in changed:
        if row["case_id"] in {"A", "B"}:
            row.update(
                label=True,
                correction=[1e100, -1e100],
                cost_repetitions=[{"future_cost": -99}],
            )
    assert (
        module.validate_inner_validation_provenance(
            **_plans(module, cases, changed, groups)
        )
        == original
    )


@pytest.mark.parametrize("kind", ["pair", "triple"])
def test_actual_typed_seed_training_hashes_match_exact_declared_complement(
    tmp_path, module, kind
):
    cases, samples, groups = _independent(tmp_path)
    planner = module.nested_plan if kind == "pair" else module.inner_validation_plan
    fit = planner(groups, samples)["seed_fits"][0]
    policy = _policy(fit["training_sample_hashes"])
    receipt = module.require_exact_seed_policy_complement(
        policy=policy, fit=fit, source_samples=samples
    )
    assert receipt["policy_hash"] == policy.policy_hash
    assert receipt["training_sample_hashes"] == fit["training_sample_hashes"]
    assert receipt["exact_complement_checked"] is True
    assert receipt["source_artifact_binding_checked"] is False
    assert receipt["normalization_checked"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_policy",
        "omitted_policy_hash",
        "reordered_policy",
        "untyped_policy",
        "bool_fit",
        "bool_group",
        "incomplete_fit",
        "duplicate_sample",
        "foreign_excluded_case",
        "ridge",
        "bool_sample_target",
        "missing_parent",
        "duplicate_target",
    ],
)
def test_seed_policy_and_fit_complement_boundaries_reject(tmp_path, module, mutation):
    cases, samples, groups = _independent(tmp_path)
    fit = module.nested_plan(groups, samples)["seed_fits"][0]
    hashes = list(fit["training_sample_hashes"])
    if mutation == "foreign_policy":
        hashes[0] = _sha(b"foreign")
    elif mutation == "omitted_policy_hash":
        hashes.pop()
    elif mutation == "reordered_policy":
        hashes.reverse()
    policy = _policy(hashes, ridge=1.0 if mutation == "ridge" else 10000.0)
    if mutation == "untyped_policy":
        policy = policy.to_dict()
    elif mutation == "bool_fit":
        fit["fit_index"] = False
    elif mutation == "bool_group":
        fit["excluded_group_indices"][0] = False
    elif mutation == "incomplete_fit":
        fit["training_sample_hashes"].pop()
    elif mutation == "duplicate_sample":
        samples.append(deepcopy(samples[0]))
    elif mutation == "foreign_excluded_case":
        fit["excluded_case_ids"][0] = "foreign"
    elif mutation == "bool_sample_target":
        samples[0]["target_index"] = True
    elif mutation == "missing_parent":
        samples[0].pop("parent_hash")
    elif mutation == "duplicate_target":
        samples[1]["target_index"] = samples[0]["target_index"]
    with pytest.raises(ValueError):
        module.require_exact_seed_policy_complement(
            policy=policy, fit=fit, source_samples=samples
        )


def test_parent_and_target_identity_projection_stays_bound_without_numeric_features(
    tmp_path, module
):
    cases, samples, groups = _independent(tmp_path)
    fit = module.nested_plan(groups, samples)["seed_fits"][0]
    policy = _policy(fit["training_sample_hashes"])
    original = module.require_exact_seed_policy_complement(
        policy=policy, fit=fit, source_samples=samples
    )
    changed = deepcopy(samples)
    changed[0]["parent_hash"] = _sha(b"different original parent")
    altered = module.require_exact_seed_policy_complement(
        policy=policy, fit=fit, source_samples=changed
    )
    assert (
        altered["original_sample_identity_roster_hash"]
        != original["original_sample_identity_roster_hash"]
    )
    assert altered["training_sample_hashes"] == original["training_sample_hashes"]
