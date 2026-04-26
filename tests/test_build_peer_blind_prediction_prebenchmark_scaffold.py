from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import build_peer_blind_prediction_prebenchmark_scaffold as scaffold_builder  # noqa: E402


def test_prebenchmark_scaffold_stays_pending_without_measured_response() -> None:
    payload = scaffold_builder.build_scaffold(
        {
            "contract_pass": True,
            "source_family": "edefense_peer_blind_prediction",
            "seed_id": "edefense_peer_blind_prediction_seed_01",
            "benchmark_track": "blind_prediction_dynamic_holdout",
            "readiness": {
                "public_input_ready": True,
                "measured_response_ready": False,
                "benchmark_case_ready": False,
                "compare_report_ready": False,
                "viewer_entry_ready": False,
            },
            "excitation_package": {"gm_case_labels": ["Random Noise", "GM1", "GM2"]},
        },
        {
            "measured_response_present": False,
        },
    )

    assert payload["contract_pass"] is True
    assert payload["pending_boundary"] == "measured_response_missing"
    assert payload["readiness"]["benchmark_case_ready"] is False
    assert len(payload["candidate_cases"]) == 3
    assert payload["candidate_cases"][0]["compare_report_status"] == "pending_measured_response"
