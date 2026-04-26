from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/generate_optimization_history_viewer_payload.py"
    )
    spec = importlib.util.spec_from_file_location("optimization_history_payload_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_payload_uses_selected_event_history() -> None:
    module = _load_module()
    report_payload = {
        "contract_pass": True,
        "summary": {
            "accepted_count": 4,
            "changed_group_count": 3,
            "baseline_cost_proxy": 100.0,
            "final_cost_proxy": 90.0,
            "baseline_max_dcr": 0.93,
            "final_max_dcr": 0.98,
            "baseline_constructability_avg": 0.42,
            "final_constructability_avg": 0.35,
            "objective_profile": "balanced_practice",
            "budget_mode": "high",
            "solver_backend_static": "hip_static",
            "solver_backend_ndtha": "hip_ndtha",
        },
        "inputs": {
            "max_iterations": 8,
            "effective_max_iterations": 8,
        },
    }
    accepted_payload = {
        "accepted_candidate_explain_rows": [
            {
                "group_id": "G-1",
                "selected_in_final_loop": True,
                "selected_event_index": 1,
                "action_name": "beam_section_down",
                "member_id": "40102",
                "combination_name": "ULS_WX",
                "viewer_row_ref": "ULS_WX::3::40102::40102",
                "viewer_overlay_row_id": "overlay_row::1::11::40102::beam_section_down",
                "viewer_row_url": "../visualization/structural_optimization_viewer.html?source=cost_reduction_reverse_sync&overlay_member_id=40102",
                "viewer_slice_url": "../visualization/structural_optimization_viewer.html?source=cost_reduction_reverse_sync&overlay_group_index=11",
                "recommended_results_card": "time-history",
                "recommended_results_series_index": 2,
                "projected_cost_delta": 7.0,
                "max_dcr": 0.97,
                "constructability_gain": 0.04,
            },
            {
                "group_id": "G-2",
                "selected_in_final_loop": True,
                "selected_event_index": 1,
                "action_name": "wall_thickness_down",
                "projected_cost_delta": 3.0,
                "max_dcr": 0.95,
                "constructability_gain": 0.02,
            },
            {
                "group_id": "G-1",
                "selected_in_final_loop": True,
                "selected_event_index": 2,
                "action_name": "beam_section_down",
                "projected_cost_delta": 1.5,
                "max_dcr": 0.98,
                "constructability_gain": 0.01,
            },
            {
                "group_id": "G-X",
                "selected_in_final_loop": False,
                "selected_event_index": 2,
                "action_name": "ignored",
                "projected_cost_delta": 999.0,
                "max_dcr": 9.9,
                "constructability_gain": 9.9,
            },
        ]
    }

    payload = module.build_payload(report_payload, accepted_payload)

    assert payload["viewer_family"] == "optimization_history_viewer"
    assert payload["source_mode"] == "report_plus_accepted_rows"
    assert payload["summary"]["iteration_count"] == 2
    assert payload["summary"]["iteration_budget"] == 8
    assert payload["summary"]["changed_group_count"] == 3
    assert payload["summary"]["final_cost_proxy"] == 90.0
    assert payload["summary"]["final_max_dcr"] == 0.98
    assert payload["summary"]["final_penalty"] == 0.35

    history = payload["history"]
    assert len(history) == 3
    assert history[0]["iter"] == 0
    assert history[0]["cost"] == 100.0
    assert history[1]["iter"] == 1
    assert history[1]["modified"] == 2
    assert history[1]["selected_count"] == 2
    assert "beam_section_down" in history[1]["event_label"]
    assert history[1]["handoff"]["member_id"] == "40102"
    assert history[1]["handoff"]["load_case"] == "ULS_WX"
    assert history[1]["handoff"]["row_ref"] == "ULS_WX::3::40102::40102"
    assert history[1]["handoff"]["overlay_row_id"] == "overlay_row::1::11::40102::beam_section_down"
    assert history[1]["handoff"]["viewer_row_url"].endswith("overlay_member_id=40102")
    assert history[1]["handoff"]["viewer_slice_url"].endswith("overlay_group_index=11")
    assert history[1]["handoff"]["results_card"] == "time-history"
    assert history[1]["handoff"]["results_series_index"] == 2
    assert history[1]["handoff"]["overlay_member_id"] == "40102"
    assert history[1]["handoff"]["overlay_action_name"] == "beam_section_down"
    assert history[-1]["iter"] == 2
    assert history[-1]["modified"] == 3
    assert history[-1]["selected_count"] == 3
    assert history[-1]["cost"] == 90.0
    assert history[-1]["dcr"] == 0.98
    assert history[-1]["penalty"] == 0.35


def test_main_generates_release_payload(tmp_path: Path) -> None:
    module = _load_module()
    report_path = tmp_path / "report.json"
    accepted_path = tmp_path / "accepted.json"
    out_path = tmp_path / "optimization_history_viewer.json"

    report_path.write_text(
        json.dumps(
            {
                "contract_pass": False,
                "reason_code": "CHECK",
                "summary": {
                    "accepted_count": 1,
                    "changed_group_count": 1,
                    "baseline_cost_proxy": 12.0,
                    "final_cost_proxy": 10.0,
                    "baseline_max_dcr": 0.8,
                    "final_max_dcr": 0.9,
                    "baseline_constructability_avg": 0.4,
                    "final_constructability_avg": 0.3,
                },
                "inputs": {"effective_max_iterations": 3},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    accepted_path.write_text(
        json.dumps(
            {
                "accepted_candidate_explain_rows": [
                    {
                        "group_id": "A",
                        "selected_in_final_loop": True,
                        "selected_event_index": 1,
                        "action_name": "detailing_down",
                        "projected_cost_delta": 2.0,
                        "max_dcr": 0.9,
                        "constructability_gain": 0.1,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.build_payload(
        json.loads(report_path.read_text(encoding="utf-8")),
        json.loads(accepted_path.read_text(encoding="utf-8")),
    )
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["summary"]["iteration_count"] == 1
    assert written["history"][-1]["modified"] == 1
    assert written["history"][-1]["cost"] == 10.0
