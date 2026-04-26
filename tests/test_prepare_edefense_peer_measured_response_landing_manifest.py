import sys
from pathlib import Path


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_edefense_peer_measured_response_landing_manifest as landing_manifest  # noqa: E402


def test_measured_response_landing_manifest_reports_pending_manual_landing() -> None:
    payload = landing_manifest.build_manifest(
        {
            "expected_groups": {
                "measured_response": {
                    "patterns": [
                        "*response*.csv",
                        "*measurement*.csv",
                        "*sensor*.csv",
                        "*drift*.csv",
                        "*accel*.csv",
                    ],
                    "matched_files": [],
                }
            }
        },
        Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01"),
    )

    assert payload["contract_pass"] is False
    assert payload["landing_state"] == "pending"
    assert payload["reason_code"] == "ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING"
    assert payload["summary_line"].startswith("E-Defense/PEER measured-response landing manifest: PENDING")
    assert len(payload["expected_patterns"]) == 5
    assert payload["matched_files"] == []


def test_measured_response_landing_manifest_reports_ready_bundle(tmp_path: Path) -> None:
    target = tmp_path / "measured_story_drifts.csv"
    target.write_text("time_s,story_label,drift_ratio_x\n0.0,L2,0.001\n", encoding="utf-8")
    payload = landing_manifest.build_manifest(
        {
            "expected_groups": {
                "measured_response": {
                    "patterns": ["*measurement*.csv", "*sensor*.csv", "*drift*.csv"],
                }
            }
        },
        tmp_path,
    )

    assert payload["contract_pass"] is True
    assert payload["landing_state"] == "recorded"
    assert payload["reason_code"] == "PASS"
    assert payload["summary_line"].startswith("E-Defense/PEER measured-response landing manifest: RECORDED")
    assert payload["matched_files"] == ["measured_story_drifts.csv"]
    assert "ready for normalization" in payload["reason"]
