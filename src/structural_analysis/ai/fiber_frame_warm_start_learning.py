"""Research-only displacement learning with explicit dataset isolation checks.

The predictor supplies a Newton initial displacement, never material state or a
final engineering result. Dataset checks validate supplied identities, not their
external provenance, licensing, or independent engineering verification.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import math
import re
from time import perf_counter_ns
from typing import Any, Literal

import numpy as np

from structural_analysis.benchmark.fiber_frame_runtime import (
    FiberFrameWarmStartInput,
    FiberFrameWarmStartProposal,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_SPLITS = ("train", "validation", "holdout")
WarmStartDatasetSplit = Literal["train", "validation", "holdout"]


class FiberFrameWarmStartLearningError(ValueError):
    """Invalid, leaking, or numerically unusable research learning input."""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise FiberFrameWarmStartLearningError(f"{name}: finite number required")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise FiberFrameWarmStartLearningError(
            f"{name}: finite number required"
        ) from exc
    if not math.isfinite(result):
        raise FiberFrameWarmStartLearningError(f"{name}: finite number required")
    return result


def _vector(value: Any, name: str) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list, np.ndarray)):
        raise FiberFrameWarmStartLearningError(
            f"{name}: one-dimensional vector required"
        )
    if isinstance(value, np.ndarray) and value.ndim != 1:
        raise FiberFrameWarmStartLearningError(
            f"{name}: one-dimensional vector required"
        )
    result = tuple(_finite(item, name) for item in value)
    if not result:
        raise FiberFrameWarmStartLearningError(f"{name}: empty vector")
    return result


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise FiberFrameWarmStartLearningError(f"{name}: sha256 identity required")
    return value


def _identity(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FiberFrameWarmStartLearningError(f"{name}: stable identity required")
    return value


def _validate_model_coordinate_scale(
    model_features: Any,
    free_global_dofs: Sequence[int],
    physical_coordinate_scale: Sequence[float],
) -> None:
    """Bind duplicated coordinate units to the declared model rotation length.

    The model feature artifact is decoded before this helper is called. This
    checks an internal metadata relation, not the authenticity of a problem hash.
    """
    values = dict(zip(model_features.feature_names, model_features.values, strict=True))
    rotation_length = values.get("rotation_coordinate_scale_m")
    if rotation_length is None:
        raise FiberFrameWarmStartLearningError(
            "model_features: rotation_coordinate_scale_m is required"
        )
    rotation_length = _finite(rotation_length, "rotation_coordinate_scale_m")
    if rotation_length <= 0:
        raise FiberFrameWarmStartLearningError(
            "model_features: rotation_coordinate_scale_m must be positive"
        )
    rotation_scale = _finite(
        1.0 / rotation_length, "rotation_coordinate_scale reciprocal"
    )
    scale = _vector(physical_coordinate_scale, "physical_coordinate_scale")
    try:
        dofs = tuple(free_global_dofs)
    except TypeError as error:
        raise FiberFrameWarmStartLearningError(
            "model_features: valid free DOF coordinates required"
        ) from error
    if len(dofs) != len(scale) or any(type(dof) is not int or dof < 0 for dof in dofs):
        raise FiberFrameWarmStartLearningError(
            "model_features: valid free DOF coordinates required"
        )
    expected = tuple(rotation_scale if dof % 3 == 2 else 1.0 for dof in dofs)
    if scale != expected:
        raise FiberFrameWarmStartLearningError(
            "model_features: coordinate scale does not match declared rotation length"
        )


def _input_snapshot(value: FiberFrameWarmStartInput) -> FiberFrameWarmStartInput:
    if type(value) is not FiberFrameWarmStartInput:
        raise FiberFrameWarmStartLearningError(
            "runtime_input: exact input type required"
        )
    _hash(value.problem_contract_hash, "problem_contract_hash")
    _hash(value.parent_checkpoint_state_hash, "parent_checkpoint_state_hash")
    parent = _vector(value.parent_free_coordinates_m, "parent_free_coordinates_m")
    scale = _vector(value.physical_coordinate_scale, "physical_coordinate_scale")
    try:
        dofs = tuple(value.free_global_dofs)
    except TypeError as exc:
        raise FiberFrameWarmStartLearningError(
            "free_global_dofs: sequence required"
        ) from exc
    if any(type(item) is not int or item < 0 for item in dofs):
        raise FiberFrameWarmStartLearningError(
            "free_global_dofs: nonnegative integers required"
        )
    if len(set(dofs)) != len(dofs) or tuple(sorted(dofs)) != dofs:
        raise FiberFrameWarmStartLearningError(
            "free_global_dofs: unique ordered DOFs required"
        )
    if (
        len(parent) != len(scale)
        or len(parent) != len(dofs)
        or any(x <= 0 for x in scale)
    ):
        raise FiberFrameWarmStartLearningError(
            "coordinate_profile: shape or scale invalid"
        )
    parent_load = _finite(value.parent_load_factor, "parent_load_factor")
    target_load = _finite(value.target_load_factor, "target_load_factor")
    if parent_load < 0 or target_load <= parent_load:
        raise FiberFrameWarmStartLearningError(
            "load_factors: increasing nonnegative path required"
        )
    previous_parts = (
        value.previous_checkpoint_state_hash,
        value.previous_load_factor,
        value.previous_free_coordinates_m,
    )
    if all(item is None for item in previous_parts):
        previous = None
        previous_load = None
    elif any(item is None for item in previous_parts):
        raise FiberFrameWarmStartLearningError(
            "previous_checkpoint: incomplete history"
        )
    else:
        _hash(value.previous_checkpoint_state_hash, "previous_checkpoint_state_hash")
        if value.previous_checkpoint_state_hash == value.parent_checkpoint_state_hash:
            raise FiberFrameWarmStartLearningError(
                "previous_checkpoint: duplicate parent identity"
            )
        previous = _vector(
            value.previous_free_coordinates_m, "previous_free_coordinates_m"
        )
        previous_load = _finite(value.previous_load_factor, "previous_load_factor")
        if len(previous) != len(parent) or not 0 <= previous_load < parent_load:
            raise FiberFrameWarmStartLearningError(
                "previous_checkpoint: shape or load invalid"
            )
    model_features = value.model_features
    if model_features is not None:
        from structural_analysis.ai.fiber_frame_warm_start_features import (
            FiberFrameWarmStartModelFeatures,
            decode_fiber_frame_warm_start_model_features,
        )

        if type(model_features) is not FiberFrameWarmStartModelFeatures:
            raise FiberFrameWarmStartLearningError(
                "model_features: exact immutable feature type required"
            )
        try:
            model_features = decode_fiber_frame_warm_start_model_features(
                model_features.to_dict()
            )
        except (ValueError, TypeError, KeyError) as error:
            raise FiberFrameWarmStartLearningError(
                "model_features: invalid feature contract"
            ) from error
        if model_features.problem_contract_hash != value.problem_contract_hash:
            raise FiberFrameWarmStartLearningError(
                "model_features: runtime problem binding mismatch"
            )
        _validate_model_coordinate_scale(model_features, dofs, scale)
    return FiberFrameWarmStartInput(
        value.problem_contract_hash,
        value.parent_checkpoint_state_hash,
        value.previous_checkpoint_state_hash,
        parent_load,
        previous_load,
        target_load,
        dofs,
        scale,
        parent,
        previous,
        model_features,
    )


def _input_payload(value: FiberFrameWarmStartInput) -> dict[str, Any]:
    payload = {
        name: list(item) if isinstance(item, tuple) else item
        for name, item in vars(value).items()
        if name != "model_features"
    }
    if value.model_features is not None:
        payload["model_features"] = value.model_features.to_dict()
    return payload


@dataclass(frozen=True)
class FiberFrameWarmStartSample:
    sample_id: str
    project_id: str
    geometry_family_id: str
    load_history_id: str
    model_identity_hash: str
    physical_problem_identity_hash: str
    split: WarmStartDatasetSplit
    runtime_input: FiberFrameWarmStartInput
    accepted_target_free_coordinates_m: tuple[float, ...]
    sample_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "sample_id",
            "project_id",
            "geometry_family_id",
            "load_history_id",
        ):
            _identity(getattr(self, name), name)
        for name in ("model_identity_hash", "physical_problem_identity_hash"):
            _hash(getattr(self, name), name)
        if self.split not in _SPLITS:
            raise FiberFrameWarmStartLearningError("split: unsupported split")
        snapshot = _input_snapshot(self.runtime_input)
        if self.physical_problem_identity_hash != snapshot.problem_contract_hash:
            raise FiberFrameWarmStartLearningError(
                "physical_problem_identity_hash: input mismatch"
            )
        target = _vector(self.accepted_target_free_coordinates_m, "accepted_target")
        if len(target) != len(snapshot.free_global_dofs):
            raise FiberFrameWarmStartLearningError(
                "accepted_target: coordinate shape mismatch"
            )
        object.__setattr__(self, "runtime_input", snapshot)
        object.__setattr__(self, "accepted_target_free_coordinates_m", target)
        object.__setattr__(self, "sample_hash", canonical_hash(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": "fiber-frame-warm-start-sample.v2"
            if self.runtime_input.model_features is not None
            else "fiber-frame-warm-start-sample.v1",
            **{
                name: getattr(self, name)
                for name in (
                    "sample_id",
                    "project_id",
                    "geometry_family_id",
                    "load_history_id",
                    "model_identity_hash",
                    "physical_problem_identity_hash",
                    "split",
                )
            },
            "runtime_input": _input_payload(self.runtime_input),
            "accepted_target_free_coordinates_m": list(
                self.accepted_target_free_coordinates_m
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "sample_hash": self.sample_hash}


def validate_fiber_frame_warm_start_dataset(
    samples: Sequence[FiberFrameWarmStartSample],
) -> dict[str, Any]:
    """Check declared split identities; no external provenance is certified."""
    rows = tuple(samples)
    if not rows or any(type(row) is not FiberFrameWarmStartSample for row in rows):
        raise FiberFrameWarmStartLearningError(
            "dataset: nonempty sample sequence required"
        )
    conditioned = {row.runtime_input.model_features is not None for row in rows}
    if len(conditioned) != 1:
        raise FiberFrameWarmStartLearningError(
            "dataset: model-conditioned and history-only samples cannot be mixed"
        )
    owners: dict[tuple[str, str], str] = {}
    sample_ids: set[str] = set()
    input_hashes: set[str] = set()
    counts = dict.fromkeys(_SPLITS, 0)
    for row in rows:
        if row.sample_id in sample_ids:
            raise FiberFrameWarmStartLearningError("dataset: duplicate sample_id")
        sample_ids.add(row.sample_id)
        input_hash = canonical_hash(_input_payload(row.runtime_input))
        if input_hash in input_hashes:
            raise FiberFrameWarmStartLearningError("dataset: duplicate runtime input")
        input_hashes.add(input_hash)
        counts[row.split] += 1
        identities = [
            (name, getattr(row, name))
            for name in (
                "project_id",
                "geometry_family_id",
                "load_history_id",
                "model_identity_hash",
                "physical_problem_identity_hash",
            )
        ]
        identities.append(
            ("checkpoint", row.runtime_input.parent_checkpoint_state_hash)
        )
        if row.runtime_input.previous_checkpoint_state_hash is not None:
            identities.append(
                ("checkpoint", row.runtime_input.previous_checkpoint_state_hash)
            )
        for key in identities:
            if key in owners and owners[key] != row.split:
                raise FiberFrameWarmStartLearningError(f"split_leakage: {key[0]}")
            owners[key] = row.split
    if any(count == 0 for count in counts.values()):
        raise FiberFrameWarmStartLearningError(
            "dataset: train, validation and holdout required"
        )
    payload = {
        "schema_version": "fiber-frame-warm-start-dataset.v2"
        if True in conditioned
        else "fiber-frame-warm-start-dataset.v1",
        "sample_hashes": sorted(row.sample_hash for row in rows),
        "split_counts": counts,
        "declared_identity_isolation_pass": True,
        "external_provenance_verified": False,
        "source_licensing_verified": False,
        "physical_target_replay_verified": False,
        "production_promotion_eligible": False,
        "validation_scope": "provided_identity_consistency_only",
    }
    if True in conditioned:
        from structural_analysis.ai.fiber_frame_warm_start_features import (
            MODEL_FEATURE_PROFILE,
        )

        payload["model_feature_profile"] = MODEL_FEATURE_PROFILE
    return {**payload, "dataset_hash": canonical_hash(payload)}


def _features(value: FiberFrameWarmStartInput) -> np.ndarray:
    parent = np.asarray(value.parent_free_coordinates_m, dtype=np.float64)
    previous = np.asarray(
        value.previous_free_coordinates_m or value.parent_free_coordinates_m
    )
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            result = np.concatenate(
                (
                    parent,
                    previous,
                    parent - previous,
                    np.asarray(
                        [
                            value.parent_load_factor,
                            value.previous_load_factor
                            if value.previous_load_factor is not None
                            else value.parent_load_factor,
                            value.target_load_factor,
                            float(value.previous_free_coordinates_m is not None),
                        ]
                    ),
                )
            )
    except FloatingPointError as exc:
        raise FiberFrameWarmStartLearningError("features: arithmetic overflow") from exc
    if not np.all(np.isfinite(result)):
        raise FiberFrameWarmStartLearningError("features: nonfinite result")
    return result


@dataclass(frozen=True)
class FiberFrameLearnedWarmStartPolicy:
    """Immutable ridge model; uncertainty is an uncalibrated range indicator."""

    free_global_dofs: tuple[int, ...]
    physical_coordinate_scale: tuple[float, ...]
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    feature_min: tuple[float, ...]
    feature_max: tuple[float, ...]
    target_scale: tuple[float, ...]
    weights: tuple[tuple[float, ...], ...]
    training_sample_hashes: tuple[str, ...]
    ridge: float
    ood_margin: float
    policy_id: str = field(default="research-ridge-displacement-warm-start", init=False)
    policy_version: str = field(default="v1", init=False)
    artifact_hash: str = field(init=False)

    def __post_init__(self) -> None:
        # Copy every supplied sequence so callers cannot mutate the artifact.
        dofs = tuple(self.free_global_dofs)
        if (
            not dofs
            or any(type(item) is not int or item < 0 for item in dofs)
            or tuple(sorted(set(dofs))) != dofs
        ):
            raise FiberFrameWarmStartLearningError("policy: invalid DOF profile")
        object.__setattr__(self, "free_global_dofs", dofs)
        for name in (
            "physical_coordinate_scale",
            "feature_mean",
            "feature_scale",
            "feature_min",
            "feature_max",
            "target_scale",
        ):
            object.__setattr__(self, name, _vector(getattr(self, name), name))
        matrix = tuple(_vector(row, "weights") for row in self.weights)
        object.__setattr__(self, "weights", matrix)
        hashes = tuple(
            _hash(item, "training_sample_hash") for item in self.training_sample_hashes
        )
        if not hashes or tuple(sorted(set(hashes))) != hashes:
            raise FiberFrameWarmStartLearningError(
                "policy: unique ordered training hashes required"
            )
        object.__setattr__(self, "training_sample_hashes", hashes)
        size = 3 * len(dofs) + 4
        if any(
            len(getattr(self, name)) != size
            for name in ("feature_mean", "feature_scale", "feature_min", "feature_max")
        ):
            raise FiberFrameWarmStartLearningError("policy: feature shape mismatch")
        if (
            len(self.physical_coordinate_scale) != len(dofs)
            or len(self.target_scale) != len(dofs)
            or len(matrix) != size + 1
            or any(len(row) != len(dofs) for row in matrix)
        ):
            raise FiberFrameWarmStartLearningError("policy: output shape mismatch")
        if any(
            item <= 0
            for name in ("physical_coordinate_scale", "feature_scale", "target_scale")
            for item in getattr(self, name)
        ):
            raise FiberFrameWarmStartLearningError("policy: positive scales required")
        if any(
            low > high
            for low, high in zip(self.feature_min, self.feature_max, strict=True)
        ):
            raise FiberFrameWarmStartLearningError("policy: inverted feature bounds")
        for name in ("ridge", "ood_margin"):
            value = _finite(getattr(self, name), name)
            if value < 0 or (name == "ridge" and value == 0):
                raise FiberFrameWarmStartLearningError(f"{name}: invalid range")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "artifact_hash", canonical_hash(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": "fiber-frame-learned-warm-start-policy.v1",
            **{
                name: getattr(self, name)
                for name in (
                    "policy_id",
                    "policy_version",
                    "free_global_dofs",
                    "physical_coordinate_scale",
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
            "feature_contract": "parent_previous_displacement_and_load_factors_only.v1",
            "prediction_target": "next_accepted_displacement_increment",
            "preprocessing_fit_split": "train",
            "uncertainty_kind": "uncalibrated_feature_range_indicator_not_probability",
            "production_promotion_eligible": False,
            "physical_result_authority": False,
            "external_verification_claimed": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "artifact_hash": self.artifact_hash}

    def propose(self, value: FiberFrameWarmStartInput) -> FiberFrameWarmStartProposal:
        snapshot = _input_snapshot(value)
        fallback = FiberFrameWarmStartProposal(
            snapshot.parent_free_coordinates_m, 1.0, True
        )
        if (
            snapshot.free_global_dofs != self.free_global_dofs
            or snapshot.physical_coordinate_scale != self.physical_coordinate_scale
        ):
            return fallback
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                features = _features(snapshot)
                low, high = np.asarray(self.feature_min), np.asarray(self.feature_max)
                tolerance = np.maximum((high - low) * self.ood_margin, 1.0e-12)
                outside = (features < low - tolerance) | (features > high + tolerance)
                if np.any(outside):
                    return fallback
                normalized = (features - np.asarray(self.feature_mean)) / np.asarray(
                    self.feature_scale
                )
                increment = np.append(normalized, 1.0) @ np.asarray(self.weights)
                prediction = np.asarray(
                    snapshot.parent_free_coordinates_m
                ) + increment * np.asarray(self.target_scale)
                if not np.all(np.isfinite(prediction)):
                    return fallback
        except (FloatingPointError, FiberFrameWarmStartLearningError):
            return fallback
        # Zero only means no range violation; it is not confidence calibration.
        return FiberFrameWarmStartProposal(
            tuple(float(x) for x in prediction), 0.0, False
        )


@dataclass(frozen=True)
class FiberFrameWarmStartTrainingResult:
    policy: FiberFrameLearnedWarmStartPolicy
    training_wall_ns: int
    _dataset_samples: tuple[FiberFrameWarmStartSample, ...] = field(repr=False)

    @property
    def dataset_report(self) -> dict[str, Any]:
        return validate_fiber_frame_warm_start_dataset(self._dataset_samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "fiber-frame-warm-start-training-result.v1",
            "policy": self.policy.to_dict(),
            "dataset_report": self.dataset_report,
            "training_wall_ns": self.training_wall_ns,
            "training_timing_profile": "local-perf-counter-ns-sidecar.v1",
            "training_timing_enters_policy_identity": False,
            "production_promotion_eligible": False,
        }


def train_fiber_frame_warm_start_policy(
    samples: Sequence[FiberFrameWarmStartSample],
    *,
    ridge: float = 1.0e-6,
    ood_margin: float = 0.1,
) -> FiberFrameWarmStartTrainingResult:
    """Fit train rows only; validation/holdout targets never enter the model."""
    started = perf_counter_ns()
    rows = tuple(samples)
    validate_fiber_frame_warm_start_dataset(rows)
    if any(row.runtime_input.model_features is not None for row in rows):
        raise FiberFrameWarmStartLearningError(
            "training: model-conditioned samples require the conditioned policy trainer"
        )
    ridge = _finite(ridge, "ridge")
    ood_margin = _finite(ood_margin, "ood_margin")
    if ridge <= 0 or ood_margin < 0:
        raise FiberFrameWarmStartLearningError("training: ridge and OOD margin invalid")
    training = sorted(
        (row for row in rows if row.split == "train"), key=lambda row: row.sample_hash
    )
    if len(training) < 2:
        raise FiberFrameWarmStartLearningError(
            "training: at least two train rows required"
        )
    profile = (
        training[0].runtime_input.free_global_dofs,
        training[0].runtime_input.physical_coordinate_scale,
    )
    if any(
        (
            row.runtime_input.free_global_dofs,
            row.runtime_input.physical_coordinate_scale,
        )
        != profile
        for row in training
    ):
        raise FiberFrameWarmStartLearningError(
            "training: one coordinate profile required"
        )
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            features = np.vstack([_features(row.runtime_input) for row in training])
            targets = np.vstack(
                [
                    np.asarray(row.accepted_target_free_coordinates_m)
                    - np.asarray(row.runtime_input.parent_free_coordinates_m)
                    for row in training
                ]
            )
            mean = features.mean(axis=0)
            scale = np.maximum(np.max(np.abs(features - mean), axis=0), 1.0e-12)
            normalized = (features - mean) / scale
            target_scale = np.maximum(np.max(np.abs(targets), axis=0), 1.0e-12)
            design = np.column_stack((normalized, np.ones(len(training))))
            regularizer = np.sqrt(ridge) * np.eye(design.shape[1])
            regularizer[-1, -1] = 0.0
            augmented_x = np.vstack((design, regularizer))
            augmented_y = np.vstack(
                (targets / target_scale, np.zeros((design.shape[1], targets.shape[1])))
            )
            weights, _, _, _ = np.linalg.lstsq(augmented_x, augmented_y, rcond=None)
            values = (mean, scale, target_scale, weights)
            if any(not np.all(np.isfinite(value)) for value in values):
                raise FiberFrameWarmStartLearningError(
                    "training: nonfinite fitted parameters"
                )
    except (FloatingPointError, np.linalg.LinAlgError) as exc:
        raise FiberFrameWarmStartLearningError(
            "training: numerical overflow or fit failure"
        ) from exc
    policy = FiberFrameLearnedWarmStartPolicy(
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
    return FiberFrameWarmStartTrainingResult(policy, perf_counter_ns() - started, rows)
