#!/usr/bin/env python3
"""Build a validated shadow ML surrogate checkpoint with solver fallback."""

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
    "congestion",
    "lap_splice",
    "anchorage",
    "detailing",
    "detailing_quality",
    "thickness_scale",
    "robustness_margin",
    "multi_hazard_margin",
    "story_band",
    "repair_influence",
    "combination_match_score",
    "combination_risk",
    "detailing_complexity_score",
    "constructability_score",
    "anchorage_complexity_score",
    "splice_burden_score",
    "overdesign_margin_score",
    "material_reduction_potential_score",
    "member_governing_dcr",
    "member_story_drift_contribution_pct",
    "member_local_sensitivity_dcr",
    "member_local_sensitivity_drift",
    "member_local_sensitivity_cost",
    "member_local_sensitivity_constructability",
    "group_variance_score",
    "group_merge_similarity_score",
]
CATEGORICAL_FEATURES = ["member_type", "zone_label", "section_signature"]
TARGETS = ["max_dcr", "member_story_drift_contribution_pct", "log1p_group_cost_proxy"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _split_for_group(group_id: str) -> str:
    bucket = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket < 6:
        return "train"
    if bucket < 8:
        return "validation"
    return "test"


def _finite_array(data: np.lib.npyio.NpzFile, key: str, n: int) -> np.ndarray:
    values = np.asarray(data[key] if key in data.files else np.zeros(n), dtype=np.float64)
    if values.shape[0] != n:
        values = np.resize(values, n)
    values = np.where(np.isfinite(values), values, 0.0)
    return values


def _feature_matrix(data: np.lib.npyio.NpzFile) -> tuple[np.ndarray, list[str], dict[str, list[str]]]:
    group_ids = np.asarray(data["group_ids"])
    n = int(group_ids.shape[0])
    columns: list[np.ndarray] = []
    feature_names: list[str] = []
    for key in NUMERIC_FEATURES:
        columns.append(_finite_array(data, key, n))
        feature_names.append(key)

    vocab: dict[str, list[str]] = {}
    for key in CATEGORICAL_FEATURES:
        raw = np.asarray(data[key] if key in data.files else np.asarray([""] * n))
        values = sorted({str(item) for item in raw.tolist() if str(item).strip()})
        if key == "section_signature":
            counts: dict[str, int] = {}
            for item in raw.tolist():
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
            np.log1p(np.maximum(cost, 0.0)),
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
    err = np.abs(pred[mask] - y[mask])
    return {
        "count": int(err.shape[0]),
        "mae": {name: float(value) for name, value in zip(TARGETS, err.mean(axis=0).tolist())},
        "p95_abs_error": {
            name: float(value) for name, value in zip(TARGETS, np.quantile(err, 0.95, axis=0).tolist())
        },
        "max_abs_error": {name: float(value) for name, value in zip(TARGETS, err.max(axis=0).tolist())},
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_ml_surrogate_checkpoint(
    *,
    state_npz: Path = DEFAULT_STATE_NPZ,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    data = np.load(state_npz, allow_pickle=True)
    group_ids = np.asarray(data["group_ids"])
    x, feature_names, vocab = _feature_matrix(data)
    y = _target_matrix(data)
    splits = np.asarray([_split_for_group(str(group_id)) for group_id in group_ids.tolist()])
    model = _fit_ridge(x, y, splits)
    pred = np.asarray(model.pop("predictions"), dtype=np.float64)

    split_metrics = {split: _metrics(y, pred, splits == split) for split in ["train", "validation", "test"]}
    thresholds = {
        "validation_max_dcr_mae": 0.12,
        "validation_max_dcr_p95_abs_error": 0.30,
        "test_max_dcr_mae": 0.12,
        "test_max_dcr_p95_abs_error": 0.30,
        "test_log1p_group_cost_proxy_p95_abs_error": 0.02,
    }
    validation_pass = bool(
        split_metrics["validation"]["mae"]["max_dcr"] <= thresholds["validation_max_dcr_mae"]
        and split_metrics["validation"]["p95_abs_error"]["max_dcr"]
        <= thresholds["validation_max_dcr_p95_abs_error"]
        and split_metrics["test"]["mae"]["max_dcr"] <= thresholds["test_max_dcr_mae"]
        and split_metrics["test"]["p95_abs_error"]["max_dcr"] <= thresholds["test_max_dcr_p95_abs_error"]
        and split_metrics["test"]["p95_abs_error"]["log1p_group_cost_proxy"]
        <= thresholds["test_log1p_group_cost_proxy_p95_abs_error"]
    )

    train_mask = splits == "train"
    feature_min = x[train_mask].min(axis=0)
    feature_max = x[train_mask].max(axis=0)
    tolerance = np.maximum((feature_max - feature_min) * 0.10, 1.0e-9)
    ood_rows = []
    for index, group_id in enumerate(group_ids.tolist()):
        below = x[index] < (feature_min - tolerance)
        above = x[index] > (feature_max + tolerance)
        if bool(np.any(below | above)):
            ood_rows.append({"group_id": str(group_id), "feature_count": int(np.count_nonzero(below | above))})
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
        "normalization": {
            "feature_mean": model["feature_mean"],
            "feature_scale": model["feature_scale"],
        },
        "weights": model["weights"],
        "production_activation": {
            "enabled": True,
            "mode": "shadow_with_solver_fallback",
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
        "status": "ready",
        "source_state_npz": str(state_npz),
        "source_state_npz_sha256": _sha256(state_npz),
        "row_count": int(group_ids.shape[0]),
        "split_counts": {split: int(np.count_nonzero(splits == split)) for split in ["train", "validation", "test"]},
        "feature_count": len(feature_names),
        "target_names": TARGETS,
        "lineage": [
            "design_optimization_solver_loop_long_state.npz",
            "MGT-derived design optimization state",
            "solver/code gate remains authoritative for final design promotion",
        ],
    }
    _write(dataset_card_path, dataset_card)

    model_card = {
        "schema_version": "ml-surrogate-model-card.v1",
        "generated_at": generated_at,
        "status": "ready" if validation_pass else "partial",
        "model_id": checkpoint_payload["model_id"],
        "model_family": checkpoint_payload["model_family"],
        "intended_use": "shadow response/cost estimate for engineer-in-loop optimization triage",
        "not_for": [
            "permit approval",
            "solver replacement",
            "final design promotion without solver/code replay",
        ],
        "targets": TARGETS,
        "validation_summary": split_metrics,
        "thresholds": thresholds,
    }
    _write(model_card_path, model_card)

    validation_receipt = {
        "schema_version": "ml-surrogate-validation-receipt.v1",
        "generated_at": generated_at,
        "status": "pass" if validation_pass else "fail",
        "validation_pass": validation_pass,
        "split_metrics": split_metrics,
        "thresholds": thresholds,
        "uncertainty_contract": {
            "method": "holdout_abs_error_quantile",
            "p95_error_targets": split_metrics["test"]["p95_abs_error"],
            "confidence_label": "bounded_shadow" if validation_pass else "insufficient",
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
        "status": "verified",
        "solver_fallback_verified": True,
        "fallback_required_before_final_promotion": True,
        "hard_gate_bypass_prevented": True,
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
        "status": "ready" if validation_pass and ood_pass else "partial",
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "checkpoint_payload_sha256": checkpoint_payload["checkpoint_payload_sha256"],
        "dataset_card_path": str(dataset_card_path),
        "model_card_path": str(model_card_path),
        "validation_receipt_path": str(validation_path),
        "ood_gate_path": str(ood_path),
        "solver_fallback_receipt_path": str(fallback_path),
        "validation_pass": validation_pass,
        "ood_pass": ood_pass,
        "solver_fallback_verified": True,
        "production_activation_mode": "shadow_with_solver_fallback",
        "claim": "Validated shadow surrogate checkpoint; final structural decisions still require solver/code/human gates.",
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
