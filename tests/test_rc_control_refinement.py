"""Finite comparisons are observations, not mesh-error or design certificates."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from tests import test_rc_control_local_research as shared
from tests.test_rc_control_local_research import SOURCE, candidate

from structural_analysis.benchmark import rc_control_refinement as r
from structural_analysis.benchmark import rc_control_reuse as reuse
from structural_analysis.benchmark import rc_control_design as study


# Re-export the exact original fixture functions without importing names that
# parameter injection shadows. Fixture lifetime and implementation are unchanged.
model = shared.model
control_request = shared.control_request
options = shared.options


def session():
    return reuse.RCControlResultSession(source_revision=SOURCE, scope_id="research")


def tolerances():
    # Authored broad software-integration limits, never engineering criteria.
    return tuple(
        r.RCResponseTolerance(name, 1e-7, 0.2)
        for name in (
            "node_translation",
            "reaction_force",
            "reaction_moment",
            "steel_strain",
            "steel_plastic_strain",
            "concrete_tensile_envelope",
        )
    )


def run(model, control_request, options, root, **kwargs):
    return r.run_rc_refinement(
        model,
        control_request,
        session=kwargs.pop("session", session()),
        scope_id="research",
        levels=kwargs.pop("levels", (8, 16, 32)),
        tolerances=kwargs.pop("tolerances", tolerances()),
        output_directory=root,
        **options,
        **kwargs,
    )


@pytest.mark.parametrize(
    "levels",
    [(2, 8), (8, 4, 16), (2, 2, 4), (2, 4, 64), (True, 8, 16), [2, 4, 8], (1, 4, 8)],
)
def test_ladder_rejects_before_output(
    model, control_request, options, tmp_path, levels
):
    with pytest.raises(ValueError):
        run(model, control_request, options, tmp_path / "bad", levels=levels)
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("value", [True, -1.0, float("nan"), float("inf"), "1"])
def test_invalid_tolerance(value):
    with pytest.raises(ValueError):
        r.RCResponseTolerance("node_translation", value, 0)


def test_unknown_response_and_duplicate_response_reject():
    with pytest.raises(ValueError):
        r.RCResponseTolerance("all_accurate", 1.0, 1.0)
    with pytest.raises(ValueError):
        r._plan((8, 16, 32), (tolerances()[0], tolerances()[0]))


def test_comparison_handles_zero_signed_values_and_missing_samples():
    t = r.RCResponseTolerance("reaction_force", 1e-9, 0)
    assert r.compare_response_traces({"a": 0.0}, {"a": -0.0}, t)["exceeded_count"] == 0
    assert (
        r.compare_response_traces({"a": 0.0}, {"a": 5e-10}, t)["status"]
        == "within_declared_tolerance"
    )
    assert (
        r.compare_response_traces({"a": 0.0}, {"a": 2e-9}, t)["status"]
        == "outside_declared_tolerance"
    )
    assert (
        r.compare_response_traces({"a": 1.0}, {"b": 1.0}, t)["status"]
        == "not_comparable"
    )
    assert r.compare_response_traces(None, {"a": 1.0}, t)["status"] == "not_comparable"
    with pytest.raises(ValueError):
        r.compare_response_traces({"a": float("nan")}, {"a": 1.0}, t)


def test_refinement_changes_only_quadrature_and_preserves_original(model):
    before = model.to_dict()
    refined = r.refine_sections(model, 16)
    assert model.to_dict() == before
    assert refined.sections[0]["concrete_layer_count"] == 16
    assert refined.materials == model.materials
    assert r.physical_quantity_basis(
        r.design.calculate_fiber_frame_member_quantities(refined)
    ) == r.physical_quantity_basis(
        r.design.calculate_fiber_frame_member_quantities(model)
    )


def test_real_three_levels_and_repricing_reuse(
    model, control_request, options, tmp_path
):
    s = session()
    first = run(model, control_request, options, tmp_path / "first", session=s)
    assert first["status"] == "comparison_criteria_met"
    assert first["scoped_screen_outcome"] is True
    assert first["new_model_evaluations"] == 3
    assert (
        sum(
            x["new_work"]["known_counters"]["attempted_step_count"]
            for x in first["rows"]
        )
        == 24
    )
    assert all(
        x == "comparison_criteria_met" for x in first["response_status"].values()
    )
    assert first["claims"]["continuum_error_bound_proved"] is False
    again = run(
        model,
        control_request,
        options | {"prices": replace(options["prices"], concrete_per_m3=200.0)},
        tmp_path / "again",
        session=s,
        max_new_model_analyses=0,
    )
    assert (
        again["new_model_evaluations"] == 0 and again["reused_model_evaluations"] == 3
    )
    assert again["adjacent_pairs"] == first["adjacent_pairs"]
    assert all(x["new_work"]["api_invocation_count"] == 0 for x in again["rows"])
    # Steel identities are physical locations, despite shifted concrete fiber indices.
    for pair in first["adjacent_pairs"]:
        assert (
            next(x for x in pair["responses"] if x["response"] == "steel_strain")[
                "matched_count"
            ]
            == 16
        )


def test_concrete_field_does_not_inherit_nodal_pass(
    model, control_request, options, tmp_path
):
    result = run(
        model,
        control_request,
        options,
        tmp_path / "field",
        tolerances=(
            *tolerances(),
            r.RCResponseTolerance("concrete_damage_field", 0.01, 0.01),
        ),
    )
    assert result["response_status"]["node_translation"] == "comparison_criteria_met"
    assert (
        result["response_status"]["concrete_damage_field"] == "comparison_unavailable"
    )
    assert result["scoped_screen_outcome"] is None


def test_zero_tolerance_flags_different_refinement(
    model, control_request, options, tmp_path
):
    result = run(
        model,
        control_request,
        options,
        tmp_path / "strict",
        levels=(2, 4, 8),
        tolerances=(r.RCResponseTolerance("reaction_force", 0, 0),),
    )
    assert result["response_status"]["reaction_force"] == "refinement_required"
    assert result["scoped_screen_outcome"] is None


def test_insufficient_budget_does_not_promote_coarse_result(
    model, control_request, options, tmp_path
):
    result = run(
        model, control_request, options, tmp_path / "budget", max_new_model_analyses=1
    )
    assert result["new_model_evaluations"] == 1
    assert result["rows"][-1]["status"] == "budget_exhausted"
    assert result["scoped_screen_outcome"] is None
    assert result["status"] == "further_verification_required"


def test_unknown_work_stops_and_retains_denominator(
    model, control_request, options, tmp_path, monkeypatch
):
    original = study._evaluate_design_row

    def fault(*a, **k):
        row = original(*a, **k)
        row["invocations"][0]["unknown_execution_work"] = True
        return row

    monkeypatch.setattr(study, "_evaluate_design_row", fault)
    result = run(model, control_request, options, tmp_path / "unknown")
    assert result["unknown_work"] is True
    assert result["new_model_evaluations"] == 1
    assert len(result["rows"]) == 3
    assert result["scoped_screen_outcome"] is None


def test_fine_verification_failure_is_not_physical_rejection(
    model, control_request, options, tmp_path, monkeypatch
):
    original = study._evaluate_design_row

    def fault(m, *a, **k):
        row = original(m, *a, **k)
        if m.sections[0]["concrete_layer_count"] == 32:
            row["full_reference_verification_pass"] = False
            row["status"] = "verification_blocked"
        return row

    monkeypatch.setattr(study, "_evaluate_design_row", fault)
    result = run(model, control_request, options, tmp_path / "failure")
    assert result["rows"][-1]["status"] == "unverified"
    assert result["scoped_screen_outcome"] is None


def test_scope_screen_change_is_not_stable_acceptance(
    model, control_request, options, tmp_path, monkeypatch
):
    original = study._evaluate_design_row

    def fault(m, *a, **k):
        row = original(m, *a, **k)
        row["selection_eligible"] = m.sections[0]["concrete_layer_count"] != 16
        return row

    monkeypatch.setattr(study, "_evaluate_design_row", fault)
    result = run(model, control_request, options, tmp_path / "toggle")
    assert result["status"] == "comparison_criteria_met"
    assert result["screen_decision_stable_over_final_three_levels"] is False
    assert result["scoped_screen_outcome"] is None


def test_refined_pool_search_matches_fully_evaluated_candidate_prices(
    model, control_request, options, tmp_path
):
    s = session()
    alternatives = (candidate("cheap", 0.35), candidate("expensive", 0.5))
    result = r.run_refined_candidate_search(
        model,
        alternatives,
        control_request,
        levels=(8, 16, 32),
        tolerances=tolerances(),
        session=s,
        scope_id="research",
        output_directory=tmp_path / "pool",
        max_new_model_analyses=6,
        **options,
    )
    assert result["status"] == "pool_minimum_confirmed"
    assert result["cost_bound"]["selected_candidate_id"] == "cheap"
    assert result["new_model_evaluations"] == 6
    assert result["cost_bound"]["unverified_response_candidate_ids"] == ["expensive"]
    exhaustive = []
    for name, m in [
        ("baseline", model),
        *(
            (c.candidate_id, r.design.apply_fiber_frame_section_changes(model, c))
            for c in alternatives
        ),
    ]:
        report = run(
            m, control_request, options, tmp_path / f"oracle-{name}", fresh=True
        )
        if report["scoped_screen_outcome"]:
            exhaustive.append(
                (
                    r.design._estimate(
                        r.design.calculate_fiber_frame_member_quantities(m),
                        options["prices"],
                    )["total"],
                    name,
                )
            )
    assert min(exhaustive)[1] == result["cost_bound"]["selected_candidate_id"]
    warm = r.run_refined_candidate_search(
        model,
        alternatives,
        control_request,
        levels=(8, 16, 32),
        tolerances=tolerances(),
        session=s,
        scope_id="research",
        output_directory=tmp_path / "warm",
        max_new_model_analyses=0,
        **options,
    )
    assert warm["new_model_evaluations"] == 0 and warm["reused_model_evaluations"] == 6


def test_missing_cheaper_refinement_blocks_cost_minimum(
    model, control_request, options, tmp_path
):
    result = r.run_refined_candidate_search(
        model,
        (candidate("cheap", 0.35),),
        control_request,
        levels=(8, 16, 32),
        tolerances=tolerances(),
        session=session(),
        scope_id="research",
        output_directory=tmp_path / "limited",
        max_new_model_analyses=3,
        **options,
    )
    assert result["cost_bound"]["pool_minimum_feasible_estimate"] is None
    assert result["refinement_screen_outcomes"]["cheap"] is None


def test_library_hash_streaming_keeps_identical_digest(tmp_path):
    data = b"xyz" * 1_000_000
    path = tmp_path / "library.so"
    path.write_bytes(data)
    assert reuse._file_digest(path) == "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("assembly_reuse", [False, True])
def test_refinement_cli_separate_process_warm_reprice(
    control_request, options, tmp_path, assembly_reuse
):
    import os
    import subprocess
    import sys
    from tests.test_rc_control_local_research import ROOT, experiment_file

    request = tmp_path / "request.json"
    request.write_bytes(study._bytes(control_request.to_dict()))
    config = tmp_path / "refinement.json"
    config.write_bytes(
        study._bytes(
            {
                "schema_version": "local-rc-refinement-input.v1",
                "levels": [8, 16, 32],
                "responses": [
                    {
                        "response": t.response,
                        "absolute": t.absolute,
                        "relative": t.relative,
                    }
                    for t in tolerances()
                ],
            }
        )
    )
    exp = experiment_file(tmp_path / "prices.json", options)
    prefix = [
        sys.executable,
        "-m",
        "structural_analysis.benchmark.rc_control_refinement_cli",
        "--model",
        str(ROOT / "examples/public_rc_fiber_frame_cantilever.json"),
        "--request",
        str(request),
        "--experiment",
        str(exp),
        "--refinement",
        str(config),
        "--source-revision",
        SOURCE,
        "--store-root",
        str(tmp_path / "store"),
    ]
    if assembly_reuse:
        prefix.append("--reuse-line-search-assembly")
    env = os.environ | {"STRUCTURAL_RC_STORE_TOKEN": "test-only-refinement-store-owner"}
    outputs = []
    for name, budget in [("cold", "6"), ("warm", "0")]:
        execution = subprocess.run(
            [
                *prefix,
                "--output",
                str(tmp_path / name),
                "--max-new-model-analyses",
                budget,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert execution.returncode == 0, execution.stderr
        outputs.append(json.loads(execution.stdout))
        plan = json.loads((tmp_path / name / "plan.json").read_bytes())
        assert plan["execution_options"] == {
            "reuse_line_search_assembly": assembly_reuse
        }
        experiment_file(exp, options, 200.0)
    assert outputs[0]["new_model_evaluations"] == 6
    assert outputs[1]["new_model_evaluations"] == 0
    assert outputs[1]["reused_model_evaluations"] == 6
    assert (
        outputs[0]["cost_bound"]["selected_candidate_id"]
        == outputs[1]["cost_bound"]["selected_candidate_id"]
        == "cheap"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": "local-rc-refinement-input.v1",
            "levels": [8, 16, 32],
            "responses": [],
        },
        {"schema_version": "wrong", "levels": [8, 16, 32], "responses": []},
        {
            "schema_version": "local-rc-refinement-input.v1",
            "levels": [8, 16, 32],
            "responses": [{}],
        },
    ],
)
def test_refinement_cli_invalid_config(payload, tmp_path):
    from structural_analysis.benchmark.rc_control_refinement_cli import read_refinement

    path = tmp_path / "bad.json"
    path.write_bytes(study._bytes(payload))
    with pytest.raises(ValueError):
        read_refinement(path)


@pytest.mark.parametrize("bad", [None, 0, 1, "true", [], {}])
def test_reuse_execution_option_rejects_before_context(bad, monkeypatch):
    def forbidden():
        raise AssertionError("invalid options must not inspect the runtime")

    monkeypatch.setattr(reuse, "_runtime_fingerprint", forbidden)
    with pytest.raises(ValueError, match="boolean"):
        reuse.RCControlResultSession(
            source_revision=SOURCE,
            scope_id="research",
            reuse_line_search_assembly=bad,
        )


@pytest.mark.parametrize("enabled", [False, True])
def test_reference_wrapper_preserves_explicit_assembly_option(
    model, control_request, options, tmp_path, monkeypatch, enabled
):
    captured = []

    def capture(*args):
        captured.append(args)
        return {"delegated": True}

    # A delegation test only; the real solver is exercised separately below.
    monkeypatch.setattr(study, "_reference_design_row", capture)
    result = study._evaluate_design_row(
        model,
        None,
        control_request,
        root=tmp_path,
        **options,
        terminal_limits=None,
        reuse_line_search_assembly=enabled,
    )
    assert result == {"delegated": True}
    expected = control_request.api_kwargs() | {"restart": None}
    if enabled:
        expected["reuse_line_search_assembly"] = True
    assert captured[0][4] == expected


def test_assembly_option_preserved_across_durable_reuse(
    model, control_request, options, tmp_path
):
    from tests.test_rc_control_persistence import repository

    def make(enabled):
        return reuse.RCControlResultSession(
            source_revision=SOURCE,
            scope_id="research",
            repository=repository(tmp_path / "store"),
            reuse_line_search_assembly=enabled,
        )

    off = make(False)
    on = make(True)
    original = shared.evaluate(off, model, control_request, options, tmp_path / "off")
    with pytest.raises(reuse.NewAnalysisRequired):
        shared.evaluate(
            on,
            model,
            control_request,
            options,
            tmp_path / "wrong-mode",
            allow_new_analysis=False,
        )
    assert not (tmp_path / "wrong-mode").exists()
    options_copy = on.execution_options
    options_copy["reuse_line_search_assembly"] = False
    assert on.execution_options == {"reuse_line_search_assembly": True}
    result = shared.evaluate(on, model, control_request, options, tmp_path / "on")
    assert result["physics_key"] != original["physics_key"]
    assert result["execution_options"] == {"reuse_line_search_assembly": True}
    assert result["row"]["full_reference_verification_pass"] is True
    assert original["row"]["full_reference_verification_pass"] is True
    assert len(result["row"]["invocations"]) == 2
    for field in ("quantities", "material_estimate", "performance", "screens"):
        assert result["row"][field] == original["row"][field]
    warmed = shared.evaluate(
        make(True),
        model,
        control_request,
        options,
        tmp_path / "warm",
        prices=replace(options["prices"], concrete_per_m3=150.0),
        allow_new_analysis=False,
    )
    assert warmed["reuse_origin"] == "durable_original"
    assert warmed["execution_options"] == result["execution_options"]
    assert warmed["new_work"]["api_invocation_count"] == 0
    assert warmed["fresh_reference_verification_this_call"] is False
    for role, meta in result["row"]["artifacts"].items():
        assert (tmp_path / "on" / meta["path"]).read_bytes() == (
            tmp_path / "warm" / warmed["row"]["artifacts"][role]["path"]
        ).read_bytes()


@pytest.mark.parametrize("enabled", [False, True])
def test_refinement_plan_binds_assembly_option(
    model, control_request, options, tmp_path, enabled
):
    current = reuse.RCControlResultSession(
        source_revision=SOURCE,
        scope_id="research",
        reuse_line_search_assembly=enabled,
    )
    result = r.run_rc_refinement(
        model,
        control_request,
        levels=(2, 4, 8),
        tolerances=tolerances(),
        session=current,
        scope_id="research",
        max_new_model_analyses=0,
        output_directory=tmp_path / "refinement",
        **options,
    )
    plan = json.loads((tmp_path / "refinement/plan.json").read_bytes())
    assert plan["execution_options"] == {"reuse_line_search_assembly": enabled}
    digest = plan.pop("plan_hash")
    assert digest == study._sha(study._bytes(plan)) == result["plan_hash"]
    result = r.run_refined_candidate_search(
        model,
        (candidate("cheap", 0.35),),
        control_request,
        levels=(2, 4, 8),
        tolerances=tolerances(),
        session=current,
        scope_id="research",
        max_new_model_analyses=0,
        output_directory=tmp_path / "search",
        **options,
    )
    plan = json.loads((tmp_path / "search/plan.json").read_bytes())
    assert plan["execution_options"] == {"reuse_line_search_assembly": enabled}
    assert result["cost_bound"]["pool_minimum_feasible_estimate"] is None
