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
