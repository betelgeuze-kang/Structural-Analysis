"""Merge-specific guards; fault injection does not constitute physical validation."""

from __future__ import annotations

import json

import pytest

from tests import test_rc_control_local_research as shared
from tests import test_rc_control_durable_research as chunks
from structural_analysis.benchmark import rc_control_cost_search as search
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import rc_control_refinement as refinement
from structural_analysis.benchmark.rc_control_reuse import (
    NewAnalysisRequired,
    RCControlResultSession,
)

model = shared.model
control_request = shared.control_request
options = shared.options


def evaluate(session, model, control_request, options, path, **kwargs):
    return session.evaluate(
        model,
        control_request,
        scope_id="research",
        output_directory=path,
        **options,
        **kwargs,
    )


@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_assembly_reuse_setting_requires_boolean(value):
    with pytest.raises(ValueError, match="boolean"):
        RCControlResultSession(
            source_revision=shared.SOURCE,
            scope_id="research",
            reuse_line_search_assembly=value,
        )


def test_reuse_option_reaches_current_reference_and_remains_bound(
    model,
    control_request,
    options,
    tmp_path,
    monkeypatch,
):
    observed = []
    original = study._reference_design_row

    def record(*args, **kwargs):
        observed.append(dict(args[4]))
        return original(*args, **kwargs)

    monkeypatch.setattr(study, "_reference_design_row", record)
    session = RCControlResultSession(
        source_revision=shared.SOURCE,
        scope_id="research",
        reuse_line_search_assembly=True,
    )
    first = evaluate(session, model, control_request, options, tmp_path / "first")
    assert observed and all(x["reuse_line_search_assembly"] is True for x in observed)
    assert first["row"]["full_reference_verification_pass"] is True
    assert first["execution_options"] == {"reuse_line_search_assembly": True}
    exposed = session.execution_options
    exposed["reuse_line_search_assembly"] = False
    assert session.execution_options["reuse_line_search_assembly"] is True
    second = evaluate(
        session,
        model,
        control_request,
        options,
        tmp_path / "second",
        allow_new_analysis=False,
    )
    assert second["new_work"]["api_invocation_count"] == 0
    assert second["execution_options"] == first["execution_options"]
    assert second["row"]["performance"] == first["row"]["performance"]
    off = RCControlResultSession(source_revision=shared.SOURCE, scope_id="research")
    assert session._key(model, control_request) != off._key(model, control_request)


def test_assembly_reuse_and_reference_preserve_simple_response(
    model,
    control_request,
    options,
    tmp_path,
):
    results = []
    for enabled in (False, True):
        session = RCControlResultSession(
            source_revision=shared.SOURCE,
            scope_id="research",
            reuse_line_search_assembly=enabled,
        )
        root = tmp_path / str(enabled)
        report = evaluate(session, model, control_request, options, root)
        assert report["row"]["full_reference_verification_pass"] is True
        results.append(
            json.loads(
                (root / report["row"]["artifacts"]["result"]["path"]).read_bytes()
            )
        )
    assert results[0]["response_history"] == results[1]["response_history"]
    assert results[0]["preload_response"] == results[1]["preload_response"]


def test_persistent_result_cannot_cross_assembly_strategy(
    model,
    control_request,
    options,
    tmp_path,
):
    from structural_analysis.execution.rc_result_repository import (
        open_local_rc_repository,
    )

    repository = open_local_rc_repository(
        tmp_path / "store",
        tenant_id="research",
        scope_id="research",
        authorization_token="merge-test-only-auth-token",
    )
    off = RCControlResultSession(
        source_revision=shared.SOURCE, scope_id="research", repository=repository
    )
    evaluate(off, model, control_request, options, tmp_path / "off")
    on = RCControlResultSession(
        source_revision=shared.SOURCE,
        scope_id="research",
        repository=repository,
        reuse_line_search_assembly=True,
    )
    with pytest.raises(NewAnalysisRequired):
        evaluate(
            on,
            model,
            control_request,
            options,
            tmp_path / "on",
            allow_new_analysis=False,
        )
    assert not (tmp_path / "on").exists()


def test_chunk_store_uses_integrated_no_replace_owner(tmp_path):
    chunks.session(tmp_path / "store")
    owner = tmp_path / "store/rc-local-owner.json"
    before = owner.read_bytes()
    with pytest.raises(ValueError, match="authorization"):
        chunks.DurableRCControlResultSession(
            store_root=tmp_path / "store",
            source_revision=chunks.SOURCE,
            scope_id="lab",
            authorization_token=chunks.TENANT + "changed",
            worker_token=chunks.WORKER,
        )
    assert owner.read_bytes() == before


def test_legacy_chunk_store_is_not_silently_claimed(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    sentinel = root / "unattributed-old-job"
    sentinel.mkdir()
    with pytest.raises(ValueError, match="explicit owner migration"):
        chunks.session(root)
    assert sentinel.is_dir()
    assert not (root / "rc-local-owner.json").exists()


def test_chunk_pause_counts_new_work_and_is_not_a_cache_hit(
    model,
    control_request,
    options,
    tmp_path,
):
    session = chunks.session(
        tmp_path / "store", chunk_target_count=2, max_chunks_per_call=1
    )
    report = search.run_rc_control_cost_search(
        model,
        (shared.candidate("cheap", 0.35),),
        control_request,
        session=session,
        scope_id="lab",
        output_directory=tmp_path / "paused",
        max_new_model_analyses=1,
        **options,
    )
    assert report["new_model_evaluations"] == 1
    assert report["reused_model_evaluations"] == 0
    assert all(v is None for v in report["outcomes"].values())
    assert report["cost_bound"]["pool_minimum_feasible_estimate"] is None
    assert report["new_work"]["known_counters"]["attempted_step_count"] == 6


def test_chunk_adapter_keeps_cooperative_cancellation(
    model,
    control_request,
    options,
    tmp_path,
):
    report = search.run_rc_control_cost_search(
        model,
        (shared.candidate("cheap", 0.35),),
        control_request,
        session=chunks.session(tmp_path / "store"),
        scope_id="lab",
        output_directory=tmp_path / "cancelled",
        stop_requested=lambda: True,
        **options,
    )
    assert report["status"] == "cancelled_between_models"
    assert report["new_model_evaluations"] == report["reused_model_evaluations"] == 0
    assert all(v is None for v in report["outcomes"].values())


def test_historical_unknown_cannot_supply_a_cost_incumbent(
    model,
    control_request,
    options,
    tmp_path,
    monkeypatch,
):
    # Explicit fault injection after a real successful evaluation.
    original = chunks.DurableRCControlResultSession.evaluate

    def unknown(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        assert result["row"]["full_reference_verification_pass"] is True
        result["historical_unknown_work"] = True
        return result

    monkeypatch.setattr(chunks.DurableRCControlResultSession, "evaluate", unknown)
    result = search.run_rc_control_cost_search(
        model,
        (shared.candidate("expensive", 0.5),),
        control_request,
        session=chunks.session(tmp_path / "store"),
        scope_id="lab",
        output_directory=tmp_path / "unknown",
        **options,
    )
    assert result["status"] == "unknown_work_stop"
    assert result["cost_bound"]["pool_minimum_feasible_estimate"] is None
    assert all(value is None for value in result["outcomes"].values())


def test_chunk_results_do_not_enter_refinement_cache_implicitly(
    model,
    control_request,
    options,
    tmp_path,
):
    with pytest.raises(ValueError):
        refinement.run_rc_refinement(
            model,
            control_request,
            session=chunks.session(tmp_path / "store"),
            scope_id="lab",
            levels=(2, 4, 8),
            tolerances=(refinement.RCResponseTolerance("node_translation", 1e-8, 0.1),),
            output_directory=tmp_path / "wrong-profile",
            **options,
        )
    assert not (tmp_path / "wrong-profile").exists()
