from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_g1_true_newton_load_sweep_status.py"
SPEC = importlib.util.spec_from_file_location(
    "build_g1_true_newton_load_sweep_status", SCRIPT_PATH
)
assert SPEC is not None
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _fake_candidate(*, load_scale: float, **_: object) -> dict:
    final = 537.1799036113136 if load_scale < 1.0 else 716.2398790963002
    initial = 14000.0 if load_scale < 1.0 else 20000.0
    return {
        "schema_version": "g1-true-newton-reference-candidate.v1",
        "status": "ready",
        "reason_code": "max_steps",
        "uses_real_mgt_model": True,
        "load_scale": load_scale,
        "true_newton_candidate": {
            "steps": 4,
            "initial_residual_n": initial,
            "final_residual_n": final,
            "total_reduction_ratio": (initial - final) / initial,
            "monotonic_residual_decrease": True,
            "residual_gate_passed": False,
            "stop_reason": "max_steps",
        },
        "modified_newton_baseline": {
            "final_residual_n": final + 0.01,
        },
        "true_newton_faster_than_modified": True,
    }


def test_true_newton_load_sweep_records_full_load_descent_without_promotion(
    monkeypatch,
) -> None:
    monkeypatch.setattr(module, "run_g1_true_newton_reference_candidate", _fake_candidate)

    payload = module.build_g1_true_newton_load_sweep_status(
        repo_root=REPO_ROOT,
        load_scales=(0.75, 1.0),
        max_newton_steps=4,
    )

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["promotes_g1_closure"] is False
    assert payload["max_attempted_load_scale"] == 1.0
    assert payload["full_load_attempted"] is True
    assert payload["full_load_true_newton_residual_descent_observed"] is True
    assert payload["full_load_true_newton_residual_gate_passed"] is False
    assert payload["full_load_true_newton_final_residual_n"] == 716.2398790963002
    assert payload["rows"][1]["load_scale"] == 1.0
    assert payload["rows"][1]["true_newton_residual_descent_observed"] is True
    assert "full_load_true_newton_residual_gate_not_passed" in payload["blockers"]
    assert "production_rocm_hip_not_executed_by_true_newton_sweep" in payload[
        "blockers"
    ]
    assert "not a G1 closure" in payload["claim_boundary"]


def test_true_newton_load_sweep_writes_json_and_markdown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module, "run_g1_true_newton_reference_candidate", _fake_candidate)
    out = tmp_path / "sweep.json"
    out_md = tmp_path / "sweep.md"

    payload = module.write_g1_true_newton_load_sweep_status(
        repo_root=REPO_ROOT,
        out=out,
        out_md=out_md,
        load_scales=(0.75, 1.0),
    )

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["schema_version"] == module.SCHEMA_VERSION
    assert saved["summary_line"] == payload["summary_line"]
    markdown = out_md.read_text(encoding="utf-8")
    assert "# G1 True-Newton Load Sweep Status" in markdown
    assert "716.2398790963002" in markdown
    assert "full_load_checkpoint_not_created_by_true_newton_sweep" in markdown
