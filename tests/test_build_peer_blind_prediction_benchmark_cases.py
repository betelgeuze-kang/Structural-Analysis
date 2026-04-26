from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import build_peer_blind_prediction_benchmark_cases as builder  # noqa: E402


def test_build_peer_blind_prediction_cases_marks_pending_without_measured_response() -> None:
    cases_payload, report_payload = builder.build_cases(
        {
            "contract_pass": True,
            "source_family": "edefense_peer_blind_prediction",
            "readiness": {"public_input_ready": True},
        },
        {"contract_pass": False, "summary": {}},
        {
            "candidate_cases": [
                {"case_id": "seed::gm1", "excitation_label": "GM1", "excitation_kind": "ground_motion"},
                {"case_id": "seed::gm2", "excitation_label": "GM2", "excitation_kind": "ground_motion"},
            ]
        },
    )

    assert len(cases_payload["cases"]) == 2
    assert cases_payload["cases"][0]["compare_ready"] is False
    assert report_payload["summary"]["measured_response_ready"] is False
    assert report_payload["reason_code"] == "PASS_PENDING_MEASURED_RESPONSE"


def test_build_peer_blind_prediction_cases_marks_ready_with_measured_response() -> None:
    cases_payload, report_payload = builder.build_cases(
        {
            "contract_pass": True,
            "source_family": "edefense_peer_blind_prediction",
            "readiness": {"public_input_ready": True},
        },
        {"contract_pass": True, "summary": {"acceleration_channel_count": 6, "drift_channel_count": 2, "sensor_row_count": 3}},
        {
            "candidate_cases": [
                {"case_id": "seed::gm1", "excitation_label": "GM1", "excitation_kind": "ground_motion"},
            ]
        },
    )

    assert cases_payload["cases"][0]["compare_ready"] is True
    assert report_payload["summary"]["measured_response_ready"] is True
    assert report_payload["reason_code"] == "PASS"
