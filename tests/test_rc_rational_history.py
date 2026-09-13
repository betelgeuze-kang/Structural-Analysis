"""Saved rational histories support counterfactuals without changing accepted results."""

from copy import deepcopy
from decimal import localcontext, ROUND_DOWN
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.materials.retained_fiber_strain import (
    RetainedStrainSteel,
    RetainedStrainConcrete,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "rational_history", ROOT / "scripts/diagnose_rc_rational_history.py"
)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def test_ordered_components_close_with_rounding_history_interaction_and_load():
    high = [[F(1, 3), F(5, 3)], [F(2), F(9)]]
    finite = [[F(float(x)) for x in row] for row in high]
    orders = diag.decompose(finite, high, F(8), F(2))
    assert all(sum(values.values(), F()) == 8 for values in orders.values())
    assert (
        orders["reference_parent_then_history"]["finite_coordinate_difference"]
        != orders["history_then_candidate_parent"]["finite_coordinate_difference"]
    )
    assert orders["reference_parent_then_history"]["external_load_difference"] == -2
    assert orders["reference_parent_then_history"]["returned_stress_rounding"] != 0


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    p = tmp_path_factory.mktemp("rational-history") / "study"
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
        material_arithmetic="retained-strain",
        fiber_strain_evaluation="retained-coordinate",
        force_accumulation="rational",
    )
    return p


def test_original_endpoints_and_actual_nested_call_counts_without_solving(
    study, monkeypatch
):
    from structural_analysis.elements import StatefulFiberBeam2D
    from structural_analysis.materials.stateful_fiber_section import (
        StatefulRCFiberSection,
    )
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )

    counts = {"selected": 0, "base": 0}
    for group, classes in [
        ("selected", [RetainedStrainSteel, RetainedStrainConcrete]),
        ("base", [BilinearCombinedHardeningSteel, AsymmetricConcreteDamageMaterial]),
    ]:
        for cls in classes:
            original = cls.integrate

            def counted(self, strain, parent, original=original, group=group):
                counts[group] += 1
                return original(self, strain, parent)

            monkeypatch.setattr(cls, "integrate", counted)

    def forbidden(*a, **k):
        pytest.fail("diagnostic must not solve or commit")

    monkeypatch.setattr(StatefulFiberBeam2D, "integrate", forbidden)
    monkeypatch.setattr(StatefulRCFiberSection, "integrate", forbidden)
    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    with localcontext() as context:
        context.prec = 7
        context.rounding = ROUND_DOWN
        result = diag.diagnose(study)
    assert result["target_count"] == 3 and len(result["rows"]) == 81
    assert counts == {"selected": 1008, "base": 1008}
    assert result["work"]["total_material_integrate_entries"] == sum(counts.values())
    assert result["work"]["assembly_verifier_material_integrations"] == 0
    assert "material_integrations" not in result["work"]
    assert (
        result["work"]["selected_material_trial_calls"]
        == result["work"]["nested_original_base_calls"]
        == 1008
    )
    assert result["work"]["original_material_endpoints_verified"] == 504
    assert result["work"]["independent_100_digit_stress_evaluations"] == 1008
    assert result["work"]["original_assembly_verifications"] == 6
    assert result["work"]["native_reopens"] == 2
    assert result["work"]["newton_solves"] == result["work"]["state_commits"] == 0
    assert all(row["exact_rational_decompositions_close"] for row in result["rows"])
    assert {r["field"].split("/")[0] for r in result["rows"]} == {
        "member",
        "section",
        "reaction",
    }


@pytest.mark.parametrize(
    "field",
    ["identity", "rational_force", "trial_state", "low_coordinate", "section_history"],
)
def test_rehashed_altered_original_records_fail(study, tmp_path, field):
    p = tmp_path / "study"
    shutil.copytree(study, p)
    if field == "identity":
        path = p / "request.json"
        d = json.loads(path.read_text())
        d["force_accumulation"] = "binary64"
        path.write_text(json.dumps(d))
    else:
        path = p / "secant/001-1-step.json"
        step = json.loads(path.read_text())
        er = step["trial_assembly"]["member_assemblies"][0]["element_response"]
        if field == "rational_force":
            er["rational_force_local"][0][0] = str(
                int(er["rational_force_local"][0][0]) + 1
            )
        elif field == "trial_state":
            er["section_responses"][0]["fiber_responses"][0]["trial_state"][
                "tensile_history_strain"
            ] += 0.01
        elif field == "low_coordinate":
            er["local_displacement_compensation"][0] += 1e-9
        payload = deepcopy(step)
        payload.pop("step_hash")
        step["step_hash"] = diag.canonical_hash(payload)
        path.write_text(json.dumps(step))
        pf = p / "secant/path.json"
        d = json.loads(pf.read_text())
        d["response_history"][1]["source_step_hash"] = step["step_hash"]
        if field == "section_history":
            d["response_history"][1]["section_results"][0]["section_state_hash"] = (
                "sha256:" + "1" * 64
            )
        payload = deepcopy(d)
        payload.pop("path_hash")
        d["path_hash"] = diag.canonical_hash(payload)
        pf.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="rational"):
        diag.diagnose(p)
