from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import materialize_peer_blind_prediction_sample_measured_response as sample_builder  # noqa: E402


def test_sample_measured_response_materializer_writes_case_bundle(tmp_path: Path) -> None:
    out_root = tmp_path / "sample"
    payload = sample_builder.materialize_sample_bundle(
        {
            "source_family": "edefense_peer_blind_prediction",
            "seed_id": "edefense_peer_blind_prediction_seed_01",
            "excitation_package": {"gm_case_labels": ["Random Noise", "GM1", "GM2"]},
        },
        out_root,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["case_count"] == 3
    assert (out_root / "measured_response_acceleration.csv").exists()
    assert (out_root / "measured_response_drift.csv").exists()
    assert (out_root / "sensor_manifest.json").exists()
