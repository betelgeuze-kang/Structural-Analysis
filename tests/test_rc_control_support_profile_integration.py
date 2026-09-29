"""Authored small-model integration checks, not measured physical validation.

The prices and refinement tolerances below are synthetic software controls.
No timing, AI speedup, construction savings or design approval is inferred.
"""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_cost_search as search
from structural_analysis.benchmark import rc_control_refinement as refinement
from structural_analysis.benchmark.rc_control_reuse import RCControlResultSession
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from tests.test_rc_control_durable_research import (
    TENANT,
    evaluate,
    session as durable_session,
)
from tests.test_rc_fiber_pin_roller_beam_public import _model, _request


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "a" * 40  # Explicit test label; the real runtime fingerprint is still bound.


def _options():
    return {
        "history_limits": design.FiberFrameHistoryLimits(1, 1),
        "material_limits": design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        "prices": design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-30", "synthetic regression; not a quote"
        ),
    }


def _profile(profile, *, preload=True):
    if profile == "pin_roller":
        request = _request((-1e-6, -2e-6))
        if preload:
            request = replace(request, constant_nodal_loads=(("N4", 0.0, -0.01, 0.0),))
        return _model(), request, 1.9
    model = load_neutral_json_bytes(
        (
            ROOT / "examples/research/rc_internal_portal_20mm/original-model.json"
        ).read_bytes()
    )
    return (
        model,
        BoundedRCFiberDirectControlRequest(
            control_global_dof=9,
            targets_m=(-1e-6, -2e-6),
            experimental_two_fixed_endpoints=True,
            constant_nodal_loads=(
                (("N3", 0.0, -0.01, 0.0), ("N4", 0.0, -0.01, 0.0)) if preload else ()
            ),
        ),
        10.0,
    )


def _original(report, directory, role="result"):
    return (directory / report["row"]["artifacts"][role]["path"]).read_bytes()


def _assert_quantity(quantities, length, width=0.4):
    assert sum(row["length_m"] for row in quantities["members"]) == pytest.approx(
        length
    )
    assert quantities["totals"]["gross_concrete_volume_m3"] == pytest.approx(
        width * 0.6 * length
    )
    assert quantities["totals"]["longitudinal_rebar_mass_kg"] == pytest.approx(
        8 * 0.000387 * length * 7850
    )


def _assert_direct_original(report, directory, profile, request, length, width=0.4):
    row = report["row"]
    assert row["full_reference_verification_pass"] is True
    assert row["selection_eligible"] is True
    assert not report["new_work"]["unknown_work"]
    assert [r["phase"] for r in row["invocations"]] == ["analysis", "verification"]
    assert all(not r["unknown_execution_work"] for r in row["invocations"])
    payload = json.loads(_original(report, directory))
    flag = (
        "experimental_pin_roller_beam"
        if profile == "pin_roller"
        else "experimental_two_fixed_endpoints"
    )
    assert payload["request"][flag] is True
    assert payload["path"]["accepted_target_prefix_m"] == list(request.targets_m)
    assert len(payload["response_history"]) == len(request.targets_m)
    if request.constant_nodal_loads:
        assert (
            payload["request"]["constant_nodal_loads"]
            == request.to_dict()["constant_nodal_loads"]
        )
        assert payload["preload_response"] is not None
    _assert_quantity(row["quantities"], length, width)
    assert row["material_estimate"]["total"] == pytest.approx(
        width * 0.6 * length * 100 + 8 * 0.000387 * length * 7850
    )


def _candidate():
    return design.FiberFrameDesignCandidate(
        "narrower", (design.FiberFrameSectionChange("RC1", width_m=0.36),)
    )


def _local_session():
    return RCControlResultSession(source_revision=SOURCE, scope_id="research")


def _tolerances():
    # Broad authored comparison controls, never engineering acceptance criteria.
    return (
        refinement.RCResponseTolerance("node_translation", 1e-8, 1),
        refinement.RCResponseTolerance("reaction_force", 1, 1),
        refinement.RCResponseTolerance("steel_strain", 1e-6, 1),
    )


def test_pin_roller_durable_reopen_reprice_rescreen_preserves_full_path(tmp_path):
    model, request, length = _profile("pin_roller", preload=False)
    original_model = model.canonical_payload()
    options = _options()
    store = tmp_path / "store"
    chunk_options = {"chunk_target_count": 1, "max_chunks_per_call": 1}
    prefix_session = durable_session(store, **chunk_options)
    prefix = evaluate(
        prefix_session,
        model,
        request,
        options,
        tmp_path / "prefix",
    )
    assert prefix["job"]["status"] == "checkpointed"
    assert prefix["job"]["progress"]["completed_steps"] == 1
    assert not prefix["row"]["full_reference_verification_pass"]
    assert "result" not in prefix["row"]["artifacts"]
    assert prefix["new_work"]["api_invocation_count"] == 2
    prefix_service = prefix_session._store(prefix["physics_key"])
    saved_bytes = prefix_service.read_checkpoint(
        prefix["job"]["job_id"], tenant_id="lab", authorization_token=TENANT
    )
    saved = json.loads(saved_bytes)

    final_dir = tmp_path / "final"
    final = evaluate(
        durable_session(store, **chunk_options), model, request, options, final_dir
    )
    assert final["job"]["status"] == "succeeded"
    assert final["row"]["full_reference_verification_pass"] is True
    assert final["new_work"]["api_invocation_count"] == 2
    assert final["original_work_not_recharged"]["api_invocation_count"] == 2
    assert not final["historical_unknown_work"]
    _assert_quantity(final["row"]["quantities"], length)
    result = json.loads(_original(final, final_dir))
    assert result["receipts"][0] == saved["receipts"][0]
    assert (
        result["receipts"][1]["api_request"]["restart_input_sha256"]
        == (saved["receipts"][0]["checkpoint_sha256"])
    )
    assert [
        (r["node_id"], r["dof"])
        for r in result["api_result"]["terminal_response"]["support_reactions"]
    ] == [("N2", "UX"), ("N2", "UY"), ("N6", "UY")]
    fresh_dir = tmp_path / "fresh"
    fresh = _local_session().evaluate(
        model, request, scope_id="research", output_directory=fresh_dir, **options
    )
    _assert_direct_original(fresh, fresh_dir, "pin_roller", request, length)
    fresh_payload = json.loads(_original(fresh, fresh_dir))
    assert result["api_result"]["response_history"] == fresh_payload["response_history"]
    assert (
        result["api_result"]["terminal_response"] == fresh_payload["terminal_response"]
    )

    original_files = {
        role: _original(final, final_dir, role) for role in final["row"]["artifacts"]
    }
    repriced_dir = tmp_path / "repriced"
    repriced = evaluate(
        durable_session(store, **chunk_options),
        model,
        request,
        options,
        repriced_dir,
        allow_new_analysis=False,
        prices=replace(options["prices"], concrete_per_m3=150),
        history_limits=replace(options["history_limits"], maximum_translation_m=1e-12),
    )
    assert repriced["mode"] == "verified_durable_original_reused"
    assert repriced["row"]["full_reference_verification_pass"] is True
    assert repriced["row"]["selection_eligible"] is False
    assert repriced["new_work"]["api_invocation_count"] == 0
    assert all(v == 0 for v in repriced["new_work"]["known_counters"].values())
    assert not repriced["new_work"]["unknown_work"]
    assert repriced["original_work_not_recharged"]["api_invocation_count"] == 4
    assert not repriced["fresh_reference_verification_this_call"]
    assert repriced["row"]["material_estimate"]["total"] - final["row"][
        "material_estimate"
    ]["total"] == pytest.approx(0.4 * 0.6 * length * 50)
    for role, raw in original_files.items():
        assert _original(repriced, repriced_dir, role) == raw
        assert _original(final, final_dir, role) == raw
    assert model.canonical_payload() == original_model


@pytest.mark.parametrize("profile", ["pin_roller", "two_fixed"])
def test_local_cost_search_preserves_support_profile_and_physical_prices(
    tmp_path, profile
):
    model, request, length = _profile(profile)
    report = search.run_rc_control_cost_search(
        model,
        (_candidate(),),
        request,
        session=_local_session(),
        scope_id="research",
        output_directory=tmp_path / "search",
        **_options(),
    )
    assert report["status"] == "pool_minimum_confirmed"
    assert report["cost_bound"]["selected_candidate_id"] == "narrower"
    assert report["new_model_evaluations"] == 2
    assert report["new_work"]["api_invocation_count"] == 4
    estimates = []
    for name, width in (("baseline", 0.4), ("narrower", 0.36)):
        directory = tmp_path / "search" / name
        evaluation = json.loads((directory / "evaluation.json").read_bytes())
        _assert_direct_original(evaluation, directory, profile, request, length, width)
        estimates.append(evaluation["row"]["material_estimate"]["total"])
    assert estimates[0] - estimates[1] == pytest.approx(0.04 * 0.6 * length * 100)


@pytest.mark.parametrize("profile", ["pin_roller", "two_fixed"])
def test_refinement_preserves_support_profile_and_quadrature_quantity_basis(
    tmp_path, profile
):
    model, request, length = _profile(profile)
    directory = tmp_path / "refinement"
    report = refinement.run_rc_refinement(
        model,
        request,
        levels=(2, 3, 4),
        tolerances=_tolerances(),
        session=_local_session(),
        scope_id="research",
        output_directory=directory,
        **_options(),
    )
    assert report["new_model_evaluations"] == 3
    assert not report["unknown_work"]
    assert len(report["adjacent_pairs"]) == 2
    quantities = []
    for count in (2, 3, 4):
        root = directory / f"layers-{count:03d}"
        evaluation = json.loads((root / "evaluation.json").read_bytes())
        _assert_direct_original(evaluation, root, profile, request, length)
        quantities.append(evaluation["row"]["quantities"]["totals"])
    assert quantities[0] == quantities[1] == quantities[2]
    assert report["claims"]["continuum_error_bound_proved"] is False


@pytest.mark.parametrize("profile", ["pin_roller", "two_fixed"])
def test_refined_cost_search_verifies_each_profile_before_finite_pool_selection(
    tmp_path, profile
):
    model, request, length = _profile(profile)
    directory = tmp_path / "search"
    report = refinement.run_refined_candidate_search(
        model,
        (_candidate(),),
        request,
        levels=(2, 3, 4),
        tolerances=_tolerances(),
        session=_local_session(),
        scope_id="research",
        output_directory=directory,
        max_new_model_analyses=6,
        **_options(),
    )
    assert report["new_model_evaluations"] == 6
    assert report["status"] == "pool_minimum_confirmed"
    assert report["cost_bound"]["selected_candidate_id"] == "narrower"
    for name, width in (("baseline", 0.4), ("narrower", 0.36)):
        for count in (2, 3, 4):
            root = directory / name / f"layers-{count:03d}"
            evaluation = json.loads((root / "evaluation.json").read_bytes())
            _assert_direct_original(evaluation, root, profile, request, length, width)


@pytest.mark.parametrize("profile", ["pin_roller", "two_fixed"])
def test_unsupported_durable_loading_profiles_reject_before_job_output(
    tmp_path, profile
):
    model, request, _ = _profile(profile, preload=profile == "pin_roller")
    store = tmp_path / "store"
    session = durable_session(store)
    before = {
        p.relative_to(store): p.read_bytes() for p in store.rglob("*") if p.is_file()
    }
    with pytest.raises(ValueError, match="support/loading profile is unsupported"):
        evaluate(session, model, request, _options(), tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
    after = {
        p.relative_to(store): p.read_bytes() for p in store.rglob("*") if p.is_file()
    }
    assert after == before
    assert list(store.rglob("jobs.sqlite3")) == [store / "jobs.sqlite3"]
