from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


PHASE1 = Path(__file__).resolve().parent.parent / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

SCRIPT_PATH = PHASE1 / "run_g1_active_frontier_shell_policy_replay_probe.py"
SPEC = importlib.util.spec_from_file_location(
    "run_g1_active_frontier_shell_policy_replay_probe", SCRIPT_PATH
)
assert SPEC is not None
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_anchor_row_reconstructs_external_load_from_components() -> None:
    residual = np.asarray([0.5, -2.0, 1.0], dtype=np.float64)
    components = {
        "frame": np.asarray([1.0, 0.0, 4.0], dtype=np.float64),
        "shell_bending_drilling": np.asarray([0.25, -0.5, 2.0], dtype=np.float64),
    }

    row = probe._anchor_row(
        residual=residual,
        component_forces=components,
        free=np.asarray([10, 20, 30], dtype=np.int64),
        global_dof=20,
    )

    assert row["found"] is True
    assert row["reduced_index"] == 1
    assert row["internal_sum_n"] == -0.5
    assert row["inferred_external_load_n"] == 1.5
    assert row["dominant_internal_component"] == "shell_bending_drilling"


def test_best_policy_uses_lowest_residual_inf() -> None:
    best = probe._best_policy(
        [
            {"policy": "all_components", "status": "ready", "residual_inf_n": 3.0},
            {
                "policy": "structural_components_only",
                "status": "ready",
                "residual_inf_n": 1.0,
            },
            {"policy": "blocked", "status": "blocked", "residual_inf_n": 0.0},
        ]
    )

    assert best["policy"] == "structural_components_only"


def test_parse_policies_defaults_when_empty() -> None:
    assert probe._parse_policies("") == probe.DEFAULT_POLICIES
    assert probe._parse_policies("all_components, structural_components_only") == (
        "all_components",
        "structural_components_only",
    )
