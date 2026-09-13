"""Finite fiber projection and native history effects reach the failed force fields."""

from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "fiber_history", ROOT / "scripts/diagnose_rc_control_fiber_history.py"
)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def test_direct_fiber_projection_matches_independent_decimal_hermite():
    length, xi, y = 2.7, 0.7745966692414834, 0.15
    high = [0.001, -0.023, 0.0001, 0.006, -0.019, 0.0003]
    low = [1e-20, -3e-19, 7e-22, 0.0, -9e-20, 1e-22]
    response = {
        "generalized_strains": [[0.01, 0.04]],
        "local_displacements": high,
        "local_displacement_compensation": low,
    }
    with localcontext() as c:
        c.prec = 100
        D = Decimal.from_float
        L, x, yy = map(D, (length, xi, y))
        u = [D(a) + D(b) for a, b in zip(high, low, strict=True)]
        ratio = (x + 1) / 2
        curvature = (
            (-6 + 12 * ratio) * u[1] / L**2
            + (-4 + 6 * ratio) * u[2] / L
            + (6 - 12 * ratio) * u[4] / L**2
            + (-2 + 6 * ratio) * u[5] / L
        )
        direct = (u[3] - u[0]) / L - yy * curvature
    assert diag.fiber_strain_levels(response, 0, length, xi, y)[2] == float(direct)


def test_projection_cancellation_and_both_interaction_orders_are_retained():
    response = {
        "generalized_strains": [[1.0, 1.0 + 2**-27]],
        "local_displacements": [0.0] * 6,
    }
    original, projected, _ = diag.fiber_strain_levels(
        response, 0, 1.0, 0.0, 1.0 - 2**-27
    )
    assert original == 0 and projected == 2**-54
    values = [[F(x) for x in range(6)], [F(2 * x + 10) for x in range(6)]]
    orders = diag.ordered_components(values, F(31), F(3))
    assert orders["reference_parent_then_history"]["parent_history_difference"] == 15
    assert orders["history_then_candidate_parent"]["parent_history_difference"] == 10
    assert all(sum(row.values()) == 31 for row in orders.values())
    assert orders["reference_parent_then_history"]["external_load_difference"] == -3


@pytest.fixture(scope="module", params=["generalized", "direct-coordinate"])
def study(tmp_path_factory, request):
    p = tmp_path_factory.mktemp("fiber-history") / "study"
    benchmark_rc_control_seed_paths(
        load_neutral_json(
            ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
        ),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-5, -2e-5, -1e-5), allow_reversals=True, maximum_reversals=1
        ),
        source_revision="0" * 40,
        output_directory=p,
        strain_evaluation="exact-rational",
        coordinate_precision="twofold-increment",
        material_arithmetic="stable-stress",
        fiber_strain_evaluation=request.param,
    )
    return p


def test_original_cyclic_trials_verified_with_no_section_element_or_newton_calls(
    study, monkeypatch
):
    from structural_analysis.materials.stateful_fiber_section import (
        StatefulRCFiberSection,
    )
    from structural_analysis.elements import StatefulFiberBeam2D
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )
    from structural_analysis.materials.stable_stress import (
        StableStressSteel,
        StableStressConcrete,
    )

    calls = []
    for cls in (StableStressSteel, StableStressConcrete):
        original = cls.integrate

        def counted(self, strain, parent, original=original):
            calls.append(type(self).__name__)
            return original(self, strain, parent)

        monkeypatch.setattr(cls, "integrate", counted)

    def forbidden(*args, **kwargs):
        pytest.fail("counterfactual must not solve or commit")

    monkeypatch.setattr(StatefulRCFiberSection, "integrate", forbidden)
    monkeypatch.setattr(StatefulFiberBeam2D, "integrate", forbidden)
    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    result = diag.diagnose(study)
    assert result["target_count"] == 3 and len(result["rows"]) == 45
    direct = result["fiber_strain_evaluation"] == "direct-coordinate"
    assert (
        result["work"]["material_trial_calls"]
        == len(calls)
        == 3 * 84 * (4 if direct else 12)
    )
    if direct:
        for row in result["rows"]:
            for values in row["orders"].values():
                assert all(
                    values[k] == 0
                    for k in diag.STRAIN_EFFECTS
                    if k != "finite_coordinate_difference"
                )
    assert result["work"]["original_material_responses_verified"] == 3 * 84 * 2
    assert result["work"]["newton_solves"] == result["work"]["state_commits"] == 0
    assert all(row["exact_rational_decompositions_close"] for row in result["rows"])


@pytest.mark.parametrize(
    "field", ["fiber_strain", "trial_state", "generalized_strain", "local_coordinate"]
)
def test_rehashed_changed_saved_material_evidence_rejected(study, tmp_path, field):
    import shutil

    p = tmp_path / "study"
    shutil.copytree(study, p)
    target = p / "secant/001-1-step.json"
    step = json.loads(target.read_text())
    e = step["trial_assembly"]["member_assemblies"][0]["element_response"]
    if field == "fiber_strain":
        e["section_responses"][0]["fiber_strains"][0] += 0.01
    elif field == "trial_state":
        e["section_responses"][0]["fiber_responses"][0]["trial_state"][
            "tensile_history_strain"
        ] += 0.01
    elif field == "local_coordinate":
        e["local_displacements"][0] += 0.01
    else:
        e["generalized_strains"][0][0] += 0.01
    payload = deepcopy(step)
    payload.pop("step_hash")
    step["step_hash"] = canonical_hash(payload)
    target.write_text(json.dumps(step))
    pathfile = p / "secant/path.json"
    path = json.loads(pathfile.read_text())
    path["response_history"][1]["source_step_hash"] = step["step_hash"]
    payload = deepcopy(path)
    payload.pop("path_hash")
    import hashlib

    path["path_hash"] = (
        "sha256:" + hashlib.sha256(diag.force.canonical(payload)).hexdigest()
    )
    pathfile.write_text(json.dumps(path))
    with pytest.raises(
        ValueError,
        match="original.*(material response replay|fiber strain projection|generalized strain evaluation)",
    ):
        diag.diagnose(p)
