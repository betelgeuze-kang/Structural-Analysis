from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_direct_residual_adaptive_preconditioned_global_newton as adaptive  # noqa: E402


def test_adaptive_global_newton_child_timeout_writes_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"
    checkpoint_npz = tmp_path / "frontier.npz"

    def timeout_run(command, **kwargs):
        raise adaptive.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output="partial stdout",
            stderr="partial stderr",
        )

    def load_checkpoint(_checkpoint_npz: Path):
        return {"residual_inf_n": 1.23}, np.zeros(1), None, None

    monkeypatch.setattr(adaptive.subprocess, "run", timeout_run)
    monkeypatch.setattr(adaptive, "_load_checkpoint", load_checkpoint)

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=checkpoint_npz,
        output_json=output_json,
        output_final_checkpoint_npz=tmp_path / "final.npz",
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=0.01,
        apply_shell_material_tangent=True,
        compact_output_final_checkpoint=True,
        residual_tolerance_n=5.0e-4,
        relative_increment_tolerance=1.0e-4,
    )

    controller = payload["controller"]
    assert controller["stop_reason"] == "child_timeout_seconds_exceeded"
    assert controller["child_timeout_seconds"] == 0.01
    assert controller["apply_shell_material_tangent"] is True
    assert controller["compact_output_final_checkpoint"] is True
    assert controller["runtime_budget_exceeded"] is True
    assert payload["final_direct_residual_inf_n"] == 1.23

    row = payload["rows"][0]
    assert row["status"] == "timeout"
    assert row["subprocess_timeout"] is True
    assert row["base_direct_residual_inf_n"] == 1.23
    assert row["subprocess_stdout"] == "partial stdout"
    assert row["subprocess_stderr"] == "partial stderr"
    assert "--allow-cpu-diagnostic" in row["subprocess_command"]
    assert "--apply-shell-material-tangent" in row["subprocess_command"]
    assert "--compact-output-final-checkpoint" in row["subprocess_command"]
    assert "--enable-matrix-free-global-krylov" in row["subprocess_command"]
    assert "--matrix-free-global-krylov-preconditioner-input-scale" in row[
        "subprocess_command"
    ]
    assert row["preconditioner_input_scale"] == 1.0

    child_receipt = json.loads(Path(row["child_receipt_path"]).read_text())
    assert child_receipt["status"] == "timeout"
    assert child_receipt["preconditioner_input_scale"] == 1.0
    assert child_receipt["apply_shell_material_tangent"] is True
    assert child_receipt["output_final_checkpoint_written"] is False
    assert child_receipt["matrix_free_global_krylov"]["stop_reason"] == (
        "child_timeout_seconds_exceeded"
    )
    assert child_receipt["base_direct_residual"]["direct_residual_inf_n"] == 1.23
    assert not Path(row["child_checkpoint_path"]).exists()


def test_adaptive_global_newton_child_subprocess_reads_completed_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"

    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "base_direct_residual": {
                        "direct_residual_inf_n": 2.0,
                    },
                    "final_direct_residual": {
                        "direct_residual_inf_n": 1.0,
                    },
                    "matrix_free_global_krylov": {
                        "accepted": True,
                        "stop_reason": "candidate_accepted",
                        "best_candidate": {
                            "direct_residual_inf_n": 1.0,
                            "relative_improvement": 0.5,
                            "alpha": 1.0,
                            "alpha_source": "line_search",
                            "relative_increment_gate_passed": True,
                            "residual_gate_passed": False,
                        },
                        "matvec_count": 1,
                        "preconditioner_solve_count": 1,
                        "preconditioner_regularization": 1.0e-6,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return adaptive.subprocess.CompletedProcess(
            command,
            0,
            stdout="completed stdout",
            stderr="",
        )

    monkeypatch.setattr(adaptive.subprocess, "run", completed_run)

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=output_json,
        output_final_checkpoint_npz=tmp_path / "final.npz",
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_alpha_values=(1.0,),
        matrix_free_global_krylov_preconditioner_input_scales=(0.5, 2.0),
        matrix_free_global_krylov_min_relative_improvement=1.0e-6,
        child_timeout_seconds=0.01,
    )

    row = payload["rows"][0]
    assert row["subprocess_timeout"] is False
    assert row["subprocess_returncode"] == 0
    assert row["subprocess_stdout"] == "completed stdout"
    assert row["accepted"] is True
    assert row["preconditioner_input_scale"] == 0.5
    assert payload["controller"][
        "matrix_free_global_krylov_preconditioner_input_scales"
    ] == [0.5, 2.0]
    assert payload["promoted_rows"] == [row]
    assert payload["final_direct_residual_inf_n"] == 1.0
    assert payload["controller"]["stop_reason"] == "max_controller_steps_reached"
