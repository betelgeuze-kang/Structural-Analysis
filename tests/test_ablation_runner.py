from pathlib import Path
import json
import subprocess
import sys

import pytest

REPORT = Path(
    "implementation/phase1/release/design_optimization/design_optimization_ablation_report.json"
)
DATASET = Path(
    "implementation/phase1/release/design_optimization/design_optimization_dataset.npz"
)


def _ensure_report():
    if REPORT.exists():
        return
    if not DATASET.exists():
        pytest.skip(
            "legacy design-optimization ablation requires the non-committed "
            "design_optimization_dataset.npz evidence input"
        )
    subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_design_optimization_ablation.py",
            "--budget",
            "low",
            "--objective-profile",
            "cost_first",
        ],
        check=True,
    )


def test_ablation_report_has_required_scenarios():
    _ensure_report()
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    scenario_ids = {row["scenario_id"] for row in payload["scenarios"]}
    assert {
        "slab_off",
        "beam_wall_only",
        "connection_detailing_only",
        "mixed_full",
        "zone_locked_core",
        "zone_locked_perimeter",
    } <= scenario_ids
    mixed = next(
        row for row in payload["scenarios"] if row["scenario_id"] == "mixed_full"
    )
    assert "dominant_action_family_ratio" in mixed
