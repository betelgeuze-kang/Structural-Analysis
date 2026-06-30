from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_structural_product_development_roadmap.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_structural_product_development_roadmap",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_minimal_inputs(repo_root: Path) -> None:
    productization = repo_root / "implementation/phase1/release_evidence/productization"
    release = repo_root / "implementation/phase1/release"

    _write_json(
        productization / "product_readiness_snapshot.json",
        {
            "status": "blocked",
            "blocker_count": 3,
            "evidence_fresh": True,
            "snapshot_source_state_consistent": True,
            "release_ready": False,
            "paid_pilot_ready": False,
            "limited_commercial_ready": False,
            "workstation_delivery_ready": False,
            "independent_product_ready": False,
            "assisted_service_pilot_ready": False,
            "ga_enterprise_ready": False,
            "components": {
                "external_benchmark_receipts": {
                    "ready": False,
                    "attached_count": 1,
                    "queue_count": 4,
                },
                "g1": {
                    "full_load_hip_newton_lane_observed_load_scale": 0.656,
                },
                "github_actions_ci_streak": {
                    "pr_consecutive_pass_count": 12,
                    "nightly_consecutive_pass_count": 4,
                },
                "human_ux_observation": {
                    "blocker_count": 1,
                },
                "license_status": {
                    "status": "blocked",
                },
                "solver_product": {
                    "ready": False,
                    "blocker_count": 1,
                    "blockers": ["solver_validation_blocked"],
                },
            },
        },
    )
    _write_json(
        productization / "pm_release_gate_report.json",
        {
            "paid_pilot_candidate": True,
            "limited_commercial_milestone_ready": False,
            "milestones": [{"ok": True}, {"ok": False}],
            "release_area_matrix": [
                {"area": "ci", "ok": True, "blockers": []},
                {"area": "ux", "ok": False, "blockers": ["human_observation_missing"]},
            ],
        },
    )
    _write_json(
        productization / "developer_preview_rc_status.json",
        {
            "status": "blocked",
            "final_gate_pass_count": 1,
            "final_gate_count": 2,
            "final_gates": [
                {"item": "small_model", "contract_pass": True, "blockers": []},
                {
                    "item": "medium_model",
                    "contract_pass": False,
                    "blockers": ["medium_model_missing"],
                },
            ],
        },
    )
    _write_json(
        productization / "release_evidence_freshness_report.json",
        {
            "contract_pass": True,
            "summary": {"pass_count": 10, "artifact_count": 10},
        },
    )
    _write_json(productization / "mgt_g1_direct_residual_terminal_gate_report.json", {"contract_pass": True})
    _write_json(
        productization / "g1_full_load_hip_newton_lane_report.json",
        {"contract_pass": False, "blockers": ["full_load_hip_newton_not_closed"]},
    )
    _write_json(
        productization / "g1_f2g_f2h_cause_narrowing_status.json",
        {
            "status": "ready",
            "contract_pass": True,
            "evidence_signals": {
                "support_or_link_row_gap_disfavored": True,
                "f2h_lightweight_0p1_0p2_0p4_ready": True,
            },
        },
    )
    _write_json(
        repo_root / "implementation/phase1/customer_shadow_evidence_status.json",
        {"summary": {"completed_shadow_case_count": 1, "min_completed_shadow_cases": 3}},
    )
    _write_json(
        release / "external_benchmark_submission_readiness.json",
        {"summary": {"ready_to_start_full_submission_now": False}},
    )


def test_structural_product_development_roadmap_summarizes_blocked_stages(
    tmp_path: Path,
) -> None:
    _write_minimal_inputs(tmp_path)

    payload = module.build_structural_product_development_roadmap(repo_root=tmp_path)

    assert payload["schema_version"] == "structural-product-development-roadmap.v1"
    assert payload["surface_id"] == "structural_product_development_roadmap"
    assert payload["status"] == "blocked"
    assert payload["product_completion_claim"] is False
    assert payload["stage_count"] == 7
    assert payload["ready_stage_count"] == 1
    assert payload["primary_blocker"] == "ux::human_observation_missing"

    stages = {row["stage_id"]: row for row in payload["roadmap_stages"]}
    assert stages["evidence_freshness_and_snapshot_integrity"]["status"] == "ready"
    assert stages["pm_release_gate"]["blockers"] == ["ux::human_observation_missing"]
    assert stages["g1_solver_closure"]["blockers"] == [
        "full_load_hip_newton_not_closed"
    ]
    assert (
        stages["g1_solver_closure"]["summary"]["f2g_f2h_cause_narrowing_status"]
        == "ready"
    )
    assert (
        stages["g1_solver_closure"]["summary"]["recommended_g1_next_direction"]
        == "global_connectivity_consistent_newton_rocm_lane"
    )
    assert (
        "implementation/phase1/release_evidence/productization/g1_f2g_f2h_cause_narrowing_status.json"
        in stages["g1_solver_closure"]["evidence_artifacts"]
    )
    assert stages["paid_pilot_readiness"]["blockers"] == [
        "customer_shadow_below_required:1/3",
        "external_benchmark_receipts_pending:1/4",
        "product_snapshot_paid_pilot_ready_false",
    ]


def test_write_structural_product_development_roadmap_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    _write_minimal_inputs(tmp_path)
    out_json = tmp_path / "roadmap.json"
    out_md = tmp_path / "roadmap.md"

    payload = module.write_structural_product_development_roadmap(
        repo_root=tmp_path,
        out_json=out_json,
        out_md=out_md,
    )

    assert json.loads(out_json.read_text(encoding="utf-8"))["summary_line"] == payload[
        "summary_line"
    ]
    assert "# Structural Product Development Roadmap" in out_md.read_text(
        encoding="utf-8"
    )
