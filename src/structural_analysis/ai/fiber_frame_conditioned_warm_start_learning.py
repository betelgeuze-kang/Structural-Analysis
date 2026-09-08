"""Train-only model-conditioned guesses; the Newton solver retains authority.

Physical coordinates are solver coordinates times their per-input scale. Thus
translation features are metres and rotation features are radians, even when
different models use different rotation-coordinate length scales.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
import re
from time import perf_counter_ns
from typing import Any

import numpy as np

from structural_analysis.ai.fiber_frame_warm_start_features import (
    MODEL_FEATURE_PROFILE,
    FiberFrameWarmStartModelFeatures,
    decode_fiber_frame_warm_start_model_features,
)
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    FiberFrameWarmStartLearningError,
    FiberFrameWarmStartSample,
    _features,
    _finite,
    _hash,
    _input_snapshot,
    _validate_model_coordinate_scale,
    _vector,
    validate_fiber_frame_warm_start_dataset,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    FiberFrameWarmStartInput,
    FiberFrameWarmStartProposal,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


POLICY_SCHEMA = "fiber-frame-conditioned-warm-start-policy.v2"


def _model_features(
    value: FiberFrameWarmStartInput,
) -> FiberFrameWarmStartModelFeatures:
    features = value.model_features
    if type(features) is not FiberFrameWarmStartModelFeatures:
        raise FiberFrameWarmStartLearningError(
            "model_features: typed features required"
        )
    try:
        snapshot = decode_fiber_frame_warm_start_model_features(features.to_dict())
    except (ValueError, TypeError, OverflowError, AttributeError, KeyError) as exc:
        raise FiberFrameWarmStartLearningError(
            "model_features: invalid snapshot"
        ) from exc
    if snapshot.problem_contract_hash != value.problem_contract_hash:
        raise FiberFrameWarmStartLearningError(
            "model_features: problem binding mismatch"
        )
    _validate_model_coordinate_scale(
        snapshot, value.free_global_dofs, value.physical_coordinate_scale
    )
    return snapshot


def _conditioned_features(
    value: FiberFrameWarmStartInput, model: FiberFrameWarmStartModelFeatures
) -> np.ndarray:
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            scale = np.asarray(value.physical_coordinate_scale)
            physical = replace(
                value,
                parent_free_coordinates_m=tuple(
                    np.asarray(value.parent_free_coordinates_m) * scale
                ),
                previous_free_coordinates_m=None
                if value.previous_free_coordinates_m is None
                else tuple(np.asarray(value.previous_free_coordinates_m) * scale),
            )
            result = np.concatenate((np.asarray(model.values), _features(physical)))
    except FloatingPointError as exc:
        raise FiberFrameWarmStartLearningError("features: arithmetic overflow") from exc
    if not np.all(np.isfinite(result)):
        raise FiberFrameWarmStartLearningError("features: nonfinite result")
    return result


@dataclass(frozen=True)
class FiberFrameConditionedWarmStartPolicy:
    """Immutable ridge artifact bound to topology/material context and feature layout."""

    free_global_dofs: tuple[int, ...]
    context_hash: str
    model_feature_names: tuple[str, ...]
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    feature_min: tuple[float, ...]
    feature_max: tuple[float, ...]
    target_scale: tuple[float, ...]
    weights: tuple[tuple[float, ...], ...]
    training_sample_hashes: tuple[str, ...]
    ridge: float
    ood_margin: float
    model_feature_profile: str = field(default=MODEL_FEATURE_PROFILE, init=False)
    policy_id: str = field(
        default="research-model-conditioned-ridge-displacement-warm-start", init=False
    )
    policy_version: str = field(default="v2", init=False)
    artifact_hash: str = field(init=False)

    def __post_init__(self) -> None:
        try:
            dofs = tuple(self.free_global_dofs)
            names = tuple(self.model_feature_names)
            matrix = tuple(_vector(row, "weights") for row in self.weights)
            hashes = tuple(
                _hash(item, "training_sample_hash")
                for item in self.training_sample_hashes
            )
        except TypeError as exc:
            raise FiberFrameWarmStartLearningError(
                "policy: sequences required"
            ) from exc
        if (
            not dofs
            or any(type(item) is not int or item < 0 for item in dofs)
            or tuple(sorted(set(dofs))) != dofs
        ):
            raise FiberFrameWarmStartLearningError("policy: invalid DOF profile")
        if (
            not names
            or len(names) > 2048
            or any(
                type(name) is not str
                or re.fullmatch(r"[a-z][a-z0-9_]{0,127}", name) is None
                for name in names
            )
            or len(set(names)) != len(names)
        ):
            raise FiberFrameWarmStartLearningError(
                "policy: invalid model feature layout"
            )
        if len(hashes) < 2 or tuple(sorted(set(hashes))) != hashes:
            raise FiberFrameWarmStartLearningError(
                "policy: unique ordered training hashes required"
            )
        _hash(self.context_hash, "context_hash")
        for name, value in (
            ("free_global_dofs", dofs),
            ("model_feature_names", names),
            ("weights", matrix),
            ("training_sample_hashes", hashes),
        ):
            object.__setattr__(self, name, value)
        for name in (
            "feature_mean",
            "feature_scale",
            "feature_min",
            "feature_max",
            "target_scale",
        ):
            object.__setattr__(self, name, _vector(getattr(self, name), name))
        size = len(names) + 3 * len(dofs) + 4
        if any(
            len(getattr(self, name)) != size
            for name in ("feature_mean", "feature_scale", "feature_min", "feature_max")
        ):
            raise FiberFrameWarmStartLearningError("policy: feature shape mismatch")
        if (
            len(self.target_scale) != len(dofs)
            or len(matrix) != size + 1
            or any(len(row) != len(dofs) for row in matrix)
        ):
            raise FiberFrameWarmStartLearningError("policy: output shape mismatch")
        if any(
            item <= 0
            for name in ("feature_scale", "target_scale")
            for item in getattr(self, name)
        ):
            raise FiberFrameWarmStartLearningError("policy: positive scales required")
        if any(
            low > high
            for low, high in zip(self.feature_min, self.feature_max, strict=True)
        ):
            raise FiberFrameWarmStartLearningError(
                "policy: inconsistent feature bounds"
            )
        for name in ("ridge", "ood_margin"):
            value = _finite(getattr(self, name), name)
            if value < 0 or (name == "ridge" and value == 0):
                raise FiberFrameWarmStartLearningError(f"{name}: invalid range")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "artifact_hash", canonical_hash(self._payload()))

    def _payload(self) -> dict[str, Any]:
        result = {
            "schema_version": POLICY_SCHEMA,
            **{
                name: getattr(self, name)
                for name in (
                    "policy_id",
                    "policy_version",
                    "model_feature_profile",
                    "free_global_dofs",
                    "context_hash",
                    "model_feature_names",
                    "feature_mean",
                    "feature_scale",
                    "feature_min",
                    "feature_max",
                    "target_scale",
                    "weights",
                    "training_sample_hashes",
                    "ridge",
                    "ood_margin",
                )
            },
            "feature_contract": "preanalysis_model_and_physical_parent_previous_coordinates_and_load_factors.v1",
            "physical_coordinate_conversion": "solver_coordinates_times_per_input_physical_coordinate_scale",
            "prediction_target": "next_accepted_physical_coordinate_increment_m_and_rad",
            "preprocessing_fit_split": "train",
            "uncertainty_kind": "uncalibrated_feature_range_indicator_not_probability",
            "production_promotion_eligible": False,
            "physical_result_authority": False,
            "external_verification_claimed": False,
        }
        # JSON-shaped detached exports are also accepted by the strict decoder.
        return {
            key: [list(row) for row in value]
            if key == "weights"
            else list(value)
            if isinstance(value, tuple)
            else value
            for key, value in result.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "artifact_hash": self.artifact_hash}

    def propose(self, value: FiberFrameWarmStartInput) -> FiberFrameWarmStartProposal:
        if type(value) is not FiberFrameWarmStartInput:
            raise FiberFrameWarmStartLearningError(
                "runtime_input: exact input type required"
            )
        # Bad model metadata must not prevent a valid parent-only fallback.
        snapshot = _input_snapshot(replace(value, model_features=None))
        fallback = FiberFrameWarmStartProposal(
            snapshot.parent_free_coordinates_m, 1.0, True
        )
        try:
            model = _model_features(value)
            if (
                snapshot.free_global_dofs != self.free_global_dofs
                or model.context_hash != self.context_hash
                or model.feature_names != self.model_feature_names
            ):
                return fallback
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                features = _conditioned_features(snapshot, model)
                low, high = np.asarray(self.feature_min), np.asarray(self.feature_max)
                tolerance = np.maximum((high - low) * self.ood_margin, 1.0e-12)
                if np.any((features < low - tolerance) | (features > high + tolerance)):
                    return fallback
                normalized = (features - np.asarray(self.feature_mean)) / np.asarray(
                    self.feature_scale
                )
                physical_delta = (
                    np.append(normalized, 1.0) @ np.asarray(self.weights)
                ) * np.asarray(self.target_scale)
                prediction = np.asarray(
                    snapshot.parent_free_coordinates_m
                ) + physical_delta / np.asarray(snapshot.physical_coordinate_scale)
                if not np.all(np.isfinite(prediction)):
                    return fallback
        except (FloatingPointError, FiberFrameWarmStartLearningError):
            return fallback
        return FiberFrameWarmStartProposal(
            tuple(float(x) for x in prediction), 0.0, False
        )


@dataclass(frozen=True)
class FiberFrameConditionedWarmStartTrainingResult:
    policy: FiberFrameConditionedWarmStartPolicy
    training_wall_ns: int
    _dataset_samples: tuple[FiberFrameWarmStartSample, ...] = field(repr=False)

    @property
    def dataset_report(self) -> dict[str, Any]:
        return validate_fiber_frame_warm_start_dataset(self._dataset_samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "fiber-frame-conditioned-warm-start-training-result.v2",
            "policy": self.policy.to_dict(),
            "dataset_report": self.dataset_report,
            "training_wall_ns": self.training_wall_ns,
            "training_timing_profile": "local-perf-counter-ns-sidecar.v1",
            "training_timing_enters_policy_identity": False,
            "production_promotion_eligible": False,
        }


def train_fiber_frame_conditioned_warm_start_policy(
    samples: Sequence[FiberFrameWarmStartSample],
    *,
    ridge: float = 1.0e-6,
    ood_margin: float = 0.1,
) -> FiberFrameConditionedWarmStartTrainingResult:
    """Fit geometry/load and physical-coordinate features using train rows only."""
    started = perf_counter_ns()
    rows = tuple(samples)
    validate_fiber_frame_warm_start_dataset(rows)
    ridge, ood_margin = _finite(ridge, "ridge"), _finite(ood_margin, "ood_margin")
    if ridge <= 0 or ood_margin < 0:
        raise FiberFrameWarmStartLearningError("training: ridge and OOD margin invalid")
    training = sorted(
        (row for row in rows if row.split == "train"), key=lambda row: row.sample_hash
    )
    if len(training) < 2:
        raise FiberFrameWarmStartLearningError(
            "training: at least two train rows required"
        )
    inputs = [_input_snapshot(row.runtime_input) for row in training]
    models = [_model_features(value) for value in inputs]
    profile = (
        inputs[0].free_global_dofs,
        models[0].context_hash,
        models[0].feature_names,
    )
    if any(
        (value.free_global_dofs, model.context_hash, model.feature_names) != profile
        for value, model in zip(inputs, models, strict=True)
    ):
        raise FiberFrameWarmStartLearningError(
            "training: one topology/material context and feature layout required"
        )
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            features = np.vstack(
                [
                    _conditioned_features(value, model)
                    for value, model in zip(inputs, models, strict=True)
                ]
            )
            targets = np.vstack(
                [
                    (
                        np.asarray(row.accepted_target_free_coordinates_m)
                        - np.asarray(value.parent_free_coordinates_m)
                    )
                    * np.asarray(value.physical_coordinate_scale)
                    for row, value in zip(training, inputs, strict=True)
                ]
            )
            mean = features.mean(axis=0)
            scale = np.maximum(np.max(np.abs(features - mean), axis=0), 1.0e-12)
            normalized = (features - mean) / scale
            target_scale = np.maximum(np.max(np.abs(targets), axis=0), 1.0e-12)
            design = np.column_stack((normalized, np.ones(len(training))))
            regularizer = np.sqrt(ridge) * np.eye(design.shape[1])
            regularizer[-1, -1] = 0.0
            weights, _, _, _ = np.linalg.lstsq(
                np.vstack((design, regularizer)),
                np.vstack(
                    (
                        targets / target_scale,
                        np.zeros((design.shape[1], targets.shape[1])),
                    )
                ),
                rcond=None,
            )
            if any(
                not np.all(np.isfinite(value))
                for value in (mean, scale, target_scale, weights)
            ):
                raise FiberFrameWarmStartLearningError(
                    "training: nonfinite fitted parameters"
                )
    except (FloatingPointError, np.linalg.LinAlgError) as exc:
        raise FiberFrameWarmStartLearningError(
            "training: numerical overflow or fit failure"
        ) from exc
    policy = FiberFrameConditionedWarmStartPolicy(
        *profile,
        tuple(mean),
        tuple(scale),
        tuple(features.min(axis=0)),
        tuple(features.max(axis=0)),
        tuple(target_scale),
        tuple(tuple(row) for row in weights),
        tuple(row.sample_hash for row in training),
        ridge,
        ood_margin,
    )
    return FiberFrameConditionedWarmStartTrainingResult(
        policy, perf_counter_ns() - started, rows
    )


def decode_fiber_frame_conditioned_warm_start_policy(
    value: dict[str, Any],
) -> FiberFrameConditionedWarmStartPolicy:
    """Decode a complete, internally hash-bound artifact without fitting it."""
    from dataclasses import fields

    constructor = {
        item.name for item in fields(FiberFrameConditionedWarmStartPolicy) if item.init
    }
    metadata = {
        "schema_version",
        "policy_id",
        "policy_version",
        "model_feature_profile",
        "feature_contract",
        "physical_coordinate_conversion",
        "prediction_target",
        "preprocessing_fit_split",
        "uncertainty_kind",
        "production_promotion_eligible",
        "physical_result_authority",
        "external_verification_claimed",
        "artifact_hash",
    }
    if type(value) is not dict or set(value) != constructor | metadata:
        raise FiberFrameWarmStartLearningError("policy: exact artifact fields required")
    vectors = {
        "free_global_dofs",
        "model_feature_names",
        "feature_mean",
        "feature_scale",
        "feature_min",
        "feature_max",
        "target_scale",
        "training_sample_hashes",
        "weights",
    }
    if any(type(value[name]) is not list for name in vectors) or any(
        type(row) is not list for row in value["weights"]
    ):
        raise FiberFrameWarmStartLearningError("policy: JSON arrays required")
    try:
        policy = FiberFrameConditionedWarmStartPolicy(
            **{name: value[name] for name in constructor}
        )
        if canonical_hash(value) != canonical_hash(policy.to_dict()):
            raise FiberFrameWarmStartLearningError(
                "policy: artifact identity or profile mismatch"
            )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FiberFrameWarmStartLearningError(
            "policy: invalid conditioned artifact"
        ) from exc
    return policy
