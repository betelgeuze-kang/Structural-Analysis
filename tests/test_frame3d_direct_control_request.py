"""Strict transport and typed identity checks; this module never runs a solver."""

from copy import deepcopy
from dataclasses import fields, replace
import json

import pytest

from structural_analysis.api import frame3d_direct_control as public_api
from structural_analysis.api import frame3d_direct_control_request as request
from structural_analysis.api.frame3d_direct_control import (
    BoundedFrame3DDirectControlConfig,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    StatefulCorotationalFrame3DDisplacementControlConfig as SolverConfig,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseConfig as FrameConfig,
)
from structural_analysis.solvers.nonlinear.scalable_sparse_factorization import (
    SCALABLE_SPARSE_FACTORIZATION_POLICY_ID,
    ScalableSparseFactorizationPolicy,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SPARSE_FACTORIZATION_POLICY_ID,
    SparseFactorizationPolicy,
)


def _bytes(payload):
    return json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _minimal(**values):
    return {
        "schema_version": "bounded-frame3d-direct-control-request.v1",
        "control_node_id": "roof-절점",
        "control_dof": "UX",
        "control_targets": [0.001, 0.002],
        **values,
    }


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("request transport must not execute the solver")

    monkeypatch.setattr(
        public_api,
        "run_stateful_corotational_frame3d_displacement_control_path",
        forbidden,
    )
    monkeypatch.setattr(
        public_api, "analyze_bounded_frame3d_direct_control_model_ir", forbidden
    )


def _roundtrip(config):
    payload = request.bounded_frame3d_direct_control_request_payload(config)
    restored = request.decode_bounded_frame3d_direct_control_request(_bytes(payload))
    assert restored == config
    assert restored.to_dict() == config.to_dict()
    assert restored.request_hash == config.request_hash
    assert restored.resume_contract_hash == config.resume_contract_hash
    assert restored.solver_config.contract_hash == config.solver_config.contract_hash
    assert (
        restored.solver_config.frame_config.factorization_policy.policy_hash
        == config.solver_config.frame_config.factorization_policy.policy_hash
    )
    assert type(restored.control_targets) is tuple
    assert type(restored.solver_config.line_search_alphas) is tuple
    assert type(restored.solver_config.frame_config.line_search_alphas) is tuple
    return payload, restored


@pytest.mark.parametrize("solver_config", (None, {}, {"frame_config": {}}))
def test_omitted_configuration_keeps_existing_nested_default_factory(solver_config):
    payload = _minimal()
    if solver_config is not None:
        payload["solver_config"] = solver_config
    config = request.decode_bounded_frame3d_direct_control_request(_bytes(payload))
    expected = BoundedFrame3DDirectControlConfig("roof-절점", "UX", (0.001, 0.002))
    assert config == expected
    policy = config.solver_config.frame_config.factorization_policy
    assert policy.maximum_condition_number_1 == 1e14
    assert policy.minimum_normalized_absolute_pivot == 1e-16
    _roundtrip(config)


@pytest.mark.parametrize(
    "policy_class,policy_id",
    (
        (SparseFactorizationPolicy, SPARSE_FACTORIZATION_POLICY_ID),
        (ScalableSparseFactorizationPolicy, SCALABLE_SPARSE_FACTORIZATION_POLICY_ID),
    ),
)
def test_explicit_named_policy_uses_its_own_defaults(policy_class, policy_id):
    payload = _minimal(
        solver_config={
            "frame_config": {"factorization_policy": {"policy_id": policy_id}}
        }
    )
    config = request.decode_bounded_frame3d_direct_control_request(_bytes(payload))
    policy = config.solver_config.frame_config.factorization_policy
    assert type(policy) is policy_class
    assert policy == policy_class()
    if policy_class is SparseFactorizationPolicy:
        assert policy.maximum_condition_number_1 == 1e12
        assert policy.minimum_normalized_absolute_pivot == 1e-14
        assert (
            config.resume_contract_hash
            != BoundedFrame3DDirectControlConfig(
                "roof-절점", "UX", (0.001, 0.002)
            ).resume_contract_hash
        )
    _roundtrip(config)


def _custom_solver(policy):
    frame = FrameConfig(
        residual_relative_tolerance=2e-8,
        residual_absolute_tolerance_kn=3e-7,
        increment_relative_tolerance=4e-10,
        increment_absolute_tolerance_m=5e-12,
        maximum_iterations=55,
        minimum_characteristic_length_m=6e-12,
        minimum_reference_force_kn=7.0,
        line_search_alphas=(1.0, 0.75, 0.25),
        adaptive_load_cutback_enabled=False,
        load_cutback_ratio=0.4,
        maximum_load_cutback_depth=9,
        maximum_load_cutback_substeps=257,
        minimum_load_increment_factor=8e-6,
        factorization_policy=policy,
    )
    return SolverConfig(
        frame_config=frame,
        control_relative_tolerance=2e-10,
        control_absolute_tolerance_m=3e-12,
        control_absolute_tolerance_rad=4e-12,
        minimum_control_reference_m=5e-9,
        load_factor_increment_tolerance=6e-10,
        maximum_iterations=44,
        maximum_path_targets=10,
        allow_direction_reversal=True,
        maximum_direction_reversals=2,
        adaptive_target_cutback_enabled=False,
        target_cutback_ratio=0.3,
        maximum_target_cutback_depth=6,
        maximum_target_cutback_substeps=150,
        maximum_path_solve_attempts=1024,
        minimum_control_increment_m=7e-9,
        minimum_control_increment_rad=8e-9,
        line_search_alphas=(1.0, 0.6, 0.2),
    )


@pytest.mark.parametrize("control_dof", ("UX", "UY", "UZ", "RX", "RY", "RZ"))
@pytest.mark.parametrize(
    "policy",
    (
        SparseFactorizationPolicy(
            maximum_condition_number_1=2e12,
            minimum_normalized_absolute_pivot=3e-14,
            maximum_backward_error=4e-12,
            maximum_exact_condition_equations=128,
        ),
        ScalableSparseFactorizationPolicy(
            maximum_condition_number_1=2e14,
            minimum_normalized_absolute_pivot=3e-16,
            maximum_backward_error=4e-12,
            maximum_equations=320,
            inverse_solve_block_size=8,
        ),
    ),
)
def test_all_custom_constructor_knobs_and_control_units_roundtrip(policy, control_dof):
    config = BoundedFrame3DDirectControlConfig(
        "roof-절점", control_dof, (0.001, -0.001, 0.002), _custom_solver(policy)
    )
    payload, restored = _roundtrip(config)
    assert restored.control_unit == ("m" if control_dof.startswith("U") else "rad")
    assert set(payload) == {
        "schema_version",
        "control_node_id",
        "control_dof",
        "control_targets",
        "solver_config",
    }
    solver = payload["solver_config"]
    frame = solver["frame_config"]
    for actual, cls in (
        (solver, SolverConfig),
        (frame, FrameConfig),
        (frame["factorization_policy"], type(policy)),
    ):
        assert set(actual) == {field.name for field in fields(cls) if field.init}
    assert "profile" not in solver
    assert "policy_hash" not in frame["factorization_policy"]


def test_payload_exports_are_detached_and_source_bytes_remain_unchanged():
    source = _bytes(_minimal())
    frozen = bytes(source)
    config = request.decode_bounded_frame3d_direct_control_request(source)
    identity = config.request_hash, config.resume_contract_hash
    exported = request.bounded_frame3d_direct_control_request_payload(config)
    exported["control_targets"][0] = 999
    exported["solver_config"]["line_search_alphas"].clear()
    exported["solver_config"]["frame_config"]["factorization_policy"]["policy_id"] = (
        "changed"
    )
    assert source == frozen
    assert (config.request_hash, config.resume_contract_hash) == identity
    _roundtrip(config)
    next_leg = replace(config, control_targets=(0.003,))
    assert next_leg.request_hash != config.request_hash
    assert next_leg.resume_contract_hash == config.resume_contract_hash


@pytest.mark.parametrize(
    "payload",
    (
        {},
        _minimal(schema_version="bounded-frame3d-direct-control-request.v2"),
        _minimal(schema_version=True),
        _minimal(control_node_id=1),
        _minimal(control_node_id=""),
        _minimal(control_dof="ux"),
        _minimal(control_dof=["UX"]),
        _minimal(control_targets=None),
        _minimal(control_targets="0.1"),
        _minimal(control_targets=[]),
        _minimal(control_targets=[True]),
        _minimal(control_targets=["0.1"]),
        _minimal(control_targets=[[0.1]]),
        _minimal(control_targets=[2**53 + 1]),
        _minimal(solver_config=None),
        _minimal(solver_config=[]),
        _minimal(solver_config={"frame_config": None}),
        _minimal(solver_config={"line_search_alphas": [1, True]}),
        _minimal(solver_config={"line_search_alphas": "1"}),
        _minimal(solver_config={"line_search_alphas": [0.5]}),
        _minimal(solver_config={"line_search_alphas": [1, 0.5, 0.5]}),
        _minimal(solver_config={"line_search_alphas": [1, 0]}),
        _minimal(solver_config={"line_search_alphas": []}),
        _minimal(solver_config={"maximum_iterations": 201}),
        _minimal(solver_config={"frame_config": {"maximum_iterations": 20}}),
        _minimal(solver_config={"maximum_path_targets": 1}),
        _minimal(solver_config={"maximum_direction_reversals": 1}),
        _minimal(solver_config={"allow_direction_reversal": True}),
        _minimal(solver_config={"target_cutback_ratio": 1}),
        _minimal(solver_config={"maximum_path_solve_attempts": 65537}),
    ),
)
def test_invalid_top_level_and_linked_typed_contracts_fail_without_solver(payload):
    with pytest.raises(ValueError):
        request.decode_bounded_frame3d_direct_control_request(_bytes(payload))


@pytest.mark.parametrize("layer", ("request", "solver", "frame", "policy"))
@pytest.mark.parametrize("unknown", ("extra", "profile", "contract_hash", "__class__"))
def test_unknown_fields_are_rejected_at_every_object_depth(layer, unknown):
    config = BoundedFrame3DDirectControlConfig("N", "UX", (0.001,))
    payload = request.bounded_frame3d_direct_control_request_payload(config)
    target = payload
    for key in {
        "request": (),
        "solver": ("solver_config",),
        "frame": ("solver_config", "frame_config"),
        "policy": ("solver_config", "frame_config", "factorization_policy"),
    }[layer]:
        target = target[key]
    target[unknown] = None
    with pytest.raises(ValueError, match="fields"):
        request.decode_bounded_frame3d_direct_control_request(_bytes(payload))


@pytest.mark.parametrize(
    "layer,field_map",
    (
        ("solver", request._SOLVER_FIELDS),
        ("frame", request._FRAME_FIELDS),
        ("exact", request._EXACT_POLICY_FIELDS),
        ("scalable", request._SCALABLE_POLICY_FIELDS),
    ),
)
def test_all_counts_flags_and_numbers_reject_json_type_confusion(layer, field_map):
    policy = (
        ScalableSparseFactorizationPolicy()
        if layer == "scalable"
        else SparseFactorizationPolicy()
    )
    base = request.bounded_frame3d_direct_control_request_payload(
        BoundedFrame3DDirectControlConfig("N", "UX", (0.001,), _custom_solver(policy))
    )
    for field, kind in field_map.items():
        bad_values = {
            "number": (True, "1", None, 2**53 + 1),
            "count": (True, 1.0, "1", None, -1),
            "boolean": (0, 1, "false", None),
        }.get(kind, ())
        for value in bad_values:
            payload = deepcopy(base)
            target = payload["solver_config"]
            if layer != "solver":
                target = target["frame_config"]
            if layer in ("exact", "scalable"):
                target = target["factorization_policy"]
            target[field] = value
            with pytest.raises(ValueError):
                request.decode_bounded_frame3d_direct_control_request(_bytes(payload))


@pytest.mark.parametrize(
    "policy",
    (
        {},
        None,
        [],
        {"policy_id": None},
        {"policy_id": True},
        {"policy_id": "custom"},
        {"policy_id": SPARSE_FACTORIZATION_POLICY_ID, "maximum_equations": 100},
        {
            "policy_id": SCALABLE_SPARSE_FACTORIZATION_POLICY_ID,
            "maximum_exact_condition_equations": 100,
        },
        {
            "policy_id": SCALABLE_SPARSE_FACTORIZATION_POLICY_ID,
            "maximum_equations": 8,
            "inverse_solve_block_size": 9,
        },
    ),
)
def test_missing_unknown_or_cross_profile_policy_never_falls_back(policy):
    with pytest.raises(ValueError):
        request.decode_bounded_frame3d_direct_control_request(
            _bytes(
                _minimal(
                    solver_config={"frame_config": {"factorization_policy": policy}}
                )
            )
        )


def test_serializer_rejects_custom_or_misleading_scalable_policy_id():
    for policy_id in ("custom", SPARSE_FACTORIZATION_POLICY_ID):
        config = BoundedFrame3DDirectControlConfig(
            "N",
            "UX",
            (0.001,),
            _custom_solver(ScalableSparseFactorizationPolicy(policy_id=policy_id)),
        )
        with pytest.raises(ValueError):
            request.bounded_frame3d_direct_control_request_payload(config)


@pytest.mark.parametrize(
    "raw",
    (
        b"",
        b"null",
        b"[]",
        b"true",
        b"1",
        b"{",
        b"{} {}",
        b"\xff",
        b'{"x":1,"x":2}',
        b'{"x":{"a":1,"a":2}}',
        b'{"x":1,"\\u0078":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        b'{"x":1e400}',
        b'{"x":-1e400}',
        b'{"x":' + b"9" * 400 + b"}",
        b'{"x":"\\ud800"}',
        b'{"\\udfff":1}',
        b'{"x":' + b"[" * 65 + b"0" + b"]" * 65 + b"}",
        b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}",
    ),
)
def test_strict_json_rejects_malformed_nonfinite_duplicate_or_deep_bytes(raw):
    with pytest.raises(ValueError):
        request.strict_json_object_bytes(raw)
    with pytest.raises(ValueError):
        request.decode_bounded_frame3d_direct_control_request(raw)


def test_strict_object_parser_preserves_model_transport_values_without_model_validation():
    payload = {
        "model": {
            "node_id": "기둥",
            "integer": 3,
            "real": 2.5,
            "flag": True,
            "unset": None,
            "rows": [0, -1, 1e-300],
        }
    }
    raw = _bytes(payload)
    assert request.strict_json_object_bytes(raw) == payload
    assert request.strict_json_object_bytes(raw, maximum_bytes=len(raw)) == payload
    with pytest.raises(ValueError, match="maximum_bytes"):
        request.strict_json_object_bytes(raw, maximum_bytes=len(raw) - 1)


@pytest.mark.parametrize("data", ("{}", bytearray(b"{}"), memoryview(b"{}"), {}, None))
def test_json_input_is_exact_bytes(data):
    with pytest.raises(ValueError, match="bytes"):
        request.strict_json_object_bytes(data)


@pytest.mark.parametrize("limit", (True, False, 1.0, 0, -1, "1", None))
def test_json_size_limit_is_a_positive_exact_integer(limit):
    with pytest.raises(ValueError, match="maximum_bytes"):
        request.strict_json_object_bytes(b"{}", maximum_bytes=limit)


def test_request_byte_budget_cannot_be_raised_by_payload_or_serializer():
    limit = request.BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_MAX_BYTES
    assert limit == 128 * 1024
    raw = _bytes(_minimal(control_node_id="N" * limit))
    with pytest.raises(ValueError, match="maximum_bytes"):
        request.decode_bounded_frame3d_direct_control_request(raw)
    # Generic transport callers can explicitly choose their own document budget.
    assert request.strict_json_object_bytes(raw, maximum_bytes=len(raw))[
        "control_node_id"
    ]
    config = BoundedFrame3DDirectControlConfig("N" * limit, "UX", (0.001,))
    with pytest.raises(ValueError, match="maximum_bytes"):
        request.bounded_frame3d_direct_control_request_payload(config)


@pytest.mark.parametrize("config", (None, {}, SolverConfig()))
def test_serializer_requires_the_exact_public_typed_config(config):
    with pytest.raises(ValueError):
        request.bounded_frame3d_direct_control_request_payload(config)
