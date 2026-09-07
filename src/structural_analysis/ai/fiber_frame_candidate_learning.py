"""Research candidate ranking from pre-solve section geometry and RC bar features.

Public solves produce the labels. Caller-declared split identifiers and source
revisions are not independent-project or external provenance attestations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
import json
import math
import re
from time import perf_counter_ns
from typing import Any

import numpy as np

from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark.fiber_frame_design import (
    calculate_fiber_frame_member_quantities,
)
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
)


class FiberFrameCandidateLearningError(ValueError):
    """Invalid or leaking candidate-learning experiment."""


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
    """Exclude labels and warnings so metadata-only renaming cannot split physics."""
    payload = model.canonical_payload()
    payload.pop("metadata", None)
    payload.pop("warnings", None)
    return canonical_hash(payload)


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
    snapshot = model.detached_analysis_snapshot()
    quantities = calculate_fiber_frame_member_quantities(snapshot)
    sections = {section["id"]: section for section in snapshot.sections}
    assigned = [sections[member["section"]] for member in snapshot.elements]
    n = len(assigned)
    try:
        values = (
            float(n),
            math.fsum(row["length_m"] for row in quantities["members"]),
            quantities["totals"]["gross_concrete_volume_m3"],
            quantities["totals"]["longitudinal_rebar_volume_m3"],
            *(
                math.fsum(float(row[name]) for row in assigned) / n
                for name in ("width_m", "depth_m", "cover_m")
            ),
            math.fsum(row["width_m"] * row["depth_m"] ** 3 / 12.0 for row in assigned),
            math.fsum(row["top_bar_count"] for row in assigned),
            math.fsum(row["bottom_bar_count"] for row in assigned),
            math.fsum(row["bar_area_m2"] for row in assigned),
        )
        features = tuple(_number(value, "feature") for value in values)
    except (OverflowError, ArithmeticError) as exc:
        raise FiberFrameCandidateLearningError("geometry features overflow") from exc
    context = snapshot.canonical_payload()
    context.pop("metadata", None)
    context.pop("warnings", None)
    for section in context["sections"]:
        for name in _SECTION_FEATURE_FIELDS:
            section.pop(name, None)
    return features, canonical_hash(
        {"fixed_analysis_context": context, "configuration": asdict(config)}
    )


@dataclass(frozen=True)
class FiberFrameCandidatePrediction:
    maximum_translation_m: float | None
    maximum_absolute_fiber_strain: float | None
    ood: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "uncertainty_kind": "uncalibrated_feature_range_indicator_not_probability",
            "physical_result_authority": False,
        }


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
    artifact_hash: str = field(init=False)

    def __post_init__(self) -> None:
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
            or len(self.target_scale) != 2
            or len(weights) != n + 1
            or any(len(row) != 2 for row in weights)
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
        return {
            "schema_version": "fiber-frame-candidate-ridge-policy.v1",
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
            "targets": [
                "terminal_maximum_translation_m",
                "terminal_maximum_absolute_fiber_strain",
            ],
            "preprocessing_fit_split": "train",
            "study_scope": "local_synthetic_section_family_research",
            "independent_project_generalization_verified": False,
            "production_promotion_eligible": False,
            "physical_result_authority": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "artifact_hash": self.artifact_hash}

    def predict(
        self, model: CanonicalModel, config: public_api.PublicRCFiberFrameConfig
    ) -> FiberFrameCandidatePrediction:
        def fallback(reason: str) -> FiberFrameCandidatePrediction:
            return FiberFrameCandidatePrediction(None, None, True, reason)

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
        except Exception:
            return fallback("feature_or_inference_failed")
        return FiberFrameCandidatePrediction(
            float(prediction[0]),
            float(prediction[1]),
            False,
            "in_train_feature_range_uncalibrated",
        )


@dataclass(frozen=True)
class FiberFrameCandidateTrainingResult:
    status: str
    policy: FiberFrameCandidatePolicy | None
    _report_json: str = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._report_json)


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
        physical_identity = candidate_model_identity(case.model)
        keys.append(("physical_model", physical_identity))
        for key in keys:
            if key in owners and owners[key] != case.split:
                raise FiberFrameCandidateLearningError(f"split_leakage: {key[0]}")
            owners[key] = case.split
        if physical_identity in physical_models:
            raise FiberFrameCandidateLearningError("duplicate_physical_model")
        physical_models.add(physical_identity)


def _fit(
    samples: list[dict[str, Any]], ridge: float, margin: float
) -> FiberFrameCandidatePolicy:
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
                np.vstack((y / target_scale, np.zeros((design.shape[1], 2)))),
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
    )


def train_fiber_frame_candidate_policy(
    cases: Sequence[FiberFrameWarmStartDataCase],
    *,
    source_revision: str,
    ridge: float = 1e-6,
    ood_margin: float = 0.1,
) -> FiberFrameCandidateTrainingResult:
    """Compute labels by full public solve, then fit only train-case targets."""
    source_revision = _source_revision(source_revision)
    ridge, ood_margin = _number(ridge, "ridge"), _number(ood_margin, "ood_margin")
    if ridge <= 0 or ood_margin < 0:
        raise FiberFrameCandidateLearningError("ridge or OOD margin invalid")
    cases = tuple(cases)
    _validate_cases(cases)
    data_started = perf_counter_ns()
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
                body = {
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
            policy = _fit(samples, ridge, ood_margin)
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
        "schema_version": "fiber-frame-candidate-learning.v1",
        "status": "ready" if policy else "blocked",
        "source_revision": source_revision,
        "cases": rows,
        "samples": samples,
        "policy": policy.to_dict() if policy else None,
        "failure": failure,
        "cost_accounting": {
            "data_generation_wall_ns": data_wall,
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
    report["report_hash"] = canonical_hash(report)
    return FiberFrameCandidateTrainingResult(
        report["status"], policy, json.dumps(report, sort_keys=True, allow_nan=False)
    )
