from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_g1_true_newton_full_load_checkpoint_candidate_status.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_true_newton_full_load_checkpoint_candidate_status", SCRIPT_PATH
)
assert SPEC is not None
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _fake_candidate(**kwargs: object) -> dict:
    checkpoint = Path(kwargs["output_final_checkpoint_npz"])
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"fixture")
    return {
        "schema_version": "g1-true-newton-reference-candidate.v1",
        "status": "ready",
        "reason_code": "max_steps",
        "uses_real_mgt_model": True,
        "load_scale": kwargs.get("load_scale", 1.0),
        "true_newton_candidate": {
            "steps": kwargs.get("max_newton_steps", 12),
            "initial_residual_n": 22323.093943383923,
            "final_residual_n": 464.56223807569995,
            "total_reduction_ratio": 0.9791882547360113,
            "monotonic_residual_decrease": True,
            "residual_gate_passed": False,
            "stop_reason": "max_steps",
        },
        "output_final_checkpoint": {
            "written": True,
            "path": str(checkpoint),
            "schema": "mgt-direct-residual-newton-state.v1",
            "load_scale": 1.0,
            "dof_count": 12,
            "free_dof_count": 4,
            "direct_residual_inf_n": 464.56223807569995,
            "residual_gate_passed": False,
            "promotes_g1_closure": False,
        },
    }


def test_full_load_checkpoint_candidate_status_records_candidate_without_closure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(module, "run_g1_true_newton_reference_candidate", _fake_candidate)

    payload = module.build_g1_true_newton_full_load_checkpoint_candidate_status(
        repo_root=REPO_ROOT,
        checkpoint_npz=tmp_path / "candidate.npz",
        max_newton_steps=12,
    )

    assert payload["status"] == "candidate_created"
    assert payload["contract_pass"] is True
    assert payload["evidence_closure_pass"] is False
    assert payload["promotes_g1_closure"] is False
    assert payload["checkpoint_written"] is True
    assert payload["checkpoint_schema_pass"] is True
    assert payload["checkpoint_load_scale_pass"] is True
    assert payload["true_newton_candidate"]["final_residual_n"] == 464.56223807569995
    assert payload["full_load_true_newton_residual_descent_observed"] is True
    assert payload["full_load_true_newton_residual_gate_passed"] is False
    assert "full_load_true_newton_checkpoint_residual_gate_not_passed" in payload[
        "blockers"
    ]
    assert "not a G1 closure" in payload["claim_boundary"]


def test_full_load_checkpoint_candidate_status_writes_json_and_markdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(module, "run_g1_true_newton_reference_candidate", _fake_candidate)
    out = tmp_path / "status.json"
    out_md = tmp_path / "status.md"

    payload = module.write_g1_true_newton_full_load_checkpoint_candidate_status(
        repo_root=REPO_ROOT,
        checkpoint_npz=tmp_path / "candidate.npz",
        out=out,
        out_md=out_md,
    )

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["schema_version"] == module.SCHEMA_VERSION
    assert saved["summary_line"] == payload["summary_line"]
    markdown = out_md.read_text(encoding="utf-8")
    assert "# G1 True-Newton Full-Load Checkpoint Candidate Status" in markdown
    assert "464.56223807569995" in markdown
    assert "full_load_true_newton_checkpoint_residual_gate_not_passed" in markdown
