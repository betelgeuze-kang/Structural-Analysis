"""Explicit layer plumbing; authored cases do not establish physical validation."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.api.planar_frame import PlanarFrameConfig, analyze_planar_frame
from structural_analysis.api.nonlinear_fiber_frame import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
)
from structural_analysis.ai.fiber_frame_candidate_learning import (
    candidate_preanalysis_features,
)
from structural_analysis.ai.fiber_frame_physical_identity import (
    fiber_frame_physical_model_identity,
)
from structural_analysis.benchmark.fiber_frame_design import (
    calculate_fiber_frame_member_quantities,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.materials.stateful_fiber_section import (
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.model_ir import parse_model_ir_v2

ROOT = Path(__file__).resolve().parents[1]
LAYERS = [{"y_m": -0.08, "bar_count": 2}, {"y_m": 0.08, "bar_count": 2}]


def canonical(layers=LAYERS):
    p = json.loads(
        (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_text()
    )
    if layers is not False:
        p["sections"][0]["intermediate_steel_layers"] = deepcopy(layers)
    return load_neutral_json_bytes(json.dumps(p).encode())


def test_canonical_layers_bind_physics_quantities_and_policy_context():
    base, layered = canonical(False), canonical()
    config = PublicRCFiberFrameConfig(load_steps=2)
    q0, q1 = [calculate_fiber_frame_member_quantities(m) for m in (base, layered)]
    section = layered.sections[0]
    expected_ratio = (section["top_bar_count"] + section["bottom_bar_count"] + 4) / (
        section["top_bar_count"] + section["bottom_bar_count"]
    )
    assert q1["totals"]["longitudinal_rebar_mass_kg"] == pytest.approx(
        q0["totals"]["longitudinal_rebar_mass_kg"] * expected_ratio
    )
    assert (
        q1["totals"]["gross_concrete_volume_m3"]
        == q0["totals"]["gross_concrete_volume_m3"]
    )
    shifted = canonical([{"y_m": -0.06, "bar_count": 2}, {"y_m": 0.06, "bar_count": 2}])
    assert fiber_frame_physical_model_identity(
        layered
    ) != fiber_frame_physical_model_identity(shifted)
    assert (
        candidate_preanalysis_features(layered, config)[1]
        != candidate_preanalysis_features(shifted, config)[1]
    )
    result = analyze_public_rc_fiber_frame(layered, config)
    assert result.status == "ready"
    assert result.checkpoint_artifact()


@pytest.mark.parametrize(
    "backend", ["numpy_linalg_solve_dense", "scipy_sparse_splu_cpu_exact_1536"]
)
def test_model_ir_layers_execute_public_planar_path(backend):
    p = json.loads((ROOT / "examples/planar_frame_rc_portal.json").read_text())
    p["sections"][0]["parameters"]["intermediate_steel_layers"] = deepcopy(LAYERS)
    d = parse_model_ir_v2(p, require_analysis_ready=True)
    result = analyze_planar_frame(
        d, PlanarFrameConfig(load_steps=2, matrix_backend=backend)
    )
    assert result.converged
    fibers = result.to_dict()["result_ir"]["fiber_results"]
    assert any("steel-intermediate" in str(row) for row in fibers)


@pytest.mark.parametrize(
    "layers",
    [
        None,
        [],
        [{"y_m": 0, "bar_count": True}],
        [{"y_m": 0.3, "bar_count": 2}],
        [{"y_m": 0, "bar_count": 2}, {"y_m": 0, "bar_count": 2}],
        [{"y_m": 0, "bar_count": 2, "area": 1}],
    ],
)
def test_canonical_invalid_layers_fail_before_solver(layers):
    result = analyze_public_rc_fiber_frame(
        canonical(layers), PublicRCFiberFrameConfig(load_steps=2)
    )
    assert result.status == "blocked"
    payload = json.loads((ROOT / "examples/planar_frame_rc_portal.json").read_text())
    payload["sections"][0]["parameters"]["intermediate_steel_layers"] = deepcopy(layers)
    with pytest.raises(ValueError):
        parse_model_ir_v2(payload, require_analysis_ready=True)


def test_layer_factory_preserves_legacy_identity_and_adds_exact_area():
    legacy = make_rectangular_stateful_rc_fiber_section()
    repeated = make_rectangular_stateful_rc_fiber_section(
        intermediate_steel_layers=None
    )
    assert repeated.contract_hash == legacy.contract_hash
    changed = make_rectangular_stateful_rc_fiber_section(
        intermediate_steel_layers=deepcopy(LAYERS)
    )
    added = changed.fibers[len(legacy.fibers) :]
    assert [f.y_m for f in added] == [-0.08, 0.08]
    assert sum(f.area_m2 for f in added) == pytest.approx(4 * 3.87e-4)
