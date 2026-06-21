from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_direct_residual_adaptive_preconditioned_global_newton as adaptive  # noqa: E402


def _hip_residual_engine_contract() -> dict[str, object]:
    return {
        "hip_residual_engine_contract_passed": True,
        "hip_residual_engine_required": True,
        "hip_residual_engine_required_lane_count": 1,
        "hip_residual_engine_passed_lane_count": 1,
        "hip_residual_engine_backends": ["hip_full_residual"],
        "hip_residual_engine_blockers": [],
    }


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
    monkeypatch.setattr(
        adaptive,
        "_collect_hip_preflight",
        lambda: {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": True,
            "torch_importable": True,
            "cuda_device_count": 1,
            "diagnostic": "available",
        },
    )

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=checkpoint_npz,
        output_json=output_json,
        output_final_checkpoint_npz=tmp_path / "final.npz",
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_difference_scheme="central",
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual_resident",
        matrix_free_global_krylov_require_hip_batch_replay=True,
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
    assert controller["matrix_free_global_krylov_full_assembly_trial_replay"] is True
    assert controller["matrix_free_global_krylov_difference_scheme"] == "central"
    assert (
        controller["matrix_free_global_krylov_batch_replay_backend"]
        == "hip_full_residual_resident"
    )
    assert controller["matrix_free_global_krylov_require_hip_batch_replay"] is True
    assert (
        controller["matrix_free_global_krylov_linear_solver_backend"]
        == "torch_hip_gmres"
    )
    assert (
        controller[
            "matrix_free_global_krylov_linear_solver_backend_auto_selected_reason"
        ]
        == "hip_batch_replay_required_suppresses_host_gmres"
    )
    assert controller["matrix_free_global_krylov_preconditioner_mode"] == "none"
    assert (
        controller["matrix_free_global_krylov_preconditioner_mode_disabled_reason"]
        == "hip_batch_replay_required_suppresses_cpu_current_tangent_preconditioner"
    )
    assert controller["runtime_budget_exceeded"] is True
    assert payload["final_direct_residual_inf_n"] == 1.23

    row = payload["rows"][0]
    assert row["status"] == "timeout"
    assert row["subprocess_timeout"] is True
    assert row["base_direct_residual_inf_n"] == 1.23
    assert row["subprocess_stdout"] == "partial stdout"
    assert row["subprocess_stderr"] == "partial stderr"
    assert "--allow-cpu-diagnostic" not in row["subprocess_command"]
    assert "--apply-shell-material-tangent" in row["subprocess_command"]
    assert "--compact-output-final-checkpoint" in row["subprocess_command"]
    assert "--enable-matrix-free-global-krylov" in row["subprocess_command"]
    assert "--matrix-free-global-krylov-difference-scheme" in row["subprocess_command"]
    assert "central" in row["subprocess_command"]
    assert "--matrix-free-global-krylov-batch-replay-backend" in row[
        "subprocess_command"
    ]
    assert "hip_full_residual_resident" in row["subprocess_command"]
    preconditioner_mode_index = row["subprocess_command"].index(
        "--matrix-free-global-krylov-preconditioner-mode"
    )
    assert row["subprocess_command"][preconditioner_mode_index + 1] == "none"
    assert "--matrix-free-global-krylov-require-hip-batch-replay" in row[
        "subprocess_command"
    ]
    linear_backend_index = row["subprocess_command"].index(
        "--matrix-free-global-krylov-linear-solver-backend"
    )
    assert row["subprocess_command"][linear_backend_index + 1] == "torch_hip_gmres"
    assert "--matrix-free-global-krylov-full-assembly-trial-replay" in row[
        "subprocess_command"
    ]
    assert "--matrix-free-global-krylov-preconditioner-input-scale" in row[
        "subprocess_command"
    ]
    assert row["preconditioner_input_scale"] == 1.0

    child_receipt = json.loads(Path(row["child_receipt_path"]).read_text())
    assert child_receipt["status"] == "timeout"
    assert child_receipt["preconditioner_input_scale"] == 1.0
    assert child_receipt["difference_scheme"] == "central"
    assert child_receipt["preconditioner_mode"] == "none"
    assert child_receipt["batch_replay_backend"] == "hip_full_residual_resident"
    assert child_receipt["require_hip_batch_replay"] is True
    assert child_receipt["linear_solver_backend"] == "torch_hip_gmres"
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


def test_adaptive_global_newton_runtime_budget_implies_child_timeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"
    seen_timeouts: list[float] = []

    def timeout_run(command, **kwargs):
        seen_timeouts.append(float(kwargs["timeout"]))
        raise adaptive.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output="budget stdout",
            stderr="budget stderr",
        )

    def load_checkpoint(_checkpoint_npz: Path):
        return {"residual_inf_n": 3.0}, np.zeros(1), None, None

    monkeypatch.setattr(adaptive.subprocess, "run", timeout_run)
    monkeypatch.setattr(adaptive, "_load_checkpoint", load_checkpoint)

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
        max_controller_runtime_seconds=0.25,
    )

    assert seen_timeouts
    assert 0.0 < seen_timeouts[0] <= 0.25
    assert payload["controller"]["runtime_budget_seconds"] == 0.25
    assert payload["controller"]["child_timeout_seconds"] is None
    assert payload["controller"]["stop_reason"] == "child_timeout_seconds_exceeded"
    assert payload["controller"]["runtime_budget_exceeded"] is True

    row = payload["rows"][0]
    assert row["subprocess_timeout"] is True
    assert 0.0 < row["child_timeout_seconds"] <= 0.25
    assert row["subprocess_stdout"] == "budget stdout"


def test_adaptive_global_newton_hip_preflight_unavailable_returns_partial_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"

    def fake_hip_preflight() -> dict:
        return {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": False,
            "torch_importable": True,
            "cuda_device_count": 0,
            "diagnostic": "no HIP devices found",
        }

    monkeypatch.setattr(adaptive, "_collect_hip_preflight", fake_hip_preflight)

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=output_json,
        child_output_dir=child_output_dir,
        matrix_free_global_krylov_require_hip_batch_replay=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
    )

    assert payload["status"] == "partial"
    assert payload["adaptive_preconditioned_global_newton_ready"] is False
    assert "hip_preflight" in payload
    assert payload["hip_preflight"]["hip_available"] is False
    assert payload["hip_preflight"]["torch_importable"] is True
    assert payload["hip_preflight"]["cuda_device_count"] == 0
    assert payload["controller"]["enabled"] is True
    assert payload["controller"]["attempted"] is False
    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "hip_runtime_unavailable"
    assert payload["controller"]["matrix_free_global_krylov_require_hip_batch_replay"] is True
    assert payload["rows"] == []
    assert payload["promoted_rows"] == []
    assert payload["final_direct_residual_inf_n"] is None

    assert output_json.is_file()
    written = json.loads(output_json.read_text())
    assert written["hip_preflight"] == fake_hip_preflight()
    assert written["rows"] == []


def test_adaptive_global_newton_raises_for_hip_required_with_cpu_backend(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="matrix_free_global_krylov_require_hip_batch_replay",
    ):
        adaptive.run_adaptive_preconditioned_global_newton(
            mgt_path=tmp_path / "case.mgt",
            checkpoint_npz=tmp_path / "frontier.npz",
            output_json=tmp_path / "controller.json",
            child_output_dir=tmp_path / "children",
            matrix_free_global_krylov_require_hip_batch_replay=True,
            matrix_free_global_krylov_batch_replay_backend="cpu",
        )


def test_adaptive_global_newton_torch_hip_gmres_hip_unavailable_returns_partial_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"

    def fake_hip_preflight() -> dict:
        return {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": False,
            "torch_importable": False,
            "cuda_device_count": 0,
            "diagnostic": "torch_not_importable",
        }

    monkeypatch.setattr(adaptive, "_collect_hip_preflight", fake_hip_preflight)

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=output_json,
        child_output_dir=child_output_dir,
        matrix_free_global_krylov_linear_solver_backend="torch_hip_gmres",
        matrix_free_global_krylov_require_hip_batch_replay=False,
        matrix_free_global_krylov_batch_replay_backend="cpu",
    )

    assert payload["status"] == "partial"
    assert payload["adaptive_preconditioned_global_newton_ready"] is False
    assert "hip_preflight" in payload
    assert payload["hip_preflight"]["hip_available"] is False
    assert payload["hip_preflight"]["diagnostic"] == "torch_not_importable"
    assert payload["controller"]["enabled"] is True
    assert payload["controller"]["attempted"] is False
    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "hip_runtime_unavailable"
    assert payload["controller"][
        "matrix_free_global_krylov_linear_solver_backend"
    ] == "torch_hip_gmres"
    assert payload["controller"]["matrix_free_global_krylov_require_hip_batch_replay"] is False
    assert payload["rows"] == []
    assert payload["promoted_rows"] == []
    assert payload["final_direct_residual_inf_n"] is None

    assert output_json.is_file()
    written = json.loads(output_json.read_text())
    assert written["hip_preflight"] == fake_hip_preflight()
    assert written["rows"] == []


def test_adaptive_global_hip_required_non_conservative_claim_boundary(
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
                    "base_direct_residual": {"direct_residual_inf_n": 2.0},
                    "final_direct_residual": {"direct_residual_inf_n": 1.0},
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
                    },
                    "gate_assessment": {"fallback_zero_passed": True},
                    "residual_contract": _hip_residual_engine_contract(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return adaptive.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(adaptive.subprocess, "run", completed_run)
    monkeypatch.setattr(
        adaptive,
        "_collect_hip_preflight",
        lambda: {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": True,
            "torch_importable": True,
            "cuda_device_count": 1,
            "diagnostic": "available",
        },
    )

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=output_json,
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=1.0,
    )

    claim = payload["claim_boundary"]
    assert claim["cpu_diagnostic_only"] is False
    assert claim["official_rocm_hip_closure_required"] is False
    assert claim["residual_replay_is_regularization_free"] is True
    assert payload["promoted_rows"]
    assert payload["controller"]["promotion_count"] == 1


def test_adaptive_global_conservative_claim_boundary_on_timeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"
    checkpoint_npz = tmp_path / "frontier.npz"

    def timeout_run(command, **kwargs):
        raise adaptive.subprocess.TimeoutExpired(
            command, kwargs["timeout"], output="", stderr="",
        )

    def load_checkpoint(_checkpoint_npz: Path):
        return {"residual_inf_n": 2.0}, np.zeros(1), None, None

    monkeypatch.setattr(adaptive.subprocess, "run", timeout_run)
    monkeypatch.setattr(adaptive, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        adaptive,
        "_collect_hip_preflight",
        lambda: {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": True,
            "torch_importable": True,
            "cuda_device_count": 1,
            "diagnostic": "available",
        },
    )

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=checkpoint_npz,
        output_json=output_json,
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=0.01,
    )

    claim = payload["claim_boundary"]
    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True
    assert payload["controller"]["stop_reason"] == "child_timeout_seconds_exceeded"


def test_adaptive_global_conservative_claim_boundary_on_child_fallback_fail(
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
                    "base_direct_residual": {"direct_residual_inf_n": 2.0},
                    "final_direct_residual": {"direct_residual_inf_n": 1.0},
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
                    },
                    "gate_assessment": {"fallback_zero_passed": False},
                    "residual_contract": _hip_residual_engine_contract(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return adaptive.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(adaptive.subprocess, "run", completed_run)
    monkeypatch.setattr(
        adaptive,
        "_collect_hip_preflight",
        lambda: {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": True,
            "torch_importable": True,
            "cuda_device_count": 1,
            "diagnostic": "available",
        },
    )

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=output_json,
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=1.0,
    )

    claim = payload["claim_boundary"]
    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True
    assert payload["promoted_rows"] == []
    assert payload["controller"]["promotion_count"] == 0
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["child_gate_assessment"]["fallback_zero_passed"] is False
    assert "child_fallback_zero_audit_not_closed" in row[
        "child_strict_hip_promotion_blockers"
    ]


def test_adaptive_global_hip_required_missing_residual_contract_blocks_promotion(
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
                    "base_direct_residual": {"direct_residual_inf_n": 2.0},
                    "final_direct_residual": {"direct_residual_inf_n": 1.0},
                    "matrix_free_global_krylov": {
                        "accepted": True,
                        "stop_reason": "candidate_accepted",
                        "best_candidate": {
                            "direct_residual_inf_n": 1.0,
                            "relative_improvement": 0.5,
                            "alpha": 1.0,
                            "relative_increment_gate_passed": True,
                            "residual_gate_passed": False,
                        },
                    },
                    "gate_assessment": {"fallback_zero_passed": True},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return adaptive.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(adaptive.subprocess, "run", completed_run)
    monkeypatch.setattr(
        adaptive,
        "_collect_hip_preflight",
        lambda: {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": True,
            "torch_importable": True,
            "cuda_device_count": 1,
            "diagnostic": "available",
        },
    )

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=1.0,
    )

    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["child_hip_residual_engine_contract_passed"] is False
    assert "child_hip_residual_engine_contract_not_proven" in row[
        "child_strict_hip_promotion_blockers"
    ]
    assert payload["promoted_rows"] == []
    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "no_regularization_factor_promoted"
    assert payload["final_direct_residual_inf_n"] == 2.0


def test_adaptive_global_conservative_claim_boundary_on_child_claim_boundary() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": {
                    "cpu_diagnostic_only": True,
                    "official_rocm_hip_closure_required": False,
                },
                "child_blockers": [],
                "child_residual_contract": _hip_residual_engine_contract(),
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_adaptive_global_conservative_claim_boundary_on_child_strict_blocker() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": None,
                "child_blockers": ["g1_fallback_zero_audit_not_closed"],
                "child_residual_contract": _hip_residual_engine_contract(),
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_adaptive_frozen_shell_material_hip_replay_flag_in_child_command(
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
            output="",
            stderr="",
        )

    def load_checkpoint(_checkpoint_npz: Path):
        return {"residual_inf_n": 1.0}, __import__("numpy").zeros(1), None, None

    monkeypatch.setattr(adaptive.subprocess, "run", timeout_run)
    monkeypatch.setattr(adaptive, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        adaptive,
        "_collect_hip_preflight",
        lambda: {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": True,
            "torch_importable": True,
            "cuda_device_count": 1,
            "diagnostic": "available",
        },
    )

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=checkpoint_npz,
        output_json=output_json,
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=0.01,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
    )

    controller = payload["controller"]
    assert controller["apply_shell_material_tangent"] is True
    assert controller["allow_frozen_shell_material_tangent_hip_replay"] is True

    row = payload["rows"][0]
    assert "--apply-shell-material-tangent" in row["subprocess_command"]
    assert (
        "--allow-frozen-shell-material-tangent-hip-replay"
        in row["subprocess_command"]
    )

    child_receipt = json.loads(Path(row["child_receipt_path"]).read_text())
    assert child_receipt["allow_frozen_shell_material_tangent_hip_replay"] is True


def test_adaptive_frozen_flag_absent_when_disabled(
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
            output="",
            stderr="",
        )

    def load_checkpoint(_checkpoint_npz: Path):
        return {"residual_inf_n": 1.0}, __import__("numpy").zeros(1), None, None

    monkeypatch.setattr(adaptive.subprocess, "run", timeout_run)
    monkeypatch.setattr(adaptive, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        adaptive,
        "_collect_hip_preflight",
        lambda: {
            "checked_at": "2025-01-01T00:00:00+00:00",
            "hip_available": True,
            "torch_importable": True,
            "cuda_device_count": 1,
            "diagnostic": "available",
        },
    )

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=checkpoint_npz,
        output_json=output_json,
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=0.01,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=False,
    )

    controller = payload["controller"]
    assert controller["apply_shell_material_tangent"] is True
    assert controller["allow_frozen_shell_material_tangent_hip_replay"] is False

    row = payload["rows"][0]
    assert "--apply-shell-material-tangent" in row["subprocess_command"]
    assert (
        "--allow-frozen-shell-material-tangent-hip-replay"
        not in row["subprocess_command"]
    )

    child_receipt = json.loads(Path(row["child_receipt_path"]).read_text())
    assert child_receipt["allow_frozen_shell_material_tangent_hip_replay"] is False


def test_adaptive_frozen_flag_absent_without_shell_material_tangent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"

    def timeout_run(command, **kwargs):
        raise adaptive.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output="",
            stderr="",
        )

    def load_checkpoint(_checkpoint_npz: Path):
        return {"residual_inf_n": 1.0}, __import__("numpy").zeros(1), None, None

    monkeypatch.setattr(adaptive.subprocess, "run", timeout_run)
    monkeypatch.setattr(adaptive, "_load_checkpoint", load_checkpoint)

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=output_json,
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=0.01,
        apply_shell_material_tangent=False,
        allow_frozen_shell_material_tangent_hip_replay=True,
    )

    controller = payload["controller"]
    assert controller["apply_shell_material_tangent"] is False
    assert controller["allow_frozen_shell_material_tangent_hip_replay"] is True

    row = payload["rows"][0]
    assert "--apply-shell-material-tangent" not in row["subprocess_command"]
    assert (
        "--allow-frozen-shell-material-tangent-hip-replay"
        not in row["subprocess_command"]
    )


def test_adaptive_state_dependent_shell_material_hip_replay_flag_wins(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "controller.json"
    child_output_dir = tmp_path / "children"

    def timeout_run(command, **kwargs):
        raise adaptive.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output="",
            stderr="",
        )

    def load_checkpoint(_checkpoint_npz: Path):
        return {"residual_inf_n": 1.0}, __import__("numpy").zeros(1), None, None

    monkeypatch.setattr(adaptive.subprocess, "run", timeout_run)
    monkeypatch.setattr(adaptive, "_load_checkpoint", load_checkpoint)

    payload = adaptive.run_adaptive_preconditioned_global_newton(
        mgt_path=tmp_path / "case.mgt",
        checkpoint_npz=tmp_path / "frontier.npz",
        output_json=output_json,
        child_output_dir=child_output_dir,
        tangent_regularization_factors=(1.0e-6,),
        max_controller_steps=1,
        matrix_free_global_krylov_max_iterations=1,
        matrix_free_global_krylov_alpha_values=(1.0,),
        child_timeout_seconds=0.01,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    controller = payload["controller"]
    assert controller["allow_frozen_shell_material_tangent_hip_replay"] is True
    assert controller["allow_state_dependent_shell_material_tangent_hip_replay"] is True

    row = payload["rows"][0]
    assert "--apply-shell-material-tangent" in row["subprocess_command"]
    assert (
        "--allow-state-dependent-shell-material-tangent-hip-replay"
        in row["subprocess_command"]
    )
    assert (
        "--allow-frozen-shell-material-tangent-hip-replay"
        not in row["subprocess_command"]
    )

    child_receipt = json.loads(Path(row["child_receipt_path"]).read_text())
    assert (
        child_receipt["allow_state_dependent_shell_material_tangent_hip_replay"]
        is True
    )


def test_adaptive_residual_contract_state_dependent_allows_non_conservative() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": (
                    "State-dependent shell-material tangent HIP replay "
                    "computes candidate state tangent but host operator "
                    "refresh is not full production ROCm/HIP residency closure."
                ),
                "child_blockers": [],
                "child_residual_contract": {
                    **_hip_residual_engine_contract(),
                    "allow_state_dependent_shell_material_tangent_hip_replay": True,
                    "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                },
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is False
    assert claim["official_rocm_hip_closure_required"] is False
    assert claim["host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency"] is True


def test_adaptive_residual_contract_frozen_without_state_dependent_stays_conservative() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": (
                    "Frozen shell-material tangent HIP replay is not "
                    "state-dependent material Newton closure."
                ),
                "child_blockers": [],
                "child_residual_contract": {
                    **_hip_residual_engine_contract(),
                    "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure": True,
                },
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_adaptive_residual_contract_missing_stays_conservative() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": (
                    "HIP residual replay happened but production ROCm "
                    "residency is not fully closed."
                ),
                "child_blockers": [],
                "child_residual_contract": None,
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_adaptive_residual_contract_does_not_bypass_rocm_hip_blocker() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": None,
                "child_blockers": ["rocm_hip_backend_not_production_resident"],
                "child_residual_contract": {
                    **_hip_residual_engine_contract(),
                    "allow_state_dependent_shell_material_tangent_hip_replay": True,
                    "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                },
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_adaptive_residual_contract_does_not_bypass_explicit_unavailable_blocker() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": None,
                "child_blockers": ["hip_batch_replay_required_unavailable"],
                "child_residual_contract": {
                    **_hip_residual_engine_contract(),
                    "allow_state_dependent_shell_material_tangent_hip_replay": True,
                },
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_adaptive_residual_contract_no_state_dependent_and_frozen_stays_conservative() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": (
                    "HIP residual replay attempted with host operator "
                    "boundary and HIP unsupported status."
                ),
                "child_blockers": [],
                "child_residual_contract": {
                    **_hip_residual_engine_contract(),
                    "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure": True,
                },
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_adaptive_state_dependent_residual_contract_no_field_stays_conservative() -> None:
    claim = adaptive._build_adaptive_global_claim_boundary(
        require_hip_batch_replay=True,
        backend_is_hip=True,
        hip_preflight_available=True,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": (
                    "HIP residual replay happened but ROCm production "
                    "residency is not fully closed."
                ),
                "child_blockers": [],
                "child_residual_contract": {
                    "some_other_field": True,
                },
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True
