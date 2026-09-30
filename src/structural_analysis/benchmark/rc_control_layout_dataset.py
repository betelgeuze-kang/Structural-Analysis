"""Train-only layout preprocessing with explicit fixed-history split scope.

This does not replace the joint geometry/history warm-start split contract.
No labels, fitted response policy or authenticated project evidence are created.
"""

import numpy as np

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_layout_features import (
    LAYOUT_FEATURE_NAMES,
    PROFILE,
    control_layout_candidate_features,
)
from structural_analysis.benchmark.rc_control_learning import RCControlLearningCase
from structural_analysis.benchmark.rc_control_learning_split import (
    geometry_shapes_overlap,
)


def prepare_control_layout_dataset(cases):
    """Prepare 2+ training cases and separate validation/holdout geometry groups."""
    if (
        type(cases) is not tuple
        or not 4 <= len(cases) <= 32
        or any(type(c) is not RCControlLearningCase for c in cases)
    ):
        raise ValueError("four to 32 typed layout cases required")
    ordered = sorted(cases, key=lambda c: c.case_id)
    if len({c.case_id for c in ordered}) != len(ordered):
        raise ValueError("unique layout case identities required")
    counts = {
        split: sum(c.split == split for c in ordered)
        for split in ("train", "validation", "holdout")
    }
    if counts["train"] < 2 or not counts["validation"] or not counts["holdout"]:
        raise ValueError("training, validation and holdout cases required")
    if any(c.measurement_source is not None for c in ordered):
        raise ValueError(
            "external measured labels require a separate admission contract"
        )
    if len({c.load_history_id for c in ordered}) != 1:
        raise ValueError(
            "declare the shared fixed history, not independent history labels"
        )
    records = []
    for case in ordered:
        descriptor = control_layout_candidate_features(case.model, case.request)
        records.append(
            {
                "case_id": case.case_id,
                "project_id": case.project_id,
                "geometry_family_id": case.geometry_family_id,
                "load_history_id": case.load_history_id,
                "split": case.split,
                "descriptor": descriptor,
            }
        )
    if len({r["descriptor"]["context_hash"] for r in records}) != 1:
        raise ValueError("one fixed topology/material/load-history context required")
    if len({r["descriptor"]["physical_model_identity"] for r in records}) != len(
        records
    ):
        raise ValueError("duplicate physical layout model")
    parents = list(range(len(records)))

    def find(i):
        while parents[i] != i:
            i = parents[i]
        return i

    for i, row in enumerate(records):
        for j, previous in enumerate(records[:i]):
            overlap = geometry_shapes_overlap(
                row["descriptor"]["geometry_shape_screen"],
                previous["descriptor"]["geometry_shape_screen"],
            )
            if overlap:
                parents[find(i)] = find(j)
            if row["split"] != previous["split"] and (
                overlap
                or row["project_id"] == previous["project_id"]
                or row["geometry_family_id"] == previous["geometry_family_id"]
            ):
                raise ValueError("split_leakage: project_or_geometry_overlap")
    groups: dict[int, list[str]] = {}
    for i, row in enumerate(records):
        groups.setdefault(find(i), []).append(row["case_id"])
    train = [r for r in records if r["split"] == "train"]
    if len({find(i) for i, row in enumerate(records) if row["split"] == "train"}) < 2:
        raise ValueError("two distinct training geometry groups required")
    x = np.asarray([r["descriptor"]["values"] for r in train], dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        mean, scale = x.mean(axis=0), x.std(axis=0)
    if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)):
        raise ValueError("finite training-only normalization required")
    constant = scale == 0
    scale[constant] = 1.0
    low, high = x.min(axis=0), x.max(axis=0)
    for row in records:
        v = np.asarray(row["descriptor"]["values"])
        row["outside_train_minmax_features"] = [
            name
            for name, outside in zip(
                LAYOUT_FEATURE_NAMES, (v < low) | (v > high), strict=True
            )
            if outside
        ]
    result = {
        "schema_version": "experimental-rc-control-layout-dataset.v1",
        "feature_profile": PROFILE,
        "feature_names": list(LAYOUT_FEATURE_NAMES),
        "context_hash": records[0]["descriptor"]["context_hash"],
        "cases": records,
        "split_counts": counts,
        "geometry_groups": list(groups.values()),
        "preprocessing": {
            "fit_split": "train",
            "weighting": "one_row_per_case",
            "case_ids": [r["case_id"] for r in train],
            "mean": mean.tolist(),
            "scale": scale.tolist(),
            "minimum": x.min(axis=0).tolist(),
            "maximum": x.max(axis=0).tolist(),
            "constant_columns": constant.tolist(),
        },
        "split_scope": "geometry_and_declared_project_groups_under_one_fixed_history",
        "independent_load_history_split": False,
        "project_provenance_authenticated": False,
        "joint_geometry_history_split": False,
        "response_policy_fitted": False,
        "external_labels_admitted": False,
        "physical_result_authority": False,
    }
    result["report_hash"] = _sha(_bytes(result))
    return result
