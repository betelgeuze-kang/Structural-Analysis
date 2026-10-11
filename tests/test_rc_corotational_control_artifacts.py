"""Fresh source checks for experimental corotational artifacts, not physical proof."""

import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_corotational_control import (
    RCCorotationalControlExecutionError,
    analyze_rc_corotational_control,
    validate_rc_corotational_control_artifacts,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

MODEL = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_l_frame_material_history.json"
)
TARGETS = (-1e-6, -2e-6, -1.5e-6)
OPTIONS = dict(
    control_node_id="N3",
    control_component="UY",
    fixed_nodal_loads=(("N3", "FX", -0.01),),
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def test_full_artifact_verification_and_coherent_response_tampering():
    model = load_neutral_json(MODEL)
    artifacts = analyze_rc_corotational_control(model, TARGETS, **OPTIONS)
    payload = json.loads(artifacts.result_bytes)
    assert payload["contract_pass"]
    assert payload["work"] == dict(
        preload_solver_calls=1,
        restart_replay_solver_calls=0,
        control_solver_calls=3,
        unavailable_execution_work=False,
    )
    assert len(payload["responses"]) == 4
    assert all(
        row["nodes"][2]["external_loads_kn_knm"][0] == -0.01
        for row in payload["responses"]
    )
    report = validate_rc_corotational_control_artifacts(
        model,
        TARGETS,
        result=artifacts.result_bytes,
        continuation=artifacts.continuation_bytes,
        **OPTIONS,
    )
    assert report["contract_pass"]
    assert report["replay_work"] == payload["work"]
    assert report["independent_physical_validation"] is False
    payload["responses"][-1]["nodes"][2]["displacements_m_rad"][1] += 1e-5
    rejected = validate_rc_corotational_control_artifacts(
        model,
        TARGETS,
        result=canonical(payload),
        continuation=artifacts.continuation_bytes,
        **OPTIONS,
    )
    assert not rejected["artifact_contract_pass"]
    assert rejected["fresh_source_execution_invoked"]
    assert rejected["replay_work"]["control_solver_calls"] == 3


def test_restart_replays_prefix_and_counts_work_before_advancing(tmp_path):
    model = load_neutral_json(MODEL)
    pause = analyze_rc_corotational_control(
        model, TARGETS, attempt_limit_per_call=1, **OPTIONS
    )
    report = validate_rc_corotational_control_artifacts(
        model,
        TARGETS,
        result=pause.result_bytes,
        continuation=pause.continuation_bytes,
        attempt_limit_per_call=1,
        **OPTIONS,
    )
    assert report["artifact_contract_pass"]
    assert not report["physical_path_complete"]
    checkpoint = tmp_path / "restart.json"
    checkpoint.write_bytes(pause.continuation_bytes)
    resumed = analyze_rc_corotational_control(
        load_neutral_json(MODEL), TARGETS, restart=checkpoint.read_bytes(), **OPTIONS
    )
    payload = json.loads(resumed.result_bytes)
    assert payload["contract_pass"]
    assert payload["work"] == dict(
        preload_solver_calls=1,
        restart_replay_solver_calls=1,
        control_solver_calls=2,
        unavailable_execution_work=False,
    )
    full = analyze_rc_corotational_control(model, TARGETS, **OPTIONS)
    assert resumed.continuation_bytes == full.continuation_bytes
    assert payload["responses"] == json.loads(full.result_bytes)["responses"]
    verified = validate_rc_corotational_control_artifacts(
        model,
        TARGETS,
        result=resumed.result_bytes,
        continuation=resumed.continuation_bytes,
        restart=pause.continuation_bytes,
        **OPTIONS,
    )
    assert verified["contract_pass"]
    assert verified["replay_work"] == payload["work"]


def test_rehashed_budget_rewind_fails_fresh_prefix_replay():
    model = load_neutral_json(MODEL)
    pause = analyze_rc_corotational_control(
        model, TARGETS, attempt_limit_per_call=2, **OPTIONS
    )
    record = json.loads(pause.continuation_bytes)
    record["payload"]["spent"] = 1
    record["sha256"] = hashlib.sha256(canonical(record["payload"])).hexdigest()
    with pytest.raises(RCCorotationalControlExecutionError) as error:
        analyze_rc_corotational_control(
            model, TARGETS, restart=canonical(record), **OPTIONS
        )
    assert "fresh complete-prefix replay" in str(error.value.__cause__)
    assert error.value.work["preload_solver_calls"] == 1
    assert error.value.work["restart_replay_solver_calls"] == 1
    assert error.value.work["control_solver_calls"] == 0
    assert error.value.work["unavailable_execution_work"]


def test_failed_preload_is_valid_blocked_evidence_without_success_claim():
    model = load_neutral_json(MODEL)
    options = dict(OPTIONS, preload_config=NewtonRaphsonConfig(max_iterations=0))
    result = analyze_rc_corotational_control(model, TARGETS, **options)
    payload = json.loads(result.result_bytes)
    assert payload["status"] == "blocked"
    assert payload["terminal_reason"] == "preload_failed"
    assert not payload["contract_pass"]
    assert result.continuation_bytes is None
    assert payload["work"]["preload_solver_calls"] == 1
    report = validate_rc_corotational_control_artifacts(
        model, TARGETS, result=result.result_bytes, continuation=None, **options
    )
    assert report["artifact_contract_pass"]
    assert not report["contract_pass"]


def test_invalid_request_rejected_before_preload(monkeypatch):
    import structural_analysis.api.rc_corotational_control as api

    def forbidden(*args, **kwargs):
        pytest.fail("invalid input invoked a solver")

    monkeypatch.setattr(
        api, "solve_stateful_corotational_fiber_frame2d_load_step", forbidden
    )
    for change in (
        {"maximum_attempt_count": True},
        {"control_component": "RZ"},
        {"config": False},
        {"preload_config": NewtonRaphsonConfig(max_iterations=201)},
    ):
        with pytest.raises(ValueError):
            api.analyze_rc_corotational_control(
                load_neutral_json(MODEL), TARGETS, **dict(OPTIONS, **change)
            )
    with pytest.raises(ValueError):
        api.analyze_rc_corotational_control(
            load_neutral_json(MODEL), (-1e-6, -1e-6), **OPTIONS
        )


def test_nonlinear_artifact_replay_preserves_damage_and_plasticity():
    from structural_analysis.io.neutral.loader import load_neutral_json_bytes

    payload = json.loads(MODEL.read_text())
    payload["nodes"] = payload["nodes"][:2]
    payload["nodes"][1]["coordinates"] = [0.0, 1.0, 0.0]
    payload["elements"] = payload["elements"][:1]
    payload["materials"][0].update(
        yield_stress_mpa=400.0,
        isotropic_hardening_modulus_mpa=1000.0,
        kinematic_hardening_modulus_mpa=1000.0,
    )
    payload["materials"][1].update(
        tensile_softening_rate=20.0, compressive_softening_rate=20.0
    )
    payload["sections"][0].update(
        width_m=0.2,
        depth_m=0.2,
        cover_m=0.03,
        concrete_layer_count=8,
        top_bar_count=2,
        bottom_bar_count=2,
        bar_area_m2=0.0002,
    )
    payload["loads"][0]["node"] = "N2"
    payload["loads"][0]["components"].update(FX=1.0, FY=0.0)
    model = load_neutral_json_bytes(canonical(payload))
    targets = (0.005, 0.01, -0.005, -0.01, 0.005)
    options = dict(
        control_node_id="N2",
        control_component="UX",
        fixed_nodal_loads=(("N2", "FY", -10.0),),
    )
    result = analyze_rc_corotational_control(model, targets, **options)
    observed = json.loads(result.result_bytes)
    assert observed["contract_pass"]
    damage = {"tensile_damage": 0.0, "compressive_damage": 0.0, "plastic_strain": 0.0}

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in damage:
                    damage[key] = max(damage[key], abs(item))
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(json.loads(result.continuation_bytes))
    assert all(value > 0.0 for value in damage.values())
    verified = validate_rc_corotational_control_artifacts(
        model,
        targets,
        result=result.result_bytes,
        continuation=result.continuation_bytes,
        **options,
    )
    assert verified["contract_pass"]
    assert verified["replay_work"] == observed["work"]
    assert observed["work"]["control_solver_calls"] > len(targets)
