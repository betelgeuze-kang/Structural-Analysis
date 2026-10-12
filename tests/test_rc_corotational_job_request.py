"""Request admission and snapshot isolation; never execute numerical analysis."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict
import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.execution.rc_corotational_job_request import (
    RC_COROTATIONAL_JOB_OPERATION,
    RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
    RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION,
    rc_corotational_job_canonical_bytes,
    validate_rc_corotational_job_request,
)
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


MODEL = (
    Path(__file__).parents[1]
    / "examples/public_rc_fiber_frame_l_frame_material_history.json"
)


def request():
    # Transport uses exact JSON arrays; solver dataclasses use immutable tuples.
    return json.loads(
        json.dumps(
            {
                "schema_version": RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
                "operation": RC_COROTATIONAL_JOB_OPERATION,
                "case_id": "corotational-admission-test",
                "model": json.loads(MODEL.read_bytes()),
                "source_revision": "b" * 40,
                "result_contract": RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION,
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
                "execution_config": {
                    "attempt_limit_per_call": 1,
                    "maximum_api_invocations": 100,
                },
            }
        )
    )


@pytest.fixture(autouse=True)
def forbid_numerical_solves(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure request admission invoked numerical execution")

    for module_name, names in (
        (
            "structural_analysis.api.rc_corotational_control",
            (
                "analyze_rc_corotational_control",
                "validate_rc_corotational_control_artifacts",
                "solve_stateful_corotational_fiber_frame2d_load_step",
                "run_corotational_control_subdivision",
            ),
        ),
        (
            "structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision",
            ("solve_stateful_corotational_fiber_frame2d_displacement_control_step",),
        ),
    ):
        for name in names:
            monkeypatch.setattr(f"{module_name}.{name}", forbidden)


def change(payload, path, value):
    cursor = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def test_admitted_snapshot_named_options_and_progress_budget():
    payload = request()
    admitted = validate_rc_corotational_job_request(payload)
    assert admitted.to_dict() == payload
    assert validate_rc_corotational_job_request(admitted.request_bytes) == admitted
    assert (
        admitted.request_hash
        == "sha256:" + hashlib.sha256(admitted.request_bytes).hexdigest()
    )
    assert admitted.model.input_checksum == admitted.source_input_checksum
    assert admitted.model.canonical_model_checksum == admitted.source_model_checksum
    assert admitted.targets_m == (-1e-6, -2e-6, -1.5e-6)
    assert admitted.config.fixed_nodal_loads == (("N3", "FX", -0.01),)
    assert admitted.progress_total == 255
    assert admitted.progress_total != len(admitted.targets_m)
    assert admitted.progress_unit == "control_solver_attempts"
    assert admitted.source_revision_is_execution_attestation is False
    options = admitted.api_kwargs()
    assert options["control_node_id"] == "N3"
    assert options["control_component"] == "UY"
    assert options["attempt_limit_per_call"] == 1
    assert "maximum_api_invocations" not in options
    assert (
        type(options["config"])
        is StatefulCorotationalFiberFrame2DDisplacementControlConfig
    )
    assert type(options["preload_config"]) is NewtonRaphsonConfig


def test_caller_and_returned_mutations_do_not_change_frozen_request():
    payload = request()
    original = deepcopy(payload)
    admitted = validate_rc_corotational_job_request(payload)
    first_bytes, first_hash = admitted.request_bytes, admitted.request_hash
    payload["model"]["nodes"][0]["coordinates"][0] = 123.0
    payload["config"]["targets_m"][0] = 123.0
    payload["config"]["fixed_nodal_loads"][0][2] = 123.0
    payload["config"]["config"]["line_search_alphas"][0] = 0.25
    payload["execution_config"]["maximum_api_invocations"] = 1
    escaped = admitted.to_dict()
    escaped["model"]["nodes"].clear()
    escaped["config"]["targets_m"].clear()
    escaped_model = admitted.model
    escaped_model.nodes[0]["coordinates"][0] = 456.0
    escaped_model.loads.clear()
    escaped_options = admitted.api_kwargs()
    escaped_options["fixed_nodal_loads"] = ()
    assert admitted.to_dict() == original
    assert admitted.request_bytes == first_bytes and admitted.request_hash == first_hash
    assert admitted.model.nodes[0]["coordinates"][0] == 0.0
    assert admitted.config.fixed_nodal_loads == (("N3", "FX", -0.01),)
    for target, field, value in (
        (admitted, "case_id", "changed"),
        (admitted.config, "maximum_attempt_count", 1),
        (admitted.config.solver_config, "maximum_iterations", 1),
        (admitted.execution_config, "maximum_api_invocations", 1),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(target, field, value)


@pytest.mark.parametrize(
    "path,value",
    [
        (("source_revision",), "sha256:" + "b" * 64),
        (("source_revision",), "B" * 40),
        (("source_revision",), "b" * 39),
        (("source_revision",), 123),
        (("schema_version",), "structural-analysis-job-request.v5"),
        (("operation",), "bounded_rc_fiber_direct_control"),
        (("result_contract",), "bounded-rc-fiber-job-result.v1"),
        (("case_id",), "space in id"),
        (("config", "control_node_id"), "missing"),
        (("config", "control_node_id"), "N1"),
        (("config", "control_component"), "RZ"),
        (("config", "control_component"), True),
        (("config", "targets_m"), []),
        (("config", "targets_m"), [1.0] * 256),
        (("config", "targets_m"), [0.0, -0.0]),
        (("config", "targets_m"), [True]),
        (("config", "targets_m"), ["1.0"]),
        (("config", "targets_m"), [2**53]),
        (("config", "targets_m"), [float("nan")]),
        (("config", "fixed_nodal_loads"), [["N3", "FX", True]]),
        (("config", "fixed_nodal_loads"), [["missing", "FX", 1.0]]),
        (("config", "fixed_nodal_loads"), [["N3", "FZ", 1.0]]),
        (("config", "fixed_nodal_loads"), [["N3", "FX", 1.0], ["N3", "FX", 2.0]]),
        (("config", "fixed_nodal_loads"), [["N3", "FX"]]),
        (("config", "fixed_nodal_loads"), [["N3", "FX", 1.0]] * 49),
        (("config", "maximum_attempt_count"), True),
        (("config", "maximum_attempt_count"), 0),
        (("config", "maximum_attempt_count"), 4097),
        (("config", "maximum_subdivision_depth"), True),
        (("config", "maximum_subdivision_depth"), -1),
        (("config", "maximum_subdivision_depth"), 21),
        (("config", "experimental_pin_roller_beam"), 1),
        (("config", "experimental_fixed_guided_axial"), "true"),
        (("config", "config", "residual_tolerance"), True),
        (("config", "config", "maximum_iterations"), 201),
        (("config", "config", "line_search_alphas"), [1.0, True]),
        (("config", "config", "line_search_alphas"), [0.5, 1.0]),
        (("config", "config", "matrix_backend"), VECTOR_SPARSE_MATRIX_BACKEND),
        (("config", "preload_config", "max_iterations"), 201),
        (("config", "preload_config", "matrix_backend"), "unknown"),
        (("execution_config", "attempt_limit_per_call"), True),
        (("execution_config", "attempt_limit_per_call"), 0),
        (("execution_config", "attempt_limit_per_call"), 4097),
        (("execution_config", "maximum_api_invocations"), True),
        (("execution_config", "maximum_api_invocations"), 0),
        (("execution_config", "maximum_api_invocations"), 100001),
        (("model", "warnings"), [1]),
        (("model", "nodes", 1, "coordinates", 2), 0.5),
        (("model", "nodes", 1, "coordinates", 0), True),
    ],
)
def test_invalid_identity_or_execution_semantics_fail_before_solve(path, value):
    payload = request()
    change(payload, path, value)
    with pytest.raises(ValueError):
        validate_rc_corotational_job_request(payload)


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("config",),
        ("execution_config",),
        ("model",),
        ("model", "units"),
        ("model", "coordinate_system"),
        ("config", "config"),
        ("config", "preload_config"),
    ],
)
def test_extra_fields_and_missing_explicit_fields_rejected(path):
    payload = request()
    cursor = payload
    for key in path:
        cursor = cursor[key]
    cursor["unknown_field"] = 1
    with pytest.raises(ValueError):
        validate_rc_corotational_job_request(payload)
    cursor.pop("unknown_field")
    cursor.pop(next(iter(cursor)))
    with pytest.raises(ValueError):
        validate_rc_corotational_job_request(payload)


def test_profile_flags_match_supported_geometry_without_solve():
    payload = request()
    payload["config"]["experimental_pin_roller_beam"] = True
    payload["config"]["experimental_fixed_guided_axial"] = True
    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_rc_corotational_job_request(payload)
    payload["config"]["experimental_fixed_guided_axial"] = False
    with pytest.raises(ValueError, match="unsupported corotational model input"):
        validate_rc_corotational_job_request(payload)
    # A declared fixed-guided profile is accepted only with its matching supports.
    payload = request()
    payload["model"]["nodes"] = payload["model"]["nodes"][:2]
    payload["model"]["elements"] = payload["model"]["elements"][:1]
    payload["model"]["supports"].append({"node": "N2", "dofs": ["UY", "RZ"]})
    payload["model"]["loads"][0]["node"] = "N2"
    payload["model"]["loads"][0]["components"].update(FX=1.0, FY=0.0)
    payload["config"].update(
        control_node_id="N2",
        control_component="UX",
        fixed_nodal_loads=[],
        experimental_fixed_guided_axial=True,
    )
    supported = validate_rc_corotational_job_request(payload)
    assert supported.api_kwargs()["experimental_fixed_guided_axial"]
    payload["config"]["experimental_fixed_guided_axial"] = False
    with pytest.raises(ValueError, match="unsupported corotational model input"):
        validate_rc_corotational_job_request(payload)


@pytest.mark.parametrize(
    "path,value",
    [
        (("source_revision",), "c" * 40),
        (("config", "targets_m"), [-1e-6, -3e-6]),
        (("config", "fixed_nodal_loads", 0, 2), -0.02),
        (("config", "config", "maximum_iterations"), 39),
        (("config", "preload_config", "max_iterations"), 24),
        (("config", "maximum_attempt_count"), 254),
        (("config", "maximum_subdivision_depth"), 7),
        (("execution_config", "attempt_limit_per_call"), 2),
        (("execution_config", "maximum_api_invocations"), 99),
        (("model", "materials", 0, "yield_stress_mpa"), 251.0),
    ],
)
def test_full_authored_source_policy_and_inputs_bound_into_resume_hash(path, value):
    payload = request()
    before = validate_rc_corotational_job_request(payload)
    change(payload, path, value)
    after = validate_rc_corotational_job_request(payload)
    assert after.request_hash != before.request_hash
    assert after.resume_contract_hash != before.resume_contract_hash


def test_strict_json_transport_and_supported_execution_limits():
    payload = request()
    raw = rc_corotational_job_canonical_bytes(payload)
    reordered = json.dumps(payload, indent=2).encode()
    assert validate_rc_corotational_job_request(
        raw
    ) == validate_rc_corotational_job_request(reordered)
    for invalid in (
        b'{"schema_version":"a","schema_version":"b"}',
        b'{"config":NaN}',
        b'{"config":1e309}',
        b"[]",
        b"not json",
        b" " * (16 * 1024 * 1024 + 1),
    ):
        with pytest.raises(ValueError):
            validate_rc_corotational_job_request(invalid)
    for invalid in ({1: "coerced key"}, {"x": (1, 2)}, {"x": object()}):
        with pytest.raises(ValueError):
            rc_corotational_job_canonical_bytes(invalid)
    payload["config"]["targets_m"] = [1e-6 * (i + 1) for i in range(255)]
    payload["config"]["maximum_attempt_count"] = 4096
    payload["config"]["maximum_subdivision_depth"] = 20
    payload["execution_config"].update(
        attempt_limit_per_call=4096, maximum_api_invocations=100000
    )
    assert validate_rc_corotational_job_request(payload).progress_total == 4096
    payload["config"]["maximum_attempt_count"] = 1
    payload["config"]["maximum_subdivision_depth"] = 0
    payload["execution_config"].update(
        attempt_limit_per_call=1, maximum_api_invocations=1
    )
    assert validate_rc_corotational_job_request(payload).progress_total == 1
