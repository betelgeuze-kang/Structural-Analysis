"""Research candidate ranking from pre-solve section geometry and RC bar features.

Public solves produce the labels. Caller-declared split identifiers and source
revisions are not independent-project or external provenance attestations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
import json
import math
import re
from time import perf_counter_ns
from types import MappingProxyType
from typing import Any

import numpy as np

from structural_analysis.ai.fiber_frame_physical_identity import (
    PHYSICAL_MODEL_IDENTITY_PROFILE,
    fiber_frame_physical_model_identity,
    fiber_frame_physical_model_payload,
)
from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
    _ID as _CASE_ID,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel


_SECTION_FEATURE_FIELDS = (
    "width_m",
    "depth_m",
    "cover_m",
    "top_bar_count",
    "bottom_bar_count",
    "bar_area_m2",
)
_MAX_FEATURE_MEMBERS = 15
CANDIDATE_FEATURE_PROFILE = "canonical-member-section-features.padded15.v2"
CANDIDATE_POLICY_SCHEMA = "fiber-frame-candidate-ridge-policy.v2"
CANDIDATE_LEARNING_SCHEMA = "fiber-frame-candidate-learning.v2"
CANDIDATE_TERMINAL_TARGET_PROFILE = "terminal_response.v1"
CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE = "terminal_and_committed_material_history.v1"
CANDIDATE_HISTORY_POLICY_SCHEMA = "fiber-frame-candidate-ridge-policy.v3"
CANDIDATE_HISTORY_LEARNING_SCHEMA = "fiber-frame-candidate-learning.v3"
CANDIDATE_TERMINAL_TARGETS = (
    "terminal_maximum_translation_m",
    "terminal_maximum_absolute_fiber_strain",
)
CANDIDATE_HISTORY_TARGETS = (
    "history_maximum_translation_m",
    "history_maximum_absolute_fiber_strain",
    "history_maximum_steel_accumulated_plastic_strain",
    "history_maximum_concrete_tensile_damage",
    "history_maximum_concrete_compressive_damage",
)
_HISTORY_LABEL_SCHEMA = "fiber-frame-candidate-history-label-source.v1"
_HISTORY_LABEL_SCOPE = "case_identity_preflight_features_full_public_response_history_and_constitutive_label_collection_including_source_replays"
_HISTORY_LABEL_CLAIMS = {
    "history_labels_are_positive_committed_epoch_maxima": True,
    "material_memory_is_current_yield_event": False,
    "caller_limits_used_to_clip_targets": False,
    "frozen_label_validation_is_independent_source_replay": False,
}
FEATURE_NAMES = (
    "member_count",
    "total_length_m",
    "gross_concrete_volume_m3",
    "longitudinal_rebar_volume_m3",
    "mean_width_m",
    "mean_depth_m",
    "mean_cover_m",
    "sum_rectangular_inertia_m4",
    "sum_top_bar_count",
    "sum_bottom_bar_count",
    "sum_bar_area_m2",
) + tuple(
    f"member_{index}_{name}"
    for index in range(_MAX_FEATURE_MEMBERS)
    for name in _SECTION_FEATURE_FIELDS
)


class FiberFrameCandidateLearningError(ValueError):
    """Invalid or leaking candidate-learning experiment."""


def _target_names(profile: str) -> tuple[str, ...]:
    if type(profile) is not str or profile not in (
        CANDIDATE_TERMINAL_TARGET_PROFILE,
        CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE,
    ):
        raise FiberFrameCandidateLearningError("unsupported candidate target_profile")
    return CANDIDATE_TERMINAL_TARGETS + (
        CANDIDATE_HISTORY_TARGETS
        if profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE
        else ()
    )


def _history_targets(values: Sequence[Any]) -> tuple[float, ...]:
    if len(values) != 7:
        raise FiberFrameCandidateLearningError("seven history targets required")
    targets = tuple(_number(value, "history target") for value in values)
    if (
        any(value < 0 for value in targets)
        or any(value > 1 for value in targets[5:])
        or targets[2] < targets[0]
        or targets[3] < targets[1]
    ):
        raise FiberFrameCandidateLearningError("history target physical range invalid")
    return targets


def _source_revision(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64}", value
    ):
        raise FiberFrameCandidateLearningError("full source revision required")
    return f"sha256:{value}" if len(value) == 64 else value


def _number(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise FiberFrameCandidateLearningError(f"{name}: finite number required")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise FiberFrameCandidateLearningError(
            f"{name}: finite number required"
        ) from exc
    if not math.isfinite(result):
        raise FiberFrameCandidateLearningError(f"{name}: finite number required")
    return result


def candidate_model_identity(model: CanonicalModel) -> str:
    """Bind supported physics independently of authored entity labels or order."""
    return fiber_frame_physical_model_identity(model)


def candidate_preanalysis_features(
    model: CanonicalModel,
    config: public_api.PublicRCFiberFrameConfig,
) -> tuple[tuple[float, ...], str]:
    """Only section geometry and authored bars vary inside a fixed solve context."""
    if (
        type(model) is not CanonicalModel
        or type(config) is not public_api.PublicRCFiberFrameConfig
    ):
        raise FiberFrameCandidateLearningError("exact model and config types required")
    context = fiber_frame_physical_model_payload(model)
    assigned = [member["section"] for member in context["members"]]
    n = len(assigned)
    if not 1 <= n <= _MAX_FEATURE_MEMBERS:
        raise FiberFrameCandidateLearningError("feature member count exceeds profile")
    coordinates = context["node_coordinates_m"]
    lengths = [
        math.dist(coordinates[row["nodes"][0]], coordinates[row["nodes"][1]])
        for row in context["members"]
    ]
    try:
        values = (
            float(n),
            math.fsum(lengths),
            math.fsum(
                row["width_m"] * row["depth_m"] * length
                for row, length in zip(assigned, lengths, strict=True)
            ),
            math.fsum(
                (row["top_bar_count"] + row["bottom_bar_count"])
                * row["bar_area_m2"]
                * length
                for row, length in zip(assigned, lengths, strict=True)
            ),
            *(
                math.fsum(float(row[name]) for row in assigned) / n
                for name in ("width_m", "depth_m", "cover_m")
            ),
            math.fsum(row["width_m"] * row["depth_m"] ** 3 / 12.0 for row in assigned),
            math.fsum(row["top_bar_count"] for row in assigned),
            math.fsum(row["bottom_bar_count"] for row in assigned),
            math.fsum(row["bar_area_m2"] for row in assigned),
            *(row[name] for row in assigned for name in _SECTION_FEATURE_FIELDS),
            *((0.0,) * ((_MAX_FEATURE_MEMBERS - n) * len(_SECTION_FEATURE_FIELDS))),
        )
        features = tuple(_number(value, "feature") for value in values)
    except (OverflowError, ArithmeticError) as exc:
        raise FiberFrameCandidateLearningError("geometry features overflow") from exc
    for section in assigned:
        for name in _SECTION_FEATURE_FIELDS:
            section.pop(name)
    return features, canonical_hash(
        {
            "feature_profile": CANDIDATE_FEATURE_PROFILE,
            "fixed_analysis_context": context,
            "configuration": asdict(config),
        }
    )


@dataclass(frozen=True)
class FiberFrameCandidatePrediction:
    maximum_translation_m: float | None
    maximum_absolute_fiber_strain: float | None
    ood: bool
    reason: str
    target_profile: str = CANDIDATE_TERMINAL_TARGET_PROFILE
    history_prediction: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        _target_names(self.target_profile)
        if self.target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE:
            if (
                type(self.ood) is not bool
                or type(self.reason) is not str
                or not self.reason
            ):
                raise FiberFrameCandidateLearningError(
                    "history prediction status invalid"
                )
            if self.ood:
                if (
                    self.history_prediction is not None
                    or self.maximum_translation_m is not None
                    or self.maximum_absolute_fiber_strain is not None
                ):
                    raise FiberFrameCandidateLearningError(
                        "OOD history must be unavailable"
                    )
            else:
                if not isinstance(self.history_prediction, Mapping) or set(
                    self.history_prediction
                ) != set(CANDIDATE_HISTORY_TARGETS):
                    raise FiberFrameCandidateLearningError(
                        "exact history predictions required"
                    )
                targets = _history_targets(
                    (
                        self.maximum_translation_m,
                        self.maximum_absolute_fiber_strain,
                        *(
                            self.history_prediction[key]
                            for key in CANDIDATE_HISTORY_TARGETS
                        ),
                    )
                )
                object.__setattr__(
                    self,
                    "history_prediction",
                    MappingProxyType(
                        dict(zip(CANDIDATE_HISTORY_TARGETS, targets[2:], strict=True))
                    ),
                )
        elif self.history_prediction is not None:
            raise FiberFrameCandidateLearningError(
                "terminal profile has no history predictions"
            )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "maximum_translation_m": self.maximum_translation_m,
            "maximum_absolute_fiber_strain": self.maximum_absolute_fiber_strain,
            "ood": self.ood,
            "reason": self.reason,
            "uncertainty_kind": "uncalibrated_feature_range_indicator_not_probability",
            "physical_result_authority": False,
        }
        if self.target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE:
            result.update(
                target_profile=self.target_profile,
                history_prediction=None
                if self.history_prediction is None
                else dict(self.history_prediction),
            )
        return result


@dataclass(frozen=True)
class FiberFrameCandidatePolicy:
    context_hash: str
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    feature_min: tuple[float, ...]
    feature_max: tuple[float, ...]
    target_scale: tuple[float, ...]
    weights: tuple[tuple[float, ...], ...]
    training_sample_hashes: tuple[str, ...]
    ridge: float
    ood_margin: float
    target_profile: str = CANDIDATE_TERMINAL_TARGET_PROFILE
    artifact_hash: str = field(init=False)

    def __post_init__(self) -> None:
        target_count = len(_target_names(self.target_profile))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.context_hash):
            raise FiberFrameCandidateLearningError("context_hash is invalid")
        for name in (
            "feature_mean",
            "feature_scale",
            "feature_min",
            "feature_max",
            "target_scale",
        ):
            object.__setattr__(
                self, name, tuple(_number(x, name) for x in getattr(self, name))
            )
        weights = tuple(
            tuple(_number(x, "weight") for x in row) for row in self.weights
        )
        object.__setattr__(self, "weights", weights)
        hashes = tuple(self.training_sample_hashes)
        if (
            not hashes
            or any(
                not isinstance(h, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", h)
                for h in hashes
            )
            or hashes != tuple(sorted(set(hashes)))
        ):
            raise FiberFrameCandidateLearningError("training_sample_hashes are invalid")
        object.__setattr__(self, "training_sample_hashes", hashes)
        n = len(FEATURE_NAMES)
        if (
            any(
                len(getattr(self, key)) != n
                for key in (
                    "feature_mean",
                    "feature_scale",
                    "feature_min",
                    "feature_max",
                )
            )
            or len(self.target_scale) != target_count
            or len(weights) != n + 1
            or any(len(row) != target_count for row in weights)
        ):
            raise FiberFrameCandidateLearningError("policy dimensions invalid")
        if any(value <= 0 for value in (*self.feature_scale, *self.target_scale)):
            raise FiberFrameCandidateLearningError("positive policy scales required")
        if any(
            low > high
            for low, high in zip(self.feature_min, self.feature_max, strict=True)
        ):
            raise FiberFrameCandidateLearningError("policy range bounds invalid")
        ridge, margin = (
            _number(self.ridge, "ridge"),
            _number(self.ood_margin, "ood_margin"),
        )
        if ridge <= 0 or margin < 0:
            raise FiberFrameCandidateLearningError("ridge or OOD margin invalid")
        object.__setattr__(self, "ridge", ridge)
        object.__setattr__(self, "ood_margin", margin)
        object.__setattr__(self, "artifact_hash", canonical_hash(self._payload()))

    def _payload(self) -> dict[str, Any]:
        result = {
            "schema_version": CANDIDATE_HISTORY_POLICY_SCHEMA
            if self.target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE
            else CANDIDATE_POLICY_SCHEMA,
            "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
            "feature_profile": CANDIDATE_FEATURE_PROFILE,
            **{
                name: getattr(self, name)
                for name in (
                    "context_hash",
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
            "features": list(FEATURE_NAMES),
            "targets": list(_target_names(self.target_profile)),
            "preprocessing_fit_split": "train",
            "study_scope": "local_synthetic_section_family_research",
            "independent_project_generalization_verified": False,
            "production_promotion_eligible": False,
            "physical_result_authority": False,
        }
        if self.target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE:
            result["target_profile"] = self.target_profile
        return result

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "artifact_hash": self.artifact_hash}

    def predict(
        self, model: CanonicalModel, config: public_api.PublicRCFiberFrameConfig
    ) -> FiberFrameCandidatePrediction:
        def fallback(reason: str) -> FiberFrameCandidatePrediction:
            return FiberFrameCandidatePrediction(
                None, None, True, reason, self.target_profile
            )

        try:
            features, context = candidate_preanalysis_features(model, config)
            if context != self.context_hash:
                return fallback("analysis_context_out_of_distribution")
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                x = np.asarray(features)
                low, high = np.asarray(self.feature_min), np.asarray(self.feature_max)
                tolerance = np.maximum((high - low) * self.ood_margin, 1e-12)
                if np.any((x < low - tolerance) | (x > high + tolerance)):
                    return fallback("feature_range_out_of_distribution")
                normalized = (x - self.feature_mean) / self.feature_scale
                prediction = (
                    np.append(normalized, 1.0) @ np.asarray(self.weights)
                ) * self.target_scale
                if not np.all(np.isfinite(prediction)) or np.any(prediction < 0):
                    return fallback("prediction_nonfinite_or_negative")
                if self.target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE:
                    try:
                        _history_targets(prediction)
                    except FiberFrameCandidateLearningError:
                        return fallback("prediction_history_range_inconsistent")
        except Exception:
            return fallback("feature_or_inference_failed")
        return FiberFrameCandidatePrediction(
            float(prediction[0]),
            float(prediction[1]),
            False,
            "in_train_feature_range_uncalibrated",
            self.target_profile,
            dict(
                zip(CANDIDATE_HISTORY_TARGETS, map(float, prediction[2:]), strict=True)
            )
            if self.target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE
            else None,
        )


@dataclass(frozen=True)
class FiberFrameCandidateTrainingResult:
    status: str
    policy: FiberFrameCandidatePolicy | None
    _report_json: str = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._report_json)


def _hash_field(value: Any) -> None:
    if type(value) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise FiberFrameCandidateLearningError("history label source hash invalid")


def _validate_history_label_source(sample: dict[str, Any]) -> None:
    """Check copied label/binding consistency, not independently replay physics."""
    source = sample.get("history_label_source")
    if (
        type(source) is not dict
        or set(source)
        != {
            "schema_version",
            "bindings",
            "constitutive_history_report_hash",
            "accepted_epoch_count",
            "terminal_checkpoint_state_hash",
            "epochs",
            "source_hash",
        }
        or source["schema_version"] != _HISTORY_LABEL_SCHEMA
    ):
        raise FiberFrameCandidateLearningError("history label source schema invalid")
    if source["source_hash"] != canonical_hash(
        {key: value for key, value in source.items() if key != "source_hash"}
    ):
        raise FiberFrameCandidateLearningError("history label source seal mismatch")
    bindings = source["bindings"]
    if type(bindings) is not dict or set(bindings) != {
        "source_result_hash",
        "canonical_model_checksum",
        "input_checksum",
        "problem_contract_hash",
        "checkpoint_chain_hash",
        "checkpoint_artifact_hash",
        "checkpoint_artifact_byte_length",
        "response_history_report_hash",
        "engineering_history_hash",
    }:
        raise FiberFrameCandidateLearningError("history label bindings invalid")
    for key, value in bindings.items():
        if key == "checkpoint_artifact_byte_length":
            if type(value) is not int or value <= 0:
                raise FiberFrameCandidateLearningError(
                    "history checkpoint length invalid"
                )
        else:
            _hash_field(value)
    for key in ("constitutive_history_report_hash", "terminal_checkpoint_state_hash"):
        _hash_field(source[key])
    for key, sample_key in (
        ("source_result_hash", "public_result_hash"),
        ("canonical_model_checksum", "canonical_model_checksum"),
        ("input_checksum", "input_checksum"),
        ("checkpoint_chain_hash", "checkpoint_chain_hash"),
    ):
        if bindings[key] != sample[sample_key]:
            raise FiberFrameCandidateLearningError(
                "history label sample/source mismatch"
            )
    count, epochs = source["accepted_epoch_count"], source["epochs"]
    if (
        type(count) is not int
        or not 1 <= count <= 64
        or type(epochs) is not list
        or len(epochs) != count
    ):
        raise FiberFrameCandidateLearningError("history label epoch coverage invalid")
    previous = None
    for index, epoch in enumerate(epochs, start=1):
        if type(epoch) is not dict or set(epoch) != {
            "epoch",
            "step_index",
            "load_factor",
            "checkpoint_state_hash",
            "parent_checkpoint_state_hash",
            "engineering_recovery_hash",
            "targets",
        }:
            raise FiberFrameCandidateLearningError("history label epoch fields invalid")
        if (
            type(epoch["epoch"]) is not int
            or epoch["epoch"] != index
            or type(epoch["step_index"]) is not int
            or epoch["step_index"] != index
            or _number(epoch["load_factor"], "load factor") != index / count
        ):
            raise FiberFrameCandidateLearningError(
                "history label epoch schedule invalid"
            )
        for key in (
            "checkpoint_state_hash",
            "parent_checkpoint_state_hash",
            "engineering_recovery_hash",
        ):
            _hash_field(epoch[key])
        if previous is not None and epoch["parent_checkpoint_state_hash"] != previous:
            raise FiberFrameCandidateLearningError(
                "history label parent chain mismatch"
            )
        previous = epoch["checkpoint_state_hash"]
        if type(epoch["targets"]) is not list:
            raise FiberFrameCandidateLearningError(
                "history epoch target vector invalid"
            )
        _history_targets((0.0, 0.0, *epoch["targets"]))
    targets = _history_targets(sample["targets"])
    expected = [max(epoch["targets"][i] for epoch in epochs) for i in range(5)]
    if (
        previous != source["terminal_checkpoint_state_hash"]
        or canonical_hash(list(targets[2:])) != canonical_hash(expected)
        or canonical_hash(list(targets[:2]))
        != canonical_hash(epochs[-1]["targets"][:2])
    ):
        raise FiberFrameCandidateLearningError(
            "history label target aggregate mismatch"
        )


def _collect_history_labels(result, config) -> dict[str, Any]:
    """Recover original accepted sources; never solve shortened load prefixes."""
    from structural_analysis.benchmark import (
        fiber_frame_constitutive_history as constitutive,
    )
    from structural_analysis.benchmark.fiber_frame_design import (
        MATERIAL_HISTORY_METRICS,
        _check_material_history_bindings,
    )

    if type(result) is not public_api.PublicRCFiberFrameResult:
        raise FiberFrameCandidateLearningError(
            "exact public history label result required"
        )
    history = public_api.recover_public_rc_fiber_frame_response_history(result)
    if type(history) is not public_api.PublicRCFiberFrameResponseHistory:
        raise FiberFrameCandidateLearningError("exact public response history required")
    response = history.to_dict()
    if (
        history.status != "ready"
        or history.contract_pass is not True
        or response.get("status") != "ready"
        or response.get("contract_pass") is not True
        or response.get("source_result_hash") != result.result_hash
        or response.get("canonical_model_checksum") != result.canonical_model_checksum
        or response.get("report_hash") != history.report_hash
        or response["report_hash"]
        != canonical_hash(
            {key: value for key, value in response.items() if key != "report_hash"}
        )
    ):
        raise FiberFrameCandidateLearningError(
            "history label response binding mismatch"
        )
    engineering = response["history"]
    if engineering["history_hash"] != response["history_hash"] or engineering[
        "history_hash"
    ] != canonical_hash(
        {key: value for key, value in engineering.items() if key != "history_hash"}
    ):
        raise FiberFrameCandidateLearningError(
            "history label engineering seal mismatch"
        )
    observed = constitutive.inspect_public_rc_fiber_frame_constitutive_history(result)
    if type(observed) is not constitutive.FiberFrameConstitutiveHistory:
        raise FiberFrameCandidateLearningError(
            "exact constitutive label source required"
        )
    material = observed.to_dict()
    _check_material_history_bindings(material, result, response, config)
    epochs = []
    if len(engineering["steps"]) != config.load_steps:
        raise FiberFrameCandidateLearningError("history label step coverage mismatch")
    for step, state in zip(engineering["steps"], material["states"][1:], strict=True):
        nodes, fibers = step["node_displacements"], step["fiber_results"]
        if not nodes or not fibers:
            raise FiberFrameCandidateLearningError(
                "nonempty history label response rows required"
            )
        values = [
            max(
                math.hypot(
                    *(_number(row[key], key) for key in ("UX_m", "UY_m", "UZ_m"))
                )
                for row in nodes
            ),
            max(abs(_number(row["strain"], "strain")) for row in fibers),
            *(
                _number(state["materials"][kind]["fields"][native]["maximum"], metric)
                for metric, (_, kind, native) in MATERIAL_HISTORY_METRICS.items()
            ),
        ]
        if any(
            canonical_hash(step["envelope"][name]) != canonical_hash(value)
            for name, value in zip(
                ("maximum_translation_m", "maximum_absolute_fiber_strain"),
                values[:2],
                strict=True,
            )
        ):
            raise FiberFrameCandidateLearningError(
                "history label step envelope mismatch"
            )
        _history_targets((0.0, 0.0, *values))
        epochs.append(
            {
                "epoch": step["epoch"],
                "step_index": step["step_index"],
                "load_factor": step["target_load_factor"],
                "checkpoint_state_hash": step["bindings"]["checkpoint_state_hash"],
                "parent_checkpoint_state_hash": step["bindings"][
                    "parent_checkpoint_state_hash"
                ],
                "engineering_recovery_hash": step["recovery_hash"],
                "targets": values,
            }
        )
    for i, name in enumerate(
        ("maximum_translation_m", "maximum_absolute_fiber_strain")
    ):
        if canonical_hash(engineering["envelope"][name]) != canonical_hash(
            max(row["targets"][i] for row in epochs)
        ):
            raise FiberFrameCandidateLearningError(
                "history label complete envelope mismatch"
            )
    source = {
        "schema_version": _HISTORY_LABEL_SCHEMA,
        "bindings": material["bindings"],
        "constitutive_history_report_hash": material["report_hash"],
        "accepted_epoch_count": config.load_steps,
        "terminal_checkpoint_state_hash": result.checkpoint["terminal_state_hash"],
        "epochs": epochs,
    }
    return {**source, "source_hash": canonical_hash(source)}


def _validated_training_report(
    training: FiberFrameCandidateTrainingResult,
) -> tuple[dict[str, Any], set[str]]:
    """Verify frozen sample membership before using its physical leakage guard.

    Hashes bind these local artifacts to each other; they do not attest external
    provenance. Old profiles require an explicitly produced new training artifact.
    """
    try:
        policy = training.policy
        if (
            type(training) is not FiberFrameCandidateTrainingResult
            or training.status != "ready"
            or type(policy) is not FiberFrameCandidatePolicy
        ):
            raise ValueError("ready typed training artifact required")
        report = training.to_dict()
        history_target = (
            policy.target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE
        )
        expected_schema = (
            CANDIDATE_HISTORY_LEARNING_SCHEMA
            if history_target
            else CANDIDATE_LEARNING_SCHEMA
        )
        if (
            type(report) is not dict
            or report.get("schema_version") != expected_schema
            or report.get("identity_profile") != PHYSICAL_MODEL_IDENTITY_PROFILE
            or report.get("feature_profile") != CANDIDATE_FEATURE_PROFILE
            or report.get("status") != "ready"
        ):
            raise ValueError("unsupported training report schema or profile")
        if history_target:
            if report.get("target_profile") != policy.target_profile or report.get(
                "targets"
            ) != list(_target_names(policy.target_profile)):
                raise ValueError("history training target profile mismatch")
            if type(report.get("claims")) is not dict or any(
                report["claims"].get(key) is not expected
                for key, expected in _HISTORY_LABEL_CLAIMS.items()
            ):
                raise ValueError("history training claims mismatch")
        elif "target_profile" in report or "targets" in report:
            raise ValueError("terminal training report cannot declare history profile")
        body = {key: value for key, value in report.items() if key != "report_hash"}
        if report.get("report_hash") != canonical_hash(body):
            raise ValueError("training report hash mismatch")
        if policy.artifact_hash != canonical_hash(policy._payload()) or canonical_hash(
            report.get("policy")
        ) != canonical_hash(policy.to_dict()):
            raise ValueError("training report and policy identity mismatch")
        samples = report.get("samples")
        if type(samples) is not list or not samples:
            raise ValueError("training samples required")
        train_hashes, train_identities, sample_hashes = [], set(), set()
        case_ids, splits = set(), set()
        physical_ids = set()
        group_owners = {}
        for sample in samples:
            if (
                type(sample) is not dict
                or sample.get("identity_profile") != PHYSICAL_MODEL_IDENTITY_PROFILE
                or sample.get("feature_profile") != CANDIDATE_FEATURE_PROFILE
                or sample.get("split") not in ("train", "validation", "holdout")
                or not isinstance(sample.get("case_id"), str)
                or not isinstance(sample.get("model_identity_hash"), str)
                or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}", sample["model_identity_hash"]
                )
            ):
                raise ValueError("invalid training sample profile or identity")
            sample_body = {
                key: value for key, value in sample.items() if key != "sample_hash"
            }
            sample_hash = canonical_hash(sample_body)
            if sample.get("sample_hash") != sample_hash:
                raise ValueError("training sample hash mismatch")
            if history_target:
                if sample.get("target_profile") != policy.target_profile:
                    raise ValueError("history sample target profile mismatch")
                for key in (
                    "case_id",
                    "project_id",
                    "geometry_family_id",
                    "load_history_id",
                ):
                    value = sample.get(key)
                    if not isinstance(value, str) or not _CASE_ID.fullmatch(value):
                        raise ValueError("history sample stable identity required")
                    if key != "case_id":
                        owner = group_owners.setdefault((key, value), sample["split"])
                        if owner != sample["split"]:
                            raise ValueError(f"history sample split_leakage: {key}")
                if type(sample.get("features")) is not list or len(
                    sample["features"]
                ) != len(FEATURE_NAMES):
                    raise ValueError("history sample feature dimensions invalid")
                for value in sample["features"]:
                    _number(value, "sample feature")
                _hash_field(sample.get("context_hash"))
                _validate_history_label_source(sample)
            elif "target_profile" in sample or "history_label_source" in sample:
                raise ValueError("terminal sample cannot declare history labels")
            if (
                sample_hash in sample_hashes
                or sample["case_id"] in case_ids
                or sample["model_identity_hash"] in physical_ids
            ):
                raise ValueError("duplicate training sample or physical model")
            sample_hashes.add(sample_hash)
            case_ids.add(sample["case_id"])
            physical_ids.add(sample["model_identity_hash"])
            splits.add(sample["split"])
            if sample["split"] == "train":
                if sample.get("context_hash") != policy.context_hash:
                    raise ValueError("training sample and policy context mismatch")
                train_hashes.append(sample_hash)
                train_identities.add(sample["model_identity_hash"])
        if (
            splits != {"train", "validation", "holdout"}
            or len(train_hashes) < 2
            or tuple(sorted(train_hashes)) != policy.training_sample_hashes
        ):
            raise ValueError("training sample membership does not match frozen policy")
        cases = report.get("cases")
        if (
            type(cases) is not list
            or len(cases) != len(samples)
            or any(
                type(row) is not dict
                or row.get("status") != "ready"
                or row.get("analysis_requested") is not True
                or not isinstance(row.get("case_id"), str)
                or row.get("split") not in ("train", "validation", "holdout")
                for row in cases
            )
            or sorted((row["case_id"], row["split"]) for row in cases)
            != sorted((row["case_id"], row["split"]) for row in samples)
        ):
            raise ValueError("training case and sample membership mismatch")
        if history_target:
            samples_by_id = {sample["case_id"]: sample for sample in samples}
            for row in cases:
                sample = samples_by_id[row["case_id"]]
                source = sample["history_label_source"]
                validation = row.get("validation")
                if (
                    row.get("public_result_hash") != sample["public_result_hash"]
                    or row.get("history_label_source_hash") != source["source_hash"]
                    or type(validation) is not dict
                    or validation.get("contract_pass") is not True
                    or validation.get("exact_engineering_recovery") is not True
                    or validation.get("checkpoint_available") is not True
                    or validation.get("result_hash") != sample["public_result_hash"]
                    or type(validation.get("terminal_epoch")) is not int
                    or validation["terminal_epoch"] != source["accepted_epoch_count"]
                    or _number(
                        validation.get("terminal_load_factor"), "terminal factor"
                    )
                    != 1.0
                    or type(row.get("history_label_collection_wall_ns")) is not int
                    or row["history_label_collection_wall_ns"] < 0
                    or type(row.get("data_generation_wall_ns")) is not int
                    or row["history_label_collection_wall_ns"]
                    > row["data_generation_wall_ns"]
                ):
                    raise ValueError("history training case/source or cost mismatch")
        cost = report.get("cost_accounting")
        if type(cost) is not dict or any(
            type(cost.get(key)) is not int or cost[key] < 0
            for key in (
                "data_generation_wall_ns",
                "training_wall_ns",
                "full_analysis_request_count",
            )
        ):
            raise ValueError("invalid training cost accounting")
        if cost["full_analysis_request_count"] != len(cases):
            raise ValueError("training request count and case membership mismatch")
        if history_target and cost.get("data_generation_scope") != _HISTORY_LABEL_SCOPE:
            raise ValueError("history label generation cost scope mismatch")
        return report, train_identities
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FiberFrameCandidateLearningError(
            f"invalid frozen training artifact: {exc}"
        ) from exc


def _validate_cases(cases: tuple[FiberFrameWarmStartDataCase, ...]) -> None:
    if not cases or any(
        type(case) is not FiberFrameWarmStartDataCase for case in cases
    ):
        raise FiberFrameCandidateLearningError("typed training cases required")
    if len({case.case_id for case in cases}) != len(cases):
        raise FiberFrameCandidateLearningError("duplicate training case_id")
    owners: dict[tuple[str, str], str] = {}
    physical_models: set[str] = set()
    for case in cases:
        keys = [
            (name, getattr(case, name))
            for name in ("project_id", "geometry_family_id", "load_history_id")
        ]
        try:
            physical_identity = candidate_model_identity(case.model)
        except ValueError:
            # Unsupported cases remain in collection's failure denominator.
            physical_identity = None
        if physical_identity is not None:
            keys.append(("physical_model", physical_identity))
        for key in keys:
            if key in owners and owners[key] != case.split:
                raise FiberFrameCandidateLearningError(f"split_leakage: {key[0]}")
            owners[key] = case.split
        if physical_identity in physical_models:
            raise FiberFrameCandidateLearningError("duplicate_physical_model")
        if physical_identity is not None:
            physical_models.add(physical_identity)


def _fit(
    samples: list[dict[str, Any]],
    ridge: float,
    margin: float,
    target_profile: str = CANDIDATE_TERMINAL_TARGET_PROFILE,
) -> FiberFrameCandidatePolicy:
    target_count = len(_target_names(target_profile))
    if target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE:
        for sample in samples:
            if sample.get("target_profile") != target_profile:
                raise FiberFrameCandidateLearningError(
                    "fit sample target profile mismatch"
                )
            _history_targets(sample["targets"])
            if len(sample["features"]) != len(FEATURE_NAMES):
                raise FiberFrameCandidateLearningError("fit feature dimensions invalid")
            for value in sample["features"]:
                _number(value, "fit feature")
    training = sorted(
        (row for row in samples if row["split"] == "train"),
        key=lambda row: row["sample_hash"],
    )
    if len(training) < 2 or {row["split"] for row in samples} != {
        "train",
        "validation",
        "holdout",
    }:
        raise FiberFrameCandidateLearningError(
            "two train cases plus validation and holdout required"
        )
    if len({row["context_hash"] for row in training}) != 1:
        raise FiberFrameCandidateLearningError(
            "train cases require one fixed analysis context"
        )
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            x = np.asarray([row["features"] for row in training], dtype=np.float64)
            y = np.asarray([row["targets"] for row in training], dtype=np.float64)
            mean = x.mean(axis=0)
            scale = np.maximum(np.max(np.abs(x - mean), axis=0), 1e-12)
            target_scale = np.maximum(np.max(np.abs(y), axis=0), 1e-12)
            design = np.column_stack(((x - mean) / scale, np.ones(len(x))))
            regularizer = np.eye(design.shape[1]) * math.sqrt(ridge)
            regularizer[-1, -1] = 0
            weights, _, _, _ = np.linalg.lstsq(
                np.vstack((design, regularizer)),
                np.vstack(
                    (y / target_scale, np.zeros((design.shape[1], target_count)))
                ),
                rcond=None,
            )
    except (FloatingPointError, np.linalg.LinAlgError) as exc:
        raise FiberFrameCandidateLearningError(
            "candidate training arithmetic failed"
        ) from exc
    return FiberFrameCandidatePolicy(
        training[0]["context_hash"],
        tuple(mean),
        tuple(scale),
        tuple(x.min(axis=0)),
        tuple(x.max(axis=0)),
        tuple(target_scale),
        tuple(tuple(row) for row in weights),
        tuple(row["sample_hash"] for row in training),
        ridge,
        margin,
        target_profile,
    )


def train_fiber_frame_candidate_policy(
    cases: Sequence[FiberFrameWarmStartDataCase],
    *,
    source_revision: str,
    ridge: float = 1e-6,
    ood_margin: float = 0.1,
    target_profile: str = CANDIDATE_TERMINAL_TARGET_PROFILE,
) -> FiberFrameCandidateTrainingResult:
    """Compute labels by full public solve, then fit only train-case targets."""
    source_revision = _source_revision(source_revision)
    target_names = _target_names(target_profile)
    history_target = target_profile == CANDIDATE_MATERIAL_HISTORY_TARGET_PROFILE
    ridge, ood_margin = _number(ridge, "ridge"), _number(ood_margin, "ood_margin")
    if ridge <= 0 or ood_margin < 0:
        raise FiberFrameCandidateLearningError("ridge or OOD margin invalid")
    cases = tuple(cases)
    data_started = perf_counter_ns()
    _validate_cases(cases)
    preflight_wall = perf_counter_ns() - data_started
    samples, rows = [], []
    for case in cases:
        started = perf_counter_ns()
        model = case.model
        row = {
            "case_id": case.case_id,
            "split": case.split,
            "status": "blocked",
            "solver_executed": False,
            "analysis_requested": False,
            "failure": None,
        }
        if history_target:
            row["history_label_collection_wall_ns"] = None
        try:
            features, context = candidate_preanalysis_features(model, case.config)
            row.update(analysis_requested=True, solver_executed=None)
            result = public_api.analyze_public_rc_fiber_frame(model, case.config)
            row["solver_executed"] = result.metrics.get("solver_executed")
            if any(
                item.get("kind") == "rc_fiber_frame_execution_failed"
                for item in result.unsupported_features
            ):
                row["solver_executed"] = None
            validation = public_api.validate_public_rc_fiber_frame_result(result)
            row.update(
                public_result_hash=result.result_hash, validation=validation.to_dict()
            )
            if (
                not validation.contract_pass
                or result.canonical_model_checksum != model.canonical_model_checksum
                or result.input_checksum != model.input_checksum
                or validation.terminal_epoch != case.config.load_steps
                or validation.terminal_load_factor != 1.0
            ):
                row["failure"] = "full_physical_verification_blocked"
            else:
                targets = [
                    max(
                        math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
                        for node in result.node_displacements
                    ),
                    max(abs(fiber["strain"]) for fiber in result.fiber_results),
                ]
                label_source = None
                if history_target:
                    history_started = perf_counter_ns()
                    try:
                        label_source = _collect_history_labels(result, case.config)
                        targets.extend(
                            max(epoch["targets"][i] for epoch in label_source["epochs"])
                            for i in range(5)
                        )
                        _history_targets(targets)
                    except Exception as exc:
                        row["history_label_failure"] = {
                            "kind": "history_label_collection_failed",
                            "exception_type": type(exc).__name__,
                            "detail": str(exc),
                        }
                        raise
                    finally:
                        row["history_label_collection_wall_ns"] = (
                            perf_counter_ns() - history_started
                        )
                body = {
                    "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
                    "feature_profile": CANDIDATE_FEATURE_PROFILE,
                    "case_id": case.case_id,
                    "split": case.split,
                    "project_id": case.project_id,
                    "geometry_family_id": case.geometry_family_id,
                    "load_history_id": case.load_history_id,
                    "model_identity_hash": candidate_model_identity(model),
                    "canonical_model_checksum": model.canonical_model_checksum,
                    "input_checksum": model.input_checksum,
                    "features": features,
                    "context_hash": context,
                    "targets": [_number(value, "target") for value in targets],
                    "public_result_hash": result.result_hash,
                    "checkpoint_chain_hash": result.contract_bindings[
                        "checkpoint_chain_hash"
                    ],
                }
                if history_target:
                    body.update(
                        target_profile=target_profile, history_label_source=label_source
                    )
                    _validate_history_label_source(body)
                    row["history_label_source_hash"] = label_source["source_hash"]
                samples.append({**body, "sample_hash": canonical_hash(body)})
                row["status"] = "ready"
        except Exception as exc:
            row.update(
                failure="label_collection_failed", exception_type=type(exc).__name__
            )
        row["data_generation_wall_ns"] = perf_counter_ns() - started
        rows.append(row)
    data_wall = perf_counter_ns() - data_started
    policy, failure, train_wall = None, None, None
    if all(row["status"] == "ready" for row in rows):
        train_started = perf_counter_ns()
        try:
            policy = (
                _fit(samples, ridge, ood_margin, target_profile)
                if history_target
                else _fit(samples, ridge, ood_margin)
            )
        except Exception as exc:
            failure = {
                "kind": "training_failed",
                "exception_type": type(exc).__name__,
                "detail": str(exc),
            }
        train_wall = perf_counter_ns() - train_started
    else:
        failure = {"kind": "one_or_more_label_cases_blocked"}
    report = {
        "schema_version": CANDIDATE_HISTORY_LEARNING_SCHEMA
        if history_target
        else CANDIDATE_LEARNING_SCHEMA,
        "identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": CANDIDATE_FEATURE_PROFILE,
        "status": "ready" if policy else "blocked",
        "source_revision": source_revision,
        "cases": rows,
        "samples": samples,
        "policy": policy.to_dict() if policy else None,
        "failure": failure,
        "cost_accounting": {
            "data_generation_wall_ns": data_wall,
            "validation_preflight_wall_ns": preflight_wall,
            "data_generation_scope": (
                "case_identity_preflight_features_and_full_public_label_collection"
            ),
            "training_wall_ns": train_wall,
            "full_analysis_request_count": sum(
                row["analysis_requested"] for row in rows
            ),
            "known_solver_execution_count": sum(
                row["solver_executed"] is True for row in rows
            ),
            "unknown_solver_execution_count": sum(
                row["solver_executed"] is None for row in rows
            ),
        },
        "claims": {
            "study_scope": "local_synthetic_section_family_research",
            "caller_declared_split_ids_prove_independent_projects": False,
            "independent_project_generalization_verified": False,
            "external_provenance_verified": False,
            "source_revision_is_attestation": False,
            "trained_on_evaluation_targets": False,
            "production_promotion_eligible": False,
            "terminal_screening_is_full_history_limit_envelope": False,
        },
    }
    if history_target:
        report.update(target_profile=target_profile, targets=list(target_names))
        report["cost_accounting"]["data_generation_scope"] = _HISTORY_LABEL_SCOPE
        report["claims"].update(_HISTORY_LABEL_CLAIMS)
    report["report_hash"] = canonical_hash(report)
    return FiberFrameCandidateTrainingResult(
        report["status"], policy, json.dumps(report, sort_keys=True, allow_nan=False)
    )
