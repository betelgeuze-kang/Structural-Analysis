"""Train-only physical corrections to the accepted-history secant predictor.

This opt-in artifact leaves v2 and all Newton guards unchanged. A rejected or
out-of-distribution proposal abstains to the parent, including when a secant
baseline would otherwise be available. No solver response is produced here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, fields, replace
from time import perf_counter_ns
from typing import Any

import numpy as np

from structural_analysis.ai.fiber_frame_conditioned_warm_start_learning import (
    FiberFrameConditionedWarmStartPolicy,
    _conditioned_features,
    _model_features,
)
from structural_analysis.ai.fiber_frame_warm_start_features import MODEL_FEATURE_PROFILE
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    FiberFrameWarmStartLearningError,
    FiberFrameWarmStartSample,
    _finite,
    _input_snapshot,
    validate_fiber_frame_warm_start_dataset,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    FiberFrameWarmStartInput,
    FiberFrameWarmStartProposal,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


POLICY_SCHEMA = "fiber-frame-secant-correction-warm-start-policy.v3"
POLICY_ID = "research-model-conditioned-ridge-secant-correction-warm-start"
BASELINE_CONTRACT = (
    "accepted_parent_previous_secant_solver_coordinates_unequal_load_spacing"
    "_or_parent_when_no_previous.v1"
)
PREDICTION_TARGET = (
    "next_accepted_minus_secant_baseline_physical_coordinate_correction_m_and_rad"
)


def _secant_baseline(value: FiberFrameWarmStartInput) -> np.ndarray:
    """Match runtime _secant_proposal arithmetic on an already checked input."""
    current = np.asarray(value.parent_free_coordinates_m)
    if value.previous_free_coordinates_m is None:
        return current.copy()
    previous = np.asarray(value.previous_free_coordinates_m)
    denominator = value.parent_load_factor - value.previous_load_factor
    if denominator <= 0.0:
        raise FiberFrameWarmStartLearningError("secant: increasing history required")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        factor = (value.target_load_factor - value.parent_load_factor) / denominator
        result = current + factor * (current - previous)
    if not np.all(np.isfinite(result)):
        raise FiberFrameWarmStartLearningError("secant: nonfinite baseline")
    return result


@dataclass(frozen=True)
class FiberFrameSecantCorrectionWarmStartPolicy(FiberFrameConditionedWarmStartPolicy):
    """Immutable v3 ridge artifact with the existing checked v2 feature layout."""

    policy_id: str = field(default=POLICY_ID, init=False)
    policy_version: str = field(default="v3", init=False)
    baseline_contract: str = field(default=BASELINE_CONTRACT, init=False)

    def _payload(self) -> dict[str, Any]:
        return {
            **super()._payload(),
            "schema_version": POLICY_SCHEMA,
            "baseline_contract": self.baseline_contract,
            "prediction_target": PREDICTION_TARGET,
        }

    def propose(self, value: FiberFrameWarmStartInput) -> FiberFrameWarmStartProposal:
        if type(value) is not FiberFrameWarmStartInput:
            raise FiberFrameWarmStartLearningError(
                "runtime_input: exact input type required"
            )
        snapshot = _input_snapshot(replace(value, model_features=None))
        fallback = FiberFrameWarmStartProposal(
            snapshot.parent_free_coordinates_m, 1.0, True
        )
        try:
            model = _model_features(value)
            if (
                self.model_feature_profile != MODEL_FEATURE_PROFILE
                or self.policy_id != POLICY_ID
                or self.policy_version != "v3"
                or self.baseline_contract != BASELINE_CONTRACT
                or snapshot.free_global_dofs != self.free_global_dofs
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
                baseline = _secant_baseline(snapshot)
                normalized = (features - np.asarray(self.feature_mean)) / np.asarray(
                    self.feature_scale
                )
                correction = (
                    np.append(normalized, 1.0) @ np.asarray(self.weights)
                ) * np.asarray(self.target_scale)
                delta = np.zeros_like(baseline)
                np.divide(
                    correction,
                    np.asarray(snapshot.physical_coordinate_scale),
                    out=delta,
                    where=correction != 0.0,
                )
                prediction = baseline.copy()
                # Adding +0 to a -0 baseline changes its bytes. A zero correction
                # must preserve the exact existing secant (or genesis parent).
                np.add(baseline, delta, out=prediction, where=delta != 0.0)
                if not np.all(np.isfinite(prediction)):
                    return fallback
        except (
            FloatingPointError,
            OverflowError,
            FiberFrameWarmStartLearningError,
        ):
            return fallback
        return FiberFrameWarmStartProposal(
            tuple(float(x) for x in prediction), 0.0, False
        )


@dataclass(frozen=True)
class FiberFrameSecantCorrectionWarmStartTrainingResult:
    policy: FiberFrameSecantCorrectionWarmStartPolicy
    training_wall_ns: int
    _dataset_samples: tuple[FiberFrameWarmStartSample, ...] = field(repr=False)

    @property
    def dataset_report(self) -> dict[str, Any]:
        return validate_fiber_frame_warm_start_dataset(self._dataset_samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "fiber-frame-secant-correction-warm-start-training-result.v3",
            "policy": self.policy.to_dict(),
            "dataset_report": self.dataset_report,
            "training_wall_ns": self.training_wall_ns,
            "training_timing_profile": "local-perf-counter-ns-sidecar.v1",
            "training_timing_enters_policy_identity": False,
            "production_promotion_eligible": False,
        }


def train_fiber_frame_secant_correction_warm_start_policy(
    samples: Sequence[FiberFrameWarmStartSample],
    *,
    ridge: float = 1.0e-6,
    ood_margin: float = 0.1,
) -> FiberFrameSecantCorrectionWarmStartTrainingResult:
    """Fit correction arrays without replacing or relabelling source samples."""
    started = perf_counter_ns()
    rows = tuple(samples)
    validate_fiber_frame_warm_start_dataset(rows)
    for row in rows:
        if replace(row).sample_hash != row.sample_hash:
            raise FiberFrameWarmStartLearningError(
                "sample: stored identity differs from current source sample"
            )
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
                        - _secant_baseline(value)
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
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        raise FiberFrameWarmStartLearningError(
            "training: numerical overflow or fit failure"
        ) from exc
    policy = FiberFrameSecantCorrectionWarmStartPolicy(
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
    return FiberFrameSecantCorrectionWarmStartTrainingResult(
        policy, perf_counter_ns() - started, rows
    )


def decode_fiber_frame_secant_correction_warm_start_policy(
    value: dict[str, Any],
) -> FiberFrameSecantCorrectionWarmStartPolicy:
    """Decode an exact v3 artifact without fitting or altering its source hashes."""
    constructor = {
        item.name
        for item in fields(FiberFrameSecantCorrectionWarmStartPolicy)
        if item.init
    }
    metadata = {
        "schema_version",
        "policy_id",
        "policy_version",
        "model_feature_profile",
        "feature_contract",
        "physical_coordinate_conversion",
        "prediction_target",
        "baseline_contract",
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
        policy = FiberFrameSecantCorrectionWarmStartPolicy(
            **{name: value[name] for name in constructor}
        )
        if canonical_hash(value) != canonical_hash(policy.to_dict()):
            raise FiberFrameWarmStartLearningError(
                "policy: artifact identity or profile mismatch"
            )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FiberFrameWarmStartLearningError(
            "policy: invalid secant-correction artifact"
        ) from exc
    return policy
