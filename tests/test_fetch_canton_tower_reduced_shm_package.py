from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import fetch_canton_tower_reduced_shm_package as canton_fetch  # noqa: E402


def test_normalize_target_name_for_minimum_package() -> None:
    assert (
        canton_fetch._normalize_target_name(
            "https://polyucee.hk/ceyxia/benchmark/Phase%20I%20data/Phase_I_measurement%20description.pdf"
        )
        == "Phase_I_measurement_description.pdf"
    )
    assert (
        canton_fetch._normalize_target_name(
            "https://polyucee.hk/ceyxia/benchmark/Phase%20I%20data/Phase%20I%20data_all.zip"
        )
        == "Phase_I_data_all.zip"
    )
