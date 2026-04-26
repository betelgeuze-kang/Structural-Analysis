from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import prepare_edefense_peer_measured_response_landing_template as template_builder  # noqa: E402


def test_measured_response_template_surfaces_bundle_layout() -> None:
    payload = template_builder.build_template(
        {
            "source_family": "edefense_peer_blind_prediction",
            "seed_id": "edefense_peer_blind_prediction_seed_01",
            "local_input_root": "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01",
            "expected_groups": {
                "measured_response": {
                    "patterns": ["*response*.csv", "*sensor*.csv"],
                }
            },
        },
        {
            "input_root": "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01",
            "excitation_package": {"gm_case_labels": ["Random Noise", "GM1", "GM2"]},
        },
    )

    assert payload["contract_pass"] is True
    assert len(payload["accepted_file_patterns"]) == 2
    assert len(payload["preferred_bundle_layout"]) == 3
    assert payload["channel_groups"][0]["group_id"] == "acceleration"
    assert payload["gm_case_labels"] == ["Random Noise", "GM1", "GM2"]
