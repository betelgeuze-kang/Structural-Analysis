"""Authored mixed-layer transport, persistence and quantities, not source calibration."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control import (
    analyze_bounded_rc_fiber_direct_control,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution.rc_fiber_quantities import (
    calculate_fiber_frame_member_quantities,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes

ROOT = Path(__file__).parents[1]


def authored():
    return json.loads(
        (ROOT / "examples/public_rc_fiber_frame_explicit_layers.json").read_text()
    )


def model(data=None):
    return load_neutral_json_bytes(
        json.dumps(authored() if data is None else data).encode()
    )


def test_compiler_preserves_layer_geometry_laws_and_total_steel_quantity():
    compiled, blockers, _ = _compile(model())
    assert not blockers
    section = compiled.problem.members[0].element.section
    steel = [f for f in section.fibers if f.material_kind == "steel"]
    assert [f.y_m for f in steel] == [-0.25, -0.15, 0.24]
    assert [f.area_m2 for f in steel] == pytest.approx([0.0006, 0.0004, 0.0002])
    assert [section.steel_material_for(f.fiber_id).yield_stress_mpa for f in steel] == [
        250,
        250,
        404,
    ]
    q = calculate_fiber_frame_member_quantities(model())
    assert q["totals"]["longitudinal_rebar_volume_m3"] == pytest.approx(0.0012 * 3)
    assert q["totals"]["longitudinal_rebar_mass_kg"] == pytest.approx(0.0012 * 3 * 7850)
    assert q["totals"]["gross_concrete_volume_m3"] == pytest.approx(0.4 * 0.6 * 3)


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "duplicate_id",
        "duplicate_y",
        "outside",
        "bool_count",
        "unknown_material",
        "concrete_as_steel",
        "unknown_field",
        "too_many",
        "zero_area",
        "overflow",
        "gross_overflow",
        "legacy_mix",
    ],
)
def test_invalid_explicit_layers_fail_before_numerical_work(kind):
    data = authored()
    section = data["sections"][0]
    layers = section["steel_layers"]
    if kind == "empty":
        section["steel_layers"] = []
    elif kind == "duplicate_id":
        layers[1]["id"] = layers[0]["id"]
    elif kind == "duplicate_y":
        layers[1]["y_m"] = layers[0]["y_m"]
    elif kind == "outside":
        layers[2]["y_m"] = 0.3
    elif kind == "bool_count":
        layers[0]["bar_count"] = True
    elif kind == "unknown_material":
        layers[0]["steel_material"] = "missing"
    elif kind == "concrete_as_steel":
        layers[0]["steel_material"] = "concrete"
    elif kind == "unknown_field":
        layers[0]["silent_default"] = 1
    elif kind == "too_many":
        section["steel_layers"] = layers * 11
    elif kind == "zero_area":
        layers[0]["bar_area_m2"] = 0
    elif kind == "overflow":
        layers[0]["bar_area_m2"] = 1e308
    elif kind == "gross_overflow":
        section.update(width_m=1e308, depth_m=10)
    else:
        section["top_bar_count"] = 3
    compiled, blockers, _ = _compile(model(data))
    assert compiled is None and blockers


def test_layer_model_restart_is_exact_and_changed_layer_is_rejected():
    source = model()
    config = BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6))
    whole = analyze_bounded_rc_fiber_direct_control(
        source, config.targets_m, **config.api_kwargs()
    )
    prefix = analyze_bounded_rc_fiber_direct_control(
        source, (-1e-6,), **config.api_kwargs()
    )
    resumed = analyze_bounded_rc_fiber_direct_control(
        source,
        (-2e-6,),
        restart=prefix.checkpoint_artifact_bytes(),
        **config.api_kwargs(),
    )
    assert whole.to_dict()["contract_pass"] and resumed.to_dict()["contract_pass"]
    assert whole.checkpoint_artifact_bytes() == resumed.checkpoint_artifact_bytes()
    changed = authored()
    changed["sections"][0]["steel_layers"][1]["bar_area_m2"] *= 1.01
    with pytest.raises(
        ValueError, match="restart source/configuration/control/budget mismatch"
    ):
        analyze_bounded_rc_fiber_direct_control(
            model(changed),
            (-2e-6,),
            restart=prefix.checkpoint_artifact_bytes(),
            **config.api_kwargs(),
        )


def test_mixed_layers_survive_durable_restart_and_quantity_report(tmp_path):
    from structural_analysis.execution.job_service import DurableJobService
    from structural_analysis.execution.rc_fiber_direct_control_worker import (
        execute_rc_fiber_direct_control_claim,
    )

    tenant = {
        "tenant_id": "a",
        "authorization_token": "synthetic-explicit-layer-tenant-token",
    }
    worker = {
        "worker_id": "w",
        "authorization_token": "synthetic-explicit-layer-worker-token",
    }

    def service():
        return DurableJobService(
            tmp_path / "store",
            tenant_tokens={"a": tenant["authorization_token"]},
            worker_tokens={"w": worker["authorization_token"]},
        )

    request = {
        "schema_version": "structural-analysis-job-request.v3",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "authored-explicit-layers",
        "model": authored(),
        "config": BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6)).to_dict(),
        "source_revision": "a" * 40,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {"chunk_target_count": 1, "maximum_api_invocations": 8},
    }
    current = service()
    job = current.submit_job(
        **tenant, idempotency_key="layers", request=deepcopy(request)
    )
    first = execute_rc_fiber_direct_control_claim(
        current, current.claim_next(**worker), **worker
    )
    assert first.status == "checkpointed"
    current = service()
    final = execute_rc_fiber_direct_control_claim(
        current, current.claim_next(**worker), **worker
    )
    assert final.status == "succeeded"
    report = current.create_rc_quantity_report(
        job.job_id,
        **tenant,
        expected_request_hash=final.request.content_hash,
        expected_result_artifact_hash=final.result.content_hash,
        declared_prices=None,
    )
    raw = service().read_rc_quantity_report(job.job_id, report["report_id"], **tenant)
    assert json.loads(raw)["quantities"]["totals"][
        "longitudinal_rebar_mass_kg"
    ] == pytest.approx(28.26)
    assert (
        json.loads(current.read_request(job.job_id, **tenant))["model"]
        == request["model"]
    )
    assert current.validate_integrity(job.job_id, **tenant)["contract_pass"]
