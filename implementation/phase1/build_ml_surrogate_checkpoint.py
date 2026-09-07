#!/usr/bin/env python3
"""Build a research surrogate with strict pre-analysis inputs and solver authority."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_STATE_NPZ = REPO_ROOT / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_long_state.npz"
DEFAULT_CHECKPOINT_DIR = REPO_ROOT / "implementation/phase1/release/ml_surrogate"

NUMERIC_FEATURES = [
    "rebar_ratio",
    "thickness_scale",
    "story_band",
]
CATEGORICAL_FEATURES = ["member_type", "zone_label", "section_signature"]
TARGETS = ["max_dcr", "member_story_drift_contribution_pct", "log1p_group_cost_proxy"]
TARGET_SOURCE_FIELDS = ["max_dcr", "member_story_drift_contribution_pct", "group_cost_proxy"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _split_for_group(group_id: str) -> str:
    bucket = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket < 6:
        return "train"
    if bucket < 8:
        return "validation"
    return "test"


def _required_array(data: np.lib.npyio.NpzFile, key: str, n: int | None = None) -> np.ndarray:
    if key not in data.files:
        raise ValueError(f"dataset_missing_field:{key}")
    try:
        values = np.asarray(data[key])
    except ValueError as exc:
        raise ValueError(f"dataset_unsupported_dtype:{key}") from exc
    if values.ndim != 1 or (n is not None and values.shape != (n,)):
        raise ValueError(f"dataset_shape_mismatch:{key}:expected=({n},):actual={values.shape}")
    return values


def _finite_array(data: np.lib.npyio.NpzFile, key: str, n: int) -> np.ndarray:
    values = _required_array(data, key, n)
    if values.dtype.kind not in "iuf":
        raise ValueError(f"dataset_non_numeric_field:{key}")
    values = values.astype(np.float64)
    if not bool(np.isfinite(values).all()):
        raise ValueError(f"dataset_non_finite_field:{key}")
    if key == "group_cost_proxy" and bool((values < 0.0).any()):
        raise ValueError("dataset_negative_cost:group_cost_proxy")
    if bool((values < 0.0).any()):
        raise ValueError(f"dataset_negative_field:{key}")
    if key == "rebar_ratio" and bool((values > 1.0).any()):
        raise ValueError("dataset_domain_violation:rebar_ratio")
    if key == "thickness_scale" and bool((values <= 0.0).any()):
        raise ValueError("dataset_domain_violation:thickness_scale")
    if key == "story_band" and bool((values != np.floor(values)).any()):
        raise ValueError("dataset_domain_violation:story_band")
    return values


def _text_array(data: np.lib.npyio.NpzFile, key: str, n: int | None = None) -> np.ndarray:
    values = _required_array(data, key, n)
    if values.dtype.kind != "U":
        raise ValueError(f"dataset_non_text_field:{key}")
    if any(not value.strip() or value != value.strip() for value in values.tolist()):
        raise ValueError(f"dataset_empty_or_untrimmed_field:{key}")
    return values


def _feature_matrix(
    data: np.lib.npyio.NpzFile, splits: np.ndarray,
) -> tuple[np.ndarray, list[str], dict[str, list[str]]]:
    n = len(splits)
    columns: list[np.ndarray] = []
    feature_names: list[str] = []
    for key in NUMERIC_FEATURES:
        columns.append(_finite_array(data, key, n))
        feature_names.append(key)

    vocab: dict[str, list[str]] = {}
    for key in CATEGORICAL_FEATURES:
        raw = _text_array(data, key, n)
        training_values = raw[splits == "train"].tolist()
        values = sorted(set(training_values))
        if key == "section_signature":
            counts: dict[str, int] = {}
            for item in training_values:
                text = str(item)
                counts[text] = counts.get(text, 0) + 1
            values = [value for value, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:24]]
        vocab[key] = values
        for value in values:
            columns.append(np.asarray([1.0 if str(item) == value else 0.0 for item in raw.tolist()], dtype=np.float64))
            feature_names.append(f"{key}={value}")
    return np.vstack(columns).T.astype(np.float64), feature_names, vocab


def _target_matrix(data: np.lib.npyio.NpzFile) -> np.ndarray:
    cost = _finite_array(data, "group_cost_proxy", int(np.asarray(data["group_ids"]).shape[0]))
    return np.vstack(
        [
            _finite_array(data, "max_dcr", cost.shape[0]),
            _finite_array(data, "member_story_drift_contribution_pct", cost.shape[0]),
            np.log1p(cost),
        ]
    ).T.astype(np.float64)


def _fit_ridge(x: np.ndarray, y: np.ndarray, splits: np.ndarray, ridge_lambda: float = 1.0e-6) -> dict[str, Any]:
    train = splits == "train"
    mean = x[train].mean(axis=0)
    scale = x[train].std(axis=0)
    scale[scale < 1.0e-12] = 1.0
    x_norm = (x - mean) / scale
    design = np.c_[np.ones(x_norm.shape[0]), x_norm]
    xt = design[train]
    yt = y[train]
    reg = ridge_lambda * np.eye(xt.shape[1])
    reg[0, 0] = 0.0
    weights = np.linalg.solve(xt.T @ xt + reg, xt.T @ yt)
    pred = design @ weights
    return {
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "weights": weights.tolist(),
        "predictions": pred,
    }


def _metrics(y: np.ndarray, pred: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    if not bool(mask.any()):
        return {"count": 0, "mae": {}, "p95_abs_error": {}, "max_abs_error": {}}
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            err = np.abs(pred[mask] - y[mask])
            aggregates = {
                "mae": err.mean(axis=0),
                "p95_abs_error": np.quantile(err, 0.95, axis=0),
                "max_abs_error": err.max(axis=0),
            }
    except FloatingPointError as exc:
        raise ValueError("dataset_non_finite_metrics") from exc
    if any(not bool(np.isfinite(values).all()) for values in aggregates.values()):
        raise ValueError("dataset_non_finite_metrics")
    return {
        "count": int(err.shape[0]),
        **{
            metric: {name: float(value) for name, value in zip(TARGETS, values.tolist())}
            for metric, values in aggregates.items()
        },
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")


def build_ml_surrogate_checkpoint(
    *,
    state_npz: Path = DEFAULT_STATE_NPZ,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    with np.load(state_npz, allow_pickle=False) as data:
        group_ids = _text_array(data, "group_ids")
        if len(group_ids) == 0:
            raise ValueError("dataset_empty_rows")
        if len(set(group_ids.tolist())) != len(group_ids):
            raise ValueError("dataset_duplicate_group_id")
        splits = np.asarray([_split_for_group(group_id) for group_id in group_ids.tolist()])
        if any(not bool((splits == split).any()) for split in ["train", "validation", "test"]):
            raise ValueError("dataset_empty_split:train_validation_test_required")
        x, feature_names, vocab = _feature_matrix(data, splits)
        y = _target_matrix(data)
        unknown_categories = np.zeros(len(group_ids), dtype=np.int64)
        for key, values in vocab.items():
            unknown_categories += ~np.isin(_text_array(data, key, len(group_ids)), values)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            model = _fit_ridge(x, y, splits)
    except (FloatingPointError, np.linalg.LinAlgError) as exc:
        raise ValueError("dataset_non_finite_or_unsolvable_fit") from exc
    pred = np.asarray(model.pop("predictions"), dtype=np.float64)
    if not bool(np.isfinite(pred).all()) or any(
        not bool(np.isfinite(np.asarray(model[key])).all())
        for key in ["feature_mean", "feature_scale", "weights"]
    ):
        raise ValueError("dataset_non_finite_fit")

    split_metrics = {split: _metrics(y, pred, splits == split) for split in ["train", "validation", "test"]}
    thresholds = {
        "validation_max_dcr_mae": 0.12,
        "validation_max_dcr_p95_abs_error": 0.30,
        "test_max_dcr_mae": 0.12,
        "test_max_dcr_p95_abs_error": 0.30,
        "test_log1p_group_cost_proxy_p95_abs_error": 0.02,
    }
    configured_criteria_pass = bool(
        split_metrics["validation"]["mae"]["max_dcr"] <= thresholds["validation_max_dcr_mae"]
        and split_metrics["validation"]["p95_abs_error"]["max_dcr"]
        <= thresholds["validation_max_dcr_p95_abs_error"]
        and split_metrics["test"]["mae"]["max_dcr"] <= thresholds["test_max_dcr_mae"]
        and split_metrics["test"]["p95_abs_error"]["max_dcr"] <= thresholds["test_max_dcr_p95_abs_error"]
        and split_metrics["test"]["p95_abs_error"]["log1p_group_cost_proxy"]
        <= thresholds["test_log1p_group_cost_proxy_p95_abs_error"]
    )
    # No approved drift-error threshold exists in the current catalog. Keep
    # those metrics visible, but do not turn a partial target check into a
    # successful validation of the complete three-target surrogate.
    unassessed_targets = ["member_story_drift_contribution_pct"]
    validation_pass = configured_criteria_pass and not unassessed_targets
    validation_coverage = {
        "configured_criteria_pass": configured_criteria_pass,
        "assessed_targets": ["max_dcr", "log1p_group_cost_proxy"],
        "unassessed_targets": unassessed_targets,
        "all_target_criteria_defined": False,
        "blockers": ["drift_target_error_threshold_not_defined"],
    }

    train_mask = splits == "train"
    feature_min = x[train_mask].min(axis=0)
    feature_max = x[train_mask].max(axis=0)
    tolerance = np.maximum((feature_max - feature_min) * 0.10, 1.0e-9)
    ood_rows = []
    for index, group_id in enumerate(group_ids.tolist()):
        below = x[index] < (feature_min - tolerance)
        above = x[index] > (feature_max + tolerance)
        feature_count = int(np.count_nonzero(below | above)) + int(unknown_categories[index])
        if feature_count:
            ood_rows.append({"group_id": str(group_id), "feature_count": feature_count})
    ood_pass = len(ood_rows) == 0

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "checkpoint.pt"
    dataset_card_path = checkpoint_dir / "dataset_card.json"
    model_card_path = checkpoint_dir / "model_card.json"
    validation_path = checkpoint_dir / "validation_receipt.json"
    ood_path = checkpoint_dir / "ood_gate.json"
    fallback_path = checkpoint_dir / "solver_fallback_receipt.json"
    manifest_path = output_json or (productization_dir / "ml_surrogate_checkpoint_manifest.json")

    common_artifacts = {
        "dataset_card": str(dataset_card_path),
        "model_card": str(model_card_path),
        "validation_receipt": str(validation_path),
        "ood_gate": str(ood_path),
        "solver_fallback_receipt": str(fallback_path),
    }
    split_policy = {
        "method": "sha256_group_id_60_20_20",
        "scope": "member_group_research_only",
        "preprocessing_fit_split": "train",
        "project_geometry_load_history_isolation_verified": False,
        "generalization_claim": "not_established",
    }
    dataset_contract = {
        "version": "pre-analysis-design-inputs.v1",
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "target_source_fields": TARGET_SOURCE_FIELDS,
        "candidate_response_features_permitted": False,
        "invalid_input_policy": "reject_missing_shape_dtype_non_finite",
        "split_policy": split_policy,
    }
    checkpoint_payload = {
        "schema_version": "ml-surrogate-checkpoint.v1",
        "generated_at": generated_at,
        "model_id": "bounded-linear-response-shadow-v1",
        "model_family": "ridge_linear_surrogate",
        "mode": "shadow_with_solver_fallback",
        "state_npz": str(state_npz),
        "state_npz_sha256": _sha256(state_npz),
        "feature_names": feature_names,
        "categorical_vocabulary": vocab,
        "targets": TARGETS,
        "dataset_contract": dataset_contract,
        "normalization": {
            "feature_mean": model["feature_mean"],
            "feature_scale": model["feature_scale"],
        },
        "weights": model["weights"],
        "production_activation": {
            "enabled": False,
            "mode": "shadow_with_solver_fallback",
            "blocked_reason": "project_geometry_load_history_isolation_not_verified",
            "hard_constraints": "solver_and_code_check_required_for_final_promotion",
            "can_change_final_design_without_solver": False,
        },
        "artifacts": common_artifacts,
        "checkpoint_payload_sha256": "",
    }
    checkpoint_payload["checkpoint_payload_sha256"] = _json_sha({k: v for k, v in checkpoint_payload.items() if k != "checkpoint_payload_sha256"})
    _write(checkpoint_path, checkpoint_payload)

    dataset_card = {
        "schema_version": "ml-surrogate-dataset-card.v1",
        "generated_at": generated_at,
        "status": "research_only",
        "source_state_npz": str(state_npz),
        "source_state_npz_sha256": _sha256(state_npz),
        "row_count": int(group_ids.shape[0]),
        "split_counts": {split: int(np.count_nonzero(splits == split)) for split in ["train", "validation", "test"]},
        "feature_count": len(feature_names),
        "target_names": TARGETS,
        "dataset_contract": dataset_contract,
        "promotion_eligible": False,
        "lineage": [
            str(state_npz),
            "source hash identifies the supplied state; project/geometry/load-history provenance is not verified",
            "solver/code gate remains authoritative for final design promotion",
        ],
    }
    _write(dataset_card_path, dataset_card)

    model_card = {
        "schema_version": "ml-surrogate-model-card.v1",
        "generated_at": generated_at,
        "status": "research_only",
        "model_id": checkpoint_payload["model_id"],
        "model_family": checkpoint_payload["model_family"],
        "intended_use": "shadow response/cost estimate for engineer-in-loop optimization triage",
        "not_for": [
            "permit approval",
            "solver replacement",
            "final design promotion without solver/code replay",
            "cross-project generalization claims from member-group holdout metrics",
        ],
        "targets": TARGETS,
        "validation_summary": split_metrics,
        "validation_coverage": validation_coverage,
        "thresholds": thresholds,
    }
    _write(model_card_path, model_card)

    validation_receipt = {
        "schema_version": "ml-surrogate-validation-receipt.v1",
        "generated_at": generated_at,
        "status": "incomplete" if configured_criteria_pass else "fail",
        "validation_pass": validation_pass,
        "validation_coverage": validation_coverage,
        "validation_scope": "member_group_research_only",
        "promotion_eligible": False,
        "split_metrics": split_metrics,
        "thresholds": thresholds,
        "uncertainty_contract": {
            "method": "holdout_abs_error_quantile",
            "p95_error_targets": split_metrics["test"]["p95_abs_error"],
            "confidence_label": "member_group_research_only" if validation_pass else "insufficient",
        },
    }
    _write(validation_path, validation_receipt)

    ood_gate = {
        "schema_version": "ml-surrogate-ood-gate.v1",
        "generated_at": generated_at,
        "status": "pass" if ood_pass else "fail",
        "ood_pass": ood_pass,
        "method": "train_feature_min_max_with_10pct_tolerance",
        "checked_row_count": int(group_ids.shape[0]),
        "ood_row_count": len(ood_rows),
        "ood_rows_head": ood_rows[:20],
        "unsupported_or_ood_behavior": "solver_only_engineer_review_required",
    }
    _write(ood_path, ood_gate)

    fallback_receipt = {
        "schema_version": "ml-surrogate-solver-fallback-receipt.v1",
        "generated_at": generated_at,
        "status": "required_unverified",
        "solver_fallback_verified": False,
        "verification_scope": "policy_only_no_solver_or_code_check_executed",
        "fallback_required_before_final_promotion": True,
        "hard_gate_bypass_prevented": False,
        "required_final_promotion_gates": [
            "solver_replay_passed",
            "code_check_replay_passed",
            "human_review_recorded",
        ],
    }
    _write(fallback_path, fallback_receipt)

    manifest = {
        "schema_version": "ml-surrogate-checkpoint-manifest.v1",
        "generated_at": generated_at,
        "status": "research_only",
        "promotion_eligible": False,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "checkpoint_payload_sha256": checkpoint_payload["checkpoint_payload_sha256"],
        "dataset_card_path": str(dataset_card_path),
        "model_card_path": str(model_card_path),
        "validation_receipt_path": str(validation_path),
        "ood_gate_path": str(ood_path),
        "solver_fallback_receipt_path": str(fallback_path),
        "validation_pass": validation_pass,
        "validation_coverage": validation_coverage,
        "ood_pass": ood_pass,
        "solver_fallback_verified": False,
        "production_activation_mode": "shadow_with_solver_fallback",
        "claim": "Research member-group holdout only; project/geometry/load-history isolation is unverified and production activation is disabled.",
    }
    _write(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-npz", type=Path, default=DEFAULT_STATE_NPZ)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_ml_surrogate_checkpoint(
        state_npz=args.state_npz,
        checkpoint_dir=args.checkpoint_dir,
        productization_dir=args.productization_dir,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "ml_surrogate_checkpoint_manifest.json")
    print(
        "ml-surrogate-checkpoint: "
        f"status={payload['status']} validation={payload['validation_pass']} "
        f"ood={payload['ood_pass']} -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
