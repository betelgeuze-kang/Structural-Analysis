"""Actual isolated-process continuation of the bounded experimental 3D API."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = (
    ROOT / "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
)
TARGETS = (0.003, 0.006, 0.001, -0.004, 0.002)

# Every invocation imports the real API in a new interpreter. Only paths to the
# original ModelIR, request, and (for resume) persisted canonical checkpoint cross
# the process boundary; no Python result, adapter, or material state is passed.
WORKER = textwrap.dedent(
    """\
    import json
    import os
    from pathlib import Path
    import sys

    import structural_analysis.api.frame3d_direct_control as api
    from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
        StatefulCorotationalFrame3DDisplacementControlConfig,
    )
    from structural_analysis.model_ir.loader import load_model_ir_v2

    model_path, request_path, checkpoint_path, output_path = sys.argv[1:]
    request = json.loads(Path(request_path).read_bytes())
    config = api.BoundedFrame3DDirectControlConfig(
        control_node_id="N2",
        control_dof="UX",
        control_targets=tuple(request["control_targets"]),
        solver_config=StatefulCorotationalFrame3DDisplacementControlConfig(
            allow_direction_reversal=True,
            maximum_direction_reversals=request["maximum_direction_reversals"],
        ),
    )
    document = load_model_ir_v2(model_path)
    checkpoint = (
        None if checkpoint_path == "-" else Path(checkpoint_path).read_bytes()
    )
    solver_calls = 0
    real_run = api.run_stateful_corotational_frame3d_displacement_control_path

    def counted_run(*args, **kwargs):
        global solver_calls
        solver_calls += 1
        return real_run(*args, **kwargs)

    # This observer delegates every call to the real solver. It proves rejected
    # restart inputs fail before solver entry, without injecting a solver result.
    api.run_stateful_corotational_frame3d_displacement_control_path = counted_run
    try:
        result = api.analyze_bounded_frame3d_direct_control_model_ir(
            document, config, restart_checkpoint_artifact=checkpoint
        )
    except api.BoundedFrame3DDirectControlError as error:
        print(json.dumps({
            "pid": os.getpid(), "solver_calls": solver_calls,
            "error_code": error.code, "error_path": error.path,
        }, allow_nan=False, sort_keys=True))
        sys.exit(2)

    artifact_path = Path(output_path).with_suffix(".checkpoint.json")
    artifact_path.write_bytes(result.checkpoint_artifact_bytes())
    Path(output_path).write_text(
        json.dumps(result.to_dict(), allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({
        "pid": os.getpid(), "solver_calls": solver_calls,
        "status": result.status,
    }, allow_nan=False, sort_keys=True))
    """
)


def _request(path: Path, targets, *, maximum_reversals: int = 4) -> Path:
    path.write_text(
        json.dumps(
            {
                "control_targets": targets,
                "maximum_direction_reversals": maximum_reversals,
            },
            allow_nan=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _run(
    model_path: Path,
    request_path: Path,
    output_path: Path,
    *,
    checkpoint_path: Path | None = None,
    expected_error: str | None = None,
) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(model_path),
            str(request_path),
            str(checkpoint_path) if checkpoint_path else "-",
            str(output_path),
        ],
        cwd=output_path.parent,
        # Do not inherit ambient credentials, Python hooks, or application state.
        # Thread bounds avoid competing with unrelated runtime measurements.
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
    assert completed.returncode == (2 if expected_error else 0), completed.stderr
    observation = json.loads(completed.stdout)
    assert observation["pid"] != os.getpid()
    if expected_error:
        assert observation["error_code"] == expected_error
        assert observation["solver_calls"] == 0
        assert not output_path.exists()
        assert not output_path.with_suffix(".checkpoint.json").exists()
    else:
        assert observation["solver_calls"] == 1
        assert observation["status"] == "ready"
    return observation


@pytest.fixture(scope="module")
def persisted_runs(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("frame3d-process-restart")
    model_path = workspace / "model.json"
    source_bytes = MODEL_PATH.read_bytes()
    model_path.write_bytes(source_bytes)
    prefix_request = _request(workspace / "prefix-request.json", TARGETS[:2])
    suffix_request = _request(workspace / "suffix-request.json", TARGETS[2:])
    full_request = _request(workspace / "full-request.json", TARGETS)

    prefix_path = workspace / "prefix-result.json"
    prefix = _run(model_path, prefix_request, prefix_path)
    checkpoint_path = prefix_path.with_suffix(".checkpoint.json")
    prefix_bytes = checkpoint_path.read_bytes()
    # _run waits for process A to exit before process B can read its bytes.
    resumed_path = workspace / "resumed-result.json"
    resumed = _run(
        model_path,
        suffix_request,
        resumed_path,
        checkpoint_path=checkpoint_path,
    )
    full_path = workspace / "full-result.json"
    full = _run(model_path, full_request, full_path)
    assert len({prefix["pid"], resumed["pid"], full["pid"]}) == 3
    assert model_path.read_bytes() == source_bytes
    assert checkpoint_path.read_bytes() == prefix_bytes
    return {
        "workspace": workspace,
        "model_path": model_path,
        "suffix_request": suffix_request,
        "checkpoint_path": checkpoint_path,
        "prefix_bytes": prefix_bytes,
        "prefix_path": prefix_path,
        "resumed_path": resumed_path,
        "full_path": full_path,
    }


def test_fresh_process_resume_reproduces_exact_cyclic_terminal_bytes(
    persisted_runs,
) -> None:
    resumed_path = persisted_runs["resumed_path"]
    full_path = persisted_runs["full_path"]
    resumed = json.loads(resumed_path.read_bytes())
    full = json.loads(full_path.read_bytes())
    assert resumed_path.with_suffix(".checkpoint.json").read_bytes() == (
        full_path.with_suffix(".checkpoint.json").read_bytes()
    )
    for key in (
        "checkpoint_artifact",
        "source_binding",
        "model_hash",
        "node_displacements",
        "support_reactions",
        "material_states",
    ):
        assert resumed[key] == full[key], key
    for key in (
        "accepted_target_chain_hash",
        "final_load_factor",
        "final_control_coordinate",
        "cumulative_direction_reversal_count",
    ):
        assert resumed["metrics"][key] == full["metrics"][key], key
    assert full["metrics"]["path_mode"] == "cyclic_reversal"
    assert full["metrics"]["cumulative_direction_reversal_count"] == 2
    assert resumed["metrics"]["resumed_with_direction_reversal"] is True
    assert resumed["checkpoint_artifact"]["exact_resume_supported"] is True
    assert full["metrics"]["final_control_coordinate"] == pytest.approx(TARGETS[-1])


def test_process_results_retain_experimental_authority(persisted_runs) -> None:
    for key in ("prefix_path", "resumed_path", "full_path"):
        result = json.loads(persisted_runs[key].read_bytes())
        assert result["contract_pass"] is True
        assert result["metrics"]["fallback_used"] is False
        assert result["metrics"]["regularization_used"] is False
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


@pytest.mark.parametrize(
    "mutation", ("corrupted_bytes", "different_model", "different_config")
)
def test_persisted_restart_rejects_changed_inputs_before_solver(
    persisted_runs, mutation
) -> None:
    workspace = persisted_runs["workspace"]
    model_path = persisted_runs["model_path"]
    request_path = persisted_runs["suffix_request"]
    checkpoint_path = persisted_runs["checkpoint_path"]
    error = "bounded_frame3d_checkpoint_artifact_contract_mismatch"
    if mutation == "corrupted_bytes":
        corrupted = bytearray(persisted_runs["prefix_bytes"])
        marker = b'"artifact_hash":"sha256:'
        position = corrupted.index(marker) + len(marker)
        corrupted[position] = ord("1") if corrupted[position] == ord("0") else ord("0")
        checkpoint_path = workspace / "corrupted-checkpoint.json"
        checkpoint_path.write_bytes(corrupted)
        error = "bounded_frame3d_checkpoint_artifact_hash_mismatch"
    elif mutation == "different_model":
        payload = json.loads(model_path.read_bytes())
        payload["materials"][0]["parameters"]["elastic_modulus_pa"] = 210000000000.0
        model_path = workspace / "different-model.json"
        model_path.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    else:
        request_path = _request(
            workspace / "different-config.json", TARGETS[2:], maximum_reversals=3
        )
    _run(
        model_path,
        request_path,
        workspace / f"rejected-{mutation}.json",
        checkpoint_path=checkpoint_path,
        expected_error=error,
    )
    assert (
        persisted_runs["checkpoint_path"].read_bytes() == persisted_runs["prefix_bytes"]
    )
