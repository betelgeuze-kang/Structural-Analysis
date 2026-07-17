from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    STATE_IR_SCHEMA_VERSION,
    StateIRError,
    commit_trial_state,
    create_initial_state,
    open_trial_state,
    rollback_trial_state,
    validate_state_ir,
    validate_state_ir_manifest,
)

SCHEMA_PATH = REPO_ROOT / "src/structural_analysis/schemas/state_ir_v1.schema.json"


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _plan(**changes: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "model_ir_content_hash": _hash("1"),
        "solver_numeric_buffer_hash": _hash("2"),
        "solver_entity_mapping_hash": _hash("3"),
        "solver_artifact_hash": _hash("4"),
        "plan_hash": _hash("5"),
        "operator_hash": _hash("6"),
        "load_pattern_id": "LC1",
        "node_count": 2,
        "dof_count": 12,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_initial_state_is_schema_valid_deterministic_and_deeply_immutable() -> None:
    first = create_initial_state(_plan())
    second = create_initial_state(_plan())
    manifest = first.to_dict()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(manifest)
    assert first.schema_version == STATE_IR_SCHEMA_VERSION
    assert first.role == "committed"
    assert first.epoch == 0
    assert first.parent_state_hash is None
    assert first.load_step == 0
    assert first.iteration == 0
    assert first.load_factor == 0.0
    assert first.state_hash == second.state_hash
    assert first.to_manifest() == manifest
    assert manifest["solver_numeric_buffer_hash"] == _hash("2")
    assert manifest["solver_entity_mapping_hash"] == _hash("3")
    assert manifest["solver_artifact_hash"] == _hash("4")
    assert manifest["kinematics"]["velocity_component_units"] == [
        "m/s",
        "m/s",
        "m/s",
        "rad/s",
        "rad/s",
        "rad/s",
    ]
    assert manifest["constitutive_state"] == {
        "mode": "stateless_linear_elastic",
        "stateful": False,
        "value_count": 0,
        "values": [],
    }

    for vector in (
        first.displacement_si,
        first.velocity_si,
        first.acceleration_si,
    ):
        assert vector.dtype.str == "<f8"
        assert vector.flags.c_contiguous
        assert not vector.flags.writeable
        assert not np.any(vector)
        with pytest.raises(ValueError):
            vector.setflags(write=True)
    with pytest.raises(TypeError):
        first.vector_hashes["displacement"] = _hash("f")
    with pytest.raises(TypeError):
        first.extensions["vendor:test"] = True


def test_trial_commit_and_exact_rollback_preserve_explicit_lineage() -> None:
    accepted = create_initial_state(_plan())
    accepted_manifest = accepted.to_dict()
    proposal = np.linspace(0.0, 0.011, accepted.dof_count, dtype="<f8")
    trial = open_trial_state(
        accepted,
        proposal,
        load_step=1,
        iteration=0,
        load_factor=1.0,
        time_s=0.0,
    )

    proposal[:] = -99.0
    assert trial.role == "trial"
    assert trial.epoch == 1
    assert trial.parent_state_hash == accepted.state_hash
    assert trial.state_hash != accepted.state_hash
    assert not np.any(trial.displacement_si == -99.0)

    rolled_back = rollback_trial_state(accepted, trial)
    assert rolled_back is accepted
    assert rolled_back.to_dict() == accepted_manifest

    committed = commit_trial_state(accepted, trial)
    assert committed.role == "committed"
    assert committed.epoch == trial.epoch
    assert committed.parent_state_hash == trial.state_hash
    np.testing.assert_array_equal(committed.displacement_si, trial.displacement_si)
    assert committed.vector_hashes == trial.vector_hashes
    validate_state_ir(committed, expected_plan=_plan())

    next_trial = open_trial_state(committed, committed.displacement_si, load_step=2)
    assert next_trial.epoch == 2
    assert next_trial.parent_state_hash == committed.state_hash


def test_signed_zero_is_normalized_before_vector_and_state_hashing() -> None:
    accepted = create_initial_state(_plan())
    positive = np.zeros(accepted.dof_count, dtype="<f8")
    negative = positive.copy()
    negative[0] = -0.0

    first = open_trial_state(accepted, positive)
    second = open_trial_state(accepted, negative)

    assert not np.any(np.signbit(second.displacement_si))
    assert first.vector_hashes == second.vector_hashes
    assert first.state_hash == second.state_hash


@pytest.mark.parametrize("nonfinite", [np.nan, np.inf, -np.inf])
def test_nonfinite_vector_and_scalar_inputs_fail_closed(nonfinite: float) -> None:
    accepted = create_initial_state(_plan())
    vector = np.zeros(accepted.dof_count, dtype="<f8")
    vector[3] = nonfinite

    with pytest.raises(StateIRError) as vector_error:
        open_trial_state(accepted, vector)
    assert vector_error.value.code == "state_vector_nonfinite"

    with pytest.raises(StateIRError) as scalar_error:
        open_trial_state(
            accepted,
            np.zeros(accepted.dof_count),
            load_factor=nonfinite,
        )
    assert scalar_error.value.code == "number_nonfinite"


def test_mutable_or_wrong_endian_forged_vectors_are_rejected() -> None:
    state = create_initial_state(_plan())
    mutable = state.displacement_si.copy()
    mutable.setflags(write=False)
    forged_mutable = replace(state, displacement_si=mutable)

    with pytest.raises(StateIRError) as mutable_error:
        validate_state_ir(forged_mutable)
    assert mutable_error.value.code == "state_vector_mutable"

    wrong_endian = np.asarray(state.displacement_si, dtype=">f8")
    wrong_endian.setflags(write=False)
    forged_endian = replace(state, displacement_si=wrong_endian)
    with pytest.raises(StateIRError) as endian_error:
        validate_state_ir(forged_endian)
    assert endian_error.value.code == "state_vector_dtype_invalid"


def test_forged_vector_hash_state_hash_and_mutable_hash_map_are_rejected() -> None:
    state = create_initial_state(_plan())
    forged_vector_hash = replace(
        state,
        vector_hashes=MappingProxyType(
            {**dict(state.vector_hashes), "displacement": _hash("f")}
        ),
    )
    with pytest.raises(StateIRError) as vector_error:
        validate_state_ir(forged_vector_hash)
    assert vector_error.value.code == "vector_hash_mismatch"

    forged_state_hash = replace(state, state_hash=_hash("e"))
    with pytest.raises(StateIRError) as state_error:
        validate_state_ir(forged_state_hash)
    assert state_error.value.code == "state_hash_mismatch"

    forged_mutable_hashes = replace(state, vector_hashes=dict(state.vector_hashes))
    with pytest.raises(StateIRError) as mapping_error:
        validate_state_ir(forged_mutable_hashes)
    assert mapping_error.value.code == "vector_hashes_mutable"


def test_stale_plan_parent_and_epoch_transitions_are_rejected() -> None:
    plan = _plan()
    accepted = create_initial_state(plan)
    trial = open_trial_state(accepted, np.zeros(accepted.dof_count))
    committed = commit_trial_state(accepted, trial)
    later_trial = open_trial_state(committed, committed.displacement_si, load_step=2)

    stale_plan = _plan(plan_hash=_hash("9"))
    with pytest.raises(StateIRError) as plan_error:
        validate_state_ir(accepted, expected_plan=stale_plan)
    assert plan_error.value.code == "state_plan_binding_mismatch"

    with pytest.raises(StateIRError) as parent_error:
        rollback_trial_state(accepted, later_trial)
    assert parent_error.value.code in {"trial_parent_mismatch", "trial_epoch_mismatch"}

    stale_epoch = replace(trial, epoch=3)
    with pytest.raises(StateIRError) as forged_error:
        rollback_trial_state(accepted, stale_epoch)
    assert forged_error.value.code == "state_hash_mismatch"


def test_plan_binding_shape_and_identifier_contracts_fail_closed() -> None:
    with pytest.raises(StateIRError) as missing:
        create_initial_state(SimpleNamespace())
    assert missing.value.code == "execution_plan_binding_missing"

    with pytest.raises(StateIRError) as inconsistent:
        create_initial_state(_plan(dof_count=11))
    assert inconsistent.value.code == "execution_plan_dof_count_invalid"

    with pytest.raises(StateIRError) as invalid_hash:
        create_initial_state(_plan(operator_hash="not-a-hash"))
    assert invalid_hash.value.code == "hash_invalid"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["kinematics"].update({"device_pointer": "0x123"}),
        lambda payload: payload.update({"epoch": 0.0}),
        lambda payload: payload.update({"dof_count": True}),
        lambda payload: payload["step"].update({"iteration": "0"}),
    ],
)
def test_state_manifest_rejects_unknown_fields_and_wrong_json_types(mutate) -> None:
    payload = deepcopy(create_initial_state(_plan()).to_dict())
    mutate(payload)

    with pytest.raises(StateIRError) as error:
        validate_state_ir_manifest(payload)

    assert error.value.code == "state_schema_invalid"


def test_state_manifest_rejects_stale_hash_after_schema_valid_change() -> None:
    payload = deepcopy(create_initial_state(_plan()).to_dict())
    payload["load_pattern_id"] = "LC2"

    with pytest.raises(StateIRError) as error:
        validate_state_ir_manifest(payload)

    assert error.value.code == "state_hash_mismatch"
