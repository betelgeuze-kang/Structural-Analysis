from pathlib import Path
import sys
from zipfile import ZipFile


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import normalize_canton_tower_reduced_shm_package as canton_normalize  # noqa: E402


def test_normalize_canton_package_creates_csv(tmp_path: Path) -> None:
    zip_path = tmp_path / "Phase_I_data_all.zip"
    with ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "Acc data/accdata_2010-01-19-18.txt",
            "\n".join(
                [
                    "0.1 0.2",
                    "0.2 0.3",
                    "0.3 0.4",
                    "0.4 0.5",
                    "0.5 0.6",
                    "0.6 0.7",
                ]
            ),
        )
        zf.writestr("Wind data/direction/2010-01-19-18.txt", "\n".join(["1", "2", "3", "4", "5", "6"]))
        zf.writestr("Wind data/speed/2010-01-19-18.txt", "\n".join(["7", "8", "9", "10", "11", "12"]))
        zf.writestr("Temperature data/Temperature.txt", "\n".join(str(20 + i) for i in range(60)))

    payload = canton_normalize.normalize_package(zip_path, tmp_path / "normalized", start_hour_index=0, hour_count=1)

    assert payload["contract_pass"] is True
    assert payload["summary"]["generated_csv_count"] == 1
    target_csv = Path(payload["generated_rows"][0]["target_csv"])
    assert target_csv.exists()
    header = target_csv.read_text(encoding="utf-8").splitlines()[0]
    assert "time_sec" in header
    assert "acc_ch01_g" in header
    assert "disp_ch01_m" in header
    assert "wind_direction_deg" in header
    assert "temperature_c" in header
