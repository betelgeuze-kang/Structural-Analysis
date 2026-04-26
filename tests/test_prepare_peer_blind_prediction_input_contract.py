from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_peer_blind_prediction_input_contract as contract_builder  # noqa: E402


def test_peer_blind_prediction_input_contract_marks_measured_pending() -> None:
    payload = contract_builder.build_contract(
        {
            "contract_pass": True,
            "summary": {
                "geometry_doc_count": 6,
                "material_bundle_present": True,
                "gm_workbook_present": True,
            },
            "geometry_docs": ["Columns.pdf", "Foundation.pdf"],
            "gm_workbook_summary": {
                "gm_name_count": 3,
                "gm_names": ["Random Noise", "GM1", "GM2"],
                "sequence_step_count": 4,
                "sequence_labels": ["Random Noise", "GM1", "Random Noise", "GM2"],
            },
            "materials_bundle_summary": {
                "bundle_files": ["Materials.xlsx", "Grout_datasheet.pdf"],
                "materials_workbook": {"sheet_names": ["Concrete", "Steel"]},
            },
        },
        {
            "source_family": "edefense_peer_blind_prediction",
            "seed_id": "edefense_peer_blind_prediction_seed_01",
            "benchmark_track": "blind_prediction_dynamic_holdout",
            "local_input_root": "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01",
            "summary": {"required_group_pass_count": 3, "required_group_count": 4},
            "expected_groups": {"measured_response": {"patterns": ["*response*.csv"]}},
        },
        {
            "measured_response_present": False,
            "expected_patterns": ["*response*.csv"],
            "matched_files": [],
        },
        {
            "contract_pass": False,
            "landing_state": "pending",
            "reason_code": "ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING",
            "summary_line": "E-Defense/PEER measured-response landing manifest: PENDING | matched=0 | csv=0 | accel_candidates=0 | drift_candidates=0 | sensors=0",
            "summary": {"matched_file_count": 0, "csv_file_count": 0},
        },
    )

    assert payload["contract_pass"] is True
    assert payload["readiness"]["public_input_ready"] is True
    assert payload["readiness"]["benchmark_case_ready"] is False
    assert payload["readiness"]["measured_response_landing_manifest_ready"] is False
    assert payload["measured_response_package"]["present"] is False
    assert payload["measured_response_package"]["landing_manifest_present"] is True
    assert payload["measured_response_package"]["landing_manifest_contract_pass"] is False
    assert payload["measured_response_landing_manifest"]["contract_pass"] is False
    assert payload["measured_response_landing_manifest"]["reason_code"] == "ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING"
    assert payload["summary"]["gm_name_count"] == 3
    assert payload["summary"]["landing_manifest_contract_pass"] is False
    assert payload["summary"]["landing_manifest_matched_file_count"] == 0
    assert len(payload["proposed_case_ids"]) == 3
    assert payload["reason_code"] == "PASS_INPUT_CONTRACT_READY_MEASURED_PENDING"
