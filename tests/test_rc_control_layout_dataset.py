"""Fixed-history geometry splits must not masquerade as joint generalization."""

import pytest

from tests.test_rc_control_learning import case
from structural_analysis.benchmark.rc_control_layout_dataset import (
    prepare_control_layout_dataset,
)
from structural_analysis.benchmark.rc_control_learning_split import (
    validate_control_learning_split_shapes,
)


def roster(tmp_path, *, holdout=(6.0, 4.7), shared_project=False):
    return (
        case(tmp_path, "train-a", "train", lengths=(2.0, 1.5), load="fixed-history"),
        case(tmp_path, "train-b", "train", lengths=(3.0, 2.5), load="fixed-history"),
        case(
            tmp_path,
            "validation",
            "validation",
            lengths=(2.5, 2.0),
            load="fixed-history",
        ),
        case(
            tmp_path,
            "holdout",
            "holdout",
            lengths=holdout,
            load="fixed-history",
            project="train-a" if shared_project else "holdout",
        ),
    )


def test_preprocessing_is_train_only_and_input_order_does_not_change_identity(tmp_path):
    cases = roster(tmp_path)
    a = prepare_control_layout_dataset(cases)
    b = prepare_control_layout_dataset(roster(tmp_path, holdout=(7.0, 4.1)))
    assert a["preprocessing"] == b["preprocessing"]
    assert a["report_hash"] != b["report_hash"]
    assert a == prepare_control_layout_dataset(tuple(reversed(cases)))
    assert a["split_counts"] == {"train": 2, "validation": 1, "holdout": 1}
    assert len(a["geometry_groups"]) == 4
    assert a["independent_load_history_split"] is False
    assert a["joint_geometry_history_split"] is False
    assert a["project_provenance_authenticated"] is False
    assert a["response_policy_fitted"] is False
    # The existing joint split gate remains strict despite this scoped preparation.
    with pytest.raises(ValueError, match="resampled_control_history"):
        validate_control_learning_split_shapes(cases)


@pytest.mark.parametrize(
    "change",
    [
        "scaled",
        "duplicate_model",
        "project",
        "missing_holdout",
        "duplicate_case",
        "history_label",
        "history_values",
        "family",
    ],
)
def test_rejects_leaking_or_misdeclared_layout_rosters(tmp_path, change):
    cases = roster(
        tmp_path,
        holdout=(4.0, 3.0) if change == "scaled" else (6.0, 4.7),
        shared_project=change == "project",
    )
    if change == "duplicate_model":
        cases = roster(tmp_path, holdout=(2.0, 1.5))
    if change == "missing_holdout":
        cases = cases[:-1]
    if change == "duplicate_case":
        cases = cases + (cases[0],)
    if change in ("history_label", "history_values", "family"):
        kwargs = {
            "lengths": (6.0, 4.7),
            "load": "other" if change == "history_label" else "fixed-history",
        }
        if change == "history_values":
            kwargs["history"] = (-1e-5, -2e-5, 1e-5)
        if change == "family":
            kwargs["family"] = "train-a"
        cases = cases[:-1] + (case(tmp_path, "holdout", "holdout", **kwargs),)
    with pytest.raises(ValueError):
        prepare_control_layout_dataset(cases)


def test_scaled_training_aliases_do_not_supply_two_geometry_groups(tmp_path):
    cases = roster(tmp_path)
    scaled = case(
        tmp_path, "train-b", "train", lengths=(4.0, 3.0), load="fixed-history"
    )
    with pytest.raises(ValueError, match="two distinct training geometry groups"):
        prepare_control_layout_dataset((cases[0], scaled, *cases[2:]))
