"""Explicit pre-solve switching inputs without material state or step identity."""

from structural_analysis.benchmark.rc_control_learning import _features

PROFILE = "rc-switch-accepted-prefix-features.v1"


def prefix_features(context, model_features):
    values = _features(context, model_features)
    width = len(model_features.feature_names)
    # Drop accepted-step count. Keep physical targets/increments and last states.
    selected = [*values[: width + 3], *values[width + 4 :]]
    coordinates = len(context.accepted_augmented_coordinates_m[-1])
    names = [
        *("model." + name for name in model_features.feature_names),
        "target_m",
        "target_increment_m",
        "previous_target_increment_m",
        *(f"last_coordinate_{i}" for i in range(coordinates)),
        *(f"coordinate_increment_{i}" for i in range(coordinates)),
    ]
    if len(names) != len(selected) or len(set(names)) != len(names):
        raise ValueError("unique aligned prefix features required")
    return {
        "profile": PROFILE,
        "feature_names": names,
        "values": [float(v) for v in selected],
    }


PRIOR_WORK_PROFILE = "rc-switch-accepted-prefix-prior-work-features.v1"
PRIOR_WORK_COUNTERS = (
    "core_calls",
    "newton_iterations",
    "linear_solves",
    "assembly_dispatches",
    "line_search_dispatches",
    "terminal_refinement_dispatches",
)


def prefix_prior_work_features(context, model_features):
    """Append known work from this arm's immediately preceding accepted step.

    Identity fields validate the predecessor; they never enter this vector.
    This profile requires all six counters. Unrecorded dispatch counts are not
    zero. The callback caller must abstain when this function raises ValueError.
    """
    from structural_analysis.ai.fiber_frame_warm_start_features import (
        FiberFrameWarmStartModelFeatures,
    )
    from structural_analysis.benchmark.rc_control_prior_work import (
        validate_rc_control_prior_work,
    )
    from math import isfinite

    if type(model_features) is not FiberFrameWarmStartModelFeatures:
        raise ValueError("exact typed model features required")
    previous = validate_rc_control_prior_work(context)
    if (
        type(context.target_m) not in (int, float)
        or (type(context.target_m) is int and abs(context.target_m) > 2**53 - 1)
        or not isfinite(context.target_m)
    ):
        raise ValueError("exact finite current target required")
    counters = [getattr(previous, name) for name in PRIOR_WORK_COUNTERS]
    if any(type(value) is not int or not 0 <= value <= 2**53 - 1 for value in counters):
        raise ValueError("all exact known predecessor counters required")
    prefix = prefix_features(context, model_features)
    return {
        "profile": PRIOR_WORK_PROFILE,
        "feature_names": [
            *prefix["feature_names"],
            *("prior_work." + name for name in PRIOR_WORK_COUNTERS),
        ],
        "values": [*prefix["values"], *(float(value) for value in counters)],
    }
