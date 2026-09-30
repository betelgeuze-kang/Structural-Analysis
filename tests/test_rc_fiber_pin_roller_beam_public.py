"""Synthetic pin/roller beam boundary, not a measured 4TU or Alberta fit."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.ai.fiber_frame_physical_identity import (
    fiber_frame_physical_model_identity,
    fiber_frame_physical_model_payload,
)
from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.api import rc_fiber_frame_direct_control_cli as cli
from structural_analysis.api.rc_fiber_frame_direct_control import (
    analyze_bounded_rc_fiber_direct_control,
    validate_bounded_rc_fiber_direct_control_artifacts,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    PIN_ROLLER_BEAM_REQUEST_SCHEMA_VERSION,
)
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as control_path
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


BASE = Path(__file__).resolve().parents[1] / "examples/public_rc_fiber_frame_cantilever.json"
STATIONS_M = (0.0, 0.2, 0.7, 0.95, 1.2, 1.7, 1.9)


def _payload():
    """A 4TU-like *geometry* using the repository's unrelated synthetic RC section."""
    data = json.loads(BASE.read_bytes())
    data["nodes"] = [
        {"id": f"N{index + 1}", "coordinates": [x, 0.0, 0.0]}
        for index, x in enumerate(STATIONS_M)
    ]
    data["elements"] = [
        {
            "id": f"M{index + 1}",
            "type": "stateful_rc_fiber_frame2d",
            "nodes": [f"N{index + 1}", f"N{index + 2}"],
            "section": "RC1",
            "integration_order": 2,
        }
        for index in range(len(STATIONS_M) - 1)
    ]
    data["supports"] = [
        {"node": "N2", "dofs": ["UX", "UY"]},
        {"node": "N6", "dofs": ["UY"]},
    ]
    data["loads"] = [
        {
            "node": node,
            "components": {
                "FX": 0.0,
                "FY": -1.0,
                "FZ": 0.0,
                "MX": 0.0,
                "MY": 0.0,
                "MZ": 0.0,
            },
        }
        for node in ("N3", "N5")
    ]
    return data


def _model(payload=None):
    return load_neutral_json_bytes(
        json.dumps(_payload() if payload is None else payload, allow_nan=False).encode()
    )


def _request(targets=(-1e-6,)):
    return BoundedRCFiberDirectControlRequest(
        control_global_dof=10,
        targets_m=tuple(targets),
        experimental_pin_roller_beam=True,
    )


def test_legacy_v1_v3_problem_identity_hashes_and_reaction_rows_remain_exact():
    sources = (
        (
            BASE,
            {},
            (0, 1, 2),
            "sha256:25bb7d79cb6355d604d50640c3665d137a45c263582217bc24465ffce5f24ae8",
            "sha256:0be40a21cd24a62319dfff406e4722b71ca12f15ef555fe5d0ac5bc6a1efdc0d",
            [("N1", "UX"), ("N1", "UY"), ("N1", "RZ")],
        ),
        (
            Path(__file__).resolve().parents[1]
            / "examples/research/rc_internal_portal_20mm/original-model.json",
            {"experimental_two_fixed_endpoints": True},
            (0, 1, 2, 3, 4, 5),
            "sha256:79a077684e27c4468e8941a33189e5daac38f4eb3a5dc90ecc6487e5ca65d45d",
            "sha256:841696507774a66d92701f2bf2cb5c3b76f9d2b9599f964c6e45ce1788c921a5",
            [
                (node, dof)
                for node in ("N1", "N2")
                for dof in ("UX", "UY", "RZ")
            ],
        ),
    )
    for path, profile, fixed, problem_hash, identity_hash, reaction_ids in sources:
        model = load_neutral_json_bytes(path.read_bytes())
        compiled, blockers, _ = public._compile(model, **profile)
        assert compiled is not None and not blockers
        assert compiled.problem.fixed_global_dofs == fixed
        assert compiled.problem.contract_hash == problem_hash
        assert fiber_frame_physical_model_identity(model, **profile) == identity_hash
        rows = public._reaction_rows(
            compiled,
            list(range(1, 6 * len(compiled.node_ids) + 1)),
        )
        assert [(row["node_id"], row["dof"]) for row in rows] == reaction_ids
        assert [row["value_si"] for row in rows] == (
            [1.0, 2.0, 6.0]
            if len(reaction_ids) == 3
            else [1.0, 2.0, 6.0, 7.0, 8.0, 12.0]
        )
    for profile, request_hash, resume_hash in (
        (
            {},
             "sha256:b35c8acebb4e4a4aec77e50a996c21457299f8e07228e6495b22919a31cf3a56",
             "sha256:477939f60a5dc50b612dce4407248f38a66090b6401bf609eeea2aaafe5ac1ae"),
        (
            {"experimental_two_fixed_endpoints": True},
             "sha256:24614ea8bd32628c5dbfc98a98a51c9b61e35978604328b26c71d388911009f0",
             "sha256:1e5c806c54a22047563d454771273e5a51f2f0d43bd7d339bd014d5e67373a0a"),
    ):
        request = BoundedRCFiberDirectControlRequest(4, (-1e-6,), **profile)
        assert request.request_hash == request_hash
        assert request.resume_contract_hash == resume_hash


def test_explicit_v4_compiler_accepts_interior_pin_and_roller_only():
    model = _model()
    for flags, expected in (
        ({}, "rc_fiber_frame_support_count_unsupported"),
        ({"experimental_two_fixed_endpoints": True}, "rc_fiber_frame_support_node_invalid"),
    ):
        compiled, blockers, _ = public._compile(model, **flags)
        assert compiled is None and blockers[0]["kind"] == expected
    compiled, blockers, _ = public._compile(
        model, experimental_pin_roller_beam=True
    )
    assert compiled is not None and not blockers
    assert compiled.problem.fixed_global_dofs == (3, 4, 16)
    assert compiled.support_node_ids == ("N2", "N6")
    assert compiled.problem.free_global_dofs.count(5) == 1  # pin rotation
    assert compiled.problem.free_global_dofs.count(15) == 1  # roller UX
    assert compiled.problem.free_global_dofs.count(17) == 1  # roller rotation


@pytest.mark.parametrize(
    ("mutate", "kind"),
    [
        (
            lambda p: p["supports"][1].update(dofs=["UX", "UY"]),
            "rc_fiber_frame_pin_roller_support_roles_invalid",
        ),
        (
            lambda p: p["supports"][1].update(dofs=["UY", "RZ"]),
            "rc_fiber_frame_support_dofs_invalid",
        ),
        (
            lambda p: p["supports"][1].update(node="N2"),
            "rc_fiber_frame_support_node_invalid",
        ),
        (
            lambda p: p["supports"][1].update(node="missing"),
            "rc_fiber_frame_support_node_invalid",
        ),
        (
            lambda p: p["nodes"][3]["coordinates"].__setitem__(1, 0.01),
            "rc_fiber_frame_pin_roller_beam_geometry_invalid",
        ),
        (
            lambda p: (
                p["nodes"][3]["coordinates"].__setitem__(0, 1.2),
                p["nodes"][4]["coordinates"].__setitem__(0, 0.95),
            ),
            "rc_fiber_frame_pin_roller_beam_geometry_invalid",
        ),
        (
            lambda p: p["loads"][0].update(node="N2"),
            "rc_fiber_frame_support_load_unsupported",
        ),
    ],
)
def test_v4_fail_closed_support_geometry_and_load_preflight(mutate, kind):
    payload = _payload()
    mutate(payload)
    compiled, blockers, _ = public._compile(
        _model(payload), experimental_pin_roller_beam=True
    )
    assert compiled is None and blockers[0]["kind"] == kind
    if kind == "rc_fiber_frame_support_load_unsupported":
        assert "pin or roller" in blockers[0]["detail"]


def test_v4_allows_endpoint_pin_roller_for_horizontal_beams_without_overhangs():
    payload = _payload()
    payload["supports"] = [
        {"node": "N1", "dofs": ["UX", "UY"]},
        {"node": "N7", "dofs": ["UY"]},
    ]
    compiled, blockers, _ = public._compile(
        _model(payload), experimental_pin_roller_beam=True
    )
    assert compiled is not None and not blockers
    assert compiled.problem.fixed_global_dofs == (0, 1, 19)


def test_v4_physical_identity_binds_pin_roller_profile_and_restrained_dofs():
    original = _model()
    renamed = deepcopy(_payload())
    aliases = {f"N{i}": f"BeamNode{i}" for i in range(1, 8)}
    for node in renamed["nodes"]:
        node["id"] = aliases[node["id"]]
    for member in renamed["elements"]:
        member["nodes"] = [aliases[node] for node in member["nodes"]]
    for row in renamed["loads"] + renamed["supports"]:
        row["node"] = aliases[row["node"]]
    profile = {"experimental_pin_roller_beam": True}
    physical = fiber_frame_physical_model_payload(original, **profile)
    assert physical == fiber_frame_physical_model_payload(_model(renamed), **profile)
    assert physical["compiler_profile"] == (
        public.EXPERIMENTAL_RC_FIBER_FRAME_PIN_ROLLER_BEAM_CONTROL_PROFILE
    )
    assert physical["fixed_global_dofs"] == [3, 4, 16]
    assert fiber_frame_physical_model_identity(original, **profile) == (
        fiber_frame_physical_model_identity(_model(renamed), **profile)
    )
    swapped = _payload()
    swapped["supports"] = [
        {"node": "N2", "dofs": ["UY"]},
        {"node": "N6", "dofs": ["UX", "UY"]},
    ]
    assert fiber_frame_physical_model_identity(original, **profile) != (
        fiber_frame_physical_model_identity(_model(swapped), **profile)
    )
    with pytest.raises(ValueError, match="supported public RC profile"):
        fiber_frame_physical_model_identity(original)
    with pytest.raises(ValueError, match="mutually exclusive"):
        fiber_frame_physical_model_identity(
            original,
            experimental_pin_roller_beam=True,
            experimental_two_fixed_endpoints=True,
        )


def test_v4_four_point_path_reactions_rotation_and_fresh_restart_replay():
    model, request = _model(), _request()
    assert request.to_dict()["schema_version"] == PIN_ROLLER_BEAM_REQUEST_SCHEMA_VERSION
    result = analyze_bounded_rc_fiber_direct_control(
        model, request.targets_m, **request.api_kwargs()
    )
    payload = result.to_dict()
    assert result.status == "ready" and result.contract_pass is True
    assert payload["model"]["compiler_profile"] == (
        public.EXPERIMENTAL_RC_FIBER_FRAME_PIN_ROLLER_BEAM_CONTROL_PROFILE
    )
    response = payload["terminal_response"]
    reactions = response["support_reactions"]
    assert [(row["node_id"], row["dof"]) for row in reactions] == [
        ("N2", "UX"),
        ("N2", "UY"),
        ("N6", "UY"),
    ]
    node_rows = {row["node_id"]: row for row in response["node_displacements"]}
    for node in ("N2", "N6"):
        assert node_rows[node]["UY_m"] == 0.0
        assert abs(node_rows[node]["RZ_rad"]) > 1e-9
    assert node_rows["N2"]["UX_m"] == 0.0
    assert abs(node_rows["N6"]["UX_m"]) < 1e-10
    applied_total_n = -2_000.0 * response["load_factor"]
    vertical_n = sum(row["value_si"] for row in reactions if row["dof"] == "UY")
    assert vertical_n + applied_total_n == pytest.approx(0.0, abs=1e-6)
    assert reactions[1]["value_si"] == pytest.approx(reactions[2]["value_si"], abs=1e-6)
    assert reactions[0]["value_si"] == pytest.approx(0.0, abs=1e-6)
    verified = validate_bounded_rc_fiber_direct_control_artifacts(
        model,
        request.targets_m,
        result=result.result_artifact_bytes(),
        checkpoint=result.checkpoint_artifact_bytes(),
        **request.api_kwargs(),
    )
    assert verified.status == "valid_artifact" and verified.contract_pass is True
    restart = result.checkpoint_artifact_bytes()
    continuation = analyze_bounded_rc_fiber_direct_control(
        model,
        (-2e-6,),
        control_global_dof=request.control_global_dof,
        experimental_pin_roller_beam=True,
        restart=restart,
    )
    assert continuation.status == "ready" and continuation.contract_pass is True
    assert len(continuation.to_dict()["response_history"]) == 2
    assert continuation.to_dict()["response_history"][0] == response


def test_v4_restart_rejects_a_different_pin_roller_partition():
    model, request = _model(), _request()
    first = analyze_bounded_rc_fiber_direct_control(
        model, request.targets_m, **request.api_kwargs()
    )
    swapped = _payload()
    swapped["supports"] = [
        {"node": "N2", "dofs": ["UY"]},
        {"node": "N6", "dofs": ["UX", "UY"]},
    ]
    with pytest.raises(ValueError, match="restart source/configuration/control/budget mismatch"):
        analyze_bounded_rc_fiber_direct_control(
            _model(swapped),
            (-2e-6,),
            control_global_dof=10,
            experimental_pin_roller_beam=True,
            restart=first.checkpoint_artifact_bytes(),
        )


@pytest.mark.parametrize("node", ("N2", "N6"))
def test_v4_preload_cannot_be_applied_directly_at_a_restrained_support(node):
    with pytest.raises(ValueError, match="support node"):
        analyze_bounded_rc_fiber_direct_control(
            _model(),
            (-1e-6,),
            control_global_dof=10,
            experimental_pin_roller_beam=True,
            constant_nodal_loads=((node, 0.0, -1.0, 0.0),),
        )


def test_v4_failed_second_target_rolls_back_to_first_original(monkeypatch):
    model = _model()
    original = control_path.solve_stateful_fiber_frame2d_displacement_control_step
    calls = 0

    def fail_after_first(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic second-step failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        control_path,
        "solve_stateful_fiber_frame2d_displacement_control_step",
        fail_after_first,
    )
    result = analyze_bounded_rc_fiber_direct_control(
        model,
        (-1e-6, -2e-6),
        control_global_dof=10,
        experimental_pin_roller_beam=True,
    )
    payload = result.to_dict()
    assert result.status == "blocked" and result.contract_pass is False
    assert len(payload["response_history"]) == 1
    assert payload["path"]["attempts"][1]["rollback_exact"] is True
    assert payload["path"]["attempts"][1]["accepted_checkpoint_hash"] == (
        payload["path"]["attempts"][1]["parent_checkpoint_hash"]
    )
    assert payload["checkpoint"] is not None


def test_v4_cli_run_replays_exact_synthetic_beam(tmp_path):
    model_path = tmp_path / "model.json"
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    model_path.write_text(json.dumps(_payload()))
    request_path.write_text(json.dumps(_request().to_dict()))
    assert cli.main(
        [
            "run",
            "--model",
            str(model_path),
            "--request",
            str(request_path),
            "--output",
            str(result_path),
            "--report",
            str(report_path),
            "--checkpoint-output",
            str(checkpoint_path),
        ]
    ) == 0
    result = json.loads(result_path.read_bytes())
    report = json.loads(report_path.read_bytes())
    assert result["request"]["experimental_pin_roller_beam"] is True
    assert len(result["terminal_response"]["support_reactions"]) == 3
    assert report["request"]["schema_version"] == PIN_ROLLER_BEAM_REQUEST_SCHEMA_VERSION
    assert report["contract_pass"] is True
    assert report["verification"]["fresh_source_execution_invoked"] is True
    assert checkpoint_path.is_file()
    verify_report_path = tmp_path / "verify-report.json"
    assert cli.main(
        [
            "verify",
            "--model",
            str(model_path),
            "--request",
            str(request_path),
            "--result",
            str(result_path),
            "--checkpoint",
            str(checkpoint_path),
            "--report",
            str(verify_report_path),
        ]
    ) == 0
    verify_report = json.loads(verify_report_path.read_bytes())
    assert verify_report["contract_pass"] is True
    assert verify_report["verification"]["fresh_source_execution_invoked"] is True
    tampered = deepcopy(result)
    tampered["terminal_response"]["support_reactions"][1]["value_si"] += 1.0
    tampered_path = tmp_path / "tampered-result.json"
    tampered_path.write_text(json.dumps(tampered))
    bad_report_path = tmp_path / "bad-verify-report.json"
    assert cli.main(
        [
            "verify",
            "--model",
            str(model_path),
            "--request",
            str(request_path),
            "--result",
            str(tampered_path),
            "--checkpoint",
            str(checkpoint_path),
            "--report",
            str(bad_report_path),
        ]
    ) == 2
    bad_report = json.loads(bad_report_path.read_bytes())
    assert bad_report["artifact_contract_pass"] is False
