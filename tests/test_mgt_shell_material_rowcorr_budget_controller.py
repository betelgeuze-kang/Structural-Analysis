from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_shell_material_rowcorr_budget_controller as controller  # noqa: E402


def _write_seed(path: Path, final_residual: float = 14.0) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "partial",
                "base_direct_residual": {"direct_residual_inf_n": 18.0},
                "final_direct_residual": {
                    "direct_residual_inf_n": final_residual,
                    "residual_gate_passed": False,
                },
                "current_tangent_residual_row_correction": {
                    "accepted": True,
                    "promotion_count": 1,
                    "stop_reason": "max_promotions_exhausted",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_shell_material_rowcorr_budget_zero_launches_no_children(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("zero-budget controller must not launch a child")

    monkeypatch.setattr(controller.subprocess, "run", fail_run)

    payload = controller.run_shell_material_rowcorr_budget_controller(
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        output_final_checkpoint_npz=tmp_path / "not_written.npz",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_controller_runtime_seconds=0.0,
        child_timeout_seconds=1.0,
    )

    assert payload["controller"]["stop_reason"] == "runtime_budget_exceeded"
    assert payload["controller"]["runtime_budget_exceeded"] is True
    assert payload["controller"]["promotion_count"] == 0
    assert payload["rows"] == []
    assert payload["seed_probe"]["final_direct_residual_inf_n"] == 14.0
    assert payload["final_direct_residual_inf_n"] == 14.0
    assert payload["output_final_checkpoint_written"] is False
    assert not (tmp_path / "not_written.npz").exists()
    assert payload["initial_checkpoint_path"].endswith(
        "mgt_equilibrium_newton_focused_followup365_attached_regularized_direct_final_checkpoint.npz"
    )


def test_shell_material_rowcorr_budget_promotes_completed_child(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
                    "base_direct_residual": {"direct_residual_inf_n": 18.0},
                    "final_direct_residual": {
                        "direct_residual_inf_n": 13.0,
                        "residual_gate_passed": False,
                    },
                    "current_tangent_residual_row_correction": {
                        "accepted": True,
                        "promotion_count": 1,
                        "stop_reason": "max_promotions_exhausted",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return controller.subprocess.CompletedProcess(
            command,
            0,
            stdout="completed stdout",
            stderr="",
        )

    monkeypatch.setattr(controller.subprocess, "run", completed_run)

    final_checkpoint = tmp_path / "promoted.npz"
    payload = controller.run_shell_material_rowcorr_budget_controller(
        seed_probe_json=_write_seed(tmp_path / "seed.json", final_residual=14.0),
        output_json=tmp_path / "controller.json",
        output_final_checkpoint_npz=final_checkpoint,
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        row_target_counts=(1, 2),
        row_support_column_counts=(4,),
        row_alpha_values=(0.015625,),
        max_candidates=2,
        write_child_checkpoints=True,
        child_timeout_seconds=1.0,
    )

    row = payload["rows"][0]
    assert row["accepted"] is True
    assert row["target_row_count"] == 1
    assert row["support_column_count"] == 4
    assert row["frontier_improvement_inf_n"] == 1.0
    assert row["subprocess_stdout"] == "completed stdout"
    assert "--apply-shell-material-tangent" in row["subprocess_command"]
    assert "--compact-output-final-checkpoint" in row["subprocess_command"]
    assert "--enable-current-tangent-residual-row-correction" in row[
        "subprocess_command"
    ]
    assert payload["promoted_rows"] == [row]
    assert payload["controller"]["promotion_count"] == 1
    assert payload["controller"]["stop_reason"] == "candidate_promoted"
    assert payload["final_direct_residual_inf_n"] == 13.0
    assert final_checkpoint.read_bytes() == b"checkpoint"


def test_shell_material_rowcorr_budget_uses_controller_json_as_seed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "base_direct_residual": {"direct_residual_inf_n": 8.0},
                    "final_direct_residual": {
                        "direct_residual_inf_n": 7.0,
                        "residual_gate_passed": False,
                    },
                    "current_tangent_residual_row_correction": {
                        "accepted": True,
                        "promotion_count": 1,
                        "stop_reason": "max_promotions_exhausted",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return controller.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(controller.subprocess, "run", completed_run)
    seed = tmp_path / "seed_controller.json"
    seed.write_text(
        json.dumps(
            {
                "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
                "status": "partial",
                "initial_frontier_direct_residual_inf_n": 9.0,
                "final_direct_residual_inf_n": 8.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = controller.run_shell_material_rowcorr_budget_controller(
        seed_probe_json=seed,
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        child_timeout_seconds=1.0,
    )

    assert payload["seed_probe"]["final_direct_residual_inf_n"] == 8.0
    assert payload["initial_frontier_direct_residual_inf_n"] == 8.0
    assert payload["rows"][0]["seed_frontier_direct_residual_inf_n"] == 8.0
    assert payload["rows"][0]["frontier_improvement_inf_n"] == 1.0


def test_shell_material_rowcorr_budget_child_timeout_writes_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def timeout_run(command, **kwargs):
        raise controller.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(controller.subprocess, "run", timeout_run)

    payload = controller.run_shell_material_rowcorr_budget_controller(
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        child_timeout_seconds=0.01,
    )

    row = payload["rows"][0]
    assert row["status"] == "timeout"
    assert row["accepted"] is False
    assert row["subprocess_timeout"] is True
    assert row["subprocess_stdout"] == "partial stdout"
    assert row["subprocess_stderr"] == "partial stderr"
    assert payload["controller"]["stop_reason"] == "child_timeout_seconds_exceeded"
    assert payload["controller"]["runtime_budget_exceeded"] is True
    assert payload["final_direct_residual_inf_n"] == 14.0

    child_receipt = json.loads(Path(row["child_receipt_path"]).read_text())
    assert child_receipt["status"] == "timeout"
    assert child_receipt["output_final_checkpoint_npz"] is None
    assert child_receipt["output_final_checkpoint_written"] is False
    assert child_receipt["current_tangent_residual_row_correction"]["stop_reason"] == (
        "child_timeout_seconds_exceeded"
    )
