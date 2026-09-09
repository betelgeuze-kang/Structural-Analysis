"""Actual constant-load public transport, source replay and failure accounting."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api import rc_fiber_frame_direct_control_cli as cli
from structural_analysis.api import rc_fiber_frame_direct_control_request as transport
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

MODEL = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_cantilever.json"
)
TARGETS = (-1e-5, -2e-5, 1e-5)
OPTIONS = dict(
    control_global_dof=4,
    constant_nodal_loads=(("N2", -600.0, 0.0, 0.0),),
    allow_reversals=True,
    maximum_reversals=2,
    maximum_targets=6,
)


def _forbid(*args, **kwargs):
    pytest.fail("unexpected control/preload invocation")


@pytest.fixture(scope="module")
def model():
    return load_neutral_json(MODEL)


@pytest.fixture(scope="module")
def actual(model):
    full = api.analyze_bounded_rc_fiber_direct_control(model, TARGETS, **OPTIONS)
    prefix = api.analyze_bounded_rc_fiber_direct_control(model, TARGETS[:1], **OPTIONS)
    resumed = api.analyze_bounded_rc_fiber_direct_control(
        model, TARGETS[1:], restart=prefix.checkpoint_artifact_bytes(), **OPTIONS
    )
    assert full.contract_pass and prefix.contract_pass and resumed.contract_pass
    return full, prefix, resumed


def test_public_actual_preload_reversal_recovery_and_replay(model, actual):
    full, prefix, resumed = actual
    payload, continued = full.to_dict(), resumed.to_dict()
    assert (
        payload["schema_version"] == api.CONSTANT_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION
    )
    assert payload["preload_response"]["epoch"] == 1
    assert [row["epoch"] for row in payload["response_history"]] == [2, 3, 4]
    assert payload["preload_response"] == continued["preload_response"]
    assert payload["response_history"] == continued["response_history"]
    assert full.checkpoint_artifact_bytes() == resumed.checkpoint_artifact_bytes()
    assert payload["metrics"]["control_work"]["attempted_step_count"] == 4
    assert continued["path"]["metrics"]["preload_work"]["attempted_step_count"] == 1
    assert (
        continued["path"]["metrics"]["prefix_replay_work"]["attempted_step_count"] == 1
    )
    assert continued["path"]["metrics"]["suffix_work"]["attempted_step_count"] == 2
    for item in (payload, continued):
        assert item["metrics"]["control_work"]["unknown_solver_work_attempt_count"] == 0
        assert item["metrics"]["response_reassembly_verified_count"] == 4
        for row in (item["preload_response"], *item["response_history"]):
            assert row["support_reactions"][0]["value_si"] == pytest.approx(
                600000.0, abs=1e-7
            )
    report = api.validate_bounded_rc_fiber_direct_control_artifacts(
        model,
        TARGETS[1:],
        result=resumed.result_artifact_bytes(),
        checkpoint=resumed.checkpoint_artifact_bytes(),
        restart=prefix.checkpoint_artifact_bytes(),
        **OPTIONS,
    ).to_dict()
    assert report["contract_pass"]
    assert report["replay_control_work"]["attempted_step_count"] == 4
    assert not report["claims"]["independent_physical_validation"]


def test_empty_suffix_replays_preload_and_prefix(model, actual):
    full = actual[0]
    verified = api.analyze_bounded_rc_fiber_direct_control(
        model, (), restart=full.checkpoint_artifact_bytes(), **OPTIONS
    )
    assert verified.contract_pass
    assert verified.checkpoint_artifact_bytes() == full.checkpoint_artifact_bytes()
    assert verified.to_dict()["metrics"]["control_work"]["attempted_step_count"] == 4


def test_constant_pattern_change_rejects_restart_before_any_solve(
    model, actual, monkeypatch
):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_constant_load_preload", _forbid
    )
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    with pytest.raises(ValueError, match="source/configuration"):
        api.analyze_bounded_rc_fiber_direct_control(
            model,
            TARGETS[1:],
            restart=actual[1].checkpoint_artifact_bytes(),
            **(OPTIONS | {"constant_nodal_loads": (("N2", -601.0, 0.0, 0.0),)}),
        )


def test_forged_preload_hash_requires_fresh_preload_and_accounts_for_it(
    model, actual, monkeypatch
):
    raw = json.loads(actual[1].checkpoint_artifact_bytes())
    raw["preload_step_hash"] = "sha256:" + "0" * 64
    raw.pop("artifact_hash")
    raw["artifact_hash"] = paths._hash(paths._json(raw))
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    result = api.analyze_bounded_rc_fiber_direct_control(
        model, TARGETS[1:], restart=paths._json(raw), **OPTIONS
    ).to_dict()
    assert result["status"] == "invalid_execution"
    assert result["metrics"]["control_work"]["attempted_step_count"] == 1
    assert result["metrics"]["control_work"]["unknown_solver_work_attempt_count"] == 0
    assert result["checkpoint"] is None


def test_failed_preload_stops_before_control_and_retains_work(model, monkeypatch):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_displacement_control_step", _forbid
    )
    result = api.analyze_bounded_rc_fiber_direct_control(
        model,
        TARGETS,
        **(OPTIONS | {"constant_nodal_loads": (("N2", -30000.0, 0.0, 0.0),)}),
        config=paths.StatefulFiberFrame2DDisplacementControlConfig(
            newton=NewtonRaphsonConfig(max_iterations=1)
        ),
    ).to_dict()
    assert not result["contract_pass"] and result["checkpoint"] is None
    assert result["metrics"]["control_work"]["attempted_step_count"] == 1
    # The blocked Newton return omits iteration/linear counters; do not invent them.
    assert result["metrics"]["control_work"]["unknown_solver_work_attempt_count"] == 1
    step = result["failure"]["attempts"][0]["step"]
    assert not step["committed"]
    assert step["accepted_checkpoint"] == step["parent_checkpoint"]


def test_constant_support_load_in_si_reaction(model):
    r = api.analyze_bounded_rc_fiber_direct_control(
        model,
        TARGETS[:1],
        **(
            OPTIONS
            | {
                "constant_nodal_loads": (
                    ("N1", -7.0, 0.0, 0.0),
                    ("N2", -600.0, 0.0, 0.0),
                )
            }
        ),
    ).to_dict()
    assert r["contract_pass"]
    assert r["preload_response"]["support_reactions"][0]["value_si"] == pytest.approx(
        607000.0
    )


def test_request_v2_roundtrip_and_resume_identity():
    request = transport.BoundedRCFiberDirectControlRequest(targets_m=TARGETS, **OPTIONS)
    raw = transport.bounded_rc_fiber_direct_control_request_payload(request)
    assert raw["schema_version"] == transport.CONSTANT_REQUEST_SCHEMA_VERSION
    assert transport.decode_bounded_rc_fiber_direct_control_request(raw) == request
    assert (
        replace(request, targets_m=TARGETS[:1]).resume_contract_hash
        == request.resume_contract_hash
    )
    assert (
        replace(
            request, constant_nodal_loads=(("N2", -601.0, 0.0, 0.0),)
        ).resume_contract_hash
        != request.resume_contract_hash
    )
    old = deepcopy(raw)
    old["schema_version"] = transport.REQUEST_SCHEMA_VERSION
    with pytest.raises(ValueError, match="unknown"):
        transport.decode_bounded_rc_fiber_direct_control_request(old)


@pytest.mark.parametrize(
    "rows",
    [
        None,
        [],
        [{"node_id": "N2", "FX_kN": -600.0, "FY_kN": 0.0}],
        [{"node_id": "N2", "FX_kN": True, "FY_kN": 0.0, "MZ_kNm": 0.0}],
        [{"node_id": "N2", "FX_kN": 0.0, "FY_kN": 0.0, "MZ_kNm": 0.0}],
        [{"node_id": "N2", "FX_kN": -600.0, "FY_kN": 0.0, "MZ_kNm": 0.0}] * 2,
    ],
)
def test_invalid_constant_request_rows_reject(rows):
    raw = transport.BoundedRCFiberDirectControlRequest(
        targets_m=TARGETS, **OPTIONS
    ).to_dict()
    raw["constant_nodal_loads"] = rows
    with pytest.raises(ValueError):
        transport.decode_bounded_rc_fiber_direct_control_request(raw)


def test_undeclared_node_rejected_before_preload(model, monkeypatch):
    monkeypatch.setattr(
        paths, "solve_stateful_fiber_frame2d_constant_load_preload", _forbid
    )
    with pytest.raises(ValueError, match="undeclared"):
        api.analyze_bounded_rc_fiber_direct_control(
            model,
            TARGETS,
            **(OPTIONS | {"constant_nodal_loads": (("missing", -600.0, 0.0, 0.0),)}),
        )


def test_cli_v2_runs_and_explicitly_verifies(tmp_path):
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            transport.BoundedRCFiberDirectControlRequest(
                targets_m=TARGETS[:1], **OPTIONS
            ).to_dict()
        )
    )
    result, checkpoint, report = (
        tmp_path / name for name in ("result.json", "checkpoint.json", "report.json")
    )
    assert (
        cli.main(
            [
                "run",
                "--model",
                str(MODEL),
                "--request",
                str(request),
                "--output",
                str(result),
                "--checkpoint-output",
                str(checkpoint),
                "--report",
                str(report),
            ]
        )
        == 0
    )
    assert (
        cli.main(
            [
                "verify",
                "--model",
                str(MODEL),
                "--request",
                str(request),
                "--result",
                str(result),
                "--checkpoint",
                str(checkpoint),
                "--report",
                str(tmp_path / "verification.json"),
            ]
        )
        == 0
    )
    assert (
        json.loads(result.read_bytes())["metrics"]["control_work"][
            "attempted_step_count"
        ]
        == 2
    )
