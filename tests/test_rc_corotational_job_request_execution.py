"""Request-to-source integration; invocation authority is not supplied here."""

from dataclasses import asdict
import json
from pathlib import Path

from structural_analysis.api.rc_corotational_control import (
    analyze_rc_corotational_control,
    validate_rc_corotational_control_artifacts,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.execution.rc_corotational_job_request import (
    validate_rc_corotational_job_request,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


def test_serialized_request_executes_pauses_reopens_and_accounts_for_replay(tmp_path):
    model = (
        Path(__file__).parents[1]
        / "examples/public_rc_fiber_frame_l_frame_material_history.json"
    )
    payload = {
        "schema_version": "structural-analysis-job-request.v6",
        "operation": "bounded_rc_corotational_control",
        "case_id": "request-source-integration",
        "model": json.loads(model.read_bytes()),
        "source_revision": "b" * 40,
        "result_contract": "bounded-rc-corotational-job-result.v1",
        "config": {
            "control_node_id": "N3",
            "control_component": "UY",
            "targets_m": [-1e-6, -2e-6, -1.5e-6],
            "fixed_nodal_loads": [["N3", "FX", -0.01]],
            "config": asdict(
                StatefulCorotationalFiberFrame2DDisplacementControlConfig()
            ),
            "preload_config": asdict(NewtonRaphsonConfig()),
            "maximum_attempt_count": 255,
            "maximum_subdivision_depth": 8,
            "experimental_pin_roller_beam": False,
            "experimental_fixed_guided_axial": False,
        },
        "execution_config": {"attempt_limit_per_call": 1, "maximum_api_invocations": 6},
    }
    original = validate_rc_corotational_job_request(json.dumps(payload).encode())
    saved = tmp_path / "request.json"
    saved.write_bytes(original.request_bytes)
    restart = None
    totals = dict(
        preload_solver_calls=0, restart_replay_solver_calls=0, control_solver_calls=0
    )
    for completed in (1, 2, 3):
        reopened = validate_rc_corotational_job_request(saved.read_bytes())
        assert reopened.request_hash == original.request_hash
        artifacts = analyze_rc_corotational_control(
            reopened.model, reopened.targets_m, restart=restart, **reopened.api_kwargs()
        )
        result = json.loads(artifacts.result_bytes)
        verified = validate_rc_corotational_control_artifacts(
            reopened.model,
            reopened.targets_m,
            result=artifacts.result_bytes,
            continuation=artifacts.continuation_bytes,
            restart=restart,
            **reopened.api_kwargs(),
        )
        assert verified["artifact_contract_pass"]
        assert result["total_control_attempts"] == completed
        assert verified["contract_pass"] == (completed == 3)
        for work in (result["work"], verified["replay_work"]):
            for key in totals:
                totals[key] += work[key]
            assert not work["unavailable_execution_work"]
        restart = artifacts.continuation_bytes
    assert totals == dict(
        preload_solver_calls=6, restart_replay_solver_calls=6, control_solver_calls=6
    )
    assert sum(totals.values()) == 18
