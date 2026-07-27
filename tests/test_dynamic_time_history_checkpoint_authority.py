from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation" / "phase1" / "dynamic_time_history_contract_stub.py"
GROUND_MOTION = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "open_data"
    / "seismic"
    / "el_centro_like_60s_dt0p01.csv"
)


def test_dynamic_time_history_report_mints_source_authentic_checkpoint(
    tmp_path: Path,
) -> None:
    output = tmp_path / "dynamic_time_history_report.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ground-motion-csv",
            str(GROUND_MOTION),
            "--no-use-adaptive-newton",
            "--out",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    checkpoint = payload["transient_checkpoint"]
    assert payload["contract_pass"] is True
    assert payload["checks"]["source_authentic_checkpoint_pass"] is True
    assert checkpoint["authority"] == "source_authentic_checkpoint"
    assert checkpoint["self_consistent_checkpoint"] is True
    assert checkpoint["source_authentic_checkpoint"] is True
    assert checkpoint["parent_content_bound"] is True
    assert checkpoint["force_history_sample_count"] == 6001
    for field in (
        "parent_content_hash",
        "force_history_hash",
        "initial_state_hash",
        "source_result_hash",
        "replay_result_hash",
    ):
        assert checkpoint[field].startswith("sha256:")
    assert checkpoint["newmark_replay_pass"] is True
    assert checkpoint["equilibrium_replay_pass"] is True
    assert checkpoint["work_dissipation_replay_pass"] is True
