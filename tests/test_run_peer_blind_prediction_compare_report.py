from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import run_peer_blind_prediction_compare_report as compare_report  # noqa: E402


def test_peer_blind_compare_report_pending_without_measured_response() -> None:
    payload = compare_report.build_report(
        {"cases": [{"case_id": "seed::gm1"}]},
        {"summary": {"case_count": 1}},
        {"contract_pass": False, "summary": {"acceleration_channel_count": 0}},
        {
            "contract_pass": False,
            "landing_state": "pending",
            "reason_code": "ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING",
            "summary_line": "E-Defense/PEER measured-response landing manifest: PENDING | matched=0 | csv=0 | accel_candidates=0 | drift_candidates=0 | sensors=0",
            "summary": {"matched_file_count": 0, "csv_file_count": 0},
        },
    )
    assert payload["summary"]["measured_response_ready"] is False
    assert payload["summary"]["measured_response_landing_manifest_ready"] is False
    assert payload["summary"]["landing_manifest_contract_pass"] is False
    assert payload["summary"]["landing_manifest_matched_file_count"] == 0
    assert payload["results_explorer"]["entry_kind"] == "blind_prediction_compare_family"
    assert payload["reason_code"] == "PASS_COMPARE_PENDING_MEASURED_RESPONSE"
    assert payload["summary_line"].endswith("landing_manifest=recorded")
    assert payload["evidence"]["measured_landing_manifest_summary_line"].startswith(
        "E-Defense/PEER measured-response landing manifest: PENDING"
    )
    assert payload["evidence"]["measured_landing_manifest_contract_pass"] is False
