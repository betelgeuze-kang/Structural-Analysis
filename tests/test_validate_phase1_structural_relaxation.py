from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/validate_phase1_artifacts.py"
    )
    spec = importlib.util.spec_from_file_location(
        "validate_phase1_artifacts_for_structural_relaxation_tests",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_structural_relaxation_validator_accepts_three_lane_report() -> None:
    module = _load_module()
    report = {
        "summary": {
            "all_converged": True,
            "within_5pct_variability": True,
            "models_used": ["three_lane_frame_soa"],
        },
        "runs": [
            {"model": "three_lane_frame_soa", "converged": True},
            {"model": "three_lane_frame_soa", "converged": True},
        ],
    }

    assert module.validate_structural_relaxation(report) == []


def test_structural_relaxation_validator_rejects_non_structural_model() -> None:
    module = _load_module()
    report = {
        "summary": {
            "all_converged": True,
            "within_5pct_variability": True,
            "models_used": ["retired_non_structural_model"],
        },
        "runs": [{"model": "retired_non_structural_model", "converged": True}],
    }

    assert module.validate_structural_relaxation(report) == [
        "structural_relaxation.models_used invalid",
        "structural_relaxation.run_model invalid",
    ]
