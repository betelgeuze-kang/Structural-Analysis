from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_g1_global_connectivity_load_path_audit.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

SPEC = importlib.util.spec_from_file_location("build_g1_global_connectivity_load_path_audit", SCRIPT_PATH)
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_mgt(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_global_connectivity_audit_finds_element_path_to_support(tmp_path: Path) -> None:
    mgt = tmp_path / "model.mgt"
    f2g = tmp_path / "f2g.local.json"
    _write_mgt(
        mgt,
        """*NODE
1, 0, 0, 0
2, 1, 0, 0
3, 1, 1, 0
4, 0, 1, 0
*ELEMENT
10, BEAM, 1, 1, 1, 2, 0, 0
11, PLATE, 1, 1, 2, 3, 4, 0, 0, 0, 0
*CONSTRAINT
1, 111111
*ELASTICLINK
""",
    )
    _write_json(
        f2g,
        {
            "status": "ready",
            "dominant_dof_rows": [
                {
                    "mode_index": 0,
                    "rank_in_mode": 1,
                    "node_id": 4,
                    "dof": "UY",
                    "support_member": False,
                    "elastic_link_degree": 0,
                    "elastic_link_support_reachable": False,
                }
            ],
        },
    )

    payload = audit_module.build_audit(repo_root=tmp_path, mgt_path=mgt, f2g_audit_path=f2g)

    assert payload["status"] == "ready"
    assert payload["promotes_g1_closure"] is False
    summary = payload["summary"]
    assert summary["dominant_node_count"] == 1
    assert summary["dominant_nodes_element_reachable_to_support_count"] == 1
    assert summary["dominant_nodes_without_element_path_to_support_count"] == 0
    assert summary["global_connectivity_classification"] == (
        "element_graph_connects_dominant_modes_to_supports"
    )
    assert payload["dominant_node_summaries"][0]["element_graph_hops_to_support"] == 2
    assert payload["decision_record"] == {
        "schema_version": "g1-global-connectivity-decision-record.v1",
        "classification": "element_graph_connects_dominant_modes_to_supports",
        "dominant_node_count": 1,
        "dominant_nodes_element_reachable_to_support_count": 1,
        "dominant_nodes_without_element_path_to_support_count": 0,
        "element_graph_closes_dominant_packet": True,
        "row_only_support_or_elastic_link_correction_decision": "stop",
        "row_only_correction_loop_stopped": True,
        "primary_next_lane": "consistent_residual_jacobian_newton_rocm_worker",
        "required_next_receipts": [
            "implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json",
            "implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json",
        ],
        "rationale": [
            "1/1 dominant near-null nodes reach authored supports through structural elements.",
            "A direct support-row or elastic-link-row absence is no longer the leading G1 explanation.",
            "Further G1 progress requires consistent residual/Jacobian Newton evidence and a production ROCm/HIP residual/JVP lane.",
        ],
        "claim_boundary": (
            "This decision record only routes the next G1 diagnostic slice. It does "
            "not prove full-load 1.0 equilibrium, material Newton breadth, or "
            "production ROCm/HIP residency."
        ),
    }
    assert (
        payload["next_actions"][0]
        == "stop_row_only_support_or_elastic_link_correction_loop"
    )


def test_global_connectivity_audit_reports_disconnected_dominant_component(
    tmp_path: Path,
) -> None:
    mgt = tmp_path / "model.mgt"
    f2g = tmp_path / "f2g.local.json"
    _write_mgt(
        mgt,
        """*NODE
1, 0, 0, 0
2, 1, 0, 0
4, 10, 0, 0
5, 11, 0, 0
*ELEMENT
10, BEAM, 1, 1, 1, 2, 0, 0
20, BEAM, 1, 1, 4, 5, 0, 0
*CONSTRAINT
1, 111111
*ELASTICLINK
""",
    )
    _write_json(
        f2g,
        {
            "status": "ready",
            "dominant_dof_rows": [
                {
                    "mode_index": 0,
                    "rank_in_mode": 1,
                    "node_id": 4,
                    "dof": "UX",
                    "support_member": False,
                    "elastic_link_degree": 0,
                    "elastic_link_support_reachable": False,
                }
            ],
        },
    )

    payload = audit_module.build_audit(repo_root=tmp_path, mgt_path=mgt, f2g_audit_path=f2g)

    assert payload["status"] == "ready"
    summary = payload["summary"]
    assert summary["dominant_nodes_element_reachable_to_support_count"] == 0
    assert summary["dominant_nodes_without_element_path_to_support_count"] == 1
    assert summary["element_graph_connectivity_gap_detected"] is True
    assert summary["global_connectivity_classification"] == "element_graph_connectivity_gap_detected"
    assert payload["ranked_findings"][0]["finding_id"] == (
        "dominant_near_null_nodes_not_reachable_to_support_via_element_graph"
    )
    assert payload["decision_record"][
        "row_only_support_or_elastic_link_correction_decision"
    ] == "hold_pending_connectivity_mapping"
    assert payload["decision_record"]["row_only_correction_loop_stopped"] is False
    assert payload["decision_record"]["primary_next_lane"] == (
        "structural_connectivity_load_path_mapping"
    )
    assert (
        payload["next_actions"][0]
        == "inspect_disconnected_structural_components_and_load_path_mapping"
    )
