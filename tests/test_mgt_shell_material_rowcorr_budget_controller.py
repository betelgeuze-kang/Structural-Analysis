from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_shell_material_rowcorr_budget_controller as controller  # noqa: E402


def _hip_residual_engine_contract() -> dict[str, object]:
    return {
        "hip_residual_engine_contract_passed": True,
        "hip_residual_engine_required": True,
        "hip_residual_engine_required_lane_count": 1,
        "hip_residual_engine_passed_lane_count": 1,
        "hip_residual_engine_backends": ["hip_full_residual"],
        "hip_residual_engine_blockers": [],
    }


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
                    "gate_assessment": {"fallback_zero_passed": True},
                    "residual_contract": _hip_residual_engine_contract(),
                    "claim_boundary": (
                        "Frozen shell-material tangent HIP replay is not "
                        "state-dependent material Newton closure."
                    ),
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
        row_target_mode="current_component_rows",
        row_frontier_component_scale_mode="dominant_component_magnitude",
        row_jacobian_mode="finite_difference",
        row_support_selection="target_rows",
        row_fd_max_support_columns=16,
        row_batch_fd_replay=True,
        row_batch_fd_replay_chunk_size=32,
        row_batch_replay_backend="hip_full_residual",
        row_require_hip_batch_replay=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        row_use_residual_only_assembly=True,
        row_batch_alpha_replay=True,
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
    assert "--current-tangent-residual-row-target-mode" in row["subprocess_command"]
    assert "current_component_rows" in row["subprocess_command"]
    assert "--current-tangent-residual-row-frontier-component-scale-mode" in row[
        "subprocess_command"
    ]
    assert "dominant_component_magnitude" in row["subprocess_command"]
    assert "--current-tangent-residual-row-jacobian-mode" in row["subprocess_command"]
    assert "finite_difference" in row["subprocess_command"]
    assert "--current-tangent-residual-row-support-selection" in row[
        "subprocess_command"
    ]
    assert "target_rows" in row["subprocess_command"]
    assert "--current-tangent-residual-row-batch-fd-replay" in row[
        "subprocess_command"
    ]
    assert "--current-tangent-residual-row-batch-replay-backend" in row[
        "subprocess_command"
    ]
    assert "hip_full_residual" in row["subprocess_command"]
    assert "--current-tangent-residual-row-require-hip-batch-replay" in row[
        "subprocess_command"
    ]
    assert "--allow-frozen-shell-material-tangent-hip-replay" in row[
        "subprocess_command"
    ]
    assert "--current-tangent-residual-row-use-residual-only-assembly" in row[
        "subprocess_command"
    ]
    assert "--current-tangent-residual-row-batch-alpha-replay" in row[
        "subprocess_command"
    ]
    assert row["row_target_mode"] == "current_component_rows"
    assert row["row_jacobian_mode"] == "finite_difference"
    assert row["row_support_selection"] == "target_rows"
    assert payload["controller"]["row_target_mode"] == "current_component_rows"
    assert payload["controller"]["row_support_selection"] == "target_rows"
    assert payload["controller"]["row_batch_fd_replay"] is True
    assert payload["controller"]["row_batch_replay_backend"] == "hip_full_residual"
    assert payload["controller"]["row_require_hip_batch_replay"] is True
    assert (
        payload["controller"]["allow_frozen_shell_material_tangent_hip_replay"]
        is True
    )
    assert payload["controller"]["preflight_blockers"] == []
    assert payload["claim_boundary"]["cpu_diagnostic_only"] is True
    assert payload["claim_boundary"]["official_rocm_hip_closure_required"] is True
    assert payload["promoted_rows"] == [row]
    assert payload["controller"]["promotion_count"] == 1
    assert payload["controller"]["stop_reason"] == "candidate_promoted"
    assert payload["final_direct_residual_inf_n"] == 13.0
    assert final_checkpoint.read_bytes() == b"checkpoint"


def test_shell_material_rowcorr_budget_blocks_hip_required_material_tangent_before_child(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_run(*_args, **_kwargs):
        raise AssertionError("HIP-required material tangent preflight must not launch a child")

    monkeypatch.setattr(controller.subprocess, "run", fail_run)

    payload = controller.run_shell_material_rowcorr_budget_controller(
        seed_probe_json=_write_seed(tmp_path / "seed.json", final_residual=14.0),
        output_json=tmp_path / "controller.json",
        child_output_dir=tmp_path / "children",
        row_batch_replay_backend="hip_full_residual",
        row_require_hip_batch_replay=True,
        row_batch_fd_replay=True,
        row_use_residual_only_assembly=True,
        row_batch_alpha_replay=True,
    )

    assert payload["controller"]["promotion_count"] == 0
    assert (
        payload["controller"]["stop_reason"]
        == "hip_required_shell_material_tangent_backend_unavailable"
    )
    assert payload["controller"]["preflight_blockers"] == [
        "hip_required_shell_material_tangent_batch_backend_unavailable"
    ]
    assert payload["rows"] == []
    assert payload["final_direct_residual_inf_n"] == 14.0
    assert payload["claim_boundary"]["hip_required_material_tangent_backend_available"] is False


def test_shell_material_rowcorr_hip_required_missing_residual_contract_blocks_promotion(
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
                    "base_direct_residual": {"direct_residual_inf_n": 14.0},
                    "final_direct_residual": {"direct_residual_inf_n": 13.0},
                    "current_tangent_residual_row_correction": {
                        "accepted": True,
                        "promotion_count": 1,
                        "stop_reason": "max_promotions_exhausted",
                    },
                    "gate_assessment": {"fallback_zero_passed": True},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return controller.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(controller.subprocess, "run", completed_run)

    payload = controller.run_shell_material_rowcorr_budget_controller(
        seed_probe_json=_write_seed(tmp_path / "seed.json", final_residual=14.0),
        output_json=tmp_path / "controller.json",
        output_final_checkpoint_npz=tmp_path / "final.npz",
        child_output_dir=tmp_path / "children",
        python_exe=tmp_path / "python",
        row_batch_replay_backend="hip_full_residual",
        row_require_hip_batch_replay=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        row_batch_fd_replay=True,
        row_use_residual_only_assembly=True,
        row_batch_alpha_replay=True,
        write_child_checkpoints=True,
        child_timeout_seconds=1.0,
    )

    row = payload["rows"][0]
    assert row["accepted"] is False
    assert row["row_correction_accepted"] is True
    assert row["child_hip_residual_engine_contract_passed"] is False
    assert "child_hip_residual_engine_contract_not_proven" in row[
        "child_strict_hip_promotion_blockers"
    ]
    assert payload["promoted_rows"] == []
    assert payload["controller"]["promotion_count"] == 0
    assert payload["final_direct_residual_inf_n"] == 14.0
    assert not (tmp_path / "final.npz").exists()


def test_shell_material_rowcorr_state_dependent_flag_allows_hip_child(
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
                    "base_direct_residual": {"direct_residual_inf_n": 10.0},
                    "final_direct_residual": {"direct_residual_inf_n": 9.0},
                    "current_tangent_residual_row_correction": {
                        "accepted": True,
                        "promotion_count": 1,
                        "stop_reason": "max_promotions_exhausted",
                    },
                    "gate_assessment": {"fallback_zero_passed": True},
                    "residual_contract": _hip_residual_engine_contract(),
                    "claim_boundary": (
                        "State-dependent shell-material tangent HIP replay computes "
                        "candidate state tangent but host operator refresh is not full "
                        "production ROCm/HIP residency closure."
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return controller.subprocess.CompletedProcess(
            command, 0, stdout="", stderr="",
        )

    monkeypatch.setattr(controller.subprocess, "run", completed_run)

    payload = controller.run_shell_material_rowcorr_budget_controller(
        seed_probe_json=_write_seed(tmp_path / "seed.json", final_residual=10.0),
        output_json=tmp_path / "controller.json",
        output_final_checkpoint_npz=tmp_path / "final.npz",
        child_output_dir=tmp_path / "children",
        row_target_counts=(1,),
        row_support_column_counts=(4,),
        row_alpha_values=(0.015625,),
        row_batch_replay_backend="hip_full_residual",
        row_require_hip_batch_replay=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        row_batch_fd_replay=True,
        row_use_residual_only_assembly=True,
        row_batch_alpha_replay=True,
        write_child_checkpoints=True,
        child_timeout_seconds=1.0,
    )

    assert payload["controller"]["preflight_blockers"] == []
    assert (
        payload["controller"][
            "allow_state_dependent_shell_material_tangent_hip_replay"
        ]
        is True
    )
    assert payload["controller"]["promotion_count"] == 1
    assert commands
    command = commands[0]
    assert "--allow-state-dependent-shell-material-tangent-hip-replay" in command
    assert "--allow-frozen-shell-material-tangent-hip-replay" not in command


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


def test_shell_material_rowcorr_budget_rejects_hip_required_with_cpu_backend(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="row_require_hip_batch_replay"):
        controller.run_shell_material_rowcorr_budget_controller(
            seed_probe_json=_write_seed(tmp_path / "seed.json"),
            output_json=tmp_path / "controller.json",
            row_require_hip_batch_replay=True,
            row_batch_replay_backend="cpu",
        )


def test_cli_rejects_hip_required_without_hip_backend(capsys) -> None:
    result = controller.main([
        "--allow-cpu-diagnostic",
        "--row-require-hip-batch-replay",
    ])
    captured = capsys.readouterr()
    assert result == 2
    assert "row_require_hip_batch_replay" in captured.err


def test_shell_rowcorr_no_preflight_blocker_hip_non_conservative_boundary(
) -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": None,
                "child_blockers": [],
                "child_residual_contract": _hip_residual_engine_contract(),
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is False
    assert claim["official_rocm_hip_closure_required"] is False
    assert claim["hip_required_material_tangent_backend_available"] is True
    assert claim["rocm_hip_runtime_available"] is True


def test_shell_rowcorr_claim_boundary_reflects_child_hip_runtime_unavailable() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
        runtime_budget_exceeded=False,
        promoted_rows=[],
        rows=[
            {
                "child_blockers": ["rocm_hip_runtime_unavailable"],
                "child_residual_contract": {
                    "hip_residual_engine_blockers": [
                        "rocm_hip_runtime_unavailable"
                    ],
                },
                "child_gate_assessment": {
                    "rocm_hip_runtime_available": False,
                },
            }
        ],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True
    assert claim["hip_required_material_tangent_backend_available"] is False
    assert claim["rocm_hip_runtime_available"] is False


def test_shell_rowcorr_conservative_boundary_on_child_claim_boundary() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": {
                    "cpu_diagnostic_only": False,
                    "official_rocm_hip_closure_required": True,
                },
                "child_blockers": [],
                "child_residual_contract": _hip_residual_engine_contract(),
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_shell_rowcorr_conservative_boundary_on_child_strict_blocker() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": None,
                "child_blockers": ["row_correction_cpu_batch_replay_fallback_suppressed"],
                "child_residual_contract": _hip_residual_engine_contract(),
            }
        ],
        rows=[],
    )

    assert claim["cpu_diagnostic_only"] is True
    assert claim["official_rocm_hip_closure_required"] is True


def test_shell_rowcorr_residual_contract_state_dependent_allows_non_conservative() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
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


def test_shell_rowcorr_residual_contract_frozen_without_state_dependent_stays_conservative() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
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


def test_shell_rowcorr_residual_contract_missing_stays_conservative() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
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


def test_shell_rowcorr_residual_contract_does_not_bypass_rocm_hip_blocker() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": None,
                "child_blockers": ["rocm_hip_krylov_not_available"],
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


def test_shell_rowcorr_residual_contract_does_not_bypass_explicit_unavailable_blocker() -> None:
    claim = controller._build_shell_rowcorr_claim_boundary(
        require_hip=True,
        backend_is_hip=True,
        preflight_blockers_exist=False,
        runtime_budget_exceeded=False,
        promoted_rows=[
            {
                "child_gate_assessment": {"fallback_zero_passed": True},
                "child_claim_boundary": None,
                "child_blockers": ["hip_krylov_solver_required_unavailable"],
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
