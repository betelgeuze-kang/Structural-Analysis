"""The force-response sidecar never grants authority from a self-declared row."""

import importlib.util
import json
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_rc_force_response_floor",
    SOURCE / "scripts" / "audit_rc_force_response_floor.py",
)
assert SPEC and SPEC.loader
floor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(floor)


def _plan_and_request():
    request = {
        "targets_m": [-0.00014],
        "control_global_dof": 10,
        "experimental_pin_roller_beam": True,
        "constant_nodal_loads": [],
        "solver_config": {
            "control_tolerance_m": 1e-12,
            "load_factor_coordinate_scale_m": 0.001,
            "newton": {"max_iterations": 4},
        },
    }
    plan = {
        "schema_version": floor.PLAN_SCHEMA,
        "source_revision": "a" * 40,
        "audit_receipt_sha256": "sha256:" + "b" * 64,
        "target_index": 0,
        "target_displacement_m": -0.00014,
        "minimum_load_factor": 180.0,
        "evaluation_timing": "posthoc",
    }
    return plan, request


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("target_index", True, "exact target index"),
        ("target_index", 1, "exact target index"),
        ("target_displacement_m", -0.00013, "target displacement"),
        ("minimum_load_factor", 0.0, "positive finite"),
        ("minimum_load_factor", True, "positive finite"),
        ("minimum_load_factor", float("inf"), "positive finite"),
        ("evaluation_timing", "prospective", "posthoc diagnosis only"),
        ("audit_receipt_sha256", "sha256:" + "c" * 64, "pin the passing audit"),
    ],
)
def test_floor_plan_rejects_ambiguous_or_unbound_inputs(field, value, message):
    plan, request = _plan_and_request()
    floor.validate_plan(plan, request, "a" * 40, "sha256:" + "b" * 64)
    plan[field] = value
    with pytest.raises(ValueError, match=message):
        floor.validate_plan(plan, request, "a" * 40, "sha256:" + "b" * 64)


@pytest.mark.parametrize("mutation", ["preload", "not_pin_roller"])
def test_floor_plan_refuses_changed_loading_scope(mutation):
    plan, request = _plan_and_request()
    if mutation == "preload":
        request["constant_nodal_loads"] = [{"node_id": "N4", "FY_kN": -1.0}]
    else:
        request["experimental_pin_roller_beam"] = False
    with pytest.raises(ValueError, match="without preload"):
        floor.validate_plan(plan, request, "a" * 40, "sha256:" + "b" * 64)


@pytest.mark.parametrize("reversed_factor", [0.0, -183.3385816483193])
def test_positive_floor_rejects_reversed_or_zero_baseline_direction(reversed_factor):
    outcomes = [
        {"candidate_id": "baseline", "load_factor_at_target": reversed_factor},
        {"candidate_id": "w42", "load_factor_at_target": 183.3385816483193},
    ]
    with pytest.raises(ValueError, match="baseline load factor must be positive"):
        floor.require_positive_baseline_factor(outcomes)
    outcomes[0]["load_factor_at_target"] = 190.45085421226264
    floor.require_positive_baseline_factor(outcomes)


def _saved_verified_row(tmp_path):
    directory = tmp_path / "oracle"
    candidate_dir = directory / "w42"
    candidate_dir.mkdir(parents=True)
    checkpoint_hash = "sha256:" + "1" * 64
    step_hash = "sha256:" + "2" * 64
    parent_hash = "sha256:" + "3" * 64
    _, request = _plan_and_request()
    result = {
        "schema_version": "bounded-rc-fiber-direct-control-result.v1",
        "status": "ready",
        "contract_pass": True,
        "failure": None,
        "unsupported_features": [],
        "request": {
            "control_global_dof": 10,
            "targets_m": [-0.00014],
            "experimental_pin_roller_beam": True,
            "configuration": request["solver_config"],
        },
        "path": {
            "schema_version": "stateful-fiber-frame2d-control-path.v1",
            "status": "ready",
            "targets_m": [-0.00014],
            "accepted_target_prefix_m": [-0.00014],
            "attempts": [{
                "committed": True,
                "target_control_displacement_m": -0.00014,
                "accepted_checkpoint_hash": checkpoint_hash,
                "parent_checkpoint_hash": parent_hash,
                "step": {
                    "step_hash": step_hash,
                    "accepted_checkpoint": {
                        "state_hash": checkpoint_hash,
                        "parent_state_hash": parent_hash,
                        "load_factor": 183.3385816483193,
                        "global_displacements": [0.0] * 10 + [-0.00014],
                    },
                },
            }],
        },
        "control": {"global_dof": 10, "component": "UY", "node_id": "N4"},
        "response_history": [{
            "checkpoint_hash": checkpoint_hash,
            "parent_checkpoint_hash": parent_hash,
            "source_step_hash": step_hash,
            "node_displacements": [{"node_id": "N4", "UY_m": -0.00014}],
            "load_factor": 183.3385816483193,
        }],
    }
    result["path"]["path_hash"] = floor.sha(floor.canonical(result["path"]))
    result["result_hash"] = floor.sha(floor.canonical(result))
    verification = {
        "schema_version": "bounded-rc-fiber-direct-control-validation.v1",
        "status": "valid_artifact",
        "contract_pass": True,
        "artifact_contract_pass": True,
        "fresh_source_execution_invoked": True,
        "solver_replay_performed": True,
        "physical_path_complete": True,
        "unavailable_execution_work": False,
        "verified_result_hash": result["result_hash"],
        "errors": [],
    }
    row = {
        "candidate_id": "w42",
        "status": "verified",
        "failure": None,
        "full_reference_verification_pass": True,
        "selection_eligible": True,
        "screens": {"declared_upper_bound": {"status": "pass"}},
        "artifacts": {},
    }

    def save(name, value):
        relative = f"w42/{name}.json"
        raw = floor.canonical(value) + b"\n"
        (directory / relative).write_bytes(raw)
        row["artifacts"][name] = {
            "path": relative,
            "byte_length": len(raw),
            "sha256": floor.sha(raw),
        }

    save("result", result)
    save("verification", verification)
    return row, result, verification, directory, save


def test_floor_value_comes_from_exact_verified_target(tmp_path):
    row, _, _, directory, _ = _saved_verified_row(tmp_path)
    _, request = _plan_and_request()
    value = floor.verified_load_factor(
        row, {}, directory, request, 0, -0.00014
    )
    assert value == 183.3385816483193
    assert value >= 180.0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("changed_bytes", "artifact bytes differ"),
        ("unsealed_result", "original result is incomplete"),
        ("wrong_replay_hash", "stored fresh replay receipt"),
        ("wrong_target_coordinate", "target displacement not verified"),
        ("response_only_factor", "accepted checkpoint differs from target response"),
    ],
)
def test_resealed_or_changed_originals_do_not_grant_floor_pass(
    tmp_path, mutation, message
):
    row, result, verification, directory, save = _saved_verified_row(tmp_path)
    _, request = _plan_and_request()
    if mutation == "changed_bytes":
        path = directory / "w42/result.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "unsealed_result":
        result["response_history"][0]["load_factor"] = 999.0
        save("result", result)
    elif mutation == "wrong_replay_hash":
        verification["verified_result_hash"] = "sha256:" + "f" * 64
        save("verification", verification)
    else:
        if mutation == "wrong_target_coordinate":
            result["response_history"][0]["node_displacements"][0]["UY_m"] = -0.00013
        else:
            result["response_history"][0]["load_factor"] = 999.0
        result.pop("result_hash")
        result["result_hash"] = floor.sha(floor.canonical(result))
        verification["verified_result_hash"] = result["result_hash"]
        save("result", result)
        save("verification", verification)
    with pytest.raises(ValueError, match=message):
        floor.verified_load_factor(row, {}, directory, request, 0, -0.00014)


def test_floor_json_rejects_duplicate_keys_and_external_symlink(tmp_path):
    duplicate = tmp_path / "ambiguous.json"
    duplicate.write_text('{"target_index":0,"target_index":1}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        floor.load(duplicate)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"load_factor": 999}))
    packet = tmp_path / "packet"
    packet.mkdir()
    (packet / "escape.json").symlink_to(outside)
    reference = {"path": "escape.json", "byte_length": outside.stat().st_size,
                 "sha256": floor.sha(outside.read_bytes())}
    with pytest.raises(ValueError, match="escapes packet"):
        floor.checked_ref(packet, reference, "escape")
