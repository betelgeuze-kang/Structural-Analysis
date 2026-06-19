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

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=chain,
        counter_receipts=(),
        launch_receipts=("followup390_child.json",),
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

    payload = build_mgt_g1_shell_material_budgeted_continuation_status.build_report(
        productization_dir=productization,
        chain_receipts=(
            "base.json",
            "followup396.json",
            "followup397.json",
            "followup398.json",
        ),
        counter_receipts=(),
        launch_receipts=(),
        direct_residual_tolerance_n=5.0e-4,
    )

    assert payload["frontier_chain_monotonic_nonincreasing"] is True
    assert payload["latest_frontier_receipt"] == "followup398.json"
    assert payload["latest_frontier_direct_residual_inf_n"] == 5.74426714604332
    assert payload["residual_gap_to_tolerance_n"] == 5.74426714604332 - 5.0e-4
    assert payload["frontier_chain"][-1]["compact_checkpoint_exists"] is True
    assert payload["frontier_chain"][-3]["checkpoint_compact"] is False
    assert payload["frontier_chain"][-1]["checkpoint_compact"] is True
    assert payload["latest_frontier_checkpoint_compact"] is True
    assert payload["storage_policy"]["latest_frontier_checkpoint_compact"] is True
    assert payload["storage_policy"]["frontier_chain_full_history_checkpoint_present"] is True
    assert payload["storage_policy"]["full_history_checkpoint_avoided"] is False
    assert payload["frontier_chain"][-2]["schema_version"] == (
        "mgt-direct-residual-adaptive-preconditioned-global-newton.v1"
    )
    assert payload["frontier_chain"][-1]["schema_version"] == (
        "mgt-shell-material-rowcorr-budget-controller.v1"
    )
    assert payload["frontier_chain"][-1]["base_direct_residual_inf_n"] == 6.117752205061414
    assert payload["frontier_chain"][-1]["direct_residual_inf_n"] == 5.74426714604332
    assert "direct_residual_gate_not_closed" in payload["blockers"]
    assert "full_mesh_nonlinear_equilibrium_not_closed" in payload["blockers"]
    assert "production_rocm_hip_residual_row_backend_not_closed" in payload["blockers"]
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
    assert json.loads(out.read_text(encoding="utf-8"))["latest_frontier_direct_residual_inf_n"] == 1.3
    assert (
        "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4.npz"
        in json.loads(out.read_text(encoding="utf-8"))["next_actions"][0]
    )
