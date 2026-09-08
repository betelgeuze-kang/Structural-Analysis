"""Experimental 3D CLI contracts, with shared real solver observations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 uses the declared compatibility dependency.
    import tomli as tomllib

import pytest

import structural_analysis.api._output_integrity as output_integrity
import structural_analysis.api.frame3d_direct_control as api
import structural_analysis.api.frame3d_direct_control_cli as cli
from structural_analysis.api.frame3d_direct_control_request import (
    bounded_frame3d_direct_control_request_payload,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    StatefulCorotationalFrame3DDisplacementControlConfig,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "examples/bounded_frame3d_direct_control.model-ir.v2.json"
AXIAL_MODEL_PATH = (
    ROOT / "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
)
# This is deliberately a caller declaration, not a source attestation.
SOURCE_REVISION = "a" * 40
CYCLIC_TARGETS = (0.003, 0.006, 0.001, -0.004, 0.002)


def _config(*targets, control_dof="UY", **solver_settings):
    return api.BoundedFrame3DDirectControlConfig(
        "N2",
        control_dof,
        tuple(targets or (-8.0e-6, -1.6e-5)),
        StatefulCorotationalFrame3DDisplacementControlConfig(**solver_settings),
    )


def _write_request(path, config):
    path.write_text(
        json.dumps(
            bounded_frame3d_direct_control_request_payload(config),
            allow_nan=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _inputs(workspace, *, config=None, model_path=MODEL_PATH, checkpoint=None):
    workspace.mkdir(parents=True, exist_ok=True)
    model = workspace / "model.json"
    model.write_bytes(model_path.read_bytes())
    request = _write_request(workspace / "request.json", config or _config())
    restart = None
    if checkpoint is not None:
        restart = workspace / "restart.json"
        restart.write_bytes(checkpoint)
    return {"model": model, "request": request, "restart": restart}


def _outputs(workspace, *, old=False):
    paths = {
        "result": workspace / "result.json",
        "report": workspace / "execution-report.json",
        "checkpoint": workspace / "checkpoint.json",
    }
    if old:
        for key, path in paths.items():
            path.write_bytes(f"old {key}\n".encode())
    return paths


def _argv(inputs, outputs, *, revision=SOURCE_REVISION, checkpoint_output=True):
    args = [
        str(inputs["model"]),
        "--request",
        str(inputs["request"]),
        "--source-revision",
        revision,
        "--out",
        str(outputs["result"]),
        "--report-out",
        str(outputs["report"]),
    ]
    if inputs["restart"] is not None:
        args += ["--restart-checkpoint", str(inputs["restart"])]
    if checkpoint_output:
        args += ["--checkpoint-out", str(outputs["checkpoint"])]
    return args


def _bytes(paths):
    return {key: path.read_bytes() for key, path in paths.items() if path is not None}


def _assert_preserved(paths, before):
    assert _bytes(paths) == before
    assert not list(next(iter(paths.values())).parent.glob(".*.tmp"))


def _forbid_solver(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid CLI input must not enter the numerical solver")

    monkeypatch.setattr(
        api, "run_stateful_corotational_frame3d_displacement_control_path", unexpected
    )


def _assert_parser_error(args):
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


@pytest.fixture(scope="module")
def actual_runs(tmp_path_factory):
    """Four real CLI/API calls; later mutations reuse their immutable results."""
    workspace = tmp_path_factory.mktemp("frame3d-cli-actual")
    configurations = {
        "monotonic": _config(),
        "rotation": _config(1.0e-6, control_dof="RX"),
        "partial": _config(maximum_path_solve_attempts=1),
        "zero_completed": _config(maximum_iterations=1, maximum_target_cutback_depth=0),
    }
    records = {}
    original_analyze = cli.analyze_bounded_frame3d_direct_control_model_ir
    original_solver = api.run_stateful_corotational_frame3d_displacement_control_path
    solver_calls = 0

    def counted_solver(*args, **kwargs):
        nonlocal solver_calls
        solver_calls += 1
        return original_solver(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            api,
            "run_stateful_corotational_frame3d_displacement_control_path",
            counted_solver,
        )
        for name, config in configurations.items():
            inputs = _inputs(workspace / name, config=config)
            outputs = _outputs(workspace / name, old=True)
            before = _bytes(inputs)
            retained = []

            def capture_result(*args, **kwargs):
                result = original_analyze(*args, **kwargs)
                retained.append(result)
                return result

            patch.setattr(
                cli, "analyze_bounded_frame3d_direct_control_model_ir", capture_result
            )
            code = cli.main(_argv(inputs, outputs))
            assert len(retained) == 1
            result = retained[0]
            assert code == (0 if result.status == "ready" else 2)
            _assert_preserved(inputs, before)
            assert json.loads(outputs["result"].read_bytes()) == result.to_dict()
            records[name] = {
                "inputs": inputs,
                "outputs": outputs,
                "result": result,
                "code": code,
                "report": json.loads(outputs["report"].read_bytes()),
            }
    assert solver_calls == len(configurations)
    return records


PROCESS_OBSERVER = textwrap.dedent(
    """\
    import json
    import os
    import sys
    import structural_analysis.api.frame3d_direct_control as api
    from structural_analysis.api.frame3d_direct_control_cli import main

    calls = 0
    original = api.run_stateful_corotational_frame3d_displacement_control_path
    def counted(*args, **kwargs):
        global calls
        calls += 1
        return original(*args, **kwargs)
    api.run_stateful_corotational_frame3d_displacement_control_path = counted
    code = main(sys.argv[1:])
    print(json.dumps({"pid": os.getpid(), "solver_calls": calls, "exit_code": code}))
    raise SystemExit(code)
    """
)


def _run_process(args, cwd):
    completed = subprocess.run(
        [sys.executable, "-c", PROCESS_OBSERVER, *args],
        cwd=cwd,
        env={
            "PATH": os.defpath,
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONHASHSEED": "0",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    observation = json.loads(completed.stdout.splitlines()[-1])
    assert observation["solver_calls"] == 1
    assert observation["exit_code"] == 0
    assert observation["pid"] != os.getpid()
    return observation


@pytest.fixture(scope="module")
def cyclic_runs(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("frame3d-cli-cyclic")
    records = {}
    for name, targets in (
        ("prefix", CYCLIC_TARGETS[:2]),
        ("suffix", CYCLIC_TARGETS[2:]),
        ("full", CYCLIC_TARGETS),
    ):
        checkpoint = (
            records["prefix"]["outputs"]["checkpoint"].read_bytes()
            if name == "suffix"
            else None
        )
        inputs = _inputs(
            workspace / name,
            config=_config(
                *targets,
                control_dof="UX",
                allow_direction_reversal=True,
                maximum_direction_reversals=4,
            ),
            model_path=AXIAL_MODEL_PATH,
            checkpoint=checkpoint,
        )
        outputs = _outputs(workspace / name)
        before = _bytes(inputs)
        observation = _run_process(_argv(inputs, outputs), workspace / name)
        _assert_preserved(inputs, before)
        records[name] = {
            "inputs": inputs,
            "outputs": outputs,
            "observation": observation,
            "result": json.loads(outputs["result"].read_bytes()),
            "report": json.loads(outputs["report"].read_bytes()),
        }
    assert len({row["observation"]["pid"] for row in records.values()}) == 3
    return records


def test_cli_monotonic_matches_retained_real_api_result(actual_runs):
    row = actual_runs["monotonic"]
    result = row["result"]
    assert row["code"] == 0
    assert result.contract_pass is True
    assert result.metrics["completed_requested_target_count"] == 2
    assert result.metrics["final_control_coordinate"] == pytest.approx(-1.6e-5)
    assert (
        row["outputs"]["checkpoint"].read_bytes() == result.checkpoint_artifact_bytes()
    )
    assert api.validate_bounded_frame3d_direct_control_result(result) is result


def test_cli_rotation_keeps_rad_and_control_global_dof(actual_runs):
    result = actual_runs["rotation"]["result"]
    assert result.status == "ready"
    assert result.control["control_dof"] == "RX"
    assert result.control["control_unit"] == "rad"
    assert result.control["control_global_dof"] == 9
    assert result.metrics["final_control_coordinate"] == pytest.approx(1.0e-6)
    assert (
        result.metrics["scaled_residual_inf_norm"]
        <= result.metrics["scaled_residual_tolerance"]
    )


def test_cli_blocked_retains_exact_partial_checkpoint_and_counts(actual_runs):
    row = actual_runs["partial"]
    result = row["result"]
    assert row["code"] == 2
    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.metrics["requested_target_count"] == 2
    assert result.metrics["completed_requested_target_count"] == 1
    assert result.checkpoint_artifact["exact_resume_supported"] is True
    assert (
        row["outputs"]["checkpoint"].read_bytes() == result.checkpoint_artifact_bytes()
    )


def test_cli_zero_completed_is_blocked_without_promoting_genesis(actual_runs):
    row = actual_runs["zero_completed"]
    result = row["result"]
    assert row["code"] == 2
    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.metrics["completed_requested_target_count"] == 0
    assert result.metrics["final_control_coordinate"] == 0.0
    assert result.terminal_reason_code
    assert all(
        state["accumulated_plastic_strain"] == 0.0 for state in result.material_states
    )


def test_cli_fresh_process_cyclic_restart_matches_full_terminal_bytes(cyclic_runs):
    suffix, full = (cyclic_runs[name] for name in ("suffix", "full"))
    assert (
        suffix["outputs"]["checkpoint"].read_bytes()
        == full["outputs"]["checkpoint"].read_bytes()
    )
    for key in (
        "checkpoint_artifact",
        "source_binding",
        "model_hash",
        "node_displacements",
        "support_reactions",
        "material_states",
    ):
        assert suffix["result"][key] == full["result"][key], key
    for key in (
        "accepted_target_chain_hash",
        "final_load_factor",
        "final_control_coordinate",
        "cumulative_direction_reversal_count",
    ):
        assert suffix["result"]["metrics"][key] == full["result"]["metrics"][key], key
    assert suffix["result"]["metrics"]["resumed_with_direction_reversal"] is True
    assert full["result"]["metrics"]["cumulative_direction_reversal_count"] == 2


def _assert_execution_report(report, result, inputs):
    payload = deepcopy(report)
    reported_hash = payload.pop("report_hash")
    assert canonical_hash(payload) == reported_hash
    assert (
        report["schema_version"] == "bounded-frame3d-direct-control-execution-report.v1"
    )
    assert report["source_revision"] == SOURCE_REVISION
    assert report["source_revision_is_attestation"] is False
    assert report["result_contract_validation_passed"] is True
    assert report["execution_contract_pass"] is result["contract_pass"]
    assert report["status"] == result["status"]
    for key in (
        "result_hash",
        "source_binding",
        "model_hash",
        "solver_result_hash",
        "terminal_reason_code",
        "checkpoint_artifact",
        "authority",
    ):
        assert report[key] == result[key], key
    assert report["request_hash"] == result["control"]["request_hash"]
    assert report["resume_contract_hash"] == result["control"]["resume_contract_hash"]
    identities = {row["role"]: row for row in report["inputs"]}
    expected_roles = {"model", "request"}
    if inputs["restart"] is not None:
        expected_roles.add("restart_checkpoint")
    assert set(identities) == expected_roles
    assert len(report["inputs"]) == len(expected_roles)
    for role, identity in identities.items():
        path = inputs["restart" if role == "restart_checkpoint" else role]
        raw = path.read_bytes()
        assert identity == {
            "role": role,
            "path": str(path.resolve()),
            "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "byte_length": len(raw),
        }
    assert result["authority"] == {
        "candidate_api_exposed": True,
        "capability_registry_public": False,
        "workbench_execution": False,
        "numerical_authority": "bounded_candidate",
        "recovery_authority": "node_and_support_candidate",
        "external_vv_level": 0,
        "independent_operator_attached": False,
        "design_authority": False,
        "formal_verification_level_2": False,
        "release_eligible": False,
    }


def test_all_real_reports_bind_exact_inputs_and_keep_experimental_authority(
    actual_runs,
    cyclic_runs,
):
    for row in actual_runs.values():
        _assert_execution_report(row["report"], row["result"].to_dict(), row["inputs"])
    for row in cyclic_runs.values():
        _assert_execution_report(row["report"], row["result"], row["inputs"])


def test_cli_validates_before_publication(tmp_path, monkeypatch, actual_runs):
    inputs = _inputs(tmp_path)
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    result = actual_runs["monotonic"]["result"]
    authority = dict(result.authority)
    authority["capability_registry_public"] = True
    forged = replace(result, authority=authority)
    payload = forged.to_dict()
    payload.pop("result_hash")
    forged = replace(forged, result_hash=canonical_hash(payload))
    monkeypatch.setattr(
        cli, "analyze_bounded_frame3d_direct_control_model_ir", lambda *a, **kw: forged
    )
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(outputs, before)


@pytest.mark.parametrize("mismatch", ["control", "source"])
def test_other_valid_result_cannot_bind_current_request(
    tmp_path,
    monkeypatch,
    actual_runs,
    mismatch,
):
    inputs = _inputs(tmp_path)
    if mismatch == "source":
        document = json.loads(inputs["model"].read_bytes())
        document["model_id"] += "-different-source"
        inputs["model"].write_text(json.dumps(document), encoding="utf-8")
    result = actual_runs["rotation" if mismatch == "control" else "monotonic"]["result"]
    assert api.validate_bounded_frame3d_direct_control_result(result) is result
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    monkeypatch.setattr(
        cli, "analyze_bounded_frame3d_direct_control_model_ir", lambda *a, **kw: result
    )
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(outputs, before)


@pytest.mark.parametrize("changed_input", ["model", "request", "restart"])
def test_input_bytes_changed_during_analysis_prevent_publication(
    tmp_path,
    monkeypatch,
    actual_runs,
    changed_input,
):
    result = actual_runs["monotonic"]["result"]
    inputs = _inputs(tmp_path, checkpoint=result.checkpoint_artifact_bytes())
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)

    def changed(*args, **kwargs):
        path = inputs[changed_input]
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(cli, "analyze_bounded_frame3d_direct_control_model_ir", changed)
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(outputs, before)


def test_output_symlink_rebinding_during_analysis_preserves_targets(
    tmp_path,
    monkeypatch,
    actual_runs,
):
    inputs = _inputs(tmp_path)
    originals = _outputs(tmp_path, old=True)
    before = _bytes(originals)
    result_alias = tmp_path / "result-link.json"
    result_alias.symlink_to(originals["result"])
    outputs = {**originals, "result": result_alias}
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_bytes(b"unrelated original\n")

    def changed(*args, **kwargs):
        result_alias.unlink()
        result_alias.symlink_to(unrelated)
        return actual_runs["monotonic"]["result"]

    monkeypatch.setattr(cli, "analyze_bounded_frame3d_direct_control_model_ir", changed)
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(originals, before)
    assert unrelated.read_bytes() == b"unrelated original\n"


@pytest.mark.parametrize("replacement_number", [2, 3])
def test_cli_shared_atomic_bundle_rolls_back_caught_replace_failure(
    tmp_path,
    monkeypatch,
    actual_runs,
    replacement_number,
):
    inputs = _inputs(tmp_path)
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    monkeypatch.setattr(
        cli,
        "analyze_bounded_frame3d_direct_control_model_ir",
        lambda *args, **kwargs: actual_runs["monotonic"]["result"],
    )
    _forbid_solver(monkeypatch)
    original_replace = output_integrity.os.replace
    calls = 0

    def fail_once(source, destination):
        nonlocal calls
        calls += 1
        if calls == replacement_number:
            raise OSError("injected caught output replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr(output_integrity.os, "replace", fail_once)
    _assert_parser_error(_argv(inputs, outputs))
    assert calls > replacement_number  # At least one previously replaced file restored.
    _assert_preserved(outputs, before)


def test_unavailable_exact_checkpoint_clears_explicit_stale_output(
    tmp_path,
    monkeypatch,
    actual_runs,
):
    # A transport-only derivative models an incomplete cutback boundary. The
    # original blocked numerical observation is not claimed to have this path.
    original = actual_runs["partial"]["result"]
    metrics = dict(original.metrics)
    metrics.update(
        {
            "final_checkpoint_at_requested_target_boundary": False,
            "exact_checkpoint_resume_supported": False,
        }
    )
    artifact = dict(original.checkpoint_artifact)
    artifact.update(
        {
            "available": False,
            "schema_version": None,
            "artifact_hash": None,
            "byte_length": 0,
            "exact_resume_supported": False,
        }
    )
    result = replace(
        original,
        metrics=metrics,
        checkpoint_artifact=artifact,
        _checkpoint_artifact_bytes=None,
    )
    payload = result.to_dict()
    payload.pop("result_hash")
    result = replace(result, result_hash=canonical_hash(payload))
    assert api.validate_bounded_frame3d_direct_control_result(result) is result
    inputs = _inputs(tmp_path, config=_config(maximum_path_solve_attempts=1))
    outputs = _outputs(tmp_path, old=True)
    monkeypatch.setattr(
        cli, "analyze_bounded_frame3d_direct_control_model_ir", lambda *a, **kw: result
    )
    _forbid_solver(monkeypatch)
    assert cli.main(_argv(inputs, outputs)) == 2
    assert not outputs["checkpoint"].exists()
    report = json.loads(outputs["report"].read_bytes())
    assert report["execution_contract_pass"] is False
    assert report["result_contract_validation_passed"] is True
    assert report["checkpoint_artifact"]["available"] is False


def test_checkpoint_output_is_optional_and_does_not_clear_unrequested_file(
    tmp_path,
    monkeypatch,
    actual_runs,
):
    inputs = _inputs(tmp_path)
    outputs = _outputs(tmp_path, old=True)
    old_checkpoint = outputs["checkpoint"].read_bytes()
    monkeypatch.setattr(
        cli,
        "analyze_bounded_frame3d_direct_control_model_ir",
        lambda *args, **kwargs: actual_runs["monotonic"]["result"],
    )
    _forbid_solver(monkeypatch)
    assert cli.main(_argv(inputs, outputs, checkpoint_output=False)) == 0
    assert outputs["checkpoint"].read_bytes() == old_checkpoint
    assert (
        json.loads(outputs["report"].read_bytes())["checkpoint_artifact"]["available"]
        is True
    )


@pytest.mark.parametrize("mutation", ["bytes", "config"])
def test_valid_checkpoint_changed_or_bound_to_other_config_fails_before_solver(
    tmp_path,
    monkeypatch,
    cyclic_runs,
    mutation,
):
    checkpoint = cyclic_runs["prefix"]["outputs"]["checkpoint"].read_bytes()
    config = _config(
        *CYCLIC_TARGETS[2:],
        control_dof="UX",
        allow_direction_reversal=True,
        maximum_direction_reversals=3 if mutation == "config" else 4,
    )
    inputs = _inputs(
        tmp_path, config=config, model_path=AXIAL_MODEL_PATH, checkpoint=checkpoint
    )
    if mutation == "bytes":
        payload = json.loads(checkpoint)
        payload["artifact_hash"] = "sha256:" + "0" * 64
        inputs["restart"].write_text(json.dumps(payload), encoding="utf-8")
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(outputs, before)


@pytest.mark.parametrize("revision", ["", "abc123", "g" * 40, "sha256:" + "a" * 40])
def test_invalid_source_revision_preserves_outputs(tmp_path, monkeypatch, revision):
    inputs = _inputs(tmp_path)
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs, revision=revision))
    _assert_preserved(outputs, before)


@pytest.mark.parametrize("input_name", ["model", "request", "restart"])
@pytest.mark.parametrize("alias", ["exact", "symlink", "hardlink", "nested"])
def test_output_aliases_protected_input_before_any_input_read(
    tmp_path,
    monkeypatch,
    input_name,
    alias,
):
    inputs = _inputs(tmp_path, checkpoint=b"original restart bytes\n")
    outputs = _outputs(tmp_path, old=True)
    before_inputs, before_outputs = _bytes(inputs), _bytes(outputs)
    protected = inputs[input_name]
    alias_path = tmp_path / "alias.json"
    if alias == "exact":
        alias_path = protected
    elif alias == "symlink":
        alias_path.symlink_to(protected)
    elif alias == "hardlink":
        os.link(protected, alias_path)
    else:
        alias_path = protected / "nested.json"
    invocation_outputs = {**outputs, "checkpoint": alias_path}
    original_open = Path.open
    protected_resolved = {
        path.resolve() for path in inputs.values() if path is not None
    }

    def no_input_read(path, mode="r", *args, **kwargs):
        if "r" in mode and path.resolve() in protected_resolved:
            pytest.fail("path validation must precede reading any protected input")
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", no_input_read)
        _forbid_solver(patch)
        _assert_parser_error(_argv(inputs, invocation_outputs))
    _assert_preserved(inputs, before_inputs)
    _assert_preserved(outputs, before_outputs)


@pytest.mark.parametrize("collision", ["same", "nested", "symlink", "hardlink"])
def test_output_bundle_collision_preserves_existing_files(
    tmp_path, monkeypatch, collision
):
    inputs = _inputs(tmp_path)
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    invocation = dict(outputs)
    if collision == "same":
        invocation["report"] = outputs["result"]
    elif collision == "nested":
        invocation["checkpoint"] = outputs["result"] / "artifact.json"
    else:
        link = tmp_path / "report-alias.json"
        if collision == "symlink":
            link.symlink_to(outputs["result"])
        else:
            os.link(outputs["result"], link)
        invocation["report"] = link
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, invocation))
    _assert_preserved(outputs, before)


@pytest.mark.parametrize(
    ("input_name", "contents"),
    [
        ("request", b'{"schema_version":"one","schema_version":"two"}'),
        ("request", b'{"control_targets":[NaN]}'),
        ("request", b'{"broken":'),
        ("model", b'{"schema_version":"one","schema_version":"two"}'),
        ("model", b'{"coordinate":Infinity}'),
        ("restart", b'{"broken":'),
    ],
)
def test_invalid_json_fails_without_solver_or_output_changes(
    tmp_path,
    monkeypatch,
    input_name,
    contents,
):
    inputs = _inputs(tmp_path, checkpoint=b"{}")
    inputs[input_name].write_bytes(contents)
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(outputs, before)


@pytest.mark.parametrize(
    ("input_name", "limit"),
    [
        ("model", 16 * 1024 * 1024),
        ("request", 128 * 1024),
        ("restart", 8 * 1024 * 1024),
    ],
)
def test_oversized_inputs_fail_before_solver(tmp_path, monkeypatch, input_name, limit):
    inputs = _inputs(tmp_path, checkpoint=b"{}")
    inputs[input_name].write_bytes(b" " * (limit + 1))
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(outputs, before)


@pytest.mark.parametrize(
    "mutation", ["unknown", "bool_count", "bad_dof", "zero_target", "zero_load"]
)
def test_invalid_config_and_model_semantics_preserve_outputs(
    tmp_path, monkeypatch, mutation
):
    inputs = _inputs(tmp_path)
    target = inputs["model"] if mutation == "zero_load" else inputs["request"]
    payload = json.loads(target.read_bytes())
    if mutation == "unknown":
        payload["unrecognized"] = True
    elif mutation == "bool_count":
        payload["solver_config"]["maximum_iterations"] = True
    elif mutation == "bad_dof":
        payload["control_dof"] = "FX"
    elif mutation == "zero_target":
        payload["control_targets"] = [0.0]
    else:
        load = payload["load_patterns"][0]["nodal_loads"][0]["components_si"]
        load.update({key: 0.0 for key in load})
    target.write_text(json.dumps(payload), encoding="utf-8")
    outputs = _outputs(tmp_path, old=True)
    before = _bytes(outputs)
    _forbid_solver(monkeypatch)
    _assert_parser_error(_argv(inputs, outputs))
    _assert_preserved(outputs, before)


def test_console_entry_and_module_help_are_available():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["scripts"][
        "structural-analysis-bounded-frame3d-control"
    ] == ("structural_analysis.api.frame3d_direct_control_cli:main")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "structural_analysis.api.frame3d_direct_control_cli",
            "--help",
        ],
        cwd=ROOT,
        env={"PATH": os.defpath, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    for option in (
        "--request",
        "--source-revision",
        "--restart-checkpoint",
        "--checkpoint-out",
    ):
        assert option in completed.stdout
