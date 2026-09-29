"""An experimental RC candidate policy for an authored indexed force response.

Only complete, freshly replayed numerical paths can provide training labels.
The policy ranks candidates; it never replaces an accepted solver result.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import ClassVar

import numpy as np

from structural_analysis.ai.fiber_frame_candidate_learning import (
    FEATURE_NAMES,
    candidate_model_identity,
)
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_learning import (
    CENTERED_FIT_METHOD,
    FIT_METHODS,
    TARGETS,
    _candidate_fit_parameters,
    _finite,
    _valid_targets,
    control_candidate_features,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model.schema import CanonicalModel


FORCE_FACTOR_POLICY_SCHEMA = "experimental-rc-control-force-factor-policy.v1"
FORCE_FACTOR_TRAINING_SCHEMA = "experimental-rc-control-force-factor-training.v1"
FORCE_FACTOR_TARGETS = (*TARGETS, "load_factor_at_target")
_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def _target(floor: dict) -> dict:
    return {
        "target_index": floor["target_index"],
        "target_control_displacement_m": floor["target_control_displacement_m"],
    }


def control_force_factor_features(model, request, force_response_floor):
    """Bind section descriptors to the complete request and indexed response.

    The threshold is deliberately not part of the feature context: a policy
    estimates the signed factor, and a predeclared threshold screens it later.
    """
    floor = study._validated_force_response_floor(force_response_floor, model, request)
    if floor is None:
        raise ValueError("indexed force-response floor required")
    values, context = control_candidate_features(model, request)
    return values, study._sha(
        study._bytes(
            {
                "feature_profile": "rc-control-indexed-force-factor.v1",
                "fixed_context_hash": context,
                "force_target": _target(floor),
            }
        )
    )


def _valid_force_targets(values):
    return (
        type(values) in (list, tuple)
        and len(values) == len(FORCE_FACTOR_TARGETS)
        and _valid_targets(values[:-1])
        and _finite(values[-1])
    )


@dataclass(frozen=True)
class RCControlForceFactorPolicy:
    """Strictly serialized, uncalibrated same-context candidate prediction."""

    _json: str
    _schema: ClassVar[str] = FORCE_FACTOR_POLICY_SCHEMA
    _features: ClassVar[tuple[str, ...]] = FEATURE_NAMES
    _targets: ClassVar[tuple[str, ...]] = FORCE_FACTOR_TARGETS

    def __post_init__(self):
        if type(self._json) is not str or len(self._json) > 2 * 1024 * 1024:
            raise ValueError("bounded serialized force-factor policy required")
        p = strict_json_object_bytes(self._json.encode(), maximum_bytes=2 * 1024 * 1024)
        keys = {
            "schema_version",
            "context_hash",
            "force_target",
            "features",
            "targets",
            "mean",
            "scale",
            "minimum",
            "maximum",
            "target_scale",
            "weights",
            "ridge",
            "ood_margin",
            "training_model_identities",
            "training_sample_hashes",
            "label_comparison_hash",
            "policy_hash",
        }
        if type(p) is not dict or set(p) != keys:
            raise ValueError("exact force-factor policy fields required")
        target = p["force_target"]
        if (
            p["schema_version"] != self._schema
            or p["features"] != list(self._features)
            or p["targets"] != list(self._targets)
            or type(target) is not dict
            or set(target) != {"target_index", "target_control_displacement_m"}
            or type(target["target_index"]) is not int
            or target["target_index"] < 0
            or not _finite(target["target_control_displacement_m"])
            or any(
                type(p[key]) is not str or _HASH.fullmatch(p[key]) is None
                for key in ("context_hash", "label_comparison_hash", "policy_hash")
            )
        ):
            raise ValueError("force-factor policy profile or context invalid")
        n, m = len(self._features), len(self._targets)
        for key, size in (
            ("mean", n),
            ("scale", n),
            ("minimum", n),
            ("maximum", n),
            ("target_scale", m),
        ):
            if (
                type(p[key]) is not list
                or len(p[key]) != size
                or not all(_finite(value) for value in p[key])
            ):
                raise ValueError("force-factor policy array invalid")
        if (
            any(value <= 0 for value in (*p["scale"], *p["target_scale"]))
            or any(
                low > high for low, high in zip(p["minimum"], p["maximum"], strict=True)
            )
            or not _finite(p["ridge"])
            or p["ridge"] <= 0
            or not _finite(p["ood_margin"])
            or not 0 <= p["ood_margin"] <= 1
            or type(p["weights"]) is not list
            or len(p["weights"]) != n + 1
            or any(
                type(row) is not list
                or len(row) != m
                or not all(_finite(value) for value in row)
                for row in p["weights"]
            )
        ):
            raise ValueError("force-factor policy numeric contract invalid")
        for key in ("training_model_identities", "training_sample_hashes"):
            values = p[key]
            if (
                type(values) is not list
                or not 2 <= len(values) <= 17
                or any(
                    type(value) is not str or _HASH.fullmatch(value) is None
                    for value in values
                )
                or len(set(values)) != len(values)
            ):
                raise ValueError("unique force-factor training identities required")
        if len(p["training_model_identities"]) != len(p["training_sample_hashes"]):
            raise ValueError("force-factor training identity counts differ")
        if (
            study._sha(
                study._bytes(
                    {key: value for key, value in p.items() if key != "policy_hash"}
                )
            )
            != p["policy_hash"]
        ):
            raise ValueError("force-factor policy hash mismatch")
        object.__setattr__(self, "_json", study._bytes(p).decode())

    def to_dict(self):
        return json.loads(self._json)

    @property
    def policy_hash(self):
        return self.to_dict()["policy_hash"]

    def predict(self, model, request, force_response_floor):
        values, context = control_force_factor_features(
            model, request, force_response_floor
        )
        p = self.to_dict()
        reason = None
        if (
            _target(force_response_floor) != p["force_target"]
            or context != p["context_hash"]
        ):
            reason = "force_target_or_fixed_context_mismatch"
        else:
            x = np.asarray(values)
            low, high = np.asarray(p["minimum"]), np.asarray(p["maximum"])
            margin = p["ood_margin"] * (high - low)
            if np.any(x < low - margin) or np.any(x > high + margin):
                reason = "outside_training_feature_bounds"
        prediction = None
        if reason is None:
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                z = np.append((np.asarray(values) - p["mean"]) / p["scale"], 1.0)
                targets = (z @ np.asarray(p["weights"])) * p["target_scale"]
            converted = targets.tolist()
            if not _valid_force_targets(converted):
                reason = "prediction_nonfinite_or_inconsistent"
            else:
                prediction = dict(zip(self._targets, converted, strict=True))
        return {
            "policy_hash": p["policy_hash"],
            "performance": prediction,
            "abstained": prediction is None,
            "reason": reason or "in_training_feature_bounds_uncalibrated",
            "physical_result_authority": False,
            "uncertainty_calibrated": False,
        }


def load_rc_control_force_factor_policy(raw: bytes):
    if type(raw) is not bytes:
        raise ValueError("force-factor policy bytes required")
    return RCControlForceFactorPolicy(raw.decode("utf-8"))


def train_rc_control_force_factor_policy(
    baseline: CanonicalModel,
    candidates: tuple[design.FiberFrameDesignCandidate, ...],
    request: BoundedRCFiberDirectControlRequest,
    *,
    force_response_floor: dict,
    history_limits: design.FiberFrameHistoryLimits,
    material_limits: design.FiberFrameMaterialHistoryLimits,
    source_revision: str,
    output_directory: Path,
    ridge: float = 1.0,
    ood_margin: float = 0.0,
    fit_method: str = CENTERED_FIT_METHOD,
):
    """Fit only on complete, freshly replayed same-context indexed responses."""
    if (
        type(baseline) is not CanonicalModel
        or type(request) is not BoundedRCFiberDirectControlRequest
    ):
        raise ValueError("exact baseline and direct-control request required")
    request = decode_bounded_rc_fiber_direct_control_request(
        study._bytes(request.to_dict())
    )
    floor = study._validated_force_response_floor(
        force_response_floor, baseline, request
    )
    if floor is None:
        raise ValueError("indexed force-response floor required")
    if (
        type(candidates) is not tuple
        or not 1 <= len(candidates) <= 16
        or any(
            type(candidate) is not design.FiberFrameDesignCandidate
            for candidate in candidates
        )
        or type(history_limits) is not design.FiberFrameHistoryLimits
        or type(material_limits) is not design.FiberFrameMaterialHistoryLimits
    ):
        raise ValueError("exact training candidates and screens required")
    if (
        type(source_revision) is not str
        or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None
    ):
        raise ValueError("full source revision required")
    if (
        fit_method not in FIT_METHODS
        or not _finite(ridge)
        or ridge <= 0
        or not _finite(ood_margin)
        or not 0 <= ood_margin <= 1
    ):
        raise ValueError("supported finite force-factor fit configuration required")
    started_wall, started_cpu = perf_counter_ns(), process_time_ns()
    original = baseline.detached_analysis_snapshot()
    models = [original] + [
        design.apply_fiber_frame_section_changes(original, candidate)
        for candidate in candidates
    ]
    descriptors = [
        control_force_factor_features(model, request, floor) for model in models
    ]
    model_ids = [
        candidate_model_identity(model, experimental_pin_roller_beam=True)
        for model in models
    ]
    if (
        len(set(model_ids)) != len(models)
        or len({context for _, context in descriptors}) != 1
    ):
        raise ValueError(
            "unique physical training models in one fixed context required"
        )
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    study._save(
        root,
        "plan.json",
        study._bytes(
            {
                "schema_version": "experimental-rc-control-force-factor-training-plan.v1",
                "source_revision": source_revision,
                "training_model_identities": model_ids,
                "context_hash": descriptors[0][1],
                "control_request": request.to_dict(),
                "force_response_floor": floor,
                "ridge": ridge,
                "ood_margin": ood_margin,
                "fit_method": fit_method,
                "independent_project_geometry_history_split": False,
            }
        ),
    )
    labels = study.compare_rc_control_designs(
        original,
        candidates,
        request,
        history_limits=history_limits,
        material_limits=material_limits,
        prices=None,
        source_revision=source_revision,
        output_directory=root / "labels",
        force_response_floor=floor,
    )
    if (
        labels["status"] != "complete"
        or len(labels["rows"]) != len(models)
        or not all(row["full_reference_verification_pass"] for row in labels["rows"])
    ):
        raise ValueError(
            "all force-factor training paths must complete and freshly verify"
        )
    invocations = [inv for row in labels["rows"] for inv in row["invocations"]]
    if any(inv["unknown_execution_work"] or inv["work"] is None for inv in invocations):
        raise ValueError("unknown numerical work cannot supply force-factor labels")
    samples = []
    for row, model, (features, _) in zip(
        labels["rows"], models, descriptors, strict=True
    ):
        ref = row["artifacts"]["model"]
        raw = (root / "labels" / ref["path"]).read_bytes()
        if len(raw) != ref["byte_length"] or study._sha(raw) != ref["sha256"]:
            raise ValueError("original force-factor training model bytes differ")
        if (
            load_neutral_json_bytes(raw).canonical_model_checksum
            != model.canonical_model_checksum
        ):
            raise ValueError("force-factor training row/model order differs")
        targets = [row["performance"][key] for key in FORCE_FACTOR_TARGETS]
        if not _valid_force_targets(targets):
            raise ValueError(
                "complete finite signed force-factor training labels required"
            )
        sample = {
            "model_identity": candidate_model_identity(
                model, experimental_pin_roller_beam=True
            ),
            "features": list(features),
            "targets": targets,
            "result_sha256": row["artifacts"]["result"]["sha256"],
            "verification_sha256": row["artifacts"]["verification"]["sha256"],
        }
        sample["sample_hash"] = study._sha(study._bytes(sample))
        samples.append(sample)
    study._save(root, "training-samples.json", study._bytes(samples))
    study._save(
        root,
        "fit-started.json",
        study._bytes(
            {
                "status": "started",
                "unknown_fit_work_until_outcome": True,
            }
        ),
    )
    fit_wall, fit_cpu = perf_counter_ns(), process_time_ns()
    try:
        parameters = _candidate_fit_parameters(
            np.asarray([sample["features"] for sample in samples]),
            np.asarray([sample["targets"] for sample in samples]),
            ridge,
            fit_method,
        )
        payload = {
            "schema_version": FORCE_FACTOR_POLICY_SCHEMA,
            "context_hash": descriptors[0][1],
            "force_target": _target(floor),
            "features": list(FEATURE_NAMES),
            "targets": list(FORCE_FACTOR_TARGETS),
            **parameters,
            "ridge": ridge,
            "ood_margin": ood_margin,
            "training_model_identities": model_ids,
            "training_sample_hashes": [sample["sample_hash"] for sample in samples],
            "label_comparison_hash": labels["report_hash"],
        }
        payload["policy_hash"] = study._sha(study._bytes(payload))
        policy = RCControlForceFactorPolicy(study._bytes(payload).decode())
    except BaseException as error:
        study._save(
            root,
            "fit-outcome.json",
            study._bytes(
                {
                    "status": "interrupted"
                    if isinstance(error, KeyboardInterrupt)
                    else "raised",
                    "exception_kind": type(error).__name__,
                    "wall_ns": perf_counter_ns() - fit_wall,
                    "cpu_ns": process_time_ns() - fit_cpu,
                    "unknown_fit_work_until_outcome": True,
                }
            ),
        )
        raise
    fit = {
        "status": "completed",
        "wall_ns": perf_counter_ns() - fit_wall,
        "cpu_ns": process_time_ns() - fit_cpu,
        "unknown_fit_work_until_outcome": False,
        "method": fit_method,
    }
    study._save(root, "fit-outcome.json", study._bytes(fit))
    study._save(root, "policy.json", study._bytes(policy.to_dict()))
    report = {
        "schema_version": FORCE_FACTOR_TRAINING_SCHEMA,
        "source_revision": source_revision,
        "force_response_floor": floor,
        "label_comparison_hash": labels["report_hash"],
        "policy_hash": policy.policy_hash,
        "sample_count": len(samples),
        "fit": fit,
        "label_generation_wall_ns": labels["total_wall_ns"],
        "label_invocations": invocations,
        "wall_ns": perf_counter_ns() - started_wall,
        "cpu_ns": process_time_ns() - started_cpu,
        "timing_scope": "training_preparation_labels_fresh_replay_fit_and_artifact_IO_excluding_final_report_write",
        "independent_generalization": False,
        "net_savings_proved": False,
    }
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "training.json", study._bytes(report))
    return policy, report
