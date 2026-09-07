"""Tests for the validated shadow ML surrogate checkpoint."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
sys.path.insert(0, str(REPO_ROOT / "implementation/phase1"))

from build_ml_surrogate_checkpoint import (  # noqa: E402
    _feature_matrix,
    _json_sha,
    _split_for_group,
    _write,
    build_ml_surrogate_checkpoint,
)
from ml_surrogate_production_gate import probe_ml_surrogate_production_gate  # noqa: E402


def _state_arrays(row_count: int = 60) -> dict[str, np.ndarray]:
    return {
        "group_ids": np.asarray([f"clean-checkout-group-{index:03d}" for index in range(row_count)], dtype=str),
        "rebar_ratio": np.full(row_count, 0.02),
        "thickness_scale": np.ones(row_count),
        "story_band": np.ones(row_count, dtype=np.int64),
        "member_type": np.full(row_count, "column"),
        "zone_label": np.full(row_count, "core"),
        "section_signature": np.full(row_count, "rect-400x400"),
        "max_dcr": np.full(row_count, 0.8),
        "member_story_drift_contribution_pct": np.full(row_count, 0.05),
        "group_cost_proxy": np.full(row_count, 1_000.0),
    }


def _build_temp_checkpoint(tmp_path: Path) -> tuple[dict[str, object], Path]:
    state_npz = tmp_path / "design_optimization_state.npz"
    checkpoint_dir = tmp_path / "checkpoint"
    productization_dir = tmp_path / "productization"
    np.savez_compressed(state_npz, **_state_arrays())

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ml_surrogate_checkpoint.py"),
            "--state-npz",
            str(state_npz),
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--productization-dir",
            str(productization_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    manifest = json.loads(
        (productization_dir / "ml_surrogate_checkpoint_manifest.json").read_text(encoding="utf-8")
    )
    return manifest, productization_dir


def test_build_ml_surrogate_checkpoint_current_lane(tmp_path: Path) -> None:
    manifest, _productization_dir = _build_temp_checkpoint(tmp_path)
    assert manifest["schema_version"] == "ml-surrogate-checkpoint-manifest.v1"
    assert manifest["status"] == "research_only"
    assert manifest["promotion_eligible"] is False
    assert manifest["validation_pass"] is False
    assert manifest["validation_coverage"]["configured_criteria_pass"] is True
    assert manifest["validation_coverage"]["unassessed_targets"] == ["member_story_drift_contribution_pct"]
    assert manifest["ood_pass"] is True
    assert manifest["solver_fallback_verified"] is False
    checkpoint = json.loads(Path(manifest["checkpoint_path"]).read_text(encoding="utf-8"))
    assert checkpoint["production_activation"]["enabled"] is False
    assert checkpoint["dataset_contract"]["split_policy"][
        "project_geometry_load_history_isolation_verified"
    ] is False

    for key in [
        "dataset_card_path",
        "model_card_path",
        "validation_receipt_path",
        "ood_gate_path",
        "solver_fallback_receipt_path",
    ]:
        assert Path(manifest[key]).is_file()
        json.dumps(json.loads(Path(manifest[key]).read_text(encoding="utf-8")), allow_nan=False)
    receipt = json.loads(Path(manifest["validation_receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["status"] == "incomplete"
    fallback = json.loads(Path(manifest["solver_fallback_receipt_path"]).read_text(encoding="utf-8"))
    assert fallback["status"] == "required_unverified"
    assert fallback["verification_scope"] == "policy_only_no_solver_or_code_check_executed"
    assert fallback["hard_gate_bypass_prevented"] is False
    json.dumps(checkpoint, allow_nan=False)


def test_member_holdout_cannot_promote_production_status_or_contracts(tmp_path: Path) -> None:
    manifest, productization_dir = _build_temp_checkpoint(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_ml_multi_objective_status.py"),
            "--output-json",
            str(productization_dir / "ml_multi_objective_status.json"),
            "--pareto-archive-json",
            str(PRODUCTIZATION / "optimization_pareto_research_archive.json"),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PHASE1_ML_SURROGATE_OPT_IN": "1",
            "PHASE1_ML_SURROGATE_CHECKPOINT": str(manifest["checkpoint_path"]),
        },
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    status = json.loads(
        (productization_dir / "ml_multi_objective_status.json").read_text(encoding="utf-8")
    )
    gate = status["ml_surrogate_production_gate"]
    assert status["status"] != "production_shadow_solver_gated_ready"
    assert status["production_ml_wired"] is False
    assert gate["checkpoint_validated"] is False
    assert gate["blockers"] == ["project_geometry_load_history_validation_not_implemented"]
    assert gate["hard_gate_bypass_prevented"] is False

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_engine_productization_contracts.py"),
            "--productization-dir",
            str(productization_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    contracts = json.loads(
        (productization_dir / "ai_engine_productization_contracts.json").read_text(encoding="utf-8")
    )
    inference = json.loads(
        (productization_dir / "ai_inference_runtime_receipt.json").read_text(encoding="utf-8")
    )
    assert contracts["status"] != "production_ai_ready"
    assert inference["status"] != "ready"


@pytest.mark.parametrize("field", ["rebar_ratio", "member_type", "max_dcr", "group_ids"])
def test_missing_required_input_rejected_without_artifacts(tmp_path: Path, field: str) -> None:
    arrays = _state_arrays()
    arrays.pop(field)
    _assert_invalid_state(tmp_path, arrays, f"dataset_missing_field:{field}")


def _assert_invalid_state(tmp_path: Path, arrays: dict[str, np.ndarray], error: str) -> None:
    state = tmp_path / "invalid.npz"
    np.savez_compressed(state, **arrays)
    with pytest.raises(ValueError, match=error):
        build_ml_surrogate_checkpoint(
            state_npz=state,
            checkpoint_dir=tmp_path / "checkpoint",
            productization_dir=tmp_path / "productization",
        )
    assert not (tmp_path / "checkpoint").exists()
    assert not (tmp_path / "productization").exists()


@pytest.mark.parametrize("field", ["rebar_ratio", "max_dcr", "member_story_drift_contribution_pct", "group_cost_proxy"])
@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_non_finite_input_is_not_imputed(tmp_path: Path, field: str, invalid: float) -> None:
    arrays = _state_arrays()
    arrays[field][0] = invalid
    _assert_invalid_state(tmp_path, arrays, f"dataset_non_finite_field:{field}")


def test_finite_holdout_values_that_overflow_metrics_are_rejected(tmp_path: Path) -> None:
    arrays = _state_arrays()
    holdout = np.asarray([_split_for_group(group) != "train" for group in arrays["group_ids"]])
    arrays["member_story_drift_contribution_pct"][holdout] = 1.0e308
    _assert_invalid_state(tmp_path, arrays, "dataset_non_finite_metrics")


def test_finite_features_that_overflow_fit_are_rejected(tmp_path: Path) -> None:
    arrays = _state_arrays()
    arrays["thickness_scale"][:] = 1.0e308
    _assert_invalid_state(tmp_path, arrays, "dataset_non_finite_or_unsolvable_fit")


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_non_finite_values_cannot_be_serialized_or_hashed(tmp_path: Path, invalid: float) -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        _json_sha({"metric": invalid})
    with pytest.raises(ValueError, match="Out of range float"):
        _write(tmp_path / "nested" / "bad.json", {"metric": invalid})
    assert not (tmp_path / "nested").exists()


@pytest.mark.parametrize("field", ["rebar_ratio", "thickness_scale", "story_band", "max_dcr", "member_story_drift_contribution_pct"])
def test_negative_design_values_and_targets_are_rejected(tmp_path: Path, field: str) -> None:
    arrays = _state_arrays()
    arrays[field][0] = -1
    _assert_invalid_state(tmp_path, arrays, f"dataset_negative_field:{field}")


@pytest.mark.parametrize("field,value", [("rebar_ratio", 1.1), ("thickness_scale", 0.0), ("story_band", 1.5)])
def test_invalid_design_domains_are_rejected(tmp_path: Path, field: str, value: float) -> None:
    arrays = _state_arrays()
    arrays[field] = arrays[field].astype(np.float64)
    arrays[field][0] = value
    _assert_invalid_state(tmp_path, arrays, f"dataset_domain_violation:{field}")


@pytest.mark.parametrize("field", ["rebar_ratio", "member_type", "max_dcr"])
@pytest.mark.parametrize("shape", [(59,), (60, 1), ()])
def test_shapes_are_rejected_instead_of_resized(tmp_path: Path, field: str, shape: tuple[int, ...]) -> None:
    arrays = _state_arrays()
    arrays[field] = np.full(shape, arrays[field][0])
    _assert_invalid_state(tmp_path, arrays, f"dataset_shape_mismatch:{field}")


@pytest.mark.parametrize(
    ("field", "values", "error"),
    [
        ("max_dcr", np.full(60, "0.8"), "dataset_non_numeric_field:max_dcr"),
        ("member_type", np.ones(60), "dataset_non_text_field:member_type"),
        ("member_type", np.full(60, ""), "dataset_empty_or_untrimmed_field:member_type"),
        ("group_ids", np.full(60, "same-id"), "dataset_duplicate_group_id"),
        ("group_cost_proxy", np.full(60, -1.0), "dataset_negative_cost:group_cost_proxy"),
        ("rebar_ratio", np.full(60, object()), "dataset_unsupported_dtype:rebar_ratio"),
    ],
)
def test_invalid_values_are_not_silently_coerced(
    tmp_path: Path, field: str, values: np.ndarray, error: str,
) -> None:
    arrays = _state_arrays()
    arrays[field] = values
    _assert_invalid_state(tmp_path, arrays, error)


@pytest.mark.parametrize("row_count,error", [(0, "dataset_empty_rows"), (1, "dataset_empty_split")])
def test_empty_rows_or_holdout_rejected(tmp_path: Path, row_count: int, error: str) -> None:
    _assert_invalid_state(tmp_path, _state_arrays(row_count), error)


def test_response_targets_and_derivatives_cannot_change_features(tmp_path: Path) -> None:
    arrays = _state_arrays()
    split = np.asarray([_split_for_group(item) for item in arrays["group_ids"]])
    before = tmp_path / "before.npz"
    after = tmp_path / "after.npz"
    np.savez_compressed(before, **arrays)
    for key in [
        "max_dcr", "member_story_drift_contribution_pct", "group_cost_proxy",
        "member_governing_dcr", "member_local_sensitivity_drift", "robustness_margin",
        "overdesign_margin_score", "material_reduction_potential_score",
    ]:
        arrays[key] = np.arange(60, dtype=np.float64)
    np.savez_compressed(after, **arrays)
    with np.load(before, allow_pickle=False) as initial, np.load(after, allow_pickle=False) as altered:
        original_features, names, _ = _feature_matrix(initial, split)
        changed_features, changed_names, _ = _feature_matrix(altered, split)
    np.testing.assert_array_equal(original_features, changed_features)
    assert names == changed_names
    assert all(name.split("=", 1)[0] in {
        "rebar_ratio", "thickness_scale", "story_band", "member_type", "zone_label", "section_signature",
    } for name in names)


def test_holdout_only_category_does_not_fit_vocabulary_and_is_ood(tmp_path: Path) -> None:
    arrays = _state_arrays()
    index = next(i for i, group in enumerate(arrays["group_ids"]) if _split_for_group(group) == "test")
    arrays["section_signature"][index] = "unseen"
    state = tmp_path / "state.npz"
    np.savez_compressed(state, **arrays)
    manifest = build_ml_surrogate_checkpoint(
        state_npz=state, checkpoint_dir=tmp_path / "checkpoint", productization_dir=tmp_path / "productization",
    )
    checkpoint = json.loads(Path(manifest["checkpoint_path"]).read_text(encoding="utf-8"))
    assert "unseen" not in checkpoint["categorical_vocabulary"]["section_signature"]
    assert manifest["ood_pass"] is False
    ood = json.loads(Path(manifest["ood_gate_path"]).read_text(encoding="utf-8"))
    assert ood["ood_rows_head"] == [{"group_id": arrays["group_ids"][index], "feature_count": 2}]


@pytest.mark.parametrize("legacy", [False, True])
def test_opt_in_and_self_declared_cards_cannot_bypass_missing_provenance_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy: bool,
) -> None:
    manifest, _ = _build_temp_checkpoint(tmp_path)
    checkpoint_path = Path(manifest["checkpoint_path"])
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["production_activation"]["enabled"] = True
    if legacy:
        checkpoint.pop("dataset_contract")
    else:
        checkpoint["dataset_contract"]["split_policy"]["project_geometry_load_history_isolation_verified"] = True
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    for name in ["dataset_card", "model_card"]:
        path = Path(checkpoint["artifacts"][name])
        card = json.loads(path.read_text(encoding="utf-8"))
        card["status"] = "ready"
        path.write_text(json.dumps(card), encoding="utf-8")
    for name, overrides in [
        ("validation_receipt", {"status": "pass", "validation_pass": True}),
        ("solver_fallback_receipt", {
            "status": "verified", "solver_fallback_verified": True, "hard_gate_bypass_prevented": True,
        }),
    ]:
        path = Path(checkpoint["artifacts"][name])
        receipt = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**receipt, **overrides}), encoding="utf-8")
    monkeypatch.setenv("PHASE1_ML_SURROGATE_OPT_IN", "1")
    monkeypatch.delenv("PHASE1_ML_SURROGATE_DISABLE", raising=False)
    monkeypatch.setenv("PHASE1_ML_SURROGATE_CHECKPOINT", str(checkpoint_path))
    gate = probe_ml_surrogate_production_gate()
    assert all(gate[key] is True for key in [
        "activation_enabled", "dataset_card_ready", "model_card_ready", "validation_ready",
        "ood_gate_ready", "solver_fallback_ready", "hard_gate_bypass_prevented",
    ])
    assert gate["production_ml_wired"] is False
    assert gate["checkpoint_validated"] is False
    assert gate["blockers"] == [
        "legacy_dataset_contract_unverified" if legacy else "project_geometry_load_history_validation_not_implemented",
    ]
