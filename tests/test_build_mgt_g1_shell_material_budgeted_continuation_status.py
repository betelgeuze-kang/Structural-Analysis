from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_mgt_g1_shell_material_budgeted_continuation_status.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_mgt_g1_shell_material_budgeted_continuation_status",
    SCRIPT_PATH,
)
assert SPEC is not None
build_mgt_g1_shell_material_budgeted_continuation_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_mgt_g1_shell_material_budgeted_continuation_status)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _direct_probe(path: Path, *, base: float, final: float) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": base},
            "final_direct_residual": {
                "direct_residual_inf_n": final,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 1,
            },
        },
    )


def _controller_receipt(path: Path, *, initial: float, final: float) -> Path:
    checkpoint = path.with_suffix(".npz")
    checkpoint.write_bytes(b"compact")
    child = path.parent / f"{path.stem}_child.json"
    _write_json(
        child,
        {
            "promotion_passes": [
                {"actual_direct_residual_inf_n": (initial + final) / 2.0},
                {"actual_direct_residual_inf_n": final},
            ]
        },
    )
    return _write_json(
        path,
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "initial_frontier_direct_residual_inf_n": initial,
            "final_direct_residual_inf_n": final,
            "final_checkpoint_path": str(checkpoint),
            "controller": {
                "promotion_count": 1,
                "max_row_promotions_per_child": 2,
                "stop_reason": "candidate_promoted",
                "runtime_budget_exceeded": False,
                "compact_child_checkpoints": True,
            },
            "rows": [{"child_receipt_path": str(child)}],
            "promoted_rows": [{"child_receipt_path": str(child)}],
        },
    )


def _adaptive_global_krylov_receipt(
    path: Path, *, initial: float, final: float, checkpoint_name: str, compact: bool
) -> Path:
    checkpoint = path.parent / checkpoint_name
    checkpoint.write_bytes(b"compact")
    child = path.parent / f"{path.stem}_child.json"
    _write_json(
        child,
        {
            "promotion_passes": [
                {"actual_direct_residual_inf_n": (initial + final) / 2.0},
                {"actual_direct_residual_inf_n": final},
            ]
        },
    )
    return _write_json(
        path,
        {
            "schema_version": "mgt-direct-residual-adaptive-preconditioned-global-newton.v1",
            "status": "partial",
            "final_direct_residual_inf_n": final,
            "final_checkpoint_path": str(checkpoint),
            "controller": {
                "promotion_count": 1,
                "max_controller_steps": 1,
                "stop_reason": "max_controller_steps_reached",
                "runtime_budget_exceeded": False,
                "compact_output_final_checkpoint": compact,
            },
            "rows": [
                {
                    "child_receipt_path": str(child),
                    "base_direct_residual_inf_n": initial,
                    "final_direct_residual_inf_n": final,
                }
            ],
            "promoted_rows": [
                {
                    "child_receipt_path": str(child),
                    "base_direct_residual_inf_n": initial,
                    "final_direct_residual_inf_n": final,
                }
            ],
        },
    )


def _strict_hip_non_promoting_receipt(path: Path, *, residual: float) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "mgt-g1-alternating-newton-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": residual,
            "final_checkpoint_path": str(path.with_suffix(".npz")),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "strict_hip_runtime_unavailable",
                "runtime_budget_exceeded": False,
                "strict_hip_runtime_preflight": {
                    "available": False,
                    "reason": "torch_hip_device_unavailable",
                },
            },
            "claim_boundary": {
                "g1_closure_claimed": False,
                "strict_hip_runtime_preflight_passed": False,
            },
        },
    )


def _hip_row_backend_summary(
    path: Path,
    *,
    base: float,
    final: float,
    gate: float,
    production_claimed: bool = False,
) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "mgt-direct-residual-hip-largest-rows-summary.v1",
            "status": "ready" if production_claimed else "partial",
            "residual_gate_n": gate,
            "claim_boundary": (
                "Production in-process ROCm/HIP residency claimed."
                if production_claimed
                else "Residual descent evidence only. This does not claim final residual gate "
                "closure, full-load path closure, or production in-process ROCm/HIP residency."
            ),
            "cumulative_from_followup69": {
                "base_direct_residual_inf_n": base,
                "final_direct_residual_inf_n": final,
            },
            "assessment": "bounded HIP row backend summary",
            "next_solver_step": "switch to a stronger coupled node/shell/frame controller",
        },
    )


def _consistent_residual_jacobian_audit_summary(
    path: Path,
    *,
    residual: float,
    margin: float,
) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "mgt-residual-jacobian-physical-audit-summary.v1",
            "status": "partial",
            "followup86_hotspot_jvp_audit": {
                "status": "ready",
                "residual_jacobian_consistency_ready": True,
                "assessment": "checked hotspot directions match finite-difference JVPs",
            },
            "latest_residual_state": {
                "direct_residual_inf_n": residual,
                "remaining_residual_margin_to_gate_n": margin,
            },
            "next_solver_step": "switch to a production Newton path",
            "claim_boundary": (
                "Physical residual/Jacobian audit evidence only. It does not claim "
                "residual gate closure, full-load path closure, or production "
                "in-process ROCm/HIP residency."
            ),
        },
    )


def _cached_residual_jvp_summary(path: Path, *, residual: float, margin: float) -> Path:
    checkpoint = "cached_jvp_latest_checkpoint.npz"
    return _write_json(
        path,
        {
            "schema_version": "mgt-cached-residual-jvp-multi-ridge-controller.v1",
            "status": "partial",
            "latest_direct_residual_inf_n": residual,
            "remaining_residual_margin_to_gate_n": margin,
            "residual_gate_n": 0.001,
            "latest_checkpoint": checkpoint,
            "start_checkpoint": "cached_jvp_start_checkpoint.npz",
            "configuration": {"retain_latest_checkpoint_only": True},
            "steps": [
                {
                    "basis_npz": "cached_jvp_latest_probe.npz",
                    "checkpoint": checkpoint,
                    "checkpoint_retained": True,
                    "promoted": True,
                }
            ],
            "claim_boundary": (
                "Controller convenience for cached residual/JVP multi-ridge probes only. "
                "It does not claim residual gate closure or production ROCm/HIP residency."
            ),
        },
    )


def test_shell_material_status_counts_latest_completed_frontier_and_launch_only_receipt(tmp_path: Path) -> None:
    productization = tmp_path / "productization"
    chain = (
        "base.json",
        "seed.json",
        "followup389.json",
    )
    _direct_probe(productization / "base.json", base=19.0, final=18.0)
    _direct_probe(productization / "seed.json", base=18.0, final=10.0)
    _controller_receipt(productization / "followup389.json", initial=10.0, final=8.0)
    _write_json(
        productization / "followup390_child.json",
        {"schema_version": "launch.v1", "status": "in_progress"},
    )
    _strict_hip_non_promoting_receipt(productization / "followup400.json", residual=8.0)

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=chain,
        counter_receipts=(),
        launch_receipts=("followup390_child.json", "followup400.json"),
        direct_residual_tolerance_n=5.0e-4,
    )

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is True
    assert (
        payload["reuse_policy"]
        == "status_rebuilt_from_existing_g1_shell_material_direct_residual_receipts"
    )
    assert payload["input_checksums"][str(productization / "base.json")].startswith("sha256:")
    assert payload["input_checksums"][str(productization / "seed.json")].startswith("sha256:")
    assert payload["input_checksums"][str(productization / "followup389.json")].startswith("sha256:")
    assert payload["input_checksums"][str(productization / "followup390_child.json")].startswith("sha256:")
    assert payload["direct_residual_gate_passed"] is False
    assert payload["latest_frontier_receipt"] == "followup389.json"
    assert payload["latest_frontier_compact_checkpoint"].endswith("followup389.npz")
    assert payload["latest_frontier_compact_checkpoint_exists"] is True
    assert payload["latest_frontier_direct_residual_inf_n"] == 8.0
    assert payload["residual_gap_to_tolerance_n"] == 8.0 - 5.0e-4
    assert payload["residual_gap_ratio_to_tolerance"] == 8.0 / 5.0e-4
    assert payload["frontier_chain_monotonic_nonincreasing"] is True
    assert payload["frontier_improvement_inf_n"] == 10.0
    assert payload["frontier_chain"][-1]["compact_checkpoint_exists"] is True
    assert payload["frontier_chain"][-1]["controller"]["internal_pass_finals_n"][-1] == 8.0
    assert payload["non_promoting_launch_receipts"][0]["counted_in_frontier"] is False
    assert payload["non_promoting_launch_receipts"][1]["counted_in_frontier"] is False
    assert (
        payload["non_promoting_launch_receipts"][1]["controller_stop_reason"]
        == "strict_hip_runtime_unavailable"
    )
    assert payload["non_promoting_launch_receipts"][1]["strict_hip_runtime_available"] is False
    assert payload["non_promoting_launch_receipts"][1]["direct_residual_inf_n"] == 8.0
    assert payload["same_operator_repetition_exhausted"] is False
    assert payload["same_operator_no_descent_receipts"] == []
    assert "followup389.npz" in payload["next_actions"][0]
    assert "followup389.json" in payload["next_actions"][0]
    assert "direct_residual_gate_not_closed" in payload["blockers"]


def test_shell_material_status_blocks_missing_checkpoint_and_nonmonotonic_chain(tmp_path: Path) -> None:
    productization = tmp_path / "productization"
    _direct_probe(productization / "base.json", base=4.0, final=3.0)
    _write_json(
        productization / "bad.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "initial_frontier_direct_residual_inf_n": 3.0,
            "final_direct_residual_inf_n": 3.5,
            "final_checkpoint_path": str(productization / "missing.npz"),
            "controller": {"promotion_count": 0},
        },
    )

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=("base.json", "bad.json"),
        counter_receipts=(),
        launch_receipts=(),
        direct_residual_tolerance_n=5.0e-4,
    )

    assert payload["frontier_chain_monotonic_nonincreasing"] is False
    assert payload["compact_checkpoint_ready"] is False
    assert "frontier_residual_not_monotonic" in payload["blockers"]
    assert "compact_checkpoint_missing" in payload["blockers"]


def test_shell_material_status_uses_controller_child_row_base_fallback(tmp_path: Path) -> None:
    productization = tmp_path / "productization"
    _direct_probe(productization / "base.json", base=9.0, final=8.0)
    checkpoint = productization / "controller.npz"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"compact")
    _write_json(
        productization / "controller.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "initial_frontier_direct_residual_inf_n": None,
            "final_direct_residual_inf_n": 7.0,
            "final_checkpoint_path": str(checkpoint),
            "rows": [{"base_direct_residual_inf_n": 8.0}],
            "controller": {"promotion_count": 1},
        },
    )

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=("base.json", "controller.json"),
        counter_receipts=(),
        launch_receipts=(),
    )

    assert payload["frontier_chain"][-1]["base_direct_residual_inf_n"] == 8.0
    assert payload["frontier_chain"][-1]["direct_residual_inf_n"] == 7.0


def test_shell_material_status_prefers_controller_best_candidate_base_over_seed(
    tmp_path: Path,
) -> None:
    productization = tmp_path / "productization"
    checkpoint = productization / "controller.npz"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"compact")
    _write_json(
        productization / "controller.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "initial_frontier_direct_residual_inf_n": 14.9,
            "final_direct_residual_inf_n": 5.3,
            "final_checkpoint_path": str(checkpoint),
            "controller": {"promotion_count": 1},
            "best_candidate_row": {"base_direct_residual_inf_n": 5.7},
            "rows": [{"base_direct_residual_inf_n": 5.7}],
            "promoted_rows": [{"base_direct_residual_inf_n": 5.7}],
        },
    )

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=("controller.json",),
        counter_receipts=(),
        launch_receipts=(),
    )

    assert payload["frontier_chain"][-1]["base_direct_residual_inf_n"] == 5.7
    assert payload["frontier_chain"][-1]["direct_residual_inf_n"] == 5.3


def test_shell_material_status_extends_chain_with_adaptive_global_krylov_and_rowcorr_followups(
    tmp_path: Path,
) -> None:
    productization = tmp_path / "productization"
    _direct_probe(productization / "base.json", base=12.0, final=11.0)
    _adaptive_global_krylov_receipt(
        productization / "followup396.json",
        initial=11.0,
        final=6.117776861921165,
        checkpoint_name="followup396_final_checkpoint.npz",
        compact=False,
    )
    _adaptive_global_krylov_receipt(
        productization / "followup397.json",
        initial=6.117776861921165,
        final=6.117752205061414,
        checkpoint_name="followup397_final_checkpoint.npz",
        compact=True,
    )
    _controller_receipt(
        productization / "followup398.json",
        initial=6.117752205061414,
        final=5.74426714604332,
    )
    _controller_receipt(
        productization / "followup401.json",
        initial=5.74426714604332,
        final=5.393578678157873,
    )
    _controller_receipt(
        productization / "followup402.json",
        initial=5.393578678157873,
        final=5.064299859094071,
    )
    _controller_receipt(
        productization / "followup403.json",
        initial=5.064299859094071,
        final=4.985171267567502,
    )
    _controller_receipt(
        productization / "followup405.json",
        initial=4.985171267567502,
        final=4.7551275786384295,
    )

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=(
            "base.json",
            "followup396.json",
            "followup397.json",
            "followup398.json",
            "followup401.json",
            "followup402.json",
            "followup403.json",
            "followup405.json",
        ),
        counter_receipts=(),
        launch_receipts=(),
        direct_residual_tolerance_n=5.0e-4,
    )

    assert payload["frontier_chain_monotonic_nonincreasing"] is True
    assert payload["latest_frontier_receipt"] == "followup405.json"
    assert payload["latest_frontier_direct_residual_inf_n"] == 4.7551275786384295
    assert payload["residual_gap_to_tolerance_n"] == 4.7551275786384295 - 5.0e-4
    assert payload["frontier_chain"][-1]["compact_checkpoint_exists"] is True
    assert payload["frontier_chain"][-7]["checkpoint_compact"] is False
    assert payload["frontier_chain"][-1]["checkpoint_compact"] is True
    assert payload["latest_frontier_checkpoint_compact"] is True
    assert payload["storage_policy"]["latest_frontier_checkpoint_compact"] is True
    assert payload["storage_policy"]["frontier_chain_full_history_checkpoint_present"] is True
    assert payload["storage_policy"]["full_history_checkpoint_avoided"] is False
    assert payload["frontier_chain"][-6]["schema_version"] == (
        "mgt-direct-residual-adaptive-preconditioned-global-newton.v1"
    )
    assert payload["frontier_chain"][-1]["schema_version"] == (
        "mgt-shell-material-rowcorr-budget-controller.v1"
    )
    assert payload["frontier_chain"][-1]["base_direct_residual_inf_n"] == 4.985171267567502
    assert payload["frontier_chain"][-1]["direct_residual_inf_n"] == 4.7551275786384295
    assert "direct_residual_gate_not_closed" in payload["blockers"]
    assert "full_mesh_nonlinear_equilibrium_not_closed" in payload["blockers"]
    assert "production_rocm_hip_residual_row_backend_not_closed" in payload["blockers"]
    assert "consistent_residual_jacobian_newton_not_closed" in payload["blockers"]


def test_shell_material_status_summarizes_hip_row_backend_as_nonclosing_evidence(
    tmp_path: Path,
) -> None:
    productization = tmp_path / "productization"
    _direct_probe(productization / "base.json", base=2.0, final=1.0)
    _hip_row_backend_summary(
        productization / "hip67.json",
        base=0.034,
        final=0.0339,
        gate=0.001,
    )
    _hip_row_backend_summary(
        productization / "hip74.json",
        base=0.0339,
        final=0.03346553206631597,
        gate=0.001,
    )

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=("base.json",),
        counter_receipts=(),
        launch_receipts=(),
        hip_residual_row_backend_receipts=("hip67.json", "hip74.json"),
        direct_residual_tolerance_n=5.0e-4,
    )

    hip_backend = payload["hip_residual_row_backend"]
    assert hip_backend["contract_pass"] is False
    assert hip_backend["latest_receipt"] == "hip74.json"
    assert hip_backend["latest_final_direct_residual_inf_n"] == 0.03346553206631597
    assert hip_backend["latest_residual_gate_n"] == 0.001
    assert hip_backend["latest_residual_gap_ratio_to_gate"] == 33.46553206631597
    assert hip_backend["receipts"][-1]["production_residency_claimed"] is False
    assert hip_backend["receipts"][-1]["blocking_reasons"] == [
        "residual_gate_not_closed",
        "production_in_process_rocm_hip_residency_not_claimed",
    ]
    assert "production_rocm_hip_residual_row_backend_not_closed" in payload["blockers"]


def test_shell_material_status_summarizes_consistent_jacobian_as_nonclosing_evidence(
    tmp_path: Path,
) -> None:
    productization = tmp_path / "productization"
    _direct_probe(productization / "base.json", base=2.0, final=1.0)
    _write_json(
        productization / "component_probe.json",
        {
            "schema_version": "mgt-residual-jacobian-consistency-probe.v1",
            "status": "partial",
            "residual_jacobian_consistency_ready": False,
            "component_only": True,
            "base_residual_inf_n": 0.034,
            "blockers": ["component_only_diagnostic_not_consistency_closure"],
            "claim_boundary": (
                "Full-model diagnostic comparing assembled tangent K*d against "
                "finite-difference physical residual action dR/du*d. This is not "
                "a nonlinear equilibrium closure."
            ),
        },
    )
    _consistent_residual_jacobian_audit_summary(
        productization / "physical_audit.json",
        residual=0.033465481263974306,
        margin=0.032465481263974305,
    )
    _cached_residual_jvp_summary(
        productization / "cached_jvp_latest.json",
        residual=0.033136466982157,
        margin=0.032136466982157,
    )

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=("base.json",),
        counter_receipts=(),
        launch_receipts=(),
        hip_residual_row_backend_receipts=(),
        consistent_residual_jacobian_receipts=(
            "component_probe.json",
            "physical_audit.json",
            "cached_jvp_latest.json",
        ),
        direct_residual_tolerance_n=5.0e-4,
    )

    consistency = payload["consistent_residual_jacobian_newton"]
    assert consistency["contract_pass"] is False
    assert consistency["latest_receipt"] == "cached_jvp_latest.json"
    assert consistency["latest_status"] == "partial"
    assert consistency["latest_residual_jacobian_consistency_ready"] is False
    assert consistency["latest_component_only"] is False
    assert (
        consistency["latest_remaining_residual_margin_to_gate_n"]
        == 0.032136466982157
    )
    assert consistency["latest_checkpoint"] == "cached_jvp_latest_checkpoint.npz"
    assert consistency["latest_checkpoint_exists"] is False
    assert consistency["controller_start_checkpoint"] == "cached_jvp_start_checkpoint.npz"
    assert consistency["controller_start_checkpoint_exists"] is False
    assert consistency["latest_checkpoint_retained_by_summary"] is True
    assert consistency["latest_checkpoint_promoted_by_summary"] is True
    assert consistency["advertised_retained_checkpoint_missing"] is True
    assert consistency["missing_controller_replay_artifact_count"] == 3
    assert consistency["missing_controller_replay_artifacts"] == [
        {
            "role": "controller_start_checkpoint",
            "path": "cached_jvp_start_checkpoint.npz",
        },
        {
            "role": "retained_latest_checkpoint",
            "path": "cached_jvp_latest_checkpoint.npz",
        },
        {"role": "step_basis_npz", "path": "cached_jvp_latest_probe.npz"},
    ]
    assert consistency["restart_ready"] is False
    assert consistency["restart_blockers"] == [
        "latest_checkpoint_missing",
        "advertised_retained_checkpoint_missing",
        "controller_start_checkpoint_missing",
        "controller_replay_artifacts_missing",
    ]
    regeneration_feasibility = consistency["regeneration_feasibility"]
    assert (
        regeneration_feasibility["schema_version"]
        == "g1-cached-residual-jvp-regeneration-feasibility.v1"
    )
    assert regeneration_feasibility["controller_script_exists"] is True
    assert regeneration_feasibility["start_checkpoint"] == (
        "cached_jvp_start_checkpoint.npz"
    )
    assert regeneration_feasibility["start_checkpoint_exists"] is False
    assert regeneration_feasibility["advertised_latest_checkpoint"] == (
        "cached_jvp_latest_checkpoint.npz"
    )
    assert regeneration_feasibility["advertised_latest_checkpoint_exists"] is False
    assert regeneration_feasibility["step_basis_npz_expected_count"] == 1
    assert regeneration_feasibility["step_basis_npz_missing_count"] == 1
    assert regeneration_feasibility["missing_artifact_count"] == 3
    assert regeneration_feasibility["can_regenerate_advertised_chain"] is False
    assert regeneration_feasibility["can_replay_advertised_chain"] is False
    assert regeneration_feasibility["blocked_reasons"] == [
        "controller_start_checkpoint_missing",
        "advertised_latest_checkpoint_missing",
        "advertised_step_basis_npz_missing",
        "advertised_retained_checkpoint_missing",
    ]
    assert "--allow-cpu-diagnostic" in regeneration_feasibility[
        "non_promoting_regeneration_command_template"
    ]
    assert "diagnostic routing evidence only" in regeneration_feasibility[
        "claim_boundary"
    ]
    assert consistency["receipts"][2]["base_direct_residual_inf_n"] == 0.033136466982157
    assert consistency["receipts"][2]["residual_gate_n"] == 0.001
    assert consistency["receipts"][2]["latest_checkpoint"] == "cached_jvp_latest_checkpoint.npz"
    assert consistency["receipts"][2]["latest_checkpoint_exists"] is False
    assert (
        consistency["receipts"][2]["controller_start_checkpoint"]
        == "cached_jvp_start_checkpoint.npz"
    )
    assert consistency["receipts"][2]["controller_start_checkpoint_exists"] is False
    assert consistency["receipts"][2]["latest_checkpoint_retained_by_summary"] is True
    assert consistency["receipts"][2]["latest_checkpoint_promoted_by_summary"] is True
    assert consistency["receipts"][2]["advertised_retained_checkpoint_missing"] is True
    assert consistency["receipts"][2]["missing_controller_replay_artifact_count"] == 3
    assert consistency["receipts"][2]["regeneration_feasibility"] == (
        regeneration_feasibility
    )
    assert consistency["receipts"][2]["restart_ready"] is False
    assert consistency["receipts"][0]["component_only"] is True
    assert consistency["receipts"][1]["blocking_reasons"] == [
        "receipt_not_ready",
        "residual_gate_not_closed",
        "production_in_process_rocm_hip_residency_not_claimed",
        "latest_checkpoint_not_advertised",
        "claim_boundary_disclaims_closure",
    ]
    assert consistency["receipts"][2]["blocking_reasons"] == [
        "receipt_not_ready",
        "residual_jacobian_consistency_not_ready",
        "residual_gate_not_closed",
        "production_in_process_rocm_hip_residency_not_claimed",
        "controller_start_checkpoint_missing",
        "controller_replay_artifacts_missing",
        "latest_checkpoint_missing",
        "advertised_retained_checkpoint_missing",
        "claim_boundary_disclaims_closure",
    ]
    assert "consistent_residual_jacobian_newton_not_closed" in payload["blockers"]


def test_cli_writes_report_and_fails_blocked(tmp_path: Path) -> None:
    productization = tmp_path / "productization"
    _direct_probe(productization / "mgt_direct_residual_shell_material_tangent_base_followup379_probe.json", base=19.0, final=18.0)
    _direct_probe(productization / "mgt_direct_residual_shell_material_tangent_rowcorr_min_followup380_probe.json", base=18.0, final=14.0)
    for name, initial, final in [
        ("mgt_shell_material_rowcorr_budget_controller_followup383_target2_support4.json", 14.0, 13.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup384_target2_support4_compact_checkpoint.json", 13.0, 12.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup385_continue_target2_support4.json", 12.0, 11.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup386_continue_target2_support4.json", 11.0, 10.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup387_target4_support4.json", 10.0, 9.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup388_multistep_target4_support4.json", 9.0, 8.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup389_multistep_target4_support4.json", 8.0, 7.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup391_multistep_target4_support4.json", 7.0, 6.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup392_multistep_target4_support4.json", 6.0, 5.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup393_multistep_target4_support4.json", 5.0, 4.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup394_multistep_target4_support4.json", 4.0, 3.0),
        ("mgt_shell_material_rowcorr_budget_controller_followup395_multistep_target4_support4.json", 3.0, 2.0),
    ]:
        _controller_receipt(productization / name, initial=initial, final=final)
    _adaptive_global_krylov_receipt(
        productization
        / "mgt_direct_residual_shell_material_adaptive_global_krylov_followup396_smoke.json",
        initial=2.0,
        final=1.5,
        checkpoint_name="mgt_direct_residual_shell_material_adaptive_global_krylov_followup396_smoke_final_checkpoint.npz",
        compact=False,
    )
    _adaptive_global_krylov_receipt(
        productization
        / "mgt_direct_residual_shell_material_adaptive_global_krylov_followup397_compact_smoke.json",
        initial=1.5,
        final=1.4,
        checkpoint_name="mgt_direct_residual_shell_material_adaptive_global_krylov_followup397_compact_smoke_final_checkpoint.npz",
        compact=True,
    )
    _controller_receipt(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4.json",
        initial=1.4,
        final=1.3,
    )
    _controller_receipt(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup401_target4_support4_cpu_continuation.json",
        initial=1.3,
        final=1.2,
    )
    _controller_receipt(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup402_target4_support4_cpu_continuation.json",
        initial=1.2,
        final=1.1,
    )
    _controller_receipt(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup403_target4_support4_cpu_continuation.json",
        initial=1.1,
        final=1.05,
    )
    followup405_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_candidate1_target8_support4_final_checkpoint.npz"
    )
    followup405_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup405_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_candidate1_target8_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 1.05},
            "final_direct_residual": {
                "direct_residual_inf_n": 1.0,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 3,
                "stop_reason": "no_residual_descent",
                "target_row_count": 8,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup405_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup407_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup407_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup407_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup407_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup407_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup407_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup407_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 1.0},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.94,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup407_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup408_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup408_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup408_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.94},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.88,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup408_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup409_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup409_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup409_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup409_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup409_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup409_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup409_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.88},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.82,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup409_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup410_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup410_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup410_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup410_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup410_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup410_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup410_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.82},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.77,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup410_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup411_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup411_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup411_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup411_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup411_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup411_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup411_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.77},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.72,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup411_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup412_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup412_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup412_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup412_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup412_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup412_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup412_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.72},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.68,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup412_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup413_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup413_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup413_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup413_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup413_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup413_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup413_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.68},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.64,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup413_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup414_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup414_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup414_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup414_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup414_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup414_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup414_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.64},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.60,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup414_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup415_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_candidate1_target16_support4_final_checkpoint.npz"
    )
    followup415_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup415_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.60},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.59,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 1,
                "stop_reason": "no_residual_descent",
                "target_row_count": 16,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup415_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup416_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup416_target32_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup416_target32_support4_cpu_continuation_candidate1_target32_support4_final_checkpoint.npz"
    )
    followup416_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup416_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup416_target32_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup416_target32_support4_cpu_continuation_candidate1_target32_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.59},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.55,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 32,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup416_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup417_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup417_target32_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup417_target32_support4_cpu_continuation_candidate1_target32_support4_final_checkpoint.npz"
    )
    followup417_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup417_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup417_target32_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup417_target32_support4_cpu_continuation_candidate1_target32_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.55},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.52,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 32,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup417_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup418_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_candidate1_target32_support4_final_checkpoint.npz"
    )
    followup418_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup418_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_candidate1_target32_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.52},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.51,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 1,
                "stop_reason": "no_residual_descent",
                "target_row_count": 32,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup418_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup419_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup419_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup419_target64_support4_cpu_continuation_candidate1_target64_support4_final_checkpoint.npz"
    )
    followup419_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup419_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup419_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup419_target64_support4_cpu_continuation_candidate1_target64_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.51},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.48,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 64,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup419_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup420_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup420_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup420_target64_support4_cpu_continuation_candidate1_target64_support4_final_checkpoint.npz"
    )
    followup420_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup420_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup420_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup420_target64_support4_cpu_continuation_candidate1_target64_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.48},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.45,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 64,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup420_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup421_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup421_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup421_target64_support4_cpu_continuation_candidate1_target64_support4_final_checkpoint.npz"
    )
    followup421_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup421_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup421_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup421_target64_support4_cpu_continuation_candidate1_target64_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.45},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.42,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 64,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup421_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup422_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup422_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup422_target64_support4_cpu_continuation_candidate1_target64_support4_final_checkpoint.npz"
    )
    followup422_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup422_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup422_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup422_target64_support4_cpu_continuation_candidate1_target64_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.42},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.39,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 64,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup422_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup423_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup423_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup423_target64_support4_cpu_continuation_candidate1_target64_support4_final_checkpoint.npz"
    )
    followup423_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup423_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup423_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup423_target64_support4_cpu_continuation_candidate1_target64_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.39},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.36,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 64,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup423_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup424_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup424_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup424_target64_support4_cpu_continuation_candidate1_target64_support4_final_checkpoint.npz"
    )
    followup424_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup424_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup424_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup424_target64_support4_cpu_continuation_candidate1_target64_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.36},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.34,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 64,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup424_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup425_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup425_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup425_target64_support4_cpu_continuation_candidate1_target64_support4_final_checkpoint.npz"
    )
    followup425_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup425_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup425_target64_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup425_target64_support4_cpu_continuation_candidate1_target64_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.34},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.32,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 64,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup425_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup427_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup427_target128_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup427_target128_support4_cpu_continuation_candidate1_target128_support4_final_checkpoint.npz"
    )
    followup427_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup427_checkpoint.write_bytes(b"compact-target128")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup427_target128_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup427_target128_support4_cpu_continuation_candidate1_target128_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.32},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.30,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 128,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup427_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup428_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup428_target128_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup428_target128_support4_cpu_continuation_candidate1_target128_support4_final_checkpoint.npz"
    )
    followup428_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup428_checkpoint.write_bytes(b"compact-target128-followup428")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup428_target128_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup428_target128_support4_cpu_continuation_candidate1_target128_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.30},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.28,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 128,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup428_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup429_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_candidate1_target128_support4_final_checkpoint.npz"
    )
    followup429_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup429_checkpoint.write_bytes(b"compact-target128-followup429")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_candidate1_target128_support4.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.28},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.27,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 3,
                "stop_reason": "no_residual_descent",
                "target_row_count": 128,
                "support_column_count": 4,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup429_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup431_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_candidate1_target128_support8_final_checkpoint.npz"
    )
    followup431_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup431_checkpoint.write_bytes(b"compact-target128-support8-followup431")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_candidate1_target128_support8.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.27},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.265,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 1,
                "stop_reason": "no_residual_descent",
                "target_mode": "largest_rows",
                "jacobian_mode": "current_tangent",
                "support_selection": "row_strongest",
                "target_row_count": 128,
                "support_column_count": 8,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup431_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    followup408_support8_checkpoint = (
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_candidate1_target16_support8_final_checkpoint.npz"
    )
    followup408_support8_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    followup408_support8_checkpoint.write_bytes(b"compact")
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_candidate1_target16_support8.json",
        {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "status": "partial",
            "base_direct_residual": {"direct_residual_inf_n": 0.94},
            "final_direct_residual": {
                "direct_residual_inf_n": 0.8801,
                "residual_gate_passed": False,
            },
            "current_tangent_residual_row_correction": {
                "accepted": True,
                "promotion_count": 4,
                "stop_reason": "max_promotions_exhausted",
                "target_row_count": 16,
                "support_column_count": 8,
            },
            "output_final_checkpoint": {
                "written": True,
                "path": str(followup408_support8_checkpoint),
                "compact_checkpoint": True,
            },
        },
    )
    _controller_receipt(
        productization / "mgt_shell_material_rowcorr_budget_controller_followup382_support8_checkpointed.json",
        initial=14.0,
        final=14.0,
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup390_multistep_target4_support4_children"
        / "mgt_shell_material_rowcorr_budget_controller_followup390_multistep_target4_support4_candidate1_target4_support4.json",
        {"status": "in_progress"},
    )
    _strict_hip_non_promoting_receipt(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup399_target_rows_strict_hip_smoke.json",
        residual=1.3,
    )
    _strict_hip_non_promoting_receipt(
        productization / "mgt_g1_followup400_strict_hip_target_rows_alternating_smoke.json",
        residual=1.3,
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup404_target4_support4_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(productization / "followup403.npz"),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 1.05,
                    "final_direct_residual_inf_n": 1.05,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup406_target8_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup405_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 1.0,
                    "final_direct_residual_inf_n": 1.0,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup426_target64_support4_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup425_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.32,
                    "final_direct_residual_inf_n": 0.32,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup430_target256_support4_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup429_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.27,
                    "final_direct_residual_inf_n": 0.27,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup432_target128_support16_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup433_target192_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup434_target96_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup435_bending_drilling_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_shell_bending_drilling_rows",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup436_normal_rows_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_shell_normal_rows",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup436_shell_normal_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_shell_normal_rows",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup437_geometry_normal_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_shell_geometry_normal_rows",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup438_geometry_normal_bending_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_shell_geometry_normal_bending_rows",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup439_shell_element_blocks_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_shell_element_blocks",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup440_element_blocks_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_element_blocks",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup441_frame_element_blocks_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_frame_element_blocks",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup442_node_blocks_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "residual_node_blocks",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "current_component_rows",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup444_frontier_component_rows_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "frontier_component_rows",
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup445_fd_largest_rows_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "largest_rows",
                "row_jacobian_mode": "finite_difference",
                "row_target_counts": [128],
                "row_support_column_counts": [8],
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup446_residual_weighted_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "largest_rows",
                "row_jacobian_mode": "current_tangent",
                "row_support_selection": "residual_weighted",
                "row_target_counts": [128],
                "row_support_column_counts": [8],
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup447_fd_target_rows_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "largest_rows",
                "row_jacobian_mode": "finite_difference",
                "row_support_selection": "target_rows",
                "row_target_counts": [128],
                "row_support_column_counts": [8],
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    _write_json(
        productization
        / "mgt_shell_material_rowcorr_budget_controller_followup448_fd_residual_weighted_support8_cpu_continuation.json",
        {
            "schema_version": "mgt-shell-material-rowcorr-budget-controller.v1",
            "status": "partial",
            "final_direct_residual_inf_n": 14.0,
            "final_checkpoint_path": str(followup431_checkpoint),
            "controller": {
                "promotion_count": 0,
                "stop_reason": "max_candidates_reached",
                "runtime_budget_exceeded": False,
                "row_target_mode": "largest_rows",
                "row_jacobian_mode": "finite_difference",
                "row_support_selection": "residual_weighted",
                "row_target_counts": [128],
                "row_support_column_counts": [8],
            },
            "rows": [
                {
                    "accepted": False,
                    "base_direct_residual_inf_n": 0.265,
                    "final_direct_residual_inf_n": 0.265,
                    "row_correction_stop_reason": "no_residual_descent",
                }
            ],
            "claim_boundary": {
                "cpu_diagnostic_only": True,
                "official_rocm_hip_closure_required": True,
            },
        },
    )
    out = tmp_path / "out.json"
    rc = build_mgt_g1_shell_material_budgeted_continuation_status.main(
        [
            "--productization-dir",
            str(productization),
            "--out",
            str(out),
            "--fail-blocked",
        ]
    )

    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["latest_frontier_direct_residual_inf_n"] == 0.265
    assert payload["latest_frontier_operator_stop_reason"] == "no_residual_descent"
    assert payload["latest_frontier_operator_target_row_count"] == 128
    assert payload["latest_frontier_operator_support_column_count"] == 8
    assert payload["latest_frontier_operator_promotion_count"] == 1
    assert payload["counter_evidence"][-1]["receipt"] == (
        "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_children/"
        "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_candidate1_target16_support8.json"
    )
    assert payload["counter_evidence"][-1]["direct_residual_inf_n"] == 0.8801
    assert payload["same_operator_repetition_exhausted"] is True
    assert payload["same_operator_exhausted_at_latest_checkpoint"] is True
    assert payload["same_operator_no_descent_receipts"] == [
        "mgt_shell_material_rowcorr_budget_controller_followup404_target4_support4_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup406_target8_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup426_target64_support4_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup430_target256_support4_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup432_target128_support16_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup433_target192_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup434_target96_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup435_bending_drilling_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup436_normal_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup437_geometry_normal_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup438_geometry_normal_bending_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup439_shell_element_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup440_element_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup441_frame_element_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup442_node_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup444_frontier_component_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup445_fd_largest_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup446_residual_weighted_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup447_fd_target_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup448_fd_residual_weighted_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_children/"
        "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_candidate1_target8_support4.json",
        "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_children/"
        "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_candidate1_target16_support4.json",
        "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_children/"
        "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_candidate1_target32_support4.json",
        "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_children/"
        "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_candidate1_target128_support4.json",
        "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_children/"
        "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_candidate1_target128_support8.json",
    ]
    mode_exhaustion = payload["row_target_mode_exhaustion"]
    assert mode_exhaustion["all_configured_modes_exhausted_at_latest_checkpoint"] is True
    assert mode_exhaustion["missing_modes"] == []
    assert mode_exhaustion["exhausted_modes"] == [
        "largest_rows",
        "residual_node_blocks",
        "residual_element_blocks",
        "residual_frame_element_blocks",
        "residual_shell_element_blocks",
        "residual_shell_bending_drilling_rows",
        "residual_shell_normal_rows",
        "residual_shell_geometry_normal_rows",
        "residual_shell_geometry_normal_bending_rows",
        "frontier_component_rows",
        "current_component_rows",
    ]
    assert mode_exhaustion["receipt_by_mode"]["largest_rows"] == (
        "mgt_shell_material_rowcorr_budget_controller_followup448_fd_residual_weighted_support8_cpu_continuation.json"
    )
    assert (
        mode_exhaustion["receipt_by_mode"]["frontier_component_rows"]
        == "mgt_shell_material_rowcorr_budget_controller_followup444_frontier_component_rows_support8_cpu_continuation.json"
    )
    assert (
        mode_exhaustion["receipt_by_mode"]["current_component_rows"]
        == "mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation.json"
    )
    strategy_exhaustion = payload["largest_rows_operator_strategy_exhaustion"]
    assert (
        strategy_exhaustion[
            "all_configured_strategies_exhausted_at_latest_checkpoint"
        ]
        is True
    )
    assert strategy_exhaustion["missing_strategy_ids"] == []
    assert strategy_exhaustion["exhausted_strategy_ids"] == [
        "current_tangent_row_strongest_target128_support8",
        "current_tangent_residual_weighted_target128_support8",
        "finite_difference_row_strongest_target128_support8",
        "finite_difference_target_rows_target128_support8",
        "finite_difference_residual_weighted_target128_support8",
    ]
    assert strategy_exhaustion["receipt_by_strategy_id"] == {
        "current_tangent_row_strongest_target128_support8": (
            "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_children/"
            "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_candidate1_target128_support8.json"
        ),
        "current_tangent_residual_weighted_target128_support8": (
            "mgt_shell_material_rowcorr_budget_controller_followup446_residual_weighted_support8_cpu_continuation.json"
        ),
        "finite_difference_row_strongest_target128_support8": (
            "mgt_shell_material_rowcorr_budget_controller_followup445_fd_largest_rows_support8_cpu_continuation.json"
        ),
        "finite_difference_target_rows_target128_support8": (
            "mgt_shell_material_rowcorr_budget_controller_followup447_fd_target_rows_support8_cpu_continuation.json"
        ),
        "finite_difference_residual_weighted_target128_support8": (
            "mgt_shell_material_rowcorr_budget_controller_followup448_fd_residual_weighted_support8_cpu_continuation.json"
        ),
    }
    assert payload["next_actions"][0].startswith(
        "all configured largest-rows target128/support8 support/Jacobian strategies are exhausted"
    )
    assert payload["pending_launch_only_receipts"] == []
    duplicate_alias = payload["duplicate_alias_receipts"][-1]
    assert duplicate_alias["receipt"] == (
        "mgt_shell_material_rowcorr_budget_controller_followup436_shell_normal_support8_cpu_continuation.json"
    )
    assert duplicate_alias["duplicate_of_receipt"] == (
        "mgt_shell_material_rowcorr_budget_controller_followup436_normal_rows_support8_cpu_continuation.json"
    )
    assert duplicate_alias["counted_in_frontier"] is False
    assert duplicate_alias["counted_in_row_target_exhaustion"] is False
    assert duplicate_alias["controller_row_target_mode"] == "residual_shell_normal_rows"
    assert duplicate_alias["direct_residual_inf_n"] == 0.265
    assert duplicate_alias["claim_boundary"]["duplicate_alias_only"] is True
    non_promoting = payload["non_promoting_launch_receipts"]
    assert [
        row["receipt"]
        for row in non_promoting[-23:]
    ] == [
        "mgt_shell_material_rowcorr_budget_controller_followup399_target_rows_strict_hip_smoke.json",
        "mgt_g1_followup400_strict_hip_target_rows_alternating_smoke.json",
        "mgt_shell_material_rowcorr_budget_controller_followup404_target4_support4_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup406_target8_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup426_target64_support4_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup430_target256_support4_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup432_target128_support16_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup433_target192_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup434_target96_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup435_bending_drilling_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup436_normal_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup437_geometry_normal_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup438_geometry_normal_bending_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup439_shell_element_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup440_element_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup441_frame_element_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup442_node_blocks_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup444_frontier_component_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup445_fd_largest_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup446_residual_weighted_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup447_fd_target_rows_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup448_fd_residual_weighted_support8_cpu_continuation.json",
    ]
    assert non_promoting[-22]["controller_stop_reason"] == "strict_hip_runtime_unavailable"
    assert non_promoting[-1]["controller_promotion_count"] == 0
    assert non_promoting[-1]["controller_stop_reason"] == "max_candidates_reached"
    assert non_promoting[-1]["controller_row_jacobian_mode"] == "finite_difference"
    assert non_promoting[-1]["controller_row_support_selection"] == "residual_weighted"
    assert non_promoting[-1]["counted_in_frontier"] is False
    assert non_promoting[-1]["direct_residual_inf_n"] == 0.265
    assert non_promoting[-1]["top_level_direct_residual_inf_n"] == 14.0
    assert non_promoting[-1]["top_level_child_frontier_mismatch"] is True
    assert non_promoting[-1]["top_level_direct_residual_counted"] is False
    assert (
        non_promoting[-1]["top_level_residual_boundary"]
        == "top_level_controller_residual_differs_from_child_frontier; "
        "status uses child receipt residual for non-promoting boundary evidence"
    )
    assert non_promoting[-1]["child_attempt_count"] == 1
    assert non_promoting[-1]["child_accepted_count"] == 0
    assert non_promoting[-1]["child_best_base_direct_residual_inf_n"] == 0.265
    assert non_promoting[-1]["child_best_final_direct_residual_inf_n"] == 0.265
    assert non_promoting[-1]["child_row_correction_stop_reasons"] == [
        "no_residual_descent"
    ]
