import json
from pathlib import Path
import sys

import numpy as np
from scipy.io import savemat


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import canton_tower_reduced_order_utils as rom_utils  # noqa: E402
import run_canton_tower_reduced_order_compare as rom_compare  # noqa: E402


def test_summarize_canton_tower_system_matrices_extracts_modes(tmp_path: Path) -> None:
    mat_path = tmp_path / "system_matrices.mat"
    savemat(
        mat_path,
        {
            "kk_global": np.diag([4.0, 9.0, 16.0]),
            "mm_global": np.eye(3),
            "kk_01": np.diag([4.0, 9.0]),
            "mm_01": np.eye(2),
        },
    )

    payload = rom_utils.summarize_canton_tower_system_matrices(mat_path, max_modes=3)

    assert payload["global_dof_count"] == 3
    assert payload["segment_matrix_pair_count"] == 1
    assert payload["global_matrix_present"] is True
    assert payload["global_mode_frequencies_hz"][0] > 0.0


def test_build_canton_reduced_order_compare_report_uses_summary(tmp_path: Path) -> None:
    mat_path = tmp_path / "system_matrices.mat"
    savemat(
        mat_path,
        {
            "kk_global": np.diag([4.0, 9.0, 16.0]),
            "mm_global": np.eye(3),
            "kk_01": np.diag([4.0, 9.0]),
            "mm_01": np.eye(2),
        },
    )

    report = rom_compare.build_report(
        mat_path=mat_path,
        normalization_report={"summary": {"generated_channel_count_max": 2}},
        conversion_report={"outputs": {"benchmark_case_count": 5, "dynamic_case_count": 5}},
        benchmark_payload={"cases": [{"case_id": "canton_001"}]},
    )

    assert report["contract_pass"] is True
    assert report["summary"]["global_dof_count"] == 3
    assert report["summary"]["observed_channel_count"] == 2
    assert report["summary"]["benchmark_case_count"] == 5
    assert "Canton Tower reduced-order compare: PASS" in report["summary_line"]
