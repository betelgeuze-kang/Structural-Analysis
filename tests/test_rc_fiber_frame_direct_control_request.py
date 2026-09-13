"""Transport-only RC control contracts; no analysis is performed."""

from copy import deepcopy
from dataclasses import fields, replace
import json

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control_request as request
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as path
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


def minimal(**updates):
    return {
        "schema_version": request.REQUEST_SCHEMA_VERSION,
        "control_global_dof": 4,
        "targets_m": [-1e-5, -2e-5],
        **updates,
    }


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("request decode/encode must not solve")

    monkeypatch.setattr(
        path, "solve_stateful_fiber_frame2d_displacement_control_step", forbidden
    )


@pytest.mark.parametrize("config", [None, {}, {"newton": {}}])
def test_defaults_and_mapping_bytes_roundtrip(config):
    payload = minimal()
    if config is not None:
        payload["solver_config"] = config
    original = deepcopy(payload)
    typed = request.decode_bounded_rc_fiber_direct_control_request(payload)
    encoded = request.bounded_rc_fiber_direct_control_request_payload(typed)
    restored = request.decode_bounded_rc_fiber_direct_control_request(
        json.dumps(encoded).encode()
    )
    assert typed == restored
    assert typed.solver_config == StatefulFiberFrame2DDisplacementControlConfig()
    assert typed.request_hash == restored.request_hash
    assert typed.resume_contract_hash == restored.resume_contract_hash
    assert payload == original
    encoded["solver_config"]["newton"]["line_search_alphas"].clear()
    assert typed.solver_config.newton.line_search_alphas


def test_all_constructor_settings_preserved_including_polishing_and_line_search():
    config = StatefulFiberFrame2DDisplacementControlConfig(
        newton=NewtonRaphsonConfig(
            residual_tolerance=2e-9,
            increment_tolerance=3e-11,
            max_iterations=17,
            line_search_alphas=(1.0, 0.2, 0.03),
            terminal_polishing=True,
        ),
        control_tolerance_m=4e-12,
        load_factor_coordinate_scale_m=0.004,
    )
    typed = request.BoundedRCFiberDirectControlRequest(
        4, (-1e-5, 2e-5, 0.0), config, True, 2, 7
    )
    payload = request.bounded_rc_fiber_direct_control_request_payload(typed)
    assert set(payload["solver_config"]) == {f.name for f in fields(config)}
    assert set(payload["solver_config"]["newton"]) == {
        f.name for f in fields(config.newton)
    }
    restored = request.decode_bounded_rc_fiber_direct_control_request(payload)
    assert (
        restored == typed
        and restored.solver_config.contract_hash == config.contract_hash
    )
    assert restored.api_kwargs()["config"] == config
    assert (
        replace(typed, targets_m=(1e-5,)).resume_contract_hash
        == typed.resume_contract_hash
    )
    assert replace(typed, targets_m=(1e-5,)).request_hash != typed.request_hash
    for changed in (
        replace(typed, maximum_targets=8),
        replace(typed, maximum_reversals=3),
        replace(typed, solver_config=replace(config, control_tolerance_m=8e-12)),
    ):
        assert changed.resume_contract_hash != typed.resume_contract_hash


@pytest.mark.parametrize(
    "update",
    [
        {"schema_version": "old"},
        {"unknown": 1},
        {"control_global_dof": True},
        {"control_global_dof": 5},
        {"control_global_dof": -1},
        {"control_global_dof": 48},
        {"targets_m": [True]},
        {"targets_m": [".1"]},
        {"targets_m": [2**53]},
        {"targets_m": [1e-5, 1e-5]},
        {"targets_m": list(range(256))},
        {"targets_m": [0.1, -0.1, 0.1]},
        {"targets_m": None},
        {"allow_reversals": 1},
        {"maximum_reversals": True},
        {"maximum_reversals": 1},
        {"allow_reversals": True, "maximum_reversals": 255},
        {"maximum_targets": True},
        {"maximum_targets": 0},
        {"maximum_targets": 256},
        {"maximum_targets": 1},
        {"solver_config": {"unknown": 1}},
        {"solver_config": {"newton": {"extra": 1}}},
        {"solver_config": {"newton": {"max_iterations": 201}}},
        {"solver_config": {"newton": {"max_iterations": True}}},
        {"solver_config": {"newton": {"max_iterations": 1.0}}},
        {"solver_config": {"newton": {"terminal_polishing": 1}}},
        {
            "solver_config": {
                "newton": {"matrix_backend": "scipy_sparse_splu_cpu_exact_1536"}
            }
        },
        {"solver_config": {"newton": {"line_search_alphas": [True]}}},
        {"solver_config": {"newton": {"line_search_alphas": [0.5, 1]}}},
        {"solver_config": {"newton": {"line_search_alphas": []}}},
        {"solver_config": {"control_tolerance_m": 0}},
        {"solver_config": {"load_factor_coordinate_scale_m": True}},
    ],
)
def test_invalid_fields_types_and_limits_reject(update):
    with pytest.raises(ValueError):
        request.decode_bounded_rc_fiber_direct_control_request(minimal(**update))


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"[]",
        b"\xff",
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":1e999}',
        b'{"a":' + b"[" * 70 + b"0" + b"]" * 70 + b"}",
        b" " * (request.REQUEST_MAX_BYTES + 1),
        bytearray(b"{}"),
        "{}",
    ],
)
def test_invalid_raw_bytes_fail_closed(raw):
    with pytest.raises(ValueError):
        request.decode_bounded_rc_fiber_direct_control_request(raw)


@pytest.mark.parametrize("layer", ["top", "solver", "newton"])
def test_duplicate_keys_rejected_at_each_config_layer(layer):
    payload = request.bounded_rc_fiber_direct_control_request_payload(
        request.decode_bounded_rc_fiber_direct_control_request(minimal())
    )
    raw = json.dumps(payload)
    key = {
        "top": '"control_global_dof": 4',
        "solver": '"control_tolerance_m": 1e-12',
        "newton": '"max_iterations": 25',
    }[layer]
    assert key in raw
    raw = raw.replace(key, key + ", " + key, 1)
    with pytest.raises(ValueError, match="duplicate"):
        request.decode_bounded_rc_fiber_direct_control_request(raw.encode())


def test_empty_suffix_and_zero_are_preserved_for_restart_context_preflight():
    assert (
        request.decode_bounded_rc_fiber_direct_control_request(
            minimal(targets_m=[])
        ).targets_m
        == ()
    )
    assert request.decode_bounded_rc_fiber_direct_control_request(
        minimal(targets_m=[-0.0])
    ).to_dict()["targets_m"] == [-0.0]


@pytest.mark.parametrize(
    "mapping",
    [
        {1: "coerced"},
        minimal(targets_m=(0.1,)),
        minimal(solver_config={"newton": {1: 2}}),
    ],
)
def test_mapping_does_not_coerce_non_json_keys_or_sequences(mapping):
    with pytest.raises(ValueError):
        request.decode_bounded_rc_fiber_direct_control_request(mapping)


def test_mapping_alias_expansion_is_bounded_before_json_serialization():
    tree = [1]
    for _ in range(30):
        tree = [tree, tree]
    with pytest.raises(ValueError, match="node count"):
        request.decode_bounded_rc_fiber_direct_control_request(minimal(targets_m=tree))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 2**53, True, -1, 0])
@pytest.mark.parametrize("field", ["residual_tolerance", "increment_tolerance"])
def test_all_newton_numeric_tolerances_reject_invalid_values(field, value):
    with pytest.raises(ValueError):
        request.decode_bounded_rc_fiber_direct_control_request(
            minimal(solver_config={"newton": {field: value}})
        )
