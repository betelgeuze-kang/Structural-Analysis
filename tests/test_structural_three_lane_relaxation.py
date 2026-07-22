from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PHASE1 = ROOT / "implementation" / "phase1"
SCRIPT = PHASE1 / "structural_three_lane_relaxation.py"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

spec = importlib.util.spec_from_file_location("structural_three_lane_relaxation", SCRIPT)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_three_lane_frame_topology_is_structural_and_linear_in_node_count() -> None:
    frame = module.build_three_lane_frame(node_count=5)

    assert frame.node_count == 5
    assert frame.point_count == 15
    assert sum(frame.fixed) == 3
    assert len(frame.spring_i) == 35


def test_relaxation_is_deterministic_and_uses_structural_contract_names() -> None:
    kwargs = {
        "node_count": 12,
        "base_force": 120.0,
        "max_steps": 24,
        "tol": 1e-2,
        "decay_hint": 0.96,
    }

    first = module.run_relaxation_case(**kwargs)
    second = module.run_relaxation_case(**kwargs)

    assert first == second
    assert first["model"] == "three_lane_frame_soa"
    assert first["point_count"] == 36
    assert first["spring_count"] == 91
    assert "bead_count" not in first


def test_workload_contract_matches_the_structural_relaxation_model() -> None:
    result = module.run_workload_pass(node_count=12, steps=3)

    assert result["model"] == "three_lane_frame_soa"
    assert result["point_count"] == 36
    assert result["spring_count"] == 91
    assert result["work_scalar"] >= 0.0
