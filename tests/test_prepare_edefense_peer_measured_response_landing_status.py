from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_edefense_peer_measured_response_landing_status as landing_status  # noqa: E402


def test_measured_response_landing_status_marks_pending() -> None:
    payload = landing_status.build_status(
        {
            "expected_groups": {
                "measured_response": {
                    "present": False,
                    "patterns": ["*measurement*.csv", "*sensor*.csv"],
                    "matched_files": [],
                }
            }
        },
        Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01"),
    )

    assert payload["contract_pass"] is False
    assert payload["public_landing_present"] is False
    assert payload["measured_response_present"] is False
    assert payload["channel_inventory_claimed"] is False
    assert payload["reason_code"] == "ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING"
    assert len(payload["expected_patterns"]) == 2


def test_measured_response_landing_status_records_workbook_public_landing_without_overclaiming_channels() -> None:
    payload = landing_status.build_status(
        {
            "expected_groups": {
                "measured_response": {
                    "present": True,
                    "public_landing_present": True,
                    "public_landing_mode": "workbook_only",
                    "patterns": ["*experimentalresults*.xlsx"],
                    "matched_files": ["Experimentalresults.xlsx"],
                    "workbook_candidate_count": 1,
                    "csv_like_candidate_count": 0,
                    "archive_candidate_count": 0,
                    "json_candidate_count": 0,
                    "explicit_channel_claims": {
                        "acceleration": False,
                        "drift": False,
                        "sensor_manifest": False,
                        "basis": "filename_inventory_only",
                    },
                }
            }
        },
        Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01"),
    )

    assert payload["contract_pass"] is True
    assert payload["public_landing_present"] is True
    assert payload["measured_response_present"] is False
    assert payload["channel_inventory_claimed"] is False
    assert payload["landing_mode"] == "workbook_only"
    assert payload["reason_code"] == "PASS_PUBLIC_LANDING_RECORDED_CHANNELS_UNVERIFIED"
    assert payload["summary"]["workbook_candidate_count"] == 1
    assert payload["summary"]["csv_like_candidate_count"] == 0
    assert "channels=unverified" in payload["summary_line"]
    assert "Normalize the landed workbook" in payload["next_action"]
