"""Saved-force arithmetic is verified before ordered counterfactual attribution."""

from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "force_diag", ROOT / "scripts/diagnose_rc_control_force_error.py"
)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def test_exact_geometry_coefficients_match_independent_decimal_polynomial():
    L, x = 2.7, 0.7745966692414834
    with localcontext() as ctx:
        ctx.prec = 100
        length = Decimal.from_float(L)
        ratio = (Decimal.from_float(x) + 1) / 2
        expected = [
            [-1 / length, 0, 0, 1 / length, 0, 0],
            [
                0,
                (-6 + 12 * ratio) / length**2,
                (-4 + 6 * ratio) / length,
                0,
                (6 - 12 * ratio) / length**2,
                (-2 + 6 * ratio) / length,
            ],
        ]
    assert np.array_equal(
        [[float(v) for v in row] for row in diag.rational_b(L, x)],
        [[float(v) for v in row] for row in expected],
    )


def test_attribution_preserves_cancellation_and_exposes_residual_stress_effect():
    ref = {stage: {"member/M1/0": Fraction(0)} for stage in diag.STAGES}
    values = [Fraction(2), Fraction(1, 2), Fraction(3, 4), Fraction(1, 4)]
    candidate = {
        stage: {"member/M1/0": v} for stage, v in zip(diag.STAGES, values, strict=True)
    }
    row = diag.attribute(ref, candidate, 1e-10, 1e-8)[0]
    assert list(row["components_si"].values()) == [1.5, -0.25, 0.5, 0.25]
    assert row["difference_candidate_minus_reference_si"] == sum(
        row["components_si"].values()
    )
    assert row["exact_rational_decomposition_closes"]


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    path = tmp_path_factory.mktemp("force-diagnostic") / "study"
    benchmark_rc_control_seed_paths(
        load_neutral_json(
            ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
        ),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-5, -2e-5, -1e-5), allow_reversals=True, maximum_reversals=1
        ),
        source_revision="0" * 40,
        output_directory=path,
        strain_evaluation="exact-rational",
        coordinate_precision="twofold-increment",
    )
    return path


def test_saved_cyclic_response_replays_without_material_or_newton_execution(
    study, monkeypatch
):
    from structural_analysis.elements import StatefulFiberBeam2D
    from structural_analysis.materials.stateful_fiber_section import (
        StatefulRCFiberSection,
    )
    from structural_analysis.assembly import (
        stateful_fiber_frame2d_displacement_control as control,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("diagnostic must not perform integration or Newton solves")

    monkeypatch.setattr(StatefulFiberBeam2D, "integrate", forbidden)
    monkeypatch.setattr(StatefulRCFiberSection, "integrate", forbidden)
    monkeypatch.setattr(control, "newton_raphson_vector", forbidden)
    result = diag.diagnose(study)
    assert result["target_count"] == 3 and len(result["rows"]) == 45
    assert result["work"] == {
        "model_compilations": 1,
        "original_step_force_replays": 6,
        "section_integrations": 0,
        "constituent_integrations": 0,
        "newton_solves": 0,
        "state_commits": 0,
    }
    assert len(result["input_files"]) == 10
    assert all(row["exact_rational_decomposition_closes"] for row in result["rows"])


@pytest.mark.parametrize(
    "field", ["stress", "resultant", "local", "global", "reaction", "transform"]
)
def test_rehashed_changed_original_force_data_is_rejected(study, tmp_path, field):
    # A standalone input copy; the complete original fixture remains intact.
    import shutil

    path = tmp_path / "study"
    shutil.copytree(study, path)
    target = path / "secant/001-1-step.json"
    step = json.loads(target.read_text())
    member = step["trial_assembly"]["member_assemblies"][0]
    if field == "stress":
        member["element_response"]["section_responses"][0]["fiber_stresses_mpa"][0] += 1
    elif field == "resultant":
        member["element_response"]["section_responses"][0]["resultants"][
            "axial_force_kn"
        ] += 1
    elif field == "local":
        member["element_response"]["internal_force_local"][0] += 1
    elif field == "global":
        member["internal_load_global"][0] += 1
    elif field == "reaction":
        step["trial_assembly"]["reactions_global"][0] += 1
    else:
        member["transformation_global_to_local"][0][0] += 1
    payload = deepcopy(step)
    payload.pop("step_hash")
    step["step_hash"] = canonical_hash(payload)
    target.write_text(json.dumps(step))
    history_file = path / "secant/path.json"
    history = json.loads(history_file.read_text())
    history["response_history"][1]["source_step_hash"] = step["step_hash"]
    history.pop("path_hash")
    import hashlib

    history["path_hash"] = (
        "sha256:" + hashlib.sha256(diag.canonical(history)).hexdigest()
    )
    history_file.write_text(json.dumps(history))
    with pytest.raises(ValueError, match="original arithmetic replay differs"):
        diag.diagnose(path)


def test_cli_rejects_output_inside_original_before_any_work(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "diagnostic",
            "--study",
            str(tmp_path),
            "--output",
            str(tmp_path / "new.json"),
        ],
    )
    monkeypatch.setattr(
        diag, "diagnose", lambda *a: pytest.fail("must reject before work")
    )
    with pytest.raises(SystemExit) as caught:
        diag.main()
    assert caught.value.code == 2
    assert not (tmp_path / "new.json").exists()
