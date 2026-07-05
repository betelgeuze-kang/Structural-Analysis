"""Hermetic tests for the repeated scaled-LSMR chain probe."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


PHASE1 = Path(__file__).resolve().parents[1] / "implementation" / "phase1"


def _load(module_name: str):
    if str(PHASE1) not in sys.path:
        sys.path.insert(0, str(PHASE1))
    path = PHASE1 / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _step(before: float, after: float, path: str) -> dict:
    return {
        "status": "ready",
        "reason_code": "PASS",
        "promotes_g1_closure": False,
        "line_search_preview": {
            "status": "ready",
            "accepted_alpha": 1.0,
            "residual_before_n": before,
            "residual_after_n": after,
            "residual_reduction_ratio": (before - after) / before,
        },
        "output_final_checkpoint": {
            "written": True,
            "path": path,
            "direct_residual_inf_n": after,
            "residual_gate_passed": False,
            "promotes_g1_closure": False,
        },
    }


def test_summarize_chain_ready_non_promoting():
    chain = _load("run_g1_mgt_sparse_direct_scaled_lsmr_chain_probe")
    payload = chain.summarize_chain(
        step_payloads=[
            _step(3.0, 2.0, "step1.npz"),
            _step(2.0, 1.5, "step2.npz"),
            _step(1.5, 1.0, "step3.npz"),
        ],
        initial_checkpoint=Path("initial.npz"),
        max_steps=3,
        residual_gate_n=0.5,
    )

    assert payload["schema_version"] == chain.SCHEMA_VERSION
    assert payload["status"] == "ready"
    assert payload["step_count"] == 3
    assert payload["ready_step_count"] == 3
    assert payload["checkpoint_written_step_count"] == 3
    assert payload["monotonic_residual_descent"] is True
    assert payload["initial_residual_n"] == 3.0
    assert payload["final_residual_n"] == 1.0
    assert payload["residual_gate_n"] == 0.5
    assert payload["final_residual_gate_passed"] is False
    assert payload["final_residual_gate_gap_n"] == 0.5
    assert payload["final_residual_over_gate"] == 2.0
    assert payload["gate_convergence_assessment"] == "descent_but_gate_not_closed"
    assert payload["recommended_next_action"] == (
        "continue_scaled_lsmr_chain_or_compare_operator_variant"
    )
    assert payload["total_reduction_n"] == 2.0
    assert payload["last_step_reduction_n"] == 0.5
    assert payload["mean_step_reduction_n"] == 2.0 / 3.0
    assert payload["latest_checkpoint_path"] == "step3.npz"
    assert payload["promotes_g1_closure"] is False


def test_summarize_chain_review_when_step_does_not_descend():
    chain = _load("run_g1_mgt_sparse_direct_scaled_lsmr_chain_probe")
    payload = chain.summarize_chain(
        step_payloads=[
            _step(3.0, 2.0, "step1.npz"),
            _step(2.0, 2.5, "step2.npz"),
        ],
        initial_checkpoint=Path("initial.npz"),
        max_steps=2,
    )

    assert payload["status"] == "review"
    assert payload["reason_code"] == "CHAIN_NOT_FULLY_READY"
    assert payload["monotonic_residual_descent"] is False
    assert payload["promotes_g1_closure"] is False


def test_summarize_chain_marks_gate_stall_when_step_count_is_huge():
    chain = _load("run_g1_mgt_sparse_direct_scaled_lsmr_chain_probe")
    payload = chain.summarize_chain(
        step_payloads=[
            _step(10.0, 9.999, "step1.npz"),
            _step(9.999, 9.998, "step2.npz"),
        ],
        initial_checkpoint=Path("initial.npz"),
        max_steps=2,
        residual_gate_n=1.0,
    )

    assert payload["status"] == "ready"
    assert payload["monotonic_residual_descent"] is True
    assert payload["estimated_steps_to_gate_at_last_reduction"] > 1000
    assert payload["gate_convergence_assessment"] == "stalled_for_gate"
    assert payload["recommended_next_action"] == (
        "switch_operator_preconditioner_or_tangent_model_before_extending_scaled_lsmr_chain"
    )


def test_run_chain_probe_threads_opt_in_jvp_eps(tmp_path, monkeypatch):
    chain = _load("run_g1_mgt_sparse_direct_scaled_lsmr_chain_probe")
    seen: list[float] = []

    def fake_smoke(**kwargs):
        seen.append(kwargs["jvp_eps"])
        step = len(seen)
        return _step(
            before=1.0 - 0.1 * (step - 1),
            after=0.9 - 0.1 * (step - 1),
            path=str(tmp_path / f"step{step}.npz"),
        )

    monkeypatch.setattr(
        chain,
        "run_g1_mgt_sparse_direct_physical_line_search_smoke",
        fake_smoke,
    )

    payload = chain.run_chain_probe(
        mgt_model=tmp_path / "fake.mgt",
        initial_checkpoint_npz=tmp_path / "initial.npz",
        max_steps=2,
        gmres_maxiter=8,
        jvp_eps=1.0e-3,
        output_json=tmp_path / "chain.json",
        step_prefix=tmp_path / "chain_step",
    )

    assert seen == [1.0e-3, 1.0e-3]
    assert payload["jvp_eps"] == 1.0e-3
    assert payload["step_count"] == 2
    assert payload["promotes_g1_closure"] is False
