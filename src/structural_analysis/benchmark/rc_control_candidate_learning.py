"""Candidate ranking labels from complete, freshly verified RC control studies.

This fixed-family learner ranks geometry alternatives. It does not inherit the
load-control learner's response labels or establish independent generalization.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns

import numpy as np

from structural_analysis.ai.fiber_frame_candidate_learning import (
    FEATURE_NAMES,
    candidate_model_identity,
    candidate_preanalysis_features,
)
from structural_analysis.api.nonlinear_fiber_frame import PublicRCFiberFrameConfig
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model.schema import CanonicalModel


POLICY_SCHEMA = "experimental-rc-control-candidate-policy.v1"
TARGETS = (
    "terminal_maximum_translation_m",
    "terminal_maximum_absolute_fiber_strain",
    "maximum_translation_m",
    "maximum_absolute_fiber_strain",
    "maximum_steel_accumulated_plastic_strain",
    "maximum_concrete_tensile_damage",
    "maximum_concrete_compressive_damage",
)
_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def control_candidate_features(model, request):
    """Reuse pre-solve geometry descriptors, binding the complete control request.

    The default public configuration is only the existing descriptor's fixed
    serialization context. No load-control solve or label is invoked here.
    The direct request separately binds control DOF, constants, complete target
    order, reversal rules, tolerances and arithmetic.
    """
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact direct-control request required")
    restored = decode_bounded_rc_fiber_direct_control_request(
        study._bytes(request.to_dict())
    )
    values, geometry_context = candidate_preanalysis_features(
        model, PublicRCFiberFrameConfig()
    )
    return values, study._sha(
        study._bytes(
            {
                "feature_profile": "rc-control-fixed-family-candidate.v1",
                "geometry_context": geometry_context,
                "control_request": restored.to_dict(),
            }
        )
    )


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _valid_targets(values):
    return (
        len(values) == len(TARGETS)
        and all(_finite(v) and v >= 0 for v in values)
        and values[0] <= values[2]
        and values[1] <= values[3]
        and values[5] <= 1
        and values[6] <= 1
    )


@dataclass(frozen=True)
class RCControlCandidatePolicy:
    """An immutable serialized policy; each exported dictionary is detached."""

    _json: str

    def __post_init__(self):
        if type(self._json) is not str or len(self._json) > 2 * 1024 * 1024:
            raise ValueError("bounded serialized candidate policy required")
        p = json.loads(self._json)
        keys = {
            "schema_version",
            "context_hash",
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
            raise ValueError("exact candidate policy fields required")
        if (
            p["schema_version"] != POLICY_SCHEMA
            or p["features"] != list(FEATURE_NAMES)
            or p["targets"] != list(TARGETS)
            or any(
                type(p[k]) is not str or not _HASH.fullmatch(p[k])
                for k in ("context_hash", "label_comparison_hash", "policy_hash")
            )
        ):
            raise ValueError("candidate policy profile or identity mismatch")
        n = len(FEATURE_NAMES)
        for key, size in (
            ("mean", n),
            ("scale", n),
            ("minimum", n),
            ("maximum", n),
            ("target_scale", len(TARGETS)),
        ):
            if (
                type(p[key]) is not list
                or len(p[key]) != size
                or not all(_finite(v) for v in p[key])
            ):
                raise ValueError("candidate policy array dimensions or values invalid")
        if (
            any(v <= 0 for v in (*p["scale"], *p["target_scale"]))
            or any(lo > hi for lo, hi in zip(p["minimum"], p["maximum"], strict=True))
            or not _finite(p["ridge"])
            or p["ridge"] <= 0
            or not _finite(p["ood_margin"])
            or not 0 <= p["ood_margin"] <= 1
            or type(p["weights"]) is not list
            or len(p["weights"]) != n + 1
            or any(
                type(row) is not list
                or len(row) != len(TARGETS)
                or not all(_finite(v) for v in row)
                for row in p["weights"]
            )
        ):
            raise ValueError("candidate policy numeric contract invalid")
        for key in ("training_model_identities", "training_sample_hashes"):
            values = p[key]
            if (
                type(values) is not list
                or not 2 <= len(values) <= 17
                or any(type(v) is not str or not _HASH.fullmatch(v) for v in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError("unique training identities required")
        if len(p["training_model_identities"]) != len(p["training_sample_hashes"]):
            raise ValueError("training identity counts differ")
        payload = {k: v for k, v in p.items() if k != "policy_hash"}
        if study._sha(study._bytes(payload)) != p["policy_hash"]:
            raise ValueError("candidate policy hash mismatch")
        object.__setattr__(self, "_json", study._bytes(p).decode())

    def to_dict(self):
        return json.loads(self._json)

    @property
    def policy_hash(self):
        return self.to_dict()["policy_hash"]

    def predict(self, model, request):
        p = self.to_dict()
        values, context = control_candidate_features(model, request)
        reason = None
        x = np.asarray(values)
        if context != p["context_hash"]:
            reason = "control_or_fixed_model_context_mismatch"
        else:
            low, high = np.asarray(p["minimum"]), np.asarray(p["maximum"])
            margin = p["ood_margin"] * (high - low)
            if np.any(x < low - margin) or np.any(x > high + margin):
                reason = "outside_training_feature_bounds"
        prediction = None
        if reason is None:
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                z = np.append((x - p["mean"]) / p["scale"], 1.0)
                values = (z @ np.asarray(p["weights"])) * p["target_scale"]
            converted = values.tolist()
            if not _valid_targets(converted):
                reason = "prediction_nonfinite_or_inconsistent"
            else:
                prediction = dict(zip(TARGETS, converted, strict=True))
        return {
            "policy_hash": p["policy_hash"],
            "performance": prediction,
            "abstained": prediction is None,
            "reason": reason or "in_training_feature_bounds_uncalibrated",
            "physical_result_authority": False,
            "uncertainty_calibrated": False,
        }


def train_rc_control_candidate_policy(
    baseline: CanonicalModel,
    candidates: tuple[design.FiberFrameDesignCandidate, ...],
    request: BoundedRCFiberDirectControlRequest,
    *,
    history_limits: design.FiberFrameHistoryLimits,
    material_limits: design.FiberFrameMaterialHistoryLimits,
    source_revision: str,
    output_directory: Path,
    ridge: float = 1.0,
    ood_margin: float = 0.0,
):
    """Generate full reference/replay labels, then fit only this training family.

    Screens are recorded but do not filter training rows. Infeasible examples
    are useful labels; incomplete or unverified physical paths are not labels.
    """
    wall, cpu = perf_counter_ns(), process_time_ns()
    if (
        not _finite(ridge)
        or ridge <= 0
        or not _finite(ood_margin)
        or not 0 <= ood_margin <= 1
    ):
        raise ValueError("positive finite ridge and bounded OOD margin required")
    if type(candidates) is not tuple or not 1 <= len(candidates) <= 16:
        raise ValueError("one to sixteen training alternatives required")
    if type(source_revision) is not str or not re.fullmatch(
        r"[0-9a-f]{40}", source_revision
    ):
        raise ValueError("full source revision required")
    models = [baseline.detached_analysis_snapshot()] + [
        design.apply_fiber_frame_section_changes(baseline, c) for c in candidates
    ]
    descriptors = [control_candidate_features(m, request) for m in models]
    model_ids = [candidate_model_identity(m) for m in models]
    if len(set(model_ids)) != len(models) or len({d[1] for d in descriptors}) != 1:
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
                "source_revision": source_revision,
                "training_model_identities": model_ids,
                "context_hash": descriptors[0][1],
                "control_request": request.to_dict(),
                "ridge": ridge,
                "ood_margin": ood_margin,
                "independent_campaign": False,
            }
        ),
    )
    labels = study.compare_rc_control_designs(
        baseline,
        candidates,
        request,
        history_limits=history_limits,
        material_limits=material_limits,
        prices=None,
        source_revision=source_revision,
        output_directory=root / "labels",
    )
    if labels["status"] != "complete" or not all(
        r["full_reference_verification_pass"] for r in labels["rows"]
    ):
        raise ValueError("all full training paths must complete and freshly verify")
    samples = []
    for row, model, descriptor in zip(labels["rows"], models, descriptors, strict=True):
        ref = row["artifacts"]["model"]
        raw = (root / "labels" / ref["path"]).read_bytes()
        if len(raw) != ref["byte_length"] or study._sha(raw) != ref["sha256"]:
            raise ValueError("original training model bytes differ")
        original = load_neutral_json_bytes(raw)
        if original.canonical_model_checksum != model.canonical_model_checksum:
            raise ValueError("training row/model order differs")
        targets = [row["performance"][key] for key in TARGETS]
        if not _valid_targets(targets):
            raise ValueError(
                "complete finite training response/material targets required"
            )
        sample = {
            "model_identity": candidate_model_identity(model),
            "features": list(descriptor[0]),
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
        study._bytes({"status": "started", "unknown_fit_work_until_outcome": True}),
    )
    fit_wall, fit_cpu = perf_counter_ns(), process_time_ns()
    try:
        x = np.asarray([s["features"] for s in samples])
        y = np.asarray([s["targets"] for s in samples])
        mean, scale, target_scale = x.mean(axis=0), x.std(axis=0), y.std(axis=0)
        scale, target_scale = (
            np.where(scale > 0, scale, 1.0),
            np.where(target_scale > 0, target_scale, 1.0),
        )
        z = np.column_stack(((x - mean) / scale, np.ones(len(x))))
        u, singular, vt = np.linalg.svd(z, full_matrices=False)
        weights = (vt.T * (singular / (singular**2 + ridge))) @ u.T @ (y / target_scale)
        p = {
            "schema_version": POLICY_SCHEMA,
            "context_hash": descriptors[0][1],
            "features": list(FEATURE_NAMES),
            "targets": list(TARGETS),
            "mean": mean.tolist(),
            "scale": scale.tolist(),
            "minimum": x.min(axis=0).tolist(),
            "maximum": x.max(axis=0).tolist(),
            "target_scale": target_scale.tolist(),
            "weights": weights.tolist(),
            "ridge": ridge,
            "ood_margin": ood_margin,
            "training_model_identities": model_ids,
            "training_sample_hashes": [s["sample_hash"] for s in samples],
            "label_comparison_hash": labels["report_hash"],
        }
        p["policy_hash"] = study._sha(study._bytes(p))
        policy = RCControlCandidatePolicy(study._bytes(p).decode())
    except BaseException as exc:
        study._save(
            root,
            "fit-outcome.json",
            study._bytes(
                {
                    "status": "interrupted"
                    if isinstance(exc, KeyboardInterrupt)
                    else "raised",
                    "exception_kind": type(exc).__name__,
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
        "method": "svd-ridge-penalized-intercept.v1",
    }
    study._save(root, "fit-outcome.json", study._bytes(fit))
    study._save(root, "policy.json", study._bytes(policy.to_dict()))
    report = {
        "schema_version": "experimental-rc-control-candidate-training.v1",
        "source_revision": source_revision,
        "label_comparison_hash": labels["report_hash"],
        "policy_hash": policy.policy_hash,
        "sample_count": len(samples),
        "fit": fit,
        "label_generation_wall_ns": labels["total_wall_ns"],
        "label_invocations": [
            inv for row in labels["rows"] for inv in row["invocations"]
        ],
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - cpu,
        "timing_scope": "training_preparation_labels_fresh_replay_fit_and_artifact_IO_excluding_final_report_write",
        "independent_generalization": False,
        "net_savings_proved": False,
    }
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "training.json", study._bytes(report))
    return policy, report
