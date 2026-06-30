from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_g1_f2g_f2h_cause_narrowing_status.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

SPEC = importlib.util.spec_from_file_location("build_g1_f2g_f2h_cause_narrowing_status", SCRIPT_PATH)
assert SPEC and SPEC.loader
status_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status_module)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cause_narrowing_deprioritizes_row_only_support_fix(tmp_path: Path) -> None:
    f2g = tmp_path / "f2g.local.json"
    f2h = tmp_path / "f2h.local.json"
    g1 = tmp_path / "g1.json"
    global_connectivity = tmp_path / "g1_global_connectivity.json"
    script = tmp_path / "scripts/build_g1_f2g_f2h_cause_narrowing_status.py"
    _write_json(
        f2g,
        {
            "status": "ready",
            "summary": {
                "dominant_dof_row_count": 64,
                "direct_support_member_count": 0,
                "direct_elastic_link_endpoint_count": 0,
                "elastic_link_reachable_to_support_count": 0,
                "global_frame_shell_tangent_integration_ready": False,
            },
            "ranked_findings": [
                {"finding_id": "near_null_packet_is_distributed_translation_rotation"}
            ],
        },
    )
    _write_json(
        f2h,
        {
            "status": "ready",
            "summary": {
                "required_sequence_proven": True,
                "all_steps_ready": True,
                "max_converged_load_scale": 0.4,
                "residual_trend_across_increasing_load": "nondecreasing",
            },
            "residual_history": [
                {"load_scale": 0.1, "residual_inf_n": 1.0e-6},
                {"load_scale": 0.4, "residual_inf_n": 4.0e-6},
            ],
        },
    )
    _write_json(
        g1,
        {
            "contract_pass": False,
            "blockers": [
                "child_consistent_residual_jacobian_newton_not_proven",
                "hip_consistency_proof_gate_not_passed",
            ],
        },
    )
    _write_json(
        global_connectivity,
        {
            "status": "ready",
            "summary": {
                "dominant_node_count": 8,
                "dominant_nodes_element_reachable_to_support_count": 8,
                "dominant_nodes_without_element_path_to_support_count": 0,
                "element_graph_connectivity_gap_detected": False,
                "global_connectivity_classification": "element_graph_connects_dominant_modes_to_supports",
            },
        },
    )
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# fixture\n", encoding="utf-8")

    payload = status_module.build_status(
        repo_root=tmp_path,
        f2g_audit_path=f2g,
        f2h_status_path=f2h,
        g1_full_load_path=g1,
        global_connectivity_path=global_connectivity,
    )

    assert payload["status"] == "ready"
    assert payload["promotes_g1_closure"] is False
    assert payload["evidence_signals"]["support_or_link_row_gap_disfavored"] is True
    assert payload["evidence_signals"]["full_structural_graph_audit_status"] == "ready"
    assert payload["evidence_signals"]["global_connectivity_classification"] == (
        "element_graph_connects_dominant_modes_to_supports"
    )
    assert payload["evidence_signals"]["dominant_nodes_without_element_path_to_support_count"] == 0
    assert payload["evidence_signals"]["f2h_lightweight_0p1_0p2_0p4_ready"] is True
    assert payload["hypothesis_rank"][0]["hypothesis"] == "direct_support_or_elastic_link_row_missing"
    assert payload["hypothesis_rank"][0]["classification"] == "deprioritized"
    assert payload["hypothesis_rank"][1]["classification"] == "load_path_transfer_or_tangent_gap"
    assert "stop_row_only_support_or_elastic_link_correction_loop" in payload["next_actions"]


def test_cause_narrowing_blocks_when_f2h_is_not_ready(tmp_path: Path) -> None:
    f2g = tmp_path / "f2g.local.json"
    f2h = tmp_path / "f2h.local.json"
    g1 = tmp_path / "g1.json"
    script = tmp_path / "scripts/build_g1_f2g_f2h_cause_narrowing_status.py"
    _write_json(
        f2g,
        {
            "status": "ready",
            "summary": {
                "dominant_dof_row_count": 4,
                "direct_support_member_count": 0,
                "direct_elastic_link_endpoint_count": 0,
                "elastic_link_reachable_to_support_count": 0,
            },
        },
    )
    _write_json(f2h, {"status": "blocked", "summary": {"required_sequence_proven": False}})
    _write_json(g1, {"contract_pass": False, "blockers": []})
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# fixture\n", encoding="utf-8")

    payload = status_module.build_status(
        repo_root=tmp_path,
        f2g_audit_path=f2g,
        f2h_status_path=f2h,
        g1_full_load_path=g1,
    )

    assert payload["status"] == "blocked"
    assert "f2h_lightweight_continuation_not_ready" in payload["blockers"]
