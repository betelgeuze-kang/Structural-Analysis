from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_g1_alternating_newton_controller as alternating  # noqa: E402


def _write_seed(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "status": "partial",
                "final_direct_residual": {"direct_residual_inf_n": 10.0},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _patch_available_hip(monkeypatch) -> None:
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
            "reason": "available",
            "torch_hip_device_name": "fake-hip",
        },
    )


def _hip_residual_engine_contract() -> dict[str, object]:
    return {
        "hip_residual_engine_contract_passed": True,
        "hip_residual_engine_required": True,
        "hip_residual_engine_required_lane_count": 1,
        "hip_residual_engine_passed_lane_count": 1,
        "hip_residual_engine_backends": ["hip_full_residual_resident"],
        "hip_residual_engine_blockers": [],
    }


def test_alternating_controller_promotes_row_then_global(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(f"checkpoint-{len(commands)}".encode("utf-8"))
        if "run_mgt_shell_material_rowcorr_budget_controller.py" in command[1]:
            output_path.write_text(
                json.dumps(
                    {
                        "status": "partial",
                        "final_direct_residual_inf_n": 9.0,
                        "controller": {"promotion_count": 1},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            output_path.write_text(
                json.dumps(
                    {
                        "status": "partial",
                        "final_direct_residual_inf_n": 8.5,
                        "controller": {"promotion_count": 1},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)

    final_checkpoint = tmp_path / "final.npz"
    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        output_final_checkpoint_npz=final_checkpoint,
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        child_timeout_seconds=10.0,
        row_support_selection="target_rows",
        row_batch_replay_backend="hip_full_residual",
        row_require_hip_batch_replay=True,
    )

    assert payload["controller"]["promotion_count"] == 2
    assert payload["controller"]["stop_reason"] == "max_cycles_reached"
    assert payload["initial_frontier_direct_residual_inf_n"] == 10.0
    assert payload["final_direct_residual_inf_n"] == 8.5
    assert len(payload["rows"]) == 2
    assert [row["lane"] for row in payload["rows"]] == [
        "row_fd_component",
        "global_krylov",
    ]
    assert all(row["accepted"] for row in payload["rows"])
    assert "--row-target-mode" in commands[0]
    assert "current_component_rows" in commands[0]
    assert "--row-jacobian-mode" in commands[0]
    assert "finite_difference" in commands[0]
    assert "--row-support-selection" in commands[0]
    assert "target_rows" in commands[0]
    assert "--row-batch-replay-backend" in commands[0]
    assert "hip_full_residual" in commands[0]
    assert "--row-require-hip-batch-replay" in commands[0]
    assert payload["controller"]["row_support_selection"] == "target_rows"
    assert payload["controller"]["row_batch_replay_backend"] == "hip_full_residual"
    assert payload["controller"]["row_require_hip_batch_replay"] is True
    assert "--matrix-free-global-krylov-full-assembly-trial-replay" not in commands[1]
    assert final_checkpoint.read_bytes() == b"checkpoint-2"


def test_alternating_controller_zero_budget_launches_no_children(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("zero budget must not launch children")

    monkeypatch.setattr(alternating.subprocess, "run", fail_run)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        max_controller_runtime_seconds=0.0,
    )

    assert payload["controller"]["stop_reason"] == "runtime_budget_exceeded"
    assert payload["controller"]["runtime_budget_exceeded"] is True
    assert payload["controller"]["promotion_count"] == 0
    assert payload["rows"] == []
    assert payload["final_direct_residual_inf_n"] == 10.0


def test_alternating_controller_gives_child_receipt_timeout_grace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    seen_timeout: list[float] = []
    seen_timeout_commands: list[list[str]] = []

    def completed_run(command, **kwargs):
        seen_timeout.append(float(kwargs["timeout"]))
        seen_timeout_commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
    )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        max_controller_runtime_seconds=2.0,
        child_timeout_seconds=2.0,
        child_timeout_grace_seconds=5.0,
    )

    assert len(seen_timeout) == 2
    assert 6.9 < seen_timeout[0] <= 7.0
    global_command = next(
        command
        for command in seen_timeout_commands
        if "run_mgt_direct_residual_adaptive_preconditioned_global_newton.py"
        in command[1]
    )
    global_child_timeout_index = global_command.index("--child-timeout-seconds")
    assert 1.9 < float(global_command[global_child_timeout_index + 1]) <= 2.0
    row = payload["rows"][0]
    assert 1.9 < row["child_runtime_budget_seconds"] <= 2.0
    assert 6.9 < row["subprocess_timeout_seconds"] <= 7.0
    assert payload["controller"]["child_timeout_grace_seconds"] == 5.0


def test_alternating_controller_can_run_global_only_sequence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"global-checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.5,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        global_krylov_max_iterations=4,
        global_krylov_difference_scheme="central",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        global_krylov_require_hip_batch_replay=True,
        global_krylov_probe_max_step=2.5e-5,
        global_krylov_residual_scale_floor=3.0,
        global_krylov_min_relative_improvement=2.0e-6,
        global_enable_secant_family_seed=True,
        global_max_secant_family_promotions=2,
        global_secant_family_window_sizes=(2, 4),
        global_secant_family_ridge_factors=(0.0, 1.0e-6),
        global_secant_family_alpha_values=(1.0, 0.25),
        global_secant_family_min_relative_improvement=3.0e-6,
    )

    assert len(commands) == 1
    assert "run_mgt_direct_residual_adaptive_preconditioned_global_newton.py" in commands[0][1]
    max_iter_index = commands[0].index("--matrix-free-global-krylov-max-iterations")
    assert commands[0][max_iter_index + 1] == "4"
    difference_scheme_index = commands[0].index(
        "--matrix-free-global-krylov-difference-scheme"
    )
    assert commands[0][difference_scheme_index + 1] == "central"
    batch_backend_index = commands[0].index(
        "--matrix-free-global-krylov-batch-replay-backend"
    )
    assert commands[0][batch_backend_index + 1] == "hip_full_residual_resident"
    preconditioner_mode_index = commands[0].index(
        "--matrix-free-global-krylov-preconditioner-mode"
    )
    assert commands[0][preconditioner_mode_index + 1] == "none"
    assert "--matrix-free-global-krylov-require-hip-batch-replay" in commands[0]
    linear_backend_index = commands[0].index(
        "--matrix-free-global-krylov-linear-solver-backend"
    )
    assert commands[0][linear_backend_index + 1] == "torch_hip_gmres"
    max_step_index = commands[0].index("--matrix-free-global-krylov-probe-max-step")
    assert commands[0][max_step_index + 1] == "2.5e-05"
    scale_floor_index = commands[0].index(
        "--matrix-free-global-krylov-residual-scale-floor"
    )
    assert commands[0][scale_floor_index + 1] == "3.0"
    min_improvement_index = commands[0].index(
        "--matrix-free-global-krylov-min-relative-improvement"
    )
    assert commands[0][min_improvement_index + 1] == "2e-06"
    assert "--enable-secant-family-seed" in commands[0]
    max_secant_index = commands[0].index("--max-secant-family-promotions")
    assert commands[0][max_secant_index + 1] == "2"
    window_index = commands[0].index("--secant-family-window-sizes")
    assert commands[0][window_index + 1] == "2,4"
    ridge_index = commands[0].index("--secant-family-ridge-factors")
    assert commands[0][ridge_index + 1] == "0.0,1e-06"
    secant_alpha_index = commands[0].index("--secant-family-alpha-values")
    assert commands[0][secant_alpha_index + 1] == "1.0,0.25"
    secant_min_index = commands[0].index("--secant-family-min-relative-improvement")
    assert commands[0][secant_min_index + 1] == "3e-06"
    assert payload["controller"]["lane_sequence"] == ["global_krylov"]
    assert payload["controller"]["global_krylov_max_iterations"] == 4
    assert payload["controller"]["global_krylov_difference_scheme"] == "central"
    assert (
        payload["controller"]["global_krylov_batch_replay_backend"]
        == "hip_full_residual_resident"
    )
    assert payload["controller"]["global_krylov_require_hip_batch_replay"] is True
    assert (
        payload["controller"]["global_krylov_linear_solver_backend"]
        == "torch_hip_gmres"
    )
    assert (
        payload["controller"][
            "global_krylov_linear_solver_backend_auto_selected_reason"
        ]
        == "hip_batch_replay_required_suppresses_host_gmres"
    )
    assert payload["controller"]["global_krylov_preconditioner_mode"] == "none"
    assert (
        payload["controller"]["global_krylov_preconditioner_mode_disabled_reason"]
        == "hip_batch_replay_required_suppresses_cpu_current_tangent_preconditioner"
    )
    assert payload["controller"]["global_krylov_probe_max_step"] == 2.5e-5
    assert payload["controller"]["global_krylov_residual_scale_floor"] == 3.0
    assert payload["controller"]["global_krylov_min_relative_improvement"] == 2.0e-6
    assert payload["controller"]["global_secant_family_seed_enabled"] is True
    assert payload["controller"]["global_max_secant_family_promotions"] == 2
    assert payload["controller"]["global_secant_family_window_sizes"] == [2, 4]
    assert payload["controller"]["global_secant_family_ridge_factors"] == [0.0, 1e-6]
    assert payload["controller"]["global_secant_family_alpha_values"] == [1.0, 0.25]
    assert (
        payload["controller"]["global_secant_family_min_relative_improvement"]
        == 3.0e-6
    )
    assert payload["controller"]["promotion_count"] == 1
    assert payload["rows"][0]["lane"] == "global_krylov"
    assert payload["final_direct_residual_inf_n"] == 9.5


def test_strict_hip_residual_engine_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        if "run_mgt_shell_material_rowcorr_budget_controller.py" in command[1]:
            final_residual = 9.0
        else:
            final_residual = 8.5
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": final_residual,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        strict_hip_residual_engine=True,
    )

    assert payload["controller"]["strict_hip_residual_engine"] is True
    assert (
        payload["controller"]["strict_hip_residual_engine_fallback_zero_expectation"]
        is True
    )
    assert payload["controller"]["row_require_hip_batch_replay"] is True
    assert payload["controller"]["global_krylov_require_hip_batch_replay"] is True
    assert payload["controller"]["row_batch_replay_backend"] == "hip_full_residual"
    assert (
        payload["controller"]["global_krylov_batch_replay_backend"]
        == "hip_full_residual_resident"
    )

    row_command = next(
        c for c in commands
        if "run_mgt_shell_material_rowcorr_budget_controller.py" in c[1]
    )
    global_command = next(
        c for c in commands
        if "run_mgt_direct_residual_adaptive_preconditioned_global_newton.py"
        in c[1]
    )

    assert "--row-require-hip-batch-replay" in row_command
    assert "--matrix-free-global-krylov-require-hip-batch-replay" in global_command
    linear_backend_index = global_command.index(
        "--matrix-free-global-krylov-linear-solver-backend"
    )
    assert global_command[linear_backend_index + 1] == "torch_hip_gmres"
    assert (
        payload["controller"]["global_krylov_linear_solver_backend"]
        == "torch_hip_gmres"
    )
    assert (
        payload["controller"][
            "global_krylov_linear_solver_backend_auto_selected_reason"
        ]
        == "hip_batch_replay_required_suppresses_host_gmres"
    )
    assert payload["controller"]["promotion_count"] == 2


def test_strict_hip_residual_engine_rejects_child_fallback_boundary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_receipt = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_receipt.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "gate_assessment": {
                        "fallback_zero_passed": False,
                        "fallback_zero_audit": {
                            "fallback_zero_boundary_count": 1,
                            "fallback_zero_boundaries": [
                                {
                                    "boundary": (
                                        "global_krylov_cpu_batch_replay_fallback_suppressed"
                                    )
                                }
                            ],
                        },
                    },
                    "blockers": ["g1_fallback_zero_audit_not_closed"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_receipt),
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "cycle_without_global_promotion"
    assert payload["final_direct_residual_inf_n"] == 10.0
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert "fallback_zero_not_passed" in reasons
    assert "strict_child_blockers" in reasons


def test_strict_hip_residual_engine_preflight_blocks_child_launch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("strict HIP unavailable preflight must not launch children")

    monkeypatch.setattr(alternating.subprocess, "run", fail_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": False,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": False,
            "reason": "torch_hip_device_unavailable",
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        max_cycles=1,
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "strict_hip_runtime_unavailable"
    assert payload["rows"] == []
    assert payload["final_direct_residual_inf_n"] == 10.0
    assert payload["controller"]["strict_hip_runtime_preflight"] == {
        "available": False,
        "torch_imported": True,
        "torch_rocm_build": True,
        "torch_hip_device_available": False,
        "reason": "torch_hip_device_unavailable",
    }


def test_strict_hip_residual_engine_rejects_cpu_backends(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HIP row batch replay backend"):
        alternating.run_g1_alternating_newton_controller(
            checkpoint_npz=tmp_path / "seed.npz",
            seed_probe_json=_write_seed(tmp_path / "seed.json"),
            output_json=tmp_path / "controller.json",
            child_output_dir=tmp_path / "children",
            max_cycles=0,
            strict_hip_residual_engine=True,
            row_batch_replay_backend="cpu",
            global_krylov_batch_replay_backend="hip_full_residual",
        )

    with pytest.raises(ValueError, match="HIP global Krylov batch replay backend"):
        alternating.run_g1_alternating_newton_controller(
            checkpoint_npz=tmp_path / "seed.npz",
            seed_probe_json=_write_seed(tmp_path / "seed.json"),
            output_json=tmp_path / "controller.json",
            child_output_dir=tmp_path / "children",
            max_cycles=0,
            strict_hip_residual_engine=True,
            row_batch_replay_backend="hip_full_residual",
            global_krylov_batch_replay_backend="cpu",
        )


def test_strict_hip_residual_engine_rejects_child_cpu_diagnostic_claim_boundary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "claim_boundary": {
                        "cpu_diagnostic_only": True,
                        "official_rocm_hip_closure_required": False,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "cycle_without_global_promotion"
    assert payload["final_direct_residual_inf_n"] == 10.0
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert "claim_boundary_cpu_diagnostic_only" in reasons


def test_strict_hip_residual_engine_rejects_child_rocm_hip_closure_claim_boundary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps({"gate_assessment": {"fallback_zero_passed": True}}) + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "claim_boundary": {
                        "cpu_diagnostic_only": False,
                        "official_rocm_hip_closure_required": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "cycle_without_global_promotion"
    assert payload["final_direct_residual_inf_n"] == 10.0
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert "claim_boundary_official_rocm_hip_closure_required" in reasons


def test_strict_hip_residual_engine_rejects_child_string_claim_boundary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps({"gate_assessment": {"fallback_zero_passed": True}}) + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "claim_boundary": (
                        "CPU diagnostic fallback path. "
                        "Official ROCm-HIP-required closure pending."
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "cycle_without_global_promotion"
    assert payload["final_direct_residual_inf_n"] == 10.0
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert (
        "claim_boundary_string_suggests_cpu_or_hip_required" in reasons
    )


def test_strict_hip_residual_engine_accepts_child_without_claim_boundary(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 1
    assert payload["controller"]["stop_reason"] == "max_cycles_reached"
    assert payload["final_direct_residual_inf_n"] == 9.0
    row = payload["rows"][0]
    assert row["accepted"] is True
    assert row["strict_fallback_zero_audit"]["passed"] is True


def test_strict_hip_accepts_nested_non_conservative_claim_boundary(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "claim_boundary": {
                        "cpu_diagnostic_only": False,
                        "official_rocm_hip_closure_required": False,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 1
    assert payload["controller"]["stop_reason"] == "max_cycles_reached"
    row = payload["rows"][0]
    assert row["accepted"] is True
    assert row["strict_fallback_zero_audit"]["passed"] is True


def test_alternating_frozen_replay_flag_in_row_child_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("row_fd_component",),
        allow_frozen_shell_material_tangent_hip_replay=True,
    )

    assert payload["controller"]["allow_frozen_shell_material_tangent_hip_replay"] is True
    row_command = commands[0]
    assert (
        "--allow-frozen-shell-material-tangent-hip-replay" in row_command
    )


def test_alternating_frozen_replay_flag_in_global_child_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.5,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        allow_frozen_shell_material_tangent_hip_replay=True,
    )

    assert payload["controller"]["allow_frozen_shell_material_tangent_hip_replay"] is True
    global_command = commands[0]
    assert (
        "--allow-frozen-shell-material-tangent-hip-replay" in global_command
    )


def test_alternating_state_dependent_replay_flag_in_row_and_global_child_commands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "claim_boundary": (
                        "State-dependent shell-material tangent HIP replay "
                        "is not full production ROCm/HIP residency closure."
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("row_fd_component", "global_krylov"),
        allow_frozen_shell_material_tangent_hip_replay=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assert (
        payload["controller"][
            "allow_state_dependent_shell_material_tangent_hip_replay"
        ]
        is True
    )
    assert len(commands) == 2
    for command in commands:
        assert "--allow-state-dependent-shell-material-tangent-hip-replay" in command
        assert "--allow-frozen-shell-material-tangent-hip-replay" not in command


def test_alternating_frozen_flag_absent_when_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("row_fd_component", "global_krylov"),
        allow_frozen_shell_material_tangent_hip_replay=False,
    )

    assert payload["controller"]["allow_frozen_shell_material_tangent_hip_replay"] is False
    for command in commands:
        assert (
            "--allow-frozen-shell-material-tangent-hip-replay" not in command
        )


def test_strict_hip_audit_blocks_frozen_replay_non_closure_claim(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "claim_boundary": {
                        "cpu_diagnostic_only": True,
                        "official_rocm_hip_closure_required": False,
                        "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_frozen_shell_material_tangent_hip_replay=True,
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "cycle_without_global_promotion"
    assert payload["controller"]["allow_frozen_shell_material_tangent_hip_replay"] is True
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert "claim_boundary_cpu_diagnostic_only" in reasons


def test_non_strict_claim_boundary_preserves_cpu_diagnostic_only(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("row_fd_component",),
    )

    cb = payload["claim_boundary"]
    assert cb["cpu_diagnostic_only"] is True
    assert cb["official_rocm_hip_closure_required"] is True
    assert "strict_hip_residual_engine_active" not in cb
    assert "residual_replay_requires_hip_only" not in cb
    assert "cpu_fallback_expectation_zero_suppressed" not in cb


def test_strict_hip_claim_boundary_no_cpu_diagnostic_only(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    cb = payload["claim_boundary"]
    assert cb["cpu_diagnostic_only"] is False
    assert cb["official_rocm_hip_closure_required"] is True
    assert cb["strict_hip_residual_engine_active"] is True
    assert cb["residual_replay_requires_hip_only"] is True
    assert cb["cpu_fallback_expectation_zero_suppressed"] is True
    assert cb["rocm_hip_runtime_available"] is True
    assert cb["strict_hip_runtime_preflight_passed"] is True


def test_strict_hip_claim_boundary_preflight_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("strict HIP unavailable preflight must not launch children")

    monkeypatch.setattr(alternating.subprocess, "run", fail_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": False,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": False,
            "reason": "torch_hip_device_unavailable",
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        max_cycles=1,
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    cb = payload["claim_boundary"]
    assert cb["cpu_diagnostic_only"] is False
    assert cb["strict_hip_residual_engine_active"] is True
    assert cb["rocm_hip_runtime_available"] is False
    assert cb["strict_hip_runtime_preflight_passed"] is False
    assert cb["g1_closure_claimed"] is False
    assert payload["status"] == "partial"
    assert payload["controller"]["stop_reason"] == "strict_hip_runtime_unavailable"


def test_strict_hip_closure_assessment_when_rocm_hip_runtime_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("strict HIP unavailable preflight must not launch children")

    monkeypatch.setattr(alternating.subprocess, "run", fail_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": False,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": False,
            "reason": "torch_hip_device_unavailable",
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        max_cycles=1,
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["strict_hip_engine_governs"] is True
    assert assessment["strict_hip_runtime_governs"] is False
    assert assessment["evidence_child_receipt_path"] is None
    assert assessment["evidence_location"] is None
    assert assessment["full_load_direct_residual_passed"] is False
    assert assessment["relative_increment_verified"] is False
    assert assessment["relative_increment_passed"] is False
    assert assessment["material_newton_state_dependent_passed"] is False
    assert assessment["hip_residual_engine_contract_passed"] is False
    assert assessment["frozen_only_is_not_state_dependent_closure"] is False
    assert assessment["fallback_zero_passed"] is False
    assert assessment["child_fallback_zero_passed"] is False
    assert "strict_hip_runtime_unavailable" in assessment["blockers"]
    assert "no_promoted_child_receipt" in assessment["blockers"]


def test_strict_hip_claim_boundary_state_dependent_replay_note(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    cb = payload["claim_boundary"]
    assert cb["cpu_diagnostic_only"] is False
    assert (
        cb["host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency"]
        is True
    )


def test_strict_hip_accepts_nested_direct_probe_state_dependent_contract_string_claim(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "gate_assessment": {"fallback_zero_passed": True},
                    "residual_contract": {
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                    "claim_boundary": (
                        "State-dependent shell-material tangent HIP replay. "
                        "Host shell CSR/operator refresh, not production ROCm/HIP residency."
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 1
    assert payload["controller"]["stop_reason"] == "max_cycles_reached"
    row = payload["rows"][0]
    assert row["accepted"] is True
    assert row["strict_fallback_zero_audit"]["passed"] is True


def test_strict_hip_rejects_direct_probe_string_claim_without_residual_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "gate_assessment": {"fallback_zero_passed": True},
                    "claim_boundary": (
                        "State-dependent shell-material tangent HIP replay. "
                        "Host shell CSR/operator refresh, not production ROCm/HIP residency."
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "cycle_without_global_promotion"
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert "claim_boundary_string_suggests_cpu_or_hip_required" in reasons


def test_strict_hip_rejects_direct_probe_frozen_only_contract_string_claim(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "gate_assessment": {"fallback_zero_passed": True},
                    "residual_contract": {
                        "allow_frozen_shell_material_tangent_hip_replay": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": False,
                    },
                    "claim_boundary": (
                        "Frozen shell-material tangent HIP replay. "
                        "Host shell CSR/operator refresh, not production ROCm/HIP residency."
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    assert payload["controller"]["stop_reason"] == "cycle_without_global_promotion"
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert "claim_boundary_string_suggests_cpu_or_hip_required" in reasons


def test_strict_hip_rejects_state_dependent_contract_with_cpu_fallback_string(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "gate_assessment": {"fallback_zero_passed": True},
                    "residual_contract": {
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                    "claim_boundary": (
                        "CPU diagnostic fallback path with host operator refresh. "
                        "Production ROCm/HIP residency is not fully closed."
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assert payload["controller"]["promotion_count"] == 0
    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["strict_fallback_zero_audit"]["passed"] is False
    reasons = {
        blocker["reason"]
        for blocker in row["strict_fallback_zero_audit"]["blockers"]
    }
    assert "claim_boundary_string_suggests_cpu_or_hip_required" in reasons


def test_non_strict_claim_boundary_no_state_dependent_note(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("row_fd_component",),
    )

    cb = payload["claim_boundary"]
    assert (
        "host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency"
        not in cb
    )


def test_g1_closure_assessment_all_gates_passed_status_passed(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is True
    assert assessment["strict_hip_engine_governs"] is True
    assert assessment["strict_hip_runtime_governs"] is True
    assert assessment["full_load_direct_residual_passed"] is True
    assert assessment["relative_increment_verified"] is True
    assert assessment["relative_increment_passed"] is True
    assert assessment["material_newton_state_dependent_passed"] is True
    assert assessment["hip_residual_engine_contract_passed"] is True
    assert assessment["fallback_zero_passed"] is True
    assert assessment["child_fallback_zero_passed"] is True
    assert assessment["frozen_only_is_not_state_dependent_closure"] is False
    assert assessment["blockers"] == []
    assert payload["status"] == "passed"


def test_g1_closure_assessment_frozen_only_blocks_closure(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_frozen_shell_material_tangent_hip_replay": True,
                        "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_frozen_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["strict_hip_engine_governs"] is True
    assert assessment["strict_hip_runtime_governs"] is True
    assert assessment["full_load_direct_residual_passed"] is True
    assert assessment["relative_increment_verified"] is True
    assert assessment["relative_increment_passed"] is True
    assert assessment["material_newton_state_dependent_passed"] is False
    assert assessment["frozen_only_is_not_state_dependent_closure"] is True
    assert assessment["fallback_zero_passed"] is True
    assert assessment["child_fallback_zero_passed"] is True
    assert (
        "child_state_dependent_material_newton_gate_not_proven"
        in assessment["blockers"]
    )
    assert payload["status"] == "partial"


def test_g1_closure_assessment_requires_hip_residual_engine_contract(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["hip_residual_engine_contract_passed"] is False
    assert "child_hip_residual_engine_contract_not_proven" in assessment["blockers"]
    assert payload["status"] == "partial"


def test_g1_closure_assessment_non_strict_never_claims_closure(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    monkeypatch.setattr(
        alternating,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "available": True,
            "torch_imported": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
            "reason": "available",
            "torch_hip_device_name": "fake-hip",
        },
    )

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["strict_hip_engine_governs"] is False
    assert payload["status"] == "partial"


def test_g1_closure_assessment_no_shell_material_replay_blocks_closure(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["strict_hip_engine_governs"] is True
    assert assessment["full_load_direct_residual_passed"] is True
    assert assessment["relative_increment_verified"] is True
    assert assessment["relative_increment_passed"] is True
    assert assessment["material_newton_state_dependent_passed"] is False
    assert assessment["frozen_only_is_not_state_dependent_closure"] is False
    assert (
        "child_state_dependent_material_newton_gate_not_proven"
        in assessment["blockers"]
    )
    assert payload["status"] == "partial"


def test_g1_closure_assessment_requires_child_residual_and_increment_gates(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["full_load_direct_residual_passed"] is False
    assert assessment["relative_increment_verified"] is False
    assert assessment["relative_increment_passed"] is False
    assert assessment["material_newton_state_dependent_passed"] is True
    assert assessment["child_fallback_zero_passed"] is True
    assert "child_direct_residual_gate_not_passed" in assessment["blockers"]
    assert "child_relative_increment_gate_not_verified" in assessment["blockers"]
    assert payload["status"] == "partial"


def test_strict_hip_cli_does_not_require_allow_cpu_diagnostic(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: list[dict[str, object]] = []

    def mock_run_controller(*, checkpoint_npz, seed_probe_json, output_json, strict_hip_residual_engine, **_kwargs):
        called.append({
            "strict_hip_residual_engine": strict_hip_residual_engine,
            "output_json": output_json,
        })
        return {
            "status": "partial",
            "final_direct_residual_inf_n": 10.0,
            "controller": {"promotion_count": 0, "stop_reason": "no_steps"},
        }

    monkeypatch.setattr(alternating, "run_g1_alternating_newton_controller", mock_run_controller)

    seed_json = tmp_path / "seed.json"
    _write_seed(seed_json)
    checkpoint_npz = tmp_path / "seed.npz"

    exit_code = alternating.main([
        "--checkpoint-npz", str(checkpoint_npz),
        "--seed-probe-json", str(seed_json),
        "--output-json", str(tmp_path / "out.json"),
        "--strict-hip-residual-engine",
        "--row-batch-replay-backend", "hip_full_residual",
        "--global-krylov-batch-replay-backend", "hip_full_residual",
        "--max-cycles", "0",
    ])

    assert exit_code == 0
    assert len(called) == 1
    assert called[0]["strict_hip_residual_engine"] is True


def test_non_strict_cli_requires_allow_cpu_diagnostic(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: list[dict[str, object]] = []

    def mock_run_controller(**_kwargs):
        called.append({})
        return {
            "status": "partial",
            "final_direct_residual_inf_n": 10.0,
            "controller": {"promotion_count": 0, "stop_reason": "no_steps"},
        }

    monkeypatch.setattr(alternating, "run_g1_alternating_newton_controller", mock_run_controller)

    seed_json = tmp_path / "seed.json"
    _write_seed(seed_json)
    checkpoint_npz = tmp_path / "seed.npz"

    exit_code = alternating.main([
        "--checkpoint-npz", str(checkpoint_npz),
        "--seed-probe-json", str(seed_json),
        "--output-json", str(tmp_path / "out.json"),
        "--max-cycles", "0",
    ])

    assert exit_code == 2
    assert called == []


def test_non_strict_cli_allows_cpu_diagnostic_with_flag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: list[dict[str, object]] = []

    def mock_run_controller(strict_hip_residual_engine=False, **_kwargs):
        called.append({"strict_hip_residual_engine": strict_hip_residual_engine})
        return {
            "status": "partial",
            "final_direct_residual_inf_n": 10.0,
            "controller": {"promotion_count": 0, "stop_reason": "no_steps"},
        }

    monkeypatch.setattr(alternating, "run_g1_alternating_newton_controller", mock_run_controller)

    seed_json = tmp_path / "seed.json"
    _write_seed(seed_json)
    checkpoint_npz = tmp_path / "seed.npz"

    exit_code = alternating.main([
        "--checkpoint-npz", str(checkpoint_npz),
        "--seed-probe-json", str(seed_json),
        "--output-json", str(tmp_path / "out.json"),
        "--allow-cpu-diagnostic",
        "--max-cycles", "0",
    ])

    assert exit_code == 0
    assert len(called) == 1
    assert called[0]["strict_hip_residual_engine"] is False


def test_strict_hip_cli_with_cpu_row_backend_blocked_early(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: list[dict[str, object]] = []

    def mock_run_controller(**_kwargs):
        called.append({})
        return {}

    monkeypatch.setattr(alternating, "run_g1_alternating_newton_controller", mock_run_controller)

    seed_json = tmp_path / "seed.json"
    _write_seed(seed_json)
    checkpoint_npz = tmp_path / "seed.npz"

    exit_code = alternating.main([
        "--checkpoint-npz", str(checkpoint_npz),
        "--seed-probe-json", str(seed_json),
        "--output-json", str(tmp_path / "out.json"),
        "--strict-hip-residual-engine",
        "--row-batch-replay-backend", "cpu",
        "--global-krylov-batch-replay-backend", "hip_full_residual",
        "--max-cycles", "0",
    ])

    assert exit_code == 2
    assert called == []


def test_strict_hip_cli_with_cpu_global_backend_blocked_early(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called: list[dict[str, object]] = []

    def mock_run_controller(**_kwargs):
        called.append({})
        return {}

    monkeypatch.setattr(alternating, "run_g1_alternating_newton_controller", mock_run_controller)

    seed_json = tmp_path / "seed.json"
    _write_seed(seed_json)
    checkpoint_npz = tmp_path / "seed.npz"

    exit_code = alternating.main([
        "--checkpoint-npz", str(checkpoint_npz),
        "--seed-probe-json", str(seed_json),
        "--output-json", str(tmp_path / "out.json"),
        "--strict-hip-residual-engine",
        "--row-batch-replay-backend", "hip_full_residual",
        "--global-krylov-batch-replay-backend", "cpu",
        "--max-cycles", "0",
    ])

    assert exit_code == 2
    assert called == []


def test_g1_closure_uses_nested_child_gate_contract_when_top_level_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": False,
                                "relative_increment_gate_verified": False,
                                "relative_increment_gate_passed": False,
                                "fallback_zero_passed": False,
                            },
                            "child_residual_contract": {
                                "allow_frozen_shell_material_tangent_hip_replay": True,
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assert payload["controller"]["promotion_count"] == 1
    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is True
    assert assessment["full_load_direct_residual_passed"] is True
    assert assessment["relative_increment_verified"] is True
    assert assessment["relative_increment_passed"] is True
    assert assessment["material_newton_state_dependent_passed"] is True
    assert assessment["fallback_zero_passed"] is True
    assert assessment["child_fallback_zero_passed"] is True
    assert assessment["evidence_location"] is not None
    assert "::rows[" in assessment["evidence_location"]
    assert "->" in assessment["evidence_location"]
    assert assessment["blockers"] == []
    assert payload["status"] == "passed"


def test_g1_closure_nested_evidence_not_used_when_top_level_sufficient(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_frozen_shell_material_tangent_hip_replay": True,
                        "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                    "rows": [
                        {
                            "accepted": True,
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": False,
                                "fallback_zero_passed": False,
                            },
                            "child_residual_contract": {
                                "allow_frozen_shell_material_tangent_hip_replay": True,
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is True
    assert assessment["full_load_direct_residual_passed"] is True
    assert "::rows[" not in assessment["evidence_location"]


def test_g1_closure_nested_evidence_requires_child_receipt_path(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": True,
                                "relative_increment_gate_verified": True,
                                "relative_increment_gate_passed": True,
                                "fallback_zero_passed": True,
                            },
                            "child_residual_contract": {
                                "shell_material_tangent_residual_applied": True,
                                "allow_state_dependent_shell_material_tangent_hip_replay": True,
                                "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                                **_hip_residual_engine_contract(),
                            },
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["full_load_direct_residual_passed"] is False
    assert assessment["relative_increment_verified"] is False
    assert assessment["material_newton_state_dependent_passed"] is False
    assert "child_direct_residual_gate_not_passed" in assessment["blockers"]
    assert "child_state_dependent_material_newton_gate_not_proven" in assessment["blockers"]
    assert payload["status"] == "partial"


def test_g1_closure_nested_frozen_only_contract_blocks_closure(
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
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": True,
                                "relative_increment_gate_verified": True,
                                "relative_increment_gate_passed": True,
                                "fallback_zero_passed": True,
                            },
                            "child_residual_contract": {
                                "shell_material_tangent_residual_applied": True,
                                "allow_frozen_shell_material_tangent_hip_replay": True,
                                "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure": True,
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_frozen_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["material_newton_state_dependent_passed"] is False
    assert assessment["frozen_only_is_not_state_dependent_closure"] is True
    assert (
        "child_state_dependent_material_newton_gate_not_proven"
        in assessment["blockers"]
    )
    assert payload["status"] == "partial"


def test_g1_closure_uses_latest_accepted_nested_row_with_both_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "promoted_rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": False,
                                "fallback_zero_passed": True,
                            },
                            "child_residual_contract": {
                                "shell_material_tangent_residual_applied": True,
                                "allow_state_dependent_shell_material_tangent_hip_replay": True,
                                "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                                **_hip_residual_engine_contract(),
                            },
                        },
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": True,
                                "relative_increment_gate_verified": True,
                                "relative_increment_gate_passed": True,
                                "fallback_zero_passed": True,
                            },
                            "child_residual_contract": {
                                "shell_material_tangent_residual_applied": True,
                                "allow_state_dependent_shell_material_tangent_hip_replay": True,
                                "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                                **_hip_residual_engine_contract(),
                            },
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is True
    assert assessment["full_load_direct_residual_passed"] is True
    assert assessment["relative_increment_verified"] is True
    assert assessment["material_newton_state_dependent_passed"] is True
    assert assessment["evidence_location"] is not None
    assert "::promoted_rows[1]" in assessment["evidence_location"]
    assert "->" in assessment["evidence_location"]


def test_g1_closure_falls_back_to_rows_when_promoted_rows_lack_nested_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                    "residual_contract": {
                        "shell_material_tangent_residual_applied": True,
                        "allow_state_dependent_shell_material_tangent_hip_replay": True,
                        "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                        **_hip_residual_engine_contract(),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "promoted_rows": [
                        {"accepted": True, "summary_only": True},
                    ],
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": True,
                                "relative_increment_gate_verified": True,
                                "relative_increment_gate_passed": True,
                                "fallback_zero_passed": True,
                            },
                            "child_residual_contract": {
                                "shell_material_tangent_residual_applied": True,
                                "allow_state_dependent_shell_material_tangent_hip_replay": True,
                                "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                                **_hip_residual_engine_contract(),
                            },
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
        allow_state_dependent_shell_material_tangent_hip_replay=True,
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is True
    assert assessment["evidence_location"] is not None
    assert "::rows[0]" in assessment["evidence_location"]
    assert "->" in assessment["evidence_location"]


def test_g1_closure_nested_evidence_not_triggered_when_no_both_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def completed_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        nested_direct = output_path.with_name(f"{output_path.stem}_direct.json")
        nested_direct.write_text(
            json.dumps(
                {
                    "gate_assessment": {
                        "direct_residual_gate_passed": True,
                        "relative_increment_gate_verified": True,
                        "relative_increment_gate_passed": True,
                        "fallback_zero_passed": True,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                    "gate_assessment": {"fallback_zero_passed": True},
                    "rows": [
                        {
                            "accepted": True,
                            "child_receipt_path": str(nested_direct),
                            "child_gate_assessment": {
                                "direct_residual_gate_passed": True,
                                "relative_increment_gate_verified": True,
                                "relative_increment_gate_passed": True,
                                "fallback_zero_passed": True,
                            },
                            "child_residual_contract": {
                                "shell_material_tangent_residual_applied": True,
                                "allow_state_dependent_shell_material_tangent_hip_replay": True,
                                "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency": True,
                                **_hip_residual_engine_contract(),
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)
    _patch_available_hip(monkeypatch)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("global_krylov",),
        strict_hip_residual_engine=True,
        row_batch_replay_backend="hip_full_residual",
        global_krylov_batch_replay_backend="hip_full_residual_resident",
    )

    assessment = payload["g1_closure_assessment"]
    assert assessment["g1_closure_claimed"] is False
    assert assessment["relative_increment_verified"] is False
    assert assessment["material_newton_state_dependent_passed"] is False
    assert "child_relative_increment_gate_not_verified" in assessment["blockers"]
    assert "child_state_dependent_material_newton_gate_not_proven" in assessment["blockers"]


def test_alternating_controller_propagates_row_support_selection_to_child(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("row_fd_component",),
        row_support_selection="target_rows",
    )

    assert payload["controller"]["row_support_selection"] == "target_rows"
    assert len(commands) == 1
    row_command = commands[0]
    assert "--current-tangent-residual-row-support-selection" not in row_command
    assert "--row-support-selection" in row_command
    support_selection_index = row_command.index("--row-support-selection")
    assert row_command[support_selection_index + 1] == "target_rows"


def test_alternating_controller_default_row_support_selection_is_row_strongest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def completed_run(command, **_kwargs):
        commands.append(command)
        output_path = Path(command[command.index("--output-json") + 1])
        checkpoint_path = Path(
            command[command.index("--output-final-checkpoint-npz") + 1]
        )
        checkpoint_path.write_bytes(b"checkpoint")
        output_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "final_direct_residual_inf_n": 9.0,
                    "controller": {"promotion_count": 1},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return alternating.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(alternating.subprocess, "run", completed_run)

    payload = alternating.run_g1_alternating_newton_controller(
        checkpoint_npz=tmp_path / "seed.npz",
        seed_probe_json=_write_seed(tmp_path / "seed.json"),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        max_cycles=1,
        lane_sequence=("row_fd_component",),
    )

    assert payload["controller"]["row_support_selection"] == "row_strongest"
    assert len(commands) == 1
    row_command = commands[0]
    assert "--current-tangent-residual-row-support-selection" not in row_command
    assert "--row-support-selection" in row_command
    support_selection_index = row_command.index("--row-support-selection")
    assert row_command[support_selection_index + 1] == "row_strongest"
